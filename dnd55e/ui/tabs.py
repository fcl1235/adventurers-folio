"""中间栏的六个标签页 (构建期)。

从 ui_shell._build_mid (原 252 行) 拆出。每个 `build_*` 函数只负责搭控件、
把控件挂到 app 上, 不负责刷新数值 —— 数值由 ui_sheet.refresh 填。

**标签页的创建顺序不能变**: 技能 / 法术 / 装备·加成 / 职业 / 专长·特性 / 笔记,
`_layoutcheck.py` 按顺序比对各页尺寸。
"""
import tkinter as tk
from tkinter import ttk

from .. import consts
from ..consts import ABILITY_CN
from ..theme import (DIM, GOLD2, HintText, LISTBOX_STYLE, ScrollFrame,
                     TEXT_STYLE, UI_FONT)

# 物品分类筛选: (显示名, kind 值；None = 全部)
ITEM_KINDS = [("全部", None), ("戒指", "ring"), ("斗篷", "cloak"),
              ("护甲盾牌", "armor"), ("武器", "weapon"), ("魔杖", "wand"),
              ("法杖", "staff"), ("弹药", "ammunition"), ("奇物", "wondrous")]


def build_skills(app, nb):
    """技能页。"""
    t1 = ttk.Frame(nb, padding=8)
    app.tab_skills = t1
    nb.add(t1, text=" 技 能 ")
    ttk.Label(t1, text="🎲=掷检定   ✓=熟练   ◇/◆=专精 Expertise "
                       "(需先熟练, 双倍熟练加值)",
              style="Dim.TLabel").pack(anchor="w", pady=(0, 2))
    app.skill_hint = HintText(t1, text="鼠标停在技能名上可看它管什么检定",
                              fg=DIM, height=2, wraplength=430)
    app.skill_hint.pack(anchor="w", pady=(0, 6))
    grid = ttk.Frame(t1)
    grid.pack(fill="both", expand=True)
    app.skill_vars, app.skill_modlbls = {}, {}
    app.skill_namelbls, app.skill_expbtns = {}, {}
    F = UI_FONT
    for i, s in enumerate(app.rules.d["skills"]):
        sid = s["id"]
        r, col = i % 9, i // 9
        row = ttk.Frame(grid)
        row.grid(row=r, column=col, sticky="w", padx=(0, 26), pady=3)
        ttk.Button(row, text="🎲", width=3, style="Mini.TButton",
                   command=lambda x=sid: app._roll_skill(x)
                   ).pack(side="left")
        v = tk.BooleanVar()
        app.skill_vars[sid] = v
        ttk.Checkbutton(row, variable=v, width=2,
                        command=lambda x=sid: app._skill_toggled(x)
                        ).pack(side="left")
        nl = ttk.Label(row, text=s["name"].split(" ")[0], width=8,
                       anchor="w")
        nl.pack(side="left")
        nl.bind("<Enter>", lambda e, x=sid: app._skill_hover(x))
        ab = ttk.Label(row, text=ABILITY_CN[s["ability"]], width=3,
                       style="Dim.TLabel")
        ab.pack(side="left")
        app.skill_namelbls[sid] = nl
        ml = ttk.Label(row, text="+0", width=4, font=(F, 10, "bold"))
        ml.pack(side="left")
        app.skill_modlbls[sid] = ml
        eb = ttk.Button(row, text="◇", width=3, style="Mini.TButton",
                        command=lambda x=sid: app._toggle_expertise(x))
        eb.pack(side="left", padx=(2, 0))
        app.skill_expbtns[sid] = eb
    return t1


def build_spells(app, nb):
    """法术页。"""
    t2 = ttk.Frame(nb, padding=8)
    app.tab_spells = t2
    nb.add(t2, text=" 法 术 ")
    head = ttk.Frame(t2)
    head.pack(fill="x")
    app.slots_head = ttk.Label(head, text="", style="H2.TLabel")
    app.slots_head.pack(side="left")
    # 法师才有法术书 (其它职业在 refresh 里保持隐藏)
    app.spellbook_btn = ttk.Button(head, text="📖 法术书 (0)",
                                   style="Mini.TButton",
                                   command=app._spellbook_open)
    app.slots_frame = ttk.Frame(t2)
    app.slots_frame.pack(anchor="nw", pady=(2, 4))
    app.slots_widgets = {}

    bar = ttk.Frame(t2)
    bar.pack(fill="x", pady=2)
    app.spell_add_cb = ttk.Combobox(bar, state="readonly", width=24)
    app.spell_add_cb.pack(side="left")
    app.spell_add_btn = ttk.Button(bar, text="＋ 学习", style="Mini.TButton",
                                   command=app._spell_add)
    app.spell_add_btn.pack(side="left", padx=3)
    ttk.Button(bar, text="－ 移除", style="Mini.TButton",
               command=app._spell_del).pack(side="left")
    ttk.Button(bar, text="▶ 施放", style="Gold.TButton",
               command=app._spell_cast).pack(side="right")
    ttk.Button(bar, text="◉ 专注", style="Mini.TButton",
               command=app._spell_focus).pack(side="right", padx=3)
    app.spell_quota_lbl = ttk.Label(t2, text="", style="Dim.TLabel")
    app.spell_quota_lbl.pack(anchor="w", pady=(2, 0))

    app.spell_list = tk.Listbox(t2, height=7, **LISTBOX_STYLE)
    app.spell_list.pack(fill="x", pady=2)
    app.spell_list.bind("<<ListboxSelect>>", app._spell_show)
    ttk.Label(t2, text="法术详情", style="H2.TLabel").pack(
        anchor="w", pady=(2, 0))
    app.spell_detail = tk.Text(t2, height=7, wrap="word", state="disabled",
                               **TEXT_STYLE, width=1)
    app.spell_detail.pack(fill="both", expand=True, pady=2)
    ttk.Label(t2, text="● 剩余环位 ○ 已用；戏法不耗环位；"
                       "专注法术同时只能维持一个。",
              style="Dim.TLabel", wraplength=520,
              justify="left").pack(anchor="w", side="bottom")
    return t2


def build_gear(app, nb):
    """装备·加成页。"""
    t3 = ttk.Frame(nb, padding=6)
    nb.add(t3, text=" 装备·加成 ")
    wf = ttk.LabelFrame(t3, text="武器与攻击", padding=4)
    wf.pack(fill="x")
    r1 = ttk.Frame(wf)
    r1.pack(fill="x")
    ttk.Label(r1, text="武器:").pack(side="left")
    app.weapon_cb = ttk.Combobox(r1, state="readonly", width=19,
                                 values=["（未装备）"]
                                 + [w[0] for w in consts.WEAPONS])
    app.weapon_cb.pack(side="left", padx=4)
    app.weapon_cb.bind("<<ComboboxSelected>>",
                       lambda e: app._weapon_changed())
    ttk.Label(r1, text="魔法 +").pack(side="left", padx=(6, 0))
    app.wmagic_var = tk.IntVar(value=0)
    ttk.Spinbox(r1, from_=0, to=3, width=3, textvariable=app.wmagic_var,
                command=app._weapon_changed).pack(side="left")
    ttk.Button(r1, text="掷攻击", style="Mini.TButton",
               command=app._attack_roll).pack(side="right", padx=2)
    ttk.Button(r1, text="掷伤害", style="Mini.TButton",
               command=app._damage_roll).pack(side="right")
    # 攻击/伤害摘要单独一行: 文本长度随武器变化, 放 r1 里会把整页撑宽
    rb = ttk.Frame(wf)
    rb.pack(fill="x", pady=(2, 0))
    ttk.Label(rb, text="副手:").pack(side="left")
    app.offhand_cb = ttk.Combobox(rb, state="readonly", width=19,
                                  values=["（无）"])
    app.offhand_cb.pack(side="left", padx=4)
    app.offhand_cb.bind("<<ComboboxSelected>>",
                        lambda e: app._offhand_changed())
    ttk.Button(rb, text="副手攻击", style="Mini.TButton",
               command=app._offhand_attack).pack(side="right", padx=2)
    ar = ttk.Frame(wf)
    ar.pack(fill="x", pady=(2, 0))
    app.atk_lbl = ttk.Label(ar, text="", font=("", 10, "bold"),
                            foreground=GOLD2, wraplength=470,
                            justify="left")
    app.atk_lbl.pack(side="left", anchor="w")
    app.grip_var = tk.BooleanVar(value=False)
    app.grip_chk = ttk.Checkbutton(
        ar, text="双手持用", variable=app.grip_var,
        command=app._grip_changed)
    app.grip_chk.pack(side="left", padx=(6, 0))
    r2 = ttk.Frame(wf)
    r2.pack(fill="x", pady=(2, 0))
    ttk.Label(r2, text="战斗风格:").pack(side="left")
    app.style_cb = ttk.Combobox(
        r2, state="readonly", width=26,
        values=["（无）"] + [v[0] for v in consts.FIGHTING_STYLES.values()])
    app.style_cb.pack(side="left", padx=4)
    app.style_cb.bind("<<ComboboxSelected>>",
                      lambda e: app._style_changed())
    app.style_note = ttk.Label(r2, text="", style="Dim.TLabel")
    app.style_note.pack(side="left", padx=6)

    mf = ttk.LabelFrame(t3, text="魔法物品 / 饰品 (勾选即自动计入)", padding=4)
    mf.pack(fill="x", pady=(4, 0))
    # 140 件全平铺会撑爆标签页: 分类筛选 + 固定高度滚动区
    fr = ttk.Frame(mf)
    fr.pack(fill="x", pady=(0, 2))
    ttk.Label(fr, text="分类", style="Dim.TLabel").pack(side="left")
    app.item_filter_var = tk.StringVar(value="全部")
    app.item_filter_cb = ttk.Combobox(
        fr, state="readonly", width=6, textvariable=app.item_filter_var,
        values=[cn for cn, _k in ITEM_KINDS])
    app.item_filter_cb.pack(side="left", padx=4)
    app.item_filter_cb.bind("<<ComboboxSelected>>",
                            lambda e: app._item_filter_changed())
    app.item_count_lbl = ttk.Label(fr, text="", style="Dim.TLabel")
    app.item_count_lbl.pack(side="left", padx=6)
    app.item_scroll = ScrollFrame(mf, height=76)
    app.item_scroll.pack(fill="x")
    app.item_grid = app.item_scroll.body
    app.item_vars = {}
    app.item_cbs = {}
    for it in consts.MAGIC_ITEMS:
        app.item_vars[it["id"]] = tk.BooleanVar()
    app._build_item_grid()
    # 提示行必须在滚动区外 (固定底部), 否则会被物品格压在中间
    app.item_hint = HintText(mf, text="鼠标停在物品上可看效果",
                             fg=DIM, height=2, wraplength=520)
    app.item_hint.pack(fill="x", pady=(2, 0))

    ttk.Label(t3, text="加成明细 (自动计算来源)", style="H2.TLabel").pack(
        anchor="w", pady=(2, 0))
    app.bonus_text = tk.Text(t3, height=2, wrap="word", state="disabled",
                             **TEXT_STYLE, width=1)
    app.bonus_text.pack(fill="x", pady=2)

    lw = ttk.Frame(t3)
    lw.pack(fill="x", pady=(2, 0))
    ttk.Label(lw, text="武器专精 (长休可换)", style="H2.TLabel"
              ).pack(side="left")
    ttk.Button(lw, text="编辑…", style="Mini.TButton",
               command=app._edit_mastery).pack(side="left", padx=8)
    app.mastery_list = tk.Listbox(t3, height=2, **LISTBOX_STYLE)
    app.mastery_list.pack(fill="x", pady=2)

    ttk.Label(t3, text="装备清单 (自由文本)", style="H2.TLabel").pack(
        anchor="w", pady=(2, 0))
    app.eq_text = tk.Text(t3, height=2, wrap="word", **TEXT_STYLE, width=1)
    app.eq_text.pack(fill="both", expand=True, pady=2)
    app.eq_text.bind("<FocusOut>", lambda e: app._notes_changed())
    return t3


def build_class(app, nb):
    """职业页 (内容由 ui_sheet._render_class_tab 填)。"""
    t6 = ttk.Frame(nb, padding=8)
    app.tab_class = t6
    nb.add(t6, text=" 职 业 ")
    ttk.Label(t6, text="资源可手动增减；短休/长休会按规则自动恢复。",
              style="Dim.TLabel").pack(anchor="w", side="bottom")
    app.class_scroll = ScrollFrame(t6, height=462)
    app.class_scroll.pack(fill="both", expand=True)
    app.class_body = app.class_scroll.body
    return t6


def build_feats(app, nb):
    """专长·特性页。"""
    t4 = ttk.Frame(nb, padding=8)
    app.tab_feats = t4
    nb.add(t4, text=" 专长·特性 ")
    ttk.Label(t4, text="专长 (点选看效果)", style="H2.TLabel").pack(anchor="w")
    fr = ttk.Frame(t4)
    fr.pack(fill="x", pady=(4, 0))
    app.feat_list = tk.Listbox(fr, height=5, **LISTBOX_STYLE)
    app.feat_list.pack(side="left", fill="both", expand=True)
    app.feat_list.bind("<<ListboxSelect>>", app._on_feat_select)
    fb = ttk.Frame(fr)
    fb.pack(side="left", padx=(6, 0))
    ttk.Button(fb, text="+ 添加", command=app._add_feat
               ).pack(fill="x", pady=2)
    ttk.Button(fb, text="− 移除", command=app._del_feat
               ).pack(fill="x", pady=2)
    app.feat_info = HintText(t4, text="点选专长查看效果说明",
                             fg=DIM, height=3, wraplength=560)
    app.feat_info.pack(anchor="w", pady=(4, 0))
    ttk.Label(t4, text="※ 自动计入数值: Tough (每级 HP+2)、"
                       "Alert (先攻 +熟练)；其余专长按说明手动应用。",
              style="Dim.TLabel", wraplength=560,
              justify="left").pack(anchor="w", pady=(2, 0))
    ttk.Label(t4, text="种族特性 / 背景", style="H2.TLabel").pack(
        anchor="w", pady=(8, 0))
    app.trait_text = tk.Text(t4, height=10, wrap="word", state="disabled",
                             **TEXT_STYLE, width=1)
    app.trait_text.pack(fill="both", expand=True, pady=4)
    return t4


def build_notes(app, nb):
    """笔记页。"""
    t5 = ttk.Frame(nb, padding=8)
    nb.add(t5, text=" 笔 记 ")
    ttk.Label(t5, text="语言 (通用语外自选 2 门, 逗号分隔):",
              style="H2.TLabel").pack(anchor="w")
    app.lang_entry = ttk.Entry(t5)
    app.lang_entry.pack(fill="x", pady=2)
    app.lang_entry.bind("<FocusOut>", lambda e: app._lang_changed())
    ttk.Label(t5, text="备注 / 法术列表 / 背景故事:",
              style="H2.TLabel").pack(anchor="w", pady=(8, 0))
    app.note_text = tk.Text(t5, wrap="word", **TEXT_STYLE, width=1)
    app.note_text.pack(fill="both", expand=True, pady=2)
    app.note_text.bind("<FocusOut>", lambda e: app._notes_changed())
    return t5


# 顺序即标签页顺序, 不能改
BUILDERS = (build_skills, build_spells, build_gear,
            build_class, build_feats, build_notes)


def build_all(app, nb):
    """按固定顺序建六个标签页。"""
    for fn in BUILDERS:
        fn(app, nb)
