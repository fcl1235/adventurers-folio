# -*- coding: utf-8 -*-
"""黄金对账：拿旧程序（dnd55e）当数值 oracle，验证新内核。

**三层矩阵**（P7 起）。一层一层往上加内容，每一层都要能对上账：

  层 0 `class`     纯职业（无子职、无专长）—— 12 职业 × 20 级 × 10 项
  层 1 `subclass`  职业 + 一个子职 —— 48 子职
  层 2 `feat`      职业 + 一个专长 —— 12 条无属性加值的专长

为什么分层而不是一锅端：层 0 的差异只有「规则算错」，层 1/2 的差异还可能是
「旧程序没实现这块内容」。混在一起时，一条真 bug 会被一堆「旧程序不做」淹掉。
分层后每层的差异都能单独解释。

**差异必须登记**。`KNOWN_DELTAS` 里每条都要写清「为什么这不是 bug」，
没登记的差异一律 FAIL；登记了却又不差异的会提示删掉（白名单不能变成垃圾桶）。

用法：
  python tools/golden.py            对账（优先用快照）
  python tools/golden.py --write    重新生成快照
  python tools/golden.py --live     忽略快照，直接跑旧程序
  python tools/golden.py --layer subclass   只跑某一层
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

SNAPSHOT_CLASS = ROOT / "tests" / "golden" / "legacy.json"
SNAPSHOT_LAYERS = ROOT / "tests" / "golden" / "layers.json"

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

LAYERS = ("class", "subclass", "feat")

# 层 2 的专长：**只挑原文里没有任何属性加值的**。
# 带属性 +1 的专长会一头撞上 G12（旧程序漏算 43 条专长的属性），差异来源就说不清了。
# 所以「哨兵 / 巫师杀手」这类看着像纯战斗的专长不能进这一层 —— 2024 版它们都带
# 「力量或敏捷 +1」。`tests/unit/test_golden_matrix.py` 会用内容本身校验这条规矩。
# `legacy` 是旧程序里的设置方式：普通专长进 feats 列表，战斗风格走 fighting_style 字段。
FEAT_CASES: tuple[tuple[str, tuple[str, str], tuple[str, ...]], ...] = (
    # (新内核专长 id, (旧程序设置方式, 旧程序里的名字), 只在这些职业上测 —— 空 = 全部)
    ("dnd2024.feat.tough", ("feat", "Tough"), ()),
    ("dnd2024.feat.alert", ("feat", "Alert"), ()),
    ("dnd2024.feat.skilled", ("feat", "Skilled"), ()),
    ("dnd2024.feat.savage_attacker", ("feat", "Savage Attacker"), ()),
    ("dnd2024.feat.tavern_brawler", ("feat", "Tavern Brawler"), ()),
    ("dnd2024.feat.defense", ("style", "defense"), ("fighter", "paladin", "ranger")),
    ("dnd2024.feat.archery", ("style", "archery"), ("fighter", "paladin", "ranger")),
    ("dnd2024.feat.dueling", ("style", "dueling"), ("fighter", "paladin", "ranger")),
    ("dnd2024.feat.great_weapon_fighting", ("style", "great_weapon"), ("fighter", "paladin", "ranger")),
    ("dnd2024.feat.two_weapon_fighting", ("style", "two_weapon"), ("fighter", "paladin", "ranger")),
    ("dnd2024.feat.protection", ("style", "protection"), ("fighter", "paladin")),
    ("dnd2024.feat.blind_fighting", ("style", "blind_fighting"), ("fighter", "paladin", "ranger")),
    ("dnd2024.feat.interception", ("style", "interception"), ("fighter", "paladin")),
    ("dnd2024.feat.thrown_weapon_fighting", ("style", "thrown_weapon"), ("fighter", "paladin", "ranger")),
    ("dnd2024.feat.unarmed_fighting", ("style", "unarmed"), ("fighter", "paladin", "ranger")),
)

# 已知差异白名单：`(层, 职业, 变体, 字段) -> 原因`。
# **必须写清原因**，且一旦旧程序补齐就要删掉（脚本会提示）。
KNOWN_DELTAS: dict[tuple[str, str, str, str], str] = {
    ("subclass", "sorcerer", "dnd2024.subclass.sorcerer.draconic_sorcery", "hp"):
        "旧程序把子职当纯文本，不算龙族韧性；新内核按原文「3 级 +3、此后每个术士等级 +1」，"
        "也就是 等级 × 1（20 级 +20）",
    ("subclass", "sorcerer", "dnd2024.subclass.sorcerer.draconic_sorcery", "ac"):
        "旧程序不实现子职数值；新内核按原文「无甲时 10 + 敏捷 + 魅力」，"
        "本口径魅力 −1，所以是 11 而不是无甲基础 12",
}


def _row(char) -> dict[str, Any]:
    return {
        "hp": char.hp_max(),
        "pb": char.pb(),
        "ac": char.ac_breakdown()[0],
        "attack": char.attack_bonus(),
        "speed": char.speed(),
        **{"save.%s" % key: char.save_mod(upper)
           for upper, key in zip(ABILITY_UPPER, ABILITY_LOWER)},
    }


# --- 旧程序 -----------------------------------------------------------
def _legacy_char(rules, class_id: str, level: int):
    import dnd55e

    char = dnd55e.Character(rules)
    char.class_id, char.level = class_id, level
    char.background_id, char.species_id = "", ""
    char.base_scores.update(SCORES_UPPER)
    char.hp_current = char.hp_max()
    return char


def legacy_class_rows() -> dict[str, dict[str, Any]]:
    import dnd55e

    rules = dnd55e.Rules()
    rows: dict[str, dict[str, Any]] = {}
    for class_id in LEGACY_ORDER:
        for level in range(1, 21):
            rows["%s:%d" % (class_id, level)] = _row(_legacy_char(rules, class_id, level))
    return rows


def legacy_subclass_rows(rules, pairs) -> dict[str, dict[str, Any]]:
    """`pairs` 是 `subclass_pairs()` 的结果 —— key 用**新内核的 id**。

    旧程序里只有英文显示名，如果拿它当 key，两层就永远对不上（新内核写的是 id），
    而且「0 组 × 11 项 = 0 项差异」还会显示成全绿。
    """
    rows: dict[str, dict[str, Any]] = {}
    for class_id, sub_id, name in pairs:
        for level in range(1, 21):
            char = _legacy_char(rules, class_id, level)
            char.subclass = name
            rows["%s|%s:%d" % (class_id, sub_id, level)] = _row(char)
    return rows


def legacy_feat_rows(rules) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for feat_id, (kind, name), classes in FEAT_CASES:
        for class_id in (classes or tuple(LEGACY_ORDER)):
            for level in range(1, 21):
                char = _legacy_char(rules, class_id, level)
                if kind == "style":
                    char.fighting_style = name
                else:
                    char.feats = [name]
                rows["%s|%s:%d" % (class_id, feat_id, level)] = _row(char)
    return rows


# --- 新内核 -----------------------------------------------------------
def _sheet_row(bundle, class_id: str, level: int, subclass: str | None = None,
               feats: tuple[str, ...] = ()) -> dict[str, Any]:
    import dnd5r.api as api

    actor = api.new_character(
        bundle, CLASS_MAP[class_id], level, SCORES,
        name_zh="对账角色", name_en="Golden Dummy",
        subclass=subclass, feats=feats,
    )
    sheet = api.character_sheet(actor, bundle)
    return {
        "hp": sheet["hp"]["maximum"],
        "pb": sheet["proficiency_bonus"],
        "ac": sheet["ac"]["total"],
        "attack": sheet["attack"]["total"],
        "speed": sheet["speed"]["walk"],
        **{"save.%s" % key: sheet["saves"][key]["total"] for key in ABILITY_LOWER},
    }


def subclass_pairs(bundle, rules) -> list[tuple[str, str, str]]:
    """(职业, 新内核子职 id, 旧程序子职名) —— 按英文名对齐，对不上的直接报。"""
    out: list[tuple[str, str, str]] = []
    by_class: dict[str, dict[str, str]] = {}
    for sub_id, sub in bundle.subclasses.items():
        class_key = sub.class_id.rsplit(".", 1)[-1]
        by_class.setdefault(class_key, {})[sub.name.get("en")] = sub_id
    for class_id in LEGACY_ORDER:
        kernel = by_class.get(class_id, {})
        for name, _zh, _summary in rules.sub_options(class_id):
            sub_id = kernel.get(name)
            if sub_id is None:
                raise SystemExit("[FAIL] 子职对不上：%s 的 %r 在新内核里没有同名条目（有：%s）"
                                 % (class_id, name, "、".join(sorted(kernel)) or "无"))
            out.append((class_id, sub_id, name))
    return out


# --- 对账 -------------------------------------------------------------
# 这一轮里实际命中过哪些白名单条（用来提示「登记了但已不差异」的陈旧条目）
_hit_deltas: set[tuple[str, str, str, str]] = set()


def compare(layer: str, legacy: dict, fresh: dict, verbose: bool = False) -> tuple[list[str], int, int]:
    """逐项对账。返回 (差异, 比对项数, 在册差异数)。

    白名单按 `(层, 职业, 变体, 字段)` 登记 —— 变体已经写进 key，所以同一子职
    在 20 个等级上的同一处差异只需要一条原因，不用抄 20 遍。
    """
    issues: list[str] = []
    compared = 0
    excused = 0
    for key, expected in legacy.items():
        actual = fresh.get(key)
        if actual is None:
            continue
        compared += 1
        if "|" in key:
            class_id, _, rest = key.partition("|")
            variant = rest.rpartition(":")[0]
        else:
            class_id, _, _level = key.partition(":")
            variant = ""
        for field in FIELDS:
            want, got = expected.get(field), actual.get(field)
            if want == got:
                continue
            reason = KNOWN_DELTAS.get((layer, class_id, variant, field))
            if reason is not None:
                excused += 1
                _hit_deltas.add((layer, class_id, variant, field))
                if verbose:
                    print("  [在册] %s %s：旧 %r / 新 %r —— %s"
                          % (key, field, want, got, reason))
                continue
            issues.append("%s %s：旧 %r ≠ 新 %r" % (key, field, want, got))
    return issues, compared, excused


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="新旧内核黄金对账（三层矩阵）")
    parser.add_argument("--write", action="store_true", help="重新生成快照")
    parser.add_argument("--live", action="store_true", help="忽略快照，直接跑旧程序")
    parser.add_argument("--root", default=str(ROOT / "plugins"))
    parser.add_argument("--layer", default="", help="只跑某一层：class / subclass / feat")
    parser.add_argument("--verbose", action="store_true", help="逐条打印在册差异")
    args = parser.parse_args(argv)

    layers = (args.layer,) if args.layer else LAYERS
    for name in layers:
        if name not in LAYERS:
            parser.error("未知层：%r（可选 %s）" % (name, "/".join(LAYERS)))

    print("=== 黄金对账 ===")
    legacy: dict[str, dict[str, dict[str, Any]]] = {}
    if not (args.write or args.live):
        if SNAPSHOT_CLASS.exists():
            legacy["class"] = json.loads(SNAPSHOT_CLASS.read_text(encoding="utf-8"))
        if SNAPSHOT_LAYERS.exists():
            legacy.update(json.loads(SNAPSHOT_LAYERS.read_text(encoding="utf-8")))
        print("来源：快照 %s" % SNAPSHOT_CLASS.relative_to(ROOT))
    missing = [] if args.write else [name for name in layers if name not in legacy]
    if missing:
        print("[SKIP] 快照里没有这一层：%s（先跑 --write）" % "、".join(missing))
        return 0

    import dnd5r.api as api

    bundle = api.load_content(args.root)
    if bundle.errors:
        for issue in bundle.errors:
            print("[FAIL] 内容：%s" % issue)
        print("GOLDEN FAILED（内容加载有错）")
        return 1

    rules = None
    fresh: dict[str, dict[str, dict[str, Any]]] = {}
    # 前提不满足的组合（哨兵要 4 级、战斗风格只有三个职业有）不是缺口，
    # 但要**数出来**：悄悄少测一半和跳过全部长得一样。
    skipped: list[str] = []
    if "class" in layers:
        fresh["class"] = {}
        for class_id in LEGACY_ORDER:
            for level in range(1, 21):
                fresh["class"]["%s:%d" % (class_id, level)] = _sheet_row(bundle, class_id, level)
    if {"subclass", "feat"} & set(layers):
        import dnd55e

        rules = dnd55e.Rules()
    if "subclass" in layers:
        fresh["subclass"] = {}
        for class_id, sub_id, _name in subclass_pairs(bundle, rules):
            for level in range(1, 21):
                fresh["subclass"]["%s|%s:%d" % (class_id, sub_id, level)] = _sheet_row(
                    bundle, class_id, level, subclass=sub_id)
    if "feat" in layers:
        fresh["feat"] = {}
        for feat_id, _legacy_spec, classes in FEAT_CASES:
            for class_id in (classes or tuple(LEGACY_ORDER)):
                for level in range(1, 21):
                    try:
                        fresh["feat"]["%s|%s:%d" % (class_id, feat_id, level)] = _sheet_row(
                            bundle, class_id, level, feats=(feat_id,))
                    except api.RuleError as exc:
                        skipped.append("%s %s Lv%d：%s" % (class_id, feat_id, level, exc))

    if args.write:
        # 快照的每一行都必须来自**旧程序** —— 拿新内核算完再存，等于自己跟自己比。
        if "class" in fresh:
            SNAPSHOT_CLASS.parent.mkdir(parents=True, exist_ok=True)
            rows = legacy_class_rows()
            SNAPSHOT_CLASS.write_text(
                json.dumps(rows, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            print("已写入快照：%s（%d 条）" % (SNAPSHOT_CLASS.relative_to(ROOT), len(rows)))
        if {"subclass", "feat"} & set(fresh):
            layers_rows: dict[str, dict[str, Any]] = {}
            if "subclass" in fresh:
                layers_rows["subclass"] = legacy_subclass_rows(rules, subclass_pairs(bundle, rules))
            if "feat" in fresh:
                layers_rows["feat"] = legacy_feat_rows(rules)
            SNAPSHOT_LAYERS.write_text(
                json.dumps(layers_rows, ensure_ascii=False, indent=1, sort_keys=True),
                encoding="utf-8")
            print("已写入快照：%s（%s）"
                  % (SNAPSHOT_LAYERS.relative_to(ROOT),
                     " / ".join("%s %d 条" % (key, len(value))
                                for key, value in layers_rows.items())))
        print("GOLDEN OK（快照已更新）")
        return 0

    total_compared = 0
    total_excused = 0
    issues: list[str] = []
    layer_titles = {"class": "层 0 职业", "subclass": "层 1 +子职", "feat": "层 2 +专长"}
    for name in layers:
        layer_issues, compared, excused = compare(
            name, legacy[name], fresh[name], verbose=args.verbose)
        total_compared += compared
        total_excused += excused
        issues.extend(layer_issues)
        print("%s：%d 组 × %d 项 = %d 项，差异 %d 项（在册 %d）"
              % (layer_titles[name], compared, len(FIELDS), compared * len(FIELDS),
                 len(layer_issues), excused))

    if skipped:
        print("前提不满足跳过：%d 组（例：%s）" % (len(skipped), skipped[0]))

    stale = [key for key in KNOWN_DELTAS
             if key[0] in layers and key not in _hit_deltas]
    for key in stale:
        print("[NOTE] 白名单里的 %s 现在已一致，可以删掉这一条" % (key,))

    if issues:
        for issue in issues[:30]:
            print("[FAIL] %s" % issue)
        if len(issues) > 30:
            print("       ... 另有 %d 项" % (len(issues) - 30))
        print("GOLDEN FAILED（%d 处差异）" % len(issues))
        return 1

    if not total_compared:
        print("GOLDEN SKIP（新内核还没有已实现的内容）")
        return 0

    print("GOLDEN OK（%d 项全部一致，其中 %d 项按登记原因放行）"
          % (total_compared * len(FIELDS), total_excused))
    return 0


if __name__ == "__main__":
    sys.exit(main())
