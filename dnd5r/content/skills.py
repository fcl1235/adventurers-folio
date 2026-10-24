# -*- coding: utf-8 -*-
"""技能与工具定义（18 项技能 + 37 件工具）。拆自 P11 之前的 content.py。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..kernel.ids import is_valid
from ..kernel.errors import PluginError
from ..kernel.text import Text
from ..model.statblock import ABILITY_KEYS

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
    # 「这些法术用哪个属性施放」—— 2024 魔法入门的原文是「选专长时挑一项」，
    # 不是跟着法术表走。它不加属性值，只决定 DC 与攻击加值。
    "casting_ability": ("str", "dex", "con", "int", "wis", "cha"),
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
