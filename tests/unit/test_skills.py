# -*- coding: utf-8 -*-
"""P6b 验收：18 项技能作为内容 + 技能检定的三条来源。

在此之前内核只有 `skill.<key>` 这种令牌，没有任何地方把它们算成数值 ——
界面就算想显示「隐匿 +7」也无从下手。这一组盯四件事：

  1. 技能是**内容**（`skills.yaml`），id 的末段必须与内核的 18 项 key 一致
  2. 技能检定 = 属性调整值 + 熟练（+ 专精），与豁免同一套 `ability_check`
  3. 加值两档：所有技能（`skill_check`）与指定技能（`skill.stealth`）都能加
  4. sheet 的 18 行随熟练变化，行数不缺不多
"""

import dataclasses
import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import SKILL_KEYS, PluginError, parse_skill
from dnd5r.kernel.text import Text

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
ROGUE = "dnd2024.class.rogue"
SCORES = {"str": 10, "dex": 17, "con": 14, "int": 12, "wis": 12, "cha": 10}


def _row(sheet, key):
    return [row for row in sheet["skills"] if row["key"] == key][0]


class SkillContentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_eighteen_skills_loaded(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertEqual(len(self.bundle.skills), 18)
        self.assertEqual(sorted(skill.key for skill in self.bundle.skills.values()),
                         sorted(SKILL_KEYS))

    def test_bilingual_names(self):
        for skill in self.bundle.skills.values():
            self.assertTrue(skill.name.zh)
            self.assertTrue(skill.name.en)

    def test_key_must_be_one_of_eighteen(self):
        with self.assertRaises(PluginError):
            parse_skill({"id": "dnd2024.skill.basketweaving",
                         "name": {"zh": "编织", "en": "Basketweaving"},
                         "ability": "dex"}, source="test")

    def test_ability_must_be_valid(self):
        with self.assertRaises(PluginError):
            parse_skill({"id": "dnd2024.skill.stealth",
                         "name": {"zh": "隐匿", "en": "Stealth"},
                         "ability": "luck"}, source="test")


class SkillSheetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _rogue(self):
        return api.new_character(self.bundle, ROGUE, 5, SCORES)

    def test_sheet_has_eighteen_rows(self):
        sheet = api.character_sheet(self._rogue(), self.bundle)
        self.assertEqual(len(sheet["skills"]), 18)
        for row in sheet["skills"]:
            self.assertIn(row["key"], SKILL_KEYS)
            self.assertIn(row["ability"],
                          ("str", "dex", "con", "int", "wis", "cha"))

    def test_proficiency_adds_bonus(self):
        actor = self._rogue()          # 5 级：熟练 +3，敏捷 17 → +3
        before = _row(api.character_sheet(actor, self.bundle), "stealth")["total"]
        actor.profile = actor.profile.with_proficiencies(["skill.stealth"])
        after = _row(api.character_sheet(actor, self.bundle), "stealth")
        self.assertEqual(after["total"], before + 3)
        self.assertTrue(after["proficient"])
        self.assertIn("熟练", after["detail"])

    def test_expertise_doubles_proficiency(self):
        actor = self._rogue()
        actor.profile = actor.profile.with_proficiencies(["skill.stealth"])
        plain = _row(api.character_sheet(actor, self.bundle), "stealth")["total"]
        # 专精是 Profile.expertise，不是熟练的另一种写法
        actor.profile = dataclasses.replace(
            actor.profile, expertise=frozenset(["skill.stealth"]))
        expert = _row(api.character_sheet(actor, self.bundle), "stealth")
        self.assertEqual(expert["total"], plain + 3)
        self.assertTrue(expert["expertise"])

    def test_unproficient_skill_is_just_the_ability(self):
        sheet = api.character_sheet(self._rogue(), self.bundle)
        row = _row(sheet, "athletics")      # 力量 10 → +0
        self.assertEqual(row["total"], 0)
        self.assertFalse(row["proficient"])

    def test_skill_detail_shows_ability(self):
        """明细要说清「+3 是敏捷」，否则玩家没法核对熟练到底算没算。"""
        sheet = api.character_sheet(self._rogue(), self.bundle)
        row = _row(sheet, "stealth")
        self.assertIn("DEX", row["detail"])
        self.assertEqual(row["total"], 3)      # 敏捷 17 → +3，未熟练


if __name__ == "__main__":
    unittest.main()
