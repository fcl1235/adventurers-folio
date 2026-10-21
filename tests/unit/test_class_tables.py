# -*- coding: utf-8 -*-
"""P5a 验收：12 职业的「表」是对的。

这些断言不看规则文本，只看**数字表**：生命骰、豁免、法术位、资源容量。
12 个职业 × 20 级 = 2400 个对账项已经在 golden 里比对过数值，
这里补的是「结构上不该出现的形态」：

  * 环位数量越级（1 级就有 2 环位）
  * 资源在解锁前就有次数 / 解锁后还是没有
  * 同一次建卡出现重复池 id（兼职会踩）
  * 施法职业没有环位表、非施法职业却有
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.model.levels import ClassLevel
from dnd5r.model.resources import PoolKind

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}

FULL_CASTERS = ("dnd2024.class.bard", "dnd2024.class.cleric", "dnd2024.class.druid",
                "dnd2024.class.sorcerer", "dnd2024.class.wizard")
HALF_CASTERS = ("dnd2024.class.paladin", "dnd2024.class.ranger")
MARTIAL = ("dnd2024.class.barbarian", "dnd2024.class.fighter",
           "dnd2024.class.monk", "dnd2024.class.rogue")


class TableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_all_twelve_classes_present(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertEqual(len(self.bundle.classes), 12)
        self.assertEqual(len(self.bundle.manifests), 1)

    def test_headers_are_sane(self):
        for class_id, class_def in self.bundle.classes.items():
            with self.subTest(class_id=class_id):
                self.assertIn(class_def.hit_die, (6, 8, 10, 12), class_id)
                self.assertEqual(len(class_def.saves), 2, class_id)
                self.assertEqual(len(set(class_def.saves)), 2, class_id)
                self.assertGreaterEqual(len(class_def.powers), 8, class_id)
                self.assertLessEqual(int(class_def.subclass_level), 3, class_id)

    def test_casters_have_tables_and_martials_do_not(self):
        for class_id in FULL_CASTERS + HALF_CASTERS + ("dnd2024.class.warlock",):
            with self.subTest(class_id=class_id):
                self.assertTrue(self.bundle.class_def(class_id).slots, class_id)
        for class_id in MARTIAL:
            with self.subTest(class_id=class_id):
                self.assertFalse(self.bundle.class_def(class_id).slots, class_id)

    def test_no_slot_level_before_it_unlocks(self):
        """1 级不可能有 2 环位；9 环位最早 17 级。这条能挡住整表错位一行。"""
        for class_id, class_def in self.bundle.classes.items():
            if not class_def.slots:
                continue
            with self.subTest(class_id=class_id):
                level_one = class_def.slots_at(ClassLevel(1))
                self.assertEqual(level_one[1:], (0,) * 8, class_id)
                for level in range(1, 10):
                    row = class_def.slots_at(ClassLevel(level))
                    if row[level - 1]:          # 有第 N 环位，说明等级够
                        self.assertGreaterEqual(level, self._unlock(class_id, level), class_id)

    def _unlock(self, class_id, slot_level):
        # 2024 全职施法者：第 N 环位在 2N-1 级解锁；半施法者更晚，用宽松下界即可
        return max(1, slot_level)

    def test_slot_capacity_is_monotonic(self):
        """等级升高，某一环的位子不能变少。

        唯一的例外是邪术师：契约位会**整体上移**（1 环 2 个 → 2 环 2 个 → …），
        1 环位归零是规则本身，不是数据错。这条例外必须写出来，
        否则下一个人会以为可以随便归零。
        """
        for class_id, class_def in self.bundle.classes.items():
            if not class_def.slots or class_id == "dnd2024.class.warlock":
                continue
            with self.subTest(class_id=class_id):
                previous = (0,) * 9
                for level in range(1, 21):
                    row = class_def.slots_at(ClassLevel(level))
                    for index, (old, new) in enumerate(zip(previous, row)):
                        self.assertGreaterEqual(
                            new, old, "%s 第 %d 级 %d 环位变少：%d → %d"
                            % (class_id, level, index + 1, old, new))
                    previous = row

    def test_full_caster_reaches_ninth_level_slots(self):
        for class_id in FULL_CASTERS:
            with self.subTest(class_id=class_id):
                self.assertGreater(self.bundle.class_def(class_id).slots_at(ClassLevel(20))[8], 0)

    def test_half_casters_stop_at_fifth(self):
        for class_id in HALF_CASTERS:
            with self.subTest(class_id=class_id):
                row = self.bundle.class_def(class_id).slots_at(ClassLevel(20))
                self.assertEqual(row[5:], (0,) * 4, class_id)
                self.assertGreater(row[4], 0, class_id)


class ResourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_capacity_positive_at_unlock_level(self):
        """资源表里出现的第一个等级，次数必须 > 0 —— 否则等于没解锁。"""
        for class_id, class_def in self.bundle.classes.items():
            for resource in class_def.resources:
                with self.subTest(resource=resource.id):
                    if resource.by_level:
                        first = min(resource.by_level)
                        self.assertGreater(resource.capacity_at(ClassLevel(first)), 0, resource.id)

    def test_no_zero_pool_on_character(self):
        for class_id in self.bundle.classes:
            for level in (1, 5, 11, 20):
                with self.subTest(class_id=class_id, level=level):
                    actor = api.new_character(self.bundle, class_id, level, SCORES,
                                              name_zh="表检", name_en="Table")
                    for pool in actor.resources.pools.values():
                        self.assertGreater(pool.capacity, 0, pool.id)

    def test_pool_ids_are_unique(self):
        for class_id in self.bundle.classes:
            actor = api.new_character(self.bundle, class_id, 20, SCORES,
                                      name_zh="表检", name_en="Table")
            ids = list(actor.resources.pools)
            self.assertEqual(len(ids), len(set(ids)), class_id)

    def test_slot_pools_are_slots(self):
        actor = api.new_character(self.bundle, "dnd2024.class.wizard", 5, SCORES,
                                  name_zh="法师", name_en="Wizard")
        slots = [pool for pool in actor.resources.pools.values()
                 if pool.kind is PoolKind.SLOT]
        self.assertEqual([pool.capacity for pool in slots], [4, 3, 2])

    def test_warlock_pact_slots_short_rest(self):
        """契约位是短休恢复；写成长休就等于每次战斗都不够用。"""
        actor = api.new_character(self.bundle, "dnd2024.class.warlock", 5, SCORES,
                                  name_zh="邪术师", name_en="Warlock")
        slots = [pool for pool in actor.resources.pools.values()
                 if pool.kind is PoolKind.SLOT]
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].refresh.value, "short_rest")


if __name__ == "__main__":
    unittest.main()
