# -*- coding: utf-8 -*-
"""把 Actor 的当前状态装进 `RefContext`，造出一个 Resolver。

`Resolver` 自己**不读内容**（它只吃 Modifier），但**造**它必须读 ——
无甲 / 持盾这些事实要看装备槽里的 id 与形态，护甲要查内容里的护甲表。
所以这一步单独放一层，别塞回 Resolver 里。

这段装配原先在 api 与 session 里各写了一遍；施法结算又要用第三次，
于是收到这里。三份各写一遍的后果不是代码丑，而是**其中一个忘了传护甲**，
于是同一个角色在界面上 AC 15、结算时按 12 算 —— 最难发现的那种错。
"""

from __future__ import annotations

from typing import Mapping

from ..model.actor import Actor
from ..model.levels import ClassLevel, TotalLevel
from .armor import loadout_for
from .contributions import facts_for
from .progression import proficiency_bonus
from .resolver import RefContext, Resolver

__all__ = ["resolver_for"]


def resolver_for(
    actor: Actor,
    armors: Mapping | None = None,
) -> Resolver:
    """派生值求解器。给了护甲表才会读装备（护甲 / 盾）与真实的无甲事实。

    `armors` 是内容里的护甲表（id → 定义）；缺省空表 = 当作没穿任何护甲，
    而不是报错 —— 怪物、召唤物、没有装备概念的对象都要能算 AC。
    """
    profile = actor.profile
    total = profile.total if profile else TotalLevel(1)
    class_level = None
    if profile and len(profile.classes) == 1:
        class_level = ClassLevel(int(profile.classes[0].class_level))
    top = actor.top()
    loadout = loadout_for(actor, armors or {})
    return Resolver(RefContext(
        prof_bonus=proficiency_bonus(total),
        total_level=total,
        class_level=class_level,
        abilities=top.statblock.abilities,
        speeds=dict(top.statblock.speeds),
        facts=facts_for(actor, class_level, loadout),
    ))
