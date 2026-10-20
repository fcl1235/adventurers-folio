"""左右栏与英雄卡: 搭建控件, 数值由 ui_sheet.refresh 填。"""
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


class PanelsMixin():
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

        self.ab_hint = HintText(ab, text="鼠标停在属性名上可看该属性的用途",
                                fg=DIM, height=2, wraplength=286)
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
        self.cond_hint = HintText(cf, text="鼠标停在状态名上可看效果",
                                  fg=DIM, height=2, wraplength=262)
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
