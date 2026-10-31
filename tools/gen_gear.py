# -*- coding: utf-8 -*-
"""把冒险装备（非武器/非护甲）落成 `items/gear.yaml`。

数据源是 `data/raw/equipment.json`（2024 SRD 5.2 的装备快照）。价格与重量**照抄**，
不手填 —— 手抄的典型错法是公斤与磅混着写，看不出来。中文名与归类（pack/tool/
focus/ammo/clothing）是我方认定的文本，写在本脚本的白名单里。

为什么只收 17 件：这些是 12 职业**起始装备包**里实际出现的东西
（见 `tools/gen_starting_gear.py`）。整本装备表 182 条不是本轮目标 —— 收进来
就得逐条翻译，而界面上暂时没有「买装备」这条路径能用到它们。

用法：python tools/gen_gear.py [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "equipment.json"
TARGET = ROOT / "plugins" / "dnd2024-core" / "items" / "gear.yaml"

# 英文名 → (slug, 中文名, category)
WHITELIST = {
    "Explorer's Pack": ("explorers_pack", "探索者背包", "pack"),
    "Dungeoneer's Pack": ("dungeoneers_pack", "地城探险背包", "pack"),
    "Priest's Pack": ("priests_pack", "祭司背包", "pack"),
    "Scholar's Pack": ("scholars_pack", "学者背包", "pack"),
    "Entertainer's Pack": ("entertainers_pack", "艺人背包", "pack"),
    "Burglar's Pack": ("burglars_pack", "窃贼背包", "pack"),
    "Herbalism Kit": ("herbalism_kit", "草药工具", "tool"),
    "Thieves' Tools": ("thieves_tools", "盗贼工具", "tool"),
    "Sprig of Mistletoe": ("sprig_of_mistletoe", "槲寄生枝", "focus"),
    "Crystal": ("crystal", "水晶", "focus"),
    "Orb": ("orb", "法球", "focus"),
    "Book": ("book", "书", "focus"),
    "Spellbook": ("spellbook", "法术书", "book"),
    "Robe": ("robe", "长袍", "clothing"),
    "Arrows": ("arrows", "箭矢（20 支）", "ammo"),
    "Quiver": ("quiver", "箭袋", "ammo"),
}

# 快照里没有的（5e 把法器归到 equipment-categories，不在 equipment 清单里）。
# 数值按 SRD 5.2《Adventuring Gear》表手填，只这一条。
MANUAL = {
    "Holy Symbols": {
        "slug": "holy_symbol",
        "zh": "圣徽",
        "category": "focus",
        "cost_cp": 500,
        "weight": 1.0,
        "contains": 0,
    },
}

UNIT_CP = {"cp": 1, "sp": 10, "gp": 100, "pp": 1000}


def _cost_cp(row: dict) -> int | None:
    cost = row.get("cost")
    if not cost:
        return None
    unit = str(cost.get("unit", "gp")).lower()
    if unit not in UNIT_CP:
        raise SystemExit("%s 的价格单位不认识：%r" % (row["name"], unit))
    return int(cost["quantity"]) * UNIT_CP[unit]


def _dump_text(text: str) -> str:
    """YAML 内联字符串：含冒号/引号就套单引号（中文里常有「：」）。"""
    if any(ch in text for ch in ":#'\"{}[]&*!|>%@`"):
        return "'%s'" % text.replace("'", "''")
    return text


def build_rows() -> list[str]:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    by_name = {row["name"]: row for row in data["items"]}
    lines: list[str] = []

    for name in WHITELIST:
        if name not in by_name:
            raise SystemExit("快照里找不到 %r" % name)

    for name, (slug, zh, category) in WHITELIST.items():
        row = by_name[name]
        cost = _cost_cp(row)
        weight = row.get("weight")
        contains = len(row.get("contents") or ())
        lines.append("- id: dnd2024.item.gear.%s" % slug)
        lines.append("  kind: gear")
        lines.append("  name: {zh: %s, en: %s}" % (_dump_text(zh), _dump_text(name)))
        lines.append("  category: %s" % category)
        if cost is not None:
            lines.append("  cost_cp: %d" % cost)
        if weight is not None:
            lines.append("  weight: %s" % weight)
        if contains:
            lines.append("  contains: %d" % contains)

    for name, row in MANUAL.items():
        lines.append("- id: dnd2024.item.gear.%s" % row["slug"])
        lines.append("  kind: gear")
        lines.append("  name: {zh: %s, en: %s}" % (_dump_text(row["zh"]),
                                                  _dump_text(name)))
        lines.append("  category: %s" % row["category"])
        lines.append("  cost_cp: %d" % row["cost_cp"])
        lines.append("  weight: %s" % row["weight"])
        if row["contains"]:
            lines.append("  contains: %d" % row["contains"])
    return lines


HEADER = """\
# 冒险装备（非武器 / 非护甲 / 非盾）。由 tools/gen_gear.py 从 data/raw/equipment.json
# 的 2024 SRD 5.2 快照生成，价格与重量照抄快照，中文名为本插件文本。
#
# 字段：
#   category   pack / tool / focus / book / clothing / ammo / gear
#   cost_cp    价格（铜币；1 gp = 100 cp）
#   weight     磅
#   contains   背包类内含的件数（内容清单不展开：展开要再收 40 件物品并逐条翻译，
#              界面上「含 11 件」已经够用）
#
# 这些物品**不参与 AC、攻击、施法**的结算 —— 它们是背包里的东西。
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = parser.parse_args(argv)

    if TARGET.exists() and not args.force:
        print("%s 已存在，加 --force 覆盖" % TARGET.relative_to(ROOT))
        return 0

    lines = build_rows()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8",
                      newline="\n")
    print("写入 %s（%d 件）" % (TARGET.relative_to(ROOT),
                                len(WHITELIST) + len(MANUAL)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
