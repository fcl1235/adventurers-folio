# -*- coding: utf-8 -*-
"""P5e 生成器：把 48 个子职变成插件 YAML（一子职一文件）。

数据源：
  dnd55e_classes_detail.json     子职归属、中文说明（旧程序翻译）
  dnd55e/data/classes_ui.json    子职中文名（subclass_cn）
  data/raw/subclasses.json       12 个 SRD 子职的英文原文

48 个子职里只有 12 个在 SRD 里，另外 36 个**没有英文原文**。
这不是可以糊过去的事，所以处理方式是明说：`en` 文案写成
「<英文名> — 规则原文不在 SRD 5.2 里」，中文那条是本插件认定的正式文本。
漏掉的英文原文记在 `架构设计v3-插件化.md` §14 的缺口清单里。

生成物是**内容**：可以先全部落成 passive + note，再把有真实原语的条目手改成
真实机制（改完文件里会带 `# hand-edited`，生成器就不再碰它）。

用法：
  python tools/gen_subclasses.py                # 生成缺失的子职
  python tools/gen_subclasses.py --force        # 连已有文件一起覆盖
  python tools/gen_subclasses.py --only champion evoker
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
OUT = ROOT / "plugins" / "dnd2024-core" / "subclasses"

# 手写过的子职：生成器绝不覆盖（一键 --force 把真实机制冲掉过一次）
HAND_WRITTEN = {"champion", "draconic_sorcery"}

CLASS_ZH = {
    "barbarian": "野蛮人", "bard": "吟游诗人", "cleric": "牧师", "druid": "德鲁伊",
    "fighter": "战士", "monk": "武僧", "paladin": "圣武士", "ranger": "游侠",
    "rogue": "游荡者", "sorcerer": "术士", "warlock": "邪术师", "wizard": "法师",
}

CLASS_EN = {
    "barbarian": "Barbarian", "bard": "Bard", "cleric": "Cleric", "druid": "Druid",
    "fighter": "Fighter", "monk": "Monk", "paladin": "Paladin", "ranger": "Ranger",
    "rogue": "Rogue", "sorcerer": "Sorcerer", "warlock": "Warlock", "wizard": "Wizard",
}

# 36 个子职不在 SRD 5.2 里，英文原文不存在（不是没抓到）。占位文案只写英文，
# 不把中文塞进 en 字段 —— 双语界面里 en 一栏出现中文比留空更难看。
NO_ENGLISH = (
    "%s — the full rules text of this subclass is not part of SRD 5.2, so this plugin "
    "carries the normalized Chinese text as the authoritative copy."
)


# --- 文本工具（与 gen_classes.py 同一套规则） --------------------------
def clean_english(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)
    return text.replace("**", "")


def split_name(raw: str) -> tuple[str, str]:
    """「世界树的生命力 Vitality of the Tree」→ (中文, 英文)。

    旧程序把中文名和英文名拼在一起；没有英文尾巴时英文返回空串。
    """
    name = (raw or "").strip()
    parts = name.split()
    tail: list[str] = []
    while parts and re.fullmatch(r"[A-Za-z][A-Za-z'&,\-]*", parts[-1]):
        tail.insert(0, parts.pop())
    return " ".join(parts).strip(), " ".join(tail).strip()


def slug(text: str) -> str:
    """英文名 → id 片段：小写、空格与连字符变下划线、去掉其余符号。"""
    value = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip().lower())
    return re.sub(r"_+", "_", value).strip("_")


def block(text: str, indent: int) -> str:
    pad = " " * indent
    body = (text or "").replace("\r", "").strip() or "—"
    return "|-\n" + "\n".join(pad + line for line in body.splitlines())


def flow(pairs: list[tuple[str, Any]]) -> str:
    return "{" + ", ".join("%s: %s" % (key, value) for key, value in pairs) + "}"


# --- 数据源 -----------------------------------------------------------
def load_sources() -> tuple[dict, dict[str, str], dict[str, dict]]:
    detail = json.loads((ROOT / "dnd55e_classes_detail.json").read_text(encoding="utf-8"))
    ui = json.loads((ROOT / "dnd55e" / "data" / "classes_ui.json").read_text(encoding="utf-8"))
    raw = json.loads((RAW / "subclasses.json").read_text(encoding="utf-8"))
    english = {item["name"]: item for item in raw.get("items", ())}
    return detail["subclasses"], ui.get("subclass_cn") or {}, english


def english_features(item: dict) -> dict[tuple[int, str], str]:
    """SRD 子职的英文特性表：(等级, 英文名) → 原文。"""
    return {(int(row["level"]), row["name"]): row.get("description", "")
            for row in item.get("features", ())}


# --- 渲染 -------------------------------------------------------------
def render(class_id: str, en_name: str, row: dict, zh_name: str,
           srd: dict | None) -> str:
    sub_slug = slug(en_name)
    ident = "dnd2024.subclass.%s.%s" % (class_id, sub_slug)
    features = row.get("features") or ()
    levels = [int(item["level"]) for item in features]
    unlock = min(levels) if levels else 3
    en_feats = english_features(srd) if srd else {}

    out = [
        "# 由 tools/gen_subclasses.py 从 dnd55e_classes_detail.json + data/raw/subclasses.json 生成。",
        "# 重跑生成器会覆盖本文件；要长期改动请改数据源，或在文件里写一个 hand-edited 注释让它别碰。",
        "# 特性目前一律是 passive + note：规则原文已登记，数值结算随后逐条落地。",
        "",
        "id: %s" % ident,
        "class: dnd2024.class.%s" % class_id,
        "name: %s" % flow([("zh", zh_name), ("en", en_name)]),
        "summary:",
        "  zh: " + block(row.get("summary") or zh_name, 4),
        "  en: " + block(
            clean_english(srd.get("description", "")) if srd and srd.get("description")
            else "The %s subclass of the %s." % (en_name, CLASS_EN[class_id]),
            4),
        "unlock_level: %d" % unlock,
        "",
        "powers:",
    ]

    for feature in features:
        level = int(feature["level"])
        zh_feat, en_feat = split_name(feature.get("name", ""))
        zh_text = (feature.get("desc") or "").strip()
        en_text = clean_english(en_feats.get((level, en_feat), ""))
        if not en_text:
            en_text = NO_ENGLISH % (en_feat or zh_feat)

        out += [
            "  - id: %s.%s" % (ident, slug(en_feat) or "feature_%d" % level),
            "    name: %s" % flow([("zh", zh_feat), ("en", en_feat)]),
            "    level: %d" % level,
            "    kind: passive",
            "    target: self",
            "    text:",
            "      zh: " + block(zh_text, 8),
            "      en: " + block(en_text, 8),
            "    effects:",
            "      - note:",
            "          zh: " + block("本条尚未接入数值原语，规则原文如上。", 12),
            "          en: " + block(
                "No numeric primitive is wired to this feature yet; the rule text above is the source.", 12),
            "",
        ]
    return "\n".join(out).rstrip() + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 48 个子职的插件 YAML")
    parser.add_argument("--only", nargs="*", default=None, help="只生成这些子职（按英文名或 id 片段）")
    parser.add_argument("--force", action="store_true", help="覆盖已生成的文件")
    args = parser.parse_args(argv)

    detail, subclass_cn, english = load_sources()
    OUT.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []

    for en_name, row in detail.items():
        class_id = row["class"]
        sub_slug = slug(en_name)
        if args.only and sub_slug not in args.only and en_name not in args.only:
            continue
        if sub_slug in HAND_WRITTEN:
            skipped.append("%s（手写）" % sub_slug)
            continue
        path = OUT / ("%s.%s.yaml" % (class_id, sub_slug))
        if path.exists():
            if "# hand-edited" in path.read_text(encoding="utf-8"):
                skipped.append("%s（已手改）" % sub_slug)
                continue
            if not args.force:
                skipped.append(sub_slug)
                continue
        text = render(class_id, en_name, row, subclass_cn.get(en_name, en_name),
                      english.get(en_name))
        path.write_text(text, encoding="utf-8")
        written.append(sub_slug)

    print("生成：%s" % ("、".join(written) or "无"))
    if skipped:
        print("跳过（已存在，加 --force 覆盖）：%s" % "、".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
