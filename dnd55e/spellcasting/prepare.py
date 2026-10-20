# -*- coding: utf-8 -*-
"""法术准备：配额、可准备环级、能否准备某道法术。

"这一环能不能准备/能不能学" 委托给 `levels` 子包的按环规则，
升环加成也从那里取 —— 数据仍在 JSON，规则按环拆分在代码里。
"""
from .. import consts
from ..util import (ability_mod)
from . import levels


class PrepareMixin:
    """PrepareMixin"""

    def level_rule(self, spell_or_level):
        """取某一环（或某道法术所属环）的规则对象。

        可以传环级整数、法术字典、法术 id 字符串。
        """
        if isinstance(spell_or_level, dict):
            lv = spell_or_level.get("level", 0)
        elif isinstance(spell_or_level, str):
            lv = (self.r.spell(spell_or_level) or {}).get("level", 0)
        else:
            lv = spell_or_level
        return levels.at(lv)

    def can_learn_spell(self, sid):
        """这道法术现在能否学会/抄录（含按环的特殊规则）。"""
        s = self.r.spell(sid)
        if not s:
            return False
        return self.level_rule(s).can_learn(self, s)

    def can_prepare_spell(self, sid):
        """这道法术现在能否准备（含按环的特殊规则）。"""
        s = self.r.spell(sid)
        if not s:
            return False
        return self.level_rule(s).can_prepare(self, s)

    def upcast_dice(self, sid, slot_level):
        """这道法术用某个环位施放时的升环加成文案。"""
        s = self.r.spell(sid)
        if not s:
            return ""
        return self.level_rule(s).upcast_dice(self, s, slot_level)

    def max_spell_level(self):
        """当前能施放的最高环级 (由普通法术位决定; 秘契法术不算普通法术位)"""
        slots = self.spell_slots()
        arc = set(self.arcanum_levels())
        normal = [lv for lv in slots if lv not in arc]
        return max(normal) if normal else 0

    def learnable_max_level(self):
        """可以「学会/写入」的最高环级 —— 含邪术师秘契 6–9 环"""
        slots = self.spell_slots()
        return max(slots) if slots else 0

    def prepared_count(self):
        """已准备法术数 (秘契法术不占普通准备配额; 固定准备的法术也不占)"""
        lim = self.max_spell_level()
        fixed = set(self.fixed_spells())
        return sum(1 for sid in (self.spells or {}).get("prepared", [])
                   if sid not in fixed
                   and (self.r.spell(sid) or {}).get("level", 0) <= lim)

    def cantrip_cap(self):
        """戏法数量: 用 2024 职业逐级表 (4 级 / 10 级各 +1)"""
        if self.third_caster():
            row = self._third_row()
            cap = int(row[0]) if row else 0
            return cap + (1 if self.order in ("thaumaturge", "magician") else 0)
        tbl = consts.CANTRIPS_KNOWN.get(self.class_id or "")
        if tbl:
            cap = int(tbl.get(self.level, 0))
        else:
            base = consts.SPELL_COUNTS.get(self.class_id, (0, 0))[0]
            if base <= 0:
                return 0
            cap = base + (1 if self.level >= 4 else 0) \
                + (1 if self.level >= 10 else 0)
        # 神圣职阶·施法者 / 原始职阶·魔术师: 额外 1 个戏法
        if self.order in ("thaumaturge", "magician"):
            cap += 1
        return cap

    def prepared_hint(self):
        """准备/已知法术的数量上限 —— 2024 各职业表逐级固定值"""
        if not self.casting():
            return 0
        if self.third_caster():
            row = self._third_row()
            return int(row[1]) if row else 0
        tbl = consts.PREPARED_SPELLS.get(self.class_id or "")
        if tbl:
            return int(tbl.get(self.level, 0))
        return max(1, self.level + ability_mod(self.score(
            self.casting()["ability"])))
