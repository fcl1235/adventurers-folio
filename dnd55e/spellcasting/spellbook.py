# -*- coding: utf-8 -*-
"""角色模型分片: spellcasting/spellbook.py (由 character.py 物理拆分, P1 纯搬运)。"""


class SpellbookMixin:
    """SpellbookMixin"""

    def mastery_cap(self):
        """18 级法术精通的法术总数: 由职业模块决定"""
        return self.cls_module().mastery_cap(self)

    def signature_cap(self):
        return self.cls_module().signature_cap(self)

    def _wizard_spell_ids(self):
        """法师法术表的 id 集合 (惰性缓存)"""
        ids = getattr(self, "_wiz_ids", None)
        if ids is None:
            ids = {s["id"] for s in self.r.class_spells("wizard")}
            self._wiz_ids = ids
        return ids

    def book_max_level(self):
        """能抄进书的最高环级 = 当前能准备的最高环级"""
        if not self.cls_module().owns_spellbook(self):
            return 0
        return max(self.max_spell_level(), 1)

    def in_book(self, sid):
        """这个法术是否已经抄在法术书里"""
        return bool(sid) and sid in (self.spellbook or [])

    def book_spells(self, lv=None):
        """法术书里的法术 (可只取某一环)"""
        out = []
        for sid in (self.spellbook or []):
            s = self.r.spell(sid)
            if s and (lv is None or s["level"] == lv):
                out.append(s)
        return sorted(out, key=lambda s: (s["level"], s["name"]))

    def can_prepare(self, sid):
        """能否准备: 必须是法师法术, 且已在法术书中"""
        if not self.cls_module().owns_spellbook(self):
            return False
        return self.in_book(sid) and sid in {
            x["id"] for x in self.r.class_spells(self.class_id)}

    def ritual_castable(self, sid):
        """书里的仪式法术可以不准备就直接施放 (额外 10 分钟, 不耗环位)"""
        s = self.r.spell(sid)
        return bool(s) and self.in_book(sid) and bool(s.get("ritual"))

    def copy_cost(self, sid):
        """抄录花费: 50 gp × 环级"""
        s = self.r.spell(sid)
        return 50 * (s["level"] if s else 0)

    def copy_hours(self, sid):
        """抄录耗时: 2 小时 × 环级"""
        s = self.r.spell(sid)
        return 2 * (s["level"] if s else 0)

    def book_add(self, sid, free=False):
        """把法术抄进书 → (ok, msg)。free=True 消耗 1 次免费抄录"""
        s = self.r.spell(sid)
        if not s:
            return False, "法术库里没有这个法术"
        if not self.cls_module().owns_spellbook(self):
            return False, "只有法师拥有法术书"
        if sid not in {x["id"] for x in
                       self.r.class_spells(self.class_id)}:
            return False, f"{s['name']} 不是本职业法术，不能抄进法术书"
        if self.in_book(sid):
            return False, f"{s['name']} 已经在法术书里了"
        if s["level"] < 1:
            return False, "戏法不进法术书，直接会就可以"
        top = self.book_max_level()
        if s["level"] > top:
            return False, f"你目前最高只能把 {top} 环法术抄进书里"
        if free:
            if self.book_pending <= 0:
                return False, "没有可用的免费抄录次数了"
            self.book_pending -= 1
        self.spellbook.append(sid)
        tag = "免费抄录" if free else \
            f"花费 {self.copy_cost(sid)} gp · {self.copy_hours(sid)} 小时抄录"
        return True, f"{s['name']}（{s['level']} 环）已写入法术书 · {tag}"

    def book_remove(self, sid):
        """把法术从书里划掉 → (ok, msg)。正准备中的不能移除"""
        s = self.r.spell(sid)
        name = s["name"] if s else "该法术"
        if not self.in_book(sid):
            return False, f"{name} 不在法术书里"
        if sid in ((self.spells or {}).get("prepared") or []):
            return False, f"{name} 正在准备中，请先在法术页取消准备"
        if sid in self.fixed_spells():
            return False, f"{name} 由职业特性始终准备，不能从书里移除"
        self.spellbook.remove(sid)
        return True, f"{name} 已从法术书移除"

    def book_auto_fill(self):
        """兼容旧存档: 没有 spellbook 字段时, 用已准备的法师法术灌满"""
        if not self.cls_module().owns_spellbook(self):
            self.spellbook = []
            return
        if self.spellbook:
            return
        own = {s["id"] for s in self.r.class_spells(self.class_id)}
        for sid in ((self.spells or {}).get("prepared") or []):
            if sid in own and sid not in self.spellbook:
                self.spellbook.append(sid)

    def _choice_spells(self, raw, min_level, levels, cap, one_per_level=False):
        """校验「自选法术」: 必须是本职业法术、指定环级、数量受限"""
        if not self.cls_module().owns_spellbook(self) \
                or self.level < min_level:
            return []
        own = {s["id"] for s in self.r.class_spells(self.class_id)}
        out, used_lv = [], set()
        for sid in (raw or []):
            if sid in out or sid not in own:
                continue
            s = self.r.spell(sid)
            if not s or s["level"] not in levels:
                continue
            if one_per_level and s["level"] in used_lv:
                continue
            out.append(sid)
            used_lv.add(s["level"])
            if len(out) >= cap:
                break
        return out

    def is_mastery_spell(self, sid):
        return sid in (self.mastery_spells or [])

    def is_signature_spell(self, sid):
        return sid in (self.signature_spells or [])

    def signature_left(self, sid):
        """招牌法术本短休还剩几次免费施放"""
        if not self.is_signature_spell(sid):
            return 0
        return 0 if sid in (self.signature_used or []) else 1
