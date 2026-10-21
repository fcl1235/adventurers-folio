# -*- coding: utf-8 -*-
"""双等级与施法者等级换算（约束 C8）。

三个概念不许混：
  TotalLevel   熟练加值、戏法伤害档位
  ClassLevel   特性解锁、资源次数、属性提升
  caster_level 兼职合并法术位表（派生值，不是角色属性）
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Mapping, Sequence

from ..kernel.errors import RuleError
from ..model.levels import ClassLevel, TotalLevel
from ..model.profile import Profile

MAX_CLASS_LEVEL = 20
MAX_TOTAL_LEVEL = 20


class CasterKind(str, Enum):
    """职业的施法者类型。新增「四分之一施法」自制职业只需加一个枚举值。"""

    NONE = "none"
    FULL = "full"
    HALF = "half"
    THIRD = "third"
    PACT = "pact"     # 契约魔法：独立池，不进合并表


def proficiency_bonus(total: TotalLevel) -> int:
    """只看总等级，全卡唯一来源。"""
    value = int(total)
    if value < 1:
        raise RuleError("总等级必须 >= 1：%r" % value)
    return 2 + (value - 1) // 4


def caster_level(entries: Iterable[tuple[ClassLevel, CasterKind]]) -> int:
    """合并施法者等级：全职全额、半施法向下取整一半、三分之一向下取整三分之一。"""
    total = 0
    for level, kind in entries:
        if kind is CasterKind.FULL:
            total += int(level)
        elif kind is CasterKind.HALF:
            total += int(level) // 2
        elif kind is CasterKind.THIRD:
            total += int(level) // 3
        elif kind in (CasterKind.PACT, CasterKind.NONE):
            continue
        else:
            raise RuleError("未知施法者类型：%r" % (kind,))
    return total


def slots_from_table(
    effective_level: int,
    table: Mapping[int, Mapping[int, int]],
) -> dict[int, int]:
    """查合并法术位表。表在内容里，内核不写公式。"""
    if effective_level < 0:
        raise RuleError("施法者等级不能为负")
    row = table.get(int(effective_level)) or {}
    return {int(level): int(count) for level, count in row.items() if int(count) > 0}


def validate_total(profile: Profile) -> None:
    if int(profile.total) > MAX_TOTAL_LEVEL:
        raise RuleError("总等级超过上限 %d：%d" % (MAX_TOTAL_LEVEL, int(profile.total)))
    for entry in profile.classes:
        if int(entry.class_level) > MAX_CLASS_LEVEL:
            raise RuleError("职业 %s 等级超过上限 %d" % (entry.class_id, MAX_CLASS_LEVEL))


def check_prereq(abilities, required: Mapping[str, int]) -> list[str]:
    """检查属性前提（兼职进/出都要求 13 主属性）。返回不满足项。"""
    missing = []
    for key, need in required.items():
        try:
            score = abilities.score(key)
        except RuleError:
            missing.append("%s 未知属性" % key)
            continue
        if score < int(need):
            missing.append("%s %d < %d" % (key, score, int(need)))
    return missing


def effective_caster_level(
    profile: Profile,
    caster_kinds: Mapping[str, CasterKind],
) -> tuple[int, int]:
    """返回 (合并施法者等级, 契约施法者等级)。契约位永远独立。"""
    entries: list[tuple[ClassLevel, CasterKind]] = []
    pact = 0
    for entry in profile.classes:
        kind = caster_kinds.get(entry.class_id, CasterKind.NONE)
        entries.append((entry.class_level, kind))
        if kind is CasterKind.PACT:
            pact += int(entry.class_level)
    return caster_level(entries), pact


def attacks_per_action(text_sources: Sequence[tuple[str, int]]) -> int:
    """额外攻击类能力取最大，不叠加（Stack.MAX 的语义在这儿落地）。"""
    best = 1
    for _source, count in text_sources:
        best = max(best, int(count))
    return best
