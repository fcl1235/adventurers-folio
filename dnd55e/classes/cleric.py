# -*- coding: utf-8 -*-
"""牧师：1 级职阶（守护者 / 奇术师）由数据表驱动，这里只留位置。"""
from . import registry
from .base import ClassModule


@registry.register("cleric")
class Cleric(ClassModule):
    name_cn = "牧师"
