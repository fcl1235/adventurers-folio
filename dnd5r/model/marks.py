# -*- coding: utf-8 -*-
"""一次性标记：挂上、用掉就没的那种好处。

为什么它既不是 Modifier 也不是 ActiveEffect：

  * **不是 Modifier**：优势不是数值。加进合计会变成「+5」，那是另一条规则。
  * **不是 ActiveEffect**：`grant_advantage` 挂上去就**一直有效**，而
    「本回合结束前下一次攻击优势」有次数、有期限、用完即消。ActiveEffect
    里没有「消费」这个语义，硬塞进去只能靠外部代码到处找它、手动删它。

所以单独一层，只回答三件事：**还有几条、什么时候过期、用掉了没有**。

三种作用域（`expires`）：

  turn   自己的回合结束时清（默认 —— 原文绝大多数写「本回合结束前」）
  round  一轮结束时清（在别人的回合里被挂上的，如队友给的援护）
  never  只能显式移除

**不进存档**：与 `Encounter` / `ActionEconomy` 同一条理由 —— 关掉程序就不该
记得「上一轮那个优势还没用」。`Actor.to_dict()` 里也没有它。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from ..kernel.errors import RuleError

# 标记种类。目前只有「待消费的优势/劣势」与「待消费的额外伤害」两种形状，
# 两者都是「掷骰/命中那一刻才决定要不要用」—— 这正是标记存在的理由。
MARK_KINDS = ("advantage", "extra_damage")
SCOPES = ("turn", "round", "never")


@dataclass
class Mark:
    """挂在角色身上的一条待消费标记。

    `uses` 是「还能用几次」：用掉一次减一，减到 0 就整条移除。
    `id` 与 `source` 一起构成身份：同一来源再挂一次会**替换**旧的那条，
    而不是叠加 —— 用两次月光步也只有一次「下一次攻击优势」。
    """

    id: str
    kind: str = "advantage"
    target: str = "attack.all"
    mode: str = "adv"
    source: str = ""
    label: str = ""
    uses: int = 1
    expires: str = "turn"
    # 额外伤害用这两个字段；优势标记留空
    dice: str = ""
    damage_type: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise RuleError("Mark.id 不能为空")
        if self.kind not in MARK_KINDS:
            raise RuleError("未知标记种类：%r（可选 %s）"
                            % (self.kind, "/".join(MARK_KINDS)))
        if self.mode not in ("adv", "dis"):
            raise RuleError("标记的 mode 只能是 adv 或 dis：%r" % (self.mode,))
        if self.expires not in SCOPES:
            raise RuleError("未知过期作用域：%r（可选 %s）"
                            % (self.expires, "/".join(SCOPES)))
        if int(self.uses) < 1:
            raise RuleError("标记次数必须 >= 1：%r" % (self.uses,))

    @property
    def key(self) -> str:
        return "%s|%s|%s|%s" % (self.kind, self.mode, self.target, self.source)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "target": self.target,
            "mode": self.mode, "source": self.source, "label": self.label,
            "uses": int(self.uses), "expires": self.expires,
            "dice": self.dice, "damage_type": self.damage_type,
        }


@dataclass
class MarkSet:
    """一个角色身上的全部标记 + 本回合的用量记账。

    `spent` 是给「每回合一次」这类**限次通道**用的：它不是标记，没有期限，
    只是「这一回合已经用过没有」的账。放在同一个对象里，是因为它和标记
    共享同一条生命周期 —— 回合结束时一起清。
    """

    items: list[Mark] = field(default_factory=list)
    spent: dict[str, int] = field(default_factory=dict)

    # --- 增删 ---------------------------------------------------------
    def add(self, mark: Mark) -> Mark:
        """同一身份（kind/mode/target/source）再挂一次 = 替换，不叠加次数。"""
        self.items = [item for item in self.items if item.key != mark.key]
        self.items.append(mark)
        return mark

    def active(self) -> list[Mark]:
        return [item for item in self.items if item.uses > 0]

    def matching(self, predicate: Callable[[Mark], bool]) -> list[Mark]:
        return [item for item in self.active() if predicate(item)]

    def consume(self, predicate: Callable[[Mark], bool]) -> list[Mark]:
        """用掉一次：`uses` 减一，减到 0 移除。返回这次真正被消费的标记。

        `predicate` 由规则层给（匹配逻辑要读 `advantage.target_matches`，
        那是 rules 层的东西；model 层不该 import rules）。
        """
        spent: list[Mark] = []
        for item in self.items:
            if item.uses <= 0 or not predicate(item):
                continue
            item.uses -= 1
            spent.append(item)
        self.items = [item for item in self.items if item.uses > 0]
        return spent

    # --- 用量记账 -----------------------------------------------------
    def spend(self, key: str, amount: int = 1) -> None:
        self.spent[key] = int(self.spent.get(key, 0)) + int(amount)

    def spent_on(self, key: str) -> int:
        return int(self.spent.get(key, 0))

    # --- 过期 ---------------------------------------------------------
    def end_turn(self) -> list[Mark]:
        """自己回合结束：清 `turn` 标记与全部用量记账。返回被清掉的标记。"""
        return self._purge(("turn",), clear_spent=True)

    def end_round(self) -> list[Mark]:
        """一轮结束：清 `round` 标记（`never` 保留，`turn` 早在回合末清过了）。"""
        return self._purge(("round",), clear_spent=False)

    def clear(self) -> list[Mark]:
        """全部清空（长休、切换角色、重置遭遇战）。"""
        return self._purge(SCOPES, clear_spent=True)

    def _purge(self, scopes: Iterable[str], clear_spent: bool) -> list[Mark]:
        wanted = set(scopes)
        gone = [item for item in self.items if item.expires in wanted]
        self.items = [item for item in self.items if item.expires not in wanted]
        if clear_spent:
            self.spent.clear()
        return gone

    # --- 输出 ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "spent": dict(self.spent),
        }

    def __len__(self) -> int:
        return len(self.items)


__all__ = ["Mark", "MarkSet", "MARK_KINDS", "SCOPES"]
