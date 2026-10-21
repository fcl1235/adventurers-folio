# -*- coding: utf-8 -*-
"""野兽形态 —— 德鲁伊「荒野变形」的形态筛选与面板换算。

数据来自 dnd55e/data/monsters.json（SRD 野兽，CR 0–6）。

2024 规则「属性值替换」：变形后力量/敏捷/体质、AC、速度、感官、攻击
全部改用形态数据；智力/感知/魅力、HP 与生命骰、熟练加值、熟练项、专长、
职业特性保留本体的。这里的纯函数只负责「算」，写回角色的部分在
Character 里（core/base.py 的 score 覆盖、core/derived.py 的 ac/speed）。
"""

from . import consts

# 2024 德鲁伊 荒野变形 CR 上限：(等级, CR)
_DRUID_CAP = ((8, 1.0), (4, 0.5), (2, 0.25))
# 2024 大地结社 Circle of the Moon 上限（3 级选子职后才生效）
# Circle Forms 原文: 上限 = 德鲁伊等级 // 3, 且不超过 6 —— 下表等价。
_MOON_CAP = ((18, 6.0), (15, 5.0), (12, 4.0), (9, 3.0), (6, 2.0), (3, 1.0))
# 2024 Beast Shapes 表「Known Forms」: 2 级 4 / 4 级 6 / 8 级 8
_KNOWN_FORMS = ((8, 8), (4, 6), (2, 4))


def _cap(table, level):
    for lv, cr in table:
        if level >= lv:
            return cr
    return None


def cr_num(m):
    return float(m.get("cr_num") or 0)


def known_forms(level):
    """2024 规则: 已知形态数量 (2/4/8 级 → 4/6/8), 1 级为 0"""
    return _cap(_KNOWN_FORMS, level) or 0


def cap_for(level, subclass=None):
    """当前等级的可选 CR 上限；不可变形返回 None"""
    if level < 2:
        return None
    if subclass == "Circle of the Moon" and level >= 3:
        return _cap(_MOON_CAP, level)
    return _cap(_DRUID_CAP, level)


def fly_ok(level):
    """飞行速度形态从 8 级起可选 (2024 规则; 月环不例外)"""
    return level >= 8


def swim_ok(level):
    """游泳速度形态从 4 级起可选 (2024 规则; 月环不例外)"""
    return level >= 4


def temp_hp(level, subclass=None):
    """变形时获得的临时 HP: 德鲁伊等级; 月环 3 级起为 3×等级"""
    if level < 2:
        return 0
    if subclass == "Circle of the Moon" and level >= 3:
        return 3 * level
    return level


def suggested_ac(base_ac, wis_mod, level, subclass=None):
    """月环 3 级起: AC = max(形态 AC, 13 + 感知调整值)"""
    if subclass == "Circle of the Moon" and level >= 3:
        return max(int(base_ac or 0), 13 + int(wis_mod))
    return int(base_ac or 0)


def ac_for(m, wis_mod, level, subclass=None):
    """变形后的 AC 与来源说明 (月环可被 13+感知 抬起来)"""
    base = int(m.get("ac") or 10)
    ac = suggested_ac(base, wis_mod, level, subclass)
    note = m.get("ac_note") or "天生护甲"
    if ac > base:
        return ac, f"野兽形态 {base} → 大地结社 13+感知 = {ac}"
    return ac, f"野兽形态 AC {ac}（{note}）"


def speeds(m):
    """形态的速度字典 {'walk': 40, 'fly': 0, ...}，0 值剔除"""
    sp = m.get("speed") or {}
    out = {}
    for key in ("walk", "climb", "fly", "swim", "burrow"):
        v = int(sp.get(key) or 0)
        if v:
            out[key] = v
    out["hover"] = bool(sp.get("hover"))
    return out


def senses(m):
    """形态的特殊感官 {'darkvision': 60, 'blindsight': 30, ...}"""
    out = {}
    for key in ("darkvision", "blindsight", "tremorsense", "truesight"):
        v = int((m.get("senses") or {}).get(key) or 0)
        if v:
            out[key] = v
    return out


def attacks(m):
    """形态里能掷的攻击动作 (剔除多重攻击这种纯说明项)"""
    out = []
    for a in (m.get("actions") or []):
        if a.get("attack_bonus") is None and a.get("dc") is None:
            continue
        out.append(a)
    return out


def skill_note(m):
    """形态自带的技能加值（只作参考: 2024 变形保留的是「你自己的」熟练项）"""
    sk = m.get("skills") or {}
    return "、".join(f"{k} +{v}" for k, v in sk.items())


def shapes(level, subclass=None):
    """可选野兽形态。

    2024 规则的门槛: 2 级起可变形; 2 级不能带飞行/游泳;
    4 级起可带游泳; 8 级起可带飞行 (月环只提高 CR, 不放宽速度限制)。
    本程序列出全部符合条件形态供参考, 「已知形态 N 种」由 known_forms 给出。
    """
    cap = cap_for(level, subclass)
    if cap is None:
        return []
    can_fly = fly_ok(level)
    can_swim = swim_ok(level)
    out = []
    for m in consts.MONSTERS:
        if m.get("companion"):
            continue          # 游侠野兽伙伴的 stat block 不是德鲁伊形态
        if cr_num(m) > cap + 1e-9:
            continue
        sp = m.get("speed") or {}
        if not can_fly and sp.get("fly"):
            continue
        if not can_swim and sp.get("swim"):
            continue
        out.append(m)
    return sorted(out, key=lambda m: (cr_num(m), m["name"]))


def summary(m):
    """一行摘要：CR / AC / HP / 速度"""
    sp = m.get("speed") or {}
    bits = [f"CR {m.get('cr')}", f"AC {m.get('ac')}", f"HP {m.get('hp')}"]
    for key, cn in (("walk", "步行"), ("fly", "飞行"),
                    ("swim", "游泳"), ("climb", "攀爬"), ("burrow", "掘地")):
        if sp.get(key):
            bits.append(f"{cn} {sp[key]}")
    return " · ".join(bits)


def attack_line(action):
    """把一条攻击动作转成掷骰用的一行说明"""
    if action.get("kind") == "save":
        return (f"{action.get('name')}（{action.get('save')} 豁免 "
                f"DC {action.get('dc')}）{action.get('desc', '')}")
    if action.get("attack_bonus") is None:
        return f"{action.get('name')}：{action.get('desc', '')}"
    rng = action.get("range")
    reach = f"触及 {action.get('reach')} 尺" if action.get("reach") else ""
    if rng:
        reach = f"射程 {rng[0]}/{rng[1]} 尺"
    dmg = action.get("damage") or ""
    parts = action.get("damage_parts") or []
    if parts:
        dmg = " + ".join(f"{p.get('damage')} {p.get('damage_type')}" for p in parts)
    else:
        dmg = f"{dmg} {action.get('damage_type') or ''}".strip()
    return (f"{action.get('name')}：命中 +{action.get('attack_bonus')}，"
            f"{reach}，伤害 {dmg}")
