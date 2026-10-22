# -*- coding: utf-8 -*-
"""召唤物 stat block 的**可算部分**。

为什么不做成 `FormSpec`（荒野变形那套）：变形形态是**固定数值**（熊就是 AC 11 / HP 34），
召唤物是**法术环级的函数** —— 同一个施法者用 4 环还是 6 环召出来的，是两只强度不同的生物。
固定数值表表达不了这件事，所以这里有两样新东西：

  `Scaling`     base + per_slot × (环级 − from_level)   ← AC / HP 都是这个形状
  `DamagePart`  骰式 + 固定加值 + 每环 +N + 施法属性调整值

**7 种 AC / 15 种 HP 的写法能全部落进 `Scaling`**（"11 + 法术环级" = base 11 / per_slot 1 /
from_level 0；"30 + 5 × 超出 2 级的环级" = base 30 / per_slot 5 / from_level 2），
所以内容里不再出现「11 + 法术环级」这种字符串 —— 字符串没法算，也没法验算。

这个模块只认规则词汇（体型、动作类别、伤害构成），不认任何具体召唤物的名字：
`SummonDef` 在 `content.py`，这里只负责把它的字段算成数值（约束 C1）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..kernel.dice import Die, Dice
from ..kernel.dice import parse as parse_dice
from ..kernel.errors import DiceError, PluginError, RuleError
from ..kernel.text import Text
from ..model.statblock import ABILITY_KEYS

SIZES: tuple[str, ...] = ("tiny", "small", "medium", "large", "huge", "gargantuan")

SPEED_KINDS: tuple[str, ...] = ("walk", "climb", "swim", "fly", "burrow")
SENSE_KINDS: tuple[str, ...] = ("blindsight", "darkvision", "tremorsense", "truesight")

# 一个字面量决定「这条动作怎么读」：要不要掷命中、要不要对面豁免、是不是治疗。
# 不是内容 —— 换一套规则书也还是这几类。
ACTION_KINDS: tuple[str, ...] = (
    "melee", "ranged", "save", "multiattack", "heal", "other",
)
_MAX_SLOT = 9


# --- 随环级变化的数值 ---------------------------------------------------
@dataclass(frozen=True)
class Scaling:
    """`base + per_slot × max(0, 环级 − from_level)`。

    `from_level` 是「从哪一环开始加」：生命值常见「超出 5 级的环级」，
    所以 from_level 写的是**基础环级**，不是 0。AC 那几种都从 0 起算，
    写 0 就等于「每环都加」。
    """

    base: int
    per_slot: int = 0
    from_level: int = 0

    def __post_init__(self) -> None:
        if self.base < 0:
            raise PluginError("基础值不能为负：%r" % (self.base,))
        if self.per_slot < 0:
            raise PluginError("每环增长不能为负（要减就写在 base 上）：%r" % (self.per_slot,))
        if not 0 <= self.from_level <= _MAX_SLOT:
            raise PluginError("from_level 必须在 0–%d：%r" % (_MAX_SLOT, self.from_level))

    def at(self, slot_level: int) -> int:
        slot = int(slot_level)
        if slot < 1:
            # 0 环是戏法，没有「用几环召」这回事 —— 静默返回 base 会给出一个假数。
            raise RuleError("环级至少是 1：%r" % (slot_level,))
        return self.base + self.per_slot * max(0, slot - self.from_level)

    def describe(self) -> str:
        """中文说明。界面显示公式，而不是只显示当前那个数 —— 玩家要知道升环涨多少。"""
        if not self.per_slot:
            return str(self.base)
        if not self.from_level:
            return "%d + %d × 法术环级" % (self.base, self.per_slot)
        return "%d + %d × 超出 %d 级的环级" % (self.base, self.per_slot, self.from_level)

    def to_dict(self) -> dict:
        return {"base": self.base, "per_slot": self.per_slot,
                "from_level": self.from_level, "text": self.describe()}


def parse_scaling(data: Any, where: str = "") -> Scaling:
    """接受 `15` / `{base: 11, per_slot: 1}` 两种写法。"""
    if isinstance(data, bool):
        raise PluginError("%s 的数值不能是布尔" % where)
    if isinstance(data, int):
        return Scaling(base=int(data))
    if not isinstance(data, Mapping):
        raise PluginError("%s 必须是整数或 {base, per_slot, from_level}" % where)
    if "base" not in data:
        raise PluginError("%s 缺少 base" % where)
    try:
        return Scaling(base=int(data["base"]),
                       per_slot=int(data.get("per_slot", 0)),
                       from_level=int(data.get("from_level", 0)))
    except (TypeError, ValueError):
        raise PluginError("%s 的 base/per_slot/from_level 必须是整数" % where)


# --- 伤害构成 -----------------------------------------------------------
@dataclass(frozen=True)
class DamagePart:
    """一段伤害：`骰式 + 固定值 + 每环 +N + 可选施法属性调整值`。

    「1d6 + 4 + the spell's level」→ dice "1d6" / flat 4 / per_slot 1。
    「1d4 + 3 (Medium or smaller)」这种**按体型分叉**的，写成同一条动作下的多个
    `DamagePart`，各自带 `label` —— 分叉是内容的事，不是多一种语法。

    `per_slot_dice` 是「每提升一环再多一颗骰」（活化物件的 1d4/1d6/1d12），
    与 `per_slot`（每环 +N 定值）是两种不同的升环写法，别混用。
    """

    dice: str = ""
    flat: int = 0
    per_slot: int = 0
    caster_mod: bool = False
    per_slot_dice: str = ""
    per_slot_dice_above: int = 0
    damage_type: str = ""
    label: Text | None = None

    def __post_init__(self) -> None:
        if not self.dice and not self.flat and not self.per_slot and not self.caster_mod \
                and not self.per_slot_dice:
            raise PluginError("伤害构成至少要有一项数值")
        if self.per_slot < 0:
            raise PluginError("每环增长不能为负：%r" % (self.per_slot,))
        if self.per_slot_dice and not 1 <= self.per_slot_dice_above <= _MAX_SLOT:
            raise PluginError("per_slot_dice 必须配 per_slot_dice_above（1–%d）"
                              % _MAX_SLOT)
        if self.per_slot_dice_above and not self.per_slot_dice:
            raise PluginError("写了 per_slot_dice_above 却没写 per_slot_dice")
        if self.dice:
            _require_dice(self.dice, "dice")
        if self.per_slot_dice:
            _require_dice(self.per_slot_dice, "per_slot_dice")

    def at(self, slot_level: int, caster_mod: int = 0) -> str:
        """算出这个环级下的骰式（字符串，交给 UI / 掷骰）。"""
        slot = int(slot_level)
        if slot < 1:
            raise RuleError("环级至少是 1：%r" % (slot_level,))
        counts: dict[int, int] = {}
        flat = int(self.flat) + self.per_slot * slot
        if self.caster_mod:
            flat += int(caster_mod)
        if self.dice:
            base = parse_dice(self.dice)
            flat += base.flat
            for die in base.dice:
                counts[die.sides] = counts.get(die.sides, 0) + die.count
        if self.per_slot_dice:
            steps = max(0, slot - self.per_slot_dice_above)
            if steps:
                extra = parse_dice(self.per_slot_dice)
                flat += extra.flat * steps
                for die in extra.dice:
                    counts[die.sides] = counts.get(die.sides, 0) + die.count * steps
        return str(Dice(dice=tuple(Die(count=counts[sides], sides=sides)
                                   for sides in sorted(counts)), flat=flat))

    def to_dict(self, slot_level: int = 0, caster_mod: int = 0) -> dict:
        row = {"type": self.damage_type, "caster_mod": self.caster_mod,
               "label": self.label.to_dict() if self.label else None}
        if slot_level:
            row["at_slot"] = self.at(slot_level, caster_mod)
        return row


def _require_dice(expr: str, field: str) -> None:
    try:
        parse_dice(expr)
    except DiceError as exc:
        raise PluginError("%s 的骰式不合法：%s" % (field, exc))


def parse_damage_part(data: Any, damage_types: Sequence[str],
                      where: str = "") -> DamagePart:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的伤害构成必须是映射" % where)
    known = tuple(damage_types)
    kind = str(data.get("type", "")).lower()
    if kind and kind not in known:
        raise PluginError("%s 的伤害类型不认识：%r（可选 %s）"
                          % (where, kind, "/".join(known)))
    try:
        return DamagePart(
            dice=str(data.get("dice", "")),
            flat=int(data.get("flat", 0)),
            per_slot=int(data.get("per_slot", 0)),
            caster_mod=bool(data.get("caster_mod", False)),
            per_slot_dice=str(data.get("per_slot_dice", "")),
            per_slot_dice_above=int(data.get("per_slot_dice_above", 0)),
            damage_type=kind,
            label=Text.from_dict(data["label"], where="%s label" % where)
            if data.get("label") else None,
        )
    except (TypeError, ValueError):
        raise PluginError("%s 的 flat/per_slot 必须是整数" % where)


# --- 一条特性 / 动作 ----------------------------------------------------
@dataclass(frozen=True)
class SummonAction:
    """traits / actions / bonus_actions / reactions 共用一种形状。

    分三个容器而不是加一个 `slot` 字段：附赠动作与反应在战斗里是**不同的资源**，
    挤进一个列表再按字段过滤，界面迟早会把附赠动作当普通动作列出来。
    """

    name: Text
    kind: str = "other"
    text: Text | None = None
    attack: str = ""
    reach: int = 0
    range: int = 0
    save: str = ""
    save_dc: str = ""
    area: tuple[str, int] | None = None
    damage: tuple[DamagePart, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in ACTION_KINDS:
            raise PluginError("%s 的动作类别必须是 %s"
                              % (self.name.zh, "/".join(ACTION_KINDS)))
        if self.attack and self.attack != "spell":
            raise PluginError("%s 的攻击加值只支持 spell（等于施法者的法术攻击加值）"
                              % self.name.zh)
        if self.save and self.save not in ABILITY_KEYS:
            raise PluginError("%s 的豁免属性不合法：%r" % (self.name.zh, self.save))
        if self.save_dc and self.save_dc != "spell":
            raise PluginError("%s 的豁免 DC 只支持 spell" % self.name.zh)
        if self.save and not self.save_dc:
            raise PluginError("%s 要豁免却没写 save_dc" % self.name.zh)
        if self.kind == "melee" and self.reach < 1:
            raise PluginError("%s 是近战动作，必须写 reach" % self.name.zh)
        if self.kind == "ranged" and self.range < 1:
            raise PluginError("%s 是远程动作，必须写 range" % self.name.zh)
        if self.kind == "save" and not self.save:
            raise PluginError("%s 是豁免动作，必须写 save" % self.name.zh)
        if self.area is not None:
            shape, size = self.area
            if shape not in ("cone", "line", "sphere", "cube", "cylinder") or int(size) < 1:
                raise PluginError("%s 的区域不合法：%r" % (self.name.zh, (self.area,)))

    def to_dict(self, locale: str = "zh", slot_level: int = 0,
                caster_mod: int = 0) -> dict:
        return {
            "name": self.name.get(locale),
            "kind": self.kind,
            "text": self.text.get(locale) if self.text else "",
            "attack": self.attack,
            "reach": self.reach,
            "range": self.range,
            "save": self.save,
            "save_dc": self.save_dc,
            "area": list(self.area) if self.area else None,
            "damage": [part.to_dict(slot_level, caster_mod) for part in self.damage],
        }


def parse_action(data: Any, damage_types: Sequence[str], where: str = "") -> SummonAction:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的动作必须是映射" % where)
    if "name" not in data:
        raise PluginError("%s 的动作缺少 name" % where)
    area = data.get("area")
    parsed_area = None
    if isinstance(area, Mapping):
        parsed_area = (str(area.get("shape", "")), int(area.get("size", 0)))
    elif isinstance(area, (list, tuple)) and len(area) == 2:
        parsed_area = (str(area[0]), int(area[1]))
    elif area:
        raise PluginError("%s 的 area 要写成 {shape, size}" % where)
    rows = data.get("damage") or ()
    if isinstance(rows, Mapping):
        rows = [rows]
    return SummonAction(
        name=Text.from_dict(data["name"], where="%s name" % where),
        kind=str(data.get("kind", "other")).lower(),
        text=Text.from_dict(data["text"], where="%s text" % where)
        if data.get("text") else None,
        attack=str(data.get("attack", "")).lower(),
        reach=int(data.get("reach", 0) or 0),
        range=int(data.get("range", 0) or 0),
        save=str(data.get("save", "")).lower(),
        save_dc=str(data.get("save_dc", "")).lower(),
        area=parsed_area,
        damage=tuple(parse_damage_part(row, damage_types, where=where) for row in rows),
    )


# --- 结算 ---------------------------------------------------------------
def resolve(summon, slot_level: int, caster_mod: int = 0, size: str = "",
            locale: str = "zh") -> dict:
    """把一只召唤物在某个环级下的样子算成一张卡。

    `summon` 只按属性读取（不 import `SummonDef`）：`content.py` 依赖本模块，
    反过来 import 会成环。`size` 只在「同一只召唤物按体型分叉」（活化物件）时才需要。
    """
    slot = int(slot_level)
    if slot < 1:
        raise RuleError("环级至少是 1：%r" % (slot_level,))
    picked = str(size or "").lower()
    if picked and picked not in SIZES:
        raise RuleError("体型不认识：%r（可选 %s）" % (size, "/".join(SIZES)))

    hp: int | None = None
    if getattr(summon, "hp_by_size", None):
        table = summon.hp_by_size
        if not picked:
            # 有体型分叉却不给体型，宁可报错也不猜 —— 猜错就是凭空多一倍的命。
            raise RuleError("%s 的生命值按体型分叉，必须指定体型（可选 %s）"
                            % (summon.id, "/".join(f"{k}={v}" for k, v in table.items())))
        if picked not in table:
            raise RuleError("%s 没有体型 %r 的生命值（可选 %s）"
                            % (summon.id, picked, "/".join(table)))
        hp = int(table[picked])
    if summon.hp is not None:
        hp = summon.hp.at(slot)

    speeds = {}
    locked = {}
    for kind, value in summon.speeds.items():
        need = int((summon.speeds_require_slot or {}).get(kind, 0))
        if need and slot < need:
            # 还没解禁的速度不静默丢弃 —— 界面要能说「飞行 60 尺，4 环起」，
            # 否则低环玩家会以为这只生物压根不会飞。
            locked[kind] = need
            continue
        speeds[kind] = int(value)

    return {
        "id": summon.id,
        "name": summon.name.get(locale),
        "variant": summon.variant.get(locale) if summon.variant else "",
        "spell": summon.spell,
        "slot_level": slot,
        "size": summon.size,
        "size_picked": picked,
        "creature_type": summon.creature_type,
        "ac": summon.ac.at(slot),
        "ac_text": summon.ac.describe(),
        "hp": hp,
        "hp_options": {key: int(value) for key, value in (summon.hp_by_size or {}).items()},
        "hp_text": (summon.hp.describe() if summon.hp is not None
                    else "／".join("%s %d" % (k, v) for k, v in summon.hp_by_size.items())),
        "hp_dice": summon.hp_dice.get(locale) if summon.hp_dice else "",
        "speeds": speeds,
        "speeds_locked": {kind: {"value": int(summon.speeds[kind]), "slot": need}
                          for kind, need in locked.items()},
        "abilities": dict(summon.abilities.scores),
        "senses": dict(summon.senses),
        "passive_perception": int(summon.passive_perception),
        "languages": summon.languages.get(locale),
        "resistances": list(summon.damage_resistances),
        "immunities": list(summon.damage_immunities),
        "condition_immunities": list(summon.condition_immunities),
        "traits": [row.to_dict(locale, slot, caster_mod) for row in summon.traits],
        "actions": [row.to_dict(locale, slot, caster_mod) for row in summon.actions],
        "bonus_actions": [row.to_dict(locale, slot, caster_mod)
                          for row in summon.bonus_actions],
        "reactions": [row.to_dict(locale, slot, caster_mod) for row in summon.reactions],
        "note": summon.note.get(locale) if summon.note else "",
    }


def slot_curve(summon, base_slot: int, locale: str = "zh", caster_mod: int = 0,
               size: str = "") -> list[dict]:
    """从基础环到 9 环的 AC / HP 曲线（界面用来说明「升环会变多强」）。

    `base_slot` 由调用方给（法术自己的环级）—— 召唤物条目里不存这个数，
    存两份必然漂移。
    """
    rows = []
    for slot in range(max(1, int(base_slot)), _MAX_SLOT + 1):
        try:
            card = resolve(summon, slot, caster_mod, size, locale)
        except RuleError:
            continue
        rows.append({"slot": slot, "ac": card["ac"], "hp": card["hp"]})
    return rows
