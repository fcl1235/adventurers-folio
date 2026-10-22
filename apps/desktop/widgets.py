# -*- coding: utf-8 -*-
"""桌面前端的控件：只负责「怎么摆」，不含任何规则。

所有数字都来自 `dnd5r.api.character_sheet()` 的返回值 —— 界面这一层
**不查表、不算加值**（约束 C3/C5）。要加一个新数字，先让它出现在 sheet 里。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# 布局铁律（吃过两次亏，见 README）：
#   1. 底部栏必须先 pack(side="bottom")，再 pack 伸展的内容 —— 否则窄屏时整条消失
#   2. 中栏可用宽 610、标签页可用高 574（沿用旧程序的实测值）
#   3. 横向控件要算「个数 × 宽 ≤ 610」，9 个法术位盒那种直接换成两行
COL_LEFT = 250
COL_MID = 610
COL_RIGHT = 300
ROW_HEIGHT = 22


class ScrollText(ttk.Frame):
    """只读文本块（定高、可滚动）。高度固定，内容多少都不改变布局高度。"""

    def __init__(self, master, height: int = 6, width: int = 30) -> None:
        super().__init__(master)
        self.text = tk.Text(self, height=height, width=width, wrap="word",
                            relief="flat", borderwidth=0, padx=6, pady=4)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=bar.set)
        self.text.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.text.configure(state="disabled")

    def set_text(self, value: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.text.configure(state="disabled")


class KeyValue(ttk.Frame):
    """左标签右数值的竖排小表（AC / 先攻 / HP 这类）。"""

    def __init__(self, master, rows: int = 4) -> None:
        super().__init__(master)
        self._values: list[tk.StringVar] = []
        self._labels: list[ttk.Label] = []
        for index in range(rows):
            caption = ttk.Label(self, width=8)
            value = tk.StringVar(value="")
            shown = ttk.Label(self, textvariable=value, anchor="e")
            caption.grid(row=index, column=0, sticky="w", pady=1)
            shown.grid(row=index, column=1, sticky="e", pady=1)
            self.columnconfigure(1, weight=1)
            self._labels.append(caption)
            self._values.append(value)

    def set_row(self, index: int, caption: str, value: str) -> None:
        self._labels[index].configure(text=caption)
        self._values[index].set(value)

    def clear(self) -> None:
        for caption, value in zip(self._labels, self._values):
            caption.configure(text="")
            value.set("")


class GridTable(ttk.Frame):
    """标签网格表（定行数、定列宽）。

    不用 `ttk.Treeview` 的原因很实在：它会把 `"+2"` 当整数收成 `2`，
    技能加值全变成没有符号的数字。角色卡上「+3 熟练」与「3 点属性」是两回事，
    符号丢了就读不出来。Label 不做这种转换，而且行高固定、reqsize 可预测。
    """

    def __init__(self, master, columns: list[tuple[str, int]], rows: int) -> None:
        super().__init__(master)
        self.columns = columns
        self.row_count = rows
        self._cells: list[list[ttk.Label]] = []
        for index, (title, width) in enumerate(columns):
            ttk.Label(self, text=title, width=width, anchor="w",
                      font=("Microsoft YaHei UI", 9, "bold")).grid(
                row=0, column=index, sticky="w", padx=(0, 6))
        for row in range(rows):
            line = []
            for index, (_, width) in enumerate(columns):
                cell = ttk.Label(self, text="", width=width, anchor="w")
                cell.grid(row=row + 1, column=index, sticky="w", padx=(0, 6), pady=1)
                line.append(cell)
            self._cells.append(line)

    def fill(self, rows: list[tuple[tuple[str, ...], str]]) -> None:
        """`rows` 是 (单元格文本, 颜色标记)；多余的旧行清空。"""
        for index, line in enumerate(self._cells):
            if index < len(rows):
                cells, tag = rows[index]
                for cell, text in zip(line, cells):
                    cell.configure(text=str(text))
                    if tag == "prof":
                        cell.configure(foreground="#1d5fa8")
                    elif tag == "expert":
                        cell.configure(foreground="#0f5132")
                    else:
                        cell.configure(foreground="#222222")
            else:
                for cell in line:
                    cell.configure(text="", foreground="#222222")

    def text(self, row: int, column: int) -> str:
        return self._cells[row][column].cget("text")


class ListPane(ttk.Frame):
    """可选清单（Listbox + 滚动条）。

    `Listbox` 不做任何类型转换，`"+2"` 进来还是 `"+2"` —— 这一点比 Treeview 强。
    选中一律走 `select_id()`：extended 模式下 `selection_set` 是**追加**，
    直接设会留上一个选中项，测试里会静默选错行（旧程序吃过这个亏）。
    """

    def __init__(self, master, height: int = 10, width: int = 40) -> None:
        super().__init__(master)
        self.list = tk.Listbox(self, height=height, width=width, exportselection=False,
                               activestyle="none", relief="flat",
                               highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.list.yview)
        self.list.configure(yscrollcommand=bar.set)
        self.list.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self._ids: list[str] = []

    def fill(self, rows: list[tuple[str, str]]) -> None:
        """`rows` 是 (id, 显示文本)。重画后按 id 恢复选中项。"""
        keep = self.selected_id()
        self.list.delete(0, "end")
        self._ids = [row_id for row_id, _ in rows]
        for _, text in rows:
            self.list.insert("end", text)
        if keep:
            self.select_id(keep)

    def selected_id(self) -> str:
        picked = self.list.curselection()
        return self._ids[picked[0]] if picked else ""

    def select_id(self, row_id: str) -> None:
        if row_id not in self._ids:
            return
        index = self._ids.index(row_id)
        self.list.selection_clear(0, "end")
        self.list.selection_set(index)
        self.list.activate(index)
        self.list.see(index)

    def index_of(self, row_id: str) -> int:
        return self._ids.index(row_id) if row_id in self._ids else -1

    def text_at(self, index: int) -> str:
        return self.list.get(index)

    @property
    def row_count(self) -> int:
        return int(self.list.size())


def section(master, title: str, note: str = "") -> ttk.LabelFrame:
    """带标题的分区框；note 是给玩家的一句说明（不是给我们自己看的注释）。"""
    frame = ttk.LabelFrame(master, text=title, padding=(8, 4))
    if note:
        ttk.Label(frame, text=note, foreground="#666666").pack(anchor="w")
    return frame


def hint_bar(master) -> ttk.Label:
    """底部提示行。**必须 side="bottom" pack**，否则内容一挤就被裁掉。"""
    return ttk.Label(master, anchor="w", foreground="#666666")
