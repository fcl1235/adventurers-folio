# -*- coding: utf-8 -*-
"""结算后修正：OverrideOutcome（掷骰后改数 / 保底）。

这一类与「做事」的原语不同：结果已经出来了，要改的是**骰面本身**。
首个真实用例是游荡者可靠天赋（熟练的技能/工具检定，d20 ≤ 9 按 10 计）。
闪避（豁免成功零伤）那类要等伤害管道挂上豁免钩子，通道先留着。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from ...kernel.errors import PluginError
from .base import Effect, EffectContext, register


@dataclass(frozen=True, slots=True)
class OverrideOutcome(Effect):
    """d20 掷出低面时按保底值计。

        override_outcome: { set_die: 10, when_die_lte: 9, applies_to: check }

    `applies_to` 只认三种：check（技能/工具检定）/ save / attack。
    `when_proficient: true` 表示只对**熟练**的那类检定生效（可靠天赋的原文）。
    优势/劣势取高/低之后的**保留骰**作为判定面 —— 原文说的是 "a d20 roll"。
    """

    op: ClassVar[str] = "override_outcome"
    set_die: int = 10
    when_die_lte: int = 9
    applies_to: str = "check"
    when_proficient: bool = False

    def __post_init__(self) -> None:
        if self.applies_to not in ("check", "save", "attack"):
            raise PluginError("override_outcome 的 applies_to 只认 check/save/attack：%r"
                              % (self.applies_to,))
        if not 1 <= int(self.set_die) <= 20:
            raise PluginError("override_outcome 的 set_die 必须在 1–20：%r"
                              % (self.set_die,))
        if not 1 <= int(self.when_die_lte) < int(self.set_die):
            raise PluginError("override_outcome 的 when_die_lte 必须小于 set_die：%r"
                              % (self.when_die_lte,))

    def apply(self, ctx: EffectContext) -> None:
        """被动原语：真正被消费的地方是 `api.roll_check`（掷骰后）。

        这里不抛错也不做事 —— 抛错会让「每个被动都要能 apply」的契约测试
        误报；做事则会造出「用一次能力触发保底」的假语义。
        """
        ctx.note("override_outcome 是被动保底：由检定掷骰自动套用")

    def to_dict(self) -> dict:
        return {"set_die": self.set_die, "when_die_lte": self.when_die_lte,
                "applies_to": self.applies_to, "when_proficient": self.when_proficient}

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "OverrideOutcome":
        if not isinstance(payload, Mapping):
            raise PluginError("%s 的 override_outcome 必须是映射" % where)
        return cls(
            set_die=int(payload.get("set_die", 10)),
            when_die_lte=int(payload.get("when_die_lte", 9)),
            applies_to=str(payload.get("applies_to", "check")).lower(),
            when_proficient=bool(payload.get("when_proficient", False)),
        )


register(OverrideOutcome)
