# -*- coding: utf-8 -*-
"""骰式 AST：可解析、可计算、可序列化。

支持 "2d6"、"d20"、"8d6+3"、"2d6+1d4-1" 这种组合式。
符号引用（等级、调整值）不在这里，由 rules 层先求值再喂进来。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .errors import DiceError
from .rng import Rng

_TERM = re.compile(r"[+-]?[^+-]+")


@dataclass(frozen=True, slots=True)
class Die:
    count: int
    sides: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise DiceError("骰子个数必须 >= 1：%r" % (self.count,))
        if self.sides < 2:
            raise DiceError("骰子面数必须 >= 2：%r" % (self.sides,))


@dataclass(frozen=True, slots=True)
class RollPart:
    die: Die
    rolls: tuple[int, ...]
    dropped: tuple[int, ...] = ()

    @property
    def subtotal(self) -> int:
        return sum(self.rolls)


@dataclass(frozen=True, slots=True)
class RollResult:
    total: int
    parts: tuple[RollPart, ...] = ()

    def describe(self) -> str:
        bits = []
        for part in self.parts:
            marks = ",".join(str(r) for r in part.rolls)
            if part.dropped:
                marks += "（弃 %s）" % ",".join(str(d) for d in part.dropped)
            bits.append("%dd%d[%s]" % (part.die.count, part.die.sides, marks))
        return " + ".join(bits) if bits else str(self.total)


@dataclass(frozen=True, slots=True)
class Dice:
    dice: tuple[Die, ...] = ()
    flat: int = 0

    # --- 数值边界 -----------------------------------------------------
    @property
    def minimum(self) -> int:
        return sum(d.count for d in self.dice) + self.flat

    @property
    def maximum(self) -> int:
        return sum(d.count * d.sides for d in self.dice) + self.flat

    @property
    def average(self) -> float:
        total = sum(d.count * (d.sides + 1) / 2 for d in self.dice)
        return total + self.flat

    def roll(self, rng: Rng) -> RollResult:
        parts = []
        total = self.flat
        for die in self.dice:
            rolls = tuple(rng.randint(1, die.sides) for _ in range(die.count))
            parts.append(RollPart(die=die, rolls=rolls))
            total += sum(rolls)
        return RollResult(total=total, parts=tuple(parts))

    def __str__(self) -> str:
        bits = ["%dd%d" % (d.count, d.sides) for d in self.dice]
        if self.flat:
            bits.append(("+" if self.flat > 0 else "") + str(self.flat))
        return "".join(bits) if bits else "0"


def parse(expr: str) -> Dice:
    """把 "2d6+3" 解析成 Dice。空式、负骰、非法段都报错。"""
    if not isinstance(expr, str):
        raise DiceError("骰式必须是字符串：%r" % (expr,))
    text = expr.replace(" ", "").lower()
    if not text:
        raise DiceError("骰式不能为空")

    dice: list[Die] = []
    flat = 0
    for chunk in _TERM.findall(text):
        negative = chunk.startswith("-")
        body = chunk.lstrip("+-")
        if not body:
            raise DiceError("骰式有不完整的项：%r" % expr)
        if "d" in body:
            if negative:
                raise DiceError("不支持负骰子：%r" % expr)
            count_text, _, sides_text = body.partition("d")
            try:
                count = int(count_text) if count_text else 1
                sides = int(sides_text)
            except ValueError:
                raise DiceError("骰式项无法解析：%r" % chunk)
            dice.append(Die(count=count, sides=sides))
        else:
            try:
                flat += (-1 if negative else 1) * int(body)
            except ValueError:
                raise DiceError("骰式项无法解析：%r" % chunk)

    if not dice and flat == 0 and text not in ("0", "+0", "-0"):
        raise DiceError("骰式解析结果为空：%r" % expr)
    return Dice(dice=tuple(dice), flat=flat)


def roll_d20(rng: Rng, mode: str = "flat") -> RollResult:
    """mode: flat / adv / dis。优势劣势各掷两次，保留高/低。"""
    if mode not in ("flat", "adv", "dis"):
        raise DiceError("未知掷骰模式：%r" % mode)
    first = rng.randint(1, 20)
    if mode == "flat":
        return RollResult(total=first, parts=(RollPart(Die(1, 20), (first,)),))
    second = rng.randint(1, 20)
    keep = max(first, second) if mode == "adv" else min(first, second)
    drop = min(first, second) if mode == "adv" else max(first, second)
    return RollResult(
        total=keep,
        parts=(RollPart(Die(1, 20), (keep,), (drop,)),),
    )


def combine(values: Sequence[Dice]) -> Dice:
    dice: list[Die] = []
    flat = 0
    for item in values:
        dice.extend(item.dice)
        flat += item.flat
    return Dice(dice=tuple(dice), flat=flat)
