# -*- coding: utf-8 -*-
"""变形：压栈、可选形态过滤、临时 HP 的给予与收回。

这里只有机制，没有任何一种野兽的名字 —— 形态数据在内容插件里。

四条不变量（P4 的验收标准）：
  1. 属性：力/敏/体换成形态值，智/感/魅保留本体
  2. AC：用形态的 AC，护甲与盾牌在变形期间不生效
  3. HP：上限不变（写在本体池上），临时 HP 按 policy 给
  4. 动作：变形期间被禁止的事（如施法）由 forbid 沿层链生效
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from ..kernel.errors import IllegalAction, RuleError
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.levels import ClassLevel
from ..model.statblock import ABILITY_KEYS, Abilities, Statblock
from .monsters import MonsterAttack, MonsterTrait


@dataclass(frozen=True, slots=True)
class CrAxis:
    """CR 轴：等级门槛 → 最高 CR。阈值为「达到该等级时」。"""

    steps: Mapping[int, float]
    swim_from: int = 4
    fly_from: int = 8

    def __post_init__(self) -> None:
        if not self.steps:
            raise RuleError("CR 轴不能为空")
        for level, cr in self.steps.items():
            if int(level) < 1 or float(cr) < 0:
                raise RuleError("CR 轴条目不合法：%r=%r" % (level, cr))

    def max_cr(self, class_level: ClassLevel) -> float:
        usable = [int(level) for level in self.steps if int(level) <= int(class_level)]
        if not usable:
            return 0.0
        return float(self.steps[max(usable)])

    def allows_swim(self, class_level: ClassLevel) -> bool:
        return int(class_level) >= int(self.swim_from)

    def allows_fly(self, class_level: ClassLevel) -> bool:
        return int(class_level) >= int(self.fly_from)


@dataclass(frozen=True, slots=True)
class FormSpec:
    """一只可选形态。

    **形态就是那只野兽的整张卡**，不只是「变成它以后我的属性是多少」。
    所以除了 Statblock 要的字段，还带 `saves` 与 `traits` 与三槽动作：

    - `saves` 是**卡上印着的**豁免加值（猫的敏捷豁免 +4，敏捷只有 +2）。
      变形后的角色被人放法术时，`target_from_actor` 读的就是这一份 ——
      不带上它，德鲁伊变猫以后会用一个规则里没有的数去豁免。
    - `traits` 与动作都只有文字/数字，没有判定语义（G23 未修）。
    - 动作的**形状与怪物完全一样**（`MonsterAttack`），结算也走同一条
      `resolve_monster_attack` —— 两头各写一套的话，命中加值迟早对不上。

    `keep` 名单（荒野变形固定 int/wis/cha）在 `build_form` 里生效，
    所以这里存的六项属性是形态的原值，不是混合后的结果。
    """

    id: str
    name: Text
    ac: int
    hp: int
    cr: float
    abilities: Abilities
    speeds: Mapping[str, int]
    senses: Mapping[str, int] = None  # type: ignore[assignment]
    size: str = "medium"
    saves: Mapping[str, int] = None  # type: ignore[assignment]
    traits: tuple[MonsterTrait, ...] = ()
    actions: tuple[MonsterAttack, ...] = ()
    bonus_actions: tuple[MonsterAttack, ...] = ()
    reactions: tuple[MonsterAttack, ...] = ()

    def __post_init__(self) -> None:
        if self.ac < 1:
            raise RuleError("%s 的 AC 不合法：%r" % (self.id, self.ac))
        if self.hp < 1:
            raise RuleError("%s 的 HP 不合法：%r" % (self.id, self.hp))
        if self.cr < 0:
            raise RuleError("%s 的 CR 不能为负" % self.id)
        if self.senses is None:
            object.__setattr__(self, "senses", {})
        if self.saves is None:
            object.__setattr__(self, "saves", {})
        for key in self.saves:
            if key not in ABILITY_KEYS:
                raise RuleError("%s 的豁免加值写给了不存在的属性：%r" % (self.id, key))

    @property
    def can_swim(self) -> bool:
        return int(self.speeds.get("swim", 0)) > 0

    @property
    def can_fly(self) -> bool:
        return int(self.speeds.get("fly", 0)) > 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name.to_dict(),
            "ac": self.ac,
            "hp": self.hp,
            "cr": self.cr,
            "speed": dict(self.speeds),
        }


def max_cr(axis: CrAxis, class_level: ClassLevel) -> float:
    return axis.max_cr(class_level)


def eligible_forms(
    forms: Iterable[FormSpec],
    axis: CrAxis,
    class_level: ClassLevel,
) -> list[FormSpec]:
    """按 CR 与速度解禁过滤。游速 4 级、飞行 8 级 —— 这条常被漏掉。"""
    limit = axis.max_cr(class_level)
    allow_swim = axis.allows_swim(class_level)
    allow_fly = axis.allows_fly(class_level)
    picked = [
        form for form in forms
        if form.cr <= limit + 1e-9
        and (allow_swim or not form.can_swim)
        and (allow_fly or not form.can_fly)
    ]
    return sorted(picked, key=lambda item: (item.cr, item.id))


def reasons_for(axis: CrAxis, class_level: ClassLevel, form: FormSpec) -> list[str]:
    """某个形态为什么现在不可选 —— 前端用它显示灰掉的原因。"""
    reasons: list[str] = []
    limit = axis.max_cr(class_level)
    if form.cr > limit + 1e-9:
        reasons.append("CR %s 超过当前上限 %s" % (form.cr, limit))
    if form.can_swim and not axis.allows_swim(class_level):
        reasons.append("游泳速度要 %d 级才解禁" % axis.swim_from)
    if form.can_fly and not axis.allows_fly(class_level):
        reasons.append("飞行速度要 %d 级才解禁" % axis.fly_from)
    return reasons


def build_form(
    form: FormSpec,
    ac_min: int | None = None,
    keep: Sequence[str] = (),
    keep_scores: Mapping[str, int] | None = None,
) -> Actor:
    """把形态数据变成一层 Actor。

    `keep` 是「保留本体属性」的清单（荒野变形固定 int/wis/cha）——
    只换三项物理属性是 2024 的硬要求，不是可选风味，别省。

    ac_base 要减去敏捷调整值：Resolver 统一按「基础 + 敏捷」算，
    把最终 AC 反推成基础值，才不会重复加一次敏捷。

    ac_min 是「最终 AC 的下限」——月之环用 `13 + 感知调整值` 顶掉偏低的形态 AC。
    形态自带更高的 AC 时保留形态值，所以是 max 不是覆盖。

    `saves` 原样带进 Statblock（与 `build_monster` 同一个做法）：形态卡上印着的
    豁免加值不属于「保留本体」的那三项，它跟着形态走。
    """
    abilities = form.abilities
    if keep and keep_scores:
        overrides = {key: int(keep_scores[key]) for key in keep if key in keep_scores}
        if overrides:
            abilities = abilities.replace(**overrides)

    dex_mod = abilities.mod("dex")
    final_ac = int(form.ac)
    if ac_min is not None:
        final_ac = max(final_ac, int(ac_min))
    statblock = Statblock(
        name=form.name,
        abilities=abilities,
        ac_base=max(0, final_ac - dex_mod),
        speeds=dict(form.speeds),
        senses=dict(form.senses or {}),
        size=form.size,
        cr=form.cr,
        saves=dict(form.saves or {}),
    )
    return Actor(
        id="%s%s" % (FORM_PREFIX, form.id),
        kind=ActorKind.FORM,
        statblock=statblock,
        hp=HpPool(maximum=form.hp),
        display_name=form.name.zh,
    )


def enter_form(
    actor: Actor,
    form: FormSpec,
    temp_hp: int,
    forbid: Sequence[str] = (),
    ac_min: int | None = None,
    keep: Sequence[str] = ("int", "wis", "cha"),
) -> Actor:
    """压栈并给临时 HP。返回新的顶层。"""
    body = actor.root()
    if body.above is not None:
        body.above.unmorph()  # 已经在变形：先回本体，避免层链叠罗汉
    layer = build_form(form, ac_min, keep, body.statblock.abilities.scores)
    layer.forbid = tuple(forbid)
    body.morph_into(layer)
    before = body.hp.temp
    after = body.hp.grant_temp(int(temp_hp))
    layer.morph_temp = max(0, after - before)
    return layer


def leave_form(actor: Actor) -> Actor:
    """回到本体，收回形态给的临时 HP。"""
    top = actor.top()
    if top.layer is None:
        raise IllegalAction("当前没有变形")
    return top.unmorph()


def is_morphed(actor: Actor) -> bool:
    return actor.top().layer is not None


FORM_PREFIX = "form."


def form_id(actor: Actor) -> str | None:
    """变形中的角色对应哪一条形态内容；没变形返回 None。

    `build_form` 把层 Actor 的 id 写成 `form.<形态 id>`，因为层不是内容里的东西
    （同一只熊变成两次得到的是两个层），不能直接占用内容 id。这里拆回去。
    """
    top = actor.top()
    if top.kind is not ActorKind.FORM:
        return None
    ident = str(top.id)
    return ident[len(FORM_PREFIX):] if ident.startswith(FORM_PREFIX) else ident


def forbidden(actor: Actor, action: str) -> bool:
    return actor.top().forbids(action)
