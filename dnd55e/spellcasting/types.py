# -*- coding: utf-8 -*-
"""施法者类型：法术位的算法按「全施法 / 半施法 / 三分之一施法 / 契约魔法」分四种。

每种一个类，`slots(ch)` 返回该类型在角色当前等级下的法术位表。
卡在 `dnd55e_core_data.json` 的 `classes[].casting.type` 上，新增施法类型
只需在这里加一个类并登记，`_base_slots` 不用改。
"""
from .. import consts


class CastingType:
    """法术位算法基类（不施法时返回空表）。"""

    key = ""

    def slots(self, ch):
        return {}

    def short_rest_recharge(self, ch):
        """短休是否恢复法术位。"""
        return False


class FullCaster(CastingType):
    """全施法者：法师/牧师/德鲁伊/吟游诗人/术士。"""

    key = "full"

    def slots(self, ch):
        return ch.r.full_slots(ch.level)


class HalfCaster(CastingType):
    """半施法者：圣武士/游侠。"""

    key = "half"

    def slots(self, ch):
        return dict(consts.HALF_SLOTS[ch.level])


class ThirdCaster(CastingType):
    """三分之一施法者：奥法骑士/诡术师（借子职表）。"""

    key = "third"

    def slots(self, ch):
        row = ch._third_row()
        return dict(row[2]) if row else {}


class PactCaster(CastingType):
    """契约魔法：邪术师。法术位全部同一环级，短休恢复。

    2024 版：1 级 1 个；2–10 级 2 个；11–16 级 3 个；17 级以上 4 个。
    环级 = min(5, (等级+1)//2)，11/13/15/17 级另加秘契法术位。
    """

    key = "pact"

    def slots(self, ch):
        lv = ch.level
        if lv == 1:
            n = 1
        elif lv >= 17:
            n = 4
        elif lv >= 11:
            n = 3
        else:
            n = 2
        sl = min(5, (lv + 1) // 2)
        out = {sl: n}
        if lv >= 11:
            out[6] = 1     # 秘契法术 Mystic Arcanum
        if lv >= 13:
            out[7] = 1
        if lv >= 15:
            out[8] = 1
        if lv >= 17:
            out[9] = 1
        return out

    def short_rest_recharge(self, ch):
        return True


_TYPES = {}


def _register(cls):
    _TYPES[cls.key] = cls()
    return cls


for _cls in (FullCaster, HalfCaster, ThirdCaster, PactCaster):
    _register(_cls)

_NONE = CastingType()


def of(casting):
    """按 `casting` 配置取算法；没有施法能力时返回空实现。"""
    if not casting:
        return _NONE
    return _TYPES.get(casting.get("type") or "", _NONE)


def keys():
    return sorted(_TYPES)
