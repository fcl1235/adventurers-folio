# -*- coding: utf-8 -*-
"""角色模型分片: core/combat/offhand.py (由 character.py 物理拆分, P1 纯搬运)。"""
from ... import consts
from ...util import (ability_mod)


class OffhandMixin:
    """OffhandMixin"""

    def offhand_entry(self):
        return next((w for w in consts.WEAPONS if w[0] == self.offhand_weapon),
                    None)

    def has_dual_wielder(self):
        return self.has_feat("Dual Wielder", "双武器大师")

    def offhand_can_dual(self):
        """2024 Light: 两把都是轻型武器。
        「双武器大师」放宽为「两把都不是双手/两用武器」"""
        main, off = self.weapon, self.offhand_weapon
        if not main or not off:
            return False
        light = set(consts.LIGHT_WEAPONS)
        if main in light and off in light:
            return True
        if not self.has_dual_wielder():
            return False
        bad = {"two_handed", "versatile"}
        return not (set(self.weapon_props(main)) & bad
                    or set(self.weapon_props(off)) & bad)

    def offhand_ability(self):
        w = self.offhand_entry()
        if not w:
            return "STR"
        props = self.weapon_props(w[0])
        if "finesse" in props or w[0] in consts.FINESSSE_SET:
            return "DEX" if self.score("DEX") > self.score("STR") else "STR"
        return "STR"

    def offhand_attack_bonus(self):
        w = self.offhand_entry()
        if not w or not self.offhand_can_dual():
            return 0
        pb = self.pb() if self.has_weapon_prof(w[0]) else 0
        return (ability_mod(self.score(self.offhand_ability())) + pb
                - self.exh_penalty())

    def offhand_damage_dice(self):
        w = self.offhand_entry()
        return w[2].split(" ")[0] if w else ""

    def offhand_damage_type(self):
        w = self.offhand_entry()
        if not w:
            return ""
        parts = w[2].split(" ")
        return parts[1] if len(parts) > 1 else ""

    def offhand_damage_bonus(self):
        """2024: 副手攻击伤害不加属性调整值 (负值照加);
        有「双武器战斗」战斗风格才加"""
        w = self.offhand_entry()
        if not w or not self.offhand_can_dual():
            return 0
        m = ability_mod(self.score(self.offhand_ability()))
        extra = m if self.fighting_style == "two_weapon" else min(0, m)
        extra += self.cls_module().damage_bonus_extra(
            self, self.offhand_ability(), False)
        return extra

    def offhand_note(self):
        """副手不可用时的原因, 可用则返回空串"""
        if not self.offhand_weapon:
            return ""
        if not self.offhand_can_dual():
            if self.has_dual_wielder():
                return "双武器大师也要求两把都不是双手/两用武器"
            return "副手必须与主手同为轻型武器（或选「双武器大师」专长）"
        return ""
