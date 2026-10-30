# -*- coding: utf-8 -*-
"""掷骰记录：右栏那个「掷了什么、掷出多少」的小面板。

规矩与其它页面一致：**引擎给什么就显示什么**（`api.roll_check` 的返回值），
这里不做加值、不判断成败 —— DC 在桌上，引擎里没有。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme
from .widgets import ABILITY_ZH

LOG_LIMIT = 60          # 记录条数上限（沿用旧程序口径）


def _label_of(result: dict) -> str:
    """记录里的名字。

    注意：`api.roll_check` 返回的 `label` **对豁免是内部 token**（`save.dex`）、
    对裸属性是全大写（`STR`），只有技能/工具才是真正的中文名。
    这些 token 是给脚本用的标识，不是给玩家看的，所以这两种情况一律自己拼 ——
    不然记录里会一半中文一半英文。
    """
    kind = result.get("kind")
    key = str(result.get("key") or "")
    if kind == "save":
        return "%s豁免" % ABILITY_ZH.get(key, key.upper())
    if kind == "ability":
        return "%s检定" % ABILITY_ZH.get(key, key.upper())
    if kind == "initiative":
        return "先攻"
    return str(result.get("label") or "").strip() or key or kind or "检定"


def format_roll(result: dict) -> str:
    """把一次掷骰的返回值压成一行：`隐匿：15（d20 12 +3）`。

    优势/劣势必须写在行尾 —— 同一项技能掷出 15 与「优势掷出 15」是两回事。
    """
    total = int(result.get("total", 0))
    die = result.get("die", "?")
    modifier = int(result.get("modifier", 0))
    marks = ""
    if result.get("advantage"):
        marks = "　优势"
    elif result.get("disadvantage"):
        marks = "　劣势"
    return "%s：%d（d20 %s %+d）%s" % (_label_of(result), total, die, modifier, marks)


class DiceLog(ttk.Frame):
    """掷骰记录。最新的一条在最上面，超出上限丢最旧的。"""

    def __init__(self, master, height: int = 5, width: int = 30) -> None:
        super().__init__(master)
        self.list = tk.Listbox(self, height=height, width=width,
                               exportselection=False, borderwidth=0,
                               **theme.LISTBOX_STYLE)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=bar.set)
        self.list.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self._lines: list[str] = []

    def add(self, text: str) -> None:
        self._lines.insert(0, text)
        del self._lines[LOG_LIMIT:]
        self.list.delete(0, "end")
        for line in self._lines:
            self.list.insert("end", line)

    def clear(self) -> None:
        self._lines.clear()
        self.list.delete(0, "end")

    def lines(self) -> list[str]:
        return list(self._lines)

    @property
    def row_count(self) -> int:
        return int(self.list.size())
