# -*- coding: utf-8 -*-
"""邪术师：契约法术位与秘契法术由数据表驱动，模块留位置。"""
from . import registry
from .base import ClassModule


@registry.register("warlock")
class Warlock(ClassModule):
    name_cn = "邪术师"
