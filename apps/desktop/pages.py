# -*- coding: utf-8 -*-
"""角色卡的四个页面。每个页面只做一件事：把 sheet 里的一段画出来。

页面不持有规则，也不缓存派生值 —— `refresh(sheet)` 每次都整块重画。
缓存派生值是旧程序最容易出漂的地方（改了一件装备，三个地方还在用旧 AC）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .i18n import T, join
from . import theme
from .cards import AbilityCard
from .dice import DiceLog
from .widgets import (ABILITY_ZH, CARD_LEFT, COL_MID, COL_RIGHT, GridTable,
                      KeyValue, RollGrid, hit_dice_text, section, sense_text)

ABILITY_ORDER = ("str", "dex", "con", "int", "wis", "cha")
# 列宽是**字符数**（ttk.Label 的单位）。像素预算由布局审计现量 reqwidth 得出，
# 不在这里手算 —— 字体一变手算的值就废了。
SKILL_COLUMNS = [("技能", 10), ("属性", 5), ("加值", 5), ("熟练", 5), ("明细", 24)]
ATTACK_COLUMNS = [("武器", 12), ("命中", 5), ("伤害", 11)]


def _signed(value: int) -> str:
    return "%+d" % int(value)


def _mode_mark(row: dict) -> str:
    """优势/劣势的短标记。页面只负责显示，判断来自 sheet 的 `mode`。"""
    mode = row.get("mode")
    if mode == "adv":
        return T("（优势）")
    if mode == "dis":
        return T("（劣势）")
    return ""


class OverviewPage(ttk.Frame):
    """概览：六属性卡 / 18 技能 / 战斗数值与攻击。

    左栏是**六张属性卡**（2 列 × 3 行），不是一张文本表：调整值 18pt 金色是卡面主角，
    分数与豁免是配角。旧程序就是这样，一眼能读出「我力量 +4」。
    """

    def __init__(self, master, on_roll=None, on_action=None) -> None:
        super().__init__(master, padding=(6, 4))
        self._on_roll = on_roll
        self._on_action = on_action
        self._build()

    def _build(self) -> None:
        left = ttk.Frame(self, width=CARD_LEFT)
        mid = ttk.Frame(self, width=COL_MID)
        right = ttk.Frame(self, width=COL_RIGHT)
        left.grid(row=0, column=0, sticky="nsw")
        mid.grid(row=0, column=1, sticky="nsew", padx=8)
        right.grid(row=0, column=2, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        # 三栏留个引用：布局审计要单独量某一栏（整页 reqheight 是取最高的那一栏，
        # 左栏加了属性编辑行也不会让页面变高，光看整页会以为「加了没影响」）。
        self.left, self.mid, self.right = left, mid, right

        # --- 左：六张属性卡 ------------------------------------------------
        # 宽度靠 `grid columnconfigure(minsize=148, weight=1)` 撑 —— `ttk.Frame(width=)`
        # **不约束 reqsize**（实测概览常量合计 1176，页面 req 只有 793），
        # 写 width= 是撑不出 320 的。
        box = section(left, T("属性"))
        box.pack(fill="x")
        grid = ttk.Frame(box)
        grid.pack(fill="x")
        self.ability_cards: dict[str, AbilityCard] = {}
        for index, key in enumerate(ABILITY_ORDER):
            card = AbilityCard(grid, key, ABILITY_ZH[key])
            card.grid(row=index // 2, column=index % 2,
                      sticky="nsew", padx=4, pady=3)
            self.ability_cards[key] = card
        for column in (0, 1):
            grid.columnconfigure(column, minsize=148, weight=1)
        # 「检 / 豁」按钮接上掷骰。`on_roll(kind, key)` 由外壳注入 ——
        # 页面自己不碰 api，掷完的记录也归外壳管。
        if self._on_roll is not None:
            for key, card in self.ability_cards.items():
                card.set_roll_callbacks(
                    lambda attribute=key: self._roll("ability", attribute),
                    lambda attribute=key: self._roll("save", attribute),
                )

        # --- 左：属性就地编辑 ---------------------------------------------
        # 收起时只占一行按钮。**改的是原始属性**（`Profile.base_scores`）：
        # 卡面上显示的分数里混着专长与子职加值，从来回倒推减不掉那些加值，
        # 所以界面必须把「建卡时填的那个数」原样拿来做输入框的初值。
        self.edit_toggle = ttk.Button(box, text=T("编辑属性"), style="Mini.TButton",
                                      width=8, command=self.toggle_edit)
        self.edit_toggle.pack(anchor="e", pady=(2, 0))
        self.edit_row = ttk.Frame(box)
        self.score_vars: dict[str, tk.IntVar] = {}
        for index, key in enumerate(ABILITY_ORDER):
            cell = ttk.Frame(self.edit_row)
            cell.grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 6), pady=1)
            ttk.Label(cell, text=ABILITY_ZH[key], style="Dim.TLabel").pack(side="left")
            var = tk.IntVar(value=10)
            ttk.Spinbox(cell, from_=1, to=30, width=3, textvariable=var,
                        justify="center").pack(side="left", padx=(3, 0))
            self.score_vars[key] = var
        buttons = ttk.Frame(self.edit_row)
        buttons.grid(row=2, column=0, columnspan=3, sticky="e", pady=(2, 0))
        self.apply_scores_button = ttk.Button(buttons, text=T("应用"), style="Mini.TButton",
                                              width=5, command=self._apply_scores)
        self.apply_scores_button.pack(side="left")
        ttk.Button(buttons, text=T("取消"), style="Mini.TButton", width=5,
                   command=lambda: self.toggle_edit(False)).pack(side="left", padx=(4, 0))
        self.base_scores: dict[str, int] = {}
        self._build_error = ttk.Label(box, text="", style="Dim.TLabel",
                                      wraplength=290, justify="left")

        # --- 中：技能 + 熟练工具 ---------------------------------------------
        # 工具**只列熟练的**，且用一行折行文本而不是小表：全 37 件铺在卡上会把
        # 18 项技能挤没，而未熟练的工具本来也不需要常驻 —— 真要掷，
        # `api.roll_check(kind="tool")` 任意指定都行。一行文本还不会随熟练数长高。
        # 打包顺序：先把底部这块 `side="bottom"` 钉住，再让技能吃掉剩余空间。
        self.tools_var = tk.StringVar(value="")
        tools = section(mid, T("熟练与精通"), T("工具熟练 / 武器精通（命中后结算）"))
        tools.pack(side="bottom", fill="x", pady=(6, 0))
        self.tools_label = ttk.Label(tools, textvariable=self.tools_var,
                                     wraplength=400, justify="left")
        self.tools_label.pack(anchor="w")
        # 武器精通是 2024 的核心新机制：以前只在建卡向导与装备页逐件出现，
        # 建完卡在卡面上找不到「我精通哪几件」。一行折行文本，不随件数长高。
        # **wraplength 必须小于中栏宽度（约 441）**：中栏是被技能表撑开的，
        # 这里给 560 会把整页顶到 1237（窗口只有 1122）—— 实测踩过。
        self.mastery_var = tk.StringVar(value="")
        self.mastery_label = ttk.Label(tools, textvariable=self.mastery_var,
                                       style="Dim.TLabel", wraplength=400,
                                       justify="left")
        self.mastery_label.pack(anchor="w", pady=(2, 0))

        skills = section(mid, T("技能"), T("熟练加熟练加值，专精再加一份；明细在右侧说明栏"))
        skills.pack(fill="both", expand=True)
        self.skills = RollGrid(skills, SKILL_COLUMNS, rows=18,
                               on_roll=lambda key: self._roll("skill", key))
        self.skills.pack(fill="both", expand=True)

        # --- 右：战斗数值 + 攻击 + 掷骰记录（全部定高，不滚动）------------------
        # 打包顺序是铁律：**先 side="bottom" 钉住记录**，再让上面的区块吃剩余空间。
        # 反过来做，内容一长记录就被挤到看不见的地方。
        #
        # 这里**不用 ScrollFrame**：以前右栏是 Canvas 里嵌一个 1121px 的 Frame
        # 塞进 402px 的视口，滚动时旧位置不擦，整块内容重影（「倒地」两遍）。
        # 状态面板搬去「状态」页之后，剩下的两块定高就够，不需要滚动。
        dice = section(right, T("掷骰记录"))
        dice.pack(side="bottom", fill="x", pady=(4, 0))
        self.dice_log = DiceLog(dice, height=5, width=30)
        self.dice_log.pack(fill="both", expand=True)

        body = right
        fight = section(body, T("战斗"))
        fight.pack(fill="x")
        # 抗性/感官以前全仓库零显示点（§P6 方案里点名过的缺口），一并补在这里
        self.fight = KeyValue(fight, rows=10)
        self.fight.pack(fill="x", pady=(0, 6))

        attacks = section(body, T("攻击"))
        attacks.pack(fill="x", pady=(6, 0))
        self.attacks = GridTable(attacks, ATTACK_COLUMNS, rows=8)
        self.attacks.pack(fill="x")

    def _roll(self, kind: str, key: str) -> None:
        if self._on_roll is not None:
            self._on_roll(kind, key)

    # --- 属性编辑 ---------------------------------------------------------
    def toggle_edit(self, open_: bool | None = None) -> None:
        """展开/收起属性输入行。默认按当前状态切换。"""
        expanded = bool(self.edit_row.winfo_manager())
        want = (not expanded) if open_ is None else bool(open_)
        if want:
            self._load_scores()
            if not expanded:
                self.edit_row.pack(fill="x", pady=(4, 0))
            self.edit_toggle.configure(text=T("收起"))
        else:
            if expanded:
                self.edit_row.pack_forget()
            self.edit_toggle.configure(text=T("编辑属性"))
            self._set_edit_error("")

    def _load_scores(self) -> None:
        """初值必须是**原始属性**。没有记录时退回卡面分数并说明：那已经含了加值，
        照着改会把专长加值吃掉一层。"""
        for key, var in self.score_vars.items():
            value = self.base_scores.get(key)
            if value is None:
                value = int((self._shown_scores or {}).get(key, 10))
            var.set(int(value))

    def _apply_scores(self) -> None:
        scores = {}
        for key, var in self.score_vars.items():
            try:
                scores[key] = int(var.get())
            except (tk.TclError, ValueError):
                self._set_edit_error(T("「%s」不是整数") % ABILITY_ZH[key])
                return
        if self._on_action is None:
            return
        if self._on_action("scores", scores):
            self.toggle_edit(False)

    def _set_edit_error(self, text: str) -> None:
        self._build_error.configure(text=text, foreground=theme.WARN if text else theme.DIM)
        if text:
            self._build_error.pack(anchor="w", pady=(2, 0))
        elif self._build_error.winfo_manager():
            self._build_error.pack_forget()

    def set_edit_error(self, text: str) -> None:
        """给外壳用：改属性被规则拒绝时把原因写在这行输入底下，
        而不是只在窗口底部的状态栏闪一句（那里离输入框太远，容易被忽略）。"""
        self._set_edit_error(text)

    # --- 数据 -------------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        abilities = sheet.get("abilities") or {}
        saves = sheet.get("saves") or {}
        # 属性编辑要的是**原始值**（加值之前）。卡面分数已经含了专长/子职加值，
        # 拿它当初值再「+2」会把加值吃掉一层。
        self.base_scores = dict(sheet.get("base_scores") or {})
        self._shown_scores = {key: int((abilities.get(key) or {}).get("score", 10))
                              for key in ABILITY_ORDER}
        if self.edit_row.winfo_manager():
            self._load_scores()        # 展开着的时候跟着数据走，别停在旧值上
        for key in ABILITY_ORDER:
            row = abilities.get(key) or {}
            save = saves.get(key) or {}
            self.ability_cards[key].set_values(
                mod=int(row.get("mod", 0)),
                score=int(row.get("score", 0)),
                save=int(save.get("total", 0)),
                proficient=bool(save.get("proficient")),
            )

        self.refresh_skills(sheet)
        self.refresh_tools(sheet)
        self.refresh_masteries(sheet)
        self.refresh_fight(sheet)
        self.refresh_attacks(sheet)

    def refresh_skills(self, sheet: dict) -> None:
        rows = []
        for row in sheet.get("skills") or []:
            mark = T("专精") if row.get("expertise") else (T("熟练") if row.get("proficient") else "")
            tag = "expert" if row.get("expertise") else ("prof" if row.get("proficient") else "")
            rows.append(((row["name"], row["ability"].upper(),
                          _signed(row["total"]), mark, row["detail"]), tag,
                         row["key"]))
        self.skills.fill(rows)

    def refresh_tools(self, sheet: dict) -> None:
        """只列熟练的工具，一行折行文本 —— 不随熟练数长高，版面才稳。"""
        known = [row for row in (sheet.get("tools") or []) if row.get("proficient")]
        if not known:
            self.tools_var.set(T("尚无工具熟练（%d 件工具仍可掷，指定属性即可）")
                               % len(sheet.get("tools") or ()))
            return
        self.tools_var.set(join("%s %s" % (row["name"], _signed(row["total"]))
                                     for row in known))

    def refresh_masteries(self, sheet: dict) -> None:
        """武器精通：只列**哪几件**（效果名在装备页逐件看）。

        这里刻意不带效果（「擦伤」「击倒」）：带上之后一行装不下、折成两行时
        整页高度会顶到 636/646，6 件武器名字再长一点就越过预算。卡面要回答的是
        「我精通哪几件」；每种精通的算法在装备页与遭遇战记录里，而**攻击掷骰时
        是真的会带上效果** —— 别在这行写「未结算」，那是旧实现的说法。
        """
        rows = (sheet.get("origin") or {}).get("masteries") or []
        if not rows:
            self.mastery_var.set("")
            return
        self.mastery_var.set(T("武器精通：%s")
                             % join(row["name"] for row in rows))

    def refresh_fight(self, sheet: dict) -> None:
        """0–7 行的**语义冻结**（测试按索引读，别挪）：AC/先攻/HP/速度/熟练/抗性/感官/暴击。

        8–9 是后来补的两行：生命骰 + 攻击次数合成一行、力竭一行。右栏不再滚动，
        11 行塞不进预算 —— 生命骰与攻击次数都是「战斗节奏」信息，合成一行读得通。
        """
        hp = sheet.get("hp") or {}
        speed = (sheet.get("speed") or {}).get("walk", 0)
        init = sheet.get("initiative") or {}
        self.fight.clear()
        self.fight.set_row(0, "AC", str((sheet.get("ac") or {}).get("total", 0)))
        self.fight.set_row(1, T("先攻"), _signed(init.get("total", 0)) + _mode_mark(init))
        self.fight.set_row(2, "HP", "%s/%s" % (hp.get("current", 0), hp.get("maximum", 0)))
        self.fight.set_row(3, T("速度"), T("%d 尺") % speed)
        self.fight.set_row(4, T("熟练"), _signed(sheet.get("proficiency_bonus", 0)))
        resist = sheet.get("resistances") or []
        self.fight.set_row(5, T("抗性"), join(resist) if resist else "—")
        self.fight.set_row(6, T("感官"), sense_text(sheet.get("senses") or {}) or "—")
        self.fight.set_row(7, T("暴击"), "≥ %d" % int((sheet.get("crit") or {}).get("min", 20)))
        dice = hit_dice_text(hp.get("hit_dice"), sheet.get("classes")) or "—"
        self.fight.set_row(8, T("生命骰"), T("%s · 攻击 %s")
                           % (dice, sheet.get("attacks_per_action", "—")))
        # 9 = 力竭。**这里必须写清它是真扣了的**，与状态页「只记录」相反。
        exh = sheet.get("exhaustion") or {}
        level = int(exh.get("level", 0))
        if level:
            self.fight.set_row(9, T("力竭"), T("%d 级（d20 %+d · 速度 %+d 尺）")
                               % (level, int(exh.get("penalty", 0)),
                                  int(exh.get("speed", 0))))
        else:
            self.fight.set_row(9, T("力竭"), T("无"))

    def refresh_attacks(self, sheet: dict) -> None:
        rows = []
        for row in (sheet.get("attacks") or [])[:8]:
            bonus = int(row.get("damage_bonus") or 0)
            damage = "%s%s %s" % (row.get("damage", ""),
                                  _signed(bonus) if bonus else "",
                                  row.get("damage_type", ""))
            rows.append(((row.get("name", ""), _signed(row.get("attack", 0)), damage), ""))
        self.attacks.fill(rows)
