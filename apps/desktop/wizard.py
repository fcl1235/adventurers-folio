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

from . import theme
from .widgets import ABILITY_ZH, KeyValue, ListPane, ScrollFrame, section


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
        self.steps = api.WIZARD_STEPS
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
        for key, text, action in (("cancel", "取消", self.cancel),
                                  ("back", "← 上一步", self.prev_step),
                                  ("next", "下一步 →", self.next_step),
                                  ("finish", "建卡", self.finish)):
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

    def finish(self) -> None:
        """建卡 / 改卡。有错就跳回第一个出错的那一步，**不弹窗** —— 弹窗在零弹窗
        铁律下是禁止的，而且一个「有错误」的弹窗什么也没告诉玩家。"""
        problems = api.draft_problems(self.app.bundle, self.draft, self.app.locale)
        blocking = [item for item in problems if item.get("level", "error") != "warn"]
        if blocking:
            first = blocking[0]
            target = api.STEP_INDEX.get(first["step"], 0)
            self.go(target)
            self._set_status("还差这些：" + "；".join(item["text"] for item in blocking[:3]),
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
            self._set_status("建卡失败：%s" % exc, warn=True)
            return
        self.app.finish_wizard(actor, editing=self.editing)

    # --- 渲染 -------------------------------------------------------------
    def render(self) -> None:
        _clear(self.body)
        self.progress_var.set("第 %d / %d 步 · %s"
                              % (self.index + 1, len(self.steps), self.current["title"]))
        for index, button in enumerate(self.step_buttons):
            # 用 style 而不是 state：灰掉当前步会让人以为「这步不能改」
            button.configure(style="Active.Mini.TButton" if index == self.index
                             else "Mini.TButton")
        builder = getattr(self, "_step_%s" % self.current["key"], None)
        if builder is None:                       # 理论上不会发生，但不许静默白屏
            ttk.Label(self.body, text="这一步还没做：%s" % self.current["key"]).pack()
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
        problems = [item for item in
                    api.draft_problems(self.app.bundle, self.draft, self.app.locale)
                    if item["step"] == key]
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
        ttk.Label(left, text="职业").pack(anchor="w")
        pane = ListPane(left, height=14, width=22)
        pane.pack(fill="both", expand=True)
        pane.fill([(row["id"], "%s（d%dd）" % (row["name"], row["hit_die"]))
                   for row in options["classes"]])
        self.class_pane = pane

        right = ttk.Frame(self.body)
        right.pack(side="left", fill="both", expand=True)
        detail = section(right, "职业详情")
        detail.pack(fill="x")
        self.class_detail = ttk.Label(detail, text="", style="Dim.TLabel",
                                      justify="left", wraplength=640)
        self.class_detail.pack(anchor="w")

        row = ttk.Frame(right)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="等级").pack(side="left")
        self.level_var = tk.IntVar(value=int(self.draft.get("class_level") or 1))
        spin = ttk.Spinbox(row, from_=1, to=20, width=4, textvariable=self.level_var,
                           command=self._on_level)
        spin.pack(side="left", padx=(6, 16))
        self.level_var.trace_add("write", lambda *_: self._on_level())
        ttk.Label(row, text="子职").pack(side="left")
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
            self.class_detail.configure(text="先选一个职业。")
            # 职业清空了，子职下拉也得跟着清 —— 留着上一个职业的子职，
            # 玩家会以为「这个职业也能选它」。
            self._subclass_ids = []
            self.subclass_box.configure(values=["（暂无）"], state="disabled")
            self.subclass_box.current(0)
            return
        class_def = self.app.bundle.class_def(class_id)
        level = int(self.draft.get("class_level") or 1)
        marks = []
        if class_def.hit_die:
            marks.append("生命骰 d%d" % class_def.hit_die)
        if class_def.primary:
            marks.append("主属性 " + "、".join(ABILITY_ZH.get(k, k.upper())
                                          for k in class_def.primary))
        if class_def.saves:
            marks.append("豁免熟练 " + "、".join(ABILITY_ZH.get(k, k.upper())
                                           for k in class_def.saves))
        marks.append("技能 %d 项" % class_def.skill_choices)
        if class_def.caster.value != "none":
            marks.append("施法（%s）" % ABILITY_ZH.get(class_def.casting_ability, "?"))
        mastery = api.mastery_choices(self.app.bundle, class_id, level)
        if mastery["count"]:
            marks.append("武器精通 %d 件" % mastery["count"])
        self.class_detail.configure(text="　·　".join(marks))

        info = api.subclass_choices(self.app.bundle, class_id, level, self.app.locale)
        labels = ["（暂无）"] + [row["name"] for row in info["options"]]
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
        ttk.Label(left, text="背景").pack(anchor="w")
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
            self.background_detail.configure(text="先选一个背景。")
            return
        rows = [item.summary.get(self.app.locale)]
        rows.append("属性加值：" + "、".join(ABILITY_ZH.get(k, k.upper())
                                        for k in item.abilities))
        if item.origin_feat:
            feat = self.app.bundle.feats.get(item.origin_feat)
            rows.append("起始专长：%s" % (feat.name.get(self.app.locale)
                                     if feat else item.origin_feat))
        if item.skills:
            rows.append("技能熟练：" + "、".join(item.skills))
        if item.tool_label is not None:
            rows.append("工具：" + item.tool_label.get(self.app.locale))
        self.background_detail.configure(text="\n".join(rows))

    # --- 第 3 步：物种 -----------------------------------------------------
    def _step_species(self) -> None:
        options = api.step_options(self.app.bundle, "species", self.draft,
                                   self.app.locale)
        left = ttk.Frame(self.body)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text="物种").pack(anchor="w")
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
            self.species_detail.configure(text="先选一个物种。（2024 规则里物种不是必选）")
            return
        size_zh = {"tiny": "微型", "small": "小型", "medium": "中型",
                   "large": "大型"}
        rows = [item.summary.get(self.app.locale),
                "体型 %s · 速度 %d 尺" % ("/".join(size_zh.get(s, s) for s in item.size),
                                     item.speed)]
        for power in item.powers:
            rows.append("\n【%s】%s" % (power.name.get(self.app.locale),
                                       power.text.get(self.app.locale)))
        self.species_detail.configure(text="\n".join(rows))

    # --- 第 4 步：属性 -----------------------------------------------------
    def _step_scores(self) -> None:
        options = api.step_options(self.app.bundle, "scores", self.draft,
                                   self.app.locale)
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        box = section(top, "生成方式")
        box.pack(side="left", fill="x")
        self.mode_var = tk.StringVar(value=str(self.draft.get("score_mode")
                                               or "standard_array"))
        for key in options["modes"]:
            ttk.Radiobutton(box, text=options["mode_zh"].get(key, key),
                            value=key, variable=self.mode_var,
                            command=self._on_mode).pack(anchor="w")

        roll = section(top, "快捷")
        roll.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ttk.Button(roll, text="标准数组", style="Mini.TButton",
                   command=lambda: self._preset_scores("standard_array")).pack(anchor="w")
        ttk.Button(roll, text="掷 4d6 弃最低", style="Mini.TButton",
                   command=lambda: self._preset_scores("roll")).pack(anchor="w")
        self.cost_var = tk.StringVar()
        ttk.Label(roll, textvariable=self.cost_var, style="Dim.TLabel").pack(anchor="w")

        # `section()` 内部已经 pack 了一个说明标签，直接往里 grid 会撞管理器。
        # 所以这里自己建区框，再把网格放进一个中间 Frame。
        grid_box = ttk.LabelFrame(self.body, text="属性值", padding=(8, 4))
        grid_box.pack(fill="x", pady=(8, 0))
        ttk.Label(grid_box, text="上限 15 是购买上限；16 以上只能由背景与专长提供。",
                  style="Dim.TLabel").pack(anchor="w")
        grid = ttk.Frame(grid_box)
        grid.pack(anchor="w")
        self.score_vars: dict[str, tk.IntVar] = {}
        for index, key in enumerate(options["keys"]):
            cell = ttk.Frame(grid)
            cell.grid(row=0, column=index, padx=(0, 12), sticky="w")
            ttk.Label(cell, text=ABILITY_ZH.get(key, key.upper())).pack()
            var = tk.IntVar(value=int((self.draft.get("scores") or {}).get(key, 10)))
            ttk.Spinbox(cell, from_=1, to=20, width=4, textvariable=var,
                        command=self._on_scores).pack()
            var.trace_add("write", lambda *_: self._on_scores())
            self.score_vars[key] = var

        bonus = section(self.body, "背景加值",
                        "从背景给的那几项属性里分：一项 +2 加一项 +1，或三项各 +1。")
        bonus.pack(fill="x", pady=(8, 0))
        self.bonus_var = tk.StringVar()
        self.bonus_box = ttk.Combobox(bonus, textvariable=self.bonus_var,
                                      state="readonly", width=44)
        self.bonus_box.pack(anchor="w")
        self.bonus_box.bind("<<ComboboxSelected>>", self._on_bonus)
        self._fill_bonus_box()
        self._refresh_cost()

    def _on_mode(self) -> None:
        self.draft["score_mode"] = self.mode_var.get()
        self._refresh_cost()
        self._report()

    def _preset_scores(self, mode: str) -> None:
        """按选定的方式重新发一套数。**掷骰走内核的 rng**（C4：界面不 import random）。"""
        self.draft["score_mode"] = mode
        if self.mode_var.get() != mode:
            self.mode_var.set(mode)
        if mode == "standard_array":
            scores = api.score_presets()["standard"]
        elif mode == "roll":
            scores = api.random_scores()
        else:
            return
        self.draft["scores"] = dict(scores)
        for key, var in getattr(self, "score_vars", {}).items():
            var.set(int(scores.get(key, 10)))
        self._refresh_cost()
        self._report()

    def _on_scores(self) -> None:
        scores = {}
        for key, var in self.score_vars.items():
            try:
                scores[key] = int(var.get())
            except (tk.TclError, ValueError):
                return                       # 输入框里是空的/半个字符，等它填完
        self.draft["scores"] = scores
        self._refresh_cost()
        self._report()

    def _fill_bonus_box(self) -> None:
        plans = self._bonus_plans()
        self._bonus_labels = []
        for plan in plans:
            self._bonus_labels.append(
                "、".join("%s %+d" % (ABILITY_ZH.get(k, k.upper()), v)
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
        scores = self.draft.get("scores") or {}
        if self.draft.get("score_mode") == "point_buy":
            try:
                spent = api.score_cost(scores)
            except api.DndError as exc:
                self.cost_var.set(str(exc))
                return
            budget = api.score_presets()["budget"]
            self.cost_var.set("点买已花 %d / %d 点" % (spent, budget))
            return
        final = dict(scores)
        for key, value in (self.draft.get("background_bonus") or {}).items():
            if key in final:
                final[key] = final[key] + int(value)
        pairs = "　".join("%s %d" % (ABILITY_ZH.get(k, k.upper()), final.get(k, 0))
                          for k in scores)
        self.cost_var.set("加值后：" + pairs if pairs else "")

    # --- 第 5 步：技能 -----------------------------------------------------
    def _step_skills(self) -> None:
        options = api.step_options(self.app.bundle, "skills", self.draft,
                                   self.app.locale)
        head = ttk.Frame(self.body)
        head.pack(fill="x")
        ttk.Label(head, text="从本职业技能表里选 %d 项" % options["choices"],
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
                text += "　— 背景已给"
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
        self.skill_count_var.set("已选 %d / %d" % (len(self.draft.get("skills") or []), need))

    # --- 第 6 步：武器精通 -------------------------------------------------
    def _step_masteries(self) -> None:
        options = api.step_options(self.app.bundle, "masteries", self.draft,
                                   self.app.locale)
        head = ttk.Frame(self.body)
        head.pack(fill="x")
        ttk.Label(head, text="选 %d 件武器的精通" % options["count"],
                  font=(theme.UI_FONT, 11, "bold")).pack(side="left")
        ttk.Label(head, text="只记录、不结算：精通都要在命中后做选择",
                  style="Dim.TLabel").pack(side="left", padx=(12, 0))
        self.mastery_count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.mastery_count_var).pack(side="right")

        if not options["options"]:
            ttk.Label(self.body, text="这个职业没有武器精通，这一步直接跳过。",
                      style="Dim.TLabel").pack(anchor="w", pady=12)
            self.mastery_count_var.set("")
            return

        scroller = ScrollFrame(self.body, height=430)
        scroller.pack(fill="both", expand=True, pady=(6, 0))
        self.mastery_vars: dict[str, tk.IntVar] = {}
        chosen = set(self.draft.get("masteries") or ())
        for row in options["options"]:
            var = tk.IntVar(value=1 if row["id"] in chosen else 0)
            mastery = row["mastery"] or "—"
            text = "%s　%s　精通:%s" % (row["name"], row["damage"], mastery)
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
        self.mastery_count_var.set("已选 %d / %d"
                                   % (len(self.draft.get("masteries") or []), need))

    # --- 第 7 步：法术 -----------------------------------------------------
    def _step_spells(self) -> None:
        options = api.step_options(self.app.bundle, "spells", self.draft,
                                   self.app.locale)
        class_id = str(self.draft.get("class_id") or "")
        if not options["caster"]:
            ttk.Label(self.body, text="这个职业不施法，这一步直接跳过。",
                      style="Dim.TLabel").pack(anchor="w", pady=12)
            return

        head = ttk.Frame(self.body)
        head.pack(fill="x")
        ttk.Label(head, text="戏法 %d 个 · 准备法术 %d 个"
                             % (options["cantrip_limit"], options["prepared_limit"]),
                  font=(theme.UI_FONT, 11, "bold")).pack(side="left")
        self.spell_count_var = tk.StringVar()
        ttk.Label(head, textvariable=self.spell_count_var).pack(side="right")

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

        cantrip_box = section(left, "戏法")
        cantrip_box.pack(fill="both", expand=True)
        scroller = ScrollFrame(cantrip_box, height=390)
        scroller.pack(fill="both", expand=True)
        for row in options["cantrips"]:
            var = tk.IntVar(value=1 if row["id"] in chosen_cantrips else 0)
            ttk.Checkbutton(scroller.body, text=row["name"], variable=var,
                            command=self._on_spells).pack(anchor="w")
            var.trace_add("write", lambda *_: self._on_spells(silent=True))
            self.cantrip_vars[row["id"]] = var

        prepared_box = section(right, "准备法术（按环）")
        prepared_box.pack(fill="both", expand=True)
        scroller2 = ScrollFrame(prepared_box, height=390)
        scroller2.pack(fill="both", expand=True)
        for group in options["levels"]:
            ttk.Label(scroller2.body, text="%d 环" % group["level"],
                      font=(theme.UI_FONT, 10, "bold")).pack(anchor="w", pady=(4, 0))
            for row in group["spells"]:
                mark = "（专注）" if row["concentration"] else ""
                var = tk.IntVar(value=1 if row["id"] in chosen_prepared else 0)
                ttk.Checkbutton(scroller2.body, text=row["name"] + mark, variable=var,
                                command=self._on_spells).pack(anchor="w")
                var.trace_add("write", lambda *_: self._on_spells(silent=True))
                self.prepared_vars[row["id"]] = var
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
        self.spell_count_var.set("戏法 %d · 法术 %d" % (cantrips, prepared))

    # --- 第 8 步：汇总 -----------------------------------------------------
    def _step_summary(self) -> None:
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        name_box = section(top, "名字")
        name_box.pack(side="left", fill="x")
        self.name_var = tk.StringVar(value=str(self.draft.get("name_zh") or ""))
        ttk.Entry(name_box, textvariable=self.name_var, width=24).pack(side="left")
        self.name_var.trace_add("write", lambda *_: self._on_name())
        en_box = section(top, "英文名", "只用于双语内容回退，可以留空。")
        en_box.pack(side="left", fill="x", padx=(8, 0))
        self.name_en_var = tk.StringVar(value=str(self.draft.get("name_en") or ""))
        ttk.Entry(en_box, textvariable=self.name_en_var, width=24).pack(side="left")
        self.name_en_var.trace_add("write", lambda *_: self._on_name_en())

        table = section(self.body, "确认一下")
        table.pack(fill="both", expand=True, pady=(8, 0))
        # 9 行正好是 `_fill_summary()` 铺的条数。多给几行只会多出 3 条空白，
        # 白占高度（这个窗口的高度预算是按像素算的）。
        self.summary = KeyValue(table, rows=9)
        self.summary.pack(anchor="w")
        self._fill_summary()

    def _on_name(self) -> None:
        self.draft["name_zh"] = self.name_var.get()

    def _on_name_en(self) -> None:
        self.draft["name_en"] = self.name_en_var.get()

    def _fill_summary(self) -> None:
        bundle = self.app.bundle
        locale = self.app.locale
        draft = self.draft
        class_def = bundle.classes.get(str(draft.get("class_id") or ""))
        sub = bundle.subclasses.get(str(draft.get("subclass") or ""))
        species = bundle.species.get(str(draft.get("species") or ""))
        background = bundle.backgrounds.get(str(draft.get("background") or ""))
        rows = [
            ("职业", "%s %d 级" % (class_def.name.get(locale) if class_def else "—",
                                  int(draft.get("class_level") or 0))),
            ("子职", sub.name.get(locale) if sub else "—"),
            ("物种", species.name.get(locale) if species else "—"),
            ("背景", background.name.get(locale) if background else "—"),
        ]
        scores = draft.get("scores") or {}
        bonus = draft.get("background_bonus") or {}
        final = {key: int(value) + int(bonus.get(key, 0)) for key, value in scores.items()}
        rows.append(("属性", "　".join("%s %d" % (ABILITY_ZH.get(k, k.upper()), v)
                                    for k, v in final.items())))
        rows.append(("技能", "、".join(draft.get("skills") or ()) or "—"))
        rows.append(("精通", "%d 件" % len(draft.get("masteries") or ())))
        class_id = str(draft.get("class_id") or "")
        rows.append(("戏法", str(len((draft.get("cantrips") or {}).get(class_id, ())))))
        rows.append(("法术", str(len((draft.get("prepared") or {}).get(class_id, ())))))
        self.summary.clear()
        for index, (caption, value) in enumerate(rows):
            self.summary.set_row(index, caption, value)


def _checked(var) -> bool:
    """`IntVar` 是不是勾上的。空值（输入框被清空）当没勾。"""
    try:
        return bool(int(var.get()))
    except (tk.TclError, ValueError):
        return False
