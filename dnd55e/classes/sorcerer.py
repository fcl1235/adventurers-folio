# -*- coding: utf-8 -*-
"""术士：超魔法、先天魔法、术法源泉、魔法恢复。"""
from . import registry
from .base import ClassModule


@registry.register("sorcerer")
class Sorcerer(ClassModule):
    name_cn = "术士"

    def metamagic_cap(self, ch):
        """已知超魔法上限: 2 级 2 个, 10 级 +2, 17 级 +2"""
        if ch.level < 2:
            return 0
        return 2 + (2 if ch.level >= 10 else 0) + (2 if ch.level >= 17 else 0)

    def innate_cap(self, ch):
        return 2

    def mm_free(self, ch):
        """20 级「奥术神化」: 先天魔法期间, 每回合 1 个超魔法不花术法点"""
        return ch.level >= 20 and bool(ch.innate_active)

    def font_can_use(self, ch):
        return ch.level >= 2

    def sorcerous_rest_ok(self, ch):
        """魔法恢复: 5 级起"""
        return ch.level >= 5

    def pre_slots_state(self, ch, d, to_int):
        """术法源泉换出的临时法术位: 必须在 spell_slots_used 之前读入,
        否则会被当成超出职业表的非法值丢掉。"""
        ch.font_slots = {}
        if ch.level < 2:
            return None
        for k, v in (d.get("font_slots") or {}).items():
            kk = to_int(k, 0, 1, 5)
            vv = to_int(v, 0, 0, 9)
            if kk and vv:
                ch.font_slots[kk] = vv
        return True
