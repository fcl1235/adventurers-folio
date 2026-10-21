# -*- coding: utf-8 -*-
"""生命值：上限是派生值，不是存档字段。

2024 规则：1 级满骰，之后每级取固定值（骰面一半 + 1）加体质调整值；
体质调整值最低按 +1 计入每级增量（`max(1, ...)` 保护的是这个下限，
不是「生命值不能为负」）。

兼职角色的生命骰来自**每个职业各自的骰面**，所以这里的接口按
(骰面, 该职业技能等级) 一段一段加，最后再由调用方求和。
"""

from __future__ import annotations

from ..kernel.errors import RuleError
from ..model.levels import ClassLevel, as_class_level
from ..model.resources import Pool, PoolKind, Refresh


def hp_per_level(hit_die: int, con_mod: int) -> int:
    """2 级以后每升一级的固定增量。"""
    if hit_die < 2:
        raise RuleError("生命骰面必须 >= 2：%r" % (hit_die,))
    return max(1, hit_die // 2 + 1 + int(con_mod))


def hit_points_max(
    hit_die: int,
    con_mod: int,
    level: ClassLevel,
    per_level_bonus: int = 0,
    flat_bonus: int = 0,
) -> int:
    """单职业的 HP 上限。

    per_level_bonus：专长/种族这类「每级 +N」（坚韧、矮人韧性）
    flat_bonus     ：传奇恩惠这类「一次性 +N」（强健之恩惠 +40）
    """
    steps = int(level)
    if steps < 1:
        raise RuleError("等级必须 >= 1：%r" % steps)
    total = int(hit_die) + int(con_mod)
    total += (steps - 1) * hp_per_level(hit_die, con_mod)
    total += int(per_level_bonus) * steps
    total += int(flat_bonus)
    return max(1, total)


def hit_dice_pool(class_id: str, hit_die: int, level: ClassLevel) -> Pool:
    """生命骰也是一池资源：短休可以花，长休回一半。"""
    return Pool(
        id="hit_dice.%s" % class_id,
        kind=PoolKind.DICE,
        capacity=int(level),
        owner_class=class_id,
        refresh=Refresh.LONG_REST,
    )


def hit_dice_average(hit_die: int) -> int:
    """短休花一颗生命骰的回血量（不掷骰时取固定值）。"""
    return hit_die // 2 + 1


def multiclass_hit_points(
    segments: "list[tuple[int, ClassLevel]]",
    con_mod: int,
    per_level_bonus: int = 0,
    flat_bonus: int = 0,
) -> int:
    """兼职：每个职业第一级都取满骰，其余级取固定值。"""
    if not segments:
        raise RuleError("至少要有一个职业段")
    total = 0
    for hit_die, level in segments:
        total += hit_points_max(hit_die, con_mod, as_class_level(int(level)), per_level_bonus, 0)
    return max(1, total + int(flat_bonus))
