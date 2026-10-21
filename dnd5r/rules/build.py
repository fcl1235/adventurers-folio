# -*- coding: utf-8 -*-
"""建角色：把内容定义 + 玩家选择落成一个 Actor。

这里只做「事实的拼装」：职业等级、属性、熟练、资源池、HP 上限。
派生值（AC、豁免、攻击）一律不写进 Actor，交给 Resolver 现算（C5）。
"""

from __future__ import annotations

from typing import Any, Mapping

from ..content import ClassDef, ContentBundle
from ..kernel.errors import RuleError
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.inventory import Inventory
from ..model.levels import ClassLevel, TotalLevel, as_class_level
from ..model.profile import ClassEntry, Profile
from ..model.statblock import Abilities, Statblock
from .health import hit_dice_pool, hit_points_max
from .progression import proficiency_bonus


def _ref_map(
    abilities: Abilities,
    class_level: ClassLevel,
    total: TotalLevel,
    prof_bonus: int,
    speeds: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "prof_bonus": prof_bonus,
        "total_level": int(total),
        "class_level": int(class_level),
        "abilities": abilities,
        "speeds": dict(speeds),
    }


def build_actor(
    bundle: ContentBundle,
    class_id: str,
    class_level: int,
    scores: Mapping[str, int],
    name_zh: str,
    name_en: str,
    actor_id: str = "pc.hero",
    kind: ActorKind = ActorKind.PC,
    extra_proficiencies: tuple[str, ...] = (),
) -> Actor:
    """建一个单职业角色。兼职在 P3 的 Session 里做（要合并位表与熟练来源）。"""
    class_def: ClassDef = bundle.class_def(class_id)
    level = as_class_level(class_level)
    abilities = Abilities.of(**dict(scores))
    total = TotalLevel(int(level))
    prof = proficiency_bonus(total)

    con_mod = abilities.mod("con")
    hp_max = hit_points_max(class_def.hit_die, con_mod, level)

    name = Text.of(name_zh, name_en)
    statblock = Statblock(name=name, abilities=abilities)

    saves = tuple("save.%s" % key for key in class_def.saves)
    profile = Profile(
        classes=(ClassEntry.make(class_id, level),),
        proficiencies=frozenset(saves) | frozenset(extra_proficiencies),
    )

    actor = Actor(
        id=actor_id,
        kind=kind,
        statblock=statblock,
        hp=HpPool(maximum=hp_max),
        profile=profile,
        inventory=Inventory(),
        display_name=name_zh,
    )

    ref = _ref_map(abilities, level, total, prof, statblock.speeds)
    for resource in class_def.resources:
        pool = resource.build(level, ref)
        if pool.capacity <= 0:
            continue  # 未解锁的资源不建池，避免界面上出现 0/0
        actor.resources.add(pool)
    actor.resources.add(hit_dice_pool(class_id, class_def.hit_die, level))
    return actor


def class_level_of(actor: Actor, class_id: str) -> ClassLevel:
    if actor.profile is None:
        raise RuleError("角色没有职业档案")
    return actor.profile.class_level(class_id)


def available_powers(bundle: ContentBundle, actor: Actor):
    """这个角色当前解锁的全部能力（按钮 + 被动）。兼职时按每个职业分别取。"""
    if actor.profile is None:
        return ()
    found = []
    for entry in actor.profile.classes:
        found.extend(bundle.book.for_class(entry.class_id, entry.class_level))
    return tuple(sorted(found, key=lambda item: (item.owner, int(item.level), item.id)))
