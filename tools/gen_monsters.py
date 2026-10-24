# -*- coding: utf-8 -*-
"""P9c 生成器：把旧程序的 91 只 SRD 怪物做成 `monsters.yaml`。

数据源：`dnd55e/data/monsters.json`（旧程序从 SRD 5.2 抓的那一份，中文是旧程序译的）。

**为什么用旧数据当权威**：`data/raw/_5e_bestiary_phb.json` 只有 15 只（连狼都没有），
而这一份有 91 只、CR 0–6、动作带 `attack_bonus` 与伤害骰。数是数，名字是名，
旧程序的中文译名照抄，不另起一套（否则同一种生物两个中文名）。

**英文文案**：数据里只有中文说明，没有英文原文。按 G8 的口径**不编假英文**，
`en` 写一句「尚未导入」并说明中文是正式文本 —— 名字本身有英文（「狼 Wolf」），
所以只拆名字，不编句子。

**这一层要守住的两条**：
  1. `attack_bonus` 原样落盘，绝不按「属性 + 熟练」重算（实测 85/95 条对不上）
  2. `desc` 里的数字与结构化字段**都来自同一行原文**，改一处就要重跑生成器

用法：
  python tools/gen_monsters.py            # 写出 plugins/dnd2024-core/monsters.yaml
  python tools/gen_monsters.py --check    # 只比对，不写文件（CI 用）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dnd55e" / "data" / "monsters.json"
OUT = ROOT / "plugins" / "dnd2024-core" / "monsters.yaml"

SIZE_ZH = {"微型": "tiny", "小型": "small", "中型": "medium",
           "大型": "large", "巨型": "huge", "超巨型": "gargantuan"}

ABILITY_ZH = {"STR": "str", "DEX": "dex", "CON": "con",
              "INT": "int", "WIS": "wis", "CHA": "cha"}

DAMAGE_ZH = {"钝击": "bludgeoning", "穿刺": "piercing", "挥砍": "slashing",
             "强酸": "acid", "冷冻": "cold", "火焰": "fire", "力场": "force",
             "闪电": "lightning", "死灵": "necrotic", "毒素": "poison",
             "心灵": "psychic", "光耀": "radiant", "雷鸣": "thunder"}

SKILL_ZH = {"察觉": "perception", "隐匿": "stealth", "特技": "acrobatics",
            "运动": "athletics", "体操": "acrobatics", "洞悉": "insight",
            "威吓": "intimidation", "说服": "persuasion", "调查": "investigation",
            "奥秘": "arcana", "历史": "history", "医药": "medicine",
            "自然": "nature", "宗教": "religion", "驯兽": "animal_handling",
            "欺骗": "deception", "表演": "performance", "生存": "survival"}

SPEED_KEYS = ("walk", "climb", "fly", "swim", "burrow")
SENSE_KEYS = ("blindsight", "darkvision", "tremorsense", "truesight")

NO_ENGLISH = (
    "(SRD 5.2 — the English wording has not been imported; the Chinese line is "
    "this plugin's working text.)"
)

# 特性 → 掷骰形状（G23 / P10b）。**只映射算得出来的那一类**：
# 群体战术问「目标的 5 尺内有没有它这一伙未失能的盟友」，
# 阵营（Combatant.side）与位置（Encounter）都能回答，`when: ally_near_target`。
# 灵巧脱身（Nimble Escape）是附赠动作撤离/躲藏，不改这一掷 —— 留文字。
TRAIT_MODES = {"Pack Tactics": ("adv", "ally_near_target")}

_CJK = re.compile(r"[\u4e00-\u9fff]")


def split_name(raw: str) -> tuple[str, str]:
    """「狼 Wolf」→（狼, Wolf）。没有英文尾巴时英文留空，由调用方决定怎么处理。"""
    text = (raw or "").strip()
    match = re.search(r"^(.*?[\u4e00-\u9fff])\s+([A-Za-z][A-Za-z0-9'’\-\s,/()]*)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text, ""


def slug(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")


def quote(value: str) -> str:
    """YAML 标量。只在必要时加引号，让文件保持可读（中文名不加引号）。"""
    text = str(value)
    if not text:
        return '""'
    keyword = text.lower() in {"true", "false", "yes", "no", "null", "~", "on", "off"}
    special = any(ch in ":#{}[],&*!|>'\"%@`\n\t" for ch in text)
    numeric = re.fullmatch(r"[-+]?\d+(\.\d+)?", text) is not None
    if keyword or special or numeric or text != text.strip() or text[0] in "-?":
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return '"%s"' % escaped
    return text


def inline(mapping: dict[str, object]) -> str:
    return "{ %s }" % ", ".join("%s: %s" % (k, quote(v)) for k, v in mapping.items())


def text_block(key: str, value: str, indent: str) -> list[str]:
    """多行/长文本用 `|` 块。`|-` 不留尾换行，比较差异时更稳。"""
    lines = str(value).strip().splitlines() or [""]
    out = ["%s%s: |-" % (indent, key)]
    out.extend("%s  %s" % (indent, line) for line in lines)
    return out


def bilingual_text(key: str, zh: str, en: str, indent: str) -> list[str]:
    """`text: { zh: ..., en: ... }` 的块写法。

    两段都用块标量：中文说明常常很长，写成一行 flow mapping 会让 diff 变成
    「整行都变了」，看不出到底改了哪句话。
    """
    out = ["%s%s:" % (indent, key)]
    out.extend(text_block("zh", zh, indent + "  "))
    out.extend(text_block("en", en, indent + "  "))
    return out


def damage_rows(action: dict) -> list[dict]:
    dice = str(action.get("damage") or "").strip()
    if not dice:
        return []
    kind = DAMAGE_ZH.get(str(action.get("damage_type") or "").strip(), "")
    return [{"dice": dice, "type": kind}]


def render_action(action: dict, indent: str = "    ") -> list[str]:
    zh, en = split_name(action.get("name", ""))
    kind = str(action.get("kind") or "melee").lower()
    name = {"zh": zh, "en": en or zh}
    lines = ["%s- name: %s" % (indent, inline(name)), "%s  kind: %s" % (indent, kind)]
    bonus = action.get("attack_bonus")
    if bonus is not None:
        lines.append("%s  attack_bonus: %d" % (indent, int(bonus)))
    reach = int(action.get("reach") or 0)
    if reach:
        lines.append("%s  reach: %d" % (indent, reach))
    rng = action.get("range")
    if isinstance(rng, (list, tuple)) and rng:
        lines.append("%s  range: %d" % (indent, int(rng[0])))
        if len(rng) > 1:
            lines.append("%s  long_range: %d" % (indent, int(rng[1])))
    save = ABILITY_ZH.get(str(action.get("save") or "").strip().upper(), "")
    if save:
        lines.append("%s  save: %s" % (indent, save))
    if action.get("dc"):
        lines.append("%s  save_dc: %d" % (indent, int(action["dc"])))
    rows = damage_rows(action)
    if rows:
        lines.append("%s  damage:" % indent)
        lines.extend("%s    - %s" % (indent, inline(row)) for row in rows)
    desc = str(action.get("desc") or "").strip()
    if desc:
        lines.extend(bilingual_text("text", desc, NO_ENGLISH, indent + "  "))
    return lines


def render_trait(trait: dict, indent: str = "    ") -> list[str]:
    zh, en = split_name(trait.get("name", ""))
    lines = ["%s- name: %s" % (indent, inline({"zh": zh, "en": en or zh}))]
    lines.extend(bilingual_text("text", str(trait.get("desc") or "").strip(),
                                NO_ENGLISH, indent + "  "))
    mapping = TRAIT_MODES.get(en)
    if mapping:
        lines.append("%s  attack_mode: %s"
                     % (indent, inline({"mode": mapping[0], "when": mapping[1]})))
    return lines


def render_monster(monster: dict) -> str:
    ident = "dnd2024.monster.%s" % slug(str(monster["id"]))
    zh, en = split_name(monster.get("name", ""))
    abilities = monster.get("abilities") or {}
    lines = [
        "- id: %s" % ident,
        "  name: %s" % inline({"zh": zh, "en": en or zh}),
        "  size: %s" % SIZE_ZH.get(str(monster.get("size")).strip(), "medium"),
        "  ac: %d" % int(monster["ac"]),
        "  hp: %d" % int(monster["hp"]),
    ]
    if monster.get("hp_dice"):
        lines.append("  hp_dice: %s" % quote(monster["hp_dice"]))
    lines.append("  cr: %s" % ("%g" % float(monster.get("cr_num") or 0)))
    lines.append("  abilities: %s" % inline(
        {ABILITY_ZH[k]: int(v) for k, v in abilities.items() if k in ABILITY_ZH}))

    speeds = {key: int((monster.get("speed") or {}).get(key) or 0) for key in SPEED_KEYS}
    speeds = {key: value for key, value in speeds.items() if value}
    lines.append("  speeds: %s" % inline(speeds or {"walk": 30}))

    senses = monster.get("senses") or {}
    shown = {key: int(senses.get(key) or 0) for key in SENSE_KEYS}
    shown = {key: value for key, value in shown.items() if value}
    if shown:
        lines.append("  senses: %s" % inline(shown))
    passive = senses.get("passive_perception")
    if passive:
        lines.append("  passive_perception: %d" % int(passive))

    saves = {ABILITY_ZH[k]: int(v) for k, v in (monster.get("saves") or {}).items()
             if k in ABILITY_ZH}
    if saves:
        lines.append("  saves: %s" % inline(saves))
    skills = {SKILL_ZH[k]: int(v) for k, v in (monster.get("skills") or {}).items()
              if k in SKILL_ZH}
    if skills:
        lines.append("  skills: %s" % inline(skills))

    for folder, key in (("traits", "traits"), ("actions", "actions"),
                        ("bonus_actions", "bonus_actions"),
                        ("reactions", "reactions")):
        rows = monster.get(key) or []
        if not rows:
            continue
        lines.append("  %s:" % folder)
        for row in rows:
            lines.extend(render_action(row) if folder != "traits"
                         else render_trait(row))
    return "\n".join(lines)


HEADER = """\
# 由 tools/gen_monsters.py 生成，别手改（改了就重跑生成器）。
#
# 来源：dnd55e/data/monsters.json（SRD 5.2，CR 0–6，91 只）。
# 中文说明是旧程序的译文，本文件照抄。英文说明**尚未导入**，所以每个 `text.en`
# 都是一句占位声明，不是翻译 —— 编一句英文比留空更糟（见 §14 / G8）。
#
# `attack_bonus` 是原文印在卡上的数，绝不由「属性调整值 + 熟练」推算：
# 95 条攻击里 85 条推不出来（巨鳄啃咬 +8，力量 +5、敏捷 -1，凑不出来）。
# `saves` 同理，是印着的豁免加值；引擎优先读它，读不到才按属性推。

"""


def build() -> str:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    monsters = data["monsters"] if isinstance(data, dict) else data
    rows = sorted(monsters, key=lambda item: (float(item.get("cr_num") or 0),
                                              str(item.get("id"))))
    body = "\n\n".join(render_monster(row) for row in rows)
    return HEADER + body + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_monsters", description="生成怪物表")
    parser.add_argument("--check", action="store_true", help="只比对，不写文件")
    args = parser.parse_args(argv)

    if not SOURCE.exists():
        print("缺少数据源：%s" % SOURCE)
        return 2
    text = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("monsters.yaml 与生成结果不一致，请重跑 python tools/gen_monsters.py")
            return 1
        print("monsters.yaml 与生成结果一致")
        return 0
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    count = text.count("\n- id: ")
    print("写出 %s（%d 只）" % (OUT.relative_to(ROOT), count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
