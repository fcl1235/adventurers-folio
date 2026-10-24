# -*- coding: utf-8 -*-
"""feats_general.json 校验脚本（2024 PHB 专长数据）

用法:  python _featcheck.py
校验：JSON 可解析 / 键名唯一 / 必填字段 / effects 白名单 / 枚举合法性 /
      spell_grants 交叉引用 / prereq 结构 / 计数与 _counts 一致。
不因“未核实”条目而失败（只报告）。
"""
import json
import os
import sys

PATH = os.path.join("dnd55e", "data", "feats_general.json")

# ---- 规范白名单（_dataspec.md A 节） ----
EFFECT_KEYS = {
    "initiative_pb": "bool", "hp_per_level": "int", "ac": "int", "save": "int|dict",
    "check": "int", "speed": "int", "unarmed_die": "str", "set_ability": "dict",
    "skills": "int", "expertise": "int", "save_prof_choice": "int",
    "armor_prof": "list", "weapon_prof": "list", "tool_prof": "int",
    "attack_bonus": "int", "attack_bonus_ranged": "int", "damage_bonus": "int",
    "heavy_damage_pb": "bool", "bonus_attack_on_crit_or_kill": "bool",
    "concentration_adv": "bool",
    "hp_flat": "int", "truesight": "int", "skill_all_prof": "bool",
    "expertise_choice": "int", "ability_boost": "dict", "resist_choice": "dict",
    "spell_grants": "dict", "note_only": "bool",
}

DAMAGE_TYPES = {"acid", "bludgeoning", "cold", "fire", "force", "lightning",
                "necrotic", "piercing", "poison", "psychic", "radiant",
                "slashing", "thunder"}

ARMOR_ENUM = {"light", "medium", "heavy", "shields"}
WEAPON_ENUM = {"simple", "martial"}
ABILITIES = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}
# 传奇恩惠在 2024 PHB 里统一是「任选一项 +1, 上限 30」, 用 ability_boost 表达
BOON_ABILITIES = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}
CLASS_IDS = {"barbarian", "bard", "cleric", "druid", "fighter", "monk",
             "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard"}
SECTIONS = ["general", "fighting_style", "epic_boon"]
REQUIRED = ["cn", "desc", "prereq", "effects"]
# 条目可选字段白名单（classes 仅用于职业专属战斗风格）
OPTIONAL = {"repeatable", "source", "classes"}

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


class DupDict(dict):
    pass


def no_dup_hook(pairs):
    d = DupDict()
    for k, v in pairs:
        if k in d:
            err("重复键: %s" % k)
        d[k] = v
    return d


def check_prereq(name, pre):
    if not isinstance(pre, dict):
        err("%s: prereq 不是对象" % name)
        return
    for k in pre:
        if k not in ("level", "abilities", "feature", "spellcasting"):
            err("%s: prereq 出现未知字段 %r" % (name, k))
    lvl = pre.get("level")
    if not isinstance(lvl, int) or isinstance(lvl, bool):
        err("%s: prereq.level 必须是整数" % name)
    elif not 0 <= lvl <= 20:
        err("%s: prereq.level 越界 %d（须 0-20，0 = 无等级前提）" % (name, lvl))
    sc = pre.get("spellcasting")
    if sc is not None and not isinstance(sc, bool):
        err("%s: prereq.spellcasting 必须是布尔" % name)
    abilities = pre.get("abilities", [])
    if not isinstance(abilities, list):
        err("%s: prereq.abilities 必须是列表" % name)
        abilities = []
    for item in abilities:
        if (not isinstance(item, list) or len(item) != 2
                or item[0] not in ABILITIES or not isinstance(item[1], int)):
            err("%s: prereq.abilities 项非法 %r（应为 [\"STR\",13]）" % (name, item))
    feat = pre.get("feature")
    if feat is not None and not isinstance(feat, str):
        err("%s: prereq.feature 必须是字符串或 null" % name)


def check_effects(name, eff):
    if not isinstance(eff, dict):
        err("%s: effects 不是对象" % name)
        return
    if not eff:
        err("%s: effects 为空（至少应有 note_only）" % name)
    for k, v in eff.items():
        if k not in EFFECT_KEYS:
            err("%s: effects 出现白名单外的 key %r" % (name, k))
            continue
        kind = EFFECT_KEYS[k]
        if kind == "bool" and not isinstance(v, bool):
            err("%s: effects.%s 应为布尔" % (name, k))
        elif kind == "int" and (not isinstance(v, int) or isinstance(v, bool)):
            err("%s: effects.%s 应为整数" % (name, k))
        elif kind == "str" and not isinstance(v, str):
            err("%s: effects.%s 应为字符串" % (name, k))
        elif kind == "list" and not isinstance(v, list):
            err("%s: effects.%s 应为列表" % (name, k))
        elif kind == "dict" and not isinstance(v, dict):
            err("%s: effects.%s 应为对象" % (name, k))
        elif kind == "int|dict" and not isinstance(v, (int, dict)):
            err("%s: effects.%s 应为整数或对象" % (name, k))

    if "armor_prof" in eff:
        for a in eff["armor_prof"]:
            if a not in ARMOR_ENUM:
                err("%s: armor_prof 枚举非法 %r" % (name, a))
    if "weapon_prof" in eff:
        for w in eff["weapon_prof"]:
            if w not in WEAPON_ENUM:
                err("%s: weapon_prof 枚举非法 %r" % (name, w))
    if "set_ability" in eff:
        for k, v in eff["set_ability"].items():
            if k not in ABILITIES:
                err("%s: set_ability 属性名非法 %r" % (name, k))
            if not isinstance(v, int):
                err("%s: set_ability.%s 应为整数" % (name, k))
    if "save" in eff and isinstance(eff["save"], dict):
        for k, v in eff["save"].items():
            if k != "all" and k not in ABILITIES:
                err("%s: save 键非法 %r" % (name, k))
            if not isinstance(v, int):
                err("%s: save.%s 应为整数" % (name, k))
    if "ability_boost" in eff:
        ab = eff["ability_boost"]
        for k in ab:
            if k not in ("from", "max"):
                err("%s: ability_boost 出现未知字段 %r" % (name, k))
        src = ab.get("from") or []
        if not isinstance(src, list) or not src:
            err("%s: ability_boost.from 应为非空列表" % name)
        else:
            for a in src:
                if a not in ABILITIES:
                    err("%s: ability_boost.from 属性名非法 %r" % (name, a))
        mx = ab.get("max", 30)
        if not isinstance(mx, int) or isinstance(mx, bool) or not 20 < mx <= 30:
            err("%s: ability_boost.max 应为 21-30 的整数" % name)
    if "resist_choice" in eff:
        rc = eff["resist_choice"]
        for k in rc:
            if k not in ("from", "count"):
                err("%s: resist_choice 出现未知字段 %r" % (name, k))
        cnt = rc.get("count", 1)
        if not isinstance(cnt, int) or isinstance(cnt, bool) or cnt < 1:
            err("%s: resist_choice.count 应为正整数" % name)
        src = rc.get("from") or []
        if not isinstance(src, list) or not src:
            err("%s: resist_choice.from 应为非空列表" % name)
        else:
            for r in src:
                if r not in DAMAGE_TYPES:
                    err("%s: resist_choice.from 伤害类型非法 %r" % (name, r))
            if isinstance(cnt, int) and not isinstance(cnt, bool) \
                    and cnt > len(src):
                err("%s: resist_choice.count 大于可选类型数" % name)
    if "spell_grants" in eff:
        sg = eff["spell_grants"]
        cls = sg.get("class")
        if cls not in CLASS_IDS:
            err("%s: spell_grants.class 非法 %r（须为 12 职业 id 之一）" % (name, cls))
        for k in ("cantrips", "level1"):
            if k in sg and (not isinstance(sg[k], int) or isinstance(sg[k], bool)):
                err("%s: spell_grants.%s 应为整数" % (name, k))
        for k in sg:
            if k not in ("class", "cantrips", "level1"):
                warn("%s: spell_grants 出现未知字段 %r" % (name, k))


def main():
    if not os.path.exists(PATH):
        print("[FAIL] 找不到 %s" % PATH)
        return 1
    with open(PATH, encoding="utf-8") as f:
        raw = f.read()
    try:
        data = json.loads(raw, object_pairs_hook=no_dup_hook)
    except Exception as exc:  # noqa: BLE001
        print("[FAIL] JSON 解析失败: %s" % exc)
        return 1

    total = 0
    complete = 0
    unverified = []
    stat = {}

    for sec in SECTIONS:
        part = data.get(sec)
        if not isinstance(part, dict):
            err("缺少区块 %r" % sec)
            continue
        stat[sec] = len(part)
        for en, item in part.items():
            total += 1
            if not en or not isinstance(item, dict):
                err("%s/%s: 条目格式错误" % (sec, en))
                continue
            missing = [k for k in REQUIRED if k not in item]
            if missing:
                err("%s: 缺少必填字段 %s" % (en, ", ".join(missing)))
            else:
                complete += 1
            cn = item.get("cn", "")
            if not isinstance(cn, str) or not cn.strip():
                err("%s: cn 为空" % en)
            desc = item.get("desc", "")
            if not isinstance(desc, str) or len(desc.strip()) < 10:
                err("%s: desc 过短或缺失" % en)
            if "repeatable" in item and not isinstance(item["repeatable"], bool):
                err("%s: repeatable 应为布尔" % en)
            for k in item:
                if k not in REQUIRED and k not in OPTIONAL:
                    err("%s: 条目出现未定义字段 %r" % (en, k))
            if "classes" in item:
                cls = item["classes"]
                if not isinstance(cls, list) or not cls:
                    err("%s: classes 应为非空列表" % en)
                else:
                    for c in cls:
                        if c not in CLASS_IDS:
                            err("%s: classes 取值非法 %r（须为 12 职业 id 之一）" % (en, c))
                    if sec != "fighting_style":
                        err("%s: classes 只允许用于 fighting_style 条目" % en)
            check_prereq(en, item.get("prereq"))
            check_effects(en, item.get("effects", {}))

            src = item.get("source")
            if not isinstance(src, str) or not src.strip():
                warn("%s: 未标注 source，按未核实处理" % en)
                unverified.append("%s [%s]" % (en, sec))
            elif src.strip().lower() in ("unverified", "tbd", "unknown"):
                unverified.append("%s [%s]" % (en, sec))

            # 分类前提串味检查
            eff = item.get("effects", {})
            if sec == "epic_boon" and item.get("prereq", {}).get("level") != 19:
                err("%s: 传奇恩惠先决等级应为 19" % en)
            if sec == "epic_boon":
                boost = item.get("effects", {}).get("ability_boost")
                if not isinstance(boost, dict):
                    err("%s: 传奇恩惠应带 effects.ability_boost（任选一项 +1）" % en)
                else:
                    for a in (boost.get("from") or []):
                        if a not in BOON_ABILITIES:
                            err("%s: ability_boost.from 属性名非法 %r" % (en, a))
                    if boost.get("max") != 30:
                        err("%s: 传奇恩惠的 ability_boost.max 应为 30" % en)
            if sec == "fighting_style":
                pre_fs = item.get("prereq", {})
                if pre_fs.get("feature") != "Fighting Style":
                    err("%s: 战斗风格专长的 prereq.feature 应为 Fighting Style" % en)
                if pre_fs.get("level") != 0:
                    err("%s: 战斗风格专长的 prereq.level 应为 0（无等级前提）" % en)

    counts = data.get("_counts", {})
    for sec in SECTIONS:
        if sec in counts and counts[sec] != stat.get(sec):
            err("_counts.%s=%s 与实际 %s 不一致" % (sec, counts[sec], stat.get(sec)))

    print("=" * 62)
    print("general %d 条 / fighting_style %d 条 / epic_boon %d 条（合计 %d）"
          % (stat.get("general", 0), stat.get("fighting_style", 0),
             stat.get("epic_boon", 0), total))
    print("字段完整率：%d/%d = %.1f%%" % (complete, total,
                                      100.0 * complete / total if total else 0.0))
    limited = [(k, v["classes"]) for k, v in (data.get("fighting_style") or {}).items()
               if isinstance(v, dict) and "classes" in v]
    print("职业限定战斗风格：%d 条 %s" % (len(limited), limited if limited else ""))
    print("未核实条数：%d" % len(unverified))
    for u in unverified:
        print("  - 未核实: %s" % u)
    print("警告 %d 条，错误 %d 条" % (len(warnings), len(errors)))
    for w in warnings[:20]:
        print("  [WARN] %s" % w)
    for e in errors[:40]:
        print("  [ERROR] %s" % e)
    if errors:
        print("结果：FAIL")
        return 1
    print("结果：PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
