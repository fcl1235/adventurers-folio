# -*- coding: utf-8 -*-
"""暗色主题: 颜色常量、ttk 样式、滚动容器。"""
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont


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

class HintText(tk.Text):
    """固定高度、可滚动的单行提示框。

    为什么不用 tk.Label: Label 的高度按「行数」写死（height=2），
    中文长句换行后行数超过写死的行数就被裁掉——这正是此前
    「文字被挤出显示框」的根因。

    这里改成 tk.Text: 高度由 height 行高固定, 文字超出时用鼠标滚轮
    翻阅, 不改变控件尺寸, 因此父容器的版面也不会抖动
    （`_layoutcheck.py` 有对应断言）。

    用法与 Label 兼容: `.config(text=..., foreground=...)` 照旧可用。
    """

    def __init__(self, master, height=2, text="", wraplength=None, **kw):
        kw.setdefault("wrap", "word")
        kw.setdefault("relief", "flat")
        kw.setdefault("borderwidth", 0)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("padx", 2)
        kw.setdefault("pady", 1)
        kw.setdefault("font", (UI_FONT, 9))
        kw.setdefault("background", kw.pop("bg", BG))
        kw.setdefault("foreground", kw.pop("fg", DIM))
        # width 由 wraplength 换算: tk.Text 的宽度单位是「字符」,
        # 直接写 width=1 会让提示框只有 1 个字宽
        kw.setdefault("width", 1)
        super().__init__(master, height=height, **kw)
        if wraplength:
            self.configure(width=self._chars_for(wraplength))
        self.configure(state="disabled")
        self.tag_configure("body", justify="left", lmargin1=0, lmargin2=0)
        if text:
            self.set_text(text)
        self.bind("<Enter>", self._wheel_on)
        self.bind("<Leave>", self._wheel_off)

    def _chars_for(self, px):
        """把像素宽度换成等效的字符数。

        tk.Text 的 width 单位是「平均字符宽」，Tk 内部按 ASCII 字宽估算
        （不是汉字宽），所以这里也用 '0' 去量，才能得到和原来
        wraplength 一致的实际像素宽。
        """
        try:
            f = tkfont.Font(font=self.cget("font"))
            unit = max(1, f.measure("0"))
            return max(8, int(px // unit))
        except Exception:                     # 字体不可用时退回经验值
            return max(8, int(px // 7))

    # ---- 与 Label 兼容的接口 ----
    def config(self, **kw):          # noqa: D401  (Label 同名方法)
        fg = kw.pop("foreground", None)
        bg = kw.pop("background", None)
        text = kw.pop("text", None)
        if fg is not None:
            kw["foreground"] = fg
            self.tag_configure("body", foreground=fg)
        if bg is not None:
            kw["background"] = bg
        if kw:
            super().config(**kw)
        if text is not None:
            self.set_text(text)

    configure = config

    def cget(self, key):
        if key == "text":
            return self.get_text()
        return super().cget(key)

    def set_text(self, text):
        """换文案: 保持只读与固定高度, 滚回顶部。"""
        self.configure(state="normal")
        self.delete("1.0", "end")
        if text:
            # 末尾换行会被 Text 当成额外一行, 去掉以免多出一行空白
            self.insert("1.0", text.rstrip("\n"))
        self.tag_add("body", "1.0", "end")
        self.configure(state="disabled")
        self.yview_moveto(0)

    def get_text(self):
        return self.get("1.0", "end-1c")

    # ---- 滚轮: 只在指针悬停于本控件时接管 ----
    def _wheel_on(self, _e=None):
        self.bind_all("<MouseWheel>", self._on_wheel)

    def _wheel_off(self, _e=None):
        self.unbind_all("<MouseWheel>")

    def _on_wheel(self, e):
        # 内容没超出时不要吞掉滚轮事件
        first, last = self.yview()
        if first <= 0.0 and last >= 1.0:
            return
        self.yview_scroll(-1 * (e.delta // 120 if e.delta else 0), "units")


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
