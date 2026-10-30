# -*- coding: utf-8 -*-
"""人物卡上「一眼要看见」的两种块：数值胶囊与属性卡。

这两个控件是「明确标识各项数值」这件事的载体 —— 旧程序里调整值是 18pt 金色，
分数是小字，豁免在右上角。新界面之前把六属性压成一行 `17 (+3)` 的同字号文本，
数字都还在，但看不出哪个是主、哪个是辅。

规矩：**只显示，不计算**。所有数字由页面从 `character_sheet()` 取来传进来，
这里不查表、不加值（约束 C3/C5）。
"""
from __future__ import annotations

from tkinter import ttk

from . import theme


class Chip(ttk.Frame):
    """hero 条上的数值徽章：上面一行小字标题，下面一个大号数值。

    旧程序是 `ttk.Frame(style="Card.TFrame", padding=(7,5))` 里放
    标题（DimCard）+ 值（16pt bold）。
    """

    def __init__(self, master, title: str, *, width: int | None = None) -> None:
        super().__init__(master, style="Card.TFrame", padding=(8, 5))
        self._title = ttk.Label(self, text=title, style="DimCard.TLabel")
        self._title.pack(anchor="center")
        self._value = ttk.Label(self, text="—", style="Card.TLabel",
                                font=(theme.UI_FONT, 15, "bold"), anchor="center")
        self._value.pack(anchor="center")
        if width:
            self.configure(width=width)

    # --- 接口 ---------------------------------------------------------
    def set_value(self, text: str, color: str | None = None) -> None:
        self._value.configure(text=text,
                              foreground=color if color is not None else theme.TEXT)

    def value(self) -> str:
        return str(self._value.cget("text"))

    def title(self) -> str:
        return str(self._title.cget("text"))


class AbilityCard(ttk.Frame):
    """一张属性卡：中文名 + 英文缩写 / 大号调整值 / 属性分数 / 豁免值。

    分数在界面上是**只读**的：改分数要走 `rebuild_actor`（会重算 HP 上限），
    那是「编辑角色」不是「改个数字」，所以不给就地输入框。
    """

    def __init__(self, master, key: str, name_zh: str) -> None:
        super().__init__(master, style="Card.TFrame", padding=(8, 6))
        self.key = key
        # 标题行：左「力量 STR」，右「豁免 +3」
        head = ttk.Frame(self, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="%s %s" % (name_zh, key.upper()),
                  style="DimCard.TLabel").pack(side="left")
        self._save = ttk.Label(head, text="", style="DimCard.TLabel")
        self._save.pack(side="right")
        # 大号调整值：这是卡面主角
        self._mod = ttk.Label(self, text="—", style="Card.TLabel",
                              font=(theme.UI_FONT, 18, "bold"), anchor="center")
        self._mod.pack(fill="x", pady=(2, 0))
        # 原始分数
        self._score = ttk.Label(self, text="", style="DimCard.TLabel",
                                anchor="center")
        self._score.pack(fill="x")
        # 「检 / 豁」小按钮。旧程序就在这个位置，roll 有就用、没接就置灰 ——
        # 让按钮看起来能点却没反应是最差的体验。
        buttons = ttk.Frame(self, style="Card.TFrame")
        buttons.pack(fill="x", pady=(3, 0))
        self.check_button = ttk.Button(buttons, text="检",
                                       style="Mini.TButton", width=3,
                                       command=self._on_check, state="disabled")
        self.check_button.pack(side="left", expand=True, fill="x")
        self.save_button = ttk.Button(buttons, text="豁",
                                      style="Mini.TButton", width=3,
                                      command=self._on_save, state="disabled")
        self.save_button.pack(side="left", expand=True, fill="x", padx=(3, 0))
        self._check = None
        self._save_hook = None

    # --- 接口 ---------------------------------------------------------
    def set_roll_callbacks(self, on_check, on_save) -> None:
        """接上掷骰。没接之前两个按钮是灰的。"""
        self._check, self._save_hook = on_check, on_save
        state = "normal" if on_check else "disabled"
        self.check_button.configure(command=self._on_check, state=state)
        self.save_button.configure(command=self._on_save,
                                   state="normal" if on_save else "disabled")

    def _on_check(self) -> None:
        if self._check is not None:
            self._check(self.key)

    def _on_save(self) -> None:
        if self._save_hook is not None:
            self._save_hook(self.key)

    def set_values(self, *, mod: int, score: int, save: int,
                   proficient: bool = False) -> None:
        self._mod.configure(text="%+d" % mod, foreground=theme.GOLD2)
        self._score.configure(text="数值 %d" % score)
        # 熟练豁免用紫色标出来 —— 与技能表的「熟练」同一套视觉语言
        self._save.configure(text="豁免 %+d" % save,
                             foreground=theme.PURPLE if proficient else theme.DIM)

    def mod_text(self) -> str:
        return str(self._mod.cget("text"))

    def score_text(self) -> str:
        return str(self._score.cget("text"))

    def save_text(self) -> str:
        return str(self._save.cget("text"))

    def save_proficient(self) -> bool:
        return str(self._save.cget("foreground")) == theme.PURPLE
