# -*- coding: utf-8 -*-
"""错误类型。分两类：规则错误（用户可修正）与程序错误（插件/数据坏了）。"""


class DndError(Exception):
    """所有本项目异常的基类。"""


class RuleError(DndError):
    """规则层面不成立：数值越界、组合非法。"""


class IllegalAction(RuleError):
    """当前状态下这个动作不能执行（没次数、没动作、条件不满足）。"""


class PluginError(DndError):
    """插件清单、引用或内容不合法。"""


class TextError(DndError):
    """双语文案缺失或不完整。"""


class DiceError(RuleError):
    """骰式无法解析。"""


class IdError(DndError):
    """命名空间 id 不合规范。"""


class PredicateError(RuleError):
    """条件表达式写错（未知比较符、类型不符）。"""


class RngError(DndError):
    """随机源异常：脚本序列耗尽、取值范围不符。"""
