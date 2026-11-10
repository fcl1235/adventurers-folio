# -*- coding: utf-8 -*-
"""状态面板：条件勾选 / 力竭等级 / 死亡豁免 / 专注 DC。

为什么单独一个文件：这四块都是「改事实」的控件（会写回 actor），
与概览页那些只读数字不是一类东西；P7 的建卡向导与后续的遭遇战面板
也要复用它，塞在 `pages.py` 里就得复制粘贴。

**它现在整页都是自己的**（`pages_status.py`）：以前它被塞进概览右栏那个
300×400 的滚动容器里 —— 自己就 557px 高，必须滚才能看见死亡豁免，而
Canvas 里嵌 Frame 的滚动在 Windows 上不擦旧像素，表现为整块内容重影。
搬出来之后它有两列宽度，14 个条件排 4 列，一屏看完。

**诚实原则**（写死）：
  * 条件 = 已记录，未计入数值。规则的后果大片取决于具体情形（麻痹=近战必中、
    束缚=速度 0），没有目标模型时硬算只会算错 —— 界面必须说出来。
  * 力竭 = 已计入。每级 −2 全部 d20、−5 尺速度，数字来自 sheet，本文件不乘。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .i18n import T, join
from . import theme
from .conditions import CONDITIONS, name_of
from .widgets import section

# 勾选列数：整页宽度下 4 列正好（14 个条件 = 4 行），两列会拖成 7 行白占高度
CONDITION_COLUMNS = 4


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
        # 两列：左列是三个「改一个数」的块，右列是 14 个条件（4 列勾选）。
        # 单列排下来 557px，整页放不满；两列排开一屏看完，也不用滚动。
        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 12))
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew")
        self.columnconfigure(1, weight=1)

        # 力竭
        box = section(left, T("力竭"), T("每级全部 d20 −2、速度 −5 尺（已计入数值）"))
        box.pack(fill="x")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(2, 0))
        ttk.Label(row, text=T("等级"), style="Dim.TLabel").pack(side="left")
        self.exhaustion_var = tk.IntVar(value=0)
        self.exhaustion_spin = ttk.Spinbox(
            row, from_=0, to=6, width=4, textvariable=self.exhaustion_var,
            command=self._apply_exhaustion, justify="center")
        self.exhaustion_spin.pack(side="left", padx=(6, 6))
        self.exhaustion_spin.bind("<Return>", lambda _e: self._apply_exhaustion())
        self.exhaustion_spin.bind("<FocusOut>", lambda _e: self._apply_exhaustion())
        self.exhaustion_note = ttk.Label(row, text=T("无"), style="Dim.TLabel")
        self.exhaustion_note.pack(side="left")

        # 条件
        box = section(right, T("状态"), T("已记录，未计入数值"))
        box.pack(fill="both", expand=True)
        self.condition_vars: dict[str, tk.BooleanVar] = {}
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        for index, (ident, _label) in enumerate(CONDITIONS):
            var = tk.BooleanVar(value=False)
            # 名字走 `name_of`（= `Catalog` 取值时翻译），**不能直接用元组里的
            # 中文** —— 那样切到英文这 14 个勾选框还是中文，而 `T()` 根本没被调用，
            # `i18n.MISSING` 也发现不了（探针扫控件树才抓到）。
            box_ = ttk.Checkbutton(grid, text=name_of(ident), variable=var,
                                   command=lambda i=ident: self._apply_condition(i))
            box_.grid(row=index // CONDITION_COLUMNS, column=index % CONDITION_COLUMNS,
                      sticky="w", padx=(0, 10))
            self.condition_vars[ident] = var
        for column in range(CONDITION_COLUMNS):
            grid.columnconfigure(column, weight=1)
        # 内容包自己施加的状态（狂暴 …）没有勾选框，但要看得见，否则「状态栏里没有」
        self.extra_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.extra_var, style="Dim.TLabel",
                  wraplength=560, justify="left").pack(anchor="w", pady=(2, 0))
        # 这一栏最容易误会成「勾了就自动扣数值」。写明它是什么、不是什么。
        note = T("勾只代表「记上了」。具体后果（麻痹 = 近战必中、束缚 = 速度 0）"
                 "取决于当时的情形，本程序没有目标模型，所以不替你算。")
        ttk.Label(box, text=note, style="Dim.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(6, 0))

        # 死亡豁免
        box = section(left, T("死亡豁免"), T("HP 为 0 时掷：10 以上成功，三次成功稳定"))
        box.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.success_var = tk.StringVar(value=_dot(0, 3))
        self.failed_var = tk.StringVar(value=_dot(0, 3))
        ttk.Label(row, text=T("成功"), style="Dim.TLabel").pack(side="left")
        ttk.Label(row, textvariable=self.success_var,
                  foreground=theme.OK).pack(side="left", padx=(4, 10))
        ttk.Label(row, text=T("失败"), style="Dim.TLabel").pack(side="left")
        ttk.Label(row, textvariable=self.failed_var,
                  foreground=theme.WARN).pack(side="left", padx=(4, 0))
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(4, 0))
        self.death_button = ttk.Button(row, text=T("掷死亡豁免"), style="Mini.TButton",
                                       command=lambda: self._fire("death_save", None))
        self.death_button.pack(side="left")
        self.death_reset = ttk.Button(row, text=T("重置"), style="Mini.TButton", width=5,
                                      command=lambda: self._fire("death_reset", None))
        self.death_reset.pack(side="left", padx=(4, 0))
        self.death_note_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.death_note_var,
                  style="Dim.TLabel").pack(anchor="w", pady=(2, 0))

        # 专注
        box = section(left, T("专注"), T("受伤时掷体质豁免，DC = max(10, 伤害 ÷ 2)"))
        box.pack(fill="x", pady=(6, 0))
        # 第一行先说事实：现在在专注哪一道。以前这一栏只有「伤害 → DC」，
        # 谁也没记自己在专注什么，于是放第二道专注法术不会顶掉第一道。
        focus_row = ttk.Frame(box)
        focus_row.pack(fill="x")
        self.focus_var = tk.StringVar(value=T("当前没有在专注任何法术"))
        self.focus_label = ttk.Label(focus_row, textvariable=self.focus_var,
                                     style="Dim.TLabel")
        self.focus_label.pack(side="left")
        self.end_focus_button = ttk.Button(
            focus_row, text=T("结束专注"), style="Mini.TButton", width=8,
            command=lambda: self._fire("concentration_end", None))
        self.end_focus_button.pack(side="right")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(4, 0))
        ttk.Label(row, text=T("伤害"), style="Dim.TLabel").pack(side="left")
        self.damage_var = tk.IntVar(value=0)
        self.damage_spin = ttk.Spinbox(row, from_=0, to=999, width=5,
                                       textvariable=self.damage_var, justify="center")
        self.damage_spin.pack(side="left", padx=(6, 8))
        self.concentration_button = ttk.Button(
            row, text=T("专注检定"), style="Mini.TButton",
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
            self._refresh_concentration(sheet.get("concentration") or {})
        finally:
            self._building = False

    def _refresh_concentration(self, info: dict) -> None:
        """「正在专注：《云雾术》（1 环）」—— 事实从 sheet 来，界面不自己拼名字。

        没在专注时按钮要真的 disabled：留着可点，玩家点了会以为撤掉了什么。
        """
        active = bool(info.get("active"))
        self.focus_var.set(str(info.get("text") or T("当前没有在专注任何法术")))
        self.focus_label.configure(foreground=theme.TEXT if active else theme.DIM)
        self.end_focus_button.configure(state="normal" if active else "disabled")

    def _refresh_exhaustion(self, info: dict) -> None:
        level = int(info.get("level", 0))
        self.exhaustion_var.set(level)
        if not level:
            self.exhaustion_note.configure(text=T("无"), foreground=theme.DIM)
            return
        self.exhaustion_note.configure(
            text=T("全部 d20 %+d · 速度 %+d 尺") % (int(info.get("penalty", 0)),
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
        self.extra_var.set((T("另有（来自能力）：") + join(name_of(i) for i in sorted(extra)))
                           if extra else "")

    def _refresh_death(self, info: dict, hp: dict) -> None:
        success = int(info.get("succeeded", 0))
        failed = int(info.get("failed", 0))
        self.success_var.set(_dot(success, int(info.get("succeeded_of", 3))))
        self.failed_var.set(_dot(failed, int(info.get("failed_of", 3))))
        if info.get("dead"):
            note = T("已死亡")
        elif info.get("stable"):
            note = T("已稳定（停止掷骰）")
        elif int(hp.get("current", 1) or 0) > 0:
            note = T("HP 尚未到 0，不需要掷")
        else:
            note = T("还在濒死：掷到 10 以上成功")
        self.death_note_var.set(note)
        state = "disabled" if (info.get("dead") or info.get("stable")
                               or int(hp.get("current", 1) or 0) > 0) else "normal"
        self.death_button.configure(state=state)

    def set_concentration_dc(self, dc: int, resolved: str = "") -> None:
        text = "DC %d" % dc
        if resolved:
            text = "%s　%s" % (text, resolved)
        self.dc_var.set(text)
