# -*- coding: utf-8 -*-
"""P7b 验收：优势 / 劣势终于有消费方（G1）。

在此之前「优势」只是文字：20 条特性写着「你有优势」，掷骰那边一次也只掷一个 d20。
这一组测试盯住四件事：

  1. 标记的匹配规则（精确 / 父级覆盖 / 优势劣势抵消）
  2. 优势**真的进了掷骰**：`rolled == True` 时掷两次、取高、留下被弃的那个
  3. 加值与角色卡**同源**（不是第二套算法）
  4. 诚实标记：有优势的能力报 `dice`，不许报 `counted`（它不是 +5），
     也不许报 `text`（它确实生效了）

断言一律挑**本来不成立**的样本（§14.3 的教训）：证明「敏捷豁免有优势」不算数，
要同时证明「力量豁免没有优势」。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.rules import advantage
from dnd5r.rules.contributions import power_status

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
BARBARIAN = "dnd2024.class.barbarian"
FIGHTER = "dnd2024.class.fighter"
CHAMPION = "dnd2024.subclass.fighter.champion"


class AdvantageRulesTest(unittest.TestCase):
    """纯函数的规则，不需要内容包。"""

    def test_parse_label(self):
        self.assertEqual(advantage.parse_label("advantage.adv.save.dex"), ("adv", "save.dex"))
        self.assertEqual(advantage.parse_label("advantage.dis.check.all"), ("dis", "check.all"))
        # 不是优势标记的一律 None —— 别的标签不该被当成优势
        self.assertIsNone(advantage.parse_label("modifier:ac"))
        self.assertIsNone(advantage.parse_label("advantage.weird.save.dex"))
        self.assertIsNone(advantage.parse_label("advantage.adv."))
        self.assertIsNone(advantage.parse_label(None))

    def test_parent_covers_children(self):
        self.assertTrue(advantage.target_matches("check.all", "check.athletics"))
        self.assertTrue(advantage.target_matches("save.all", "save.dex"))
        # 反过来不成立：指定技能的优势不该扩散到全体
        self.assertFalse(advantage.target_matches("check.athletics", "check.all"))
        self.assertFalse(advantage.target_matches("check.athletics", "check.stealth"))
        # 跨类别不串味
        self.assertFalse(advantage.target_matches("save.dex", "check.dex"))
        self.assertFalse(advantage.target_matches("attack.all", "initiative"))

    def test_merge_cancels(self):
        self.assertEqual(advantage.merge([]), "flat")
        self.assertEqual(advantage.merge(["adv"]), "adv")
        self.assertEqual(advantage.merge(["dis"]), "dis")
        self.assertEqual(advantage.merge(["adv", "dis"]), "flat")
        self.assertEqual(advantage.merge(["flat", "adv"]), "adv")


class AdvantageWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def _actor(self, class_id, level, subclass=None):
        return api.new_character(self.bundle, class_id, level, SCORES,
                                 name_zh="测试", name_en="Test", subclass=subclass)

    def test_danger_sense_only_on_dex(self):
        actor = self._actor(BARBARIAN, 2)
        sheet = api.character_sheet(actor, self.bundle)
        self.assertEqual(sheet["saves"]["dex"]["mode"], "adv")
        self.assertIn("危险感知", sheet["saves"]["dex"]["mode_sources"])
        # 反证：力量豁免不该有优势
        self.assertEqual(sheet["saves"]["str"]["mode"], "flat")
        self.assertEqual(sheet["saves"]["str"]["mode_sources"], [])

    def test_danger_sense_not_below_level(self):
        # 1 级还没有「危险感知」
        sheet = api.character_sheet(self._actor(BARBARIAN, 1), self.bundle)
        self.assertEqual(sheet["saves"]["dex"]["mode"], "flat")

    def test_danger_sense_drops_when_incapacitated(self):
        actor = self._actor(BARBARIAN, 2)
        actor.conditions.add("incapacitated")
        sheet = api.character_sheet(actor, self.bundle)
        self.assertEqual(sheet["saves"]["dex"]["mode"], "flat")
        self.assertEqual(sheet["saves"]["dex"]["mode_sources"], [])

    def test_feral_instinct_is_initiative_only(self):
        actor = self._actor(BARBARIAN, 7)
        sheet = api.character_sheet(actor, self.bundle)
        self.assertEqual(sheet["initiative"]["mode"], "adv")
        self.assertIn("野性本能", sheet["initiative"]["mode_sources"])
        # 先攻优势不是「敏捷检定优势」：两者名字不同，不能串
        self.assertEqual(sheet["skills"][0]["mode"] in ("flat", "adv"), True)

    def test_champion_athlete_gives_two_markers(self):
        actor = self._actor(FIGHTER, 3, CHAMPION)
        sheet = api.character_sheet(actor, self.bundle)
        self.assertEqual(sheet["initiative"]["mode"], "adv")
        athletics = next(row for row in sheet["skills"] if row["key"] == "athletics")
        self.assertEqual(athletics["mode"], "adv")
        # 反证：别的力量技能（威吓不是力量，用 sleight_of_hand 更明确）不该有优势
        stealth = next(row for row in sheet["skills"] if row["key"] == "stealth")
        self.assertEqual(stealth["mode"], "flat")

    def test_roll_uses_two_dice(self):
        actor = self._actor(BARBARIAN, 7)
        result = api.roll_check(actor, self.bundle, "initiative", rng=ScriptedRng([7, 15]))
        self.assertTrue(result["advantage"])
        self.assertEqual(result["die"], 15)
        self.assertEqual(result["dropped"], [7])
        self.assertEqual(result["total"], 15 + result["modifier"])

    def test_roll_flat_uses_one_die(self):
        actor = self._actor(BARBARIAN, 7)
        # 力量豁免没有优势 —— 脚本只给一个值，多掷一次就会因为「序列耗尽」炸掉
        result = api.roll_check(actor, self.bundle, "save", "str", rng=ScriptedRng([11]))
        self.assertFalse(result["advantage"])
        self.assertEqual(result["total"], 11 + result["modifier"])

    def test_roll_modifier_matches_sheet(self):
        """掷骰的加值必须与角色卡显示的一致 —— 两套算法会悄悄分叉。"""
        actor = self._actor(BARBARIAN, 7)
        sheet = api.character_sheet(actor, self.bundle)
        for ability in ("str", "dex", "con", "int", "wis", "cha"):
            result = api.roll_check(actor, self.bundle, "save", ability,
                                    rng=ScriptedRng([10, 10]))
            self.assertEqual(result["modifier"], sheet["saves"][ability]["total"])
        self.assertEqual(
            api.roll_check(actor, self.bundle, "initiative", rng=ScriptedRng([10, 10]))["modifier"],
            sheet["initiative"]["total"])
        for row in sheet["skills"]:
            result = api.roll_check(actor, self.bundle, "skill", row["key"],
                                    rng=ScriptedRng([10, 10]))
            self.assertEqual(result["modifier"], row["total"], row["key"])

    def test_roll_check_rejects_unknown(self):
        actor = self._actor(BARBARIAN, 2)
        with self.assertRaises(api.RuleError):
            api.roll_check(actor, self.bundle, "jump", "str")
        with self.assertRaises(api.RuleError):
            api.roll_check(actor, self.bundle, "save", "luck")
        with self.assertRaises(api.RuleError):
            api.roll_check(actor, self.bundle, "skill", "basketweaving")

    def test_status_says_dice_not_counted(self):
        """优势进了掷骰通道，但**没有**进数值 —— 三档说法必须分清。"""
        actor = self._actor(BARBARIAN, 2)
        powers = {row["id"]: row for row in api.character_sheet(actor, self.bundle)["powers"]}
        danger = powers["dnd2024.class.barbarian.danger_sense"]
        self.assertEqual(danger["status"], "dice")
        self.assertEqual(power_status(api.find_power(self.bundle, danger["id"], actor)), "dice")


if __name__ == "__main__":
    unittest.main()
