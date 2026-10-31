# -*- coding: utf-8 -*-
"""把 12 职业的起始装备落成 `starting-gear.yaml`。

数据源：`data/raw/classes.json`（2024 SRD 5.2 快照）的 `starting_equipment_options`。
每个职业有两到三组选项，其中一组是「装备包 + N 枚金币」，另一组是「纯金币」——
这正是 2024 PHB 的 A/B 选项。不手抄的理由与 gen_weapons 一样：38 行里错一件看不出来。

物品名到内容 id 的映射**不写死**，是查出来的：
  * 先查 `items/weapons.yaml` / `items/armors.yaml` 的英文名（武器与护甲已经存在）
  * 再查 `items/gear.yaml`（本轮的冒险装备）
  * 都没有 → 直接报错退出。缺一件就少一件，不能让角色建出来少把武器。

用法：python tools/gen_starting_gear.py [--force]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "classes.json"
PLUGIN = ROOT / "plugins" / "dnd2024-core"
TARGET = PLUGIN / "starting-gear.yaml"

# `equipment.json` 与职业表对同一件东西的叫法不完全一样
ALIAS = {
    "Holy Symbols": "Holy Symbol",
}

UNIT_CP = {"cp": 1, "sp": 10, "gp": 100, "pp": 1000}


def _load_items() -> dict[str, str]:
    """英文名 → 内容 id。三个文件合起来查。"""
    found: dict[str, str] = {}
    for filename in ("weapons.yaml", "armors.yaml", "gear.yaml"):
        path = PLUGIN / "items" / filename
        rows = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for row in rows:
            name = row["name"]["en"]
            if name in found:
                raise SystemExit("英文名重复：%s（%s 与 %s）" % (name, found[name], row["id"]))
            found[name] = row["id"]
    return found


def _resolve(name: str, lookup: dict[str, str]) -> str:
    # 先按原名查，查不到才走别名 —— 反过来的话 `Holy Symbols`（两边都叫这个）
    # 会被别名改写成 `Holy Symbol`，反而查不到。
    for key in (name, ALIAS.get(name, "")):
        if key and key in lookup:
            return lookup[key]
    raise SystemExit("物品 %r 没有对应的内容条目（先在 items/*.yaml 里补上）" % name)


def build(lines_out: list[str]) -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    lookup = _load_items()
    count = 0
    for row in data["items"]:
        class_slug = row["index"]
        class_id = "dnd2024.class.%s" % class_slug
        groups = row.get("starting_equipment_options") or []
        if not groups:
            raise SystemExit("%s 没有起始装备选项" % row["name"])
        lines_out.append("- class: %s" % class_id)
        lines_out.append("  options:")
        for group in groups:
            # 一个 group = **一次选择**，里面的每个 option 是互斥的一项。
            # 战士有三项（A 包 / B 包 / 纯金币），不是一组里堆两套装备 —— 按 group
            # 摊平过一次，结果是把两套甲都塞进同一包、金币还叠加成 155。
            options = group["from"]["options"]
            letter = 0
            for option in options:
                if option["option_type"] == "money":
                    items = []
                    gold = 0
                    unit = str(option.get("unit", "gp")).lower()
                    gold = int(option["count"]) * UNIT_CP[unit] // 100
                elif option["option_type"] == "multiple":
                    items = []
                    gold = 0
                    for entry in option.get("items", ()):
                        if entry.get("option_type") == "money":
                            unit = str(entry.get("unit", "gp")).lower()
                            gold += int(entry["count"]) * UNIT_CP[unit] // 100
                            continue
                        ref = entry.get("of") or {}
                        if not ref:
                            continue      # 空占位（武僧那组有一个）
                        items.append((_resolve(ref["name"], lookup),
                                      int(entry.get("count", 1))))
                else:
                    raise SystemExit("%s 出现没见过的选项类型 %r"
                                     % (row["name"], option["option_type"]))
                suffix = "abc"[letter]
                letter += 1
                title = "装备包 %s" % suffix.upper() if items else "金币"
                english = "Equipment pack %s" % suffix.upper() if items else "Gold"
                lines_out.append("    - id: dnd2024.package.%s.%s"
                                 % (class_slug, suffix))
                lines_out.append("      label: {zh: %s, en: %s}" % (title, english))
                lines_out.append("      gold: %d" % gold)
                if items:
                    lines_out.append("      items:")
                    for item_id, qty in items:
                        lines_out.append("        - {item: %s, count: %d}"
                                         % (item_id, qty))
                else:
                    lines_out.append("      items: []")
                count += 1
    return count


HEADER = """\
# 2024 SRD 5.2 起始装备（由 tools/gen_starting_gear.py 从 data/raw/classes.json 生成）。
#
# 每个职业两到三组互斥选项：一组是「装备包 + 金币」，另一组是纯金币。
# 建卡与建卡向导都从这里取 —— 界面上的单选就是这里的 `label`。
#
# 字段：
#   gold   选项**附带**的金币（纯金币选项就是全部家当）
#   items  [item: 内容 id, count: 件数]；空列表表示这一组只有钱
#
# 自动装备（哪件穿上、哪把拿在手上）不写在这里，由 rules/starting.py 按类别推断。
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = parser.parse_args(argv)
    if TARGET.exists() and not args.force:
        print("%s 已存在，加 --force 覆盖" % TARGET.relative_to(ROOT))
        return 0
    lines: list[str] = []
    count = build(lines)
    TARGET.write_text(HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8",
                      newline="\n")
    print("写入 %s（%d 组选项）" % (TARGET.relative_to(ROOT), count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
