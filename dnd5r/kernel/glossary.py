# -*- coding: utf-8 -*-
"""术语表：同一概念在中文里不许出现两种译名。

只做一件事 —— 扫描中文文案里有没有「禁用变体」，例如把「敏捷豁免」写成「敏捷检定」。
这类错误不会让程序崩，只会让规则悄悄错，所以必须进 CI。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .errors import PluginError
from .text import Text


@dataclass(frozen=True, slots=True)
class Term:
    key: str
    zh: str
    en: str
    forbid_zh: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, key: str, data: Mapping) -> "Term":
        if "zh" not in data or "en" not in data:
            raise PluginError("术语 %s 必须同时有 zh 与 en" % key)
        forbid = data.get("forbid_zh") or ()
        if isinstance(forbid, str):
            forbid = (forbid,)
        return cls(
            key=key,
            zh=str(data["zh"]),
            en=str(data["en"]),
            forbid_zh=tuple(str(x) for x in forbid),
        )


@dataclass
class Glossary:
    terms: dict[str, Term] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Mapping]) -> "Glossary":
        if not isinstance(data, Mapping):
            raise PluginError("术语表必须是映射")
        return cls({key: Term.from_dict(key, value) for key, value in data.items()})

    def lint(self, text: Text, where: str = "") -> list[str]:
        """返回问题列表；空列表代表通过。"""
        issues: list[str] = []
        for term in self.terms.values():
            for bad in term.forbid_zh:
                if bad and bad in text.zh:
                    issues.append(
                        "%s 用了「%s」，应为「%s」（%s）" % (where or "文案", bad, term.zh, term.key)
                    )
        return issues

    def lint_many(self, items: Iterable[tuple[Text, str]]) -> list[str]:
        issues: list[str] = []
        for text, where in items:
            issues.extend(self.lint(text, where))
        return issues
