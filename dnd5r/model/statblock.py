# -*- coding: utf-8 -*-
"""属性与数值底板。

Abilities 是唯一叶子：调整值 = floor((值-10)/2)，其余一切派生都从这里出。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from ..kernel.errors import RuleError
from ..kernel.text import Text

ABILITY_KEYS: tuple[str, ...] = ("str", "dex", "con", "int", "wis", "cha")
ABILITY_NAMES: Mapping[str, Text] = MappingProxyType({
    "str": Text.of("力量", "Strength"),
    "dex": Text.of("敏捷", "Dexterity"),
    "con": Text.of("体质", "Constitution"),
    "int": Text.of("智力", "Intelligence"),
    "wis": Text.of("感知", "Wisdom"),
    "cha": Text.of("魅力", "Charisma"),
})

SCORE_MIN, SCORE_MAX = 1, 30


def ability_mod(score: int) -> int:
    return (int(score) - 10) // 2


@dataclass(frozen=True, slots=True)
class Abilities:
    scores: Mapping[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.scores, Mapping):
            raise RuleError("属性必须是映射")
        missing = [key for key in ABILITY_KEYS if key not in self.scores]
        if missing:
            raise RuleError("缺少属性：%s" % ", ".join(missing))
        clean = {}
        for key in ABILITY_KEYS:
            value = self.scores[key]
            if not isinstance(value, int) or isinstance(value, bool):
                raise RuleError("属性 %s 必须是整数：%r" % (key, value))
            if not (SCORE_MIN <= value <= SCORE_MAX):
                raise RuleError("属性 %s 超出 %d..%d：%r" % (key, SCORE_MIN, SCORE_MAX, value))
            clean[key] = value
        object.__setattr__(self, "scores", MappingProxyType(clean))

    @classmethod
    def of(cls, **scores: int) -> "Abilities":
        return cls(scores=dict(scores))

    def score(self, key: str) -> int:
        if key not in self.scores:
            raise RuleError("未知属性：%r" % (key,))
        return self.scores[key]

    def mod(self, key: str) -> int:
        return ability_mod(self.score(key))

    def replace(self, **changes: int) -> "Abilities":
        data = dict(self.scores)
        data.update(changes)
        return Abilities(scores=data)

    def to_dict(self) -> dict:
        return dict(self.scores)


@dataclass(frozen=True, slots=True)
class Statblock:
    """一张数值底板：玩家本体、野兽形态、怪物、召唤物都用它。"""

    name: Text
    abilities: Abilities
    ac_base: int = 10
    speeds: Mapping[str, int] = field(default_factory=lambda: {"walk": 30})
    senses: Mapping[str, int] = field(default_factory=dict)
    size: str = "medium"
    cr: float = 0.0
    # 卡上直接印着的豁免加值（怪物）。空 = 按「属性调整值 + 熟练」推。
    # 为什么要这个字段：怪物的豁免熟练不总等于 `属性 + 熟练`，
    # 推一遍会悄悄算错；模板上写多少就是多少。
    saves: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, Text):
            raise RuleError("Statblock.name 必须是 Text")
        if self.ac_base < 0:
            raise RuleError("AC 基础值不能为负")
        for mode, value in self.speeds.items():
            if value < 0:
                raise RuleError("速度不能为负：%s=%r" % (mode, value))
        bad = [key for key in self.saves if key not in ABILITY_KEYS]
        if bad:
            raise RuleError("豁免加值只能按 %s 写：%r" % ("/".join(ABILITY_KEYS), bad))
        object.__setattr__(self, "speeds", MappingProxyType(dict(self.speeds)))
        object.__setattr__(self, "senses", MappingProxyType(dict(self.senses)))
        object.__setattr__(self, "saves", MappingProxyType(dict(self.saves)))

    def speed(self, mode: str = "walk") -> int:
        return int(self.speeds.get(mode, 0))
