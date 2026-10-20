# -*- coding: utf-8 -*-
"""戏法 (0 环) 规则。

戏法不进法术书、不占准备配额，伤害随**角色等级**在 5/11/17 级各提升一次，
而不是随法术位环级提升 —— 这是它和 1–9 环最大的规则差异。
"""
from . import SpellLevel, register

# 戏法伤害随角色等级提升的台阶
CANTRIP_TIERS = ((17, 4), (11, 3), (5, 2), (1, 1))


@register(0)
class Cantrip(SpellLevel):

    def can_learn(self, ch, spell):
        """戏法只要有戏法配额就能学，与可学最高环级无关。"""
        return ch.cantrip_cap() > 0

    def can_prepare(self, ch, spell):
        """戏法不需要准备 —— 学会了就一直可用。"""
        return True

    def upcast_dice(self, ch, spell, slot_level):
        return ""

    def slot_hint(self, ch, slot_level):
        return "戏法不消耗法术位"

    def tier(self, ch):
        """当前角色等级对应的戏法倍率 (1–4 倍)。"""
        for gate, mult in CANTRIP_TIERS:
            if ch.level >= gate:
                return mult
        return 1

    def scaled_damage(self, ch, spell):
        """戏法的实际伤害骰：把基础骰数乘以倍率。"""
        base = (spell or {}).get("damage") or ""
        if "d" not in base:
            return base
        mult = self.tier(ch)
        if mult <= 1:
            return base
        num, _, rest = base.partition("d")
        try:
            return "%dd%s" % (int(num) * mult, rest)
        except ValueError:
            return base
