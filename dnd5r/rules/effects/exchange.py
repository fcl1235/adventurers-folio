# -*- coding: utf-8 -*-
"""Exchange：资源双向兑换（术法点 ↔ 法术位）。

为什么不是 SpendResource + RecoverResource 各写一条：兑换是**一件事**，
两条效果没法表达「点不够就一位都不扣」的原子性 —— 失败回滚是 use_power
给的，但成功时「扣了点、位没建出来」这种半截状态必须由原语自己保证。

两个方向（2024 原文，PHB Font of Magic）：

  slots_to_points  法术位化点：花掉指定环级的一个位，得等量术法点（无动作）
  points_to_slots  创造法术位：按表花点（2/3/5/6/7），附赠动作，长休消失，
                   且有「最低术士等级」门槛 —— 表写在内容里，内核不背数字

创造的位是 `Refresh.VANISH` 的独立池（dnd2024.slot.created.N）：长休整池蒸发，
不污染职业位表的容量 —— 池容量一旦被临时改动，长休回满就会把临时的位变永久。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar
from typing import Any, Mapping

from ...kernel.errors import IllegalAction, PluginError
from ...kernel.text import Text
from ...model.resources import Pool, PoolKind, Refresh
from ..spellcasting import spend_slot
from .base import Effect, EffectContext, register

DIRECTIONS = ("points_to_slots", "slots_to_points")
CREATED_PREFIX = "dnd2024.slot.created."


@dataclass(frozen=True, slots=True)
class ExchangeOption:
    """points_to_slots 的一档：花多少点、造几环的位、几级起可用。"""

    slot_level: int
    cost: int
    min_level: int

    def to_dict(self) -> dict:
        return {"slot_level": self.slot_level, "cost": self.cost,
                "min_level": self.min_level}


@dataclass(frozen=True, slots=True)
class Exchange(Effect):
    """兑换。`pool` 是点池的内容 id；`choice` 里带 slot_level（要造/要烧几环）。"""

    op: ClassVar[str] = "exchange"

    direction: str = "points_to_slots"
    pool: str = ""
    options: tuple[ExchangeOption, ...] = ()
    # slots_to_points 每烧一个位得几点：缺省 = 等于环级（魔法源泉）；
    # 写整数 = 固定量（灵感泉源「花任意一个位回一次灵感」是 1）
    gain: int = 0

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise PluginError("exchange 的 direction 只认 %s：%r"
                              % ("/".join(DIRECTIONS), self.direction))
        if not self.pool:
            raise PluginError("exchange 必须写 pool（点池的内容 id）")
        if self.direction == "points_to_slots" and not self.options:
            raise PluginError("points_to_slots 必须带兑换表 options")

    def apply(self, ctx: EffectContext) -> None:
        root = ctx.actor.root()
        scratch = dict(ctx.scratch)
        level = int(scratch.get("slot_level") or 0)
        if level < 1:
            raise IllegalAction("要选一个环级（choice: {\"slot_level\": N}）")

        if self.direction == "slots_to_points":
            self._slot_to_points(ctx, root, slot_lv=level)
        else:
            self._points_to_slot(ctx, root, level, scratch)

    # --- 位 → 点 --------------------------------------------------------
    def _slot_to_points(self, ctx: EffectContext, root, slot_lv: int) -> None:
        points = root.resources.get(self.pool)
        before = points.available
        # 花掉玩家指定环级的一个位（有账本却没这一环 → spend_slot 自己会拒绝）
        spend_slot(root, slot_lv)
        gained = int(self.gain) if int(self.gain) > 0 else int(slot_lv)
        points.recover(gained)
        ctx.note("把一个 %d 环法术位化作 %d 点%s（%d → %d）"
                 % (slot_lv, gained, points.label.zh or "点数",
                    before, points.available))

    # --- 点 → 位 --------------------------------------------------------
    def _points_to_slot(self, ctx: EffectContext, root, slot_lv: int,
                        scratch: Mapping[str, Any]) -> None:
        option = next((row for row in self.options if row.slot_level == slot_lv), None)
        if option is None:
            raise IllegalAction("造不出 %d 环法术位（可造：%s）"
                                % (slot_lv, "、".join(str(row.slot_level)
                                                      for row in self.options)))
        class_level = int(ctx.class_level or 0)
        if class_level < option.min_level:
            raise IllegalAction("%d 环法术位要术士等级 %d 起（当前 %d）"
                                % (slot_lv, option.min_level, class_level))
        points = root.resources.get(self.pool)
        if not points.can_spend(option.cost):
            raise IllegalAction("术法点剩 %d，造 %d 环法术位要 %d 点"
                                % (points.available, slot_lv, option.cost))
        points.spend(option.cost)

        pool_id = "%s%d" % (CREATED_PREFIX, slot_lv)
        existing = root.resources.pools.get(pool_id)
        if existing is not None:
            existing.raise_cap(existing.capacity + 1)   # 今天造第二个：叠一颗
            existing.refill()
        else:
            root.resources.add(Pool(
                id=pool_id, kind=PoolKind.SLOT, capacity=1,
                label=Text.of("创造的 %d 环法术位（长休消失）" % slot_lv,
                              "Created Level %d Slot (vanishes on Long Rest)" % slot_lv),
                refresh=Refresh.VANISH,
            ))
        ctx.note("花 %d 点造出一个 %d 环法术位（长休消失）"
                % (option.cost, slot_lv))

    def to_dict(self) -> dict:
        return {"direction": self.direction, "pool": self.pool,
                "options": [row.to_dict() for row in self.options],
                "gain": self.gain}

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "Exchange":
        if not isinstance(payload, Mapping):
            raise PluginError("%s 的 exchange 必须是映射" % where)
        options = []
        for row in payload.get("options") or ():
            options.append(ExchangeOption(
                slot_level=int(row["slot_level"]),
                cost=int(row["cost"]),
                min_level=int(row.get("min_level", 1)),
            ))
        return cls(
            direction=str(payload.get("direction", "points_to_slots")).lower(),
            pool=str(payload.get("pool", "")),
            options=tuple(options),
            gain=int(payload.get("gain", 0) or 0),
        )


register(Exchange)
