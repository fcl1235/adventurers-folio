# -*- coding: utf-8 -*-
"""法术位：算法按施法者类型分派（见 `types.py`），这里只做汇总与查询。"""
from . import types


class SlotsMixin:
    """SlotsMixin"""

    def spell_slots(self):
        """返回 {环级: 最大次数} —— 含术法源泉兑换出的临时法术位"""
        slots = self._base_slots()
        if not slots:
            return slots
        for lv, n in (self.font_slots or {}).items():
            if n > 0:
                slots[lv] = slots.get(lv, 0) + n
        return slots

    def _base_slots(self):
        """职业表给的法术位 (不含术法源泉兑换)"""
        return types.of(self.casting()).slots(self)

    def slots_recharge_short_rest(self):
        return types.of(self.casting()).short_rest_recharge(self)

    def arcanum_levels(self):
        """秘契法术 (Mystic Arcanum, 邪术师 11/13/15/17 级) —— 1 次/长休,
        不属于契约法术位, 短休不恢复。"""
        if not types.of(self.casting()).key == "pact":
            return []
        return [lv for lv in (6, 7, 8, 9) if lv in self.spell_slots()]

    def pact_level(self):
        """契约法术位的环级 (邪术师: 全部法术位都是这个环级)"""
        if not types.of(self.casting()).key == "pact":
            return 0
        slots = self.spell_slots()
        normal = [lv for lv in slots if lv not in self.arcanum_levels()]
        return max(normal) if normal else 0
