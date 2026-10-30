# -*- coding: utf-8 -*-
"""死亡豁免（2024）。

在桌上最容易记错的三条，在这里定死：
  * **10 以上算成功**（含 10，不是「大于 10」）
  * **自然 1 记两次失败**（不是一次，也不是直接死）
  * **自然 20 直接回 1 HP 并结束濒死**（不是「算一次成功」）
另外：死亡豁免**不吃任何加值**，也不受力竭影响 —— 它掷的是「命」而不是「检定」，
所以这里刻意不走 `Resolver`。写成 `roll + con_mod` 是最常见的那种错。
"""

from __future__ import annotations

from ..kernel.rng import Rng
from ..model.death import DEAD_AT, STABLE_AT, DeathSaves

DC = 10
REVIVE_ROLL = 20

OUTCOME_ONGOING = "ongoing"
OUTCOME_STABLE = "stable"
OUTCOME_DEAD = "dead"
OUTCOME_REVIVED = "revived"

OUTCOME_ZH = {
    OUTCOME_ONGOING: "还在濒死",
    OUTCOME_STABLE: "已稳定",
    OUTCOME_DEAD: "已死亡",
    OUTCOME_REVIVED: "回魂（1 HP）",
}


def resolve_death_save(saves: DeathSaves, roll: int) -> dict:
    """把一次 d20 结果记进 `saves`，返回这次发生了什么。

    副作用限定在 `saves` 里；HP 的变化（自然 20 回 1 点）由调用方做 ——
    `DeathSaves` 够不着 `HpPool`，也不该够得着。
    """
    roll = int(roll)
    if not 1 <= roll <= 20:
        raise ValueError("死亡豁免的 d20 落在 1–20 之外：%r" % (roll,))
    if saves.dead or saves.stable:
        # 记分已经终止，再掷不该把结果改回去（否则玩家连掷就能「复活」）
        return _summary(roll, False, OUTCOME_DEAD if saves.dead else OUTCOME_STABLE, saves)

    if roll == REVIVE_ROLL:
        saves.reset()
        return _summary(roll, True, OUTCOME_REVIVED, saves)
    if roll == 1:
        saves.add_failure(2)
    elif roll >= DC:
        saves.add_success(1)
    else:
        saves.add_failure(1)

    if saves.dead:
        outcome = OUTCOME_DEAD
    elif saves.stable:
        outcome = OUTCOME_STABLE
    else:
        outcome = OUTCOME_ONGOING
    return _summary(roll, roll >= DC, outcome, saves)


def _summary(roll: int, success: bool, outcome: str, saves: DeathSaves) -> dict:
    return {
        "roll": roll,
        "success": success,
        "outcome": outcome,
        "label": OUTCOME_ZH[outcome],
        "succeeded": saves.succeeded,
        "failed": saves.failed,
        "succeeded_of": STABLE_AT,
        "failed_of": DEAD_AT,
        "revived": outcome == OUTCOME_REVIVED,
    }


def roll_death_save(saves: DeathSaves, rng: Rng) -> dict:
    """掷一次并记账。骰点走 rng 参数（C4：只有 kernel/rng.py 能 import random）。"""
    from ..kernel.dice import roll_d20
    return resolve_death_save(saves, roll_d20(rng).total)
