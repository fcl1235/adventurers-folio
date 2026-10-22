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


WIZARD = "dnd2024.class.wizard"
INT_SCORES = {"str": 8, "dex": 14, "con": 14, "int": 17, "wis": 12, "cha": 10}


class SpellPageTest(unittest.TestCase):
    """P6e 验收：法术页能选、能存、选错能说清楚。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _page(self, class_id=WIZARD, level=5, scores=INT_SCORES):
        actor = api.new_character(self.bundle, class_id, level, scores)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app, app.spells

    def test_non_caster_page_is_disabled(self):
        _, page = self._page(FIGHTER, 5, SCORES)
        self.assertEqual(str(page.pick_button.cget("state")), "disabled")
        self.assertEqual(page.prepared.row_count, 0)
        self.assertIn("不施法", page.status_var.get() + page.class_var.get())

    def test_caster_lists_options(self):
        _, page = self._page()
        block = page._block()
        self.assertEqual(page.prepared.row_count, len(block["prepared"]["options"]))
        self.assertEqual(page.cantrips.row_count, len(block["cantrips"]["options"]))
        self.assertIn("0 /", page.prep_frame.cget("text"))

    def test_toggle_writes_to_profile(self):
        app, page = self._page()
        target = page._spell_options("prepared")[0]["id"]
        page.prepared.select_id(target)
        self.assertTrue(page.toggle_prepared(), page.status_var.get())
        self.assertIn(target, app.actor.profile.spells_of(WIZARD))
        self.assertIn("1 /", page.prep_frame.cget("text"))

    def test_toggle_again_removes(self):
        app, page = self._page()
        target = page._spell_options("prepared")[0]["id"]
        page.prepared.select_id(target)
        page.toggle_prepared()
        page.prepared.select_id(target)
        self.assertTrue(page.toggle_prepared(), page.status_var.get())
        self.assertNotIn(target, app.actor.profile.spells_of(WIZARD))

    def test_row_is_marked_when_chosen(self):
        _, page = self._page()
        target = page._spell_options("prepared")[0]["id"]
        before = page.prepared.text_at(page.prepared.index_of(target))
        page.prepared.select_id(target)
        page.toggle_prepared()
        after = page.prepared.text_at(page.prepared.index_of(target))
        self.assertNotEqual(before, after, "选定后清单行没有勾选标记")
        self.assertTrue(after.startswith("✓"), after)

    def test_quota_overflow_reports_error_and_keeps_actor(self):
        app, page = self._page()
        options = [row["id"] for row in page._spell_options("prepared")]
        quota = int(page._block()["prepared"]["max"])
        for spell_id in options[:quota]:
            page.prepared.select_id(spell_id)
            self.assertTrue(page.toggle_prepared(), page.status_var.get())
        page.prepared.select_id(options[quota])
        self.assertFalse(page.toggle_prepared(), "超过名额还成功了")
        self.assertIn("上限", page.status_var.get())
        self.assertEqual(len(app.actor.profile.spells_of(WIZARD)), quota)
        # 失败后选中项还在（玩家要能马上换个法术，而不是重新找）
        self.assertEqual(page.prepared.selected_id(), options[quota])

    def test_detail_panel_shows_the_selected_spell(self):
        _, page = self._page()
        row = page._spell_options("prepared")[0]
        text = page.show("prepared", row["id"])
        self.assertIn(row["name"], text)
        self.assertIn("施法", text)

    def test_cantrip_and_prepared_are_separate(self):
        app, page = self._page()
        cantrip = page._spell_options("cantrips")[0]["id"]
        page.cantrips.select_id(cantrip)
        self.assertTrue(page.toggle_cantrip(), page.status_var.get())
        self.assertIn(cantrip, app.actor.profile.cantrips_of(WIZARD))
        self.assertEqual(app.actor.profile.spells_of(WIZARD), ())

    def test_selection_survives_refresh(self):
        """重画清单后选中项不能丢 —— 否则连着选两个法术要点两次。"""
        _, page = self._page()
        target = page._spell_options("prepared")[3]["id"]
        page.prepared.select_id(target)
        page.refresh(page.app.sheet)
        self.assertEqual(page.prepared.selected_id(), target)


if __name__ == "__main__":
    unittest.main()
