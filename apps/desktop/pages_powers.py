# -*- coding: utf-8 -*-
"""能力页：资源池、能力清单、防御信息。

这一页解决的是「我有什么、还剩几次、哪些能点」——以前这些只存在于 sheet 里，
玩家看不到。三件事各有各的坑：

  1. 资源池的剩余/上限来自 `sheet["pools"]`（已扣掉用掉的次数），界面不自己算。
  2. 能力清单里的 `blocked` 是「现在为什么不能用」（没资源、耗了动作、变形禁令），
     直接把服务端给的理由显示出来 —— 自己判一遍必然与执行时对不上。
  3. `status` 是诚实标记：只有文字的能力不许画得像已经生效。

「使用」按钮走 `api.use_power`，返回的报告（事件 + 掷骰明细）原样贴到右栏。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import dnd5r.api as api

from .widgets import COL_LEFT, COL_MID, COL_RIGHT, KeyValue, ListPane, ScrollText, section

REFRESH_ZH = {"long_rest": "长休恢复", "short_rest": "短休恢复",
              "initiative": "遭遇开始", "never": "不自动恢复", "turn": "每回合"}
SENSE_ZH = {"darkvision": "黑暗视觉", "blindsight": "盲视",
            "tremorsense": "震颤感知", "truesight": "真实视觉"}
STATUS_MARK = {"counted": "✓", "dice": "◆", "active": "▶", "manual": "△", "text": "□"}
STATUS_ZH = {"counted": "已计入数值", "dice": "改掷骰", "active": "使用时结算",
             "manual": "待手动处理", "text": "仅规则文字"}
KIND_ZH = {"passive": "被动", "activated": "主动", "reaction": "反应",
           "triggered": "触发"}


class PowersPage(ttk.Frame):
    """能力页。`app` 只用 actor / bundle / locale / refresh。"""

    def __init__(self, master, app) -> None:
        super().__init__(master, padding=(6, 4))
        self.app = app
        self._powers: list[dict] = []
        self._pools: list[dict] = []
        self._power_id = ""
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

        # --- 左：资源池 ---------------------------------------------------
        pools = section(left, "资源")
        pools.pack(fill="x")
        self.pools = KeyValue(pools, rows=9)
        self.pools.pack(fill="x")

        defense = section(left, "防御")
        defense.pack(fill="x", pady=(8, 0))
        self.defense = KeyValue(defense, rows=6)
        self.defense.pack(fill="x")

        # --- 中：能力清单 + 说明 ------------------------------------------
        listed = section(mid, "能力")
        listed.pack(fill="both", expand=True)
        ttk.Label(listed, text="✓ 已计入　◆ 改掷骰　▶ 用时算　△ 待手动　□ 仅文字",
                  foreground="#666666").pack(anchor="w")
        self.powers = ListPane(listed, height=10, width=52)
        self.powers.pack(fill="both", expand=True, pady=(2, 0))
        self.powers.list.bind("<<ListboxSelect>>", lambda _e: self._select_power())

        detail = section(mid, "说明")
        detail.pack(fill="both", expand=True, pady=(6, 0))
        self.text = ScrollText(detail, height=8, width=52)
        self.text.pack(fill="both", expand=True)

        # --- 右：使用 -----------------------------------------------------
        use = ttk.Frame(right)
        use.pack(fill="x")
        self.use_button = ttk.Button(use, text="使用这项能力", command=self.use_selected)
        self.use_button.pack(side="left")
        self.blocked_var = tk.StringVar(value="")
        ttk.Label(use, textvariable=self.blocked_var, foreground="#a33",
                  wraplength=290, justify="left").pack(anchor="w", pady=(4, 0))

        result = section(right, "使用结果")
        result.pack(fill="both", expand=True, pady=(6, 0))
        self.report = ScrollText(result, height=16, width=30)
        self.report.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="")
        self.status = ttk.Label(self, textvariable=self.status_var, anchor="w")
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

    # --- 数据 -------------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        self._busy = True
        try:
            self._powers = list(sheet.get("powers") or [])
            self._pools = list(sheet.get("pools") or [])
            if self._power_id not in {row["id"] for row in self._powers}:
                self._power_id = self._powers[0]["id"] if self._powers else ""
            self._fill_pools()
            self._fill_defense(sheet)
            self._fill_powers()
            self._fill_detail()
        finally:
            self._busy = False

    def _fill_pools(self) -> None:
        self.pools.clear()
        if not self._pools:
            self.pools.set_row(0, "资源", "无（这个等级还没解锁）")
            return
        for index, pool in enumerate(self._pools[:9]):
            self.pools.set_row(
                index, pool.get("label") or pool["id"],
                "%d / %d" % (pool["left"], pool["max"]))

    def _fill_defense(self, sheet: dict) -> None:
        self.defense.clear()
        senses = sheet.get("senses") or {}
        sense_text = "、".join("%s %d 尺" % (SENSE_ZH.get(key, key), value)
                              for key, value in sorted(senses.items())) or "—"
        self.defense.set_row(0, "AC", str((sheet.get("ac") or {}).get("total", 0)))
        self.defense.set_row(1, "暴击", "≥ %d" % int((sheet.get("crit") or {}).get("min", 20)))
        self.defense.set_row(2, "感官", sense_text)
        self.defense.set_row(3, "抗性", _join(sheet.get("resistances")))
        self.defense.set_row(4, "免疫", _join(sheet.get("immunities")))
        conditions = sheet.get("conditions") or []
        self.defense.set_row(5, "状态", "、".join(conditions) if conditions else "—")

    def _fill_powers(self) -> None:
        rows = []
        for row in self._powers:
            mark = STATUS_MARK.get(row.get("status") or "text", "□")
            kind = KIND_ZH.get(row.get("kind") or "", row.get("kind") or "")
            tail = ""
            if row.get("button") and row.get("blocked"):
                tail = "　（不可用）"
            rows.append((row["id"], "%s %s　%s%s" % (mark, row["name"], kind, tail)))
        self.powers.fill(rows)
        if self._power_id:
            self.powers.select_id(self._power_id)
        if not self._powers:
            self._status("这个角色还没有能力。")

    def _selected(self) -> dict:
        for row in self._powers:
            if row["id"] == self._power_id:
                return row
        return {}

    def _select_power(self) -> None:
        picked = self.powers.selected_id()
        if not picked or picked == self._power_id:
            return
        self._power_id = picked
        self._fill_detail()

    def _fill_detail(self) -> None:
        row = self._selected()
        if not row:
            self.text.set_text("")
            self.blocked_var.set("")
            self.use_button.configure(state="disabled")
            return
        head = "%s（%s · %s）" % (row["name"], KIND_ZH.get(row.get("kind") or "", "?"),
                                 STATUS_ZH.get(row.get("status") or "text", "?"))
        path = row.get("subtitle") or ""
        body = (row.get("text") or "")
        self.text.set_text("\n".join(item for item in (head, path, "", body) if item))

        blocked = row.get("blocked") or []
        self.blocked_var.set("现在不能用：" + "；".join(blocked) if blocked else "")
        state = "normal" if row.get("button") and not blocked else "disabled"
        self.use_button.configure(state=state)
        if not row.get("button"):
            self.use_button.configure(text="被动能力（无需使用）")
        else:
            self.use_button.configure(text="使用这项能力")

    def _status(self, text: str, error: bool = False) -> None:
        self.status_var.set(text)
        self.status.configure(foreground="#a33" if error else "#666666")

    # --- 使用 -------------------------------------------------------------
    def use_selected(self) -> bool:
        """点「使用」：走 api.use_power，把返回的报告贴到右栏。"""
        if self._busy:
            return False
        row = self._selected()
        if not row or not row.get("button"):
            self._status("这是一项被动能力，不需要使用。", error=True)
            return False
        report = api.use_power(self.app.actor, self.app.bundle, row["id"],
                               locale=self.app.locale)
        if not report.get("ok"):
            self.report.set_text(str(report.get("message") or "使用失败"))
            self._status(str(report.get("message") or "使用失败"), error=True)
            self._fill_detail()
            return False
        self.report.set_text(_report_text(report))
        self._status("已使用「%s」。" % row["name"])
        self.app.refresh()          # 资源与 HP 可能变了
        self._fill_detail()          # 刷新可用性（次数用掉后按钮该灰）
        return True


def _join(values) -> str:
    return "、".join(str(item) for item in values) if values else "—"


def _report_text(report: dict) -> str:
    """使用报告：先把掷骰明细列出来（玩家最想看的），再列事件。"""
    parts = []
    for roll in report.get("rolls") or []:
        parts.append("%s：%s（%s）" % (roll.get("label", ""), roll.get("total", ""),
                                    roll.get("detail", "")))
    for event in report.get("events") or []:
        text = event.get("text") if isinstance(event, dict) else None
        if text:
            parts.append(str(text))
    if not parts:
        parts.append("这次没有产生掷骰或状态变化。")
    return "\n".join(parts)
