# -*- coding: utf-8 -*-
"""法术定义与职业法术表。拆自 P11 之前的 content.py。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..kernel.dice import parse as parse_dice
from ..kernel.dice import stack as stack_dice
from ..kernel.errors import DiceError, PluginError
from ..kernel.ids import is_valid
from ..kernel.text import Text

# --- 法术 -------------------------------------------------------------
SPELL_SCHOOLS = (
    "abjuration", "conjuration", "divination", "enchantment",
    "evocation", "illusion", "necromancy", "transmutation",
)
CAST_KINDS = ("action", "bonus", "reaction", "time", "special")
DURATION_KINDS = ("instant", "time", "permanent", "special")
AREA_SHAPES = ("sphere", "cube", "cone", "cylinder", "line", "emanation")
# 豁免成功后的伤害：半伤 / 无伤。**留空 = 未判定**，见 SpellDef.save_effect。
SAVE_EFFECTS = ("half", "none")


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


def _parse_upcast_dice(data: Any, where: str) -> tuple[str, int]:
    """升环加骰：`{dice: 1d6, above: 3}`（也收裸字符串，环级默认取法术自身环级）。

    这是**会不会算错数**的字段，所以坏数据当场拒绝，不做「猜一个」的兜底。
    """
    if not data:
        return "", 0
    if isinstance(data, str):
        try:
            parse_dice(data)
        except DiceError as exc:
            raise PluginError("%s 的升环骰式不合法：%r（%s）" % (where, data, exc))
        return data, 0
    if not isinstance(data, Mapping):
        raise PluginError("%s 的 upcast_dice 必须是映射或骰式字符串" % where)
    dice = str(data.get("dice") or "")
    if not dice:
        raise PluginError("%s 的 upcast_dice 缺少 dice" % where)
    try:
        parse_dice(dice)
    except DiceError as exc:
        raise PluginError("%s 的升环骰式不合法：%r（%s）" % (where, dice, exc))
    try:
        above = int(data.get("above") or 0)
    except (TypeError, ValueError):
        raise PluginError("%s 的 upcast_dice.above 必须是整数：%r"
                          % (where, data.get("above")))
    return dice, above


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
    # 豁免成功时吃什么：`half` 半伤 / `none` 无伤 / **空串 = 未判定**。
    #
    # 第三种状态不是偷懒。有些法术的 `save` 与 `damage` 是**两件独立的事**：
    # 灼热金属的伤害是接触就吃、豁免只管「能不能拿住」；荆棘丛生的伤害来自移动；
    # 寒冰锥这类「攻击命中 + 另一次豁免爆裂」的法术两条线都有。
    # 把它们一律写成 `none`，结算时会算出规则里不存在的 0 点伤害 ——
    # 比「不知道」更糟，因为它看上去像个答案。
    save_effect: str = ""
    # **必中伤害**（没有攻击、没有豁免，掷下去就是伤害）。
    #
    # 必须内容显式声明，不能从「有伤害骰 + 没有 save/attack」推出来：
    # 那些带「命中后追加」的增益（斩击、诅咒、印记）伤害表里也有骰子，
    # 但它们**不是**「施放即结算」—— 推出来的 `auto` 会在施法瞬间
    # 给目标扣一次根本还没发生的伤害。
    auto_damage: bool = False
    attack: str = ""
    area: tuple[str, int] | None = None
    damage: Mapping[int, str] = field(default_factory=dict)
    damage_type: str = ""
    upcast: str = ""
    # 升环加骰：`upcast_dice` 每提升一环加一次，从 `upcast_above` 环起算。
    #
    # 数据源只给「基础环」的骰式，升环写在英文正文里（"increases by 1d6 for
    # each spell slot level above 3"）。不解析它，用 4 环放火球会算出 8d6 ——
    # 一个不少不多、但就是错的数。解析不出来的（改成「多一道射线」那种）
    # 留空，宁可只给基础骰也不给错的。
    upcast_dice: str = ""
    upcast_above: int = 0
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
        if self.save_effect and self.save_effect not in SAVE_EFFECTS:
            raise PluginError("%s 的 save_effect 必须是 %s（或留空表示未判定）"
                              % (self.id, "/".join(SAVE_EFFECTS)))
        if self.save_effect and not self.save:
            raise PluginError("%s 写了 save_effect 却没写 save" % self.id)
        if self.save_effect and not self.damage:
            raise PluginError("%s 写了 save_effect 却没有伤害骰" % self.id)
        if self.auto_damage:
            if not self.damage:
                raise PluginError("%s 标了 auto_damage 却没有伤害骰" % self.id)
            if self.save or self.attack:
                raise PluginError("%s 标了 auto_damage，不该同时有 save / attack "
                                  "（必中与判定只能二选一）" % self.id)
        for token in self.components:
            if token not in ("v", "s", "m"):
                raise PluginError("%s 的成分只能是 v/s/m：%r" % (self.id, token))
        if self.level == 0 and self.damage and 0 not in self.damage:
            raise PluginError("%s 是戏法，damage 表必须从 0 档开始" % self.id)
        if self.upcast_dice:
            try:
                parse_dice(self.upcast_dice)
            except DiceError as exc:
                raise PluginError("%s 的升环骰式不合法：%r（%s）"
                                  % (self.id, self.upcast_dice, exc))
            if not 0 <= int(self.upcast_above) <= 9:
                raise PluginError("%s 的 upcast_above 必须在 0–9：%r"
                                  % (self.id, self.upcast_above))
            if not self.damage:
                raise PluginError("%s 写了升环骰式却没有基础伤害表" % self.id)
        _check_scaling(self)

    @property
    def is_cantrip(self) -> bool:
        return int(self.level) == 0

    @property
    def is_button(self) -> bool:
        """反应与「1 分钟」类法术不该在战斗回合里当按钮按 —— 界面上仍要列出。"""
        return self.cast_kind in ("action", "bonus")

    def damage_at(self, slot_level: int) -> str:
        """在该环位施放时的伤害骰式；查不到就返回空串（不是 0）。

        表里通常只有基础环，更高的环位靠 `upcast_dice` 叠上去：火球 3 环 8d6、
        4 环 9d6。叠不出来（升环是「多一道射线」这类）就只给基础骰 ——
        少一个骰子还能被玩家看出来，凭空多一个就看不出来了。
        """
        base = lookup_dice(self.damage, int(slot_level))
        if not base or not self.upcast_dice:
            return base
        above = int(slot_level) - int(self.upcast_above or self.level)
        if above <= 0:
            return base
        return stack_dice(base, self.upcast_dice, above)

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
            "save_effect": self.save_effect,
            "auto_damage": self.auto_damage,
            "attack": self.attack,
            "area": None if self.area is None else {"shape": self.area[0], "feet": self.area[1]},
            "damage": {int(key): value for key, value in self.damage.items()},
            "damage_type": self.damage_type,
            "upcast": self.upcast,
            "upcast_dice": ({"dice": self.upcast_dice, "above": int(self.upcast_above)}
                            if self.upcast_dice else None),
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
    upcast_dice, upcast_above = _parse_upcast_dice(data.get("upcast_dice"), ident)
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
        save_effect=str(data.get("save_effect", "")).lower(),
        auto_damage=bool(data.get("auto_damage", False)),
        attack=str(data.get("attack", "")).lower(),
        area=_parse_area(data.get("area"), ident),
        damage=damage,
        damage_type=damage_type,
        upcast=upcast,
        upcast_dice=upcast_dice,
        upcast_above=upcast_above,
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
