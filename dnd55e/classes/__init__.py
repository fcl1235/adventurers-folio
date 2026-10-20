# -*- coding: utf-8 -*-
"""职业模块包。

`from dnd55e.classes import get, all_modules` 后即可按 class_id 取模块。
每个模块文件在 import 时用 @registry.register 自注册；本文件按 id 排序导入，
确保注册顺序稳定（无甲防御等单人 hook 依赖它）。
"""
from . import (barbarian, bard, cleric, druid, fighter, monk,  # noqa: F401
               paladin, ranger, rogue, sorcerer, warlock, wizard)
from .base import ClassModule
from .registry import all_modules, get, name_cn, register

__all__ = ["ClassModule", "all_modules", "get", "name_cn", "register"]
