# -*- coding: utf-8 -*-
"""P4 验收：状态 / 力竭 / 濒死 / 专注。

这四样最容易出的错不是「算错了」，而是**算了一半**：

  1. 力竭只扣了豁免没扣攻击（或反之）—— 所以断言是「全部 d20」而不是抽查一个
  2. 力竭没有明细，界面上只看到一个变小的数字，玩家没法核对
  3. 死亡豁免被写成「d20 + 体质」或自然 1 只记一次失败
  4. 状态被当成「已计入数值」，而实际上规则效果根本没实现 —— 撒谎型 UI

所以下面既断言数值，也断言「界面能读到的那句话」。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import RuleError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.model.actor import Actor, ActorKind, HpPool, MAX_EXHAUSTION
from dnd5r.model.death import DeathSaves
from dnd5r.model.statblock import Abilities, Statblock
from dnd5r.rules.build import rebuild_actor
from dnd5r.rules.death import resolve_death_save
from dnd5r.rules.resolver import exhaustion_penalty, exhaustion_speed_penalty

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"
ROGUE = "dnd2024.class.rogue"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
DEX_SCORES = {"str": 10, "dex": 17, "con": 14, "int": 12, "wis": 12, "cha": 10}


class ExhaustionTest(unittest.TestCase):
    """力竭是真计入数值的 —— 每级全部 d20 −2、速度 −5 尺。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _actor(self, class_id=FIGHTER, scores=None):
        return api.new_character(self.bundle, class_id, 5, scores or SCORES)

    def test_penalty_constants(self):
        self.assertEqual(exhaustion_penalty(0), 0)
        self.assertEqual(exhaustion_penalty(1), -2)
        self.assertEqual(exhaustion_penalty(3), -6)
        self.assertEqual(exhaustion_speed_penalty(2), -10)

    def test_every_d20_drops_by_four_at_level_two(self):
        """**全部** d20：六项豁免、全部技能、攻击、先攻。查一个不算数。"""
        actor = self._actor()
        before = api.character_sheet(actor, self.bundle)
        api.set_exhaustion(actor, 2)
        after = api.character_sheet(actor, self.bundle)

        for key in ("str", "dex", "con", "int", "wis", "cha"):
            self.assertEqual(after["saves"][key]["total"],
                             before["saves"][key]["total"] - 4,
                             "力竭 2 级时 %s 豁免该 −4" % key)
            self.assertIn("力竭 2 级", after["saves"][key]["detail"],
                          "明细里必须写清这 4 点是力竭扣的")
        for row_before, row_after in zip(before["skills"], after["skills"]):
            self.assertEqual(row_after["total"], row_before["total"] - 4,
                             "力竭 2 级时技能「%s」该 −4" % row_after["name"])
        self.assertEqual(after["attack"]["total"], before["attack"]["total"] - 4)
        self.assertEqual(after["initiative"]["total"], before["initiative"]["total"] - 4)

    def test_speed_drops_five_per_level(self):
        actor = self._actor()
        before = api.character_sheet(actor, self.bundle)["speed"]["walk"]
        api.set_exhaustion(actor, 2)
        after = api.character_sheet(actor, self.bundle)["speed"]["walk"]
        self.assertEqual(after, before - 10)

    def test_speed_never_goes_negative(self):
        """6 级时速度会扣到 0 以下 —— 负速度在桌上没有意义，卡在 0。"""
        actor = self._actor()
        api.set_exhaustion(actor, MAX_EXHAUSTION)
        self.assertEqual(api.character_sheet(actor, self.bundle)["speed"]["walk"], 0)

    def test_sheet_reports_its_own_penalty(self):
        """界面不许自己乘 2：减值与速度惩罚都从 sheet 读，避免两处对不上。"""
        actor = self._actor()
        api.set_exhaustion(actor, 3)
        info = api.character_sheet(actor, self.bundle)["exhaustion"]
        self.assertEqual(info["level"], 3)
        self.assertEqual(info["penalty"], -6)
        self.assertEqual(info["speed"], -15)
        self.assertEqual(info["max"], MAX_EXHAUSTION)

    def test_level_is_validated(self):
        actor = self._actor()
        self.assertEqual(api.set_exhaustion(actor, 0), 0)
        for bad in (-1, 7, "2", 2.0, True):
            with self.assertRaises(RuleError, msg="力竭等级 %r 该被拒" % (bad,)):
                api.set_exhaustion(actor, bad)

    def test_survives_rebuild(self):
        """改个专长不该把「力竭 2 级」抹掉 —— 那是玩家记的事实，不是派生值。"""
        actor = self._actor()
        api.set_exhaustion(actor, 2)
        actor.death_saves.failed = 2
        fresh = rebuild_actor(self.bundle, actor)
        self.assertEqual(fresh.exhaustion, 2)
        self.assertEqual(fresh.death_saves.failed, 2,
                         "重建不能让人「复活」")
        self.assertEqual(api.character_sheet(fresh, self.bundle)["exhaustion"]["penalty"], -4)


class ConditionTest(unittest.TestCase):
    """状态只记录、不计入数值 —— 界面必须这么说，测试也这么断言。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_toggle_is_idempotent(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        self.assertTrue(api.set_condition(actor, "prone", True))
        self.assertFalse(api.set_condition(actor, "prone", True), "重复记不算变化")
        self.assertIn("prone", api.character_sheet(actor, self.bundle)["conditions"])
        self.assertTrue(api.set_condition(actor, "prone", False))
        self.assertFalse(api.set_condition(actor, "prone", False))

    def test_empty_id_refused(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        for bad in ("", "   ", None):
            with self.assertRaises(RuleError):
                api.set_condition(actor, bad, True)

    def test_conditions_do_not_change_numbers(self):
        """**这是有意为之**：倒地/束缚的后果要看具体情形，硬算只会算错。
        所以这里断言「数值不变」，界面负责说明「未计入」。"""
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        before = api.character_sheet(actor, self.bundle)
        api.set_condition(actor, "restrained", True)
        api.set_condition(actor, "prone", True)
        after = api.character_sheet(actor, self.bundle)
        self.assertEqual(after["ac"]["total"], before["ac"]["total"])
        self.assertEqual(after["speed"]["walk"], before["speed"]["walk"])
        self.assertEqual(len(after["conditions"]), 2)

    def test_clear_conditions_reports_what_went(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        api.set_condition(actor, "prone", True)
        api.set_condition(actor, "poisoned", True)
        self.assertEqual(api.clear_conditions(actor), ("poisoned", "prone"))
        self.assertEqual(api.character_sheet(actor, self.bundle)["conditions"], [])


class DeathSaveTest(unittest.TestCase):
    """死亡豁免：10 以上成功、自然 1 记两次失败、自然 20 回 1 HP。"""

    def _saves(self):
        return DeathSaves()

    def test_dc_is_ten_inclusive(self):
        saves = self._saves()
        self.assertFalse(resolve_death_save(saves, 9)["success"])
        self.assertEqual(saves.failed, 1)
        self.assertTrue(resolve_death_save(saves, 10)["success"])
        self.assertEqual(saves.succeeded, 1)

    def test_natural_one_is_two_failures(self):
        saves = self._saves()
        result = resolve_death_save(saves, 1)
        self.assertFalse(result["success"])
        self.assertEqual(saves.failed, 2, "自然 1 记**两次**失败")

    def test_three_failures_is_death_and_locks(self):
        saves = self._saves()
        resolve_death_save(saves, 3)
        resolve_death_save(saves, 4)
        result = resolve_death_save(saves, 1)
        self.assertEqual(result["outcome"], "dead")
        # 死后再掷不许把结果改回去，否则「连掷就能复活」
        again = resolve_death_save(saves, 20)
        self.assertEqual(again["outcome"], "dead")
        self.assertTrue(saves.dead)

    def test_three_successes_is_stable(self):
        saves = self._saves()
        for _ in range(3):
            result = resolve_death_save(saves, 12)
        self.assertEqual(result["outcome"], "stable")
        self.assertFalse(saves.dead)

    def test_natural_twenty_revives_with_one_hp(self):
        saves = self._saves()
        saves.failed = 2
        result = resolve_death_save(saves, 20)
        self.assertTrue(result["revived"])
        self.assertEqual(result["outcome"], "revived")
        self.assertEqual((saves.succeeded, saves.failed), (0, 0), "回魂后记分清零")

    def test_api_revive_raises_hp_to_one(self):
        bundle = api.load_content(PLUGINS)
        actor = api.new_character(bundle, FIGHTER, 5, SCORES)
        actor.hp.current = 0
        result = api.roll_death_save(actor, ScriptedRng([20]))
        self.assertEqual(result["roll"], 20)
        self.assertEqual(actor.hp.current, 1)

    def test_api_refuses_when_not_dying(self):
        bundle = api.load_content(PLUGINS)
        actor = api.new_character(bundle, FIGHTER, 5, SCORES)
        with self.assertRaises(RuleError):
            api.roll_death_save(actor, ScriptedRng([20]))

    def test_reset(self):
        bundle = api.load_content(PLUGINS)
        actor = api.new_character(bundle, FIGHTER, 5, SCORES)
        actor.hp.current = 0
        api.roll_death_save(actor, ScriptedRng([2]))
        api.reset_death_saves(actor)
        view = api.death_save_view(actor)
        self.assertEqual((view["succeeded"], view["failed"]), (0, 0))
        self.assertFalse(view["dead"] or view["stable"])


class ConcentrationTest(unittest.TestCase):
    def test_dc_table(self):
        self.assertEqual(api.concentration_dc(0), 10)
        self.assertEqual(api.concentration_dc(7), 10)
        self.assertEqual(api.concentration_dc(20), 10)
        self.assertEqual(api.concentration_dc(21), 10)
        self.assertEqual(api.concentration_dc(22), 11)
        self.assertEqual(api.concentration_dc(41), 20)

    def test_bad_input(self):
        with self.assertRaises(RuleError):
            api.concentration_dc(-1)
        with self.assertRaises(RuleError):
            api.concentration_dc("十")


class StateSaveTest(unittest.TestCase):
    """v1 存档读进来要有默认值；v2 要往返。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_round_trip(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        api.set_condition(actor, "prone", True)
        api.set_exhaustion(actor, 2)
        actor.hp.current = 0
        actor.death_saves.failed = 1
        payload = api.save_character(actor)
        self.assertEqual(payload["version"], api.SAVE_VERSION)
        self.assertEqual(payload["exhaustion"], 2)
        self.assertEqual(payload["death_saves"]["failed"], 1)
        self.assertIn("prone", payload["conditions"])

        fresh = api.load_character(self.bundle, payload)
        self.assertEqual(fresh.exhaustion, 2)
        self.assertEqual(fresh.death_saves.failed, 1)
        self.assertIn("prone", fresh.conditions.ids())

    def test_v1_save_loads_with_defaults(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        payload = api.save_character(actor)
        for key in ("conditions", "exhaustion", "death_saves"):
            payload.pop(key)
        payload["version"] = 1
        fresh = api.load_character(self.bundle, payload)
        self.assertEqual(fresh.exhaustion, 0)
        self.assertEqual((fresh.death_saves.succeeded, fresh.death_saves.failed), (0, 0))
        self.assertEqual(fresh.conditions.ids(), ())

    def test_bad_exhaustion_in_file_is_clamped(self):
        """存档被人手改成 99 级时别让整份档读不开 —— 夹到上限。"""
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        payload = api.save_character(actor)
        payload["exhaustion"] = 99
        fresh = api.load_character(self.bundle, payload)
        self.assertEqual(fresh.exhaustion, MAX_EXHAUSTION)


if __name__ == "__main__":
    unittest.main()
