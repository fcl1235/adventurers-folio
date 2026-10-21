# -*- coding: utf-8 -*-
"""领域事件：不可变，可落盘、可回放、可直接喂给掷骰记录或 AI。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union

from .text import Text


@dataclass(frozen=True, slots=True)
class Event:
    pass


@dataclass(frozen=True, slots=True)
class RollEvent(Event):
    label: str
    total: int
    detail: str = ""
    mode: str = "flat"


@dataclass(frozen=True, slots=True)
class ResourceEvent(Event):
    pool_id: str
    delta: int
    used: int
    capacity: int | None = None


@dataclass(frozen=True, slots=True)
class HpEvent(Event):
    current: int
    maximum: int
    temp: int = 0


@dataclass(frozen=True, slots=True)
class ConditionEvent(Event):
    condition_id: str
    applied: bool


@dataclass(frozen=True, slots=True)
class PowerEvent(Event):
    power_id: str
    ok: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class NoteEvent(Event):
    """仅提示、不结算的内容（如语言、暗语）。"""

    text: Text
    source: str = ""


@dataclass(frozen=True, slots=True)
class Report:
    events: tuple[Event, ...] = ()
    rolls: tuple[RollEvent, ...] = ()
    ok: bool = True
    message: str = ""

    def extend(self, other: "Report") -> "Report":
        return Report(
            events=self.events + other.events,
            rolls=self.rolls + other.rolls,
            ok=self.ok and other.ok,
            message=self.message or other.message,
        )


AnyEvent = Union[RollEvent, ResourceEvent, HpEvent, ConditionEvent, PowerEvent, NoteEvent]
