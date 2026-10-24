# -*- coding: utf-8 -*-
"""资源定义：池的容量、恢复方式（内容侧）。拆自 P11 之前的 content.py。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..kernel.ids import is_valid
from ..kernel.errors import PluginError
from ..kernel.text import Text
from ..model.levels import ClassLevel
from ..model.resources import Pool, PoolKind, Refresh
from ..rules.amount import Amount, parse_amount

RESOURCE_KINDS = {item.value: item for item in PoolKind}
REFRESH_KINDS = {item.value: item for item in Refresh}


# --- 资源 -------------------------------------------------------------
@dataclass(frozen=True)
class ResourceDef:
    """一个资源池的定义。次数表放数据里，代码只负责查表。"""

    id: str
    kind: PoolKind
    refresh: Refresh = Refresh.LONG_REST
    capacity: Amount | None = None
    by_level: Mapping[int, int] | None = None
    recover_on_short_rest: int = 0
    label: Text | None = None
    owner_class: str = ""
    # 这个池几级才有。0 = 与所属内容同时解锁。
    # 职业资源用 `by_level` 表达「2 级 2 次、6 级 3 次」，低等级自然算成 0；
    # 但子职的池往往容量是常数或「属性调整值」，等级门槛得单独说一句 ——
    # 否则 3 级德鲁伊的卡上会多出一个 10 级才解锁、还没有按钮的次数池。
    level: ClassLevel = ClassLevel(0)
    # 「这个来源授予的**每一道有环级的法术**各建一个池，各 1 次」。
    # 妖精触碰的「两道法术各一次」按这道开关展开：合成一个 capacity 2 的池，
    # 玩家就能连放两次迷踪步 —— 那不是原文的意思。
    # 戏法不建池：戏法本来就能无限施放，给一个「1 次」的池是凭空多出一个限制。
    per_spell: bool = False

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("资源 id 不合规范：%r" % (self.id,))
        if int(self.level) < 0:
            raise PluginError("资源 %s 的解锁等级不能是负数" % self.id)
        if self.capacity is None and not self.by_level:
            raise PluginError("资源 %s 必须给 capacity 或 by_level" % self.id)
        if self.by_level:
            for key, value in self.by_level.items():
                if int(key) < 1 or int(value) < 0:
                    raise PluginError("资源 %s 的等级表不合法：%r=%r" % (self.id, key, value))
        if self.per_spell and self.kind is not PoolKind.CHARGE:
            raise PluginError("资源 %s 写了 per_spell，只能是次数（charge）池" % self.id)
        if self.per_spell:
            # 每个法术恰好一次 —— 别的数字原文里没有，写出来就是编的
            cap = self.capacity
            if self.by_level or cap is None or cap.dice is not None \
                    or cap.table is not None or cap.flat != 1 \
                    or cap.plus is not None or cap.times is not None:
                raise PluginError("资源 %s 的 per_spell 只能写 capacity: 1" % self.id)

    def capacity_at(self, level: ClassLevel, ref_map: Mapping[str, Any] | None = None) -> int:
        """按「本职业等级」查表。兼职时次数按职业等级，不按总等级（G15）。"""
        if int(self.level) and int(level) < int(self.level):
            return 0                    # 还没解锁：调用方见到 0 就不建池
        if self.by_level:
            usable = [int(key) for key in self.by_level if int(key) <= int(level)]
            if not usable:
                return 0
            return int(self.by_level[max(usable)])
        assert self.capacity is not None
        if ref_map is None:
            if self.capacity.times is not None or self.capacity.plus is not None:
                raise PluginError(
                    "资源 %s 的容量依赖等级引用，必须提供 ref_map" % self.id
                )
            return self.capacity.flat
        return self.capacity.evaluate(ref_map)

    def build(self, level: ClassLevel, ref_map: Mapping[str, Any] | None = None) -> Pool:
        return Pool(
            id=self.id,
            kind=self.kind,
            capacity=self.capacity_at(level, ref_map),
            label=self.label,
            owner_class=self.owner_class or None,
            refresh=self.refresh,
            recover_on_short_rest=self.recover_on_short_rest,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind.value, "refresh": self.refresh.value,
            "by_level": dict(self.by_level or {}),
            "recover_on_short_rest": self.recover_on_short_rest,
            "level": int(self.level),
            "per_spell": self.per_spell,
        }


def parse_resource(data: Any, owner_class: str = "") -> ResourceDef:
    if not isinstance(data, Mapping):
        raise PluginError("资源条目必须是映射：%r" % (data,))
    ident = data.get("id")
    if not ident:
        raise PluginError("资源缺少 id")
    kind_key = str(data.get("kind", "charge")).lower()
    if kind_key not in RESOURCE_KINDS:
        raise PluginError("%s 的资源类型必须是 %s" % (ident, "/".join(sorted(RESOURCE_KINDS))))
    refresh_key = str(data.get("refresh", "long_rest")).lower()
    if refresh_key not in REFRESH_KINDS:
        raise PluginError("%s 的恢复方式必须是 %s" % (ident, "/".join(sorted(REFRESH_KINDS))))

    by_level = None
    if data.get("by_level"):
        try:
            by_level = {int(key): int(value) for key, value in data["by_level"].items()}
        except (TypeError, ValueError):
            raise PluginError("%s 的 by_level 必须是 等级→次数 的映射" % ident)

    capacity = None
    if data.get("capacity") is not None:
        capacity = parse_amount(data["capacity"], where="%s capacity" % ident)

    label = None
    if data.get("label") is not None:
        label = Text.from_dict(data["label"], where="%s label" % ident)

    # `level` 这里不能过 `as_class_level`：它要求 >= 1，而 0 在这里是
    # 「与所属内容同时解锁」的哨兵值（与 `Power.level` 的默认值同一个意思）。
    raw_level = data.get("level", 0)
    if isinstance(raw_level, bool) or not isinstance(raw_level, int):
        raise PluginError("%s 的 level 必须是整数：%r" % (ident, raw_level))

    return ResourceDef(
        id=str(ident),
        kind=RESOURCE_KINDS[kind_key],
        refresh=REFRESH_KINDS[refresh_key],
        capacity=capacity,
        by_level=by_level,
        recover_on_short_rest=int(data.get("recover_on_short_rest", 0)),
        label=label,
        owner_class=str(data.get("owner", owner_class)),
        level=ClassLevel(raw_level),
        per_spell=bool(data.get("per_spell", False)),
    )
