# -*- coding: utf-8 -*-
"""状态中文名。**属于界面文案，不属于规则**（C1：内核不认识「倒地」这个词）。

15 条标准状态里**力竭不在这里** —— 它有自己的 0–6 级阶梯，
再列一个勾选框就会出现「勾了力竭但等级是 0」这种自相矛盾的状态。
"""

from __future__ import annotations

# (id, 中文)。顺序按「桌上最常勾的靠前」，不是字母序。
CONDITIONS: tuple[tuple[str, str], ...] = (
    ("prone", "倒地"),
    ("grappled", "擒抱"),
    ("restrained", "束缚"),
    ("frightened", "恐惧"),
    ("poisoned", "中毒"),
    ("blinded", "目盲"),
    ("charmed", "魅惑"),
    ("deafened", "耳聋"),
    ("invisible", "隐形"),
    ("incapacitated", "失能"),
    ("stunned", "震慑"),
    ("paralyzed", "麻痹"),
    ("petrified", "石化"),
    ("unconscious", "昏迷"),
)

_ZH = dict(CONDITIONS)

# 内容包自己造的临时状态（狂暴、隐匿……）没有中文名。**不要硬翻**：
# 宁可把 id 原样显示，也好过把 "raging" 翻成「愤怒」让玩家对不上原文。
EXHAUSTION_ID = "exhaustion"


def name_of(condition_id: str) -> str:
    return _ZH.get(condition_id, condition_id)


def label_list(ids) -> str:
    """把一组 id 变成一行「倒地、恐惧」；空集合给空串（由调用方决定写不写「无」）。"""
    return "、".join(name_of(item) for item in ids)
