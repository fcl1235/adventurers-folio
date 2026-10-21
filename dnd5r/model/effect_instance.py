# -*- coding: utf-8 -*-
"""持续效果实例：能力生效后留在角色身上的那部分。

设计要点（见 §11 G14）：
  * 时长要分时钟：回合 / 轮 / 分钟 / 小时 / 长休 / 永久
  * 效果携带的是「已解析的 Modifier」，不是 Power —— 能力定义改了不该影响已生效的实例
  * 只存事实（还有几回合、来源是谁），派生值照旧现算
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from ..kernel.errors import RuleError


class DurationKind(str, Enum):
    TURN = "turn"            # 到自己的下个回合开始
    ROUND = "round"          # 按轮计
    MINUTE = "minute"
    HOUR = "hour"
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"
    PERMANENT = "permanent"  # 不自然过期，只能被显式移除


@dataclass(frozen=True, slots=True)
class Duration:
    kind: DurationKind
    value: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DurationKind):
            raise RuleError("Duration.kind 必须是 DurationKind：%r" % (self.kind,))
        if self.value < 1:
            raise RuleError("持续时长必须 >= 1：%r" % (self.value,))

    @classmethod
    def parse(cls, data: Any) -> "Duration":
        """支持 "1 round" / "10 minute" / "permanent" / {"kind": "minute", "value": 10}。"""
        if isinstance(data, Duration):
            return data
        if isinstance(data, str):
            text = data.strip().lower()
            if text in ("permanent", "always", "forever"):
                return cls(DurationKind.PERMANENT)
            count, _, unit = text.partition(" ")
            unit = unit.strip().rstrip("s")
            aliases = {
                "turn": DurationKind.TURN, "round": DurationKind.ROUND,
                "minute": DurationKind.MINUTE, "hour": DurationKind.HOUR,
                "short_rest": DurationKind.SHORT_REST, "long_rest": DurationKind.LONG_REST,
            }
            if unit not in aliases:
                raise RuleError("未知时长单位：%r" % data)
            try:
                value = int(count) if count else 1
            except ValueError:
                raise RuleError("时长数字不合法：%r" % data)
            return cls(aliases[unit], max(1, value))
        if isinstance(data, dict):
            kind = str(data.get("kind", "permanent")).lower()
            try:
                return cls(DurationKind(kind), int(data.get("value", 1)))
            except ValueError:
                raise RuleError("未知时长类型：%r" % (data,))
        raise RuleError("时长写法不支持：%r" % (data,))

    def short(self) -> str:
        if self.kind is DurationKind.PERMANENT:
            return "永久"
        return "%d %s" % (self.value, self.kind.value.replace("_", " "))


@dataclass
class ActiveEffect:
    """挂在角色身上的一段效果。"""

    id: str
    source: str = ""              # 能力 id
    label: str = ""
    modifiers: list = field(default_factory=list)
    conditions: tuple[str, ...] = ()
    resistances: tuple[str, ...] = ()
    immunities: tuple[str, ...] = ()
    granted_actions: int = 0
    duration: Duration = field(default_factory=lambda: Duration(DurationKind.PERMANENT))
    remaining: int = 0

    def __post_init__(self) -> None:
        if not self.id:
            raise RuleError("ActiveEffect.id 不能为空")
        if self.remaining == 0:
            self.remaining = self.duration.value

    @property
    def expired(self) -> bool:
        return self.duration.kind is not DurationKind.PERMANENT and self.remaining <= 0

    def tick(self, amount: int = 1) -> bool:
        """推进时钟；返回是否到期。永久效果不推进。"""
        if self.duration.kind is DurationKind.PERMANENT:
            return False
        self.remaining = max(0, self.remaining - amount)
        return self.remaining <= 0

    def dies_at_rest(self, kind: str) -> bool:
        """休息时清理：短休清 SHORT_REST 及更短的，长休全清（除永久）。"""
        if self.duration.kind is DurationKind.PERMANENT:
            return False
        if self.duration.kind is DurationKind.LONG_REST:
            return kind == "long_rest"
        if self.duration.kind is DurationKind.SHORT_REST:
            return kind in ("short_rest", "long_rest")
        return kind == "long_rest"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "label": self.label,
            "duration": {"kind": self.duration.kind.value, "value": self.duration.value},
            "remaining": self.remaining,
            "conditions": list(self.conditions),
            "resistances": list(self.resistances),
            "granted_actions": self.granted_actions,
        }


def purge_expired(effects: Iterable[ActiveEffect]) -> list[ActiveEffect]:
    return [item for item in effects if not item.expired]


def by_source(effects: Iterable[ActiveEffect], source: str) -> list[ActiveEffect]:
    return [item for item in effects if item.source == source]
