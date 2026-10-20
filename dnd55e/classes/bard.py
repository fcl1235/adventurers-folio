# -*- coding: utf-8 -*-
"""吟游诗人：万事通（半熟练）。"""
from . import registry
from .base import ClassModule


@registry.register("bard")
class Bard(ClassModule):
    name_cn = "吟游诗人"

    def half_proficiency(self, ch):
        """万事通: 未含熟练加值的属性检定 + 半个熟练加值"""
        if ch.level >= 2:
            return ch.pb() // 2
        return 0

    def expertise_allowance(self, ch, level):
        return (2 if level >= 2 else 0) + (2 if level >= 9 else 0)

    def explain(self, ch, phase):
        if phase == "early" and ch.level >= 2:
            return [(171, f"职业·万事通: 非熟练检定 +{ch.pb() // 2}")]
        return []
