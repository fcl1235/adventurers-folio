# -*- coding: utf-8 -*-
"""会话：前后端之间唯一的操作入口。

一条铁律：**前端不发方法名，发意图**。
`dispatch(UsePower("..."))` 返回 `(view, report)`，前端只负责把二者画出来。

Session 持有回合状态（动作经济、随机源、日志），角色本身的派生值仍然现算。
这样 CLI 能无头跑完整个流程 —— 这本身就是后端独立的证明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .content import ClassDef, ContentBundle, load_all
from .kernel.errors import DndError, IllegalAction
from .kernel.events import Report
from .kernel.rng import Rng, SeededRng
from .kernel.text import Text
from .model.actor import Actor
from .model.levels import ClassLevel, TotalLevel
from .model.profile import ClassEntry
from .rules.actioneconomy import ActionEconomy, ActionType
from .rules.build import available_powers, build_actor, eligible_forms_for, morph_class_of
from .rules.effects import EffectContext
from .rules.morph import FormSpec, is_morphed
from .rules.powers import Power, can_use, phase_label, use_power
from .rules.progression import proficiency_bonus
from .rules.rest import RestResult, long_rest, short_rest
from .rules.resolver import RefContext, Resolver
from .view import Card, CardAction, CharacterView, HeaderView


# --- 命令 -------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class UsePower:
    """用能力。`choice` 是这次操作需要玩家做的选择（如变形选哪个形态）。"""

    power_id: str
    choice: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ShortRest:
    dice: int = 0


@dataclass(frozen=True, slots=True)
class LongRest:
    pass


@dataclass(frozen=True, slots=True)
class NewTurn:
    pass


@dataclass(frozen=True, slots=True)
class TakeDamage:
    amount: int


@dataclass(frozen=True, slots=True)
class Regain:
    amount: int


Command = (UsePower, ShortRest, LongRest, NewTurn, TakeDamage, Regain)


class Session:
    def __init__(
        self,
        bundle: ContentBundle,
        locale: str = "zh",
        seed: int | None = None,
        rng: Rng | None = None,
    ) -> None:
        self.bundle = bundle
        self.locale = locale
        self.rng = rng or SeededRng(seed)
        self.economy = ActionEconomy()
        self.actor: Actor | None = None
        self.log: list[str] = []
        self.last_report: Report = Report()

    # --- 打开 ---------------------------------------------------------
    @classmethod
    def open(cls, root: str = "plugins", locale: str = "zh", seed: int | None = None) -> "Session":
        return cls(load_all(root), locale=locale, seed=seed)

    def create_character(
        self,
        class_id: str,
        class_level: int,
        scores: Mapping[str, int],
        name_zh: str = "无名冒险者",
        name_en: str = "Unnamed Adventurer",
        actor_id: str = "pc.hero",
    ) -> Actor:
        self.actor = build_actor(
            self.bundle, class_id=class_id, class_level=class_level,
            scores=scores, name_zh=name_zh, name_en=name_en, actor_id=actor_id,
        )
        self.economy = ActionEconomy(movement=self.actor.statblock.speed("walk"))
        self.log = []
        return self.actor

    @property
    def character(self) -> Actor:
        if self.actor is None:
            raise IllegalAction("会话里还没有角色")
        return self.actor

    # --- 上下文 -------------------------------------------------------
    def hit_dies(self) -> dict[str, int]:
        found: dict[str, int] = {}
        profile = self.character.profile
        if profile is None:
            return found
        for entry in profile.classes:
            class_def = self.bundle.classes.get(entry.class_id)
            if class_def is not None:
                found[entry.class_id] = class_def.hit_die
        return found

    def morph_class(self) -> tuple[ClassEntry, ClassDef] | None:
        """当前职业里带「形态轴」的那个（德鲁伊）。按数据找，不判 class_id。"""
        return morph_class_of(self.character, self.bundle)

    def forms(self) -> list[FormSpec]:
        """当前可选的全部形态：按 CR 轴 + 游速 4 级 / 飞行 8 级解禁过滤。

        还要求「变形能力本身已解锁」——1 级德鲁伊有 CR 轴但还没有荒野变形，
        这时候列出形态就是骗人。
        """
        return eligible_forms_for(self.character, self.bundle)

    def is_morphed(self) -> bool:
        return is_morphed(self.character)

    def resolver(self) -> Resolver:
        actor = self.character
        profile = actor.profile
        total = profile.total if profile else TotalLevel(1)
        class_level = None
        if profile and len(profile.classes) == 1:
            class_level = ClassLevel(int(profile.classes[0].class_level))
        top = actor.top()
        return Resolver(RefContext(
            prof_bonus=proficiency_bonus(total),
            total_level=total,
            class_level=class_level,
            abilities=top.statblock.abilities,
            speeds=dict(top.statblock.speeds),
        ))

    def context_for(self, power: Power | None = None) -> EffectContext:
        actor = self.character
        profile = actor.profile
        class_level = None
        if profile is not None:
            if power is not None and profile.has_class(power.owner):
                class_level = profile.class_level(power.owner)
            elif len(profile.classes) == 1:
                class_level = profile.classes[0].class_level
        total = profile.total if profile else TotalLevel(1)
        return EffectContext(
            actor=actor,
            rng=self.rng,
            locale=self.locale,
            prof_bonus=proficiency_bonus(total),
            total_level=total,
            class_level=class_level,
            source=power.id if power else "",
        )

    # --- 派发 ---------------------------------------------------------
    def dispatch(self, command: Any) -> tuple[CharacterView, Report]:
        try:
            report = self._handle(command)
        except DndError as exc:
            report = Report(ok=False, message=str(exc))
        if report.message:
            self.log.append(report.message)
        self.last_report = report
        return self.view(), report

    def _handle(self, command: Any) -> Report:
        if isinstance(command, UsePower):
            return self._use_power(command.power_id, command.choice)
        if isinstance(command, ShortRest):
            return self._rest(short_rest(self.character, self.hit_dies(),
                                        spend=command.dice, rng=self.rng))
        if isinstance(command, LongRest):
            return self._rest(long_rest(self.character))
        if isinstance(command, NewTurn):
            self.economy.start_turn(movement=self.character.statblock.speed("walk"))
            return Report(ok=True, message="新回合：动作与附赠动作已恢复")
        if isinstance(command, TakeDamage):
            applied = self.character.root().hp.damage(int(command.amount))
            return Report(ok=True, message="受到 %d 点伤害" % applied)
        if isinstance(command, Regain):
            healed = self.character.root().hp.heal(int(command.amount))
            return Report(ok=True, message="恢复 %d 点生命" % healed)
        raise IllegalAction("不认识的命令：%r" % (command,))

    def _use_power(self, power_id: str, choice: Mapping[str, Any] | None = None) -> Report:
        power = self._resolve_power(power_id)
        context = self.context_for(power)
        context.scratch.update(self._scratch(power, choice or {}))
        report = use_power(power, context, self.economy)
        for key, amount in list(context.scratch.items()):
            if key.startswith("granted_"):
                try:
                    self.economy.grant(ActionType(key[len("granted_"):]), int(amount))
                except DndError:
                    continue
        return report

    def _resolve_power(self, power_id: str) -> Power:
        """取「这个角色当前等级下」的能力对象。

        不能直接查 PowerBook：叠层（18 级野兽施法解除施法禁令）是按等级
        现算的，book 里那份是未叠层的原版。
        """
        for power in available_powers(self.bundle, self.character):
            if power.id == power_id:
                return power
        return self.bundle.book.get(power_id)   # 不存在时抛「没有这个能力」

    def _scratch(self, power: Power, choice: Mapping[str, Any]) -> dict[str, Any]:
        """把这次操作需要的数据塞进 scratch（变形要选形态就是这么进来的）。"""
        scratch: dict[str, Any] = dict(choice)
        if any(getattr(effect, "op", "") == "morph" for effect in power.effects):
            scratch["forms"] = {form.id: form for form in self.forms()}
        return scratch

    def _rest(self, result: RestResult) -> Report:
        self.economy = ActionEconomy(movement=self.character.statblock.speed("walk"))
        return Report(ok=True, message=result.summary)

    # --- 投影 ---------------------------------------------------------
    def view(self) -> CharacterView:
        actor = self.character
        resolver = self.resolver()
        top = actor.top()
        profile = actor.profile
        ac = resolver.armor_class(top)

        classes: list[str] = []
        level = 1
        if profile is not None:
            for entry in profile.classes:
                class_def = self.bundle.classes.get(entry.class_id)
                label = class_def.name.get(self.locale) if class_def else entry.class_id
                classes.append("%s %d" % (label, int(entry.class_level)))
            level = int(profile.total)

        header = HeaderView(
            name=top.statblock.name.get(self.locale),
            classes=tuple(classes),
            level=level,
            hp=actor.hp.current,
            hp_max=actor.hp.maximum,
            temp_hp=actor.hp.temp,
            ac=ac.total,
            ac_detail=ac.describe(),
            speed={mode: resolver.speed(top, mode).total for mode in top.statblock.speeds},
            proficiency_bonus=proficiency_bonus(profile.total if profile else TotalLevel(1)),
            conditions=actor.conditions.ids(),
        )

        cards = self._power_cards() + self._pool_cards()
        return CharacterView(
            header=header,
            cards=tuple(cards),
            attacks=self._attack_cards(),
            log=tuple(self.log[-12:]),
        )

    def _power_cards(self) -> list[Card]:
        actor = self.character
        profile = actor.profile
        cards: list[Card] = []
        if profile is None:
            return cards
        for entry in profile.classes:
            class_def = self.bundle.classes.get(entry.class_id)
            if class_def is None:
                continue
            for power in class_def.powers_at(entry.class_level):
                cards.append(self._card_for(power))
        return cards

    def _card_for(self, power: Power) -> Card:
        title = power.name.get(self.locale)
        detail = (power.text.get(self.locale),)
        if not power.is_button:
            subtitle = "被动" if power.kind.value == "passive" else {
                "triggered": "触发：%s" % phase_label(power.phase),
            }.get(power.kind.value, power.kind.value)
            value, _ = self._cost_value(power)
            return Card(id="power:%s" % power.id, title=title, subtitle=subtitle,
                        value=value, tone="dim", detail=detail)

        reasons = can_use(power, self.context_for(power), self.economy)
        value, tone = self._cost_value(power)
        badges = tuple(
            ["kind.%s" % power.kind.value] + (["blocked"] if reasons else [])
        )
        return Card(
            id="power:%s" % power.id,
            title=title,
            subtitle=power.subtitle(self.locale),
            value=value,
            tone="dim" if reasons else tone,
            badges=badges,
            actions=() if reasons else (
                CardAction(command="use_power", label=title,
                           payload={"power_id": power.id}),
            ),
            detail=detail + tuple(reasons),
        )

    def _cost_value(self, power: Power) -> tuple[str, str]:
        cost = power.cost
        if cost is None or not cost.resource:
            return "", "normal"
        root = self.character.root().resources
        if not root.has(cost.resource):
            return "—", "dim"
        pool = root.get(cost.resource)
        return "%d/%d" % (pool.available, pool.capacity), ("dim" if pool.available == 0 else "normal")

    def _pool_cards(self) -> list[Card]:
        """只给「没有按钮对应」的池出卡：按钮卡上已经显示余量，重复会看花眼。"""
        taken = {power.cost.resource
                 for power in self.bundle.book.all()
                 if power.is_button and power.cost and power.cost.resource}
        cards = []
        for pool in self.character.root().resources.pools.values():
            if pool.id in taken:
                continue
            title = pool.label.get(self.locale) if pool.label else pool.id.split(".")[-1]
            if pool.id.startswith("hit_dice."):
                title = "生命骰"
            cards.append(Card(
                id="pool:%s" % pool.id,
                title=title,
                subtitle={"charge": "次数", "point": "点数", "slot_level": "环级",
                          "dice": "骰池"}.get(pool.kind.value, pool.kind.value),
                value="%d/%d" % (pool.available, pool.capacity),
                tone="dim" if pool.available == 0 else "normal",
                badges=("refresh.%s" % pool.refresh.value,),
            ))
        return cards

    def _attack_cards(self) -> list[Card]:
        actor = self.character
        resolver = self.resolver()
        top = actor.top()
        ability = "str" if top.statblock.abilities.mod("str") >= top.statblock.abilities.mod("dex") else "dex"
        attack = resolver.attack_bonus(top, ability, proficient=True)
        count = 1
        profile = actor.profile
        if profile is not None:
            for entry in profile.classes:
                class_def = self.bundle.classes.get(entry.class_id)
                if class_def is not None:
                    count = max(count, class_def.total_attacks(entry.class_level))
        label = {"str": "力量", "dex": "敏捷"}.get(ability, ability)
        return (Card(
            id="attack:basic",
            title="普通攻击",
            subtitle="%s武器 · +%d" % (label, attack.total),
            value="%d 次/动作" % count,
            tone="normal",
            detail=("武器数据在 P5 接入；当前只验证攻击加值与攻击次数。",),
        ),)

    def report_dict(self) -> dict:
        report = self.last_report
        return {
            "ok": report.ok,
            "message": report.message,
            "events": [type(event).__name__ for event in report.events],
            "rolls": [{"label": roll.label, "total": roll.total, "detail": roll.detail}
                      for roll in report.rolls],
        }


__all__ = [
    "Session", "UsePower", "ShortRest", "LongRest", "NewTurn", "TakeDamage", "Regain",
]
