# -*- coding: utf-8 -*-
"""暗色主题: 颜色常量、ttk 样式、滚动容器。"""
import tkinter as tk
from tkinter import ttk


BG = "#17151c"        # 主背景
PANEL = "#211e29"     # 面板
CARD = "#2a2734"      # 卡片
CARD2 = "#353145"     # 按钮
BORDER = "#453f52"    # 边框
GOLD = "#c9a227"      # 主强调·金
GOLD2 = "#e8c34a"     # 亮金
RED = "#c0392b"       # 危险/扣血
RED2 = "#8e2f24"
GREEN = "#4e9a51"
TEXT = "#e8e6df"      # 主文字
DIM = "#9a97a3"       # 次要文字
PURPLE = "#b39ddb"    # 专精/豁免标记
INK = "#1a1512"       # 金底上的深字
TXT_BG = "#26242f"    # 文本框底

UI_FONT = "Microsoft YaHei UI"

TEXT_STYLE = dict(background=TXT_BG, foreground=TEXT, insertbackground=TEXT,
                  relief="flat", highlightthickness=1,
                  highlightbackground=BORDER, highlightcolor=GOLD,
                  font=(UI_FONT, 10))
LISTBOX_STYLE = dict(background=CARD, foreground=TEXT, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=GOLD, selectbackground=GOLD,
                     selectforeground=INK, activestyle="none",
                     font=(UI_FONT, 10))

class ScrollFrame(ttk.Frame):
    """竖向滚动容器: 内容统一放进 self.body, 避免长列表撑破标签页。"""

    def __init__(self, master, height=400, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0,
                                bg=BG, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical",
                                 command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.body,
                                              anchor="nw")
        self.body.bind("<Configure>", self._sync_scroll)
        self.canvas.bind("<Configure>", self._sync_width)
        self.canvas.bind("<Enter>", self._wheel_on)
        self.canvas.bind("<Leave>", self._wheel_off)
        self.body.bind("<Enter>", self._wheel_on)
        self.body.bind("<Leave>", self._wheel_off)

    def _sync_scroll(self, _e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _wheel_on(self, _e=None):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _wheel_off(self, _e=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e):
        delta = -1 * (e.delta // 120) if e.delta else 0
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def to_top(self):
        self.canvas.yview_moveto(0)


def apply_theme(root):
    """把暗色主题套到 root 上 (ttk 样式 + 下拉列表配色)。"""
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    F = UI_FONT
    st.configure(".", font=(F, 10), background=BG, foreground=TEXT,
                 fieldbackground=CARD, troughcolor=PANEL,
                 bordercolor=BORDER, insertcolor=TEXT,
                 selectbackground=GOLD, selectforeground=INK)
    st.configure("TFrame", background=BG)
    st.configure("Panel.TFrame", background=PANEL)
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG, foreground=TEXT)
    st.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    st.configure("Card.TLabel", background=CARD, foreground=TEXT)
    st.configure("Dim.TLabel", background=BG, foreground=DIM)
    st.configure("DimPanel.TLabel", background=PANEL, foreground=DIM)
    st.configure("DimCard.TLabel", background=CARD, foreground=DIM)
    st.configure("GoldPanel.TLabel", background=PANEL, foreground=GOLD2)
    st.configure("Title.TLabel", font=(F, 22, "bold"),
                 background=BG, foreground=GOLD2)
    st.configure("H2.TLabel", font=(F, 11, "bold"),
                 background=BG, foreground=GOLD2)
    st.configure("TLabelframe", background=BG, bordercolor=BORDER)
    st.configure("TLabelframe.Label", background=BG, foreground=GOLD2,
                 font=(F, 10, "bold"))
    # 按钮
    st.configure("TButton", background=CARD2, foreground=TEXT,
                 bordercolor=BORDER, padding=(10, 5))
    st.map("TButton",
           background=[("active", "#403b4e"), ("pressed", "#4a4459"),
                       ("disabled", "#26232e")],
           foreground=[("disabled", "#5c5967")])
    st.configure("Gold.TButton", background="#8a6d1a",
                 foreground="#ffe9a8", font=(F, 10, "bold"))
    st.map("Gold.TButton", background=[("active", "#a8871f"),
                                       ("pressed", GOLD)])
    st.configure("Hero.TButton", background="#8a6d1a", padding=(24, 12),
                 foreground="#ffe9a8", font=(F, 13, "bold"))
    st.map("Hero.TButton", background=[("active", "#a8871f"),
                                       ("pressed", GOLD)])
    st.configure("Red.TButton", background=RED2, foreground="#ffd9d2")
    st.map("Red.TButton", background=[("active", "#a83a2c"),
                                      ("pressed", RED)])
    st.configure("Green.TButton", background="#2f6b3a",
                 foreground="#d8f2dc")
    st.map("Green.TButton", background=[("active", "#3a8348"),
                                        ("pressed", GREEN)])
    st.configure("Mini.TButton", padding=(4, 1), font=(F, 9))
    # 选项卡
    st.configure("TNotebook", background=BG, bordercolor=BORDER)
    st.configure("TNotebook.Tab", background=PANEL, foreground=DIM,
                 padding=(14, 6))
    st.map("TNotebook.Tab", background=[("selected", CARD2)],
           foreground=[("selected", GOLD2)])
    # 输入控件
    st.configure("TEntry", fieldbackground=CARD, foreground=TEXT,
                 insertcolor=TEXT, bordercolor=BORDER)
    st.configure("TSpinbox", fieldbackground=CARD, foreground=TEXT,
                 insertcolor=TEXT, bordercolor=BORDER, arrowcolor=TEXT)
    st.configure("TCombobox", fieldbackground=CARD, foreground=TEXT,
                 insertcolor=TEXT, bordercolor=BORDER, arrowcolor=TEXT)
    # readonly 状态在 clam 下必须显式 map, 否则输入框仍是白底
    st.map("TCombobox",
           fieldbackground=[("readonly", CARD), ("!disabled", CARD)],
           foreground=[("readonly", TEXT)],
           selectbackground=[("readonly", CARD)],
           selectforeground=[("readonly", TEXT)],
           arrowcolor=[("readonly", GOLD2)])
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", GOLD)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    # 勾选/单选
    for name in ("TCheckbutton", "TRadiobutton"):
        st.configure(name, background=BG, foreground=TEXT)
        st.map(name, background=[("active", BG)],
               foreground=[("active", GOLD2)])
    # 进度条
    st.configure("HP.Horizontal.TProgressbar", troughcolor="#3a2126",
                 background=RED, bordercolor=BORDER)
    st.configure("XP.Horizontal.TProgressbar", troughcolor="#33302a",
                 background=GOLD, bordercolor=BORDER)
    st.configure("TSeparator", background=BORDER)
