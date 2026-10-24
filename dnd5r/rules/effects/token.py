# -*- coding: utf-8 -*-
"""GrantToken：把一颗骰**交给别人**，可被其消耗、会过期（G5/G30）。

与其它原语的本质差别：受益者不是自己。P9a 决定 7 定过「愿意与否不进程序」，
这里同理 —— **受益者是一条输入**（choice 里的 target_id，从遭遇战里指认），
程序不猜「谁该拿这颗骰」。

首个真实用例是吟游诗人灵感：附赠动作、只能给别人、d6→d8/d10/d12（5/10/15 级）、
**同时只能持有一颗**（Mark.add 的同源替换正好是这条规则）、一小时内可用
（引擎没有时钟，用 `rest` 作用域近似：撑不过一次休息）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from ...kernel.errors import IllegalAction, PluginError, RuleError
from ...model.marks import Mark
from ..amount import parse_amount
from .base import Effect, EffectContext, register

TOKEN_KIND = "token"


@dataclass(frozen=True, slots=True)
class GrantToken(Effect):
    """交出一颗骰。

        grant_token:
          die: {table: {1: 6, 5: 8, 10: 10, 15: 12}, key: class_level}
          expires: rest          # turn / round / rest / never
          forbid_self: true      # 原文 another creature
          range_feet: 60         # 没摆位不判距离（宁可放过，不可误拦）

    `die` 三种写法：骰式字符串（"1d6"）、整数（6 → 1d6）、Amount（按等级查表）。
    受益者从 `choice: {"target_id": ...}` 来，按遭遇战参与者解析。
    """

    op: ClassVar[str] = "grant_token"
    die: Any = "1d6"
    expires: str = "rest"
    label: str = ""
    forbid_self: bool = True
    range_feet: int = 60

    def __post_init__(self) -> None:
        if self.expires not in ("turn", "round", "rest", "never"):
            raise PluginError("grant_token 的 expires 只认 turn/round/rest/never：%r"
                              % (self.expires,))
        if self.range_feet < 0:
            raise PluginError("grant_token 的 range_feet 不能为负：%r"
                              % (self.range_feet,))

    def _die_formula(self, ctx: EffectContext) -> str:
        """骰式在**授予那一刻**定死（规则如此：给出去的是几面就是几面）。"""
        if isinstance(self.die, str):
            return self.die
        if isinstance(self.die, int) and not isinstance(self.die, bool):
            return "1d%d" % int(self.die)
        amount = self.die if hasattr(self.die, "evaluate") else parse_amount(
            self.die, where="grant_token.die")
        ref = ctx.ref_map()
        ref["class_level"] = int(ctx.class_level or 1)
        return "1d%d" % max(2, int(amount.evaluate(ref)))

    def apply(self, ctx: EffectContext) -> None:
        ident = str(ctx.scratch.get("target_id", "") or "")
        if not ident:
            raise IllegalAction("要指认受益者（choice: {\"target_id\": 场上的人}）")
        if ctx.encounter is None:
            ctx.note("未结算：没有遭遇战，受益者无从指认（%s）" % (self.label or "授予"))
            return
        try:
            combatant = ctx.encounter.get(ident)
        except RuleError as exc:
            raise IllegalAction(str(exc))
        if self.forbid_self and combatant.actor.root() is ctx.actor.root():
            raise IllegalAction("这颗骰只能给别人，不能给自己")
        # 距离只在「双方都摆过位」时才判：没摆位时的 (0,0) 距离毫无意义，
        # 宁可放过也不误拦（与 Encounter 位置默认同一条口径）
        if self.range_feet and combatant.placed and ctx.encounter.has(ctx.actor):
            source = ctx.encounter.get(ctx.actor)
            if source.placed:
                feet = ctx.encounter.distance(source, combatant)
                if feet > self.range_feet:
                    raise IllegalAction("受益者超出 %d 尺（现在 %d 尺）"
                                        % (self.range_feet, feet))
        name = self.label or ctx.source.rsplit(".", 1)[-1]
        formula = self._die_formula(ctx)
        # 同源替换 = 「同时只能持有一颗」：Mark.add 的语义正好是这条规则
        combatant.actor.root().marks.add(Mark(
            id="token.%s" % (self.label or ctx.source.rsplit(".", 1)[-1]),
            kind=TOKEN_KIND, target="test.d20", mode="adv",
            source=ctx.source, label=name, uses=1,
            expires=self.expires, dice=formula))
        ctx.note("把一颗%s（%s）交给 %s" % (name, formula, combatant.label))

    def to_dict(self) -> dict:
        return {"die": str(self.die), "expires": self.expires,
                "label": self.label, "forbid_self": self.forbid_self,
                "range_feet": self.range_feet}

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "GrantToken":
        if not isinstance(payload, Mapping):
            raise PluginError("%s 的 grant_token 必须是映射" % where)
        return cls(
            die=payload.get("die", "1d6"),
            expires=str(payload.get("expires", "rest")).lower(),
            label=str(payload.get("label", "")),
            forbid_self=bool(payload.get("forbid_self", True)),
            range_feet=int(payload.get("range_feet", 60)),
        )


register(GrantToken)
