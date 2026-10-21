# -*- coding: utf-8 -*-
"""把旧程序的武器表（dnd55e/data/weapons.json）换成插件里的 weapons.yaml。

为什么用生成器而不是手抄：38 行 × 7 个字段，手抄的典型错法是**整表错位一行**
（匕首写成短剑的伤害），而且看不出来。生成器的输入是仓库里本来就有的 SRD 快照。

约定：
  * id 用 `dnd2024.item.weapon.<english_snake>`，英文名转小写下划线
  * 类别 simple / martial；伤害类型 bludgeoning / piercing / slashing
  * `properties` 原样保留（light/finesse/two_handed/versatile/thrown/heavy/reach/loading/ranged）
  * 两用武器的另一档伤害进 `versatile`
  * 目标文件已存在且带 `# hand-edited` 时不覆盖

用法：python tools/gen_weapons.py [--force]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dnd55e" / "data" / "weapons.json"
TARGET = ROOT / "plugins" / "dnd2024-core" / "items" / "weapons.yaml"

CATEGORY = {"简单": "simple", "军用": "martial"}
DAMAGE_TYPE = {"钝击": "bludgeoning", "穿刺": "piercing", "挥砍": "slashing"}

HEADER = """\
# 2024 SRD 武器表（由 tools/gen_weapons.py 从旧程序快照生成）。
#
# 字段：
#   category    simple / martial
#   damage      伤害骰；versatile 武器的双手档写在 versatile
#   properties  light / finesse / two_handed / versatile / thrown / heavy / reach / loading / ranged
#   mastery     2024 武器专精属性（cleave / graze / nick / push / sap / slow / topple / vex）
#
# 规则层不判「哪把武器该用力量还是敏捷」—— 那是 finesse/ranged 属性的推论，
# 见 rules/weapons.py；这里只放数据。
"""


def _snake(name_en: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", name_en.strip().lower()).strip("_")
    return text


def load_rows() -> list[dict]:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    light = set(data.get("light") or ())
    finesse = set(data.get("finesse") or ())
    rows = []
    for row in data["weapons"]:
        full, category, damage, mastery = row[0], row[1], row[2], row[3]
        props = list(row[4]) if len(row) > 4 else []
        versatile = row[5] if len(row) > 5 else None
        name_zh, _, name_en = full.partition(" ")
        dice, _, kind = damage.partition(" ")
        # 快照里的 light/finesse 是独立清单，属性数组可能漏标 —— 以清单为准并集
        if full in light and "light" not in props:
            props.append("light")
        if full in finesse and "finesse" not in props:
            props.append("finesse")
        rows.append({
            "id": "dnd2024.item.weapon.%s" % _snake(name_en),
            "kind": "weapon",
            "name": {"zh": name_zh, "en": name_en},
            "category": CATEGORY[category],
            "damage": dice,
            "damage_type": DAMAGE_TYPE[kind],
            "versatile": versatile,
            "properties": sorted(props),
            "mastery": mastery.lower(),
        })
    return rows


def render(rows: list[dict]) -> str:
    out = [HEADER]
    for row in rows:
        out.append("- id: %s" % row["id"])
        out.append("  kind: weapon")
        out.append("  name: {zh: %s, en: %s}" % (row["name"]["zh"], row["name"]["en"]))
        out.append("  category: %s" % row["category"])
        out.append("  damage: \"%s\"" % row["damage"])
        out.append("  damage_type: %s" % row["damage_type"])
        if row["versatile"]:
            out.append("  versatile: \"%s\"" % row["versatile"])
        if row["properties"]:
            out.append("  properties: [%s]" % ", ".join(row["properties"]))
        else:
            out.append("  properties: []")
        out.append("  mastery: %s" % row["mastery"])
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成武器 YAML")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if TARGET.exists():
        text = TARGET.read_text(encoding="utf-8")
        if "# hand-edited" in text and not args.force:
            print("[SKIP] %s 是手写文件" % TARGET.relative_to(ROOT))
            return 0
    rows = load_rows()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(rows), encoding="utf-8")
    print("已写入 %s（%d 件武器）" % (TARGET.relative_to(ROOT), len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
