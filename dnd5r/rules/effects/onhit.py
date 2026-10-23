# -*- coding: utf-8 -*-
"""命中时结算的通道：额外伤害。

`damage` 原语是「用这个能力时直接扣血」（火球、偷袭之外的主动伤害）；
`extra_damage` 完全相反 —— 它**什么都不做**，只是声明「我命中时要多掷这些骰子」，
等 `rules/attack.resolve_attack` 来取。

为什么必须分开：月华形态的「每回合一次 +2d10」不是一次主动行为。玩家点它
什么都不该发生（它不是按钮），而每次挥爪时它应该出现在「可以加的额外伤害」
清单里。如果把 2d10 写成 `damage`，点一下就凭空掉血 —— 那是在凭空造伤害。

`limit` 是两种真实的措辞：
  turn    每回合一次（月华形态、偷袭、猎人印记）
  attack  每次命中都算（光耀斩这类）

「每回合一次」的记账在 `Actor.marks.spent` 里，回合结束时一起清 ——
标记与记账共享同一条生命周期，不需要第二个时钟。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from ...kernel.dice import parse as parse_dice
from ...kernel.errors import PluginError
from ...kernel.text import Text
from .base import Effect, EffectContext, register

LIMITS = ("turn", "attack")


@dataclass(frozen=True, slots=True)
class ExtraDamage(Effect):
    """命中时可选追加的伤害骰。被动声明，不在这里掷。"""

    op: ClassVar[str] = "extra_damage"
    dice: str = "1d6"
    damage_type: str = ""
    limit: str = "turn"
    when: Mapping[str, Any] | None = None
    label: str = ""

    def __post_init__(self) -> None:
        # 骰式在这里就解析一次：写错的内容要在加载时报，而不是等到玩家挥刀那一下
        parse_dice(str(self.dice))
        if self.limit not in LIMITS:
            raise PluginError("extra_damage.limit 只能是 %s：%r"
                              % ("/".join(LIMITS), self.limit))

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "ExtraDamage":
        if isinstance(payload, str):
            return cls(dice=payload)
        if not isinstance(payload, Mapping):
            raise PluginError("%s extra_damage 参数必须是骰式或映射" % where)
        dice = payload.get("dice") or payload.get("damage")
        if not dice:
            raise PluginError("%s extra_damage 缺少 dice" % where)
        limit = str(payload.get("limit", "turn")).lower()
        if limit not in LIMITS:
            raise PluginError("%s extra_damage.limit 只能是 %s：%r"
                              % (where, "/".join(LIMITS), limit))
        when = payload.get("when")
        if when is not None and not isinstance(when, Mapping):
            raise PluginError("%s extra_damage.when 必须是映射" % where)
        return cls(
            dice=str(dice),
            damage_type=str(payload.get("type") or payload.get("damage_type") or ""),
            limit=limit,
            when=when,
            label=str(payload.get("label", "")),
        )

    def apply(self, ctx: EffectContext) -> None:
        """被当成主动能力点到了：明说它不在这里结算，别让玩家以为白点了。"""
        ctx.note(Text.of(
            "额外伤害 %s 在**命中时**结算，不是用这个能力时；攻击掷骰里会列出来"
            % self.dice,
            "Extra damage %s applies on a hit, not when this feature is used; "
            "the attack roll lists it" % self.dice), self.op)

    def to_dict(self) -> dict:
        return {
            "op": self.op, "dice": self.dice, "type": self.damage_type,
            "limit": self.limit, "when": dict(self.when or {}) or None,
        }


for _cls in (ExtraDamage,):
    register(_cls)
