# -*- coding: utf-8 -*-
"""常驻贡献：把「被动能力写下的东西」变成 Resolver 的输入。

为什么需要这一层：`grant_modifier` 的 `apply()` 只在**用一次能力**的时候跑
（狂暴、光环的临时层）。可被动的无甲防御、守护灵光从不需要「用」——
它们必须每次都算进去。P2 只实现了「用的时候给」，没实现「一直都在」，
所以 12 职业对账时 AC 与豁免全对不上。

这一层不做规则判断，只做收集：
  1. 已解锁被动的 grant_modifier / grant_defense / grant_proficiency
  2. 角色身上生效中的 ActiveEffect（狂暴这类有时限的）

`when` 条件仍由 resolve() 求值，facts 由 `facts_for()` 提供。
"""

from __future__ import annotations

from typing import Any

from ..model.actor import Actor
from ..model.levels import ClassLevel
from .modifiers import Modifier
from .build import available_powers
from .powers import Power


def facts_for(actor: Actor, class_level: ClassLevel | None = None) -> dict[str, Any]:
    """条件求值用的事实。少写一个事实 = 条件永远是 False，所以这里只放确定的。"""
    pool = actor.root().hp
    top = actor.top()
    facts: dict[str, Any] = {
        "hp": pool.current,
        "hp_max": pool.maximum,
        "temp_hp": pool.temp,
        "morphed": top.layer is not None,
        # 护甲通道还没接（P5b）；现在恒为「没穿甲」，接入后这里改读装备
        "unarmored": True,
        "conditions": set(actor.conditions.ids()),
    }
    if class_level is not None:
        facts["class_level"] = int(class_level)
    return facts


def _unlocked(bundle, actor: Actor) -> list[Power]:
    return list(available_powers(bundle, actor))


def passive_modifiers(bundle, actor: Actor) -> tuple[Modifier, ...]:
    """角色当前所有常驻 Modifier（带 source，明细里能看出是谁给的）。"""
    found: list[Modifier] = []
    for power in _unlocked(bundle, actor):
        for effect in power.effects:
            for mod in getattr(effect, "modifiers", ()):
                found.append(mod if mod.source else _with_source(mod, power.id))
    for node in (actor.root(), actor.top()):
        for effect in node.effects:
            for mod in getattr(effect, "modifiers", ()):
                found.append(mod if mod.source else _with_source(mod, effect.id))
    return tuple(found)


def _with_source(mod: Modifier, source: str) -> Modifier:
    return Modifier(
        target=mod.target, value=mod.value, stack=mod.stack, source=source,
        scope=mod.scope, direction=mod.direction, when=mod.when,
    )


def passive_proficiencies(bundle, actor: Actor) -> set[str]:
    """被动给的永久熟练（无甲防御之外的「全部豁免熟练」这类）。

    临时熟练（有时限或条件）不走这里 —— 它们留在 ActiveEffect 里。
    """
    tokens: set[str] = set()
    for power in _unlocked(bundle, actor):
        for effect in power.effects:
            tokens |= set(getattr(effect, "tokens", ()) or ())
    return tokens


def modifiers_for(modifiers, target: str) -> list[Modifier]:
    """按 target 过滤。`resolve()` 不做过滤，调用方必须自己分开。"""
    return [mod for mod in modifiers if mod.target == target]


def save_modifiers(modifiers, ability: str) -> list[Modifier]:
    return modifiers_for(modifiers, "save.%s" % ability)


__all__ = [
    "facts_for", "passive_modifiers", "passive_proficiencies",
    "modifiers_for", "save_modifiers",
]
