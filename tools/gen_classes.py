# -*- coding: utf-8 -*-
"""P5 生成器：把 SRD 2024 原始数据变成插件 YAML。

为什么要有生成器：12 个职业 × 20 级 × （环位/戏法/准备数/资源）一共近千个数，
手抄必然出错，而且错了看不出来。数据源是仓库里已有的原始 JSON：

  data/raw/classes.json              生命骰、豁免、技能选择、施法元数据
  data/raw/class-levels-2024.json    逐级的环位/戏法/准备数/资源
  data/raw/features-2024.json        特性的英文原文
  dnd55e_classes_detail.json         特性的中文名与中文说明（旧程序翻译）

生成物是**内容**，落盘后就是普通 YAML，可以手改 —— 但手改前请先看清
文件头的说明：重跑生成器会覆盖。

用法：
  python tools/gen_classes.py                # 生成缺失的职业
  python tools/gen_classes.py --force        # 连已有文件一起覆盖
  python tools/gen_classes.py --only barbarian bard
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
OUT = ROOT / "plugins" / "dnd2024-core" / "classes"

CLASS_ZH = {
    "barbarian": "野蛮人", "bard": "吟游诗人", "cleric": "牧师", "druid": "德鲁伊",
    "fighter": "战士", "monk": "武僧", "paladin": "圣武士", "ranger": "游侠",
    "rogue": "游荡者", "sorcerer": "术士", "warlock": "邪术师", "wizard": "法师",
}

CASTER = {
    "barbarian": "none", "fighter": "none", "monk": "none", "rogue": "none",
    "bard": "full", "cleric": "full", "druid": "full", "sorcerer": "full", "wizard": "full",
    "paladin": "half", "ranger": "half",
    "warlock": "pact",
}

# 资源池的语义（次数 / 点数 / 环级预算）。数据里只给数值，语义要人给一次。
RESOURCE_KIND = {
    "rage": "charge", "inspiration": "charge", "channel": "charge",
    "wildshape": "charge", "second_wind": "charge", "action_surge": "charge",
    "indomitable": "charge", "favored_enemy": "charge", "pact_slots": "charge",
    "focus": "point", "sorcery": "point", "lay_on_hands": "point",
    "arcane_recovery": "slot_level",
}

# 数据里的公式写法 → Amount 的字段
FORMULA = {
    "cha_mod_min1": "{ plus: ability.cha, floor: 1 }",
    "level": "{ plus: class_level }",
    "5*level": "{ flat: 5, times: class_level }",
}

SLOT_REFRESH = {"warlock": "short_rest"}     # 契约位短休恢复

# 契约位已经有 `slots` 表（且短休恢复），再建一个「契约位个数」池会重复计
SKIP_RESOURCES = {"warlock": {"pact_slots"}}

# 这两个职业是手写的（能力带真实效果与原语），生成器不许碰 —— 一键 --force 把
# 手写内容冲掉过，所以这里硬拦，而不是靠「记得别加 --force」。
HAND_WRITTEN = {"fighter", "druid"}

RESOURCE_EN = {
    "rage": "Rage", "inspiration": "Bardic Inspiration", "channel": "Channel Divinity",
    "wildshape": "Wild Shape", "second_wind": "Second Wind", "action_surge": "Action Surge",
    "indomitable": "Indomitable", "favored_enemy": "Favored Enemy",
    "focus": "Focus Points", "sorcery": "Sorcery Points", "lay_on_hands": "Lay On Hands",
    "arcane_recovery": "Arcane Recovery",
}


# --- 文本清洗 ---------------------------------------------------------
def clean_english(text: str) -> str:
    """SRD 抓取件里有「ex- pended」这种断词，先并回再压成一行。"""
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)
    return text.replace("**", "")


def split_name(raw: str, english: str) -> str:
    """旧程序把中文名和英文名拼在一起（「狂暴 Rage」），拆开。"""
    name = (raw or "").strip()
    if english and name.endswith(english):
        name = name[: -len(english)].strip()
    # 兜底：末尾还挂着纯 ASCII 的词（「引导神力 Channel Divinity」）也切掉
    parts = name.split()
    while parts and re.fullmatch(r"[A-Za-z][A-Za-z\'&\- ]*", " ".join(parts[-2:]) if len(parts) >= 2 else parts[-1]):
        parts.pop()
    return " ".join(parts) or english


def block(text: str, indent: int) -> str:
    pad = " " * indent
    body = text.replace("\r", "").strip() or "—"
    # 单行也用 block 标量：冒号、井号、破折号都不会被当成 YAML 语法
    return "|-\n" + "\n".join(pad + line for line in body.splitlines() or ["—"])


def flow(pairs: list[tuple[str, Any]]) -> str:
    return "{" + ", ".join("%s: %s" % (key, value) for key, value in pairs) + "}"


# --- 各部分 -----------------------------------------------------------
def load_sources():
    classes = {row["index"]: row for row in
               json.loads((RAW / "classes.json").read_text(encoding="utf-8"))["items"]}
    levels = json.loads((RAW / "class-levels-2024.json").read_text(encoding="utf-8"))
    feats = json.loads((RAW / "features-2024.json").read_text(encoding="utf-8"))
    detail = json.loads((ROOT / "dnd55e_classes_detail.json").read_text(encoding="utf-8"))
    return classes, levels, feats, detail


def skill_choices(meta: dict) -> tuple[int, list[str]]:
    for block_ in meta.get("proficiency_choices") or ():
        options = ((block_.get("from") or {}).get("options") or [])
        skills = [item["item"]["index"][len("skill-"):] for item in options
                  if str(item.get("item", {}).get("index", "")).startswith("skill-")]
        if skills:
            return int(block_.get("choose", 2)), skills
    return 2, []


def slot_rows(levels: list[dict]) -> dict[int, list[int]]:
    rows: dict[int, list[int]] = {}
    for row in levels:
        cast = row.get("spellcasting") or {}
        if not cast:
            continue
        rows[int(row["level"])] = [
            int(cast.get("spell_slots_level_%d" % index, 0)) for index in range(1, 10)
        ]
    return rows


def casting_tables(levels: list[dict]) -> tuple[dict[int, int], dict[int, int]]:
    cantrips, prepared = {}, {}
    for row in levels:
        cast = row.get("spellcasting") or {}
        if cast:
            cantrips[int(row["level"])] = int(cast.get("cantrips_known", 0))
            prepared[int(row["level"])] = int(cast.get("prepared_spells", 0))
    return cantrips, prepared


def resource_block(class_id: str, detail: dict) -> list[str]:
    lines: list[str] = []
    skipped = SKIP_RESOURCES.get(class_id, set())
    for row in detail.get("resources") or ():
        rid = row["id"]
        if rid in skipped:
            continue
        kind = RESOURCE_KIND.get(rid, "charge")
        label_en = RESOURCE_EN.get(rid, rid.replace("_", " ").title())
        label_zh = split_name(row.get("name", ""), label_en)
        table = row.get("table")
        formula = row.get("formula")
        short = row.get("short")
        lines.append("  - id: dnd2024.resource.%s.%s" % (class_id, rid))
        lines.append("    kind: %s" % kind)
        if short == "all":
            lines.append("    refresh: short_rest")
        else:
            lines.append("    refresh: long_rest")
            if short:
                lines.append("    recover_on_short_rest: %d" % int(short))
        lines.append("    label: %s" % flow([("zh", label_zh), ("en", label_en)]))
        if table:
            pairs = [(int(level), int(value)) for level, value in table.items()
                     if value is not None]
            pairs.sort()
            if pairs:
                items = ", ".join("%d: %d" % pair for pair in pairs)
                lines.append("    by_level: { %s }" % items)
            else:
                lines.append("    capacity: 1")
        elif formula in FORMULA:
            lines.append("    capacity: %s" % FORMULA[formula])
        elif formula == "half_level_ceil":
            # 奥术回想：可恢复的环数总计 ≤ 法师等级的一半（向上取整）。
            # Amount 表达不了取整，所以直接展开成表 —— 内核只查表，不写公式。
            items = ", ".join("%d: %d" % (level, (level + 1) // 2) for level in range(1, 21))
            lines.append("    by_level: { %s }" % items)
        else:
            # 不知怎么表达的公式：宁可让加载报错，也不要静默给个假数字
            raise SystemExit("%s 的资源 %s 有未知 formula：%r" % (class_id, rid, formula))
        lines.append("")
    return lines


def power_blocks(class_id: str, detail: dict, feats: dict) -> list[str]:
    lines: list[str] = []
    for feature in detail.get("features") or ():
        index = feature["index"]
        english = feats.get(index) or {}
        zh_name = split_name(feature.get("name", ""), feature.get("name_en", ""))
        en_name = feature.get("name_en") or english.get("name") or index
        zh_text = (feature.get("desc") or "").strip()
        en_text = clean_english(english.get("description") or "")
        if not zh_text:
            zh_text = en_text
        if not en_text:
            en_text = zh_text

        slug = index.split("-", 1)[1].replace("-", "_")   # id 只允许下划线
        lines.append("  - id: dnd2024.class.%s.%s" % (class_id, slug))
        lines.append("    name: %s" % flow([("zh", zh_name), ("en", en_name)]))
        lines.append("    level: %d" % int(feature.get("level", 1)))
        lines.append("    kind: passive")
        lines.append("    target: self")
        lines.append("    text:")
        lines.append("      zh: " + block(zh_text, 8))
        lines.append("      en: " + block(en_text, 8))
        lines.append("    effects:")
        lines.append("      - note:")
        lines.append("          zh: " + block("数值结算见 P5 后续：本条先登记规则原文。", 12))
        lines.append("          en: " + block("Number resolution lands later in P5; the rule text is registered here.", 12))
        lines.append("")
    return lines


def render(class_id: str, meta: dict, levels: list[dict], feats: dict, detail: dict) -> str:
    choices, skills = skill_choices(meta)
    zh = CLASS_ZH[class_id]
    en = meta["name"]
    out = [
        "# 由 tools/gen_classes.py 从 data/raw/* + dnd55e_classes_detail.json 生成。",
        "# 重跑生成器会覆盖本文件；要长期改动请改数据源，或改完这里再把它从生成列表里去掉。",
        "# 特性目前一律是 passive + note：规则原文已登记，数值结算随 P5 后续逐条落地。",
        "",
        "id: dnd2024.class.%s" % class_id,
        "name: %s" % flow([("zh", zh), ("en", en)]),
        "hit_die: %d" % int(meta["hit_die"]),
        "primary: [%s]" % ", ".join(item["index"] for item in
                                    (meta.get("primary_ability") or {}).get("ability_scores") or []),
        "saves: [%s]" % ", ".join(item["index"] for item in meta.get("saving_throws") or []),
        "caster: %s" % CASTER[class_id],
        "subclass_level: 3",
        "skill_choices: %d" % choices,
        "skill_list:",
    ]
    out += ["  - %s" % skill for skill in skills]

    resources = resource_block(class_id, detail)
    if resources:
        out += ["", "resources:"] + resources

    rows = slot_rows(levels)
    if rows:
        out += ["", "# 法术位表：等级 → 1..9 环容量（内核只查表，不写公式）", "slots:"]
        for level in sorted(rows):
            out.append("  %d: [%s]" % (level, ", ".join(str(item) for item in rows[level])))
        cantrips, prepared = casting_tables(levels)
        out += ["", "cantrips:"]
        out += ["  %d: %d" % (level, value) for level, value in sorted(cantrips.items())]
        out += ["", "prepared:"]
        out += ["  %d: %d" % (level, value) for level, value in sorted(prepared.items())]
        if class_id in SLOT_REFRESH:
            out += ["", "slot_refresh: %s" % SLOT_REFRESH[class_id]]

    out += ["", "powers:"] + power_blocks(class_id, detail, feats)
    return "\n".join(out).rstrip() + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 12 职业的插件 YAML")
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--force", action="store_true",
                        help="覆盖已生成的文件（带 # hand-edited 标记的永远不覆盖）")
    args = parser.parse_args(argv)

    classes, levels, feats, bundle = load_sources()
    details = bundle["classes"]
    targets = args.only or [key for key in classes]
    OUT.mkdir(parents=True, exist_ok=True)

    written, skipped = [], []
    for class_id in targets:
        if class_id in HAND_WRITTEN:
            skipped.append("%s（手写）" % class_id)
            continue
        path = OUT / ("%s.yaml" % class_id)
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            # 文件里出现 # hand-edited 说明有人手工补了真实机制，覆盖就是丢代码
            if "# hand-edited" in existing:
                skipped.append("%s（已手改）" % class_id)
                continue
            if not args.force:
                skipped.append(class_id)
                continue
        text = render(class_id, classes[class_id], levels[class_id], feats, details[class_id])
        path.write_text(text, encoding="utf-8")
        written.append(class_id)

    print("生成：%s" % ("、".join(written) or "无"))
    if skipped:
        print("跳过（已存在，加 --force 覆盖）：%s" % "、".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
