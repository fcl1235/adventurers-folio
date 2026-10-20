# -*- coding: utf-8 -*-
"""战士：战斗风格、武器专精、额外攻击（数据表驱动，模块只留说明）。"""
from . import registry
from .base import ClassModule


@registry.register("fighter")
class Fighter(ClassModule):
    name_cn = "战士"
