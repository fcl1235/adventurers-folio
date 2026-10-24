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
from typing import TYPE_CHECKING, Any, Mapping

from ..kernel.dice import DiceError
from ..kernel.dice import parse as parse_dice
from ..kernel.errors import PluginError, RuleError
from ..kernel.text import Text
from ..model.actor import Actor, ActorKind, HpPool
from ..model.statblock import ABILITY_KEYS, Abilities, Statblock
from .advantage import merge

if TYPE_CHECKING:
    from .encounter import Encounter

SIZES: tuple[str, ...] = ("tiny", "small", "medium", "large", "huge", "gargantuan")
SPEED_KINDS: tuple[str, ...] = ("walk", "climb", "swim", "fly", "burrow")
SENSE_KINDS: tuple[str, ...] = ("blindsight", "darkvision", "tremorsense", "truesight")
# 一条动作用哪种方式结算，五种就够：掷命中 / 掷命中（远程）/ 对面豁免 /
# 只是「多重攻击」的说明（真正的结算在它列的那几条攻击里）/ 其余（纯文字）。
ACTION_KINDS: tuple[str, ...] = ("melee", "ranged", "save", "multiattack", "other")

# 特性可以改变的掷骰形状。`flat` 不写进内容（写了等于「无条件平掷」的废话）。
MODE_VALUES: tuple[str, ...] = ("adv", "dis")
# 三种事实：两种问 HP、一种问位置。都不是内容能自答的。
MODE_FACTS: tuple[str, ...] = ("ally_near_target", "target_wounded", "self_bloodied")


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
    """被动特性。

    大多数特性**只有文字** —— 它们改的是环境（能不能在水下呼吸）、
    惩罚谁（阳光敏感），不是这一掷的数字。硬把它们变成字段就是在编规则。

    但有一类例外是**算得出来的**，而且不算就会明着错：改变这一掷的
    **掷骰形状**（优势/劣势）。所以 `attack_mode` + `when` 两个字段：

        attack_mode: { mode: adv, when: ally_near_target }

    `when` 只认三种事实，都得由 `Encounter` / `Actor` 回答，不是内容自己说了算：

      ally_near_target  目标的 5 尺内有没有**它这一伙**的人（阵营 + 位置）
      target_wounded    目标 HP 未满（`current < maximum`）
      self_bloodied     自己浴血（`current * 2 <= maximum`，2024 的 Bloodied）

    留空 = 无条件（数据里没有这种条目，通道先留着）。
    **算不出来就说算不出来**（`unknown`），不许默认「不成立」——
    那会把「不知道谁站在旁边」悄悄变成「没有盟友」。
    """

    name: Text
    text: Text
    attack_mode: str = ""
    when: str = ""

    def __post_init__(self) -> None:
        if self.attack_mode and self.attack_mode not in MODE_VALUES:
            raise PluginError("%s 的攻击掷骰模式只能是 %s：%r"
                              % (self.name.zh, "/".join(MODE_VALUES), self.attack_mode))
        if self.when and self.when not in MODE_FACTS:
            raise PluginError("%s 的触发事实不认识：%r（只认 %s）"
                              % (self.name.zh, self.when, "/".join(MODE_FACTS)))
        if self.when and not self.attack_mode:
            raise PluginError("%s 写了 when 却没有 attack_mode —— 那句条件不会生效"
                              % self.name.zh)

    def to_dict(self, locale: str = "zh") -> dict:
        row = {"name": self.name.get(locale), "text": self.text.get(locale)}
        if self.attack_mode:
            row["attack_mode"] = self.attack_mode
            row["when"] = self.when
        return row


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
    # `attack_mode` 两种写法都收：结构式 `{mode: adv, when: ...}`（生成器用）
    # 与平铺的 `attack_mode: adv` + `when: ...`（手写内容顺手）。
    # 值域校验在 `MonsterTrait.__post_init__`，这里的职责只是把字段读出来。
    mode_data = data.get("attack_mode")
    attack_mode = when = ""
    if isinstance(mode_data, Mapping):
        attack_mode = str(mode_data.get("mode", "")).strip().lower()
        when = str(mode_data.get("when", "")).strip().lower()
    elif mode_data:
        attack_mode = str(mode_data).strip().lower()
        when = str(data.get("when", "")).strip().lower()
    return MonsterTrait(
        name=Text.from_dict(data["name"], where="%s name" % where),
        text=Text.from_dict(data["text"], where="%s text" % where),
        attack_mode=attack_mode,
        when=when,
    )


# --- 特性事实（G23 / P10b）-----------------------------------------------
UNKNOWN = "unknown"

_FACT_ZH = {
    "ally_near_target": "目标的 5 尺内有没有它这一伙的人",
    "target_wounded": "目标 HP 是否未满",
    "self_bloodied": "自己是否浴血",
}


def _fact_value(
    fact: str,
    encounter: "Encounter | None",
    attacker: Actor,
    target: Actor | None,
) -> str:
    """回答一个事实：`true` / `false` / `unknown`。

    **unknown 不许折叠成 false** ——「不知道谁站在旁边」和「没有盟友」是两句话，
    折叠了就会把玩家实打实的优势悄悄吃掉。算不出的分支全部显式返回 unknown。
    """
    if fact == "self_bloodied":
        hp = attacker.root().hp
        return "true" if hp.current * 2 <= hp.maximum else "false"
    if fact == "target_wounded":
        if target is None:
            return UNKNOWN          # 手填的 Target 没有 HP，看得见 AC 看不见血
        hp = target.root().hp
        return "true" if hp.current < hp.maximum else "false"
    if fact == "ally_near_target":
        if encounter is None or target is None:
            return UNKNOWN          # 没有场，就没有「站在谁旁边」
        try:
            source = encounter.get(attacker)
            mark = encounter.get(target)
        except RuleError:
            return UNKNOWN          # 打人或挨打的那个不在场上
        if not mark.placed:
            return UNKNOWN          # 目标没摆位，5 尺无从量起
        allies = encounter.allies_of(source)
        if any(not item.placed for item in allies):
            return UNKNOWN          # 有盟友没摆位：他可能就站在旁边
        return "true" if encounter.allies_near(source, mark) else "false"
    raise PluginError("不认识的触发事实：%r（只认 %s）"
                      % (fact, "/".join(MODE_FACTS)))


def trait_attack_mode(
    traits: tuple[MonsterTrait, ...],
    encounter: "Encounter | None",
    attacker: Actor,
    target: Actor | None = None,
    locale: str = "zh",
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """把一张特性表折成（掷骰模式, 给了模式的特性名, 无法判定的说明）。

    优势与劣势同时成立 = 平掷（与玩家通道同一条规则，走 `advantage.merge`）。
    unknown 的特性**不猜**：按平掷走，把话说出来让 DM 自己选掷骰模式。
    """
    modes: list[str] = []
    sources: list[str] = []
    unknowns: list[str] = []
    for trait in traits:
        if not trait.attack_mode:
            continue
        name = trait.name.get(locale)
        value = _fact_value(trait.when, encounter, attacker, target)
        if value == "true":
            modes.append(trait.attack_mode)
            sources.append(name)
        elif value == "unknown":
            unknowns.append("%s 判不了（%s：位置或血量算不出来），本次按平掷；"
                            "要改请手动指定掷骰模式" % (name, _FACT_ZH.get(trait.when, trait.when)))
    return merge(modes), tuple(sources), tuple(unknowns)


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
    "MODE_VALUES", "MODE_FACTS", "UNKNOWN",
    "DamageRoll", "MonsterAttack", "MonsterTrait",
    "parse_damage_roll", "parse_attack", "parse_trait",
    "trait_attack_mode", "_fact_value",
    "build_monster", "label_for", "cr_text",
    "find_attack", "attack_options", "monster_stats",
]
