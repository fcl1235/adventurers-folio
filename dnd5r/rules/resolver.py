# -*- coding: utf-8 -*-
"""派生值求解：AC / 豁免 / 攻击 / 法术 DC / 速度 / 技能。

所有结果都是 Resolution，因此每个数字都带来源明细。
这里不读内容，只吃 Modifier。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ..model.actor import Actor
from ..model.levels import ClassLevel, TotalLevel
from ..model.statblock import Abilities
from .modifiers import Modifier, Resolution, Stack, resolve


@dataclass(frozen=True, slots=True)
class RefContext:
    prof_bonus: int
    total_level: TotalLevel
    class_level: ClassLevel | None
    abilities: Abilities
    speeds: Mapping[str, int]

    def as_mapping(self) -> dict:
        return {
            "prof_bonus": self.prof_bonus,
            "total_level": int(self.total_level),
            "class_level": None if self.class_level is None else int(self.class_level),
            "abilities": self.abilities,
            "speeds": dict(self.speeds),
        }


class Resolver:
    """一个 Resolver 绑定一份上下文（通常对应一个角色当前状态）。"""

    def __init__(self, ctx: RefContext) -> None:
        self.ctx = ctx
        self._ctx_map = ctx.as_mapping()

    # --- 防御 ---------------------------------------------------------
    def armor_class(self, actor: Actor, modifiers: Iterable[Modifier] = ()) -> Resolution:
        stat = actor.top().statblock
        base = stat.ac_base + stat.abilities.mod("dex")
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    def saving_throw(
        self,
        actor: Actor,
        ability: str,
        proficient: bool = False,
        modifiers: Iterable[Modifier] = (),
    ) -> Resolution:
        stat = actor.top().statblock
        base = stat.abilities.mod(ability)
        if proficient:
            base += self.ctx.prof_bonus
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    # --- 进攻 ---------------------------------------------------------
    def attack_bonus(
        self,
        actor: Actor,
        ability: str = "str",
        proficient: bool = True,
        modifiers: Iterable[Modifier] = (),
    ) -> Resolution:
        stat = actor.top().statblock
        base = stat.abilities.mod(ability)
        if proficient:
            base += self.ctx.prof_bonus
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    def spell_dc(
        self,
        actor: Actor,
        ability: str = "int",
        modifiers: Iterable[Modifier] = (),
    ) -> Resolution:
        stat = actor.top().statblock
        base = 8 + self.ctx.prof_bonus + stat.abilities.mod(ability)
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    def spell_attack(
        self,
        actor: Actor,
        ability: str = "int",
        modifiers: Iterable[Modifier] = (),
    ) -> Resolution:
        stat = actor.top().statblock
        base = self.ctx.prof_bonus + stat.abilities.mod(ability)
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    # --- 机动与感知 ---------------------------------------------------
    def speed(self, actor: Actor, mode: str = "walk", modifiers: Iterable[Modifier] = ()) -> Resolution:
        base = actor.top().statblock.speed(mode)
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    def sense(self, actor: Actor, mode: str, modifiers: Iterable[Modifier] = ()) -> Resolution:
        base = int(actor.top().statblock.senses.get(mode, 0))
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    # --- 检定 ---------------------------------------------------------
    def ability_check(
        self,
        actor: Actor,
        ability: str,
        proficient: bool = False,
        expertise: bool = False,
        modifiers: Iterable[Modifier] = (),
    ) -> Resolution:
        stat = actor.top().statblock
        base = stat.abilities.mod(ability)
        if expertise:
            base += self.ctx.prof_bonus * 2
        elif proficient:
            base += self.ctx.prof_bonus
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    def passive_score(self, actor: Actor, ability: str, proficient: bool = False) -> int:
        return 10 + self.ability_check(actor, ability, proficient=proficient).total


def with_set(value: int, source: str) -> Modifier:
    """便捷构造：用 SET 替换基础公式（无甲防御、换 AC 公式时用）。"""
    return Modifier(target="ac", value=value, stack=Stack.SET, source=source)
