# -*- coding: utf-8 -*-
"""前端契约：卡片 DTO。

UI 只认识 `Card`。它不判断规则、不算数值、不查词表 ——
标题、副标题、数值、能不能点，全部由后端算好塞进来。

这样加一个职业特性，前端一行不用改（§6）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class CardAction:
    """按钮。点了就把它原样发回去，前端不解释 payload。"""

    command: str
    label: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"command": self.command, "label": self.label, "payload": dict(self.payload)}


@dataclass(frozen=True, slots=True)
class Card:
    id: str
    title: str
    subtitle: str = ""
    value: str = ""
    tone: str = "normal"          # normal / warn / dim / good
    badges: tuple[str, ...] = ()
    actions: tuple[CardAction, ...] = ()
    detail: tuple[str, ...] = ()

    @property
    def interactive(self) -> bool:
        return bool(self.actions)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "value": self.value,
            "tone": self.tone,
            "badges": list(self.badges),
            "actions": [action.to_dict() for action in self.actions],
            "detail": list(self.detail),
        }


@dataclass(frozen=True, slots=True)
class HeaderView:
    name: str
    classes: tuple[str, ...] = ()
    level: int = 1
    hp: int = 0
    hp_max: int = 0
    temp_hp: int = 0
    ac: int = 0
    ac_detail: str = ""
    speed: Mapping[str, int] = field(default_factory=dict)
    proficiency_bonus: int = 2
    conditions: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "classes": list(self.classes),
            "level": self.level,
            "hp": self.hp,
            "hp_max": self.hp_max,
            "temp_hp": self.temp_hp,
            "ac": self.ac,
            "ac_detail": self.ac_detail,
            "speed": dict(self.speed),
            "proficiency_bonus": self.proficiency_bonus,
            "conditions": list(self.conditions),
        }


@dataclass(frozen=True, slots=True)
class CharacterView:
    header: HeaderView
    cards: tuple[Card, ...] = ()
    attacks: tuple[Card, ...] = ()
    log: tuple[str, ...] = ()

    def card(self, card_id: str) -> Card:
        for item in self.cards + self.attacks:
            if item.id == card_id:
                return item
        raise KeyError("没有这张卡：%s" % card_id)

    def actions(self) -> tuple[CardAction, ...]:
        return tuple(action for card in self.cards + self.attacks for action in card.actions)

    def to_dict(self) -> dict:
        return {
            "header": self.header.to_dict(),
            "cards": [card.to_dict() for card in self.cards],
            "attacks": [card.to_dict() for card in self.attacks],
            "log": list(self.log),
        }
