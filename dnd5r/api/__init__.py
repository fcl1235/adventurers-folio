# -*- coding: utf-8 -*-
"""唯一门面：前端只能用这里的东西（约束 C3）。

P1 阶段先提供「建角色」与「看角色」两件事，
卡片化 DTO 与 Session.dispatch 在 P3 补齐。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.levels import ClassLevel
from ..model.profile import ClassEntry, Profile
from ..model.statblock import Abilities, Statblock
from ..rules.progression import MAX_TOTAL_LEVEL, proficiency_bonus, validate_total
from ..rules.resolver import RefContext, Resolver

VERSION = "0.1.0"


def create_actor(
    name_zh: str,
    name_en: str,
    scores: Mapping[str, int],
    classes: Sequence[tuple[str, int]],
    hp_max: int = 10,
    kind: ActorKind = ActorKind.PC,
    actor_id: str = "pc.hero",
) -> Actor:
    """建一个角色。classes 是 (职业 id, 该职业等级) 列表，支持兼职。

    前端只传字符串，不接触 kernel.Text —— 这样 C3 才能守住。
    """
    entries = tuple(ClassEntry.make(class_id, level) for class_id, level in classes)
    profile = Profile(classes=entries)
    validate_total(profile)

    name = Text.of(name_zh, name_en)
    abilities = Abilities.of(**dict(scores))
    statblock = Statblock(name=name, abilities=abilities)
    return Actor(
        id=actor_id,
        kind=kind,
        statblock=statblock,
        hp=HpPool(maximum=hp_max),
        profile=profile,
        display_name=name_zh,
    )


def resolver_for(actor: Actor) -> Resolver:
    profile = actor.profile
    total = profile.total if profile else 1
    class_level = None
    if profile and len(profile.classes) == 1:
        class_level = ClassLevel(int(profile.classes[0].class_level))
    ctx = RefContext(
        prof_bonus=proficiency_bonus(total),
        total_level=total,
        class_level=class_level,
        abilities=actor.statblock.abilities,
        speeds=dict(actor.statblock.speeds),
    )
    return Resolver(ctx)


def actor_view(actor: Actor, locale: str = "zh") -> dict:
    """只读投影：派生值全部现算，不落档。"""
    resolver = resolver_for(actor)
    profile = actor.profile
    top = actor.top()
    view: dict[str, Any] = {
        "id": actor.id,
        "kind": actor.kind.value,
        "name": top.statblock.name.get(locale),
        "hp": {
            "current": actor.hp.current,
            "maximum": actor.hp.maximum,
            "temp": actor.hp.temp,
        },
        "ac": resolver.armor_class(top).describe(),
        "speed": {mode: resolver.speed(top, mode).total for mode in top.statblock.speeds},
        "abilities": {
            key: {
                "score": top.statblock.abilities.score(key),
                "mod": top.statblock.abilities.mod(key),
            }
            for key in ("str", "dex", "con", "int", "wis", "cha")
        },
        "conditions": list(actor.conditions.ids()),
        "pools": [
            {"id": pool.id, "left": pool.available, "max": pool.capacity}
            for pool in actor.root().resources.pools.values()
        ],
    }
    if profile:
        view["classes"] = [
            {"id": entry.class_id, "class_level": int(entry.class_level)}
            for entry in profile.classes
        ]
        view["total_level"] = int(profile.total)
        view["proficiency_bonus"] = proficiency_bonus(profile.total)
        view["multiclass"] = profile.is_multiclass
        view["max_total_level"] = MAX_TOTAL_LEVEL
    return view


def plugin_summary(root: str = "plugins", locale: str = "zh") -> list[dict]:
    """给前端看的插件列表；坏掉的插件只记录不抛出。"""
    from ..loader import discover

    found = discover(root)
    return [
        {
            "id": manifest.id,
            "kind": manifest.kind,
            "version": manifest.version,
            "name": manifest.name.get(locale),
            "provides": {key: len(value) for key, value in manifest.provides.items()},
        }
        for manifest in found.manifests
    ]


__all__ = ["VERSION", "create_actor", "resolver_for", "actor_view", "plugin_summary"]
