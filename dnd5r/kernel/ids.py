# -*- coding: utf-8 -*-
"""命名空间 id：小写、点分、至少两段。

例：dnd2024.class.second_wind、homebrew.spell.fire_bolt_barrage
"""

from __future__ import annotations

import re

from .errors import IdError

_SEGMENT = re.compile(r"^[a-z][a-z0-9_]*$")
# 插件 id 允许连字符与单段（dnd2024-core、variant-gritty）
_PLUGIN_SEGMENT = re.compile(r"^[a-z][a-z0-9_-]*$")


def parse(ident: str) -> tuple[str, ...]:
    if not isinstance(ident, str):
        raise IdError("id 必须是字符串，实际为 %r" % (type(ident).__name__,))
    parts = tuple(ident.split("."))
    if len(parts) < 2:
        raise IdError("id 至少要有两段：%r" % ident)
    for part in parts:
        if not _SEGMENT.match(part):
            raise IdError("id 段 %r 不合规范（小写字母开头，仅含 a-z0-9_）：%r" % (part, ident))
    return parts


def is_valid(ident: str) -> bool:
    try:
        parse(ident)
    except IdError:
        return False
    return True


def is_plugin_id(ident: str) -> bool:
    """插件 id 比内容 id 宽松：允许单段、允许连字符（dnd2024-core）。"""
    if not isinstance(ident, str) or not ident:
        return False
    return all(_PLUGIN_SEGMENT.match(part) for part in ident.split("."))


def join(*parts: str) -> str:
    return ".".join(parts)


def tail(ident: str) -> str:
    return parse(ident)[-1]


def namespace(ident: str) -> str:
    return parse(ident)[0]
