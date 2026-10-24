# -*- coding: utf-8 -*-
"""魔能祈唤 / 攻击选项 数据校验 (改 data/invocations.json、attack_riders.json 后必跑)。

检查项:
  * id 唯一且是 kebab-case; 名称、说明非空
  * effects 只能用 Character.invocation_effects() 认识的 key, 且类型对
  * 等级前提在 1–20 之间; 攻击选项的 classes 必须是真实职业
  * damage 形如 NdM; dice_by_level 单调不减, 且门槛不低于条目等级
  * requires 指向真实存在的攻击选项
"""
import json
import os
import sys

from dnd55e.paths import BASE_DIR
from dnd55e.rules import Rules

FAIL = []

EFFECT_KEYS = {
    "pact_blade": bool, "blast_cha": bool, "blast_range": bool,
    "blast_push": bool, "armor_of_shadows": bool, "devils_sight": bool,
    "conc_adv": bool, "lifedrinker": bool, "swim_speed": bool,
    "extra_attack": int, "temp_hp": str,
}

r = Rules()
CLASSES = {c["id"] for c in r.d["classes"]}


def _kebab(s):
    """id 只允许小写字母/数字/-/_ (项目里两种分隔符都有)"""
    return bool(s) and all(ch.islower() or ch.isdigit() or ch in "-_"
                           for ch in s)


# ---- 魔能祈唤 ----
inv_raw = json.load(open(os.path.join(BASE_DIR, "dnd55e", "data",
                                      "invocations.json"), encoding="utf-8"))
invs = inv_raw["invocations"]
seen = set()
for v in invs:
    iid = v.get("id", "")
    if iid in seen:
        FAIL.append(f"祈唤 id 重复: {iid}")
    seen.add(iid)
    if not _kebab(iid):
        FAIL.append(f"祈唤 id 含非法字符: {iid}")
    if not str(v.get("name") or "").strip():
        FAIL.append(f"{iid}: 缺 name")
    if not str(v.get("desc") or "").strip():
        FAIL.append(f"{iid}: 缺 desc")
    lv = v.get("level", 1)
    if not isinstance(lv, int) or not 1 <= lv <= 15:
        FAIL.append(f"{iid}: level 非法 {lv}")
    for k, val in (v.get("effects") or {}).items():
        if k not in EFFECT_KEYS:
            FAIL.append(f"{iid}: 未知 effects key {k}")
            continue
        if EFFECT_KEYS[k] is bool and not isinstance(val, bool):
            FAIL.append(f"{iid}: {k} 应为 bool")
        if EFFECT_KEYS[k] is int and not isinstance(val, int):
            FAIL.append(f"{iid}: {k} 应为 int")
        if EFFECT_KEYS[k] is str and not isinstance(val, str):
            FAIL.append(f"{iid}: {k} 应为 str")
print(f"祈唤 {len(invs)} 条 · 可学等级 {sorted({v['level'] for v in invs})}")

# ---- 攻击选项 ----
rd_raw = json.load(open(os.path.join(BASE_DIR, "dnd55e", "data",
                                     "attack_riders.json"), encoding="utf-8"))
riders = rd_raw["riders"]
rids = {x["id"] for x in riders}
for x in riders:
    rid = x.get("id", "")
    if not _kebab(rid):
        FAIL.append(f"攻击选项 id 含非法字符: {rid}")
    if not str(x.get("desc") or "").strip():
        FAIL.append(f"{rid}: 缺 desc")
    for cid in (x.get("classes") or []):
        if cid not in CLASSES:
            FAIL.append(f"{rid}: 未知职业 {cid}")
    if not 1 <= int(x.get("level", 1)) <= 20:
        FAIL.append(f"{rid}: level 非法")
    dmg = x.get("damage")
    if dmg:
        parts = str(dmg).split("d")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            FAIL.append(f"{rid}: damage 不是 NdM 形式: {dmg}")
    prev = 0
    for need, cnt in (x.get("dice_by_level") or []):
        if need < int(x.get("level", 1)):
            FAIL.append(f"{rid}: dice_by_level 门槛 {need} 低于条目等级")
        if cnt < prev:
            FAIL.append(f"{rid}: dice_by_level 骰数不单调")
        prev = cnt
    req = x.get("requires")
    if req and req not in rids:
        FAIL.append(f"{rid}: requires 指向不存在的 {req}")
print(f"攻击选项 {len(riders)} 条: " + "、".join(
    f"{x['id']}({x['classes'][0]} {x['level']}级)" for x in riders))

# ---- 可用性: 每个职业在各等级都能正确筛出来 ----
for cid in CLASSES:
    for lv in range(1, 21):
        ch = __import__("dnd55e.character", fromlist=["Character"]).Character(r)
        ch.class_id, ch.level = cid, lv
        ch.invocations = [v["id"] for v in invs
                          if v["level"] <= lv][:ch.invocation_cap()]
        if len(ch.invocations) > ch.invocation_cap():
            FAIL.append(f"{cid} {lv} 级祈唤超上限")
        for row in ch.attack_riders():
            if int(row["level"]) > lv:
                FAIL.append(f"{cid} {lv} 级出现了未解锁的 {row['id']}")
print("各职业 × 1–20 级祈唤/攻击选项筛选正常")

if FAIL:
    print("\n" + "=" * 50)
    for f in FAIL:
        print("✗", f)
    sys.exit(1)
print("INVOCATIONCHECK OK")
