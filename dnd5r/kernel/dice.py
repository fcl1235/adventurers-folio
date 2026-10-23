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
        """同面数的骰子合并着写（`1d10` + `1d10` → `2d10`）。

        重击是把骰子翻倍得来的，两段同面骰若原样拼成 `1d10+1d10`，
        既长又容易读成「两种伤害」。合并之后 `2d10` 就是玩家认得的写法。
        """
        counts: dict[int, int] = {}
        order: list[int] = []
        for die in self.dice:
            if die.sides not in counts:
                counts[die.sides] = 0
                order.append(die.sides)
            counts[die.sides] += die.count
        bits = ["%dd%d" % (counts[sides], sides) for sides in order]
        text = "+".join(bits)
        if self.flat:
            if not text:
                return str(self.flat)          # 纯定值（徒手 1 点）不要写成 "+1"
            text += ("+" if self.flat > 0 else "-") + str(abs(self.flat))
        return text or "0"


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


def stack(expr: str, extra: str, times: int = 1) -> str:
    """`expr` 叠 `times` 份 `extra`：`8d6` + 2 × `1d6` → `10d6`。

    升环就是这么算的 —— 「每提升一环 +1d6」是**同一颗骰子多掷几次**，
    不是把合计乘上去：写成 ×2 会连定值一起翻倍（`2d6+3` 会变成 14 + 6）。
    """
    if times <= 0 or not extra:
        return expr
    if not expr:
        return extra
    parts = [parse(expr), parse(extra)]
    flat = parts[0].flat + parts[1].flat * times
    dice: list[Die] = list(parts[0].dice)
    for _ in range(times):
        dice.extend(parts[1].dice)
    return str(Dice(dice=tuple(dice), flat=flat))


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
