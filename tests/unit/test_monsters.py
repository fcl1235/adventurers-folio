# -*- coding: utf-8 -*-
"""P9c 验收：怪物名单（含动作）与怪物攻击。

在这之前，战斗里的「对面」只是一个 `Target(label="木桩", ac=15)`：能挨打，
但不会还手 —— 因为全项目没有一处存着怪物的动作。`bestiary/beasts.yaml` 是
荒野变形的形态表（16 只，只有属性/AC/HP），熊变成熊以后照样按徒手算。

这组测试盯六件事：

  1. 91 只怪物都进得了 `bundle.monsters`，且每条 `text` 双语齐全；
  2. **命中加值取内容里的原值**，不按「属性 + 熟练」推（巨蜘蛛咬 +5，力量 +1）；
  3. **卡上的豁免加值优先**：`target_from_actor` 读 `Statblock.saves`，
     不读的话玩家扔火球时的 DC 会差两点，而界面上两个数字都「看着对」；
  4. 同种多只的 id 与显示名要分开（三只哥布林三段血）；
  5. 怪物攻击照玩家的规矩：命中 → 分段伤害 → 抗性 → 落 HP，
     预览不扣血不扣额度，动作/附赠只有自己回合能用、反应可以借别人的回合；
  6. 豁免类与「多重攻击」**不假装结算**：只回报是哪一类。

第 2 条是这一阶段的理由本身。实测 91 只里 85 条攻击推不出来 ——
如果这里改成推算，测试必须变红。
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import IllegalAction, RuleError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.model.inventory import EquipSlot
from dnd5r.rules.combat import Target, target_from_actor

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
MONSTERS = PLUGINS / "dnd2024-core" / "monsters.yaml"
FIGHTER = "dnd2024.class.fighter"
LONGSWORD = "dnd2024.item.weapon.longsword"

WOLF = "dnd2024.monster.wolf"            # AC 12 / HP 11 / 咬 +4 1d6+2
CROCODILE = "dnd2024.monster.giant_crocodile"   # 啃咬 +8，力量 +5 / 敏捷 -1
CAT = "dnd2024.monster.cat"              # 敏捷豁免印着 +4，而敏捷 15（+2）
CONSTRICTOR = "dnd2024.monster.constrictor_snake"   # 豁免类动作
APE = "dnd2024.monster.ape"              # 多重攻击

SOLDIER = {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def fighter(self, ac_note=""):
        actor = api.new_character(
            self.bundle, FIGHTER, 5, SOLDIER, name_zh="战士", name_en="Fighter")
        actor.inventory.equip(EquipSlot.MAIN_HAND, LONGSWORD)
        return actor

    def monster(self, ident=WOLF, index=1):
        return api.spawn_monster(self.bundle, ident, index)

    def duel(self, monster=None, rolls=(20, 1)):
        """建一场两人的遭遇战，并推进到**怪物**那一回合。"""
        hero = self.fighter()
        foe = monster or self.monster()
        encounter = api.new_encounter([hero, foe], rng=ScriptedRng(list(rolls)))
        guard = 0
        while api.encounter_view(encounter)["current"] != foe.id:
            api.advance_turn(encounter)
            guard += 1
            assert guard < 10, "遭遇战里没轮到怪物"
        return hero, foe, encounter


class ContentTest(Base):
    """内容层：怪物进得来、字段对得上。"""

    def test_all_monsters_loaded(self):
        self.assertEqual(len(self.bundle.monsters), 91)

    def test_wolf_stats_match_srd(self):
        wolf = self.bundle.monsters[WOLF]
        self.assertEqual(wolf.name.zh, "狼")
        self.assertEqual(wolf.name.en, "Wolf")
        self.assertEqual((wolf.ac, wolf.hp), (12, 11))
        self.assertAlmostEqual(wolf.cr, 0.25)
        self.assertEqual(wolf.speeds["walk"], 40)
        self.assertEqual(wolf.senses["darkvision"], 60)
        self.assertEqual(wolf.passive_perception, 15)

    def test_every_action_text_is_bilingual(self):
        """C7：双语都非空。英文是「尚未导入」的声明，不是空串也不是中文。"""
        for ident, monster in self.bundle.monsters.items():
            for row in monster.traits + monster.actions \
                    + monster.bonus_actions + monster.reactions:
                self.assertTrue(row.name.zh and row.name.en, ident)
                if row.text is not None:
                    self.assertTrue(row.text.zh.strip(), ident)
                    self.assertIn("English", row.text.en, ident)

    def test_action_kinds_are_known(self):
        kinds = {"melee", "ranged", "save", "multiattack", "other"}
        for ident, monster in self.bundle.monsters.items():
            for row in monster.actions:
                self.assertIn(row.kind, kinds, ident)

    def test_generated_file_is_up_to_date(self):
        """生成器与落盘文件必须一致：手改了没重跑就会变红。"""
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "gen_monsters.py"), "--check"],
            cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class PrintedNumbersTest(Base):
    """第 2、3 条：卡上的数不许重算。"""

    def test_attack_bonus_comes_from_content_not_abilities(self):
        """巨鳄的啃咬 +8，而力量 +5、敏捷 -1。

        属性 + 熟练的四种组合是 5 / 7 / -1 / 1 —— 没有一个等于 8。
        任何「按属性推加值」的实现都会在这里算出 7，测试必须变红。
        """
        croc = self.bundle.monsters[CROCODILE]
        bite = [row for row in croc.actions if row.attack_bonus is not None][0]
        self.assertEqual((croc.abilities.mod("str"), croc.abilities.mod("dex")), (5, -1))
        self.assertEqual(bite.attack_bonus, 8)
        formulas = {croc.abilities.mod("str"), croc.abilities.mod("str") + 2,
                    croc.abilities.mod("dex"), croc.abilities.mod("dex") + 2}
        self.assertNotIn(bite.attack_bonus, formulas)

    def test_saves_come_from_content(self):
        """猫的敏捷豁免印着 +4，敏捷 15 只有 +2 —— 按属性推就少两点。"""
        cat = self.monster(CAT)
        self.assertEqual(dict(cat.statblock.saves), {"dex": 4})
        self.assertEqual(cat.statblock.abilities.mod("dex"), 2)

    def test_target_reads_printed_saves(self):
        cat = self.monster(CAT)
        target = target_from_actor(self.bundle, cat)
        self.assertEqual(target.save_bonus("dex"), 4)
        # 没印的那几项仍按属性推（猫的体质 10 → +0）
        self.assertEqual(target.save_bonus("con"), cat.statblock.abilities.mod("con"))

    def test_player_saves_still_derived(self):
        """加了「印着的豁免」这条通道后，玩家不能受影响：没有印的值就走推导。"""
        hero = self.fighter()
        self.assertEqual(dict(hero.statblock.saves), {})
        target = target_from_actor(self.bundle, hero)
        self.assertEqual(target.save_bonus("str"),
                         hero.statblock.abilities.mod("str") + 3)   # 战士熟练力量豁免


class SpawnTest(Base):
    """第 4 条：同种多只要分得开。"""

    def test_index_separates_ids_and_labels(self):
        first = self.monster(WOLF, 1)
        third = self.monster(WOLF, 3)
        self.assertEqual(first.id, WOLF)
        self.assertEqual(third.id, WOLF + "#3")
        self.assertEqual(first.display_name, "狼")
        self.assertEqual(third.display_name, "狼 3")
        self.assertIsNot(first.hp, third.hp)

    def test_broken_id_says_what_is_available(self):
        with self.assertRaises(api.PluginError):
            api.spawn_monster(self.bundle, "dnd2024.monster.dragon")

    def test_sheet_carries_actions_and_cr_text(self):
        sheet = api.monster_sheet(self.bundle, WOLF)
        self.assertEqual(sheet["cr_text"], "1/4")
        self.assertEqual(sheet["ac"], 12)
        self.assertEqual([row["key"] for row in sheet["actions"]], ["action:0"])
        self.assertEqual(sheet["actions"][0]["attack_bonus"], 4)

    def test_wolf_ac_survives_the_ac_base_roundtrip(self):
        """AC 反推成 ac_base 后，Resolver 再算回来必须还是 12（别把敏捷加两次）。"""
        wolf = self.monster()
        target = Target(label="狼", ac=12, actor=wolf)
        self.assertEqual(wolf.statblock.ac_base + wolf.statblock.abilities.mod("dex"), 12)
        self.assertEqual(target.ac, 12)


class MonsterAttackTest(Base):
    """第 5 条：怪物打人的结算。"""

    def test_hit_damages_the_player(self):
        hero, wolf, encounter = self.duel()
        before = hero.hp.current
        result = api.monster_attack(
            encounter, self.bundle, wolf, "action:0", hero,
            rng=ScriptedRng([15, 4]), apply=True)
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["attack"]["bonus"], 4)     # 卡上的数
        self.assertEqual(result["attack"]["total"], 19)
        self.assertEqual(result["damage"]["total"], 6)     # 1d6[4] + 2
        self.assertEqual(hero.hp.current, before - 6)
        self.assertEqual(result["hp"]["applied"], 6)

    def test_roll_uses_the_printed_bonus(self):
        """掷出来的加值也必须是卡上的数 —— 只断言内容字段抓不到「结算时重算」。"""
        hero, croc, encounter = self.duel(self.monster(CROCODILE))
        result = api.monster_attack(
            encounter, self.bundle, croc, "action:1", hero,   # action:0 是「多重攻击」
            rng=ScriptedRng([10, 1, 1, 1]), apply=False)     # 3d10 咬中
        self.assertEqual(result["attack"]["bonus"], 8)
        self.assertEqual(result["attack"]["total"], 18)
        self.assertNotEqual(result["attack"]["bonus"],
                            croc.statblock.abilities.mod("str") + 2)   # 那会算出 7

    def test_miss_changes_nothing(self):
        hero, wolf, encounter = self.duel()
        before = hero.hp.current
        result = api.monster_attack(
            encounter, self.bundle, wolf, "action:0", hero,
            rng=ScriptedRng([2]), apply=True)
        self.assertEqual(result["outcome"], "miss")
        self.assertEqual(hero.hp.current, before)
        self.assertEqual(result["damage"]["total"], 0)

    def test_critical_doubles_dice_only(self):
        hero, wolf, encounter = self.duel()
        result = api.monster_attack(
            encounter, self.bundle, wolf, "action:0", hero,
            rng=ScriptedRng([20, 3, 5]), apply=True)
        self.assertEqual(result["outcome"], "critical")
        self.assertEqual(result["damage"]["total"], 3 + 5 + 2)   # 2d6 + 2

    def test_pays_the_action_once(self):
        hero, wolf, encounter = self.duel()
        result = api.monster_attack(
            encounter, self.bundle, wolf, "action:0", hero,
            rng=ScriptedRng([15, 4]), apply=True)
        self.assertEqual(result["economy"]["after"]["action"], 0)
        again = ScriptedRng([15, 4])
        with self.assertRaises(IllegalAction):
            api.monster_attack(encounter, self.bundle, wolf, "action:0", hero,
                               rng=again, apply=True)

    def test_preview_pays_nothing(self):
        hero, wolf, encounter = self.duel()
        before = hero.hp.current
        result = api.monster_attack(
            encounter, self.bundle, wolf, "action:0", hero,
            rng=ScriptedRng([15, 4]), apply=False)
        self.assertTrue(result["economy"]["preview"])
        self.assertEqual(result["economy"]["after"]["action"], 1)
        self.assertEqual(hero.hp.current, before)
        self.assertIsNone(result["hp"]["applied"])

    def test_action_needs_its_own_turn(self):
        """先攻序里第一个人是战士时，狼不能用动作打人 —— 只有反应可以。"""
        hero, wolf, encounter = self.duel()
        api.advance_turn(encounter)     # 轮回到战士
        with self.assertRaises(IllegalAction):
            api.monster_attack(encounter, self.bundle, wolf, "action:0", hero,
                               rng=ScriptedRng([15, 4]), apply=True)

    def test_resistance_halves_by_segment(self):
        hero, wolf, encounter = self.duel()
        armored = Target(label="石像鬼", ac=10, actor=hero,
                         resistances=frozenset({"piercing"}))
        result = api.monster_attack(
            encounter, self.bundle, wolf, "action:0", armored,
            rng=ScriptedRng([15, 6]), apply=False)
        self.assertEqual(result["damage"]["breakdown"][0]["raw"], 8)
        self.assertEqual(result["damage"]["total"], 4)
        self.assertEqual(result["damage"]["defense"], "resistance")

    def test_save_action_does_not_pretend(self):
        hero, snake, encounter = self.duel(self.monster(CONSTRICTOR))
        save_row = [row for row in api.monster_actions(self.bundle, CONSTRICTOR)
                    if row["kind"] == "save"][0]
        result = api.monster_attack(
            encounter, self.bundle, snake, save_row["key"], hero,
            rng=ScriptedRng([]), apply=True)
        self.assertFalse(result["rolled"])
        self.assertEqual(result["outcome"], "save_required")
        self.assertIn("DC %d" % save_row["save_dc"], " ".join(result["notes"]))
        self.assertEqual(hero.hp.current, hero.hp.maximum)

    def test_multiattack_label_costs_no_action(self):
        hero, ape, encounter = self.duel(self.monster(APE))
        row = [item for item in api.monster_actions(self.bundle, APE)
               if item["kind"] == "multiattack"][0]
        result = api.monster_attack(encounter, self.bundle, ape, row["key"], hero,
                                    rng=ScriptedRng([]), apply=True)
        self.assertFalse(result["rolled"])
        self.assertEqual(result["economy"]["kind"], "")
        self.assertEqual(encounter.get(ape).economy.action, 1)

    def test_reaction_may_be_used_off_turn(self):
        """反应能在别人回合里用 —— 这是「借机攻击」那条规矩的另一半。

        内容里 91 只怪物没有一条带反应的攻击动作，所以这里现造一只：
        规则不该因为「当前内容刚好用不到」而写死成「必须自己回合」。
        """
        guard, encounter = self.guard_duel()
        before = encounter.get(guard["actor"]).economy.to_dict()
        result = api.monster_attack(encounter, guard["bundle"], guard["actor"],
                                    "reaction:0", guard["hero"],
                                    rng=ScriptedRng([12, 3]), apply=True)
        self.assertEqual(result["economy"]["kind"], "reaction")
        self.assertEqual(result["economy"]["after"]["reaction"], 0)
        # 动作没被动过（守卫本来就没轮到，begin 把他的动作置 0）
        self.assertEqual(result["economy"]["after"]["action"], before["action"])

    def test_bonus_action_still_needs_its_turn(self):
        guard, encounter = self.guard_duel()
        with self.assertRaises(IllegalAction):
            api.monster_attack(encounter, guard["bundle"], guard["actor"],
                               "bonus:0", guard["hero"],
                               rng=ScriptedRng([12, 3]), apply=True)

    def guard_duel(self):
        """现造一只带「反击（反应）」的守卫，让战士先攻（守卫不在自己回合）。"""
        from copy import copy

        from dnd5r.content import MonsterDef
        from dnd5r.kernel.text import Text
        from dnd5r.model.statblock import Abilities
        from dnd5r.rules.monsters import DamageRoll, MonsterAttack

        riposte = MonsterAttack(
            name=Text.of("反击", "Riposte"), kind="melee", attack_bonus=5,
            reach=5, damage=(DamageRoll("1d8+2", "slashing"),))
        monster = MonsterDef(
            id="test.monster.guard", name=Text.of("守卫", "Guard"),
            ac=14, hp=20, cr=1,
            abilities=Abilities.of(str=14, dex=10, con=12, int=10, wis=10, cha=10),
            speeds={"walk": 30}, reactions=(riposte,), bonus_actions=(riposte,))
        bundle = copy(self.bundle)
        bundle.monsters = dict(self.bundle.monsters)
        bundle.monsters[monster.id] = monster
        hero = self.fighter()
        actor = api.spawn_monster(bundle, monster.id)
        encounter = api.new_encounter([hero, actor], rng=ScriptedRng([20, 1]))
        self.assertEqual(api.encounter_view(encounter)["current"], hero.id)
        return {"bundle": bundle, "actor": actor, "hero": hero, "encounter": encounter}, encounter

    def test_unknown_key_is_rejected(self):
        hero, wolf, encounter = self.duel()
        with self.assertRaises(RuleError):
            api.monster_attack(encounter, self.bundle, wolf, "action:9", hero,
                               apply=True)
        with self.assertRaises(RuleError):
            api.monster_attack(encounter, self.bundle, wolf, "尾巴", hero,
                               apply=True)


class MonsterAgainstPlayerAttackTest(Base):
    """玩家打怪物：AC/HP 走的是同一套 `attack_roll`。"""

    def test_player_kills_the_wolf(self):
        hero = self.fighter()
        wolf = self.monster()
        result = api.attack_roll(hero, self.bundle, wolf, rng=ScriptedRng([15, 8]),
                                 apply=True)
        self.assertEqual(result["outcome"], "hit")
        self.assertLess(wolf.hp.current, wolf.hp.maximum)
        self.assertEqual(wolf.hp.current, 11 - result["damage"]["total"])


if __name__ == "__main__":
    unittest.main()
