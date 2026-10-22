# -*- coding: utf-8 -*-
"""从 `data/raw/equipment.json` 生成工具表 `plugins/dnd2024-core/tools.yaml`。

2024 版的工具共 37 件，分四类（工匠 / 游戏 / 乐器 / 其他），每件在原文里带一个
**建议属性**（「用这件工具做属性检定时，通常配哪项属性」）。这个字段不是我们编的，
是 `equipment.json` 里的 `ability`；写在内容里让界面有一个合理的默认值，
但检定仍然允许换属性 —— 规则原文就是「DM 决定用哪项属性」。

中文名与英文名各一份：`tool_cn` 在旧程序里只有 11 条（还是粗分类，比如
「工匠工具」一个词盖住 18 件），不够用，所以完整的对照表放在本脚本里。
**名字是我们翻译的，不是抄来的** —— 这一层没有可抄的权威来源。

用法：
    python tools/gen_tools.py            # 只在文件不存在时生成
    python tools/gen_tools.py --force    # 覆盖
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "equipment.json"
OUT = ROOT / "plugins" / "dnd2024-core" / "tools.yaml"

# 英文名 → 中文名。37 件全给，缺一件就报错（漏一件等于玩家看不到那件工具）。
TOOL_ZH = {
    "Alchemist's Supplies": "炼金工具",
    "Bagpipes": "风笛",
    "Brewer's Supplies": "酿酒工具",
    "Calligrapher's Supplies": "书法工具",
    "Carpenter's Tools": "木匠工具",
    "Cartographer's Tools": "制图工具",
    "Cobbler's Tools": "鞋匠工具",
    "Cook's Utensils": "厨具",
    "Dice": "骰子",
    "Disguise Kit": "易容工具",
    "Dragonchess": "龙棋",
    "Drum": "鼓",
    "Dulcimer": "扬琴",
    "Flute": "长笛",
    "Forgery Kit": "伪造工具",
    "Glassblower's Tools": "吹玻璃工具",
    "Herbalism Kit": "草药工具",
    "Horn": "号角",
    "Jeweler's Tools": "珠宝匠工具",
    "Leatherworker's Tools": "皮革匠工具",
    "Lute": "鲁特琴",
    "Lyre": "里拉琴",
    "Mason's Tools": "石匠工具",
    "Navigator's Tools": "领航工具",
    "Painter's Supplies": "绘画工具",
    "Pan flute": "排箫",
    "Playing Cards": "扑克牌",
    "Poisoner's Kit": "制毒工具",
    "Potter's Tools": "陶匠工具",
    "Shawm": "肖姆管",
    "Smith's Tools": "铁匠工具",
    "Thieves' Tools": "盗贼工具",
    "Three-Dragon Ante": "三龙安特牌",
    "Tinker's Tools": "修补工具",
    "Viol": "维奥尔琴",
    "Weaver's Tools": "织布工具",
    "Woodcarver's Tools": "木雕工具",
}

# 原文的 `equipment_categories` → 内核的 kind（四类，与 TOOL_KINDS 一致）。
# 顺序有意义：一件工具可能同时挂 `tools` 与 `artisans-tools`，取更具体的那个。
KIND_BY_CATEGORY = (
    ("artisans-tools", "artisan"),
    ("gaming-sets", "gaming"),
    ("musical-instruments", "musical"),
    ("other-tools", "other"),
)
ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")


def slug(text: str) -> str:
    out = []
    for char in text.strip().lower():
        out.append(char if char.isalnum() else "_")
    value = "".join(out)
    while "__" in value:
        value = value.replace("__", "_")
    return value.strip("_")


def load_rows() -> list[dict]:
    data = json.loads(RAW.read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    rows: list[dict] = []
    missing_zh: list[str] = []
    for item in items:
        categories = {cat["index"] for cat in (item.get("equipment_categories") or ())}
        kind = next((value for key, value in KIND_BY_CATEGORY if key in categories), "")
        if not kind:
            continue
        ability = (item.get("ability") or {}).get("index")
        if ability not in ABILITY_KEYS:
            # 没有建议属性的「工具」是别的分类混进来的（比如攀爬工具属于冒险装备）
            continue
        name = str(item["name"])
        if name not in TOOL_ZH:
            missing_zh.append(name)
            continue
        rows.append({
            "key": slug(item["index"]),
            "zh": TOOL_ZH[name],
            "en": name,
            "kind": kind,
            "ability": ability,
        })
    if missing_zh:
        raise SystemExit("缺少中文名：%s（在 TOOL_ZH 里补上）" % "、".join(missing_zh))
    rows.sort(key=lambda row: (row["kind"], row["key"]))
    return rows


def render(rows: list[dict]) -> str:
    out = [
        "# 由 tools/gen_tools.py 从 data/raw/equipment.json 生成。",
        "# 重跑生成器会覆盖本文件；要长期改动请改生成器的 TOOL_ZH 或数据源。",
        "#",
        "# `ability` 是原文给的**建议属性**（用这件工具做检定时通常配哪项），",
        "# 不是硬绑定 —— 规则是「DM 决定用哪项属性」，界面据此给默认值。",
    ]
    for row in rows:
        out += [
            "- id: dnd2024.tool.%s" % row["key"],
            "  name: {zh: %s, en: %s}" % (row["zh"], row["en"]),
            "  kind: %s" % row["kind"],
            "  ability: %s" % row["ability"],
        ]
    return "\n".join(out).rstrip() + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成工具表的插件 YAML")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = parser.parse_args(argv)

    rows = load_rows()
    if not rows:
        raise SystemExit("数据源里一件工具都没找到，先检查 data/raw/equipment.json")
    if OUT.exists() and not args.force:
        print("已存在，跳过（加 --force 覆盖）：%s" % OUT.name)
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(rows), encoding="utf-8")
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    print("生成 %d 件工具：%s" % (len(rows), "、".join(
        "%s %d" % (key, value) for key, value in sorted(kinds.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
