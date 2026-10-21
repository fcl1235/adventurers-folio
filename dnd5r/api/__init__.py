# -*- coding: utf-8 -*-
"""唯一门面：前端只能用这里的东西（约束 C3）。

P2 提供四件事：
  load_content   加载插件内容
  new_character  按内容建角色（HP、资源池、豁免熟练都按数据算）
  character_sheet 只读投影（派生值现算，不落档）
  use_power      执行一个主动能力，返回可直接展示的报告
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from ..content import ClassDef, ContentBundle, load_all
from ..kernel.errors import DndError
from ..kernel.events import Report
from ..kernel.rng import Rng, SeededRng
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.levels import ClassLevel, TotalLevel
from ..model.profile import ClassEntry, Profile
from ..model.statblock import Abilities, Statblock
from ..rules.actioneconomy import ActionEconomy, ActionType
from ..rules.armor import Loadout, ac_inputs, loadout_for
from ..rules.build import (
    available_powers, build_actor, eligible_forms_for, morph_class_of,
    owner_class_id, subclass_defs,
)
from ..rules.contributions import (
    facts_for, modifiers_for, passive_modifiers, passive_proficiencies, save_modifiers,
)
from ..rules.effects import EffectContext
from ..rules.health import hit_dice_average
from ..rules.morph import reasons_for
from ..rules.powers import Power, can_use
from ..rules.progression import MAX_TOTAL_LEVEL, proficiency_bonus, validate_total
from ..rules.resolver import RefContext, Resolver, crit_text
from ..rules.scores import score_bonus_of
from ..rules.weapons import profiles_for
from ..rules.powers import use_power as _use_power
from ..session import LongRest, NewTurn, Regain, Session, ShortRest, TakeDamage, UsePower

VERSION = "0.3.0"

ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")


# --- 内容 -------------------------------------------------------------
def load_content(root: str = "plugins") -> ContentBundle:
    """加载插件目录。坏的插件只进 errors，不抛出。"""
    return load_all(root)


def content_summary(bundle: ContentBundle, locale: str = "zh") -> dict:
    stats = bundle.stats()
    stats["class_names"] = sorted(item.name.get(locale) for item in bundle.classes.values())
    stats["plugins"] = [manifest.id for manifest in bundle.manifests]
    return stats


def subclass_options(
    bundle: ContentBundle,
    class_id: str | None = None,
    locale: str = "zh",
) -> dict:
    """可选子职。不给 class_id 就按职业分组全列出来（建角色界面用）。"""
    rows = (bundle.subclasses_for(class_id) if class_id
            else sorted(bundle.subclasses.values(), key=lambda item: (item.class_id, item.id)))
    return {
        "class": class_id,
        "options": [
            {
                "id": sub.id,
                "class": sub.class_id,
                "name": sub.name.get(locale),
                "summary": sub.summary.get(locale),
                "unlock_level": int(sub.unlock_level),
                "powers": len(sub.powers),
            }
            for sub in rows
        ],
    }


# --- 建角色 -----------------------------------------------------------
def create_actor(
    name_zh: str,
    name_en: str,
    scores: Mapping[str, int],
    classes: Sequence[tuple[str, int]],
    hp_max: int = 10,
    kind: ActorKind = ActorKind.PC,
    actor_id: str = "pc.hero",
) -> Actor:
    """最低层的构造：只拼事实，不算 HP（P1 的接口，保留兼容）。"""
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


def new_character(
    content: ContentBundle,
    class_id: str,
    class_level: int,
    scores: Mapping[str, int],
    name_zh: str = "无名冒险者",
    name_en: str = "Unnamed Adventurer",
    actor_id: str = "pc.hero",
    subclass: str | None = None,
) -> Actor:
    """按内容建角色：HP 上限、资源池、豁免熟练全部从 ClassDef 出来。"""
    return build_actor(
        content,
        class_id=class_id,
        class_level=class_level,
        scores=scores,
        name_zh=name_zh,
        name_en=name_en,
        actor_id=actor_id,
        subclass=subclass,
    )


# --- 派生值 -----------------------------------------------------------
def resolver_for(actor: Actor, content: ContentBundle | None = None) -> Resolver:
    """派生值求解器。给了内容包才会读装备（护甲 / 盾）与真实的无甲事实。"""
    profile = actor.profile
    total = profile.total if profile else TotalLevel(1)
    class_level = None
    if profile and len(profile.classes) == 1:
        class_level = ClassLevel(int(profile.classes[0].class_level))
    top = actor.top()
    loadout = loadout_for(actor, content.armors) if content is not None else Loadout()
    ctx = RefContext(
        prof_bonus=proficiency_bonus(total),
        total_level=total,
        class_level=class_level,
        abilities=top.statblock.abilities,
        speeds=dict(top.statblock.speeds),
        facts=facts_for(actor, class_level, loadout),
    )
    return Resolver(ctx)


def _proficient_saves(actor: Actor) -> set[str]:
    if actor.profile is None:
        return set()
    return {token.split(".", 1)[1] for token in actor.profile.proficiencies
            if token.startswith("save.")}


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


def _ability_rows(actor: Actor, content: ContentBundle, morphed: bool = False) -> dict:
    """属性行：值 / 调整值 / 「白给了多少」。

    变形期间力敏体已被形态换掉，本体的属性加值不再体现在这三项上，
    所以变形时 `bonus` 一律报 0 —— 免得界面上出现「熊 19 力（+4 原始冠军）」。
    """
    top = actor.top()
    bonus = {} if morphed else score_bonus_of(available_powers(content, actor))
    return {
        key: {
            "score": top.statblock.abilities.score(key),
            "mod": top.statblock.abilities.mod(key),
            "bonus": int(bonus.get(key, 0)),
        }
        for key in ABILITY_KEYS
    }


def character_sheet(actor: Actor, content: ContentBundle, locale: str = "zh") -> dict:
    """只读投影：卡片、派生值、能力列表。前端不判断任何规则。"""
    resolver = resolver_for(actor, content)
    profile = actor.profile
    top = actor.top()
    root = actor.root()
    loadout = loadout_for(actor, content.armors)
    morphed = top.layer is not None
    saves_prof = _proficient_saves(actor) | {
        token.split(".", 1)[1]
        for token in passive_proficiencies(content, actor)
        if token.startswith("save.")
    }
    # 常驻贡献：被动能力的 modifier（无甲防御、守护灵光）必须每次都算进去
    mods = passive_modifiers(content, actor, locale)

    base, gear_mods = ac_inputs(loadout, top.statblock, locale)
    ac = resolver.armor_class(
        top, list(modifiers_for(mods, "ac")) + list(gear_mods), base=base
    )
    # 速度加值：变形期间形态的速度取代本体，一切加值都不算（快速移动也不例外）
    speeds = {
        mode: resolver.speed(
            top, mode, () if morphed else modifiers_for(mods, "speed.%s" % mode)
        ).total
        for mode in top.statblock.speeds
    }
    saves = {
        key: resolver.saving_throw(top, key, proficient=key in saves_prof,
                                   modifiers=save_modifiers(mods, key))
        for key in ABILITY_KEYS
    }
    # 攻击：默认用最高的力量／敏捷，只看是否熟练（武器数据在 P5c）
    attack_ability = "str" if top.statblock.abilities.mod("str") >= top.statblock.abilities.mod("dex") else "dex"
    attack = resolver.attack_bonus(top, attack_ability, proficient=True,
                                   modifiers=modifiers_for(mods, "attack"))

    attacks_per_action = 1
    for class_def in _class_defs(actor, content):
        level = profile.class_level(class_def.id) if profile else ClassLevel(1)
        attacks_per_action = max(attacks_per_action, class_def.total_attacks(level))

    tokens = set(actor.profile.proficiencies) if actor.profile else set()
    tokens |= passive_proficiencies(content, actor)
    attack_profiles = profiles_for(actor, content.weapons, top.statblock.abilities,
                                   resolver.ctx.prof_bonus, tokens)
    attacks = [item.to_dict(locale) for item in attack_profiles]
    crit = resolver.crit_range(top, modifiers_for(mods, "attack.crit_min"))

    powers = []
    for power in available_powers(content, actor):
        reasons = can_use(power, _context(actor, locale, SeededRng(0), power, content), None) \
            if power.is_button else []
        powers.append({
            "id": power.id,
            "owner": power.owner,
            "level": int(power.level),
            "kind": power.kind.value,
            "name": power.name.get(locale),
            "text": power.text.get(locale),
            "subtitle": power.subtitle(locale),
            "button": power.is_button,
            "blocked": reasons,
        })

    sheet: dict[str, Any] = {
        "id": actor.id,
        "kind": actor.kind.value,
        "name": top.statblock.name.get(locale),
        "hp": {
            "current": actor.hp.current,
            "maximum": actor.hp.maximum,
            "temp": actor.hp.temp,
            "hit_dice": [{"id": pool.id, "left": pool.available, "max": pool.capacity}
                         for pool in root.resources.pools.values()
                         if pool.kind.value == "dice"],
        },
        "ac": {"total": ac.total, "detail": ac.describe()},
        "initiative": resolver.ability_check(top, "dex").total,
        "speed": speeds,
        "abilities": _ability_rows(actor, content, morphed),
        "gear": loadout.to_dict(locale),
        "saves": {key: {"total": value.total, "detail": value.describe(),
                        "proficient": key in saves_prof}
                  for key, value in saves.items()},
        "attack": {"total": attack.total, "detail": attack.describe(), "ability": attack_ability},
        "crit": {"min": crit.total, "detail": crit.describe(),
                 "text": crit_text(crit.total)},
        "attacks": attacks,
        "attacks_per_action": attacks_per_action,
        "conditions": list(actor.conditions.ids()),
        "morphed": actor.top().layer is not None,
        "forms": [
            {"id": form.id, "name": form.name.get(locale), "cr": form.cr,
             "ac": form.ac, "hp": form.hp, "speeds": dict(form.speeds)}
            for form in eligible_forms_for(actor, content)
        ],
        "pools": [
            {"id": pool.id, "left": pool.available, "max": pool.capacity,
             "kind": pool.kind.value, "refresh": pool.refresh.value}
            for pool in root.resources.pools.values()
            if pool.kind.value != "dice"
        ],
        "powers": powers,
    }
    if profile:
        sheet["classes"] = [
            {"id": entry.class_id, "class_level": int(entry.class_level),
             "name": content.classes[entry.class_id].name.get(locale)
             if entry.class_id in content.classes else entry.class_id}
            for entry in profile.classes
        ]
        sheet["subclasses"] = [
            {"id": sub.id, "class": sub.class_id,
             "name": sub.name.get(locale), "summary": sub.summary.get(locale),
             "unlock_level": int(sub.unlock_level),
             "unlocked": int(profile.class_level(sub.class_id)) >= int(sub.unlock_level)}
            for sub in subclass_defs(content, profile)
        ]
        sheet["total_level"] = int(profile.total)
        sheet["proficiency_bonus"] = proficiency_bonus(profile.total)
        sheet["multiclass"] = profile.is_multiclass
        sheet["max_total_level"] = MAX_TOTAL_LEVEL
    return sheet


def actor_view(actor: Actor, locale: str = "zh") -> dict:
    """兼容 P1 的最小视图（不依赖内容包）。"""
    resolver = resolver_for(actor)
    profile = actor.profile
    top = actor.top()
    view: dict[str, Any] = {
        "id": actor.id,
        "kind": actor.kind.value,
        "name": top.statblock.name.get(locale),
        "hp": {"current": actor.hp.current, "maximum": actor.hp.maximum, "temp": actor.hp.temp},
        "ac": resolver.armor_class(top).describe(),
        "speed": {mode: resolver.speed(top, mode).total for mode in top.statblock.speeds},
        "abilities": {key: {"score": top.statblock.abilities.score(key),
                            "mod": top.statblock.abilities.mod(key)}
                      for key in ABILITY_KEYS},
        "conditions": list(actor.conditions.ids()),
        "pools": [{"id": pool.id, "left": pool.available, "max": pool.capacity}
                  for pool in actor.root().resources.pools.values()],
    }
    if profile:
        view["classes"] = [{"id": entry.class_id, "class_level": int(entry.class_level)}
                           for entry in profile.classes]
        view["total_level"] = int(profile.total)
        view["proficiency_bonus"] = proficiency_bonus(profile.total)
        view["multiclass"] = profile.is_multiclass
        view["max_total_level"] = MAX_TOTAL_LEVEL
    return view


# --- 执行能力 ---------------------------------------------------------
def _context(
    actor: Actor,
    locale: str = "zh",
    rng: Rng | None = None,
    power: Power | None = None,
    content: ContentBundle | None = None,
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
    )


def find_power(content: ContentBundle, power_id: str, actor: Actor | None = None) -> Power:
    """按 id 取能力。给了 actor 就取「他当前等级解锁的那一份」（含叠层）。"""
    if actor is not None:
        for power in available_powers(content, actor):
            if power.id == power_id:
                return power
    return content.book.get(power_id)


def use_power(
    actor: Actor,
    content: ContentBundle,
    power_id: str,
    economy: ActionEconomy | None = None,
    seed: int | None = None,
    locale: str = "zh",
    choice: Mapping[str, Any] | None = None,
) -> dict:
    """执行主动能力，返回 {ok, message, events, rolls, sheet} 供前端直接渲染。

    `choice` 是这次操作要玩家做的选择：变形要传 `{"form_id": ...}`。
    """
    power = find_power(content, power_id, actor)
    economy = economy if economy is not None else ActionEconomy()
    ctx = _context(actor, locale, SeededRng(seed), power, content)
    ctx.scratch.update(choice or {})
    if any(getattr(effect, "op", "") == "morph" for effect in power.effects):
        ctx.scratch["forms"] = {form.id: form for form in eligible_forms_for(actor, content)}
    try:
        report = _use_power(power, ctx, economy)
    except DndError as exc:
        return {"ok": False, "message": str(exc), "events": [], "rolls": [],
                "sheet": character_sheet(actor, content, locale)}

    for key, amount in list(ctx.scratch.items()):
        if key.startswith("granted_"):
            kind = key[len("granted_"):]
            try:
                economy.grant(ActionType(kind), int(amount))
            except DndError:
                continue

    return {
        "ok": report.ok,
        "message": report.message,
        "events": [_event_dict(event) for event in report.events],
        "rolls": [{"label": roll.label, "total": roll.total, "detail": roll.detail}
                  for roll in report.rolls],
        "economy": economy.to_dict(),
        "sheet": character_sheet(actor, content, locale),
    }


def _event_dict(event) -> dict:
    data = {"type": type(event).__name__}
    for key in ("current", "maximum", "temp", "pool_id", "delta", "used", "capacity",
                "condition_id", "applied", "power_id", "ok", "reason", "label", "total"):
        if hasattr(event, key):
            data[key] = getattr(event, key)
    return data


def form_options(actor: Actor, content: ContentBundle, locale: str = "zh") -> dict:
    """变形形态清单：可选 + 不可选（带原因）。

    前端只负责画，不判断 CR 轴和游泳／飞行解禁 —— 那是内容侧的事。
    """
    found = morph_class_of(actor, content)
    if found is None:
        return {"class": None, "class_level": 0, "usable": [], "blocked": []}
    entry, class_def = found
    usable = eligible_forms_for(actor, content)
    usable_ids = {form.id for form in usable}
    blocked = [
        {
            "id": form.id,
            "name": form.name.get(locale),
            "cr": form.cr,
            "reasons": reasons_for(class_def.morph, entry.class_level, form)
            or ["变形能力还没解锁"],
        }
        for form in sorted(content.forms.values(), key=lambda item: (item.cr, item.id))
        if form.id not in usable_ids
    ]
    return {
        "class": class_def.name.get(locale),
        "class_level": int(entry.class_level),
        "usable": [
            {"id": form.id, "name": form.name.get(locale), "cr": form.cr,
             "ac": form.ac, "hp": form.hp, "speeds": dict(form.speeds)}
            for form in usable
        ],
        "blocked": blocked,
    }


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


__all__ = [
    "VERSION", "load_content", "content_summary",
    "create_actor", "new_character", "resolver_for",
    "character_sheet", "actor_view",
    "find_power", "use_power", "plugin_summary",
    "eligible_forms_for", "morph_class_of", "form_options",
    "ActionEconomy", "ActionType",
    "Session", "UsePower", "ShortRest", "LongRest", "NewTurn", "TakeDamage", "Regain",
]
