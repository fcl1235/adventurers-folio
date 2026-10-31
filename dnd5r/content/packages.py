# -*- coding: utf-8 -*-
"""起始装备包：建卡时「A 包还是纯金币」的那个选择。

它不是物品，也不进 `items/`：一个包是**一组引用 + 一小笔金币**，与物品目录
是两种东西。为什么不做成「职业的字段」：12 个职业各 2–3 组，写进 class yaml
会把 `ClassDef` 撑成一个既管规则又管仓库的杂货铺；单独一份 `starting-gear.yaml`
还能由生成器整体重出（`tools/gen_starting_gear.py`）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..kernel.errors import PluginError
from ..kernel.ids import is_valid
from ..kernel.text import Text


@dataclass(frozen=True)
class StartingPack:
    """一组起始装备。

    `items` 是 `(内容 id, 件数)`，顺序**有意义** —— 自动装备按这个顺序挑
    「第一把武器拿在手上」，所以写内容时把主武器写前面。
    `gold` 是这一组附带的钱（纯金币选项就是全部家当）。
    """

    id: str
    class_id: str
    label: Text
    gold: int = 0
    items: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("起始装备 id 不合规范：%r" % (self.id,))
        if not is_valid(self.class_id):
            raise PluginError("%s 的职业 id 不合规范：%r" % (self.id, self.class_id))
        if self.gold < 0:
            raise PluginError("%s 的金币不能为负：%r" % (self.id, self.gold))
        seen: set[str] = set()
        for item_id, count in self.items:
            if not is_valid(item_id):
                raise PluginError("%s 里的物品 id 不合规范：%r" % (self.id, item_id))
            if count < 1:
                raise PluginError("%s 里 %s 的件数必须 ≥ 1" % (self.id, item_id))
            if item_id in seen:
                # 同一个包里写两次会让「装了几件」有两个说法，合并与否都是猜
                raise PluginError("%s 里 %s 出现了两次（合并成一条）" % (self.id, item_id))
            seen.add(item_id)

    def item_ids(self) -> tuple[str, ...]:
        return tuple(item_id for item_id, _ in self.items)

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "id": self.id, "class_id": self.class_id,
            "label": self.label.get(locale), "gold": self.gold,
            "items": [{"id": item_id, "count": count}
                      for item_id, count in self.items],
        }


def parse_starting_pack(data: Any, class_id: str, where: str = "") -> StartingPack:
    prefix = ("%s: " % where) if where else ""
    if not isinstance(data, Mapping):
        raise PluginError("%s起始装备条目必须是映射" % prefix)
    ident = data.get("id")
    if not ident:
        raise PluginError("%s起始装备缺少 id" % prefix)
    if "label" not in data:
        raise PluginError("%s %s 缺少 label" % (prefix, ident))
    rows: Iterable[Any] = data.get("items") or ()
    items: list[tuple[str, int]] = []
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("item"):
            raise PluginError("%s %s 的物品条目要写成 {item: id, count: n}" % (prefix, ident))
        try:
            count = int(row.get("count", 1))
        except (TypeError, ValueError):
            raise PluginError("%s %s 的件数不是整数：%r"
                              % (prefix, ident, row.get("count")))
        items.append((str(row["item"]), count))
    try:
        gold = int(data.get("gold", 0) or 0)
    except (TypeError, ValueError):
        raise PluginError("%s %s 的金币不是整数：%r" % (prefix, ident, data.get("gold")))
    return StartingPack(
        id=str(ident),
        class_id=class_id,
        label=Text.from_dict(data["label"], where="%s label" % ident),
        gold=gold,
        items=tuple(items),
    )


def check_starting_packs(packs: Iterable[StartingPack],
                         known_items: Mapping[str, Any]) -> list[str]:
    """内容自检：包里的物品与职业都得存在。返回问题列表（空 = 通过）。

    放在这里而不是 loader 里，是为了 `plugins_cli` 也能复用同一份判断。
    """
    problems: list[str] = []
    for pack in packs:
        for item_id, _ in pack.items:
            if item_id not in known_items:
                problems.append("%s 引用了不存在的物品 %s" % (pack.id, item_id))
    return problems


__all__ = ["StartingPack", "parse_starting_pack", "check_starting_packs"]
