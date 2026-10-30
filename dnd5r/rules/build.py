# -*- coding: utf-8 -*-
"""建角色：把内容定义 + 玩家选择落成一个 Actor。

这里只做「事实的拼装」：职业等级、属性、熟练、资源池、HP 上限。
派生值（AC、豁免、攻击）一律不写进 Actor，交给 Resolver 现算（C5）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from ..content import (
    ClassDef, ContentBundle, FeatDef, SubclassDef, powers_at_level,
)
from ..kernel.errors import RuleError
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.death import DeathSaves
from ..model.inventory import Inventory
from ..model.levels import ClassLevel, TotalLevel, as_class_level
from ..model.profile import ClassEntry, Profile
from ..model.resources import Pool, PoolKind, Refresh
from ..model.statblock import ABILITY_KEYS, Abilities, Statblock
from .feats import check_feat_choices, collect_picks, feat_spells, hard_problems, picks_for
from .health import hit_dice_pool, hit_points_max, multiclass_hit_points
from .progression import MAX_TOTAL_LEVEL, effective_caster_level, slots_from_table
from .modifiers import resolve as resolve_modifiers
from .morph import CrAxis, eligible_forms
from .powers import Power
from .progression import proficiency_bonus
from .spellcasting import check_spell_picks
from .scores import apply_score_bonuses, merge_bonuses, score_bonuses


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


def feat_defs(bundle: ContentBundle, profile: Profile | None) -> tuple[FeatDef, ...]:
    """档案里登记的专长（缺插件时跳过，理由同子职）。"""
    if profile is None:
        return ()
    return tuple(bundle.feats[item] for item in profile.feats if item in bundle.feats)


def feat_picks(bundle: ContentBundle, profile: Profile | None, locale: str = "zh"):
    """档案里专长的选择结果。**派生值的唯一入口** —— 别在别处重算一次。"""
    return collect_picks(feat_defs(bundle, profile), profile.choices if profile else {}, locale)


def feat_spell_grants(bundle: ContentBundle, profile: Profile | None,
                      locale: str = "zh"):
    """档案里**专长授予的法术**：谁给的、用哪个属性施放、第几次登记。

    建资源池与战斗结算共用这一份 —— 一边按「迷踪步有一次免费施放」建池，
    另一边按「迷踪步是妖精触碰给的、用魅力施放」算 DC，两处各算一遍必然分叉。
    """
    feats = feat_defs(bundle, profile)
    if not feats:
        return ()
    repeats = {feat.id: profile.feats.count(feat.id) for feat in feats}
    return feat_spells(feats, profile.choices if profile else {}, repeats, locale)


def _check_feats(
    bundle: ContentBundle,
    feats: tuple[str, ...],
    total: TotalLevel,
    class_ids: tuple[str, ...],
    scores: Mapping[str, int],
) -> tuple[FeatDef, ...]:
    """选取前提 —— 硬前提在这里拒绝，软前提（属性）留给选单提示。

    「可重复选取」由内容声明（`repeatable: true`，如属性提升）：只有这类专长
    允许登记两次。别的专长出现两次是数据错误，不是「玩家贪心」。
    """
    seen: dict[str, int] = {}
    for feat_id in feats:
        seen[feat_id] = seen.get(feat_id, 0) + 1
    for feat_id, count in sorted(seen.items()):
        if count > 1 and not bundle.feat(feat_id).repeatable:
            raise RuleError("专长「%s」不可重复选取，却登记了 %d 次"
                            % (bundle.feat(feat_id).name.get("zh"), count))
    feats = tuple(dict.fromkeys(feats))      # 重复登记只建一次特性，加值按次数另算
    found: list[FeatDef] = []
    for feat_id in feats:
        feat = bundle.feat(feat_id)
        problems = hard_problems(feat, int(total), class_ids)
        if problems:
            raise RuleError("专长「%s」不满足前提：%s"
                            % (feat.name.get("zh"), "；".join(problems)))
        found.append(feat)
    return tuple(found)


def _per_spell_pools(
    bundle: ContentBundle,
    resource,
    feat: FeatDef,
    copy: int,
    choices: Mapping[str, tuple[str, ...]],
    ref: Mapping[str, Any],
) -> list[Pool]:
    """把「每道法术各一次」展开成**每道法术一个池**。

    只有**有环级的**法术建池：戏法本来就能无限施放，给它一个 1 次的池
    等于凭空加了个限制。选择项还没选好时一道法术都没有 —— 也就不建池，
    界面那边显示的是「这条专长还差一项没选」，不是「你有 1 次用不掉」。

    池标签用**法术名**而不是内容里的通用名：专长页上并列两行「免费施放次数」
    却都是「妖精触碰的免费施法」，玩家分不出哪一行是迷踪步。
    """
    level = ClassLevel(int(ref.get("total_level") or 1))
    base = resource.id if copy == 0 else "%s_%d" % (resource.id, copy + 1)
    pools: list[Pool] = []
    for spell_id in picks_for(feat, choices, index=copy).spells:
        spell = bundle.spells.get(spell_id)
        if spell is None or int(spell.level) < 1:
            continue
        built = resource.build(level, ref)
        pools.append(replace(
            built,
            id="%s.%s" % (base, spell_id.rsplit(".", 1)[-1]),
            label=spell.name,
            spell=spell.id,
            source=feat.id,
        ))
    return pools


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
    extra_expertise: tuple[str, ...] = (),
    extra_resistances: tuple[str, ...] = (),
    subclass: str | None = None,
    feats: tuple[str, ...] = (),
    choices: Mapping[str, tuple[str, ...]] | None = None,
    cantrips: Mapping[str, tuple[str, ...]] | None = None,
    prepared: Mapping[str, tuple[str, ...]] | None = None,
    extra_classes: "Sequence[tuple[str, int]]" = (),
    extra_subclasses: "Sequence[str]" = (),
) -> Actor:
    """建角色（支持兼职）。事实的拼装：职业等级、属性、熟练、资源池、HP 上限。

    `class_id/class_level` 是**起始职业**（豁免熟练只来自它，§12.3）；
    `extra_classes` 是 (职业, 等级) 列表，按传入顺序进档案 —— 顺序决定
    HP 分段（只有起始职业的 1 级取满骰）。

    兼职的三条硬规则在这里落地：
      1. **前置属性**：每个非起始职业都要过 `multiclass.yaml` 的 prereq
         （按加值后的当前属性判 —— 升级历史不进档案，这是写明的近似）。
      2. **熟练**：起始职业给整套起始熟练；兼职职业只给 grants 那一份，
         永远不给豁免熟练。
      3. **法术位**：≥2 个非契约施法职业查合并表（caster-progression.yaml），
         位池不属于任何职业（花的时候按环级挑最低）；契约位永远独立。

    专长与子职一样是**玩家选择**：`feats` 是内容 id，`choices` 是「选了还要选什么」。
    选不完不报错，留在 `feat_picks().pending` 给界面当待办；选错当场抛 RuleError。
    """
    class_def: ClassDef = bundle.class_def(class_id)
    level = as_class_level(class_level)
    # 兼职段：去重校验 + 全部职业定义一次取齐
    extras: list[tuple[ClassDef, ClassLevel]] = []
    seen = {class_id}
    for extra_id, extra_level in extra_classes:
        if extra_id in seen:
            raise RuleError("职业 %s 登记了两次" % extra_id)
        seen.add(extra_id)
        extras.append((bundle.class_def(extra_id), as_class_level(int(extra_level))))

    all_defs: list[tuple[ClassDef, ClassLevel]] = [(class_def, level)] + extras
    total_preview = sum(int(lv) for _def, lv in all_defs)
    if total_preview > MAX_TOTAL_LEVEL:
        raise RuleError("总等级超过上限 %d：%d（单职业最多 20，兼职共享这 20 级）"
                        % (MAX_TOTAL_LEVEL, total_preview))

    # 子职：起始职业用 `subclass`，其余用 `extra_subclasses`（按归属职业各查各的）
    subclass_map: dict[str, str] = {}
    for sub_id in [subclass] + [str(item) for item in extra_subclasses]:
        if not sub_id:
            continue
        sub = bundle.subclass(sub_id)
        if sub.class_id not in {def_.id for def_, _lv in all_defs}:
            raise RuleError("子职 %s 不属于这个角色的职业（它挂在 %s 上）"
                            % (sub.id, sub.class_id))
        subclass_map[sub.class_id] = sub.id

    # 属性加值通道：原始冠军 / 身心合一这类「属性值 +4」的能力在这里落地。
    # 必须在算 HP 之前：加值改了体质调整值，HP 上限跟着变，否则 20 级会少 40 点。
    def _powers_of(def_: ClassDef, lv: ClassLevel):
        merged = list(def_.powers)
        sub_id = subclass_map.get(def_.id)
        if sub_id is not None:
            sub = bundle.subclasses[sub_id]
            if int(lv) >= int(sub.unlock_level):
                merged.extend(sub.powers)
        return powers_at_level(tuple(merged), lv)

    powers = _powers_of(class_def, level)
    all_powers = tuple(powers)
    for def_, lv in extras:
        for power in _powers_of(def_, lv):
            if power not in all_powers:
                all_powers += (power,)
    # 专长：硬前提（等级/职业）不满足就拒绝；选择项先结算，属性加值要赶在 HP 之前
    picked_choices = dict(choices or {})
    chosen_feats = tuple(feats)
    # 专长前提看**总等级**（兼职也算）：19 级恩惠不会因为某个职业只有 3 级就拒绝
    total = TotalLevel(sum(int(lv) for _def, lv in all_defs))
    class_ids = tuple(def_.id for def_, _lv in all_defs)
    feat_defs_ = _check_feats(bundle, chosen_feats, total, class_ids, scores)
    feat_powers = tuple(p for feat in feat_defs_ for p in feat.powers)
    all_powers = all_powers + tuple(p for p in feat_powers if p not in all_powers)
    # 可重复选取的专长（属性提升）按登记次数结算加值：登记两次就是两轮选择
    repeats = {feat.id: chosen_feats.count(feat.id) for feat in feat_defs_}
    picks = collect_picks(
        [feat for feat in feat_defs_ for _ in range(repeats.get(feat.id, 1))],
        picked_choices,
    )
    problems = check_feat_choices(bundle, feat_defs_, picked_choices, repeats)
    if problems:
        raise RuleError("专长选择有问题：" + "；".join(problems))
    bonuses = merge_bonuses(score_bonuses(all_powers), picks.score)
    abilities = apply_score_bonuses(Abilities.of(**dict(scores)), bonuses)

    # 兼职前置：按加值后的当前属性判（§12.4 的口径写在 multiclass.yaml 头部）
    for def_, _lv in extras:
        entry = bundle.multiclass.get(def_.id)
        if entry is None:
            raise RuleError("内容没有 %s 的兼职条目（multiclass.yaml）" % def_.id)
        blocked = entry.prereq_ok(abilities)
        if blocked:
            raise RuleError("进入 %s 的属性前提不满足：%s"
                            % (def_.id, "；".join(blocked)))

    con_mod = abilities.mod("con")
    name = Text.of(name_zh, name_en)
    statblock = Statblock(name=name, abilities=abilities)
    ref = _ref_map(abilities, level, total, proficiency_bonus(total),
                   statblock.speeds)
    # HP：兼职分段（起始职业 1 级满骰，其余全按固定值），单职业走原公式
    hp_max = _hp_max_of(all_defs, con_mod, all_powers, ref)

    saves = tuple("save.%s" % key for key in class_def.saves)   # 只来自起始职业
    grant_tokens: list[str] = []
    for def_, _lv in extras:
        grant_tokens.extend(bundle.multiclass[def_.id].grants)
    # 法术选择（戏法 / 准备法术）是玩家选择，与专长选择同一层：
    # 建角色时校验配额与环级上限，选错当场炸，选不完不算错（界面显示剩余名额）。
    spell_cantrips = {key: tuple(value) for key, value in (cantrips or {}).items()}
    spell_prepared = {key: tuple(value) for key, value in (prepared or {}).items()}
    spell_problems = check_spell_picks(
        bundle, {def_.id: lv for def_, lv in all_defs}, spell_cantrips, spell_prepared)
    if spell_problems:
        raise RuleError("法术选择有问题：" + "；".join(spell_problems))
    profile = Profile(
        classes=tuple(ClassEntry.make(def_.id, lv) for def_, lv in all_defs),
        subclasses=tuple(subclass_map.values()),
        proficiencies=(frozenset(saves)
                       | frozenset(class_def.proficiencies)
                       | frozenset(grant_tokens)
                       | frozenset(extra_proficiencies)
                       | picks.proficiencies),
        expertise=picks.expertise | frozenset(extra_expertise),
        feats=chosen_feats,
        choices=picked_choices,
        resistances=picks.resistances | frozenset(extra_resistances),
        cantrips=spell_cantrips,
        prepared=spell_prepared,
        # 原始属性（加值之前）必须留在档案里：存档、重建、界面改专长都要靠它。
        base_scores={key: int(scores[key]) for key in ABILITY_KEYS},
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

    for def_, lv in all_defs:
        # 资源里的 class_level 引用按**所属职业**的等级求值（术法点 = 术士等级，
        # 不是主职业等级）。ref 是共享映射，这里按职业换档再传。
        class_ref = _ref_map(abilities, lv, total, proficiency_bonus(total),
                             statblock.speeds)
        for resource in def_.resources:
            pool = resource.build(lv, class_ref)
            if pool.capacity <= 0:
                continue  # 未解锁的资源不建池，避免界面上出现 0/0
            actor.resources.add(pool)
        # 子职自己的池（月光步「感知调整值次，至少 1 次」）。次数按**父职业等级**查表，
        # 池的 owner 是子职 —— 与专长的池同一个口径：owner 记「是哪个内容给的」。
        sub_id = subclass_map.get(def_.id)
        if sub_id is not None:
            sub = bundle.subclasses[sub_id]
            for resource in sub.resources_at(lv):
                pool = resource.build(lv, class_ref)
                if pool.capacity <= 0:
                    continue
                actor.resources.add(pool)
    # 专长给的池（「每长休一次免费施放」）。可重复专长按次数展开（魔法入门两次 = 两个池）。
    feat_copies: dict[str, int] = {}
    for feat in [item for item in feat_defs_
                 for _ in range(int(repeats.get(item.id, 1)))]:
        copy = feat_copies.get(feat.id, 0)
        feat_copies[feat.id] = copy + 1
        for resource in feat.resources:
            if resource.per_spell:
                for pool in _per_spell_pools(bundle, resource, feat, copy,
                                             picked_choices, ref):
                    actor.resources.add(pool)
                continue
            built = (resource if copy == 0
                     else replace(resource, id="%s_%d" % (resource.id, copy + 1)))
            pool = built.build(ClassLevel(int(total)), ref)
            if pool.capacity <= 0:
                continue
            actor.resources.add(pool)
    _build_slot_pools(bundle, actor, all_defs)
    for def_, lv in all_defs:
        actor.resources.add(hit_dice_pool(def_.id, def_.hit_die, lv))
    return actor


def _hp_max_of(
    all_defs: "list[tuple[ClassDef, ClassLevel]]",
    con_mod: int,
    all_powers,
    ref: Mapping[str, Any],
) -> int:
    """HP 上限：单职业走 `hit_points_max`，兼职走分段（health.multiclass_hit_points）。"""
    per_level = _hp_bonus(all_powers, "hp.per_level", ref)
    flat = _hp_bonus(all_powers, "hp.flat", ref)
    if len(all_defs) == 1:
        def_, lv = all_defs[0]
        return hit_points_max(def_.hit_die, con_mod, lv,
                              per_level_bonus=per_level, flat_bonus=flat)
    return multiclass_hit_points(
        [(def_.hit_die, lv) for def_, lv in all_defs],
        con_mod, per_level_bonus=per_level, flat_bonus=flat)


def _build_slot_pools(
    bundle: ContentBundle,
    actor: Actor,
    all_defs: "list[tuple[ClassDef, ClassLevel]]",
) -> None:
    """法术位池。三条路（§12.2）：

    * 契约（邪术师）：永远按自己的位表独立建池（短休恢复），不入合并表；
    * 只有一个非契约施法职业：按**它自己的**位表 —— 单职业行为与池 id 完全不变；
    * ≥2 个非契约施法职业：按合并表（caster-progression.yaml）建一套
      「不属于任何职业」的池 —— 花的时候只看环级（§14.24：位不认职业）。
    """
    pact_defs = [(def_, lv) for def_, lv in all_defs
                 if def_.caster is not None and def_.caster.value == "pact"]
    casters = [(def_, lv) for def_, lv in all_defs
               if def_.caster is not None
               and def_.caster.value in ("full", "half", "third")]
    for def_, lv in pact_defs:
        _add_class_slots(actor, def_, lv)
    if len(casters) == 1:
        def_, lv = casters[0]
        _add_class_slots(actor, def_, lv)
    elif len(casters) >= 2:
        if not bundle.caster_progression:
            raise RuleError("内容没有兼职合并位表（caster-progression.yaml）")
        effective = effective_caster_level(
            Profile(classes=tuple(ClassEntry.make(d.id, lv) for d, lv in casters)),
            {d.id: d.caster for d, _lv in casters},
        )[0]
        row = slots_from_table(effective, bundle.caster_progression)
        for slot_level, capacity in sorted(row.items()):
            actor.resources.add(Pool(
                id="engine.slot.spellcasting.%d" % slot_level,
                kind=PoolKind.SLOT, capacity=capacity,
                label=Text.of("%d 环法术位" % slot_level,
                              "Level %d Spell Slots" % slot_level),
                refresh=Refresh.LONG_REST,
            ))


def _add_class_slots(actor: Actor, def_: ClassDef, lv: ClassLevel) -> None:
    """按职业自己的位表建池（单职业与契约位的口径，池 id/owner 与 P5a 起一致）。"""
    for index_, capacity in enumerate(def_.slots_at(lv), start=1):
        if capacity <= 0:
            continue
        actor.resources.add(Pool(
            id="engine.slot.%s.%d" % (def_.id.split(".")[-1], index_),
            kind=PoolKind.SLOT, capacity=capacity,
            label=Text.of("%d 环法术位" % index_, "Level %d Spell Slots" % index_),
            owner_class=def_.id, refresh=def_.slot_refresh,
        ))


def build_from_profile(
    bundle: ContentBundle,
    profile: Profile,
    name_zh: str,
    name_en: str,
    actor_id: str = "pc.hero",
    kind: ActorKind = ActorKind.PC,
) -> Actor:
    """按**档案**重建角色（读档、改专长、洗点都用它）。

    为什么必须走 `build_actor` 而不是「改一改现有 Actor」：属性加值、HP 上限、
    法位表、资源池全是建角色时一次算定的，散着改必然漏一处（改完体质，
    HP 上限还是旧的）。所以唯一正确的做法是整只重建。

    档案里有一类东西**推导不出来**：玩家单独挑的熟练、专精、抗性（`Profile`
    里那些不由内容决定的项）。第一遍先按内容算，再把这些差值补回去 ——
    循环最多两轮，因为补进去的项本身不会再生出新的差值。
    """
    # 兼职重建：第一个职业是起始职业，其余进 extra_classes；子职按归属职业分发。
    entry = profile.classes[0]
    scores = {key: profile.base_score(key) for key in ABILITY_KEYS}
    owner_ids = {item.class_id for item in profile.classes}
    primary_subclass = next(
        (sub for sub in profile.subclasses
         if sub in bundle.subclasses
         and bundle.subclasses[sub].class_id == entry.class_id),
        None,
    )
    extra_subclasses = tuple(
        sub for sub in profile.subclasses
        if sub in bundle.subclasses
        and bundle.subclasses[sub].class_id != entry.class_id
    )

    extra_prof: tuple[str, ...] = ()
    extra_exp: tuple[str, ...] = ()
    extra_res: tuple[str, ...] = ()
    actor: Actor | None = None
    for _ in range(3):
        extras = tuple((item.class_id, int(item.class_level))
                       for item in profile.classes[1:])
        actor = build_actor(
            bundle, entry.class_id, int(entry.class_level), scores,
            name_zh, name_en, actor_id=actor_id, kind=kind,
            extra_proficiencies=extra_prof, extra_expertise=extra_exp,
            extra_resistances=extra_res,
            subclass=primary_subclass, feats=profile.feats, choices=profile.choices,
            cantrips=profile.cantrips, prepared=profile.prepared,
            extra_classes=extras, extra_subclasses=extra_subclasses,
        )
        assert actor.profile is not None
        got = actor.profile
        missing_prof = tuple(sorted(set(profile.proficiencies) - set(got.proficiencies)))
        missing_exp = tuple(sorted(set(profile.expertise) - set(got.expertise)))
        missing_res = tuple(sorted(set(profile.resistances) - set(got.resistances)))
        if not (missing_prof or missing_exp or missing_res):
            return actor
        extra_prof = tuple(sorted(set(extra_prof) | set(missing_prof)))
        extra_exp = tuple(sorted(set(extra_exp) | set(missing_exp)))
        extra_res = tuple(sorted(set(extra_res) | set(missing_res)))
    # 补了两轮还差，说明差值在自我增殖（数据有问题），不能带着错往下走
    raise RuleError("按档案重建时熟练/专精/抗性无法收敛，档案可能有矛盾项")


def rebuild_actor(
    bundle: ContentBundle,
    actor: Actor,
    profile: Profile | None = None,
) -> Actor:
    """重建并**保住运行时状态**：当前 HP、临时 HP、资源的已用数、背包与装备。

    界面改一个专长就得重建（属性加值变了），但玩家不该因此回满血、
    或者把用掉的狂暴次数吐回来 —— 那是两件不同的事。

    **装备也必须搬**：AC 是每次取卡时从 `inventory.equipped` 现读的
    （`rules/armor.loadout_for`），不搬就等于「改一次力量，护甲自己脱了」。
    实测过：穿锁甲 + 盾 AC 18，改完 str 回到 12。

    `profile` 是「还没写进 actor 的档案」：先在一份新档案上重建，成功了再换掉旧的。
    这样校验失败时 actor 一个字段都没动过。
    """
    profile = profile if profile is not None else actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案，无法重建")
    name = actor.statblock.name
    fresh = build_from_profile(bundle, profile, name.zh, name.en,
                               actor_id=actor.id, kind=actor.kind)
    old_hp = actor.root().hp
    fresh.hp.current = max(0, min(old_hp.current, fresh.hp.maximum))
    fresh.hp.temp = old_hp.temp
    for pool_id, pool in actor.root().resources.pools.items():
        if not fresh.resources.has(pool_id):
            continue
        used = pool.capacity - pool.available
        if used > 0:
            fresh.resources.pools[pool_id].spend(used)
    # 深拷贝而不是共享：调用方可能还留着旧 actor，别名会让「改一份、两份都变」。
    # 走 to_dict/from_dict 而不是 copy.deepcopy，顺便验证背包序列化是完整的。
    fresh.inventory = Inventory.from_dict(actor.root().inventory.to_dict())
    fresh.conditions = actor.conditions
    fresh.effects = list(actor.effects)
    fresh.display_name = actor.display_name
    # 力竭与濒死记分同样是运行时事实：改个专长不该把「力竭 2 级」抹掉，
    # 也不该让一个只剩两次死亡豁免失败的角色复活。
    fresh.exhaustion = int(actor.root().exhaustion)
    fresh.death_saves = DeathSaves.from_dict(actor.root().death_saves.to_dict())
    return fresh


def class_level_of(actor: Actor, class_id: str) -> ClassLevel:
    if actor.profile is None:
        raise RuleError("角色没有职业档案")
    return actor.profile.class_level(class_id)


def available_powers(bundle: ContentBundle, actor: Actor):
    """这个角色当前解锁的全部能力（按钮 + 被动），**含子职特性**。

    走 `powers_at` 而不是 `PowerBook.for_class`：前者会按等级把 patch 叠上去
    （18 级野兽施法解除变形施法禁令），后者是未叠层的原版。

    职业与子职的能力**先合并再叠层**：月环 3 级的「圆月形态」改写的是
    德鲁伊的荒野变形，两个列表分开叠层时那条 patch 永远落不到目标上。
    子职特性仍按**父职业**等级判定（`unlock_level` 先挡一道）。
    """
    if actor.profile is None:
        return ()
    found = []
    for entry in actor.profile.classes:
        class_def = bundle.classes.get(entry.class_id)
        if class_def is None:
            continue
        merged = list(class_def.powers)
        for sub in subclass_defs(bundle, actor.profile):
            if sub.class_id == entry.class_id and int(entry.class_level) >= int(sub.unlock_level):
                merged.extend(sub.powers)
        found.extend(powers_at_level(tuple(merged), entry.class_level))
    # 专长没有等级门槛（等级是**选取前提**，已在建角色时判过），全部生效
    for feat in feat_defs(bundle, actor.profile):
        found.extend(feat.powers)
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
    axis = morph_axis_for(actor, bundle, class_def)
    if axis is None:
        return []
    return eligible_forms(bundle.forms.values(), axis, entry.class_level)


def morph_axis_for(actor: Actor, bundle: ContentBundle, class_def=None):
    """这个角色**实际生效**的 CR 轴。

    默认取职业轴；子职改写变形（月环「圆月形态」：CR = 职业等级 ÷ 3）时，
    改写后的 morph 效果里带着新的阈值表，两处必须是同一个来源 ——
    否则界面上能选的形态与结算时能变的形态会不一致。
    游泳/飞行解禁仍取职业轴：那两条不是子职能改的。
    """
    if actor.profile is None:
        return None
    if class_def is None:
        found = morph_class_of(actor, bundle)
        if found is None:
            return None
        class_def = found[1]
    effect = None
    for power in available_powers(bundle, actor):
        for item in power.effects:
            if getattr(item, "op", "") == "morph":
                effect = item
    if effect is None:
        return None                     # 1 级德鲁伊还没有荒野变形
    steps = getattr(effect, "cr_by_level", None)
    base = class_def.morph
    if steps:
        return (replace(base, steps=dict(steps)) if base is not None
                else CrAxis(steps=dict(steps)))
    return base
