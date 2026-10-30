# -*- coding: utf-8 -*-
"""桌面外壳：一个窗口、一个角色、若干页面。

前端只用 `dnd5r.api`（约束 C3）：这里没有一处规则计算，全部数字来自
`api.character_sheet()`。所以「界面上显示的值」与「CLI / 测试算出的值」
不可能不一致 —— 它们是同一个函数。

零弹窗铁律：`selftest=True` 时窗口 **只 withdraw，永不 deiconify**。
探针要尺寸就用 reqsize，不靠把窗口亮出来量。

骨架对齐旧程序：hero 条（身份 / HP / 数值胶囊）+ 左属性卡 + 中标签页 + 右状态。
以前新界面只有一个三行文字的 header，于是「人物卡」看起来像一张表单。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import dnd5r.api as api

from . import theme
from .cards import Chip
from .pages import OverviewPage
from .pages_encounter import EncounterPage
from .pages_feats import FeatPage
from .pages_powers import PowersPage
from .pages_spells import SpellPage
from .widgets import COL_MID, hit_dice_text, hint_bar

# 设计尺寸：与旧程序一致，左 320 属性卡 + 中 610 标签页 + 右 300 状态正好放下。
WINDOW_SIZE = (1340, 860)
# **布局保证能塞下的最小窗口**：uicheck 与 test_desktop 都按它算预算。
WINDOW_MIN = (1180, 820)
# 真正的硬下限（小屏才用得上）。低于 WINDOW_MIN 时页面会被裁，这是已知限制。
WINDOW_FLOOR = (1024, 600)


class DesktopApp(tk.Tk):
    def __init__(self, bundle, actor, *, locale: str = "zh", selftest: bool = False) -> None:
        super().__init__()
        self.bundle = bundle
        self.actor = actor
        self.locale = locale
        self.selftest = selftest
        self.sheet: dict = {}
        # 遭遇战是 app 级状态（P15）：战斗页创建/销毁它，能力页（授予目标）
        # 与法术页（召唤入場）都要读同一份 —— 挂在页私有属性上别的页够不着。
        self.encounter = None

        self.title("冒险者手帖 · 5R 角色卡")
        # 主题必须在建控件**之前**套上：ttk 样式是「建的时候就查」的，
        # 先建再改样式，已经建好的控件有一部分不会跟着变（Text/Listbox 更不会）。
        theme.apply_theme(self)
        self.minsize(*WINDOW_FLOOR)
        if selftest:
            self.withdraw()          # 永不 deiconify：探针不许抢焦点
        else:
            self._fit()

        self._build()
        self.refresh()

    # --- 窗口尺寸 ---------------------------------------------------------
    def _fit(self) -> None:
        """按屏幕收缩：设计尺寸 → 屏宽-40 / 屏高-100 → 不低于硬下限。"""
        try:
            screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        except tk.TclError:                  # 无显示环境（极少），用设计尺寸
            screen_w, screen_h = WINDOW_SIZE
        width = min(WINDOW_SIZE[0], max(WINDOW_FLOOR[0], screen_w - 40))
        height = min(WINDOW_SIZE[1], max(WINDOW_FLOOR[1], screen_h - 100))
        self.geometry("%dx%d" % (width, height))

    # --- 骨架 -------------------------------------------------------------
    def _build(self) -> None:
        # 顺序有讲究：状态栏先占底部，再给会伸展的笔记本，否则窄屏时整条被裁掉
        self.status = hint_bar(self)
        self.status.pack(side="bottom", fill="x", padx=8, pady=(2, 6))

        self.hero = self._build_hero()
        self.hero.pack(side="top", fill="x", padx=8, pady=(6, 2))

        self.book = ttk.Notebook(self)
        self.book.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))

        self.overview = OverviewPage(self.book)
        self.book.add(self.overview, text="概览")
        self.spells = SpellPage(self.book, self)
        self.book.add(self.spells, text="法术")
        self.feats = FeatPage(self.book, self)
        self.book.add(self.feats, text="专长")
        self.powers_page = PowersPage(self.book, self)
        self.book.add(self.powers_page, text="能力")
        self.encounter_page = EncounterPage(self.book, self)
        self.book.add(self.encounter_page, text="战斗")
        self.pages = [self.overview, self.spells, self.feats, self.powers_page,
                      self.encounter_page]

    def _build_hero(self) -> ttk.Frame:
        """身份 + 生命值 + 5 个数值胶囊。

        `name_var` / `sub_var` / `state_var` 三个变量名保留 —— 测试直接摸它们。
        """
        hero = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        # 左：身份
        ident = ttk.Frame(hero, style="Panel.TFrame")
        ident.pack(side="left", anchor="n")
        self.name_var = tk.StringVar()
        ttk.Label(ident, textvariable=self.name_var, style="Panel.TLabel",
                  font=(theme.UI_FONT, 17, "bold"),
                  foreground=theme.GOLD2).pack(anchor="w")
        self.sub_var = tk.StringVar()
        ttk.Label(ident, textvariable=self.sub_var, style="DimPanel.TLabel",
                  wraplength=360, justify="left").pack(anchor="w")
        self.state_var = tk.StringVar()
        ttk.Label(ident, textvariable=self.state_var, style="DimPanel.TLabel",
                  foreground=theme.WARN).pack(anchor="w", pady=(2, 0))

        # 中：生命值。数字用大号且按比例变色，进度条只做辅助。
        hp_box = ttk.Frame(hero, style="Panel.TFrame")
        hp_box.pack(side="left", anchor="n", padx=(28, 0))
        hp_head = ttk.Frame(hp_box, style="Panel.TFrame")
        hp_head.pack(anchor="w")
        ttk.Label(hp_head, text="❤ 生命值", style="DimPanel.TLabel").pack(side="left")
        self.hp_var = tk.StringVar()
        self.hp_value = ttk.Label(hp_head, textvariable=self.hp_var, style="Panel.TLabel",
                                  font=(theme.UI_FONT, 20, "bold"))
        self.hp_value.pack(side="left", padx=(8, 0))
        self.hp_bar = ttk.Progressbar(hp_box, style="HP.Horizontal.TProgressbar",
                                      length=235, maximum=100, value=0)
        self.hp_bar.pack(anchor="w", pady=(3, 0))
        self.hp_detail = ttk.Label(hp_box, text="", style="DimPanel.TLabel")
        self.hp_detail.pack(anchor="w")

        # 右：5 个数值胶囊（AC / 先攻 / 速度 / 熟练 / 察觉）
        chips = ttk.Frame(hero, style="Panel.TFrame")
        chips.pack(side="right", anchor="n")
        self.chips: dict[str, Chip] = {}
        for key, title in (("ac", "护甲 AC"), ("initiative", "先攻"),
                           ("speed", "速度"), ("prof", "熟练"), ("perception", "察觉")):
            chip = Chip(chips, title)
            chip.pack(side="left", padx=(6, 0))
            self.chips[key] = chip
        return hero

    # --- 刷新 -------------------------------------------------------------
    def refresh(self) -> None:
        """整个界面按最新的 sheet 重画。改完数据就调它，别做局部补丁。"""
        self.sheet = api.character_sheet(self.actor, self.bundle, self.locale)
        for page in self.pages:
            page.refresh(self.sheet)
        self._refresh_header()

    def apply_actor(self, actor) -> None:
        """换掉角色并重画。改档案（专长选择项）后必须整只换 —— 派生值全变了。"""
        self.actor = actor
        self.refresh()

    def _refresh_header(self) -> None:
        sheet = self.sheet
        self.name_var.set(sheet.get("name", ""))
        classes = "、".join("%s %d" % (row["name"], row["class_level"])
                            for row in sheet.get("classes", []))
        subs = "、".join(row["name"] for row in sheet.get("subclasses", []) if row.get("unlocked"))
        total = sheet.get("total_level", 0)
        self.sub_var.set(" · ".join(item for item in
                                    [classes, subs, "总等级 %d" % total] if item))
        marks = []
        if sheet.get("morphed"):
            marks.append("变形中")
        if sheet.get("conditions"):
            marks.append("状态：" + "、".join(sheet["conditions"]))
        self.state_var.set("  ".join(marks))
        self._refresh_hp(sheet)
        self._refresh_chips(sheet)
        self.status.configure(
            text="内容：%d 职业 / %d 子职 / %d 法术 / %d 专长 · 错误 %d"
                 % (len(self.bundle.classes), len(self.bundle.subclasses),
                    len(self.bundle.spells), len(self.bundle.feats),
                    len(self.bundle.errors)))

    def _refresh_hp(self, sheet: dict) -> None:
        hp = sheet.get("hp", {})
        current, maximum = int(hp.get("current", 0)), int(hp.get("maximum", 0))
        self.hp_var.set("%d / %d" % (current, maximum))
        self.hp_value.configure(foreground=theme.hp_color(current, maximum))
        self.hp_bar.configure(maximum=max(1, maximum), value=current)
        extras = []
        if hp.get("temp"):
            extras.append("临时 %d" % hp["temp"])
        dice = hit_dice_text(hp.get("hit_dice"), sheet.get("classes"))
        if dice:
            extras.append("生命骰 " + dice)
        self.hp_detail.configure(text=" · ".join(extras))

    def _refresh_chips(self, sheet: dict) -> None:
        perception = next((row["total"] for row in sheet.get("skills", ())
                           if row.get("key") == "perception"), None)
        self.chips["ac"].set_value(str(sheet.get("ac", {}).get("total", "—")))
        self.chips["initiative"].set_value(
            "%+d" % sheet.get("initiative", {}).get("total", 0))
        self.chips["speed"].set_value("%d" % sheet.get("speed", {}).get("walk", 0))
        self.chips["prof"].set_value("%+d" % sheet.get("proficiency_bonus", 0))
        self.chips["perception"].set_value(
            "%+d" % perception if perception is not None else "—")

    # --- 给探针用 ---------------------------------------------------------
    def page_size(self, page: ttk.Frame) -> tuple[int, int]:
        """页面自身需要的尺寸（不依赖窗口是否可见）。"""
        return page.winfo_reqwidth(), page.winfo_reqheight()

    def chrome_height(self) -> int:
        """窗口中**不归页面用**的那部分高度：状态栏 + hero + 标签条 + 外边距。

        **现量，不许写死。** 这里原来在测试里被写死成 40（"header + 标签条"），
        一旦顶栏长高（比如加一条 hero），那个 40 就假了 —— 会出现
        「报 LAYOUT OK 但实际已经超预算」这种最难查的错。实测 old header 时是 99。
        """
        self.update_idletasks()
        tallest = max(self.page_size(page)[1] for page in self.pages)
        return self.winfo_reqheight() - tallest

    def hero_height(self) -> int:
        """hero 条占的高度（预算里最该盯住的一块）。"""
        self.update_idletasks()
        return self.hero.winfo_reqheight()

    def layout_report(self) -> dict:
        """布局审计用的纯数据：每页 reqsize + 中栏预算。

        `update_idletasks()` 只做几何计算，**不映射窗口**（此时窗口是 withdrawn）。
        """
        self.update_idletasks()
        return {
            "window": WINDOW_SIZE,
            "window_min": WINDOW_MIN,
            "chrome": self.chrome_height(),
            "hero": self.hero_height(),
            "mid_budget": COL_MID,
            "pages": [{"name": str(page), "req": self.page_size(page)}
                      for page in self.pages],
        }
