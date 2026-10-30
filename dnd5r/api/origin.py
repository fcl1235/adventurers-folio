# -*- coding: utf-8 -*-
"""出身：物种、背景、武器精通（P6）。

三件事的「重建成本」不一样，所以分成三组函数：

  * 换物种 / 换背景 → **必须 rebuild**。物种给 HP（矮人每级 +1）、速度、抗性；
    背景给属性加值（可能加在体质上 → HP 上限）。
  * 换精通 → **不需要 rebuild**。它只是记在档案里的一个集合，不参与任何派生值。
  * 属性生成（点买 / 标准数组 / 4d6）→ 只算数值，不建角色；建卡向导最后
    一次性把 scores 交给 `create_actor` / `set_base_scores`。

「武器精通效果不结算」是**写明的取舍**，不是漏做：精通都要命中后的战术选择
（推 10 尺、换伤害骰、附赠动作再打一次），内核没有目标与回合对象就算不出来。
界面照实标「已记录，未结算」，不假装算过了。
"""

from __future__ import annotations

from typing import Iterable, Mapping

from ..content import ContentBundle
from ..kernel.errors import RuleError
from ..kernel.rng import Rng
from ..model.actor import Actor
from ..rules.abilities import (
    POINT_BUY_BUDGET, POINT_BUY_MAX, POINT_BUY_MIN, STANDARD_ARRAY,
    background_bonus, point_buy_cost, roll_scores, score_range_ok,
    standard_array, validate_point_buy,
)
from ..rules.build import rebuild_actor
from ..rules.effects import NoteEffect
from ..rules.powers import Power

# 属性生成方式
SCORE_MODES = ("point_buy", "standard_array", "roll")
SCORE_MODE_ZH = {
    "point_buy": "点数购买（27 点，8–15）",
    "standard_array": "标准数组（15/14/13/12/10/8）",
    "roll": "掷骰（4d6 弃最低）",
}


def _settled(power: Power) -> bool:
    """这条特性是不是真的接进了数值管道。

    判据只有一条：效果里除 `note` 之外还有别的东西。`note` 是「规则登记在这、
    数值还没接」的标记物，所以只要全是 note，就不能在界面上说它生效了。
    """
    return any(not isinstance(effect, NoteEffect) for effect in power.effects)


def _trait_row(power: Power, locale: str = "zh") -> dict:
    return {
        "id": power.id,
        "name": power.name.get(locale),
        "text": power.text.get(locale),
        "level": int(power.level),
        "settled": _settled(power),
    }


# --- 查内容 -----------------------------------------------------------
def species_catalog(content: ContentBundle, locale: str = "zh") -> list[dict]:
    """物种清单（按 id 排序，界面自己决定怎么分组）。"""
    rows = []
    for species_id in sorted(content.species):
        item = content.species[species_id]
        rows.append({
            "id": item.id,
            "name": item.name.get(locale),
            "summary": item.summary.get(locale),
            "size": list(item.size),
            "speed": int(item.speed),
            "traits": [_trait_row(power, locale) for power in item.powers],
        })
    return rows


def background_catalog(content: ContentBundle, locale: str = "zh") -> list[dict]:
    """背景清单。技能的显示名从技能表查，查不到就退回 key（不编中文名）。"""
    rows = []
    for background_id in sorted(content.backgrounds):
        item = content.backgrounds[background_id]
        feat = content.feats.get(item.origin_feat)
        skills = []
        for key in item.skills:
            skill = next((s for s in content.skills.values() if s.key == key), None)
            skills.append({"key": key, "name": skill.name.get(locale) if skill else key})
        rows.append({
            "id": item.id,
            "name": item.name.get(locale),
            "summary": item.summary.get(locale),
            "abilities": list(item.abilities),
            "origin_feat": item.origin_feat,
            "origin_feat_name": feat.name.get(locale) if feat else item.origin_feat,
            "skills": skills,
            "tool": item.tool,
            "tool_label": None if item.tool_label is None else item.tool_label.get(locale),
        })
    return rows


def bonus_shapes(background_id: str, content: ContentBundle) -> list[dict[str, int]]:
    """这个背景允许的全部加值分配：一项 +2 一项 +1（3×2=6 种），或三项各 +1（1 种）。"""
    item = content.background(background_id)
    keys = list(item.abilities)
    shapes: list[dict[str, int]] = [{key: 1 for key in keys}]
    for plus_two in keys:
        for plus_one in keys:
            if plus_two == plus_one:
                continue
            shapes.append({plus_two: 2, plus_one: 1})
    return shapes


# --- 属性生成 ---------------------------------------------------------
def score_presets() -> dict:
    """三条属性生成方式各自的常量。界面照这个画控件，不自己写死数字。"""
    return {
        "budget": POINT_BUY_BUDGET,
        "min": POINT_BUY_MIN,
        "max": POINT_BUY_MAX,
        "standard": standard_array(),
        "modes": list(SCORE_MODES),
        "mode_labels": dict(SCORE_MODE_ZH),
    }


def check_scores(mode: str, scores: Mapping[str, int]) -> list[str]:
    """属性是否可用。返回问题清单（空 = 通过），不抛异常 —— 界面要边输边提示。"""
    problems = score_range_ok(scores)
    if problems:
        return problems
    if mode == "point_buy":
        return validate_point_buy(scores)
    if mode == "standard_array":
        if sorted(int(scores[key]) for key in scores) != sorted(STANDARD_ARRAY):
            return ["标准数组必须正好用完 %s" % "/".join(str(v) for v in STANDARD_ARRAY)]
        return []
    if mode == "roll":
        return []                      # 掷骰只看范围（4d6 弃最低必在 3–18）
    raise RuleError("未知的属性生成方式：%r" % (mode,))


def score_cost(scores: Mapping[str, int]) -> int:
    return point_buy_cost(scores)


def random_scores(rng: Rng) -> dict[str, int]:
    return roll_scores(rng)


# --- 设定出身 ---------------------------------------------------------
def set_origin(
    actor: Actor,
    content: ContentBundle,
    species: str | None = None,
    background: str | None = None,
    bonus: Mapping[str, int] | None = None,
) -> Actor:
    """换物种 / 背景 / 加值分配，返回**新的** actor。

    不传的项保持原样；传空串表示清掉。加值形态不合法、或加了背景没给的属性时
    当场抛 RuleError —— 静默纠正会养出一个「属性对不上卡面」的角色。
    """
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案，无法设出身")
    new_species = profile.species if species is None else str(species)
    new_background = profile.background if background is None else str(background)
    if new_species:
        content.species_def(new_species)          # 存在性检查，别把坏 id 写进档案
    if new_background:
        content.background(new_background)

    if bonus is None:
        new_bonus = dict(profile.background_bonus)
    else:
        new_bonus = {str(key).lower(): int(value) for key, value in bonus.items()}
    if new_background:
        # 换了背景时旧分配必须重验：新背景可能不给那些属性
        item = content.background(new_background)
        background_bonus(item.abilities, new_bonus)
    elif new_bonus:
        raise RuleError("没有选背景就不能有背景加值")

    updated = profile.with_origin(new_species, new_background, new_bonus)
    if updated == profile:
        return actor
    return rebuild_actor(content, actor, updated)


def set_masteries(actor: Actor, weapons: Iterable[str]) -> Actor:
    """记录武器精通（武器 id）。**不 rebuild**：它不参与任何派生值。"""
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案，无法记录武器精通")
    updated = profile.with_masteries(weapons)
    if updated == profile:
        return actor
    actor.profile = updated
    return actor


# --- 视图 -------------------------------------------------------------
def origin_view(actor: Actor, content: ContentBundle, locale: str = "zh") -> dict:
    """卡上「出身」那一块：物种、背景、加值、精通，以及每条特性有没有结算。"""
    profile = actor.profile
    if profile is None:
        return {"species": None, "background": None, "bonus": {}, "masteries": []}
    species_row = None
    if profile.species and profile.species in content.species:
        item = content.species[profile.species]
        species_row = {
            "id": item.id,
            "name": item.name.get(locale),
            "summary": item.summary.get(locale),
            "size": list(item.size),
            "speed": int(item.speed),
            "traits": [_trait_row(power, locale) for power in item.powers
                       if int(power.level) <= int(profile.total)],
        }
    background_row = None
    if profile.background and profile.background in content.backgrounds:
        item = content.backgrounds[profile.background]
        feat = content.feats.get(item.origin_feat)
        background_row = {
            "id": item.id,
            "name": item.name.get(locale),
            "summary": item.summary.get(locale),
            "abilities": list(item.abilities),
            "origin_feat": item.origin_feat,
            "origin_feat_name": feat.name.get(locale) if feat else item.origin_feat,
            "tool": item.tool,
            "tool_label": None if item.tool_label is None else item.tool_label.get(locale),
        }
    masteries = []
    for weapon_id in sorted(profile.masteries):
        # 精通按武器的**内容 id** 记（与专长、子职同一个口径），查不到就原样显示 id
        weapon = content.weapons.get(weapon_id)
        masteries.append({"id": weapon_id,
                          "name": weapon.name.get(locale) if weapon else weapon_id,
                          "mastery": getattr(weapon, "mastery", "") if weapon else ""})
    return {
        "species": species_row,
        "background": background_row,
        "bonus": {key: int(value) for key, value in profile.background_bonus.items()},
        "masteries": masteries,
        # 精通效果没结算这件事要在数据里说清楚，界面别自己编一句话
        "masteries_settled": False,
    }
