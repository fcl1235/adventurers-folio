# -*- coding: utf-8 -*-
"""专注的门面：现在在专注什么 / 受伤掷豁免 / 主动结束。

这个文件补的是一个**断了一半的通道**。之前 `api/state.py` 只有
`concentration_dc(damage)`：能算 DC，但没有任何地方记「此刻在专注哪一道」。
后果不是「少个数字」，而是三条规则同时失效：

  * 开始第二条专注法术时，第一条不会中断（桌上会变成两条同时生效）；
  * 受伤掷完 DC，没有一条记录可以被「打断」；
  * 角色卡上永远看不出自己在专注 —— 关掉程序再打开更不用说。

判定本身不在这里：掷骰走 `api/combat.roll_check`，它和角色卡用同一个
`Resolver`（卡上体质豁免 +5、掷的时候 +3 是这类代码最难发现的错）。
"""

from __future__ import annotations

from typing import Any

from ..content import ContentBundle
from ..kernel.rng import Rng
from ..model.actor import Actor
from ..model.concentration import Concentration
from ..rules import concentration as rules
from ..rules.text import tr
from .combat import roll_check

__all__ = [
    "concentration_view", "concentration_save", "end_concentration",
    "concentration_label",
]


def concentration_label(entry: Concentration, locale: str = "zh") -> str:
    """「《祝福》（1 环）」/「"Bless" (level 1)」。戏法单独说，不写「0 环」。

    拼法在 `rules/concentration.label` —— 施法报告与状态页写的是同一句。
    """
    return rules.label(entry, locale)


def concentration_view(actor: Actor, locale: str = "zh") -> dict[str, Any]:
    """给界面读的专注状态。`active=False` 时 `spell` 是 None，不是空字典 ——
    空字典会让界面「取 spell.name 没 KeyError」地静默画出空白行。"""
    entry = rules.current(actor)
    if entry is None:
        return {"active": False, "spell": None, "label": "",
                "text": tr("当前没有在专注任何法术", locale)}
    label = concentration_label(entry, locale)
    return {"active": True, "spell": entry.to_dict(), "label": label, "text": label}


def concentration_save(
    actor: Actor,
    content: ContentBundle,
    damage: int,
    rng: Rng | None = None,
    locale: str = "zh",
) -> dict[str, Any]:
    """受伤后的专注豁免。**失败就真的中断**，并把断掉的那道法术报回来。

    没在专注任何法术时仍然掷一次（桌上 DM 常想先看看豁免结果），但报告里
    `active=False`、`line` 明说这次掷骰不会中断任何东西 —— 不假装做了件事。

    返回值里的 `roll` 是 `api.roll_check` 的原样结果，界面用同一套格式化
    （优势/劣势、明细都在里面），不自己再算一遍加值。
    """
    dc = rules.dc_for(damage)
    entry = rules.current(actor)
    roll = roll_check(actor, content, "save", "con", rng=rng, locale=locale)
    kept = rules.keeps(roll["total"], dc)
    broken: Concentration | None = None
    if entry is not None and not kept:
        broken = rules.end(actor)
    if entry is None:
        line = tr("没有在专注任何法术（这次只掷体质豁免，不会中断任何东西）", locale)
    elif kept:
        line = tr("专注检定 DC %d → %d，保持专注", locale) % (dc, roll["total"])
    else:
        line = tr("专注检定 DC %d → %d，专注打断（《%s》）", locale) % (
            dc, roll["total"], broken.name(locale) if broken else "")
    return {
        "dc": int(dc),
        "roll": roll,
        "total": int(roll["total"]),
        "kept": bool(kept),
        # 「掷之前有没有在专注」。没在专注时 kept 无意义，界面据 active 说话。
        "active": entry is not None,
        "spell": entry.to_dict() if entry is not None else None,
        "broken": broken.to_dict() if broken is not None else None,
        "line": line,
        "view": concentration_view(actor, locale),
    }


def end_concentration(actor: Actor, locale: str = "zh") -> dict[str, Any]:
    """主动结束专注（换法术、想留个附赠动作、或单纯想撤掉增益）。"""
    entry = rules.end(actor)
    if entry is None:
        line = tr("当前没有在专注任何法术", locale)
    else:
        line = tr("结束专注《%s》", locale) % entry.name(locale)
    return {
        "spell": entry.to_dict() if entry is not None else None,
        "label": concentration_label(entry, locale) if entry is not None else "",
        "line": line,
        "view": concentration_view(actor, locale),
    }
