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


FIGHTER = "dnd2024.class.fighter"
FIGHTER_SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


class ContentApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content("plugins")

    def make(self, level=1):
        return api.new_character(self.bundle, FIGHTER, level, FIGHTER_SCORES,
                                 name_zh="测试战士", name_en="Test Fighter")

    def test_content_summary(self):
        summary = api.content_summary(self.bundle)
        self.assertEqual(summary["classes"], 1)
        self.assertEqual(summary["errors"], 0)
        self.assertIn("战士", summary["class_names"])

    def test_new_character_matches_oracle_numbers(self):
        """与旧程序对齐：1 级战士、16/14/14/10/12/8 → HP 12、AC 12、力量豁免 +5。"""
        sheet = api.character_sheet(self.make(1), self.bundle)
        self.assertEqual(sheet["hp"]["maximum"], 12)
        self.assertEqual(sheet["ac"]["total"], 12)
        self.assertEqual(sheet["saves"]["str"]["total"], 5)
        self.assertEqual(sheet["saves"]["con"]["total"], 4)
        self.assertEqual(sheet["attack"]["total"], 5)
        self.assertEqual(sheet["proficiency_bonus"], 2)
        self.assertEqual(sheet["attacks_per_action"], 1)

    def test_higher_level_numbers(self):
        sheet = api.character_sheet(self.make(20), self.bundle)
        self.assertEqual(sheet["hp"]["maximum"], 164)
        self.assertEqual(sheet["proficiency_bonus"], 6)
        self.assertEqual(sheet["attacks_per_action"], 4)

    def test_pools_and_hit_dice(self):
        sheet = api.character_sheet(self.make(10), self.bundle)
        pools = {row["id"]: row for row in sheet["pools"]}
        self.assertEqual(pools["dnd2024.resource.fighter.second_wind"]["max"], 4)
        self.assertEqual(pools["dnd2024.resource.fighter.action_surge"]["max"], 1)
        self.assertEqual(pools["dnd2024.resource.fighter.indomitable"]["max"], 1)
        self.assertEqual(sheet["hp"]["hit_dice"][0]["max"], 10)

    def test_low_level_has_no_indomitable_pool(self):
        sheet = api.character_sheet(self.make(5), self.bundle)
        ids = {row["id"] for row in sheet["pools"]}
        self.assertNotIn("dnd2024.resource.fighter.indomitable", ids)

    def test_powers_filtered_by_level(self):
        sheet = api.character_sheet(self.make(5), self.bundle)
        names = [row["name"] for row in sheet["powers"]]
        self.assertIn("额外攻击", names)
        self.assertNotIn("不屈", names)

    def test_use_power_spends_pool_and_heals(self):
        actor = self.make(1)
        actor.hp.current = 2
        result = api.use_power(actor, self.bundle, "dnd2024.class.fighter.second_wind", seed=1)
        self.assertTrue(result["ok"])
        self.assertEqual(actor.resources.get("dnd2024.resource.fighter.second_wind").available, 1)
        self.assertGreater(actor.hp.current, 2)
        self.assertTrue(result["rolls"])
        self.assertEqual(result["economy"]["bonus"], 0)

    def test_use_power_when_exhausted(self):
        actor = self.make(1)
        api.use_power(actor, self.bundle, "dnd2024.class.fighter.second_wind", seed=1)
        api.use_power(actor, self.bundle, "dnd2024.class.fighter.second_wind", seed=1)
        blocked = api.use_power(actor, self.bundle, "dnd2024.class.fighter.second_wind", seed=1)
        self.assertFalse(blocked["ok"])
        self.assertIn("不足", blocked["message"])

    def test_action_surge_grants_action(self):
        actor = self.make(2)
        economy = api.ActionEconomy()
        economy.pay(api.ActionType.ACTION)
        result = api.use_power(actor, self.bundle, "dnd2024.class.fighter.action_surge",
                               economy=economy, seed=1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["economy"]["action"], 1)  # 用掉 1 个又拿回 1 个

    def test_passive_power_cannot_be_used(self):
        actor = self.make(5)
        result = api.use_power(actor, self.bundle, "dnd2024.class.fighter.extra_attack", seed=1)
        self.assertFalse(result["ok"])
        self.assertIn("不是主动能力", result["message"])

    def test_sheet_is_locale_aware(self):
        actor = self.make(1)
        self.assertEqual(api.character_sheet(actor, self.bundle, "en")["name"], "Test Fighter")
        names = [row["name"] for row in api.character_sheet(actor, self.bundle, "en")["powers"]]
        self.assertIn("Second Wind", names)

    def test_unknown_power(self):
        from dnd5r.kernel.errors import PluginError

        with self.assertRaises(PluginError):
            api.find_power(self.bundle, "dnd2024.class.fighter.nope")


if __name__ == "__main__":
    unittest.main()
