# -*- coding: utf-8 -*-
"""桌面前端的控件：只负责「怎么摆」，不含任何规则。

所有数字都来自 `dnd5r.api.character_sheet()` 的返回值 —— 界面这一层
**不查表、不算加值**（约束 C3/C5）。要加一个新数字，先让它出现在 sheet 里。

配色一律取 `theme` 里的语义常量，**这个文件里不许出现十六进制色值**：
以前 44 处硬编码颜色散在五个页面里，改一次主题要满仓库找。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import theme

# 布局铁律（吃过两次亏，见 README）：
#   1. 底部栏必须先 pack(side="bottom")，再 pack 伸展的内容 —— 否则窄屏时整条消失
#   2. 中栏可用宽 610、标签页可用高 574（沿用旧程序的实测值）
#   3. 横向控件要算「个数 × 宽 ≤ 610」，9 个法术位盒那种直接换成两行
COL_LEFT = 250
COL_MID = 610
COL_RIGHT = 300
ROW_HEIGHT = 22
# 概览页左栏专用：六张属性卡要 2 列 × 148px，250 放不下。
# 共享的 COL_LEFT 不动 —— pages_encounter.py 用 COL_LEFT-20 算换行宽度。
CARD_LEFT = 320

# 「感官」键的中文名。三个页面都要用，以前抄了两份（pages_powers / pages_spells），
# 抄两份的下场是改一处漏一处。
SENSE_ZH = {"darkvision": "黑暗视觉", "blindsight": "盲视",
            "tremorsense": "震颤感知", "truesight": "真实视觉"}

# 六属性的中文名。技能表、属性卡、掷骰记录都用它。
ABILITY_ZH = {"str": "力量", "dex": "敏捷", "con": "体质",
              "int": "智力", "wis": "感知", "cha": "魅力"}

# 伤害类型的中文名。法术页与装备页都要用 —— 以前只有法术页有一份，
# 装备页再抄一份又是「改一处漏一处」。
DAMAGE_ZH = {
    "acid": "强酸", "bludgeoning": "钝击", "cold": "冷冻", "fire": "火焰",
    "force": "力场", "lightning": "闪电", "necrotic": "黯蚀", "piercing": "穿刺",
    "poison": "毒素", "psychic": "心灵", "radiant": "光耀", "slashing": "挥砍",
    "thunder": "雷鸣",
}


def sense_text(senses: dict) -> str:
    """`{darkvision: 60}` → 「黑暗视觉 60 尺」。带单位，别让人猜。"""
    return "、".join("%s %d 尺" % (SENSE_ZH.get(key, key), value)
                    for key, value in (senses or {}).items())


def hit_dice_text(pools, classes) -> str:
    """生命骰池 → 「战士 5/5」。

    `sheet["hp"]["hit_dice"]` 是 `[{"id": "hit_dice.<职业 id>", "left": 5, "max": 5}]`，
    直接把列表塞进 Label 会打出 `[{'id': ...}]` 这种东西（第一版就是这样）。
    职业名从 `sheet["classes"]` 里对，对不上就退回 id 末段。
    """
    names = {row.get("id"): row.get("name") for row in (classes or ())}
    parts = []
    for pool in pools or ():
        ident = str(pool.get("id", ""))
        class_id = ident[len("hit_dice."):] if ident.startswith("hit_dice.") else ident
        label = names.get(class_id) or class_id.rsplit(".", 1)[-1]
        parts.append("%s %s/%s" % (label, pool.get("left"), pool.get("max")))
    return "、".join(parts)



class ScrollText(ttk.Frame):
    """只读文本块（定高、可滚动）。高度固定，内容多少都不改变布局高度。"""

    def __init__(self, master, height: int = 6, width: int = 30) -> None:
        super().__init__(master)
        self.text = tk.Text(self, height=height, width=width, wrap="word",
                            padx=6, pady=4, **theme.TEXT_STYLE)
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
    """左标签右数值的竖排小表（AC / 先攻 / HP 这类）。

    值用 12pt 粗体：这张表出现在概览右栏，是「扫一眼读数字」的场景，
    与标签同字号同粗细时数字会被文字淹没。
    """

    def __init__(self, master, rows: int = 4) -> None:
        super().__init__(master)
        self._values: list[tk.StringVar] = []
        self._labels: list[ttk.Label] = []
        for index in range(rows):
            caption = ttk.Label(self, width=8, style="Dim.TLabel")
            value = tk.StringVar(value="")
            shown = ttk.Label(self, textvariable=value, anchor="e",
                              font=(theme.UI_FONT, 11, "bold"))
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

    def label_at(self, index: int) -> str:
        return str(self._labels[index].cget("text"))

    def value_at(self, index: int) -> str:
        return self._values[index].get()


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
                      font=(theme.UI_FONT, 9, "bold")).grid(
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
                color = theme.TAG_COLORS.get(tag, theme.TEXT)
                for cell, text in zip(line, cells):
                    cell.configure(text=str(text), foreground=color)
            else:
                for cell in line:
                    cell.configure(text="", foreground=theme.TEXT)

    def text(self, row: int, column: int) -> str:
        return self._cells[row][column].cget("text")


class RollGrid(ttk.Frame):
    """带掷骰按钮的网格表（技能表用）。

    **列索引与 `GridTable` 完全一致**：`text(row, col)` 的 `col` 只数数据列，
    按钮不算列 —— 测试与审计都按 `text(i, 0)` 读名称，加一个按钮不该把列号挪位。
    """

    def __init__(self, master, columns: list[tuple[str, int]], rows: int,
                 on_roll=None) -> None:
        super().__init__(master)
        self.columns = columns
        self.row_count = rows
        self._on_roll = on_roll
        self._keys: list[str] = []
        self._buttons: list[ttk.Button] = []
        self._cells: list[list[ttk.Label]] = []
        for index, (title, width) in enumerate(columns):
            ttk.Label(self, text=title, width=width, anchor="w",
                      font=(theme.UI_FONT, 9, "bold")).grid(
                row=0, column=index + 1, sticky="w", padx=(0, 6))
        for row in range(rows):
            button = ttk.Button(self, text="🎲", style="Mini.TButton", width=2,
                                command=lambda index=row: self._roll(index),
                                state="normal" if on_roll else "disabled")
            button.grid(row=row + 1, column=0, padx=(0, 4), pady=1)
            self._buttons.append(button)
            line = []
            for index, (_, width) in enumerate(columns):
                cell = ttk.Label(self, text="", width=width, anchor="w")
                cell.grid(row=row + 1, column=index + 1, sticky="w",
                          padx=(0, 6), pady=1)
                line.append(cell)
            self._cells.append(line)

    def fill(self, rows: list[tuple[tuple[str, ...], str, str]]) -> None:
        """`rows` 是 (单元格文本, 颜色标记, 掷骰用的 key)；多余的旧行清空。"""
        self._keys = []
        for index, line in enumerate(self._cells):
            if index < len(rows):
                cells, tag, key = rows[index]
                color = theme.TAG_COLORS.get(tag, theme.TEXT)
                self._keys.append(key)
                self._buttons[index].configure(
                    state="normal" if self._on_roll and key else "disabled")
                for cell, text in zip(line, cells):
                    cell.configure(text=str(text), foreground=color)
            else:
                for cell in line:
                    cell.configure(text="", foreground=theme.TEXT)
                self._buttons[index].configure(state="disabled")

    def key_at(self, row: int) -> str:
        return self._keys[row] if row < len(self._keys) else ""

    def text(self, row: int, column: int) -> str:
        return self._cells[row][column].cget("text")

    def _roll(self, index: int) -> None:
        if self._on_roll is None:
            return
        key = self.key_at(index)
        if key:
            self._on_roll(key)


class ListPane(ttk.Frame):
    """可选清单（Listbox + 滚动条）。

    `Listbox` 不做任何类型转换，`"+2"` 进来还是 `"+2"` —— 这一点比 Treeview 强。
    选中一律走 `select_id()`：extended 模式下 `selection_set` 是**追加**，
    直接设会留上一个选中项，测试里会静默选错行（旧程序吃过这个亏）。
    """

    def __init__(self, master, height: int = 10, width: int = 40) -> None:
        super().__init__(master)
        self.list = tk.Listbox(self, height=height, width=width,
                               exportselection=False, borderwidth=0,
                               **theme.LISTBOX_STYLE)
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


class ScrollFrame(ttk.Frame):
    """定高竖向滚动容器：内容放进 `self.body`。

    高度**由构造参数定死**，不跟着内容长 —— 这样它才能塞进高度预算里。

    `scrollregion` 用 `after_idle` 合并：旧程序是每建一个子控件就 bind 一次
    `<Configure>` 重设 scrollregion，20 个控件就是 20 次全量重排，
    表现是「拖动时一块一块慢慢刷出来」。合并之后一次重画只设一次。
    """

    def __init__(self, master, height: int = 320, width: int | None = None) -> None:
        super().__init__(master)
        # 画布**必须给 width**：不给的话它会用自己的默认宽（约 395px），
        # 把整个右栏顶宽 95px，页面横向预算就白算了。
        self.canvas = tk.Canvas(self, height=height, width=width or 300, bd=0,
                                highlightthickness=1,
                                highlightbackground=theme.BORDER,
                                background=theme.BG)
        self.bar = ttk.Scrollbar(self, orient="vertical",
                                 command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, style="TFrame")
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._schedule_sync)
        self.canvas.bind("<Configure>", self._sync_width)
        self.canvas.bind("<Enter>", self._wheel_on)
        self.canvas.bind("<Leave>", self._wheel_off)
        self.body.bind("<Enter>", self._wheel_on)
        self.body.bind("<Leave>", self._wheel_off)
        self._pending: str | None = None

    def _schedule_sync(self, _event=None) -> None:
        if self._pending is not None:
            return
        self._pending = self.after_idle(self._sync_scroll)

    def _sync_scroll(self) -> None:
        self._pending = None
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event) -> None:
        self.canvas.itemconfigure(self._win, width=event.width)

    def _wheel_on(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _wheel_off(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event) -> None:
        first, last = self.canvas.yview()
        if first <= 0.0 and last >= 1.0:      # 没得滚就别吞事件
            return
        step = -1 * (event.delta // 120) if event.delta else 0
        if step:
            self.canvas.yview_scroll(step, "units")

    def to_top(self) -> None:
        self.canvas.yview_moveto(0)


def section(master, title: str, note: str = "") -> ttk.LabelFrame:
    """带标题的分区框；note 是给玩家的一句说明（不是给我们自己看的注释）。"""
    frame = ttk.LabelFrame(master, text=title, padding=(8, 4))
    if note:
        ttk.Label(frame, text=note, style="Dim.TLabel").pack(anchor="w")
    return frame


def hint_bar(master) -> ttk.Label:
    """底部提示行。**必须 side="bottom" pack**，否则内容一挤就被裁掉。"""
    return ttk.Label(master, anchor="w", style="Dim.TLabel")
