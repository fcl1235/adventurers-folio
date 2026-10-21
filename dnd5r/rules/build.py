# -*- coding: utf-8 -*-
"""建角色：把内容定义 + 玩家选择落成一个 Actor。

这里只做「事实的拼装」：职业等级、属性、熟练、资源池、HP 上限。
派生值（AC、豁免、攻击）一律不写进 Actor，交给 Resolver 现算（C5）。
"""

from __future__ import annotations

from typing import Any, Mapping

from ..content import ClassDef, ContentBundle, SubclassDef
from ..kernel.errors import RuleError
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.inventory import Inventory
from ..model.levels import ClassLevel, TotalLevel, as_class_level
from ..model.profile import ClassEntry, Profile
from ..model.resources import Pool, PoolKind, Refresh
from ..model.statblock import Abilities, Statblock
from .health import hit_dice_pool, hit_points_max
from .modifiers import resolve as resolve_modifiers
from .morph import eligible_forms
from .powers import Power
from .progression import proficiency_bonus
from .scores import apply_score_bonuses, score_bonuses


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


def subclass_defs(bundle: ContentBundle, profile: Profile | None) -> tuple[SubclassDef, ...]:
    """档案里挂着的子职（内容不存在时跳过 —— 缺插件不该让整张卡崩掉）。"""
    if profile is None:
        return ()
    return tuple(
        bundle.subclasses[item] for item in profile.subclasses
        if item in bundle.subclasses
    )


def _hp_bonus(powers, target: str, ref: Mapping[str, Any]) -> int:
    """HP 通道：`hp.per_level`（每级 +N）/ `hp.flat`（一次性 +N）。

    走 Modifier 是为了让「坚韧 +2×等级」「龙裔韧性 +3×术士等级」共用一条通道 ——
    数值与等级的关系写在内容的 Amount 里，代码不知道谁是术士。
    """
    mods = [
        mod for power in powers
        for effect in power.effects
        for mod in getattr(effect, "modifiers", ())
        if mod.target == target
    ]
    if not mods:
        return 0
    return resolve_modifiers(mods, base=0, ctx=dict(ref)).total


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
    subclass: str | None = None,
) -> Actor:
    """建一个单职业角色。兼职在 P3 的 Session 里做（要合并位表与熟练来源）。"""
    class_def: ClassDef = bundle.class_def(class_id)
    level = as_class_level(class_level)
    total = TotalLevel(int(level))
    prof = proficiency_bonus(total)

    # 子职只在自己职业的等级达到门槛后才给特性（3 级才选，1–2 级传进来也不生效）
    sub = bundle.subclass(subclass) if subclass else None
    if sub is not None and sub.class_id != class_id:
        raise RuleError("子职 %s 不属于职业 %s" % (sub.id, class_id))
    sub_powers = sub.powers_at(level) if sub is not None else ()

    # 属性加值通道：原始冠军 / 身心合一这类「属性值 +4」的能力在这里落地。
    # 必须在算 HP 之前：加值改了体质调整值，HP 上限跟着变，否则 20 级会少 40 点。
    powers = class_def.powers_at(level)
    all_powers = tuple(powers) + tuple(p for p in sub_powers if p not in powers)
    bonuses = score_bonuses(all_powers)
    abilities = apply_score_bonuses(Abilities.of(**dict(scores)), bonuses)

    con_mod = abilities.mod("con")
    name = Text.of(name_zh, name_en)
    statblock = Statblock(name=name, abilities=abilities)
    ref = _ref_map(abilities, level, total, prof, statblock.speeds)
    hp_max = hit_points_max(
        class_def.hit_die, con_mod, level,
        per_level_bonus=_hp_bonus(all_powers, "hp.per_level", ref),
        flat_bonus=_hp_bonus(all_powers, "hp.flat", ref),
    )

    saves = tuple("save.%s" % key for key in class_def.saves)
    profile = Profile(
        classes=(ClassEntry.make(class_id, level),),
        subclasses=(sub.id,) if sub is not None else (),
        proficiencies=(frozenset(saves)
                       | frozenset(class_def.proficiencies)
                       | frozenset(extra_proficiencies)),
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

    for resource in class_def.resources:
        pool = resource.build(level, ref)
        if pool.capacity <= 0:
            continue  # 未解锁的资源不建池，避免界面上出现 0/0
        actor.resources.add(pool)
    for index_, capacity in enumerate(class_def.slots_at(level), start=1):
        if capacity <= 0:
            continue
        actor.resources.add(Pool(
            id="dnd2024.slot.%s.%d" % (class_id.split(".")[-1], index_),
            kind=PoolKind.SLOT,
            capacity=capacity,
            label=Text.of("%d 环法术位" % index_, "Level %d Spell Slots" % index_),
            owner_class=class_id,
            refresh=class_def.slot_refresh,
        ))
    actor.resources.add(hit_dice_pool(class_id, class_def.hit_die, level))
    return actor


def class_level_of(actor: Actor, class_id: str) -> ClassLevel:
    if actor.profile is None:
        raise RuleError("角色没有职业档案")
    return actor.profile.class_level(class_id)


def available_powers(bundle: ContentBundle, actor: Actor):
    """这个角色当前解锁的全部能力（按钮 + 被动），**含子职特性**。

    走 `powers_at` 而不是 `PowerBook.for_class`：前者会按等级把 patch 叠上去
    （18 级野兽施法解除变形施法禁令），后者是未叠层的原版。

    子职特性用**父职业**的等级判定：「3 级才拿子职」由 `SubclassDef.powers_at`
    的等级门槛表达，所以这里不需要先看职业几级再决定要不要加子职。
    """
    if actor.profile is None:
        return ()
    found = []
    for entry in actor.profile.classes:
        class_def = bundle.classes.get(entry.class_id)
        if class_def is not None:
            found.extend(class_def.powers_at(entry.class_level))
        for sub in subclass_defs(bundle, actor.profile):
            if sub.class_id == entry.class_id:
                found.extend(sub.powers_at(entry.class_level))
    return tuple(sorted(found, key=lambda item: (item.owner, int(item.level), item.id)))


def owner_class_id(bundle: ContentBundle, power: Power) -> str | None:
    """这个能力属于哪个职业 —— 子职特性的 owner 是子职，要顺着 class 找回去。

    派生数值里 `class_level` 这类符号引用必须绑到**父职业**的等级上，
    否则子职特性的「每级 +3」会算成 0 或者总等级。
    """
    if power.owner in bundle.classes:
        return power.owner
    subclass = bundle.subclasses.get(power.owner)
    return None if subclass is None else subclass.class_id


def morph_class_of(actor: Actor, bundle: ContentBundle):
    """这个角色身上带「形态轴」的那个职业（德鲁伊）。按数据找，不判 class_id。"""
    if actor.profile is None:
        return None
    for entry in actor.profile.classes:
        class_def = bundle.classes.get(entry.class_id)
        if class_def is not None and class_def.morph is not None:
            return entry, class_def
    return None


def eligible_forms_for(actor: Actor, bundle: ContentBundle):
    """当前可选的形态。还要求变形能力本身已解锁 —— 1 级德鲁伊还没有荒野变形。"""
    found = morph_class_of(actor, bundle)
    if found is None:
        return []
    entry, class_def = found
    unlocked = any(
        getattr(effect, "op", "") == "morph"
        for power in class_def.powers_at(entry.class_level)
        for effect in power.effects
    )
    if not unlocked:
        return []
    return eligible_forms(bundle.forms.values(), class_def.morph, entry.class_level)
