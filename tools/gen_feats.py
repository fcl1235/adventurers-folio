# -*- coding: utf-8 -*-
"""P5g 生成器：把 79 个专长变成插件 YAML（一专长一文件）。

数据源：
  dnd55e/data/feats_general.json   43 通用 + 12 战斗风格 + 12 传奇恩惠（中文说明 + effects 键）
  dnd55e/data/feats.json           12 个起源专长（中文名 + 中文说明）
  data/raw/feats.json              17 个 SRD 专长的英文原文
  data/raw/_5e_feats.json          77 条 XPHB 原文的**结构化字段**（ability / prerequisite）

**属性加值以 XPHB 的 `ability` 字段为准**，中文说明只在没有原文时兜底。
理由：旧中文数据是按 2014 版翻译后手改的，`effects` 又只记了恩惠那 12 条 —— 两处都不可靠。
实测就抓到「骑乘战斗者」中文写「智力或感知」、原文是 `str/dex/wis`。按文字解析会把错固化。

**英文只有 17 条**：SRD 5.2 只收录了这些，其余原文不存在（不是没抓到）。
所以 `en` 文案统一写成「… is not part of SRD 5.2」，中文那条是本插件认定的正式文本。
宁可明说缺，也不要编 —— 编出来的英文会让人以为是从书上抄的。

旧数据的 `effects` 键是**旧程序**的白名单，这里翻译成新原语：

    armor_prof / weapon_prof   → grant_proficiency（armor.* / weapon.*）
    speed / ac / hp_flat       → grant_modifier（speed.walk / ac / hp.flat）
    truesight                  → grant_modifier（sense.truesight）
    attack_bonus_ranged        → grant_modifier（attack.ranged）
    ability_boost              → choices（ability_boost，cap 取恩惠的 30）
    save_prof_choice           → choices（save）
    skills / expertise         → choices（skill / expertise）
    skill_all_prof             → grant_proficiency（18 项技能）
    resist_choice              → choices（resistance）
    其余（unarmed_die / spell_grants / heavy_damage_pb / ...）→ 不生成 power，规则原文留在 text

最后那一类不是偷懒：`unarmed_die` 需要一个「徒手伤害骰」通道，
`heavy_damage_pb` 需要战斗结算，硬塞进现有原语会变成**假数据**。

用法：
  python tools/gen_feats.py               # 生成缺失的专长
  python tools/gen_feats.py --force       # 连已有文件一起覆盖
  python tools/gen_feats.py --only archery defense
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:            # 脚本方式运行时 tools/ 在 path 上，不在 ROOT
    sys.path.insert(0, str(ROOT))
RAW = ROOT / "data" / "raw"
OUT = ROOT / "plugins" / "dnd2024-core" / "feats"

# 手写过的专长：生成器绝不覆盖
HAND_WRITTEN = {
    "ability_score_improvement", "defense", "resilient", "tough", "skilled",
}

KIND_BY_SECTION = {
    "general": "general",
    "fighting_style": "fighting_style",
    "epic_boon": "epic_boon",
}

ARMOR_ZH = {"light": "轻型护甲", "medium": "中型护甲", "heavy": "重型护甲", "shield": "盾牌"}
ARMOR_EN = {"light": "Light", "medium": "Medium", "heavy": "Heavy", "shield": "Shields"}
# 旧数据写 "shields"，职业 YAML 里写 "shield"（token 是 armor.shield）—— 在这里统一
ARMOR_TOKEN = {"shields": "shield"}
WEAPON_ZH = {"simple": "简易武器", "martial": "军用武器"}
WEAPON_EN = {"simple": "Simple", "martial": "Martial"}

NO_ENGLISH = (
    "%s — the full rules text of this feat is not part of SRD 5.2, so this plugin "
    "carries the normalized Chinese text as the authoritative copy."
)

# 起源专长：中文名 → 英文名（旧数据的中文名带括号后缀，英文没有）
ORIGIN_EN = {
    "魔法入门": "Magic Initiate",
    "巧匠": "Crafter",
    "医师": "Healer",
    "幸运": "Lucky",
    "乐师": "Musician",
    "多面手": "Skilled",
    "酒馆斗殴者": "Tavern Brawler",
    "坚韧": "Tough",
    "警觉": "Alert",
    "凶蛮攻击者": "Savage Attacker",
}
ORIGIN_SUFFIX_EN = {"牧师": "Cleric", "德鲁伊": "Druid", "法师": "Wizard", "邪术师": "Warlock"}


# --- 文本工具（与 gen_subclasses.py 同一套规则） -----------------------
def clean_english(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)
    return text.replace("**", "")


def slug(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip().lower())
    return re.sub(r"_+", "_", value).strip("_")


def block(text: str, indent: int) -> str:
    pad = " " * indent
    body = (text or "").replace("\r", "").strip() or "—"
    return "|-\n" + "\n".join(pad + line for line in body.splitlines())


def flow(pairs: list[tuple[str, Any]]) -> str:
    return "{" + ", ".join("%s: %s" % (key, value) for key, value in pairs) + "}"


def split_origin(cn_name: str) -> tuple[str, str, str]:
    """「魔法入门·牧师」→ (基础中文名, 英文名, 英文后缀)。"""
    match = re.match(r"^(.*?)·(.*)$", cn_name)
    if not match:
        base = cn_name
        return base, ORIGIN_EN.get(base, base), ""
    base, suffix_zh = match.group(1), match.group(2)
    suffix = ORIGIN_SUFFIX_EN.get(suffix_zh, "")
    name = ORIGIN_EN.get(base, base)
    return base, ("%s (%s)" % (name, suffix) if suffix else name), suffix


# --- 数据源 -----------------------------------------------------------
def load_xphb() -> dict[str, dict]:
    """XPHB 原文里的结构化字段：{英文名: {"ability": [...], "level": n, "category": "G"}}。"""
    path = RAW / "_5e_feats.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8")).get("feat") or []
    rows = raw if isinstance(raw, list) else list(raw.values())
    out: dict[str, dict] = {}
    for item in rows:
        if not isinstance(item, dict) or item.get("source") != "XPHB":
            continue
        level = 0
        for prereq in item.get("prerequisite") or ():
            if isinstance(prereq, dict) and prereq.get("level"):
                level = max(level, int(prereq["level"]))
        out[str(item["name"])] = {
            "ability": item.get("ability") or [],
            "level": level,
            "category": str(item.get("category") or ""),
        }
    return out


def load_sources() -> tuple[dict[str, dict], dict[str, dict]]:
    """返回 (有序专长表, 英文原文表)。

    专长表的每项统一成：
      { en, zh, kind, level, abilities, min_score, feature, classes, repeatable,
        text_zh, effects, source, xphb }
    """
    detail = json.loads((ROOT / "dnd55e" / "data" / "feats_general.json").read_text(encoding="utf-8"))
    origin = json.loads((ROOT / "dnd55e" / "data" / "feats.json").read_text(encoding="utf-8"))["origin"]
    raw = json.loads((RAW / "feats.json").read_text(encoding="utf-8"))["items"]
    xphb = load_xphb()

    english = {item["name"]: item for item in raw}
    rows: dict[str, dict] = {}

    for section, kind in KIND_BY_SECTION.items():
        for en_name, row in (detail.get(section) or {}).items():
            prereq = row.get("prereq") or {}
            abilities = [str(pair[0]).lower() for pair in (prereq.get("abilities") or ())]
            min_score = max([int(pair[1]) for pair in (prereq.get("abilities") or ())] or [0])
            rows[slug(en_name)] = {
                "en": en_name,
                "zh": row.get("cn") or en_name,
                "kind": kind,
                "level": int(prereq.get("level") or 0),
                "abilities": abilities,
                "min_score": min_score,
                "feature": prereq.get("feature"),
                "classes": [str(item) for item in (row.get("classes") or ())],
                "repeatable": bool(row.get("repeatable")),
                "text_zh": (row.get("desc") or "").strip(),
                "effects": row.get("effects") or {},
                "source": row.get("source") or "",
                "xphb": xphb.get(en_name) or {},
            }

    for cn_name, value in origin.items():
        base, en_name, suffix = split_origin(str(cn_name))
        zh_name, zh_text = str(value[0]), str(value[1])
        rows[slug(en_name)] = {
            "en": en_name,
            "zh": zh_name,
            "kind": "origin",
            "level": 0,
            "abilities": [],
            "min_score": 0,
            "feature": None,
            "classes": [],
            "repeatable": en_name.split(" (")[0] in ("Magic Initiate", "Skilled"),
            "text_zh": zh_text,
            "effects": {},
            "source": "PHB 2024",
            "xphb": xphb.get(base) or {},
        }
    return rows, english


# --- 效果 → 原语 -------------------------------------------------------
def join_en(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return "%s and %s" % (", ".join(parts[:-1]), parts[-1])


def power_text(key: str, value: Any) -> tuple[str, str]:
    """一条效果的中英说明。这是**机制**说明，不是规则原文。"""
    if key == "armor_prof":
        items = [ARMOR_TOKEN.get(item, item) for item in value]
        zh = "获得%s熟练。" % "、".join(ARMOR_ZH.get(item, item) for item in items)
        en = "You gain training with %s." % join_en(
            [ARMOR_EN.get(item, item) for item in items])
        return zh, en
    if key == "weapon_prof":
        zh = "获得%s熟练。" % "、".join(WEAPON_ZH.get(item, item) for item in value)
        en = "You gain training with %s weapons." % join_en(
            [WEAPON_EN.get(item, item) for item in value])
        return zh, en
    if key == "speed":
        return "速度 +%d 尺。" % value, "Your Speed increases by %d feet." % value
    if key == "ac":
        return ("护甲加值 +%d（仅穿着护甲时）。" % value,
                "You gain a +%d bonus to Armor Class while wearing armor." % value)
    if key == "hp_flat":
        return ("生命值上限 +%d。" % value,
                "Your Hit Point maximum increases by %d." % value)
    if key == "truesight":
        return ("获得 %d 尺真实视觉。" % value,
                "You gain Truesight with a range of %d feet." % value)
    if key == "attack_bonus_ranged":
        return ("远程武器攻击检定 +%d。" % value,
                "You gain a +%d bonus to attack rolls you make with Ranged weapons." % value)
    if key == "skill_all_prof":
        return ("获得全部 18 项技能熟练。",
                "You gain proficiency in all eighteen skills.")
    raise KeyError(key)


def build_powers(ident: str, row: dict) -> list[tuple[str, str, list[str]]]:
    """把旧 effects 翻译成 (power 后缀, 载荷行, 文本) 的列表。

    返回的载荷行直接进 YAML，文本是 (zh, en)。
    """
    effects = row["effects"]
    out: list[tuple[str, str, tuple[str, str]]] = []
    if effects.get("armor_prof"):
        armor = [ARMOR_TOKEN.get(item, item) for item in effects["armor_prof"]]
        out.append(("armor", "      - grant_proficiency: %s"
                    % flow([("armor", "[%s]" % ", ".join(armor))]),
                    power_text("armor_prof", effects["armor_prof"])))
    if effects.get("weapon_prof"):
        out.append(("weapon", "      - grant_proficiency: %s"
                    % flow([("weapon", "[%s]" % ", ".join(effects["weapon_prof"]))]),
                    power_text("weapon_prof", effects["weapon_prof"])))
    if effects.get("speed"):
        out.append(("speed", "      - grant_modifier: {target: speed.walk, value: %d}"
                    % int(effects["speed"]), power_text("speed", int(effects["speed"]))))
    if effects.get("ac"):
        out.append(("ac", "      - grant_modifier: {target: ac, value: %d, when: {unarmored: false}}"
                    % int(effects["ac"]), power_text("ac", int(effects["ac"]))))
    if effects.get("hp_flat"):
        out.append(("hp", "      - grant_modifier: {target: hp.flat, value: %d}"
                    % int(effects["hp_flat"]), power_text("hp_flat", int(effects["hp_flat"]))))
    if effects.get("truesight"):
        out.append(("truesight", "      - grant_modifier: {target: sense.truesight, value: %d}"
                    % int(effects["truesight"]), power_text("truesight", int(effects["truesight"]))))
    if effects.get("attack_bonus_ranged"):
        out.append(("ranged", "      - grant_modifier: {target: attack.ranged, value: %d}"
                    % int(effects["attack_bonus_ranged"]),
                    power_text("attack_bonus_ranged", int(effects["attack_bonus_ranged"]))))
    if effects.get("skill_all_prof"):
        from dnd5r.content import CHOICE_UNIVERSE

        skills = CHOICE_UNIVERSE["skill"]
        out.append(("skills", "      - grant_proficiency: %s"
                    % flow([("skill", "[%s]" % ", ".join(skills))]),
                    power_text("skill_all_prof", True)))
    return [(name, line, text) for name, line, text in out]


ABILITY_ZH = {"力量": "str", "敏捷": "dex", "体质": "con",
              "智力": "int", "感知": "wis", "魅力": "cha"}
ABILITY_ORDER = ("str", "dex", "con", "int", "wis", "cha")
# 「力量或敏捷 +1（上限 20）」。要求「（上限 N）」是为了不误伤
# 「伤害掷骰 +2（可持用盾牌）」这类战斗加成。
BOOST_RE = re.compile(r"([^。；]*?)\+(\d)（上限 (\d+)）")


def parse_boost_from_text(text: str) -> dict | None:
    """从中文说明里认出「属性 +1」。

    旧数据的 effects 只记了 12 个传奇恩惠的 ability_boost，**40 多个通用专长的
    +1 全在说明文字里**。不解析就会静默丢掉一整条机制 —— 玩家选了专长，
    属性却不动，比报错更难发现。所以这里按文字解析，并且解析不出就不生成。
    """
    match = BOOST_RE.search(text or "")
    if not match:
        return None
    head, amount, cap = match.group(1), int(match.group(2)), int(match.group(3))
    if "尚无豁免熟练" in head:
        return None            # 坚毅：加值与「选的哪项豁免」绑定，手写文件里处理
    if "任选" in head:
        pool: list[str] = []   # 「任选一项属性」= 六项随便挑
    else:
        names = re.findall("力量|敏捷|体质|智力|感知|魅力", head)
        pool = [ABILITY_ZH[name] for name in dict.fromkeys(names)]
        if not pool:
            return None
    choice = {"id": "boost", "kind": "ability_boost", "count": 1,
              "amount": amount, "cap": cap}
    if len(pool) < 6:
        choice["from"] = pool
    return choice


def ability_from_xphb(spec: list, cap: int) -> dict | None:
    """XPHB 的 `ability` 字段 → 一个 ability_boost 选择项。

    原文有四种写法，全部收敛到「count 次、每次 amount 点」：

        [{"cha": 1}]                                       固定 +1 魅力
        [{"choose": {"from": [...], "amount": 2}}]          一项 +2
        [{"choose": {"from": [...], "count": 2}}]           两项各 +1
        ASI 同时给上面两条 = 「一项 +2 **或** 两项各 +1」

    最后这种不需要新语法：`count: 2, amount: 1, repeat: true` 里「同一项选两次」就是 +2。
    """
    if not spec:
        return None
    pools: list[list[str]] = []
    fixed: list[str] = []
    picks = 0
    for entry in spec:
        if not isinstance(entry, dict) or entry.get("hidden"):
            continue
        if "choose" in entry:
            chosen = entry["choose"] or {}
            pool = [str(item).lower() for item in (chosen.get("from") or ())]
            pools.append(pool)
            one = int(chosen.get("amount") or 1) * int(chosen.get("count") or 1)
            picks = max(picks, one)
        else:
            names = [key for key in entry if key in ABILITY_ZH.values()]
            if names:
                fixed.extend(names)
                picks = max(picks, int(entry[names[0]] or 1))
    if not pools and not fixed:
        return None
    pool = [key for key in ABILITY_ORDER if key in set(pools[0] if pools else fixed)]
    count = picks if picks >= 2 else 1
    choice = {"id": "boost", "kind": "ability_boost", "count": count, "amount": 1, "cap": cap}
    if count >= 2:
        # 「两项各 +1」与「一项 +2」用同一组参数表达
        choice["repeat"] = True
    if len(pool) < 6:
        choice["from"] = pool
    if count >= 2:
        choice["label"] = {"zh": "任选 %d 项属性各 +1（上限 %d）" % (count, cap),
                           "en": "Increase %d ability scores by 1 each (maximum %d)" % (count, cap)}
    else:
        choice["label"] = {"zh": "任选一项属性 +1（上限 %d）" % cap,
                           "en": "Increase one ability score by 1 (maximum %d)" % cap}
    return choice


# 旧数据里只有两条战斗风格写了 `spell_grants`，且只写「几道戏法」。「魔法入门」三兄弟
# 与「妖精触碰」这一族的法术部分只写在中文说明里 —— 就在这里补，不改旧数据库：
# 旧程序不读这个键，但它是**旧程序的数据文件**，不该为了新内核的需要去动它。
#
# 三种写法：
#   list + cantrips/level1  → 从某张职业法术表里选几道
#   schools + list: any     → 「任选一道某学派的 N 环法术」，不限职业法术表
#   fixed                   → 「你始终准备该法术」里写死的那几道（不需要选）
SCHOOL_ZH = {
    "abjuration": "防护", "conjuration": "咒法", "divination": "预言",
    "enchantment": "惑控", "evocation": "塑能", "illusion": "幻术",
    "necromancy": "死灵", "transmutation": "变化",
}
# 只给「选择项说明」用。职业显示名在职业插件里，这里不引用 —— 生成器不该依赖
# 插件内容（它读的是旧程序的数据文件）。缺了就退回 id，至少不会静默空白。
CLASS_ZH = {"cleric": "牧师", "druid": "德鲁伊", "wizard": "法师"}
HAND_GRANTS = {
    "Magic Initiate (Cleric)": {
        "list": "cleric", "cantrips": 2, "level1": 1,
        # 「可不用法术位施放 1 次，长休后恢复」—— 就一道法术，所以池容量是精确的 1
        "resource": {"id": "free_cast", "zh": "魔法入门的免费施法",
                     "en": "Magic Initiate free casting"},
    },
    "Magic Initiate (Druid)": {
        "list": "druid", "cantrips": 2, "level1": 1,
        "resource": {"id": "free_cast", "zh": "魔法入门的免费施法",
                     "en": "Magic Initiate free casting"},
    },
    "Magic Initiate (Wizard)": {
        "list": "wizard", "cantrips": 2, "level1": 1,
        "resource": {"id": "free_cast", "zh": "魔法入门的免费施法",
                     "en": "Magic Initiate free casting"},
    },
    "Fey-Touched": {
        "list": "any", "level1": 1, "schools": ["divination", "enchantment"],
        "fixed": ["misty_step"],
        # 「两道法术各自可免费施放一次」= **按法术计次**，不是共享的一格。
        # 合成 capacity 2 会让人能连放两次迷踪步 —— 宁可先不建池，留给回合流程（G16）。
        "note_zh": "迷踪步与你选的那道法术各可免法术位施放一次，长休恢复；"
                   "「各一次」是按法术记的次数，现在没有按法术计次的池，先手动记。",
        "note_en": "Each of the two spells can be cast once without a spell slot; "
                   "per-spell uses are not modelled yet, track them by hand.",
    },
    "Shadow-Touched": {
        "list": "any", "level1": 1, "schools": ["illusion", "necromancy"],
        "fixed": ["invisibility"],
        "note_zh": "隐形术与你选的那道法术各可免法术位施放一次，长休恢复；"
                   "「各一次」是按法术记的次数，现在没有按法术计次的池，先手动记。",
        "note_en": "Each of the two spells can be cast once without a spell slot; "
                   "per-spell uses are not modelled yet, track them by hand.",
    },
    "Telepathic": {
        "fixed": ["detect_thoughts"],
        "note_zh": "侦测思想可免法术位与法术成分施放一次，长休恢复；这道法术是写死的，不是选择项。",
        "note_en": "Detect Thoughts can be cast once without a spell slot or components; "
                   "the spell itself is fixed.",
    },
}


def spell_id(name: str) -> str:
    """`misty_step` → `dnd2024.spell.misty_step`。已经是全 id 就原样返回。"""
    return name if name.startswith("dnd2024.") else "dnd2024.spell.%s" % name


def _grant_spec(row: dict) -> dict:
    """这个专长给不给法术：先看旧数据的 `spell_grants`，再看手写表。

    旧数据用的是 `class` 键，手写表用 `list` —— 在这里统一，别让下游记两套。
    """
    spec = row["effects"].get("spell_grants") or HAND_GRANTS.get(row["en"]) or {}
    if not isinstance(spec, dict) or not spec:
        return {}
    merged = dict(spec)
    if not merged.get("list"):
        merged["list"] = str(merged.get("class") or "").lower()
    return merged


def build_choices(row: dict) -> list[dict]:
    effects = row["effects"]
    found: list[dict] = []
    cap = 30 if row["kind"] == "epic_boon" else 20
    authoritative = ability_from_xphb((row.get("xphb") or {}).get("ability") or [], cap)
    if authoritative:
        found.append(authoritative)
    elif effects.get("ability_boost"):
        boost = effects["ability_boost"]
        choice = {
            "id": "boost",
            "kind": "ability_boost",
            "count": 1,
            "amount": 1,
            "cap": int(boost.get("max") or 20),
            "label": {"zh": "任选一项属性 +1（上限 %d）" % int(boost.get("max") or 20),
                      "en": "Increase one ability score by 1 (maximum %d)"
                            % int(boost.get("max") or 20)},
        }
        pool = [str(item).lower() for item in (boost.get("from") or ())]
        if len(pool) < 6:
            choice["from"] = pool
        found.append(choice)
    if effects.get("save_prof_choice"):
        found.append({"id": "save", "kind": "save",
                      "count": int(effects["save_prof_choice"])})
    if effects.get("skills"):
        found.append({"id": "skill", "kind": "skill", "count": int(effects["skills"])})
    if effects.get("expertise"):
        found.append({"id": "expertise", "kind": "expertise", "count": int(effects["expertise"])})
    if effects.get("expertise_choice"):
        found.append({"id": "expertise", "kind": "expertise",
                      "count": int(effects["expertise_choice"])})
    grants = _grant_spec(row)
    if grants:
        # 「给你两道牧师戏法」这类：候选是**那张职业法术表**里的 0 环法术，
        # 不抄进内容（抄了必然和法术表漂）—— 见 rules/feats.py:spell_pool
        spells = grants.get("list")
        cn_name = CLASS_ZH.get(spells, spells)
        zh_where = "任意法术表" if spells == "any" else "%s法术表" % cn_name
        en_where = "any spell list" if spells == "any" else "the %s spell list" % spells
        cantrips = int(grants.get("cantrips") or 0)
        if cantrips:
            found.append({"id": "cantrips", "kind": "spell", "count": cantrips,
                          "spell_list": spells, "spell_level": 0,
                          "label": {"zh": "从%s的戏法里选 %d 道" % (zh_where, cantrips),
                                    "en": "Choose %d cantrip%s from %s"
                                          % (cantrips, "" if cantrips == 1 else "s",
                                             en_where)}})
        level1 = int(grants.get("level1") or 0)
        if level1:
            schools = [str(item) for item in (grants.get("schools") or ())]
            choice = {"id": "spell", "kind": "spell", "count": level1,
                      "spell_list": spells, "spell_level": 1}
            if schools:
                choice["spell_school"] = schools
            zh_schools = "或".join(SCHOOL_ZH.get(item, item) for item in schools)
            choice["label"] = {
                "zh": "从%s的 1 环法术里选 %d 道%s"
                      % (zh_where, level1, "（%s）" % zh_schools if schools else ""),
                "en": "Choose %d level 1 spell%s from %s%s"
                      % (level1, "" if level1 == 1 else "s", en_where,
                         " (%s)" % "/".join(schools) if schools else ""),
            }
            found.append(choice)
    if not effects.get("ability_boost") and not authoritative:
        parsed = parse_boost_from_text(row["text_zh"])
        if parsed:
            found.append(parsed)
    if effects.get("resist_choice"):
        resist = effects["resist_choice"]
        found.append({"id": "resist", "kind": "resistance",
                      "count": int(resist.get("count") or 1),
                      "from": [str(item) for item in (resist.get("from") or ())]})
    return found


# --- 渲染 -------------------------------------------------------------
def render(row: dict, english: dict[str, dict]) -> str:
    en_name = row["en"]
    ident = "dnd2024.feat.%s" % slug(en_name)
    srd = english.get(en_name)
    if srd is None and " (" in en_name:
        srd = english.get(en_name.split(" (")[0])

    zh_text = row["text_zh"] or row["zh"]
    en_text = clean_english(srd.get("description", "")) if srd else ""
    if not en_text:
        en_text = NO_ENGLISH % en_name

    out = [
        "# 由 tools/gen_feats.py 从 dnd55e/data/feats_general.json + data/raw/feats.json 生成。",
        "# 重跑生成器会覆盖本文件；要长期改动请改数据源，或在文件里写一个 hand-edited 注释让它别碰。",
        "",
        "id: %s" % ident,
        "kind: %s" % row["kind"],
        "name: %s" % flow([("zh", row["zh"]), ("en", en_name)]),
        "level: %d" % row["level"],
    ]
    if row["abilities"]:
        out.append("abilities: [%s]" % ", ".join(row["abilities"]))
        out.append("min_score: %d" % (row["min_score"] or 13))
    if row["classes"]:
        out.append("classes: [%s]" % ", ".join(row["classes"]))
    if row["repeatable"]:
        out.append("repeatable: true")
    out += ["text:", "  zh: " + block(zh_text, 4), "  en: " + block(en_text, 4)]

    choices = build_choices(row)
    if choices:
        out.append("choices:")
        for choice in choices:
            pairs: list[tuple[str, Any]] = [("id", choice["id"]), ("kind", choice["kind"])]
            if choice.get("count"):
                pairs.append(("count", int(choice["count"])))
            if choice.get("amount"):
                pairs.append(("amount", int(choice["amount"])))
            if choice.get("cap"):
                pairs.append(("cap", int(choice["cap"])))
            if choice.get("repeat"):
                pairs.append(("repeat", "true"))
            if choice.get("from"):
                pairs.append(("from", "[%s]" % ", ".join(choice["from"])))
            if choice.get("spell_list"):
                pairs.append(("spell_list", choice["spell_list"]))
            if choice.get("spell_level") is not None and choice.get("spell_list"):
                pairs.append(("spell_level", int(choice["spell_level"])))
            if choice.get("spell_school"):
                pairs.append(("spell_school", "[%s]" % ", ".join(choice["spell_school"])))
            if choice.get("label"):
                pairs.append(("label", flow([("zh", choice["label"]["zh"]),
                                             ("en", choice["label"]["en"])])))
            out.append("  - %s" % flow(pairs))

    grants = _grant_spec(row)
    fixed = [spell_id(item) for item in (grants.get("fixed") or ())]
    if fixed:
        out.append("spells: [%s]" % ", ".join(fixed))
    resource = grants.get("resource")
    if resource:
        # 「每长休可不耗法术位施放一次」。只给**恰好一道法术**的专长建池 ——
        # 两道法术「各一次」是按法术计次，合并成一个 2 次的池会算错（见 HAND_GRANTS）。
        out += [
            "resources:",
            "  - id: %s.%s" % (ident, resource["id"]),
            "    kind: charge",
            "    refresh: long_rest",
            "    capacity: 1",
            "    label: %s" % flow([("zh", resource["zh"]), ("en", resource["en"])]),
        ]

    powers = build_powers(ident, row)
    if grants.get("note_zh"):
        # 「各一次」这种暂时算不了的效果写成显式提示，状态是 text 而不是假装算过了
        note = flow([("zh", grants["note_zh"]), ("en", grants.get("note_en", ""))])
        powers.append(("note", "      - note: %s" % note,
                       (grants["note_zh"], grants.get("note_en", ""))))
    if powers:
        out.append("")
        out.append("powers:")
        for name, line, (zh, en) in powers:
            out += [
                "  - id: %s.%s" % (ident, name),
                "    name: %s" % flow([("zh", row["zh"]), ("en", en_name)]),
                "    kind: passive",
                "    target: self",
                "    text:",
                "      zh: " + block(zh, 8),
                "      en: " + block(en, 8),
                "    effects:",
                line,
                "",
            ]
    return "\n".join(out).rstrip() + "\n"


def audit_ability(rows: dict[str, dict]) -> list[str]:
    """中文说明解析出来的属性池 vs XPHB 原文，不一致就报出来。

    这一条是给「以后」用的：原文若被替换、或有人改了中文说明，这里会立刻出声，
    而不是等玩家发现「选了专长属性不动」。
    """
    problems: list[str] = []
    for feat_slug, row in sorted(rows.items()):
        spec = (row.get("xphb") or {}).get("ability") or []
        if not spec:
            continue
        cap = 30 if row["kind"] == "epic_boon" else 20
        truth = ability_from_xphb(spec, cap)
        parsed = parse_boost_from_text(row["text_zh"])
        if truth is None or parsed is None:
            continue                       # 一边没有就不比（坚毅的加值绑在豁免选择上）
        left = set(truth.get("from") or ABILITY_ZH.values())
        right = set(parsed.get("from") or ABILITY_ZH.values())
        if left != right:
            problems.append("%s：中文说明 %s ≠ 原文 %s"
                            % (row["en"], "/".join(sorted(right)), "/".join(sorted(left))))
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成专长的插件 YAML")
    parser.add_argument("--only", nargs="*", default=None, help="只生成这些专长（按英文名或 id 片段）")
    parser.add_argument("--force", action="store_true", help="覆盖已生成的文件")
    args = parser.parse_args(argv)

    rows, english = load_sources()
    for line in audit_ability(rows):
        print("属性池不一致 —— %s" % line)
    OUT.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []

    for feat_slug, row in rows.items():
        if args.only and feat_slug not in args.only and row["en"] not in args.only:
            continue
        if feat_slug in HAND_WRITTEN:
            skipped.append("%s（手写）" % feat_slug)
            continue
        path = OUT / ("%s.yaml" % feat_slug)
        if path.exists():
            if "# hand-edited" in path.read_text(encoding="utf-8"):
                skipped.append("%s（已手改）" % feat_slug)
                continue
            if not args.force:
                skipped.append(feat_slug)
                continue
        path.write_text(render(row, english), encoding="utf-8")
        written.append(feat_slug)

    print("生成 %d 个：%s" % (len(written), "、".join(written) or "无"))
    if skipped:
        print("跳过 %d 个（已存在/手写，加 --force 覆盖）：%s"
              % (len(skipped), "、".join(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
