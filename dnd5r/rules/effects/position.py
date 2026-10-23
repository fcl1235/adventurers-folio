# -*- coding: utf-8 -*-
"""位置型原语：在一个遭遇战里挪动谁。

它和别的原语不同 —— 不改任何数值，只改 `Encounter` 里的坐标。
所以有两条额外的诚实要求：

1. **没有遭遇战就不算**。角色卡单独打开时没有场上位置这回事，
   这时候不是「传送成功但没变化」，而是「没结算」，必须说出来。
2. **没给坐标也不假装成功**。目标格从 `scratch["to"]` 读（界面把玩家
   点的格子放进去）；没有就记一条 note，让人知道这次点击没生效。

为什么要做原语而不是让界面自己调坐标：距离上限、占位、越界这三道检查
如果散在界面里，CLI 和桌面端迟早各写一套，然后其中一套慢慢就不检查了。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from ...kernel.text import Text
from .base import Effect, EffectContext, register


@register
@dataclass(frozen=True, slots=True)
class Teleport(Effect):
    """把自己挪到 `scratch["to"]` 指定的格子，最多 `max_feet` 尺。

    目前两个用例都长在同一个子职上（一条主动传送 + 一条被动加成），
    按「≥2 个不同职业」的规矩还不够格单独立原语。
    但它是纯机制（只改坐标、只做检查），不含任何内容知识，
    放进内核不会长出职业分支；先收着，等第二个职业用到时就是既有原语。
    """

    op: ClassVar[str] = "teleport"
    max_feet: int = 30

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "Teleport":
        if payload is None:
            return cls()
        if isinstance(payload, Mapping):
            return cls(max_feet=int(payload.get("max_feet", 30)))
        return cls(max_feet=int(payload))

    def apply(self, ctx: EffectContext) -> None:
        enc = ctx.encounter
        if enc is None:
            ctx.note(Text.of(
                "没有进行中的遭遇战，传送未结算（先摆位再放这一下）",
                "No encounter is running, so the teleport was not resolved."))
            return

        to = ctx.scratch.get("to")
        if to is None:
            ctx.note(Text.of(
                "没有指定传送目标格，未结算",
                "No destination was given, so the teleport was not resolved."))
            return

        x, y = int(to[0]), int(to[1])
        result = enc.teleport(ctx.actor.root(), x, y, self.max_feet)
        ctx.note(Text.of(
            "传送到 (%d, %d)，%d 尺" % (x, y, int(result["feet"])),
            "Teleported to (%d, %d), %d feet." % (x, y, int(result["feet"]))))
        ctx.scratch["teleported"] = result

    def to_dict(self) -> dict:
        return {"op": self.op, "max_feet": int(self.max_feet)}
