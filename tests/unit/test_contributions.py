# -*- coding: utf-8 -*-
"""P5a 验收：常驻贡献管道（被动特性 → Resolver）。

P2 只实现了「用一次能力时给加值」，没实现「被动写的加值一直都在」。
结果是 12 职业对账里 AC 与豁免全对不上（无甲防御、守护灵光、偷渡者豁免）。
这个文件锁住那条管道：被动特性不需要「被使用」，也必须算进派生值。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.rules.contributions import (
    facts_for,
    modifiers_for,
    passive_modifiers,
    passive_proficiencies,
    save_modifiers,
)

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


def _class(name: str) -> str:
    return "dnd2024.class.%s" % name


class ContributionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def sheet(self, class_name, level, scores=None):
        actor = api.new_character(self.bundle, _class(class_name), level, scores or SCORES,
                                  name_zh="贡献", name_en="Contribution")
        return actor, api.character_sheet(actor, self.bundle)

    # --- 无甲防御 -----------------------------------------------------
    def test_barbarian_unarmored_defense_adds_con(self):
        """野蛮人：10 + 敏 2 + 体 2 = 14，不是 12。"""
        _, sheet = self.sheet("barbarian", 1)
        self.assertEqual(sheet["ac"]["total"], 14)

    def test_monk_unarmored_defense_adds_wis(self):
        """武僧：10 + 敏 2 + 感 1 = 13。"""
        _, sheet = self.sheet("monk", 1)
        self.assertEqual(sheet["ac"]["total"], 13)

    def test_unarmored_defense_only_when_unarmored(self):
        """条件挂在 `unarmored` 上，护甲通道接进来（P5b）以后它自动跟着失效。

        「穿甲以后确实失效」由 test_armor.py 验证；这里只锁条件本身存在。
        """
        actor, _ = self.sheet("barbarian", 1)
        mods = modifiers_for(passive_modifiers(self.bundle, actor), "ac")
        self.assertEqual(len(mods), 1)
        self.assertEqual(dict(mods[0].when or {}), {"unarmored": True})
        self.assertTrue(facts_for(actor)["unarmored"])

    def test_armor_and_shield_are_separate_facts(self):
        """野蛮人的无甲防御允许持盾，武僧的不允许 —— 差别必须写在内容里。

        如果把两条合并成一句「unarmored」，武僧就得在代码里判职业，
        野蛮人则会被误伤（持盾就掉 AC）。
        """
        barbarian, _ = self.sheet("barbarian", 1)
        monk, _ = self.sheet("monk", 1)
        when_barbarian = modifiers_for(passive_modifiers(self.bundle, barbarian), "ac")[0].when
        when_monk = modifiers_for(passive_modifiers(self.bundle, monk), "ac")[0].when
        self.assertEqual(dict(when_barbarian), {"unarmored": True})
        self.assertEqual(dict(when_monk), {"unarmored": True, "shield": False})
        facts = facts_for(monk)
        self.assertIn("unarmored", facts)
        self.assertIn("shield", facts)

    def test_average_defense_does_not_stack_across_classes(self):
        """同一个 ac target 上两条 SET 会互相冲突 —— 这里用加法，所以只验证不重复。"""
        actor, sheet = self.sheet("barbarian", 1)
        ac_mods = modifiers_for(passive_modifiers(self.bundle, actor), "ac")
        self.assertEqual(sum(1 for mod in ac_mods if mod.target == "ac"), 1)

    # --- 守护灵光 -----------------------------------------------------
    def test_aura_of_protection_from_level_six(self):
        _, before = self.sheet("paladin", 5)
        _, after = self.sheet("paladin", 6)
        for key in ("str", "dex", "con", "int", "wis", "cha"):
            with self.subTest(save=key):
                self.assertEqual(after["saves"][key]["total"] - before["saves"][key]["total"], 1)

    def test_aura_uses_charisma_with_floor_one(self):
        """魅力 8（-1）时灵光仍给 +1；魅力 20（+5）时给 +5。这是 2024 的新写法。"""
        low = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
        high = dict(low, cha=20)
        _, weak = self.sheet("paladin", 6, low)
        _, strong = self.sheet("paladin", 6, high)
        self.assertEqual(weak["saves"]["int"]["total"], 1)          # 0 + 灵光 1
        self.assertEqual(strong["saves"]["int"]["total"], 5)        # 0 + 灵光 5

    def test_aura_modifiers_are_scoped_as_aura(self):
        actor, _ = self.sheet("paladin", 6)
        mods = [mod for mod in passive_modifiers(self.bundle, actor)
                if mod.target.startswith("save.")]
        self.assertEqual(len(mods), 6)
        self.assertTrue(all(mod.scope.value == "aura" for mod in mods))

    # --- 熟练授予 -----------------------------------------------------
    def test_monk_disciplined_survivor_grants_all_saves(self):
        _, before = self.sheet("monk", 13)
        _, after = self.sheet("monk", 14)
        gained = {key for key in before["saves"] if not before["saves"][key]["proficient"]}
        self.assertEqual(gained, {"con", "int", "wis", "cha"})
        self.assertTrue(all(after["saves"][key]["proficient"] for key in after["saves"]))

    def test_rogue_slippery_mind_grants_wis_and_cha(self):
        _, before = self.sheet("rogue", 14)
        _, after = self.sheet("rogue", 15)
        for key in ("wis", "cha"):
            with self.subTest(save=key):
                self.assertFalse(before["saves"][key]["proficient"])
                self.assertTrue(after["saves"][key]["proficient"])
        self.assertFalse(after["saves"]["con"]["proficient"])

    def test_passive_proficiencies_are_tokens(self):
        actor, _ = self.sheet("monk", 14)
        tokens = passive_proficiencies(self.bundle, actor)
        self.assertIn("save.con", tokens)
        self.assertTrue(all("." in token for token in tokens))

    # --- 明细 ---------------------------------------------------------
    def test_ac_detail_names_the_source(self):
        """明细要能说出「+4 来自哪条特性」，否则玩家看到 16 不知道从哪来的。"""
        actor, sheet = self.sheet("barbarian", 1)
        mods = modifiers_for(passive_modifiers(self.bundle, actor), "ac")
        self.assertEqual(mods[0].source, "无甲防御")
        self.assertIn("无甲防御", sheet["ac"]["detail"])

    def test_source_can_be_localized(self):
        """明细用显示名而不是 id：英文界面不该看到 dnd2024.class... 。"""
        actor, _ = self.sheet("barbarian", 1)
        english = modifiers_for(passive_modifiers(self.bundle, actor, "en"), "ac")
        self.assertEqual(english[0].source, "Unarmored Defense")

    def test_save_modifiers_are_filtered_by_ability(self):
        """resolve() 不按 target 过滤，调用方必须分开 —— 分开错了会 6 项豁免全加一遍。"""
        actor, _ = self.sheet("paladin", 6)
        mods = passive_modifiers(self.bundle, actor)
        self.assertEqual(len(save_modifiers(mods, "wis")), 1)
        self.assertEqual(len(modifiers_for(mods, "ac")), 0)


if __name__ == "__main__":
    unittest.main()
