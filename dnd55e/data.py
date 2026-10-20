# -*- coding: utf-8 -*-
"""按需加载 data/*.json 的规则数据 (lru_cache, 首次使用时才读盘)。"""
import json
import os
from functools import lru_cache

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@lru_cache(maxsize=None)
def _load(name):
    with open(os.path.join(DATA_DIR, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


# ---- 属性 / 点数 ----
def abilities():
    return list(_load("abilities")["abilities"])


def ability_cn():
    return dict(_load("abilities")["ability_cn"])


def ability_desc():
    return dict(_load("abilities")["ability_desc"])


def point_cost():
    return {int(k): v for k, v in _load("abilities")["point_cost"].items()}


def standard_array():
    return list(_load("abilities")["standard_array"])


# ---- 技能 / 状态 / 术语 ----
def skill_desc():
    return dict(_load("skills")["skill_desc"])


def conditions():
    return list(_load("skills")["conditions"])


def condition_desc():
    return dict(_load("skills")["condition_desc"])


def tool_cn():
    return dict(_load("skills")["tool_cn"])


def size_cn():
    return dict(_load("skills")["size_cn"])


def weapon_prof_cn():
    return dict(_load("skills")["weapon_prof_cn"])


def armor_prof_cn():
    return dict(_load("skills")["armor_prof_cn"])


def cast_type_cn():
    return dict(_load("skills")["cast_type_cn"])


def cast_mode_cn():
    return dict(_load("skills")["cast_mode_cn"])


# ---- 武器 / 护甲 / 物品 ----
def weapons():
    return [tuple(w) for w in _load("weapons")["weapons"]]


def light_weapons():
    return set(_load("weapons")["light"])


def finesse_weapons():
    return set(_load("weapons")["finesse"])


def weapon_props():
    """武器属性表: {名称: [light/finesse/two_handed/versatile/ranged/thrown/...]}

    2024 规则里的「双手/远程/灵巧/轻型」原本靠中文名猜, 容易漏
    (例如大棒 Greatclub 是双手武器但名字里没有「巨/大剑」), 改成数据驱动。
    """
    return {w[0]: list(w[4]) if len(w) > 4 else []
            for w in _load("weapons")["weapons"]}


def versatile_dice():
    """两用武器双手持用时的伤害骰 {名称: '1d10'}"""
    return {w[0]: w[5] for w in _load("weapons")["weapons"] if len(w) > 5}


def mastery_desc():
    return dict(_load("weapons")["mastery_desc"])

def mastery_cn_map():
    return dict(_load("weapons")["mastery_cn"])


def armors():
    return [tuple(a) for a in _load("armors")["armors"]]


def armor_cats():
    return list(_load("armors")["cats"])


def armor_cats_cn():
    return dict(_load("armors")["cats_cn"])


def armor_str_req():
    """重甲的力量需求 (不满足则速度 -10 尺, 2024 规则)"""
    return list(_load("armors")["str_req"])


def armor_stealth():
    """该护甲是否让隐匿检定带劣势"""
    return list(_load("armors")["stealth"])


def magic_items():
    return [dict(i) for i in _load("items")["items"]]


def items_by_id():
    return {i["id"]: i for i in magic_items()}


# ---- 专长 ----
def feat_info():
    return {k: tuple(v) for k, v in _load("feats")["origin"].items()}


def general_feats():
    """2024 PHB 通用专长 / 战斗风格 / 传奇恩惠
    返回 {分类: {英文名: {cn, prereq, desc, effects, ...}}}"""
    raw = _load("feats_general")
    return {sec: {k: dict(v) for k, v in (raw.get(sec) or {}).items()}
            for sec in ("general", "fighting_style", "epic_boon")}


def feats_by_name():
    """全表拍平: {英文名: {**字段, '_sec': 分类}}"""
    out = {}
    for sec, rows in general_feats().items():
        for k, v in rows.items():
            item = dict(v)
            item["_sec"] = sec
            out[k] = item
    return out


# ---- 野兽形态 (荒野变形 / 野兽伙伴 / 变形术) ----
def monsters():
    return [dict(m) for m in _load("monsters")["monsters"]]


def monsters_by_id():
    return {m["id"]: m for m in monsters()}


# ---- 法术召唤物 (Summon X / 变形术 / 寻获坐骑 / 活化物件) ----
def summons():
    return [dict(s) for s in _load("summons")["summons"]]


def summons_by_id():
    return {s["id"]: s for s in summons()}


# ---- 职业相关文案 ----
def subclass_cn():
    return dict(_load("classes_ui")["subclass_cn"])


def fighting_styles():
    return {k: (v[0], v[1], v[2])
            for k, v in _load("classes_ui")["fighting_styles"].items()}


def style_min_level():
    return dict(_load("classes_ui")["style_min_level"])


def orders():
    """1 级职阶 (牧师 神圣职阶 / 德鲁伊 原始职阶)"""
    return {k: {kk: tuple(vv) for kk, vv in v.items()}
            for k, v in _load("classes_ui").get("orders", {}).items()}


def spell_counts():
    return {k: tuple(v) for k, v in _load("classes_ui")["spell_counts"].items()}


def metamagic_options():
    """2024 超魔法: {id: (名称, 术法点, 说明, 可叠加)}"""
    raw = _load("metamagic")["options"]
    return {k: (v["name"], int(v["cost"]), v["desc"], bool(v["stack"]))
            for k, v in raw.items()}


def _lv_rows(row):
    """{"3": [...]} -> {3: [...]}"""
    return {int(lv): list(ids) for lv, ids in row.items()}


def fixed_spells():
    """始终准备的法术 (职业特性 + 子职), 不占准备配额
    {"class": {cid: {lv: [sid]}},
     "subclass": {sid: {"table": {lv: [sid]}} 或 {"land": {land: {lv: [sid]}}}}
    """
    raw = _load("fixed_spells")
    subs = {}
    for sid, row in raw["subclass"].items():
        if "land" in row:
            subs[sid] = {"land": {land: _lv_rows(t) for land, t in row["land"].items()}}
        else:
            subs[sid] = {"table": _lv_rows(row)}
    return {"class": {cid: _lv_rows(r) for cid, r in raw["class"].items()},
            "subclass": subs}


def font_of_magic():
    """术士·术法源泉: {环级: 术法点代价} + 上限环级 + 说明"""
    raw = _load("classes_ui")["font_of_magic"]
    return {"cost": {int(k): v for k, v in raw["cost"].items()},
            "max_slot_level": int(raw["max_slot_level"]),
            "note": raw["note"]}


def half_slots():
    return {int(lv): {int(a): b for a, b in row.items()}
            for lv, row in _load("classes_ui")["half_slots"].items()}


def prepared_spells():
    """逐级「准备法术数」上限 (2024 各职业表, 不是等级+属性调整值)"""
    return {k: {int(lv): v for lv, v in row.items()}
            for k, row in _load("classes_ui")["prepared_spells"].items()}


def cantrips_known():
    """逐级「戏法数」上限"""
    return {k: {int(lv): v for lv, v in row.items()}
            for k, row in _load("classes_ui")["cantrips_known"].items()}


def third_caster():
    """1/3 施法者子职 (奥法骑士 / 诡术师): 逐级 戏法/准备数/法术位"""
    out = {}
    for sub, ent in _load("classes_ui")["third_caster"].items():
        tbl = {}
        for lv, row in ent["table"].items():
            tbl[int(lv)] = (int(row[0]), int(row[1]),
                            {int(k): v for k, v in row[2].items()})
        out[sub] = {**{k: v for k, v in ent.items() if k != "table"},
                    "table": tbl}
    return out


# ---- 种族 ----
def _species():
    return _load("species")


def species_skill_bonus():
    return dict(_species()["skill_bonus"])


def species_auto_skills():
    return dict(_species()["auto_skills"])


def legacy_species():
    return dict(_species()["legacy"])


def legacy_species_cn():
    return dict(_species()["legacy_cn"])


def species_spells():
    return _species()["spells"]


def lineage_cn():
    return dict(_species()["lineage_cn"])


