# -*- coding: utf-8 -*-
"""专长页：看到自己拿了什么、还差哪些没选、以及哪些其实没算进数值。

第三块要求「诚实」：`api.character_sheet()` 给每条专长一个 `status`，
这里必须原样说给玩家听。把「只有规则文字」的专长画得像已经生效，
比没做这个功能更糟 —— 玩家会拿着错的数字上桌。

选择项一律提交给 `api.set_feat_choice` 校验（数量、候选、专精须已熟练），
失败时显示原因并回到服务端状态。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import dnd5r.api as api

from .widgets import COL_LEFT, COL_MID, COL_RIGHT, ListPane, ScrollText, section

ABILITY_ZH = {"str": "力量", "dex": "敏捷", "con": "体质",
              "int": "智力", "wis": "感知", "cha": "魅力"}
KIND_ZH = {"origin": "起源", "general": "通用",
           "fighting_style": "战斗风格", "epic_boon": "传奇恩惠"}
STATUS_MARK = {"counted": "✓", "active": "▶", "manual": "△", "text": "□"}
STATUS_TEXT = {
    "counted": "已计入数值：这条专长的加值/熟练/抗性算在角色卡里了。",
    "active": "使用时结算：点能力按钮才会产生效果，角色卡上的常驻数字不含它。",
    "manual": "只登记了规则，尚未计入数值：优势/劣势暂时没有消费方，需要手动处理。",
    "text": "只登记了规则，尚未计入数值：本程序没有把它算进任何数字。",
}


def _option_label(kind: str, value: str, bundle) -> str:
    """把选项的内部值翻成中文。技能从内容里查，属性用固定表。"""
    if kind in ("skill", "expertise"):
        skill = bundle.skills.get("dnd2024.skill.%s" % value)
        return skill.name.zh if skill else value
    return ABILITY_ZH.get(value, value)


class FeatPage(ttk.Frame):
    """专长页。`app` 只用 actor / bundle / locale / refresh / apply_actor。"""

    def __init__(self, master, app) -> None:
        super().__init__(master, padding=(6, 4))
        self.app = app
        self._feats: list[dict] = []
        self._feat_id = ""
        self._choice_id = ""
        self._busy = False
        self._build()

    # --- 骨架 -------------------------------------------------------------
    def _build(self) -> None:
        left = ttk.Frame(self, width=COL_LEFT)
        mid = ttk.Frame(self, width=COL_MID)
        right = ttk.Frame(self, width=COL_RIGHT)
        left.grid(row=0, column=0, sticky="nsw")
        mid.grid(row=0, column=1, sticky="nsew", padx=8)
        right.grid(row=0, column=2, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # --- 左：专长清单 -------------------------------------------------
        listed = section(left, "专长")
        listed.pack(fill="both", expand=True)
        ttk.Label(listed, text="✓ 已计入　▶ 用时算　△ 待手动　□ 仅文字",
                  foreground="#666666").pack(anchor="w")
        self.feats = ListPane(listed, height=20, width=28)
        self.feats.pack(fill="both", expand=True, pady=(2, 0))
        self.feats.list.bind("<<ListboxSelect>>", lambda _e: self._select_feat())

        # --- 中：说明 -----------------------------------------------------
        intro = section(mid, "说明")
        intro.pack(fill="both", expand=True)
        self.text = ScrollText(intro, height=12, width=52)
        self.text.pack(fill="both", expand=True)

        # --- 中下：选择项 -------------------------------------------------
        self.choice_frame = section(mid, "选择项")
        self.choice_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.choice_box = ttk.Combobox(self.choice_frame, state="readonly", width=46)
        self.choice_box.pack(fill="x")
        self.choice_box.bind("<<ComboboxSelected>>", lambda _e: self._fill_options())
        self.options = ListPane(self.choice_frame, height=7, width=52)
        self.options.pack(fill="both", expand=True, pady=(4, 0))

        # --- 右：操作 -----------------------------------------------------
        actions = section(right, "当前选择")
        actions.pack(fill="x")
        self.summary_var = tk.StringVar(value="")
        ttk.Label(actions, textvariable=self.summary_var, wraplength=268,
                  justify="left").pack(anchor="w")

        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(6, 0))
        self.add_button = ttk.Button(buttons, text="加上", command=self.add_pick)
        self.add_button.pack(side="left")
        self.remove_button = ttk.Button(buttons, text="去掉一个", command=self.remove_pick)
        self.remove_button.pack(side="left", padx=(6, 0))
        self.clear_button = ttk.Button(buttons, text="清空", command=self.clear_picks)
        self.clear_button.pack(side="left", padx=(6, 0))

        self.honesty = ScrollText(right, height=8, width=30)
        self.honesty.pack(fill="both", expand=True, pady=(8, 0))

        self.status_var = tk.StringVar(value="")
        self.status = ttk.Label(self, textvariable=self.status_var, anchor="w")
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

    # --- 数据 -------------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        self._busy = True
        try:
            self._feats = list(sheet.get("feats") or [])
            if not self._feat_id and self._feats:
                self._feat_id = self._feats[0]["id"]
            if self._feat_id not in {row["id"] for row in self._feats}:
                self._feat_id = self._feats[0]["id"] if self._feats else ""
            self._fill_list()
            self._fill_detail()
        finally:
            self._busy = False

    def _fill_list(self) -> None:
        rows = []
        for row in self._feats:
            mark = STATUS_MARK.get(row.get("status") or "text", "□")
            tail = "　（待选）" if row.get("pending") else ""
            rows.append((row["id"], "%s %s%s" % (mark, row["name"], tail)))
        self.feats.fill(rows)
        if self._feat_id:
            self.feats.select_id(self._feat_id)
        if not self._feats:
            self._status("这个角色还没有专长：建角色时选，或用升级流程加。")

    def _feat(self) -> dict:
        for row in self._feats:
            if row["id"] == self._feat_id:
                return row
        return {}

    def _choice(self) -> dict:
        for row in self._feat().get("choices") or []:
            if row["id"] == self._choice_id:
                return row
        return {}

    def _select_feat(self) -> None:
        picked = self.feats.selected_id()
        if not picked or picked == self._feat_id:
            return
        self._feat_id = picked
        self._choice_id = ""
        self._fill_detail()

    def _fill_detail(self) -> None:
        feat = self._feat()
        if not feat:
            self.text.set_text("")
            self.honesty.set_text("")
            self.summary_var.set("")
            self.choice_box.configure(values=[])
            self.options.fill([])
            self._enable(False)
            return
        kind = KIND_ZH.get(feat.get("kind") or "", feat.get("kind") or "")
        self.text.set_text("%s（%s）\n\n%s" % (feat["name"], kind, feat.get("text") or ""))
        self.honesty.set_text(STATUS_TEXT.get(feat.get("status") or "text",
                                              STATUS_TEXT["text"]))

        choices = feat.get("choices") or []
        labels = ["%s（还差 %d 项）" % (row["label"], row["remaining"])
                  for row in choices]
        self.choice_box.configure(values=labels)
        ids = [row["id"] for row in choices]
        if not choices:
            self._choice_id = ""
            self.choice_box.set("这条专长没有需要选择的部分")
            self.choice_box.configure(state="disabled")
            self.options.fill([])
            self.summary_var.set("已选专长：" + feat["name"])
            self._enable(False)
            return
        self.choice_box.configure(state="readonly")
        if self._choice_id not in ids:
            self._choice_id = ids[0]
        self.choice_box.current(ids.index(self._choice_id))
        self._enable(True)
        self._fill_options()

    def _fill_options(self) -> None:
        choice = self._choice()
        if not choice:
            self.options.fill([])
            return
        picked = list(choice.get("picked") or [])
        kind = str(choice.get("id") or "")
        rows = []
        for value in choice.get("options") or []:
            used = picked.count(value)
            label = _option_label(kind, str(value), self.app.bundle)
            rows.append((str(value), "%s%s" % (label, "　（已选 %d）" % used if used else "")))
        self.options.fill(rows)
        self._fill_summary(choice, picked)

    def _fill_summary(self, choice: dict, picked: list[str]) -> None:
        kind = str(choice.get("id") or "")
        names = [_option_label(kind, item, self.app.bundle) for item in picked]
        if names:
            text = "已选：" + "、".join(names)
        else:
            text = "还没选。"
        remaining = int(choice.get("remaining") or 0)
        if remaining > 0:
            text += "\n还差 %d 项。" % remaining
        else:
            text += "\n已选满。"
        self.summary_var.set(text)
        # 选满了还能「去掉一个」，但「加上」会被服务端拒绝 —— 按钮先灰掉更诚实
        self.add_button.configure(
            state="normal" if remaining > 0 and int(choice.get("count") or 0) > 0
            else "disabled")

    def _enable(self, enabled: bool) -> None:
        for widget in (self.add_button, self.remove_button, self.clear_button):
            widget.configure(state="normal" if enabled else "disabled")

    def _status(self, text: str, error: bool = False) -> None:
        self.status_var.set(text)
        self.status.configure(foreground="#a33" if error else "#666666")

    # --- 写数据 -----------------------------------------------------------
    def add_pick(self) -> bool:
        return self._apply("add")

    def remove_pick(self) -> bool:
        return self._apply("remove")

    def clear_picks(self) -> bool:
        return self._apply("clear")

    def _apply(self, action: str) -> bool:
        """三种操作走同一条路：算出新列表 → 交给服务端校验 → 整只换角色。

        `action` 用字符串而不是回调：`self.clear_picks is self.clear_picks` 是 False
        （绑定方法每次取都是新对象），用身份比较会静默走错分支。
        """
        if self._busy:
            return False
        feat = self._feat()
        choice = self._choice()
        if not feat or not choice:
            self._status("先选一条带选择项的专长。", error=True)
            return False
        value = self.options.selected_id()
        if action != "clear" and not value:
            self._status("先在下面选一个候选项。", error=True)
            return False

        picked = list(choice.get("picked") or [])
        if action == "add":
            updated = picked + [value]
        elif action == "remove":
            updated = _remove_once(picked, value)
        else:
            updated = []
        try:
            actor = api.set_feat_choice(self.app.actor, self.app.bundle,
                                        feat["id"], choice["id"], updated,
                                        locale=self.app.locale)
        except api.DndError as error:
            self._status(str(error), error=True)
            return False

        self._status("")
        self.app.apply_actor(actor)
        self._feat_id = feat["id"]
        self._choice_id = choice["id"]
        self._fill_detail()
        self._status("%s：已选 %d 项" % (choice["label"], len(updated)))
        return True


def _remove_once(picked: list[str], value: str) -> list[str]:
    """去掉**一个**匹配项。属性提升要能「力量、力量」，所以不能按值全删。"""
    out = list(picked)
    if value in out:
        out.remove(value)
    return out
