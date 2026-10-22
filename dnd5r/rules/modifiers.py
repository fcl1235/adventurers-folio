# -*- coding: utf-8 -*-
"""Modifier 管道：取代「一堆 if 与 hook」的核心抽象。

一条 Modifier 只说三件事：改什么（target）、怎么叠（stack）、谁给的（source）。
resolve() 返回带明细的总值，所以「16 = 13 皮甲 + 2 敏捷 + 1 风格」是结构产物，
不需要再手写 ac_breakdown。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..kernel.dice import Dice
from ..kernel.errors import RuleError
from ..kernel.predicate import evaluate as eval_when


class Stack(str, Enum):
    ADD = "add"
    MAX = "max"
    MIN = "min"
    SET = "set"


class Scope(str, Enum):
    SELF = "self"            # 只影响自己
    AURA = "aura"            # 光环：影响范围内友军（半径由 power 声明）
    ALLY = "ally"            # 指定友军
    ATTACKERS = "attackers"  # 影响「打我的那些人」


class Direction(str, Enum):
    GIVEN = "given"   # 我给出去的（我的攻击加值、我给敌人的优势）
    TAKEN = "taken"   # 我承受的（来袭优势、对我的减伤）


@dataclass(frozen=True, slots=True)
class Ref:
    """符号引用：值要到解析期才知道。

    支持：prof / prof/2 / prof*2 / total_level / class_level
          ability.<str|dex|con|int|wis|cha> / speed.<walk|fly|swim|climb>
    """

    path: str

    def __post_init__(self) -> None:
        if not self.path:
            raise RuleError("Ref.path 不能为空")


@dataclass(frozen=True, slots=True)
class Modifier:
    target: str
    # 整数 / 骰 / 符号引用 / Amount（「魅力调整值，最低 +1」这类带下限的值）
    value: Any
    stack: Stack = Stack.ADD
    source: str = ""
    scope: Scope = Scope.SELF
    direction: Direction = Direction.GIVEN
    when: Mapping[str, Any] | None = None
    # 只对 `score.<属性>` 生效：属性加值能顶到的上限（原始冠军 / 身心合一写 25）。
    # resolve() 不读它 —— 属性值不走 d20 管道，见 rules/contributions.py。
    cap: int | None = None

    def __post_init__(self) -> None:
        if not self.target:
            raise RuleError("Modifier.target 不能为空")
        if not isinstance(self.stack, Stack):
            raise RuleError("stack 必须是 Stack：%r" % (self.stack,))
        if not isinstance(self.scope, Scope):
            raise RuleError("scope 必须是 Scope：%r" % (self.scope,))
        if not isinstance(self.direction, Direction):
            raise RuleError("direction 必须是 Direction：%r" % (self.direction,))
        if self.cap is not None:
            if not isinstance(self.cap, int) or isinstance(self.cap, bool):
                raise RuleError("Modifier.cap 必须是整数：%r" % (self.cap,))
            if self.cap < 1:
                raise RuleError("Modifier.cap 至少是 1：%r" % (self.cap,))
            if not self.target.startswith("score."):
                raise RuleError(
                    "Modifier.cap 只对 score.<属性> 有意义，%r 请改用其他字段" % self.target
                )

    def describe_value(self) -> str:
        if isinstance(self.value, Ref):
            return self.value.path
        describe = getattr(self.value, "describe", None)
        if callable(describe) and not isinstance(self.value, (int, Dice)):
            return describe()
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Term:
    value: int
    stack: Stack
    source: str


@dataclass(frozen=True, slots=True)
class Resolution:
    total: int
    terms: tuple[Term, ...] = ()
    # 基础值的名字（"DEX" / "皮甲"）。空 = 显示「基础」。
    # 没有它，明细从「6 = 3 +3 熟练」读不出那个 3 是什么 —— 数字对了但看不懂。
    base_label: str = ""

    def describe(self) -> str:
        """「16 = 13 皮甲 + 2 敏捷 + 1 风格」

        不是加法的项要写清语义：MAX/MIN 是「取高／取低」而不是加减
        —— 重击门槛写 19 和 18，合计是 18，写成「+19 +18」会算成 57。
        """
        if not self.terms:
            return str(self.total)
        if len(self.terms) == 1 and self.terms[0].source == "@base":
            # 只有基础值时也要说清「这个 3 是什么」—— 否则未熟练的技能只显示一个数
            if self.base_label:
                return "%d = %d %s" % (self.total, self.total, self.base_label)
            return str(self.total)
        bits = []
        for term in self.terms:
            if term.source == "@base":
                source = self.base_label or "基础"
            else:
                source = term.source.lstrip("@")
            if term.stack is Stack.MAX:
                bits.append("取高 %d %s" % (term.value, source))
            elif term.stack is Stack.MIN:
                bits.append("取低 %d %s" % (term.value, source))
            else:
                sign = "+" if term.value >= 0 else "-"
                bits.append("%s%d %s" % (sign, abs(term.value), source))
        head = bits[0] if self.terms[0].stack is not Stack.ADD else bits[0].lstrip("+")
        return "%d = %s" % (self.total, " ".join([head] + bits[1:]).lstrip("+").strip())

    def sources(self) -> tuple[str, ...]:
        return tuple(term.source for term in self.terms)


def _numeric(mod: Modifier, ctx: Mapping[str, Any] | None) -> int:
    value = mod.value
    if isinstance(value, Ref):
        if ctx is None:
            raise RuleError("Modifier %s 用了符号引用 %s，但解析时没有上下文" % (mod.target, value.path))
        return resolve_ref(value, ctx)
    if isinstance(value, Dice):
        raise RuleError("骰值不能进入数值合计：%s（伤害骰请走 damage 管道）" % mod.target)
    if isinstance(value, bool):
        raise RuleError("Modifier 值不能是布尔：%r" % (value,))
    if isinstance(value, int):
        return value
    evaluate = getattr(value, "evaluate", None)
    if callable(evaluate):          # Amount：带骰/引用/下限的数量
        return int(evaluate(ctx or {}))
    raise RuleError("Modifier 值必须是整数、Dice、Ref 或 Amount：%r" % (value,))


def resolve(
    modifiers: Iterable[Modifier],
    base: int = 0,
    ctx: Mapping[str, Any] | None = None,
    base_label: str = "",
) -> Resolution:
    """按 SET → ADD → MAX/MIN 的顺序合成。

    多个 SET 值不一致视为数据错误 —— 这正是「无甲防御只能选一个」该报错的地方。
    """
    active = [mod for mod in modifiers if eval_when(mod.when, ctx or {})]

    set_terms = [mod for mod in active if mod.stack is Stack.SET]
    if set_terms:
        values = {_numeric(mod, ctx) for mod in set_terms}
        if len(values) > 1:
            raise RuleError(
                "多个互斥的 SET 冲突：%s（来源 %s）"
                % (sorted(values), ", ".join(mod.source or "?" for mod in set_terms))
            )
        total = _numeric(set_terms[-1], ctx)
        terms = [Term(total, Stack.SET, set_terms[-1].source or "@set")]
    else:
        total = base
        terms = [Term(base, Stack.SET, "@base")] if base else []

    for mod in active:
        if mod.stack is Stack.SET:
            continue
        value = _numeric(mod, ctx)
        if mod.stack is Stack.ADD:
            total += value
            terms.append(Term(value, Stack.ADD, mod.source or "@add"))
        elif mod.stack is Stack.MAX:
            if value > total:
                total = value
            terms.append(Term(value, Stack.MAX, mod.source or "@max"))
        elif mod.stack is Stack.MIN:
            if value < total:
                total = value
            terms.append(Term(value, Stack.MIN, mod.source or "@min"))

    return Resolution(total=total, terms=tuple(terms), base_label=base_label)


def resolve_ref(ref: Ref | str, ctx: Mapping[str, Any]) -> int:
    path = ref.path if isinstance(ref, Ref) else str(ref)
    key = path.replace(" ", "").lower()

    if key == "prof":
        return _need(ctx, "prof_bonus")
    if key in ("prof/2", "prof_half", "proficiency/2"):
        return _need(ctx, "prof_bonus") // 2
    if key in ("prof*2", "prof_double", "proficiency*2"):
        return _need(ctx, "prof_bonus") * 2
    if key in ("total_level", "level"):
        return _need(ctx, "total_level")
    if key == "class_level":
        value = ctx.get("class_level")
        if value is None:
            raise RuleError("符号引用 class_level 在无职业上下文中不可用")
        return int(value)

    head, _, tail = key.partition(".")
    if head == "ability" and tail:
        abilities = ctx.get("abilities")
        if abilities is None:
            raise RuleError("符号引用 ability.%s 缺少 abilities 上下文" % tail)
        return abilities.mod(tail)
    if head == "speed" and tail:
        speeds = ctx.get("speeds") or {}
        if tail not in speeds:
            raise RuleError("符号引用 speed.%s 不存在" % tail)
        return int(speeds[tail])

    raise RuleError("未知符号引用：%r" % path)


def _need(ctx: Mapping[str, Any], key: str) -> int:
    if key not in ctx:
        raise RuleError("符号引用缺少上下文 %r" % key)
    return int(ctx[key])


def group_by_target(modifiers: Iterable[Modifier]) -> dict[str, list[Modifier]]:
    grouped: dict[str, list[Modifier]] = {}
    for mod in modifiers:
        grouped.setdefault(mod.target, []).append(mod)
    return grouped
