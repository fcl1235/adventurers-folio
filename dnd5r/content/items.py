# -*- coding: utf-8 -*-
"""护甲与武器定义。拆自 P11 之前的 content.py。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..kernel.dice import parse as parse_dice
from ..kernel.errors import DndError, PluginError
from ..kernel.ids import is_valid
from ..kernel.text import Text
from ..model.inventory import EquipSlot

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


# --- 物品：冒险装备 ---------------------------------------------------
# 背包里的东西。**不参与 AC / 攻击 / 施法**的任何计算 —— 那一类只认护甲与武器。
# 分这七类只为了界面分组，以及「哪件是包、哪件是法器」这种展示上的区别。
GEAR_CATEGORIES = ("pack", "tool", "focus", "book", "clothing", "ammo", "gear")


@dataclass(frozen=True)
class GearDef:
    """一件冒险装备。

    `contains` 是背包类物品**内含的件数**（问号：为什么不列清单）：清单要再收
    40 件物品并逐条翻译，而界面上「含 11 件」已经够用。它不展开、也不影响负重
    —— 重量已经算在包身上了。
    """

    id: str
    name: Text
    category: str = "gear"
    cost_cp: int | None = None
    weight: float | None = None
    contains: int = 0

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("装备 id 不合规范：%r" % (self.id,))
        if self.category not in GEAR_CATEGORIES:
            raise PluginError("%s 的装备类别必须是 %s"
                              % (self.id, "/".join(GEAR_CATEGORIES)))
        if self.cost_cp is not None and self.cost_cp < 0:
            raise PluginError("%s 的价格不能为负：%r" % (self.id, self.cost_cp))
        if self.weight is not None and self.weight < 0:
            raise PluginError("%s 的重量不能为负：%r" % (self.id, self.weight))
        if self.contains < 0:
            raise PluginError("%s 的内含件数不能为负" % self.id)

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "id": self.id, "name": self.name.get(locale),
            "category": self.category, "cost_cp": self.cost_cp,
            "weight": self.weight, "contains": self.contains,
        }


def parse_gear(data: Any, where: str = "") -> GearDef:
    prefix = ("%s: " % where) if where else ""
    if not isinstance(data, Mapping):
        raise PluginError("%s装备条目必须是映射" % prefix)
    ident = data.get("id")
    if not ident:
        raise PluginError("%s装备缺少 id" % prefix)
    if "name" not in data:
        raise PluginError("%s %s 缺少 name" % (prefix, ident))
    cost = data.get("cost_cp")
    weight = data.get("weight")
    try:
        return GearDef(
            id=str(ident),
            name=Text.from_dict(data["name"], where="%s name" % ident),
            category=str(data.get("category", "gear")).lower(),
            cost_cp=None if cost in (None, "") else int(cost),
            weight=None if weight in (None, "") else float(weight),
            contains=int(data.get("contains", 0) or 0),
        )
    except (TypeError, ValueError) as exc:
        raise PluginError("%s %s 的数值字段不合法：%s" % (prefix, ident, exc))
