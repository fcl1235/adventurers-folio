# -*- coding: utf-8 -*-
"""声明式条件求值：内容里写 {"raging": true}、{"d20_lte": 9}。

支持：
  直接比较   {"raging": true}
  后缀比较   {"hp_lte": 10} / {"level_gte": 5} / {"tag_in": ["undead"]}
  点路径     {"combat.has_advantage": true}
  组合       {"all": [...]} / {"any": [...]} / {"not": {...}}

缺失字段一律视为 False（内容里少写字段不该让整张卡崩）。
"""

from __future__ import annotations

import operator
from typing import Any, Mapping

from .errors import PredicateError

_COMPARE = {
    "gte": operator.ge,
    "lte": operator.le,
    "gt": operator.gt,
    "lt": operator.lt,
    "ne": operator.ne,
    "eq": operator.eq,
    "in": lambda actual, expected: actual in expected,
    "not_in": lambda actual, expected: actual not in expected,
    "contains": lambda actual, expected: expected in actual,
}

_MISSING = object()


def _lookup(path: str, ctx: Mapping[str, Any]) -> Any:
    node: Any = ctx
    for piece in path.split("."):
        if isinstance(node, Mapping):
            if piece not in node:
                return _MISSING
            node = node[piece]
        else:
            node = getattr(node, piece, _MISSING)
            if node is _MISSING:
                return _MISSING
    return node


def _split(key: str) -> tuple[str, str | None]:
    head, sep, last = key.rpartition("_")
    if sep and last in _COMPARE:
        return head, last
    return key, None


def evaluate(condition: Mapping[str, Any] | None, ctx: Mapping[str, Any]) -> bool:
    if condition is None:
        return True
    if not isinstance(condition, Mapping):
        raise PredicateError("条件必须是映射，实际为 %r" % (type(condition).__name__,))

    for key, expected in condition.items():
        if key == "all":
            if not all(evaluate(item, ctx) for item in expected):
                return False
            continue
        if key == "any":
            if not any(evaluate(item, ctx) for item in expected):
                return False
            continue
        if key == "not":
            if evaluate(expected, ctx):
                return False
            continue

        path, op = _split(key)
        actual = _lookup(path, ctx)
        if actual is _MISSING:
            return False
        if op is None:
            if actual != expected:
                return False
            continue
        try:
            if not _COMPARE[op](actual, expected):
                return False
        except TypeError as exc:
            raise PredicateError("条件 %r 类型不符：%s" % (key, exc))
    return True


def explain(condition: Mapping[str, Any] | None, ctx: Mapping[str, Any]) -> list[str]:
    """返回不满足的条目，给 UI 的「为什么点不了」用。"""
    if condition is None:
        return []
    if evaluate(condition, ctx):
        return []
    reasons = []
    for key, expected in condition.items():
        if key in ("all", "any", "not"):
            if not evaluate({key: expected}, ctx):
                reasons.append("%s 不满足" % key)
            continue
        path, op = _split(key)
        actual = _lookup(path, ctx)
        if actual is _MISSING:
            reasons.append("%s 缺失" % path)
        else:
            reasons.append("%s=%r 不满足 %s %r" % (path, actual, op or "==", expected))
    return reasons
