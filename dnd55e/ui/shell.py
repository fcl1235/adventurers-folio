"""窗口骨架: 初始化 / 样式 / 菜单 / 工具栏 / 主区 / 中栏装配。"""
import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, paths, theme, util
from ..consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                      size_cn, subclass_cn, tool_cn)
from ..dialogs import DiceDialog
from ..rules import Rules
from ..theme import (BG, DIM, GOLD, GOLD2, HintText, INK, LISTBOX_STYLE,
                     PANEL, PURPLE, TEXT, TEXT_STYLE, UI_FONT)
from ..util import ability_mod, mod_str, spell_detail
from . import panels, tabs
from .tabs import ITEM_KINDS


class ShellMixin():
    def __init__(self, selftest=False):
        super().__init__()
        self._selftest = selftest
        self.title("冒险者手帖 · Character Builder")
        self.geometry("1340x860")
        self.minsize(1200, 760)
        self.configure(bg=BG)
        self.rules = Rules()
        self.char = None
        self.sneak_var = tk.BooleanVar(value=False)   # 掷伤害时是否附加偷袭
        self._xp_th = {int(k): int(v) for k, v in
                       self.rules.d["progression"]["xp_thresholds"].items()}

        self._setup_style()
        self._build_menu()
        self._build_toolbar()
        self._build_main()
        self._build_status()

        try:
            os.makedirs(paths.CHAR_DIR, exist_ok=True)
        except OSError:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if selftest:
            self.withdraw()
        else:
            self.after(300, self._auto_start)

    def _setup_style(self):
        from ..theme import apply_theme
        apply_theme(self)

    def _build_menu(self):
        mk = dict(bg=PANEL, fg=TEXT, activebackground=GOLD,
                  activeforeground=INK, bd=0)
        m = tk.Menu(self, **mk)
        filem = tk.Menu(m, tearoff=0, **mk)
        filem.add_command(label="新建角色…", command=self.new_character)
        filem.add_separator()
        filem.add_command(label="保存角色 (Ctrl+S)",
                          command=self.save_character, accelerator="Ctrl+S")
        filem.add_command(label="另存为…",
                          command=self.save_character_as)
        filem.add_command(label="打开存档文件夹",
                          command=self.open_char_folder)
        filem.add_separator()
        filem.add_command(label="载入角色… (Ctrl+O)",
                          command=self.load_character, accelerator="Ctrl+O")
        filem.add_command(label="导出角色JSON副本…",
                          command=self.export_character)
        m.add_cascade(label="文件", menu=filem)

        chm = tk.Menu(m, tearoff=0, **mk)
        chm.add_command(label="升级…", command=self.level_up)
        chm.add_separator()
        chm.add_command(label="长休 (回复HP与全部法术位)", command=self.long_rest)
        chm.add_command(label="短休 (邪术师回复法术位)", command=self.short_rest)
        m.add_cascade(label="角色", menu=chm)

        tm = tk.Menu(m, tearoff=0, **mk)
        tm.add_command(label="骰子工具", command=lambda: DiceDialog(self))
        m.add_cascade(label="工具", menu=tm)

        self.config(menu=m)
        self.bind("<Control-s>", lambda e: self.save_character())
        self.bind("<Control-o>", lambda e: self.load_character())

    def _build_toolbar(self):
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(10, 7))
        bar.pack(fill="x")
        ttk.Label(bar, text="🎲 冒险者手帖", style="GoldPanel.TLabel",
                  font=(UI_FONT, 13, "bold")).pack(side="left", padx=(2, 16))

        def b(txt, cmd, style="TButton"):
            ttk.Button(bar, text=txt, command=cmd,
                       style=style).pack(side="left", padx=3)

        b("✦ 新建角色", self.new_character, "Gold.TButton")
        b("💾 保存", self.save_character)
        b("📂 打开", self.load_character)
        b("⬇ 导出JSON", self.export_character)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                   padx=10)
        b("⬆ 升级", self.level_up, "Gold.TButton")
        b("🌙 长休", self.long_rest)
        b("☕ 短休", self.short_rest)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                   padx=10)
        b("🎲 骰子工具", lambda: DiceDialog(self))

    def _build_main(self):
        self.main_area = ttk.Frame(self)
        self.main_area.pack(fill="both", expand=True)
        self._build_empty_view()
        self._build_sheet_view()
        self._show_view()

    def _show_view(self):
        self.empty_view.pack_forget()
        self.sheet_view.pack_forget()
        view = self.sheet_view if self.char else self.empty_view
        view.pack(fill="both", expand=True)

    def _build_empty_view(self):
        v = ttk.Frame(self.main_area)
        self.empty_view = v
        inner = ttk.Frame(v)
        inner.place(relx=0.5, rely=0.42, anchor="center")
        ttk.Label(inner, text="⚔  🎲  ⚔", font=(UI_FONT, 36),
                  foreground=GOLD2, background=BG).pack(pady=(0, 8))
        ttk.Label(inner, text="冒险者手帖", style="Title.TLabel").pack()
        ttk.Label(inner, text="2024 版规则 · 建卡向导 / 升级 / 战斗追踪 一站式",
                  style="Dim.TLabel", font=(UI_FONT, 11)).pack(pady=(4, 28))
        ttk.Button(inner, text="✦  创建新角色 (六步向导)", style="Hero.TButton",
                   command=self.new_character).pack(pady=7)
        ttk.Button(inner, text="📂  打开角色存档 (.json)", style="Hero.TButton",
                   command=self.load_character).pack(pady=7)
        ttk.Label(inner,
                  text="内置: 12 职业 · 16 背景 · 10 种族 · 武器专精 · 法术位追踪 · "
                       "状态/力竭 · 快捷骰子与掷骰日志",
                  style="Dim.TLabel").pack(pady=(26, 0))

    def _build_sheet_view(self):
        v = ttk.Frame(self.main_area, padding=(10, 8))
        self.sheet_view = v
        self._build_hero(v)
        cols = ttk.Frame(v)
        cols.pack(fill="both", expand=True, pady=(8, 0))
        cols.columnconfigure(0, minsize=320)
        cols.columnconfigure(1, weight=1)
        cols.columnconfigure(2, minsize=320)
        cols.rowconfigure(0, weight=1)
        self.col_left = ttk.Frame(cols)
        self.col_left.grid(row=0, column=0, sticky="ns")
        self.col_mid = ttk.Frame(cols)
        self.col_mid.grid(row=0, column=1, sticky="nsew", padx=8)
        self.col_right = ttk.Frame(cols)
        self.col_right.grid(row=0, column=2, sticky="ns")
        self._build_left()
        self._build_mid()
        self._build_right()

    def _build_mid(self):
        self.nb = ttk.Notebook(self.col_mid)
        self.nb.pack(fill="both", expand=True)
        tabs.build_all(self, self.nb)

    def _build_item_grid(self):
        """按当前分类重建物品勾选格 (勾选状态在 item_vars 里, 重建不丢)"""
        for cb in getattr(self, "item_cbs", {}).values():
            cb.destroy()
        self.item_cbs = {}
        kind = dict(ITEM_KINDS).get(self.item_filter_var.get())
        rows = [it for it in consts.MAGIC_ITEMS
                if kind is None or it.get("kind") == kind]
        for i, it in enumerate(rows):
            # 只取中文部分: '护甲 +1 Armor +1' -> '护甲 +1'
            short = re.split(r"\s+(?=[A-Za-z])", it["name"], maxsplit=1)[0]
            cb = ttk.Checkbutton(self.item_grid, text=short,
                                 variable=self.item_vars[it["id"]],
                                 command=lambda i2=it["id"]: self._item_changed(i2))
            cb.grid(row=i // 4, column=i % 4, sticky="w", padx=3)
            cb.bind("<Enter>", lambda e, i2=it: self._item_hint(i2))
            # 右键/中键开详情卡: 左键已被勾选占用 (切换装备状态)
            cb.bind("<Button-2>", lambda e, i2=it["id"]: self._item_card_open(i2))
            cb.bind("<Button-3>", lambda e, i2=it["id"]: self._item_card_open(i2))
            self.item_cbs[it["id"]] = cb
        self.item_count_lbl.config(text=f"{len(rows)} 件")
        self.item_grid.update_idletasks()

    def _item_filter_changed(self):
        self._build_item_grid()
