# -*- coding: utf-8 -*-
"""角色模型分片: spellcasting/metamagic.py (由 character.py 物理拆分, P1 纯搬运)。"""
from .. import consts


class MetamagicMixin:
    """MetamagicMixin"""

    def metamagic_cap(self):
        """已知超魔法上限: 2 级 2 个, 10 级 +2, 17 级 +2"""
        if self.class_id != "sorcerer" or self.level < 2:
            return 0
        return 2 + (2 if self.level >= 10 else 0) + (2 if self.level >= 17 else 0)

    def metamagic_known(self):
        return [m for m in self.metamagic if m in consts.METAMAGIC][
            :self.metamagic_cap()]

    def metamagic_per_spell(self):
        """一道法术能叠几个: 默认 1; 7 级「魔法化身」先天魔法期间 2"""
        if self.level >= 7 and self.innate_active:
            return 2
        return 1

    def mm_free(self):
        """20 级「奥术神化」: 先天魔法期间, 每回合 1 个超魔法不花术法点"""
        return (self.class_id == "sorcerer" and self.level >= 20
                and self.innate_active)

    def mm_cost(self, ids):
        return sum(consts.METAMAGIC[m][1] for m in dict.fromkeys(ids)
                   if m in consts.METAMAGIC)

    def mm_validate(self, ids):
        """返回 (是否可行, 原因, 实际花费)"""
        ids = [m for m in dict.fromkeys(ids) if m in consts.METAMAGIC]
        if not ids:
            return True, "", 0
        known = set(self.metamagic_known())
        for m in ids:
            if m not in known:
                return False, f"未学会「{consts.METAMAGIC[m][0]}」", 0
        main = [m for m in ids if not consts.METAMAGIC[m][3]]
        if len(main) > self.metamagic_per_spell():
            return False, ("一道法术最多只能应用 "
                           f"{self.metamagic_per_spell()} 个超魔法"
                           "（强化/探秘可与其他叠加）"), 0
        cost = self.mm_cost(ids)
        if self.mm_free():          # 免费的那一个按最贵的一项抵扣
            cost -= max(consts.METAMAGIC[m][1] for m in ids)
        cost = max(0, cost)
        if cost > self.sorcery_left():
            return False, (f"术法点不够：这套组合要 {cost} 点，"
                           f"只剩 {self.sorcery_left()} 点"), 0
        return True, "", cost

    def mm_apply(self, ids):
        """扣术法点, 返回 (成功, 日志文案)"""
        ids = [m for m in dict.fromkeys(ids) if m in consts.METAMAGIC]
        ok, why, cost = self.mm_validate(ids)
        if not ok:
            return False, why
        if not ids:
            return True, ""
        raw = self.mm_cost(ids)
        if cost:
            self.res_spend("sorcery", cost)
        names = "＋".join(consts.METAMAGIC[m][0].split(" ")[0] for m in ids)
        saved = f"（奥术神化省下 {raw - cost} 点）" if raw > cost else ""
        spent = f"花 {cost} 点术法点" if cost else "未花术法点"
        return True, f"超魔法 {names}{saved} · {spent}"

    def innate_cap(self):
        return 2 if self.class_id == "sorcerer" else 0

    def innate_left(self):
        return max(0, self.innate_cap() - int(self.innate_used))

    def innate_on(self):
        """开启先天魔法; 次数用完时 7 级起可花 2 点术法点顶上"""
        if self.innate_cap() == 0:
            return False, "只有术士有先天魔法。"
        if self.innate_active:
            return True, ""
        if self.innate_left() > 0:
            self.innate_used += 1
        elif self.level >= 7 and self.sorcery_left() >= 2:
            self.res_spend("sorcery", 2)
        else:
            return False, "先天魔法的次数用完了（长休恢复 2 次）。"
        self.innate_active = True
        return True, ""

    def innate_off(self):
        self.innate_active = False

    def sorcerous_rest(self):
        """术士 5 级「魔法恢复」: 短休回一半术法点 (向下取整), 1 次/长休"""
        if self.class_id != "sorcerer" or self.level < 5:
            return False, ""
        if self.sorcerous_rest_used:
            return False, "「魔法恢复」本次长休已用过"
        spent = int(self.res_used.get("sorcery", 0))
        if spent <= 0:
            return False, ""
        gain = min(spent, self.level // 2)
        self.res_used["sorcery"] = spent - gain
        self.sorcerous_rest_used = True
        return True, f"魔法恢复：术法点 +{gain}"
