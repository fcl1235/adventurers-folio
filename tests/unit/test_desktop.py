# -*- coding: utf-8 -*-
"""P6c 验收：桌面前端接到 api 上，且不抢焦点。

三条硬要求：
  1. 界面上的数字与 `character_sheet()` 完全一致（前端不算第二遍）
  2. `refresh()` 之后显示跟着变（不允许缓存派生值）
  3. `selftest=True` 时窗口始终 withdrawn —— 探针不许把窗口弹到前台
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from apps.desktop.app import WINDOW_MIN, DesktopApp

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
FIGHTER = "dnd2024.class.fighter"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


class DesktopAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _app(self, class_id=FIGHTER, level=5, **kwargs):
        actor = api.new_character(self.bundle, class_id, level, SCORES, **kwargs)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app

    def test_window_stays_withdrawn(self):
        app = self._app()
        self.assertFalse(app.winfo_ismapped(), "selftest 模式下窗口不许被映射")
        self.assertFalse(app.winfo_viewable())

    def test_skills_match_sheet(self):
        app = self._app()
        rows = app.sheet["skills"]
        self.assertEqual(app.overview.skills.row_count, len(rows))
        for index, row in enumerate(rows):
            self.assertEqual(app.overview.skills.text(index, 0), row["name"])
            self.assertEqual(app.overview.skills.text(index, 2), "%+d" % row["total"])

    def test_fight_block_matches_sheet(self):
        app = self._app()
        sheet = app.sheet
        self.assertEqual(app.overview.fight._values[0].get(), str(sheet["ac"]["total"]))
        self.assertEqual(app.overview.fight._values[1].get(), "%+d" % sheet["initiative"])
        self.assertEqual(app.overview.fight._values[2].get(),
                         "%d/%d" % (sheet["hp"]["current"], sheet["hp"]["maximum"]))

    def test_refresh_follows_data(self):
        app = self._app()
        # 技能按（属性, key）排序，不能假定 0 号是哪一个 —— 按 key 找行号
        index = [row["key"] for row in app.sheet["skills"]].index("acrobatics")
        before = app.overview.skills.text(index, 2)
        app.actor.profile = app.actor.profile.with_proficiencies(["skill.acrobatics"])
        app.refresh()
        after = app.overview.skills.text(index, 2)
        self.assertNotEqual(before, after, "加了熟练之后界面没变 —— 说明缓存了派生值")
        self.assertEqual(after, "%+d" % app.sheet["skills"][index]["total"])

    def test_header_shows_class_and_level(self):
        app = self._app()
        text = app.sub_var.get()
        self.assertIn("战士", text)
        self.assertIn("5", text)

    def test_layout_fits_min_window(self):
        app = self._app()
        report = app.layout_report()
        avail_w = WINDOW_MIN[0] - 16
        avail_h = WINDOW_MIN[1] - app.status.winfo_reqheight() - 40
        for row in report["pages"]:
            width, height = row["req"]
            self.assertLessEqual(width, avail_w, "页面横向溢出")
            self.assertLessEqual(height, avail_h, "页面纵向溢出")


if __name__ == "__main__":
    unittest.main()
