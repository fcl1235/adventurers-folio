# -*- coding: utf-8 -*-
"""角色模型分片: spellcasting/fixed.py (由 character.py 物理拆分, P1 纯搬运)。"""
from .. import consts


class FixedMixin:
    """FixedMixin"""

    def fixed_spells(self):
        """始终准备、不占配额、不可移除的法术 id 列表 (按等级门槛累加)"""
        out = []
        lv = max(int(self.level or 1), 1)
        tbl = consts.FIXED_SPELLS or {}
        for gate, ids in sorted((tbl.get("class") or {}).get(self.class_id or "",
                                                          {}).items()):
            if lv >= gate:
                out.extend(ids)
        sub = (tbl.get("subclass") or {}).get(self.subclass or "")
        if sub:
            rows = (sub.get("land") or {}).get(self.land or "temperate") \
                if sub.get("land") else sub.get("table")
            for gate, ids in sorted((rows or {}).items()):
                if lv >= gate:
                    out.extend(ids)
        # 法师 18/20 级自选的法术也是「始终准备」
        out.extend(self.mastery_spells or [])
        out.extend(self.signature_spells or [])
        return list(dict.fromkeys(out))

    def fixed_source(self, sid):
        """这个法术是「职业固定」还是「子职固定」, 不是则 None"""
        lv = max(int(self.level or 1), 1)
        if sid in (self.mastery_spells or []) or \
                sid in (self.signature_spells or []):
            return "法师"
        tbl = consts.FIXED_SPELLS or {}
        for gate, ids in (tbl.get("class") or {}).get(self.class_id or "", {}).items():
            if lv >= gate and sid in ids:
                return "职业"
        sub = (tbl.get("subclass") or {}).get(self.subclass or "")
        if sub:
            rows = (sub.get("land") or {}).get(self.land or "temperate") \
                if sub.get("land") else sub.get("table")
            for gate, ids in (rows or {}).items():
                if lv >= gate and sid in ids:
                    return "子职"
        return None

    def prune_fixed(self):
        """把已经由特性授予的法术从手动列表里剔掉, 避免重复显示/重复计数"""
        fixed = set(self.fixed_spells())
        for key in ("cantrips", "prepared"):
            mine = (self.spells or {}).get(key) or []
            self.spells[key] = [s for s in mine if s not in fixed]

    def land_options(self):
        """大地结社的四种地形"""
        return [("arid", "干旱 Arid"), ("polar", "极地 Polar"),
                ("temperate", "温带 Temperate"), ("tropical", "热带 Tropical")]

    def land_label(self):
        if not self.land:
            return ""
        return dict(self.land_options()).get(self.land, self.land)
