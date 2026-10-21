# -*- coding: utf-8 -*-
"""授予型原语：给调整值、给抗性、给熟练、给优势、给动作。

这一类的共同点是「不直接改数字，而是留下一个持续生效的来源」。
所以它们产出 ActiveEffect，由 Resolver 在执行期收集 —— 效果结束就自动消失，
不需要任何回滚代码。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Sequence

from ...kernel.errors import PluginError
from ...kernel.text import Text
from ...model.effect_instance import ActiveEffect, Duration, DurationKind
from ..modifiers import Direction, Modifier, Scope, Stack
from .base import Effect, EffectContext, register

_PROF_KINDS = ("skill", "save", "armor", "weapon", "language", "tool")


def _modifier(data: Any, source: str, where: str) -> Modifier:
    if isinstance(data, Modifier):
        return data
    if not isinstance(data, Mapping):
        raise PluginError("%s modifier 必须是映射" % where)
    target = data.get("target")
    if not target:
        raise PluginError("%s modifier 缺少 target" % where)
    raw_value = data.get("value", 0)
    if isinstance(raw_value, str):
        from ..modifiers import Ref  # 延迟导入避免环

        value: Any = Ref(raw_value)
    elif isinstance(raw_value, bool):
        raise PluginError("%s modifier.value 不能是布尔值" % where)
    else:
        value = int(raw_value)
    stack = data.get("stack", "add")
    try:
        stack_value = Stack(str(stack).lower())
    except ValueError:
        raise PluginError("%s 未知叠加方式 %r" % (where, stack))
    direction = data.get("direction", "given")
    try:
        direction_value = Direction(str(direction).lower())
    except ValueError:
        raise PluginError("%s 未知方向 %r" % (where, direction))
    scope = data.get("scope", "self")
    try:
        scope_value = Scope(str(scope).lower())
    except ValueError:
        raise PluginError("%s 未知作用域 %r" % (where, scope))
    when = data.get("when")
    return Modifier(
        target=str(target),
        value=value,
        stack=stack_value,
        source=source,
        scope=scope_value,
        direction=direction_value,
        when=when,
    )


def _duration(data: Any) -> Duration:
    return Duration.parse(data) if data is not None else Duration(DurationKind.PERMANENT)


@dataclass(frozen=True, slots=True)
class GrantModifier(Effect):
    """持续/被动调整值。狂暴伤害、无甲防御、光环都走它。"""

    op: ClassVar[str] = "grant_modifier"
    modifiers: tuple[Modifier, ...]
    duration: Duration = field(default_factory=lambda: Duration(DurationKind.PERMANENT))
    label: str = ""

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "GrantModifier":
        if isinstance(payload, Mapping) and "modifiers" in payload:
            rows = payload["modifiers"]
            duration = payload.get("duration")
            label = str(payload.get("label", ""))
        elif isinstance(payload, (list, tuple)):
            rows, duration, label = payload, None, ""
        else:
            rows, duration, label = [payload], (
                payload.get("duration") if isinstance(payload, Mapping) else None
            ), ""
        if not isinstance(rows, (list, tuple)):
            rows = [rows]
        built = tuple(_modifier(row, where=where, source="") for row in rows)
        return cls(modifiers=built, duration=_duration(duration), label=label)

    def apply(self, ctx: EffectContext) -> None:
        source = ctx.source or self.op
        mods = [
            mod if mod.source else Modifier(
                target=mod.target, value=mod.value, stack=mod.stack,
                source=source, scope=mod.scope, direction=mod.direction, when=mod.when,
            )
            for mod in self.modifiers
        ]
        effect = ActiveEffect(
            id="%s:%s" % (source, self.op),
            source=source,
            label=self.label,
            modifiers=list(mods),
            duration=self.duration,
        )
        ctx.subject.effects.append(effect)
        names = "、".join(mod.target for mod in mods)
        ctx.note(Text.of("获得加值：%s（%s）" % (names, self.duration.short()),
                         "Gained modifiers on %s (%s)" % (names, self.duration.kind.value)),
                 self.op)

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "modifiers": [{"target": m.target, "value": m.describe_value(),
                           "stack": m.stack.value} for m in self.modifiers],
            "duration": {"kind": self.duration.kind.value, "value": self.duration.value},
        }


@dataclass(frozen=True, slots=True)
class GrantDefense(Effect):
    """抗性 / 免疫 / 易伤。狂暴的三项物理抗性是它的标准用例。"""

    op: ClassVar[str] = "grant_defense"
    resistance: tuple[str, ...] = ()
    immunity: tuple[str, ...] = ()
    vulnerability: tuple[str, ...] = ()
    duration: Duration = field(default_factory=lambda: Duration(DurationKind.PERMANENT))

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "GrantDefense":
        if isinstance(payload, str):
            payload = {"resistance": [payload]}
        if not isinstance(payload, Mapping):
            raise PluginError("%s grant_defense 参数必须是映射" % where)
        built = cls(
            resistance=_strs(payload.get("resistance") or payload.get("resist")),
            immunity=_strs(payload.get("immunity") or payload.get("immune")),
            vulnerability=_strs(payload.get("vulnerability") or payload.get("vulnerable")),
            duration=_duration(payload.get("duration")),
        )
        if not (built.resistance or built.immunity or built.vulnerability):
            raise PluginError("%s grant_defense 至少要给 resistance / immunity / vulnerability" % where)
        return built

    def apply(self, ctx: EffectContext) -> None:
        source = ctx.source or self.op
        ctx.subject.effects.append(ActiveEffect(
            id="%s:%s" % (source, self.op),
            source=source,
            resistances=self.resistance,
            immunities=self.immunity,
            duration=self.duration,
        ))
        bits = []
        if self.resistance:
            bits.append("抗性 " + "/".join(self.resistance))
        if self.immunity:
            bits.append("免疫 " + "/".join(self.immunity))
        if self.vulnerability:
            bits.append("易伤 " + "/".join(self.vulnerability))
        ctx.note(Text.of("获得" + "、".join(bits), "Gained " + ", ".join(bits)), self.op)

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "resistance": list(self.resistance),
            "immunity": list(self.immunity),
            "duration": {"kind": self.duration.kind.value, "value": self.duration.value},
        }


@dataclass(frozen=True, slots=True)
class GrantProficiency(Effect):
    """集合型贡献：熟练是集合，不是加减法（§11 G2）。

    统一写成带前缀的 token：skill.perception / save.wis / armor.medium /
    weapon.martial / language.elvish / tool.thieves。
    永久熟练写入 Profile；带时长的写进 ActiveEffect。
    """

    op: ClassVar[str] = "grant_proficiency"
    tokens: tuple[str, ...] = ()
    duration: Duration = field(default_factory=lambda: Duration(DurationKind.PERMANENT))

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "GrantProficiency":
        if isinstance(payload, str):
            tokens = [payload]
            duration = None
        elif isinstance(payload, (list, tuple)):
            tokens, duration = list(payload), None
        elif isinstance(payload, Mapping):
            duration = payload.get("duration")
            tokens = []
            for kind in _PROF_KINDS:
                for item in _strs(payload.get(kind) or payload.get(kind + "s")):
                    tokens.append("%s.%s" % (kind, item))
            if not tokens:
                raise PluginError("%s grant_proficiency 至少要给一类熟练（%s）"
                                  % (where, "/".join(_PROF_KINDS)))
        else:
            raise PluginError("%s grant_proficiency 参数不合法" % where)
        return cls(tokens=tuple(tokens), duration=_duration(duration))

    def apply(self, ctx: EffectContext) -> None:
        if self.duration.kind is not DurationKind.PERMANENT:
            source = ctx.source or self.op
            ctx.subject.effects.append(ActiveEffect(
                id="%s:%s" % (source, self.op),
                source=source,
                conditions=(), duration=self.duration,
            ))
            ctx.note(Text.of("临时熟练：%s" % "、".join(self.tokens),
                             "Temporary proficiencies: %s" % ", ".join(self.tokens)), self.op)
            return

        profile = ctx.subject.profile
        if profile is None:
            ctx.note(Text.of("无档案，熟练未落库：%s" % "、".join(self.tokens),
                             "No profile; proficiencies not recorded"), self.op)
            return
        languages = {token.split(".", 1)[1] for token in self.tokens if token.startswith("language.")}
        others = tuple(token for token in self.tokens if not token.startswith("language."))
        ctx.subject.profile = profile.with_proficiencies(add=others)
        if languages:
            ctx.subject.profile = _with_languages(ctx.subject.profile, languages)
        ctx.note(Text.of("获得熟练：%s" % "、".join(self.tokens),
                         "Gained proficiencies: %s" % ", ".join(self.tokens)), self.op)

    def to_dict(self) -> dict:
        return {"op": self.op, "tokens": list(self.tokens)}


def _with_languages(profile, extra):
    from ...model.profile import Profile

    return Profile(
        classes=profile.classes,
        proficiencies=profile.proficiencies,
        expertise=profile.expertise,
        languages=frozenset(set(profile.languages) | set(extra)),
        feats=profile.feats,
        choices=profile.choices,
    )


@dataclass(frozen=True, slots=True)
class GrantAdvantage(Effect):
    """优势 / 劣势，带方向（GIVEN 我给的，TAKEN 我承受的）。"""

    op: ClassVar[str] = "grant_advantage"
    target: str = "check.all"
    direction: Direction = Direction.GIVEN
    mode: str = "adv"          # adv / dis
    duration: Duration = field(default_factory=lambda: Duration(DurationKind.PERMANENT))

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "GrantAdvantage":
        if isinstance(payload, str):
            payload = {"target": payload}
        if not isinstance(payload, Mapping):
            raise PluginError("%s grant_advantage 参数必须是映射" % where)
        raw = str(payload.get("direction", "given")).lower()
        try:
            direction = Direction(raw)
        except ValueError:
            raise PluginError("%s 未知方向 %r" % (where, raw))
        mode = str(payload.get("mode", "adv")).lower()
        if mode not in ("adv", "dis"):
            raise PluginError("%s mode 只能是 adv 或 dis" % where)
        return cls(
            target=str(payload.get("target", "check.all")),
            direction=direction,
            mode=mode,
            duration=_duration(payload.get("duration")),
        )

    def apply(self, ctx: EffectContext) -> None:
        source = ctx.source or self.op
        token = "advantage.%s.%s" % (self.mode, self.target)
        ctx.subject.effects.append(ActiveEffect(
            id="%s:%s" % (source, token),
            source=source,
            label=token,
            duration=self.duration,
        ))
        word = "优势" if self.mode == "adv" else "劣势"
        ctx.note(Text.of("%s：%s" % (word, self.target), "%s on %s" % (word, self.target)), self.op)

    def to_dict(self) -> dict:
        return {"op": self.op, "target": self.target, "mode": self.mode,
                "direction": self.direction.value}


@dataclass(frozen=True, slots=True)
class GrantAction(Effect):
    """额外动作 / 把动作变成附赠 / 速度归零（行动激增、灵巧动作）。"""

    op: ClassVar[str] = "grant_action"
    kind: str = "action"       # action / bonus / reaction / movement
    amount: int = 1

    @classmethod
    def from_payload(cls, payload: Any, where: str = "") -> "GrantAction":
        if isinstance(payload, int) and not isinstance(payload, bool):
            payload = {"amount": payload}
        if not isinstance(payload, Mapping):
            raise PluginError("%s grant_action 参数必须是映射" % where)
        kind = str(payload.get("kind", payload.get("type", "action"))).lower()
        if kind not in ("action", "bonus", "reaction", "movement"):
            raise PluginError("%s 未知动作类型 %r" % (where, kind))
        return cls(kind=kind, amount=int(payload.get("amount", 1)))

    def apply(self, ctx: EffectContext) -> None:
        key = "granted_%s" % self.kind
        ctx.scratch[key] = int(ctx.scratch.get(key, 0)) + self.amount
        ctx.note(Text.of("获得额外%s ×%d" % (self.kind, self.amount),
                         "Gained extra %s x%d" % (self.kind, self.amount)), self.op)

    def to_dict(self) -> dict:
        return {"op": self.op, "kind": self.kind, "amount": self.amount}


def _strs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    raise PluginError("期望字符串或列表，实际 %r" % (value,))


for _cls in (GrantModifier, GrantDefense, GrantProficiency, GrantAdvantage, GrantAction):
    register(_cls)
