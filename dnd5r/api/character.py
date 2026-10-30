# -*- coding: utf-8 -*-
"""角色装配与变更：建卡、专长/法术选择、执行能力。

`use_power` 是唯一的主动能力入口，返回的 sheet 由 `api.sheet` 现算 ——
没有第二份投影。拆自 P11 之前的巨型 __init__。"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..content import ContentBundle
from ..kernel.errors import DndError, RuleError
from ..kernel.rng import Rng, SeededRng
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.profile import ClassEntry, Profile, class_levels_of
from ..model.statblock import Abilities, Statblock
from ..rules.actioneconomy import ActionEconomy, ActionType
from ..rules.build import (
    available_powers, build_actor, eligible_forms_for, rebuild_actor,
)
from ..rules.encounter import Encounter
from ..rules.feats import pick_key, prereq_report
from ..rules.powers import Power, use_power as _use_power
from ..rules.progression import MAX_TOTAL_LEVEL, validate_total
from ..rules.spellcasting import casting_summary, check_spell_picks
from ._support import ABILITY_KEYS, FEAT_KIND_ORDER, _context, resolver_for
from .sheet import character_sheet

def plan_spells(
    actor: Actor,
    content: ContentBundle,
    class_id: str,
    cantrips: Sequence[str] | None = None,
    prepared: Sequence[str] | None = None,
    locale: str = "zh",
) -> dict:
    """设定某职业的「已知戏法 / 准备法术」，校验通过后写回档案。

    两个参数都给 `None` 就是只查询（返回当前摘要）。校验与建角色共用
    `check_spell_picks`，所以「界面能选、记账时炸」这种不一致不会出现。
    校验失败时**不改档案** —— 抛错的调用不该留下半截状态。
    """
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案")
    if class_id not in profile.class_ids:
        raise RuleError("角色没有职业 %s" % class_id)
    updated = profile
    if cantrips is not None:
        updated = updated.with_cantrips(class_id, cantrips)
    if prepared is not None:
        updated = updated.with_prepared(class_id, prepared)

    problems = check_spell_picks(content, class_levels_of(updated),
                                 updated.cantrips, updated.prepared, locale)
    if problems:
        raise RuleError("法术选择有问题：" + "；".join(problems))

    actor.profile = updated
    return casting_summary(content, actor, class_id,
                           class_levels_of(updated)[class_id],
                           resolver_for(actor, content), locale)


def spell_plan(actor: Actor, content: ContentBundle, locale: str = "zh") -> list[dict]:
    """全部施法职业的施法摘要（法术页直接渲染这个）。"""
    profile = actor.profile
    if profile is None:
        return []
    resolver = resolver_for(actor, content)
    rows = []
    for entry in profile.classes:
        class_def = content.classes.get(entry.class_id)
        if class_def is None or not class_def.casting_ability:
            continue
        rows.append(casting_summary(content, actor, entry.class_id,
                                    entry.class_level, resolver, locale))
    return rows


def set_feat_choice(
    actor: Actor,
    content: ContentBundle,
    feat_id: str,
    choice_id: str,
    picked: Sequence[str],
    index: int = 0,
    locale: str = "zh",
) -> Actor:
    """改一个专长选择项，返回**重建后**的角色（属性加值会改一堆派生值）。

    为什么不就地改：属性提升改了体质调整值，HP 上限、豁免、技能全要跟着变。
    就地改字段必然漏一处，所以整只重建 —— 重建时保住当前 HP 与已用资源。

    失败时抛错且**原角色一个字段都没动**：先在验证通过的档案上重建，
    再整只换掉。界面可以把错误显示出来，角色仍是可用的。
    """
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案")
    feat = content.feats.get(feat_id)
    if feat is None:
        raise RuleError("没有这个专长：%s" % feat_id)
    if feat_id not in profile.feats:
        raise RuleError("角色没有这个专长：%s" % feat.name.get(locale))
    choice = next((item for item in feat.choices if item.id == choice_id), None)
    if choice is None:
        raise RuleError("专长「%s」没有选择项 %s" % (feat.name.get(locale), choice_id))
    items = tuple(str(item) for item in picked)
    key = pick_key(feat_id, choice_id, index)
    updated = profile.with_choices({**profile.choices, key: items})
    return rebuild_actor(content, actor, profile=updated)


# --- 存档 -------------------------------------------------------------


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
    feats: Sequence[str] = (),
    choices: Mapping[str, Sequence[str]] | None = None,
    cantrips: Mapping[str, Sequence[str]] | None = None,
    prepared: Mapping[str, Sequence[str]] | None = None,
    extra_classes: Sequence[tuple[str, int]] = (),
    extra_subclasses: Sequence[str] = (),
    species: str = "",
    background: str = "",
    background_bonus: Mapping[str, int] | None = None,
    masteries: Sequence[str] = (),
    extra_proficiencies: Sequence[str] = (),
    extra_expertise: Sequence[str] = (),
) -> Actor:
    """按内容建角色：HP 上限、资源池、豁免熟练全部从 ClassDef 出来。

    `choices` 是专长的「选完还要选什么」：键 `<专长 id>.<选择项 id>`，
    值是被选中的项（如 `{"dnd2024.feat.ability_score_improvement.boost": ["dex", "dex"]}`）。
    同一专长登记两次时，第二次起键写成 `<专长 id>#1.<选择项 id>`。

    `extra_classes` 是兼职段 [(职业 id, 等级)]；第一个参数永远是**起始职业**
    （豁免熟练与起始熟练只来自它）。子职：起始职业用 `subclass`，
    兼职职业的子职用 `extra_subclasses`。
    `cantrips` / `prepared` 是法术选择：键都是**职业 id**，值是法术 id。
    数量与环级的校验在 `rules/spellcasting.check_spell_picks` 里，选错当场拒绝。
    """
    return build_actor(
        content,
        class_id=class_id,
        class_level=class_level,
        scores=scores,
        name_zh=name_zh,
        name_en=name_en,
        actor_id=actor_id,
        subclass=subclass,
        feats=tuple(feats),
        choices={key: tuple(value) for key, value in (choices or {}).items()},
        cantrips={key: tuple(value) for key, value in (cantrips or {}).items()},
        prepared={key: tuple(value) for key, value in (prepared or {}).items()},
        extra_classes=tuple((str(k), int(v)) for k, v in extra_classes),
        extra_subclasses=tuple(str(item) for item in extra_subclasses),
        species=species,
        background=background,
        background_bonus=dict(background_bonus or {}),
        masteries=tuple(masteries),
        extra_proficiencies=tuple(extra_proficiencies),
        extra_expertise=tuple(extra_expertise),
    )


# --- 派生值 -----------------------------------------------------------


def feat_options(
    content: ContentBundle,
    actor: Actor | None = None,
    kind: str | None = None,
    locale: str = "zh",
) -> dict:
    """可选专长清单。`selectable` 已经按**硬前提**判过，前端只画不判断（C2 的边界）。"""
    profile = actor.profile if actor else None
    total = int(profile.total) if profile else MAX_TOTAL_LEVEL
    class_ids = profile.class_ids if profile else ()
    scores = ({key: actor.top().statblock.abilities.score(key) for key in ABILITY_KEYS}
              if actor else None)
    taken = set(profile.feats) if profile else set()
    order = {name: index for index, name in enumerate(FEAT_KIND_ORDER)}
    rows = []
    for feat in content.feats.values():
        if kind and feat.kind != kind:
            continue
        blocked = prereq_report(feat, total, class_ids, scores)
        if feat.id in taken and not feat.repeatable:
            blocked.append("已经选过（不可重复选取）")
        rows.append({
            "id": feat.id,
            "name": feat.name.get(locale),
            "kind": feat.kind,
            "level": int(feat.level),
            "selectable": not blocked,
            "blocked": blocked,
            "taken": feat.id in taken,
        })
    rows.sort(key=lambda row: (order.get(row["kind"], 99), row["level"], row["id"]))
    return {"total_level": total, "count": len(rows), "feats": rows}


def free_casts(actor: Actor, content: ContentBundle, locale: str = "zh") -> list[dict]:
    """这个角色「不消耗法术位还能放几次」的清单，给界面直接列。

    数据来源就是资源池本身（`Pool.spell`），不另存一份计数器 ——
    否则用掉一次以后，两个地方各说各话。
    """
    rows = []
    for pool in actor.root().resources.pools.values():
        if not pool.spell:
            continue
        spell = content.spells.get(pool.spell)
        rows.append({
            "pool": pool.id,
            "spell": pool.spell,
            "name": spell.name.get(locale) if spell is not None else pool.spell,
            "level": int(spell.level) if spell is not None else 0,
            "left": int(pool.available),
            "capacity": int(pool.capacity),
            "source": pool.source,
            "refresh": pool.refresh.value,
        })
    return sorted(rows, key=lambda row: (row["level"], row["pool"]))


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
    encounter: Encounter | None = None,
    rng: Rng | None = None,
) -> dict:
    """执行主动能力，返回 {ok, message, events, rolls, sheet} 供前端直接渲染。

    `choice` 是这次操作需要玩家做的选择：变形要传 `{"form_id": ...}`，
    带传送的能力要传 `{"to": (x, y)}`（格坐标）。
    传了 `encounter` 才会真的挪位置 —— 不传就是「没结算」，报告里会说。
    `rng` 优先于 `seed`：会话（Session）要延续同一条随机序列，不是每次重开。
    """
    power = find_power(content, power_id, actor)
    if economy is None and encounter is not None and encounter.has(actor):
        # 遭遇战里每个人的额度就在 Combatant 上。这里另建一份的话，
        # 界面会「扣了次数、附赠动作还剩着」，下一回合又能白用一次。
        economy = encounter.get(actor).economy
    economy = economy if economy is not None else ActionEconomy()
    ctx = _context(actor, locale, rng or SeededRng(seed), power, content,
                   encounter=encounter)
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
