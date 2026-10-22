# -*- coding: utf-8 -*-
"""武器：攻击加值、伤害加值、熟练判定。

三条推论规则（都在这里，不在数据里）：
  1. **用哪个属性**：远程用敏捷；灵巧武器取力量/敏捷较高的那个；其余用力量
  2. **是否熟练**：看 `weapon.<类别>` token。军用武器还有两个例外写法 ——
     `martial_light`（只熟军用轻型）、`martial_finesse_or_light`（熟军用灵巧或轻型），
     它们是 2024 职业表里真实存在的措辞（武僧、游荡者），不是特例代码
  3. **重型武器**：力量（远程则为敏捷）不足 13 时攻击有劣势

伤害加值默认加属性调整值；副手不加（双武器规则等 P5 后续的专长通道）。
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol

from ..kernel.dice import Dice, parse as parse_dice
from ..kernel.text import Text
from ..model.inventory import EquipSlot
from ..model.statblock import Abilities

# 术语（不是内容）：伤害类型只有三种，写在这里省得每个调用点各带一份翻译
DAMAGE_NAMES: Mapping[str, Text] = MappingProxyType({
    "bludgeoning": Text.of("钝击", "Bludgeoning"),
    "piercing": Text.of("穿刺", "Piercing"),
    "slashing": Text.of("挥砍", "Slashing"),
})


def damage_name(kind: str, locale: str = "zh") -> str:
    name = DAMAGE_NAMES.get(kind)
    return name.get(locale) if name is not None else kind


class WeaponLike(Protocol):
    """`content.WeaponDef` 的结构。用 Protocol 是为了让规则层不依赖 YAML 解析。"""

    id: str
    name: Text
    category: str
    damage: str
    damage_type: str
    versatile: str | None
    properties: tuple[str, ...]
    mastery: str


HEAVY_MIN_SCORE = 13
_MELEE_ABILITIES = ("str", "dex")


def has_property(weapon: WeaponLike, prop: str) -> bool:
    return prop in tuple(weapon.properties or ())


def is_ranged(weapon: WeaponLike) -> bool:
    return has_property(weapon, "ranged")


def attack_ability(weapon: WeaponLike, abilities: Abilities) -> str:
    """远程用敏捷；灵巧取高者；其余用力量。"""
    if is_ranged(weapon):
        return "dex"
    if has_property(weapon, "finesse"):
        return "str" if abilities.mod("str") >= abilities.mod("dex") else "dex"
    return "str"


def damage_dice(weapon: WeaponLike | None, two_handed: bool = False) -> Dice:
    """伤害骰。没有武器就是徒手 1 点（2024：1 + 力量调整值）。"""
    if weapon is None:
        return parse_dice("1")
    expr = weapon.versatile if (two_handed and weapon.versatile) else weapon.damage
    return parse_dice(str(expr))


def damage_type(weapon: WeaponLike | None) -> str:
    return weapon.damage_type if weapon is not None else "bludgeoning"


def proficient(weapon: WeaponLike | None, tokens: Iterable[str]) -> bool:
    """徒手打击永远熟练；武器看 token。"""
    if weapon is None:
        return True
    known = set(tokens)
    category = weapon.category
    if "weapon.%s" % category in known:
        return True
    if category != "martial":
        return False
    if "weapon.martial_light" in known and has_property(weapon, "light"):
        return True
    if "weapon.martial_finesse_or_light" in known and (
        has_property(weapon, "light") or has_property(weapon, "finesse")
    ):
        return True
    return False


def attack_modifier(
    weapon: WeaponLike | None,
    abilities: Abilities,
    prof_bonus: int,
    tokens: Iterable[str] = (),
) -> int:
    ability = attack_ability(weapon, abilities) if weapon is not None else "str"
    total = abilities.mod(ability)
    if proficient(weapon, tokens):
        total += int(prof_bonus)
    return total


def damage_modifier(
    weapon: WeaponLike | None,
    abilities: Abilities,
    off_hand: bool = False,
) -> int:
    """伤害加属性调整值；副手默认不加（双武器战斗风格才加，见 P5 后续）。"""
    if off_hand:
        return 0
    ability = attack_ability(weapon, abilities) if weapon is not None else "str"
    return abilities.mod(ability)


def heavy_penalty(weapon: WeaponLike | None, abilities: Abilities) -> bool:
    """2024 重型武器：力量不足 13（远程武器看敏捷）时攻击有劣势。"""
    if weapon is None or not has_property(weapon, "heavy"):
        return False
    key = "dex" if is_ranged(weapon) else "str"
    return abilities.score(key) < HEAVY_MIN_SCORE


@dataclass(frozen=True, slots=True)
class AttackProfile:
    """一次攻击的完整算式结果。前端只画，不再算。"""

    weapon_id: str
    name: Text
    ability: str
    proficient: bool
    attack: int
    damage: Dice
    damage_bonus: int
    damage_type: str
    mastery: str
    off_hand: bool = False
    disadvantage: bool = False
    # 来自能力的额外攻击加值（箭术 +2）。单列一项，攻击总值里已经加过，
    # 列出来是为了让界面能说明「+5 = +3 敏捷 +2 熟练 +2 箭术」里的最后那一项。
    misc: int = 0

    @property
    def damage_total_hint(self) -> str:
        """"1d8+3 挥砍" 这种给人看的写法。"""
        if self.damage_bonus:
            return "%s%+d" % (self.damage, self.damage_bonus)
        return str(self.damage)

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "weapon": self.weapon_id,
            "name": self.name.get(locale),
            "ability": self.ability,
            "proficient": self.proficient,
            "attack": self.attack,
            "damage": str(self.damage),
            "damage_bonus": self.damage_bonus,
            "damage_type": damage_name(self.damage_type, locale),
            "mastery": self.mastery,
            "off_hand": self.off_hand,
            "disadvantage": self.disadvantage,
            "misc": self.misc,
        }


UNARMED_NAME = Text.of("徒手打击", "Unarmed Strike")


def profile(
    weapon: WeaponLike | None,
    abilities: Abilities,
    prof_bonus: int,
    tokens: Iterable[str] = (),
    off_hand: bool = False,
    two_handed: bool = False,
    misc: int = 0,
) -> AttackProfile:
    """把武器 + 属性 + 熟练（+ 能力给的额外加值）算成一次攻击。"""
    tokens = tuple(tokens)
    attack_extra = int(misc)
    ability = attack_ability(weapon, abilities) if weapon is not None else "str"
    return AttackProfile(
        weapon_id=weapon.id if weapon is not None else "unarmed",
        name=weapon.name if weapon is not None else UNARMED_NAME,
        ability=ability,
        proficient=proficient(weapon, tokens),
        attack=attack_modifier(weapon, abilities, prof_bonus, tokens) + attack_extra,
        damage=damage_dice(weapon, two_handed=two_handed and not off_hand),
        damage_bonus=damage_modifier(weapon, abilities, off_hand=off_hand),
        damage_type=damage_type(weapon),
        mastery=weapon.mastery if weapon is not None else "",
        off_hand=off_hand,
        disadvantage=heavy_penalty(weapon, abilities),
        misc=attack_extra,
    )


def equipped_weapons(
    actor,
    weapons: Mapping[str, WeaponLike],
) -> tuple[WeaponLike | None, WeaponLike | None]:
    """读装备槽里的主手/副手武器。变形期间一律为空 —— 形态攻击不是武器攻击。"""
    if actor.top().layer is not None:
        return (None, None)
    gear = actor.root().inventory.equipped
    main = weapons.get(gear.get(EquipSlot.MAIN_HAND, ""))
    off = weapons.get(gear.get(EquipSlot.OFF_HAND, ""))
    return (main, off)


def profiles_for(
    actor,
    weapons: Mapping[str, WeaponLike],
    abilities: Abilities,
    prof_bonus: int,
    tokens: Iterable[str] = (),
    ranged_bonus: int = 0,
    melee_bonus: int = 0,
) -> tuple[AttackProfile, ...]:
    """当前这一身能打出的攻击。没拿武器就是徒手打击。

    两用武器默认按双手握持算伤害（副手空着的时候），拿了两把就退回单手档 ——
    「一只手拿剑一只手拿盾」的玩家期望看到 1d8，不是 1d10。
    """
    main, off = equipped_weapons(actor, weapons)
    tokens = tuple(tokens)

    def bonus_for(weapon: WeaponLike | None) -> int:
        """远程加值只给远程武器，近战加值只给近战（徒手算近战）。"""
        if weapon is not None and is_ranged(weapon):
            return int(ranged_bonus)
        return int(melee_bonus)

    if main is None and off is None:
        return (profile(None, abilities, prof_bonus, tokens, misc=bonus_for(None)),)
    found: list[AttackProfile] = []
    two_handed = main is not None and has_property(main, "versatile") and off is None
    if main is not None:
        found.append(profile(main, abilities, prof_bonus, tokens, two_handed=two_handed,
                             misc=bonus_for(main)))
    if off is not None:
        found.append(profile(off, abilities, prof_bonus, tokens, off_hand=True,
                             misc=bonus_for(off)))
    return tuple(found)


__all__ = [
    "WeaponLike", "AttackProfile", "UNARMED_NAME",
    "attack_ability", "attack_modifier", "damage_dice", "damage_modifier",
    "damage_type", "proficient", "heavy_penalty", "has_property", "is_ranged",
    "profile", "profiles_for", "equipped_weapons", "HEAVY_MIN_SCORE",
]
