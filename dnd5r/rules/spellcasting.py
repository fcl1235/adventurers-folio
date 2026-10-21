# -*- coding: utf-8 -*-
"""施法：法术豁免 DC、法术攻击加值、可选法术、法位与准备上限。

这一层**不做目标结算** —— 引擎现在只有一个角色，没有战斗目标模型
（敌人、区域、占据都还没进内核）。所以这里只做「算得出来的那部分」：

  DC = 8 + 熟练 + 施法属性调整值        ← 纯规则，与目标无关
  攻击加值 = 熟练 + 施法属性调整值
  可选法术 = 职业表 ∩ 当前环位 ≤ 最高可施环
  准备上限 / 戏法数 = 职业表查等级

伤害骰、豁免结果、区域影响留给出「施法结算」时再接 —— 那需要一个目标模型，
不是这一层能凭空造出来的。
"""

from __future__ import annotations

from typing import Iterable

from ..content import ClassDef, ContentBundle, SpellDef
from ..kernel.errors import RuleError
from ..model.actor import Actor
from ..model.levels import ClassLevel
from ..rules.resolver import Resolver


def casting_ability(class_def: ClassDef) -> str:
    """这个职业用哪个属性施法。数据里没写就是内容错误，不猜 int。"""
    if not class_def.casting_ability:
        raise RuleError("职业 %s 没有声明 casting_ability" % class_def.id)
    return class_def.casting_ability


def spell_dc(resolver: Resolver, actor: Actor, ability: str):
    """法术豁免 DC：8 + 熟练 + 属性调整值。"""
    return resolver.spell_dc(actor, ability)


def spell_attack_bonus(resolver: Resolver, actor: Actor, ability: str):
    return resolver.spell_attack(actor, ability)


def max_cantrips(class_def: ClassDef, class_level: ClassLevel) -> int:
    """已知戏法数（查表，取不超过等级的最大档）。"""
    return _at(class_def.cantrips, int(class_level))


def max_prepared(class_def: ClassDef, class_level: ClassLevel) -> int:
    """可准备法术数（2024 的「准备法术」表，不是「等级 + 属性」估算）。"""
    return _at(class_def.prepared, int(class_level))


def _at(table, class_level: int) -> int:
    """查表：取不超过该职业等级的最大档（与资源表同一条规则）。

    参数刻意叫 `class_level` 且只收整数 —— 这里查的是**职业**等级表，
    传进总等级就是错；C8 只拦 `level` 这个名字，名字写清才是真防线。
    """
    usable = [int(key) for key in table or () if int(key) <= int(class_level)]
    return 0 if not usable else int(table[max(usable)])


def highest_slot(actor: Actor, class_id: str) -> int:
    """这个职业当前能用的最高环位（从资源池里读，不从等级推）。"""
    top = 0
    for pool in actor.root().resources.pools.values():
        if pool.owner_class and pool.owner_class != class_id:
            continue
        if not pool.id.startswith("dnd2024.slot."):
            continue
        level = int(pool.id.rsplit(".", 1)[-1])
        if pool.capacity > 0:
            top = max(top, level)
    return top


def spell_options(
    bundle: ContentBundle,
    actor: Actor,
    class_id: str,
    class_level: ClassLevel,
) -> tuple[SpellDef, ...]:
    """这个角色在这一职业下可选的施法法术（戏法另算）。

    过滤条件只有两条：在职业表里，且环级不超过当前最高施法位。
    准备与否属于玩家的选择，不在这里筛。
    """
    top = highest_slot(actor, class_id)
    allowed = set(bundle.spell_list(class_id))
    return tuple(sorted(
        (spell for spell in bundle.spells.values()
         if spell.id in allowed and 0 < int(spell.level) <= top),
        key=lambda item: (int(item.level), item.id),
    ))


def cantrip_options(bundle: ContentBundle, class_id: str) -> tuple[SpellDef, ...]:
    allowed = set(bundle.spell_list(class_id))
    return tuple(sorted(
        (spell for spell in bundle.spells.values()
         if spell.id in allowed and int(spell.level) == 0),
        key=lambda item: item.id,
    ))


def slot_rows(actor: Actor, class_id: str, locale: str = "zh") -> list[dict]:
    """法位余量表：[(环级, 剩余, 上限)]，按环级升序。"""
    rows = []
    for pool in actor.root().resources.pools.values():
        if not pool.id.startswith("dnd2024.slot."):
            continue
        if pool.owner_class and pool.owner_class != class_id:
            continue
        level = int(pool.id.rsplit(".", 1)[-1])
        rows.append({"level": level, "left": pool.available, "max": pool.capacity,
                     "label": pool.label.get(locale) if pool.label else ""})
    return sorted(rows, key=lambda item: item["level"])


def casting_summary(
    bundle: ContentBundle,
    actor: Actor,
    class_id: str,
    class_level: ClassLevel,
    resolver: Resolver,
    locale: str = "zh",
) -> dict:
    """给界面用的一块数据：DC、攻击加值、法位、上限、可选法术。"""
    class_def = bundle.class_def(class_id)
    ability = casting_ability(class_def)
    dc = spell_dc(resolver, actor, ability)
    attack = spell_attack_bonus(resolver, actor, ability)
    spells = spell_options(bundle, actor, class_id, class_level)
    cantrips = cantrip_options(bundle, class_id)
    return {
        "class": class_id,
        "ability": ability,
        "dc": {"total": dc.total, "detail": dc.describe()},
        "attack": {"total": attack.total, "detail": attack.describe()},
        "slots": slot_rows(actor, class_id, locale),
        "highest_slot": highest_slot(actor, class_id),
        "cantrips": {"max": max_cantrips(class_def, class_level),
                     "options": [item.to_dict(locale) for item in cantrips]},
        "prepared": {"max": max_prepared(class_def, class_level),
                     "options": [item.to_dict(locale) for item in spells]},
    }


def spell_detail(bundle: ContentBundle, spell_id: str, locale: str = "zh") -> dict:
    """单条法术的展示数据（含该环位的伤害骰式）。"""
    spell = bundle.spell(spell_id)
    data = spell.to_dict(locale)
    data["damage_at_base"] = spell.damage_at(int(spell.level))
    return data


__all__ = [
    "casting_ability", "spell_dc", "spell_attack_bonus", "max_cantrips",
    "max_prepared", "highest_slot", "spell_options", "cantrip_options",
    "slot_rows", "casting_summary", "spell_detail",
]
