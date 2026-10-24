# -*- coding: utf-8 -*-
"""校验 dnd55e/data/summons.json（法术召唤物 stat block）。

运行：python _summoncheck.py
退出码 0 表示全部通过。

与 _moncheck.py 的区别：召唤物的 AC / HP 是随施法环级变化的**公式字符串**，
cr 恒为 null，所以这里不校验 CR 分档与数值范围，只校验结构与文案完整性。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "dnd55e", "data", "summons.json")
SPELL_PATH = os.path.join(ROOT, "dnd55e_spells.json")

SIZES = {"微型", "小型", "中型", "大型", "巨型", "超巨型"}
TYPES = {"beast", "aberration", "celestial", "construct", "dragon",
         "elemental", "fey", "fiend", "undead", "celestial/fey/fiend"}
KINDS = {"melee", "ranged", "save", "multiattack", "other"}
DICE_RE = re.compile(r"^\d+$|^\d+d\d+([+-]\d+)?$")
CN_RE = re.compile(r"[\u4e00-\u9fff]")
EN_RE = re.compile(r"[A-Za-z]")
ID_RE = re.compile(r"^[a-z0-9_-]+$")

REQUIRED = ("id", "name", "name_cn", "name_en", "spell", "variant", "type",
            "size", "ac", "hp", "hp_dice", "speed", "abilities", "senses",
            "languages", "traits", "actions", "bonus_actions", "reactions",
            "note")

errors = []


def err(msg):
    errors.append(msg)


def check_attack(tag, a, where):
    """校验动作 / 特性条目的公共结构。"""
    if not isinstance(a, dict):
        err(f"{tag} {where} 不是对象")
        return
    name = a.get("name", "")
    if not name:
        err(f"{tag} {where} 缺 name")
        return
    if where == "traits":
        # 特性名必须中英混排（与 monsters.json 一致），desc 非空
        if not (CN_RE.search(name) and EN_RE.search(name)):
            err(f"{tag} 特性名须中英混排: {name}")
        if not a.get("desc"):
            err(f"{tag} 特性 {name} 缺 desc")
        return
    kind = a.get("kind")
    if kind not in KINDS:
        err(f"{tag} {where} {name} kind 非法: {kind}")
    if not (CN_RE.search(name) and EN_RE.search(name)):
        err(f"{tag} 动作名须中英混排: {name}")
    if not a.get("desc"):
        err(f"{tag} 动作 {name} 缺 desc")
    for k in ("attack_bonus", "damage", "damage_type", "save", "dc"):
        if k not in a:
            err(f"{tag} 动作 {name} 缺键 {k}（无值须显式 null）")
    if kind == "melee" and a.get("reach") is None:
        err(f"{tag} 动作 {name} kind=melee 必须有 reach")
    if kind == "ranged" and a.get("range") is None:
        err(f"{tag} 动作 {name} kind=ranged 必须有 range")


def main():
    if not os.path.exists(PATH):
        print(f"FAIL 找不到 {PATH}")
        return 1
    with open(PATH, encoding="utf-8") as f:
        data = json.load(f)

    ss = data.get("summons")
    if not isinstance(ss, list) or not ss:
        print("FAIL summons 不是非空数组")
        return 1
    if data.get("count") != len(ss):
        err(f"count={data.get('count')} 与实际 {len(ss)} 条不符")
    if not data.get("_note"):
        err("缺 _note 说明字段")

    spell_ids = set()
    if os.path.exists(SPELL_PATH):
        with open(SPELL_PATH, encoding="utf-8") as f:
            spell_ids = {s["id"] for s in json.load(f)["spells"]}
    else:
        err(f"找不到 {SPELL_PATH}")

    seen = set()
    for s in ss:
        sid = s.get("id", "<no-id>")
        tag = f"[{sid}]"

        for k in REQUIRED:
            if k not in s:
                err(f"{tag} 缺必填键 {k}")
        if not ID_RE.match(str(sid)):
            err(f"{tag} id 非法")
        if sid in seen:
            err(f"{tag} id 重复")
        seen.add(sid)

        name = s.get("name", "")
        if not (CN_RE.search(name) and EN_RE.search(name)):
            err(f"{tag} name 须「中文 English」混排: {name}")
        if s.get("name") not in (f"{s.get('name_cn')} {s.get('name_en')}"):
            err(f"{tag} name 与 name_cn / name_en 不一致")

        if s.get("type") not in TYPES:
            err(f"{tag} type 非法: {s.get('type')}")
        if s.get("size") not in SIZES and "/" not in str(s.get("size")):
            err(f"{tag} size 非法: {s.get('size')}")

        # AC / HP 是公式字符串：要么是固定数值，要么必须含中文说明
        for k in ("ac", "hp"):
            v = s.get(k)
            if not isinstance(v, str) or not v.strip():
                err(f"{tag} {k} 必须是非空字符串")
            elif not CN_RE.search(v) and not re.match(r"^\d+$", v.strip()):
                err(f"{tag} {k} 必须是固定数值或含中文的公式: {v}")

        ab = s.get("abilities") or {}
        if set(ab) != {"STR", "DEX", "CON", "INT", "WIS", "CHA"}:
            err(f"{tag} abilities 必须恰好 6 键")
        elif not all(isinstance(v, int) for v in ab.values()):
            err(f"{tag} abilities 值必须全是整数")

        spd = s.get("speed") or {}
        for k in ("walk", "climb", "fly", "swim", "burrow"):
            if k not in spd:
                err(f"{tag} speed 缺键 {k}")
            elif not isinstance(spd[k], int) or spd[k] < 0:
                err(f"{tag} speed.{k} 必须是非负整数")
        if not isinstance(spd.get("hover"), bool):
            err(f"{tag} speed.hover 必须是 bool")

        sns = s.get("senses") or {}
        for k in ("darkvision", "blindsight", "tremorsense", "truesight"):
            if not isinstance(sns.get(k), int):
                err(f"{tag} senses.{k} 必须是整数")
        if not isinstance(sns.get("passive_perception"), int):
            err(f"{tag} senses.passive_perception 必须是整数")

        if not s.get("languages"):
            err(f"{tag} languages 不能为空")

        for t in s.get("traits") or []:
            check_attack(tag, t, "traits")
        acts = s.get("actions")
        if not isinstance(acts, list) or not acts:
            err(f"{tag} actions 不能为空")
        else:
            for a in acts:
                check_attack(tag, a, "actions")
        for a in s.get("bonus_actions") or []:
            check_attack(tag, a, "bonus_actions")
        for a in s.get("reactions") or []:
            check_attack(tag, a, "reactions")

        sp = s.get("spell")
        if sp not in spell_ids:
            err(f"{tag} spell={sp} 在 dnd55e_spells.json 里不存在")

    # 每个 summon 法术至少有一条 stat block
    by_spell = {}
    for s in ss:
        by_spell.setdefault(s.get("spell"), []).append(s["id"])

    print(f"文件：{PATH}")
    print(f"总数：{len(ss)}    涉及法术：{len(by_spell)} 个")
    for sp in sorted(by_spell):
        print(f"  {sp}: {len(by_spell[sp])} 条")
    sizes = {}
    for s in ss:
        sizes[s.get("size")] = sizes.get(s.get("size"), 0) + 1
    print("体型分布：" + "  ".join(f"{k}={v}" for k, v in sorted(sizes.items())))

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
