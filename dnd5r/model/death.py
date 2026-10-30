# -*- coding: utf-8 -*-
"""死亡豁免记分卡：只存「成功几次 / 失败几次」，判定在 `rules/death.py`。

为什么单独一个类型而不是两个 int 挂在 Actor 上：这两个数是**一对**——
「3 成功」和「3 失败」互斥地终止濒死，拆成两个字段就没人负责保证它们不同时成立。
"""

from __future__ import annotations

from dataclasses import dataclass

# 2024：三次成功稳定，三次失败死亡
STABLE_AT = 3
DEAD_AT = 3


@dataclass
class DeathSaves:
    succeeded: int = 0
    failed: int = 0

    def __post_init__(self) -> None:
        # 夹一次而不是报错：读旧档 / 装备改上限时不该因为一个越界数崩掉整张卡
        self.succeeded = max(0, min(int(self.succeeded), STABLE_AT))
        self.failed = max(0, min(int(self.failed), DEAD_AT))

    @property
    def dead(self) -> bool:
        return self.failed >= DEAD_AT

    @property
    def stable(self) -> bool:
        """稳定：三次成功且没死。已经死了就不叫稳定了。"""
        return not self.dead and self.succeeded >= STABLE_AT

    @property
    def pending(self) -> bool:
        """还在掷：既没稳定也没死。"""
        return not (self.dead or self.stable)

    def add_success(self, count: int = 1) -> None:
        if self.dead:
            return                     # 记满了就不再动，免得「死而复稳」
        self.succeeded = min(STABLE_AT, self.succeeded + int(count))

    def add_failure(self, count: int = 1) -> None:
        if self.stable:
            return
        self.failed = min(DEAD_AT, self.failed + int(count))

    def reset(self) -> None:
        self.succeeded = 0
        self.failed = 0

    def to_dict(self) -> dict:
        return {"succeeded": self.succeeded, "failed": self.failed}

    @classmethod
    def from_dict(cls, data) -> "DeathSaves":
        if not isinstance(data, dict):
            return cls()               # v1 存档没有这一段：当作「没开始掷」
        return cls(succeeded=int(data.get("succeeded") or 0),
                   failed=int(data.get("failed") or 0))
