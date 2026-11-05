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
from .widgets import section


class StatusPage(ttk.Frame):
    """`app.refresh()` 每轮调一次 `refresh(sheet)`。"""

    def __init__(self, master, on_action=None, on_rest=None) -> None:
        super().__init__(master, padding=(6, 4))
        self._on_rest = on_rest
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=T("状态与濒死"), style="H2.TLabel").pack(side="left")
        # 当前 HP 放在这里：状态页回答的是「他还能不能打」，血在哪一页都该看得见
        self.hp_var = tk.StringVar()
        self.hp_label = ttk.Label(head, textvariable=self.hp_var)
        self.hp_label.pack(side="right")

        # 休息区**先** pack 到 bottom（布局铁律）：下面那块状态面板是 expand=True，
        # 后 pack 的会被它挤出可视区 —— 而休息恰恰是玩家最需要点到的按钮。
        self._build_rest()

        self.state_panel = StatePanel(self, on_action=on_action)
        self.state_panel.pack(fill="both", expand=True, pady=(6, 0))

    def _build_rest(self) -> None:
        """长休 / 短休。

        为什么放在状态页：这两颗按钮改的是**角色的运行时状态**（HP、骰子、资源池），
        和「倒地 / 力竭 / 濒死」是同一类事实。放在概览页会和掷骰记录抢右栏，
        放在顶栏则挤不下（那里已经有 6 个按钮）。
        """
        box = section(self, T("休息"),
                      T("短休：花生命骰回血、回短休资源；长休：回满 HP 与全部资源"))
        box.pack(side="bottom", fill="x", pady=(6, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")

        ttk.Label(row, text=T("生命骰"), style="Dim.TLabel").pack(side="left")
        self.dice_var = tk.StringVar(value="0 / 0")
        ttk.Label(row, textvariable=self.dice_var).pack(side="left", padx=(4, 10))

        ttk.Label(row, text=T("花"), style="Dim.TLabel").pack(side="left")
        self.spend_var = tk.IntVar(value=0)
        self.spend_box = ttk.Spinbox(row, from_=0, to=0, width=3,
                                     textvariable=self.spend_var, justify="center")
        self.spend_box.pack(side="left", padx=(4, 2))
        ttk.Label(row, text=T("颗"), style="Dim.TLabel").pack(side="left")

        self.short_button = ttk.Button(row, text=T("短休"), style="Mini.TButton",
                                       width=6,
                                       command=lambda: self._rest("short"))
        self.short_button.pack(side="left", padx=(10, 4))
        self.long_button = ttk.Button(row, text=T("长休"), style="Mini.TButton",
                                      width=6, command=lambda: self._rest("long"))
        self.long_button.pack(side="left")

        # 长休预览：「点下去会发生什么」。不用点完才知道 —— 长休是不可撤销的。
        self.preview_var = tk.StringVar()
        ttk.Label(box, textvariable=self.preview_var, style="Dim.TLabel").pack(
            anchor="w", pady=(3, 0))
        # 上一次休息的结果
        self.rest_var = tk.StringVar()
        self.rest_label = ttk.Label(box, textvariable=self.rest_var, style="Dim.TLabel",
                                    wraplength=980)
        self.rest_label.pack(anchor="w")

    def _rest(self, kind: str) -> None:
        if self._on_rest is None:
            return
        try:
            spend = int(self.spend_var.get() or 0)
        except (TypeError, tk.TclError):
            spend = 0
        report = self._on_rest(kind, spend)
        if report:
            self.rest_var.set(report.get("summary") or "")
            self.rest_label.configure(foreground=theme.TEXT)

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
        self._refresh_rest(sheet.get("rest") or {})

    def _refresh_rest(self, rest: dict) -> None:
        left = int(rest.get("dice_left", 0) or 0)
        total = int(rest.get("dice_max", 0) or 0)
        self.dice_var.set("%d / %d" % (left, total))
        self.spend_box.configure(to=max(0, left))
        try:
            chosen = int(self.spend_var.get() or 0)
        except (TypeError, tk.TclError):
            chosen = 0
        if chosen > left:
            self.spend_var.set(left)

        long_rest = rest.get("long_rest") or {}
        heal = int(long_rest.get("heal", 0) or 0)
        dice = int(long_rest.get("dice", 0) or 0)
        pools = int(long_rest.get("pools", 0) or 0)
        if heal or dice or pools:
            self.preview_var.set(T("长休会：回 %d 点生命、回 %d 颗生命骰、回满 %d 个资源池")
                                 % (heal, dice, pools))
        else:
            self.preview_var.set(T("长休不会改变任何数值（已经满状态）"))
        # 短休没骰也没短休池时仍然可点 —— 让玩家看到「没有可恢复的内容」，
        # 比一个灰着的按钮什么都不说更诚实。
        self.short_button.configure(
            state="normal" if self._on_rest is not None else "disabled")
        self.long_button.configure(
            state="normal" if self._on_rest is not None else "disabled")
