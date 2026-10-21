# -*- coding: utf-8 -*-
"""生命值：公式、下限保护、兼职分段。"""

import unittest

from dnd5r.kernel.errors import RuleError
from dnd5r.model.levels import ClassLevel
from dnd5r.rules.health import (
    hit_dice_average,
    hit_dice_pool,
    hp_per_level,
    hit_points_max,
    multiclass_hit_points,
)


class HitPointsTest(unittest.TestCase):
    def test_level_one_is_full_die_plus_con(self):
        self.assertEqual(hit_points_max(10, 2, ClassLevel(1)), 12)
        self.assertEqual(hit_points_max(6, -1, ClassLevel(1)), 5)

    def test_fighter_twenty(self):
        """20 级战士、体质 14：10+2 + 19×(5+1+2) = 164。"""
        self.assertEqual(hit_points_max(10, 2, ClassLevel(20)), 164)

    def test_per_level_is_half_die_plus_one(self):
        self.assertEqual(hp_per_level(10, 2), 8)
        self.assertEqual(hp_per_level(12, 0), 7)
        self.assertEqual(hp_per_level(6, -3), 1)  # 下限 1，不能变成负数回血

    def test_negative_con_still_grows(self):
        low = hit_points_max(6, -2, ClassLevel(1))
        high = hit_points_max(6, -2, ClassLevel(10))
        self.assertGreater(high, low)

    def test_per_level_bonus(self):
        base = hit_points_max(10, 2, ClassLevel(5))
        self.assertEqual(hit_points_max(10, 2, ClassLevel(5), per_level_bonus=1),
                         base + 5)

    def test_flat_bonus(self):
        base = hit_points_max(10, 2, ClassLevel(5))
        self.assertEqual(hit_points_max(10, 2, ClassLevel(5), flat_bonus=40),
                         base + 40)

    def test_level_must_be_positive(self):
        with self.assertRaises(RuleError):
            hit_points_max(10, 2, ClassLevel(0))

    def test_multiclass_sums_segments(self):
        """5 级战士 + 3 级法师：两段都各自按「首级满骰」算，这才是 SRD 的做法。"""
        total = multiclass_hit_points([(10, ClassLevel(5)), (6, ClassLevel(3))], 2)
        self.assertEqual(total, hit_points_max(10, 2, ClassLevel(5)) + hit_points_max(6, 2, ClassLevel(3)))

    def test_hit_dice_pool(self):
        pool = hit_dice_pool("demo.class_a", 10, ClassLevel(5))
        self.assertEqual(pool.capacity, 5)
        self.assertEqual(pool.id, "hit_dice.demo.class_a")
        self.assertEqual(pool.owner_class, "demo.class_a")

    def test_hit_dice_average(self):
        self.assertEqual(hit_dice_average(10), 6)
        self.assertEqual(hit_dice_average(6), 4)


if __name__ == "__main__":
    unittest.main()
