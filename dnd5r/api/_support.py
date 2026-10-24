# -*- coding: utf-8 -*-
"""api 门面的共用底座：派生值求解、检定模式、执行上下文。

这里不放任何「一件事」，只放被多个子模块共用的装配代码（拆自 P11 之前的
巨型 __init__，见架构文档 §14.32）。"""
from __future__ import annotations

from typing import Any

from ..kernel.errors import RuleError

from ..content import ClassDef, ContentBundle
from ..kernel.rng import Rng, SeededRng
from ..model.actor import Actor
from ..model.levels import TotalLevel
from ..rules.build import owner_class_id
from ..rules.contributions import passive_advantage_modes, passive_proficiencies
from ..rules.derived import resolver_for as _resolver_for
from ..rules.effects import EffectContext
from ..rules.encounter import Encounter
from ..rules.powers import Power
from ..rules.progression import proficiency_bonus
from ..rules.resolver import Resolver

VERSION = "0.3.0"

ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")

# 选单里的分组顺序：起源 → 通用 → 战斗风格 → 传奇恩惠
FEAT_KIND_ORDER = ("origin", "general", "fighting_style", "epic_boon")


def resolver_for(actor: Actor, content: ContentBundle | None = None) -> Resolver:
    """派生值求解器。给了内容包才会读装备（护甲 / 盾）与真实的无甲事实。

    装配在 `rules/derived.py`：施法结算那边要用同一份，
    两边各写一遍的话，「界面按穿了甲算、结算按没穿算」这种错不会有任何报错。
    """
    return _resolver_for(actor, None if content is None else content.armors)


def _proficient_saves(actor: Actor) -> set[str]:
    if actor.profile is None:
        return set()
    return {token.split(".", 1)[1] for token in actor.profile.proficiencies
            if token.startswith("save.")}


def _dice_mode(content: ContentBundle, actor: Actor, query: str) -> tuple[str, tuple[str, ...]]:
    """这一次检定的掷骰模式。**所有 d20 都从这里取**，别在别处再判一遍。"""
    return passive_advantage_modes(content, actor, query)


def _proficiency_sets(actor: Actor, content: ContentBundle) -> tuple[set[str], set[str], set[str]]:
    """(豁免熟练, 技能熟练令牌, 专精令牌)。

    角色卡与掷骰**必须用同一份**：两边各算一遍的话，界面上写「隐匿 +7」、
    真掷的时候按 +5 算，是最难发现的那种错。
    """
    profile = actor.profile
    saves_prof = _proficient_saves(actor) | {
        token.split(".", 1)[1]
        for token in passive_proficiencies(content, actor)
        if token.startswith("save.")
    }
    skill_tokens = set(profile.proficiencies if profile else ())
    skill_tokens |= passive_proficiencies(content, actor)
    expertise_tokens = set(profile.expertise if profile else ())
    return saves_prof, skill_tokens, expertise_tokens


def _class_defs(actor: Actor, content: ContentBundle) -> list[ClassDef]:
    if actor.profile is None:
        return []
    found = []
    for entry in actor.profile.classes:
        if entry.class_id in content.classes:
            found.append(content.classes[entry.class_id])
    return found


def _ref_map(actor: Actor, resolver: Resolver) -> dict[str, Any]:
    return resolver.ctx.as_mapping()


# --- 执行能力 ---------------------------------------------------------
def _context(
    actor: Actor,
    locale: str = "zh",
    rng: Rng | None = None,
    power: Power | None = None,
    content: ContentBundle | None = None,
    encounter: Encounter | None = None,
) -> EffectContext:
    resolver = resolver_for(actor)
    profile = actor.profile
    class_level = None
    if profile and power is not None:
        # 子职特性的 owner 是子职 id，要顺回父职业才能拿到 class_level
        owner = owner_class_id(content, power) if content is not None else power.owner
        if owner is not None and profile.has_class(owner):
            class_level = profile.class_level(owner)
    if class_level is None and profile and len(profile.classes) == 1:
        class_level = profile.classes[0].class_level
    total = profile.total if profile else TotalLevel(1)
    return EffectContext(
        actor=actor,
        rng=rng or SeededRng(),
        locale=locale,
        prof_bonus=proficiency_bonus(total),
        total_level=total,
        class_level=class_level,
        source=power.id if power else "",
        encounter=encounter,
    )


def _need_ability(ability: str) -> None:
    if ability not in ABILITY_KEYS:
        raise RuleError("不认识的属性：%r（可选 %s）" % (ability, "/".join(ABILITY_KEYS)))
