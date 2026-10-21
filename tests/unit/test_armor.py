# -*- coding: utf-8 -*-
"""P5b 验收之二：护甲与盾。

AC 之前只有一条公式（10 + 敏捷），所以「变形期间护甲不生效」只是**结构上**
没被违反，而不变量本身没人验过。这一组测试把它变成可验的：

  1. 轻甲：11/12 + 全部敏捷
  2. 中甲：基础值 + 敏捷上限 2
  3. 重甲：不吃敏捷，**负敏捷照扣**
  4. 盾牌：+2，且不改变护甲吃敏捷的规则
  5. 无甲防御的 `unarmored` 条件现在读真装备（穿甲就失效）
  6. 野蛮人无甲防御可以持盾，武僧的不可以 —— 差别写在内容里
  7. 变形期间护甲与盾一律不生效，AC 只来自形态
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.model.inventory import EquipSlot
from dnd5r.rules.armor import dex_contribution, loadout_for

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
ID = "dnd2024.item.armor."


class ArmorDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_table_loaded(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertEqual(len(self.bundle.armors), 13)
        categories = {armor.category for armor in self.bundle.armors.values()}
        self.assertEqual(categories, {"light", "medium", "heavy", "shield"})

    def test_shapes_of_the_table(self):
        for armor_id, armor in self.bundle.armors.items():
            with self.subTest(armor_id=armor_id):
                if armor.category == "shield":
                    self.assertGreaterEqual(armor.bonus, 1)
                    self.assertEqual(armor.slot, EquipSlot.SHIELD)
                else:
                    self.assertGreaterEqual(armor.ac_base, 11)
                    self.assertEqual(armor.slot, EquipSlot.ARMOR)
                if armor.category == "heavy":
                    self.assertEqual(armor.dex_cap, 0)    # 重甲一点都不吃敏捷

    def test_unknown_slot_item_is_ignored(self):
        actor = api.new_character(self.bundle, "dnd2024.class.fighter", 1, SCORES,
                                  name_zh="甲检", name_en="Armor")
        actor.inventory.equip(EquipSlot.ARMOR, "homebrew.item.armor.mithril_vest")
        self.assertTrue(loadout_for(actor, self.bundle.armors).empty)


class ArmorClassTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _fighter(self, level=1, armor=None, shield=None, scores=None):
        actor = api.new_character(self.bundle, "dnd2024.class.fighter", level,
                                  scores or SCORES, name_zh="甲检", name_en="Armor Check")
        if armor:
            actor.inventory.equip(EquipSlot.ARMOR, ID + armor)
        if shield:
            actor.inventory.equip(EquipSlot.SHIELD, ID + shield)
        return actor, api.character_sheet(actor, self.bundle)

    def test_unarmored_baseline(self):
        _, sheet = self._fighter()
        self.assertEqual(sheet["ac"]["total"], 12)      # 10 + 2
        self.assertIsNone(sheet["gear"]["armor"])

    def test_light_armor_takes_full_dex(self):
        _, sheet = self._fighter(armor="leather")
        self.assertEqual(sheet["ac"]["total"], 13)      # 11 + 2
        _, sheet = self._fighter(armor="studded_leather")
        self.assertEqual(sheet["ac"]["total"], 14)      # 12 + 2
        self.assertIn("镶钉皮甲", sheet["ac"]["detail"])
        self.assertIn("敏捷", sheet["ac"]["detail"])

    def test_medium_armor_caps_dex(self):
        scores = dict(SCORES, dex=18)                   # +4，但中甲只吃 2
        _, sheet = self._fighter(armor="chain_shirt", scores=scores)
        self.assertEqual(sheet["ac"]["total"], 15)      # 13 + 2
        self.assertEqual(dex_contribution(self.bundle.armor(ID + "chain_shirt"), 4), 2)

    def test_heavy_armor_ignores_dex_but_keeps_penalty(self):
        _, sheet = self._fighter(armor="chain_mail")
        self.assertEqual(sheet["ac"]["total"], 16)      # 锁甲 16，不加 +2
        low = dict(SCORES, dex=8)                       # -1
        _, sheet = self._fighter(armor="chain_mail", scores=low)
        self.assertEqual(sheet["ac"]["total"], 15)      # 负敏捷照扣
        self.assertEqual(dex_contribution(self.bundle.armor(ID + "chain_mail"), -1), -1)

    def test_shield_adds_two_and_stacks_with_armor(self):
        _, sheet = self._fighter(armor="chain_mail", shield="shield")
        self.assertEqual(sheet["ac"]["total"], 18)
        self.assertIn("盾牌", sheet["ac"]["detail"])
        _, sheet = self._fighter(shield="shield")
        self.assertEqual(sheet["ac"]["total"], 14)      # 10 + 2 + 2

    def test_unarmored_defense_uses_real_equipment(self):
        """穿甲以后野蛮人的无甲防御必须失效，否则会白送体质调整值。"""
        actor = api.new_character(self.bundle, "dnd2024.class.barbarian", 1, SCORES,
                                  name_zh="野蛮人", name_en="Barbarian")
        unarmored = api.character_sheet(actor, self.bundle)["ac"]["total"]
        self.assertEqual(unarmored, 14)                 # 10 + 2(敏) + 2(体)
        actor.inventory.equip(EquipSlot.ARMOR, ID + "chain_mail")
        geared = api.character_sheet(actor, self.bundle)
        self.assertEqual(geared["ac"]["total"], 16)     # 锁甲 16 顶掉整套公式
        self.assertNotIn("unarmored_defense", geared["ac"]["detail"])

    def test_barbarian_may_hold_shield_monk_may_not(self):
        """同一条 `unarmored` 事实，两个职业的写法不同 —— 差别在内容里，不在代码里。"""
        barbarian = api.new_character(self.bundle, "dnd2024.class.barbarian", 1, SCORES,
                                      name_zh="野蛮人", name_en="Barbarian")
        barbarian.inventory.equip(EquipSlot.SHIELD, ID + "shield")
        self.assertEqual(api.character_sheet(barbarian, self.bundle)["ac"]["total"], 16)

        monk = api.new_character(self.bundle, "dnd2024.class.monk", 1, SCORES,
                                 name_zh="武僧", name_en="Monk")
        bare = api.character_sheet(monk, self.bundle)["ac"]["total"]
        self.assertEqual(bare, 13)                      # 10 + 2 + 1（感知）
        monk.inventory.equip(EquipSlot.SHIELD, ID + "shield")
        with_shield = api.character_sheet(monk, self.bundle)["ac"]["total"]
        self.assertEqual(with_shield, 14)               # 10 + 2 + 盾 2，无甲防御失效

    def test_facts_report_equipment(self):
        actor = api.new_character(self.bundle, "dnd2024.class.monk", 1, SCORES,
                                  name_zh="武僧", name_en="Monk")
        resolver = api.resolver_for(actor, self.bundle)
        self.assertTrue(resolver.ctx.facts["unarmored"])
        self.assertFalse(resolver.ctx.facts["shield"])
        actor.inventory.equip(EquipSlot.ARMOR, ID + "leather")
        resolver = api.resolver_for(actor, self.bundle)
        self.assertFalse(resolver.ctx.facts["unarmored"])

    def test_morph_drops_armor_and_shield(self):
        """变形期间护甲与盾都不生效：AC 只来自形态（野猪 11）。"""
        actor = api.new_character(self.bundle, "dnd2024.class.druid", 4, SCORES,
                                  name_zh="德鲁伊", name_en="Druid")
        actor.inventory.equip(EquipSlot.ARMOR, ID + "leather")
        actor.inventory.equip(EquipSlot.SHIELD, ID + "shield")
        before = api.character_sheet(actor, self.bundle)
        self.assertEqual(before["ac"]["total"], 15)     # 11 + 2 + 2
        self.assertEqual(before["gear"]["armor"]["id"], ID + "leather")

        result = api.use_power(actor, self.bundle, "dnd2024.class.druid.wild_shape",
                               choice={"form_id": "dnd2024.form.beast.boar"})
        self.assertTrue(result["ok"], result["message"])
        after = result["sheet"]
        self.assertEqual(after["ac"]["total"], 11)
        self.assertIsNone(after["gear"]["armor"])
        self.assertIsNone(after["gear"]["shield"])
        self.assertTrue(loadout_for(actor, self.bundle.armors).empty)

    def test_form_ac_wins_over_plate(self):
        """形态 AC 只来自形态：哪怕身上是全身板甲（18），变野猪也还是 11。"""
        actor = api.new_character(self.bundle, "dnd2024.class.druid", 4, SCORES,
                                  name_zh="德鲁伊", name_en="Druid")
        actor.inventory.equip(EquipSlot.ARMOR, ID + "plate")
        actor.inventory.equip(EquipSlot.SHIELD, ID + "shield")
        self.assertEqual(api.character_sheet(actor, self.bundle)["ac"]["total"], 20)
        result = api.use_power(actor, self.bundle, "dnd2024.class.druid.wild_shape",
                               choice={"form_id": "dnd2024.form.beast.boar"})
        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(result["sheet"]["ac"]["total"], 11)


if __name__ == "__main__":
    unittest.main()
