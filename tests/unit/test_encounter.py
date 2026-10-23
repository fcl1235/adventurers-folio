# -*- coding: utf-8 -*-
"""P9a 验收：遭遇战（回合容器、先攻、距离）与月光步传送。

在此之前，「回合」只存在于单个角色身上（`Session.economy` + `NewTurn`），
没有「谁跟谁打、现在轮到谁、彼此多远」这层。于是月环 10 级的月光步只能
扣掉次数和附赠动作，位置一动不动 —— 玩家点完发现人还在原地。

这组测试盯五件事：
  1. 先攻排序与回合推进（含「一轮结束才恢复反应」）；
  2. 距离按 5 尺格算，斜着走不算远；
  3. 移动消耗移动力，传送**不**消耗但要过距离与占位；
  4. 月光步在有遭遇战时真的挪人，没有遭遇战时明说「未结算」；
  5. 能力跑失败（超距、占位）时**退回**次数与附赠动作。

第 5 条是实测才发现的：原来 `use_power` 先付代价再跑效果，抛错就白扣一次。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import IllegalAction, RuleError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.rules.encounter import FOOT, Encounter

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
DRUID = "dnd2024.class.druid"
ROGUE = "dnd2024.class.rogue"
MOON = "dnd2024.subclass.druid.circle_of_the_moon"
STEP = MOON + ".moonlight_step"
STEP_POOL = "dnd2024.resource.druid.circle_of_the_moon.moonlight_step"

SCORES = {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 16, "cha": 12}
FAST = {"str": 10, "dex": 16, "con": 12, "int": 10, "wis": 10, "cha": 10}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def druid(self, level=10, scores=None):
        return api.new_character(
            self.bundle, DRUID, level, scores or SCORES,
            name_zh="德鲁伊", name_en="Druid", subclass=MOON)

    def foe(self, scores=None):
        return api.new_character(
            self.bundle, ROGUE, 5, scores or FAST,
            name_zh="对手", name_en="Foe", actor_id="npc.foe")

    def duel(self, rng_values=(15, 5)):
        """德鲁伊先攻必赢的一场（15+1=16 vs 5+3=8）。"""
        hero = self.druid()
        encounter = api.new_encounter([hero, self.foe()], rng=ScriptedRng(list(rng_values)))
        return hero, encounter

    def step(self, hero, encounter, choice=None):
        return api.use_power(hero, self.bundle, STEP, seed=1,
                             choice=choice, encounter=encounter)


# --- 先攻与回合 -------------------------------------------------------
class InitiativeTests(Base):
    def test_sorted_by_initiative_desc(self):
        hero, encounter = self.duel()
        self.assertEqual([c.label for c in encounter.combatants], ["德鲁伊", "对手"])
        self.assertGreater(encounter.combatants[0].initiative,
                           encounter.combatants[1].initiative)

    def test_tie_broken_by_dex_not_by_chance(self):
        """先攻同分时看敏捷调整值。随机化的同分排序没法复现，测试也就没法断言。

        两边**掷的点数不同**才凑得出同分：德鲁伊 dex 12(+1) 掷 12 = 13，
        对手 dex 16(+3) 掷 10 = 13。此时排前面的是敏捷高的那个。
        """
        slow = self.druid(scores=SCORES)          # dex 12 → +1
        quick = self.foe(scores=FAST)             # dex 16 → +3
        encounter = Encounter.of([slow, quick])
        encounter.roll_initiative(ScriptedRng([12, 10]))
        first, second = encounter.combatants
        self.assertEqual(int(first.initiative), int(second.initiative))
        self.assertEqual(first.label, "对手")

    def test_down_participants_sort_last(self):
        hero, encounter = self.duel()
        encounter.get("npc.foe").actor.root().hp.current = 0
        encounter.roll_initiative(ScriptedRng([20, 1]))    # 倒地的人掷得再高也排最后
        self.assertEqual(encounter.combatants[-1].id, "npc.foe")

    def test_begin_gives_quota_only_to_the_first(self):
        """开场时其他人不该白拿一个动作 —— 谁先攻都一样是错的。"""
        hero, encounter = self.duel()
        self.assertEqual(encounter.round, 1)
        self.assertEqual(encounter.current().label, "德鲁伊")
        self.assertEqual(encounter.get(hero).economy.action, 1)
        self.assertEqual(encounter.get("npc.foe").economy.action, 0)
        # 反应例外：被偷袭的人也得能借机攻击
        self.assertEqual(encounter.get("npc.foe").economy.reaction, 1)

    def test_next_turn_moves_pointer(self):
        _, encounter = self.duel()
        who = encounter.next_turn()
        self.assertEqual(who.label, "对手")
        self.assertEqual(encounter.round, 1)

    def test_round_advance_refills_reaction(self):
        hero, encounter = self.duel()
        encounter.get(hero).economy.reaction = 0
        encounter.next_turn()          # 轮到对手
        encounter.next_turn()          # 回到德鲁伊 = 第 2 轮
        self.assertEqual(encounter.round, 2)
        self.assertEqual(encounter.get(hero).economy.reaction, 1)

    def test_end_turn_clears_unused_quota(self):
        """额度不能攒：一个回合没用完的动作不会留到下回合。"""
        hero, encounter = self.duel()
        self.assertEqual(encounter.get(hero).economy.action, 1)
        encounter.next_turn()
        self.assertEqual(encounter.get(hero).economy.action, 0)

    def test_cannot_begin_twice(self):
        _, encounter = self.duel()
        with self.assertRaises(IllegalAction):
            encounter.begin()


# --- 距离与移动 -------------------------------------------------------
class DistanceTests(Base):
    def test_distance_is_chebyshev(self):
        """斜着走不算远：3 格横 + 4 格竖 = 4 格 = 20 尺。"""
        hero, encounter = self.duel()
        foe = encounter.get("npc.foe")
        encounter.place(hero, 0, 0)
        encounter.place(foe, 3, 4)
        self.assertEqual(api.encounter_distance(encounter, hero, foe), 4 * FOOT)

    def test_within_uses_feet(self):
        hero, encounter = self.duel()
        foe = encounter.get("npc.foe")
        encounter.place(hero, 0, 0)
        encounter.place(foe, 2, 0)      # 10 尺
        self.assertTrue(encounter.within(hero, foe, 10))
        self.assertFalse(encounter.within(hero, foe, 5))

    def test_move_costs_movement(self):
        hero, encounter = self.duel()
        report = api.move_combatant(encounter, hero, 4, 0)
        self.assertEqual(report["feet"], 20)
        self.assertEqual(report["left"], 10)      # 德鲁伊步行 30

    def test_move_rejects_beyond_movement(self):
        hero, encounter = self.duel()
        with self.assertRaises(IllegalAction):
            api.move_combatant(encounter, hero, 7, 0)      # 35 尺 > 30

    def test_move_rejects_when_not_your_turn(self):
        hero, encounter = self.duel()
        encounter.next_turn()                  # 轮到对手
        with self.assertRaises(IllegalAction):
            api.move_combatant(encounter, hero, 2, 0)

    def test_move_rejects_occupied_cell(self):
        hero, encounter = self.duel()
        encounter.place(encounter.get("npc.foe"), 2, 0)
        with self.assertRaises(IllegalAction):
            api.move_combatant(encounter, hero, 2, 0)

    def test_nearby_lists_only_inside_radius(self):
        hero, encounter = self.duel()
        encounter.place(hero, 0, 0)
        encounter.place(encounter.get("npc.foe"), 2, 0)        # 10 尺
        self.assertEqual([r["label"] for r in api.nearby(encounter, hero, 10)], ["对手"])
        self.assertEqual(api.nearby(encounter, hero, 5), [])

    def test_view_warns_when_nothing_is_placed(self):
        """没人摆位时距离一律是 0，界面必须说明「这时的 30 尺没有意义」。"""
        _, encounter = self.duel()
        view = api.encounter_view(encounter)
        self.assertEqual(view["placed"], 0)
        self.assertIn("位置还没摆", view["distance_hint"])

    def test_view_hint_disappears_once_two_are_placed(self):
        hero, encounter = self.duel()
        encounter.place(hero, 0, 0)
        encounter.place(encounter.get("npc.foe"), 1, 0)
        self.assertEqual(api.encounter_view(encounter)["distance_hint"], "")


# --- 传送 -------------------------------------------------------------
class TeleportTests(Base):
    def test_teleport_does_not_cost_movement(self):
        hero, encounter = self.duel()
        before = encounter.get(hero).economy.movement
        api.teleport_combatant(encounter, hero, 6, 0, 30)      # 30 尺
        self.assertEqual(encounter.get(hero).economy.movement, before)

    def test_teleport_rejects_beyond_limit(self):
        hero, encounter = self.duel()
        with self.assertRaises(IllegalAction):
            api.teleport_combatant(encounter, hero, 7, 0, 30)  # 35 尺

    def test_teleport_rejects_occupied(self):
        hero, encounter = self.duel()
        encounter.place(encounter.get("npc.foe"), 2, 0)
        with self.assertRaises(IllegalAction):
            api.teleport_combatant(encounter, hero, 2, 0, 30)


# --- 月光步 -----------------------------------------------------------
class MoonlightStepTests(Base):
    def test_moves_the_druid_in_an_encounter(self):
        hero, encounter = self.duel()
        report = self.step(hero, encounter, {"to": (6, 0)})
        self.assertTrue(report["ok"])
        self.assertEqual((encounter.get(hero).x, encounter.get(hero).y), (6, 0))

    def test_charges_the_bonus_action(self):
        """传送成功要付一次附赠动作 —— 之前 api 另建了额度对象，这里一直是 1。"""
        hero, encounter = self.duel()
        self.step(hero, encounter, {"to": (6, 0)})
        self.assertEqual(encounter.get(hero).economy.bonus, 0)

    def test_without_encounter_it_says_not_resolved(self):
        hero = self.druid()
        report = api.use_power(hero, self.bundle, STEP, seed=1, choice={"to": (6, 0)})
        self.assertTrue(report["ok"])
        self.assertIn("未结算", report["message"])

    def test_without_destination_it_says_not_resolved(self):
        hero, encounter = self.duel()
        report = self.step(hero, encounter)
        self.assertIn("未结算", report["message"])
        self.assertEqual((encounter.get(hero).x, encounter.get(hero).y), (0, 0))

    def test_too_far_keeps_position_and_refunds(self):
        """超距是「没传成」，不是「传了半截」：位置不动，次数与附赠都要退回。"""
        hero, encounter = self.duel()
        before = hero.resources.get(STEP_POOL).available
        report = self.step(hero, encounter, {"to": (9, 9)})   # 45 尺
        self.assertFalse(report["ok"])
        self.assertEqual((encounter.get(hero).x, encounter.get(hero).y), (0, 0))
        self.assertEqual(hero.resources.get(STEP_POOL).available, before)
        self.assertEqual(encounter.get(hero).economy.bonus, 1)

    def test_occupied_target_keeps_position_and_refunds(self):
        hero, encounter = self.duel()
        encounter.place(encounter.get("npc.foe"), 1, 1)
        before = hero.resources.get(STEP_POOL).available
        report = self.step(hero, encounter, {"to": (1, 1)})
        self.assertFalse(report["ok"])
        self.assertEqual((encounter.get(hero).x, encounter.get(hero).y), (0, 0))
        self.assertEqual(hero.resources.get(STEP_POOL).available, before)
        self.assertEqual(encounter.get(hero).economy.bonus, 1)

    def test_success_does_spend_the_charge(self):
        """和上面两条成对：成功时必须扣，否则「退回」的测试会因为从不扣而恒真。"""
        hero, encounter = self.duel()
        before = hero.resources.get(STEP_POOL).available
        self.step(hero, encounter, {"to": (6, 0)})
        self.assertEqual(hero.resources.get(STEP_POOL).available, before - 1)


# --- Session 集成 -----------------------------------------------------
class SessionTests(Base):
    def test_session_shares_one_economy_object(self):
        """会话与遭遇战必须是**同一个**额度对象，否则两边各记一套。"""
        session = api.Session.open(PLUGINS, seed=3)
        hero = session.create_character(DRUID, 10, SCORES,
                                       name_zh="德鲁伊", name_en="Druid", subclass=MOON)
        encounter = session.start_encounter([self.foe()], rng=ScriptedRng([15, 5]))
        self.assertIs(encounter.get(hero).economy, session.economy)

    def test_new_turn_walks_the_order(self):
        session = api.Session.open(PLUGINS, seed=3)
        session.create_character(DRUID, 10, SCORES,
                                 name_zh="德鲁伊", name_en="Druid", subclass=MOON)
        session.start_encounter([self.foe()], rng=ScriptedRng([15, 5]))
        _, report = session.dispatch(api.NewTurn())     # 德鲁伊 → 对手
        self.assertIn("对手", report.message)
        _, report = session.dispatch(api.NewTurn())     # 对手 → 德鲁伊（第 2 轮）
        self.assertIn("德鲁伊", report.message)
        self.assertIn("第 2 轮", report.message)

    def test_rest_keeps_same_economy_object(self):
        """休息不能换对象：换了之后 Combatant 手里还是旧的，等于休息完还能再动。"""
        session = api.Session.open(PLUGINS, seed=3)
        session.create_character(DRUID, 10, SCORES,
                                 name_zh="德鲁伊", name_en="Druid", subclass=MOON)
        enemy = self.foe()
        encounter = session.start_encounter([enemy], rng=ScriptedRng([15, 5]))
        shared = session.economy
        session.dispatch(api.ShortRest(dice=1))
        self.assertIs(session.economy, shared)
        self.assertIs(encounter.get(session.character).economy, shared)


if __name__ == "__main__":
    unittest.main()
