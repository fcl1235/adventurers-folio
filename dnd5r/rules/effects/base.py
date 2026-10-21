# -*- coding: utf-8 -*-
"""Effect 原语的基础设施。

一条 Effect 只做一件事，且必须落在一个封闭集合里（§3.3）。
新增原语的要求是「≥2 个不同职业的真实用例」，否则说明是在用原语写 if。

执行期共享的上下文（EffectContext）负责三件事：
  1. 给出符号引用需要的数值（职业等级、总等级、熟练加值、属性）
  2. 收集事件与掷骰明细，交给前端 / 掷骰记录
  3. 提供 scratch 供同一批效果之间传值（如减伤结果）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Type

from ...kernel.errors import PluginError
from ...kernel.events import Event, HpEvent, NoteEvent, Report, RollEvent
from ...kernel.rng import Rng
from ...kernel.text import Text
from ...model.actor import Actor
from ...model.levels import ClassLevel, TotalLevel


@dataclass
class EffectContext:
    """一次能力结算的全部上下文。"""

    actor: Actor
    rng: Rng
    locale: str = "zh"
    prof_bonus: int = 2
    total_level: TotalLevel = TotalLevel(1)
    class_level: ClassLevel | None = None
    source: str = ""
    subject: Actor | None = None
    events: list[Event] = field(default_factory=list)
    rolls: list[RollEvent] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    scratch: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.subject is None:
            self.subject = self.actor

    # --- 引用上下文 ---------------------------------------------------
    def ref_map(self) -> dict[str, Any]:
        stat = self.actor.top().statblock
        return {
            "prof_bonus": self.prof_bonus,
            "total_level": int(self.total_level),
            "class_level": None if self.class_level is None else int(self.class_level),
            "abilities": stat.abilities,
            "speeds": dict(stat.speeds),
        }

    # --- 收集 ---------------------------------------------------------
    def hp_changed(self) -> None:
        pool = self.subject.root().hp
        self.events.append(HpEvent(current=pool.current, maximum=pool.maximum, temp=pool.temp))

    def roll(self, label: str, total: int, detail: str = "", mode: str = "flat") -> None:
        self.rolls.append(RollEvent(label=label, total=total, detail=detail, mode=mode))

    def note(self, text: Text | str, source: str = "") -> None:
        self.notes.append(text.get(self.locale) if isinstance(text, Text) else str(text))
        if isinstance(text, Text):
            self.events.append(NoteEvent(text=text, source=source or self.source))

    def report(self, ok: bool = True, message: str = "") -> Report:
        return Report(
            events=tuple(self.events),
            rolls=tuple(self.rolls),
            ok=ok,
            message=message or "；".join(self.notes),
        )


class Effect:
    """效果原语基类。子类只实现 apply()，解析走 parse_effect()。"""

    op: ClassVar[str] = ""

    def apply(self, ctx: EffectContext) -> None:  # pragma: no cover - 抽象
        raise NotImplementedError

    def to_dict(self) -> dict:  # pragma: no cover - 调试用
        return {"op": self.op}

    def describe(self) -> str:  # pragma: no cover - 调试用
        return self.op


# --- 注册表 -----------------------------------------------------------
_REGISTRY: dict[str, Type[Effect]] = {}


def register(cls: Type[Effect]) -> Type[Effect]:
    if not cls.op:
        raise PluginError("%s 没有声明 op" % cls.__name__)
    if cls.op in _REGISTRY and _REGISTRY[cls.op] is not cls:
        raise PluginError("Effect 原语重名：%s" % cls.op)
    _REGISTRY[cls.op] = cls
    return cls


def known_ops() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def parse_effect(data: Any, where: str = "") -> Effect:
    """把 YAML 里的 {heal: {...}} / {apply_condition: raging} 变成 Effect 实例。"""
    prefix = ("%s: " % where) if where else ""
    if isinstance(data, Effect):
        return data
    if not isinstance(data, Mapping) or len(data) != 1:
        raise PluginError("%s效果必须写成 {原语: 参数} 的单键映射，实际 %r" % (prefix, data))

    op, payload = next(iter(data.items()))
    op = str(op)
    if op not in _REGISTRY:
        raise PluginError("%s未知效果原语 %r，可用：%s" % (prefix, op, ", ".join(known_ops())))
    try:
        return _REGISTRY[op].from_payload(payload, where=prefix)
    except TypeError as exc:  # 字段名写错时给一条能看懂的错
        raise PluginError("%s效果 %s 参数不匹配：%s" % (prefix, op, exc))


def parse_effects(items: Any, where: str = "") -> tuple[Effect, ...]:
    if items is None:
        return ()
    if not isinstance(items, (list, tuple)):
        raise PluginError("%s effects 必须是列表" % where)
    return tuple(parse_effect(item, where="%s[%d]" % (where, index)) for index, item in enumerate(items))


def effect_classes() -> Mapping[str, Type[Effect]]:
    return dict(_REGISTRY)
