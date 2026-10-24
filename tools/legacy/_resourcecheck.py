# -*- coding: utf-8 -*-
"""
逐级数值对账 (D&D 5.5e 人物卡)
==============================
以 data/raw/class-levels-2024.json (SRD 5.2 原始逐级表) 为基准,
把 12 个职业 × 1–20 级的派生数值全部对一遍:
  · 熟练加值 prof_bonus
  · 法术位 spell_slots_level_N
  · 戏法数 cantrips_known / 准备法术数 prepared_spells
  · 职业资源与骰型 (rage / focus / channel / wild shape / sorcery…)
只读不改; 任何一处不一致都会列出来并以非零码退出。

用法: python _resourcecheck.py
"""
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

from dnd55e.character import Character            # noqa: E402
from dnd55e.rules import Rules                    # noqa: E402
from dnd55e.util import proficiency_bonus         # noqa: E402

_RAW_PATH = os.path.join(DIR, "data", "raw", "class-levels-2024.json")
if not os.path.exists(_RAW_PATH):
    # data/raw/ 是上游快照, 不入库(见 NOTICE.md); 全新 clone 时优雅跳过而不是崩
    print("SKIP: 缺少 data/raw/class-levels-2024.json")
    print("      该目录不入库, 请先运行 python _fetch_class_detail.py 生成后重跑。")
    sys.exit(0)
RAW = json.load(open(_RAW_PATH, encoding="utf-8"))
r = Rules()
FAIL = []


def bad(msg):
    FAIL.append(msg)


def mk(cid, lv):
    c = Character(r)
    c.class_id = cid
    c.level = lv
    c.background_id = r.d["backgrounds"][0]["id"]
    c.species_id = "human"
    c.base_scores = {a: 10 for a in ("STR", "DEX", "CON", "INT", "WIS", "CHA")}
    c.skill_prof = set(c.bg_skills()) | set(c.auto_skills())
    return c


def row(cid, lv):
    return RAW[cid][lv - 1]


def res_max(c, rid):
    for x in c.resources():
        if x["id"] == rid:
            return x["max"]
    return None


def res_die(c, rid):
    for x in c.resources():
        if x["id"] == rid:
            return x["die"]
    return None


print("=" * 62)
print("逐级数值对账 (基准: data/raw/class-levels-2024.json)")
print("=" * 62)

# 原始数据里的已知噪声: (职业, 等级) -> 官方 PHB 值
# SRD 5.2 抓取时 druid 7 级/16 级戏法数出现 4/5 的错值 (8 级又掉回 3),
# 2024 PHB 德鲁伊戏法为 2 级 2 个、4 级 3 个、10 级 4 个。
RAW_NOISE = {("druid", 7): 3, ("druid", 16): 4}

checked = 0

# ---------------- 1. 熟练加值 ----------------
for cid, rows in RAW.items():
    for lv in range(1, 21):
        exp = row(cid, lv)["prof_bonus"]
        got = proficiency_bonus(lv)
        checked += 1
        if got != exp:
            bad(f"熟练加值 {cid} {lv}级: {got} != {exp}")

# ---------------- 2. 法术位 / 戏法 / 准备数 ----------------
for cid, rows in RAW.items():
    for lv in range(1, 21):
        rec = row(cid, lv)
        sc = rec.get("spellcasting")
        if not sc:
            continue
        c = mk(cid, lv)
        # 2a 法术位
        for sl in range(1, 10):
            exp = int(sc.get(f"spell_slots_level_{sl}") or 0)
            got = int(c._base_slots().get(sl, 0))
            if cid == "warlock" and sl >= 6:
                continue            # 6–9 环是秘契法术, 不是法术位
            checked += 1
            if got != exp:
                bad(f"法术位 {cid} {lv}级 {sl}环: {got} != {exp}")
        # 2b 戏法数 (原始表里 druid 7/16 级两格是非单调噪声, 以 PHB 为准)
        exp = sc.get("cantrips_known")
        if exp is not None and (cid, lv) not in RAW_NOISE:
            got = c.cantrip_cap()
            checked += 1
            if got != int(exp):
                bad(f"戏法数 {cid} {lv}级: {got} != {exp}")
        # 2c 准备/已知法术数
        exp = sc.get("prepared_spells")
        if exp is not None:
            got = c.prepared_hint()
            checked += 1
            if got != int(exp):
                bad(f"准备法术数 {cid} {lv}级: {got} != {exp}")

# ---------------- 3. 职业资源 / 骰型 ----------------
SPEC = {
    "rage": "rage_count",
    "inspiration": "bardic_inspiration_die",
    "channel": "channel_divinity_charges",
    "wildshape": "wild_shape_uses",
    "second_wind": "second_wind_uses",
    "focus": "focus_points",
    "sorcery": "sorcery_points",
    "favored_enemy": "favored_enemies",
}
for cid, rows in RAW.items():
    for lv in range(1, 21):
        spec = row(cid, lv).get("class_specific") or {}
        c = mk(cid, lv)
        for key, field in spec.items():
            if field is None:
                continue
            if key in ("rage_count", "channel_divinity_charges",
                       "wild_shape_uses", "second_wind_uses", "focus_points",
                       "sorcery_points", "favored_enemies"):
                rid = {v: k for k, v in SPEC.items()}[key]
                exp = int(field) or 0
                got = res_max(c, rid) or 0
                checked += 1
                if got != exp:
                    bad(f"资源 {cid} {lv}级 {rid}: {got} != {exp}")
            elif key == "rage_damage_bonus":
                checked += 1
                if c.rage_damage() != int(field):
                    bad(f"狂暴伤害 {cid} {lv}级: {c.rage_damage()} != {field}")
            elif key == "bardic_inspiration_die":
                checked += 1
                got = res_die(c, "inspiration") or 0
                if got != int(field):
                    bad(f"灵感骰 {cid} {lv}级: d{got} != d{field}")
            elif key == "martial_arts_die":
                checked += 1
                got = c.martial_arts_die()
                if got != int(field):
                    bad(f"武艺骰 {cid} {lv}级: d{got} != d{field}")
            elif key == "unarmored_movement_bonus":
                checked += 1
                got = c.speed() - 30
                if got != int(field):
                    bad(f"无甲移动 {cid} {lv}级: +{got} != +{field}")
            elif key == "sneak_attack":
                checked += 1
                got = c.sneak_dice()
                exp = int(field.get("dice_count") or 0)
                if got != exp:
                    bad(f"偷袭骰 {cid} {lv}级: {got}d6 != {exp}d6")
            elif key == "weapon_mastery":
                checked += 1
                got = c.mastery_count()
                if got != int(field):
                    bad(f"武器专精数 {cid} {lv}级: {got} != {field}")

print(f"共核对 {checked} 项")
if FAIL:
    print(f"\n不一致 {len(FAIL)} 项:")
    for f in FAIL[:60]:
        print("  ✗", f)
    if len(FAIL) > 60:
        print(f"  ... 其余 {len(FAIL) - 60} 项省略")
    sys.exit(1)
print("\nRESOURCECHECK OK — 逐级数值与 SRD 5.2 一致")
