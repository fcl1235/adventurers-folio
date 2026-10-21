# -*- coding: utf-8 -*-
"""角色模型分片: core/resources.py (由 character.py 物理拆分, P1 纯搬运)。"""
from ..util import (ability_mod, roll_dice)


class ResourcesMixin:
    """ResourcesMixin"""

    def resource_max(self, res):
        """资源上限: 表驱动或公式驱动"""
        if res.get("per_day"):
            return 1                    # 每天 1 次的能力 (奥术回想)
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
                "use": res.get("use"), "uses": self.res_uses(res["id"]),
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

    # ---- 「使用 1 次」的自动结算 ----
    def res_uses(self, rid):
        """该资源当前可用的用途按钮 (数据里的 uses, 按等级过滤)"""
        res = next((r for r in self.r.class_resources(self.class_id)
                    if r["id"] == rid), None)
        if res is None:
            return []
        raw = res.get("uses") or ([res["use"]] if res.get("use") else [])
        return [u for u in raw if self.level >= int(u.get("min_level") or 0)]

    def res_use(self, rid, n=1, idx=0):
        """消耗 n 点资源, 并自动结算能用数值表达的收益 (回气回血等)。

        返回 (是否成功, 说明文字)。用途来自数据里的 `uses`;
        没有 uses 的资源只记账, 把 note 当成操作说明返回。
        """
        res = next((r for r in self.r.class_resources(self.class_id)
                    if r["id"] == rid), None)
        if res is None:
            return False, ""
        uses = self.res_uses(rid)
        eff = uses[idx] if idx < len(uses) else (uses[0] if uses else {})
        if eff.get("cost"):
            n = int(eff["cost"])
        mx = self.resource_max(res)
        used = int(self.res_used.get(rid, 0))
        if res.get("formula") == "pact_slots":
            used = int(self.spell_slots_used.get(self.pact_level(), 0))
        if used + n > mx:
            return False, f"{res['name']} 剩余不足（{mx - used}/{mx}）"
        kind = eff.get("type")
        msg = ""
        if kind == "heal":
            expr = str(eff.get("dice") or "1d10").replace("level", str(self.level))
            total, detail = roll_dice(expr)
            before = self.hp_current
            self.hp_current = min(self.hp_max(), before + total)
            msg = (f"{res['name']}：{detail} → "
                   f"HP {before}→{self.hp_current}/{self.hp_max()}")
        elif kind == "heal_pool":
            per = int(eff.get("per_point") or 1)
            heal = n * per
            before = self.hp_current
            self.hp_current = min(self.hp_max(), before + heal)
            msg = (f"{res['name']}：花 {n} 点回 {heal} HP → "
                   f"HP {before}→{self.hp_current}/{self.hp_max()}")
        elif kind == "die":
            die = self._res_die(res) or 6
            total, detail = roll_dice(f"1d{die}")
            msg = f"{res['name']}：灵感骰 {detail}（交给一名队友，d20 失败时加）"
        elif kind == "bonus_die":
            total, detail = roll_dice(str(eff.get("dice") or "1d10"))
            msg = (f"{res['name']}·{eff.get('label')}：{detail}"
                   + (f"（{eff['note']}）" if eff.get("note") else ""))
        elif kind == "note":
            msg = f"{res['name']}·{eff.get('label')}：{eff.get('text', '')}"
        elif kind == "recover_slots":
            msg = f"{res['name']}：" + self._arcane_recover()
        msg = msg or f"{res['name']}：{res.get('note', '')}"
        self.res_spend(rid, n)
        return True, msg

    def _arcane_recover(self):
        """奥术回想: 恢复总环级 ≤ ceil(等级/2) 的法术位, 不含 6 环以上"""
        budget = (self.level + 1) // 2
        slots = self._base_slots()
        got = []
        for lv in sorted(slots, reverse=True):
            if lv > 5:
                continue
            while budget >= lv and int(self.spell_slots_used.get(lv, 0)) > 0:
                self.spell_slots_used[lv] -= 1
                budget -= lv
                got.append(lv)
        if not got:
            return "没有已消耗的 5 环及以下法术位可恢复"
        return ("恢复 " + "、".join(f"{lv} 环 ×{got.count(lv)}"
                                   for lv in sorted(set(got), reverse=True))
                + f"（用掉 {sum(got)}/{(self.level + 1) // 2} 点额度）")

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
