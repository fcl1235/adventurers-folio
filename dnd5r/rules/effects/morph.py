# -*- coding: utf-8 -*-
"""变形原语：把形态压到本体之上，并给临时 HP。

形态数据由会话注入（`ctx.scratch["forms"]`），所以这个原语对「有哪些野兽」
一无所知 —— 加一本新怪物手册不需要改这里。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from ...kernel.errors import IllegalAction, PluginError
from ...kernel.text import Text
from ...model.statblock import ABILITY_KEYS
from ..amount import Amount, parse_amount
from ..morph import enter_form, leave_form
from .base import Effect, EffectContext, register


@dataclass(frozen=True, slots=True)
class Morph(Effect):
    op: ClassVar[str] = "morph"
    temp_hp: Amount | None = None
    forbid: tuple[str, ...] = ()
    keep: tuple[str, ...] = ("int", "wis", "cha")
    ac_min: Amount | None = None

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "Morph":
        if not isinstance(payload, Mapping):
            raise PluginError("%s morph 参数必须是映射" % where)
        unknown = [key for key in payload
                   if key not in ("temp_hp", "forbid", "keep", "forms", "ac_min")]
        if unknown:
            raise PluginError("%s morph 里有未知字段：%s" % (where, ", ".join(sorted(unknown))))
        temp = payload.get("temp_hp")
        ac_min = payload.get("ac_min")
        forbid = payload.get("forbid") or ()
        if isinstance(forbid, str):
            forbid = (forbid,)
        keep = payload.get("keep") or ("int", "wis", "cha")
        bad = [key for key in keep if key not in ABILITY_KEYS]
        if bad:
            raise PluginError("%s morph.keep 里有未知属性：%s" % (where, ", ".join(sorted(bad))))
        return cls(
            temp_hp=parse_amount(temp, where="%s temp_hp" % where) if temp is not None else None,
            forbid=tuple(str(item) for item in forbid),
            keep=tuple(str(item) for item in keep),
            ac_min=parse_amount(ac_min, where="%s ac_min" % where) if ac_min is not None else None,
        )

    def apply(self, ctx: EffectContext) -> None:
        form_id = ctx.scratch.get("form_id")
        if not form_id:
            raise IllegalAction("变形需要先选一个形态")

        forms = ctx.scratch.get("forms") or {}
        if form_id not in forms:
            raise IllegalAction("这个形态当前不可选：%s" % form_id)

        temp = 0
        if self.temp_hp is not None:
            temp, rolled = self.temp_hp.roll(ctx.ref_map(), ctx.rng)
            if rolled is not None:
                ctx.roll("临时生命", temp, detail=rolled.describe())

        ac_min = None
        if self.ac_min is not None:
            ac_min = self.ac_min.evaluate(ctx.ref_map())

        layer = enter_form(ctx.actor, forms[form_id], temp, self.forbid, ac_min, self.keep)
        ctx.scratch["morphed_now"] = form_id
        ctx.note(
            Text.of("变形为 %s（临时生命 %d）" % (layer.statblock.name.zh, layer.morph_temp),
                    "Transformed into %s (%d temp HP)" % (layer.statblock.name.en, layer.morph_temp)),
            self.op,
        )

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "temp_hp": self.temp_hp.to_dict() if self.temp_hp else None,
            "forbid": list(self.forbid),
            "ac_min": self.ac_min.to_dict() if self.ac_min else None,
        }


@dataclass(frozen=True, slots=True)
class Revert(Effect):
    """回本体。荒野变形的「提前结束」走它（正常到时也走同一条路径）。"""

    op: ClassVar[str] = "revert"

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "Revert":
        if payload not in (None, {}, True):
            raise PluginError("%s revert 不接受参数" % where)
        return cls()

    def apply(self, ctx: EffectContext) -> None:
        body = leave_form(ctx.actor)
        ctx.scratch["reverted"] = True
        ctx.note(
            Text.of("恢复本体形态（临时生命已收回）", "Reverted to your true form"),
            self.op,
        )
        ctx.scratch["hp_after"] = body.hp.current

    def to_dict(self) -> dict:
        return {"op": self.op}


for _cls in (Morph, Revert):
    register(_cls)
