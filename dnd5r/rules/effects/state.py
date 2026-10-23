# -*- coding: utf-8 -*-
"""状态、资源与掷骰修正类原语。

这里放的是「不改角色数值，而改局面」的那几种：
给状态、花资源、改一颗已经掷出的骰子。它们是 12 职业探针里
补出来的 G7（结算后修正）与 G3（资源是池不是次数）的落点。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from ...kernel.errors import IllegalAction, PluginError
from ...kernel.text import Text
from ...model.effect_instance import Duration, DurationKind
from ...model.marks import SCOPES, Mark
from ..amount import Amount, parse_amount
from .base import Effect, EffectContext, register


@dataclass(frozen=True, slots=True)
class ApplyCondition(Effect):
    """施加状态。震慑打击、自然面纱、狂暴都靠它。"""

    op: ClassVar[str] = "apply_condition"
    condition_id: str = ""
    duration: Duration = field(default_factory=lambda: Duration(DurationKind.PERMANENT))

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "ApplyCondition":
        if isinstance(payload, str):
            return cls(condition_id=payload)
        if not isinstance(payload, Mapping):
            raise PluginError("%s apply_condition 参数必须是字符串或映射" % where)
        ident = payload.get("id") or payload.get("condition")
        if not ident:
            raise PluginError("%s apply_condition 缺少 id" % where)
        return cls(condition_id=str(ident), duration=Duration.parse(payload.get("duration", "permanent")))

    def apply(self, ctx: EffectContext) -> None:
        ctx.subject.conditions.add(self.condition_id)
        ctx.note(Text.of("获得状态：%s" % self.condition_id, "Condition: %s" % self.condition_id), self.op)

    def to_dict(self) -> dict:
        return {"op": self.op, "id": self.condition_id}


@dataclass(frozen=True, slots=True)
class RemoveCondition(Effect):
    op: ClassVar[str] = "remove_condition"
    condition_id: str = ""

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "RemoveCondition":
        if isinstance(payload, Mapping):
            ident = payload.get("id") or payload.get("condition")
            if not ident:
                raise PluginError("%s remove_condition 缺少 id" % where)
            return cls(condition_id=str(ident))
        if isinstance(payload, str) and payload.strip():
            return cls(condition_id=payload.strip())
        raise PluginError("%s remove_condition 参数必须是状态名或 {id: ...}" % where)

    def apply(self, ctx: EffectContext) -> None:
        removed = ctx.subject.conditions.remove(self.condition_id)
        ctx.note(Text.of("移除状态：%s" % self.condition_id, "Removed condition: %s" % self.condition_id), self.op)
        ctx.scratch["removed_condition"] = removed

    def to_dict(self) -> dict:
        return {"op": self.op, "id": self.condition_id}


@dataclass(frozen=True, slots=True)
class SpendResource(Effect):
    """效果内部追加花费（成本走 Cost，这里只处理「再花 1 气」这种）。"""

    op: ClassVar[str] = "spend_resource"
    pool_id: str = ""
    amount: int = 1

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "SpendResource":
        if isinstance(payload, str):
            return cls(pool_id=payload)
        if not isinstance(payload, Mapping):
            raise PluginError("%s spend_resource 参数不合法" % where)
        pool_id = payload.get("pool") or payload.get("id")
        if not pool_id:
            raise PluginError("%s spend_resource 缺少 pool" % where)
        return cls(pool_id=str(pool_id), amount=int(payload.get("amount", 1)))

    def apply(self, ctx: EffectContext) -> None:
        pool = ctx.subject.root().resources.get(self.pool_id)
        if not pool.can_spend(self.amount):
            raise IllegalAction("%s 剩余 %d，不足 %d" % (self.pool_id, pool.available, self.amount))
        pool.spend(self.amount)
        ctx.note(Text.of("消耗 %s ×%d" % (self.pool_id, self.amount),
                         "Spent %s x%d" % (self.pool_id, self.amount)), self.op)

    def to_dict(self) -> dict:
        return {"op": self.op, "pool": self.pool_id, "amount": self.amount}


@dataclass(frozen=True, slots=True)
class RecoverResource(Effect):
    """恢复资源。奥术回想的「环级总额预算」也是它，只是 amount 由外部算好。"""

    op: ClassVar[str] = "recover_resource"
    pool_id: str = ""
    amount: int = 1
    full: bool = False

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "RecoverResource":
        if isinstance(payload, str):
            return cls(pool_id=payload, full=True)
        if not isinstance(payload, Mapping):
            raise PluginError("%s recover_resource 参数不合法" % where)
        pool_id = payload.get("pool") or payload.get("id")
        if not pool_id:
            raise PluginError("%s recover_resource 缺少 pool" % where)
        return cls(
            pool_id=str(pool_id),
            amount=int(payload.get("amount", 1)),
            full=bool(payload.get("full", False)),
        )

    def apply(self, ctx: EffectContext) -> None:
        pool = ctx.subject.root().resources.get(self.pool_id)
        if self.full:
            pool.refill()
        else:
            pool.recover(self.amount)
        ctx.note(Text.of("恢复 %s（余 %d）" % (self.pool_id, pool.available),
                         "Recovered %s (%d left)" % (self.pool_id, pool.available)), self.op)

    def to_dict(self) -> dict:
        return {"op": self.op, "pool": self.pool_id, "amount": self.amount, "full": self.full}


@dataclass(frozen=True, slots=True)
class ModifyRoll(Effect):
    """掷骰后改数：加骰、重掷、保底。

    战术思维（失败时 +1d10）、不屈（重投并加等级）、
    灵感骰（d6→d12）都属于这一类 —— 它们不能当「施法前声明」处理。
    """

    op: ClassVar[str] = "modify_roll"
    amount: Amount | None = None
    mode: str = "add"          # add / reroll / floor
    applies_to: str = "any"    # any / skill_check / save / attack

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "ModifyRoll":
        if isinstance(payload, int) and not isinstance(payload, bool):
            return cls(amount=Amount(flat=payload))
        if not isinstance(payload, Mapping):
            raise PluginError("%s modify_roll 参数必须是映射" % where)
        mode = str(payload.get("mode", "add")).lower()
        if mode not in ("add", "reroll", "floor"):
            raise PluginError("%s 未知改数方式 %r" % (where, mode))
        amount_data = {key: value for key, value in payload.items()
                       if key not in ("mode", "applies_to")}
        amount = parse_amount(amount_data, where=where) if amount_data else None
        return cls(amount=amount, mode=mode, applies_to=str(payload.get("applies_to", "any")))

    def apply(self, ctx: EffectContext) -> None:
        if self.mode == "reroll":
            ctx.scratch["reroll"] = True
            ctx.note(Text.of("可以重掷", "May reroll"), self.op)
        if self.amount is None:
            return
        value, rolled = self.amount.roll(ctx.ref_map(), ctx.rng)
        if self.mode == "floor":
            ctx.scratch["roll_floor"] = max(int(ctx.scratch.get("roll_floor", 0)), value)
        else:
            ctx.scratch["roll_bonus"] = int(ctx.scratch.get("roll_bonus", 0)) + value
        if rolled is not None:
            ctx.roll("改数", value, detail=rolled.describe())
        ctx.note(Text.of("本次检定 +%d（%s）" % (value, self.applies_to),
                         "This check gets +%d (%s)" % (value, self.applies_to)), self.op)

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "mode": self.mode,
            "amount": self.amount.to_dict() if self.amount else None,
        }


@dataclass(frozen=True, slots=True)
class MarkAdvantage(Effect):
    """挂一条**一次性**的优势/劣势（"本回合结束前下一次攻击优势"）。

    与 `grant_advantage` 的区别只有一条，但很关键：那条是**一直有效**的
    （被动增益），这条挂上以后会被**消费掉**。所以它落在 `Actor.marks`，
    不进 `Actor.effects`。

    `expires: turn` 是默认：原文绝大多数写「本回合结束前」。写 `round`
    表示「这一轮内」，`never` 表示只能显式移除（诅咒那种）。
    """

    op: ClassVar[str] = "mark"
    target: str = "attack.all"
    mode: str = "adv"
    uses: int = 1
    expires: str = "turn"
    label: str = ""

    def __post_init__(self) -> None:
        if not self.target:
            raise PluginError("mark 缺少作用目标（如 attack.all）")
        if self.mode not in ("adv", "dis"):
            raise PluginError("mark.mode 只能是 adv 或 dis：%r" % (self.mode,))
        if self.expires not in SCOPES:
            raise PluginError("mark.expires 只能是 %s：%r"
                              % ("/".join(SCOPES), self.expires))
        if int(self.uses) < 1:
            raise PluginError("mark.uses 必须 >= 1：%r" % (self.uses,))

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "MarkAdvantage":
        if isinstance(payload, str):
            return cls(target=payload)
        if not isinstance(payload, Mapping):
            raise PluginError("%s mark 参数必须是目标或映射" % where)
        # 两种写法都认：`mark: {advantage: attack.all}` 与
        # `mark: {target: attack.all, mode: dis}`
        target = payload.get("advantage") or payload.get("target") or payload.get("on")
        if not target:
            raise PluginError("%s mark 缺少 advantage / target" % where)
        return cls(
            target=str(target),
            mode=str(payload.get("mode", "adv")).lower(),
            uses=int(payload.get("uses", 1)),
            expires=str(payload.get("expires", "turn")).lower(),
            label=str(payload.get("label", "")),
        )

    def apply(self, ctx: EffectContext) -> None:
        source = ctx.source or self.op
        token = "%s.%s" % (self.mode, self.target)
        ctx.subject.root().marks.add(Mark(
            id="%s:%s" % (source, token),
            kind="advantage",
            target=self.target,
            mode=self.mode,
            source=source,
            label=self.label,
            uses=int(self.uses),
            expires=self.expires,
        ))
        word = "优势" if self.mode == "adv" else "劣势"
        scope = {"turn": "本回合结束前", "round": "本轮结束前",
                 "never": "直到被移除"}[self.expires]
        ctx.note(Text.of("%s：%s（%s，%d 次）" % (word, self.target, scope, self.uses),
                         "%s on %s (%s, x%d)" % (word, self.target, self.expires, self.uses)),
                 self.op)

    def to_dict(self) -> dict:
        return {"op": self.op, "target": self.target, "mode": self.mode,
                "uses": int(self.uses), "expires": self.expires}


@dataclass(frozen=True, slots=True)
class NoteEffect(Effect):
    """显式「仅提示」。语言、黑话、衰老这类确实无法数值化的内容用它，
    而不是塞进一个 note_only 垃圾桶里假装算过了。"""

    op: ClassVar[str] = "note"
    text: Text = field(default_factory=lambda: Text.of("（无说明）", "(no description)"))

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "NoteEffect":
        if isinstance(payload, Text):
            return cls(text=payload)
        if isinstance(payload, Mapping):
            return cls(text=Text.from_dict(payload, where="%s note" % where))
        raise PluginError("%s note 必须是 {zh, en} 映射" % where)

    def apply(self, ctx: EffectContext) -> None:
        ctx.note(self.text, self.op)

    def to_dict(self) -> dict:
        return {"op": self.op, "text": self.text.to_dict()}


for _cls in (ApplyCondition, RemoveCondition, SpendResource, RecoverResource, ModifyRoll,
             MarkAdvantage, NoteEffect):
    register(_cls)
