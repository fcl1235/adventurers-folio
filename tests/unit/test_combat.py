# -*- coding: utf-8 -*-
"""P8c 验收：施法结算（G6）。

这一阶段之前引擎只会「算 DC 与攻击加值」，从没掷过骰子 —— 因为没有目标。
现在补上了目标侧（AC / 豁免 / 抗性）与三条判定通道（攻击 / 豁免 / 必中）。

这一组测试盯的都是**会算错数**的地方：

  1. 半伤要向下取整，而且只在「豁免成功 + save_effect: half」时发生
  2. 重击**加骰不加定值**（2d6+3 → 4d6+3，不是 ×2）
  3. 自然 20 必中、自然 1 必失手（哪怕加值够高）
  4. 抗性/免疫在重击与半伤**之后**才算
  5. 戏法成长看角色等级、升环看环位 —— 两条轴
  6. 未判定（`save_effect` 空）时不落库，别给一个看似完整的 0
  7. `apply=False` 不许改任何人的血
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import load_all, parse_spell
from dnd5r.kernel.errors import PluginError, RuleError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.rules.combat import (
    Casting, Target, casting_for, damage_expression, resolution_kind, resolve_spell,
)

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
WIZARD = "dnd2024.class.wizard"
FIGHTER = "dnd2024.class.fighter"
WARLOCK = "dnd2024.class.warlock"
CLERIC = "dnd2024.class.cleric"
INT_SCORES = {"str": 8, "dex": 14, "con": 14, "int": 18, "wis": 12, "cha": 10}
STR_SCORES = {"str": 16, "dex": 12, "con": 16, "int": 10, "wis": 10, "cha": 8}


def wizard(bundle, level=5):
    return api.new_character(bundle, WIZARD, level, INT_SCORES)


def _base(**kwargs):
    data = {
        "id": "dnd2024.spell.probe",
        "name": {"zh": "测试", "en": "Probe"},
        "level": 1,
        "school": "evocation",
        "text": {"zh": "测试", "en": "Probe"},
    }
    data.update(kwargs)
    return data


# --- 内容：豁免成功吃什么 ------------------------------------------------
class SaveEffectContentTest(unittest.TestCase):
    """`save_effect` 的三态必须真的分布出来，不能全是同一个值。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = load_all(PLUGINS)

    def test_three_states_exist(self):
        half = [s for s in self.bundle.spells.values() if s.save_effect == "half"]
        none = [s for s in self.bundle.spells.values() if s.save_effect == "none"]
        blank = [s for s in self.bundle.spells.values()
                 if s.save and s.damage and not s.save_effect]
        self.assertEqual((len(half), len(none), len(blank)), (46, 9, 9))

    def test_known_half_and_none(self):
        self.assertEqual(self.bundle.spells["dnd2024.spell.fireball"].save_effect, "half")
        self.assertEqual(self.bundle.spells["dnd2024.spell.sacred_flame"].save_effect, "none")
        # 「伤害与豁免是两件事」的代表：灼热金属的伤害是接触就吃
        self.assertEqual(self.bundle.spells["dnd2024.spell.heat_metal"].save_effect, "")
        # 攻击命中 + 另一次豁免：两条线，一个字段表达不了
        self.assertEqual(self.bundle.spells["dnd2024.spell.ice_knife"].save_effect, "")

    def test_requires_save(self):
        with self.assertRaises(PluginError):
            parse_spell(_base(save_effect="half", damage={"1": "1d6"}))

    def test_requires_damage(self):
        with self.assertRaises(PluginError):
            parse_spell(_base(save="dex", save_effect="half"))

    def test_rejects_unknown_value(self):
        with self.assertRaises(PluginError):
            parse_spell(_base(save="dex", save_effect="quarter", damage={"1": "1d6"}))


class AutoDamageContentTest(unittest.TestCase):
    """必中必须内容显式声明，不能从「有伤害骰 + 没 save/attack」推出来。"""

    def test_auto_damage_conflicts_with_attack(self):
        with self.assertRaises(PluginError):
            parse_spell(_base(auto_damage=True, attack="ranged", damage={"1": "1d6"}))

    def test_auto_damage_requires_damage(self):
        with self.assertRaises(PluginError):
            parse_spell(_base(auto_damage=True))

    def test_buff_spells_are_not_auto(self):
        """斩击 / 诅咒 / 印记的伤害表里有骰子，但它们**不是**「施放即结算」。

        这条一旦写成 auto，施法瞬间就会给目标扣一次还没发生的伤害。
        """
        bundle = load_all(PLUGINS)
        for spell_id in ("dnd2024.spell.divine_smite", "dnd2024.spell.hex",
                         "dnd2024.spell.hunters_mark", "dnd2024.spell.fire_shield"):
            spell = bundle.spells[spell_id]
            self.assertNotEqual(resolution_kind(spell), "auto", spell_id)
            self.assertEqual(resolution_kind(spell), "none", spell_id)


# --- 施法者这一侧 -------------------------------------------------------
class CastingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle

    def test_dc_and_attack_match_sheet(self):
        actor = wizard(self.bundle, 5)
        spell = self.bundle.spells["dnd2024.spell.fireball"]
        casting = casting_for(self.bundle, actor, spell)
        self.assertIsInstance(casting, Casting)
        self.assertEqual(casting.class_id, WIZARD)
        self.assertEqual(casting.ability, "int")
        # 8 + 熟练 3 + 智力 4
        self.assertEqual(casting.dc, 15)
        # 熟练 3 + 智力 4
        self.assertEqual(casting.attack, 7)

    def test_multiclass_must_specify(self):
        """两个职业都能放同一道法术时 DC 可能不同 —— 猜一个就是给玩家错的数。"""
        from dataclasses import replace

        from dnd5r.model.profile import ClassEntry, Profile

        base = api.new_character(self.bundle, WIZARD, 3, INT_SCORES)
        profile = Profile(classes=(ClassEntry.make(WIZARD, 3),
                                   ClassEntry.make(CLERIC, 3)))
        actor = replace(base, profile=profile)
        spell = self.bundle.spells["dnd2024.spell.detect_magic"]
        with self.assertRaises(RuleError) as ctx:
            casting_for(self.bundle, actor, spell)
        self.assertIn("指定", str(ctx.exception))
        picked = casting_for(self.bundle, actor, spell, class_id=CLERIC)
        self.assertEqual(picked.class_id, CLERIC)
        self.assertEqual(picked.ability, "wis")

    def test_non_caster_rejected(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, STR_SCORES)
        with self.assertRaises(RuleError) as ctx:
            casting_for(self.bundle, actor, self.bundle.spells["dnd2024.spell.fireball"])
        self.assertIn("没有能施放", str(ctx.exception))

    def test_spell_not_in_listed_class(self):
        actor = wizard(self.bundle, 5)
        with self.assertRaises(RuleError):
            casting_for(self.bundle, actor,
                        self.bundle.spells["dnd2024.spell.cure_wounds"], class_id=WIZARD)


# --- 两条轴：环位 vs 角色等级 -------------------------------------------
class DamageAxisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle

    def test_cantrip_scales_with_character_level(self):
        bolt = self.bundle.spells["dnd2024.spell.fire_bolt"]
        low = api.new_character(self.bundle, WIZARD, 1, INT_SCORES)
        high = api.new_character(self.bundle, WIZARD, 5, INT_SCORES)
        self.assertEqual(damage_expression(low, bolt, 0), "1d10")
        self.assertEqual(damage_expression(high, bolt, 0), "2d10")

    def test_leveled_spell_scales_with_slot(self):
        ball = self.bundle.spells["dnd2024.spell.fireball"]
        actor = wizard(self.bundle)
        self.assertEqual(damage_expression(actor, ball, 3), "8d6")
        self.assertEqual(damage_expression(actor, ball, 4), "9d6")

    def test_upcast_stacks_dice_not_total(self):
        """升环是「同一颗骰子多掷几次」：8d6 → 9d6，不是 8d6×2。"""
        ball = self.bundle.spells["dnd2024.spell.fireball"]
        self.assertEqual(ball.damage_at(9), "14d6")
        guide = self.bundle.spells["dnd2024.spell.guiding_bolt"]
        self.assertEqual(guide.damage_at(1), "4d6")
        self.assertEqual(guide.damage_at(3), "6d6")

    def test_upcast_only_where_data_says_so(self):
        """没有结构化升环的法术只给基础骰 —— 少算一个能被发现，多算一个看不出来。"""
        self.assertEqual(len([s for s in self.bundle.spells.values() if s.upcast_dice]), 37)
        # 治疗术的 "increases by 1d4" 加的是回复量，不该写成伤害升环
        self.assertEqual(self.bundle.spells["dnd2024.spell.healing_word"].upcast_dice, "")

    def test_beams_do_not_change_dice(self):
        """魔能爆的成长是**光束数**：骰子仍是 1d10，写成 damage 会凭空多 2d10。"""
        blast = self.bundle.spells["dnd2024.spell.eldritch_blast"]
        actor = api.new_character(self.bundle, WARLOCK, 5,
                                  {"str": 8, "dex": 14, "con": 14,
                                   "int": 10, "wis": 12, "cha": 18})
        self.assertEqual(damage_expression(actor, blast, 0), "1d10")
        report = resolve_spell(self.bundle, actor, blast.id, 0,
                               [Target(label="木桩", ac=10)], ScriptedRng([15, 5, 15, 5]))
        self.assertEqual(report["shots"], 2)
        self.assertEqual(len(report["rows"]), 2)

    def test_slot_below_spell_level_rejected(self):
        actor = wizard(self.bundle)
        with self.assertRaises(RuleError):
            resolve_spell(self.bundle, actor, "dnd2024.spell.fireball", 2,
                          [Target(label="木桩", ac=10)], ScriptedRng([]))


# --- 豁免通道 -----------------------------------------------------------
class SaveResolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle
        self.actor = wizard(self.bundle, 5)          # DC 15

    def test_failed_save_takes_full(self):
        # 8d6 全 4 = 32
        target = Target(label="哥布林", ac=15, saves={"dex": 2})
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fireball", 3,
                               [target], ScriptedRng([10] + [4] * 8))
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "failed")     # 10 + 2 = 12 < 15
        self.assertEqual(row["raw"], 32)
        self.assertEqual(row["damage"], 32)

    def test_successful_save_halves_down(self):
        # 11 + 2 = 13 < 15 仍然失败；用 13 通过：13 + 2 = 15 >= 15
        target = Target(label="哥布林", ac=15, saves={"dex": 2})
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fireball", 3,
                               [target], ScriptedRng([13] + [1] * 8))
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "succeeded")
        self.assertEqual(row["raw"], 4)               # 8 点的一半
        self.assertEqual(row["damage"], 4)

    def test_half_rounds_down(self):
        # 8d6 全 1 = 8 → 半伤 4；再试 7 点（不可能，8d6 最小 8），用 9 点：9 // 2 = 4
        target = Target(label="哥布林", ac=15, saves={"dex": 2})
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fireball", 3,
                               [target], ScriptedRng([20] + [1] * 7 + [2]))
        row = report["rows"][0]
        self.assertEqual(row["raw"], 4)               # 9 // 2
        self.assertEqual(row["damage"], 4)

    def test_save_effect_none_means_zero(self):
        """圣火豁免成功 = 无伤（`save_effect: none`），不是半伤。"""
        cleric = api.new_character(self.bundle, CLERIC, 5, INT_SCORES)
        target = Target(label="哥布林", ac=15, saves={"dex": 6})
        report = resolve_spell(self.bundle, cleric, "dnd2024.spell.sacred_flame", 0,
                               [target], ScriptedRng([15]))
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "succeeded")
        self.assertEqual(row["damage"], 0)
        self.assertIn("不受伤害", row["note"])

    def test_undecided_save_effect_does_not_land(self):
        """灼热金属：豁免成功后的伤害未判定 —— 掷骰给人看，但不许落库。"""
        bard = api.new_character(
            self.bundle, "dnd2024.class.bard", 5,
            {"str": 8, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 18})
        target = Target(label="铁甲兵", ac=15, saves={"con": 8})
        report = resolve_spell(self.bundle, bard, "dnd2024.spell.heat_metal", 2,
                               [target], ScriptedRng([20, 5, 5]), apply=True)
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "succeeded")
        self.assertEqual(row["damage"], 0)
        self.assertIsNone(row["applied"])
        self.assertIn("未判定", row["note"])
        self.assertIn("未判定", "".join(report["notes"]))

    def test_save_spell_without_damage_still_judges(self):
        """控制类法术没有伤害骰，但**豁免结论**照样有用。"""
        target = Target(label="卫兵", ac=15, saves={"wis": 0})
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.hold_person", 2,
                               [target], ScriptedRng([3]))
        row = report["rows"][0]
        self.assertEqual(report["kind"], "save")
        self.assertEqual(row["outcome"], "failed")
        self.assertEqual(row["damage"], 0)
        self.assertIn("只结算判定", "".join(report["notes"]))


# --- 攻击通道 -----------------------------------------------------------
class AttackResolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle
        self.actor = wizard(self.bundle, 5)          # 法术攻击 +7

    def test_hit_deals_damage(self):
        target = Target(label="木桩", ac=13)
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fire_bolt", 0,
                               [target], ScriptedRng([10, 5, 6]))
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "hit")       # 10 + 7 = 17 >= 13
        self.assertEqual(row["damage"], 11)           # 2d10（5 级）= 11

    def test_miss_deals_nothing(self):
        target = Target(label="铁罐头", ac=25)
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fire_bolt", 0,
                               [target], ScriptedRng([10]))
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "miss")
        self.assertEqual(row["damage"], 0)
        self.assertEqual(row["damage_roll"], "")

    def test_natural_twenty_crits_and_doubles_dice(self):
        target = Target(label="木桩", ac=13)
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fire_bolt", 0,
                               [target], ScriptedRng([20, 5, 6, 7, 8]))
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "critical")
        self.assertEqual(row["damage_dice"], "4d10")  # 2d10 翻倍
        self.assertEqual(row["damage"], 26)           # 5+6+7+8

    def test_natural_one_always_misses(self):
        # 加值 +7 也救不回自然 1（2024：d20 出 1 必然失手）
        target = Target(label="木桩", ac=2)
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fire_bolt", 0,
                               [target], ScriptedRng([1]))
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "miss")
        self.assertEqual(row["damage"], 0)

    def test_crit_does_not_double_flat(self):
        """重击加骰不加定值：2d6+3 重击是 4d6+3（+18），不是 (2d6+3)×2。"""
        from dnd5r.kernel.dice import parse

        from dnd5r.rules.combat import _land_damage

        row = {"damage": 0, "raw": 0, "damage_dice": "", "damage_roll": "",
               "defense": "", "note": ""}
        spell = self.bundle.spells["dnd2024.spell.fire_bolt"]
        target = Target(label="木桩", ac=10)
        # 4d6 全 1 = 4，+3 = 7；若是 ×2 会得到 (2d6 全 1 + 3) × 2 = 10
        _land_damage(row, parse("2d6+3"), spell, target, 2,
                     rng=ScriptedRng([1, 1, 1, 1]))
        self.assertEqual(row["raw"], 7)


# --- 抗性 / 免疫 --------------------------------------------------------
class DefenseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle
        self.actor = wizard(self.bundle, 5)

    def test_resistance_halves_after_crit(self):
        target = Target(label="火元素", ac=10, resistances=frozenset({"fire"}))
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fire_bolt", 0,
                               [target], ScriptedRng([20, 5, 6, 7, 8]))
        row = report["rows"][0]
        self.assertEqual(row["raw"], 26)              # 重击 4d10
        self.assertEqual(row["damage"], 13)           # 抗性在重击之后才算
        self.assertEqual(row["defense"], "resistance")

    def test_immunity_zero(self):
        target = Target(label="火巨灵", ac=10, immunities=frozenset({"fire"}))
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fire_bolt", 0,
                               [target], ScriptedRng([10, 5, 6]))
        row = report["rows"][0]
        self.assertEqual(row["damage"], 0)
        self.assertEqual(row["defense"], "immunity")

    def test_immunity_wins_over_resistance(self):
        target = Target(label="双料", ac=10,
                        resistances=frozenset({"fire"}), immunities=frozenset({"fire"}))
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fire_bolt", 0,
                               [target], ScriptedRng([10, 5, 6]))
        self.assertEqual(report["rows"][0]["defense"], "immunity")

    def test_other_type_not_affected(self):
        target = Target(label="火元素", ac=10, resistances=frozenset({"cold"}))
        report = resolve_spell(self.bundle, self.actor, "dnd2024.spell.fire_bolt", 0,
                               [target], ScriptedRng([10, 5, 6]))
        self.assertEqual(report["rows"][0]["defense"], "")


# --- 落库 ---------------------------------------------------------------
class ApplyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle
        self.caster = wizard(self.bundle, 5)

    def test_dry_run_does_not_touch_hp(self):
        victim = api.new_character(self.bundle, FIGHTER, 5, STR_SCORES)
        before = victim.hp.current
        api.roll_spell(self.caster, self.bundle, "dnd2024.spell.fire_bolt", 0,
                       [victim], seed=1)
        self.assertEqual(victim.hp.current, before)

    def test_apply_reduces_hp(self):
        victim = api.new_character(self.bundle, FIGHTER, 5, STR_SCORES)
        before = victim.hp.current
        report = api.roll_spell(self.caster, self.bundle, "dnd2024.spell.fire_bolt", 0,
                                [victim], ScriptedRng([19, 5, 6]), apply=True)
        row = report["rows"][0]
        self.assertEqual(row["outcome"], "hit")
        self.assertEqual(victim.hp.current, before - row["damage"])
        self.assertEqual(row["applied"], row["damage"])
        self.assertEqual(row["hp_before"], before)

    def test_temp_hp_absorbs_first(self):
        victim = api.new_character(self.bundle, FIGHTER, 5, STR_SCORES)
        victim.hp.grant_temp(30)
        report = api.roll_spell(self.caster, self.bundle, "dnd2024.spell.fire_bolt", 0,
                                [victim], ScriptedRng([19, 5, 6]), apply=True)
        self.assertEqual(victim.hp.temp, 30 - report["rows"][0]["damage"])
        self.assertEqual(victim.hp.current, victim.hp.maximum)


# --- 目标对象 -----------------------------------------------------------
class TargetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle

    def test_from_actor_reads_sheet(self):
        victim = api.new_character(self.bundle, FIGHTER, 5, STR_SCORES)
        target = api.target_from_actor(self.bundle, victim)
        sheet_view = api.resolver_for(victim, self.bundle)
        self.assertEqual(target.ac, sheet_view.armor_class(victim.top()).total)
        # 战士熟练力量与体质豁免（+3 熟练 +3 调整 = 6）
        self.assertEqual(target.saves["str"], 6)
        self.assertEqual(target.saves["con"], 6)
        self.assertEqual(target.saves["int"], 0)

    def test_bad_ac_rejected(self):
        with self.assertRaises(RuleError):
            Target(label="?", ac=-1)

    def test_unknown_save_key_rejected(self):
        with self.assertRaises(RuleError):
            Target(label="?", ac=10, saves={"luck": 3})

    def test_missing_save_defaults_zero(self):
        self.assertEqual(Target(label="?", ac=10).save_bonus("dex"), 0)


# --- 可复现 -------------------------------------------------------------
class DeterminismTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle
        self.actor = wizard(self.bundle, 5)

    def test_same_seed_same_result(self):
        target = Target(label="木桩", ac=12)
        first = api.roll_spell(self.actor, self.bundle, "dnd2024.spell.fireball", 3,
                               [target], seed=42)
        second = api.roll_spell(self.actor, self.bundle, "dnd2024.spell.fireball", 3,
                                [target], seed=42)
        self.assertEqual(first["rows"][0]["damage"], second["rows"][0]["damage"])
        self.assertEqual(first["rows"][0]["die"], second["rows"][0]["die"])

    def test_each_target_gets_a_row(self):
        targets = [Target(label="甲", ac=12), Target(label="乙", ac=12)]
        report = api.roll_spell(self.actor, self.bundle, "dnd2024.spell.fire_bolt", 0,
                                targets, seed=9)
        self.assertEqual([row["target"] for row in report["rows"]], ["甲", "乙"])


class ReportShapeTest(unittest.TestCase):
    """前端要靠这几个键渲染，缺一个就得再猜一次语义。"""

    @classmethod
    def setUpClass(cls):
        # 内容包只解析一次：339 个法术 × 每组一份，光解析就要几十秒
        cls.bundle = load_all(PLUGINS)

    def setUp(self):
        self.bundle = self.__class__.bundle
        self.actor = wizard(self.bundle, 5)

    def test_top_level_keys(self):
        report = api.roll_spell(self.actor, self.bundle, "dnd2024.spell.fireball", 3,
                                [Target(label="木桩", ac=12)], seed=3)
        for key in ("spell", "slot", "casting", "kind", "dice", "damage_type",
                    "save", "save_effect", "shots", "rows", "total_damage", "notes"):
            self.assertIn(key, report)
        self.assertEqual(report["casting"]["dc"], 15)
        self.assertEqual(report["kind"], "save")

    def test_row_keys(self):
        report = api.roll_spell(self.actor, self.bundle, "dnd2024.spell.fireball", 3,
                                [Target(label="木桩", ac=12)], seed=3)
        row = report["rows"][0]
        for key in ("target", "kind", "against", "target_number", "die", "bonus",
                    "outcome", "damage_dice", "damage_roll", "raw", "damage",
                    "defense", "applied", "note"):
            self.assertIn(key, row)
        self.assertEqual(row["against"], "DEX 豁免")

    def test_multiple_targets_total(self):
        targets = [Target(label="甲", ac=12), Target(label="乙", ac=12)]
        report = api.roll_spell(self.actor, self.bundle, "dnd2024.spell.fire_bolt", 0,
                                targets, seed=6)
        self.assertEqual(len(report["rows"]), 2)
        self.assertEqual(report["total_damage"],
                         sum(row["damage"] for row in report["rows"]))


if __name__ == "__main__":
    unittest.main()
