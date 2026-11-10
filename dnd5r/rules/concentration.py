# -*- coding: utf-8 -*-
"""专注的规则：开始 / 结束 / 受伤豁免。

一句话版本：**同一时刻只有一条专注**。开始新的专注法术，旧的那条立刻中断；
受伤掷体质豁免，失败也中断。这两件事以前在这套代码里都不存在 ——
`api/state.py` 只有一个算 DC 的函数，`SpellDef.concentration` 只决定报告上
印不印「专注」两个字，谁也没记「现在到底在专注什么」。

规则层的本分（C1）：这里**不认识任何法术**。条目由上层拿 `SpellDef` 拼好传进来；
本模块只管「换掉一条记录」与「DC / 成败」这两件纯算术。
"""

from __future__ import annotations

from ..kernel.errors import RuleError
from ..model.actor import Actor
from ..model.concentration import Concentration
from .text import tr

__all__ = [
    "CONCENTRATION_MIN_DC", "current", "begin", "end", "dc_for", "keeps", "label",
    "reminder",
]

# 专注豁免 DC = max(10, 伤害 // 2)。下限 10 是原文给的，不是「顺手取整」。
CONCENTRATION_MIN_DC = 10


def current(actor: Actor) -> Concentration | None:
    """此刻在专注什么。读 `root()`：变形层是临时外壳，专注是施法者的。"""
    return actor.root().concentration


def begin(actor: Actor, entry: Concentration) -> Concentration | None:
    """开始专注。返回**被顶掉的旧专注**（没有就是 None）。

    返回值必须被调用方用上：静默换掉一条专注，玩家会以为自己还在专注祝福，
    实际已经在专注别的法术了。这是典型的「程序没报错、桌上出争议」。
    """
    if not isinstance(entry, Concentration):
        raise RuleError("专注记录必须是 Concentration：%r" % (entry,))
    root = actor.root()
    old = root.concentration
    root.concentration = entry
    return old


def end(actor: Actor) -> Concentration | None:
    """中断专注，返回被中断的那一条（本来没在专注则 None）。"""
    root = actor.root()
    old = root.concentration
    root.concentration = None
    return old


def dc_for(damage: int) -> int:
    """受伤后的专注豁免 DC。**伤害为 0 也按 10 算** —— 下限就是 10。"""
    try:
        amount = int(damage)
    except (TypeError, ValueError):
        raise RuleError("伤害必须是整数：%r" % (damage,))
    if amount < 0:
        raise RuleError("伤害不能为负：%r" % (amount,))
    return max(CONCENTRATION_MIN_DC, amount // 2)


def keeps(total: int, dc: int) -> bool:
    """掷出 `total` 是否保住专注（达到 DC 即成功）。"""
    return int(total) >= int(dc)


def label(entry: Concentration, locale: str = "zh") -> str:
    """「《祝福》（1 环）」/「"Bless" (level 1)」。戏法单独说，不写「0 环」。

    放在规则层而不是界面：施法报告（`rules/combat.py`）与状态页要写同一句话，
    两处各拼一次，迟早会出现「卡上写 1 环、记录里写 0 环」。
    """
    name = entry.name(locale)
    if int(entry.level) <= 0:
        return tr("《%s》（戏法）", locale) % name
    return tr("《%s》（%d 环）", locale) % (name, int(entry.level))


def reminder(actor: Actor | None, damage: int, locale: str = "zh") -> dict | None:
    """「你打中的这个人在专注，它得掷 DC N」—— 命中/伤害结算后给 DM 的提醒。

    引擎**不替目标掷**：那是它的骰子，加值也在它卡上，坐在这一侧掷等于替玩家
    作弊。这里只把该掷的 DC 算出来，剩下的交给 `concentration_save`。
    伤害 ≤ 0（全被免疫吃掉）不算受伤，不提醒。
    """
    if actor is None or int(damage) <= 0:
        return None
    entry = current(actor)
    if entry is None:
        return None
    dc = dc_for(damage)
    text = label(entry, locale)
    return {
        "spell": entry.to_dict(),
        "label": text,
        "dc": dc,
        "line": tr("目标正在专注%s：它要掷 DC %d 的体质豁免", locale) % (text, dc),
    }
