# -*- coding: utf-8 -*-
"""P5d 验收：速度加值 + 按等级查表。

速度以前完全没人管（金对账只比 hp/pb/ac/attack/save），所以
「野蛮人 5 级 +10」「武僧无甲移动 10→30」这类能力全是 note 文本。
这一组把它变成可验的，并给 golden 加了第 11 个维度（speed）。

关键点：
  1. 只禁**重型**护甲（野蛮人快速移动、游侠游荡），轻甲/中甲照给
  2. 武僧还要**不持盾**，且五档不是等差 → `Amount.table`
  3. 变形期间形态速度取代本体，一切加值都不算
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.model.inventory import EquipSlot
from dnd5r.rules.amount import lookup, parse_amount

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
ARMOR = "dnd2024.item.armor."


class TableAmountTest(unittest.TestCase):
    def test_lookup_takes_nearest_lower(self):
        table = {2: 10, 6: 15, 10: 20, 14: 25, 18: 30}
        self.assertEqual(lookup(table, 1), 0)
        self.assertEqual(lookup(table, 2), 10)
        self.assertEqual(lookup(table, 5), 10)
        self.assertEqual(lookup(table, 6), 15)
        self.assertEqual(lookup(table, 20), 30)

    def test_amount_table_uses_class_level(self):
        amount = parse_amount({"table": {2: 10, 6: 15}})
        self.assertEqual(amount.evaluate({"class_level": 1}), 0)
        self.assertEqual(amount.evaluate({"class_level": 3}), 10)
        self.assertEqual(amount.evaluate({"class_level": 9}), 15)

    def test_amount_table_round_trips(self):
        amount = parse_amount({"table": {2: 10, 6: 15}})
        data = amount.to_dict()
        self.assertEqual(data["table"], {2: 10, 6: 15})
        self.assertEqual(data["key"], "class_level")
        self.assertEqual(parse_amount(data).evaluate({"class_level": 7}), 15)

    def test_rejects_bad_table(self):
        from dnd5r.kernel.errors import RuleError

        with self.assertRaises(RuleError):
            parse_amount({"table": {}})
        with self.assertRaises(RuleError):
            parse_amount({"table": {0: 10}})
        with self.assertRaises(RuleError):
            parse_amount({"key": "class_level"})       # key 只在有 table 时有意义


class SpeedSheetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def sheet(self, class_name, level, armor=None, shield=False):
        actor = api.new_character(self.bundle, "dnd2024.class.%s" % class_name, level,
                                  SCORES, name_zh="速度检", name_en="Speed Check")
        if armor:
            actor.inventory.equip(EquipSlot.ARMOR, ARMOR + armor)
        if shield:
            actor.inventory.equip(EquipSlot.SHIELD, ARMOR + "shield")
        return actor, api.character_sheet(actor, self.bundle)

    def speed(self, class_name, level, **kwargs):
        return self.sheet(class_name, level, **kwargs)[1]["speed"]["walk"]

    def test_barbarian_fast_movement(self):
        self.assertEqual(self.speed("barbarian", 4), 30)
        self.assertEqual(self.speed("barbarian", 5), 40)
        self.assertEqual(self.speed("barbarian", 20), 40)

    def test_only_heavy_armor_cancels_fast_movement(self):
        """「不穿重甲」不是「不穿甲」：轻甲和中甲都要保留 +10。"""
        self.assertEqual(self.speed("barbarian", 5, armor="leather"), 40)
        self.assertEqual(self.speed("barbarian", 5, armor="half_plate"), 40)
        self.assertEqual(self.speed("barbarian", 5, armor="chain_mail"), 30)

    def test_monk_unarmored_movement_table(self):
        expected = {1: 30, 2: 40, 5: 40, 6: 45, 10: 50, 14: 55, 18: 60, 20: 60}
        for level, want in expected.items():
            with self.subTest(level=level):
                self.assertEqual(self.speed("monk", level), want)

    def test_monk_loses_it_with_armor_or_shield(self):
        self.assertEqual(self.speed("monk", 10, armor="leather"), 30)
        self.assertEqual(self.speed("monk", 10, shield=True), 30)

    def test_ranger_roving(self):
        self.assertEqual(self.speed("ranger", 5), 30)
        self.assertEqual(self.speed("ranger", 6), 40)
        self.assertEqual(self.speed("ranger", 6, armor="chain_mail"), 30)

    def test_classes_without_speed_features_stay_at_thirty(self):
        for class_name in ("fighter", "wizard", "rogue", "cleric"):
            with self.subTest(class_name=class_name):
                self.assertEqual(self.speed(class_name, 20), 30)

    def test_facts_expose_armor_category(self):
        """`armor` 事实是护甲类别本身，不是布尔 —— 只禁重甲的能力全靠它。"""
        actor, _ = self.sheet("barbarian", 5, armor="chain_mail")
        self.assertEqual(api.resolver_for(actor, self.bundle).ctx.facts["armor"], "heavy")
        bare, _ = self.sheet("barbarian", 5)
        self.assertIsNone(api.resolver_for(bare, self.bundle).ctx.facts["armor"])

    def test_morph_replaces_speed(self):
        """变形期间用形态速度（野猪 40）：本体的快速移动不能叠上去。"""
        actor = api.new_character(self.bundle, "dnd2024.class.druid", 4, SCORES,
                                  name_zh="德鲁伊", name_en="Druid")
        self.assertEqual(api.character_sheet(actor, self.bundle)["speed"]["walk"], 30)
        result = api.use_power(actor, self.bundle, "dnd2024.class.druid.wild_shape",
                               choice={"form_id": "dnd2024.form.beast.boar"})
        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(result["sheet"]["speed"]["walk"], 40)

    def test_session_actor_matches_sheet(self):
        """P11 起只有一份投影（session.view 已删）：同一只角色读 sheet 即可。

        这条测试保留的原因：CLI `play` 走 Session 建角、桌面端走 api 建角，
        两条入口建出来的必须是同一套数值。
        """
        session = api.Session.open(str(PLUGINS))
        actor = session.create_character("dnd2024.class.barbarian", 5, SCORES,
                                        name_zh="野蛮人", name_en="Barbarian")
        sheet = api.character_sheet(actor, session.bundle)
        self.assertEqual(sheet["speed"]["walk"], 40)
        # 无甲防御：10 + 敏捷 +2 + 体质 +2（快速移动是速度通道，不进 AC）
        self.assertEqual(sheet["ac"]["total"], 14)
        self.assertIn("无甲防御", sheet["ac"]["detail"])


if __name__ == "__main__":
    unittest.main()
