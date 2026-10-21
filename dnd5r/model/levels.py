# -*- coding: utf-8 -*-
"""两个「等级」是不同的东西（约束 C8）。

TotalLevel  角色总等级：只能用来算熟练加值、戏法伤害档位
ClassLevel  某个职业的等级：特性解锁、资源次数、偷袭骰、属性提升

它们是 NewType，运行期只是 int，所以这里额外提供校验函数；
静态检查由 tools/lint_layers.py 的 C8 规则守住。
"""

from __future__ import annotations

from typing import Iterable, NewType

from ..kernel.errors import RuleError

TotalLevel = NewType("TotalLevel", int)
ClassLevel = NewType("ClassLevel", int)


def as_class_level(value: int) -> ClassLevel:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuleError("职业等级必须是整数：%r" % (value,))
    if value < 1:
        raise RuleError("职业等级必须 >= 1：%r" % (value,))
    return ClassLevel(value)


def as_total_level(value: int) -> TotalLevel:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuleError("总等级必须是整数：%r" % (value,))
    if value < 1:
        raise RuleError("总等级必须 >= 1：%r" % (value,))
    return TotalLevel(value)


def sum_levels(values: Iterable[ClassLevel]) -> TotalLevel:
    return TotalLevel(sum(int(v) for v in values))
