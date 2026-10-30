# -*- coding: utf-8 -*-
"""属性生成：点买 / 标准数组 / 4d6 弃最低 / 背景加值。

2024 的三条容易搞错的规矩写死在这里：
  1. 点买 **27 点**，买的是 8–15 之间；16 以上**买不到**（加值来自背景与专长）
  2. 标准数组是 `15/14/13/12/10/8`，不是旧版的 `15/14/13/12/10/8` 之外的任何变体
  3. 背景加值：从背景的三项属性里选两项，**一项 +2 一项 +1**；或者三项各 +1。
     加完上限 20。**不能拆成三个 +1 加在两项上**（「+1 +1 +1」必须是三项各一）
"""

from __future__ import annotations

from typing import Iterable, Mapping

from ..kernel.errors import RuleError
from ..kernel.rng import Rng
from ..model.statblock import ABILITY_KEYS, SCORE_MAX, SCORE_MIN

# 官方点买表：8 → 0 点，15 → 9 点
POINT_BUY_COST = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
POINT_BUY_BUDGET = 27
POINT_BUY_MIN = 8
POINT_BUY_MAX = 15
# 标准数组（从高到低）
STANDARD_ARRAY = (15, 14, 13, 12, 10, 8)
# **角色**属性上限是 20，和 `statblock.SCORE_MAX`（30）不是同一个数。
# 30 是怪物/异界生物的上限：拿它当角色上限，背景加值就会允许「19 + 2 = 21」
# 这种规则里不存在的结果。（P6 曾把两者当成一个，向导校验时露出来了。）
CHARACTER_SCORE_MAX = 20
BACKGROUND_BONUS_CAP = CHARACTER_SCORE_MAX
BACKGROUND_PLUS_TWO = 2
BACKGROUND_PLUS_ONE = 1


def point_buy_cost(scores: Mapping[str, int]) -> int:
    """这套属性的总花费。超出 8–15 的点买范围直接报错，**不夹**。"""
    total = 0
    for key in ABILITY_KEYS:
        value = int(scores.get(key, POINT_BUY_MIN))
        if not POINT_BUY_MIN <= value <= POINT_BUY_MAX:
            raise RuleError("%s 的点买值必须在 %d–%d 之间：%d"
                            % (key.upper(), POINT_BUY_MIN, POINT_BUY_MAX, value))
        total += POINT_BUY_COST[value]
    return total


def validate_point_buy(scores: Mapping[str, int],
                       budget: int = POINT_BUY_BUDGET) -> list[str]:
    """返回问题清单（空 = 合法）。给界面用：不抛异常才能边输边提示。"""
    problems: list[str] = []
    missing = [key for key in ABILITY_KEYS if key not in scores]
    if missing:
        problems.append("缺属性：%s" % ", ".join(item.upper() for item in missing))
        return problems
    try:
        spent = point_buy_cost(scores)
    except RuleError as exc:
        return [str(exc)]
    if spent > budget:
        problems.append("点买超支：花 %d 点，上限 %d" % (spent, budget))
    return problems


def standard_array() -> dict[str, int]:
    """标准数组按「力量的顺序」发牌 —— 具体哪项拿 15 由玩家分配，这里只给一套默认。"""
    return dict(zip(ABILITY_KEYS, STANDARD_ARRAY))


def roll_scores(rng: Rng) -> dict[str, int]:
    """4d6 弃最低，六次。骰点一律走 rng 参数（C4：只有 kernel/rng.py 能 import random）。"""
    scores: dict[str, int] = {}
    for key in ABILITY_KEYS:
        rolls = sorted((rng.randint(1, 6) for _ in range(4)), reverse=True)
        scores[key] = sum(rolls[:3])
    return scores


def background_bonus(abilities: Iterable[str], picks: Mapping[str, int]) -> dict[str, int]:
    """把背景加值变成 `{属性: 加值}`。

    `abilities` 是背景给的三项属性，`picks` 是玩家的分配（属性 → +2/+1/+1）。

    三条会当场拒绝的：
      * 选了背景没给的属性（那不是这个背景给的好处）
      * 值不是 +1 或 +2
      * 形态不对：合法形态只有「一个 +2 加一个 +1」或「三个 +1」
    """
    allowed = tuple(str(item).lower() for item in abilities)
    if not allowed:
        raise RuleError("这个背景没有属性加值")
    cleaned = {str(key).lower(): int(value) for key, value in picks.items()}
    if not cleaned:
        return {}
    unknown = [key for key in cleaned if key not in allowed]
    if unknown:
        raise RuleError("背景只给 %s 的加值，不能加在 %s"
                        % ("、".join(item.upper() for item in allowed),
                           "、".join(item.upper() for item in unknown)))
    bad = [value for value in cleaned.values()
           if value not in (BACKGROUND_PLUS_ONE, BACKGROUND_PLUS_TWO)]
    if bad:
        raise RuleError("背景加值只能是 +1 或 +2：%r" % (bad,))
    twos = sum(1 for value in cleaned.values() if value == BACKGROUND_PLUS_TWO)
    ones = sum(1 for value in cleaned.values() if value == BACKGROUND_PLUS_ONE)
    if (twos, ones) == (1, 1):
        pass                                   # +2 与 +1 各一项
    elif (twos, ones) == (0, 3):
        pass                                   # 三项各 +1
    else:
        raise RuleError("背景加值的两种合法形态：一项 +2 加一项 +1，或三项各 +1；"
                        "现在是 %d 个 +2、%d 个 +1" % (twos, ones))
    return cleaned


def apply_cap(scores: Mapping[str, int], bonuses: Mapping[str, int],
              cap: int = BACKGROUND_BONUS_CAP) -> dict[str, int]:
    """把加值叠到属性上并夹上限。返回新字典，不改入参。"""
    result = {key: int(scores[key]) for key in ABILITY_KEYS if key in scores}
    for key, value in (bonuses or {}).items():
        if key not in result:
            continue
        result[key] = min(cap, result[key] + int(value))
    return result


def score_range_ok(scores: Mapping[str, int]) -> list[str]:
    """手工输入（骰点/自定义）时的范围检查。"""
    problems: list[str] = []
    for key in ABILITY_KEYS:
        if key not in scores:
            problems.append("缺属性 %s" % key.upper())
            continue
        value = scores[key]
        if not isinstance(value, int) or isinstance(value, bool):
            problems.append("%s 必须是整数：%r" % (key.upper(), value))
        elif not SCORE_MIN <= value <= SCORE_MAX:
            problems.append("%s 超出 %d–%d：%d" % (key.upper(), SCORE_MIN, SCORE_MAX, value))
    return problems
