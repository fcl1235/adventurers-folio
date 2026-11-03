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

from .i18n import Catalog, T, join
from . import theme
from .widgets import COL_LEFT, COL_MID, COL_RIGHT, ListPane, ScrollText, section

# 显示用映射表：存中文原文，取值时按当前语言翻译（见 i18n.Catalog）
ABILITY_ZH = Catalog({"str": "力量", "dex": "敏捷", "con": "体质",
                      "int": "智力", "wis": "感知", "cha": "魅力"})
KIND_ZH = Catalog({"origin": "起源", "general": "通用",
                   "fighting_style": "战斗风格", "epic_boon": "传奇恩惠"})
STATUS_MARK = {"counted": "✓", "dice": "◆", "active": "▶",
               "onhit": "◈", "manual": "△", "text": "□"}
STATUS_TEXT = Catalog({
    "counted": "已计入数值：这条专长的加值/熟练/抗性算在角色卡里了。",
    "dice": "已接入掷骰：这条专长改的是掷骰形状（优势/劣势），不加数值，掷骰时会多掷一颗取高/取低。",
    "active": "使用时结算：这条专长给的是可以用一次的主动能力，点按钮才会产生效果，角色卡上的常驻数字不含它。",
    "onhit": "命中时结算：这条专长在攻击命中时追加伤害或效果，不进常驻数值，也不是按钮 —— 攻击掷骰里会把它列出来可选。",
    "manual": "只登记了规则，尚未计入数值：这条专长还需要手动处理。",
    "text": "只登记了规则，尚未计入数值：本程序没有把它算进任何数字。",
})


def _option_label(choice: dict, value: str, bundle) -> str:
    """把选项的内部值翻成中文。技能/工具/法术从内容里查，属性用固定表。"""
    kind = str(choice.get("kind") or "")
    if kind == "spell":
        # 法术名由服务端放进 `option_labels`（内容里查得到才给），查不到就退回 id
        return str((choice.get("option_labels") or {}).get(value) or value)
    if kind == "proficiency":
        # 混选的取值是**完整 token**：`skill.stealth` / `tool.thieves_tools`。
        # 靠前缀分流，只查内容里那两种，别猜。
        category, _, key = str(value).partition(".")
        if category == "tool":
            tool = bundle.tools.get("dnd2024.tool.%s" % key)
            return tool.name.zh if tool else key
        skill = bundle.skills.get("dnd2024.skill.%s" % key)
        return skill.name.zh if skill else key
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
        self._slots: dict = {}
        self._pick_ids: list[str] = []
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
        listed = section(left, T("专长"))
        listed.pack(fill="both", expand=True)
        ttk.Label(listed, text=T("✓ 已计入　◆ 改掷骰　▶ 用时算　△ 待手动　□ 仅文字"),
                  foreground=theme.DIM).pack(anchor="w")
        self.feats = ListPane(listed, height=20, width=28)
        self.feats.pack(fill="both", expand=True, pady=(2, 0))
        self.feats.list.bind("<<ListboxSelect>>", lambda _e: self._select_feat())

        # --- 左下：属性提升（4 级起，战士/盗贼多几次） ---------------------
        # 这一块就是 G35 的入口：以前只有 `new_character(feats=...)` 能登记专长，
        # 升到 4 级什么也不会发生。名额由 `sheet["feat_slots"]` 给（界面不算规则）。
        slot = section(left, T("属性提升"))
        slot.pack(fill="x", pady=(6, 0))
        self.slot_var = tk.StringVar(value="")
        ttk.Label(slot, textvariable=self.slot_var, wraplength=228,
                  justify="left").pack(anchor="w")
        self.pick_box = ttk.Combobox(slot, state="readonly", width=28)
        self.pick_box.pack(fill="x", pady=(2, 0))
        self.add_feat_button = ttk.Button(slot, text=T("加这条专长"),
                                          command=self.add_feat)
        self.add_feat_button.pack(anchor="w", pady=(4, 0))

        # --- 中：说明 -----------------------------------------------------
        intro = section(mid, T("说明"))
        intro.pack(fill="both", expand=True)
        self.text = ScrollText(intro, height=12, width=52)
        self.text.pack(fill="both", expand=True)

        # --- 中下：选择项 -------------------------------------------------
        self.choice_frame = section(mid, T("选择项"))
        self.choice_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.choice_box = ttk.Combobox(self.choice_frame, state="readonly", width=46)
        self.choice_box.pack(fill="x")
        self.choice_box.bind("<<ComboboxSelected>>", lambda _e: self._fill_options())
        self.options = ListPane(self.choice_frame, height=7, width=52)
        self.options.pack(fill="both", expand=True, pady=(4, 0))

        # --- 右：操作 -----------------------------------------------------
        actions = section(right, T("当前选择"))
        actions.pack(fill="x")
        self.summary_var = tk.StringVar(value="")
        ttk.Label(actions, textvariable=self.summary_var, wraplength=268,
                  justify="left").pack(anchor="w")

        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(6, 0))
        self.add_button = ttk.Button(buttons, text=T("加上"), command=self.add_pick)
        self.add_button.pack(side="left")
        self.remove_button = ttk.Button(buttons, text=T("去掉一个"), command=self.remove_pick)
        self.remove_button.pack(side="left", padx=(6, 0))
        self.clear_button = ttk.Button(buttons, text=T("清空"), command=self.clear_picks)
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
            self._slots = dict(sheet.get("feat_slots") or {})
            # 选中项按 `id#序号` 记。只有纯 id 的老调用（测试直接塞 id）才退回第一行。
            uids = {_uid(row) for row in self._feats}
            plain = {row["id"] for row in self._feats}
            if not self._feat_id:
                self._feat_id = _uid(self._feats[0]) if self._feats else ""
            elif self._feat_id not in uids and self._feat_id not in plain:
                self._feat_id = _uid(self._feats[0]) if self._feats else ""
            self._fill_slots()
            self._fill_list()
            self._fill_detail()
        finally:
            self._busy = False

    def _fill_slots(self) -> None:
        """左下那块：还剩几次、能加哪些。名单来自 `api.feat_options`（前提已判过）。"""
        slots = self._slots
        pending = int(slots.get("pending") or 0)
        levels = slots.get("levels") or "—"
        if int(slots.get("over") or 0) > 0:
            self.slot_var.set(T("属性提升：%s 级各一次；已用 %d 次，超出名额 %d 次")
                              % (levels, int(slots.get("used") or 0),
                                 int(slots.get("over") or 0)))
        elif pending > 0:
            self.slot_var.set(T("属性提升：%s 级各一次，还能加 %d 次")
                              % (levels, pending))
        else:
            self.slot_var.set(T("属性提升：%s 级各一次，都用完了") % levels)

        self._pick_ids: list[str] = []
        labels: list[str] = []
        if pending > 0:
            options = api.feat_options(self.app.bundle, self.app.actor,
                                       locale=self.app.locale)
            for row in options.get("feats") or []:
                # 只有「属性提升能选的」那几类才进这张名单：起源专长来自背景、
                # 战斗风格来自职业特性，从这里加会造出规则外的角色。
                if row["kind"] not in ("general", "epic_boon") or not row["selectable"]:
                    continue
                self._pick_ids.append(row["id"])
                labels.append(row["name"])
        self.pick_box.configure(values=labels)
        if labels:
            if self.pick_box.get() not in labels:
                self.pick_box.current(0)
            self.add_feat_button.configure(state="normal")
        else:
            self.pick_box.set("")
            self.add_feat_button.configure(state="disabled")

    def _fill_list(self) -> None:
        rows = []
        for row in self._feats:
            mark = STATUS_MARK.get(row.get("status") or "text", "□")
            tail = T("　（待选）") if row.get("pending") else ""
            # 清单行用 `id#序号` 当键：属性提升登记两次时，两行的 id 是一样的，
            # 用 id 当键会让「选第二行」永远落到第一行（改第二次的选择其实改了第一次）。
            rows.append((_uid(row), "%s %s%s" % (mark, row["name"], tail)))
        self.feats.fill(rows)
        if self._feat_id:
            self.feats.select_id(self._feat_id)
        if not self._feats:
            # 属性提升的入口在左下那块（4 级起才有名额），这里说清楚「为什么是空的」。
            self._status(T("这个角色还没有专长：背景的起始专长建卡时自动给，"
                         "4 级起的属性提升用左下的「加这条专长」。"))

    def _feat(self) -> dict:
        """当前选中的那一行。先按 `id#序号` 精确找，找不到再退回按 id 找第一行
        （测试与旧代码都直接给纯 id，不认序号）。"""
        for row in self._feats:
            if _uid(row) == self._feat_id:
                return row
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
        body = "%s（%s）\n\n%s" % (feat["name"], kind, feat.get("text") or "")
        spells = feat.get("spells") or []
        if spells:
            # 「始终准备」是这条专长给的东西里最容易被忘掉的一半：法术不在职业法术页里
            body += "\n\n" + T("始终准备：") + "\n" + "\n".join(
                "　· %s（%s）" % (row["name"], T("戏法") if not row.get("level")
                                  else T("%d 环") % int(row["level"]))
                for row in spells)
        pools = feat.get("resources") or []
        if pools:
            # 按法术绑定的池（妖精触碰「两道法术各一次」）逐条列名，
            # 否则两行都是「免费施放次数」，玩家分不出哪行是迷踪步
            per_spell = all(row.get("spell") for row in pools)
            body += "\n\n" + T("免费施放次数%s：") + "\n" % (T("（每道法术各一次）") if per_spell else "")
            body += "\n".join(
                T("　· %s：%d/%d（长休恢复）")
                % (row["label"], int(row["capacity"]) - int(row["used"]), int(row["capacity"]))
                for row in pools)
        self.text.set_text(body)
        self.honesty.set_text(STATUS_TEXT.get(feat.get("status") or "text",
                                              STATUS_TEXT["text"]))

        choices = feat.get("choices") or []
        labels = [T("%s（还差 %d 项）") % (row["label"], row["remaining"])
                  for row in choices]
        self.choice_box.configure(values=labels)
        ids = [row["id"] for row in choices]
        if not choices:
            self._choice_id = ""
            self.choice_box.set(T("这条专长没有需要选择的部分"))
            self.choice_box.configure(state="disabled")
            self.options.fill([])
            self.summary_var.set(T("已选专长：") + feat["name"])
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
        rows = []
        for value in choice.get("options") or []:
            used = picked.count(value)
            label = _option_label(choice, str(value), self.app.bundle)
            rows.append((str(value), "%s%s" % (label, T("　（已选 %d）") % used if used else "")))
        self.options.fill(rows)
        self._fill_summary(choice, picked)

    def _fill_summary(self, choice: dict, picked: list[str]) -> None:
        names = [_option_label(choice, item, self.app.bundle) for item in picked]
        if names:
            text = T("已选：") + join(names)
        else:
            text = T("还没选。")
        remaining = int(choice.get("remaining") or 0)
        if remaining > 0:
            text += "\n" + T("还差 %d 项。") % remaining
        else:
            text += "\n" + T("已选满。")
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
        self.status.configure(foreground=theme.WARN if error else theme.DIM)

    # --- 写数据 -----------------------------------------------------------
    def add_feat(self) -> bool:
        """用一次属性提升名额加一条专长。

        **不带选择项**：属性提升的「+2 还是两项 +1」在下面「选择项」那块里选，
        加进来以后它是「还差 2 项」的状态。一次性把选择也带走当然更好，
        但那要求这里再实现一遍「选两项、可重复」的界面 —— 现成的选择项区域
        已经能做这件事，再写一套只会两处不一致。
        """
        if self._busy:
            return False
        label = self.pick_box.get()
        ids = getattr(self, "_pick_ids", [])
        values = list(self.pick_box.cget("values") or ())
        if not label or label not in values:
            self._status(T("先在左边选一条要加的专长。"), error=True)
            return False
        feat_id = ids[values.index(label)]
        try:
            actor = api.add_feat(self.app.actor, self.app.bundle, feat_id,
                                 locale=self.app.locale)
        except api.DndError as error:
            self._status(str(error), error=True)
            return False
        self._status("")
        self._choice_id = ""
        self.app.apply_actor(actor)        # 这一步会 refresh，`_feats` 已经换成新的
        mine = [row for row in self._feats if row["id"] == feat_id]
        self._feat_id = _uid(mine[-1]) if mine else feat_id
        self.feats.select_id(self._feat_id)
        self._fill_detail()
        row = self._feat()
        needs = row.get("pending")
        if needs:
            self._status(T("已加「%s」：在下面把选择项选完（属性才会计入）")
                         % row.get("name", label))
        else:
            self._status(T("已加「%s」") % row.get("name", label))
        return True

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
            self._status(T("先选一条带选择项的专长。"), error=True)
            return False
        value = self.options.selected_id()
        if action != "clear" and not value:
            self._status(T("先在下面选一个候选项。"), error=True)
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
                                        index=int(feat.get("index") or 0),
                                        locale=self.app.locale)
        except api.DndError as error:
            self._status(str(error), error=True)
            return False

        self._status("")
        self.app.apply_actor(actor)
        # 这里必须写回 `id#序号`，不能写纯 id：属性提升登记两次时两行同 id，
        # 写纯 id 会让下一次「加上」落到**第一行**上 —— 表现是「第二次怎么选都
        # 超过 2 项」，而第一次的选择被悄悄改掉。
        self._feat_id = _uid(feat)
        self._choice_id = choice["id"]
        self._fill_detail()
        self._status(T("%s：已选 %d 项") % (choice["label"], len(updated)))
        return True


def _remove_once(picked: list[str], value: str) -> list[str]:
    """去掉**一个**匹配项。属性提升要能「力量、力量」，所以不能按值全删。"""
    out = list(picked)
    if value in out:
        out.remove(value)
    return out


def _uid(row: dict) -> str:
    """清单行的键：`<专长 id>#<第几次>`。序号在同一专长只出现一次时也照写，
    免得「只有一条时用 id、有两条时用 id#序号」这种两套规则。"""
    return "%s#%d" % (row["id"], int(row.get("index") or 0))
