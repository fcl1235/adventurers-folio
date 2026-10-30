# -*- coding: utf-8 -*-
"""P5 验收：换装、属性就地编辑、变形选择。

这一组的共同点是「改完要立刻在卡上看见」：

  1. 换装**不需要 rebuild** —— AC / 攻击表每次取卡时从装备槽现读
  2. 改属性**必须 rebuild** —— 但它改的是原始属性，加值要重新叠一遍
  3. 装不上的组合要当场拒绝，而不是装上去算出一个错的数
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.model.inventory import EquipSlot

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"
DRUID = "dnd2024.class.druid"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
WIS_SCORES = {"str": 10, "dex": 14, "con": 14, "int": 12, "wis": 17, "cha": 10}

CHAIN_MAIL = "dnd2024.item.armor.chain_mail"
LEATHER = "dnd2024.item.armor.leather"
SHIELD = "dnd2024.item.armor.shield"
LONGSWORD = "dnd2024.item.weapon.longsword"
GREATSWORD = "dnd2024.item.weapon.greatsword"


class EquipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def setUp(self):
        self.actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)

    def sheet(self):
        return api.character_sheet(self.actor, self.bundle)

    def test_equipping_changes_ac_immediately(self):
        """AC 是每次取卡现读的：改完不用重建、不用重新读档。"""
        self.assertEqual(self.sheet()["ac"]["total"], 12)
        api.equip_item(self.actor, self.bundle, "armor", LEATHER)
        self.assertEqual(self.sheet()["ac"]["total"], 13)     # 11 + 2 敏捷
        api.equip_item(self.actor, self.bundle, "armor", CHAIN_MAIL)
        self.assertEqual(self.sheet()["ac"]["total"], 16)     # 重甲不吃敏捷
        api.equip_item(self.actor, self.bundle, "shield", SHIELD)
        self.assertEqual(self.sheet()["ac"]["total"], 18)
        self.assertIn("盾牌", self.sheet()["ac"]["detail"])

    def test_slots_are_written_into_sheet(self):
        api.equip_item(self.actor, self.bundle, "armor", CHAIN_MAIL)
        self.assertEqual(self.sheet()["equipped"]["armor"], CHAIN_MAIL)
        api.equip_item(self.actor, self.bundle, "armor", None)
        self.assertNotIn("armor", self.sheet()["equipped"])

    def test_equipped_item_enters_inventory(self):
        """装上却没在背包里 = 影子装备，存盘之后就没了。"""
        api.equip_item(self.actor, self.bundle, "main_hand", LONGSWORD)
        self.assertTrue(self.actor.inventory.has_item(LONGSWORD))
        payload = api.save_character(self.actor)
        fresh = api.load_character(self.bundle, payload)
        self.assertEqual(api.equipped_map(fresh)["main_hand"], LONGSWORD,
                         "换装要能存下来")

    def test_wrong_slot_refused(self):
        for slot, item in (("armor", SHIELD), ("shield", CHAIN_MAIL),
                           ("main_hand", SHIELD), ("armor", LONGSWORD)):
            with self.assertRaises(api.RuleError, msg="%s 装 %s 该被拒" % (slot, item)):
                api.equip_item(self.actor, self.bundle, slot, item)

    def test_unknown_slot_and_item_refused(self):
        with self.assertRaises(api.RuleError):
            api.equip_item(self.actor, self.bundle, "head", CHAIN_MAIL)
        with self.assertRaises(api.RuleError):
            api.equip_item(self.actor, self.bundle, "armor", "dnd2024.item.armor.nope")

    def test_two_handed_conflicts_both_directions(self):
        api.equip_item(self.actor, self.bundle, "shield", SHIELD)
        with self.assertRaises(api.RuleError):
            api.equip_item(self.actor, self.bundle, "main_hand", GREATSWORD)
        api.equip_item(self.actor, self.bundle, "shield", None)
        api.equip_item(self.actor, self.bundle, "main_hand", GREATSWORD)
        with self.assertRaises(api.RuleError):
            api.equip_item(self.actor, self.bundle, "shield", SHIELD)

    def test_versatile_drops_to_one_hand_when_shielded(self):
        """持盾时两用武器按单手档算：盾在 SHIELD 槽，光看副手是不是空会算错。"""
        api.equip_item(self.actor, self.bundle, "main_hand", LONGSWORD)
        self.assertEqual(self.sheet()["attacks"][0]["damage"], "1d10")
        api.equip_item(self.actor, self.bundle, "shield", SHIELD)
        self.assertEqual(self.sheet()["attacks"][0]["damage"], "1d8",
                         "一手剑一手盾不该按双手握持算")
        api.equip_item(self.actor, self.bundle, "shield", None)
        self.assertEqual(self.sheet()["attacks"][0]["damage"], "1d10")

    def test_same_item_cannot_hold_both_hands(self):
        api.equip_item(self.actor, self.bundle, "main_hand", LONGSWORD)
        api.equip_item(self.actor, self.bundle, "off_hand", LONGSWORD)
        gear = api.equipped_map(self.actor)
        self.assertEqual(gear.get("off_hand"), LONGSWORD)
        self.assertNotIn("main_hand", gear, "同一把剑不能同时占两只手")

    def test_catalogs(self):
        armors = api.armor_catalog(self.bundle)["armors"]
        weapons = api.weapon_catalog(self.bundle)["weapons"]
        self.assertEqual(len(armors), 13)
        self.assertEqual(len(weapons), 38)
        self.assertTrue(all("slot" in row for row in armors))
        self.assertIn("盾牌", {row["name"] for row in armors})
        self.assertTrue(all(row["damage"] for row in weapons))

    def test_parse_slot(self):
        self.assertIs(api.parse_slot("armor"), EquipSlot.ARMOR)
        self.assertIs(api.parse_slot(EquipSlot.SHIELD), EquipSlot.SHIELD)
        with self.assertRaises(api.RuleError):
            api.parse_slot("tail")


class BaseScoreTest(unittest.TestCase):
    """改属性改的是**原始值**：卡面分数已经含了专长加值，倒推减不干净。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_con_raises_hp_cap(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        before = api.character_sheet(actor, self.bundle)["hp"]["maximum"]
        fresh = api.set_base_scores(actor, self.bundle, dict(SCORES, con=16))
        after = api.character_sheet(fresh, self.bundle)["hp"]["maximum"]
        self.assertEqual(after, before + 5, "体质 +2 = 调整值 +1 × 5 级")

    def test_current_hp_kept_and_clamped(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        actor.hp.current = 21
        fresh = api.set_base_scores(actor, self.bundle, dict(SCORES, con=16))
        self.assertEqual(fresh.hp.current, 21, "改属性不该顺手回满血")
        lowered = api.set_base_scores(actor, self.bundle, dict(SCORES, con=8))
        self.assertLessEqual(lowered.hp.current, lowered.hp.maximum)

    def test_equipment_survives(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        api.equip_item(actor, self.bundle, "armor", CHAIN_MAIL)
        api.equip_item(actor, self.bundle, "shield", SHIELD)
        fresh = api.set_base_scores(actor, self.bundle, dict(SCORES, str=18))
        self.assertEqual(api.character_sheet(fresh, self.bundle)["ac"]["total"], 18,
                         "改力量不该把甲脱了")

    def test_attack_follows_new_strength(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        api.equip_item(actor, self.bundle, "main_hand", LONGSWORD)
        before = api.character_sheet(actor, self.bundle)["attack"]["total"]
        fresh = api.set_base_scores(actor, self.bundle, dict(SCORES, str=18))
        after = api.character_sheet(fresh, self.bundle)["attack"]["total"]
        self.assertEqual(after, before + 1)

    def test_bad_input(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        with self.assertRaises(api.RuleError):
            api.set_base_scores(actor, self.bundle, {"str": 16})        # 缺项
        with self.assertRaises(api.RuleError):
            api.set_base_scores(actor, self.bundle, dict(SCORES, str=99))  # 越界
        with self.assertRaises(api.RuleError):
            api.set_base_scores(actor, self.bundle, dict(SCORES, str="16"))

    def test_base_scores_are_in_sheet(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        self.assertEqual(api.character_sheet(actor, self.bundle)["base_scores"], SCORES)


class MorphTest(unittest.TestCase):
    """变形选择：channels 里没有 `form` 时，界面上的「使用」按钮必然失败。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_wild_shape_declares_form_channel(self):
        actor = api.new_character(self.bundle, DRUID, 8, WIS_SCORES)
        sheet = api.character_sheet(actor, self.bundle)
        wild = next(row for row in sheet["powers"] if row["id"].endswith("wild_shape"))
        self.assertIn("form", wild["channels"],
                      "变形能力必须声明 form 通道，否则界面没有形态可选")

    def test_forms_available_and_morph_round_trip(self):
        actor = api.new_character(self.bundle, DRUID, 8, WIS_SCORES)
        usable = api.morph_forms(actor, self.bundle)["usable"]
        self.assertGreaterEqual(len(usable), 10)
        self.assertIsNone(api.current_form(actor))

        power_id = next(row["id"] for row in api.character_sheet(actor, self.bundle)["powers"]
                        if row["id"].endswith("wild_shape"))
        report = api.use_power(actor, self.bundle, power_id,
                               choice={"form_id": usable[0]["id"]})
        self.assertTrue(report["ok"], report.get("message"))
        self.assertEqual(api.current_form(actor), usable[0]["id"])
        self.assertTrue(api.character_sheet(actor, self.bundle)["morphed"])

        body = api.leave_form_now(actor)
        self.assertIsNone(api.current_form(body))
        self.assertFalse(api.character_sheet(body, self.bundle)["morphed"])

    def test_leaving_without_morph_raises(self):
        actor = api.new_character(self.bundle, DRUID, 8, WIS_SCORES)
        with self.assertRaises(api.RuleError):
            api.leave_form_now(actor)

    def test_unusable_form_refused(self):
        actor = api.new_character(self.bundle, DRUID, 8, WIS_SCORES)
        power_id = next(row["id"] for row in api.character_sheet(actor, self.bundle)["powers"]
                        if row["id"].endswith("wild_shape"))
        report = api.use_power(actor, self.bundle, power_id,
                               choice={"form_id": "dnd2024.form.beast.dragon"})
        self.assertFalse(report["ok"])
        self.assertIn("不可选", report["message"])


if __name__ == "__main__":
    unittest.main()
