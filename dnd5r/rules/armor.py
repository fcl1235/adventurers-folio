# -*- coding: utf-8 -*-
"""护甲与盾：AC 的基础公式来自**装备**，不是常量。

2024 的 AC 只有三类来源：
  1. 护甲 —— 写死的基础值 + 敏捷（轻甲无上限、中甲上限 2、重甲不吃敏捷）
  2. 盾牌 —— 固定加值
  3. 无甲 —— `10 + 敏捷`，职业公式（无甲防御）在它之上加调整值

这里只做「装备 → 基础值与 Modifier」，不判断任何职业。无甲防御是职业给的
Modifier，它是否生效由 `facts.unarmored` / `facts.shield` 决定（见 contributions）。

**变形期间装备一律不生效**：2024 荒野变形把「游戏数据」整套换成形态的，
所以形态的 AC 既不含护甲也不含盾牌。这条不在 UI 里做，在 `loadout_for` 里做，
否则每个调用点都要记得判一次。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from ..kernel.text import Text
from ..model.actor import Actor
from ..model.inventory import EquipSlot
from ..model.statblock import ABILITY_NAMES, Statblock
from .modifiers import Modifier, Stack

ARMOR_SLOTS = (EquipSlot.ARMOR, EquipSlot.SHIELD)


class ArmorLike(Protocol):
    """`content.ArmorDef` 的结构。用 Protocol 而不是 import，避免规则层依赖 YAML。

    只读四个数，不会去碰 id / 价格 / 重量 —— 那些属于内容。
    """

    id: str
    name: Text
    category: str
    ac_base: int
    dex_cap: int | None
    bonus: int


@dataclass(frozen=True, slots=True)
class Loadout:
    """角色这一身：一件护甲 + 一个盾牌（法术护甲之类走 Modifier，不占槽）。"""

    armor: ArmorLike | None = None
    shield: ArmorLike | None = None

    @property
    def unarmored(self) -> bool:
        return self.armor is None

    @property
    def shielded(self) -> bool:
        return self.shield is not None

    @property
    def empty(self) -> bool:
        return self.armor is None and self.shield is None

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "armor": _row(self.armor, locale),
            "shield": _row(self.shield, locale),
        }


def _row(item: ArmorLike | None, locale: str) -> dict | None:
    if item is None:
        return None
    return {
        "id": item.id,
        "name": item.name.get(locale),
        "category": item.category,
        "ac_base": item.ac_base,
        "dex_cap": item.dex_cap,
        "bonus": item.bonus,
    }


def loadout_for(actor: Actor, armors: Mapping[str, ArmorLike]) -> Loadout:
    """从背包的装备槽读出护甲与盾。变形期间返回空 Loadout。

    `armors` 是内容里的护甲表；查不到 id 就当没穿（物品可能来自别的插件，
    不该让一个缺失的外观条目把 AC 算崩）。
    """
    if actor.top().layer is not None:
        return Loadout()
    equipment = actor.root().inventory.equipped
    armor = armors.get(equipment.get(EquipSlot.ARMOR, ""))
    shield = armors.get(equipment.get(EquipSlot.SHIELD, ""))
    return Loadout(armor=armor, shield=shield)


def dex_contribution(armor: ArmorLike | None, dex_mod: int) -> int:
    """护甲能吃多少敏捷。重甲 `dex_cap = 0` 表示一点都不吃（负值照扣）。"""
    if armor is None:
        return int(dex_mod)
    if armor.dex_cap is None:
        return int(dex_mod)
    return min(int(dex_mod), int(armor.dex_cap))


def ac_inputs(
    loadout: Loadout,
    statblock: Statblock,
    locale: str = "zh",
) -> tuple[int, tuple[Modifier, ...]]:
    """返回 `(基础值, 装备给的 Modifier)`，交给 `Resolver.armor_class()`。

    无甲：基础值 = statblock 的 AC（形态自带的 AC 就是这么进来的，已经减过敏捷）
    有甲：基础值归零，护甲用 SET 顶掉「10 + 敏捷」，敏捷再按上限加回，
          这样明细能读成「15 = 14 环甲 + 1 敏捷 + 2 盾牌」而不是「基础 15」。
    """
    dex_mod = statblock.abilities.mod("dex")
    armor = loadout.armor
    extra: list[Modifier] = []

    if armor is None:
        base = statblock.ac_base + dex_mod
    else:
        base = 0
        extra.append(Modifier(
            target="ac", value=int(armor.ac_base), stack=Stack.SET,
            source=armor.name.get(locale),
        ))
        used = dex_contribution(armor, dex_mod)
        if used:
            extra.append(Modifier(
                target="ac", value=used, stack=Stack.ADD,
                source=ABILITY_NAMES["dex"].get(locale),
            ))

    if loadout.shield is not None and int(loadout.shield.bonus):
        extra.append(Modifier(
            target="ac", value=int(loadout.shield.bonus), stack=Stack.ADD,
            source=loadout.shield.name.get(locale),
        ))
    return base, tuple(extra)


__all__ = [
    "ARMOR_SLOTS", "ArmorLike", "Loadout", "loadout_for",
    "dex_contribution", "ac_inputs",
]
