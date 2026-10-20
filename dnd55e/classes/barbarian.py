# -*- coding: utf-8 -*-
"""野蛮人：无甲防御、快速移动、狂暴伤害、不屈之力、20 级压轴。"""
from . import registry
from .base import ClassModule
from ..util import ability_mod


@registry.register("barbarian")
class Barbarian(ClassModule):
    name_cn = "野蛮人"

    def can_rage(self, ch):
        return True

    def ability_cap(self, ch, ab):
        if ch.level >= 20 and ab in ("STR", "CON"):
            return 25
        return 20

    def capstone_bonus(self, ch, ab):
        if ch.level >= 20 and ab in ("STR", "CON"):
            return 4
        return 0

    def unarmored_ac(self, ch, dex_mod):
        return (10 + dex_mod + ability_mod(ch.score("CON")),
                "无甲防御(野蛮人) 10+敏捷+体质")

    def speed_bonus(self, ch):
        if ch.level < 5:
            return 0
        if ch.armor_cat() == "heavy":
            return 0
        return 10

    def indomitable_might(self, ch, ab):
        return ch.level >= 18 and ab == "STR"

    def damage_bonus_extra(self, ch, ability, two_handed):
        # 狂暴伤害只加在「用力量」的攻击上 (2024 Rage)
        if ch.raging and ability == "STR":
            return ch.rage_damage()
        return 0

    def explain(self, ch, phase):
        out = []
        if phase == "early":
            if ch.level >= 5:
                out.append((150, "职业·快速移动: 速度 +10 尺"))
            if ch.level >= 18:
                out.append((166, f"职业·不屈之力: 力量检定/豁免总值不低于力量值 "
                                 f"{ch.score('STR')}"))
            if ch.level >= 20:
                out.append((169, "职业·20级压轴: 力量与体质 / 敏捷与感知 各 +4（上限 25）"))
        else:
            if ch.level >= 1:
                rd = ch.rage_damage()
                if ch.raging:
                    out.append((218, f"职业·狂暴(进行中): 伤害 +{rd} 已计入 · "
                                     "物理伤害抗性 · 力量检定/豁免优势 · 不能专注"))
                else:
                    out.append((218, f"职业·狂暴: 伤害 +{rd}，物理伤害抗性 "
                                     "（在「职业」页点开狂暴后再算）"))
        return out
