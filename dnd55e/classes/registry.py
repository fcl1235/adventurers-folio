# -*- coding: utf-8 -*-
"""职业模块注册表。

`get(class_id)` 永远返回一个可用的模块对象（未注册时返回空实现），
所以调用方不需要写 `if module is None`。
"""
from .base import ClassModule


class _NullModule(ClassModule):
    """未知/未选择职业时的空实现。"""

    class_id = ""
    name_cn = ""


_MODULES = {}
_NULL = _NullModule()


def register(class_id):
    """装饰器：把职业模块类登记到表里。"""

    def deco(cls):
        cls.class_id = class_id
        _MODULES[class_id] = cls()
        return cls

    return deco


def get(class_id):
    """按职业 id 取模块实例；未知 id 返回空实现。"""
    if not class_id:
        return _NULL
    return _MODULES.get(class_id) or _NULL


def all_modules():
    """按注册顺序返回全部模块（顺序决定无甲防御等单人 hook 的优先级）。"""
    return list(_MODULES.values())


def name_cn(class_id):
    """职业中文名，取不到时回退到空串。"""
    return get(class_id).name_cn
