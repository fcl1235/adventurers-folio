# -*- coding: utf-8 -*-
"""中英双语：界面取词、语言切换、接口层文案。

这一批测试守的是三件**容易被悄悄改坏**的事：

  1. **模块级常量不许冻在启动语言**。`T("技能")` 在 import 时求值，写进模块级
     字典/元组就永久定死成那一个语言。所以显示表一律走 `Catalog`（取值时翻译），
     表头/槽位/模式名在使用处翻译。踩过一次：探针在 en 下仍显示「技能 / 倒地」。
  2. **切语言要整窗重建**，重建后标签页不能跳回第一页、语言按钮要显示「切过去」
     的那个语言。
  3. **接口层算出来的句子**（「要选 3 项技能」）必须在格式化**之前**翻 —— 界面
     拿到手时已经是一整句填好数的中文，按整句查表永远查不到。

零弹窗：全部用 `App(selftest=True)`（内部 withdraw），不 deiconify、不 lift。
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

import dnd5r.api as api
from apps.desktop import i18n
from apps.desktop.app import MODE_WIZARD, SETTINGS_NAME, DesktopApp
from dnd5r.rules import text as rule_text

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
FIGHTER = "dnd2024.class.fighter"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
CJK = re.compile(r"[\u4e00-\u9fff]")


class LocaleSwitchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def setUp(self):
        i18n.set_locale("zh")
        self.addCleanup(i18n.set_locale, "zh")

    def _app(self, locale=None):
        actor = api.new_character(self.bundle, FIGHTER, 5, dict(SCORES))
        app = DesktopApp(self.bundle, actor, locale=locale, selftest=True,
                         save_dir=Path(tempfile.mkdtemp()))
        self.addCleanup(app.destroy)
        return app

    def test_selftest_forces_chinese(self):
        """探针里语言必须是中文 —— 否则「上次点过 English」会让报错截图变色。"""
        app = self._app()                      # locale=None，走 selftest 分支
        self.assertEqual(app.locale, "zh")
        self.assertEqual(i18n.get_locale(), "zh")

    def test_button_shows_other_locale(self):
        app = self._app()
        self.assertEqual(app.lang_button.cget("text"), "EN")
        app.switch_locale("en")
        # 重建后是**新控件**，旧的 self.lang_button 已销毁
        self.assertEqual(app.lang_button.cget("text"), "中文")
        self.assertEqual(app.locale, "en")

    def test_switch_rebuilds_and_keeps_tab(self):
        app = self._app()
        count = len(app.pages)
        app.book.select(2)
        before = app.pages[2].__class__.__name__
        app.switch_locale("en")
        self.assertEqual(len(app.pages), count, "页数不该变")
        self.assertEqual(app.pages[2].__class__.__name__, before)
        self.assertIn("Spells", app.book.tab(2, "text"))
        self.assertEqual(app.book.index(app.book.select()), 2, "切语言后标签页不能跳回第一页")

    def test_switch_changes_visible_text(self):
        app = self._app()
        app.switch_locale("en")
        # 概览页的表头是第一眼看到的东西，也是「模块级翻译」最容易漏的地方
        self.assertEqual(app.book.tab(0, "text"), "Overview")
        titles = [app.book.tab(index, "text") for index in range(len(app.pages))]
        self.assertFalse([title for title in titles if CJK.search(title)],
                         "英文界面下标签页不该还有中文：%r" % (titles,))

    def test_settings_persist_locale(self):
        app = self._app()
        app.switch_locale("en")
        path = app.save_dir / SETTINGS_NAME
        self.assertTrue(path.exists(), "切语言要记住，否则每次启动都得再点一次")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["locale"], "en")

    def test_switch_refused_while_wizard_open(self):
        """建卡那半张卡在向导里，重建就丢了 —— 所以要挡住，并说清楚为什么。"""
        app = self._app()
        app.new_character()
        self.assertEqual(app.mode, MODE_WIZARD)
        app.switch_locale("en")
        self.assertEqual(app.locale, "zh", "建卡中不许切语言")
        self.assertIn("切换语言", app.status.cget("text"))

    def test_runtime_missing_is_empty(self):
        """en 下走一遍主要页面，运行时不该出现「查不到译文」。"""
        app = self._app()
        i18n.MISSING.clear()
        app.switch_locale("en")
        self.assertEqual(sorted(i18n.MISSING), [], "这些中文串没有英文译文")


class ModuleLevelTextTest(unittest.TestCase):
    """显示表必须是 `Catalog`：模块级 `T()` 会冻在启动语言。"""

    def setUp(self):
        i18n.set_locale("zh")
        self.addCleanup(i18n.set_locale, "zh")

    def test_catalog_translates_on_read(self):
        from apps.desktop.widgets import ABILITY_ZH
        self.assertEqual(ABILITY_ZH["str"], "力量")
        i18n.set_locale("en")
        self.assertEqual(ABILITY_ZH["str"], "Strength")
        i18n.set_locale("zh")
        self.assertEqual(ABILITY_ZH["str"], "力量")

    def test_conditions_translate(self):
        from apps.desktop.conditions import CONDITIONS, _ZH
        first_id = CONDITIONS[0][0]
        zh = _ZH[first_id]
        i18n.set_locale("en")
        self.assertNotEqual(_ZH[first_id], zh)

    def test_blank_keys_are_not_missing(self):
        """空串不是待译文案，不该被记进 MISSING。"""
        i18n.MISSING.clear()
        i18n.set_locale("en")
        self.assertEqual(i18n.T(""), "")
        self.assertEqual(i18n.MISSING, set())


class WidgetTreeTest(unittest.TestCase):
    """扫一遍**真实控件树**，看英文界面里还有没有中文。

    `i18n.MISSING` 只能查「`T()` 查不到译文」；查不到「这段字根本没走 `T()`」——
    状态页那 14 个勾选框就是直接把 `CONDITIONS` 元组里的中文塞进 `text=` 的，
    `MISSING` 一直是空的，只有扫控件才看得见。所以这条测试是必要的：
    它守的是「静态审计（`tools/i18n_audit.py`）已经绿了但界面上还有中文」这一类。
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def setUp(self):
        i18n.set_locale("zh")
        self.addCleanup(i18n.set_locale, "zh")

    def _texts(self, widget, out):
        import tkinter as tk
        from tkinter import ttk
        for child in widget.winfo_children():
            try:
                value = child.cget("text")
            except tk.TclError:
                value = None
            if isinstance(value, str) and value:
                out.append(value)
            if isinstance(child, ttk.Notebook):
                out.extend(child.tab(index, "text") for index in range(len(child.tabs())))
            try:
                values = child.cget("values")
            except tk.TclError:
                values = None
            if isinstance(values, (tuple, list)):
                out.extend(item for item in values if isinstance(item, str) and item)
            self._texts(child, out)

    def test_no_chinese_left_in_english_ui(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, dict(SCORES))
        app = DesktopApp(self.bundle, actor, locale="en", selftest=True,
                         save_dir=Path(tempfile.mkdtemp()))
        self.addCleanup(app.destroy)
        leaked: list[str] = []
        texts: list[str] = []
        # 语言按钮故意写着「中文」（写的是**切过去**的那个语言），不算漏译
        allow = {i18n.LOCALE_SHORT["zh"]}
        self._texts(app, texts)
        # 每页都切一遍：标签页内容是按需构建的，不切就看不见
        for index in range(len(app.pages)):
            app.book.select(index)
            app.update_idletasks()
            texts = []
            self._texts(app.pages[index], texts)
            leaked.extend(text for text in texts
                          if CJK.search(text) and text not in allow)
        self.assertEqual(sorted(set(leaked)), [], "英文界面里这些文案还是中文")


class ApiTextTest(unittest.TestCase):
    """接口层：算出来的句子也要按语言出。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_wizard_steps_are_translated(self):
        zh = api.wizard_steps("zh")
        en = api.wizard_steps("en")
        self.assertEqual(zh[0]["title"], "职业")
        self.assertEqual(en[0]["title"], "Class")
        self.assertEqual(len(zh), len(en))
        self.assertFalse([step["hint"] for step in en if CJK.search(step["hint"])])

    def test_score_mode_labels_translated(self):
        en = api.score_mode_labels("en")
        self.assertFalse([label for label in en.values() if CJK.search(label)])

    def test_wizard_steps_constant_stays_chinese(self):
        """`WIZARD_STEPS` 是中文原文（`STEP_INDEX` 靠它），不能被就地翻译。"""
        self.assertEqual(api.WIZARD_STEPS[0]["title"], "职业")

    def test_draft_problems_english(self):
        """把每一条校验都踩一遍，英文字面量里不该剩中文。"""
        rule_text.MISSING.clear()
        draft = api.empty_draft()
        problems = api.draft_problems(self.bundle, draft, "en")
        self.assertTrue(problems)
        self.assertFalse([item["text"] for item in problems if CJK.search(item["text"])])

        draft.update({"class_id": FIGHTER, "class_level": 5,
                      "scores": dict(SCORES), "score_mode": "point_buy",
                      "skills": ["athletics"], "masteries": [],
                      "background_bonus": {"str": 2, "con": 2}})
        texts = [item["text"] for item in api.draft_problems(self.bundle, draft, "en")]
        self.assertTrue(texts)
        self.assertFalse([text for text in texts if CJK.search(text)],
                         "英文界面上这些校验还是中文：%r" % (texts,))

    def test_rule_messages_english(self):
        """规则层那几条（属性范围 / 背景加值 / 法术选点）也要能翻。"""
        from dnd5r.rules.abilities import background_bonus, score_range_ok
        from dnd5r.rules.spellcasting import check_spell_picks

        texts = score_range_ok({"str": 99}, "en")
        self.assertTrue(texts)
        self.assertFalse([text for text in texts if CJK.search(text)])

        with self.assertRaises(Exception) as caught:
            background_bonus(("str", "dex", "con"), {"str": 2, "dex": 2}, "en")
        self.assertFalse(CJK.search(str(caught.exception)))

        picks = check_spell_picks(self.bundle, {}, {"nope": ["x"]}, None, "en")
        self.assertTrue(picks)
        self.assertFalse([text for text in picks if CJK.search(text)])

    def test_no_missing_after_exercise(self):
        """接口层译文表不缺 —— 上面几条跑过之后 MISSING 必须是空的。"""
        rule_text.MISSING.clear()
        api.wizard_steps("en")
        api.score_mode_labels("en")
        api.draft_problems(self.bundle, api.empty_draft(), "en")
        self.assertEqual(sorted(rule_text.MISSING), [])


if __name__ == "__main__":
    unittest.main()
