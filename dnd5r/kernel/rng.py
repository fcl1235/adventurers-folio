# -*- coding: utf-8 -*-
"""随机源：全项目唯一允许 import random 的地方（约束 C4）。

三种实现覆盖三种场景：
  SeededRng    真随机或固定种子（正常游玩 / 复现 bug）
  ScriptedRng  预设序列（单元测试、剧情回放）
"""

from __future__ import annotations

import random
from typing import Protocol, Sequence, runtime_checkable

from .errors import RngError


@runtime_checkable
class Rng(Protocol):
    def randint(self, low: int, high: int) -> int:
        ...

    def choice(self, seq: Sequence):
        ...


class SeededRng:
    """种子为 None 时取系统熵；给定种子则完全可复现。"""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.seed = seed

    def randint(self, low: int, high: int) -> int:
        if low > high:
            raise RngError("randint 区间非法：%d > %d" % (low, high))
        return self._rng.randint(low, high)

    def choice(self, seq: Sequence):
        if not seq:
            raise RngError("choice 不能用于空序列")
        return self._rng.choice(list(seq))


class ScriptedRng:
    """按顺序吐预设值，耗尽即报错 —— 测试里不允许悄悄回落到真随机。"""

    def __init__(self, values: Sequence[int]) -> None:
        self._values = list(values)
        self._index = 0
        self.requests: list[tuple[int, int]] = []

    def randint(self, low: int, high: int) -> int:
        if self._index >= len(self._values):
            raise RngError("脚本随机序列已耗尽（需要第 %d 个值）" % (self._index + 1))
        value = self._values[self._index]
        self._index += 1
        self.requests.append((low, high))
        if not (low <= value <= high):
            raise RngError("脚本值 %d 不在区间 [%d, %d] 内" % (value, low, high))
        return value

    def choice(self, seq: Sequence):
        if not seq:
            raise RngError("choice 不能用于空序列")
        return seq[self.randint(0, len(seq) - 1) % len(seq)]

    @property
    def remaining(self) -> int:
        return len(self._values) - self._index
