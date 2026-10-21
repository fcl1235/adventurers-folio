# -*- coding: utf-8 -*-
"""内核基础设施：无任何规则内容，不认识任何专有名词。"""

from .errors import (
    DndError, RuleError, IllegalAction, PluginError, TextError,
    DiceError, IdError, PredicateError, RngError,
)
from .ids import is_valid, parse as parse_id, join as join_id, tail as tail_id
from .text import Text, Locale, LOCALES
from .rng import Rng, SeededRng, ScriptedRng
from .dice import Dice, Die, RollResult, RollPart, parse as parse_dice, roll_d20
from .predicate import evaluate as eval_when

__all__ = [
    "DndError", "RuleError", "IllegalAction", "PluginError", "TextError",
    "DiceError", "IdError", "PredicateError", "RngError",
    "is_valid", "parse_id", "join_id", "tail_id",
    "Text", "Locale", "LOCALES",
    "Rng", "SeededRng", "ScriptedRng",
    "Dice", "Die", "RollResult", "RollPart", "parse_dice", "roll_d20",
    "eval_when",
]
