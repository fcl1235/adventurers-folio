# -*- coding: utf-8 -*-
"""怪物：场上的样子，以及它那几下动作怎么读。

与召唤物（`rules/summon.py`）的三点不同，都不是随手定的：

1. **数值是固定的**，不是环级的函数。所以没有 `Scaling` —— 哥布林的 AC 15
   就是 15，换成「15 + 0 × 环级」只是多一层没人用的抽象。
2. **命中加值是内容里印着的数**，不能从属性推。实测 91 只 SRD 怪物里，
   95 条近战/远程攻击有 85 条推不出来：巨鳄的啃咬 +8，而它的力量 +5、
   敏捷 −1（属性 + 熟练的四种组合是 5/7/−1/1，没有一个等于 8）。
   按公式硬算必然算错，所以这里存 `attack_bonus` 原值。
3. **豁免加值也是印着的数**。怪物的「豁免熟练」不总等于 `属性 + 熟练`，
   所以 `saves` 直接进 `Statblock`，`target_from_actor` 优先读它。

这里只认规则词汇（体型、动作类别、伤害类型），不认任何具体怪物的名字 ——
名字在内容插件里（约束 C1）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..kernel.dice import DiceError
from ..kernel.dice import parse as parse_dice
from ..kernel.errors import PluginError
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.statblock import ABILITY_KEYS, Abilities, Statblock

SIZES: tuple[str, ...] = ("tiny", "small", "medium", "large", "huge", "gargantuan")
SPEED_KINDS: tuple[str, ...] = ("walk", "climb", "swim", "fly", "burrow")
SENSE_KINDS: tuple[str, ...] = ("blindsight", "darkvision", "tremorsense", "truesight")
# 一条动作用哪种方式结算，五种就够：掷命中 / 掷命中（远程）/ 对面豁免 /
# 只是「多重攻击」的说明（真正的结算在它列的那几条攻击里）/ 其余（纯文字）。
ACTION_KINDS: tuple[str, ...] = ("melee", "ranged", "save", "multiattack", "other")


@dataclass(frozen=True, slots=True)
class DamageRoll:
    """一段伤害：骰式（可带定值，如 `1d6+2`）+ 伤害类型。

    骰式里带定值是原文的写法，不拆成 `dice + flat` —— 拆了就要在
    「重击加骰不加定值」那条规则里再拼回去，多一次出错的机会。
    """

    dice: str
    type: str = ""

    def __post_init__(self) -> None:
        if not self.dice:
            raise PluginError("伤害骰式不能为空")
        try:
            parse_dice(self.dice)
        except DiceError as exc:
            raise PluginError("伤害骰式不合法：%s" % exc)


@dataclass(frozen=True, slots=True)
class MonsterAttack:
    """一条动作。

    `attack_bonus` 是**印在卡上的数**（见模块注释），不是推出来的；
    `save` / `save_dc` 是「对面掷豁免」那类动作的两个数。

    三类动作各自必填的字段在 `__post_init__` 里卡死：近战要 reach、
    远程要 range、豁免要 save + dc、掷命中的要有 attack_bonus。
    少一个就报错，而不是在结算时才发现「这个数没有」。
    """

    name: Text
    kind: str = "melee"
    attack_bonus: int | None = None
    reach: int = 0
    range: int = 0
    long_range: int = 0
    save: str = ""
    save_dc: int = 0
    damage: tuple[DamageRoll, ...] = ()
    text: Text | None = None

    def __post_init__(self) -> None:
        if self.kind not in ACTION_KINDS:
            raise PluginError("%s 的动作类别必须是 %s"
                              % (self.name.zh, "/".join(ACTION_KINDS)))
        if self.kind in ("melee", "ranged") and self.attack_bonus is None:
            raise PluginError("%s 是掷命中的动作，必须写 attack_bonus" % self.name.zh)
        if self.kind == "melee" and self.reach < 1:
            raise PluginError("%s 是近战动作，必须写 reach" % self.name.zh)
        if self.kind == "ranged" and self.range < 1:
            raise PluginError("%s 是远程动作，必须写 range" % self.name.zh)
        if self.kind == "save":
            if self.save not in ABILITY_KEYS:
                raise PluginError("%s 的豁免属性不合法：%r" % (self.name.zh, self.save))
            if self.save_dc < 1:
                raise PluginError("%s 要豁免就必须写 save_dc" % self.name.zh)
        if self.long_range and self.long_range < self.range:
            raise PluginError("%s 的远射程小于常规射程" % self.name.zh)

    @property
    def is_attack_roll(self) -> bool:
        return self.kind in ("melee", "ranged")

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "name": self.name.get(locale),
            "kind": self.kind,
            "attack_bonus": self.attack_bonus,
            "reach": self.reach,
            "range": self.range,
            "long_range": self.long_range,
            "save": self.save,
            "save_dc": self.save_dc,
            "damage": [{"dice": row.dice, "type": row.type} for row in self.damage],
            "text": self.text.get(locale) if self.text else "",
        }


@dataclass(frozen=True, slots=True)
class MonsterTrait:
    """被动特性。**只有文字** —— 它们改的是判定条件，不是数字。

    真要算（「群体战术」给优势）需要「谁站在谁旁边」的判定，
    那是 `Encounter` 的事，不是内容的事。
    """

    name: Text
    text: Text

    def to_dict(self, locale: str = "zh") -> dict:
        return {"name": self.name.get(locale), "text": self.text.get(locale)}


def parse_damage_roll(data: Any, where: str = "") -> DamageRoll:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的伤害必须是映射" % where)
    if "dice" not in data:
        raise PluginError("%s 的伤害缺少 dice" % where)
    return DamageRoll(dice=str(data["dice"]), type=str(data.get("type", "")).lower())


def parse_attack(data: Any, where: str = "") -> MonsterAttack:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的怪物动作必须是映射" % where)
    if "name" not in data:
        raise PluginError("%s 的怪物动作缺少 name" % where)
    rows = data.get("damage") or ()
    if isinstance(rows, Mapping):
        rows = [rows]
    bonus = data.get("attack_bonus")
    return MonsterAttack(
        name=Text.from_dict(data["name"], where="%s name" % where),
        kind=str(data.get("kind", "melee")).lower(),
        attack_bonus=None if bonus is None else int(bonus),
        reach=int(data.get("reach", 0) or 0),
        range=int(data.get("range", 0) or 0),
        long_range=int(data.get("long_range", 0) or 0),
        save=str(data.get("save", "")).lower(),
        save_dc=int(data.get("save_dc", 0) or 0),
        damage=tuple(parse_damage_roll(row, where=where) for row in rows),
        text=Text.from_dict(data["text"], where="%s text" % where)
        if data.get("text") else None,
    )


def parse_trait(data: Any, where: str = "") -> MonsterTrait:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的怪物特性必须是映射" % where)
    for key in ("name", "text"):
        if key not in data:
            raise PluginError("%s 的怪物特性缺少 %s" % (where, key))
    return MonsterTrait(
        name=Text.from_dict(data["name"], where="%s name" % where),
        text=Text.from_dict(data["text"], where="%s text" % where),
    )


# --- 出场 ---------------------------------------------------------------
def build_monster(monster, index: int = 1) -> Actor:
    """把一只怪物变成场上的 Actor。

    `index` 是「同种第几只」：三只哥布林要有三个不同的 id，否则
    `Encounter.add` 会以「参与者重复」拒绝，而且三段血会记到同一只身上。

    AC 反推成 `ac_base`（减去敏捷调整值）：Resolver 统一按「基础 + 敏捷」算，
    与 `build_form` 同一个做法 —— 不反推就会多加一次敏捷。
    """
    abilities = monster.abilities
    statblock = Statblock(
        name=monster.name,
        abilities=abilities,
        ac_base=max(0, int(monster.ac) - abilities.mod("dex")),
        speeds=dict(monster.speeds),
        senses=dict(monster.senses),
        size=monster.size,
        cr=monster.cr,
        saves=dict(monster.saves),
    )
    return Actor(
        id=monster.id if int(index) <= 1 else "%s#%d" % (monster.id, int(index)),
        kind=ActorKind.MONSTER,
        statblock=statblock,
        hp=HpPool(maximum=int(monster.hp)),
        display_name=label_for(monster, index),
    )


def label_for(monster, index: int = 1, locale: str = "zh") -> str:
    """显示名。同种多只加序号 —— 界面上「哥布林」有三行分不清谁是谁。"""
    base = monster.name.get(locale)
    return base if int(index) <= 1 else "%s %d" % (base, int(index))


def cr_text(cr: float) -> str:
    """CR 0.25 写成「1/4」：桌上念的是「四分之一」，不是「零点二五」。"""
    value = float(cr)
    for num, den, label in ((1, 8, "1/8"), (1, 4, "1/4"), (1, 2, "1/2")):
        if abs(value - num / den) < 1e-9:
            return label
    return ("%d" % value) if abs(value - round(value)) < 1e-9 else ("%g" % value)


def _sorted_attacks(monster) -> list[tuple[str, int, MonsterAttack]]:
    """按「动作 → 附赠动作 → 反应」的顺序摊平，带回它在原列表里的下标。"""
    rows: list[tuple[str, int, MonsterAttack]] = []
    for slot, items in (("action", monster.actions),
                        ("bonus", monster.bonus_actions),
                        ("reaction", monster.reactions)):
        for index, item in enumerate(items):
            rows.append((slot, index, item))
    return rows


def find_attack(monster, slot: str, index: int) -> MonsterAttack:
    """按 `attack_options` 给出的 (slot, index) 取一条动作。

    用「位置」而不是「名字」做键：同一只怪物可能有两把完全同名的攻击
    （双持的哥布林），按名字取会静默拿到第一条。
    """
    table = {"action": monster.actions, "bonus": monster.bonus_actions,
             "reaction": monster.reactions}
    if slot not in table:
        raise PluginError("动作槽位不认识：%r（可选 %s）" % (slot, "/".join(table)))
    items = table[slot]
    if not 0 <= int(index) < len(items):
        raise PluginError("%s 的 %s 里没有第 %d 条动作"
                          % (monster.id, slot, int(index)))
    return items[int(index)]


def attack_options(monster, locale: str = "zh") -> list[dict]:
    """给界面与 API 的动作清单。`rollable` 说明这条现在能不能直接掷。"""
    rows: list[dict] = []
    for slot, index, item in _sorted_attacks(monster):
        row = item.to_dict(locale)
        row.update({
            "slot": slot,
            "index": index,
            "key": "%s:%d" % (slot, index),
            "rollable": item.is_attack_roll,
        })
        rows.append(row)
    return rows


def monster_stats(monster, actor: Actor, locale: str = "zh") -> dict:
    """一只怪物卡上的数（界面上要能核对，不能只显示名字）。"""
    top = actor.top()
    return {
        "id": actor.id,
        "name": monster.name.get(locale),
        "label": actor.display_name,
        "size": monster.size,
        "ac": int(monster.ac),
        "hp": int(monster.hp),
        "hp_dice": monster.hp_dice,
        "cr": float(monster.cr),
        "cr_text": cr_text(monster.cr),
        "abilities": dict(top.statblock.abilities.scores),
        "speeds": dict(monster.speeds),
        "senses": dict(monster.senses),
        "passive_perception": int(monster.passive_perception),
        "saves": dict(monster.saves),
        "traits": [row.to_dict(locale) for row in monster.traits],
        "actions": attack_options(monster, locale),
        "note": monster.note.get(locale) if monster.note else "",
    }


__all__ = [
    "SIZES", "SPEED_KINDS", "SENSE_KINDS", "ACTION_KINDS",
    "DamageRoll", "MonsterAttack", "MonsterTrait",
    "parse_damage_roll", "parse_attack", "parse_trait",
    "build_monster", "label_for", "cr_text",
    "find_attack", "attack_options", "monster_stats",
]
