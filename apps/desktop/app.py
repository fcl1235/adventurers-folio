# -*- coding: utf-8 -*-
"""桌面外壳：一个窗口、一个角色、四个页面。

前端只用 `dnd5r.api`（约束 C3）：这里没有一处规则计算，全部数字来自
`api.character_sheet()`。所以「界面上显示的值」与「CLI / 测试算出的值」
不可能不一致 —— 它们是同一个函数。

零弹窗铁律：`selftest=True` 时窗口 **只 withdraw，永不 deiconify**。
探针要尺寸就用 reqsize，不靠把窗口亮出来量。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import dnd5r.api as api

from .pages import OverviewPage
from .pages_encounter import EncounterPage
from .pages_feats import FeatPage
from .pages_powers import PowersPage
from .pages_spells import SpellPage
from .widgets import COL_MID, hint_bar

WINDOW_MIN = (1180, 720)


class DesktopApp(tk.Tk):
    def __init__(self, bundle, actor, *, locale: str = "zh", selftest: bool = False) -> None:
        super().__init__()
        self.bundle = bundle
        self.actor = actor
        self.locale = locale
        self.selftest = selftest
        self.sheet: dict = {}

        self.title("D&D 2024 角色卡")
        self.minsize(*WINDOW_MIN)
        if not selftest:
            self.geometry("%dx%d" % WINDOW_MIN)
        else:
            self.withdraw()          # 永不 deiconify：探针不许抢焦点

        self._build()
        self.refresh()

    # --- 骨架 -------------------------------------------------------------
    def _build(self) -> None:
        # 顺序有讲究：状态栏先占底部，再给会伸展的笔记本，否则窄屏时整条被裁掉
        self.status = hint_bar(self)
        self.status.pack(side="bottom", fill="x", padx=8, pady=(2, 6))

        header = ttk.Frame(self, padding=(10, 6, 10, 2))
        header.pack(side="top", fill="x")
        self.name_var = tk.StringVar()
        ttk.Label(header, textvariable=self.name_var,
                  font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        self.sub_var = tk.StringVar()
        ttk.Label(header, textvariable=self.sub_var,
                  foreground="#555555").pack(side="left", padx=(12, 0))
        self.state_var = tk.StringVar()
        ttk.Label(header, textvariable=self.state_var,
                  foreground="#a33").pack(side="right")

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
        self.status.configure(
            text="内容：%d 职业 / %d 子职 / %d 法术 / %d 专长 · 错误 %d"
                 % (len(self.bundle.classes), len(self.bundle.subclasses),
                    len(self.bundle.spells), len(self.bundle.feats),
                    len(self.bundle.errors)))

    # --- 给探针用 ---------------------------------------------------------
    def page_size(self, page: ttk.Frame) -> tuple[int, int]:
        """页面自身需要的尺寸（不依赖窗口是否可见）。"""
        return page.winfo_reqwidth(), page.winfo_reqheight()

    def layout_report(self) -> dict:
        """布局审计用的纯数据：每页 reqsize + 中栏预算。

        `update_idletasks()` 只做几何计算，**不映射窗口**（此时窗口是 withdrawn）。
        """
        self.update_idletasks()
        return {
            "window_min": WINDOW_MIN,
            "mid_budget": COL_MID,
            "pages": [{"name": str(page), "req": self.page_size(page)}
                      for page in self.pages],
        }
