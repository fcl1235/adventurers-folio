# -*- coding: utf-8 -*-
"""换装与属性编辑（P5）。

两件事的共同点是「改事实然后重算」：

  * 换装**不需要 rebuild** —— AC、攻击表都是每次取卡时从 `inventory.equipped`
    现读的（`rules/armor.loadout_for` / `rules/weapons.equipped_weapons`），
    改完 `refresh()` 就立刻生效。
  * 改属性**必须 rebuild** —— 属性会牵动 HP 上限、熟练、攻击、豁免一整套派生值。
    而且只能改 `Profile.base_scores`（建角色时的原始值）：界面看到的是加过专长
    与子职加值的**结果**，从来回倒推减不掉那些加值。
"""

from __future__ import annotations

from typing import Any, Mapping

from ..content import ContentBundle
from ..kernel.errors import RuleError
from ..model.actor import Actor
from ..model.inventory import EquipSlot, ItemRef
from ..model.statblock import ABILITY_KEYS
from ..rules.build import rebuild_actor
from ..rules.morph import FORM_PREFIX, leave_form

# 只支持这四个槽：护甲、盾、主手、副手。头/披风/戒指要等物品内容补齐（items/ 现在只有
# armors.yaml 与 weapons.yaml），先不摆出四个点不动的下拉框。
SUPPORTED_SLOTS = (EquipSlot.ARMOR, EquipSlot.SHIELD,
                   EquipSlot.MAIN_HAND, EquipSlot.OFF_HAND)

SLOT_ZH = {
    EquipSlot.ARMOR: "护甲",
    EquipSlot.SHIELD: "盾牌",
    EquipSlot.MAIN_HAND: "主手",
    EquipSlot.OFF_HAND: "副手",
}

HAND_SLOTS = (EquipSlot.MAIN_HAND, EquipSlot.OFF_HAND)


def _two_handed(weapon) -> bool:
    return "two_handed" in tuple(getattr(weapon, "properties", ()))


def _busy_hands(gear, bundle: ContentBundle) -> list[str]:
    """腾不出手的原因（「副手」/「盾牌」）。双手武器与盾互斥 —— 盾在 SHIELD 槽，
    不在 OFF_HAND 槽，只看副手是不是空会漏掉拿盾的人。"""
    busy = []
    if gear.equipped_at(EquipSlot.OFF_HAND):
        busy.append(SLOT_ZH[EquipSlot.OFF_HAND])
    if gear.equipped_at(EquipSlot.SHIELD):
        busy.append(SLOT_ZH[EquipSlot.SHIELD])
    return busy


def parse_slot(slot) -> EquipSlot:
    """字符串/枚举都能进。不认识就报错，**不猜**（猜错的后果是装备凭空消失）。"""
    if isinstance(slot, EquipSlot):
        found = slot
    else:
        try:
            found = EquipSlot(str(slot))
        except ValueError:
            raise RuleError("不认识的装备槽：%r" % (slot,))
    if found not in SUPPORTED_SLOTS:
        raise RuleError("%s 还不支持换装（当前只有护甲/盾/主手/副手）" % SLOT_ZH.get(found, found))
    return found


# 目录里的排序：轻→中→重→盾。**不要按 AC 倒序** —— 那样盾牌会排在最前
# （盾的 ac_base 是 0），变成「第一行是盾、第二行是最重的甲」。
CATEGORY_ORDER = {"light": 0, "medium": 1, "heavy": 2, "shield": 3}


def armor_catalog(bundle: ContentBundle, locale: str = "zh") -> dict:
    """护甲与盾的清单（13 件）。界面据 `slot` 分组，不用自己判断哪件是盾。"""
    rows = sorted(bundle.armors.values(),
                  key=lambda item: (CATEGORY_ORDER.get(item.category, 9),
                                    -item.ac_base, item.id))
    return {
        "count": len(rows),
        "armors": [
            {"id": item.id, "name": item.name.get(locale), "category": item.category,
             "ac_base": item.ac_base, "dex_cap": item.dex_cap, "bonus": item.bonus,
             "str_req": item.str_req, "stealth": item.stealth,
             "slot": item.slot.value}
            for item in rows
        ],
    }


def weapon_catalog(bundle: ContentBundle, locale: str = "zh") -> dict:
    """武器清单（38 件）。`mastery` 只记名字，**效果不结算**（见 rules/attack.py）。"""
    rows = sorted(bundle.weapons.values(), key=lambda item: (item.category, item.id))
    return {
        "count": len(rows),
        "weapons": [
            {"id": item.id, "name": item.name.get(locale), "category": item.category,
             "damage": item.damage, "damage_type": item.damage_type,
             "versatile": item.versatile,
             "properties": list(item.properties), "mastery": item.mastery}
            for item in rows
        ],
    }


def equip_item(actor: Actor, bundle: ContentBundle, slot, item_id: str | None = None,
               locale: str = "zh") -> dict:
    """装上一件、或卸下（`item_id` 为空）。返回 `{slot, item_id, changed, message}`。

    三条会当场拒绝的情况，都是「装上去也算不出对的数」的：
      1. 护甲/盾装错槽（把盾塞进护甲槽会得到两件盾都生效）
      2. 双手武器配盾或配副手武器（规则上拿不动）
      3. 同一件物品占两只手（两把相同的剑不是「双手握持」，那是 1d10 两用武器的写法）
    """
    found = parse_slot(slot)
    gear = actor.root().inventory
    current = gear.equipped_at(found)

    if item_id in (None, ""):
        gear.unequip(found)
        return {"slot": found.value, "item_id": None, "changed": current is not None,
                "message": ("已卸下%s" % SLOT_ZH[found]) if current else "本来就是空的"}

    ident = str(item_id)
    armor = bundle.armors.get(ident)
    weapon = bundle.weapons.get(ident)

    if found in (EquipSlot.ARMOR, EquipSlot.SHIELD):
        if armor is None:
            raise RuleError("%s 不是护甲或盾（%s槽只收这两类）" % (ident, SLOT_ZH[found]))
        if armor.slot is not found:
            raise RuleError("%s 是%s，要装进%s槽"
                            % (armor.name.get(locale), SLOT_ZH[armor.slot],
                               SLOT_ZH[armor.slot]))
        # 反向也要拦：主手拎着双手武器时挂不上盾
        if found is EquipSlot.SHIELD:
            main = bundle.weapons.get(gear.equipped_at(EquipSlot.MAIN_HAND) or "")
            if main is not None and _two_handed(main):
                raise RuleError("主手是双手武器 %s，用不了盾" % main.name.get(locale))
    else:
        if weapon is None:
            raise RuleError("%s 不是武器（%s槽只收武器）" % (ident, SLOT_ZH[found]))
        other = (EquipSlot.OFF_HAND if found is EquipSlot.MAIN_HAND
                 else EquipSlot.MAIN_HAND)
        if _two_handed(weapon):
            busy = _busy_hands(gear, bundle)
            if busy:
                raise RuleError("%s 是双手武器，先卸下%s"
                                % (weapon.name.get(locale), "、".join(busy)))
        if found is EquipSlot.OFF_HAND:
            main = bundle.weapons.get(gear.equipped_at(EquipSlot.MAIN_HAND) or "")
            if main is not None and _two_handed(main):
                raise RuleError("主手是双手武器 %s，用不了副手武器"
                                % main.name.get(locale))

    if current == ident:
        return {"slot": found.value, "item_id": ident, "changed": False,
                "message": "本来就装着"}

    # 同一件物品不能同时占两只手：换到另一只手时把旧的清掉
    if found in HAND_SLOTS:
        other = (EquipSlot.OFF_HAND if found is EquipSlot.MAIN_HAND
                 else EquipSlot.MAIN_HAND)
        if gear.equipped_at(other) == ident:
            gear.unequip(other)

    gear.equip(found, ident)
    if not gear.has_item(ident):
        # 装上却没在背包里 = 一件「影子装备」，存盘之后就没了。补一条。
        gear.items.append(ItemRef(item_id=ident))
    name = (armor or weapon).name.get(locale)
    return {"slot": found.value, "item_id": ident, "changed": True,
            "message": "%s → %s" % (SLOT_ZH[found], name)}


def set_base_scores(actor: Actor, bundle: ContentBundle,
                    scores: Mapping[str, int]) -> Actor:
    """改原始属性并重建，返回**新的** actor（调用方负责换掉手里的那只）。

    只收六项齐全的映射：缺项就报错。少传一个 key 时静默保留旧值，会让
    「界面按新值算、存档里是旧值」这种错一直藏着。
    """
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案，无法改属性")
    missing = [key for key in ABILITY_KEYS if key not in scores]
    if missing:
        raise RuleError("属性缺项：%s" % ", ".join(missing))
    cleaned: dict[str, int] = {}
    for key in ABILITY_KEYS:
        value = scores[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuleError("属性 %s 必须是整数：%r" % (key.upper(), value))
        cleaned[key] = int(value)
    return rebuild_actor(bundle, actor, profile.with_base_scores(cleaned))


def morph_forms(actor: Actor, bundle: ContentBundle, locale: str = "zh") -> dict:
    """变形形态清单。给选择行用；`usable` 为空说明还没到能变形的等级。"""
    from .sheet import form_options
    return form_options(actor, bundle, locale)


def leave_form_now(actor: Actor) -> Actor:
    """结束变形，返回本体。**没有变形时报错**，不静默返回原对象。"""
    return leave_form(actor)


def current_form(actor: Actor) -> str | None:
    """变形中的形态 id（没变形返回 None）。层 id 是 `form.<id>`，这里拆回来。"""
    top = actor.top()
    if top.kind.value != "form":
        return None
    ident = str(top.id)
    return ident[len(FORM_PREFIX):] if ident.startswith(FORM_PREFIX) else ident


def equipped_map(actor: Actor) -> dict[str, str]:
    """{槽: 物品 id}。界面拿它标「现在装着哪个」。"""
    return {slot.value: ident for slot, ident in actor.root().inventory.equipped.items()}
