# -*- coding: utf-8 -*-
"""暗色主题：色板、ttk 样式、给原生控件（Text / Listbox / Canvas）的配色。

**色值是从旧程序 `dnd55e/theme.py` 抄过来的，但不是 import 过来的。**
两套程序互不依赖（约束 C3：`apps/` 只能 import `dnd5r.api`），
所以这里是一份独立副本。要改配色就两边各自改，不要试图共享。

为什么必须有这么一层：新界面之前完全没有主题代码（`ttk.Style()` 出现 0 次），
控件走 Windows 默认的 `vista` 浅色，于是「角色卡」看起来像一张表单。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# --- 色板（对齐 dnd55e/theme.py:8-22）-------------------------------------
BG = "#17151c"        # 主背景
PANEL = "#211e29"     # 面板
CARD = "#2a2734"      # 卡片
CARD2 = "#353145"     # 按钮
BORDER = "#453f52"    # 边框
GOLD = "#c9a227"      # 主强调·金
GOLD2 = "#e8c34a"     # 亮金
RED = "#c0392b"       # 危险 / 扣血
RED2 = "#8e2f24"
GREEN = "#4e9a51"
TEXT = "#e8e6df"      # 主文字
DIM = "#9a97a3"       # 次要文字
PURPLE = "#b39ddb"    # 专精 / 豁免标记
INK = "#1a1512"       # 金底上的深字
TXT_BG = "#26242f"    # 文本框底

UI_FONT = "Microsoft YaHei UI"

# --- 语义色（旧程序里散落成字面量的那几个）--------------------------------
WARN = "#ff8a75"      # 错误 / 低血（旧程序 hero 的低血阈值色）
OK = "#7bc47f"        # 血健康
HP_TROUGH = "#3a2126" # 血条底槽
BUSY = "#e8c34a"      # 中等血量

# --- 遭遇战地图（旧程序 pages_encounter 是浅底色，暗色下要成对改）----------
MAP_BG = PANEL
MAP_BORDER = BORDER
MAP_GRID = "#2e2b38"
MAP_PC_FILL = "#2b3a52"
MAP_PC_EDGE = "#6fa8e0"
MAP_FOE_FILL = "#4a2b2b"
MAP_FOE_EDGE = "#e08a7a"
MAP_NEUTRAL_FILL = "#3a3744"
MAP_NEUTRAL_EDGE = "#8a8880"
MAP_EMPTY_FILL = CARD
MAP_EMPTY_EDGE = "#5c5967"
MAP_TEXT = TEXT

# --- 原生 tk 控件（ttk 样式管不到它们）-----------------------------------
# 字号统一 9：10 会让每行多约 4px，战斗页会顶破高度预算。
TEXT_STYLE = dict(background=TXT_BG, foreground=TEXT, insertbackground=TEXT,
                  relief="flat", highlightthickness=1,
                  highlightbackground=BORDER, highlightcolor=GOLD,
                  font=(UI_FONT, 9))
LISTBOX_STYLE = dict(background=CARD, foreground=TEXT, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=GOLD, selectbackground=GOLD,
                     selectforeground=INK, activestyle="none",
                     font=(UI_FONT, 9))

# 熟练 / 专精的着色（GridTable 用）
TAG_COLORS = {"prof": GOLD2, "expert": PURPLE, "": TEXT}


def hp_color(current: int, maximum: int) -> str:
    """血量按比例变色：>50% 绿 / >25% 金 / 否则红。

    与旧程序 `dnd55e/ui/panels.py` 的口径一致 —— 桌面上先看颜色再看数字，
    血少的时候应该一眼可见。
    """
    if maximum <= 0:
        return WARN
    ratio = current / maximum
    if ratio > 0.5:
        return OK
    if ratio > 0.25:
        return BUSY
    return WARN


def apply_theme(root: tk.Misc) -> None:
    """把暗色主题套到 root 上（ttk 样式 + 下拉列表 + 根窗口底色）。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:                       # 非 Tk 环境（极少数）就沿用当前主题
        pass
    font = UI_FONT
    style.configure(".", font=(font, 9), background=BG, foreground=TEXT,
                    fieldbackground=CARD, troughcolor=PANEL,
                    bordercolor=BORDER, insertcolor=TEXT,
                    selectbackground=GOLD, selectforeground=INK)
    # 容器
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Card.TFrame", background=CARD)
    # 文字
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Dim.TLabel", background=BG, foreground=DIM)
    style.configure("DimPanel.TLabel", background=PANEL, foreground=DIM)
    style.configure("DimCard.TLabel", background=CARD, foreground=DIM)
    style.configure("Gold.TLabel", background=BG, foreground=GOLD2)
    style.configure("GoldPanel.TLabel", background=PANEL, foreground=GOLD2)
    style.configure("H2.TLabel", font=(font, 11, "bold"),
                    background=BG, foreground=GOLD2)
    style.configure("Title.TLabel", font=(font, 22, "bold"),
                    background=BG, foreground=GOLD2)
    style.configure("Danger.TLabel", background=BG, foreground=WARN)
    # 分区框
    style.configure("TLabelframe", background=BG, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=GOLD2,
                    font=(font, 9, "bold"))
    # 按钮
    style.configure("TButton", background=CARD2, foreground=TEXT,
                    bordercolor=BORDER, padding=(10, 5))
    style.map("TButton",
              background=[("active", "#403b4e"), ("pressed", "#4a4459"),
                          ("disabled", "#26232e")],
              foreground=[("disabled", "#5c5967")])
    style.configure("Gold.TButton", background="#8a6d1a",
                    foreground="#ffe9a8", font=(font, 9, "bold"))
    style.map("Gold.TButton", background=[("active", "#a8871f"),
                                          ("pressed", GOLD)])
    style.configure("Red.TButton", background=RED2, foreground="#ffd9d2")
    style.map("Red.TButton", background=[("active", "#a83a2c"),
                                         ("pressed", RED)])
    style.configure("Green.TButton", background="#2f6b3a", foreground="#d8f2dc")
    style.map("Green.TButton", background=[("active", "#3a8348"),
                                           ("pressed", GREEN)])
    # 小按钮：属性卡上的「检 / 豁」用它 —— 尺寸小，塞得进 148px 宽的卡
    style.configure("Mini.TButton", padding=(3, 0), font=(font, 8))
    style.map("Mini.TButton",
              background=[("active", "#403b4e")],
              foreground=[("disabled", "#5c5967")])
    # 选项卡
    style.configure("TNotebook", background=BG, bordercolor=BORDER)
    style.configure("TNotebook.Tab", background=PANEL, foreground=DIM,
                    padding=(14, 5))
    style.map("TNotebook.Tab", background=[("selected", CARD2)],
              foreground=[("selected", GOLD2)])
    # 输入控件
    style.configure("TEntry", fieldbackground=CARD, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER)
    style.configure("TSpinbox", fieldbackground=CARD, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER, arrowcolor=TEXT)
    style.configure("TCombobox", fieldbackground=CARD, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER, arrowcolor=TEXT)
    # readonly 在 clam 下必须显式 map，否则输入框仍是白底（旧程序踩过）
    style.map("TCombobox",
              fieldbackground=[("readonly", CARD), ("!disabled", CARD)],
              foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", CARD)],
              selectforeground=[("readonly", TEXT)],
              arrowcolor=[("readonly", GOLD2)])
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", GOLD)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    # 勾选 / 单选
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=BG, foreground=TEXT)
        style.map(name, background=[("active", BG)],
                  foreground=[("active", GOLD2)])
    # 进度条（血条 / 经验）
    style.configure("HP.Horizontal.TProgressbar", troughcolor=HP_TROUGH,
                    background=RED, bordercolor=BORDER)
    style.configure("XP.Horizontal.TProgressbar", troughcolor="#33302a",
                    background=GOLD, bordercolor=BORDER)
    # 滚动条：旧程序漏了这条，暗色底下会露出一条浅灰
    style.configure("TScrollbar", background=CARD2, troughcolor=PANEL,
                    bordercolor=BORDER, arrowcolor=DIM)
    style.map("TScrollbar", background=[("active", "#4a4459")])
    style.configure("TSeparator", background=BORDER)
    # 根窗口本身（ttk 管不到）
    try:
        root.configure(bg=BG)
    except tk.TclError:
        pass
