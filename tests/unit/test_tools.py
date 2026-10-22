# -*- coding: utf-8 -*-
"""P8a 验收：工具作为独立熟练类别（G4）。

在此之前「多面手」的中文说明写着「只结算技能那一半，工具请手记」——
工具连**名字**都没有，`tool.<x>` 这个 token 语法存在但永远不会出现。
这一组盯住四件事：

  1. 37 件工具是**内容**（`tools.yaml`），不是代码里的常量
  2. 混选真的能混：`Skilled` 三项里可以有技能也有工具
  3. 工具检定 = 属性检定 + 熟练，且**属性可换**（规则是「DM 决定用哪项」）
  4. 角色卡上的工具加值与 `roll_check` 同源

断言一律挑**本来不成立**的样本：证明「盗贼工具 +4」不算数，
要同时证明「鼓 -1」（不熟练）—— 否则把熟练加值无条件加上去也能通过。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import TOOL_KINDS, PluginError
from dnd5r.kernel.errors import RuleError
from dnd5r.rules.feats import proficiency_pool

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
FIGHTER = "dnd2024.class.fighter"
SKILLED = "dnd2024.feat.skilled"
THIEVES = "dnd2024.tool.thieves_tools"
DRUM = "dnd2024.tool.drum"
# 选择项的取值是**熟练 token**（`tool.x` / `skill.x`），不是内容 id ——
# 混选时要靠前缀区分「这件工具」与「这项技能」。
THIEVES_TOKEN = "tool.thieves_tools"
DRUM_TOKEN = "tool.drum"


class ToolContentTest(unittest.TestCase):
    """工具表是内容，且抄全了。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def test_all_37_tools_loaded(self):
        self.assertEqual(len(self.bundle.tools), 37)

    def test_kinds_cover_four_categories(self):
        counts: dict[str, int] = {}
        for tool in self.bundle.tools.values():
            counts[tool.kind] = counts.get(tool.kind, 0) + 1
        self.assertEqual(sorted(counts), sorted(TOOL_KINDS))
        # 17 工匠 / 4 游戏 / 10 乐器 / 6 其他 —— 与 2024 的工具表一致
        self.assertEqual(counts, {"artisan": 17, "gaming": 4, "musical": 10, "other": 6})

    def test_every_tool_has_suggested_ability(self):
        for tool in self.bundle.tools.values():
            self.assertIn(tool.ability, ("str", "dex", "con", "int", "wis", "cha"),
                          "%s 的建议属性不合法" % tool.id)

    def test_bad_tool_rejected(self):
        from dnd5r.content import parse_tool
        good = {"id": "dnd2024.tool.demo", "name": {"zh": "演示", "en": "Demo"},
                "kind": "artisan", "ability": "dex"}
        self.assertEqual(parse_tool(dict(good)).kind, "artisan")
        with self.assertRaises(PluginError):
            parse_tool({**good, "kind": "spaceship"})     # 类别不认识
        with self.assertRaises(PluginError):
            parse_tool({**good, "ability": "luck"})       # 属性不认识
        with self.assertRaises(PluginError):
            parse_tool({k: v for k, v in good.items() if k != "ability"})


class ToolProficiencyTest(unittest.TestCase):
    """混选与熟练落库。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def _actor(self, choices):
        return api.new_character(self.bundle, FIGHTER, 4, SCORES,
                                 name_zh="测试", name_en="Test",
                                 feats=(SKILLED,), choices=choices)

    def test_pool_is_skills_plus_tools(self):
        pool = proficiency_pool(self.bundle)
        self.assertEqual(len(pool), len(self.bundle.skills) + len(self.bundle.tools))
        # 顺序稳定：先技能后工具，各自按 key 排
        self.assertTrue(pool[0].startswith("skill."))
        self.assertTrue(pool[-1].startswith("tool."))
        skills = pool[:len(self.bundle.skills)]
        self.assertEqual(list(skills), sorted(skills))
        tools = pool[len(self.bundle.skills):]
        self.assertEqual(list(tools), sorted(tools))
        # 反证：token 是完整形式，不是裸 key
        self.assertIn("skill.stealth", pool)
        self.assertIn("tool.thieves_tools", pool)

    def test_mixed_pick_lands(self):
        actor = self._actor({"dnd2024.feat.skilled.proficiency":
                             ("skill.stealth", "tool.thieves_tools", "tool.lute")})
        prof = set(actor.profile.proficiencies)
        self.assertIn("skill.stealth", prof)
        self.assertIn("tool.thieves_tools", prof)
        self.assertIn("tool.lute", prof)
        # 反证：没选的工具不该混进来
        self.assertNotIn("tool.drum", prof)

    def test_unknown_tool_rejected(self):
        with self.assertRaises(RuleError):
            self._actor({"dnd2024.feat.skilled.proficiency":
                         ("skill.stealth", "tool.lasersword", "tool.lute")})

    def test_skill_only_still_works(self):
        """老档写的是三项技能，改 kind 之后也必须照常通过。"""
        actor = self._actor({"dnd2024.feat.skilled.proficiency":
                             ("skill.stealth", "skill.arcana", "skill.insight")})
        self.assertIn("skill.stealth", actor.profile.proficiencies)


class ToolCheckTest(unittest.TestCase):
    """工具检定：属性 + 熟练，属性可换。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _actor(self, tool_taken=(THIEVES_TOKEN,)):
        # 多面手要选满 3 项才会落库（选一半是 `pending`，不是错误）——
        # 这里补两项技能凑满，保证工具那一项真的生效
        picked = tuple(tool_taken) + ("skill.arcana", "skill.insight")
        self.assertEqual(len(picked), 3)
        return api.new_character(self.bundle, FIGHTER, 4, SCORES,
                                 name_zh="测试", name_en="Test",
                                 feats=(SKILLED,),
                                 choices={"dnd2024.feat.skilled.proficiency": picked})

    def _row(self, actor, tool_id):
        sheet = api.character_sheet(actor, self.bundle)
        return next(row for row in sheet["tools"] if row["id"] == tool_id)

    def test_proficient_adds_bonus(self):
        actor = self._actor()
        row = self._row(actor, THIEVES)
        self.assertTrue(row["proficient"])
        # 4 级熟练加值 +2，敏捷 14 = +2
        self.assertEqual(row["total"], 4)
        self.assertIn("熟练", row["detail"])

    def test_not_proficient_has_no_bonus(self):
        actor = self._actor()
        row = self._row(actor, DRUM)
        self.assertFalse(row["proficient"])
        # 鼓是魅力工具，魅力 8 = -1；不熟练就只有 -1
        self.assertEqual(row["total"], -1)
        # 掷骰那条路也要单独验：卡片与 roll_check 是两段代码，
        # 只验卡片的话「掷骰那边无条件加熟练」能悄悄通过（反向验证抓过）
        roll = api.roll_check(actor, self.bundle, "tool", DRUM)
        self.assertEqual(roll["modifier"], -1)
        self.assertNotIn("熟练", roll["detail"])

    def test_ability_can_be_overridden(self):
        actor = self._actor()
        coach = api.roll_check(actor, self.bundle, "tool", THIEVES)
        self.assertIn("DEX", coach["label"])
        self.assertEqual(coach["modifier"], 4)
        # 规则是「DM 决定用哪项属性」—— 换成力量必须真的换（+3 而不是 +2）
        forced = api.roll_check(actor, self.bundle, "tool", THIEVES, ability="str")
        self.assertIn("STR", forced["label"])
        self.assertEqual(forced["modifier"], 5)   # 3 STR + 2 熟练
        # 反证：同一个角色用智力就该更低（0 + 2）
        weak = api.roll_check(actor, self.bundle, "tool", THIEVES, ability="int")
        self.assertEqual(weak["modifier"], 2)

    def test_sheet_and_roll_agree(self):
        """卡上的数字与掷骰的加值必须是同一个算法 —— 两套算法最难发现。"""
        actor = self._actor()
        row = self._row(actor, THIEVES)
        roll = api.roll_check(actor, self.bundle, "tool", THIEVES)
        self.assertEqual(row["total"], roll["modifier"])
        self.assertEqual(row["detail"], roll["detail"])

    def test_key_or_id_both_accepted(self):
        actor = self._actor()
        by_id = api.roll_check(actor, self.bundle, "tool", THIEVES)
        by_key = api.roll_check(actor, self.bundle, "tool", "thieves_tools")
        self.assertEqual(by_id["modifier"], by_key["modifier"])

    def test_unknown_tool_or_ability_rejected(self):
        actor = self._actor()
        with self.assertRaises(RuleError):
            api.roll_check(actor, self.bundle, "tool", "lasersword")
        with self.assertRaises(RuleError):
            api.roll_check(actor, self.bundle, "tool", THIEVES, ability="luck")

    def test_tool_in_check_kinds(self):
        self.assertIn("tool", api.CHECK_KINDS)


class ToolGeneratorTest(unittest.TestCase):
    """生成器与内容必须说同一件事，否则 `--force` 会悄悄改数据。"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        path = ROOT / "tools" / "gen_tools.py"
        spec = importlib.util.spec_from_file_location("gen_tools", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.gen = module

    def test_generator_is_idempotent(self):
        rows = self.gen.load_rows()
        self.assertEqual(len(rows), 37)
        text = (ROOT / "plugins" / "dnd2024-core" / "tools.yaml").read_text(encoding="utf-8")
        self.assertEqual(text, self.gen.render(rows))

    def test_every_english_name_translated(self):
        rows = self.gen.load_rows()
        for row in rows:
            self.assertTrue(row["zh"])
            # 中文名不能等于英文名（漏翻时会这样）
            self.assertNotEqual(row["zh"], row["en"], "%s 没有中文名" % row["en"])


if __name__ == "__main__":
    unittest.main()
