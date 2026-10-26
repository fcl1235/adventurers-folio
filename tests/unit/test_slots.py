# -*- coding: utf-8 -*-
"""P8h 验收：法术位真的要花（G20 / G21）。

在此之前，「法术位」只是一个**显示用的池**：`roll_spell(apply=True)` 扣血、
扣免费次数，却从不扣位；能力上的 `cost: {slot_level: 2}` 只出现在副标题里。
于是 5 级法师可以无限放 1 环法术，而界面上的 4/4 一动不动 —— 这是比算错更糟的
一类问题：它看起来是算过的。

这组测试盯四件事：
  1. `apply=True` 扣位、`apply=False` 不扣（与伤害、免费次数同一条规矩）；
  2. 升环就是扣**指定的**那一环（用 3 环放 1 环法术不能只扣 1 环位）；
  3. 位不够时**拒绝**，不许白放；
  4. `cost.slot_level` 的能力按原文「2 环或更高」挑**最低**的可付环级。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import IllegalAction
from dnd5r.model.actor import ActorKind
from dnd5r.rules.rest import long_rest
from dnd5r.rules.spellcasting import lowest_slot, slot_pools, spend_slot

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
WIZARD = "dnd2024.class.wizard"
DRUID = "dnd2024.class.druid"
MOON = "dnd2024.subclass.druid.circle_of_the_moon"
STEP = MOON + ".moonlight_step"
RECOVER = MOON + ".moonlight_step_recover"
STEP_POOL = "dnd2024.resource.druid.circle_of_the_moon.moonlight_step"

SCORES = {"str": 8, "dex": 14, "con": 14, "int": 16, "wis": 12, "cha": 10}
MAGIC_MISSILE = "dnd2024.spell.magic_missile"     # 1 环，有伤害骰
FIRE_BOLT = "dnd2024.spell.fire_bolt"             # 戏法


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def wizard(self, level=5):
        return api.new_character(self.bundle, WIZARD, level, SCORES,
                                 name_zh="法师", name_en="Wizard")

    def druid(self, level=10):
        return api.new_character(
            self.bundle, DRUID, level, dict(SCORES, wis=16),
            name_zh="德鲁伊", name_en="Druid", subclass=MOON)

    @staticmethod
    def slots(actor):
        """{环级: 剩余}，只看法术位池。"""
        return {level: pool.available for level, pool in slot_pools(actor)}


class SpendSlotTest(Base):
    """底层原语：挑哪一环、扣不动时报什么。"""

    def test_spends_the_named_level(self):
        actor = self.wizard(5)
        before = self.slots(actor)
        pool = spend_slot(actor, 2)
        self.assertEqual(pool.id, "engine.slot.wizard.2")
        self.assertEqual(self.slots(actor)[2], before[2] - 1)
        self.assertEqual(self.slots(actor)[1], before[1])   # 别的环位不动

    def test_missing_level_is_an_error(self):
        """5 级法师没有 9 环位 —— 不能当作「免费放」处理。"""
        actor = self.wizard(5)
        with self.assertRaises(IllegalAction):
            spend_slot(actor, 9)

    def test_exhausted_level_is_an_error(self):
        actor = self.wizard(5)
        for _ in range(self.slots(actor)[1]):
            spend_slot(actor, 1)
        self.assertEqual(self.slots(actor)[1], 0)
        with self.assertRaises(IllegalAction):
            spend_slot(actor, 1)

    def test_actor_without_slots_is_left_alone(self):
        """怪物／随意施法的存在没有位账本：这里只返回 None，不拦。"""
        actor = self.wizard(5)
        actor.kind = ActorKind.MONSTER
        for pool in list(actor.resources.pools.values()):
            if pool.id.startswith("engine.slot."):
                del actor.resources.pools[pool.id]
        self.assertIsNone(spend_slot(actor, 1))

    def test_lowest_qualifying_level(self):
        """「2 环或更高」挑最低的那个：有 2 环就不许先烧 5 环。"""
        actor = self.wizard(9)
        self.assertEqual(lowest_slot(actor, 2), 2)
        for _ in range(self.slots(actor)[2]):
            spend_slot(actor, 2)
        self.assertEqual(lowest_slot(actor, 2), 3)

    def test_lowest_returns_none_when_nothing_left(self):
        actor = self.wizard(5)
        self.assertIsNone(lowest_slot(actor, 9))


class CastSpendsSlotTest(Base):
    """施法结算这条路上真的扣位。"""

    def test_apply_spends_one_slot(self):
        actor = self.wizard(5)
        before = self.slots(actor)[1]
        report = api.roll_spell(actor, self.bundle, MAGIC_MISSILE, 1,
                                apply=True, seed=1)
        self.assertEqual(self.slots(actor)[1], before - 1)
        self.assertEqual(report["slot_spend"]["level"], 1)
        self.assertEqual(report["slot_spend"]["spent"], 1)
        self.assertEqual(report["slot_spend"]["left"], before - 1)

    def test_dry_run_does_not_spend(self):
        actor = self.wizard(5)
        before = self.slots(actor)
        report = api.roll_spell(actor, self.bundle, MAGIC_MISSILE, 1, seed=1)
        self.assertEqual(self.slots(actor), before)
        self.assertEqual(report["slot_spend"]["spent"], 0)
        self.assertTrue(report["slot_spend"]["preview"])

    def test_cantrip_is_free(self):
        actor = self.wizard(5)
        before = self.slots(actor)
        report = api.roll_spell(actor, self.bundle, FIRE_BOLT, 0,
                                apply=True, seed=1)
        self.assertEqual(self.slots(actor), before)
        self.assertIsNone(report["slot_spend"])

    def test_free_cast_does_not_touch_slots(self):
        """专长给的那一次用池记账，不动法术位 —— 两条账不能混。"""
        actor = api.new_character(
            self.bundle, WIZARD, 5, SCORES,
            name_zh="法师", name_en="Wizard",
            feats=("dnd2024.feat.fey_touched",),
            choices={"dnd2024.feat.fey_touched.boost": ("int",),
                     "dnd2024.feat.fey_touched.spell": ("dnd2024.spell.bless",)},
        )
        before = self.slots(actor)
        report = api.roll_spell(actor, self.bundle, "dnd2024.spell.misty_step",
                                free=True, apply=True, seed=1)
        self.assertEqual(self.slots(actor), before)
        self.assertIsNone(report["slot_spend"])

    def test_upcast_spends_the_higher_level(self):
        """用 3 环放 1 环法术：伤害按 3 环算，扣的也必须是 3 环位。"""
        actor = self.wizard(5)
        before = self.slots(actor)
        report = api.roll_spell(actor, self.bundle, MAGIC_MISSILE, 3,
                                apply=True, seed=1)
        after = self.slots(actor)
        self.assertEqual(report["slot"], 3)
        self.assertEqual((before[1], before[3]), (after[1], after[3] + 1))

    def test_out_of_slots_refuses(self):
        actor = self.wizard(2)          # 2 级法师只有 1 环位
        for _ in range(self.slots(actor)[1]):
            api.roll_spell(actor, self.bundle, MAGIC_MISSILE, 1, apply=True, seed=1)
        with self.assertRaises(IllegalAction):
            api.roll_spell(actor, self.bundle, MAGIC_MISSILE, 1, apply=True, seed=1)

    def test_long_rest_restores_slots(self):
        actor = self.wizard(5)
        api.roll_spell(actor, self.bundle, MAGIC_MISSILE, 1, apply=True, seed=1)
        long_rest(actor)
        self.assertEqual(self.slots(actor)[1], 4)


class PowerSlotCostTest(Base):
    """能力上的 `cost.slot_level`：检查、扣最低、回气。"""

    def test_recover_power_spends_the_lowest_slot(self):
        actor = self.druid()
        for _ in range(3):
            api.use_power(actor, self.bundle, STEP)
        self.assertEqual(actor.resources.get(STEP_POOL).available, 0)
        before = self.slots(actor)
        report = api.use_power(actor, self.bundle, RECOVER)
        self.assertTrue(report["ok"], report["message"])
        after = self.slots(actor)
        self.assertEqual(actor.resources.get(STEP_POOL).available, 1)
        self.assertEqual((before[2], after[2]), (after[2] + 1, after[2]))  # 扣的是 2 环
        self.assertEqual(before[3], after[3])                              # 3 环没动

    def test_recover_power_blocked_without_slots(self):
        """位用光后按钮要点不动，而且原因是数据算出来的（前端不判断）。"""
        actor = self.druid()
        for _ in range(30):          # 有界循环：位就那么多，别写成「直到用光」的死循环
            if lowest_slot(actor, 2) is None:
                break
            api.use_power(actor, self.bundle, RECOVER)
        self.assertIsNone(lowest_slot(actor, 2))
        sheet = api.character_sheet(actor, self.bundle)
        row = next(item for item in sheet["powers"] if item["id"] == RECOVER)
        self.assertTrue(row["blocked"])
        self.assertIn("法术位", "".join(row["blocked"]))

    def test_recover_never_exceeds_capacity(self):
        actor = self.druid()            # 池满 3/3
        report = api.use_power(actor, self.bundle, RECOVER)
        self.assertTrue(report["ok"])
        self.assertEqual(actor.resources.get(STEP_POOL).available, 3)


if __name__ == "__main__":
    unittest.main()
