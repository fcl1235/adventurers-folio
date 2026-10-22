# -*- coding: utf-8 -*-
"""Effect 原语集合（封闭集合，见 §3.3）。

导入本包即完成注册。新增原语的要求：
  1. 有 ≥2 个不同职业的真实用例；
  2. 在本文件里 export；
  3. `tests/unit/test_effects.py` 的契约测试自动覆盖它。
"""

from __future__ import annotations

from .base import (
    Effect,
    EffectContext,
    effect_classes,
    known_ops,
    parse_effect,
    parse_effects,
    register,
)
from .grants import (
    GrantAction,
    GrantAdvantage,
    GrantDefense,
    GrantModifier,
    GrantProficiency,
)
from .morph import Morph, Revert
from .numeric import Damage, GrantTempHp, Heal, ReduceDamage
from .state import (
    ApplyCondition,
    ModifyRoll,
    NoteEffect,
    RecoverResource,
    RemoveCondition,
    SpendResource,
)

__all__ = [
    "Effect", "EffectContext", "register", "parse_effect", "parse_effects",
    "known_ops", "effect_classes",
    "Heal", "Damage", "GrantTempHp", "ReduceDamage", "Morph", "Revert",
    "GrantModifier", "GrantDefense", "GrantProficiency", "GrantAdvantage", "GrantAction",
    "ApplyCondition", "RemoveCondition", "SpendResource", "RecoverResource",
    "ModifyRoll", "NoteEffect",
]
