# -*- coding: utf-8 -*-
"""动作经济：每回合能用几个动作。

它属于「回合状态」，不属于角色 —— 所以不放进 Actor，也不进存档。
行动激增这类能力通过 GrantAction 临时加次数，而不是自己绕过检查。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..kernel.errors import IllegalAction, RuleError


class ActionType(str, Enum):
    ACTION = "action"
    BONUS = "bonus"
    REACTION = "reaction"
    FREE = "free"      # 不消耗任何额度（行动激增的「额外一个动作」用它）
    NONE = "none"      # 纯被动

    @classmethod
    def parse(cls, data) -> "ActionType":
        if isinstance(data, cls):
            return data
        aliases = {
            "action": cls.ACTION, "a": cls.ACTION,
            "bonus": cls.BONUS, "bonus_action": cls.BONUS, "ba": cls.BONUS,
            "reaction": cls.REACTION, "r": cls.REACTION,
            "free": cls.FREE, "none": cls.NONE, "passive": cls.NONE,
            "": cls.NONE, None: cls.NONE,
        }
        key = str(data).strip().lower() if data is not None else None
        if key not in aliases:
            raise RuleError("未知动作类型：%r" % (data,))
        return aliases[key]


@dataclass
class ActionEconomy:
    """一份回合额度。默认值就是 2024 的一回合。"""

    action: int = 1
    bonus: int = 1
    reaction: int = 1
    movement: int = 30
    label: str = ""

    def _field(self, kind: ActionType) -> str | None:
        if kind is ActionType.ACTION:
            return "action"
        if kind is ActionType.BONUS:
            return "bonus"
        if kind is ActionType.REACTION:
            return "reaction"
        return None

    def available(self, kind: ActionType) -> int:
        field_name = self._field(kind)
        return 0 if field_name is None else int(getattr(self, field_name))

    def can_pay(self, kind: ActionType) -> bool:
        if kind in (ActionType.FREE, ActionType.NONE):
            return True
        return self.available(kind) > 0

    def pay(self, kind: ActionType, label: str = "") -> None:
        if kind in (ActionType.FREE, ActionType.NONE):
            return
        field_name = self._field(kind)
        if field_name is None:
            raise RuleError("无法支付的动作类型：%r" % (kind,))
        if getattr(self, field_name) <= 0:
            raise IllegalAction("%s没有可用的%s" % ("「%s」" % label if label else "", kind.value))
        setattr(self, field_name, getattr(self, field_name) - 1)

    def refund(self, kind: ActionType, amount: int = 1) -> None:
        field_name = self._field(kind)
        if field_name is None:
            return
        setattr(self, field_name, getattr(self, field_name) + amount)

    def grant(self, kind: ActionType, amount: int = 1) -> None:
        self.refund(kind, amount)

    # --- 时点 ---------------------------------------------------------
    def start_turn(self, movement: int | None = None) -> None:
        """自己回合开始：动作、附赠动作、移动恢复；反应要到下回合才回。"""
        self.action = 1
        self.bonus = 1
        if movement is not None:
            self.movement = int(movement)

    def start_round(self) -> None:
        """一轮开始：反应恢复。"""
        self.reaction = 1

    def end_turn(self) -> None:
        """回合结束：未用完的额度作废（不能攒）。"""
        self.action = 0
        self.bonus = 0
        self.movement = 0

    def reset(self, movement: int | None = None) -> None:
        """把额度恢复到一回合的初始值，**复用同一个对象**。

        换新对象的写法（`self.economy = ActionEconomy(...)`）有个坑：
        遭遇战里的 `Combatant` 拿着的是旧引用，休息之后两边就各记一套额度，
        表现为「休息完还能再动一次」。所以凡是「重置」都走这里。
        """
        self.action = 1
        self.bonus = 1
        self.reaction = 1
        if movement is not None:
            self.movement = int(movement)

    def to_dict(self) -> dict:
        return {
            "action": self.action, "bonus": self.bonus,
            "reaction": self.reaction, "movement": self.movement,
        }

    def describe(self) -> str:
        bits = []
        if self.action:
            bits.append("动作×%d" % self.action)
        if self.bonus:
            bits.append("附赠×%d" % self.bonus)
        if self.reaction:
            bits.append("反应×%d" % self.reaction)
        return " · ".join(bits) if bits else "本回合额度已用完"
