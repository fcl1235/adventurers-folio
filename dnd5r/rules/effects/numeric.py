# -*- coding: utf-8 -*-
"""数值型原语：治疗、伤害、临时 HP、减伤。

四个原语都作用在**本体的 HP 池**上（变形时 HP 池留在本体，见 §3.1），
所以这里一律走 subject.root().hp，避免「变形期间治疗加到形态上」这类错误。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Tuple

from ...kernel.errors import PluginError
from ...kernel.text import Text
from ..amount import Amount, parse_amount
from .base import Effect, EffectContext, register


def _split(payload: Any, extra: Tuple[str, ...], where: str) -> tuple[Any, dict]:
    """把 {amount: ..., 其它键} 拆成 (数量数据, 其它字段)。"""
    if not isinstance(payload, Mapping):
        return payload, {}
    rest = {key: value for key, value in payload.items() if key not in extra}
    if "amount" in payload:
        return payload["amount"], {key: payload[key] for key in extra if key in payload}
    if not rest:
        raise PluginError("%s缺少数量（amount / dice / flat）" % where)
    return rest, {key: payload[key] for key in extra if key in payload}


@dataclass(frozen=True, slots=True)
class Heal(Effect):
    """恢复 HP。回气、圣疗、治疗药水都走它。"""

    op: ClassVar[str] = "heal"
    amount: Amount
    target: str = "self"

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "Heal":
        data, extra = _split(payload, ("target",), where)
        return cls(amount=parse_amount(data, where=where), target=str(extra.get("target", "self")))

    def apply(self, ctx: EffectContext) -> None:
        pool = ctx.subject.root().hp
        value, rolled = self.amount.roll(ctx.ref_map(), ctx.rng)
        healed = pool.heal(value)
        if rolled is not None:
            ctx.roll("治疗", value, detail=rolled.describe())
        if healed:
            text = Text.of("恢复 %d 点生命" % healed, "Regained %d hit points" % healed)
        else:
            text = Text.of("生命值已满，掷出 %d 点未生效" % value,
                           "Already at full HP; %d had no effect" % value)
        ctx.note(text, self.op)
        ctx.hp_changed()
        ctx.scratch["healed"] = healed

    def to_dict(self) -> dict:
        return {"op": self.op, "amount": self.amount.to_dict(), "target": self.target}


@dataclass(frozen=True, slots=True)
class Damage(Effect):
    """造成伤害。抗性与减伤由调用方在结算前处理（P4 接防御管道）。"""

    op: ClassVar[str] = "damage"
    amount: Amount
    damage_type: str = ""
    target: str = "target"

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "Damage":
        data, extra = _split(payload, ("type", "damage_type", "target"), where)
        return cls(
            amount=parse_amount(data, where=where),
            damage_type=str(extra.get("type") or extra.get("damage_type") or ""),
            target=str(extra.get("target", "target")),
        )

    def apply(self, ctx: EffectContext) -> None:
        pool = ctx.subject.root().hp
        value, rolled = self.amount.roll(ctx.ref_map(), ctx.rng)
        applied = pool.damage(value)
        if rolled is not None:
            ctx.roll("伤害", value, detail=rolled.describe())
        suffix = "（%s）" % self.damage_type if self.damage_type else ""
        ctx.note(Text.of("受到 %d 点伤害%s" % (applied, suffix),
                         "Took %d damage%s" % (applied, " (%s)" % self.damage_type if self.damage_type else "")),
                 self.op)
        ctx.hp_changed()
        ctx.scratch["damage_taken"] = applied

    def to_dict(self) -> dict:
        return {"op": self.op, "amount": self.amount.to_dict(), "type": self.damage_type}


@dataclass(frozen=True, slots=True)
class GrantTempHp(Effect):
    """给临时 HP（取大不叠加）。"""

    op: ClassVar[str] = "grant_temp_hp"
    amount: Amount

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "GrantTempHp":
        data, _ = _split(payload, (), where)
        return cls(amount=parse_amount(data, where=where))

    def apply(self, ctx: EffectContext) -> None:
        value, rolled = self.amount.roll(ctx.ref_map(), ctx.rng)
        pool = ctx.subject.root().hp
        before = pool.temp
        effective = pool.grant_temp(value)
        if rolled is not None:
            ctx.roll("临时生命", value, detail=rolled.describe())
        ctx.note(
            Text.of("临时生命 %d（此前 %d，取高不叠加）" % (effective, before),
                    "Temp HP %d (was %d, higher applies)" % (effective, before)),
            self.op,
        )
        ctx.hp_changed()
        ctx.scratch["temp_granted"] = effective - before

    def to_dict(self) -> dict:
        return {"op": self.op, "amount": self.amount.to_dict()}


@dataclass(frozen=True, slots=True)
class ReduceDamage(Effect):
    """反应减伤：把「本可减免多少」交给结算方，自己不扣血。

    拨挡（武僧）、直觉闪避（游荡者）、轻身坠都是这一类：
    它们的差别只在「减免怎么算」，而不是「减伤」这个动作本身。
    """

    op: ClassVar[str] = "reduce_damage"
    amount: Amount
    damage_type: str = ""

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "ReduceDamage":
        data, extra = _split(payload, ("type", "damage_type"), where)
        return cls(
            amount=parse_amount(data, where=where),
            damage_type=str(extra.get("type") or extra.get("damage_type") or ""),
        )

    def apply(self, ctx: EffectContext) -> None:
        value, rolled = self.amount.roll(ctx.ref_map(), ctx.rng)
        if rolled is not None:
            ctx.roll("减伤", value, detail=rolled.describe())
        ctx.scratch["reduce_damage"] = int(ctx.scratch.get("reduce_damage", 0)) + value
    def to_dict(self) -> dict:
        return {"op": self.op, "amount": self.amount.to_dict(), "type": self.damage_type}


for _cls in (Heal, Damage, GrantTempHp, ReduceDamage):
    register(_cls)
