# -*- coding: utf-8 -*-
"""状态集合。只存「有哪些状态」，时长与到期由 rules 层按相位推进。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConditionSet:
    _ids: set[str] = field(default_factory=set)

    def add(self, condition_id: str) -> None:
        self._ids.add(condition_id)

    def remove(self, condition_id: str) -> bool:
        if condition_id in self._ids:
            self._ids.discard(condition_id)
            return True
        return False

    def has(self, condition_id: str) -> bool:
        return condition_id in self._ids

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._ids))

    def clear(self) -> None:
        self._ids.clear()

    def __len__(self) -> int:
        return len(self._ids)

    def to_dict(self) -> list[str]:
        return list(self.ids())

    @classmethod
    def from_dict(cls, rows) -> "ConditionSet":
        return cls(_ids=set(str(x) for x in (rows or ())))
