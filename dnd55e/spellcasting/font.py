# -*- coding: utf-8 -*-
"""角色模型分片: spellcasting/font.py (由 character.py 物理拆分, P1 纯搬运)。"""
from .. import consts


class FontMixin:
    """FontMixin"""

    def font_can_use(self):
        return self.class_id == "sorcerer" and self.level >= 2

    def _sorcery_res(self):
        for res in self.r.class_resources(self.class_id):
            if res["id"] == "sorcery":
                return res

    def sorcery_max(self):
        res = self._sorcery_res()
        return self.resource_max(res) if res else 0

    def sorcery_left(self):
        return max(0, self.sorcery_max() - int(self.res_used.get("sorcery", 0)))

    def font_create_slot(self, level):
        """术法点 → 临时法术位 (长休消失)。返回 (是否成功, 提示)"""
        if not self.font_can_use():
            return False, "只有 2 级以上的术士能用术法源泉。"
        conf = consts.FONT_OF_MAGIC
        level = int(level)
        cost = conf["cost"].get(level)
        if not cost or level > conf["max_slot_level"]:
            return False, f"只能兑换 1–{conf['max_slot_level']} 环的法术位。"
        left = self.sorcery_left()
        if left < cost:
            return False, f"术法点不够：需要 {cost} 点，只剩 {left} 点。"
        self.res_spend("sorcery", cost)
        self.font_slots[level] = self.font_slots.get(level, 0) + 1
        return True, (f"花 {cost} 点术法点，兑换 1 个 {level} 环临时法术位"
                      "（长休消失）。")

    def font_burn_slot(self, level):
        """法术位 → 等量术法点。返回 (是否成功, 提示)"""
        if not self.font_can_use():
            return False, "只有 2 级以上的术士能用术法源泉。"
        level = int(level)
        total = self.spell_slots().get(level, 0)
        if total <= 0:
            return False, f"没有 {level} 环法术位可烧。"
        used = int(self.spell_slots_used.get(level, 0))
        if used >= total:
            return False, f"{level} 环法术位已经用完了。"
        room = int(self.res_used.get("sorcery", 0))     # 最多能补回这么多
        if room <= 0:
            return False, "术法点已满，先花掉一些再来烧法术位。"
        gain = min(level, room)
        # 优先烧普通法术位; 普通位都烧光了才动术法源泉换出来的临时位
        base_n = self._base_slots().get(level, 0)
        if (self.font_slots or {}).get(level) and used >= base_n:
            self.font_slots[level] -= 1
            if self.font_slots[level] <= 0:
                self.font_slots.pop(level, None)
        else:
            self.spell_slots_used[level] = used + 1
        self.res_spend("sorcery", -gain)
        return True, f"烧掉 1 个 {level} 环法术位，回复 {gain} 点术法点。"
