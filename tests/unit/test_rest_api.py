# -*- coding: utf-8 -*-
"""G37 验收：休息终于有入口了。

在这之前 `rules/rest.py` 只被 CLI 壳（`session.py`）调着，`dnd5r/api/` 里
一次都没引用过，桌面端也没有按钮 —— 法术位、职业资源池、生命骰、力竭、
`rest` 作用域标记（诗人灵感）全都靠休息刷新，于是**玩家打完一场遭遇战就停在
0 位上，只能重建角色**。

这组测试盯四件事：

  1. **门面存在且数值对**：`rest_options` 报的生命骰余量、长休预览与角色真实
     资源池一致（界面不自己算）。
  2. **真的改了角色**：短休花骰回血、长休回满并清临时 HP，`rest` 作用域标记
     跟着清掉。
  3. **显示名走内容**：中文界面写「战士」「回气」，不是 `fighter` / `second_wind`
     —— 规则层不查内容，名字由 api 层拼好传进去。
  4. **双语**：`locale="en"` 时整句是英文，且不带中文标点。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.model.marks import Mark

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
FIGHTER = "dnd2024.class.fighter"
WIZARD = "dnd2024.class.wizard"
SECOND_WIND = "dnd2024.resource.fighter.second_wind"

STR16 = {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10}
INT16 = {"str": 8, "dex": 14, "con": 14, "int": 16, "wis": 12, "cha": 10}


class RestApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def fighter(self, level=5, actor_id="pc.test"):
        return api.new_character(self.bundle, FIGHTER, level, STR16,
                                 name_zh="战士", name_en="Fighter",
                                 actor_id=actor_id)

    # --- 1. 门面报的数字 ------------------------------------------------
    def test_options_report_hit_dice(self):
        actor = self.fighter()
        options = api.rest_options(actor, self.bundle)
        self.assertEqual(options["dice_max"], 5)
        self.assertEqual(options["dice_left"], 5)
        rows = options["classes"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sides"], 10)
        self.assertEqual(rows[0]["name"], "战士")

    def test_options_preview_long_rest(self):
        actor = self.fighter()
        actor.hp.current = 10
        options = api.rest_options(actor, self.bundle)
        self.assertEqual(options["long_rest"]["heal"],
                         actor.hp.maximum - 10)

    def test_options_can_short_without_dice(self):
        """骰子花光但短休池（回气）还没用时，短休仍有意义 —— 不该被禁掉。

        回气是 `Refresh.SHORT_REST`，短休不花生命骰也能回它。
        """
        actor = self.fighter()
        for _ in range(5):
            api.take_short_rest(actor, self.bundle, spend=1)
        # 五次短休顺手把回气回满了 —— 花掉一次，短休就又有意义了
        actor.resources.spend(SECOND_WIND, 1)
        options = api.rest_options(actor, self.bundle)
        self.assertEqual(options["dice_left"], 0)
        self.assertTrue(options["can_short"])

    # --- 2. 真的改了角色 -------------------------------------------------
    def test_short_rest_spends_dice_and_heals(self):
        actor = self.fighter()
        actor.hp.current = 5
        report = api.take_short_rest(actor, self.bundle, spend=2,
                                     rng=ScriptedRng([8, 9]))
        self.assertEqual(report["dice_spent"], 2)
        # 8+2 与 9+2（体质 14 是 +2）
        self.assertEqual(actor.hp.current, 5 + 10 + 11)
        self.assertEqual(api.rest_options(actor, self.bundle)["dice_left"], 3)
        self.assertEqual(report["hp"]["after"], actor.hp.current)

    def test_short_rest_never_exceeds_available_dice(self):
        actor = self.fighter()
        report = api.take_short_rest(actor, self.bundle, spend=99)
        self.assertEqual(report["dice_spent"], 5)
        self.assertEqual(api.rest_options(actor, self.bundle)["dice_left"], 0)

    def test_long_rest_restores_everything(self):
        actor = self.fighter()
        actor.hp.current = 7
        actor.hp.temp = 4
        pool = actor.resources.get(SECOND_WIND)
        full = pool.capacity
        actor.resources.spend(SECOND_WIND, 1)
        api.take_long_rest(actor, self.bundle)
        self.assertEqual(actor.hp.current, actor.hp.maximum)
        self.assertEqual(actor.hp.temp, 0)
        self.assertEqual(actor.resources.get(SECOND_WIND).available, full)
        self.assertEqual(api.rest_options(actor, self.bundle)["dice_left"], 5)

    def test_rest_clears_rest_scoped_marks(self):
        """诗人灵感这类「撑不过一次休息」的标记，休息必须清掉。"""
        actor = self.fighter()
        actor.marks.add(Mark(id="inspiration", kind="token", mode="adv",
                             expires="rest"))
        api.take_long_rest(actor, self.bundle)
        self.assertEqual([mark.id for mark in actor.marks.active()], [])

    def test_sheet_carries_rest_block(self):
        actor = self.fighter()
        sheet = api.character_sheet(actor, self.bundle)
        self.assertIn("rest", sheet)
        self.assertEqual(sheet["rest"]["dice_left"], 5)
        self.assertIsInstance(sheet["rest"]["long_rest"]["heal"], int)

    # --- 3. 显示名 -------------------------------------------------------
    def test_chinese_names_not_ids(self):
        actor = self.fighter()
        actor.hp.current = 5
        actor.resources.spend(SECOND_WIND, 1)
        summary = api.take_short_rest(actor, self.bundle, spend=1)["summary"]
        self.assertIn("战士", summary)
        self.assertIn("回气", summary)
        self.assertNotIn("fighter", summary)
        self.assertNotIn("second_wind", summary)

    def test_long_rest_uses_class_name(self):
        actor = self.fighter()
        actor.resources.spend("hit_dice.%s" % FIGHTER, 2)
        summary = api.take_long_rest(actor, self.bundle)["summary"]
        self.assertIn("战士", summary)
        self.assertNotIn("hit_dice", summary)

    # --- 4. 双语 ---------------------------------------------------------
    def test_english_report(self):
        actor = self.fighter()
        actor.hp.current = 5
        summary = api.take_short_rest(actor, self.bundle, spend=1,
                                      locale="en")["summary"]
        self.assertIn("Hit Dice", summary)
        self.assertIn("Regained", summary)
        self.assertNotIn("；", summary)
        self.assertNotIn("生命", summary)

    def test_english_kind_name(self):
        actor = self.fighter()
        self.assertEqual(api.take_long_rest(actor, self.bundle, "en")["kind_name"],
                         "Long Rest")
        self.assertEqual(api.take_long_rest(actor, self.bundle)["kind_name"],
                         "长休")

    # --- 5. 兼职 ---------------------------------------------------------
    def test_multiclass_dice_per_class(self):
        """兼职按各自骰面算：战 5 / 法 1 各一组，不能统一成 d10。"""
        actor = api.new_character(
            self.bundle, FIGHTER, 5,
            {"str": 16, "dex": 12, "con": 14, "int": 13, "wis": 10, "cha": 10},
            extra_classes=((WIZARD, 1),), actor_id="pc.multi")
        rows = {row["id"]: row for row in
                api.rest_options(actor, self.bundle)["classes"]}
        self.assertEqual(rows[FIGHTER]["sides"], 10)
        self.assertEqual(rows[WIZARD]["sides"], 6)
        self.assertEqual(rows[WIZARD]["max"], 1)


if __name__ == "__main__":
    unittest.main()
