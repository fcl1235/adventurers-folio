# -*- coding: utf-8 -*-
"""常驻贡献：把「被动能力写下的东西」变成 Resolver 的输入。

为什么需要这一层：`grant_modifier` 的 `apply()` 只在**用一次能力**的时候跑
（狂暴、光环的临时层）。可被动的无甲防御、守护灵光从不需要「用」——
它们必须每次都算进去。P2 只实现了「用的时候给」，没实现「一直都在」，
所以 12 职业对账时 AC 与豁免全对不上。

这一层不做规则判断，只做收集：
  1. 已解锁被动的 grant_modifier / grant_defense / grant_proficiency
  2. 角色身上生效中的 ActiveEffect（狂暴这类有时限的）
  3. **属性加值通道**（`score.<属性>`）：它改的是属性值本身，不进 d20 管道，
     由 `score_bonuses()` 收集、`apply_score_bonuses()` 在建角色时一次算清

`when` 条件仍由 resolve() 求值，facts 由 `facts_for()` 提供。
"""

from __future__ import annotations

from typing import Any

from ..model.actor import Actor
from ..model.levels import ClassLevel
from .armor import Loadout
from .build import available_powers
from .modifiers import Modifier
from .powers import Power
from .scores import (
    ScoreBonus, apply_score_bonuses, score_bonus_of, score_bonuses,
)


def facts_for(
    actor: Actor,
    class_level: ClassLevel | None = None,
    loadout: Loadout | None = None,
) -> dict[str, Any]:
    """条件求值用的事实。少写一个事实 = 条件永远是 False，所以这里只放确定的。

    `unarmored` 是「没穿护甲」，`shield` 是「拿着盾」，`armor` 是护甲类别
    （light / medium / heavy / None）——
    野蛮人的无甲防御允许持盾、武僧的不允许；野蛮人与游侠的快速移动只禁**重型**护甲。
    这些差别全靠这几条事实 + 内容里的 `when` 表达，代码里不出现职业判断。
    """
    pool = actor.root().hp
    top = actor.top()
    gear = loadout if loadout is not None else Loadout()
    facts: dict[str, Any] = {
        "hp": pool.current,
        "hp_max": pool.maximum,
        "temp_hp": pool.temp,
        "morphed": top.layer is not None,
        "unarmored": gear.unarmored,
        "shield": gear.shielded,
        "armor": None if gear.armor is None else gear.armor.category,
        "conditions": set(actor.conditions.ids()),
    }
    if class_level is not None:
        facts["class_level"] = int(class_level)
    return facts


# --- 属性加值通道 -----------------------------------------------------
# 实现在 rules/scores.py：本模块要 import build，build 建角色又要用这套函数，
# 直接写在这里就成环了。


def _unlocked(bundle, actor: Actor) -> list[Power]:
    return list(available_powers(bundle, actor))


def passive_modifiers(bundle, actor: Actor, locale: str = "zh") -> tuple[Modifier, ...]:
    """角色当前所有常驻 Modifier。

    `source` 用**能力的显示名**而不是 id：它会出现在明细里（
    「14 = 12 基础 +2 无甲防御」），id 出现在玩家眼前只是噪音。
    """
    found: list[Modifier] = []
    for power in _unlocked(bundle, actor):
        label = power.name.get(locale) or power.id
        for effect in power.effects:
            for mod in getattr(effect, "modifiers", ()):
                found.append(mod if mod.source else _with_source(mod, label))
    for node in (actor.root(), actor.top()):
        for effect in node.effects:
            for mod in getattr(effect, "modifiers", ()):
                found.append(mod if mod.source else _with_source(mod, effect.id))
    return tuple(found)


def _with_source(mod: Modifier, source: str) -> Modifier:
    return Modifier(
        target=mod.target, value=mod.value, stack=mod.stack, source=source,
        scope=mod.scope, direction=mod.direction, when=mod.when, cap=mod.cap,
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


def passive_defenses(bundle, actor: Actor) -> tuple[set[str], set[str]]:
    """被动能力给的抗性与免疫（`grant_defense`）。

    返回 (抗性集合, 免疫集合)。这两个是**集合**，不是加减法 ——
    与熟练同一类，所以不走 Modifier 管道。
    """
    resist: set[str] = set()
    immune: set[str] = set()
    for power in _unlocked(bundle, actor):
        for effect in power.effects:
            resist |= set(getattr(effect, "resistance", ()) or ())
            immune |= set(getattr(effect, "immunity", ()) or ())
    return resist, immune


def modifiers_for(modifiers, target: str) -> list[Modifier]:
    """按 target 过滤。`resolve()` 不做过滤，调用方必须自己分开。"""
    return [mod for mod in modifiers if mod.target == target]


def save_modifiers(modifiers, ability: str) -> list[Modifier]:
    return modifiers_for(modifiers, "save.%s" % ability)


__all__ = [
    "facts_for", "passive_modifiers", "passive_proficiencies", "passive_defenses",
    "modifiers_for", "save_modifiers",
    "ScoreBonus", "score_bonuses", "score_bonus_of", "apply_score_bonuses",
]
