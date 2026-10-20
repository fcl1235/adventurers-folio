# -*- coding: utf-8 -*-
"""武僧：无甲防御、武艺、无甲移动、自律生还者、20 级压轴。"""
from . import registry
from .base import ClassModule
from ..consts import ABILITIES
from ..util import ability_mod


@registry.register("monk")
class Monk(ClassModule):
    name_cn = "武僧"

    def ability_cap(self, ch, ab):
        if ch.level >= 20 and ab in ("DEX", "WIS"):
            return 25
        return 20

    def capstone_bonus(self, ch, ab):
        if ch.level >= 20 and ab in ("DEX", "WIS"):
            return 4
        return 0

    def unarmored_ac(self, ch, dex_mod):
        if ch.shield:
            return None
        return (10 + dex_mod + ability_mod(ch.score("WIS")),
                "无甲防御(武僧) 10+敏捷+感知")

    def speed_bonus(self, ch):
        if ch.level < 2 or ch.armor_cat() is not None or ch.shield:
            return 0
        if ch.level >= 18:
            return 30
        if ch.level >= 14:
            return 25
        if ch.level >= 10:
            return 20
        if ch.level >= 6:
            return 15
        return 10

    def save_profs_extra(self, ch):
        return set(ABILITIES) if ch.level >= 14 else set()

    def weapon_ability_override(self, ch, name, props):
        """2024 武艺: 熟练的近战武器也可用敏捷"""
        if ch.level >= 1 and ch.has_weapon_prof(name):
            return "DEX" if ch.score("DEX") >= ch.score("STR") else "STR"
        return None

    def unarmed_ability(self, ch):
        if ch.level >= 1:
            return "DEX" if ch.score("DEX") > ch.score("STR") else "STR"
        return None

    def unarmed_die(self, ch):
        return ch.class_stat("martial_arts_die", 0) or 4

    def martial_arts_die(self, ch):
        return int(ch.class_stat("martial_arts_die", 0) or 0)

    def explain(self, ch, phase):
        out = []
        if phase == "early":
            if ch.level >= 2:
                out.append((155, "职业·无甲移动: 速度提升"))
            if ch.level >= 14:
                out.append((160, "职业·自律生还者: 全部豁免熟练；失败可花 1 气点重掷"))
            if ch.level >= 20:
                out.append((169, "职业·20级压轴: 力量与体质 / 敏捷与感知 各 +4（上限 25）"))
        else:
            if ch.level >= 1:
                d = ch.class_stat("martial_arts_die", 0)
                out.append((230, f"职业·武艺: 徒手/武僧武器伤害骰 "
                                 f"{('1d%d' % d) if d else '1d4'}（附赠动作可再攻击 1 次）"))
        return out
