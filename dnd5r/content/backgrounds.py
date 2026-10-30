# -*- coding: utf-8 -*-
"""背景：三项属性、起始专长、两项技能、一件工具。

2024 的属性加值**跟着背景走**（不再跟物种），所以背景是「+2/+1 或 +1/+1/+1」
这个选择的来源。加值本身是玩家的选择（选哪两项、怎么分），这里只提供候选与规则，
选择结果由 `rules/abilities.background_bonus()` 算，装配在 `build_actor` 里。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..kernel.errors import PluginError
from ..kernel.text import Text
from ..model.statblock import ABILITY_KEYS

# 背景给的加值上限（2024：单项最高 20，与属性值上限一致）
BACKGROUND_ABILITY_COUNT = 3


@dataclass(frozen=True)
class BackgroundDef:
    id: str
    name: Text
    summary: Text
    abilities: tuple[str, ...] = ()
    origin_feat: str = ""
    skills: tuple[str, ...] = ()
    # 工具熟练：`tool` 是插件里的工具 key（"thieves_tools"），空串 = 这一类要玩家自选
    # 具体物件（"工匠工具"），不登记固定 token。`tool_label` 永远有值，卡上照它显示。
    tool: str = ""
    tool_label: "Text | None" = None
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name.to_dict(),
            "summary": self.summary.to_dict(),
            "abilities": list(self.abilities),
            "origin_feat": self.origin_feat,
            "skills": list(self.skills),
            "tool": self.tool,
            "tool_label": None if self.tool_label is None else self.tool_label.to_dict(),
            "source": self.source,
        }


def parse_background(data, source: str = "") -> BackgroundDef:
    if not isinstance(data, dict):
        raise PluginError("%s 的背景定义必须是映射" % source)
    for key in ("id", "name"):
        if key not in data:
            raise PluginError("%s 的背景定义缺少 %s（source=%s）" % (key, source))
    ident = str(data["id"])
    abilities = tuple(str(item).lower() for item in (data.get("abilities") or ()))
    if len(abilities) != BACKGROUND_ABILITY_COUNT:
        raise PluginError("%s 的背景必须给 %d 项属性，实际 %d 项"
                          % (ident, BACKGROUND_ABILITY_COUNT, len(abilities)))
    bad = [item for item in abilities if item not in ABILITY_KEYS]
    if bad:
        raise PluginError("%s 的背景属性未知：%s" % (ident, ", ".join(bad)))
    if len(set(abilities)) != len(abilities):
        raise PluginError("%s 的背景属性重复：%s" % (ident, ", ".join(abilities)))
    tool = str(data.get("tool") or "")
    label = data.get("tool_label")
    return BackgroundDef(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        summary=Text.from_dict(data.get("summary") or data["name"],
                               where="%s summary" % ident),
        abilities=abilities,
        origin_feat=str(data.get("origin_feat") or ""),
        skills=tuple(str(item) for item in (data.get("skills") or ())),
        tool=tool,
        # 标签缺省就退回工具 key —— 卡上出现一个看不出问题的空格比露个 key 更糟
        tool_label=Text.from_dict(label, where="%s tool_label" % ident) if label
        else (Text.from_dict({"zh": tool, "en": tool}, where="%s tool" % ident) if tool else None),
        source=source,
    )
