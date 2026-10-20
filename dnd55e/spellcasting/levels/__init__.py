# -*- coding: utf-8 -*-
"""法术环级规则。

每个环级一个模块，负责这一环「能不能学 / 能不能准备 / 升环加成怎么算」。
法术的**数据**（名称、伤害、描述、职业表）仍然留在 `dnd55e_spells.json`，
这里只放规则，避免把数据复制成代码后与校验链脱节。

新增规则的做法：
    from . import levels
    @levels.register(3)
    class ThirdLevel(levels.SpellLevel):
        def can_learn(self, ch, spell): ...
"""


class SpellLevel:
    """某一环的规则空实现。"""

    level = 0

    def can_learn(self, ch, spell):
        """能否学会/抄录这一环的法术。默认按可学最高环级判断。"""
        return spell["level"] <= ch.learnable_max_level()

    def can_prepare(self, ch, spell):
        """能否准备。默认按可准备最高环级判断。"""
        return spell["level"] <= ch.max_spell_level()

    def upcast_dice(self, ch, spell, slot_level):
        """升环施放的加成描述；没有则为空串。"""
        return ""

    def slot_hint(self, ch, slot_level):
        """这一环法术位的说明（邪术师秘契等特殊处理）。"""
        return ""


class _NullLevel(SpellLevel):
    pass


_NULL = _NullLevel()
_LEVELS = {}


def register(level):
    """装饰器：登记某一环的规则。"""

    def deco(cls):
        cls.level = level
        _LEVELS[level] = cls()
        return cls

    return deco


def at(level):
    """取某一环的规则；未登记时返回空实现。"""
    return _LEVELS.get(int(level or 0), _NULL)


def all_levels():
    """已登记规则的环级（升序）。"""
    return sorted(_LEVELS)


# 导入即注册：戏法规则 + 1–9 环通用规则
from . import cantrip, slots          # noqa: E402,F401
