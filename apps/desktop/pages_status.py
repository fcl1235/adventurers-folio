# -*- coding: utf-8 -*-
"""状态页：条件 / 力竭 / 死亡豁免 / 专注。

**为什么从概览右栏搬出来**：那一栏只有 300px 宽、滚动容器 400px 高，
而状态面板自己 557px —— 死亡豁免和专注默认在视野外，必须滚动才看得见；
更糟的是那块滚动区是 Canvas 里嵌 Frame，滚动时旧位置不重绘，整块内容会重影
（截图里「倒地」「成功○○○」各出现两遍）。

搬成独立一页之后：不用滚动，两列排开，14 个条件排 4 列一屏看完，
还顺手给了它写说明的地方 —— 「勾选只表示记上了」这件事以前只写在注释里。

页面不碰规则（C3）：所有状态都来自 `sheet`，写回走外壳注入的 `on_action`。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .i18n import T
from . import theme
from .state_panel import StatePanel


class StatusPage(ttk.Frame):
    """`app.refresh()` 每轮调一次 `refresh(sheet)`。"""

    def __init__(self, master, on_action=None) -> None:
        super().__init__(master, padding=(6, 4))
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=T("状态与濒死"), style="H2.TLabel").pack(side="left")
        # 当前 HP 放在这里：状态页回答的是「他还能不能打」，血在哪一页都该看得见
        self.hp_var = tk.StringVar()
        self.hp_label = ttk.Label(head, textvariable=self.hp_var)
        self.hp_label.pack(side="right")

        self.state_panel = StatePanel(self, on_action=on_action)
        self.state_panel.pack(fill="both", expand=True, pady=(6, 0))

    # --- 数据 -------------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        hp = sheet.get("hp") or {}
        current = int(hp.get("current", 0) or 0)
        maximum = int(hp.get("maximum", 0) or 0)
        text = "HP %d / %d" % (current, maximum)
        if hp.get("temp"):
            text += T("（临时 %d）") % int(hp["temp"])
        self.hp_var.set(text)
        self.hp_label.configure(foreground=theme.hp_color(current, maximum))
        self.state_panel.refresh(sheet)
