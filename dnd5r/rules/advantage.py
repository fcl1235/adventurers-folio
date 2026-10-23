# -*- coding: utf-8 -*-
"""优势 / 劣势：把角色身上挂的标记，变成 d20 的掷骰模式。

内容侧只有一种写法：`grant_advantage: {target: save.dex, mode: adv}`，
它把一条 `advantage.adv.save.dex` 标记挂到角色身上。这里负责反查：

  「这一次敏捷豁免，他身上有几条优势、几条劣势？」

  - **精确匹配**：`save.dex` 只对敏捷豁免生效
  - **父级覆盖**：`check.all` 覆盖一切属性检定，`save.all` 覆盖一切豁免
  - **抵消**：同时有优势和劣势 → 回到平掷（2024 规则，不是「优势优先」）

为什么优势不做成 Modifier：它不是数值，是**掷骰形状**。加进合计会变成「+5」，
那是另一条规则（而且会悄悄错）。所以它只能挂在 Resolution 上往下传。
"""

from __future__ import annotations

from typing import Iterable

from ..model.marks import MarkSet

FLAT = "flat"
ADV = "adv"
DIS = "dis"
MODES = (FLAT, ADV, DIS)
PREFIX = "advantage."

# 层级：查询目标可以往上一级找「全体」标记
_PARENT = {
    "check": "check.all",
    "save": "save.all",
    "attack": "attack.all",
}


def parse_label(label: str) -> tuple[str, str] | None:
    """`advantage.adv.save.dex` → ("adv", "save.dex")。不是优势标记就返回 None。"""
    if not isinstance(label, str) or not label.startswith(PREFIX):
        return None
    rest = label[len(PREFIX):]
    mode, _, target = rest.partition(".")
    if mode not in (ADV, DIS) or not target:
        return None
    return mode, target


def target_matches(token_target: str, query: str) -> bool:
    """`check.all` 命中 `check.athletics`；`save.dex` 只命中 `save.dex`。"""
    if token_target == query:
        return True
    head, _, _rest = query.partition(".")
    return token_target == _PARENT.get(head)


def merge(modes: Iterable[str]) -> str:
    """优势与劣势同时存在 = 平掷。两者都没有 = 平掷。"""
    found = set(modes)
    if ADV in found and DIS in found:
        return FLAT
    if ADV in found:
        return ADV
    if DIS in found:
        return DIS
    return FLAT


def modes_from_effects(actor, query: str) -> tuple[str, tuple[str, ...]]:
    """只读**已经挂到角色身上**的标记（运行期效果、狂暴、法术增益）。

    常驻能力里的 `grant_advantage` 不在这里 —— 那些要读内容，
    由 `contributions.passive_advantage_modes` 合并进来。
    """
    modes: list[str] = []
    sources: list[str] = []
    for layer in _layers(actor):
        for effect in getattr(layer, "effects", ()) or ():
            if getattr(effect, "expired", False):
                continue
            parsed = parse_label(getattr(effect, "label", ""))
            if parsed is None:
                continue
            mode, token_target = parsed
            if not target_matches(token_target, query):
                continue
            modes.append(mode)
            sources.append(getattr(effect, "source", "") or token_target)
    return merge(modes), tuple(sources)


def modes_for(actor, query: str) -> tuple[str, tuple[str, ...]]:
    """兼容旧名：只看已挂载标记。"""
    return modes_from_effects(actor, query)


# --- 一次性标记 -------------------------------------------------------
# 「本回合结束前下一次攻击优势」是**待消费**的：掷过一次攻击就该消失。
# 所以它不在 effects 里（那一类是一直有效的），读和消费分成两个函数 ——
# 读的时候不能顺手扣掉（预览一次攻击不该消耗标记），扣的时候要明确说扣了谁。
def mark_modes(actor, query: str) -> tuple[str, tuple[str, ...]]:
    """一次性标记里的优势/劣势。**只读**，不消费。"""
    modes: list[str] = []
    sources: list[str] = []
    for mark in _marks(actor).matching(
            lambda item: item.kind == "advantage" and target_matches(item.target, query)):
        modes.append(mark.mode)
        sources.append(mark.label or mark.source or mark.target)
    return merge(modes), tuple(sources)


def consume_marks(actor, query: str) -> list:
    """掷过之后用掉匹配的一次性标记。返回这次被消费的标记。"""
    return _marks(actor).consume(
        lambda item: item.kind == "advantage" and target_matches(item.target, query))


def _marks(actor):
    """标记挂在本体上（一次性状态不属于某一层形态）。"""
    root = getattr(actor, "root", None)
    node = root() if callable(root) else actor
    found = getattr(node, "marks", None)
    return found if found is not None else MarkSet()


def _layers(actor):
    """角色本体 + 所有叠加层（变形）。没有 top() 的模型退化成它自己。"""
    top = getattr(actor, "top", None)
    node = top() if callable(top) else actor
    while node is not None:
        yield node
        node = getattr(node, "layer", None)


__all__ = ["FLAT", "ADV", "DIS", "MODES", "PREFIX", "parse_label", "target_matches",
           "merge", "modes_for", "mark_modes", "consume_marks"]
