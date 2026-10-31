# -*- coding: utf-8 -*-
"""起始装备落地：一组包 → 背包里的物品 + 默认穿在身上的那几件。

三件事，按这个顺序做：

1. **全部进包**（同 id 合并），金币记进 `Inventory.coins_gp`。
2. **能穿的自动穿上**：AC 最高的那件甲、盾、主手第一把武器。不自动穿的话
   建出来的角色 AC 还是 10、攻击表只有徒手打击 —— 人物卡第一眼看过去就是错的。
3. **穿不上的留在包里**，返回里说明哪几件没上身（多出来的武器、没甲可穿时的
   法器等等）。界面不用猜，直接照着显示。

为什么不复用 `api.loadout.equip_item`：那是**界面动作**（带交互语义的返回值与
错误文案），而且它会把「不在背包里的物品」补一条进去。建卡时装备本来就在包里，
两套逻辑混用会让「装了什么」有两个说法。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..content import ContentBundle
from ..content.packages import StartingPack
from ..kernel.errors import PluginError, RuleError
from ..model.inventory import EquipSlot, Inventory

# 自动装备时「先看哪一类」的顺序，与返回里的展示顺序一致
SLOT_ORDER = (EquipSlot.ARMOR, EquipSlot.SHIELD,
              EquipSlot.MAIN_HAND, EquipSlot.OFF_HAND)

SLOT_ZH = {
    EquipSlot.ARMOR: "护甲",
    EquipSlot.SHIELD: "盾牌",
    EquipSlot.MAIN_HAND: "主手",
    EquipSlot.OFF_HAND: "副手",
}


@dataclass(frozen=True)
class StartingResult:
    """一次落地的结果。`equipped` 是槽 → 物品 id，`stowed` 是没上身的物品 id。"""

    pack_id: str
    gold: int
    equipped: dict[EquipSlot, str]
    stowed: tuple[str, ...]

    def to_dict(self, bundle: ContentBundle, locale: str = "zh") -> dict:
        def name(item_id: str) -> str:
            for table in (bundle.armors, bundle.weapons, bundle.gears):
                found = table.get(item_id)
                if found is not None:
                    return found.name.get(locale)
            return item_id

        return {
            "pack": self.pack_id,
            "gold": self.gold,
            "equipped": [{"slot": slot.value, "slot_zh": SLOT_ZH[slot],
                          "id": item_id, "name": name(item_id)}
                         for slot, item_id in self.equipped.items()],
            "stowed": [{"id": item_id, "name": name(item_id)} for item_id in self.stowed],
        }


def _two_handed(weapon) -> bool:
    return "two_handed" in tuple(getattr(weapon, "properties", ()))


def _pick_armor(bundle: ContentBundle, item_ids) -> str | None:
    """AC 最高的那件甲（盾不算甲，盾走自己的槽）。"""
    best: tuple[int, str] | None = None
    for item_id in item_ids:
        armor = bundle.armors.get(item_id)
        if armor is None or armor.category == "shield":
            continue
        if best is None or armor.ac_base > best[0]:
            best = (armor.ac_base, armor.id)
    return best[1] if best else None


def _pick_shield(bundle: ContentBundle, item_ids) -> str | None:
    for item_id in item_ids:
        armor = bundle.armors.get(item_id)
        if armor is not None and armor.category == "shield":
            return armor.id
    return None


def _pick_weapons(bundle: ContentBundle, item_ids) -> list[str]:
    """按包里的书写顺序取武器，同 id 只取一次。

    顺序有意义：内容里把主武器写在前面，所以「第一件」就是主手。
    """
    picked: list[str] = []
    for item_id in item_ids:
        if item_id in picked:
            continue
        if bundle.weapons.get(item_id) is not None:
            picked.append(item_id)
    return picked


def resolve_pack(bundle: ContentBundle, class_id: str,
                 pack_id: str | None) -> StartingPack | None:
    """按 id 取包；`None`/空串表示「这职业的默认那一组」（A 包）。

    找不到就报错，**不退回默认** —— 存盘里写了一个不存在的包 id，静默换成 A 包
    会让玩家发现自己换了装备却不知道为什么。
    """
    packs = bundle.starting_packs(class_id)
    if not packs:
        return None
    if not pack_id:
        return packs[0]
    for pack in packs:
        if pack.id == pack_id:
            if pack.class_id != class_id:
                raise RuleError("%s 不是 %s 的起始装备" % (pack_id, class_id))
            return pack
    raise RuleError("没有这组起始装备：%s（%s 有 %s）"
                    % (pack_id, class_id, "、".join(pack.id for pack in packs)))


def apply_starting_pack(bundle: ContentBundle, inventory: Inventory,
                        pack: StartingPack) -> StartingResult:
    """把一组起始装备放进 `inventory`（就地修改），返回穿上了什么。"""
    known = set(bundle.weapons) | set(bundle.armors) | set(bundle.gears)
    for item_id, count in pack.items:
        if item_id not in known:
            raise PluginError("%s 里的 %s 不是已知物品" % (pack.id, item_id))
        inventory.add(item_id, count)
    inventory.coins_gp += int(pack.gold)

    ids = pack.item_ids()
    armor_id = _pick_armor(bundle, ids)
    shield_id = _pick_shield(bundle, ids)
    weapons = _pick_weapons(bundle, ids)

    equipped: dict[EquipSlot, str] = {}
    if armor_id:
        inventory.equip(EquipSlot.ARMOR, armor_id)
        equipped[EquipSlot.ARMOR] = armor_id

    main_id = weapons[0] if weapons else None
    off_id = None
    if main_id:
        inventory.equip(EquipSlot.MAIN_HAND, main_id)
        equipped[EquipSlot.MAIN_HAND] = main_id
        if not _two_handed(bundle.weapons[main_id]):
            for candidate in weapons[1:]:
                weapon = bundle.weapons[candidate]
                # 双手武器不能进副手；两用武器（versatile）可以单手用，能进
                if _two_handed(weapon):
                    continue
                off_id = candidate
                break
            if off_id:
                inventory.equip(EquipSlot.OFF_HAND, off_id)
                equipped[EquipSlot.OFF_HAND] = off_id

    # 盾在双手武器之后判定：主手是双手武器时拿不了盾（这条与 loadout 同一口径）
    if shield_id and not (main_id and _two_handed(bundle.weapons[main_id])):
        inventory.equip(EquipSlot.SHIELD, shield_id)
        equipped[EquipSlot.SHIELD] = shield_id

    used = set(equipped.values())
    stowed = tuple(item_id for item_id in ids if item_id not in used)
    ordered = {slot: equipped[slot] for slot in SLOT_ORDER if slot in equipped}
    return StartingResult(pack_id=pack.id, gold=int(pack.gold),
                          equipped=ordered, stowed=stowed)


def starting_options(bundle: ContentBundle, class_id: str,
                     locale: str = "zh") -> dict:
    """界面用：某职业可选的起始装备（含每件物品的名字，免得界面自己查表）。"""
    packs = bundle.starting_packs(class_id)
    rows = []
    for pack in packs:
        items = []
        for item_id, count in pack.items:
            name = item_id
            for table in (bundle.armors, bundle.weapons, bundle.gears):
                found = table.get(item_id)
                if found is not None:
                    name = found.name.get(locale)
                    break
            items.append({"id": item_id, "name": name, "count": count})
        rows.append({"id": pack.id, "label": pack.label.get(locale),
                     "gold": int(pack.gold), "items": items})
    return {"class_id": class_id, "count": len(rows), "options": rows}
