# -*- coding: utf-8 -*-
"""装备页：护甲 · 盾 · 武器 · 槽位。

只做「写事实」这一件事：选一件 → `api.equip_item` → `app.refresh()`。
AC、攻击表、`gear` 三处都是每次取卡现读装备槽的，所以换完立刻变，**不需要重建**。

两条要在界面上说清的事：
  * 武器精通**只记录、不结算**（`rules/attack.py` 里只存名字），所以详情里
    写的是「精通：削弱 sap」而不是假装它已经生效。
  * 力量需求与隐匿劣势是展示信息 —— 2024 的力量需求影响速度，那套还没接，
    写成「力 13」不写「不满足会……」。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import dnd5r.api as api

from . import theme
from .widgets import (COL_LEFT, COL_MID, COL_RIGHT, DAMAGE_ZH, KeyValue, ListPane,
                      section)

CATEGORY_ZH = {
    "light": "轻甲", "medium": "中甲", "heavy": "重甲", "shield": "盾牌",
    "simple": "简易", "martial": "军用",
}
# 精通的中文名只是**显示用**：效果不结算，所以不做机制说明，只给桌上一眼能认的词
MASTERY_ZH = {
    "cleave": "劈砍", "graze": "擦伤", "nick": "快手", "push": "推撞",
    "sap": "削弱", "slow": "迟缓", "topple": "击倒", "vex": "扰乱",
}
PROPERTY_ZH = {
    "light": "轻型", "finesse": "灵巧", "two_handed": "双手", "versatile": "两用",
    "thrown": "投掷", "heavy": "重型", "reach": "长武", "loading": "装填",
    "ranged": "远程",
}
SLOT_ROWS = (("armor", "护甲"), ("shield", "盾牌"),
             ("main_hand", "主手"), ("off_hand", "副手"))


def _signed(value) -> str:
    return "%+d" % int(value)


class GearPage(ttk.Frame):
    """`app` 只用 actor / bundle / locale / refresh。"""

    def __init__(self, master, app) -> None:
        super().__init__(master, padding=(6, 4))
        self.app = app
        self._armors: list[dict] = []
        self._weapons: list[dict] = []
        self._loaded = False
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
        self.left, self.mid, self.right = left, mid, right

        # --- 左：当前这一身 ------------------------------------------------
        slots = section(left, "当前装备")
        slots.pack(fill="x")
        self.slots = KeyValue(slots, rows=4)
        self.slots.pack(fill="x")

        armor = section(left, "护甲值")
        armor.pack(fill="x", pady=(8, 0))
        self.ac = KeyValue(armor, rows=1)
        self.ac.pack(fill="x")
        self.ac_note_var = tk.StringVar(value="")
        ttk.Label(armor, textvariable=self.ac_note_var, style="Dim.TLabel",
                  wraplength=220, justify="left").pack(anchor="w", pady=(2, 0))

        # --- 中：护甲表 ----------------------------------------------------
        listed = section(mid, "护甲与盾", "双击也行：选中后点下面两个按钮")
        listed.pack(fill="both", expand=True)
        self.armor_list = ListPane(listed, height=9, width=52)
        self.armor_list.pack(fill="both", expand=True)
        self.armor_list.list.bind("<<ListboxSelect>>",
                                  lambda _e: self._show_armor_detail())
        row = ttk.Frame(listed)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="装备", command=self.equip_armor).pack(side="left")
        ttk.Button(row, text="卸下", command=self.unequip_armor).pack(side="left", padx=(4, 0))
        self.armor_detail_var = tk.StringVar(value="")
        ttk.Label(listed, textvariable=self.armor_detail_var, style="Dim.TLabel",
                  wraplength=520, justify="left").pack(anchor="w", pady=(4, 0))

        # --- 右：武器表 ----------------------------------------------------
        weapons = section(right, "武器", "精通已记录，效果未结算")
        weapons.pack(fill="both", expand=True)
        self.weapon_list = ListPane(weapons, height=9, width=34)
        self.weapon_list.pack(fill="both", expand=True)
        self.weapon_list.list.bind("<<ListboxSelect>>",
                                   lambda _e: self._show_weapon_detail())
        row = ttk.Frame(weapons)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="主手", style="Mini.TButton", width=5,
                   command=lambda: self.equip_weapon("main_hand")).pack(side="left")
        ttk.Button(row, text="副手", style="Mini.TButton", width=5,
                   command=lambda: self.equip_weapon("off_hand")).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="卸下", style="Mini.TButton", width=5,
                   command=self.unequip_weapon).pack(side="left", padx=(4, 0))
        self.weapon_detail_var = tk.StringVar(value="")
        ttk.Label(weapons, textvariable=self.weapon_detail_var, style="Dim.TLabel",
                  wraplength=290, justify="left").pack(anchor="w", pady=(4, 0))

        self.status_var = tk.StringVar(value="")
        self.status = ttk.Label(self, textvariable=self.status_var, anchor="w")
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

    # --- 数据 -------------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        if not self._loaded:
            self._armors = api.armor_catalog(self.app.bundle, self.app.locale)["armors"]
            self._weapons = api.weapon_catalog(self.app.bundle, self.app.locale)["weapons"]
            self._loaded = True
        self._equipped = dict(sheet.get("equipped") or {})
        self._fill_lists(self._equipped)
        self._fill_slots(sheet)
        self._show_armor_detail()
        self._show_weapon_detail()

    def _fill_lists(self, equipped: dict) -> None:
        """重画两份清单并给已装备的打 ●。

        选中项**按 id 恢复**（`ListPane.fill` 自己会做）：每次都跳回第一行的话，
        玩家装完一件就找不到自己刚才点的是哪件了。
        """
        self.armor_list.fill([(row["id"], self._armor_text(row, equipped))
                              for row in self._armors])
        self.weapon_list.fill([(row["id"], self._weapon_text(row, equipped))
                               for row in self._weapons])
        if not self.armor_list.selected_id() and self._armors:
            self.armor_list.select_id(self._armors[0]["id"])
        if not self.weapon_list.selected_id() and self._weapons:
            self.weapon_list.select_id(self._weapons[0]["id"])

    def _armor_text(self, row: dict, equipped: dict) -> str:
        """清单一行。**不用 %-6s 对齐**：中文字符是双宽，按字符数补空格只会错位，
        看上去像表格、读起来是锯齿。改用全角分隔，宽度差一点但整齐可读。"""
        mark = "●" if equipped.get(row["slot"]) == row["id"] else "　"
        value = ("AC %d" % row["ac_base"]) if row["category"] != "shield" else "+%d" % row["bonus"]
        return "%s%s（%s）%s" % (mark, row["name"],
                                 CATEGORY_ZH.get(row["category"], ""), value)

    def _weapon_text(self, row: dict, equipped: dict) -> str:
        on = row["id"] in (equipped.get("main_hand"), equipped.get("off_hand"))
        mark = "●" if on else "　"
        damage = row["damage"] + ("/" + row["versatile"] if row["versatile"] else "")
        return "%s%s（%s）%s" % (mark, row["name"],
                                 CATEGORY_ZH.get(row["category"], ""), damage)

    def _fill_slots(self, sheet: dict) -> None:
        gear = sheet.get("gear") or {}
        equipped = sheet.get("equipped") or {}
        self.slots.clear()
        for index, (slot, label) in enumerate(SLOT_ROWS):
            ident = equipped.get(slot) or ""
            self.slots.set_row(index, label, self._name_of(ident) or "—")
        self.ac.set_row(0, "AC", str((sheet.get("ac") or {}).get("total", 0)))
        self.ac_note_var.set(str((sheet.get("ac") or {}).get("detail") or ""))
        if not gear.get("armor") and not gear.get("shield"):
            self.ac_note_var.set(self.ac_note_var.get() + "\n（无甲：10 + 敏捷）")

    def _name_of(self, item_id: str) -> str:
        for row in self._armors + self._weapons:
            if row["id"] == item_id:
                return row["name"]
        return ""

    # --- 详情 -------------------------------------------------------------
    def select_armor(self, item_id: str) -> None:
        """选中并立刻更新详情。`Listbox.select_set` 不触发 `<<ListboxSelect>>`，
        只给测试与审计用的程序化选择会留下「选的是甲、详情写着盾」的错位。"""
        self.armor_list.select_id(item_id)
        self._show_armor_detail()

    def select_weapon(self, item_id: str) -> None:
        self.weapon_list.select_id(item_id)
        self._show_weapon_detail()

    def _armor_by_id(self, item_id: str) -> dict:
        return next((row for row in self._armors if row["id"] == item_id), {})

    def _weapon_by_id(self, item_id: str) -> dict:
        return next((row for row in self._weapons if row["id"] == item_id), {})

    def _show_armor_detail(self) -> None:
        row = self._armor_by_id(self.armor_list.selected_id())
        if not row:
            self.armor_detail_var.set("")
            return
        bits = ["%s · %s" % (row["name"], CATEGORY_ZH.get(row["category"], row["category"]))]
        if row["category"] != "shield":
            cap = "无上限" if row["dex_cap"] is None else str(row["dex_cap"])
            bits.append("AC %d（敏捷上限 %s）" % (row["ac_base"], cap))
        else:
            bits.append("AC +%d" % row["bonus"])
        if row["str_req"]:
            bits.append("力量需求 %d" % row["str_req"])
        bits.append("隐匿劣势" if row["stealth"] else "无隐匿劣势")
        self.armor_detail_var.set(" · ".join(bits))

    def _show_weapon_detail(self) -> None:
        row = self._weapon_by_id(self.weapon_list.selected_id())
        if not row:
            self.weapon_detail_var.set("")
            return
        bits = ["%s · %s" % (row["name"], CATEGORY_ZH.get(row["category"], row["category"])),
                row["damage"] + ("（双手 %s）" % row["versatile"] if row["versatile"] else ""),
                DAMAGE_ZH.get(row["damage_type"], row["damage_type"])]
        props = [PROPERTY_ZH.get(item, item) for item in row["properties"]]
        if props:
            bits.append("、".join(props))
        if row["mastery"]:
            bits.append("精通：%s %s" % (MASTERY_ZH.get(row["mastery"], row["mastery"]),
                                        row["mastery"]))
        self.weapon_detail_var.set(" · ".join(bits))

    # --- 操作 -------------------------------------------------------------
    def _status(self, text: str, error: bool = False) -> None:
        self.status_var.set(text)
        self.status.configure(foreground=theme.WARN if error else theme.DIM)

    def _equip(self, slot: str, item_id: str) -> bool:
        try:
            result = api.equip_item(self.app.actor, self.app.bundle, slot, item_id)
        except api.DndError as exc:
            self._status(str(exc), error=True)
            return False
        self._status(result["message"])
        self.app.refresh()
        return True

    def equip_armor(self) -> bool:
        row = self._armor_by_id(self.armor_list.selected_id())
        if not row:
            self._status("先在列表里选一件护甲或盾", error=True)
            return False
        return self._equip(row["slot"], row["id"])

    def unequip_armor(self) -> bool:
        """卸下选中的那一类：选中盾就卸盾槽，选中甲就卸甲槽。
        没选中时按护甲算（玩家点「卸下」多半是想脱甲）。"""
        row = self._armor_by_id(self.armor_list.selected_id())
        target = row["slot"] if row else "armor"
        if not self._equipped.get(target):
            self._status("%s本来就空着" % ("盾牌" if target == "shield" else "护甲"))
            return False
        return self._equip(target, "")

    def equip_weapon(self, slot: str) -> bool:
        row = self._weapon_by_id(self.weapon_list.selected_id())
        if not row:
            self._status("先在列表里选一件武器", error=True)
            return False
        return self._equip(slot, row["id"])

    def unequip_weapon(self) -> bool:
        equipped = self._equipped or {}
        # 两只手都卸：玩家点「卸下」时想要的是「手上别拿东西」，
        # 而不是猜他要点哪边
        changed = False
        for slot in ("main_hand", "off_hand"):
            if equipped.get(slot):
                changed = self._equip(slot, "") or changed
        if not changed:
            self._status("手上本来就没武器")
        return changed
