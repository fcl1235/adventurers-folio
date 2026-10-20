# -*- coding: utf-8 -*-
"""角色模型分片: core/resources.py (由 character.py 物理拆分, P1 纯搬运)。"""
from ..util import (ability_mod)


class ResourcesMixin:
    """ResourcesMixin"""

    def resource_max(self, res):
        """资源上限: 表驱动或公式驱动"""
        tbl = res.get("table")
        if tbl:
            v = tbl.get(str(self.level), tbl.get(self.level))
            return max(0, int(v or 0))
        f = res.get("formula")
        if f == "level":
            return self.level
        if f == "cha_mod_min1":
            return max(1, ability_mod(self.score("CHA")))
        if f == "wis_mod_min1":
            return max(1, ability_mod(self.score("WIS")))
        if f == "5*level":
            return 5 * self.level
        if f == "half_level_ceil":
            return (self.level + 1) // 2
        if f == "pact_slots":
            slots = self.spell_slots()
            return max(slots.values()) if slots else 0
        return 0

    def _res_die(self, res):
        die = res.get("die")
        if not die:
            return None
        best = None
        for k, v in die.items():
            if self.level >= int(k):
                best = v if best is None else max(best, v)
        return best

    def resources(self):
        """当前职业可用的资源池 (按等级过滤, 已含消耗状态)"""
        out = []
        for res in self.r.class_resources(self.class_id):
            if self.level < int(res.get("from_level", 1)):
                continue
            mx = self.resource_max(res)
            if mx <= 0 and not res.get("die"):
                continue
            if res.get("formula") == "pact_slots":
                # 契约法术位与「法术」页共用同一份已用记录, 避免两处计数打架
                used = int(self.spell_slots_used.get(self.pact_level(), 0))
            else:
                used = int(self.res_used.get(res["id"], 0))
            used = max(0, min(mx, used))
            out.append({
                "id": res["id"], "name": res["name"], "icon": res.get("icon", ""),
                "max": mx, "used": used, "left": mx - used,
                "die": self._res_die(res), "note": res.get("note", ""),
                "short": res.get("short", 0), "long": res.get("long", "all"),
                "short_after_level": res.get("short_after_level"),
                "short_after": res.get("short_after"),
            })
        return out

    def res_spend(self, rid, n=1):
        for res in self.r.class_resources(self.class_id):
            if res["id"] != rid:
                continue
            mx = self.resource_max(res)
            if res.get("formula") == "pact_slots":
                lv = self.pact_level()
                cur = int(self.spell_slots_used.get(lv, 0))
                self.spell_slots_used[lv] = max(0, min(mx, cur + n))
                return self.spell_slots_used[lv]
            used = int(self.res_used.get(rid, 0))
            self.res_used[rid] = max(0, min(mx, used + n))
            return self.res_used[rid]
        return 0

    def res_restore(self, rid, n=1):
        return self.res_spend(rid, -n)

    def res_reset(self, rest="long"):
        """短休: 按每条资源的规则恢复; 长休: 清空"""
        if rest == "long":
            self.res_used = {}
            return
        for res in self.r.class_resources(self.class_id):
            rid = res["id"]
            if res.get("formula") == "pact_slots" and res.get("short") == "all":
                self.spell_slots_used.pop(self.pact_level(), None)
                continue
            if rid not in self.res_used:
                continue
            mx = self.resource_max(res)
            if res.get("short") == "all":
                self.res_used[rid] = 0
            elif res.get("short") == 1:
                self.res_used[rid] = max(0, int(self.res_used.get(rid, 0)) - 1)
            # 达到特定等级后短休也全恢复 (如诗人 5 级灵感泉源)
            lvl = res.get("short_after_level")
            if lvl and self.level >= int(lvl) and res.get("short_after") == "all":
                self.res_used[rid] = 0
            self.res_used[rid] = min(mx, self.res_used.get(rid, 0))
