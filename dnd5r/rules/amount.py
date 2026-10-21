# -*- coding: utf-8 -*-
"""效果数值：把「1d10 + 战士等级」「5 × 等级」这类写法收成一个值对象。

内容里三种写法都合法：
  3                      常量
  "1d10"                 纯骰
  {dice: 1d10, plus: class_level, times: 1}   骰式 + 引用 + 乘数

`plus` / `times` 是符号引用（Ref），到执行期才求值 —— 所以
「回气加的是职业等级而不是总等级」这种事，在数据里就写死了，不靠代码判断。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from ..kernel.dice import Dice, RollResult, parse as parse_dice
from ..kernel.errors import DiceError, RuleError
from ..kernel.rng import Rng
from .modifiers import Ref, resolve_ref

# 允许出现在 plus / times 里的引用名（写错名字比算出错数更容易发现）
_GENERIC_REFS = (
    "class_level", "total_level", "prof", "prof_half", "prof_double",
    "ability.str", "ability.dex", "ability.con",
    "ability.int", "ability.wis", "ability.cha",
)


@dataclass(frozen=True, slots=True)
class Amount:
    """一个可求值的数量。dice 为空表示纯数值。"""

    dice: Dice | None = None
    flat: int = 0
    plus: Ref | None = None
    times: Ref | None = None

    def __post_init__(self) -> None:
        if self.dice is None and self.flat == 0 and self.plus is None:
            raise RuleError("Amount 至少要有一个来源（dice / flat / plus）")

    # --- 求值 ---------------------------------------------------------
    def roll(self, ctx: Mapping[str, Any], rng: Rng) -> tuple[int, RollResult | None]:
        """掷一次。返回 (总值, 掷骰明细)；纯数值时明细为 None。"""
        base = 0
        result = None
        if self.dice is not None:
            result = self.dice.roll(rng)
            base = result.total
        base += self.flat
        if self.plus is not None:
            base += resolve_ref(self.plus, ctx)
        if self.times is not None:
            base *= resolve_ref(self.times, ctx)
        return base, result

    def evaluate(self, ctx: Mapping[str, Any]) -> int:
        """不掷骰的上界求值（展示用：1d10 记 10）。"""
        base = self.dice.maximum if self.dice is not None else 0
        base += self.flat
        if self.plus is not None:
            base += resolve_ref(self.plus, ctx)
        if self.times is not None:
            base *= resolve_ref(self.times, ctx)
        return base

    @property
    def average(self) -> float:
        base = self.dice.average if self.dice is not None else 0
        return base + self.flat

    def describe(self, ctx: Mapping[str, Any] | None = None) -> str:
        """「1d10+3」「5×3」。ctx 缺失时引用部分按名字显示。"""
        bits = []
        if self.dice is not None:
            bits.append(str(self.dice))
        if self.flat:
            bits.append(str(self.flat))
        if self.plus is not None:
            value = resolve_ref(self.plus, ctx) if ctx is not None else None
            bits.append(str(value) if value is not None else self.plus.path)
        text = "+".join(bits) if bits else "0"
        if self.times is not None:
            value = resolve_ref(self.times, ctx) if ctx is not None else None
            text += "×%s" % (value if value is not None else self.times.path)
        return text

    def to_dict(self) -> dict:
        data: dict[str, Any] = {}
        if self.dice is not None:
            data["dice"] = str(self.dice)
        if self.flat:
            data["flat"] = self.flat
        if self.plus is not None:
            data["plus"] = self.plus.path
        if self.times is not None:
            data["times"] = self.times.path
        return data


def parse_amount(data: Any, where: str = "") -> Amount:
    prefix = ("%s: " % where) if where else ""
    if isinstance(data, bool):
        raise RuleError("%s数量不能是布尔值" % prefix)
    if isinstance(data, int):
        return Amount(flat=data)
    if isinstance(data, str):
        try:
            return Amount(dice=parse_dice(data))
        except DiceError as exc:
            raise RuleError("%s无法解析骰式 %r：%s" % (prefix, data, exc))
    if not isinstance(data, Mapping):
        raise RuleError("%s数量必须是整数、骰式字符串或映射，实际 %r" % (prefix, type(data).__name__))

    unknown = [key for key in data if key not in ("dice", "flat", "value", "plus", "times")]
    if unknown:
        raise RuleError("%s数量里有未知字段：%s" % (prefix, ", ".join(sorted(unknown))))

    dice = None
    if "dice" in data:
        raw = data["dice"]
        if isinstance(raw, int):
            raise RuleError("%s dice 要写骰式（如 1d10）而不是整数" % prefix)
        try:
            dice = parse_dice(str(raw))
        except DiceError as exc:
            raise RuleError("%s无法解析骰式 %r：%s" % (prefix, raw, exc))

    flat = data.get("flat", data.get("value", 0))
    if isinstance(flat, bool) or not isinstance(flat, int):
        raise RuleError("%s flat 必须是整数：%r" % (prefix, flat))

    return Amount(
        dice=dice,
        flat=flat,
        plus=_parse_ref(data.get("plus"), prefix),
        times=_parse_ref(data.get("times"), prefix),
    )


def _parse_ref(raw: Any, prefix: str) -> Ref | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise RuleError("%s引用必须是字符串：%r" % (prefix, raw))
    name = raw.strip().lower()
    if name not in _GENERIC_REFS and not name.startswith("speed."):
        raise RuleError(
            "%s未知引用 %r，可用：%s" % (prefix, raw, ", ".join(_GENERIC_REFS))
        )
    return Ref(name)


def ref_names() -> Tuple[str, ...]:
    return _GENERIC_REFS
