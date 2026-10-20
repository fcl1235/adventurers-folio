# -*- coding: utf-8 -*-
"""角色模型分片: spellcasting/slots.py (由 character.py 物理拆分, P1 纯搬运)。"""
from .. import consts


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
        c = self.casting()
        if not c:
            return {}
        lv = self.level
        if c["type"] == "full":
            return self.r.full_slots(lv)
        if c["type"] == "half":
            return dict(consts.HALF_SLOTS[lv])
        if c["type"] == "third":          # 奥法骑士 / 诡术师
            row = self._third_row()
            return dict(row[2]) if row else {}
        # pact magic (2024: 1级 1 个; 2–10级 2 个; 11–16级 3 个; 17+ 4 个)
        if lv == 1:
            n = 1
        elif lv >= 17:
            n = 4
        elif lv >= 11:
            n = 3
        else:
            n = 2
        sl = min(5, (lv + 1) // 2)
        slots = {sl: n}
        if lv >= 11:
            slots[6] = 1   # 秘契法术 Mystic Arcanum
        if lv >= 13:
            slots[7] = 1
        if lv >= 15:
            slots[8] = 1
        if lv >= 17:
            slots[9] = 1
        return slots

    def slots_recharge_short_rest(self):
        return bool(self.casting() and self.casting()["type"] == "pact")

    def arcanum_levels(self):
        """秘契法术 (Mystic Arcanum, 邪术师 11/13/15/17 级) —— 1 次/长休,
        不属于契约法术位, 短休不恢复。"""
        c = self.casting()
        if not c or c["type"] != "pact":
            return []
        return [lv for lv in (6, 7, 8, 9) if lv in self.spell_slots()]

    def pact_level(self):
        """契约法术位的环级 (邪术师: 全部法术位都是这个环级)"""
        c = self.casting()
        if not c or c["type"] != "pact":
            return 0
        slots = self.spell_slots()
        normal = [lv for lv in slots if lv not in self.arcanum_levels()]
        return max(normal) if normal else 0
