# -*- coding: utf-8 -*-
"""建卡向导：在**主窗口内**切换的 8 步流程（P7）。

为什么不是弹窗：Tk 的 `Toplevel` 弹窗要么写死 `geometry`（内容一变按钮就消失，
旧程序吃过两次亏），要么就得复制一套 `_fit` 逻辑；而向导本身就是这个程序最
核心的入口，占满主窗口反而更合适。骨架沿用 `book` 的位置 —— `book.pack_forget()`
之后把向导 pack 上去，取消时再换回来。

三条约束写在这里，因为它们在实现里看不出来：
  * **底部按钮栏先 pack**（`side="bottom"`），再给内容 `expand=True`。
    顺序反了，内容一长按钮栏就被挤到窗口外面 —— 表现为「下一步点不到」。
  * **校验只有一处**：所有「能不能过关」都问 `api.draft_problems()`。
    界面只负责把 `step` 翻译成「标在哪一栏」，不自己判规则。
  * **不阻止跳步**。玩家可以先把物种选好再回来选职业；「完成」时才要求全绿，
    并自动跳回第一个出错的那一步。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import dnd5r.api as api

from .i18n import Catalog, T, join
from . import theme
from .pages_spells import spell_text
from .widgets import (ABILITY_ZH, MASTERY_ZH, KeyValue, ListPane, ScrollFrame,
                      Tooltip, section)

# 三种属性生成方式各自的**输入范围**。数字框与键盘校验都照这个来 ——
# 以前框写死 1–20，点买填 18 也能停在框里，只等建卡时才报错。
SCORE_BOUNDS = {
    "point_buy": (8, 15),        # 买不到 16+（加值来自背景与专长）
    "standard_array": (8, 15),   # 15/14/13/12/10/8，端点就是 8 与 15
    "roll": (3, 18),             # 4d6 弃最低的实数范围
    # 改卡：数是已经存在的，可能是 16（点买买不到，但专长/背景抬上来的）
    "edit": (8, 20),
}

# 属性框上那句说明。三种方式约束完全不同，不能共用一句话。
SCORE_NOTES = Catalog({
    "point_buy": "8–15 之间购买，16 以上只能由背景与专长提供；超支会当场标红。",
    "standard_array": "15/14/13/12/10/8 各用一次。选一个已经被别人拿走的数，"
                      "会和对方交换位置。",
    "roll": "4d6 弃最低，范围 3–18。想重掷就点「掷 4d6 弃最低」。",
    "edit": "范围 8–20。",
})


def _clear(master) -> None:
    for child in master.winfo_children():
        child.destroy()


class WizardView(ttk.Frame):
    """8 步建卡向导。`app` 只用 bundle / locale / finish_wizard / close_wizard。

    `editing=True` 表示「改现有角色」（升级后发现还差选择）：完成时走
    `api.apply_draft`（重建并保住背包/HP/资源），而不是造一个新角色。
    """

    def __init__(self, master, app, draft: dict | None = None,
                 editing: bool = False, step: int = 0) -> None:
        super().__init__(master, padding=(6, 4))
        self.app = app
        # 步骤标题是**接口层**给的文案（`wizard_steps` 按语言取），不是界面写死的
        self.steps = api.wizard_steps(self.app.locale)
        self.index = max(0, min(len(self.steps) - 1, int(step)))
        self.editing = bool(editing)
        self.draft = api.empty_draft()
        if draft:
            self.draft.update(draft)
        # 加值分配的「第几种形态」：`bonus_plans()` 的序号比 dict 更好落地
        self.bonus_index = self._index_of_bonus()
        self._build()
        self.render()

    # --- 骨架 -------------------------------------------------------------
    def _build(self) -> None:
        # 1) 底部：状态行 + 导航栏。**先 pack**，否则内容长了它们就被裁掉
        self.footer = ttk.Frame(self)
        self.footer.pack(side="bottom", fill="x", pady=(4, 0))
        self.status_var = tk.StringVar()
        self.status = ttk.Label(self.footer, textvariable=self.status_var,
                                style="Dim.TLabel", anchor="w", wraplength=900)
        self.status.pack(side="top", fill="x")
        nav = ttk.Frame(self.footer)
        nav.pack(side="top", fill="x", pady=(2, 0))
        self.buttons: dict[str, ttk.Button] = {}
        # **顺序 = 屏幕从右到左**：`side="right"` 先 pack 的贴最右，所以元组
        # 反过来写（取消 → 建卡 → 下一步 → 上一步）屏幕才是
        # 「← 上一步 | 下一步 → | 建卡 | 取消」。正着写会出现「下一步」在左、
        # 「上一步」在右 —— 手会按错。
        for key, text, action in (("cancel", T("取消"), self.cancel),
                                  ("finish", T("建卡"), self.finish),
                                  ("next", T("下一步 →"), self.next_step),
                                  ("back", T("← 上一步"), self.prev_step)):
            button = ttk.Button(nav, text=text, command=action, width=10)
            button.pack(side="right", padx=(6, 0))
            self.buttons[key] = button
        self.progress_var = tk.StringVar()
        ttk.Label(nav, textvariable=self.progress_var, style="Dim.TLabel").pack(
            side="left")

        # 2) 顶部：步骤条
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(8, 4))
        bar.pack(side="top", fill="x", pady=(0, 4))
        self.step_buttons: list[ttk.Button] = []
        for index, step in enumerate(self.steps):
            button = ttk.Button(
                bar, text="%d %s" % (index + 1, step["title"]),
                style="Mini.TButton", width=9,
                command=lambda target=index: self.go(target))
            button.pack(side="left", padx=(0, 4))
            self.step_buttons.append(button)

        # 3) 中部：内容区。最后 pack，占剩余空间
        self.body = ttk.Frame(self)
        self.body.pack(side="top", fill="both", expand=True)

    # --- 导航 -------------------------------------------------------------
    @property
    def current(self) -> dict:
        return self.steps[self.index]

    def go(self, index: int) -> None:
        self.index = max(0, min(len(self.steps) - 1, int(index)))
        self.render()

    def next_step(self) -> None:
        self.go(self.index + 1)

    def prev_step(self) -> None:
        self.go(self.index - 1)

    def cancel(self) -> None:
        self.app.close_wizard()

    def problems(self) -> list[dict]:
        """当前草案的问题清单。**只有这一处**该问 `draft_problems` ——
        改卡与建卡的差别（属性只查范围 vs 按生成方式查）在这里统一带上。"""
        return api.draft_problems(self.app.bundle, self.draft, self.app.locale,
                                  editing=self.editing)

    def finish(self) -> None:
        """建卡 / 改卡。有错就跳回第一个出错的那一步，**不弹窗** —— 弹窗在零弹窗
        铁律下是禁止的，而且一个「有错误」的弹窗什么也没告诉玩家。"""
        problems = self.problems()
        blocking = [item for item in problems if item.get("level", "error") != "warn"]
        if blocking:
            first = blocking[0]
            target = api.STEP_INDEX.get(first["step"], 0)
            self.go(target)
            self._set_status(T("还差这些：") + "；".join(item["text"] for item in blocking[:3]),
                             warn=True)
            return
        try:
            if self.editing:
                # 改现有角色：背包、装备、当前 HP、资源都保住。
                # 走 build_from_draft 会把它们全丢掉（那是「造新角色」）
                actor = api.apply_draft(self.app.bundle, self.app.actor, self.draft,
                                        self.app.locale)
            else:
                actor = api.build_from_draft(self.app.bundle, self.draft,
                                             self.app.locale)
        except api.DndError as exc:
            self._set_status(T("建卡失败：%s") % exc, warn=True)
            return
        self.app.finish_wizard(actor, editing=self.editing)

    # --- 渲染 -------------------------------------------------------------
    def render(self) -> None:
        _clear(self.body)
        self.progress_var.set(T("第 %d / %d 步 · %s")
                              % (self.index + 1, len(self.steps), self.current["title"]))
        for index, button in enumerate(self.step_buttons):
            # 用 style 而不是 state：灰掉当前步会让人以为「这步不能改」
            button.configure(style="Active.Mini.TButton" if index == self.index
                             else "Mini.TButton")
        builder = getattr(self, "_step_%s" % self.current["key"], None)
        if builder is None:                       # 理论上不会发生，但不许静默白屏
            ttk.Label(self.body, text=T("这一步还没做：%s") % self.current["key"]).pack()
        else:
            builder()
        self._refresh_nav()
        self._report()

    def _refresh_nav(self) -> None:
        self.buttons["back"].configure(state="normal" if self.index > 0 else "disabled")
        last = self.index == len(self.steps) - 1
        self.buttons["next"].configure(state="disabled" if last else "normal")
        self.buttons["finish"].configure(state="normal" if last else "disabled")

    def _report(self, step: str | None = None) -> None:
        """把当前步的校验结果写到状态行。**只报当前步**，不然 8 步的问题
        一起堆上来，没人知道先改哪个。"""
        key = step or self.current["key"]
        problems = [item for item in self.problems() if item["step"] == key]
        if not problems:
            self._set_status(self.current["hint"])
            return
        errors = [item for item in problems if item.get("level", "error") != "warn"]
        self._set_status("；".join(item["text"] for item in problems),
                         warn=bool(errors))

    def _set_status(self, text: str, warn: bool = False) -> None:
        self.status_var.set(text)
        self.status.configure(foreground=theme.WARN if warn else theme.DIM)

    # --- 第 1 步：职业 -----------------------------------------------------
    def _step_class(self) -> None:
        options = api.step_options(self.app.bundle, "class", self.draft,
                                   self.app.locale)
        left = ttk.Frame(self.body)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text=T("职业")).pack(anchor="w")
        pane = ListPane(left, height=14, width=22)
        pane.pack(fill="both", expand=True)
        pane.fill([(row["id"], "%s（d%dd）" % (row["name"], row["hit_die"]))
                   for row in options["classes"]])
        self.class_pane = pane

        right = ttk.Frame(self.body)
        right.pack(side="left", fill="both", expand=True)
        detail = section(right, T("职业详情"))
        detail.pack(fill="x")
        self.class_detail = ttk.Label(detail, text="", style="Dim.TLabel",
                                      justify="left", wraplength=640)
        self.class_detail.pack(anchor="w")

        row = ttk.Frame(right)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text=T("等级")).pack(side="left")
        self.level_var = tk.IntVar(value=int(self.draft.get("class_level") or 1))
        spin = ttk.Spinbox(row, from_=1, to=20, width=4, textvariable=self.level_var,
                           command=self._on_level)
        spin.pack(side="left", padx=(6, 16))
        self.level_var.trace_add("write", lambda *_: self._on_level())
        ttk.Label(row, text=T("子职")).pack(side="left")
        self.subclass_var = tk.StringVar()
        # 下拉项对应的内容 id，**按位置对齐**（`_subclass_ids[i]` 是第 i+1 项）。
        # 先置空：没选职业时 `_fill_class_info` 会提前返回，此时的 `<<ComboboxSelected>>`
        # 不能炸在 AttributeError 上。
        self._subclass_ids: list[str] = []
        self.subclass_box = ttk.Combobox(row, textvariable=self.subclass_var,
                                         state="readonly", width=26)
        self.subclass_box.pack(side="left", padx=(6, 0))
        self.subclass_box.bind("<<ComboboxSelected>>", self._on_subclass)

        pane.list.bind("<<ListboxSelect>>", self._on_class)
        if self.draft.get("class_id"):
            pane.select_id(self.draft["class_id"])
        self._fill_class_info()
        # 改卡时**不能换主职业、不能改等级**：换职业等于重建（`apply_draft` 会拒绝），
        # 改等级有「升级」按钮专管。控件禁掉比让人改完被拒更好 —— 后者看起来像 bug。
        if self.editing:
            pane.list.configure(state="disabled")
            spin.configure(state="disabled")

    def _on_class(self, _event=None) -> None:
        class_id = self.class_pane.selected_id()
        if not class_id or class_id == self.draft.get("class_id"):
            return
        self.draft["class_id"] = class_id
        # 换职业后技能/精通/法术的选择全部作废：它们都是「本职业的表里选」
        self.draft["skills"] = []
        self.draft["masteries"] = []
        self.draft["cantrips"] = {}
        self.draft["prepared"] = {}
        self.draft["subclass"] = ""
        # 起始装备是**按职业**给的：不清掉就会带着上个职业的包 id 去建卡，
        # 校验会报「没有这组起始装备」，而人还停在职业这一步。
        self.draft["starting_pack"] = ""
        self._fill_class_info()
        self._report()

    def _on_level(self, _event=None) -> None:
        try:
            level = int(self.level_var.get())
        except (tk.TclError, ValueError):
            return
        self.draft["class_level"] = level
        self._fill_class_info()
        self._report()

    def _on_subclass(self, _event=None) -> None:
        # 用索引而不是名字反查：名字是**内容**，第三方插件里可能重名；
        # 索引只跟当前这份下拉列表有关，不会选错人。
        index = int(self.subclass_box.current())
        self.draft["subclass"] = "" if index <= 0 else self._subclass_ids[index - 1]
        self._report()

    def _fill_class_info(self) -> None:
        """刷新右侧详情、子职下拉、以及「等级变了 → 精通件数变了」的显示。"""
        class_id = str(self.draft.get("class_id") or "")
        if not class_id or class_id not in self.app.bundle.classes:
            self.class_detail.configure(text=T("先选一个职业。"))
            # 职业清空了，子职下拉也得跟着清 —— 留着上一个职业的子职，
            # 玩家会以为「这个职业也能选它」。
            self._subclass_ids = []
            self.subclass_box.configure(values=[T("（暂无）")], state="disabled")
            self.subclass_box.current(0)
            return
        class_def = self.app.bundle.class_def(class_id)
        level = int(self.draft.get("class_level") or 1)
        marks = []
        if class_def.hit_die:
            marks.append(T("生命骰 d%d") % class_def.hit_die)
        if class_def.primary:
            marks.append(T("主属性 ") + join(ABILITY_ZH.get(k, k.upper())
                                          for k in class_def.primary))
        if class_def.saves:
            marks.append(T("豁免熟练 ") + join(ABILITY_ZH.get(k, k.upper())
                                           for k in class_def.saves))
        marks.append(T("技能 %d 项") % class_def.skill_choices)
        if class_def.caster.value != "none":
            marks.append(T("施法（%s）") % ABILITY_ZH.get(class_def.casting_ability, "?"))
        mastery = api.mastery_choices(self.app.bundle, class_id, level)
        if mastery["count"]:
            marks.append(T("武器精通 %d 件") % mastery["count"])
        self.class_detail.configure(text="　·　".join(marks))

        info = api.subclass_choices(self.app.bundle, class_id, level, self.app.locale)
        labels = [T("（暂无）")] + [row["name"] for row in info["options"]]
        self._subclass_ids = [row["id"] for row in info["options"]]
        self.subclass_box.configure(values=labels, state="readonly")
        if not info["unlocked"]:
            # 不解锁时**不禁用**控件：玩家 3 级前也能看见有哪些子职，
            # 只是选了会被校验挡住（状态行会说「3 级才解锁」）。
            self.subclass_box.configure(state="disabled")
        chosen = str(self.draft.get("subclass") or "")
        index = self._subclass_ids.index(chosen) + 1 if chosen in self._subclass_ids else 0
        self.subclass_box.current(index)

    # --- 第 2 步：背景 -----------------------------------------------------
    def _step_background(self) -> None:
        options = api.step_options(self.app.bundle, "background", self.draft,
                                   self.app.locale)
        left = ttk.Frame(self.body)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text=T("背景")).pack(anchor="w")
        pane = ListPane(left, height=16, width=22)
        pane.pack(fill="both", expand=True)
        pane.fill([(row["id"], row["name"]) for row in options["backgrounds"]])
        self.background_pane = pane

        right = ttk.Frame(self.body)
        right.pack(side="left", fill="both", expand=True)
        self.background_detail = ttk.Label(right, text="", style="Dim.TLabel",
                                           justify="left", wraplength=640)
        self.background_detail.pack(anchor="w")
        pane.list.bind("<<ListboxSelect>>", self._on_background)
        if self.draft.get("background"):
            pane.select_id(self.draft["background"])
        self._fill_background_info()

    def _on_background(self, _event=None) -> None:
        ident = self.background_pane.selected_id()
        if not ident or ident == self.draft.get("background"):
            return
        self.draft["background"] = ident
        # 背景换了，属性加值的那三项也换了 —— 旧分配必须清掉，
        # 否则会带着「上个背景才有的属性」流到建卡时（那会是个看不懂的报错）
        self.draft["background_bonus"] = {}
        self.bonus_index = 0
        self._fill_background_info()
        self._report()

    def _bonus_plans(self) -> list[dict]:
        background_id = str(self.draft.get("background") or "")
        if not background_id:
            return []
        return api.bonus_plans(background_id, self.app.bundle)

    def _index_of_bonus(self) -> int:
        """草案里已有的背景加值对应「第几种形态」。

        `_fill_bonus_box` 会按这个序号把 `draft` 覆盖成下拉里真正选中的那一个 ——
        界面显示一种、实际算另一种是最糟的情况，所以宁可覆盖也不要错位。
        """
        current = dict(self.draft.get("background_bonus") or {})
        for index, plan in enumerate(self._bonus_plans()):
            if dict(plan) == current:
                return index
        return 0

    def _fill_background_info(self) -> None:
        ident = str(self.draft.get("background") or "")
        item = self.app.bundle.backgrounds.get(ident) if ident else None
        if item is None:
            self.background_detail.configure(text=T("先选一个背景。"))
            return
        rows = [item.summary.get(self.app.locale)]
        rows.append(T("属性加值：") + join(ABILITY_ZH.get(k, k.upper())
                                        for k in item.abilities))
        if item.origin_feat:
            feat = self.app.bundle.feats.get(item.origin_feat)
            rows.append(T("起始专长：%s") % (feat.name.get(self.app.locale)
                                     if feat else item.origin_feat))
        if item.skills:
            rows.append(T("技能熟练：") + join(item.skills))
        if item.tool_label is not None:
            rows.append(T("工具：") + item.tool_label.get(self.app.locale))
        self.background_detail.configure(text="\n".join(rows))

    # --- 第 3 步：物种 -----------------------------------------------------
    def _step_species(self) -> None:
        options = api.step_options(self.app.bundle, "species", self.draft,
                                   self.app.locale)
        left = ttk.Frame(self.body)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text=T("物种")).pack(anchor="w")
        pane = ListPane(left, height=12, width=22)
        pane.pack(fill="both", expand=True)
        pane.fill([(row["id"], row["name"]) for row in options["species"]])
        self.species_pane = pane

        right = ttk.Frame(self.body)
        right.pack(side="left", fill="both", expand=True)
        scroller = ScrollFrame(right, height=430)
        scroller.pack(fill="both", expand=True)
        self.species_detail = ttk.Label(scroller.body, text="", style="Dim.TLabel",
                                        justify="left", wraplength=620)
        self.species_detail.pack(anchor="w")
        pane.list.bind("<<ListboxSelect>>", self._on_species)
        if self.draft.get("species"):
            pane.select_id(self.draft["species"])
        self._fill_species_info()

    def _on_species(self, _event=None) -> None:
        ident = self.species_pane.selected_id()
        if not ident or ident == self.draft.get("species"):
            return
        self.draft["species"] = ident
        self._fill_species_info()
        self._report()

    def _fill_species_info(self) -> None:
        ident = str(self.draft.get("species") or "")
        item = self.app.bundle.species.get(ident) if ident else None
        if item is None:
            self.species_detail.configure(text=T("先选一个物种。（2024 规则里物种不是必选）"))
            return
        size_zh = {"tiny": T("微型"), "small": T("小型"), "medium": T("中型"),
                   "large": T("大型")}
        rows = [item.summary.get(self.app.locale),
                T("体型 %s · 速度 %d 尺") % ("/".join(size_zh.get(s, s) for s in item.size),
                                     item.speed)]
        for power in item.powers:
            rows.append("\n【%s】%s" % (power.name.get(self.app.locale),
                                       power.text.get(self.app.locale)))
        self.species_detail.configure(text="\n".join(rows))

    # --- 第 4 步：语言 -----------------------------------------------------
    def _step_languages(self) -> None:
        """2024 的语言：通用语自动 + 2 门标准自选 + 职业给的门数。

        语言**不是**物种给的（2014 才是），所以这一步在物种之后、属性之前：
        出身选完了，语言才有「职业额外给几门」可算。
        """
        options = api.step_options(self.app.bundle, "languages", self.draft,
                                   self.app.locale)
        self.language_need = int(options["need"])
        self.language_tips: list[Tooltip] = []   # 测试要能数
        head = ttk.Frame(self.body)
        head.pack(fill="x")
        ttk.Label(head, text=T("选 %d 门语言") % self.language_need,
                  font=(theme.UI_FONT, 11, "bold")).pack(side="left")
        self.language_count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.language_count_var).pack(side="right")
        ttk.Label(self.body, text=options["hint"], style="Dim.TLabel").pack(
            anchor="w", pady=(2, 0))

        scroller = ScrollFrame(self.body, height=420)
        scroller.pack(fill="both", expand=True, pady=(6, 0))
        # 自动会的与职业白给的先列出来：玩家看到手上已经有「通用语」「盗贼黑话」，
        # 才不会以为自己漏选了一门。
        if options["common"]:
            ttk.Label(scroller.body,
                      text=T("%s　— 自动会") % options["common"]["name"],
                      style="Dim.TLabel").pack(anchor="w")
        for row in options["fixed"]:
            ttk.Label(scroller.body, text=T("%s　— 职业已给") % row["name"],
                      style="Dim.TLabel").pack(anchor="w")

        self.language_vars: dict[str, tk.IntVar] = {}
        chosen = set(options["picked"])
        if options["standard"]:
            ttk.Label(scroller.body, text=T("标准语言"),
                      font=(theme.UI_FONT, 10, "bold")).pack(anchor="w", pady=(8, 2))
            for row in options["standard"]:
                self._language_check(scroller.body, row, chosen)
        if options["rare"]:
            ttk.Label(scroller.body, text=T("稀有语言"),
                      font=(theme.UI_FONT, 10, "bold")).pack(anchor="w", pady=(8, 2))
            for row in options["rare"]:
                self._language_check(scroller.body, row, chosen)
        self._refresh_language_count()

    def _language_check(self, master, row: dict, chosen: set) -> None:
        var = tk.IntVar(value=1 if row["key"] in chosen else 0)
        check = ttk.Checkbutton(master, text=row["name"], variable=var,
                               command=self._on_languages)
        check.pack(anchor="w", pady=1)
        # 原初语的「含四种方言」这类补充说明走气泡：写在勾选项后面会把
        # 那一行拉得比中栏还宽，而这个弹窗的宽度是按最小内容撑的。
        if row.get("note"):
            self.language_tips.append(Tooltip(check, row["note"]))
        var.trace_add("write", lambda *_: self._on_languages(silent=True))
        self.language_vars[row["key"]] = var

    def _on_languages(self, silent: bool = False) -> None:
        if not hasattr(self, "language_vars"):
            return
        self.draft["languages"] = [key for key, var in self.language_vars.items()
                                   if _checked(var)]
        self._refresh_language_count()
        if not silent:
            self._report()

    def _refresh_language_count(self) -> None:
        picked = [key for key, var in getattr(self, "language_vars", {}).items()
                  if _checked(var)]
        self.language_count_var.set(T("已选 %d / %d")
                                    % (len(picked), getattr(self, "language_need", 0)))

    # --- 第 5 步：属性 -----------------------------------------------------
    def _step_scores(self) -> None:
        options = api.step_options(self.app.bundle, "scores", self.draft,
                                   self.app.locale)
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        roll = None
        if self.editing:
            # 改卡：属性是已经存在的数（点买/数组/4d6 都可能，专长还抬过），
            # 再摆「生成方式」只会误导 —— 那三种方式算出来的值会覆盖他现在的卡。
            box = section(top, T("改的是卡上的原始属性"),
                          T("这里填建卡时那一组数（不含专长与背景加值）。"
                          "改完 HP 上限、熟练与攻击会重算，装备与当前 HP 不动。"))
            box.pack(fill="x")
            self.mode_var = tk.StringVar(value="edit")
        else:
            box = section(top, T("生成方式"))
            box.pack(side="left", fill="x")
            self.mode_var = tk.StringVar(value=str(self.draft.get("score_mode")
                                                   or "standard_array"))
            # `mode_labels` 是**已按语言翻好**的那份；老接口只有 `mode_zh`（永远中文）
            labels = options.get("mode_labels") or options["mode_zh"]
            for key in options["modes"]:
                ttk.Radiobutton(box, text=labels.get(key, key),
                                value=key, variable=self.mode_var,
                                command=self._on_mode).pack(anchor="w")

            roll = section(top, T("快捷"))
            roll.pack(side="left", fill="both", expand=True, padx=(8, 0))
            ttk.Button(roll, text=T("标准数组"), style="Mini.TButton",
                       command=lambda: self._preset_scores("standard_array")
                       ).pack(anchor="w")
            ttk.Button(roll, text=T("掷 4d6 弃最低"), style="Mini.TButton",
                       command=lambda: self._preset_scores("roll")).pack(anchor="w")
        self.cost_var = tk.StringVar()
        if roll is not None:
            ttk.Label(roll, textvariable=self.cost_var,
                      style="Dim.TLabel").pack(anchor="w")

        # `section()` 内部已经 pack 了一个说明标签，直接往里 grid 会撞管理器。
        # 所以这里自己建区框，再把网格放进一个中间 Frame。
        grid_box = ttk.LabelFrame(self.body, text=T("属性值"), padding=(8, 4))
        grid_box.pack(fill="x", pady=(8, 0))
        head = ttk.Frame(grid_box)
        head.pack(fill="x")
        # 说明跟着生成方式走（点买上限 / 标准数组要互换 / 掷骰范围）
        self.budget_note_var = tk.StringVar()
        ttk.Label(head, textvariable=self.budget_note_var, style="Dim.TLabel",
                  wraplength=520, justify="left").pack(side="left", anchor="w")
        # 「还剩 N 点」必须和输入框在**同一段视线里**：以前它画在「快捷」框，
        # 而且一越界就被错误文本顶掉，玩家根本不知道还剩多少。
        self.points_var = tk.StringVar()
        self.points_label = ttk.Label(head, textvariable=self.points_var,
                                      font=(theme.UI_FONT, 11, "bold"))
        self.points_label.pack(side="right", anchor="e", padx=(8, 0))
        grid = ttk.Frame(grid_box)
        grid.pack(anchor="w")
        self.score_vars: dict[str, tk.IntVar] = {}
        self.score_spins: dict[str, ttk.Spinbox] = {}
        self.score_combos: dict[str, ttk.Combobox] = {}
        self._array_values: dict[str, int] = {}
        self._syncing = False
        # `validate="key"` 让非法数字打不进去（详见 `_score_prefix_ok`）：
        # 以前的框是 1–20 死值，点买填 18 也照样停在框里，只等建卡时才报错。
        lo, hi = SCORE_BOUNDS[self._mode()]
        for index, key in enumerate(options["keys"]):
            cell = ttk.Frame(grid)
            cell.grid(row=0, column=index, padx=(0, 12), sticky="w")
            ttk.Label(cell, text=ABILITY_ZH.get(key, key.upper())).pack()
            var = tk.IntVar(value=int((self.draft.get("scores") or {}).get(key, 10)))
            spin = ttk.Spinbox(cell, from_=lo, to=hi, width=4, textvariable=var,
                               justify="center", command=self._on_scores)
            spin.configure(validate="key",
                           validatecommand=(self._watched(spin), "%P"))
            # 标准数组用下拉：六个数只能各用一次，选过的数字与对方**交换**。
            # 用数字框做不到这件事 —— 玩家能填出两个 15。
            combo = ttk.Combobox(cell, width=4, state="readonly",
                                 justify="center", textvariable=var)
            combo.bind("<<ComboboxSelected>>",
                       lambda _event, name=key: self._on_array_pick(name))
            # 离开输入框就收口：框里剩个半截数（"1"）要夹到最近的合法值，
            # 否则「框里显示 1、草案里还是 15」，玩家看到的和实际用的不是一回事。
            spin.bind("<FocusOut>", self._commit_scores)
            spin.bind("<Return>", self._commit_scores)
            var.trace_add("write", lambda *_: self._on_scores())
            self.score_vars[key] = var
            self.score_spins[key] = spin
            self.score_combos[key] = combo
        self._sync_score_widgets()

        bonus = section(self.body, T("背景加值"),
                        T("从背景给的那几项属性里分：一项 +2 加一项 +1，或三项各 +1。"))
        bonus.pack(fill="x", pady=(8, 0))
        self.bonus_var = tk.StringVar()
        self.bonus_box = ttk.Combobox(bonus, textvariable=self.bonus_var,
                                      state="readonly", width=44)
        self.bonus_box.pack(anchor="w")
        self.bonus_box.bind("<<ComboboxSelected>>", self._on_bonus)
        self._fill_bonus_box()
        self._refresh_cost()

    def _mode(self) -> str:
        """当前生成方式。控件还没建时退回草案里的值。"""
        try:
            return str(self.mode_var.get()) or "point_buy"
        except (AttributeError, tk.TclError):
            return str(self.draft.get("score_mode") or "point_buy")

    def _value_of(self, key: str) -> int:
        try:
            return int(self.score_vars[key].get())
        except (KeyError, tk.TclError, ValueError):
            return 0

    def _score_prefix_ok(self, proposed: str) -> bool:
        """键盘校验：只放行「还能补成一个合法值的半截数字」。

        这样点买模式里 `16` 根本打不进去（16–20 没有合法的补全），而 `1` 能打
        —— 它是 10–15 的前半截。空串也放行（删光是输入过程的一部分）。
        """
        if proposed == "":
            return True
        if not proposed.isdigit():
            return False
        lo, hi = SCORE_BOUNDS[self._mode()]
        return any(str(value).startswith(proposed) for value in range(lo, hi + 1))

    def _watched(self, widget):
        """把前缀校验装到某个输入框上，**被拒之后重新武装**。

        Tk 的规矩：`validatecommand` 一旦返回 0，它自己就把 `validate` 改成
        `none` —— 也就是「拒一次之后再也不校验」。不重新装回去，玩家打一个
        16 被拒，接下来 18、20 全都能进框（比一开始就不拦还糟）。
        """
        def check(proposed: str) -> bool:
            ok = self._score_prefix_ok(proposed)
            if not ok:
                widget.after_idle(lambda: widget.configure(validate="key"))
            return ok
        return self.register(check)

    def _on_mode(self) -> None:
        mode = self._mode()
        self.draft["score_mode"] = mode
        scores = dict(self.draft.get("scores") or {})
        try:
            problems = api.check_scores(mode, scores, self.app.locale)
        except api.DndError:
            problems = [T("不认识的生成方式")]
        if problems:
            # 当前这六个数在新方式下不合法（点买的 17 拿去当标准数组）。
            # **换一套合法的**，而不是留一堆非法值让人自己找 —— 换之前不会掉到
            # 更差的组合：点买与标准数组共用 15/14/13/12/10/8（正好 27 点）。
            scores = self._preset_for(mode)
            self.draft["scores"] = dict(scores)
            self._syncing = True
            try:
                for key, var in self.score_vars.items():
                    var.set(int(scores.get(key, 10)))
            finally:
                self._syncing = False
        self._array_values = dict(scores)
        self._sync_score_widgets()
        self._refresh_cost()
        self._report()
        if problems:
            # 换数必须说出来：静默把 17 改成 12 会让玩家以为自己的输入丢了
            self._set_status(T("「%s」下原来的属性不合法（%s），已换成一套合法的数值")
                             % (api.score_mode_labels(self.app.locale).get(mode, mode),
                                problems[0]),
                             warn=True)

    def _preset_for(self, mode: str) -> dict[str, int]:
        """这种方式的一套合法初始值。掷骰走内核的 rng（C4：界面不 import random）。"""
        if mode == "roll":
            return dict(api.random_scores())
        return {key: int(value) for key, value in api.score_presets()["standard"].items()}

    def _sync_score_widgets(self) -> None:
        """按生成方式换控件：点买/掷骰用数字框，标准数组用只读下拉。"""
        mode = self._mode()
        lo, hi = SCORE_BOUNDS.get(mode, (1, 20))
        standard = mode == "standard_array"
        for key, spin in self.score_spins.items():
            combo = self.score_combos[key]
            if standard:
                spin.pack_forget()
                combo.pack()
            else:
                combo.pack_forget()
                spin.configure(from_=lo, to=hi)
                if not spin.winfo_manager():
                    spin.pack()
        self.budget_note_var.set(SCORE_NOTES.get(mode, ""))
        self._refresh_array_choices()

    def _refresh_array_choices(self) -> None:
        """标准数组的下拉列**全部六个数**。

        不是只列「没人拿的」—— 六个值永远都被谁拿着，那样就一个都选不了。
        选中一个已被别人拿走的数，由 `_on_array_pick` 做交换。
        """
        pool = [str(value) for value in api.score_presets()["standard"].values()]
        for combo in self.score_combos.values():
            combo.configure(values=pool)

    def _on_array_pick(self, key: str) -> None:
        """标准数组：选中一个数就与「原来拿着它」的那格**交换**。

        交换而不是直接赋值，是因为六个数必须是 15/14/13/12/10/8 的排列 ——
        直接赋值会让两格都变成 15，而第三格的 15 失踪。
        """
        old = int(self._array_values.get(key, 10))
        new = self._value_of(key)
        holder = next((other for other, value in self._array_values.items()
                       if other != key and value == new), None)
        self._array_values[key] = new
        if holder is not None:
            self._array_values[holder] = old
            self._syncing = True
            try:
                self.score_vars[holder].set(old)
            finally:
                self._syncing = False
        self._refresh_array_choices()
        self.draft["scores"] = {name: int(var.get())
                               for name, var in self.score_vars.items()}
        self._refresh_cost()
        self._report()

    def _preset_scores(self, mode: str) -> None:
        """按选定的方式重新发一套数。**掷骰走内核的 rng**（C4：界面不 import random）。"""
        self.draft["score_mode"] = mode
        if self.mode_var.get() != mode:
            self.mode_var.set(mode)
        if mode not in ("standard_array", "roll"):
            return
        scores = self._preset_for(mode)
        self.draft["scores"] = dict(scores)
        self._syncing = True
        try:
            for key, var in getattr(self, "score_vars", {}).items():
                var.set(int(scores.get(key, 10)))
        finally:
            self._syncing = False
        self._array_values = dict(scores)
        self._sync_score_widgets()
        self._refresh_cost()
        self._report()

    def _on_scores(self) -> None:
        if getattr(self, "_syncing", False):
            return
        mode = self._mode()
        scores = {}
        for key, var in self.score_vars.items():
            try:
                scores[key] = int(var.get())
            except (tk.TclError, ValueError):
                return                       # 输入框里是空的/半个字符，等它填完
        standard = api.score_presets()["standard"].values()
        if mode == "standard_array":
            if sorted(scores.values()) != sorted(int(v) for v in standard):
                return                       # 交换进行中，等 `_on_array_pick` 收尾
            self._array_values = dict(scores)
        else:
            lo, hi = SCORE_BOUNDS.get(mode, (1, 20))
            if any(not lo <= value <= hi for value in scores.values()):
                # 框里是半截数（"1" 是 15 的前半截）：先不写草案，
                # 否则每按一个键状态行就闪一句「STR 必须在 8–15 之间」
                self._set_points("…", theme.DIM)
                return
        self.draft["scores"] = scores
        self._refresh_cost()
        self._report()

    def _commit_scores(self, _event=None) -> None:
        """离开输入框时收口：半截数（"1"）夹到最近的合法值。

        不这么做，框里显示的数和草案里的数会不一致 —— 而玩家只会看框。
        """
        mode = self._mode()
        if mode == "standard_array":
            return
        lo, hi = SCORE_BOUNDS.get(mode, (1, 20))
        changed = False
        for var in self.score_vars.values():
            try:
                value = int(var.get())
            except (tk.TclError, ValueError):
                value = lo
            fixed = max(lo, min(hi, value))
            if fixed != value:
                self._syncing = True
                try:
                    var.set(fixed)
                finally:
                    self._syncing = False
                changed = True
        if changed:
            self.draft["scores"] = {key: int(var.get())
                                    for key, var in self.score_vars.items()}
            self._refresh_cost()
            self._report()

    def _set_points(self, text: str, color: str) -> None:
        self.points_var.set(text)
        self.points_label.configure(foreground=color)

    def _fill_bonus_box(self) -> None:
        plans = self._bonus_plans()
        self._bonus_labels = []
        for plan in plans:
            self._bonus_labels.append(
                join("%s %+d" % (ABILITY_ZH.get(k, k.upper()), v)
                         for k, v in plan.items()))
        self.bonus_box.configure(values=self._bonus_labels)
        if not plans:
            self.bonus_var.set("")
            self.bonus_box.configure(state="disabled")
            return
        self.bonus_box.configure(state="readonly")
        index = min(self.bonus_index, len(plans) - 1)
        self.bonus_var.set(self._bonus_labels[index])
        self.draft["background_bonus"] = dict(plans[index])

    def _on_bonus(self, _event=None) -> None:
        plans = self._bonus_plans()
        label = self.bonus_var.get()
        if label in getattr(self, "_bonus_labels", []):
            self.bonus_index = self._bonus_labels.index(label)
            self.draft["background_bonus"] = dict(plans[self.bonus_index])
        self._refresh_cost()
        self._report()

    def _refresh_cost(self) -> None:
        """点数 / 剩余点数 / 加值预览。三种方式各有各的「还剩多少」。"""
        scores = self.draft.get("scores") or {}
        mode = self._mode()
        if mode == "point_buy":
            budget = api.score_presets()["budget"]
            try:
                spent = api.score_cost(scores, self.app.locale)
            except api.DndError as exc:
                self._set_points(str(exc), theme.WARN)
                self.cost_var.set("")
                return
            left = budget - spent
            if left > 0:
                self._set_points(T("还剩 %d 点") % left, theme.GOLD2)
            elif left == 0:
                self._set_points(T("刚好用完 %d 点") % budget, theme.OK)
            else:
                self._set_points(T("超支 %d 点") % -left, theme.WARN)
            self.cost_var.set(T("点买 %d 点：8–15 之间买，已花 %d") % (budget, spent))
            return
        if mode == "standard_array":
            self._set_points(T("六项各一次"), theme.DIM)
        elif mode == "edit":
            # 备注里已经写了范围，这里不再重复一个「8–20」
            self._set_points("", theme.DIM)
        elif mode == "roll":
            self._set_points(T("总和 %d") % sum(int(v) for v in scores.values()),
                             theme.DIM)
        final = dict(scores)
        for key, value in (self.draft.get("background_bonus") or {}).items():
            if key in final:
                final[key] = min(20, final[key] + int(value))
        pairs = "　".join("%s %d" % (ABILITY_ZH.get(k, k.upper()), final.get(k, 0))
                          for k in scores)
        self.cost_var.set(T("加值后：") + pairs if pairs else "")

    # --- 第 6 步：技能 -----------------------------------------------------
    def _step_skills(self) -> None:
        options = api.step_options(self.app.bundle, "skills", self.draft,
                                   self.app.locale)
        head = ttk.Frame(self.body)
        head.pack(fill="x")
        ttk.Label(head, text=T("从本职业技能表里选 %d 项") % options["choices"],
                  font=(theme.UI_FONT, 11, "bold")).pack(side="left")
        self.skill_count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.skill_count_var).pack(side="right")

        scroller = ScrollFrame(self.body, height=430)
        scroller.pack(fill="both", expand=True, pady=(6, 0))
        self.skill_vars: dict[str, tk.IntVar] = {}
        chosen = set(self.draft.get("skills") or ())
        for row in options["options"]:
            var = tk.IntVar(value=1 if row["key"] in chosen else 0)
            text = "%s（%s）" % (row["name"], ABILITY_ZH.get(row["ability"], "?"))
            if row["provided"]:
                text += T("　— 背景已给")
            check = ttk.Checkbutton(scroller.body, text=text, variable=var,
                                    command=self._on_skills)
            check.pack(anchor="w", pady=1)
            var.trace_add("write", lambda *_: self._on_skills(silent=True))
            self.skill_vars[row["key"]] = var
        self._refresh_skill_count()

    def _on_skills(self, silent: bool = False) -> None:
        if not hasattr(self, "skill_vars"):
            return
        self.draft["skills"] = [key for key, var in self.skill_vars.items()
                                if _checked(var)]
        self._refresh_skill_count()
        if not silent:
            self._report()

    def _refresh_skill_count(self) -> None:
        need = 0
        class_id = str(self.draft.get("class_id") or "")
        if class_id in self.app.bundle.classes:
            need = int(self.app.bundle.class_def(class_id).skill_choices)
        self.skill_count_var.set(T("已选 %d / %d") % (len(self.draft.get("skills") or []), need))

    # --- 第 7 步：武器精通 -------------------------------------------------
    def _step_masteries(self) -> None:
        options = api.step_options(self.app.bundle, "masteries", self.draft,
                                   self.app.locale)
        head = ttk.Frame(self.body)
        head.pack(fill="x")
        ttk.Label(head, text=T("选 %d 件武器的精通") % options["count"],
                  font=(theme.UI_FONT, 11, "bold")).pack(side="left")
        ttk.Label(head, text=T("只有选过的武器才能用出精通效果"),
                  style="Dim.TLabel").pack(side="left", padx=(12, 0))
        self.mastery_count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.mastery_count_var).pack(side="right")

        if not options["options"]:
            ttk.Label(self.body, text=T("这个职业没有武器精通，这一步直接跳过。"),
                      style="Dim.TLabel").pack(anchor="w", pady=12)
            self.mastery_count_var.set("")
            return

        scroller = ScrollFrame(self.body, height=430)
        scroller.pack(fill="both", expand=True, pady=(6, 0))
        self.mastery_vars: dict[str, tk.IntVar] = {}
        chosen = set(self.draft.get("masteries") or ())
        for row in options["options"]:
            var = tk.IntVar(value=1 if row["id"] in chosen else 0)
            key = row["mastery"] or ""
            # 印中文名，别把 `graze`/`topple` 这种内部值直接摆给玩家
            mastery = MASTERY_ZH.get(key, key) if key else "—"
            text = T("%s　%s　精通:%s") % (row["name"], row["damage"], mastery)
            ttk.Checkbutton(scroller.body, text=text, variable=var,
                            command=self._on_masteries).pack(anchor="w", pady=1)
            var.trace_add("write", lambda *_: self._on_masteries(silent=True))
            self.mastery_vars[row["id"]] = var
        self._refresh_mastery_count()

    def _on_masteries(self, silent: bool = False) -> None:
        if not hasattr(self, "mastery_vars"):
            return
        self.draft["masteries"] = [ident for ident, var in self.mastery_vars.items()
                                   if _checked(var)]
        self._refresh_mastery_count()
        if not silent:
            self._report()

    def _refresh_mastery_count(self) -> None:
        class_id = str(self.draft.get("class_id") or "")
        need = 0
        if class_id in self.app.bundle.classes:
            info = api.mastery_choices(self.app.bundle, class_id,
                                       int(self.draft.get("class_level") or 1))
            need = info["count"]
        self.mastery_count_var.set(T("已选 %d / %d")
                                   % (len(self.draft.get("masteries") or []), need))

    # --- 第 8 步：法术 -----------------------------------------------------
    def _step_spells(self) -> None:
        options = api.step_options(self.app.bundle, "spells", self.draft,
                                   self.app.locale)
        class_id = str(self.draft.get("class_id") or "")
        self.spell_tips: list[Tooltip] = []      # 测试要能数；非施法职业就是空表
        if not options["caster"]:
            ttk.Label(self.body, text=T("这个职业不施法，这一步直接跳过。"),
                      style="Dim.TLabel").pack(anchor="w", pady=12)
            return

        head = ttk.Frame(self.body)
        head.pack(fill="x")
        ttk.Label(head, text=T("戏法 %d 个 · 准备法术 %d 个")
                             % (options["cantrip_limit"], options["prepared_limit"]),
                  font=(theme.UI_FONT, 11, "bold")).pack(side="left")
        self.spell_count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.spell_count_var).pack(side="right")

        dim_hint = T("把鼠标停在一个法术上，会弹出它的完整说明（施法/距离/成分/持续/正文）。")
        ttk.Label(self.body, text=dim_hint, style="Dim.TLabel").pack(anchor="w", pady=(2, 0))
        columns = ttk.Frame(self.body)
        columns.pack(fill="both", expand=True, pady=(6, 0))
        left = ttk.Frame(columns)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ttk.Frame(columns)
        right.pack(side="left", fill="both", expand=True)

        self.cantrip_vars: dict[str, tk.IntVar] = {}
        self.prepared_vars: dict[str, tk.IntVar] = {}
        chosen_cantrips = set((self.draft.get("cantrips") or {}).get(class_id) or ())
        chosen_prepared = set((self.draft.get("prepared") or {}).get(class_id) or ())

        cantrip_box = section(left, T("戏法"))
        cantrip_box.pack(fill="both", expand=True)
        scroller = ScrollFrame(cantrip_box, height=390)
        scroller.pack(fill="both", expand=True)
        for row in options["cantrips"]:
            var = tk.IntVar(value=1 if row["id"] in chosen_cantrips else 0)
            check = ttk.Checkbutton(scroller.body, text=row["name"], variable=var,
                                    command=self._on_spells)
            check.pack(anchor="w")
            var.trace_add("write", lambda *_: self._on_spells(silent=True))
            self.cantrip_vars[row["id"]] = var
            # 悬停出全文。文字**延迟取**：一次建卡几十行，全部拼好会明显拖慢
            self.spell_tips.append(
                Tooltip(check, lambda item=row: spell_text(item["detail"])))

        prepared_box = section(right, T("准备法术（按环）"))
        prepared_box.pack(fill="both", expand=True)
        scroller2 = ScrollFrame(prepared_box, height=390)
        scroller2.pack(fill="both", expand=True)
        for group in options["levels"]:
            ttk.Label(scroller2.body, text=T("%d 环") % group["level"],
                      font=(theme.UI_FONT, 10, "bold")).pack(anchor="w", pady=(4, 0))
            for row in group["spells"]:
                mark = T("（专注）") if row["concentration"] else ""
                var = tk.IntVar(value=1 if row["id"] in chosen_prepared else 0)
                check = ttk.Checkbutton(scroller2.body, text=row["name"] + mark,
                                        variable=var, command=self._on_spells)
                check.pack(anchor="w")
                var.trace_add("write", lambda *_: self._on_spells(silent=True))
                self.prepared_vars[row["id"]] = var
                self.spell_tips.append(
                    Tooltip(check, lambda item=row: spell_text(item["detail"])))
        self._refresh_spell_count()

    def _on_spells(self, silent: bool = False) -> None:
        if not hasattr(self, "cantrip_vars"):
            return
        class_id = str(self.draft.get("class_id") or "")
        self.draft["cantrips"] = {class_id: [key for key, var in self.cantrip_vars.items()
                                             if _checked(var)]}
        self.draft["prepared"] = {class_id: [key for key, var in self.prepared_vars.items()
                                             if _checked(var)]}
        self._refresh_spell_count()
        if not silent:
            self._report()

    def _refresh_spell_count(self) -> None:
        cantrips = len((self.draft.get("cantrips") or {}).get(
            str(self.draft.get("class_id") or ""), ()))
        prepared = len((self.draft.get("prepared") or {}).get(
            str(self.draft.get("class_id") or ""), ()))
        self.spell_count_var.set(T("戏法 %d · 法术 %d") % (cantrips, prepared))

    # --- 第 9 步：汇总 -----------------------------------------------------
    def _name_keys(self) -> tuple[str, str]:
        """(主输入框写的键, 副输入框写的键)。主键 = 当前界面语言那个。"""
        if self.app.locale == "en":
            return "name_en", "name_zh"
        return "name_zh", "name_en"

    def _name_label(self, key: str) -> str:
        if key == "name_en":
            return T("英文名") if self.app.locale == "zh" else T("名字")
        return T("名字") if self.app.locale == "zh" else T("中文名")

    def _step_summary(self) -> None:
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        # 两个名字框各自写 `name_<语言>`。**主输入框跟着界面语言走**：英文界面
        # 里把「Name」写进 name_zh，角色卡（按 en 取名字）会显示 "Unnamed
        # Adventurer" —— 玩家填了名字，卡上却没有（实测踩到）。
        primary, secondary = self._name_keys()
        name_box = section(top, self._name_label(primary))
        name_box.pack(side="left", fill="x")
        self.name_var = tk.StringVar(value=str(self.draft.get(primary) or ""))
        ttk.Entry(name_box, textvariable=self.name_var, width=24).pack(side="left")
        self.name_var.trace_add("write", lambda *_: self._on_name())
        en_box = section(top, self._name_label(secondary),
                         T("只用于双语内容回退，可以留空。"))
        en_box.pack(side="left", fill="x", padx=(8, 0))
        self.name_en_var = tk.StringVar(value=str(self.draft.get(secondary) or ""))
        ttk.Entry(en_box, textvariable=self.name_en_var, width=24).pack(side="left")
        self.name_en_var.trace_add("write", lambda *_: self._on_name_en())

        # 起始装备：改卡模式不画 —— 改卡走 rebuild，背包原样保留，
        # 摆一排单选只会让人以为「换套餐会重发装备」。
        if not self.editing:
            self._build_starting()

        table = section(self.body, T("确认一下"))
        table.pack(fill="both", expand=True, pady=(8, 0))
        # 10 行正好是 `_fill_summary()` 铺的条数。多给几行只会多出 3 条空白，
        # 白占高度（这个窗口的高度预算是按像素算的）。
        self.summary = KeyValue(table, rows=10)
        self.summary.pack(anchor="w")
        self._fill_summary()

    def _build_starting(self) -> None:
        """起始装备单选：一组 = 一批物品 + 一点金币；「金币」那组只有钱。

        默认选中第一组（内容里写的是 A 包）。`draft["starting_pack"]` 写具体 id，
        空串的语义留给 `build_actor`（= 默认那一组），界面不依赖那个默认值。
        """
        class_id = str(self.draft.get("class_id") or "")
        options = api.starting_options(self.app.bundle, class_id,
                                       self.app.locale)["options"]
        if not options:
            return
        ids = [row["id"] for row in options]
        current = str(self.draft.get("starting_pack") or "")
        if current not in ids:
            current = ids[0]
        self.draft["starting_pack"] = current
        box = section(self.body, T("起始装备"),
                      T("建卡时直接穿在身上、放进背包的那一组。之后可以在装备页改。"))
        box.pack(fill="x", pady=(8, 0))
        self.starting_var = tk.StringVar(value=current)
        for row in options:
            ttk.Radiobutton(box, text=row["label"], value=row["id"],
                            variable=self.starting_var,
                            command=self._on_starting).pack(side="left", padx=(0, 12))

    def _on_starting(self) -> None:
        self.draft["starting_pack"] = self.starting_var.get()
        self._fill_summary()

    def _starting_text(self) -> str:
        """汇总行用的一行摘要：标签 + 前几件 + 金币。"""
        bundle = self.app.bundle
        class_id = str(self.draft.get("class_id") or "")
        pack_id = str(self.draft.get("starting_pack") or "")
        options = api.starting_options(bundle, class_id, self.app.locale)["options"]
        row = next((item for item in options if item["id"] == pack_id), None)
        if row is None:
            return "—"
        # 只列前 3 件：这一栏是 label + value 两列，长了自己会把表格撑宽
        names = join(
            "%s×%d" % (item["name"], item["count"]) if item["count"] > 1 else item["name"]
            for item in row["items"][:3])
        if len(row["items"]) > 3:
            names += " …"
        text = row["label"]
        if names:
            text += "：" + names
        if row["gold"]:
            text += "（%d gp）" % row["gold"]
        return text

    def _on_name(self) -> None:
        self.draft[self._name_keys()[0]] = self.name_var.get()

    def _on_name_en(self) -> None:
        self.draft[self._name_keys()[1]] = self.name_en_var.get()

    def _fill_summary(self) -> None:
        bundle = self.app.bundle
        locale = self.app.locale
        draft = self.draft
        class_def = bundle.classes.get(str(draft.get("class_id") or ""))
        sub = bundle.subclasses.get(str(draft.get("subclass") or ""))
        species = bundle.species.get(str(draft.get("species") or ""))
        background = bundle.backgrounds.get(str(draft.get("background") or ""))
        rows = [
            (T("职业"), T("%s %d 级") % (class_def.name.get(locale) if class_def else "—",
                                  int(draft.get("class_level") or 0))),
            (T("子职"), sub.name.get(locale) if sub else "—"),
            (T("物种"), species.name.get(locale) if species else "—"),
            (T("背景"), background.name.get(locale) if background else "—"),
        ]
        scores = draft.get("scores") or {}
        bonus = draft.get("background_bonus") or {}
        final = {key: int(value) + int(bonus.get(key, 0)) for key, value in scores.items()}
        rows.append((T("属性"), "　".join("%s %d" % (ABILITY_ZH.get(k, k.upper()), v)
                                    for k, v in final.items())))
        rows.append((T("技能"), join(draft.get("skills") or ()) or "—"))
        rows.append((T("精通"), T("%d 件") % len(draft.get("masteries") or ())))
        class_id = str(draft.get("class_id") or "")
        rows.append((T("戏法"), str(len((draft.get("cantrips") or {}).get(class_id, ())))))
        rows.append((T("法术"), str(len((draft.get("prepared") or {}).get(class_id, ())))))
        if not self.editing:
            rows.append((T("起始装备"), self._starting_text()))
        self.summary.clear()
        for index, (caption, value) in enumerate(rows):
            self.summary.set_row(index, caption, value)


def _checked(var) -> bool:
    """`IntVar` 是不是勾上的。空值（输入框被清空）当没勾。"""
    try:
        return bool(int(var.get()))
    except (tk.TclError, ValueError):
        return False
