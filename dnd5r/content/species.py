# -*- coding: utf-8 -*-
"""物种（2024 把「种族」改叫物种，规则上不再附带属性加值）。

特性走**与职业特性完全同一套原语**（`Power` + effects），所以黑暗视觉、
伤害抗性、每级 HP +1 都不用另造机制 —— 直接复用 `sense.*` / `grant_defense` /
`hp.per_level` 那三条通道。这是 P6 最重要的取舍：另造一套「物种特性 DSL」
等于让 `build_actor` 里出现第二条装配路径，两条路径迟早对不上。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..kernel.errors import PluginError
from ..kernel.text import Text
from ..rules.powers import Power, parse_power

# 2024 只有这两种体积；Small 与 Medium 的差别只在「能骑什么 / 能穿什么」
SIZES = ("tiny", "small", "medium", "large")


@dataclass(frozen=True)
class SpeciesDef:
    id: str
    name: Text
    summary: Text
    size: tuple[str, ...] = ("medium",)
    speed: int = 30
    powers: tuple[Power, ...] = ()
    # 来源（插件内的相对路径）。与其它内容定义同一个口径：追溯比「好看」重要。
    source: str = ""

    @property
    def trait_names(self) -> tuple[Text, ...]:
        return tuple(power.name for power in self.powers)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name.to_dict(),
            "summary": self.summary.to_dict(),
            "size": list(self.size),
            "speed": self.speed,
            "powers": [power.id for power in self.powers],
            "source": self.source,
        }


def parse_species(data, source: str = "") -> SpeciesDef:
    if not isinstance(data, dict):
        raise PluginError("%s 的物种定义必须是映射" % source)
    for key in ("id", "name"):
        if key not in data:
            raise PluginError("%s 的物种定义缺少 %s（source=%s）" % (key, source))
    ident = str(data["id"])
    sizes = tuple(str(item).lower() for item in (data.get("size") or ("medium",)))
    bad = [item for item in sizes if item not in SIZES]
    if bad:
        raise PluginError("%s 的体积未知：%s" % (ident, ", ".join(bad)))
    try:
        speed = int(data.get("speed", 30))
    except (TypeError, ValueError):
        raise PluginError("%s 的速度必须是整数：%r" % (ident, data.get("speed")))
    if speed <= 0:
        raise PluginError("%s 的速度必须为正：%d" % (ident, speed))
    powers = tuple(
        parse_power(item, owner=ident, source=source) for item in (data.get("powers") or ())
    )
    return SpeciesDef(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        summary=Text.from_dict(data.get("summary") or data["name"],
                               where="%s summary" % ident),
        size=sizes,
        speed=speed,
        powers=powers,
        source=source,
    )
