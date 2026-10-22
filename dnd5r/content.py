# -*- coding: utf-8 -*-
"""内容加载：把插件里的 YAML 变成 ClassDef / Power / ResourceDef。

三条原则：
  1. **内容不进代码**：这里是唯一读 YAML 的地方，规则层只吃解析好的对象。
  2. **坏内容只坏自己**：单个文件解析失败记进 errors，其余内容照常可用。
  3. **解析期就校验**：双语（C7）、id 规范、引用存在、效果可解析，
     全部在加载时炸掉，而不是等到玩家点了按钮才崩。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from .kernel.dice import parse as parse_dice
from .kernel.errors import DiceError, DndError, PluginError, RuleError
from .kernel.ids import is_valid
from .kernel.text import Text
from .model.inventory import EquipSlot
from .plugin import Manifest, load_manifest
from .rules.amount import Amount, parse_amount
from .rules.effects import parse_effects
from .rules.morph import CrAxis, FormSpec
from .rules.powers import Power, PowerBook, apply_patch, parse_power
from .rules.progression import CasterKind, attacks_per_action
from .rules.summon import (
    SENSE_KINDS,
    SIZES,
    SPEED_KINDS,
    SummonAction,
    parse_action,
    parse_scaling,
    resolve as resolve_summon,
)
from .model.levels import ClassLevel, as_class_level
from .model.resources import Pool, PoolKind, Refresh
from .model.statblock import Abilities

RESOURCE_KINDS = {item.value: item for item in PoolKind}
REFRESH_KINDS = {item.value: item for item in Refresh}


# --- 资源 -------------------------------------------------------------
@dataclass(frozen=True)
class ResourceDef:
    """一个资源池的定义。次数表放数据里，代码只负责查表。"""

    id: str
    kind: PoolKind
    refresh: Refresh = Refresh.LONG_REST
    capacity: Amount | None = None
    by_level: Mapping[int, int] | None = None
    recover_on_short_rest: int = 0
    label: Text | None = None
    owner_class: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("资源 id 不合规范：%r" % (self.id,))
        if self.capacity is None and not self.by_level:
            raise PluginError("资源 %s 必须给 capacity 或 by_level" % self.id)
        if self.by_level:
            for key, value in self.by_level.items():
                if int(key) < 1 or int(value) < 0:
                    raise PluginError("资源 %s 的等级表不合法：%r=%r" % (self.id, key, value))

    def capacity_at(self, level: ClassLevel, ref_map: Mapping[str, Any] | None = None) -> int:
        """按「本职业等级」查表。兼职时次数按职业等级，不按总等级（G15）。"""
        if self.by_level:
            usable = [int(key) for key in self.by_level if int(key) <= int(level)]
            if not usable:
                return 0
            return int(self.by_level[max(usable)])
        assert self.capacity is not None
        if ref_map is None:
            if self.capacity.times is not None or self.capacity.plus is not None:
                raise PluginError(
                    "资源 %s 的容量依赖等级引用，必须提供 ref_map" % self.id
                )
            return self.capacity.flat
        return self.capacity.evaluate(ref_map)

    def build(self, level: ClassLevel, ref_map: Mapping[str, Any] | None = None) -> Pool:
        return Pool(
            id=self.id,
            kind=self.kind,
            capacity=self.capacity_at(level, ref_map),
            label=self.label,
            owner_class=self.owner_class or None,
            refresh=self.refresh,
            recover_on_short_rest=self.recover_on_short_rest,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind.value, "refresh": self.refresh.value,
            "by_level": dict(self.by_level or {}),
            "recover_on_short_rest": self.recover_on_short_rest,
        }


def parse_resource(data: Any, owner_class: str = "") -> ResourceDef:
    if not isinstance(data, Mapping):
        raise PluginError("资源条目必须是映射：%r" % (data,))
    ident = data.get("id")
    if not ident:
        raise PluginError("资源缺少 id")
    kind_key = str(data.get("kind", "charge")).lower()
    if kind_key not in RESOURCE_KINDS:
        raise PluginError("%s 的资源类型必须是 %s" % (ident, "/".join(sorted(RESOURCE_KINDS))))
    refresh_key = str(data.get("refresh", "long_rest")).lower()
    if refresh_key not in REFRESH_KINDS:
        raise PluginError("%s 的恢复方式必须是 %s" % (ident, "/".join(sorted(REFRESH_KINDS))))

    by_level = None
    if data.get("by_level"):
        try:
            by_level = {int(key): int(value) for key, value in data["by_level"].items()}
        except (TypeError, ValueError):
            raise PluginError("%s 的 by_level 必须是 等级→次数 的映射" % ident)

    capacity = None
    if data.get("capacity") is not None:
        capacity = parse_amount(data["capacity"], where="%s capacity" % ident)

    label = None
    if data.get("label") is not None:
        label = Text.from_dict(data["label"], where="%s label" % ident)

    return ResourceDef(
        id=str(ident),
        kind=RESOURCE_KINDS[kind_key],
        refresh=REFRESH_KINDS[refresh_key],
        capacity=capacity,
        by_level=by_level,
        recover_on_short_rest=int(data.get("recover_on_short_rest", 0)),
        label=label,
        owner_class=str(data.get("owner", owner_class)),
    )


# --- 物品：护甲与盾 ---------------------------------------------------
ARMOR_CATEGORIES = ("light", "medium", "heavy", "shield")


@dataclass(frozen=True)
class ArmorDef:
    """一件护甲或一面盾。

    只放「参与 AC 计算」的字段：类别、基础值、敏捷上限、盾牌加值。
    力量需求与隐匿劣势是**展示用**的，规则层不用它们算数
    （2024 的力量需求只影响速度，属于负重/装备整套接入时再算）。
    """

    id: str
    name: Text
    category: str = "light"
    ac_base: int = 10
    dex_cap: int | None = None
    bonus: int = 0
    str_req: int = 0
    stealth: bool = False
    weight: float = 0.0

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("护甲 id 不合规范：%r" % (self.id,))
        if self.category not in ARMOR_CATEGORIES:
            raise PluginError("%s 的护甲类别必须是 %s"
                              % (self.id, "/".join(ARMOR_CATEGORIES)))
        if self.category == "shield":
            if self.bonus < 1:
                raise PluginError("%s 是盾牌，bonus 至少是 1" % self.id)
        else:
            if self.ac_base < 1:
                raise PluginError("%s 的 ac_base 至少是 1" % self.id)
            if self.dex_cap is not None and self.dex_cap < 0:
                raise PluginError("%s 的 dex_cap 不能为负：%r" % (self.id, self.dex_cap))
        if self.bonus < 0:
            raise PluginError("%s 的 bonus 不能为负" % self.id)

    @property
    def slot(self) -> EquipSlot:
        return EquipSlot.SHIELD if self.category == "shield" else EquipSlot.ARMOR

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name.to_dict(), "category": self.category,
            "ac_base": self.ac_base, "dex_cap": self.dex_cap, "bonus": self.bonus,
        }


def parse_armor(data: Any, where: str = "") -> ArmorDef:
    prefix = ("%s: " % where) if where else ""
    if not isinstance(data, Mapping):
        raise PluginError("%s护甲条目必须是映射" % prefix)
    ident = data.get("id")
    if not ident:
        raise PluginError("%s护甲缺少 id" % prefix)
    if "name" not in data:
        raise PluginError("%s %s 缺少 name" % (prefix, ident))
    dex_cap = data.get("dex_cap")
    if dex_cap is not None:
        try:
            dex_cap = int(dex_cap)
        except (TypeError, ValueError):
            raise PluginError("%s %s 的 dex_cap 必须是整数：%r" % (prefix, ident, dex_cap))
    try:
        return ArmorDef(
            id=str(ident),
            name=Text.from_dict(data["name"], where="%s name" % ident),
            category=str(data.get("category", "light")).lower(),
            ac_base=int(data.get("ac_base", 10)),
            dex_cap=dex_cap,
            bonus=int(data.get("bonus", 0)),
            str_req=int(data.get("str_req", 0)),
            stealth=bool(data.get("stealth", False)),
            weight=float(data.get("weight", 0)),
        )
    except (TypeError, ValueError) as exc:
        raise PluginError("%s %s 的数值字段不合法：%s" % (prefix, ident, exc))


# --- 物品：武器 -------------------------------------------------------
WEAPON_CATEGORIES = ("simple", "martial")
# 武器的物理伤害只有这三种。**不要**叫 `DAMAGE_TYPES` —— 那个名字下面还有一个
# 13 种的同名常量（召唤物 / 抗性用的全集），后定义会静默盖掉这一个，
# 于是「武器伤害类型是 fire」这种错数据能过校验。名字分开，两边互不影响。
WEAPON_DAMAGE_TYPES = ("bludgeoning", "piercing", "slashing")
WEAPON_PROPERTIES = (
    "light", "finesse", "two_handed", "versatile", "thrown",
    "heavy", "reach", "loading", "ranged",
)


@dataclass(frozen=True)
class WeaponDef:
    """一件武器。伤害骰、属性、专精全在数据里，规则层只做推论。

    `versatile` 是双手握持时的另一档伤害；没有它就不能双手加值。
    """

    id: str
    name: Text
    category: str = "simple"
    damage: str = "1d4"
    damage_type: str = "bludgeoning"
    versatile: str | None = None
    properties: tuple[str, ...] = ()
    mastery: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("武器 id 不合规范：%r" % (self.id,))
        if self.category not in WEAPON_CATEGORIES:
            raise PluginError("%s 的武器类别必须是 %s"
                              % (self.id, "/".join(WEAPON_CATEGORIES)))
        if self.damage_type not in WEAPON_DAMAGE_TYPES:
            raise PluginError("%s 的伤害类型必须是 %s"
                              % (self.id, "/".join(WEAPON_DAMAGE_TYPES)))
        unknown = [item for item in self.properties if item not in WEAPON_PROPERTIES]
        if unknown:
            raise PluginError("%s 的武器属性未知：%s" % (self.id, ", ".join(unknown)))
        if self.versatile and "versatile" not in self.properties:
            raise PluginError("%s 有 versatile 伤害却没声明 versatile 属性" % self.id)
        for field_name, expr in (("damage", self.damage), ("versatile", self.versatile)):
            if expr is None:
                continue
            try:
                parse_dice(str(expr))
            except DndError as exc:
                raise PluginError("%s 的 %s 不是合法骰式：%s" % (self.id, field_name, exc))

    def has(self, prop: str) -> bool:
        return prop in self.properties

    def dice(self, two_handed: bool = False):
        """伤害骰。两用武器双手握持取 `versatile` 那一档。"""
        expr = self.versatile if (two_handed and self.versatile) else self.damage
        return parse_dice(str(expr))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name.to_dict(), "category": self.category,
            "damage": self.damage, "damage_type": self.damage_type,
            "versatile": self.versatile, "properties": list(self.properties),
            "mastery": self.mastery,
        }


def parse_weapon(data: Any, where: str = "") -> WeaponDef:
    prefix = ("%s: " % where) if where else ""
    if not isinstance(data, Mapping):
        raise PluginError("%s武器条目必须是映射" % prefix)
    ident = data.get("id")
    if not ident:
        raise PluginError("%s武器缺少 id" % prefix)
    if "name" not in data:
        raise PluginError("%s %s 缺少 name" % (prefix, ident))
    props = data.get("properties") or ()
    if isinstance(props, str):
        props = [props]
    return WeaponDef(
        id=str(ident),
        name=Text.from_dict(data["name"], where="%s name" % ident),
        category=str(data.get("category", "simple")).lower(),
        damage=str(data.get("damage", "1d4")),
        damage_type=str(data.get("damage_type", "bludgeoning")).lower(),
        versatile=None if data.get("versatile") in (None, "") else str(data["versatile"]),
        properties=tuple(str(item).lower() for item in props),
        mastery=str(data.get("mastery", "")).lower(),
    )


# --- 职业 -------------------------------------------------------------
def powers_at_level(powers: tuple[Power, ...], class_level: ClassLevel) -> tuple[Power, ...]:
    """当前等级解锁的能力，**并且把已解锁的 patch 应用进去**。

    叠层必须在这里做而不是加载时做：18 级的「野兽施法」要解除变形期间
    的施法禁令，如果在加载时全局套用，2 级德鲁伊也能施法了。

    职业与子职共用这一份实现：子职特性的等级也按**父职业等级**算，
    「3 级才拿子职」这条规则由等级门槛自然表达，不需要额外的开关。
    """
    picked = [power for power in powers if int(power.level) <= int(class_level)]
    picked.sort(key=lambda item: (int(item.level), item.id))
    index = {power.id: power for power in picked}
    for power in picked:
        if not power.augments:
            continue
        for target_id in power.augments:
            if target_id in index:      # 目标也解锁了才叠，跨职业的交由校验期报错
                index[target_id] = apply_patch(index[target_id], power)
    return tuple(index[power.id] for power in picked)


@dataclass(frozen=True)
class ClassDef:
    id: str
    name: Text
    hit_die: int
    primary: tuple[str, ...] = ()
    saves: tuple[str, ...] = ()
    caster: CasterKind = CasterKind.NONE
    # 施法属性（cha/wis/int）：。caster 只说是全/半/契约施法者，不说用哪个属性
    casting_ability: str = ""
    subclass_level: ClassLevel = ClassLevel(3)
    skill_choices: int = 2
    skill_list: tuple[str, ...] = ()
    resources: tuple[ResourceDef, ...] = ()
    powers: tuple[Power, ...] = ()
    # 武器/护甲熟练，统一写带前缀的 token：weapon.simple / armor.light
    proficiencies: tuple[str, ...] = ()
    morph: CrAxis | None = None
    # 法术位表：等级 → (1 环, 2 环, …, 9 环)。内核只查表，不写公式
    slots: Mapping[int, tuple[int, ...]] = field(default_factory=dict)
    cantrips: Mapping[int, int] = field(default_factory=dict)
    prepared: Mapping[int, int] = field(default_factory=dict)
    slot_refresh: Refresh = Refresh.LONG_REST   # 邪术师契约位是短休恢复
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("职业 id 不合规范：%r" % (self.id,))
        if self.hit_die < 2:
            raise PluginError("%s 的生命骰面不合法：%r" % (self.id, self.hit_die))
        for key in self.saves:
            if key not in ("str", "dex", "con", "int", "wis", "cha"):
                raise PluginError("%s 的豁免熟练含未知属性：%r" % (self.id, key))
        if self.casting_ability and self.casting_ability not in (
                "str", "dex", "con", "int", "wis", "cha"):
            raise PluginError("%s 的施法属性不合法：%r" % (self.id, self.casting_ability))
        if self.caster is not CasterKind.NONE and not self.casting_ability:
            raise PluginError("%s 是施法职业，必须声明 casting_ability" % self.id)
        if self.caster is CasterKind.NONE and self.casting_ability:
            raise PluginError("%s 不是施法职业，却声明了 casting_ability" % self.id)
        seen = set()
        for resource in self.resources:
            if resource.id in seen:
                raise PluginError("%s 的资源 id 重复：%s" % (self.id, resource.id))
            seen.add(resource.id)

    def resource(self, resource_id: str) -> ResourceDef:
        for item in self.resources:
            if item.id == resource_id:
                return item
        raise PluginError("%s 没有资源 %s" % (self.id, resource_id))

    def powers_at(self, class_level: ClassLevel) -> tuple[Power, ...]:
        """当前等级解锁的能力（含叠层）。规则见 `powers_at_level()`。"""
        return powers_at_level(self.powers, class_level)

    def slots_at(self, class_level: ClassLevel) -> tuple[int, ...]:
        """这一级的 9 个环位容量。没有该级条目时按最近的下界（与资源表同规则）。"""
        if not self.slots:
            return (0,) * 9
        usable = [int(key) for key in self.slots if int(key) <= int(class_level)]
        if not usable:
            return (0,) * 9
        row = tuple(self.slots[max(usable)])
        return row + (0,) * (9 - len(row))

    def total_attacks(self, class_level: ClassLevel) -> int:
        """额外攻击取最大不叠加（Extra Attack 的 Stack.MAX 语义）。

        数据里写成 `grant_modifier: {target: attack.count, value: 2, stack: max}`，
        所以「5 级战士兼 5 级圣武士变成四打」这种错误结构上不可能发生。
        """
        pairs = []
        for power in self.powers_at(class_level):
            for effect in power.effects:
                for mod in getattr(effect, "modifiers", ()):
                    if mod.target == "attack.count" and isinstance(mod.value, int):
                        pairs.append((power.id, mod.value))
        return attacks_per_action(pairs)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name.to_dict(), "hit_die": self.hit_die,
            "primary": list(self.primary), "saves": list(self.saves),
            "caster": self.caster.value, "casting_ability": self.casting_ability,
            "subclass_level": int(self.subclass_level),
            "resources": [item.to_dict() for item in self.resources],
            "powers": len(self.powers),
        }


# --- 子职 -------------------------------------------------------------
@dataclass(frozen=True)
class SubclassDef:
    """一个子职：挂在某个职业上的一组特性。

    子职**不是**职业的字段，而是独立内容：它自带 id、自带特性表，
    通过 `class_id` 挂回去。这样「一个职业有四个子职」不需要职业文件知道
    任何子职的事，第三方插件也能给已有职业补子职。
    """

    id: str
    class_id: str
    name: Text
    summary: Text
    unlock_level: ClassLevel = ClassLevel(3)
    powers: tuple[Power, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("子职 id 不合规范：%r" % (self.id,))
        if not is_valid(self.class_id):
            raise PluginError("子职 %s 的 class_id 不合规范：%r" % (self.id, self.class_id))
        seen = set()
        for power in self.powers:
            if power.id in seen:
                raise PluginError("子职 %s 的特性 id 重复：%s" % (self.id, power.id))
            seen.add(power.id)

    def powers_at(self, class_level: ClassLevel) -> tuple[Power, ...]:
        """按**父职业等级**解锁的特性（含叠层）。"""
        if int(class_level) < int(self.unlock_level):
            return ()
        return powers_at_level(self.powers, class_level)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "class": self.class_id,
            "name": self.name.to_dict(),
            "summary": self.summary.to_dict(),
            "unlock_level": int(self.unlock_level),
            "powers": len(self.powers),
        }


def parse_subclass(data: Any, source: str = "", unlock_level: int = 3) -> SubclassDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的子职定义必须是映射" % source)
    for key in ("id", "class", "name", "powers"):
        if key not in data:
            raise PluginError("%s 的子职定义缺少 %s" % (source, key))

    ident = str(data["id"])
    powers = tuple(
        parse_power(row, owner=ident, source=source)
        for row in (data.get("powers") or ())
    )
    try:
        level = as_class_level(int(data.get("unlock_level", unlock_level)))
    except RuleError as exc:
        raise PluginError("%s 的子职解锁等级不合法：%s" % (ident, exc))
    return SubclassDef(
        id=ident,
        class_id=str(data["class"]),
        name=Text.from_dict(data["name"], where="%s name" % ident),
        # summary 可以省：没有就退回名字，免得界面上出现空行
        summary=Text.from_dict(data["summary"], where="%s summary" % ident)
        if data.get("summary") else Text.from_dict(data["name"], where="%s name" % ident),
        unlock_level=level,
        powers=powers,
        source=source,
    )


# --- 专长 -------------------------------------------------------------
# 专长的「静态部分」直接写成 powers（与职业特性同一套原语），
# 「玩家选择部分」写成 choices —— 选完才知道加成多少，不能在加载期算死。
FEAT_KINDS = ("origin", "general", "fighting_style", "epic_boon")

# 选择项的语义集合。故意封闭：内容里写一个内核不认识的 kind，
# 界面上就会变成一个「选了没反应」的下拉框，比报错难查得多。
CHOICE_KINDS = ("ability_boost", "save", "skill", "expertise", "resistance",
                "spell", "proficiency")
# `spell_list` 的「不限法术表」哨兵值。2024 版有些专长（妖精触碰一族）说的是
# 「任选一道某学派的 1 环法术」，没有职业限制 —— 硬塞给某张表就是改规则。
SPELL_LIST_ANY = "any"
# 这些 kind 的候选项由内核的全集决定，内容不必也不该重复列举
SKILL_KEYS = (
    "acrobatics", "animal_handling", "arcana", "athletics", "deception",
    "history", "insight", "intimidation", "investigation", "medicine",
    "nature", "perception", "performance", "persuasion", "religion",
    "sleight_of_hand", "stealth", "survival",
)
CHOICE_UNIVERSE = {
    "save": ("str", "dex", "con", "int", "wis", "cha"),
    "ability_boost": ("str", "dex", "con", "int", "wis", "cha"),
    "skill": SKILL_KEYS,
    # 专精的候选与技能同一套；「必须是已熟练」由 Profile 的集合约束兜底
    "expertise": SKILL_KEYS,
}


@dataclass(frozen=True)
class SkillDef:
    """一项技能：名称 + 所属属性。

    技能的**数值**不单独存 —— 它就是「属性检定 + 熟练（+ 专精）」，
    所以内核不为它开新通道，`rules/checks.skill_check()` 组合已有的能力。

    id 的最后一段就是熟练 token 用的 key：`dnd2024.skill.stealth` ↔ `skill.stealth`。
    两者对不上就等于「熟练了但算不出来」，所以装载时校验。
    """

    id: str
    name: Text
    ability: str

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("技能 id 不合规范：%r" % (self.id,))
        if self.key not in SKILL_KEYS:
            raise PluginError("技能 %s 的 key 不在内核的 18 项里（%s）"
                              % (self.id, ", ".join(SKILL_KEYS)))
        if self.ability not in ("str", "dex", "con", "int", "wis", "cha"):
            raise PluginError("技能 %s 的属性不合法：%r" % (self.id, self.ability))

    @property
    def key(self) -> str:
        return self.id.rsplit(".", 1)[-1]

    def to_dict(self, locale: str = "zh") -> dict:
        return {"id": self.id, "key": self.key, "ability": self.ability,
                "name": self.name.get(locale)}


def parse_skill(data: Any, source: str = "") -> SkillDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的技能定义必须是映射" % source)
    for key in ("id", "name", "ability"):
        if key not in data:
            raise PluginError("%s 的技能定义缺少 %s（%s）"
                              % (source, key, data.get("id", "?")))
    return SkillDef(
        id=str(data["id"]),
        name=Text.from_dict(data["name"], where="%s name" % data["id"]),
        ability=str(data["ability"]).lower(),
    )


# 工具的四类。与技能不同，**不设 key 白名单**：工具是内容（37 件），
# 谁都可以加一件自制工具；技能那 18 项是规则词汇，才需要闭环。
TOOL_KINDS = ("artisan", "gaming", "musical", "other")


@dataclass(frozen=True)
class ToolDef:
    """一件工具：名称 + 类别 + **建议属性**。

    `ability` 是「用这件工具做检定时通常配哪项属性」，来自原文的工具表。
    它不是硬绑定 —— 2024 的规则是「DM 决定用哪项属性」，所以检定仍然允许换，
    界面只是拿它当默认值。写成必填是因为 37 件原文全都有，缺了就是数据没抄全。

    id 的最后一段就是熟练 token 用的 key：`dnd2024.tool.thieves_tools` ↔
    `tool.thieves_tools`。两者对不上就等于「熟练了但算不出来」。
    """

    id: str
    name: Text
    kind: str
    ability: str

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("工具 id 不合规范：%r" % (self.id,))
        if self.kind not in TOOL_KINDS:
            raise PluginError("工具 %s 的类别必须是 %s" % (self.id, "/".join(TOOL_KINDS)))
        if self.ability not in ("str", "dex", "con", "int", "wis", "cha"):
            raise PluginError("工具 %s 的建议属性不合法：%r" % (self.id, self.ability))

    @property
    def key(self) -> str:
        return self.id.rsplit(".", 1)[-1]

    def to_dict(self, locale: str = "zh") -> dict:
        return {"id": self.id, "key": self.key, "kind": self.kind,
                "ability": self.ability, "name": self.name.get(locale)}


def parse_tool(data: Any, source: str = "") -> ToolDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的工具定义必须是映射" % source)
    for key in ("id", "name", "kind", "ability"):
        if key not in data:
            raise PluginError("%s 的工具定义缺少 %s（%s）"
                              % (source, key, data.get("id", "?")))
    return ToolDef(
        id=str(data["id"]),
        name=Text.from_dict(data["name"], where="%s name" % data["id"]),
        kind=str(data["kind"]).lower(),
        ability=str(data["ability"]).lower(),
    )
DAMAGE_TYPES = (
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
    "piercing", "poison", "psychic", "radiant", "slashing", "thunder",
)

# 生物类型：规则词汇（14 种），不是内容。写错一个字母就没法做「驱散善恶」这类判定，
# 所以设白名单；具体是龙还是史莱姆，那是内容说了算。
CREATURE_TYPES = (
    "aberration", "beast", "celestial", "construct", "dragon", "elemental",
    "fey", "fiend", "giant", "humanoid", "monstrosity", "ooze", "plant", "undead",
)
CONDITION_IMMUNITIES = (
    "blinded", "charmed", "deafened", "exhaustion", "frightened", "grappled",
    "incapacitated", "invisible", "paralyzed", "petrified", "poisoned",
    "prone", "restrained", "stunned", "unconscious",
)


@dataclass(frozen=True)
class SummonDef:
    """法术召出来的那只生物。

    **为什么是独立内容类型，而不是法术的一段文案**：这只生物有自己的 AC / HP /
    属性 / 抗性 / 动作，战斗里要独立掷骰、独立掉血。塞进法术的 `text` 里，
    它就永远只能被「读」，不能被「算」—— 施法结算（G6）也就没法开工。

    **数值必须是结构化的**：旧的旧程序把 AC 写成 `"11 + 法术环级"` 字符串，
    结果只能照抄给人看，升环换个环位就不知道该显示什么。这里 `ac` / `hp` 是
    `Scaling`（base + per_slot × 超出环级），任何环位都能现算，也能验算。

    `hp` 与 `hp_by_size` **二选一**：绝大多数召唤物 HP 只是环级的函数；
    活化物件的 HP 只跟物件体型有关（10 / 20 / 40），与环级无关。两种写法强行
    并成一张表，就会出现「巨型物件用 9 环召 = 40 血」这种既对又读不懂的条目。
    """

    id: str
    name: Text
    spell: str
    creature_type: str
    ac: Scaling
    languages: Text
    abilities: Abilities
    size: str = "medium"
    # 体型不由这只生物决定时（「巨型或更小」）留空 + 写 size_note 说明。
    size_note: Text | None = None
    hp: Scaling | None = None
    hp_by_size: Mapping[str, int] | None = None
    hp_dice: Text | None = None
    variant: Text | None = None
    speeds: Mapping[str, int] = field(default_factory=dict)
    # 「飞行要 4 环以上」（异界坐骑）这类速度解禁：速度 → 需要的最低环级。
    speeds_require_slot: Mapping[str, int] = field(default_factory=dict)
    senses: Mapping[str, int] = field(default_factory=dict)
    passive_perception: int = 10
    damage_resistances: tuple[str, ...] = ()
    damage_immunities: tuple[str, ...] = ()
    condition_immunities: tuple[str, ...] = ()
    traits: tuple[SummonAction, ...] = ()
    actions: tuple[SummonAction, ...] = ()
    bonus_actions: tuple[SummonAction, ...] = ()
    reactions: tuple[SummonAction, ...] = ()
    note: Text | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("召唤物 id 不合规范：%r" % (self.id,))
        if not self.spell:
            raise PluginError("召唤物 %s 必须写 summon.spell（谁把它召出来）" % self.id)
        if self.creature_type not in CREATURE_TYPES:
            raise PluginError("召唤物 %s 的生物类型必须是 %s"
                              % (self.id, "/".join(CREATURE_TYPES)))
        if self.size and self.size not in SIZES:
            raise PluginError("召唤物 %s 的体型必须是 %s" % (self.id, "/".join(SIZES)))
        if not self.size and self.size_note is None:
            raise PluginError("召唤物 %s 没写体型时必须用 size_note 说明"
                              "（「巨型或更小」这种不能靠猜）" % self.id)
        if (self.hp is None) == (not self.hp_by_size):
            raise PluginError("召唤物 %s 的 hp 与 hp_by_size 必须二选一" % self.id)
        if self.hp_by_size:
            bad = [key for key in self.hp_by_size if key not in SIZES]
            if bad:
                raise PluginError("召唤物 %s 的 hp_by_size 里有不认识的体型：%s"
                                  % (self.id, ", ".join(bad)))
            if any(int(value) < 1 for value in self.hp_by_size.values()):
                raise PluginError("召唤物 %s 的 hp_by_size 有非正数" % self.id)
        bad = [key for key in self.speeds if key not in SPEED_KINDS]
        if bad:
            raise PluginError("召唤物 %s 的速度类型不认识：%s（可选 %s）"
                              % (self.id, ", ".join(bad), "/".join(SPEED_KINDS)))
        bad = [key for key in self.speeds_require_slot
               if key not in self.speeds or not 1 <= int(self.speeds_require_slot[key]) <= 9]
        if bad:
            raise PluginError("召唤物 %s 的 speeds_require_slot 写了没有的速度或环级越界：%s"
                              % (self.id, ", ".join(bad)))
        bad = [key for key in self.senses if key not in SENSE_KINDS]
        if bad:
            raise PluginError("召唤物 %s 的感官类型不认识：%s（可选 %s）"
                              % (self.id, ", ".join(bad), "/".join(SENSE_KINDS)))
        for field_name, values in (("damage_resistances", self.damage_resistances),
                                   ("damage_immunities", self.damage_immunities)):
            bad = [item for item in values if item not in DAMAGE_TYPES]
            if bad:
                raise PluginError("召唤物 %s 的 %s 有陌生的伤害类型：%s"
                                  % (self.id, field_name, ", ".join(bad)))
        bad = [item for item in self.condition_immunities
               if item not in CONDITION_IMMUNITIES]
        if bad:
            raise PluginError("召唤物 %s 的状态免疫不认识：%s" % (self.id, ", ".join(bad)))
        if not (self.traits or self.actions or self.bonus_actions or self.reactions):
            raise PluginError("召唤物 %s 一条特性/动作都没有，等于召出来站着" % self.id)
        if not 0 <= int(self.passive_perception) <= 40:
            raise PluginError("召唤物 %s 的被动察觉不合法：%r"
                              % (self.id, self.passive_perception))

    @property
    def key(self) -> str:
        return self.id.rsplit(".", 1)[-1]

    @property
    def label(self) -> str:
        """中文显示名：「巨型昆虫·蜈蚣」这种已经把变体写进名字的，直接返回名字。"""
        if self.variant is None:
            return self.name.zh
        return "%s（%s）" % (self.name.zh, self.variant.zh)

    def ac_at(self, slot_level: int) -> int:
        return self.ac.at(int(slot_level))

    def hp_at(self, slot_level: int, size: str = "") -> int:
        if self.hp is not None:
            return self.hp.at(int(slot_level))
        table = dict(self.hp_by_size or {})
        picked = str(size or "").lower()
        if not picked:
            raise PluginError("召唤物 %s 的生命值按体型分叉，必须传 size" % self.id)
        if picked not in table:
            raise PluginError("召唤物 %s 没有体型 %r 的生命值" % (self.id, picked))
        return int(table[picked])

    def speeds_at(self, slot_level: int) -> dict[str, int]:
        slot = int(slot_level)
        return {kind: int(value) for kind, value in self.speeds.items()
                if not int(self.speeds_require_slot.get(kind, 0))
                or slot >= int(self.speeds_require_slot[kind])}

    def card(self, slot_level: int, locale: str = "zh",
             caster_mod: int = 0, size: str = "") -> dict:
        return resolve_summon(self, slot_level, caster_mod, size, locale)

    def to_dict(self, locale: str = "zh") -> dict:
        return {"id": self.id, "key": self.key, "name": self.name.get(locale),
                "variant": self.variant.get(locale) if self.variant else "",
                "spell": self.spell, "creature_type": self.creature_type,
                "size": self.size, "ac": self.ac.to_dict(),
                "hp": self.hp.to_dict() if self.hp is not None else None,
                "source": self.source}


def parse_summon(data: Any, source: str = "") -> SummonDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的召唤物定义必须是映射" % source)
    for key in ("id", "name", "spell", "creature_type", "ac", "languages", "abilities"):
        if key not in data:
            raise PluginError("%s 的召唤物定义缺少 %s（%s）"
                              % (source, key, data.get("id", "?")))
    ident = str(data["id"])
    if not is_valid(ident):
        raise PluginError("召唤物 id 不合规范：%r" % ident)
    hs = data.get("hp")
    by_size = data.get("hp_by_size")
    if (hs is None) == (not by_size):
        raise PluginError("召唤物 %s 的 hp 与 hp_by_size 必须二选一" % ident)
    try:
        abilities = Abilities.of(**{str(key): int(value)
                                    for key, value in data["abilities"].items()})
    except RuleError as exc:
        raise PluginError("%s 的属性不合法：%s" % (ident, exc))

    def actions(key: str) -> tuple[SummonAction, ...]:
        rows = data.get(key) or ()
        if isinstance(rows, Mapping):
            rows = [rows]
        return tuple(parse_action(row, DAMAGE_TYPES, where="%s %s" % (ident, key))
                     for row in rows)

    return SummonDef(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        spell=str(data["spell"]),
        creature_type=str(data["creature_type"]).lower(),
        ac=parse_scaling(data["ac"], where="%s ac" % ident),
        languages=Text.from_dict(data["languages"], where="%s languages" % ident),
        abilities=abilities,
        size=str(data.get("size", "medium")).lower(),
        size_note=Text.from_dict(data["size_note"], where="%s size_note" % ident)
        if data.get("size_note") else None,
        hp=parse_scaling(hs, where="%s hp" % ident) if hs is not None else None,
        hp_by_size={str(key).lower(): int(value) for key, value in by_size.items()}
        if by_size else None,
        hp_dice=Text.from_dict(data["hp_dice"], where="%s hp_dice" % ident)
        if data.get("hp_dice") else None,
        variant=Text.from_dict(data["variant"], where="%s variant" % ident)
        if data.get("variant") else None,
        speeds={str(k): int(v) for k, v in (data.get("speeds") or {"walk": 30}).items()},
        speeds_require_slot={str(k): int(v) for k, v in
                             (data.get("speeds_require_slot") or {}).items()},
        senses={str(k): int(v) for k, v in (data.get("senses") or {}).items()},
        passive_perception=int(data.get("passive_perception", 10)),
        damage_resistances=tuple(str(v).lower()
                                 for v in (data.get("damage_resistances") or ())),
        damage_immunities=tuple(str(v).lower()
                                for v in (data.get("damage_immunities") or ())),
        condition_immunities=tuple(str(v).lower()
                                   for v in (data.get("condition_immunities") or ())),
        traits=actions("traits"),
        actions=actions("actions"),
        bonus_actions=actions("bonus_actions"),
        reactions=actions("reactions"),
        note=Text.from_dict(data["note"], where="%s note" % ident)
        if data.get("note") else None,
        source=source,
    )


@dataclass(frozen=True)
class FeatChoice:
    """专长里「要玩家选一个」的那部分。

    `count` 是选几项，`amount` 是每项加多少。属性提升的「一项 +2 或两项 +1」
    用 `count: 2, amount: 1, repeat: true` 表达 —— 选同一项两次就是 +2。
    这样「或者」不需要新语法，规则也不会漏掉一种模式。
    """

    id: str
    kind: str
    count: int = 1
    amount: int = 0
    cap: int = 0
    # 候选项的**收窄**（如「力量或敏捷」）。空 = 用该 kind 的全集。
    pool: tuple[str, ...] = ()
    # 同一项可以选两次（「任选一项 +2」用两次 +1 表达，见 rules/feats.py）
    repeat: bool = False
    # 「选了这一项，属性值同时也 +N」（坚毅：选一项豁免，该属性 +1）。
    # 只对 save 有意义 —— 它选中就是属性名。
    boost: int = 0
    boost_cap: int = 0
    # `kind: spell` 的两个坐标：从**哪张职业法术表**里选、选几环的。
    # 候选集不写死在内容里 —— 它由法术表 + 环级动态生成（`spell_pool`），
    # 否则「魔法入门」的 3 个变体要各抄一份几十条法术 id，抄漏一条就是静默少一个选项。
    spell_list: str = ""
    spell_level: int = 0
    # 再按学派收窄（「妖精触碰」= 1 环的预言或惑控）。空 = 不限学派。
    # 用学派而不是列举法术 id：2024 版新法术随时会加进法术表，列举必然漏。
    spell_school: tuple[str, ...] = ()
    label: Text | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise PluginError("专长的选择项缺 id")
        if self.kind not in CHOICE_KINDS:
            raise PluginError("专长选择项 %s 的 kind 不认识：%r（可选 %s）"
                              % (self.id, self.kind, "/".join(CHOICE_KINDS)))
        if self.count < 1:
            raise PluginError("专长选择项 %s 的 count 至少是 1" % self.id)
        if self.kind == "ability_boost":
            if self.amount < 1:
                raise PluginError("专长选择项 %s 是属性加值，必须写 amount" % self.id)
            if self.cap and self.cap < 1:
                raise PluginError("专长选择项 %s 的 cap 至少是 1" % self.id)
        elif self.amount or self.cap:
            raise PluginError("专长选择项 %s 不是属性加值，不该写 amount/cap" % self.id)
        if self.boost:
            if self.kind != "save":
                raise PluginError("专长选择项 %s 的 boost 只对 save 有意义" % self.id)
            if self.boost < 1:
                raise PluginError("专长选择项 %s 的 boost 至少是 1" % self.id)
            if self.boost_cap and self.boost_cap < 1:
                raise PluginError("专长选择项 %s 的 boost_cap 至少是 1" % self.id)
        if self.kind == "spell":
            if not self.spell_list:
                raise PluginError("专长选择项 %s 是法术选择，必须写 spell_list（职业）" % self.id)
            if not 0 <= self.spell_level <= 9:
                raise PluginError("专长选择项 %s 的 spell_level 必须在 0–9" % self.id)
            if self.pool:
                raise PluginError("专长选择项 %s 的候选来自法术表，不该写 from" % self.id)
            bad = [item for item in self.spell_school if item not in SPELL_SCHOOLS]
            if bad:
                raise PluginError("专长选择项 %s 的 spell_school 里有不认识的学派：%s（可选 %s）"
                                  % (self.id, ", ".join(bad), "/".join(SPELL_SCHOOLS)))
            if self.spell_school and self.spell_level == 0:
                raise PluginError("专长选择项 %s 是戏法选择，戏法学派收窄没有意义（2024 戏法不限学派）"
                                  % self.id)
        elif self.spell_list or self.spell_level or self.spell_school:
            raise PluginError("专长选择项 %s 不是法术选择，不该写 spell_list/spell_level/spell_school"
                              % self.id)
        if self.pool:
            universe = set(self.options)
            unknown = [item for item in self.pool if item not in universe]
            if unknown:
                raise PluginError("专长选择项 %s 的 from 里有不认识的项：%s"
                                  % (self.id, ", ".join(unknown)))

    @property
    def options(self) -> tuple[str, ...]:
        if self.kind == "resistance":
            return self.pool or DAMAGE_TYPES
        if self.kind == "spell":
            return ()          # 候选由法术表生成，见 rules/feats.py:spell_pool
        if self.kind == "proficiency":
            # 「任意组合的技能与工具」：候选是内容（18 技能 + 37 工具），
            # 见 rules/feats.py:proficiency_pool。技能是规则词汇、工具是内容，
            # 两者长度都会变，写死在 CHOICE_UNIVERSE 里必然漂。
            return ()
        full = CHOICE_UNIVERSE.get(self.kind, ())
        if not self.pool:
            return full
        # from 只做**收窄**：顺序按全集走，界面上的排列才稳定
        return tuple(item for item in full if item in set(self.pool))

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "id": self.id, "kind": self.kind, "count": self.count,
            "amount": self.amount, "cap": self.cap, "repeat": self.repeat,
            "boost": self.boost, "boost_cap": self.boost_cap,
            "spell_list": self.spell_list, "spell_level": self.spell_level,
            "spell_school": list(self.spell_school),
            "options": list(self.options),
            "label": self.label.get(locale) if self.label else "",
        }


def parse_feat_choice(data: Any, where: str) -> FeatChoice:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的 choices 每项必须是映射" % where)
    if "id" not in data or "kind" not in data:
        raise PluginError("%s 的 choices 每项必须写 id 与 kind" % where)
    return FeatChoice(
        id=str(data["id"]),
        kind=str(data["kind"]),
        count=int(data.get("count", 1)),
        amount=int(data.get("amount", 0)),
        cap=int(data.get("cap", 0)),
        pool=tuple(str(item) for item in (data.get("from") or ())),
        repeat=bool(data.get("repeat", False)),
        boost=int(data.get("boost", 0)),
        boost_cap=int(data.get("boost_cap", 0)),
        spell_list=str(data.get("spell_list", "")),
        spell_level=int(data.get("spell_level", 0)),
        spell_school=tuple(str(item).lower() for item in (data.get("spell_school") or ())),
        label=Text.from_dict(data["label"], where="%s %s label" % (where, data["id"]))
        if data.get("label") else None,
    )


@dataclass(frozen=True)
class FeatDef:
    """一个专长：静态原语（powers）+ 待选（choices）+ 选取前提。

    专长与子职一样是**顶层内容**，不属于职业：`classes` 只用来表达
    「这个专长只有某几个职业能拿」（战斗风格），不是归属关系。
    """

    id: str
    name: Text
    text: Text
    kind: str = "general"
    level: int = 0                      # 前提等级（0 = 无等级前提）
    min_score: int = 0                  # 前提属性门槛（0 = 无属性前提）
    abilities: tuple[str, ...] = ()      # 前提属性：这些里任意一项达标即可
    feature: str | None = None           # 前提特性（如战斗风格）
    classes: tuple[str, ...] = ()        # 只有这些职业能选（空 = 所有职业）
    repeatable: bool = False
    choices: tuple[FeatChoice, ...] = ()
    powers: tuple[Power, ...] = ()
    # 「你始终准备该法术」里**写死的那一道**（妖精触碰的迷踪步、影界触碰的隐形术）。
    # 与 `kind: spell` 的选择项不同：这条不需要选，所有拿了这个专长的人都一样。
    # 只是法术 id，具体能不能施放、有几个位，仍由施法规则决定。
    spells: tuple[str, ...] = ()
    # 专长也能给资源池（「每长休一次免费施放」这类每日一次的次数）。
    # 容量按**总等级**查（专长没有「专长等级」这种轴），一般写固定值 1。
    resources: tuple[ResourceDef, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("专长 id 不合规范：%r" % (self.id,))
        if self.kind not in FEAT_KINDS:
            raise PluginError("专长 %s 的 kind 不认识：%r（可选 %s）"
                              % (self.id, self.kind, "/".join(FEAT_KINDS)))
        seen: set[str] = set()
        for choice in self.choices:
            key = "%s.%s" % (self.id, choice.id)
            if key in seen:
                raise PluginError("专长 %s 的选择项 id 重复：%s" % (self.id, choice.id))
            seen.add(key)
        for power in self.powers:
            if power.id in seen:
                raise PluginError("专长 %s 的特性 id 重复：%s" % (self.id, power.id))
            seen.add(power.id)

    def choice(self, choice_id: str) -> FeatChoice:
        for item in self.choices:
            if item.id == choice_id:
                return item
        raise PluginError("专长 %s 没有选择项 %s" % (self.id, choice_id))

    def choice_keys(self) -> tuple[str, ...]:
        """`Profile.choices` 里这个专长的键：`<专长 id>.<选择项 id>`。"""
        return tuple("%s.%s" % (self.id, item.id) for item in self.choices)

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "id": self.id,
            "name": self.name.get(locale),
            "text": self.text.get(locale),
            "kind": self.kind,
            "level": int(self.level),
            "abilities": list(self.abilities),
            "min_score": int(self.min_score),
            "classes": list(self.classes),
            "repeatable": self.repeatable,
            "choices": [item.to_dict(locale) for item in self.choices],
            "spells": list(self.spells),
            "powers": len(self.powers),
        }


def parse_feat(data: Any, source: str = "") -> FeatDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的专长定义必须是映射" % source)
    for key in ("id", "name", "text"):
        if key not in data:
            raise PluginError("%s 的专长定义缺少 %s" % (source, key))
    ident = str(data["id"])
    abilities = tuple(str(item).lower() for item in (data.get("abilities") or ()))
    bad = [item for item in abilities if item not in CHOICE_UNIVERSE["ability_boost"]]
    if bad:
        raise PluginError("%s 的前提属性不认识：%s" % (ident, ", ".join(bad)))
    return FeatDef(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        text=Text.from_dict(data["text"], where="%s text" % ident),
        kind=str(data.get("kind", "general")),
        level=int(data.get("level", 0)),
        min_score=int(data.get("min_score", 13 if abilities else 0)),
        abilities=abilities,
        feature=data.get("feature"),
        classes=tuple(str(item) for item in (data.get("classes") or ())),
        repeatable=bool(data.get("repeatable", False)),
        choices=tuple(parse_feat_choice(row, ident) for row in (data.get("choices") or ())),
        resources=tuple(parse_resource(row, owner_class=ident)
                        for row in (data.get("resources") or ())),
        spells=tuple(str(item) for item in (data.get("spells") or ())),
        powers=tuple(
            parse_power(row, owner=ident, source=source)
            for row in (data.get("powers") or ())
        ),
        source=source,
    )


def parse_cr_axis(data: Any) -> CrAxis | None:
    if data is None:
        return None
    if not isinstance(data, Mapping):
        raise PluginError("morph 段必须是映射")
    steps_raw = data.get("cr_by_level") or data.get("steps")
    if not steps_raw:
        raise PluginError("morph 段缺少 cr_by_level")
    try:
        steps = {int(key): float(value) for key, value in steps_raw.items()}
    except (TypeError, ValueError):
        raise PluginError("cr_by_level 必须是 等级→CR 的映射")
    return CrAxis(
        steps=steps,
        swim_from=int(data.get("swim_from", 4)),
        fly_from=int(data.get("fly_from", 8)),
    )


def parse_form(data: Any, source: str = "") -> FormSpec:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的形态定义必须是映射" % source)
    for key in ("id", "name", "ac", "hp", "cr", "abilities"):
        if key not in data:
            raise PluginError("%s 的形态定义缺少 %s" % (source, key))
    ident = str(data["id"])
    if not is_valid(ident):
        raise PluginError("形态 id 不合规范：%r" % ident)
    try:
        abilities = Abilities.of(**{str(key): int(value)
                                    for key, value in data["abilities"].items()})
    except RuleError as exc:
        raise PluginError("%s 的属性不合法：%s" % (ident, exc))
    speeds = {str(key): int(value) for key, value in (data.get("speeds") or {"walk": 30}).items()}
    senses = {str(key): int(value) for key, value in (data.get("senses") or {}).items()}
    return FormSpec(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        ac=int(data["ac"]),
        hp=int(data["hp"]),
        cr=float(data["cr"]),
        abilities=abilities,
        speeds=speeds,
        senses=senses,
        size=str(data.get("size", "medium")),
    )


def _parse_refresh(data: Any, where: str) -> Refresh:
    if data is None:
        return Refresh.LONG_REST
    key = str(data).strip().lower()
    if key not in REFRESH_KINDS:
        raise PluginError("%s 的 slot_refresh 必须是 %s"
                          % (where, "/".join(sorted(REFRESH_KINDS))))
    return REFRESH_KINDS[key]


def _parse_level_table(data: Any, where: str) -> dict[int, int]:
    if not data:
        return {}
    if not isinstance(data, Mapping):
        raise PluginError("%s 必须是 等级→数值 的映射" % where)
    try:
        return {int(key): int(value) for key, value in data.items()}
    except (TypeError, ValueError):
        raise PluginError("%s 必须是 等级→数值 的映射" % where)


def parse_slots(data: Any) -> dict[int, tuple[int, ...]]:
    """法术位表：`{5: [4,3,2,0,0,0,0,0,0]}`。多写或写错环数都要当场报错。"""
    if not data:
        return {}
    if not isinstance(data, Mapping):
        raise PluginError("slots 必须是 等级→9 个环位 的映射")
    rows: dict[int, tuple[int, ...]] = {}
    for key, value in data.items():
        if not isinstance(value, (list, tuple)):
            raise PluginError("slots 的 %r 必须是 9 个整数的列表" % (key,))
        if len(value) > 9:
            raise PluginError("slots 的 %r 超过 9 环：%r" % (key, value))
        try:
            row = tuple(int(item) for item in value)
        except (TypeError, ValueError):
            raise PluginError("slots 的 %r 必须是整数：%r" % (key, value))
        if any(item < 0 for item in row):
            raise PluginError("slots 的 %r 出现负环位：%r" % (key, value))
        rows[int(key)] = row
    return rows


def _parse_class_proficiencies(data: Any, where: str) -> tuple[str, ...]:
    """职业给的武器/护甲熟练。

    写成 `{weapons: [simple, martial], armor: [light, medium, shield]}`，
    解析成 `weapon.simple` / `armor.light` 这种 token —— 与 `grant_proficiency`
    同一套命名，这样装备判定只需要看一份集合。
    """
    if not data:
        return ()
    if not isinstance(data, Mapping):
        raise PluginError("%s 的 proficiencies 必须是映射" % where)
    tokens: list[str] = []
    for kind, values in data.items():
        if kind not in ("weapons", "armor"):
            raise PluginError("%s 的 proficiencies 只认 weapons / armor，实际 %r" % (where, kind))
        prefix = "weapon" if kind == "weapons" else "armor"
        for value in (values or ()):
            token = "%s.%s" % (prefix, str(value).lower().replace("-", "_"))
            if token not in tokens:
                tokens.append(token)
    return tuple(tokens)


def parse_class(data: Any, source: str = "") -> ClassDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的职业定义必须是映射" % source)
    for key in ("id", "name", "hit_die"):
        if key not in data:
            raise PluginError("%s 的职业定义缺少 %s" % (source, key))

    ident = str(data["id"])
    caster_key = str(data.get("caster", "none")).lower()
    try:
        caster = CasterKind(caster_key)
    except ValueError:
        raise PluginError("%s 的 caster 必须是 %s"
                          % (ident, "/".join(item.value for item in CasterKind)))
    try:
        subclass_level = as_class_level(int(data.get("subclass_level", 3)))
    except RuleError as exc:
        raise PluginError("%s 的子职等级不合法：%s" % (ident, exc))

    resources = tuple(
        parse_resource(item, owner_class=ident) for item in (data.get("resources") or ())
    )
    powers = tuple(
        parse_power(item, owner=ident, source=source) for item in (data.get("powers") or ())
    )

    return ClassDef(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        hit_die=int(data["hit_die"]),
        primary=tuple(str(item).lower() for item in (data.get("primary") or ())),
        saves=tuple(str(item).lower() for item in (data.get("saves") or ())),
        caster=caster,
        casting_ability=str(data.get("casting_ability", "")).lower(),
        subclass_level=subclass_level,
        skill_choices=int(data.get("skill_choices", 2)),
        skill_list=tuple(str(item) for item in (data.get("skill_list") or ())),
        resources=resources,
        powers=powers,
        proficiencies=_parse_class_proficiencies(data.get("proficiencies"), ident),
        morph=parse_cr_axis(data.get("morph")),
        slots=parse_slots(data.get("slots")),
        cantrips=_parse_level_table(data.get("cantrips"), "%s cantrips" % ident),
        prepared=_parse_level_table(data.get("prepared"), "%s prepared" % ident),
        slot_refresh=_parse_refresh(data.get("slot_refresh"), ident),
        source=source,
    )


# --- 法术 -------------------------------------------------------------
SPELL_SCHOOLS = (
    "abjuration", "conjuration", "divination", "enchantment",
    "evocation", "illusion", "necromancy", "transmutation",
)
CAST_KINDS = ("action", "bonus", "reaction", "time", "special")
DURATION_KINDS = ("instant", "time", "permanent", "special")
AREA_SHAPES = ("sphere", "cube", "cone", "cylinder", "line", "emanation")


def _parse_cast_kind(data: Any, where: str) -> tuple[str, str, str]:
    """施法时间 → (kind, 中文, 英文)。字符串就是 action/bonus/reaction。

    「1 分钟」这类不占动作的施法时间统一记 `time`，具体多久放在 text 里 ——
    内核不需要知道「1 分钟」是多少秒，它只需要知道「这不是一个动作」。
    """
    if data is None:
        return "action", "1 动作", "Action"
    if isinstance(data, str):
        key = data.strip().lower()
        fixed = {
            "action": ("action", "1 动作", "Action"),
            "bonus": ("bonus", "1 附赠动作", "Bonus Action"),
            "reaction": ("reaction", "1 反应", "Reaction"),
            "instant": ("special", "特殊", "Special"),
        }
        if key in fixed:
            return fixed[key]
        if key in CAST_KINDS:
            return key, key, key
        raise PluginError("%s 的施法时间 %r 无法识别" % (where, data))
    if isinstance(data, Mapping):
        kind = str(data.get("kind", "time")).lower()
        if kind not in CAST_KINDS:
            raise PluginError("%s 的施法时间类别必须是 %s"
                              % (where, "/".join(CAST_KINDS)))
        return (kind, str(data.get("zh", data.get("text", ""))),
                str(data.get("en", data.get("text", ""))))
    raise PluginError("%s 的施法时间必须是字符串或映射" % where)


def _parse_area(data: Any, where: str) -> tuple[str, int] | None:
    """作用范围：`{shape: sphere, feet: 20}`。没写就是单体/无范围。"""
    if not data:
        return None
    if not isinstance(data, Mapping):
        raise PluginError("%s 的 area 必须是映射" % where)
    shape = str(data.get("shape", "")).lower()
    if shape not in AREA_SHAPES:
        raise PluginError("%s 的 area.shape 必须是 %s"
                          % (where, "/".join(AREA_SHAPES)))
    feet = int(data.get("feet", 0))
    if feet <= 0:
        raise PluginError("%s 的 area.feet 必须大于 0" % where)
    return shape, feet


def _parse_damage_table(data: Any, where: str) -> tuple[dict[int, str], str, str]:
    """伤害：`{3: 8d6, type: fire, upcast: 每环 +1d6}` → (环级表, 类型, 升环说明)。

    表里放的是「在该环位施放时的骰式」—— 戏法只有 0 档，靠角色等级成长；
    升环就是查表，内核不写「每环 +1d6」这种公式。
    """
    if not data:
        return {}, "", ""
    if not isinstance(data, Mapping):
        raise PluginError("%s 的 damage 必须是映射" % where)
    table: dict[int, str] = {}
    for key, value in data.items():
        if key in ("type", "damage_type", "upcast"):
            continue
        try:
            level = int(key)
        except (TypeError, ValueError):
            raise PluginError("%s 的 damage 键必须是环级：%r" % (where, key))
        if level < 0:
            raise PluginError("%s 的 damage 环级不能为负：%r" % (where, key))
        dice = str(value)
        try:
            parse_dice(dice)                   # 骰式当场校验，坏数据不等到施法才炸
        except DiceError as exc:
            raise PluginError("%s 的伤害骰式不合法：%r（%s）" % (where, dice, exc))
        table[level] = dice
    kind = str(data.get("type") or data.get("damage_type") or "").lower()
    return table, kind, str(data.get("upcast", ""))


@dataclass(frozen=True)
class SpellDef:
    """一个法术。**只管规则，不管界面**：能算的都解析成字段，算不了的留在 text 里。

    `damage` 是「环位 → 骰式」的表而不是公式：升环、戏法成长都变成查表，
    内核里没有「每提升一环 +1d6」这种逻辑。查表规则与资源表一致（取不超过的最大档）。
    """

    id: str
    name: Text
    level: int
    school: str
    text: Text
    cast_kind: str = "action"
    cast_zh: str = ""
    cast_en: str = ""
    range_feet: int | None = None
    range_zh: str = ""
    range_en: str = ""
    components: tuple[str, ...] = ()
    material: str = ""
    duration_kind: str = "instant"
    duration_zh: str = ""
    duration_en: str = ""
    concentration: bool = False
    ritual: bool = False
    save: str = ""
    attack: str = ""
    area: tuple[str, int] | None = None
    damage: Mapping[int, str] = field(default_factory=dict)
    damage_type: str = ""
    upcast: str = ""
    # **戏法的成长档**：角色等级 → 值。和 `damage`（按环位查）是两条轴，
    # 混成一张表会让 5 级角色用 0 环位施法时查到错误的骰子。
    # `scaling_kind` 说明这个值是什么：伤害骰 / 额外伤害 / 光束数 / 射程 / 武器骰。
    scaling: Mapping[int, str] = field(default_factory=dict)
    scaling_kind: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("法术 id 不合规范：%r" % (self.id,))
        if not 0 <= int(self.level) <= 9:
            raise PluginError("%s 的法术环级必须在 0–9：%r" % (self.id, self.level))
        if self.school not in SPELL_SCHOOLS:
            raise PluginError("%s 的法术学派必须是 %s"
                              % (self.id, "/".join(SPELL_SCHOOLS)))
        if self.cast_kind not in CAST_KINDS:
            raise PluginError("%s 的施法时间类别必须是 %s"
                              % (self.id, "/".join(CAST_KINDS)))
        if self.duration_kind not in DURATION_KINDS:
            raise PluginError("%s 的持续时间类别必须是 %s"
                              % (self.id, "/".join(DURATION_KINDS)))
        if self.save and self.save not in ("str", "dex", "con", "int", "wis", "cha"):
            raise PluginError("%s 的豁免属性不合法：%r" % (self.id, self.save))
        for token in self.components:
            if token not in ("v", "s", "m"):
                raise PluginError("%s 的成分只能是 v/s/m：%r" % (self.id, token))
        if self.level == 0 and self.damage and 0 not in self.damage:
            raise PluginError("%s 是戏法，damage 表必须从 0 档开始" % self.id)
        _check_scaling(self)

    @property
    def is_cantrip(self) -> bool:
        return int(self.level) == 0

    @property
    def is_button(self) -> bool:
        """反应与「1 分钟」类法术不该在战斗回合里当按钮按 —— 界面上仍要列出。"""
        return self.cast_kind in ("action", "bonus")

    def damage_at(self, slot_level: int) -> str:
        """在该环位施放时的伤害骰式；查不到就返回空串（不是 0）。"""
        return lookup_dice(self.damage, int(slot_level))

    def scaling_at(self, character_level: int) -> str:
        """**角色等级**达到哪一档就取哪一档（5 / 11 / 17）。没写成长就返回空串。

        不要和 `damage_at` 混：那个查的是环位。戏法不能升环，成长只看角色等级。
        """
        if not self.scaling:
            return ""
        return lookup_dice(self.scaling, int(character_level))

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "id": self.id,
            "name": self.name.get(locale),
            "level": int(self.level),
            "school": self.school,
            "text": self.text.get(locale),
            "cast": {"kind": self.cast_kind,
                     "text": self.cast_zh if locale == "zh" else self.cast_en},
            "range": {"feet": self.range_feet,
                      "text": self.range_zh if locale == "zh" else self.range_en},
            "components": list(self.components),
            "material": self.material,
            "duration": {"kind": self.duration_kind,
                         "text": self.duration_zh if locale == "zh" else self.duration_en},
            "concentration": self.concentration,
            "ritual": self.ritual,
            "save": self.save,
            "attack": self.attack,
            "area": None if self.area is None else {"shape": self.area[0], "feet": self.area[1]},
            "damage": {int(key): value for key, value in self.damage.items()},
            "damage_type": self.damage_type,
            "upcast": self.upcast,
            "scaling": {"kind": self.scaling_kind,
                        "levels": {int(key): value for key, value in self.scaling.items()}},
        }


# 戏法成长档「是什么」。都用文本存值，但语义不同，界面必须能分开说：
#   伤害骰被替换 / 追加上去 / 光束数 / 射程 / 武器骰面
SCALING_KINDS = ("damage", "extra_damage", "beams", "range", "weapon_die")
_SCALING_LEVELS = (5, 11, 17)


def _check_scaling(spell: "SpellDef") -> None:
    """成长档一错，5 级之后整张卡都在骗人 —— 所以在加载期就把数据钉死。"""
    if not spell.scaling:
        if spell.scaling_kind:
            raise PluginError("%s 写了 scaling_kind 却没有 scaling 表" % spell.id)
        return
    if not spell.scaling_kind:
        raise PluginError("%s 有成长表却没写 scaling_kind（%s）"
                          % (spell.id, "/".join(SCALING_KINDS)))
    if spell.scaling_kind not in SCALING_KINDS:
        raise PluginError("%s 的 scaling_kind 不认识：%r（可选 %s）"
                          % (spell.id, spell.scaling_kind, "/".join(SCALING_KINDS)))
    if not spell.is_cantrip:
        # 有环法术的长进靠升环（`damage` 表），再写一条成长轴就会出现两个真相
        raise PluginError("%s 不是戏法，成长档只对戏法有意义（升环请写 damage 表）"
                          % spell.id)
    for key in spell.scaling:
        if int(key) not in _SCALING_LEVELS:
            raise PluginError("%s 的成长档只能是 %s 级，实际写了 %r"
                              % (spell.id, "/".join(str(item) for item in _SCALING_LEVELS), key))
    for key, value in spell.scaling.items():
        text = str(value)
        if spell.scaling_kind in ("damage", "extra_damage", "weapon_die"):
            try:
                parse_dice(text)
            except DiceError as exc:
                raise PluginError("%s 的成长档 %s 不是合法骰式：%r（%s）"
                                  % (spell.id, key, text, exc))
        else:
            try:
                if int(text) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise PluginError("%s 的成长档 %s 必须是正整数：%r"
                                  % (spell.id, key, text))


def lookup_dice(table: Mapping[int, str], level: int) -> str:
    """取不超过 level 的最大档（与资源表、Amount.table 同一条规则）。"""
    usable = [int(key) for key in table if int(key) <= int(level)]
    return "" if not usable else str(table[max(usable)])


def _parse_spell_range(data: Any, where: str) -> tuple[int | None, str, str]:
    if data is None:
        return None, "自身", "Self"
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        return int(data), "%d 尺" % int(data), "%d feet" % int(data)
    if isinstance(data, str):
        key = data.strip().lower()
        fixed = {
            "self": (None, "自身", "Self"),
            "touch": (None, "触碰", "Touch"),
            "sight": (None, "视线", "Sight"),
            "unlimited": (None, "无限", "Unlimited"),
            "special": (None, "特殊", "Special"),
        }
        if key in fixed:
            return fixed[key]
        raise PluginError("%s 的施法距离 %r 无法识别（自己写 {feet: N}）" % (where, data))
    if isinstance(data, Mapping):
        if "feet" in data:
            feet = int(data["feet"])
            if feet <= 0:
                raise PluginError("%s 的施法距离必须大于 0" % where)
            return feet, "%d 尺" % feet, "%d feet" % feet
        kind = str(data.get("kind", "")).lower()
        return _parse_spell_range(kind or "self", where)
    raise PluginError("%s 的施法距离必须是数字、字符串或映射" % where)


def _parse_duration_kind(data: Any, where: str) -> tuple[str, str, str]:
    if data is None:
        return "instant", "立即", "Instantaneous"
    if isinstance(data, str):
        key = data.strip().lower()
        if key in DURATION_KINDS:
            return key, {"instant": "立即", "time": "持续", "permanent": "永久",
                         "special": "特殊"}[key], key.title()
        raise PluginError("%s 的持续时间 %r 无法识别" % (where, data))
    if isinstance(data, Mapping):
        kind = str(data.get("kind", "time")).lower()
        if kind not in DURATION_KINDS:
            raise PluginError("%s 的持续时间类别必须是 %s"
                              % (where, "/".join(DURATION_KINDS)))
        return (kind, str(data.get("zh", data.get("text", ""))),
                str(data.get("en", data.get("text", ""))))
    raise PluginError("%s 的持续时间必须是字符串或映射" % where)


def _parse_scaling(data: Any, where: str) -> tuple[dict[int, str], str]:
    """戏法成长：`{kind: damage, 5: 2d6, 11: 3d6, 17: 4d6}` → (表, 类别)。"""
    if not data:
        return {}, ""
    if not isinstance(data, Mapping):
        raise PluginError("%s 的 scaling 必须是映射" % where)
    kind = str(data.get("kind", "")).lower()
    table: dict[int, str] = {}
    for key, value in data.items():
        if key in ("kind", "type"):
            continue
        try:
            level = int(key)
        except (TypeError, ValueError):
            raise PluginError("%s 的 scaling 键必须是角色等级：%r" % (where, key))
        table[level] = str(value)
    return table, kind


def parse_spell(data: Any, source: str = "") -> SpellDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的法术定义必须是映射" % source)
    for key in ("id", "name", "level", "school", "text"):
        if key not in data:
            raise PluginError("%s 的法术定义缺少 %s（%s）" % (source, key, data.get("id", "?")))

    ident = str(data["id"])
    cast_kind, cast_zh, cast_en = _parse_cast_kind(data.get("casting"), ident)
    duration_kind, dur_zh, dur_en = _parse_duration_kind(data.get("duration"), ident)
    range_feet, range_zh, range_en = _parse_spell_range(data.get("range"), ident)
    damage, damage_type, upcast = _parse_damage_table(data.get("damage"), ident)
    scaling, scaling_kind = _parse_scaling(data.get("scaling"), ident)
    components = tuple(str(item).lower() for item in (data.get("components") or ()))

    return SpellDef(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        level=int(data["level"]),
        school=str(data["school"]).lower(),
        text=Text.from_dict(data["text"], where="%s text" % ident),
        cast_kind=cast_kind,
        cast_zh=cast_zh,
        cast_en=cast_en,
        range_feet=range_feet,
        range_zh=range_zh,
        range_en=range_en,
        components=components,
        material=str(data.get("material", "")),
        duration_kind=duration_kind,
        duration_zh=dur_zh,
        duration_en=dur_en,
        concentration=bool(data.get("concentration", False)),
        ritual=bool(data.get("ritual", False)),
        save=str(data.get("save", "")).lower(),
        attack=str(data.get("attack", "")).lower(),
        area=_parse_area(data.get("area"), ident),
        damage=damage,
        damage_type=damage_type,
        upcast=upcast,
        scaling=scaling,
        scaling_kind=scaling_kind,
        source=source,
    )


def parse_spell_list(data: Any, source: str = "") -> tuple[str, tuple[str, ...]]:
    """职业法术表：`{class: ..., spells: [id...]}` → (职业 id, 法术 id 元组)。"""
    if not isinstance(data, Mapping):
        raise PluginError("%s 的法术表必须是映射" % source)
    for key in ("class", "spells"):
        if key not in data:
            raise PluginError("%s 的法术表缺少 %s" % (source, key))
    class_id = str(data["class"])
    if not is_valid(class_id):
        raise PluginError("%s 的法术表 class 不合规范：%r" % (source, class_id))
    spells: list[str] = []
    for item in data.get("spells") or ():
        ident = str(item)
        if not is_valid(ident):
            raise PluginError("%s 的法术表里有非法 id：%r" % (source, ident))
        if ident in spells:
            raise PluginError("%s 的法术表里 %s 重复" % (source, ident))
        spells.append(ident)
    if not spells:
        raise PluginError("%s 的法术表是空的" % source)
    return class_id, tuple(spells)


# --- 插件与汇总 -------------------------------------------------------
@dataclass
class PluginContent:
    manifest: Manifest | None = None
    classes: dict[str, ClassDef] = field(default_factory=dict)
    subclasses: dict[str, SubclassDef] = field(default_factory=dict)
    book: PowerBook = field(default_factory=PowerBook)
    forms: dict[str, FormSpec] = field(default_factory=dict)
    armors: dict[str, ArmorDef] = field(default_factory=dict)
    weapons: dict[str, WeaponDef] = field(default_factory=dict)
    spells: dict[str, SpellDef] = field(default_factory=dict)
    spell_lists: dict[str, tuple[str, ...]] = field(default_factory=dict)
    feats: dict[str, FeatDef] = field(default_factory=dict)
    skills: dict[str, SkillDef] = field(default_factory=dict)
    tools: dict[str, ToolDef] = field(default_factory=dict)
    summons: dict[str, "SummonDef"] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ContentBundle:
    classes: dict[str, ClassDef] = field(default_factory=dict)
    subclasses: dict[str, SubclassDef] = field(default_factory=dict)
    book: PowerBook = field(default_factory=PowerBook)
    forms: dict[str, FormSpec] = field(default_factory=dict)
    armors: dict[str, ArmorDef] = field(default_factory=dict)
    weapons: dict[str, WeaponDef] = field(default_factory=dict)
    spells: dict[str, SpellDef] = field(default_factory=dict)
    spell_lists: dict[str, tuple[str, ...]] = field(default_factory=dict)
    feats: dict[str, FeatDef] = field(default_factory=dict)
    skills: dict[str, SkillDef] = field(default_factory=dict)
    tools: dict[str, ToolDef] = field(default_factory=dict)
    summons: dict[str, "SummonDef"] = field(default_factory=dict)
    manifests: list[Manifest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def class_def(self, class_id: str) -> ClassDef:
        if class_id not in self.classes:
            raise PluginError("没有这个职业：%s（已加载：%s）"
                              % (class_id, ", ".join(sorted(self.classes)) or "无"))
        return self.classes[class_id]

    def armor(self, armor_id: str) -> ArmorDef:
        if armor_id not in self.armors:
            raise PluginError("没有这件护甲：%s" % armor_id)
        return self.armors[armor_id]

    def weapon(self, weapon_id: str) -> WeaponDef:
        if weapon_id not in self.weapons:
            raise PluginError("没有这件武器：%s" % weapon_id)
        return self.weapons[weapon_id]

    def spell(self, spell_id: str) -> SpellDef:
        if spell_id not in self.spells:
            raise PluginError("没有这个法术：%s" % spell_id)
        return self.spells[spell_id]

    def spell_list(self, class_id: str) -> tuple[str, ...]:
        return self.spell_lists.get(class_id, ())

    def classes_for_spell(self, spell_id: str) -> tuple[str, ...]:
        """哪些职业能施放这个法术 —— 从法术表反查，法术本身不存这份信息。

        存两份必然漂移：法术表是**权威**（第三方插件加一行就能给某个职业补法术），
        法术条目只描述法术自己。
        """
        return tuple(sorted(class_id for class_id, spells in self.spell_lists.items()
                            if spell_id in spells))

    def spells_of_level(self, level: int, class_id: str | None = None) -> tuple[SpellDef, ...]:
        """某一环的法术（可按职业过滤），按 id 排序保证界面稳定。"""
        allowed = set(self.spell_list(class_id)) if class_id else None
        return tuple(sorted(
            (spell for spell in self.spells.values()
             if int(spell.level) == int(level)
             and (allowed is None or spell.id in allowed)),
            key=lambda item: item.id,
        ))

    def summons_for_spell(self, spell_id: str) -> tuple[SummonDef, ...]:
        """这个法术能召出哪几只生物 —— 从召唤物反查，法术自己不存这份名单。

        与 `classes_for_spell` 同一个道理：召唤物条目里写 `spell`，法术条目只描述
        法术自己。存两份就会出现「法术说能召三只、召唤物表里只有两只」的漂移。
        """
        return tuple(sorted(
            (item for item in self.summons.values() if item.spell == spell_id),
            key=lambda item: (item.variant.zh if item.variant else "", item.id),
        ))

    def subclass(self, subclass_id: str) -> SubclassDef:
        if subclass_id not in self.subclasses:
            raise PluginError("没有这个子职：%s（已加载：%s）"
                              % (subclass_id, ", ".join(sorted(self.subclasses)) or "无"))
        return self.subclasses[subclass_id]

    def subclasses_for(self, class_id: str) -> tuple[SubclassDef, ...]:
        """某个职业可选的全部子职（按 id 排序，保证界面顺序稳定）。"""
        return tuple(sorted(
            (item for item in self.subclasses.values() if item.class_id == class_id),
            key=lambda item: item.id,
        ))

    def feat(self, feat_id: str) -> FeatDef:
        if feat_id not in self.feats:
            raise PluginError("没有这个专长：%s（已加载：%s）"
                              % (feat_id, ", ".join(sorted(self.feats)) or "无"))
        return self.feats[feat_id]

    def feats_of_kind(self, kind: str) -> tuple[FeatDef, ...]:
        return tuple(sorted(
            (item for item in self.feats.values() if item.kind == kind),
            key=lambda item: item.id,
        ))

    def stats(self) -> dict[str, Any]:
        return {
            "classes": len(self.classes),
            "feats": len(self.feats),
            "subclasses": len(self.subclasses),
            "powers": len(self.book.ids()),
            "forms": len(self.forms),
            "armors": len(self.armors),
            "weapons": len(self.weapons),
            "spells": len(self.spells),
            "spell_lists": len(self.spell_lists),
            "skills": len(self.skills),
            "tools": len(self.tools),
            "summons": len(self.summons),
            "by_kind": self.book.stats(),
            "errors": len(self.errors),
        }


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PluginError("%s 不是合法 YAML：%s" % (path, exc))


def load_plugin(folder: str | Path) -> PluginContent:
    base = Path(folder)
    result = PluginContent()
    try:
        result.manifest = load_manifest(base / "plugin.yaml")
    except PluginError as exc:
        result.errors.append(str(exc))
        return result

    for path in sorted((base / "classes").glob("*.yaml")) if (base / "classes").exists() else []:
        rel = "%s/classes/%s" % (base.name, path.name)
        try:
            class_def = parse_class(_read_yaml(path), source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if class_def.id in result.classes:
            result.errors.append("%s 的职业 id 重复：%s" % (rel, class_def.id))
            continue
        result.classes[class_def.id] = class_def
        for power in class_def.powers:
            try:
                result.book.add(power)
            except PluginError as exc:
                result.errors.append(str(exc))

    for path in sorted((base / "subclasses").glob("*.yaml")) \
            if (base / "subclasses").exists() else []:
        rel = "%s/subclasses/%s" % (base.name, path.name)
        try:
            subclass = parse_subclass(_read_yaml(path), source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if subclass.id in result.subclasses:
            result.errors.append("%s 的子职 id 重复：%s" % (rel, subclass.id))
            continue
        result.subclasses[subclass.id] = subclass
        for power in subclass.powers:
            try:
                result.book.add(power)
            except PluginError as exc:
                result.errors.append(str(exc))

    bestiary = base / "bestiary"
    if bestiary.exists():
        for path in sorted(bestiary.glob("*.yaml")):
            rel = "%s/bestiary/%s" % (base.name, path.name)
            try:
                rows = _read_yaml(path) or []
            except PluginError as exc:
                result.errors.append(str(exc))
                continue
            if isinstance(rows, Mapping):
                rows = [rows]
            for row in rows:
                try:
                    form = parse_form(row, source=rel)
                except (PluginError, DndError) as exc:
                    result.errors.append(str(exc))
                    continue
                if form.id in result.forms:
                    result.errors.append("%s 的形态 id 重复：%s" % (rel, form.id))
                    continue
                result.forms[form.id] = form

    _load_items(base, result)
    _load_spells(base, result)
    _load_feats(base, result)
    _load_skills(base, result)
    _load_tools(base, result)
    _load_summons(base, result)
    result.book.validate_augments()
    return result


def _load_summons(base: Path, result: PluginContent) -> None:
    """召唤物：一个插件一份 `summons.yaml`。

    与 `tools.yaml` 同一个位置：几十条、条目之间没有互相引用、按 id 取用 ——
    没有理由拆成「一条一文件」（那是专长/子职为了 git diff 好读才做的）。
    """
    path = base / "summons.yaml"
    if not path.exists():
        return
    rel = "%s/summons.yaml" % base.name
    try:
        rows = _read_yaml(path) or []
    except PluginError as exc:
        result.errors.append(str(exc))
        return
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows:
        try:
            summon = parse_summon(row, source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if summon.id in result.summons:
            result.errors.append("%s 的召唤物 id 重复：%s" % (rel, summon.id))
            continue
        result.summons[summon.id] = summon


def _load_tools(base: Path, result: PluginContent) -> None:
    """工具表：一个插件一份 `tools.yaml`（37 行，名称+类别+建议属性）。

    与技能同样的位置、同样的写法 —— 工具只是「另一种可以练熟的物品」，
    不该因为「只有 37 件」就塞进代码里。
    """
    path = base / "tools.yaml"
    if not path.exists():
        return
    rel = "%s/tools.yaml" % base.name
    try:
        rows = _read_yaml(path) or []
    except PluginError as exc:
        result.errors.append(str(exc))
        return
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows:
        try:
            tool = parse_tool(row, source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if tool.id in result.tools:
            result.errors.append("%s 的工具 id 重复：%s" % (rel, tool.id))
            continue
        result.tools[tool.id] = tool


def _load_feats(base: Path, result: PluginContent) -> None:
    """专长：一专长一文件（`feats/defense.yaml`）。

    与职业/子职同一套原语，所以装载时只多一步「把 powers 塞进 PowerBook」——
    专长的静态效果之后走的是完全相同的 modifier / effect 管道。
    """
    folder = base / "feats"
    if not folder.exists():
        return
    for path in sorted(folder.glob("*.yaml")):
        rel = "%s/feats/%s" % (base.name, path.name)
        try:
            feat = parse_feat(_read_yaml(path), source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if feat.id in result.feats:
            result.errors.append("%s 的专长 id 重复：%s" % (rel, feat.id))
            continue
        result.feats[feat.id] = feat
        for power in feat.powers:
            try:
                result.book.add(power)
            except PluginError as exc:
                result.errors.append(str(exc))


def _load_skills(base: Path, result: PluginContent) -> None:
    """技能表：一个插件一份 `skills.yaml`（18 行，名称+属性）。"""
    path = base / "skills.yaml"
    if not path.exists():
        return
    rel = "%s/skills.yaml" % base.name
    try:
        rows = _read_yaml(path) or []
    except PluginError as exc:
        result.errors.append(str(exc))
        return
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows:
        try:
            skill = parse_skill(row, source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if skill.id in result.skills:
            result.errors.append("%s 的技能 id 重复：%s" % (rel, skill.id))
            continue
        result.skills[skill.id] = skill


def _load_spells(base: Path, result: PluginContent) -> None:
    """法术与职业法术表。法术按环一文件（`spells/level-3.yaml`）。"""
    folder = base / "spells"
    if folder.exists():
        for path in sorted(folder.glob("*.yaml")):
            rel = "%s/spells/%s" % (base.name, path.name)
            try:
                rows = _read_yaml(path) or []
            except PluginError as exc:
                result.errors.append(str(exc))
                continue
            if isinstance(rows, Mapping):
                rows = [rows]
            for row in rows:
                try:
                    spell = parse_spell(row, source=rel)
                except (PluginError, DndError) as exc:
                    result.errors.append(str(exc))
                    continue
                if spell.id in result.spells:
                    result.errors.append("%s 的法术 id 重复：%s" % (rel, spell.id))
                    continue
                result.spells[spell.id] = spell

    lists = base / "spell-lists"
    if lists.exists():
        for path in sorted(lists.glob("*.yaml")):
            rel = "%s/spell-lists/%s" % (base.name, path.name)
            try:
                class_id, spells = parse_spell_list(_read_yaml(path), source=rel)
            except (PluginError, DndError) as exc:
                result.errors.append(str(exc))
                continue
            if class_id in result.spell_lists:
                result.errors.append("%s 的法术表职业重复：%s" % (rel, class_id))
                continue
            result.spell_lists[class_id] = spells


def _load_items(base: Path, result: PluginContent) -> None:
    """物品目录：按条目的 `kind` 分派。现在只有护甲，武器随 P5c 接入。"""
    folder = base / "items"
    if not folder.exists():
        return
    for path in sorted(folder.glob("*.yaml")):
        rel = "%s/items/%s" % (base.name, path.name)
        try:
            rows = _read_yaml(path) or []
        except PluginError as exc:
            result.errors.append(str(exc))
            continue
        if isinstance(rows, Mapping):
            rows = [rows]
        for row in rows:
            kind = str(row.get("kind", "armor")).lower() if isinstance(row, Mapping) else ""
            try:
                if kind == "armor":
                    armor = parse_armor(row, where=rel)
                    if armor.id in result.armors:
                        raise PluginError("%s 的护甲 id 重复：%s" % (rel, armor.id))
                    result.armors[armor.id] = armor
                elif kind == "weapon":
                    weapon = parse_weapon(row, where=rel)
                    if weapon.id in result.weapons:
                        raise PluginError("%s 的武器 id 重复：%s" % (rel, weapon.id))
                    result.weapons[weapon.id] = weapon
                else:
                    raise PluginError("%s 未知物品类型 %r（支持 armor / weapon）" % (rel, kind))
            except (PluginError, DndError) as exc:
                result.errors.append(str(exc))


def load_all(root: str | Path = "plugins") -> ContentBundle:
    """加载目录下所有插件。冲突报错但不清空已加载内容。"""
    bundle = ContentBundle()
    base = Path(root)
    if not base.exists():
        return bundle

    for folder in sorted(base.iterdir()):
        if not folder.is_dir() or not (folder / "plugin.yaml").exists():
            continue
        content = load_plugin(folder)
        bundle.errors.extend(content.errors)
        if content.manifest is None:
            continue
        bundle.manifests.append(content.manifest)
        for class_id, class_def in content.classes.items():
            if class_id in bundle.classes:
                bundle.errors.append(
                    "职业 %s 同时由 %s 与 %s 提供"
                    % (class_id, bundle.classes[class_id].source, class_def.source)
                )
                continue
            bundle.classes[class_id] = class_def
        for form_id, form in content.forms.items():
            if form_id in bundle.forms:
                bundle.errors.append("形态 %s 重复提供" % form_id)
                continue
            bundle.forms[form_id] = form
        for armor_id, armor in content.armors.items():
            if armor_id in bundle.armors:
                bundle.errors.append("护甲 %s 重复提供" % armor_id)
                continue
            bundle.armors[armor_id] = armor
        for weapon_id, weapon in content.weapons.items():
            if weapon_id in bundle.weapons:
                bundle.errors.append("武器 %s 重复提供" % weapon_id)
                continue
            bundle.weapons[weapon_id] = weapon
        for power in content.book.all():
            if bundle.book.has(power.id):
                bundle.errors.append("能力 %s 重复提供" % power.id)
                continue
            bundle.book.add(power)
        for skill_id, skill in content.skills.items():
            if skill_id in bundle.skills:
                bundle.errors.append("技能 %s 重复提供" % skill_id)
                continue
            bundle.skills[skill_id] = skill
        for tool_id, tool in content.tools.items():
            if tool_id in bundle.tools:
                bundle.errors.append("工具 %s 重复提供" % tool_id)
                continue
            bundle.tools[tool_id] = tool
        for summon_id, summon in content.summons.items():
            if summon_id in bundle.summons:
                bundle.errors.append("召唤物 %s 重复提供" % summon_id)
                continue
            bundle.summons[summon_id] = summon
        for subclass_id, subclass in content.subclasses.items():
            if subclass_id in bundle.subclasses:
                bundle.errors.append("子职 %s 重复提供" % subclass_id)
                continue
            bundle.subclasses[subclass_id] = subclass
        for spell_id, spell in content.spells.items():
            if spell_id in bundle.spells:
                bundle.errors.append("法术 %s 重复提供" % spell_id)
                continue
            bundle.spells[spell_id] = spell
        for class_id, spells in content.spell_lists.items():
            if class_id in bundle.spell_lists:
                bundle.errors.append("法术表 %s 重复提供" % class_id)
                continue
            bundle.spell_lists[class_id] = spells
        for feat_id, feat in content.feats.items():
            if feat_id in bundle.feats:
                bundle.errors.append("专长 %s 重复提供" % feat_id)
                continue
            bundle.feats[feat_id] = feat
    _check_subclass_classes(bundle)
    _check_spell_lists(bundle)
    _check_feat_spell_refs(bundle)
    _check_summon_spells(bundle)
    bundle.book.validate_augments()
    return bundle


def _check_summon_spells(bundle: ContentBundle) -> None:
    """召唤物指向的法术必须存在。

    只能合并之后查：召唤物与法术可以来自不同插件（一个插件提供法术、另一个补
    stat block 是合法用法）。查不到就是「召出来但界面找不到入口」，报错而不是静默丢。
    """
    for summon in bundle.summons.values():
        if summon.spell not in bundle.spells:
            bundle.errors.append(
                "召唤物 %s 指向不存在的法术 %s" % (summon.id, summon.spell))


def _check_spell_lists(bundle: ContentBundle) -> None:
    """法术表里引用的 id 必须存在；表里也不能把不同环级的法术混在一起。

    同样只能在合并之后查：法术与法术表可以来自不同插件。
    """
    for class_id, spells in bundle.spell_lists.items():
        if class_id not in bundle.classes:
            bundle.errors.append("法术表挂在未知职业上：%s" % class_id)
        missing = [ident for ident in spells if ident not in bundle.spells]
        if missing:
            bundle.errors.append("法术表 %s 引用了不存在的法术：%s"
                                 % (class_id, ", ".join(missing[:5])))


def _check_feat_spell_refs(bundle: ContentBundle) -> None:
    """专长引用的法术/法术表必须存在。

    与法术表同样的理由只能在合并后查：专长可以来自别的插件，法术也是。
    `choice.spell_list` 指向的职业必须**有法术表** —— 否则玩家在界面上会看到
    一个空下拉框，而不是一条能被看见的错误。
    """
    for feat in bundle.feats.values():
        missing = [ident for ident in feat.spells if ident not in bundle.spells]
        if missing:
            bundle.errors.append("专长 %s 给了不存在的法术：%s"
                                 % (feat.id, ", ".join(missing[:5])))
        for choice in feat.choices:
            if choice.kind != "spell":
                continue
            if choice.spell_list == SPELL_LIST_ANY:
                continue
            class_id = "dnd2024.class.%s" % choice.spell_list
            if class_id not in bundle.classes:
                bundle.errors.append(
                    "专长 %s 的选择项 %s 指向未知职业 %s"
                    % (feat.id, choice.id, choice.spell_list))
            elif not bundle.spell_list(class_id):
                bundle.errors.append(
                    "专长 %s 的选择项 %s 指向的职业 %s 没有法术表"
                    % (feat.id, choice.id, choice.spell_list))


def _check_subclass_classes(bundle: ContentBundle) -> None:
    """子职必须挂在已加载的职业上。

    只能放在合并之后做：职业与子职可以来自不同插件（第三方给核心职业补子职）。
    解析期查不到别的插件有没有这个职业，所以这一步晚于解析是必然的。
    """
    for subclass in bundle.subclasses.values():
        if subclass.class_id not in bundle.classes:
            bundle.errors.append(
                "子职 %s 挂在未知职业 %s 上（来自 %s）"
                % (subclass.id, subclass.class_id, subclass.source or "?")
            )


__all__ = [
    "ResourceDef", "ClassDef", "SubclassDef", "ArmorDef", "WeaponDef",
    "PluginContent", "ContentBundle",
    "parse_resource", "parse_class", "parse_subclass", "parse_cr_axis", "parse_form",
    "parse_armor", "parse_weapon", "powers_at_level",
    "SpellDef", "parse_spell", "parse_spell_list", "lookup_dice",
    "FeatDef", "FeatChoice", "parse_feat", "parse_feat_choice",
    "FEAT_KINDS", "CHOICE_KINDS", "CHOICE_UNIVERSE", "DAMAGE_TYPES", "SKILL_KEYS",
    "SkillDef", "parse_skill",
    "load_plugin", "load_all",
]
