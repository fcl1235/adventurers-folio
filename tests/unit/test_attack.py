# -*- coding: utf-8 -*-
"""P9b 验收：一次性标记与攻击伤害管线（G2b）。

在这之前，「攻击」只到掷一个 d20 加值就断了 —— 没有目标、没有伤害、没有
「用掉就没了」的优势。两条真实规则因此只能写在 `note` 里：

  月光步     本回合结束前下一次攻击优势
  月华形态   每回合一次，命中额外 2d10 光耀

这组测试盯六件事：

  1. 命中/失手/重击三种结果，重击**加骰不加定值**；
  2. 抗性/免疫按**每一段**伤害各算（光耀那 2d10 不该被挥砍抗性减半）；
  3. 优势来自标记时不进合计，只改掷骰形状，且掷过就用掉；
  4. 预览（`apply=False`）不扣血、不消耗标记、不记账；
  5. 额外伤害默认**不加**（原文是 "you can"），且每回合只有一次；
  6. 回合结束清标记与记账 —— 三条路径（遭遇战推进、单独 NewTurn、休息）。

第 3 条最容易写错：把优势当成 +5 加进 `total`，卡片上就会出现规则里没有的数。
所以每条断言都同时检查 `total` **没有**被模式影响。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import IllegalAction, RuleError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.model.inventory import EquipSlot
from dnd5r.rules.combat import Target
from dnd5r.rules.encounter import Encounter

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
FIGHTER = "dnd2024.class.fighter"
DRUID = "dnd2024.class.druid"
MOON = "dnd2024.subclass.druid.circle_of_the_moon"
STEP = MOON + ".moonlight_step"
WILD_SHAPE = "dnd2024.class.druid.wild_shape"
LONGSWORD = "dnd2024.item.weapon.longsword"
CAT = "dnd2024.form.beast.cat"

# 力量 16（+3）、5 级（熟练 +3）→ 长剑攻击 +6
SOLDIER = {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10}
# 感知 16（+3）→ 月光步 4 次，变化形
DRUID_SCORES = {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 16, "cha": 12}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def fighter(self, weapon=LONGSWORD):
        actor = api.new_character(
            self.bundle, FIGHTER, 5, SOLDIER,
            name_zh="战士", name_en="Fighter")
        if weapon:
            actor.inventory.equip(EquipSlot.MAIN_HAND, weapon)
        return actor

    def druid(self, level=14):
        return api.new_character(
            self.bundle, DRUID, level, DRUID_SCORES,
            name_zh="德鲁伊", name_en="Druid", subclass=MOON)

    def post(self, ac=15, **kwargs):
        return Target(label="木桩", ac=ac, **kwargs)


class HitTest(Base):
    """命中判定与伤害。长剑单手 1d8，副手空着按双手握持 → 1d10。"""

    def test_hit_lands_weapon_damage(self):
        # 15 + 6 = 21 ≥ AC 15；伤害 1d10 掷 5 → 5 + 3 = 8
        result = api.attack_roll(
            self.fighter(), self.bundle, self.post(15), rng=ScriptedRng([15, 5]))
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["attack"]["total"], 21)
        self.assertEqual(result["attack"]["bonus"], 6)
        self.assertEqual(result["damage"]["total"], 8)
        self.assertEqual(result["damage"]["type"], "挥砍")
        # 预览：不落库
        self.assertIsNone(result["hp"]["applied"])

    def test_miss_rolls_no_damage(self):
        rng = ScriptedRng([2])          # 2 + 6 = 8 < 15
        result = api.attack_roll(self.fighter(), self.bundle, self.post(15), rng=rng)
        self.assertEqual(result["outcome"], "miss")
        self.assertEqual(result["damage"]["total"], 0)
        self.assertEqual(rng.remaining, 0)   # 一个伤害骰都没掷

    def test_critical_adds_dice_not_flat(self):
        # d20 = 20 → 重击；1d10 变 2d10，+3 定值不翻
        result = api.attack_roll(
            self.fighter(), self.bundle, self.post(15), rng=ScriptedRng([20, 4, 7]))
        self.assertEqual(result["outcome"], "critical")
        self.assertEqual(result["damage"]["breakdown"][0]["dice"], "2d10")
        self.assertEqual(result["damage"]["total"], 4 + 7 + 3)   # 14，不是 (11+3)×2

    def test_natural_one_always_misses(self):
        # 定值 +6 也救不了：d20 出 1 必然失手
        result = api.attack_roll(
            self.fighter(), self.bundle, self.post(2), rng=ScriptedRng([1]))
        self.assertEqual(result["outcome"], "miss")

    def test_unarmed_is_one_plus_strength(self):
        result = api.attack_roll(
            self.fighter(weapon=None), self.bundle, self.post(10),
            rng=ScriptedRng([12]))
        self.assertEqual(result["weapon"]["id"], "unarmed")
        self.assertEqual(result["damage"]["total"], 4)     # 1 + 3

    def test_damage_never_negative(self):
        """力量 3 的猫徒手 «1 - 4» 是 0 点，不是 -3（负伤害会变成治疗）。"""
        actor = self.druid()
        api.use_power(actor, self.bundle, WILD_SHAPE, choice={"form_id": CAT})
        result = api.attack_roll(actor, self.bundle, self.post(5), rng=ScriptedRng([11]))
        self.assertGreaterEqual(result["damage"]["total"], 0)

    def test_attack_bonus_matches_sheet(self):
        """角色卡与掷骰必须是同一个算式 —— 卡上 +7、掷的时候 +5 是最难发现的错。"""
        actor = self.fighter()
        sheet = api.character_sheet(actor, self.bundle)
        card = next(row for row in sheet["attacks"] if row["weapon"] == LONGSWORD)
        result = api.attack_roll(actor, self.bundle, self.post(15), rng=ScriptedRng([15, 5]))
        self.assertEqual(result["attack"]["bonus"], card["attack"])


class DefenseTest(Base):
    """抗性与免疫按段算，不是先加总再减。"""

    def test_resistance_halves_the_weapon_segment(self):
        target = self.post(15, resistances=frozenset({"slashing"}))
        result = api.attack_roll(
            self.fighter(), self.bundle, target, rng=ScriptedRng([15, 9]))
        # 9 + 3 = 12 → 抗性减半 6
        self.assertEqual(result["damage"]["breakdown"][0]["raw"], 12)
        self.assertEqual(result["damage"]["total"], 6)

    def test_immunity_zeroes_the_segment(self):
        target = self.post(15, immunities=frozenset({"slashing"}))
        result = api.attack_roll(
            self.fighter(), self.bundle, target, rng=ScriptedRng([15, 9]))
        self.assertEqual(result["damage"]["total"], 0)
        self.assertEqual(result["damage"]["defense"], "immunity")


class MarkTest(Base):
    """一次性优势：不进合计、掷过就用掉、预览不动它。"""

    def cast_step(self, actor):
        return api.use_power(actor, self.bundle, STEP)

    def test_step_installs_one_mark(self):
        actor = self.druid()
        self.assertEqual(api.marks_of(actor), [])
        self.cast_step(actor)
        marks = api.marks_of(actor)
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["mode"], "adv")
        self.assertEqual(marks[0]["target"], "attack.all")
        self.assertEqual(marks[0]["expires"], "turn")
        self.assertEqual(marks[0]["uses"], 1)

    def test_advantage_changes_dice_not_total(self):
        """优势只改掷骰形状：`total` 里不能出现 +5 这种规则里没有的数。"""
        actor = self.druid()
        self.cast_step(actor)
        # 两个 d20：8 与 17，优势取 17；徒手无伤害骰 → 只消耗两个 d20
        result = api.attack_roll(
            actor, self.bundle, self.post(10), rng=ScriptedRng([8, 17]), apply=True)
        self.assertEqual(result["attack"]["mode"], "adv")
        self.assertEqual(result["attack"]["kept"], [17])
        self.assertEqual(result["attack"]["dropped"], [8])
        self.assertEqual(result["attack"]["total"], 17 + result["attack"]["bonus"])

    def test_mark_is_consumed_by_the_roll(self):
        actor = self.druid()
        self.cast_step(actor)
        api.attack_roll(actor, self.bundle, self.post(10),
                        rng=ScriptedRng([8, 17]), apply=True)
        self.assertEqual(api.marks_of(actor), [])
        # 用掉之后的下一次攻击是平掷
        after = api.attack_roll(actor, self.bundle, self.post(10), rng=ScriptedRng([9]))
        self.assertEqual(after["attack"]["mode"], "flat")

    def test_preview_keeps_the_mark(self):
        actor = self.druid()
        self.cast_step(actor)
        result = api.attack_roll(actor, self.bundle, self.post(10), rng=ScriptedRng([8, 17]))
        self.assertEqual(result["attack"]["mode"], "adv")
        self.assertEqual(len(api.marks_of(actor)), 1)
        self.assertTrue(result["marks"]["preview"])

    def test_mark_expires_when_turn_ends(self):
        actor = self.druid()
        self.cast_step(actor)
        session = api.Session(self.bundle)
        session.actor = actor
        session.dispatch(api.NewTurn())
        self.assertEqual(api.marks_of(actor), [])

    def test_rest_clears_marks(self):
        actor = self.druid()
        self.cast_step(actor)
        session = api.Session(self.bundle)
        session.actor = actor
        session.dispatch(api.ShortRest())
        self.assertEqual(api.marks_of(actor), [])

    def test_roll_check_reports_pending_mark_without_spending(self):
        """通用掷骰工具不消耗标记（否则随便掷一下就丢了优势），但要说清它还在。"""
        actor = self.druid()
        self.cast_step(actor)
        result = api.roll_check(actor, self.bundle, "attack", rng=ScriptedRng([8, 17]))
        self.assertTrue(result["advantage"])
        self.assertEqual(len(result["marks_pending"]), 1)
        self.assertEqual(len(api.marks_of(actor)), 1)


class ExtraDamageTest(Base):
    """月华形态「每回合一次 +2d10」：默认不加、加了才扣记账、每回合一次。"""

    def morphed(self, level=14):
        actor = self.druid(level)
        api.use_power(actor, self.bundle, WILD_SHAPE, choice={"form_id": CAT})
        return actor

    def test_status_is_onhit_not_active(self):
        """诚实标记：「命中时结算」不是「有按钮」—— 归成 active 玩家会到处找按钮。"""
        from dnd5r.rules.contributions import power_status

        actor = self.druid()
        power = api.find_power(self.bundle, MOON + ".lunar_form", actor)
        self.assertEqual(power_status(power), "onhit")

    def test_option_only_while_morphed(self):
        # `when: {morphed: true}` —— 人形时不该列出（列出来等于说它可以选）
        self.assertEqual(api.attack_options(self.druid(), self.bundle)["extras"], [])
        options = api.attack_options(self.morphed(), self.bundle)["extras"]
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["dice"], "2d10")
        self.assertEqual(options[0]["damage_type"], "radiant")
        self.assertTrue(options[0]["available"])

    def test_not_added_by_default(self):
        actor = self.morphed()
        # 骰子给足（d20 + 2d10）：这样「默认加上了」会失败在断言上，
        # 而不是失败在「脚本序列耗尽」—— 后者说明不了数值对不对
        result = api.attack_roll(
            actor, self.bundle, self.post(5), rng=ScriptedRng([11, 1, 1]))
        self.assertEqual(result["extras"]["chosen"], [])
        self.assertEqual(len(result["extras"]["available"]), 1)
        self.assertIn("这次没加额外伤害", " ".join(result["notes"]))

    def test_added_when_explicitly_chosen(self):
        actor = self.morphed()
        # 徒手（无骰）+ 2d10：脚本 11、3、7
        result = api.attack_roll(
            actor, self.bundle, self.post(5), rng=ScriptedRng([11, 3, 7]),
            apply=True, extras="all")
        self.assertEqual(len(result["extras"]["chosen"]), 1)
        # 徒手 1 +（猫的力量调整值）+ 2d10
        expected = max(0, 1 + actor.top().statblock.abilities.mod("str")) + 10
        self.assertEqual(result["damage"]["total"], expected)
        self.assertEqual(result["damage"]["breakdown"][1]["damage_type"], "radiant")

    def test_once_per_turn(self):
        actor = self.morphed()
        api.attack_roll(actor, self.bundle, self.post(5), rng=ScriptedRng([11, 1, 1]),
                        apply=True, extras="all")
        with self.assertRaises(RuleError):
            api.attack_roll(actor, self.bundle, self.post(5), rng=ScriptedRng([11, 1, 1]),
                            apply=True, extras="all")

    def test_preview_does_not_spend_the_once_per_turn(self):
        actor = self.morphed()
        api.attack_roll(actor, self.bundle, self.post(5), rng=ScriptedRng([11, 1, 1]),
                        extras="all")     # apply=False
        again = api.attack_roll(actor, self.bundle, self.post(5),
                                rng=ScriptedRng([11, 1, 1]), extras="all")
        self.assertEqual(len(again["extras"]["chosen"]), 1)

    def test_reset_when_turn_ends(self):
        actor = self.morphed()
        api.attack_roll(actor, self.bundle, self.post(5), rng=ScriptedRng([11, 1, 1]),
                        apply=True, extras="all")
        foe = api.new_character(self.bundle, FIGHTER, 1, SOLDIER,
                                name_zh="对手", name_en="Foe", actor_id="npc.foe")
        encounter = Encounter.of([actor, foe])
        encounter.roll_initiative(ScriptedRng([20, 1]))
        encounter.begin()
        # 把回合推回自己身上（敌人先攻高就先推一次）
        guard = 0
        while encounter.current().actor is not actor and guard < 4:
            encounter.next_turn()
            guard += 1
        encounter.next_turn()          # 结束自己的回合
        options = api.attack_options(actor, self.bundle)["extras"]
        self.assertTrue(options[0]["available"])


class EncounterQuotaTest(Base):
    """传了 `encounter` 的玩家武器攻击：额度与预览。

    这条与怪物侧（`test_monsters` 的 `test_preview_pays_nothing`）是**两段代码**，
    必须各验一次 —— 只验一边，另一边悄悄开始「预览也扣动作」是看不出来的。
    """

    def setup_turn(self):
        hero = self.fighter()
        foe = api.new_character(self.bundle, FIGHTER, 1, SOLDIER,
                                name_zh="对手", name_en="Foe", actor_id="npc.foe")
        encounter = Encounter.of([hero, foe])
        encounter.roll_initiative(ScriptedRng([20, 1]))
        encounter.begin()
        guard = 0
        while encounter.current().actor is not hero:
            encounter.next_turn()
            guard += 1
            assert guard < 4
        return hero, foe, encounter

    def test_preview_pays_no_quota(self):
        hero, foe, encounter = self.setup_turn()
        result = api.attack_roll(hero, self.bundle, foe,
                                 rng=ScriptedRng([15, 8]), encounter=encounter)
        self.assertTrue(result["economy"]["preview"])
        self.assertEqual(result["economy"]["after"]["action"], 1)

    def test_apply_pays_the_action(self):
        hero, foe, encounter = self.setup_turn()
        result = api.attack_roll(hero, self.bundle, foe,
                                 rng=ScriptedRng([15, 8]), encounter=encounter,
                                 apply=True)
        self.assertFalse(result["economy"]["preview"])
        self.assertEqual(encounter.get(hero).economy.action, 0)


class OpportunityTest(Base):
    """借机攻击：走出触及范围时报告「谁够得着、谁还有反应」。"""

    def setup_pair(self):
        hero = self.fighter()
        foe = api.new_character(self.bundle, FIGHTER, 5, SOLDIER,
                                name_zh="对手", name_en="Foe", actor_id="npc.foe")
        encounter = Encounter.of([hero, foe])
        encounter.roll_initiative(ScriptedRng([20, 1]))
        encounter.begin()
        encounter.place(hero, 0, 0)
        encounter.place(foe, 1, 0)      # 相邻：5 尺内
        return hero, foe, encounter

    def test_leaving_reach_lists_the_enemy(self):
        hero, foe, encounter = self.setup_pair()
        result = encounter.move(hero, 4, 0)
        rows = result["left_reach"]
        self.assertEqual([row["id"] for row in rows], [foe.id])
        self.assertTrue(rows[0]["reaction"])

    def test_staying_in_reach_lists_nothing(self):
        hero, foe, encounter = self.setup_pair()
        result = encounter.move(hero, 1, 1)          # 仍在 5 尺内
        self.assertEqual(result["left_reach"], [])

    def test_no_reaction_is_reported_honestly(self):
        hero, foe, encounter = self.setup_pair()
        encounter.get(foe).economy.reaction = 0
        result = encounter.move(hero, 4, 0)
        self.assertFalse(result["left_reach"][0]["reaction"])

    def test_teleport_does_not_trigger(self):
        """传送不消耗移动力，也不引发借机攻击 —— 所以不报候选。"""
        hero, foe, encounter = self.setup_pair()
        result = encounter.teleport(hero, 4, 0, 30)
        self.assertNotIn("left_reach", result)


class ReactionStrikeTest(Base):
    """借机攻击的结算：花反应、掷一次攻击；预览不动额度。"""

    def setup_pair(self):
        hero = self.fighter()
        foe = api.new_character(self.bundle, FIGHTER, 5, SOLDIER,
                                name_zh="对手", name_en="Foe", actor_id="npc.foe")
        foe.inventory.equip(EquipSlot.MAIN_HAND, LONGSWORD)
        encounter = Encounter.of([hero, foe])
        encounter.roll_initiative(ScriptedRng([20, 1]))
        encounter.begin()
        encounter.place(hero, 0, 0)
        encounter.place(foe, 1, 0)
        return hero, foe, encounter

    def test_spends_the_reaction(self):
        hero, foe, encounter = self.setup_pair()
        left = encounter.move(hero, 4, 0)["left_reach"]
        self.assertEqual([row["id"] for row in left], [foe.id])
        actions_before = encounter.get(foe).economy.action
        result = api.opportunity_attack(
            encounter, self.bundle, foe, hero, rng=ScriptedRng([18, 6]), apply=True)
        self.assertTrue(result["hit"])
        self.assertEqual(result["reaction"]["before"], 1)
        self.assertEqual(result["reaction"]["after"], 0)
        self.assertEqual(encounter.get(foe).economy.reaction, 0)
        # 动作没被动过 —— 借机攻击只花反应（此刻还没轮到 foe，动作本来就是 0）
        self.assertEqual(encounter.get(foe).economy.action, actions_before)

    def test_no_reaction_left_is_refused(self):
        hero, foe, encounter = self.setup_pair()
        encounter.get(foe).economy.reaction = 0
        with self.assertRaises(IllegalAction):
            api.opportunity_attack(
                encounter, self.bundle, foe, hero, rng=ScriptedRng([18, 6]), apply=True)

    def test_preview_does_not_spend_the_reaction(self):
        hero, foe, encounter = self.setup_pair()
        result = api.opportunity_attack(
            encounter, self.bundle, foe, hero, rng=ScriptedRng([18, 6]))
        self.assertEqual(result["reaction"]["after"], 1)
        self.assertTrue(result["reaction"]["preview"])
        self.assertEqual(encounter.get(foe).economy.reaction, 1)



class EconomyTest(Base):
    """传了 `encounter` 的攻击必须花掉动作额度 —— 否则界面上「打完了」但还能再打。

    这是 P9d 补的一条：`attack_roll` 之前只掷骰，不管额度。界面一接上，
    「点了十次都没用完动作」就会立刻暴露。副手攻击花附赠，不是动作。
    """

    def duel(self, rng_values=(20, 5)):
        hero = self.fighter()
        foe = self.fighter()
        foe.id = "npc.dummy"
        encounter = api.new_encounter([hero, foe], rng=ScriptedRng(list(rng_values)))
        while api.encounter_view(encounter)["current"] != hero.id:
            api.advance_turn(encounter)
        return hero, foe, encounter

    def test_roll_spends_the_action(self):
        hero, foe, encounter = self.duel()
        result = api.attack_roll(hero, self.bundle, foe, rng=ScriptedRng([15, 5]),
                                 apply=True, encounter=encounter)
        self.assertEqual(result["economy"]["kind"], "action")
        self.assertEqual(result["economy"]["after"]["action"], 0)
        self.assertEqual(encounter.get(hero).economy.action, 0)

    def test_preview_spends_nothing(self):
        hero, foe, encounter = self.duel()
        api.attack_roll(hero, self.bundle, foe, rng=ScriptedRng([15, 5]),
                        apply=False, encounter=encounter)
        self.assertEqual(encounter.get(hero).economy.action, 1)

    def test_second_attack_is_refused(self):
        hero, foe, encounter = self.duel()
        api.attack_roll(hero, self.bundle, foe, rng=ScriptedRng([15, 5]),
                        apply=True, encounter=encounter)
        with self.assertRaises(IllegalAction):
            api.attack_roll(hero, self.bundle, foe, rng=ScriptedRng([15, 5]),
                            apply=True, encounter=encounter)

    def test_off_hand_spends_the_bonus_action(self):
        hero, foe, encounter = self.duel()
        hero.inventory.equip(EquipSlot.OFF_HAND, LONGSWORD)
        result = api.attack_roll(hero, self.bundle, foe, off_hand=True,
                                 rng=ScriptedRng([15, 5]), apply=True,
                                 encounter=encounter)
        self.assertEqual(result["economy"]["kind"], "bonus")
        self.assertEqual(encounter.get(hero).economy.bonus, 0)
        self.assertEqual(encounter.get(hero).economy.action, 1)

    def test_out_of_turn_is_refused(self):
        hero, foe, encounter = self.duel()
        api.advance_turn(encounter)          # 轮到对手
        with self.assertRaises(IllegalAction):
            api.attack_roll(hero, self.bundle, foe, rng=ScriptedRng([15, 5]),
                            apply=True, encounter=encounter)

if __name__ == "__main__":
    unittest.main()
