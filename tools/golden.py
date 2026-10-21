# -*- coding: utf-8 -*-
"""黄金对账：拿旧程序（dnd55e）当数值 oracle，验证新内核。

只对账**已经在新内核里实现内容**的职业 —— 没写内容的职业记 SKIP，不假装通过。
这样每加一个职业，覆盖率自动上升，不需要改脚本。

用法：
  python tools/golden.py            对账（优先用快照）
  python tools/golden.py --write    重新生成快照 tests/golden/legacy.json
  python tools/golden.py --live     忽略快照，直接跑旧程序
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SNAPSHOT = ROOT / "tests" / "golden" / "legacy.json"

# 旧程序的职业 id → 新内核的内容 id（只列已迁移的）
CLASS_MAP = {
    "barbarian": "dnd2024.class.barbarian",
    "bard": "dnd2024.class.bard",
    "cleric": "dnd2024.class.cleric",
    "druid": "dnd2024.class.druid",
    "fighter": "dnd2024.class.fighter",
    "monk": "dnd2024.class.monk",
    "paladin": "dnd2024.class.paladin",
    "ranger": "dnd2024.class.ranger",
    "rogue": "dnd2024.class.rogue",
    "sorcerer": "dnd2024.class.sorcerer",
    "warlock": "dnd2024.class.warlock",
    "wizard": "dnd2024.class.wizard",
}

LEGACY_ORDER = list(CLASS_MAP)

# 固定属性：故意做成「主属性高、短板明显」，能同时验证加值与负值
SCORES_UPPER = {"STR": 16, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12, "CHA": 8}
SCORES = {key.lower(): value for key, value in SCORES_UPPER.items()}

ABILITY_UPPER = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
ABILITY_LOWER = [key.lower() for key in ABILITY_UPPER]

FIELDS = ("hp", "pb", "ac", "attack", "speed") + tuple(
    "save.%s" % key for key in ABILITY_LOWER)

# 已知缺口白名单：**必须写清原因**，且一旦实现就要删掉（脚本会提示）。
# P5b 把最后一类（属性加值通道）做完以后这里已经清空 —— 12 职业 × 1–20 级的
# 2400 项全部零差异。以后出现新差异只能靠实现补上，不能靠加白名单。
KNOWN_GAPS: dict[tuple[str, int], tuple[str, ...]] = {}


# --- 旧程序 -----------------------------------------------------------
def legacy_snapshot() -> dict[str, dict[str, Any]]:
    import dnd55e

    rules = dnd55e.Rules()
    rows: dict[str, dict[str, Any]] = {}
    for class_id in LEGACY_ORDER:
        for level in range(1, 21):
            char = dnd55e.Character(rules)
            char.class_id, char.level = class_id, level
            char.background_id, char.species_id = "", ""
            char.base_scores.update(SCORES_UPPER)
            char.hp_current = char.hp_max()
            row = {
                "hp": char.hp_max(),
                "pb": char.pb(),
                "ac": char.ac_breakdown()[0],
                "attack": char.attack_bonus(),
                "speed": char.speed(),
            }
            for upper, lower in zip(ABILITY_UPPER, ABILITY_LOWER):
                row["save.%s" % lower] = char.save_mod(upper)
            rows["%s:%d" % (class_id, level)] = row
    return rows


# --- 新内核 -----------------------------------------------------------
def new_snapshot(bundle) -> tuple[dict[str, dict[str, Any]], list[str]]:
    import dnd5r.api as api

    rows: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    for class_id, content_id in CLASS_MAP.items():
        if content_id not in bundle.classes:
            skipped.append(class_id)
            continue
        for level in range(1, 21):
            actor = api.new_character(
                bundle, content_id, level, SCORES,
                name_zh="对账角色", name_en="Golden Dummy",
            )
            sheet = api.character_sheet(actor, bundle)
            row = {
                "hp": sheet["hp"]["maximum"],
                "pb": sheet["proficiency_bonus"],
                "ac": sheet["ac"]["total"],
                "attack": sheet["attack"]["total"],
                "speed": sheet["speed"]["walk"],
            }
            for key in ABILITY_LOWER:
                row["save.%s" % key] = sheet["saves"][key]["total"]
            rows["%s:%d" % (class_id, level)] = row
    return rows, skipped


# --- 对账 -------------------------------------------------------------
def compare(legacy: dict, fresh: dict, explain_gaps: bool = False) -> list[str]:
    """逐项对账。白名单里的差异不报错，但会统计出来（不能悄悄变多）。"""
    issues: list[str] = []
    covered_gaps: set[tuple[str, int, str]] = set()
    for key, expected in legacy.items():
        actual = fresh.get(key)
        if actual is None:
            continue
        class_id, _, level_text = key.partition(":")
        gap_fields = KNOWN_GAPS.get((class_id, int(level_text)), ())
        for field in FIELDS:
            want = expected.get(field)
            got = actual.get(field)
            if want == got:
                continue
            if field in gap_fields:
                covered_gaps.add((class_id, int(level_text), field))
                continue
            issues.append("%s %s：旧 %r ≠ 新 %r" % (key, field, want, got))
    if explain_gaps:
        stale = [(key, field) for key, fields in KNOWN_GAPS.items() for field in fields
                 if (key[0], key[1], field) not in covered_gaps]
        print("白名单放行：%d 项（%s）"
              % (len(covered_gaps),
                 "、".join("%s:%d %s" % item for item in sorted(covered_gaps)) or "无"))
        for key, field in stale:
            print("[NOTE] 白名单里的 %s:%d %s 现在已一致，可以删掉这一条" % (key[0], key[1], field))
    return issues


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="新旧内核黄金对账")
    parser.add_argument("--write", action="store_true", help="重新生成快照")
    parser.add_argument("--live", action="store_true", help="忽略快照，直接跑旧程序")
    parser.add_argument("--root", default=str(ROOT / "plugins"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    print("=== 黄金对账 ===")
    if args.write or args.live or not SNAPSHOT.exists():
        print("来源：旧程序现算（dnd55e）")
        try:
            legacy = legacy_snapshot()
        except Exception as exc:  # 旧程序加载失败不该让新内核背锅
            print("[SKIP] 旧程序不可用：%s" % exc)
            return 0
        if args.write:
            SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
            SNAPSHOT.write_text(
                json.dumps(legacy, ensure_ascii=False, indent=1, sort_keys=True),
                encoding="utf-8",
            )
            print("已写入快照：%s（%d 条）" % (SNAPSHOT.relative_to(ROOT), len(legacy)))
    else:
        print("来源：快照 %s" % SNAPSHOT.relative_to(ROOT))
        legacy = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    import dnd5r.api as api

    bundle = api.load_content(args.root)
    if bundle.errors:
        for issue in bundle.errors:
            print("[FAIL] 内容：%s" % issue)
        print("GOLDEN FAILED（内容加载有错）")
        return 1

    fresh, skipped = new_snapshot(bundle)
    keys = [key for key in legacy if key in fresh]
    issues = compare({key: legacy[key] for key in keys}, fresh, explain_gaps=True)

    covered = sorted({key.split(":")[0] for key in keys}, key=LEGACY_ORDER.index)
    print("已覆盖职业：%s（%d 级 × %d 项）"
          % ("、".join(covered) or "无", len(keys), len(FIELDS)))
    print("未实现跳过：%s" % ("、".join(skipped) if skipped else "无"))

    if issues:
        for issue in issues[:30]:
            print("[FAIL] %s" % issue)
        if len(issues) > 30:
            print("       ... 另有 %d 项" % (len(issues) - 30))
        print("GOLDEN FAILED（%d 处差异）" % len(issues))
        return 1

    if not keys:
        print("GOLDEN SKIP（新内核还没有已实现的内容）")
        return 0

    print("GOLDEN OK（%d 项全部一致）" % (len(keys) * len(FIELDS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
