# -*- coding: utf-8 -*-
"""休息：短休与长休。

2024 的两条容易写错的规则，在这里定死：
  * 短休只恢复 `recover_on_short_rest` 明说的次数（回气 1 次），不是回满
  * 长休恢复**全部生命骰**（旧版是回一半），并回满所有非 NONE 资源池

休息是 ruleset 插件将来要覆盖的第一批机制，所以逻辑集中在两个函数里，
不散落到 UI 或职业模块。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..kernel.errors import RuleError
from ..kernel.rng import Rng
from ..model.actor import Actor
from ..model.effect_instance import ActiveEffect
from .health import hit_dice_average


@dataclass
class RestResult:
    kind: str
    hp_before: int
    hp_after: int
    dice_spent: int = 0
    healed: int = 0
    pools: tuple[str, ...] = ()
    expired: tuple[str, ...] = ()
    lines: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return "；".join(self.lines) if self.lines else "休息结束"


def _hit_die_pool(actor: Actor, class_id: str):
    pool_id = "hit_dice.%s" % class_id
    return actor.root().resources.get(pool_id) if actor.root().resources.has(pool_id) else None


def _expire(actor: Actor, kind: str) -> list[str]:
    """按休息类型清理持续效果。永久效果与职业资源不受影响。"""
    kept: list[ActiveEffect] = []
    gone: list[str] = []
    for effect in actor.effects:
        if effect.dies_at_rest(kind):
            gone.append(effect.id)
        else:
            kept.append(effect)
    actor.effects[:] = kept
    return gone


def short_rest(
    actor: Actor,
    hit_dies: Mapping[str, int],
    spend: int = 0,
    rng: Rng | None = None,
) -> RestResult:
    """短休。

    hit_dies：class_id → 生命骰面。兼职角色按各自骰面算。
    spend   ：总共花几颗生命骰；按职业顺序扣，扣完为止。
    rng     ：给了就逐颗掷骰，没给就取固定值（桌面常用）。
    """
    if spend < 0:
        raise RuleError("花掉的生命骰不能为负")
    root = actor.root()
    before = actor.hp.current
    lines: list[str] = []
    spent_total = 0
    healed_total = 0
    con_mod = actor.statblock.abilities.mod("con")

    remaining = int(spend)
    for class_id, sides in hit_dies.items():
        if remaining <= 0:
            break
        pool = _hit_die_pool(actor, class_id)
        if pool is None:
            continue
        usable = min(pool.available, remaining)
        if usable <= 0:
            continue
        pool.spend(usable)
        spent_total += usable
        healed_here = 0
        for _ in range(usable):
            roll = rng.randint(1, int(sides)) if rng is not None else hit_dice_average(int(sides))
            healed_here += max(1, roll + con_mod)
        healed_total += actor.hp.heal(healed_here)
        remaining -= usable
        lines.append("%s 生命骰 ×%d" % (class_id.split(".")[-1], usable))

    recovered = root.resources.short_rest_recover()
    if recovered:
        lines.append("恢复资源：" + "、".join(
            "%s +%d" % (pool.id.split(".")[-1], delta) for pool, delta in recovered))
    expired = _expire(actor, "short_rest")
    if expired:
        lines.append("结束效果 %d 个" % len(expired))
    if healed_total:
        lines.append("回复 %d 点生命" % healed_total)
    if not lines:
        lines.append("短休结束，没有可恢复的内容")

    return RestResult(
        kind="short_rest", hp_before=before, hp_after=actor.hp.current,
        dice_spent=spent_total, healed=healed_total,
        pools=tuple(pool.id for pool, _ in recovered), expired=tuple(expired),
        lines=lines,
    )


def long_rest(actor: Actor) -> RestResult:
    """长休：HP 与临时 HP 归位、生命骰全回、所有非 NONE 资源池回满。"""
    root = actor.root()
    before = actor.hp.current
    lines: list[str] = []

    pool_hp = root.hp
    healed = max(0, pool_hp.maximum - pool_hp.current)
    pool_hp.current = pool_hp.maximum
    pool_hp.temp = 0

    regained_dice = []
    for pool in root.resources.pools.values():
        if pool.id.startswith("hit_dice.") and pool.used:
            regained_dice.append(pool.id.split(".")[-1])
            pool.refill()

    recovered = root.resources.refill_all()
    expired = _expire(actor, "long_rest")

    if healed:
        lines.append("回复 %d 点生命" % healed)
    if regained_dice:
        lines.append("生命骰全回：%s" % "、".join(regained_dice))
    if recovered:
        lines.append("资源回满：%s" % "、".join(
            "%s +%d" % (pool.id.split(".")[-1], delta) for pool, delta in recovered))
    if expired:
        lines.append("结束效果 %d 个" % len(expired))
    if not lines:
        lines.append("长休结束，没有需要恢复的内容")

    return RestResult(
        kind="long_rest", hp_before=before, hp_after=pool_hp.current,
        pools=tuple(pool.id for pool, _ in recovered), expired=tuple(expired),
        lines=lines,
    )


def hit_dice_left(actor: Actor) -> int:
    root = actor.root()
    return sum(pool.available for pool in root.resources.pools.values()
               if pool.id.startswith("hit_dice."))
