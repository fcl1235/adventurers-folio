import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from . import consts, theme, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)
from .theme import ScrollFrame
from .dialogs import DiceDialog
from .util import ability_mod, mod_str, spell_detail

# 拆分后需要的内部依赖
import os
from .consts import ABILITIES, ABILITY_CN

# 物品分类筛选: (显示名, kind 值；None = 全部)
ITEM_KINDS = [("全部", None), ("戒指", "ring"), ("斗篷", "cloak"),
              ("护甲盾牌", "armor"), ("武器", "weapon"), ("魔杖", "wand"),
              ("法杖", "staff"), ("弹药", "ammunition"), ("奇物", "wondrous")]
from . import paths
from .rules import Rules
from .theme import (BG, DIM, GOLD, GOLD2, INK, LISTBOX_STYLE, PANEL,
                    PURPLE, TEXT, TEXT_STYLE, UI_FONT)


class AppShell:
    def __init__(self, selftest=False):
        super().__init__()
        self._selftest = selftest
        self.title("D&D 5.5e 人物卡 · Character Builder")
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

    # ---- 样式 ----

    def _setup_style(self):
        from .theme import apply_theme
        apply_theme(self)
    # ---- 菜单 ----

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

    # ---- 顶部工具栏: 所有常用功能一排直达 ----

    def _build_toolbar(self):
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(10, 7))
        bar.pack(fill="x")
        ttk.Label(bar, text="🎲 D&D 5.5e 人物卡", style="GoldPanel.TLabel",
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

    # ---- 主区域: 欢迎页 / 角色卡 二选一 ----

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
        ttk.Label(inner, text="D&D 5.5e 人物卡", style="Title.TLabel").pack()
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

    # ---- 角色卡布局 ----

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

    def _chip(self, parent, title, cmd=None):
        f = ttk.Frame(parent, style="Card.TFrame", padding=(10, 6))
        f.pack(side="left", padx=4)
        ttk.Label(f, text=title, style="DimCard.TLabel").pack()
        val = ttk.Label(f, text="—", style="Card.TLabel",
                        font=(UI_FONT, 16, "bold"))
        val.pack()
        if cmd:
            ttk.Button(f, text="🎲 掷", style="Mini.TButton",
                       command=cmd).pack(pady=(2, 0))
        return val

    def _build_hero(self, parent):
        F = UI_FONT
        hero = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        hero.pack(fill="x")

        # 左: 身份 + XP
        idf = ttk.Frame(hero, style="Panel.TFrame")
        idf.pack(side="left", fill="y")
        self.hero_name = ttk.Label(idf, text="—", style="GoldPanel.TLabel",
                                   font=(F, 17, "bold"))
        self.hero_name.pack(anchor="w")
        self.hero_sub = ttk.Label(idf, text="", style="DimPanel.TLabel",
                                  wraplength=440, justify="left")
        self.hero_sub.pack(anchor="w", pady=(1, 6))
        xpf = ttk.Frame(idf, style="Panel.TFrame")
        xpf.pack(anchor="w")
        ttk.Label(xpf, text="经验 XP", style="DimPanel.TLabel").pack(side="left")
        self.xp_var = tk.IntVar()
        sp = ttk.Spinbox(xpf, from_=0, to=999999, width=8,
                         textvariable=self.xp_var, command=self._xp_changed)
        sp.pack(side="left", padx=4)
        sp.bind("<Return>", lambda e: self._xp_changed())
        sp.bind("<FocusOut>", lambda e: self._xp_changed())
        self.xp_hint = ttk.Label(xpf, text="", style="GoldPanel.TLabel")
        self.xp_hint.pack(side="left", padx=(6, 0))
        self.xp_bar = ttk.Progressbar(idf, style="XP.Horizontal.TProgressbar",
                                      length=240, mode="determinate")
        self.xp_bar.pack(anchor="w", pady=(5, 0))

        # 中: HP 大面板
        hpf = ttk.Frame(hero, style="Panel.TFrame")
        hpf.pack(side="left", padx=30)
        ttk.Label(hpf, text="❤ 生命值", style="DimPanel.TLabel").pack(anchor="w")
        self.hp_big = ttk.Label(hpf, text="0 / 0", background=PANEL,
                                foreground="#ff8a75", font=(F, 20, "bold"))
        self.hp_big.pack(anchor="w")
        self.hp_bar = ttk.Progressbar(hpf, style="HP.Horizontal.TProgressbar",
                                      length=235, mode="determinate")
        self.hp_bar.pack(anchor="w", pady=3)
        row = ttk.Frame(hpf, style="Panel.TFrame")
        row.pack(anchor="w")
        for txt, n, sty in [("−5", -5, "Red.TButton"), ("−1", -1, "Red.TButton"),
                            ("+1", 1, "Green.TButton"),
                            ("+5", 5, "Green.TButton")]:
            ttk.Button(row, text=txt, width=4, style=sty,
                       command=lambda v=n: self._hp_add(v)).pack(side="left",
                                                                 padx=2)
        ttk.Button(row, text="回满", width=5,
                   command=lambda: self._hp_add(99999)).pack(side="left",
                                                             padx=(8, 2))
        ttk.Label(row, text="临时HP", style="DimPanel.TLabel").pack(
            side="left", padx=(10, 2))
        self.hp_temp_var = tk.IntVar()
        tsp = ttk.Spinbox(row, from_=0, to=99, width=4,
                          textvariable=self.hp_temp_var,
                          command=self._hp_temp_changed)
        tsp.pack(side="left")
        tsp.bind("<FocusOut>", lambda e: self._hp_temp_changed())

        # 右: 数值徽章
        chips = ttk.Frame(hero, style="Panel.TFrame")
        chips.pack(side="right")
        self.chip_ac = self._chip(chips, "🛡 护甲 AC")
        self.chip_init = self._chip(chips, "⚡ 先攻", cmd=self._roll_init)
        self.chip_speed = self._chip(chips, "👣 速度")
        self.chip_pb = self._chip(chips, "✦ 熟练")
        self.chip_pp = self._chip(chips, "👁 被动察觉")

    def _build_left(self):
        F = UI_FONT
        ab = ttk.LabelFrame(self.col_left,
                            text=" 属性 (卡片内一键掷检定/豁免) ", padding=8)
        ab.pack(fill="x")
        self.ab_entries, self.ab_modlbls, self.ab_savelbls = {}, {}, {}
        for i, a in enumerate(ABILITIES):
            card = ttk.Frame(ab, style="Card.TFrame", padding=8)
            card.grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="nsew")
            top = ttk.Frame(card, style="Card.TFrame")
            top.pack(fill="x")
            nm = ttk.Label(top, text=f"{ABILITY_CN[a]} {a}",
                           style="DimCard.TLabel")
            nm.pack(side="left")
            nm.bind("<Enter>", lambda e, x=a: self._ability_hint(x))
            sv = ttk.Label(top, text="", style="Card.TLabel",
                           foreground=PURPLE)
            sv.pack(side="right")
            self.ab_savelbls[a] = sv
            self.ab_modlbls[a] = ttk.Label(card, text="+0", style="Card.TLabel",
                                           font=(F, 18, "bold"))
            self.ab_modlbls[a].pack()
            bot = ttk.Frame(card, style="Card.TFrame")
            bot.pack(pady=(2, 0))
            v = tk.IntVar()
            sb = ttk.Spinbox(bot, from_=1, to=20, width=3, textvariable=v,
                             command=self._score_edited)
            sb.pack(side="left")
            sb.bind("<FocusOut>", lambda e: self._score_edited())
            self.ab_entries[a] = v
            ttk.Button(bot, text="检🎲", style="Mini.TButton", width=5,
                       command=lambda x=a: self._roll_check(x)
                       ).pack(side="left", padx=(4, 1))
            ttk.Button(bot, text="豁🎲", style="Mini.TButton", width=5,
                       command=lambda x=a: self._roll_save(x)
                       ).pack(side="left", padx=1)

        self.ab_hint = tk.Label(ab, text="鼠标停在属性名上可看该属性的用途",
                                bg=BG, fg=DIM, wraplength=286, justify="left",
                                anchor="nw", height=2)
        self.ab_hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ar = ttk.LabelFrame(self.col_left, text=" 护甲与防御 ", padding=8)
        ar.pack(fill="x", pady=(8, 0))
        self.armor_cb = ttk.Combobox(ar, state="readonly", width=20,
                                     values=[a[0] for a in consts.ARMORS])
        self.armor_cb.current(0)
        self.armor_cb.pack(anchor="w", pady=2)
        self.armor_cb.bind("<<ComboboxSelected>>",
                           lambda e: self._armor_changed())
        self.shield_var = tk.BooleanVar()
        ttk.Checkbutton(ar, text="盾牌 (AC +2)", variable=self.shield_var,
                        command=self._armor_changed).pack(anchor="w", pady=2)
        self.tough_var = tk.BooleanVar()
        ttk.Checkbutton(ar, text="Tough 专长 (每级 +2 HP)",
                        variable=self.tough_var,
                        command=self._tough_changed).pack(anchor="w", pady=2)

    def _build_mid(self):
        F = UI_FONT
        self.nb = ttk.Notebook(self.col_mid)
        nb = self.nb
        nb.pack(fill="both", expand=True)

        # ---- 技能 ----
        t1 = ttk.Frame(nb, padding=8)
        self.tab_skills = t1
        nb.add(t1, text=" 技 能 ")
        ttk.Label(t1, text="🎲=掷检定   ✓=熟练   ◇/◆=专精 Expertise (需先熟练, 双倍熟练加值)",
                  style="Dim.TLabel").pack(anchor="w", pady=(0, 2))
        self.skill_hint = tk.Label(t1, text="鼠标停在技能名上可看它管什么检定",
                                   bg=BG, fg=DIM, wraplength=430,
                                   justify="left", anchor="nw", height=2)
        self.skill_hint.pack(anchor="w", pady=(0, 6))
        grid = ttk.Frame(t1)
        grid.pack(fill="both", expand=True)
        self.skill_vars, self.skill_modlbls = {}, {}
        self.skill_namelbls, self.skill_expbtns = {}, {}
        for i, s in enumerate(self.rules.d["skills"]):
            sid = s["id"]
            r, col = i % 9, i // 9
            row = ttk.Frame(grid)
            row.grid(row=r, column=col, sticky="w", padx=(0, 26), pady=3)
            ttk.Button(row, text="🎲", width=3, style="Mini.TButton",
                       command=lambda x=sid: self._roll_skill(x)
                       ).pack(side="left")
            v = tk.BooleanVar()
            self.skill_vars[sid] = v
            ttk.Checkbutton(row, variable=v, width=2,
                            command=lambda x=sid: self._skill_toggled(x)
                            ).pack(side="left")
            nl = ttk.Label(row, text=s["name"].split(" ")[0], width=8,
                           anchor="w")
            nl.pack(side="left")
            nl.bind("<Enter>", lambda e, x=sid: self._skill_hover(x))
            ab = ttk.Label(row, text=ABILITY_CN[s["ability"]], width=3,
                           style="Dim.TLabel")
            ab.pack(side="left")
            self.skill_namelbls[sid] = nl
            ml = ttk.Label(row, text="+0", width=4, font=(F, 10, "bold"))
            ml.pack(side="left")
            self.skill_modlbls[sid] = ml
            eb = ttk.Button(row, text="◇", width=3, style="Mini.TButton",
                            command=lambda x=sid: self._toggle_expertise(x))
            eb.pack(side="left", padx=(2, 0))
            self.skill_expbtns[sid] = eb

        # ---- 法术 ----
        t2 = ttk.Frame(nb, padding=8)
        self.tab_spells = t2
        nb.add(t2, text=" 法 术 ")
        head = ttk.Frame(t2)
        head.pack(fill="x")
        self.slots_head = ttk.Label(head, text="", style="H2.TLabel")
        self.slots_head.pack(side="left")
        # 法师才有法术书 (其它职业在 refresh 里保持隐藏)
        self.spellbook_btn = ttk.Button(head, text="📖 法术书 (0)",
                                        style="Mini.TButton",
                                        command=self._spellbook_open)
        self.slots_frame = ttk.Frame(t2)
        self.slots_frame.pack(anchor="nw", pady=(2, 4))
        self.slots_widgets = {}

        bar = ttk.Frame(t2)
        bar.pack(fill="x", pady=2)
        self.spell_add_cb = ttk.Combobox(bar, state="readonly", width=24)
        self.spell_add_cb.pack(side="left")
        self.spell_add_btn = ttk.Button(bar, text="＋ 学习", style="Mini.TButton",
                                        command=self._spell_add)
        self.spell_add_btn.pack(side="left", padx=3)
        ttk.Button(bar, text="－ 移除", style="Mini.TButton",
                   command=self._spell_del).pack(side="left")
        ttk.Button(bar, text="▶ 施放", style="Gold.TButton",
                   command=self._spell_cast).pack(side="right")
        ttk.Button(bar, text="◉ 专注", style="Mini.TButton",
                   command=self._spell_focus).pack(side="right", padx=3)
        self.spell_quota_lbl = ttk.Label(t2, text="", style="Dim.TLabel")
        self.spell_quota_lbl.pack(anchor="w", pady=(2, 0))

        self.spell_list = tk.Listbox(t2, height=7, **LISTBOX_STYLE)
        self.spell_list.pack(fill="x", pady=2)
        self.spell_list.bind("<<ListboxSelect>>", self._spell_show)
        ttk.Label(t2, text="法术详情", style="H2.TLabel").pack(anchor="w", pady=(2, 0))
        self.spell_detail = tk.Text(t2, height=7, wrap="word", state="disabled",
                                    **TEXT_STYLE, width=1)
        self.spell_detail.pack(fill="both", expand=True, pady=2)
        ttk.Label(t2, text="● 剩余环位 ○ 已用；戏法不耗环位；专注法术同时只能维持一个。",
                  style="Dim.TLabel", wraplength=520,
                  justify="left").pack(anchor="w", side="bottom")

        # ---- 装备 / 攻击 / 加成 ----
        t3 = ttk.Frame(nb, padding=6)
        nb.add(t3, text=" 装备·加成 ")
        wf = ttk.LabelFrame(t3, text="武器与攻击", padding=4)
        wf.pack(fill="x")
        r1 = ttk.Frame(wf)
        r1.pack(fill="x")
        ttk.Label(r1, text="武器:").pack(side="left")
        self.weapon_cb = ttk.Combobox(r1, state="readonly", width=19,
                                      values=["（未装备）"]
                                      + [w[0] for w in consts.WEAPONS])
        self.weapon_cb.pack(side="left", padx=4)
        self.weapon_cb.bind("<<ComboboxSelected>>",
                            lambda e: self._weapon_changed())
        ttk.Label(r1, text="魔法 +").pack(side="left", padx=(6, 0))
        self.wmagic_var = tk.IntVar(value=0)
        ttk.Spinbox(r1, from_=0, to=3, width=3, textvariable=self.wmagic_var,
                    command=self._weapon_changed).pack(side="left")
        ttk.Button(r1, text="掷攻击", style="Mini.TButton",
                   command=self._attack_roll).pack(side="right", padx=2)
        ttk.Button(r1, text="掷伤害", style="Mini.TButton",
                   command=self._damage_roll).pack(side="right")
        # 攻击/伤害摘要单独一行: 文本长度随武器变化, 放 r1 里会把整页撑宽
        rb = ttk.Frame(wf)
        rb.pack(fill="x", pady=(2, 0))
        ttk.Label(rb, text="副手:").pack(side="left")
        self.offhand_cb = ttk.Combobox(rb, state="readonly", width=19,
                                       values=["（无）"])
        self.offhand_cb.pack(side="left", padx=4)
        self.offhand_cb.bind("<<ComboboxSelected>>",
                             lambda e: self._offhand_changed())
        ttk.Button(rb, text="副手攻击", style="Mini.TButton",
                   command=self._offhand_attack).pack(side="right", padx=2)
        ar = ttk.Frame(wf)
        ar.pack(fill="x", pady=(2, 0))
        self.atk_lbl = ttk.Label(ar, text="", font=("", 10, "bold"),
                                 foreground=GOLD2, wraplength=470,
                                 justify="left")
        self.atk_lbl.pack(side="left", anchor="w")
        self.grip_var = tk.BooleanVar(value=False)
        self.grip_chk = ttk.Checkbutton(
            ar, text="双手持用", variable=self.grip_var,
            command=self._grip_changed)
        self.grip_chk.pack(side="left", padx=(6, 0))
        r2 = ttk.Frame(wf)
        r2.pack(fill="x", pady=(2, 0))
        ttk.Label(r2, text="战斗风格:").pack(side="left")
        self.style_cb = ttk.Combobox(
            r2, state="readonly", width=26,
            values=["（无）"] + [v[0] for v in consts.FIGHTING_STYLES.values()])
        self.style_cb.pack(side="left", padx=4)
        self.style_cb.bind("<<ComboboxSelected>>",
                           lambda e: self._style_changed())
        self.style_note = ttk.Label(r2, text="", style="Dim.TLabel")
        self.style_note.pack(side="left", padx=6)

        mf = ttk.LabelFrame(t3, text="魔法物品 / 饰品 (勾选即自动计入)", padding=4)
        mf.pack(fill="x", pady=(4, 0))
        # 140 件全平铺会撑爆标签页: 分类筛选 + 固定高度滚动区
        fr = ttk.Frame(mf)
        fr.pack(fill="x", pady=(0, 2))
        ttk.Label(fr, text="分类", style="Dim.TLabel").pack(side="left")
        self.item_filter_var = tk.StringVar(value="全部")
        self.item_filter_cb = ttk.Combobox(
            fr, state="readonly", width=6, textvariable=self.item_filter_var,
            values=[cn for cn, _k in ITEM_KINDS])
        self.item_filter_cb.pack(side="left", padx=4)
        self.item_filter_cb.bind("<<ComboboxSelected>>",
                                 lambda e: self._item_filter_changed())
        self.item_count_lbl = ttk.Label(fr, text="", style="Dim.TLabel")
        self.item_count_lbl.pack(side="left", padx=6)
        self.item_scroll = ScrollFrame(mf, height=76)
        self.item_scroll.pack(fill="x")
        self.item_grid = self.item_scroll.body
        self.item_vars = {}
        self.item_cbs = {}
        for it in consts.MAGIC_ITEMS:
            self.item_vars[it["id"]] = tk.BooleanVar()
        self._build_item_grid()
        # 提示行必须在滚动区外 (固定底部), 否则会被物品格压在中间
        self.item_hint = tk.Label(mf, text="鼠标停在物品上可看效果",
                                  bg=BG, fg=DIM, wraplength=520,
                                  justify="left", anchor="nw", height=2)
        self.item_hint.pack(fill="x", pady=(2, 0))

        ttk.Label(t3, text="加成明细 (自动计算来源)", style="H2.TLabel").pack(
            anchor="w", pady=(2, 0))
        self.bonus_text = tk.Text(t3, height=2, wrap="word", state="disabled",
                                  **TEXT_STYLE, width=1)
        self.bonus_text.pack(fill="x", pady=2)

        lw = ttk.Frame(t3)
        lw.pack(fill="x", pady=(2, 0))
        ttk.Label(lw, text="武器专精 (长休可换)", style="H2.TLabel"
                  ).pack(side="left")
        ttk.Button(lw, text="编辑…", style="Mini.TButton",
                   command=self._edit_mastery).pack(side="left", padx=8)
        self.mastery_list = tk.Listbox(t3, height=2, **LISTBOX_STYLE)
        self.mastery_list.pack(fill="x", pady=2)

        ttk.Label(t3, text="装备清单 (自由文本)", style="H2.TLabel").pack(
            anchor="w", pady=(2, 0))
        self.eq_text = tk.Text(t3, height=2, wrap="word", **TEXT_STYLE, width=1)
        self.eq_text.pack(fill="both", expand=True, pady=2)
        self.eq_text.bind("<FocusOut>", lambda e: self._notes_changed())

        # ---- 职业: 资源池 / 职业特性 / 子职介绍 ----
        t6 = ttk.Frame(nb, padding=8)
        self.tab_class = t6
        nb.add(t6, text=" 职 业 ")
        ttk.Label(t6, text="资源可手动增减；短休/长休会按规则自动恢复。",
                  style="Dim.TLabel").pack(anchor="w", side="bottom")
        self.class_scroll = ScrollFrame(t6, height=462)
        self.class_scroll.pack(fill="both", expand=True)
        self.class_body = self.class_scroll.body

        # ---- 专长·特性 ----
        t4 = ttk.Frame(nb, padding=8)
        self.tab_feats = t4
        nb.add(t4, text=" 专长·特性 ")
        ttk.Label(t4, text="专长 (点选看效果)", style="H2.TLabel").pack(anchor="w")
        fr = ttk.Frame(t4)
        fr.pack(fill="x", pady=(4, 0))
        self.feat_list = tk.Listbox(fr, height=5, **LISTBOX_STYLE)
        self.feat_list.pack(side="left", fill="both", expand=True)
        self.feat_list.bind("<<ListboxSelect>>", self._on_feat_select)
        fb = ttk.Frame(fr)
        fb.pack(side="left", padx=(6, 0))
        ttk.Button(fb, text="+ 添加", command=self._add_feat
                   ).pack(fill="x", pady=2)
        ttk.Button(fb, text="− 移除", command=self._del_feat
                   ).pack(fill="x", pady=2)
        self.feat_info = tk.Label(t4, text="点选专长查看效果说明",
                                  bg=BG, fg=DIM, wraplength=560,
                                  justify="left", anchor="nw", height=3)
        self.feat_info.pack(anchor="w", pady=(4, 0))
        ttk.Label(t4, text="※ 自动计入数值: Tough (每级 HP+2)、Alert (先攻 +熟练)；"
                           "其余专长按说明手动应用。",
                  style="Dim.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(2, 0))
        ttk.Label(t4, text="种族特性 / 背景", style="H2.TLabel").pack(
            anchor="w", pady=(8, 0))
        self.trait_text = tk.Text(t4, height=10, wrap="word", state="disabled",
                                  **TEXT_STYLE, width=1)
        self.trait_text.pack(fill="both", expand=True, pady=4)

        # ---- 笔记 ----
        t5 = ttk.Frame(nb, padding=8)
        nb.add(t5, text=" 笔 记 ")
        ttk.Label(t5, text="语言 (通用语外自选 2 门, 逗号分隔):",
                  style="H2.TLabel").pack(anchor="w")
        self.lang_entry = ttk.Entry(t5)
        self.lang_entry.pack(fill="x", pady=2)
        self.lang_entry.bind("<FocusOut>", lambda e: self._lang_changed())
        ttk.Label(t5, text="备注 / 法术列表 / 背景故事:",
                  style="H2.TLabel").pack(anchor="w", pady=(8, 0))
        self.note_text = tk.Text(t5, wrap="word", **TEXT_STYLE, width=1)
        self.note_text.pack(fill="both", expand=True, pady=2)
        self.note_text.bind("<FocusOut>", lambda e: self._notes_changed())

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
            self.item_cbs[it["id"]] = cb
        self.item_count_lbl.config(text=f"{len(rows)} 件")
        self.item_grid.update_idletasks()

    def _item_filter_changed(self):
        self._build_item_grid()

    def _build_right(self):
        # 状态
        cf = ttk.LabelFrame(self.col_right, text=" 状态 (会与检定联动) ", padding=8)
        cf.pack(fill="x")
        self.cond_vars = {}
        grid = ttk.Frame(cf)
        grid.pack(anchor="w")
        for i, cond in enumerate(consts.CONDITIONS):
            v = tk.BooleanVar()
            self.cond_vars[cond] = v
            cb = ttk.Checkbutton(grid, text=cond, variable=v,
                                 command=lambda cn=cond: self._cond_toggled(cn))
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=4)
            cb.bind("<Enter>", lambda e, cn=cond: self._cond_hint(cn))
        self.cond_hint = tk.Label(cf, text="鼠标停在状态名上可看效果",
                                  bg=BG, fg=DIM, wraplength=262,
                                  justify="left", anchor="nw", height=2)
        self.cond_hint.pack(anchor="w", pady=(4, 0))
        exf = ttk.Frame(cf)
        exf.pack(anchor="w", pady=(8, 0))
        ttk.Label(exf, text="力竭等级:").pack(side="left")
        self.exh_var = tk.IntVar()
        ttk.Spinbox(exf, from_=0, to=6, width=3, textvariable=self.exh_var,
                    command=self._exh_changed).pack(side="left", padx=4)
        ttk.Label(exf, text="(每级 d20-2 · 速度-5尺)",
                  style="Dim.TLabel").pack(side="left")
        self.exh_warn = ttk.Label(cf, text="", foreground="#e05c4d")
        self.exh_warn.pack(anchor="w")

        # 濒死 / 死亡豁免 (2024: 3 成功稳定, 3 失败死亡)
        dyf = ttk.Frame(cf)
        dyf.pack(anchor="w", pady=(6, 0))
        ttk.Label(dyf, text="☠ 濒死").pack(side="left")
        self.death_lbl = ttk.Label(dyf, text="✓0 ✗0", foreground="#e05c4d")
        self.death_lbl.pack(side="left", padx=4)
        ttk.Button(dyf, text="掷", width=3, style="Mini.TButton",
                   command=self._death_save).pack(side="left", padx=2)
        ttk.Button(dyf, text="重置", width=4, style="Mini.TButton",
                   command=self._death_reset).pack(side="left")

        # 专注检定 (受伤时 DC = max(10, 伤害/2))
        ccf = ttk.Frame(cf)
        ccf.pack(anchor="w", pady=(4, 0))
        ttk.Button(ccf, text="专注检定", style="Mini.TButton",
                   command=self._conc_check).pack(side="left")
        self.conc_lbl = ttk.Label(ccf, text="专注: —", style="Dim.TLabel")
        self.conc_lbl.pack(side="left", padx=6)

        # 快捷骰子
        qf = ttk.LabelFrame(self.col_right, text=" 快捷骰子 ", padding=8)
        qf.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(qf)
        row.pack()
        for n in (4, 6, 8, 10, 12, 20):
            ttk.Button(row, text=f"d{n}", width=4, style="Mini.TButton",
                       command=lambda x=n: self._quick_die(x)
                       ).pack(side="left", padx=2, pady=2)

        # 掷骰记录
        lg = ttk.LabelFrame(self.col_right, text=" 掷骰记录 ", padding=8)
        lg.pack(fill="both", expand=True, pady=(8, 0))
        self.roll_log = tk.Listbox(lg, **LISTBOX_STYLE)
        self.roll_log.pack(fill="both", expand=True)
        ttk.Button(lg, text="清空记录", style="Mini.TButton",
                   command=lambda: self.roll_log.delete(0, "end")
                   ).pack(anchor="e", pady=(4, 0))

    def _build_status(self):
        self.status = ttk.Label(
            self, text="欢迎来到 D&D 5.5e 人物卡 —— 点击工具栏「✦ 新建角色」开始冒险",
            style="Dim.TLabel", anchor="w", padding=(12, 5))
        self.status.pack(fill="x", side="bottom")

    # ---- 刷新 ----
