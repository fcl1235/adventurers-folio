# -*- coding: utf-8 -*-
"""派生值求解：AC / 豁免 / 攻击 / 法术 DC / 速度 / 技能。

所有结果都是 Resolution，因此每个数字都带来源明细。
这里不读内容，只吃 Modifier。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..model.actor import Actor
from ..model.levels import ClassLevel, TotalLevel
from ..model.statblock import Abilities
from .modifiers import Modifier, Resolution, Stack, resolve

# d20 上唯一能自然掷出的重击面。门槛只会被能力往小改，永远不会超过它
CRIT_ON_20 = 20


@dataclass(frozen=True, slots=True)
class RefContext:
    prof_bonus: int
    total_level: TotalLevel
    class_level: ClassLevel | None
    abilities: Abilities
    speeds: Mapping[str, int]
    facts: Mapping[str, Any] = field(default_factory=dict)

    def as_mapping(self) -> dict:
        base = {
            "prof_bonus": self.prof_bonus,
            "total_level": int(self.total_level),
            "class_level": None if self.class_level is None else int(self.class_level),
            "abilities": self.abilities,
            "speeds": dict(self.speeds),
        }
        base.update(dict(self.facts))
        return base


class Resolver:
    """一个 Resolver 绑定一份上下文（通常对应一个角色当前状态）。"""

    def __init__(self, ctx: RefContext) -> None:
        self.ctx = ctx
        self._ctx_map = ctx.as_mapping()

    # --- 防御 ---------------------------------------------------------
    def armor_class(
        self,
        actor: Actor,
        modifiers: Iterable[Modifier] = (),
        base: int | None = None,
    ) -> Resolution:
        """`base` 缺省是「statblock 的 AC + 敏捷」；穿甲时由 `armor.ac_inputs()` 给。

        护甲不走 base 而走 SET Modifier，是为了让明细读得出「14 环甲 + 1 敏捷 + 2 盾牌」，
        而不是一句「基础 17」。
        """
        stat = actor.top().statblock
        if base is None:
            base = stat.ac_base + stat.abilities.mod("dex")
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    def _d20_check(
        self,
        stat,
        ability: str,
        proficient: bool,
        expertise: bool,
        modifiers: Iterable[Modifier],
        mode: str = "flat",
        mode_sources: Iterable[str] = (),
    ) -> Resolution:
        """d20 + 属性调整值 + 熟练（+ 专精），外加这一次的掷骰模式。

        熟练**不再并进 base**：把它做成一条 term，明细才写得出
        「6 = 3 DEX +3 熟练」。并进 base 的写法数值一样，但界面上只剩一个 6，
        玩家没法核对，也看不出有没有丢掉专精。

        掷骰模式（优势/劣势）由调用方算好传进来：**Resolver 不读内容**，
        而「角色身上有哪些优势」要读能力与条件（`contributions.passive_advantage_modes`）。
        这里只负责把模式挂到结果上，不自己去找。
        """
        terms = list(modifiers)
        if expertise:
            terms.append(Modifier(target="proficiency",
                                  value=self.ctx.prof_bonus * 2, source="专精"))
        elif proficient:
            terms.append(Modifier(target="proficiency",
                                  value=self.ctx.prof_bonus, source="熟练"))
        return resolve(terms, base=stat.abilities.mod(ability), ctx=self._ctx_map,
                       base_label=ability.upper(), mode=mode, mode_sources=mode_sources)

    def saving_throw(
        self,
        actor: Actor,
        ability: str,
        proficient: bool = False,
        modifiers: Iterable[Modifier] = (),
        mode: str = "flat",
        mode_sources: Iterable[str] = (),
    ) -> Resolution:
        return self._d20_check(actor.top().statblock, ability, proficient, False, modifiers,
                               mode=mode, mode_sources=mode_sources)

    # --- 进攻 ---------------------------------------------------------
    def attack_bonus(
        self,
        actor: Actor,
        ability: str = "str",
        proficient: bool = True,
        modifiers: Iterable[Modifier] = (),
        mode: str = "flat",
        mode_sources: Iterable[str] = (),
    ) -> Resolution:
        return self._d20_check(actor.top().statblock, ability, proficient, False, modifiers,
                               mode=mode, mode_sources=mode_sources)

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

    def crit_range(self, actor: Actor, modifiers: Iterable[Modifier] = ()) -> Resolution:
        """重击门槛：默认 20，「19 或 20 即重击」写成 `stack: min` 的 19。

        用 MIN 而不是 ADD，因为这是**门槛**不是加值：强化重击（19）叠加
        卓越重击（18）应该得 18，加法会变成 17。内容里写
        `grant_modifier: {target: attack.crit_min, value: 19, stack: min}`。
        """
        return resolve(modifiers, base=CRIT_ON_20, ctx=self._ctx_map)

    # --- 机动与感知 ---------------------------------------------------
    def speed(self, actor: Actor, mode: str = "walk", modifiers: Iterable[Modifier] = ()) -> Resolution:
        base = actor.top().statblock.speed(mode)
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    def sense(self, actor: Actor, mode: str, modifiers: Iterable[Modifier] = ()) -> Resolution:
        base = int(actor.top().statblock.senses.get(mode, 0))
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    def bonus(self, modifiers: Iterable[Modifier] = (), base: int = 0) -> Resolution:
        """只算加值，不带属性与熟练（箭术的远程 +2 这类条件加值用它）。

        不要拿 `attack_bonus(proficient=False)` 代替：那会顺带把属性调整值算进去。
        """
        return resolve(modifiers, base=base, ctx=self._ctx_map)

    # --- 检定 ---------------------------------------------------------
    def ability_check(
        self,
        actor: Actor,
        ability: str,
        proficient: bool = False,
        expertise: bool = False,
        modifiers: Iterable[Modifier] = (),
        mode: str = "flat",
        mode_sources: Iterable[str] = (),
    ) -> Resolution:
        return self._d20_check(actor.top().statblock, ability, proficient, expertise, modifiers,
                               mode=mode, mode_sources=mode_sources)

    def initiative(self, actor: Actor, modifiers: Iterable[Modifier] = (),
                   mode: str = "flat", mode_sources: Iterable[str] = ()) -> Resolution:
        """先攻 = 敏捷检定，但优势标记走自己的名字（野性本能、卓越运动员）。

        「先攻熟练」（警觉）不在这里：那是加值，走 `initiative` modifier 通道。
        """
        return self._d20_check(actor.top().statblock, "dex", False, False, modifiers,
                               mode=mode, mode_sources=mode_sources)

    def passive_score(self, actor: Actor, ability: str, proficient: bool = False) -> int:
        return 10 + self.ability_check(actor, ability, proficient=proficient).total


def with_set(value: int, source: str) -> Modifier:
    """便捷构造：用 SET 替换基础公式（无甲防御、换 AC 公式时用）。"""
    return Modifier(target="ac", value=value, stack=Stack.SET, source=source)


def crit_text(threshold: int) -> str:
    """门槛 → 界面写法：20 就是「20」，19 就是「19-20」。不需要翻译。"""
    value = int(threshold)
    if value >= CRIT_ON_20:
        return str(CRIT_ON_20)
    return "%d-%d" % (max(1, value), CRIT_ON_20)
