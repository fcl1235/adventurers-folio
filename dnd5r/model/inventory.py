# -*- coding: utf-8 -*-
"""背包与装备槽。

同调是背包的 3 个槽，不是物品属性 —— 所以它挂在 Inventory 上，不挂在 ItemRef 上。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..kernel.errors import RuleError

ATTUNEMENT_SLOTS = 3


class EquipSlot(str, Enum):
    MAIN_HAND = "main_hand"
    OFF_HAND = "off_hand"
    ARMOR = "armor"
    SHIELD = "shield"
    HEAD = "head"
    CLOAK = "cloak"
    HANDS = "hands"
    FEET = "feet"
    RING = "ring"
    AMULET = "amulet"


@dataclass
class ItemRef:
    item_id: str
    quantity: int = 1
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.item_id:
            raise RuleError("物品 id 不能为空")
        if self.quantity < 0:
            raise RuleError("物品数量不能为负")

    def to_dict(self) -> dict:
        return {"id": self.item_id, "quantity": self.quantity, "notes": self.notes}


@dataclass
class Inventory:
    items: list[ItemRef] = field(default_factory=list)
    equipped: dict[EquipSlot, str] = field(default_factory=dict)
    attuned: list[str] = field(default_factory=list)
    # 钱只记金币（2024 的起始装备与大多数价格表都以 gp 计）。银/铜币的换算
    # 在展示层做，档案里只留一个整数 —— 多币种并存早晚出现「买了东西找零」
    # 这种要记账本才做得对的事，本轮不做。
    coins_gp: int = 0

    # --- 物品 ---------------------------------------------------------
    def add(self, item_id: str, quantity: int = 1) -> None:
        """放进背包。同 id 合并成一条 —— 两份「箭矢 ×20」在界面上没法区分，
        存盘来回一次也会变成两条各 20 的条目。"""
        if quantity < 1:
            raise RuleError("放入背包的件数必须 ≥ 1")
        for ref in self.items:
            if ref.item_id == item_id:
                ref.quantity += quantity
                return
        self.items.append(ItemRef(item_id=item_id, quantity=quantity))

    def count_of(self, item_id: str) -> int:
        return sum(ref.quantity for ref in self.items if ref.item_id == item_id)

    # --- 装备 ---------------------------------------------------------
    def equip(self, slot: EquipSlot, item_id: str) -> None:
        self.equipped[slot] = item_id

    def unequip(self, slot: EquipSlot) -> None:
        self.equipped.pop(slot, None)

    def equipped_at(self, slot: EquipSlot) -> str | None:
        return self.equipped.get(slot)

    def has_item(self, item_id: str) -> bool:
        return any(ref.item_id == item_id and ref.quantity > 0 for ref in self.items)

    # --- 同调 ---------------------------------------------------------
    def can_attune(self, item_id: str) -> bool:
        return item_id in self.attuned or len(self.attuned) < ATTUNEMENT_SLOTS

    def attune(self, item_id: str) -> None:
        if item_id in self.attuned:
            return
        if len(self.attuned) >= ATTUNEMENT_SLOTS:
            raise RuleError("同调槽已满（上限 %d）" % ATTUNEMENT_SLOTS)
        self.attuned.append(item_id)

    def unattune(self, item_id: str) -> None:
        if item_id in self.attuned:
            self.attuned.remove(item_id)

    def to_dict(self) -> dict:
        return {
            "items": [ref.to_dict() for ref in self.items],
            "equipped": {slot.value: item for slot, item in self.equipped.items()},
            "attuned": list(self.attuned),
            "coins_gp": int(self.coins_gp),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        inv = cls()
        for row in data.get("items", ()):
            inv.items.append(ItemRef(str(row["id"]), int(row.get("quantity", 1)), str(row.get("notes", ""))))
        for slot, item in (data.get("equipped") or {}).items():
            inv.equipped[EquipSlot(slot)] = str(item)
        inv.attuned = [str(x) for x in data.get("attuned", ())]
        # 旧存档没有这个字段：缺了就是 0，不许因此读不出档
        inv.coins_gp = int(data.get("coins_gp", 0) or 0)
        return inv
