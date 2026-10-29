"""校验 dnd55e/data/items.json（魔法物品数据）。

用法: python _itemcheck.py
退出码 0 = 全部通过; 1 = 有问题。
"""

import json
import os
import re
import sys

from _path import PROJECT_ROOT as HERE           # 项目根（本脚本在 tools/legacy/）
PATH = os.path.join(HERE, "dnd55e", "data", "items.json")
RAW = os.path.join(HERE, "data", "raw", "magic-items.json")

# ---------------------------------------------------------------- 枚举 / 白名单

RARITIES = {"common", "uncommon", "rare", "very_rare", "legendary", "artifact", "varies"}
KINDS = {"ring", "cloak", "armor", "weapon", "wand", "staff", "wondrous",
         "potion", "scroll", "ammunition"}

DAMAGE_TYPES = {"acid", "bludgeoning", "cold", "fire", "force", "lightning",
                "necrotic", "piercing", "poison", "psychic", "radiant",
                "slashing", "thunder"}

CONDITIONS = {"blinded", "charmed", "deafened", "exhaustion", "frightened",
              "grappled", "incapacitated", "invisible", "paralyzed",
              "petrified", "poisoned", "prone", "restrained", "stunned",
              "unconscious"}

FIELDS = {
    "id", "name", "note", "attune",
    "ac", "save", "check", "no_armor", "speed_mult", "base_ac",
    "set_str", "set_dex", "set_con", "set_int", "set_wis", "set_cha",
    "rarity", "kind", "desc", "ac_bonus_armor", "attack", "damage",
    "spell_dc", "spell_attack", "hp_bonus", "resist", "immune",
    "condition_immune", "charges", "charge_note", "speed_bonus", "note_only",
}
INT_FIELDS = {
    "ac", "save", "check", "speed_mult", "base_ac", "set_str", "set_dex",
    "set_con", "set_int", "set_wis", "set_cha", "ac_bonus_armor", "attack",
    "damage", "spell_dc", "spell_attack", "hp_bonus", "charges", "speed_bonus",
}
LIST_FIELDS = {"resist", "immune", "condition_immune"}
BOOL_FIELDS = {"attune", "no_armor", "note_only"}
STR_FIELDS = {"id", "name", "note", "rarity", "kind", "desc", "charge_note"}

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")

# ------------------------------------------------- 原 12 条快照（回归基线）
# 这些 id 被存档引用，字段值一旦变化会毁档。
SNAPSHOT = {
    "ring_protection": {"name": "防护戒指 Ring of Protection", "ac": 1, "save": 1,
                        "note": "AC +1，豁免 +1（需同调）", "attune": True},
    "cloak_protection": {"name": "防护斗篷 Cloak of Protection", "ac": 1, "save": 1,
                         "note": "AC +1，豁免 +1（需同调）", "attune": True},
    "bracers_defense": {"name": "防御护腕 Bracers of Defense", "ac": 2,
                        "no_armor": True, "note": "无甲且无盾时 AC +2",
                        "attune": True},
    "cloak_elvenkind": {"name": "精灵斗篷 Cloak of Elvenkind",
                        "note": "隐匿检定优势（隐蔽时）", "attune": True},
    "boots_elvenkind": {"name": "精灵靴 Boots of Elvenkind",
                        "note": "潜行移动不发出声音", "attune": False},
    "boots_speed": {"name": "速度之靴 Boots of Speed", "attune": True,
                    "note": "附赠动作点脚跟: 步行速度翻倍（需同调）",
                    "speed_mult": 2},
    "gauntlets_ogre": {"name": "食人魔力量手套 Gauntlets of Ogre Power",
                       "set_str": 19, "note": "力量变为 19（不叠加）",
                       "attune": True},
    "belt_hill_giant": {"name": "山丘巨人力量腰带 Belt of Hill Giant Strength",
                        "set_str": 21, "note": "力量变为 21", "attune": True},
    "headband_intellect": {"name": "智力头带 Headband of Intellect",
                           "set_int": 19, "note": "智力变为 19", "attune": True},
    "amulet_health": {"name": "健康护符 Amulet of Health", "set_con": 19,
                      "note": "体质变为 19", "attune": True},
    "ring_free_action": {"name": "自由行动戒指 Ring of Free Action",
                         "note": "免疫束缚与麻痹、移动不受魔法限制", "attune": True},
    "stone_luck": {"name": "幸运石 Stone of Good Luck", "save": 1, "check": 1,
                   "note": "豁免与属性检定 +1（需同调）", "attune": True},
}

errors = []
warns = []

# 同名归并: 变体条目与原始库里合并成一条的物品 (id → raw index)
RAW_ALIAS = {
    "belt_hill_giant": "belt-of-giant-strength",
    "belt_stone_giant": "belt-of-giant-strength",
    "belt_fire_giant": "belt-of-giant-strength",
    "belt_cloud_giant": "belt-of-giant-strength",
    "belt_storm_giant": "belt-of-giant-strength",
    "shield_plus1": "shield-1", "shield_plus2": "shield-2",
    "shield_plus3": "shield-3",
    "armor_plus1": "armor-1", "armor_plus2": "armor-2",
    "armor_plus3": "armor-3",
    "weapon_plus1": "weapon-1", "weapon_plus2": "weapon-2",
    "weapon_plus3": "weapon-3",
    "ammunition_plus1": "ammunition-1", "ammunition_plus2": "ammunition-2",
    "ammunition_plus3": "ammunition-3",
    "wand_war_mage_plus1": "wand-of-the-war-mage-1",
    "wand_war_mage_plus2": "wand-of-the-war-mage-2",
    "wand_war_mage_plus3": "wand-of-the-war-mage-3",
    "ioun_stone_protection": "ioun-stone",
    "ioun_stone_agility": "ioun-stone",
    "ioun_stone_strength": "ioun-stone",
    "ioun_stone_insight": "ioun-stone",
    "stone_luck": "stone-of-good-luck-(luckstone)",
}


def _norm(s):
    s = s.lower().replace("+", "").replace(",", "")
    s = s.replace("(", "").replace(")", "").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def check_attune(items):
    """逐条比对原始数据 data/raw/magic-items.json 的 attunement 布尔值。"""
    if not os.path.exists(RAW):
        warns.append("找不到 raw/magic-items.json，跳过 attune 交叉核对")
        return
    with open(RAW, encoding="utf-8") as f:
        raws = json.load(f)["items"]
    byname = {}
    for r in raws:
        byname.setdefault(_norm(r["name"]), r)
    for it in items:
        iid = it.get("id", "?")
        nm = it.get("name") or ""
        en = nm.split(" ", 1)[1] if " " in nm else nm
        r = None
        key = RAW_ALIAS.get(iid)
        if key:
            r = next((x for x in raws if x["index"] == key), None)
        if r is None:
            r = byname.get(_norm(en))
        if r is None:
            r = byname.get(re.sub(r" \+\d$", "", _norm(en)))
        if r is None:
            warns.append("%s: 原始库找不到同名条目，attune 未交叉核对" % iid)
            continue
        if bool(it.get("attune")) != bool(r.get("attunement")):
            err("%s: attune=%s 与 2024 原文(%s) 不一致"
                % (iid, it.get("attune"), r.get("attunement")))


def err(msg):
    errors.append(msg)


def main():
    if not os.path.exists(PATH):
        print("找不到 %s" % PATH)
        return 1
    with open(PATH, encoding="utf-8") as f:
        raw = f.read()
    try:
        data = json.loads(raw)
    except Exception as e:                                  # noqa: BLE001
        print("JSON 解析失败: %s" % e)
        return 1
    if raw and not raw.endswith("\n"):
        err("文件末尾缺少换行")
    if "\\u" in raw:
        warns.append("文件含 \\uXXXX 转义（应为 ensure_ascii=False）")

    items = data.get("items")
    if not isinstance(items, list):
        print("顶层缺少 items 数组")
        return 1
    if not isinstance(data.get("_note"), str) or "note_only" not in data["_note"]:
        err("顶层 _note 缺失或未说明 note_only 语义")

    seen = set()
    names = {}
    for i, it in enumerate(items):
        tag = it.get("id", "#%d" % i) if isinstance(it, dict) else "#%d" % i
        if not isinstance(it, dict):
            err("%s: 不是对象" % tag)
            continue

        # --- 未知字段
        unknown = set(it) - FIELDS
        if unknown:
            err("%s: 出现未允许的字段 %s" % (tag, sorted(unknown)))

        # --- id
        iid = it.get("id")
        if not isinstance(iid, str) or not iid:
            err("%s: id 缺失或非字符串" % tag)
        else:
            if not ID_RE.match(iid):
                err("%s: id 不是小写蛇形" % iid)
            if iid != iid.lower():
                err("%s: id 含大写" % iid)
            if iid in seen:
                err("%s: id 重复" % iid)
            seen.add(iid)

        # --- name: 中文 + 英文
        nm = it.get("name")
        if not isinstance(nm, str) or not nm.strip():
            err("%s: name 缺失" % tag)
        else:
            if not CJK_RE.search(nm):
                err("%s: name 缺中文（%s）" % (tag, nm))
            if not LATIN_RE.search(nm):
                err("%s: name 缺英文（%s）" % (tag, nm))
            m = re.search(r"[A-Za-z]", nm)
            if m and not re.search(r"[\u4e00-\u9fff]", nm[:m.start()]):
                err("%s: name 不是「中文 English」顺序（%s）" % (tag, nm))
            if nm in names:
                err("%s: name 与 %s 重复" % (tag, names[nm]))
            names[nm] = tag

        # --- 枚举
        rar = it.get("rarity")
        if rar is None:
            err("%s: 缺 rarity" % tag)
        elif rar not in RARITIES:
            err("%s: rarity 非法 %r" % (tag, rar))
        kind = it.get("kind")
        if kind is None:
            err("%s: 缺 kind" % tag)
        elif kind not in KINDS:
            err("%s: kind 非法 %r" % (tag, kind))

        # --- 类型
        for k, v in it.items():
            if k in INT_FIELDS:
                if not isinstance(v, int) or isinstance(v, bool):
                    err("%s: %s 应为 int, 实为 %r" % (tag, k, v))
            elif k in BOOL_FIELDS:
                if not isinstance(v, bool):
                    err("%s: %s 应为 bool, 实为 %r" % (tag, k, v))
            elif k in STR_FIELDS:
                if not isinstance(v, str):
                    err("%s: %s 应为 str, 实为 %r" % (tag, k, v))
            elif k in LIST_FIELDS:
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    err("%s: %s 应为字符串列表, 实为 %r" % (tag, k, v))

        # --- 伤害类型 / 状态白名单
        for k in ("resist", "immune"):
            for t in it.get(k, []):
                if t not in DAMAGE_TYPES:
                    err("%s: %s 含非法伤害类型 %r" % (tag, k, t))
                if t != t.lower():
                    err("%s: %s 必须小写 %r" % (tag, k, t))
        for c in it.get("condition_immune", []):
            if c not in CONDITIONS:
                err("%s: condition_immune 含非法状态 %r" % (tag, c))

        # --- 语义小检查
        if it.get("note_only") and it.get("attune") is None:
            warns.append("%s: note_only 但缺 attune" % tag)
        if it.get("charges") is not None and not it.get("charge_note"):
            warns.append("%s: 有 charges 但缺 charge_note" % tag)
        if not it.get("desc") and not it.get("note"):
            warns.append("%s: 既无 desc 也无 note" % tag)
        ba = it.get("base_ac")
        if ba is not None:
            if not it.get("no_armor"):
                err("%s: 有 base_ac 但没有 no_armor（无法确定生效条件）" % tag)
            if isinstance(ba, int) and not isinstance(ba, bool) and ba < 10:
                err("%s: base_ac=%d 明显偏低（应为 10 以上）" % (tag, ba))
        # note_only 与数值字段可以共存（见 _note 的定义），这里不做互斥断言

    # --- attune 与原始数据交叉核对
    check_attune(items)

    # --- 原 12 条回归
    by_id = {i.get("id"): i for i in items if isinstance(i, dict)}
    for iid, snap in SNAPSHOT.items():
        cur = by_id.get(iid)
        if cur is None:
            err("回归: 原条目 %s 丢失" % iid)
            continue
        for k, v in snap.items():
            if k not in cur:
                err("回归: %s.%s 被删除" % (iid, k))
            elif cur[k] != v:
                err("回归: %s.%s 由 %r 变为 %r" % (iid, k, v, cur[k]))

    # --- 统计
    rc, kc = {}, {}
    note_only = 0
    unverified = 0
    for it in items:
        rc[it.get("rarity", "?")] = rc.get(it.get("rarity", "?"), 0) + 1
        kc[it.get("kind", "?")] = kc.get(it.get("kind", "?"), 0) + 1
        if it.get("note_only"):
            note_only += 1
        if not it.get("desc"):
            unverified += 1

    print("=" * 58)
    print("条目总数: %d" % len(items))
    print("rarity 分布: %s" % ", ".join(
        "%s=%d" % (k, rc[k]) for k in sorted(rc, key=lambda x: -rc[x])))
    print("kind   分布: %s" % ", ".join(
        "%s=%d" % (k, kc[k]) for k in sorted(kc, key=lambda x: -kc[x])))
    print("note_only 条数: %d" % note_only)
    print("未核实条数(缺 desc): %d" % unverified)
    print("原 12 条回归: %s" % ("通过" if not any(
        e.startswith("回归") for e in errors) else "失败"))
    if warns:
        print("-" * 58)
        print("提示 %d 条:" % len(warns))
        for w in warns:
            print("  ! " + w)
    print("-" * 58)
    if errors:
        print("错误 %d 条:" % len(errors))
        for e in errors:
            print("  x " + e)
        print("=" * 58)
        print("校验未通过")
        return 1
    print("校验通过")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    sys.exit(main())
