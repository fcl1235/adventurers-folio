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
from .text import join_list, tr

# 分句分隔符：中文全角分号，英文分号加空格。用「；」而不是 `join_list` 的「、」——
# 这里串起来的是**句子**（「回复 8 点生命；生命骰全回」），不是并列名词。
def _join_lines(lines: list[str], locale: str) -> str:
    sep = "；" if str(locale or "zh").lower().startswith("zh") else "; "
    return sep.join(lines)


def _display(key: str, names: Mapping[str, str] | None) -> str:
    """职业 / 资源池的显示名。

    规则层**不查内容**（C1 的同一口径：内核不认职业名，也就认不出「战士」），
    所以名字由上层用 `names` 传进来（`api/rest.py` 从 `ClassDef.name` 与
    `Pool.label` 取）。拿不到就退回 id 尾段 —— 宁可显示 `second_wind`，
    也不要显示一个编出来的中文名。
    """
    if names and key in names:
        return names[key]
    return str(key).split(".")[-1]


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
    # 句子在 `lines` 里已经按语言拼好了，`summary` 只需要知道用什么分隔符
    locale: str = "zh"

    @property
    def summary(self) -> str:
        return (_join_lines(self.lines, self.locale) if self.lines
                else tr("休息结束", self.locale))


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
    locale: str = "zh",
    names: Mapping[str, str] | None = None,
) -> RestResult:
    """短休。

    hit_dies：class_id → 生命骰面。兼职角色按各自骰面算。
    spend   ：总共花几颗生命骰；按职业顺序扣，扣完为止。
    rng     ：给了就逐颗掷骰，没给就取固定值（桌面常用）。
    names   ：class_id / 资源池 id → 显示名（见 `_display`）。
    """
    if spend < 0:
        raise RuleError(tr("花掉的生命骰不能为负", locale))
    root = actor.root()
    before = actor.hp.current
    lines: list[str] = []
    spent_total = 0
    root.marks.purge_rest()   # 与长休同一条：rest 作用域不过夜
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
        lines.append(tr("%s 生命骰 ×%d", locale) % (_display(class_id, names), usable))

    recovered = root.resources.short_rest_recover()
    if recovered:
        lines.append(tr("恢复资源：%s", locale) % join_list(
            ["%s +%d" % (_display(pool.id, names), delta) for pool, delta in recovered],
            locale))
    expired = _expire(actor, "short_rest")
    if expired:
        lines.append(tr("结束效果 %d 个", locale) % len(expired))
    if healed_total:
        lines.append(tr("回复 %d 点生命", locale) % healed_total)
    if not lines:
        lines.append(tr("短休结束，没有可恢复的内容", locale))

    return RestResult(
        kind="short_rest", hp_before=before, hp_after=actor.hp.current,
        dice_spent=spent_total, healed=healed_total,
        pools=tuple(pool.id for pool, _ in recovered), expired=tuple(expired),
        lines=lines, locale=locale,
    )


def long_rest(actor: Actor, locale: str = "zh",
              names: Mapping[str, str] | None = None) -> RestResult:
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
            regained_dice.append(pool.id)
            pool.refill()

    recovered = root.resources.refill_all()
    root.marks.purge_rest()      # 灵感这类「一小时内」的好东西撑不过一次休息
    # 创造的法术位（Refresh.VANISH）长休整池蒸发 —— 原文 "vanishes when you
    # finish a Long Rest"。恢复语义表达不了「消失」，所以是删除而不是清零。
    vanished = [pool_id for pool_id, pool in root.resources.pools.items()
                if pool.refresh.value == "vanish"]
    for pool_id in vanished:
        del root.resources.pools[pool_id]
    expired = _expire(actor, "long_rest")

    if healed:
        lines.append(tr("回复 %d 点生命", locale) % healed)
    if regained_dice:
        lines.append(tr("生命骰全回：%s", locale)
                     % join_list([_display(item, names) for item in regained_dice], locale))
    if recovered:
        lines.append(tr("资源回满：%s", locale) % join_list(
            ["%s +%d" % (_display(pool.id, names), delta) for pool, delta in recovered],
            locale))
    if expired:
        lines.append(tr("结束效果 %d 个", locale) % len(expired))
    if not lines:
        lines.append(tr("长休结束，没有需要恢复的内容", locale))

    return RestResult(
        kind="long_rest", hp_before=before, hp_after=pool_hp.current,
        pools=tuple(pool.id for pool, _ in recovered), expired=tuple(expired),
        lines=lines, locale=locale,
    )


def hit_dice_left(actor: Actor) -> int:
    root = actor.root()
    return sum(pool.available for pool in root.resources.pools.values()
               if pool.id.startswith("hit_dice."))
