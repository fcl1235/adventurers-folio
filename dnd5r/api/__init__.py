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
from ..kernel.errors import DndError, PluginError, RuleError
from ..kernel.events import Report
from ..kernel.rng import Rng, SeededRng
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.levels import ClassLevel, TotalLevel
from ..model.profile import ClassEntry, Profile, class_levels_of
from ..model.statblock import Abilities, Statblock
from ..rules.actioneconomy import ActionEconomy, ActionType
from ..rules.armor import Loadout, ac_inputs, loadout_for
from ..rules.build import (
    available_powers, build_actor, build_from_profile, eligible_forms_for,
    feat_defs, feat_picks, morph_class_of, owner_class_id, rebuild_actor,
    subclass_defs,
)
from ..rules.contributions import (
    facts_for, modifiers_for, passive_defenses, passive_modifiers,
    passive_proficiencies, power_channels, power_status, save_modifiers,
    skill_modifiers,
)
from ..rules.effects import EffectContext
from ..rules.health import hit_dice_average
from ..rules.morph import reasons_for
from ..rules.powers import Power, can_use
from ..rules.progression import MAX_TOTAL_LEVEL, proficiency_bonus, validate_total
from ..rules.resolver import RefContext, Resolver, crit_text
from ..rules.spellcasting import (
    casting_summary, check_spell_picks, spell_detail, spell_options,
)
from ..rules.feats import choice_prompt, pick_key, prereq_report
from ..rules.scores import bonus_totals, merge_bonuses, score_bonuses
from ..rules.weapons import profiles_for
from ..rules.powers import use_power as _use_power
from ..session import LongRest, NewTurn, Regain, Session, ShortRest, TakeDamage, UsePower

VERSION = "0.3.0"

ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")

# 选单里的分组顺序：起源 → 通用 → 战斗风格 → 传奇恩惠
FEAT_KIND_ORDER = ("origin", "general", "fighting_style", "epic_boon")


# --- 内容 -------------------------------------------------------------
def load_content(root: str = "plugins") -> ContentBundle:
    """加载插件目录。坏的插件只进 errors，不抛出。"""
    return load_all(root)


def content_summary(bundle: ContentBundle, locale: str = "zh") -> dict:
    stats = bundle.stats()
    stats["class_names"] = sorted(item.name.get(locale) for item in bundle.classes.values())
    stats["plugins"] = [manifest.id for manifest in bundle.manifests]
    return stats


def spell_catalog(
    bundle: ContentBundle,
    class_id: str | None = None,
    level: int | None = None,
    locale: str = "zh",
) -> dict:
    """法术目录（可按职业与环级过滤）。给界面出选择列表用。"""
    allowed = set(bundle.spell_list(class_id)) if class_id else None
    rows = [
        spell for spell in bundle.spells.values()
        if (level is None or int(spell.level) == int(level))
        and (allowed is None or spell.id in allowed)
    ]
    rows.sort(key=lambda item: (int(item.level), item.id))
    return {
        "class": class_id,
        "level": level,
        "count": len(rows),
        "spells": [
            {"id": spell.id, "name": spell.name.get(locale), "level": int(spell.level),
             "school": spell.school, "ritual": spell.ritual,
             "concentration": spell.concentration,
             "classes": list(bundle.classes_for_spell(spell.id))}
            for spell in rows
        ],
    }


def spell_info(bundle: ContentBundle, spell_id: str, locale: str = "zh") -> dict:
    """单条法术的完整展示数据（含基础环的伤害骰式）。"""
    return spell_detail(bundle, spell_id, locale)


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
SAVE_VERSION = 1


def save_character(actor: Actor, locale: str = "zh") -> dict:
    """把角色写成可存盘的字典。**只写事实**，派生值一律不写（C5）。

    派生值进档看着省事，读回来就是一包会过期的数字：内容一升级（比如某条
    专长补了 +1），存档里的旧 AC 还在，界面到底信谁？
    """
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案，无法存档")
    name = actor.statblock.name
    root = actor.root()
    return {
        "version": SAVE_VERSION,
        "id": actor.id,
        "kind": actor.kind.value,
        "name": {"zh": name.zh, "en": name.en},
        "locale": locale,
        "profile": profile.to_dict(),
        "hp": {"current": int(root.hp.current), "temp": int(root.hp.temp)},
        # 已用数按池 id 记：内容改了池容量也不会读到负数（读档时夹一次）
        "resources": {pool_id: int(pool.used)
                      for pool_id, pool in root.resources.pools.items()},
    }


def load_character(
    content: ContentBundle,
    data: Mapping[str, Any],
    locale: str = "zh",
) -> Actor:
    """从存档重建角色。存档里缺原始属性（旧档）时明确报错，不猜。"""
    version = int(data.get("version") or 0)
    if version > SAVE_VERSION:
        raise RuleError("存档版本 %d 比程序新（支持到 %d），请升级程序"
                        % (version, SAVE_VERSION))
    raw = data.get("profile")
    if not isinstance(raw, Mapping):
        raise RuleError("存档缺少 profile")
    profile = Profile.from_dict(raw)
    name = data.get("name") or {}
    actor = build_from_profile(
        content, profile,
        str(name.get("zh") or "无名角色"),
        str(name.get("en") or "Unnamed"),
        actor_id=str(data.get("id") or "pc.hero"),
    )
    hp = data.get("hp") or {}
    if "current" in hp:
        actor.hp.current = max(0, min(int(hp["current"]), actor.hp.maximum))
    actor.hp.temp = max(0, int(hp.get("temp") or 0))
    for pool_id, used in (data.get("resources") or {}).items():
        if not actor.resources.has(pool_id):
            continue                      # 内容升级后池没了：忽略，别让读档失败
        pool = actor.resources.pools[pool_id]
        amount = min(int(used), pool.capacity)
        if amount > 0:
            pool.spend(amount)
    return actor


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
) -> Actor:
    """按内容建角色：HP 上限、资源池、豁免熟练全部从 ClassDef 出来。

    `choices` 是专长的「选完还要选什么」：键 `<专长 id>.<选择项 id>`，
    值是被选中的项（如 `{"dnd2024.feat.ability_score_improvement.boost": ["dex", "dex"]}`）。
    同一专长登记两次时，第二次起键写成 `<专长 id>#1.<选择项 id>`。

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
    if morphed:
        bonus = {}
    else:
        bonus = bonus_totals(merge_bonuses(
            score_bonuses(available_powers(content, actor)),
            feat_picks(content, actor.profile).score,
        ))
    return {
        key: {
            "score": top.statblock.abilities.score(key),
            "mod": top.statblock.abilities.mod(key),
            "bonus": int(bonus.get(key, 0)),
        }
        for key in ABILITY_KEYS
    }


def _feat_rows(content: ContentBundle, actor: Actor, locale: str = "zh") -> list[dict]:
    """专长块：每条专长 + 它还没选完的选择项。"""
    profile = actor.profile
    picks = feat_picks(content, profile)
    tokens = set(profile.proficiencies if profile else ())
    tokens |= passive_proficiencies(content, actor)
    rows: list[dict] = []
    for feat in feat_defs(content, profile):
        choices = []
        for choice in feat.choices:
            key = "%s.%s" % (feat.id, choice.id)
            picked = list(profile.choices.get(key, ())) if profile else []
            options = list(choice.options)
            if choice.kind == "expertise":
                # 专精只能选已有熟练的技能 —— Profile 会校验，但选单不该给出非法项
                options = [item for item in options if "skill.%s" % item in tokens]
            choices.append({
                "id": choice.id,
                "key": key,
                "label": choice_prompt(feat, choice, locale).get(locale),
                "picked": picked,
                "remaining": choice.count - len(picked),
                "count": choice.count,
                "options": options,
            })
        rows.append({
            "id": feat.id,
            "name": feat.name.get(locale),
            "kind": feat.kind,
            "level": int(feat.level),
            "status": _feat_status(feat),
            "text": feat.text.get(locale),
            "choices": choices,
            "pending": any(row["key"] in picks.pending for row in choices),
        })
    return rows


def _feat_status(feat) -> str:
    """专长的诚实标记。与能力同一套词汇（counted/active/manual/text）。

    有选择项的专长一定算数（选完就落属性/熟练/抗性），所以直接算 counted；
    剩下的看它挂的能力里有没有真被消费的通道。
    """
    if feat.choices:
        return "counted"
    statuses = {power_status(power) for power in feat.powers}
    for level in ("counted", "active", "manual"):
        if level in statuses:
            return level
    return "text"


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

    # 熟练令牌：档案里的 + 被动能力给的（如「技能全能」）。下面多处要用，先算一次。
    skill_tokens = set(profile.proficiencies if profile else ())
    skill_tokens |= passive_proficiencies(content, actor)
    expertise_tokens = set(profile.expertise if profile else ())

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
    # 技能：属性检定 + 熟练（+ 专精）。熟练 token 与内容里的 `skill.<key>` 必须一致，
    # 所以这里从**内容**的技能表出发去查 token，而不是反过来枚举令牌。
    skill_rows = []
    for skill in sorted(content.skills.values(), key=lambda item: (item.ability, item.key)):
        token = "skill.%s" % skill.key
        proficient = token in skill_tokens
        roll = resolver.ability_check(
            top, skill.ability, proficient=proficient,
            expertise=token in expertise_tokens,
            modifiers=skill_modifiers(mods, skill.key),
        )
        skill_rows.append({
            "id": skill.id, "key": skill.key, "ability": skill.ability,
            "name": skill.name.get(locale),
            "total": roll.total, "detail": roll.describe(),
            "proficient": proficient, "expertise": token in expertise_tokens,
        })
    # 攻击：默认用最高的力量／敏捷，只看是否熟练（武器数据在 P5c）
    attack_ability = "str" if top.statblock.abilities.mod("str") >= top.statblock.abilities.mod("dex") else "dex"
    attack = resolver.attack_bonus(top, attack_ability, proficient=True,
                                   modifiers=modifiers_for(mods, "attack"))

    attacks_per_action = 1
    for class_def in _class_defs(actor, content):
        level = profile.class_level(class_def.id) if profile else ClassLevel(1)
        attacks_per_action = max(attacks_per_action, class_def.total_attacks(level))

    tokens = skill_tokens          # 上面算过一次，别在这里重算（重复来源会漂）
    ranged_bonus = 0 if morphed else resolver.bonus(
        modifiers_for(mods, "attack.ranged")).total
    attack_profiles = profiles_for(actor, content.weapons, top.statblock.abilities,
                                   resolver.ctx.prof_bonus, tokens,
                                   ranged_bonus=ranged_bonus)
    attacks = [item.to_dict(locale) for item in attack_profiles]
    crit = resolver.crit_range(top, modifiers_for(mods, "attack.crit_min"))
    senses = {}
    for mode in ("darkvision", "blindsight", "tremorsense", "truesight"):
        total = resolver.sense(top, mode, () if morphed else modifiers_for(mods, "sense.%s" % mode)).total
        if total > 0:
            senses[mode] = total
    feat_resist, feat_immune = passive_defenses(content, actor)
    resistances = sorted(feat_resist | set(profile.resistances if profile else ()))

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
            # 诚实标记：这条能力到底进没进数值。没进就不许让玩家以为算过了。
            "status": power_status(power),
            "channels": list(power_channels(power)),
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
        "senses": senses,
        "resistances": resistances,
        "immunities": sorted(feat_immune),
        "abilities": _ability_rows(actor, content, morphed),
        "gear": loadout.to_dict(locale),
        "saves": {key: {"total": value.total, "detail": value.describe(),
                        "proficient": key in saves_prof}
                  for key, value in saves.items()},
        "skills": skill_rows,
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
             "kind": pool.kind.value, "refresh": pool.refresh.value,
             # 显示名来自内容（「回气」「狂暴」），没有就退回 id —— 界面不该自己编名字
             "label": pool.label.get(locale) if pool.label else pool.id}
            for pool in root.resources.pools.values()
            if pool.kind.value != "dice"
        ],
        "powers": powers,
    }
    if profile:
        # 施法块：每个施法职业一块（兼职各算各的 DC 与法位）
        casting = []
        for entry in profile.classes:
            class_def = content.classes.get(entry.class_id)
            if class_def is None or class_def.caster is not None and class_def.caster.value == "none":
                continue
            casting.append(casting_summary(content, actor, entry.class_id,
                                           entry.class_level, resolver, locale))
        sheet["spellcasting"] = casting
        sheet["feats"] = _feat_rows(content, actor, locale)
        sheet["choices_needed"] = list(feat_picks(content, profile).pending)
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
    "create_actor", "new_character", "resolver_for", "build_from_profile",
    "set_feat_choice", "save_character", "load_character", "SAVE_VERSION",
    "character_sheet", "actor_view",
    "find_power", "use_power", "plugin_summary",
    "eligible_forms_for", "morph_class_of", "form_options",
    # 前端要 catch 的是「调用失败」这件事，所以异常类型属于 api 的契约 ——
    # 不让 apps 去 import kernel.errors（C3），否则拦错误都得越界。
    "DndError", "RuleError", "PluginError",
    "ActionEconomy", "ActionType",
    "Session", "UsePower", "ShortRest", "LongRest", "NewTurn", "TakeDamage", "Regain",
]
