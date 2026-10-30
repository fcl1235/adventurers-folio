# -*- coding: utf-8 -*-
"""P6c 验收：桌面前端接到 api 上，且不抢焦点。

三条硬要求：
  1. 界面上的数字与 `character_sheet()` 完全一致（前端不算第二遍）
  2. `refresh()` 之后显示跟着变（不允许缓存派生值）
  3. `selftest=True` 时窗口始终 withdrawn —— 探针不许把窗口弹到前台
"""

import tempfile
import unittest
from pathlib import Path

import dnd5r.api as api
from apps.desktop import theme
from apps.desktop.app import WINDOW_MIN, DesktopApp
from dnd5r.kernel.rng import ScriptedRng

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
FIGHTER = "dnd2024.class.fighter"
ROGUE = "dnd2024.class.rogue"
DRUID = "dnd2024.class.druid"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
DEX_SCORES = {"str": 10, "dex": 17, "con": 14, "int": 12, "wis": 12, "cha": 10}
WIS_SCORES = {"str": 10, "dex": 14, "con": 14, "int": 12, "wis": 17, "cha": 10}


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
        """每页的 reqsize 都要塞得进「窗口高 − 现量的 chrome」。

        chrome 以前写死 40，实测是 99：那条断言实际上多给了 59px 余量，
        属于「绿着但可能已经超了」。现在两边（这里与 uicheck）都走 chrome_height()。
        """
        app = self._app()
        report = app.layout_report()
        avail_w = WINDOW_MIN[0] - 16
        avail_h = WINDOW_MIN[1] - app.chrome_height()
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


class AppearanceTest(unittest.TestCase):
    """「明确标识各项数值」这件事，也要能被断言卡住，不能靠肉眼验收。

    这一组盯三件东西：暗色主题真的套上了、六张属性卡在且数字对、
    原生控件没有遗留浅底色。任何一条破了，界面就会退回「一张表单」。
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _app(self, class_id=FIGHTER, level=5, **kwargs):
        actor = api.new_character(self.bundle, class_id, level, SCORES, **kwargs)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app

    def test_root_is_dark(self):
        app = self._app()
        self.assertEqual(str(app.cget("bg")), theme.BG)

    def test_ability_cards_match_sheet(self):
        """六张属性卡：调整值、分数、豁免都要与 sheet 一致。"""
        app = self._app()
        cards = app.overview.ability_cards
        self.assertEqual(len(cards), 6)
        for key, card in cards.items():
            row = app.sheet["abilities"][key]
            save = app.sheet["saves"][key]
            self.assertEqual(card.mod_text(), "%+d" % row["mod"], key)
            self.assertEqual(card.score_text(), "数值 %d" % row["score"], key)
            self.assertEqual(card.save_text(), "豁免 %+d" % save["total"], key)
            self.assertEqual(card.save_proficient(), bool(save["proficient"]), key)

    def test_chips_match_sheet(self):
        app = self._app()
        perception = next(row["total"] for row in app.sheet["skills"]
                          if row["key"] == "perception")
        self.assertEqual(app.chips["ac"].value(), str(app.sheet["ac"]["total"]))
        self.assertEqual(app.chips["initiative"].value(),
                         "%+d" % app.sheet["initiative"]["total"])
        self.assertEqual(app.chips["speed"].value(),
                         "%d" % app.sheet["speed"]["walk"])
        self.assertEqual(app.chips["prof"].value(),
                         "%+d" % app.sheet["proficiency_bonus"])
        self.assertEqual(app.chips["perception"].value(), "%+d" % perception)

    def test_hp_color_follows_ratio(self):
        app = self._app()
        self.assertEqual(str(app.hp_value.cget("foreground")), theme.OK)
        app.actor.hp.current = 1
        app.refresh()
        self.assertEqual(str(app.hp_value.cget("foreground")), theme.WARN)

    def test_no_light_backgrounds_left(self):
        """ttk 样式管不到 tk 原生控件：它们必须自己配底色。"""
        app = self._app()
        dark = {value.lower() for value in
                (theme.BG, theme.PANEL, theme.CARD, theme.CARD2, theme.TXT_BG,
                 theme.MAP_BG)}
        for widget in _walk(app):
            if widget.winfo_class() not in ("Canvas", "Text", "Listbox"):
                continue
            background = str(widget.cget("background")).lower()
            self.assertIn(background, dark,
                          "%s 还是浅底色 %s" % (widget.winfo_class(), background))

    def test_hit_dice_is_readable(self):
        """生命骰是一组池，直接把列表塞进 Label 会打出 `[{'id': ...}]`。"""
        app = self._app()
        text = app.overview.fight.value_at(8)
        self.assertNotIn("{", text)
        self.assertIn("战士", text)


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


class DiceTest(unittest.TestCase):
    """掷骰：结果必须来自引擎，记录要落地，失败不许炸到 Tk 回调里。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _app(self):
        actor = api.new_character(self.bundle, ROGUE, 5, DEX_SCORES)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app

    def test_roll_matches_sheet_modifier(self):
        app = self._app()
        skill = next(row for row in app.sheet["skills"] if row["key"] == "stealth")
        result = app.roll_check("skill", "stealth", rng=ScriptedRng([13]))
        self.assertIsNotNone(result)
        self.assertEqual(result["total"], 13 + skill["total"])
        self.assertEqual(app.overview.dice_log.row_count, 1)
        self.assertIn("隐匿", app.overview.dice_log.lines()[0])

    def test_labels_are_chinese(self):
        """`label` 对豁免是内部 token（save.dex），直接显示会中英混杂。"""
        app = self._app()
        app.roll_check("save", "dex", rng=ScriptedRng([10]))
        app.roll_check("ability", "str", rng=ScriptedRng([10]))
        lines = app.overview.dice_log.lines()
        self.assertNotIn("save.", lines[0])
        self.assertIn("敏捷豁免", lines[1])
        self.assertIn("力量检定", lines[0])

    def test_log_newest_first_and_capped(self):
        app = self._app()
        for _ in range(70):
            app.roll_check("ability", "con", rng=ScriptedRng([5]))
        self.assertEqual(app.overview.dice_log.row_count, 60)

    def test_failure_reports_without_raising(self):
        app = self._app()
        self.assertIsNone(app.roll_check("nope", "x"))
        self.assertIn("掷骰失败", str(app.status.cget("text")))
        self.assertEqual(app.overview.dice_log.row_count, 0)

    def test_ability_card_buttons_are_wired(self):
        app = self._app()
        card = app.overview.ability_cards["str"]
        self.assertEqual(str(card.check_button.cget("state")), "normal")
        card.check_button.invoke()
        self.assertEqual(app.overview.dice_log.row_count, 1)


class SaveLoadTest(unittest.TestCase):
    """存读档：写到临时目录，不碰用户文件；selftest 下对话框必须短路。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _app(self, tmpdir):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        app = DesktopApp(self.bundle, actor, selftest=True, save_dir=tmpdir)
        self.addCleanup(app.destroy)
        return app

    def test_save_writes_and_load_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.actor.hp.current = 21          # 事实挂在 HpPool 上，不是 actor.hp_current
            app.refresh()
            self.assertEqual(app.sheet["hp"]["current"], 21, "refresh 后界面与事实要一致")
            path = app.save_to(Path(tmp) / "sub" / "hero.json")
            self.assertIsNotNone(path)
            self.assertTrue(Path(path).is_file(), "存档目录不存在时也要自动建")
            self.assertEqual(app.current_path, Path(path))

            # 换一个角色再读回来，确认是覆盖而不是「碰巧一样」
            fresh = self._app(tmp)
            self.assertNotEqual(fresh.sheet["name"], "")
            self.assertTrue(fresh.load_from(path))
            self.assertEqual(fresh.sheet["hp"]["current"], 21)
            self.assertEqual(fresh.current_path, Path(path))

    def test_remember_last_path(self):
        """`_last.json` 记不住不影响存盘，但记得住才有「继续上次」的余地。"""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.save_to(Path(tmp) / "a.json")
            remember = Path(tmp) / "_last.json"
            self.assertTrue(remember.is_file())
            self.assertIn("a.json", remember.read_text(encoding="utf-8"))

    def test_new_character_resets_to_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            app.save_to(Path(tmp) / "a.json")
            app.new_character()
            self.assertIsNone(app.current_path, "新建之后不该还认着旧文件")
            self.assertEqual(app.overview.dice_log.row_count, 0)

    def test_load_clears_dice_log(self):
        """换人之后上一个人的掷骰记录留着只会误导。"""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            path = app.save_to(Path(tmp) / "a.json")
            app.roll_check("ability", "str", rng=ScriptedRng([10]))
            self.assertEqual(app.overview.dice_log.row_count, 1)
            app.load_from(path)
            self.assertEqual(app.overview.dice_log.row_count, 0)

    def test_bad_file_reports_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            broken = Path(tmp) / "broken.json"
            broken.write_text("{ not json", encoding="utf-8")
            self.assertFalse(app.load_from(broken))
            self.assertIn("读档失败", str(app.status.cget("text")))
            self.assertFalse(app.load_from(Path(tmp) / "不存在.json"))

    def test_dialogs_short_circuit_in_selftest(self):
        """文件对话框会挂住探针：selftest 下必须直接返回。"""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            self.assertIsNone(app.save_dialog())
            self.assertFalse(app.open_dialog())
            self.assertEqual(list(Path(tmp).glob("*.json")), [],
                             "短路还不许顺手写出文件")


class EditRowTest(unittest.TestCase):
    """属性就地编辑：改的是原始属性，改完 HP 上限要跟着变、输入行要收起。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _app(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app

    def test_starts_collapsed_and_opens_with_base_scores(self):
        app = self._app()
        page = app.overview
        self.assertEqual(page.edit_row.winfo_manager(), "", "默认要收起")
        page.toggle_edit()
        self.assertEqual(page.edit_row.winfo_manager(), "pack")
        shown = {key: var.get() for key, var in page.score_vars.items()}
        self.assertEqual(shown, page.base_scores,
                         "输入框初值必须是原始属性，不是卡面分数")
        page.toggle_edit(False)
        self.assertEqual(page.edit_row.winfo_manager(), "")

    def test_apply_rebuilds_and_collapses(self):
        app = self._app()
        page = app.overview
        before = app.sheet["hp"]["maximum"]
        page.toggle_edit()
        page.score_vars["con"].set(16)
        page._apply_scores()
        self.assertEqual(app.sheet["hp"]["maximum"], before + 5)
        self.assertEqual(page.edit_row.winfo_manager(), "", "成功之后要收起")
        self.assertEqual(app.sheet["base_scores"]["con"], 16)

    def test_refused_value_shows_reason_and_keeps_row(self):
        app = self._app()
        page = app.overview
        page.toggle_edit()
        page.score_vars["str"].set(99)
        page._apply_scores()
        self.assertIn("99", str(page._build_error.cget("text")))
        self.assertEqual(page.edit_row.winfo_manager(), "pack", "被拒时不能收起")
        self.assertNotEqual(app.sheet["base_scores"]["str"], 99)

    def test_reopen_shows_new_values(self):
        app = self._app()
        page = app.overview
        page.toggle_edit()
        page.score_vars["str"].set(18)
        page._apply_scores()
        page.toggle_edit()
        self.assertEqual(page.score_vars["str"].get(), 18,
                         "重新展开时要显示新值，不能停在旧值上")


class MorphUiTest(unittest.TestCase):
    """变形：形态选择行要出现，用完能「结束变形」。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _app(self):
        actor = api.new_character(self.bundle, DRUID, 8, WIS_SCORES)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app

    def test_form_row_appears_for_wild_shape(self):
        app = self._app()
        page = app.powers_page
        row = next(item for item in page._powers if item["id"].endswith("wild_shape"))
        page.powers.select_id(row["id"])
        page._power_id = row["id"]
        page._fill_detail()
        self.assertEqual(page._choice_kind, "form_id")
        self.assertTrue(page._choice_map, "形态下拉里必须有可选形态")

    def test_use_morphs_and_unmorph_button_shows(self):
        app = self._app()
        page = app.powers_page
        self.assertEqual(page.unmorph_button.winfo_manager(), "",
                         "没变形时不该有「结束变形」")
        row = next(item for item in page._powers if item["id"].endswith("wild_shape"))
        page.powers.select_id(row["id"])
        page._power_id = row["id"]
        page._fill_detail()
        self.assertTrue(page.use_selected())
        self.assertTrue(app.sheet["morphed"])
        self.assertEqual(page.unmorph_button.winfo_manager(), "pack")

        self.assertTrue(page.end_morph())
        self.assertFalse(app.sheet["morphed"])
        self.assertEqual(page.unmorph_button.winfo_manager(), "")


class StatePanelTest(unittest.TestCase):
    """状态面板：勾选写事实、力竭写数值、濒死记账、专注给 DC。

    这一组盯的是「面板有没有把话说清」：力竭是真扣了的，状态是只记的 ——
    弄反了就是撒谎型 UI，比不显示更糟。
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _app(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app

    def _labels(self, widget) -> str:
        texts = []
        for node in _walk(widget):
            try:
                texts.append(str(node.cget("text")))
            except Exception:
                continue
        return " ".join(texts)

    def test_honesty_texts_are_on_screen(self):
        """状态=只记录，力竭=已计入。两句话必须在界面上，不能只写在注释里。"""
        app = self._app()
        panel = app.overview.state_panel
        text = self._labels(panel)
        self.assertIn("未计入数值", text)
        self.assertIn("已计入", text)

    def test_condition_checkbox_writes_fact(self):
        app = self._app()
        panel = app.overview.state_panel
        panel.condition_vars["prone"].set(True)
        panel._apply_condition("prone")
        self.assertIn("prone", app.sheet["conditions"])
        self.assertTrue(panel.condition_vars["prone"].get(), "刷新后勾选状态要跟着事实")
        panel.condition_vars["prone"].set(False)
        panel._apply_condition("prone")
        self.assertNotIn("prone", app.sheet["conditions"])

    def test_exhaustion_changes_numbers_and_row(self):
        app = self._app()
        app.on_state_action("exhaustion", 2)
        self.assertEqual(app.sheet["exhaustion"]["level"], 2)
        self.assertEqual(app.overview.state_panel.exhaustion_var.get(), 2)
        self.assertIn("-4", app.overview.fight.value_at(10))
        self.assertIn("力竭", app.overview.fight.label_at(10))

    def test_death_save_disabled_while_alive(self):
        app = self._app()
        self.assertEqual(str(app.overview.state_panel.death_button.cget("state")),
                         "disabled")
        app.actor.hp.current = 0
        app.refresh()
        self.assertEqual(str(app.overview.state_panel.death_button.cget("state")),
                         "normal")

    def test_death_save_roll_is_logged(self):
        app = self._app()
        app.actor.hp.current = 0
        app.refresh()
        result = app.on_state_action("death_save", rng=ScriptedRng([1]))
        self.assertEqual(result["outcome"], "ongoing")
        self.assertEqual(result["failed"], 2)
        self.assertIn("死亡豁免", app.overview.dice_log.lines()[0])
        self.assertEqual(app.overview.state_panel.success_var.get(), "○○○")
        self.assertEqual(app.overview.state_panel.failed_var.get(), "●●○")

    def test_concentration_rolls_con_save(self):
        app = self._app()
        con = app.sheet["saves"]["con"]["total"]
        app.on_state_action("concentration", 24, rng=ScriptedRng([15]))
        dc = 12                                  # max(10, 24 // 2)
        self.assertIn("DC %d" % dc, app.overview.state_panel.dc_var.get())
        expected = "成功" if 15 + con >= dc else "失败"
        self.assertIn(expected, app.overview.state_panel.dc_var.get())
        self.assertIn("专注", app.overview.dice_log.lines()[0])


if __name__ == "__main__":
    unittest.main()
