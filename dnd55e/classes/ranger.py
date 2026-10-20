# -*- coding: utf-8 -*-
"""游侠：游荡（速度 +10）、专精。"""
from . import registry
from .base import ClassModule


@registry.register("ranger")
class Ranger(ClassModule):
    name_cn = "游侠"

    def expertise_allowance(self, ch, level):
        return (1 if level >= 2 else 0) + (2 if level >= 9 else 0)

    def speed_bonus(self, ch):
        """游荡 Roving (6 级, 非重甲): 速度 +10"""
        if ch.level >= 6 and ch.armor_cat() != "heavy":
            return 10
        return 0

    def explain(self, ch, phase):
        if phase == "early" and ch.level >= 6 and ch.armor_cat() != "heavy":
            return [(152, f"职业·游荡: 速度 +10 尺，攀爬/游泳速度 = {ch.speed()} 尺")]
        return []
