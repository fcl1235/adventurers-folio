# -*- coding: utf-8 -*-
"""Power：一切「能做 / 会发生的事」的统一描述符（§3.3）。

职业特性、专长、法术、物品动作、怪物动作都是 Power，只是 owner 不同。
四种 kind 的区别只有「谁发起」：

  PASSIVE    不出按钮，只贡献 Modifier / 熟练 / 抗性
  ACTIVATED  玩家主动点，付动作与资源
  REACTION   额外要求反应
  TRIGGERED  条件满足时由引擎提问（至圣斩命中后才决定花不花位）

这里没有一处 if class_id —— 职业差异全部来自数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from ..kernel.errors import IllegalAction, PluginError, RuleError
from ..kernel.events import Report
from ..kernel.predicate import evaluate as eval_when
from ..kernel.predicate import explain as explain_when
from ..kernel.text import Text
from ..model.levels import ClassLevel, as_class_level
from .actioneconomy import ActionEconomy, ActionType
from .effects import Effect, EffectContext, parse_effects


class PowerKind(str, Enum):
    PASSIVE = "passive"
    ACTIVATED = "activated"
    REACTION = "reaction"
    TRIGGERED = "triggered"

    @classmethod
    def parse(cls, data: Any) -> "PowerKind":
        if isinstance(data, cls):
            return data
        key = str(data).strip().lower()
        if key not in {item.value for item in cls}:
            raise PluginError("未知能力类型 %r（可选 passive/activated/reaction/triggered）" % (data,))
        return cls(key)


class Phase(str, Enum):
    """TRIGGERED 的提问时点。"""

    ON_INITIATIVE = "on_initiative"
    ON_TURN_START = "on_turn_start"
    ON_TURN_END = "on_turn_end"
    ON_HIT = "on_hit"
    ON_DAMAGED = "on_damaged"
    ON_ZERO_HP = "on_zero_hp"
    ON_FAIL_SAVE = "on_fail_save"
    ON_FAIL_CHECK = "on_fail_check"
    ON_USE_POWER = "on_use_power"

    @classmethod
    def parse(cls, data: Any) -> "Phase":
        if isinstance(data, cls):
            return data
        key = str(data).strip().lower()
        if key not in {item.value for item in cls}:
            raise PluginError("未知触发时点 %r" % (data,))
        return cls(key)


@dataclass(frozen=True, slots=True)
class Cost:
    """支付方式。动作、资源、法术位三者可以同时要求。"""

    action: ActionType = ActionType.NONE
    resource: str | None = None
    amount: int = 1
    slot_level: int | None = None
    label: str = ""

    @classmethod
    def parse(cls, data: Any) -> "Cost | None":
        if data is None:
            return None
        if isinstance(data, Cost):
            return data
        if isinstance(data, str):
            return cls(action=ActionType.parse(data))
        if not isinstance(data, Mapping):
            raise PluginError("cost 必须是映射或动作名：%r" % (data,))
        unknown = [key for key in data if key not in ("action", "resource", "amount", "slot_level", "label")]
        if unknown:
            raise PluginError("cost 里有未知字段：%s" % ", ".join(sorted(unknown)))
        return cls(
            action=ActionType.parse(data.get("action", "none")),
            resource=(str(data["resource"]) if data.get("resource") else None),
            amount=int(data.get("amount", 1)),
            slot_level=(int(data["slot_level"]) if data.get("slot_level") else None),
            label=str(data.get("label", "")),
        )

    def describe(self) -> str:
        bits = []
        if self.action is not ActionType.NONE and self.action is not ActionType.FREE:
            bits.append({"action": "动作", "bonus": "附赠动作", "reaction": "反应"}.get(
                self.action.value, self.action.value))
        if self.resource:
            name = self.label or self.resource.split(".")[-1]
            bits.append("%s ×%d" % (name, self.amount))
        if self.slot_level:
            bits.append("%d 环法术位" % self.slot_level)
        return " · ".join(bit for bit in bits if bit) or "无花费"


@dataclass(frozen=True, slots=True)
class Power:
    id: str
    name: Text
    text: Text
    owner: str
    level: ClassLevel = ClassLevel(0)
    kind: PowerKind = PowerKind.PASSIVE
    cost: Cost | None = None
    target: str = "self"
    effects: tuple[Effect, ...] = ()
    phase: Phase | None = None
    when: Mapping[str, Any] | None = None
    prereq: Mapping[str, Any] | None = None
    augments: tuple[str, ...] = ()
    patch: Mapping[str, Any] | None = None
    tags: tuple[str, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise RuleError("Power.id 不能为空")
        if not isinstance(self.name, Text) or not isinstance(self.text, Text):
            raise RuleError("Power %s 的 name/text 必须是双语 Text（C7）" % self.id)
        if not isinstance(self.kind, PowerKind):
            raise RuleError("Power %s 的 kind 必须是 PowerKind" % self.id)
        if self.kind is PowerKind.TRIGGERED and self.phase is None:
            raise RuleError("Power %s 是 triggered，必须声明 phase" % self.id)
        if self.kind is PowerKind.PASSIVE and self.patch is None and not self.effects and not self.augments:
            raise RuleError("Power %s 是 passive 但既无 effects 也无 augments/patch" % self.id)

    # --- 展示 ---------------------------------------------------------
    @property
    def is_button(self) -> bool:
        """只有主动类才该在界面上出现按钮。"""
        return self.kind in (PowerKind.ACTIVATED, PowerKind.REACTION)

    def subtitle(self, locale: str = "zh") -> str:
        return self.cost.describe() if self.cost else (
            "被动" if self.kind is PowerKind.PASSIVE else self.kind.value
        )

    def describe(self, locale: str = "zh") -> str:
        return self.name.get(locale)

    def blocked_reasons(self, facts: Mapping[str, Any]) -> list[str]:
        """「为什么点不了」。前端不判断规则，只展示这里的结果。"""
        return explain_when(self.prereq, dict(facts)) if self.prereq else []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner": self.owner,
            "level": int(self.level),
            "kind": self.kind.value,
            "name": self.name.to_dict(),
            "text": self.text.to_dict(),
            "cost": None if self.cost is None else {
                "action": self.cost.action.value,
                "resource": self.cost.resource,
                "amount": self.cost.amount,
            },
            "effects": [effect.to_dict() for effect in self.effects],
        }


# --- 解析 -------------------------------------------------------------
_PATCHABLE = ("cost", "target", "level", "when", "text", "name")


def parse_power(data: Any, owner: str = "", source: str = "") -> Power:
    if not isinstance(data, Mapping):
        raise PluginError("能力条目必须是映射：%r" % (data,))
    missing = [key for key in ("id", "name", "text") if key not in data]
    if missing:
        raise PluginError("能力 %r 缺少字段：%s" % (data.get("id", "?"), ", ".join(missing)))

    ident = str(data["id"])
    try:
        level = as_class_level(int(data.get("level", 1)))
    except RuleError as exc:
        raise PluginError("能力 %s 的等级不合法：%s" % (ident, exc))

    phase = data.get("phase")
    return Power(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        text=Text.from_dict(data["text"], where="%s text" % ident),
        owner=str(data.get("owner", owner)),
        level=level,
        kind=PowerKind.parse(data.get("kind", "passive")),
        cost=Cost.parse(data.get("cost")),
        target=str(data.get("target", "self")),
        effects=parse_effects(data.get("effects"), where=ident),
        phase=Phase.parse(phase) if phase else None,
        when=data.get("when"),
        prereq=data.get("prereq"),
        augments=tuple(str(item) for item in (data.get("augments") or ())),
        patch=data.get("patch"),
        tags=tuple(str(item) for item in (data.get("tags") or ())),
        source=source,
    )


# --- 能力集合 ---------------------------------------------------------
@dataclass
class PowerBook:
    """一个角色可见的能力集合（内容插件的产物，可按职业查询）。"""

    _by_id: dict[str, Power] = field(default_factory=dict)
    _sources: dict[str, str] = field(default_factory=dict)
    _augmented: bool = False

    def add(self, power: Power, replace_existing: bool = False) -> Power:
        if power.id in self._by_id and not replace_existing:
            raise PluginError(
                "能力 id 冲突：%s 已由 %s 提供，%s 又想加"
                % (power.id, self._sources.get(power.id) or "?", power.source or "?")
            )
        self._by_id[power.id] = power
        self._sources[power.id] = power.source or power.owner
        return power

    def get(self, power_id: str) -> Power:
        if power_id not in self._by_id:
            raise PluginError("没有这个能力：%s" % power_id)
        return self._by_id[power_id]

    def has(self, power_id: str) -> bool:
        return power_id in self._by_id

    def all(self) -> tuple[Power, ...]:
        return tuple(self._by_id[key] for key in sorted(self._by_id))

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id))

    def by_owner(self, owner: str) -> tuple[Power, ...]:
        return tuple(power for power in self.all() if power.owner == owner)

    def for_class(self, class_id: str, class_level: ClassLevel) -> tuple[Power, ...]:
        """这个职业在当前等级下已经解锁的能力（按等级、id 排序）。"""
        picked = [
            power for power in self.by_owner(class_id)
            if int(power.level) <= int(class_level)
        ]
        return tuple(sorted(picked, key=lambda item: (int(item.level), item.id)))

    def buttons_for(self, class_id: str, class_level: ClassLevel) -> tuple[Power, ...]:
        return tuple(power for power in self.for_class(class_id, class_level) if power.is_button)

    def passives_for(self, class_id: str, class_level: ClassLevel) -> tuple[Power, ...]:
        return tuple(
            power for power in self.for_class(class_id, class_level)
            if power.kind is PowerKind.PASSIVE
        )

    # --- 叠层（G9） ---------------------------------------------------
    def apply_augments(self) -> "PowerBook":
        """把 passive 的 patch 合并进目标能力，返回新集合。

        只允许改白名单字段：改 effects 里的骰数这类需求，先扩原语，
        不要在这里开任意字段的口子。
        """
        if self._augmented:
            return self
        book = PowerBook(dict(self._by_id), dict(self._sources), self._augmented)
        for power in self.all():
            if not power.augments:
                continue
            if power.kind is not PowerKind.PASSIVE:
                raise PluginError("%s 声明了 augments 但本身不是 passive；"
                                  "只有被动特性才能改写别的能力" % power.id)
            for target_id in power.augments:
                if target_id not in book._by_id:
                    raise PluginError("%s 想增强不存在的能力 %s（来自 %s）"
                                      % (power.id, target_id, power.source or "?"))
                target = book._by_id[target_id]
                changes = _patch_fields(target, power)
                book._by_id[target_id] = replace(target, **changes)
        book._augmented = True
        return book

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for power in self._by_id.values():
            counts[power.kind.value] = counts.get(power.kind.value, 0) + 1
        return dict(sorted(counts.items()))


def _patch_fields(target: Power, augment: Power) -> dict[str, Any]:
    patch = dict(augment.patch or {})
    if not patch:
        raise PluginError("%s 声明了 augments 却没有 patch" % augment.id)
    unknown = [key for key in patch if key not in _PATCHABLE]
    if unknown:
        raise PluginError(
            "%s 的 patch 里有不可改的字段：%s（可改：%s）"
            % (augment.id, ", ".join(sorted(unknown)), ", ".join(_PATCHABLE))
        )
    changes: dict[str, Any] = {}
    for key, value in patch.items():
        if key == "cost":
            changes["cost"] = Cost.parse(value)
        elif key == "level":
            changes["level"] = as_class_level(int(value))
        else:
            changes[key] = value
    if "name" in changes and isinstance(changes["name"], Mapping):
        changes["name"] = Text.from_dict(changes["name"], where="%s patch name" % augment.id)
    if "text" in changes and isinstance(changes["text"], Mapping):
        changes["text"] = Text.from_dict(changes["text"], where="%s patch text" % augment.id)
    return changes


# --- 执行 -------------------------------------------------------------
_ACTION_ZH = {
    ActionType.ACTION: "动作",
    ActionType.BONUS: "附赠动作",
    ActionType.REACTION: "反应",
    ActionType.FREE: "额外动作",
    ActionType.NONE: "动作",
}

_PHASE_ZH = {
    Phase.ON_INITIATIVE: "先攻时",
    Phase.ON_TURN_START: "回合开始时",
    Phase.ON_TURN_END: "回合结束时",
    Phase.ON_HIT: "命中后",
    Phase.ON_DAMAGED: "受伤后",
    Phase.ON_ZERO_HP: "生命归零时",
    Phase.ON_FAIL_SAVE: "豁免失败后",
    Phase.ON_FAIL_CHECK: "检定失败后",
    Phase.ON_USE_POWER: "使用能力时",
}


def phase_label(phase: Phase | None) -> str:
    return _PHASE_ZH.get(phase, phase.value if phase else "—")


def can_use(
    power: Power,
    ctx: EffectContext,
    economy: ActionEconomy | None = None,
) -> list[str]:
    """返回阻止使用的原因列表（空表示可用）。前端只读这个结果。"""
    reasons: list[str] = []
    if not power.is_button:
        reasons.append("%s 不是主动能力" % power.id)

    cost = power.cost
    if cost is not None:
        if economy is not None and not economy.can_pay(cost.action):
            reasons.append("本回合没有可用的%s" % _ACTION_ZH.get(cost.action, cost.action.value))
        if cost.resource:
            root = ctx.actor.root()
            if not root.resources.has(cost.resource):
                reasons.append("缺少资源池 %s" % cost.resource)
            elif not root.resources.get(cost.resource).can_spend(cost.amount):
                pool = root.resources.get(cost.resource)
                reasons.append("%s 剩余 %d，不足 %d" % (cost.resource, pool.available, cost.amount))

    if power.prereq:
        facts = _facts(ctx)
        reasons.extend(power.blocked_reasons(facts))
    return reasons


def _facts(ctx: EffectContext) -> dict:
    actor = ctx.actor
    facts: dict[str, Any] = {
        "level": int(ctx.class_level or 0),
        "total_level": int(ctx.total_level),
        "prof_bonus": ctx.prof_bonus,
        "conditions": set(actor.conditions.ids()),
        "resources": {key: actor.root().resources.get(key).available
                      for key in actor.root().resources.ids()},
    }
    for pool_id in actor.root().resources.ids():
        facts[pool_id.replace(".", "_")] = actor.root().resources.get(pool_id).available
    return facts


def use_power(
    power: Power,
    ctx: EffectContext,
    economy: ActionEconomy | None = None,
) -> Report:
    """执行一个主动能力。检查 → 付费 → 按序跑效果 → 汇总报告。"""
    reasons = can_use(power, ctx, economy)
    if reasons:
        raise IllegalAction("%s 无法使用：%s" % (power.name.zh, "；".join(reasons)))

    if power.when is not None and not eval_when(power.when, _facts(ctx)):
        raise IllegalAction("%s 的触发条件不满足：%s"
                            % (power.name.zh, "；".join(explain_when(power.when, _facts(ctx)))))

    cost = power.cost
    if cost is not None:
        if economy is not None:
            economy.pay(cost.action, label=power.name.zh)
        if cost.resource:
            ctx.actor.root().resources.spend(cost.resource, cost.amount)

    for effect in power.effects:
        effect.apply(ctx)

    return ctx.report()
