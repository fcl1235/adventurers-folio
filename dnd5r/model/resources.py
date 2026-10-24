# -*- coding: utf-8 -*-
"""资源池：次数（charge）、点数（point）、法术位（slot_level）、骰池（dice）。

设计要点（见 §11 G3/G15）：
  * 一个池可以被多个能力共用（引导神力、气）
  * 池必须标 owner_class，兼职时次数按本职业等级算，不能按总等级
  * 游荡者没有任何池 —— 所以「零资源」必须合法
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..kernel.errors import IllegalAction, RuleError
from ..kernel.text import Text


class PoolKind(str, Enum):
    CHARGE = "charge"           # 固定次数：狂暴、荒野变形
    POINT = "point"             # 点数池：气、圣疗、术法点
    SLOT = "slot"               # 单个法术位：1 环 4 个就是 4 次
    SLOT_LEVEL = "slot_level"   # 环级预算：奥术回想
    DICE = "dice"               # 骰池：偷袭骰、灵感骰


class Refresh(str, Enum):
    NONE = "none"               # 不自动恢复
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"
    ENCOUNTER = "encounter"
    # 长休**蒸发**（不是恢复）：创造出来的法术位这类「临时获得」的池。
    # 与 NONE 的区别：NONE 是「永远不回」，VANISH 是「长休连池一起消失」。
    VANISH = "vanish"


@dataclass
class Pool:
    id: str
    kind: PoolKind
    capacity: int
    label: Text | None = None
    used: int = 0
    owner_class: str | None = None
    refresh: Refresh = Refresh.LONG_REST
    # 2024 的「短休恢复 1 次」不能靠 refresh 表达：回气是短休回 1、长休全回
    recover_on_short_rest: int = 0
    # 「这道法术可免法术位施放一次」—— 次数**绑在具体法术上**（妖精触碰的
    # 「两道法术各一次」）。空 = 通用池，谁都能花。有两个名字是为了两种查询
    # 都便宜：按法术找（施法时该不该扣）、按来源找（界面上归到哪个专长）。
    spell: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if self.capacity < 0:
            raise RuleError("资源容量不能为负：%s=%d" % (self.id, self.capacity))
        if not isinstance(self.kind, PoolKind):
            raise RuleError("资源类型必须是 PoolKind：%r" % (self.kind,))
        if not isinstance(self.refresh, Refresh):
            raise RuleError("恢复方式必须是 Refresh：%r" % (self.refresh,))
        # 绑定法术的池只能是「次数」：把它做成点数池，界面上会冒出
        # 「1/3 点 迷踪步」这种规则里不存在的东西
        if self.spell and self.kind is not PoolKind.CHARGE:
            raise RuleError("绑定法术的池只能是次数池：%s" % self.id)

    def pays_for(self, spell_id: str) -> bool:
        """这个池能不能替某道法术付账（不看余量）。"""
        return bool(self.spell) and self.spell == spell_id

    @property
    def available(self) -> int:
        return max(0, self.capacity - self.used)

    def can_spend(self, amount: int = 1) -> bool:
        return 0 < amount <= self.available

    def spend(self, amount: int = 1) -> int:
        if amount <= 0:
            raise RuleError("花费必须为正：%r" % (amount,))
        if amount > self.available:
            raise IllegalAction("%s 剩余 %d，不足 %d" % (self.id, self.available, amount))
        self.used += amount
        return self.available

    def recover(self, amount: int) -> int:
        if amount < 0:
            raise RuleError("恢复量不能为负：%r" % (amount,))
        self.used = max(0, self.used - amount)
        return self.used

    def refill(self) -> None:
        self.used = 0

    def raise_cap(self, new_capacity: int) -> None:
        if new_capacity < 0:
            raise RuleError("资源容量不能为负")
        self.capacity = new_capacity
        self.used = min(self.used, new_capacity)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind.value, "capacity": self.capacity,
            "used": self.used, "owner_class": self.owner_class,
            "refresh": self.refresh.value,
            "recover_on_short_rest": self.recover_on_short_rest,
            "spell": self.spell, "source": self.source,
        }


@dataclass
class ResourcePool:
    pools: dict[str, Pool] = field(default_factory=dict)

    def add(self, pool: Pool) -> Pool:
        if pool.id in self.pools:
            raise RuleError("资源池重复：%s" % pool.id)
        self.pools[pool.id] = pool
        return pool

    def get(self, pool_id: str) -> Pool:
        if pool_id not in self.pools:
            raise RuleError("没有资源池：%s" % pool_id)
        return self.pools[pool_id]

    def has(self, pool_id: str) -> bool:
        return pool_id in self.pools

    def spend(self, pool_id: str, amount: int = 1) -> Pool:
        pool = self.get(pool_id)
        pool.spend(amount)
        return pool

    def recover(self, pool_id: str, amount: int) -> Pool:
        pool = self.get(pool_id)
        pool.recover(amount)
        return pool

    def refill(self, refresh: Refresh) -> list[Pool]:
        touched = []
        for pool in self.pools.values():
            if pool.refresh == refresh:
                pool.refill()
                touched.append(pool)
        return touched

    def refill_all(self, include_encounter: bool = False) -> list[tuple["Pool", int]]:
        """长休：除 NONE 之外全部回满。生命骰另有规则，这里跳过。"""
        touched: list[tuple[Pool, int]] = []
        for pool in self.pools.values():
            if pool.refresh is Refresh.NONE:
                continue
            if pool.refresh is Refresh.ENCOUNTER and not include_encounter:
                continue
            if pool.id.startswith("hit_dice."):
                continue
            delta = pool.used
            if not delta:
                continue
            pool.refill()
            touched.append((pool, delta))
        return touched

    def short_rest_recover(self) -> list[tuple["Pool", int]]:
        """短休：SHORT_REST 池回满，其余按 recover_on_short_rest 回几次。"""
        touched: list[tuple[Pool, int]] = []
        for pool in self.pools.values():
            if pool.refresh is Refresh.SHORT_REST:
                delta = pool.used
                if delta:
                    pool.refill()
                    touched.append((pool, delta))
            elif pool.recover_on_short_rest:
                before = pool.used
                pool.recover(pool.recover_on_short_rest)
                delta = before - pool.used
                if delta:
                    touched.append((pool, delta))
        return touched

    def of_class(self, class_id: str) -> list[Pool]:
        return [pool for pool in self.pools.values() if pool.owner_class == class_id]

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.pools))

    def to_dict(self) -> list[dict]:
        return [self.pools[key].to_dict() for key in sorted(self.pools)]

    @classmethod
    def from_dict(cls, rows: list[dict]) -> "ResourcePool":
        pool = cls()
        for row in rows:
            pool.add(Pool(
                id=str(row["id"]),
                kind=PoolKind(row["kind"]),
                capacity=int(row["capacity"]),
                used=int(row.get("used", 0)),
                owner_class=row.get("owner_class"),
                refresh=Refresh(row.get("refresh", "long_rest")),
                recover_on_short_rest=int(row.get("recover_on_short_rest", 0)),
                spell=str(row.get("spell") or ""),
                source=str(row.get("source") or ""),
            ))
        return pool
