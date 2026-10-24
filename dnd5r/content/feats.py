# -*- coding: utf-8 -*-
"""专长定义：静态效果 + 玩家选择项。拆自 P11 之前的 content.py。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..kernel.errors import PluginError
from ..kernel.ids import is_valid
from ..kernel.text import Text
from ..rules.powers import Power, parse_power
from .bestiary import DAMAGE_TYPES
from .resources import ResourceDef, parse_resource
from .skills import CHOICE_UNIVERSE, SKILL_KEYS
from .spells import SPELL_SCHOOLS

# --- 专长 -------------------------------------------------------------
# 专长的「静态部分」直接写成 powers（与职业特性同一套原语），
# 「玩家选择部分」写成 choices —— 选完才知道加成多少，不能在加载期算死。
FEAT_KINDS = ("origin", "general", "fighting_style", "epic_boon")

# 选择项的语义集合。故意封闭：内容里写一个内核不认识的 kind，
# 界面上就会变成一个「选了没反应」的下拉框，比报错难查得多。
CHOICE_KINDS = ("ability_boost", "save", "skill", "expertise", "resistance",
                "spell", "proficiency", "casting_ability")
# `spell_list` 的「不限法术表」哨兵值。2024 版有些专长（妖精触碰一族）说的是
# 「任选一道某学派的 1 环法术」，没有职业限制 —— 硬塞给某张表就是改规则。
SPELL_LIST_ANY = "any"
# 这些 kind 的候选项由内核的全集决定，内容不必也不该重复列举


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
    # 「这道专长的法术用哪个属性施放」。空 = 内容没声明（那就只能靠职业的施法属性）。
    # 特殊值 `boost` = 取本专长 ability_boost 选择项提升的那项属性 ——
    # 妖精触碰/影界触碰的原文就是「施法属性为你以此专长提升的属性」。
    casting_ability: str = ""
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
        if self.casting_ability:
            if self.casting_ability == "boost":
                boosts = [item for item in self.choices if item.kind == "ability_boost"]
                if not boosts or any(int(item.count) != 1 for item in boosts):
                    raise PluginError(
                        "专长 %s 写 casting_ability: boost，就必须有一个「选 1 项属性」的提升项"
                        % self.id)
            elif self.casting_ability == "choose":
                picks = [item for item in self.choices if item.kind == "casting_ability"]
                if not picks:
                    raise PluginError(
                        "专长 %s 写 casting_ability: choose，就必须有一个 casting_ability 选择项"
                        % self.id)
            elif self.casting_ability not in CHOICE_UNIVERSE["casting_ability"]:
                raise PluginError("专长 %s 的 casting_ability 只能是 %s、boost 或 choose：%r"
                                  % (self.id, "/".join(CHOICE_UNIVERSE["casting_ability"]),
                                     self.casting_ability))

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
            "casting_ability": self.casting_ability,
            "resources": [item.to_dict() for item in self.resources],
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
        casting_ability=str(data.get("casting_ability") or "").lower(),
        powers=tuple(
            parse_power(row, owner=ident, source=source)
            for row in (data.get("powers") or ())
        ),
        source=source,
    )
