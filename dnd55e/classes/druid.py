# -*- coding: utf-8 -*-
"""德鲁伊：荒野变形、大地结社地形、1 级职阶。"""
from . import registry
from .base import ClassModule


@registry.register("druid")
class Druid(ClassModule):
    name_cn = "德鲁伊"

    def wild_shape_allowed(self, ch):
        return ch.level >= 2

    def explain(self, ch, phase):
        return []
