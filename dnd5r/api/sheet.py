# -*- coding: utf-8 -*-
"""投影：角色卡 / 最小视图 / 形态视图。

前端看到的派生值都从这里出 —— 同一个数只有一个算法（G24 的正解）。
拆自 P11 之前的巨型 __init__。"""
from __future__ import annotations

from typing import Any

from ..content import ContentBundle
from ..kernel.rng import SeededRng
from ..model.actor import MAX_EXHAUSTION, Actor
from ..model.death import DEAD_AT, STABLE_AT
from ..model.levels import ClassLevel
from ..rules.armor import ac_inputs, loadout_for
from ..rules.build import (
    available_powers, eligible_forms_for, feat_defs, feat_picks,
    morph_class_of, subclass_defs,
)
from ..rules.contributions import (
    modifiers_for, passive_defenses, passive_modifiers, passive_proficiencies,
    power_channels, power_status, save_modifiers, skill_modifiers,
)
from ..rules.feats import choice_prompt, proficiency_pool, spell_pool
from ..rules.morph import form_id, reasons_for
from ..rules.powers import can_use
from ..rules.progression import MAX_TOTAL_LEVEL, proficiency_bonus
from ..rules.resolver import crit_text, exhaustion_penalty, exhaustion_speed_penalty
from ..rules.scores import bonus_totals, merge_bonuses, score_bonuses
from ..rules.spellcasting import casting_summary
from ..rules.weapons import profiles_for
from ._support import (
    ABILITY_KEYS, _class_defs, _context, _dice_mode, _proficiency_sets,
    resolver_for,
)

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
        granted: list[str] = list(feat.spells)
        for choice in feat.choices:
            key = "%s.%s" % (feat.id, choice.id)
            picked = list(profile.choices.get(key, ())) if profile else []
            options = list(choice.options)
            if choice.kind == "expertise":
                # 专精只能选已有熟练的技能 —— Profile 会校验，但选单不该给出非法项
                options = [item for item in options if "skill.%s" % item in tokens]
            elif choice.kind == "spell":
                # 候选由法术表 + 环级现算，内容里不抄（见 rules/feats.py:spell_pool）
                options = list(spell_pool(content, choice))
                granted += [item for item in picked if item not in granted]
            elif choice.kind == "proficiency":
                # 「技能或工具，任意组合」—— 候选同样是现算的，且是**完整 token**
                options = list(proficiency_pool(content))
            choices.append({
                "id": choice.id,
                "key": key,
                "kind": choice.kind,
                "label": choice_prompt(feat, choice, locale).get(locale),
                "picked": picked,
                "remaining": choice.count - len(picked),
                "count": choice.count,
                "options": options,
                # 选单要显示法术名而不是裸 id；值仍然是 id
                "option_labels": {ident: _spell_name(content, ident, locale)
                                  for ident in options} if choice.kind == "spell" else {},
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
            # 这个专长给的法术：写死的 + 你在选择项里选中的，合成一条「始终准备」清单
            "spells": [_spell_row(content, ident, locale) for ident in granted],
            "resources": [_feat_pool_row(pool, locale)
                          for pool in _feat_pools(actor, feat)],
        })
    return rows


def _feat_pools(actor: Actor, feat) -> list:
    """这个专长建出来的资源池。按 id 前缀认 —— 池 id 就是 `<专长 id>.<名字>`。"""
    root = actor.root()
    return [pool for pool_id, pool in root.resources.pools.items()
            if pool_id == feat.id or pool_id.startswith(feat.id + ".")]


def _feat_pool_row(pool, locale: str = "zh") -> dict:
    return {
        "id": pool.id,
        "label": pool.label.get(locale) if pool.label else pool.id,
        "used": int(pool.used),
        "capacity": int(pool.capacity),
        # 空 = 通用池（「每长休一次免费施放」，哪道法术都行）；
        # 非空 = 只给这一道法术用（「两道法术各一次」，各记各的）
        "spell": pool.spell,
    }


def _spell_name(content: ContentBundle, spell_id: str, locale: str = "zh") -> str:
    spell = content.spells.get(spell_id)
    return spell.name.get(locale) if spell is not None else spell_id


def _spell_row(content: ContentBundle, spell_id: str, locale: str = "zh") -> dict:
    spell = content.spells.get(spell_id)
    return {
        "id": spell_id,
        "name": spell.name.get(locale) if spell is not None else spell_id,
        "level": int(spell.level) if spell is not None else 0,
        "school": spell.school if spell is not None else "",
    }


def _feat_status(feat) -> str:
    """专长的诚实标记。与能力同一套词汇（counted/dice/active/onhit/manual/text）。

    有选择项的专长一定算数（选完就落属性/熟练/抗性），所以直接算 counted；
    剩下的看它挂的能力里有没有真被消费的通道。
    """
    if feat.choices:
        return "counted"
    statuses = {power_status(power) for power in feat.powers}
    # dice 排在 counted 之后：优势/劣势改的是掷骰形状，不是加值，但它确实被消费了
    for level in ("counted", "dice", "active", "onhit", "manual"):
        if level in statuses:
            return level
    return "text"


def character_sheet(actor: Actor, content: ContentBundle, locale: str = "zh") -> dict:
    """只读投影：卡片、派生值、能力列表。前端不判断任何规则。"""
    resolver = resolver_for(actor, content)
    profile = actor.profile
    top = actor.top()
    root = actor.root()
    loadout = loadout_for(actor, content.armors)
    morphed = top.layer is not None
    saves_prof, skill_tokens, expertise_tokens = _proficiency_sets(actor, content)
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
    saves = {}
    for key in ABILITY_KEYS:
        mode, mode_sources = _dice_mode(content, actor, "save.%s" % key)
        saves[key] = resolver.saving_throw(
            top, key, proficient=key in saves_prof,
            modifiers=save_modifiers(mods, key),
            mode=mode, mode_sources=mode_sources)
    # 技能：属性检定 + 熟练（+ 专精）。熟练 token 与内容里的 `skill.<key>` 必须一致，
    # 所以这里从**内容**的技能表出发去查 token，而不是反过来枚举令牌。
    skill_rows = []
    for skill in sorted(content.skills.values(), key=lambda item: (item.ability, item.key)):
        token = "skill.%s" % skill.key
        proficient = token in skill_tokens
        mode, mode_sources = _dice_mode(content, actor, "check.%s" % skill.key)
        roll = resolver.ability_check(
            top, skill.ability, proficient=proficient,
            expertise=token in expertise_tokens,
            modifiers=skill_modifiers(mods, skill.key),
            mode=mode, mode_sources=mode_sources,
        )
        skill_rows.append({
            "id": skill.id, "key": skill.key, "ability": skill.ability,
            "name": skill.name.get(locale),
            "total": roll.total, "detail": roll.describe(),
            "mode": roll.mode, "mode_sources": list(roll.mode_sources),
            "proficient": proficient, "expertise": token in expertise_tokens,
        })
    # 工具：也是「属性检定 + 熟练」，但属性**不绑死**（规则是「DM 决定用哪项」）。
    # 卡片上按内容里的建议属性算一个默认值，掷骰时可以传 `ability` 覆盖。
    tool_rows = []
    for tool in sorted(content.tools.values(), key=lambda item: (item.kind, item.key)):
        token = "tool.%s" % tool.key
        proficient = token in skill_tokens
        mode, mode_sources = _dice_mode(content, actor, "check.%s" % tool.ability)
        roll = resolver.ability_check(
            top, tool.ability, proficient=proficient,
            modifiers=(modifiers_for(mods, token)
                       + modifiers_for(mods, "skill_check")),
            mode=mode, mode_sources=mode_sources,
        )
        tool_rows.append({
            "id": tool.id, "key": tool.key, "kind": tool.kind,
            "name": tool.name.get(locale),
            "ability": tool.ability,
            "total": roll.total, "detail": roll.describe(),
            "mode": roll.mode, "mode_sources": list(roll.mode_sources),
            "proficient": proficient,
        })
    # 攻击：默认用最高的力量／敏捷，只看是否熟练（武器数据在 P5c）
    attack_ability = "str" if top.statblock.abilities.mod("str") >= top.statblock.abilities.mod("dex") else "dex"
    attack_mode, attack_sources = _dice_mode(content, actor, "attack.%s" % attack_ability)
    attack = resolver.attack_bonus(top, attack_ability, proficient=True,
                                   modifiers=modifiers_for(mods, "attack"),
                                   mode=attack_mode, mode_sources=attack_sources)
    # 先攻单独算：它的优势标记叫 `initiative`，与「敏捷检定」不是同一条
    init_mode, init_sources = _dice_mode(content, actor, "initiative")
    initiative = resolver.initiative(top, mode=init_mode, mode_sources=init_sources)

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
        "initiative": {"total": initiative.total, "detail": initiative.describe(),
                       "mode": initiative.mode,
                       "mode_sources": list(initiative.mode_sources)},
        "speed": speeds,
        "senses": senses,
        "resistances": resistances,
        "immunities": sorted(feat_immune),
        "abilities": _ability_rows(actor, content, morphed),
        "gear": loadout.to_dict(locale),
        "saves": {key: {"total": value.total, "detail": value.describe(),
                        "mode": value.mode, "mode_sources": list(value.mode_sources),
                        "proficient": key in saves_prof}
                  for key, value in saves.items()},
        "skills": skill_rows,
        "tools": tool_rows,
        "attack": {"total": attack.total, "detail": attack.describe(), "ability": attack_ability,
                   "mode": attack.mode, "mode_sources": list(attack.mode_sources)},
        "crit": {"min": crit.total, "detail": crit.describe(),
                 "text": crit_text(crit.total)},
        "attacks": attacks,
        "attacks_per_action": attacks_per_action,
        "conditions": list(actor.conditions.ids()),
        # 力竭与濒死记分。**界面不再自己乘 2** —— 减值与速度惩罚都从这里给，
        # 免得再出「卡上写 −4、掷骰时没扣」那种对不上的老毛病。
        "exhaustion": {
            "level": int(root.exhaustion),
            "max": MAX_EXHAUSTION,
            "penalty": exhaustion_penalty(root.exhaustion),
            "speed": exhaustion_speed_penalty(root.exhaustion),
        },
        "death_saves": {
            "succeeded": root.death_saves.succeeded,
            "failed": root.death_saves.failed,
            "succeeded_of": STABLE_AT, "failed_of": DEAD_AT,
            "dead": root.death_saves.dead, "stable": root.death_saves.stable,
        },
        "morphed": actor.top().layer is not None,
        # 形态的整张卡（含它自己的攻击）：变形后界面要照着它出手，
        # 不然熊只会用徒手 1 + 力量调整值 —— 内容里的 1d8+3 等于没写。
        "form": form_view(actor, content, locale),
        "forms": [
            {"id": form.id, "name": form.name.get(locale), "cr": form.cr,
             "ac": form.ac, "hp": form.hp, "speeds": dict(form.speeds)}
            for form in eligible_forms_for(actor, content)
        ],
        "pools": [
            {"id": pool.id, "left": pool.available, "max": pool.capacity,
             "kind": pool.kind.value, "refresh": pool.refresh.value,
             # 显示名来自内容（「回气」「狂暴」），没有就退回 id —— 界面不该自己编名字
             "label": pool.label.get(locale) if pool.label else pool.id,
             # 绑在具体法术上的次数（妖精触碰的第几次迷踪步）：界面据此标「可免位施放」
             "spell": pool.spell, "source": pool.source}
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


def form_view(actor: Actor, content: ContentBundle, locale: str = "zh") -> dict:
    """当前形态的整张卡（没变形时只有 `{"morphed": False}`）。

    界面拿它画形态的攻击按钮 —— 不传它就只剩徒手 1 + 力量调整值，
    熊的啃咬 1d8+3 就白写在内容里了（G22）。

    `actions` 的形状与 `monster_actions` 完全一致（`slot:index` 键），
    所以界面点它的时候走的还是 `monster_attack` / `resolve_monster_attack`。
    """
    from ..rules.monsters import attack_options

    ident = form_id(actor)
    if ident is None:
        return {"morphed": False}
    form = content.forms.get(ident)
    if form is None:
        # 内容里没有这条形态（比如换了一套插件）：如实说缺，不假装是空卡
        return {"morphed": True, "id": ident, "name": "", "missing": True,
                "actions": [], "traits": []}
    return {
        "morphed": True,
        "id": ident,
        "name": form.name.get(locale),
        "ac": int(form.ac),
        "hp": int(form.hp),
        "cr": float(form.cr),
        "size": form.size,
        "saves": dict(form.saves or {}),
        "traits": [row.to_dict(locale) for row in form.traits],
        "actions": attack_options(form, locale),
    }


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


# --- 遭遇战 -----------------------------------------------------------
# 这里返回的是**对象**而不是 dict：前端要连着做一串操作（下一回合、移动、传送），
# 每步传 dict 回来既啰嗦，又容易只改到副本。前端把它当不透明句柄拿着就行，
# 不需要（也不应该）知道它的类型 —— C3 检查的是 import，不是返回值的类。
