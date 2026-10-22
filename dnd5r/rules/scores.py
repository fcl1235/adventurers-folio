# -*- coding: utf-8 -*-
"""属性加值通道：唯一会改「属性值本身」的入口。

为什么单开一个模块：`contributions` 要 import `build`（找已解锁能力），
而 `build` 建角色时又要用这里的函数算 HP —— 放在 contributions 里就成环了。

语义（2024）：
  - 加值改的是**属性值**，不是检定加值。所以加完之后 HP（体质）、AC（敏捷/体质）、
    攻击、豁免全部跟着变，这就是原始冠军与身心合一的真实行为。
  - 每条加值都可以带 `cap`（上限）。压轴写 25，传奇恩惠写 30。
  - 上限必须先窄后宽结算：先把 20 顶到 25，再让 +1 顶到 30。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..model.statblock import ABILITY_KEYS, SCORE_MAX, SCORE_MIN, Abilities
from .modifiers import Stack
from .powers import Power


@dataclass(frozen=True, slots=True)
class ScoreBonus:
    """一条「属性值 +N，上限 M」。上限缺省就是 30（SCORE_MAX）。"""

    ability: str
    amount: int
    cap: int | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if self.ability not in ABILITY_KEYS:
            raise ValueError("未知属性：%r" % (self.ability,))
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise ValueError("属性加值必须是整数：%r" % (self.amount,))
        if self.amount == 0:
            raise ValueError("属性加值不能是 0：%s" % self.ability)

    @property
    def limit(self) -> int:
        return SCORE_MAX if self.cap is None else min(SCORE_MAX, int(self.cap))

    def apply_to(self, score: int) -> int:
        return max(SCORE_MIN, min(self.limit, int(score) + self.amount))


def score_bonuses(powers: Iterable[Power]) -> tuple[ScoreBonus, ...]:
    """收集 `score.<属性>` 的常驻加成，并**按上限从窄到宽**排好序。

    排序不是洁癖：压轴（上限 25）与传奇恩惠（上限 30）同时存在时，
    顺序反了就会把「20 +4 → 24，再 +1 → 25」算成「顶到 25 之后 +1 无效」。
    """
    found: list[ScoreBonus] = []
    for power in powers:
        for effect in power.effects:
            for mod in getattr(effect, "modifiers", ()):
                head, _, key = mod.target.partition(".")
                if head != "score" or key not in ABILITY_KEYS:
                    continue
                if mod.stack is not Stack.ADD:
                    raise ValueError("%s 的属性加值只能是 add，实际 %s"
                                     % (mod.target, mod.stack.value))
                found.append(ScoreBonus(
                    ability=key,
                    amount=mod.value,
                    cap=mod.cap,
                    source=mod.source or power.id,
                ))
    found.sort(key=lambda item: (item.limit, item.ability))
    return tuple(found)


def merge_bonuses(*groups: Iterable[ScoreBonus]) -> tuple[ScoreBonus, ...]:
    """合并多组加值并**重新排序**（先窄后宽）。

    职业给的与专长给的分开收集，合并时必须重排一次：压轴（25）与传奇恩惠（30）
    来自两处，各排各的会把「先顶到 25 再 +1」算坏。
    """
    found = [bonus for group in groups for bonus in group]
    found.sort(key=lambda item: (item.limit, item.ability))
    return tuple(found)


def apply_score_bonuses(abilities: Abilities, bonuses: Iterable[ScoreBonus]) -> Abilities:
    """把加成落成新属性值。传进来的顺序必须已经是「先窄后宽」。"""
    scores = dict(abilities.scores)
    for bonus in bonuses:
        scores[bonus.ability] = bonus.apply_to(scores[bonus.ability])
    return Abilities.of(**scores)


def bonus_totals(bonuses: Iterable[ScoreBonus]) -> dict[str, int]:
    """给界面看的「白给了多少属性」：属性 → 累计加值（不含截断）。"""
    totals: dict[str, int] = {}
    for bonus in bonuses:
        totals[bonus.ability] = totals.get(bonus.ability, 0) + bonus.amount
    return totals


def score_bonus_of(powers: Iterable[Power]) -> dict[str, int]:
    return bonus_totals(score_bonuses(powers))


__all__ = [
    "ScoreBonus", "score_bonuses", "merge_bonuses", "apply_score_bonuses",
    "score_bonus_of", "bonus_totals",
]
