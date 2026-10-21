# -*- coding: utf-8 -*-
"""内核测试：Text / Dice / Predicate / Ids。"""

import unittest

from dnd5r.kernel import dice, ids, predicate
from dnd5r.kernel.errors import DiceError, IdError, PredicateError, RngError, TextError
from dnd5r.kernel.rng import ScriptedRng, SeededRng
from dnd5r.kernel.text import Text


class TextTest(unittest.TestCase):
    def test_both_languages_required(self):
        with self.assertRaises(TextError):
            Text(zh="回气", en="")
        with self.assertRaises(TextError):
            Text(zh="  ", en="Second Wind")

    def test_from_dict_rejects_plain_string(self):
        with self.assertRaises(TextError):
            Text.from_dict("回气")
        with self.assertRaises(TextError):
            Text.from_dict({"zh": "回气"})

    def test_get_by_locale(self):
        text = Text.of("回气", "Second Wind")
        self.assertEqual(text.get("zh"), "回气")
        self.assertEqual(text.get("en"), "Second Wind")
        with self.assertRaises(TextError):
            text.get("fr")


class DiceTest(unittest.TestCase):
    def test_parse_and_bounds(self):
        expr = dice.parse("2d6+3")
        self.assertEqual(expr.minimum, 5)
        self.assertEqual(expr.maximum, 15)
        self.assertAlmostEqual(expr.average, 10.0)

    def test_roll_is_deterministic_with_scripted_rng(self):
        expr = dice.parse("2d6+3")
        result = expr.roll(ScriptedRng([4, 5]))
        self.assertEqual(result.total, 12)
        self.assertIn("2d6[4,5]", result.describe())

    def test_mixed_terms(self):
        expr = dice.parse("1d8+1d4-1")
        self.assertEqual(expr.minimum, 1)
        self.assertEqual(expr.maximum, 11)

    def test_bad_expressions(self):
        for bad in ("", "abc", "-2d6", "2d"):
            with self.assertRaises(DiceError):
                dice.parse(bad)

    def test_advantage_keeps_higher(self):
        result = dice.roll_d20(ScriptedRng([3, 17]), mode="adv")
        self.assertEqual(result.total, 17)
        self.assertEqual(result.parts[0].dropped, (3,))

    def test_scripted_rng_out_of_range(self):
        with self.assertRaises(RngError):
            dice.parse("1d6").roll(ScriptedRng([9]))

    def test_seeded_rng_is_reproducible(self):
        first = dice.parse("3d6").roll(SeededRng(42)).total
        second = dice.parse("3d6").roll(SeededRng(42)).total
        self.assertEqual(first, second)


class PredicateTest(unittest.TestCase):
    def test_plain_and_suffix(self):
        ctx = {"raging": True, "hp": 6, "d20": 9}
        self.assertTrue(predicate.evaluate({"raging": True}, ctx))
        self.assertFalse(predicate.evaluate({"raging": False}, ctx))
        self.assertTrue(predicate.evaluate({"hp_lte": 10}, ctx))
        self.assertTrue(predicate.evaluate({"d20_lte": 9}, ctx))
        self.assertFalse(predicate.evaluate({"d20_lt": 9}, ctx))

    def test_dotted_path_and_missing_key(self):
        ctx = {"combat": {"has_advantage": True}}
        self.assertTrue(predicate.evaluate({"combat.has_advantage": True}, ctx))
        self.assertFalse(predicate.evaluate({"combat.has_disadvantage": True}, ctx))

    def test_combinators(self):
        ctx = {"a": 1, "b": 2}
        self.assertTrue(predicate.evaluate({"all": [{"a": 1}, {"b": 2}]}, ctx))
        self.assertTrue(predicate.evaluate({"any": [{"a": 9}, {"b": 2}]}, ctx))
        self.assertTrue(predicate.evaluate({"not": {"a": 9}}, ctx))

    def test_bad_condition_type(self):
        with self.assertRaises(PredicateError):
            predicate.evaluate("raging", {})

    def test_explain_lists_reasons(self):
        reasons = predicate.explain({"hp_lte": 3}, {"hp": 10})
        self.assertEqual(len(reasons), 1)


class IdsTest(unittest.TestCase):
    def test_valid_and_invalid(self):
        self.assertTrue(ids.is_valid("dnd2024.power.second_wind"))
        self.assertTrue(ids.is_valid("demo.power.x1"))
        self.assertFalse(ids.is_valid("Fighter"))
        self.assertFalse(ids.is_valid("fighter"))
        self.assertFalse(ids.is_valid("demo..x"))

    def test_parse_tail(self):
        self.assertEqual(ids.tail("demo.power.second_wind"), "second_wind")
        with self.assertRaises(IdError):
            ids.parse("bad id")


if __name__ == "__main__":
    unittest.main()
