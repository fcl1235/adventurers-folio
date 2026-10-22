# -*- coding: utf-8 -*-
"""角色卡的四个页面。每个页面只做一件事：把 sheet 里的一段画出来。

页面不持有规则，也不缓存派生值 —— `refresh(sheet)` 每次都整块重画。
缓存派生值是旧程序最容易出漂的地方（改了一件装备，三个地方还在用旧 AC）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .widgets import COL_LEFT, COL_MID, COL_RIGHT, GridTable, KeyValue, section

ABILITY_ORDER = ("str", "dex", "con", "int", "wis", "cha")
# 列宽是**字符数**（ttk.Label 的单位）。像素预算由布局审计现量 reqwidth 得出，
# 不在这里手算 —— 字体一变手算的值就废了。
SKILL_COLUMNS = [("技能", 10), ("属性", 5), ("加值", 5), ("熟练", 5), ("明细", 24)]
ATTACK_COLUMNS = [("武器", 12), ("命中", 5), ("伤害", 11)]
ABILITY_ZH = {"str": "力量", "dex": "敏捷", "con": "体质",
              "int": "智力", "wis": "感知", "cha": "魅力"}


def _signed(value: int) -> str:
    return "%+d" % int(value)


def _mode_mark(row: dict) -> str:
    """优势/劣势的短标记。页面只负责显示，判断来自 sheet 的 `mode`。"""
    mode = row.get("mode")
    if mode == "adv":
        return "（优势）"
    if mode == "dis":
        return "（劣势）"
    return ""


class OverviewPage(ttk.Frame):
    """概览：六属性 / 豁免 / 18 技能 / 战斗数值。"""

    def __init__(self, master) -> None:
        super().__init__(master, padding=(6, 4))
        self._build()

    def _build(self) -> None:
        left = ttk.Frame(self, width=COL_LEFT)
        mid = ttk.Frame(self, width=COL_MID)
        right = ttk.Frame(self, width=COL_RIGHT)
        left.grid(row=0, column=0, sticky="nsw")
        mid.grid(row=0, column=1, sticky="nsew", padx=8)
        right.grid(row=0, column=2, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # --- 左：属性 + 豁免 -------------------------------------------------
        self.abilities = KeyValue(left, rows=6)
        self.abilities.pack(fill="x", pady=(0, 8))
        saves = section(left, "豁免")
        saves.pack(fill="x")
        self.saves = KeyValue(saves, rows=6)
        self.saves.pack(fill="x")

        # --- 中：技能 -------------------------------------------------------
        skills = section(mid, "技能", "熟练加熟练加值，专精再加一份；明细在右侧说明栏")
        skills.pack(fill="both", expand=True)
        self.skills = GridTable(skills, SKILL_COLUMNS, rows=18)
        self.skills.pack(fill="both", expand=True)

        # --- 右：战斗数值 ---------------------------------------------------
        fight = section(right, "战斗")
        fight.pack(fill="x")
        # 抗性/感官以前全仓库零显示点（§P6 方案里点名过的缺口），一并补在这里
        self.fight = KeyValue(fight, rows=8)
        self.fight.pack(fill="x", pady=(0, 6))

        attacks = section(right, "攻击")
        attacks.pack(fill="both", expand=True, pady=(6, 0))
        self.attacks = GridTable(attacks, ATTACK_COLUMNS, rows=8)
        self.attacks.pack(fill="both", expand=True)

    # --- 数据 -------------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        abilities = sheet.get("abilities") or {}
        for index, key in enumerate(ABILITY_ORDER):
            row = abilities.get(key) or {}
            self.abilities.set_row(
                index, ABILITY_ZH[key],
                "%d (%s)" % (row.get("score", 0), _signed(row.get("mod", 0))))

        saves = sheet.get("saves") or {}
        for index, key in enumerate(ABILITY_ORDER):
            row = saves.get(key) or {}
            mark = "*" if row.get("proficient") else ""
            self.saves.set_row(index, "%s%s" % (ABILITY_ZH[key], mark),
                               _signed(row.get("total", 0)))

        self.refresh_skills(sheet)
        self.refresh_fight(sheet)
        self.refresh_attacks(sheet)

    def refresh_skills(self, sheet: dict) -> None:
        rows = []
        for row in sheet.get("skills") or []:
            mark = "专精" if row.get("expertise") else ("熟练" if row.get("proficient") else "")
            tag = "expert" if row.get("expertise") else ("prof" if row.get("proficient") else "")
            rows.append(((row["name"], row["ability"].upper(),
                          _signed(row["total"]), mark, row["detail"]), tag))
        self.skills.fill(rows)

    def refresh_fight(self, sheet: dict) -> None:
        hp = sheet.get("hp") or {}
        speed = (sheet.get("speed") or {}).get("walk", 0)
        init = sheet.get("initiative") or {}
        self.fight.clear()
        self.fight.set_row(0, "AC", str((sheet.get("ac") or {}).get("total", 0)))
        self.fight.set_row(1, "先攻", _signed(init.get("total", 0)) + _mode_mark(init))
        self.fight.set_row(2, "HP", "%s/%s" % (hp.get("current", 0), hp.get("maximum", 0)))
        self.fight.set_row(3, "速度", "%d 尺" % speed)
        self.fight.set_row(4, "熟练", _signed(sheet.get("proficiency_bonus", 0)))
        resist = sheet.get("resistances") or []
        self.fight.set_row(5, "抗性", "、".join(resist) if resist else "—")
        senses = sheet.get("senses") or {}
        self.fight.set_row(6, "感官", "、".join("%s %d" % (key, value)
                                               for key, value in sorted(senses.items()))
                           or "—")
        self.fight.set_row(7, "暴击", "≥ %d" % int((sheet.get("crit") or {}).get("min", 20)))

    def refresh_attacks(self, sheet: dict) -> None:
        rows = []
        for row in (sheet.get("attacks") or [])[:8]:
            bonus = int(row.get("damage_bonus") or 0)
            damage = "%s%s %s" % (row.get("damage", ""),
                                  _signed(bonus) if bonus else "",
                                  row.get("damage_type", ""))
            rows.append(((row.get("name", ""), _signed(row.get("attack", 0)), damage), ""))
        self.attacks.fill(rows)
