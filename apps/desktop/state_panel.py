# -*- coding: utf-8 -*-
"""状态面板：条件勾选 / 力竭等级 / 死亡豁免 / 专注 DC。

为什么单独一个文件：这四块都是「改事实」的控件（会写回 actor），
与概览页那些只读数字不是一类东西；P7 的建卡向导与后续的遭遇战面板
也要复用它，塞在 `pages.py` 里就得复制粘贴。

**诚实原则**（写死）：
  * 条件 = 已记录，未计入数值。规则的后果大片取决于具体情形（麻痹=近战必中、
    束缚=速度 0），没有目标模型时硬算只会算错 —— 界面必须说出来。
  * 力竭 = 已计入。每级 −2 全部 d20、−5 尺速度，数字来自 sheet，本文件不乘。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme
from .conditions import CONDITIONS, name_of
from .widgets import section

# 勾选列数：右栏约 300px，两个「☐ 倒地」放得下三个就挤了
CONDITION_COLUMNS = 2


def _dot(filled: int, total: int) -> str:
    """「●●○」—— 死亡豁免是三次记，用点比用两个数字更快读。"""
    return "●" * filled + "○" * max(0, total - filled)


class StatePanel(ttk.Frame):
    """`on_action(name, value)` 由外壳注入；面板自己不碰 api（页面无规则）。"""

    def __init__(self, master, on_action=None) -> None:
        super().__init__(master)
        self._on_action = on_action
        self._building = False          # 回填期间不许回调，否则一刷新就写库
        self._build()

    # --- 构建 ---------------------------------------------------------
    def _build(self) -> None:
        # 力竭
        box = section(self, "力竭", "每级全部 d20 −2、速度 −5 尺（已计入数值）")
        box.pack(fill="x")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(2, 0))
        ttk.Label(row, text="等级", style="Dim.TLabel").pack(side="left")
        self.exhaustion_var = tk.IntVar(value=0)
        self.exhaustion_spin = ttk.Spinbox(
            row, from_=0, to=6, width=4, textvariable=self.exhaustion_var,
            command=self._apply_exhaustion, justify="center")
        self.exhaustion_spin.pack(side="left", padx=(6, 6))
        self.exhaustion_spin.bind("<Return>", lambda _e: self._apply_exhaustion())
        self.exhaustion_spin.bind("<FocusOut>", lambda _e: self._apply_exhaustion())
        self.exhaustion_note = ttk.Label(row, text="无", style="Dim.TLabel")
        self.exhaustion_note.pack(side="left")

        # 条件
        box = section(self, "状态", "已记录，未计入数值")
        box.pack(fill="x", pady=(6, 0))
        self.condition_vars: dict[str, tk.BooleanVar] = {}
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        for index, (ident, label) in enumerate(CONDITIONS):
            var = tk.BooleanVar(value=False)
            box_ = ttk.Checkbutton(grid, text=label, variable=var,
                                   command=lambda i=ident: self._apply_condition(i))
            box_.grid(row=index // CONDITION_COLUMNS, column=index % CONDITION_COLUMNS,
                      sticky="w", padx=(0, 10))
            self.condition_vars[ident] = var
        for column in range(CONDITION_COLUMNS):
            grid.columnconfigure(column, weight=1)
        # 内容包自己施加的状态（狂暴 …）没有勾选框，但要看得见，否则「状态栏里没有」
        self.extra_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.extra_var, style="Dim.TLabel",
                  wraplength=280, justify="left").pack(anchor="w", pady=(2, 0))

        # 死亡豁免
        box = section(self, "死亡豁免", "HP 为 0 时掷：10 以上成功，三次成功稳定")
        box.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.success_var = tk.StringVar(value=_dot(0, 3))
        self.failed_var = tk.StringVar(value=_dot(0, 3))
        ttk.Label(row, text="成功", style="Dim.TLabel").pack(side="left")
        ttk.Label(row, textvariable=self.success_var,
                  foreground=theme.OK).pack(side="left", padx=(4, 10))
        ttk.Label(row, text="失败", style="Dim.TLabel").pack(side="left")
        ttk.Label(row, textvariable=self.failed_var,
                  foreground=theme.WARN).pack(side="left", padx=(4, 0))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(4, 0))
        self.death_button = ttk.Button(row, text="掷死亡豁免", style="Mini.TButton",
                                       command=lambda: self._fire("death_save", None))
        self.death_button.pack(side="left")
        self.death_reset = ttk.Button(row, text="重置", style="Mini.TButton", width=5,
                                      command=lambda: self._fire("death_reset", None))
        self.death_reset.pack(side="left", padx=(4, 0))
        self.death_note_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.death_note_var,
                  style="Dim.TLabel").pack(anchor="w", pady=(2, 0))

        # 专注
        box = section(self, "专注", "受伤时掷体质豁免，DC = max(10, 伤害 ÷ 2)")
        box.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="伤害", style="Dim.TLabel").pack(side="left")
        self.damage_var = tk.IntVar(value=0)
        self.damage_spin = ttk.Spinbox(row, from_=0, to=999, width=5,
                                       textvariable=self.damage_var, justify="center")
        self.damage_spin.pack(side="left", padx=(6, 8))
        self.concentration_button = ttk.Button(
            row, text="专注检定", style="Mini.TButton",
            command=lambda: self._fire("concentration", self._damage()))
        self.concentration_button.pack(side="left")
        self.dc_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.dc_var,
                  style="Dim.TLabel").pack(anchor="w", pady=(2, 0))

    # --- 读数 ---------------------------------------------------------
    def _damage(self) -> int:
        """Spinbox 里可能是空串或手输的乱码 —— 一律当 0，不抛给 Tk 回调。"""
        try:
            return max(0, int(self.damage_var.get()))
        except (tk.TclError, ValueError):
            return 0

    def _fire(self, name: str, value) -> None:
        if self._on_action is not None:
            self._on_action(name, value)

    def _apply_exhaustion(self) -> None:
        if self._building:
            return
        try:
            level = int(self.exhaustion_var.get())
        except (tk.TclError, ValueError):
            return                    # 输入中途的半成品不该写库
        self._fire("exhaustion", max(0, min(6, level)))

    def _apply_condition(self, ident: str) -> None:
        if self._building:
            return
        self._fire("condition", (ident, bool(self.condition_vars[ident].get())))

    # --- 数据 ---------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        self._building = True
        try:
            self._refresh_exhaustion(sheet.get("exhaustion") or {})
            self._refresh_conditions(sheet.get("conditions") or [])
            self._refresh_death(sheet.get("death_saves") or {}, sheet.get("hp") or {})
        finally:
            self._building = False

    def _refresh_exhaustion(self, info: dict) -> None:
        level = int(info.get("level", 0))
        self.exhaustion_var.set(level)
        if not level:
            self.exhaustion_note.configure(text="无", foreground=theme.DIM)
            return
        self.exhaustion_note.configure(
            text="全部 d20 %+d · 速度 %+d 尺" % (int(info.get("penalty", 0)),
                                            int(info.get("speed", 0))),
            foreground=theme.WARN if level >= 4 else theme.TEXT)

    def _refresh_conditions(self, ids) -> None:
        recorded = set(ids or ())
        extra = []
        for ident, var in self.condition_vars.items():
            var.set(ident in recorded)
        for ident in recorded:
            if ident not in self.condition_vars:
                extra.append(ident)
        self.extra_var.set(("另有（来自能力）：" + "、".join(name_of(i) for i in sorted(extra)))
                           if extra else "")

    def _refresh_death(self, info: dict, hp: dict) -> None:
        success = int(info.get("succeeded", 0))
        failed = int(info.get("failed", 0))
        self.success_var.set(_dot(success, int(info.get("succeeded_of", 3))))
        self.failed_var.set(_dot(failed, int(info.get("failed_of", 3))))
        if info.get("dead"):
            note = "已死亡"
        elif info.get("stable"):
            note = "已稳定（停止掷骰）"
        elif int(hp.get("current", 1) or 0) > 0:
            note = "HP 尚未到 0，不需要掷"
        else:
            note = "还在濒死：掷到 10 以上成功"
        self.death_note_var.set(note)
        state = "disabled" if (info.get("dead") or info.get("stable")
                               or int(hp.get("current", 1) or 0) > 0) else "normal"
        self.death_button.configure(state=state)

    def set_concentration_dc(self, dc: int, resolved: str = "") -> None:
        text = "DC %d" % dc
        if resolved:
            text = "%s　%s" % (text, resolved)
        self.dc_var.set(text)
