# -*- coding: utf-8 -*-
"""校验 dnd55e/data/monsters.json。

运行：python _moncheck.py
退出码 0 表示全部通过。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "dnd55e", "data", "monsters.json")

CR_TIERS = ["0", "1/8", "1/4", "1/2", "1", "2", "3", "4", "5", "6"]
CR_NUM = {"0": 0, "1/8": 0.125, "1/4": 0.25, "1/2": 0.5}
SIZES = {"微型", "小型", "中型", "大型", "巨型", "超巨型"}
DAMAGE_TYPES = {"穿刺", "挥砍", "钝击", "毒素", "强酸", "火焰", "冷冻",
                "闪电", "雷鸣", "黯蚀", "光耀", "心灵", "力场"}
DICE_RE = re.compile(r"^\d+$|^\d+d\d+([+-]\d+)?$")
CN_RE = re.compile(r"[\u4e00-\u9fff]")
EN_RE = re.compile(r"[A-Za-z]")

errors = []


def err(msg):
    errors.append(msg)


def main():
    if not os.path.exists(PATH):
        print(f"FAIL 找不到 {PATH}")
        return 1
    with open(PATH, encoding="utf-8") as f:
        data = json.load(f)

    ms = data.get("monsters")
    if not isinstance(ms, list) or not ms:
        print("FAIL monsters 不是非空数组")
        return 1

    seen_ids = set()
    for m in ms:
        mid = m.get("id", "<no-id>")
        tag = f"[{mid}]"

        # --- id ---
        if not re.match(r"^[a-z0-9_-]+$", str(mid)):
            err(f"{tag} id 非法")
        if mid in seen_ids:
            err(f"{tag} id 重复")
        seen_ids.add(mid)

        # --- 必填 ---
        for k in ("id", "name", "cr", "cr_num", "xp", "size", "ac", "hp",
                  "hp_dice", "speed", "abilities", "saves", "skills", "senses",
                  "languages", "traits", "actions", "bonus_actions",
                  "reactions", "edition", "source"):
            if k not in m:
                err(f"{tag} 缺字段 {k}")

        # --- 名称格式 中文 English ---
        for k in ("name",):
            v = m.get(k, "")
            if not (CN_RE.search(v) and EN_RE.search(v) and " " in v):
                err(f"{tag} {k} 不是「中文 English」格式：{v}")

        # --- cr ---
        cr = m.get("cr")
        cn = m.get("cr_num")
        if cr not in CR_NUM and not (isinstance(cr, str) and cr.isdigit()):
            err(f"{tag} cr 非法：{cr}")
        expect = CR_NUM.get(cr, int(cr) if isinstance(cr, str) and cr.isdigit() else None)
        if expect is not None and cn != expect:
            err(f"{tag} cr_num={cn} 与 cr={cr} 不符（应为 {expect}）")
        if not isinstance(cn, (int, float)):
            err(f"{tag} cr_num 不是数字")

        # --- size ---
        if m.get("size") not in SIZES:
            err(f"{tag} size 非法：{m.get('size')}")

        # --- ac / hp ---
        ac, hp = m.get("ac"), m.get("hp")
        if not isinstance(ac, int) or ac <= 0:
            err(f"{tag} ac 非正整数：{ac}")
        if not isinstance(hp, int) or hp <= 0:
            err(f"{tag} hp 非正整数：{hp}")

        # --- abilities ---
        ab = m.get("abilities") or {}
        for a in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
            if a not in ab:
                err(f"{tag} abilities 缺 {a}")
            elif not isinstance(ab[a], int):
                err(f"{tag} abilities.{a} 不是 int")
        if set(ab) != {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
            err(f"{tag} abilities 键多余：{sorted(set(ab) - {'STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA'})}")

        # --- speed ---
        sp = m.get("speed") or {}
        for k in ("walk", "climb", "fly", "swim"):
            if k not in sp:
                err(f"{tag} speed 缺 {k}")
            elif not isinstance(sp[k], int) or sp[k] < 0:
                err(f"{tag} speed.{k} 非非负整数：{sp[k]}")
        if not isinstance(sp.get("hover"), bool):
            err(f"{tag} speed.hover 不是 bool")

        # --- skills ---
        for sk, val in (m.get("skills") or {}).items():
            if not CN_RE.search(sk):
                err(f"{tag} skills 键不是中文：{sk}")
            if not isinstance(val, int):
                err(f"{tag} skills.{sk} 不是 int")

        # --- traits ---
        for t in m.get("traits") or []:
            if not (CN_RE.search(t.get("name", "")) and EN_RE.search(t.get("name", ""))):
                err(f"{tag} trait 名称格式不对：{t.get('name')}")
            if not t.get("desc"):
                err(f"{tag} trait 缺 desc：{t.get('name')}")

        # --- actions ---
        if not m.get("actions"):
            err(f"{tag} 没有任何 actions")
        for grp in ("actions", "bonus_actions", "reactions"):
            for a in m.get(grp) or []:
                an = a.get("name", "")
                if not (CN_RE.search(an) and EN_RE.search(an)):
                    err(f"{tag} 动作名称格式不对：{an}")
                if not a.get("desc"):
                    err(f"{tag} 动作缺 desc：{an}")
                kind = a.get("kind")
                if kind not in ("melee", "ranged", "save", "multiattack", "other"):
                    err(f"{tag} 动作 kind 非法：{an} -> {kind}")
                if kind in ("melee", "ranged"):
                    if not isinstance(a.get("attack_bonus"), int):
                        err(f"{tag} 攻击动作缺 int attack_bonus：{an}")
                    if not a.get("damage") or not DICE_RE.match(str(a["damage"])):
                        err(f"{tag} 攻击动作 damage 非法：{an} -> {a.get('damage')}")
                    if a.get("damage_type") not in DAMAGE_TYPES:
                        err(f"{tag} 攻击动作 damage_type 非法：{an} -> {a.get('damage_type')}")
                    if kind == "melee" and not isinstance(a.get("reach"), int):
                        err(f"{tag} 近战动作缺 int reach：{an}")
                    if kind == "ranged" and not (isinstance(a.get("range"), list) and len(a["range"]) == 2):
                        err(f"{tag} 远程动作缺 range[2]：{an}")
                if kind == "save":
                    if not isinstance(a.get("dc"), int):
                        err(f"{tag} 豁免动作缺 int dc：{an}")
                    if a.get("save") not in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
                        err(f"{tag} 豁免动作 save 非法：{an} -> {a.get('save')}")
                for p in a.get("damage_parts") or []:
                    if not DICE_RE.match(str(p.get("damage"))):
                        err(f"{tag} damage_parts 非法：{an} -> {p}")
                    if p.get("damage_type") not in DAMAGE_TYPES:
                        err(f"{tag} damage_parts 类型非法：{an} -> {p}")

    # --- CR 分档 ---
    counts = {t: 0 for t in CR_TIERS}
    for m in ms:
        cr = m.get("cr")
        if cr in counts:
            counts[cr] += 1
        else:
            err(f"[{m.get('id')}] cr={cr} 不在统计档位内")
    for t in CR_TIERS:
        need = 1 if t == "6" else 3
        if counts[t] < need:
            err(f"CR {t} 只有 {counts[t]} 只（需 >= {need}）")

    # --- 数量 ---
    if len(ms) < 45:
        err(f"总数 {len(ms)} < 45")

    # --- 汇总 ---
    fly = sum(1 for m in data["monsters"] if m["speed"].get("fly", 0) > 0)
    swim = sum(1 for m in data["monsters"] if m["speed"].get("swim", 0) > 0)
    old = sum(1 for m in data["monsters"] if m.get("edition") == "2014")

    print(f"文件：{PATH}")
    print(f"总数：{len(ms)}")
    print("各 CR 档：" + "  ".join(f"CR{t}={counts[t]}" for t in CR_TIERS))
    print(f"有飞行速度：{fly}    有游泳速度：{swim}    2014 补录：{old}")

    if errors:
        print(f"\nFAIL 共 {len(errors)} 处问题：")
        for e in errors[:60]:
            print("  -", e)
        if len(errors) > 60:
            print(f"  ... 另有 {len(errors) - 60} 处")
        return 1
    print("\nOK 全部校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
