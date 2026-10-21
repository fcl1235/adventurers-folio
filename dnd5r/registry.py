# -*- coding: utf-8 -*-
"""注册表：内容按 id 注册，冲突显式报错，来源可追溯。

覆盖语义（add / replace / patch）在 P5 加载 YAML 时使用，
这里先提供最基础的 add/replace 与 source_of 追溯。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .kernel.errors import PluginError


@dataclass
class Entry:
    kind: str
    id: str
    value: Any
    source: str

    def __repr__(self) -> str:  # pragma: no cover
        return "Entry(%s/%s from %s)" % (self.kind, self.id, self.source)


@dataclass
class Registry:
    _entries: dict[str, dict[str, Entry]] = field(default_factory=dict)

    def register(self, kind: str, ident: str, value: Any, source: str = "", replace: bool = False) -> Entry:
        bucket = self._entries.setdefault(kind, {})
        if ident in bucket and not replace:
            raise PluginError(
                "id 冲突：%s/%s 已由 %s 注册，%s 又想注册；覆盖请显式 replace"
                % (kind, ident, bucket[ident].source or "?", source or "?")
            )
        entry = Entry(kind=kind, id=ident, value=value, source=source)
        bucket[ident] = entry
        return entry

    def get(self, kind: str, ident: str) -> Any:
        bucket = self._entries.get(kind)
        if not bucket or ident not in bucket:
            raise PluginError("未注册：%s/%s" % (kind, ident))
        return bucket[ident].value

    def has(self, kind: str, ident: str) -> bool:
        return ident in self._entries.get(kind, {})

    def ids(self, kind: str) -> tuple[str, ...]:
        return tuple(sorted(self._entries.get(kind, {})))

    def source_of(self, kind: str, ident: str) -> str:
        bucket = self._entries.get(kind, {})
        return bucket[ident].source if ident in bucket else ""

    def extend(self, entries: Iterable[Entry]) -> None:
        for entry in entries:
            self.register(entry.kind, entry.id, entry.value, entry.source)

    def stats(self) -> dict[str, int]:
        return {kind: len(bucket) for kind, bucket in sorted(self._entries.items())}
