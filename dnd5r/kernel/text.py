# -*- coding: utf-8 -*-
"""统一文本值对象：中文与英文都是一等公民（约束 C7）。

内容里不存 i18n key，直接内联两种语言；缺一个都算数据错误。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import TextError

Locale = str
LOCALES: tuple[str, ...] = ("zh", "en")


@dataclass(frozen=True, slots=True)
class Text:
    """一段双语文本。两种语言都必填，不允许空串。"""

    zh: str
    en: str

    def __post_init__(self) -> None:
        for name in LOCALES:
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TextError("Text.%s 必须是字符串，实际为 %r" % (name, type(value).__name__))
            if not value.strip():
                raise TextError("Text.%s 不能为空" % name)

    # --- 构造 ---------------------------------------------------------
    @classmethod
    def of(cls, zh: str, en: str) -> "Text":
        return cls(zh=zh, en=en)

    @classmethod
    def from_dict(cls, data: Any, where: str = "") -> "Text":
        """从 YAML/JSON 的 {zh, en} 构造。字符串或单语映射一律拒绝。"""
        prefix = ("%s: " % where) if where else ""
        if isinstance(data, str):
            raise TextError("%s文案必须写成 {zh: ..., en: ...}，不能只给字符串" % prefix)
        if not isinstance(data, Mapping):
            raise TextError("%s文案必须是映射，实际为 %r" % (prefix, type(data).__name__))
        missing = [name for name in LOCALES if name not in data]
        if missing:
            raise TextError("%s缺少语言 %s" % (prefix, "/".join(missing)))
        return cls(zh=str(data["zh"]), en=str(data["en"]))

    # --- 读取 ---------------------------------------------------------
    def get(self, locale: str = "zh") -> str:
        if locale not in LOCALES:
            raise TextError("未知语言 %r，可选 %s" % (locale, "/".join(LOCALES)))
        return getattr(self, locale)

    def to_dict(self) -> dict:
        return {"zh": self.zh, "en": self.en}

    def __str__(self) -> str:  # 便于日志
        return self.zh
