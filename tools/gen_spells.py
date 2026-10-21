# -*- coding: utf-8 -*-
"""P5f 生成器：把 339 个法术变成插件 YAML（按环一文件）+ 12 张职业法术表。

数据源：
  data/raw/spells.json        英文结构化元数据（施法时间/距离/成分/持续/伤害/学派/职业）
  dnd55e_spells.json          中文名与中文说明（旧程序翻译）

**为什么不全用旧数据**：`dnd55e_spells.json` 的元数据是混合串
（`"120 尺 Component: V, S"` 这种把成分也塞进距离的脏数据），
所以结构化字段一律从英文源取，中文只取「名字」和「说明」——中文元数据
由英文结构化字段反推，出不来就明说，不硬凑。

8 个 `summon-*` 法术只存在于旧数据里，它们属于 P8 召唤阶段，这里**不生成**：
没有英文元数据就硬造，等于把脏数据洗进内容层。

用法：
  python tools/gen_spells.py                # 生成缺失的文件
  python tools/gen_spells.py --force        # 覆盖已有文件
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "plugins" / "dnd2024-core"

# 学派英文 → 中文（只用于注释与自检，内容里存英文 id）
SCHOOL_ZH = {
    "abjuration": "防护", "conjuration": "咒法", "divination": "预言",
    "enchantment": "附魔", "evocation": "塑能", "illusion": "幻术",
    "necromancy": "死灵", "transmutation": "变化",
}

# 旧数据里有、英文源里没有的法术：留给 P8 召唤阶段
SKIP = {"summon-aberration", "summon-beast", "summon-celestial", "summon-construct",
        "summon-elemental", "summon-fey", "summon-fiend", "summon-undead"}

ABILITY_ZH = {"str": "力量", "dex": "敏捷", "con": "体质",
              "int": "智力", "wis": "感知", "cha": "魅力"}
UNITS_ZH = {"round": "轮", "minute": "分钟", "hour": "小时", "day": "天"}

CAST_FIXED = {
    "action": ("action", "1 动作", "Action"),
    "bonus action": ("bonus", "1 附赠动作", "Bonus Action"),
    "reaction": ("reaction", "1 反应", "Reaction"),
}
AREA_RE = re.compile(
    r"(\d+)-foot(?:-radius)?\s+(Sphere|Cube|Cone|Cylinder|Line|Emanation)", re.I)
SAVE_RE = re.compile(
    r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) saving throw", re.I)
TIME_RE = re.compile(r"^(up to\s+)?(\d+)\s+(round|minute|hour|day)s?$", re.I)


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)
    return text.replace("**", "")


def slug(index: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", index.lower()).strip("_")


def clean_range(raw: str) -> str:
    """`"Touch Component: V, S"` 是脏数据：把成分尾巴切掉。"""
    return re.sub(r"\s*Component:.*$", "", (raw or "").strip(), flags=re.I)


# --- 各字段的解析（解析不了就返回空，不猜） ---------------------------
def parse_cast(raw: str) -> tuple[str, str, str]:
    text = (raw or "").strip()
    head = re.split(r",| or ", text, maxsplit=1)[0].strip().lower()
    if head in CAST_FIXED:
        kind, zh, en = CAST_FIXED[head]
        return kind, zh, clean(text)
    match = TIME_RE.match(text.lower())
    if match:
        amount, unit = int(match.group(2)), match.group(3).lower()
        zh = "%d %s" % (amount, UNITS_ZH[unit])
        return "time", zh, clean(text)
    return "special", "特殊", clean(text)


def parse_range(raw: str) -> tuple[int | None, str, str]:
    text = clean_range(raw)
    key = text.lower()
    if key == "self":
        return None, "自身", "Self"
    if key in ("touch", "sight", "unlimited", "special"):
        zh = {"touch": "触碰", "sight": "视线", "unlimited": "无限", "special": "特殊"}[key]
        return None, zh, text
    match = re.match(r"^(\d+)\s*feet?$", key)
    if match:
        feet = int(match.group(1))
        return feet, "%d 尺" % feet, text
    match = re.match(r"^(\d+)\s*miles?$", key)
    if match:
        miles = int(match.group(1))
        return miles * 5280, "%d 里" % miles, text
    return None, text, text          # 认不出来就原样留着，别编


def parse_duration(raw: str, concentration: bool) -> tuple[str, str, str]:
    text = clean(raw)
    key = text.lower()
    if key == "instantaneous":
        return "instant", "立即", "Instantaneous"
    if key.startswith("until dispelled"):
        return "special", "直到被驱散", text
    if key == "special":
        return "special", "特殊", text
    match = TIME_RE.match(key.replace("concentration ", ""))
    if match:
        amount, unit = int(match.group(2)), match.group(3).lower()
        zh = "%d %s" % (amount, UNITS_ZH[unit])
        if match.group(1) or concentration:
            zh = "专注，最多 " + zh
        return "time", zh, text
    return "special", text, text


def parse_save(description: str) -> str:
    match = SAVE_RE.search(description or "")
    return "" if not match else match.group(1)[:3].lower()


def parse_area(description: str) -> tuple[str, int] | None:
    match = AREA_RE.search(description or "")
    if not match:
        return None
    return match.group(2).lower(), int(match.group(1))


def parse_damage(data: Any) -> tuple[dict[int, str], str]:
    if not isinstance(data, dict) or not data.get("damage_at_slot_level"):
        return {}, ""
    table = {}
    for key, value in data["damage_at_slot_level"].items():
        try:
            table[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    kind = ((data.get("damage_type") or {}).get("index") or "").lower()
    return table, kind


# --- 渲染 -------------------------------------------------------------
def flow(pairs: list[tuple[str, Any]]) -> str:
    return "{" + ", ".join("%s: %s" % (key, value) for key, value in pairs) + "}"


def block(text: str, indent: int) -> str:
    pad = " " * indent
    body = (text or "").replace("\r", "").strip() or "—"
    return "|-\n" + "\n".join(pad + line for line in body.splitlines())


def render_spell(row: dict, zh: dict) -> str:
    ident = "dnd2024.spell.%s" % slug(row["index"])
    level = int(row["level"])
    cast_kind, cast_zh, cast_en = parse_cast(row.get("casting_time", ""))
    feet, range_zh, range_en = parse_range(row.get("range", ""))
    concentration = bool(row.get("concentration"))
    dur_kind, dur_zh, dur_en = parse_duration(row.get("duration", ""), concentration)
    table, dmg_type = parse_damage(row.get("damage"))
    area = parse_area(row.get("description", ""))
    save = parse_save(row.get("description", ""))

    out = ["  - id: %s" % ident,
           "    name: %s" % flow([("zh", zh["name"]), ("en", row["name"])]),
           "    level: %d" % level,
           "    school: %s" % row["school"]["index"].lower()]

    if cast_kind == "time":
        out.append("    casting: %s" % flow([("kind", cast_kind), ("zh", cast_zh), ("en", cast_en)]))
    elif cast_kind == "special":
        out.append("    casting: %s" % flow([("kind", "special"), ("zh", cast_zh), ("en", cast_en)]))
    else:
        out.append("    casting: %s" % cast_kind)

    if feet is None:
        kind = {"自身": "self", "触碰": "touch", "视线": "sight",
                "无限": "unlimited"}.get(range_zh, "special")
        out.append("    range: %s" % kind)
    else:
        out.append("    range: {feet: %d}" % feet)

    comps = [str(item).lower() for item in row.get("components") or ()]
    out.append("    components: [%s]" % ", ".join(comps))
    if row.get("material"):
        out.append("    material: %s" % json.dumps(clean(row["material"]), ensure_ascii=False))

    if dur_kind in ("instant", "permanent"):
        out.append("    duration: %s" % dur_kind)
    else:
        out.append("    duration: %s" % flow([("kind", dur_kind), ("zh", dur_zh), ("en", dur_en)]))
    if concentration:
        out.append("    concentration: true")
    if row.get("ritual"):
        out.append("    ritual: true")
    if save:
        out.append("    save: %s" % save)
    if row.get("attack_type"):
        out.append("    attack: %s" % str(row["attack_type"]).lower())
    if area:
        out.append("    area: %s" % flow([("shape", area[0]), ("feet", area[1])]))
    if table:
        pairs = ([("type", dmg_type)] if dmg_type else [])
        pairs += [(str(key), value) for key, value in sorted(table.items())]
        out.append("    damage: {%s}" % ", ".join("%s: %s" % pair for pair in pairs))
    if row.get("higher_level"):
        out.append("    upcast: %s" % json.dumps(clean(row["higher_level"]), ensure_ascii=False))

    out.append("    text:")
    out.append("      zh: " + block(zh.get("desc") or clean(row["description"]), 8))
    out.append("      en: " + block(clean(row["description"]), 8))
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成法术 YAML 与职业法术表")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    english = json.loads((RAW / "spells.json").read_text(encoding="utf-8"))["items"]
    chinese = {row["id"]: row for row in
               json.loads((ROOT / "dnd55e_spells.json").read_text(encoding="utf-8"))["spells"]}

    by_level: dict[int, list[str]] = {}
    lists: dict[str, list[str]] = {}
    missing_zh = []
    for row in english:
        if row["index"] in SKIP:
            continue
        zh = chinese.get(row["index"])
        if zh is None:
            missing_zh.append(row["index"])
            zh = {"name": row["name"], "desc": ""}
        by_level.setdefault(int(row["level"]), []).append(render_spell(row, zh))
        for item in row.get("classes") or ():
            lists.setdefault(item["index"], []).append(
                "dnd2024.spell.%s" % slug(row["index"]))

    (OUT / "spells").mkdir(parents=True, exist_ok=True)
    written = []
    for level, blocks in sorted(by_level.items()):
        path = OUT / "spells" / ("level-%d.yaml" % level)
        if path.exists() and not args.force:
            continue
        header = [
            "# 由 tools/gen_spells.py 从 data/raw/spells.json + dnd55e_spells.json 生成。",
            "# 第 %d 环，共 %d 条。重跑生成器会覆盖；要长期改动请改数据源。" % (level, len(blocks)),
            "# 没有结构化伤害的法术（控制类）只登记规则原文，damage 留空 —— 不猜。",
            "",
        ]
        path.write_text("\n".join(header) + "\n\n".join(blocks) + "\n", encoding="utf-8")
        written.append("level-%d（%d）" % (level, len(blocks)))

    (OUT / "spell-lists").mkdir(parents=True, exist_ok=True)
    for class_id, spells in sorted(lists.items()):
        path = OUT / "spell-lists" / ("%s.yaml" % class_id)
        if path.exists() and not args.force:
            continue
        header = [
            "# 由 tools/gen_spells.py 从 data/raw/spells.json 的 classes 字段反推。",
            "# %s 的法术表：共 %d 条。加法术只需在这里加一行 id。" % (class_id, len(spells)),
            "",
            "class: dnd2024.class.%s" % class_id,
            "spells:",
        ]
        path.write_text("\n".join(header) + "\n" +
                        "".join("  - %s\n" % item for item in sorted(spells)),
                        encoding="utf-8")
        written.append("%s（%d）" % (class_id, len(spells)))

    print("生成：%s" % ("、".join(written) or "无（加 --force 覆盖）"))
    if missing_zh:
        print("缺少中文翻译（回退英文名）：%s" % "、".join(missing_zh))
    return 0


if __name__ == "__main__":
    sys.exit(main())
