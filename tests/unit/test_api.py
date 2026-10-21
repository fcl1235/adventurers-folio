# -*- coding: utf-8 -*-
"""门面测试：前端只该看到这些。"""

import unittest

import dnd5r.api as api
from dnd5r.kernel.errors import RuleError

SCORES = {"str": 16, "dex": 14, "con": 12, "int": 10, "wis": 12, "cha": 8}


class ApiTest(unittest.TestCase):
    def test_create_and_view_single_class(self):
        actor = api.create_actor("冒险者", "Adventurer", SCORES, [("demo.class_a", 5)], hp_max=32)
        view = api.actor_view(actor)
        self.assertEqual(view["total_level"], 5)
        self.assertEqual(view["proficiency_bonus"], 3)
        self.assertFalse(view["multiclass"])
        self.assertTrue(view["ac"].startswith("12"), view["ac"])
        self.assertEqual(view["hp"]["maximum"], 32)
        self.assertEqual(view["abilities"]["str"]["mod"], 3)

    def test_multiclass_view(self):
        actor = api.create_actor("兼职者", "Multiclass", SCORES,
                                 [("demo.class_a", 5), ("demo.class_b", 3)])
        view = api.actor_view(actor)
        self.assertEqual(view["total_level"], 8)
        self.assertTrue(view["multiclass"])
        self.assertEqual([row["class_level"] for row in view["classes"]], [5, 3])

    def test_total_level_cap(self):
        with self.assertRaises(RuleError):
            api.create_actor("超限", "Over", SCORES,
                             [("demo.class_a", 12), ("demo.class_b", 9)])

    def test_locale_switch(self):
        actor = api.create_actor("冒险者", "Adventurer", SCORES, [("demo.class_a", 1)])
        self.assertEqual(api.actor_view(actor, locale="en")["name"], "Adventurer")
        self.assertEqual(api.actor_view(actor, locale="zh")["name"], "冒险者")

    def test_plugin_summary(self):
        rows = api.plugin_summary("plugins")
        self.assertEqual([row["id"] for row in rows], ["dnd2024-core"])


if __name__ == "__main__":
    unittest.main()
