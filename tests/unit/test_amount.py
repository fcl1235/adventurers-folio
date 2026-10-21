# -*- coding: utf-8 -*-
"""数量表达式：1d10 + 职业等级这类写法必须可解析、可求值、可复现。"""

import unittest

from dnd5r.kernel.errors import RuleError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.rules.amount import parse_amount

CTX = {"prof_bonus": 3, "total_level": 5, "class_level": 5, "speeds": {"walk": 30}}


class AmountParseTest(unittest.TestCase):
    def test_int(self):
        amount = parse_amount(5)
        self.assertEqual(amount.evaluate(CTX), 5)
        self.assertEqual(amount.describe(CTX), "5")

    def test_dice_string(self):
        amount = parse_amount("2d6")
        self.assertEqual(amount.evaluate(CTX), 12)
        self.assertAlmostEqual(amount.average, 7.0)

    def test_dice_plus_level(self):
        amount = parse_amount({"dice": "1d10", "plus": "class_level"})
        self.assertEqual(amount.evaluate(CTX), 15)  # 10 + 5
        self.assertEqual(amount.describe(CTX), "1d10+5")

    def test_flat_times_level(self):
        amount = parse_amount({"flat": 5, "times": "class_level"})
        self.assertEqual(amount.evaluate(CTX), 25)
        self.assertEqual(amount.describe(CTX), "5×5")

    def test_total_level_differs_from_class_level(self):
        """回气加的是职业等级；兼职时两者不同，写错就是静默算错。"""
        ctx = {"prof_bonus": 4, "total_level": 10, "class_level": 3}
        amount = parse_amount({"dice": "1d10", "plus": "class_level"})
        self.assertEqual(amount.evaluate(ctx), 13)
        other = parse_amount({"dice": "1d10", "plus": "total_level"})
        self.assertEqual(other.evaluate(ctx), 20)

    def test_roll_uses_rng(self):
        amount = parse_amount({"dice": "1d10", "plus": "class_level"})
        value, rolled = amount.roll(CTX, ScriptedRng([6]))
        self.assertEqual(value, 11)
        self.assertEqual(rolled.total, 6)
        self.assertIn("1d10", rolled.describe())

    def test_rejects_unknown_field(self):
        with self.assertRaises(RuleError):
            parse_amount({"dice": "1d6", "bonus": 3})

    def test_rejects_unknown_ref(self):
        with self.assertRaises(RuleError):
            parse_amount({"flat": 1, "plus": "weapon_damage"})

    def test_rejects_empty(self):
        with self.assertRaises(RuleError):
            parse_amount({})

    def test_rejects_bool(self):
        with self.assertRaises(RuleError):
            parse_amount(True)

    def test_rejects_int_dice(self):
        with self.assertRaises(RuleError):
            parse_amount({"dice": 6})

    def test_to_dict_roundtrip(self):
        amount = parse_amount({"dice": "1d10", "plus": "class_level"})
        data = amount.to_dict()
        again = parse_amount(data)
        self.assertEqual(again.evaluate(CTX), amount.evaluate(CTX))


if __name__ == "__main__":
    unittest.main()
