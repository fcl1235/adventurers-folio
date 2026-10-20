# -*- coding: utf-8 -*-
"""圣武士：守护灵光、至圣斩。"""
from . import registry
from .base import ClassModule
from ..util import ability_mod


@registry.register("paladin")
class Paladin(ClassModule):
    name_cn = "圣武士"

    def save_bonus(self, ch, ab):
        """守护灵光 (6 级): 魅力调整值, 最低 +1"""
        if ch.level >= 6:
            return max(1, ability_mod(ch.score("CHA")))
        return 0

    def explain(self, ch, phase):
        out = []
        if phase == "early" and ch.level >= 6:
            out.append((157, f"职业·守护灵光(10尺): 豁免 "
                             f"+{max(1, ability_mod(ch.score('CHA')))} (魅力, 最低 +1)"))
        if phase == "late" and ch.level >= 2:
            out.append((234, "职业·至圣斩: 命中后可用法术位追加 2d8 光耀 (每击一次)"))
        return out
