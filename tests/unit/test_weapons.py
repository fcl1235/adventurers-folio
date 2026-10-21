# -*- coding: utf-8 -*-
"""P5c 验收：武器通道。

攻击卡之前是「用最高的力量/敏捷 + 熟练」的占位，所以三件事没人验：
  1. **用哪个属性**：远程看敏捷，灵巧取高者
  2. **是否熟练**：wizard 拿巨剑要少熟练加值；武僧只熟「军用轻型」
  3. **伤害**：两用武器双手档、副手不加属性调整值、重型武器属性不足有劣势

数据表与推论分开：表在 `items/weapons.yaml`（38 件，生成自旧程序快照），
推论在 `rules/weapons.py`。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel import dice
from dnd5r.model.inventory import EquipSlot
from dnd5r.model.statblock import Abilities
from dnd5r.rules import weapons as w

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
W = "dnd2024.item.weapon."


def _class(name):
    return "dnd2024.class.%s" % name


class WeaponDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_table_loaded(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertEqual(len(self.bundle.weapons), 38)
        categories = {item.category for item in self.bundle.weapons.values()}
        self.assertEqual(categories, {"simple", "martial"})

    def test_versatile_pair_is_consistent(self):
        """有 versatile 属性就必须有第二档伤害，反之亦然。"""
        for weapon in self.bundle.weapons.values():
            with self.subTest(weapon=weapon.id):
                self.assertEqual(weapon.has("versatile"), bool(weapon.versatile))
        longsword = self.bundle.weapon(W + "longsword")
        self.assertEqual(str(longsword.dice()), "1d8")
        self.assertEqual(str(longsword.dice(two_handed=True)), "1d10")

    def test_property_vocabulary_is_closed(self):
        """属性表是封闭集合：写错一个词（比如 two-handed）加载期就该炸。"""
        payload = {
            "id": "probe.item.bad_axe", "kind": "weapon",
            "name": {"zh": "坏斧", "en": "Bad Axe"},
            "category": "martial", "damage": "1d8", "damage_type": "slashing",
            "properties": ["two-handed"],
        }
        from dnd5r.content import parse_weapon
        from dnd5r.kernel.errors import PluginError

        with self.assertRaises(PluginError):
            parse_weapon(payload, where="probe.yaml")


class WeaponRuleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def weapon(self, name):
        return self.bundle.weapon(W + name)

    def test_ability_by_property(self):
        abilities = Abilities.of(**SCORES)                    # 力 +3 / 敏 +2
        self.assertEqual(w.attack_ability(self.weapon("longsword"), abilities), "str")
        self.assertEqual(w.attack_ability(self.weapon("longbow"), abilities), "dex")
        self.assertEqual(w.attack_ability(self.weapon("rapier"), abilities), "str")
        nimble = Abilities.of(**dict(SCORES, str=10, dex=18))  # 力 0 / 敏 +4
        self.assertEqual(w.attack_ability(self.weapon("rapier"), nimble), "dex")

    def test_proficiency_follows_tokens(self):
        """wizard 只熟简单武器；rogue 熟「军用灵巧或轻型」；monk 只熟「军用轻型」。"""
        greatsword = self.weapon("greatsword")
        rapier = self.weapon("rapier")
        shortsword = self.weapon("shortsword")
        self.assertTrue(w.proficient(greatsword, ["weapon.martial"]))
        self.assertFalse(w.proficient(greatsword, ["weapon.simple"]))
        self.assertFalse(w.proficient(rapier, ["weapon.simple"]))
        self.assertTrue(w.proficient(rapier, ["weapon.simple", "weapon.martial_finesse_or_light"]))
        self.assertFalse(w.proficient(greatsword, ["weapon.martial_finesse_or_light"]))
        self.assertTrue(w.proficient(shortsword, ["weapon.martial_light"]))
        self.assertFalse(w.proficient(rapier, ["weapon.martial_light"]))
        self.assertTrue(w.proficient(None, []))                          # 徒手永远熟练

    def test_heavy_needs_thirteen(self):
        maul = self.weapon("maul")
        weak = Abilities.of(**dict(SCORES, str=12))
        self.assertTrue(w.heavy_penalty(maul, weak))
        self.assertFalse(w.heavy_penalty(maul, Abilities.of(**dict(SCORES, str=13))))
        self.assertFalse(w.heavy_penalty(self.weapon("longsword"), weak))

    def test_unarmed_is_one_plus_strength(self):
        abilities = Abilities.of(**SCORES)
        prof = w.profile(None, abilities, prof_bonus=2)
        self.assertEqual(prof.attack, 5)                 # 力 +3 + 熟练 2
        self.assertEqual(str(prof.damage), "1")
        self.assertEqual(prof.damage_bonus, 3)
        self.assertEqual(prof.damage_type, "bludgeoning")


class AttackSheetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def sheet(self, class_name, level=1, main=None, off=None, scores=None):
        actor = api.new_character(self.bundle, _class(class_name), level,
                                  scores or SCORES, name_zh="武器检", name_en="Weapon Check")
        if main:
            actor.inventory.equip(EquipSlot.MAIN_HAND, W + main)
        if off:
            actor.inventory.equip(EquipSlot.OFF_HAND, W + off)
        return actor, api.character_sheet(actor, self.bundle)

    def test_no_weapon_is_unarmed(self):
        _, sheet = self.sheet("fighter")
        self.assertEqual(len(sheet["attacks"]), 1)
        attack = sheet["attacks"][0]
        self.assertEqual(attack["weapon"], "unarmed")
        self.assertEqual(attack["damage"], "1")

    def test_longsword_two_handed_when_off_hand_free(self):
        _, sheet = self.sheet("fighter", 5, main="longsword")
        attack = sheet["attacks"][0]
        self.assertEqual(attack["attack"], 6)            # 力 3 + 熟练 3
        self.assertEqual(attack["damage"], "1d10")       # 双手档
        self.assertEqual(attack["damage_bonus"], 3)
        self.assertEqual(attack["damage_type"], "挥砍")
        self.assertEqual(attack["mastery"], "sap")

    def test_off_hand_adds_no_ability_modifier(self):
        _, sheet = self.sheet("fighter", 1, main="longsword", off="dagger")
        main, off = sheet["attacks"]
        self.assertEqual(main["damage"], "1d8")          # 副手占着 → 退回单手档
        self.assertTrue(off["off_hand"])
        self.assertEqual(off["damage_bonus"], 0)         # 副手不加属性调整值
        self.assertEqual(off["attack"], 5)

    def test_unproficient_weapon_loses_proficiency_bonus(self):
        """法师拿巨剑：攻击只有力量调整值，伤害照算（未熟练不影响伤害）。"""
        _, sheet = self.sheet("wizard", 1, main="greatsword")
        attack = sheet["attacks"][0]
        self.assertFalse(attack["proficient"])
        self.assertEqual(attack["attack"], 3)
        self.assertEqual(attack["damage"], "2d6")

    def test_ranged_uses_dex(self):
        _, sheet = self.sheet("ranger", 1, main="longbow")
        self.assertEqual(sheet["attacks"][0]["ability"], "dex")

    def test_druid_loses_weapons_after_shaping(self):
        actor, sheet = self.sheet("druid", 4, main="scimitar")
        self.assertEqual(sheet["attacks"][0]["weapon"], W + "scimitar")
        result = api.use_power(actor, self.bundle, "dnd2024.class.druid.wild_shape",
                               choice={"form_id": "dnd2024.form.beast.boar"})
        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(result["sheet"]["attacks"][0]["weapon"], "unarmed")

    def test_dice_string_round_trip(self):
        """`Dice.__str__` 是给界面的，纯定值不能写成 "+1"。"""
        self.assertEqual(str(dice.parse("1")), "1")
        self.assertEqual(str(dice.parse("2d6+3")), "2d6+3")
        self.assertEqual(str(dice.parse("1d8-1")), "1d8-1")


if __name__ == "__main__":
    unittest.main()
