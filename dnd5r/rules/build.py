# -*- coding: utf-8 -*-
"""建角色：把内容定义 + 玩家选择落成一个 Actor。

这里只做「事实的拼装」：职业等级、属性、熟练、资源池、HP 上限。
派生值（AC、豁免、攻击）一律不写进 Actor，交给 Resolver 现算（C5）。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from ..content import ClassDef, ContentBundle, FeatDef, SubclassDef
from ..kernel.errors import RuleError
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.inventory import Inventory
from ..model.levels import ClassLevel, TotalLevel, as_class_level
from ..model.profile import ClassEntry, Profile
from ..model.resources import Pool, PoolKind, Refresh
from ..model.statblock import ABILITY_KEYS, Abilities, Statblock
from .feats import check_feat_choices, collect_picks, feat_spells, hard_problems, picks_for
from .health import hit_dice_pool, hit_points_max
from .modifiers import resolve as resolve_modifiers
from .morph import eligible_forms
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
) -> Actor:
    """建一个单职业角色。兼职在 P3 的 Session 里做（要合并位表与熟练来源）。

    专长与子职一样是**玩家选择**：`feats` 是内容 id，`choices` 是「选了还要选什么」
    （`<专长 id>.<选择项 id>` → 选中的项）。选不完不报错，留在 `feat_picks().pending` 里
    给界面当待办；选错了当场抛 RuleError。
    """
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
    # 专长：硬前提（等级/职业）不满足就拒绝；选择项先结算，属性加值要赶在 HP 之前
    picked_choices = dict(choices or {})
    chosen_feats = tuple(feats)
    # 专长前提看**总等级**（兼职也算）：19 级恩惠不会因为某个职业只有 3 级就拒绝
    feat_defs_ = _check_feats(bundle, chosen_feats, total, (class_id,), scores)
    feat_powers = tuple(p for feat in feat_defs_ for p in feat.powers)
    all_powers = all_powers + tuple(p for p in feat_powers if p not in all_powers)
    # 可重复选取的专长（属性提升）按登记次数结算加值：登记两次就是两轮选择
    repeats = {feat.id: chosen_feats.count(feat.id) for feat in feat_defs_}
    picks = collect_picks(
        [feat for feat in feat_defs_ for _ in range(repeats.get(feat.id, 1))],
        picked_choices,
    )
    # 候选由内容生成的选项（法术、技能/工具混选）要真的在候选里 ——
    # 拿到 bundle 才能查法术表与工具表，所以校验放在这里而不是 `picks_for` 里
    problems = check_feat_choices(bundle, feat_defs_, picked_choices, repeats)
    if problems:
        raise RuleError("专长选择有问题：" + "；".join(problems))
    bonuses = merge_bonuses(score_bonuses(all_powers), picks.score)
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
    # 法术选择（戏法 / 准备法术）是玩家选择，与专长选择同一层：
    # 建角色时校验配额与环级上限，选错当场炸，选不完不算错（界面显示剩余名额）。
    spell_cantrips = {key: tuple(value) for key, value in (cantrips or {}).items()}
    spell_prepared = {key: tuple(value) for key, value in (prepared or {}).items()}
    spell_problems = check_spell_picks(
        bundle, {class_id: level}, spell_cantrips, spell_prepared)
    if spell_problems:
        raise RuleError("法术选择有问题：" + "；".join(spell_problems))
    profile = Profile(
        classes=(ClassEntry.make(class_id, level),),
        subclasses=(sub.id,) if sub is not None else (),
        proficiencies=(frozenset(saves)
                       | frozenset(class_def.proficiencies)
                       | frozenset(extra_proficiencies)
                       | picks.proficiencies),
        expertise=picks.expertise | frozenset(extra_expertise),
        feats=chosen_feats,
        choices=picked_choices,
        resistances=picks.resistances | frozenset(extra_resistances),
        cantrips=spell_cantrips,
        prepared=spell_prepared,
        # 原始属性（加值之前）必须留在档案里：存档、重建、界面改专长都要靠它。
        # 显示值里混着加值，倒推是减不掉的（有上限通道，越过上限的部分不会计入）。
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

    for resource in class_def.resources:
        pool = resource.build(level, ref)
        if pool.capacity <= 0:
            continue  # 未解锁的资源不建池，避免界面上出现 0/0
        actor.resources.add(pool)
    # 专长给的池（「每长休一次免费施放」）。容量按总等级查，一般写固定值。
    # 可重复选取的专长（魔法入门）登记两次就该有**两个**池 —— 每次登记是一次独立选择，
    # 合成一个会让人少一次施放。`feat_defs_` 是去重后的（同一专长只出现一次），
    # 所以次数要按 `repeats` 展开，不能靠遍历列表数出来。
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
    if profile.is_multiclass:
        # 兼职要合并位表、熟练来源与施法者等级，归 P7。现在悄悄按主职业建会算错。
        raise RuleError("兼职角色的重建要合并位表与熟练来源，归 P7；当前只支持单职业")
    entry = profile.classes[0]
    scores = {key: profile.base_score(key) for key in ABILITY_KEYS}
    subclass = next(
        (sub for sub in profile.subclasses
         if sub in bundle.subclasses and bundle.subclasses[sub].class_id == entry.class_id),
        None,
    )

    extra_prof: tuple[str, ...] = ()
    extra_exp: tuple[str, ...] = ()
    extra_res: tuple[str, ...] = ()
    actor: Actor | None = None
    for _ in range(3):
        actor = build_actor(
            bundle, entry.class_id, int(entry.class_level), scores,
            name_zh, name_en, actor_id=actor_id, kind=kind,
            extra_proficiencies=extra_prof, extra_expertise=extra_exp,
            extra_resistances=extra_res,
            subclass=subclass, feats=profile.feats, choices=profile.choices,
            cantrips=profile.cantrips, prepared=profile.prepared,
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
    """重建并**保住运行时状态**：当前 HP、临时 HP、资源的已用数。

    界面改一个专长就得重建（属性加值变了），但玩家不该因此回满血、
    或者把用掉的狂暴次数吐回来 —— 那是两件不同的事。

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
    fresh.conditions = actor.conditions
    fresh.effects = list(actor.effects)
    fresh.display_name = actor.display_name
    return fresh


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
    unlocked = any(
        getattr(effect, "op", "") == "morph"
        for power in class_def.powers_at(entry.class_level)
        for effect in power.effects
    )
    if not unlocked:
        return []
    return eligible_forms(bundle.forms.values(), class_def.morph, entry.class_level)
