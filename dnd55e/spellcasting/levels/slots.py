# -*- coding: utf-8 -*-
"""1–9 环通用规则。

每一环的差异只在「能不能学/能不能准备」，都由角色的环级上限决定；
升环加成的文案来自 `dnd55e_spells.json` 的 `scaling` 字段（数据不复制成代码）。
"""
from . import SpellLevel, register


class SlotLevel(SpellLevel):
    """1–9 环共用的实现。"""

    def upcast_dice(self, ch, spell, slot_level):
        """升环加成: 从 scaling 表里取当前环级那一档。"""
        sc = (spell or {}).get("scaling") or {}
        if not sc:
            return ""
        return sc.get(str(slot_level), "") or ""

    def max_upcast(self, ch, spell):
        """这道法术最高能升到几环（受角色法术位限制）。"""
        if not spell or spell.get("level", 0) < 1:
            return 0
        slots = ch.spell_slots()
        return max([lv for lv in slots if lv >= spell["level"]] or [0])

    def slot_hint(self, ch, slot_level):
        slots = ch.spell_slots()
        n = slots.get(slot_level, 0)
        return f"{slot_level} 环法术位 {n} 个" if n else ""


# 1–9 环全部登记同一个实现（每个仍是独立的类，便于以后单独覆盖某一环）
def _make(level):
    return register(level)(type("Level%d" % level, (SlotLevel,), {}))


for _lv in range(1, 10):
    _make(_lv)
