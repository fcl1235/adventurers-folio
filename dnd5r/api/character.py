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
from ..rules.feats import ASI_KINDS, feat_ledger, pick_key, prereq_report
from ..rules.powers import Power, use_power as _use_power
from ..rules.progression import MAX_TOTAL_LEVEL, validate_total
from ..rules.spellcasting import casting_summary, check_spell_picks
from ..rules.text import join_list, tr
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


def add_feat(
    actor: Actor,
    content: ContentBundle,
    feat_id: str,
    picks: Mapping[str, Sequence[str]] | None = None,
    locale: str = "zh",
) -> Actor:
    """用一次**属性提升名额**加一条专长，返回重建后的角色。

    为什么需要这个入口：以前只有 `new_character(feats=...)` 能登记专长，
    于是 4 级以后再也拿不到「+2 或换一个专长」—— 职业 YAML 里那条特性
    只是规则文字，升到 4 级什么也不会发生。

    三件事都在这里判，界面一条都不用抄：

      * 名额够不够（`feat_ledger`，各职业按自己的等级算）；
      * 这条专长**本身**能不能选（`feat_options` 的 `selectable`，前提已判过）；
      * 选择项（属性提升的 `boost`）**能在同一步一起写进去** —— 给了 `picks`
        就是一次到位；不给则留下「待选」，由专长页的选择项区域补完。
        分两步去凑的实现最怕半路存档，那种角色看起来像坏了。

    `picks` 的键是**选择项 id**（不是完整键）：`{"boost": ["dex", "dex"]}`。
    重复选取时序号由函数自己算（第几次登记就用第几格），调用方别自己拼 `#1`。
    """
    profile = actor.profile
    if profile is None:
        raise RuleError(tr("角色没有职业档案，加不了专长", locale))
    feat = content.feats.get(feat_id)
    if feat is None:
        raise RuleError(tr("没有这个专长：%s", locale) % feat_id)
    if feat.kind not in ASI_KINDS:
        # 起源专长由背景给、战斗风格由职业特性给。允许在这里加，
        # 就会养出「1 级角色手上有三个起源专长」这种查不出来的错。
        raise RuleError(tr("「%s」不是属性提升可以选的专长（%s 类由背景或职业特性给）",
                           locale) % (feat.name.get(locale), feat.kind))
    row = next((item for item in feat_options(content, actor, locale=locale)["feats"]
                if item["id"] == feat_id), None)
    if row is None:
        raise RuleError(tr("没有这个专长：%s", locale) % feat_id)
    if not row["selectable"]:
        raise RuleError(tr("现在不能选「%s」：%s", locale)
                        % (feat.name.get(locale), join_list(row["blocked"], locale)))

    ledger = feat_ledger(content, profile)
    if ledger["pending"] <= 0:
        raise RuleError(tr("还没有可用的属性提升名额（%s 级各一次；已用 %d / 共 %d）",
                           locale) % (ledger["levels"],
                                      ledger["used"], ledger["granted"]))

    index = profile.feats.count(feat_id)          # 第几次登记（属性提升会重复选）
    updated = profile.with_feats(profile.feats + (feat_id,))
    if picks:
        by_choice = {str(key): tuple(str(item) for item in value)
                     for key, value in picks.items()}
        unknown = set(by_choice) - {item.id for item in feat.choices}
        if unknown:
            raise RuleError(tr("「%s」没有这些选择项：%s", locale)
                            % (feat.name.get(locale), join_list(sorted(unknown), locale)))
        merged = dict(profile.choices)
        for choice in feat.choices:
            if choice.id in by_choice:
                merged[pick_key(feat_id, choice.id, index)] = by_choice[choice.id]
        updated = updated.with_choices(merged)
    return rebuild_actor(content, actor, profile=updated)


def remove_feat(
    actor: Actor,
    content: ContentBundle,
    feat_id: str,
    locale: str = "zh",
) -> Actor:
    """去掉一条**属性提升**专长（登记了两次就去掉最后那次）。

    只去最后一条：前面的序号不动，`#1`、`#2` 这些选择项键才不会集体错位。
    选择项一起清掉 —— 留着的话下次加同一条专长会直接吃上旧选择，
    界面上表现为「刚加的专长属性已经加过了」。
    """
    profile = actor.profile
    if profile is None:
        raise RuleError(tr("角色没有职业档案，去不了专长", locale))
    feat = content.feats.get(feat_id)
    if feat is None:
        raise RuleError(tr("没有这个专长：%s", locale) % feat_id)
    if feat_id not in profile.feats:
        raise RuleError(tr("角色没有这个专长：%s", locale) % feat.name.get(locale))
    if feat.kind not in ASI_KINDS:
        raise RuleError(tr("「%s」由背景或职业特性给，不能在这里去掉", locale)
                        % feat.name.get(locale))
    index = profile.feats.count(feat_id) - 1
    kept = profile.feats[:index] + profile.feats[index + 1:]
    choices = {key: value for key, value in profile.choices.items()
               if key not in {pick_key(feat_id, choice.id, index)
                              for choice in feat.choices}}
    if index == 0:
        # 第一次的键还有 `#0` 这种写法（`picks_for` 认它），一并清掉
        choices = {key: value for key, value in choices.items()
                   if key not in {"%s#0.%s" % (feat_id, choice.id)
                                  for choice in feat.choices}}
    updated = profile.with_feats(kept).with_choices(choices)
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
    extra_languages: Sequence[str] = (),
    starting_pack: str | None = None,
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

    `starting_pack` 是起始装备（2024 的 A/B 选项）：`None` 表示不给，
    `""` 表示这个职业的默认那一组，也可以给具体 id（`dnd2024.package.fighter.b`）。
    **默认不给**：底层调用方（对账、单测、造 NPC）不该因为内容里多了一组装备
    就换来不同的 AC；建卡向导那条路会显式传 `""`。
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
        # 语言按 **key** 传（`elvish`）；通用语也在里面 —— 规则层不知道哪个是通用语
        extra_languages=tuple(extra_languages),
        starting_pack=starting_pack,
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
