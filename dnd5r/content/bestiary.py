# -*- coding: utf-8 -*-
"""怪物 / 召唤物 / 野兽形态定义。拆自 P11 之前的 content.py。

命中加值与豁免加值都是卡上印着的数，不由属性推算 —— 见 rules/monsters.py。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..kernel.errors import PluginError, RuleError
from ..kernel.ids import is_valid
from ..kernel.text import Text
from ..model.levels import ClassLevel, as_class_level
from ..model.statblock import ABILITY_KEYS, Abilities
from ..rules.morph import CrAxis, FormSpec
from ..rules.monsters import ACTION_KINDS as MONSTER_ACTION_KINDS
from ..rules.monsters import (
    MonsterAttack,
    MonsterTrait,
    parse_attack as parse_monster_attack,
    parse_trait as parse_monster_trait,
)
from ..rules.summon import (
    Scaling,
    SENSE_KINDS,
    SIZES,
    SPEED_KINDS,
    SummonAction,
    parse_action,
    parse_scaling,
    resolve as resolve_summon,
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
class MonsterDef:
    """一只怪物（可以拿来打的那种）。

    **为什么不是 `FormSpec`**：形态（荒野变形）只回答「变成它以后我的属性是多少」，
    没有任何动作数据 —— 熊变成熊以后照样按徒手算（P9b 的报告里明写过这件事）。
    怪物要能反击，就必须有自己的命中加值、伤害骰、豁免 DC。

    **为什么命中加值不是推出来的**：SRD 怪物的攻击加值不服从「属性调整值 + 熟练」，
    91 只里 85 条对不上（`rules/monsters.py` 开头有实测）。所以 `attack_bonus`
    原样存内容里，引擎不重算。

    `saves` 是卡上印着的豁免加值（只有写了的那几项），进 `Statblock.saves`，
    `target_from_actor` 优先读它 —— 玩家扔火球砸怪物时，DC 算错两点很难被发现。
    """

    id: str
    name: Text
    ac: int
    hp: int
    cr: float
    abilities: Abilities
    size: str = "medium"
    hp_dice: str = ""
    speeds: Mapping[str, int] = field(default_factory=dict)
    senses: Mapping[str, int] = field(default_factory=dict)
    passive_perception: int = 10
    saves: Mapping[str, int] = field(default_factory=dict)
    skills: Mapping[str, int] = field(default_factory=dict)
    traits: tuple[MonsterTrait, ...] = ()
    actions: tuple[MonsterAttack, ...] = ()
    bonus_actions: tuple[MonsterAttack, ...] = ()
    reactions: tuple[MonsterAttack, ...] = ()
    note: Text | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("怪物 id 不合规范：%r" % (self.id,))
        if self.ac < 1:
            raise PluginError("怪物 %s 的 AC 不合法：%r" % (self.id, self.ac))
        if self.hp < 1:
            raise PluginError("怪物 %s 的 HP 不合法：%r" % (self.id, self.hp))
        if self.cr < 0:
            raise PluginError("怪物 %s 的 CR 不能为负" % self.id)
        if self.size not in SIZES:
            raise PluginError("怪物 %s 的体型必须是 %s" % (self.id, "/".join(SIZES)))
        bad = [key for key in self.speeds if key not in SPEED_KINDS]
        if bad:
            raise PluginError("怪物 %s 的速度类型不认识：%s（可选 %s）"
                              % (self.id, ", ".join(bad), "/".join(SPEED_KINDS)))
        bad = [key for key in self.senses if key not in SENSE_KINDS]
        if bad:
            raise PluginError("怪物 %s 的感官类型不认识：%s（可选 %s）"
                              % (self.id, ", ".join(bad), "/".join(SENSE_KINDS)))
        bad = [key for key in self.saves
               if key not in ("str", "dex", "con", "int", "wis", "cha")]
        if bad:
            raise PluginError("怪物 %s 的豁免加值只能按 str/dex/con/int/wis/cha 写：%s"
                              % (self.id, ", ".join(bad)))
        # 没有动作的怪**允许**存在（剧情里确实有），只是界面上会显示「没有动作」。
        # 不在这里报错：报错会让人以为数据坏了，其实是这一条本来就只会站着。

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "id": self.id,
            "name": self.name.get(locale),
            "size": self.size,
            "ac": int(self.ac),
            "hp": int(self.hp),
            "hp_dice": self.hp_dice,
            "cr": float(self.cr),
            "saves": dict(self.saves),
            "passive_perception": int(self.passive_perception),
            "traits": [row.to_dict(locale) for row in self.traits],
            "actions": [row.to_dict(locale) for row in self.actions],
            "source": self.source,
        }


def parse_monster(data: Any, source: str = "") -> MonsterDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的怪物定义必须是映射" % source)
    for key in ("id", "name", "ac", "hp", "cr", "abilities"):
        if key not in data:
            raise PluginError("%s 的怪物定义缺少 %s（%s）" % (source, key, data.get("id", "?")))
    ident = str(data["id"])
    if not is_valid(ident):
        raise PluginError("怪物 id 不合规范：%r" % ident)
    try:
        abilities = Abilities.of(**{str(key): int(value)
                                    for key, value in data["abilities"].items()})
    except RuleError as exc:
        raise PluginError("%s 的属性不合法：%s" % (ident, exc))

    def actions(key: str) -> tuple[MonsterAttack, ...]:
        rows = data.get(key) or ()
        if isinstance(rows, Mapping):
            rows = [rows]
        return tuple(parse_monster_attack(row, where="%s %s" % (ident, key))
                     for row in rows)

    def traits() -> tuple[MonsterTrait, ...]:
        rows = data.get("traits") or ()
        if isinstance(rows, Mapping):
            rows = [rows]
        return tuple(parse_monster_trait(row, where="%s traits" % ident) for row in rows)

    return MonsterDef(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        ac=int(data["ac"]),
        hp=int(data["hp"]),
        cr=float(data["cr"]),
        abilities=abilities,
        size=str(data.get("size", "medium")).lower(),
        hp_dice=str(data.get("hp_dice", "")),
        speeds={str(k).lower(): int(v)
                for k, v in (data.get("speeds") or {"walk": 30}).items()},
        senses={str(k).lower(): int(v) for k, v in (data.get("senses") or {}).items()},
        passive_perception=int(data.get("passive_perception", 10)),
        saves={str(k).lower(): int(v) for k, v in (data.get("saves") or {}).items()},
        skills={str(k): int(v) for k, v in (data.get("skills") or {}).items()},
        traits=traits(),
        actions=actions("actions"),
        bonus_actions=actions("bonus_actions"),
        reactions=actions("reactions"),
        note=Text.from_dict(data["note"], where="%s note" % ident)
        if data.get("note") else None,
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
    saves = {str(key): int(value) for key, value in (data.get("saves") or {}).items()}
    for key in saves:
        if key not in ABILITY_KEYS:
            raise PluginError("%s 的豁免加值写给了不存在的属性：%r" % (ident, key))

    def rows(key: str) -> tuple[MonsterAttack, ...]:
        raw = data.get(key) or ()
        if isinstance(raw, Mapping):
            raw = [raw]
        return tuple(parse_monster_attack(row, where="%s %s" % (ident, key))
                     for row in raw)

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
        saves=saves,
        traits=tuple(parse_monster_trait(row, where="%s traits" % ident)
                     for row in (data.get("traits") or ())),
        actions=rows("actions"),
        bonus_actions=rows("bonus_actions"),
        reactions=rows("reactions"),
    )
