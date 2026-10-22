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
        self.assertEqual(app.overview.fight._values[1].get(),
                         "%+d" % sheet["initiative"]["total"])
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
ASI = "dnd2024.feat.ability_score_improvement"
ALERT = "dnd2024.feat.alert"
SKILL_EXPERT = "dnd2024.feat.skill_expert"


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


class FeatPageTest(unittest.TestCase):
    """P6f 验收：专长的选择项能选、能撤，而且「没算进数值」要说出来。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _page(self, feats, class_id=FIGHTER, level=8, scores=SCORES):
        actor = api.new_character(self.bundle, class_id, level, scores, feats=feats)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app, app.feats

    def _open(self, page, feat_id):
        page.feats.select_id(feat_id)
        page._feat_id = feat_id
        page._choice_id = ""
        page._fill_detail()

    def test_lists_feats_with_pending_mark(self):
        _, page = self._page([ASI])
        self.assertEqual(page.feats.row_count, 1)
        self.assertIn("属性值提升", page.feats.text_at(0))
        self.assertIn("待选", page.feats.text_at(0))

    def test_add_pick_updates_character(self):
        """属性提升是「两项各 +1」：选两次才 +2，选一次只是待办。"""
        app, page = self._page([ASI])
        page.options.select_id("str")
        self.assertTrue(page.add_pick(), page.status_var.get())
        self.assertEqual(app.actor.top().statblock.abilities.score("str"), 16)
        self.assertTrue(page.add_pick(), page.status_var.get())
        self.assertEqual(app.actor.top().statblock.abilities.score("str"), 18)
        self.assertEqual(app.sheet["feats"][0]["choices"][0]["picked"], ["str", "str"])

    def test_con_boost_raises_hp(self):
        app, page = self._page([ASI])
        page.options.select_id("con")
        page.add_pick()
        page.options.select_id("con")
        before = app.actor.hp.maximum
        self.assertTrue(page.add_pick(), page.status_var.get())
        self.assertGreater(app.actor.hp.maximum, before)
        self.assertEqual(app.sheet["hp"]["maximum"], app.actor.hp.maximum)

    def test_overflow_refused_and_state_kept(self):
        app, page = self._page([ASI])
        for _ in range(2):
            page.options.select_id("str")
            page.add_pick()
        page.options.select_id("dex")
        self.assertFalse(page.add_pick(), "超过 2 项还写进去了")
        self.assertIn("最多选", page.status_var.get())
        self.assertEqual(app.sheet["feats"][0]["choices"][0]["picked"], ["str", "str"])

    def test_remove_and_clear(self):
        app, page = self._page([ASI])
        page.options.select_id("str")
        page.add_pick()
        page.add_pick()
        page.options.select_id("str")
        self.assertTrue(page.remove_pick(), page.status_var.get())
        self.assertEqual(page._choice()["picked"], ["str"])
        self.assertTrue(page.clear_picks(), page.status_var.get())
        self.assertEqual(page._choice()["picked"], [])

    def test_repeat_value_removed_one_at_a_time(self):
        """属性提升要能「力量、力量」：去掉一个不能把两个都删掉。"""
        _, page = self._page([ASI])
        page.options.select_id("str")
        page.add_pick()
        page.add_pick()
        page.options.select_id("str")
        page.remove_pick()
        self.assertEqual(page._choice()["picked"], ["str"])

    def test_honesty_says_text_only_feat_is_not_counted(self):
        """警觉（Alert）在本程序里只有规则文字 —— 界面必须说出来。"""
        _, page = self._page([ALERT])
        self._open(page, ALERT)
        text = page.honesty.text.get("1.0", "end")
        self.assertIn("未计入数值", text)
        self.assertIn("□", page.feats.text_at(0))

    def test_honesty_says_counted_feat_is_counted(self):
        _, page = self._page([ASI])
        self.assertIn("已计入数值", page.honesty.text.get("1.0", "end"))

    def test_feat_without_choices_disables_buttons(self):
        _, page = self._page([ALERT])
        self._open(page, ALERT)
        for button in (page.add_button, page.remove_button, page.clear_button):
            self.assertEqual(str(button.cget("state")), "disabled")

    def test_choice_switch_keeps_each_choice_separate(self):
        """技艺专家有三个选择项（技能/专精/属性）：切到另一个不能互相覆盖。"""
        app, page = self._page([SKILL_EXPERT])
        ids = [row["id"] for row in page._feat()["choices"]]
        self.assertGreater(len(ids), 1)
        page._choice_id = "skill"
        page._fill_options()
        page.options.select_id("stealth")
        self.assertTrue(page.add_pick(), page.status_var.get())
        for choice_id in ids:
            page._choice_id = choice_id
            page._fill_options()
            picked = page._choice()["picked"]
            if choice_id == "skill":
                self.assertEqual(picked, ["stealth"])
            else:
                self.assertEqual(picked, [], "别的选择项被写脏了")
        self.assertIn("skill.stealth", app.actor.profile.proficiencies)


class PowersPageTest(unittest.TestCase):
    """P6g 验收：资源池、能力清单、防御信息，以及「使用」真的改了角色。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _page(self, class_id=FIGHTER, level=5, scores=SCORES):
        actor = api.new_character(self.bundle, class_id, level, scores)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app, app.powers_page

    def _open(self, page, power_id):
        page.powers.select_id(power_id)
        page._power_id = power_id
        page._fill_detail()

    def test_pools_match_sheet(self):
        app, page = self._page()
        pools = app.sheet["pools"]
        self.assertGreater(len(pools), 0, "战士 5 级应该有资源池")
        for index, pool in enumerate(pools):
            self.assertEqual(page.pools.label_at(index), pool["label"])
            self.assertEqual(page.pools.value_at(index),
                             "%d / %d" % (pool["left"], pool["max"]))

    def test_defense_block_matches_sheet(self):
        app, page = self._page()
        sheet = app.sheet
        self.assertEqual(page.defense.value_at(0), str(sheet["ac"]["total"]))
        self.assertEqual(page.defense.value_at(1), "≥ %d" % sheet["crit"]["min"])
        # 没有抗性/感官时要显式写「—」，不能留空让玩家以为漏了
        self.assertEqual(page.defense.value_at(3), "—")

    def test_power_list_marked(self):
        _, page = self._page()
        self.assertEqual(page.powers.row_count, len(page._powers))
        text = page.powers.text_at(page.powers.index_of("dnd2024.class.fighter.second_wind"))
        self.assertIn("回气", text)
        self.assertIn("▶", text, "主动能力应标成「使用时结算」")

    def test_using_a_power_changes_character(self):
        app, page = self._page()
        app.actor.hp.current = 10
        pool_id = "dnd2024.resource.fighter.second_wind"
        before = app.actor.resources.pools[pool_id].available
        self._open(page, "dnd2024.class.fighter.second_wind")
        self.assertTrue(page.use_selected(), page.status_var.get())
        self.assertEqual(app.actor.resources.pools[pool_id].available, before - 1)
        self.assertGreater(app.actor.hp.current, 10, "回气没回血")
        self.assertTrue(page.report.text.get("1.0", "end").strip(), "没有使用报告")

    def test_spent_out_power_becomes_blocked(self):
        """次数用完必须变灰并写明原因 —— 让玩家点了才知道不行是最差的体验。"""
        _, page = self._page(level=9)
        pool_id = "dnd2024.resource.fighter.second_wind"
        total = page.app.actor.resources.pools[pool_id].available
        self._open(page, "dnd2024.class.fighter.second_wind")
        for _ in range(total):
            self.assertTrue(page.use_selected(), page.status_var.get())
        self._open(page, "dnd2024.class.fighter.second_wind")
        self.assertEqual(str(page.use_button.cget("state")), "disabled")
        self.assertTrue(page.blocked_var.get(), "用完了却没写原因")

    def test_passive_power_is_not_usable(self):
        _, page = self._page()
        self._open(page, "dnd2024.class.fighter.extra_attack")
        self.assertEqual(str(page.use_button.cget("state")), "disabled")
        self.assertFalse(page.use_selected(), "被动能力不该能「使用」")
        self.assertIn("被动", page.status_var.get())


if __name__ == "__main__":
    unittest.main()
