# -*- coding: utf-8 -*-
"""一次性脚本：给 dnd55e_spells.json 补 8 个 Summon 法术 + 给已有法术加 summon 映射。

用法：python backup/_p6e_spells.py
       python backup/_p6e_spells.py --check
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "dnd55e_spells.json")

KEYS = ("id", "name_en", "name", "level", "school", "classes", "cast",
        "range", "comp", "duration", "concentration", "ritual", "damage",
        "damage_type", "save", "attack", "area", "area_type", "scaling",
        "desc", "desc_en")

CONC1H = "up to 1 小时"


def spell(sid, name_en, name, level, classes, mat_cn, mat_en, desc, desc_en,
          summon, rng="90 尺"):
    d = {
        "id": sid, "name_en": name_en, "name": name, "level": level,
        "school": "咒法", "classes": classes, "cast": "1 动作",
        "range": rng,
        "comp": f"语/姿/材（{mat_cn}）" if mat_cn else "语/姿",
        "duration": CONC1H, "concentration": True, "ritual": False,
        "damage": "", "damage_type": "", "save": "", "attack": False,
        "area": "", "area_type": "", "scaling": {},
        "desc": desc, "desc_en": desc_en, "summon": summon,
    }
    return d


COMMON_EN = (
    "It manifests in an unoccupied space that you can see within range. "
    "The creature disappears when it drops to 0 Hit Points or when the "
    "spell ends.\n  The creature is an ally to you and your allies. In "
    "combat, the creature shares your Initiative count, but it takes its "
    "turn immediately after yours. It obeys your verbal commands (no action "
    "required by you). If you don't issue any, it takes the Dodge action and "
    "uses its movement to avoid danger."
)

NEW = [
    spell(
        "summon-beast", "Summon Beast", "召唤野兽", 2, ["druid", "ranger"],
        "一枚镶金橡果内的羽毛、一撮毛皮和一条鱼尾，价值 200+ GP",
        "a feather, tuft of fur, and fish tail inside a gilded acorn worth "
        "200+ GP",
        "召唤一只精魂兽：选择陆行、水栖或空中形态（专注 1 小时）。",
        "You call forth a bestial spirit. Choose an environment when you cast "
        "the spell: Air, Land, or Water. The spirit uses the Bestial Spirit "
        "stat block, and the environment determines certain details in it. "
        + COMMON_EN,
        {"kind": "statblock",
         "options": [{"name": "陆行", "statblock": "bestial-spirit-land"},
                     {"name": "水栖", "statblock": "bestial-spirit-water"},
                     {"name": "空中", "statblock": "bestial-spirit-air"}],
         "note": "陆行/水栖的 HP 高于空中；空中形态有飞掠，可穿越敌人身边。"}),
    spell(
        "summon-fey", "Summon Fey", "召唤妖精", 3, ["druid", "ranger",
                                                    "warlock", "wizard"],
        "一朵镀金花，价值 300+ GP", "a gilded flower worth 300+ GP",
        "召唤一只妖精精魂：选择暴躁、欢愉或狡黠气质（专注 1 小时）。",
        "You call forth a fey spirit. It manifests in an unoccupied space that "
        "you can see within range. Choose a mood when you cast the spell: "
        "Fuming, Mirthful, or Tricksy. The spirit uses the Fey Spirit stat "
        "block, and the mood determines part of its Fey Step. " + COMMON_EN,
        {"kind": "statblock",
         "options": [{"name": "暴躁", "statblock": "fey-spirit-fuming"},
                     {"name": "欢愉", "statblock": "fey-spirit-mirthful"},
                     {"name": "狡黠", "statblock": "fey-spirit-tricksy"}],
         "note": "三种气质共用数值，只改变附赠动作「妖精步」的附加效果。"}),
    spell(
        "summon-undead", "Summon Undead", "召唤亡灵", 3, ["warlock", "wizard"],
        "一颗镀金骷髅，价值 300+ GP", "a gilded skull worth 300+ GP",
        "召唤一只亡灵精魂：选择幽魂、骷髅或腐尸形态（专注 1 小时）。",
        "You call forth an undead spirit. Choose a form when you cast the "
        "spell: Ghostly, Skeletal, or Putrid. The spirit uses the Undead "
        "Spirit stat block, and the form determines certain traits and "
        "attacks in it. " + COMMON_EN,
        {"kind": "statblock",
         "options": [{"name": "幽魂", "statblock": "undead-spirit-ghostly"},
                     {"name": "骷髅", "statblock": "undead-spirit-skeletal"},
                     {"name": "腐尸", "statblock": "undead-spirit-putrid"}],
         "note": "幽魂可穿墙飞行，骷髅远程，腐尸带中毒灵光。"}),
    spell(
        "summon-aberration", "Summon Aberration", "召唤异怪", 4,
        ["warlock", "wizard"],
        "一根腌制触须与一颗眼球，装在镶铂金的小瓶里，价值 400+ GP",
        "a pickled tentacle and an eyeball in a platinum-inlaid vial worth "
        "400+ GP",
        "召唤一只异怪精魂：选择史拉蟾、夺心魔或眼魔亲族形态（专注 1 小时）。",
        "You call forth an aberrant spirit. Choose a form when you cast the "
        "spell: Beholderkin, Mind Flayer, or Slaad. The spirit uses the "
        "Aberrant Spirit stat block, and the form determines certain traits "
        "and attacks in it. " + COMMON_EN,
        {"kind": "statblock",
         "options": [{"name": "史拉蟾", "statblock": "aberrant-spirit-slaad"},
                     {"name": "夺心魔",
                      "statblock": "aberrant-spirit-mind-flayer"},
                     {"name": "眼魔亲族",
                      "statblock": "aberrant-spirit-beholderkin"}],
         "note": "史拉蟾能再生，夺心魔带心灵灵光，眼魔亲族可悬浮远程攻击。"}),
    spell(
        "summon-construct", "Summon Construct", "召唤构装", 4, ["wizard"],
        "一个锁盒，价值 400+ GP", "a lockbox worth 400+ GP",
        "召唤一个构装精魂：选择黏土、金属或石质材质（专注 1 小时）。",
        "You call forth a construct spirit. Choose a material when you cast "
        "the spell: Clay, Metal, or Stone. The spirit uses the Construct "
        "Spirit stat block, and the material determines certain traits and "
        "reactions in it. " + COMMON_EN,
        {"kind": "statblock",
         "options": [{"name": "黏土", "statblock": "construct-spirit-clay"},
                     {"name": "金属", "statblock": "construct-spirit-metal"},
                     {"name": "石质", "statblock": "construct-spirit-stone"}],
         "note": "三种材质共用数值，差别在特性与反应。"}),
    spell(
        "summon-elemental", "Summon Elemental", "召唤元素", 4,
        ["druid", "ranger", "wizard"],
        "气、一颗卵石、灰烬与水，装在镶金的小瓶里，价值 400+ GP",
        "air, a pebble, ash, and water inside a gold-inlaid vial worth 400+ GP",
        "召唤一个元素精魂：选择气、土、火或水元素（专注 1 小时）。",
        "You call forth an elemental spirit. Choose an element when you cast "
        "the spell: Air, Earth, Fire, or Water. The spirit uses the Elemental "
        "Spirit stat block, and the element determines its speed and the "
        "damage type of its Slam. " + COMMON_EN,
        {"kind": "statblock",
         "options": [{"name": "气", "statblock": "elemental-spirit-air"},
                     {"name": "土", "statblock": "elemental-spirit-earth"},
                     {"name": "火", "statblock": "elemental-spirit-fire"},
                     {"name": "水", "statblock": "elemental-spirit-water"}],
         "note": "重击伤害类型随元素变化：土=钝击、火=火焰、水=寒冷、气=闪电。"}),
    spell(
        "summon-celestial", "Summon Celestial", "召唤天界", 5,
        ["cleric", "paladin"],
        "一件圣物匣，价值 500+ GP", "a reliquary worth 500+ GP",
        "召唤一个天界精魂：选择复仇者或守卫者形态（专注 1 小时）。",
        "You call forth a celestial spirit. Choose a form when you cast the "
        "spell: Avenger or Defender. The spirit uses the Celestial Spirit "
        "stat block, and the form determines certain details in it. "
        + COMMON_EN,
        {"kind": "statblock",
         "options": [{"name": "复仇者",
                      "statblock": "celestial-spirit-avenger"},
                     {"name": "守卫者",
                      "statblock": "celestial-spirit-defender"}],
         "note": "复仇者远程输出、守卫者近战且 AC 与临时生命更高。"}),
    spell(
        "summon-fiend", "Summon Fiend", "召唤邪魔", 6, ["warlock", "wizard"],
        "一小瓶血，价值 600+ GP", "a bloody vial worth 600+ GP",
        "召唤一个邪魔精魂：选择恶魔、魔鬼或尤格罗斯形态（专注 1 小时）。",
        "You call forth a fiendish spirit. Choose a form when you cast the "
        "spell: Demon, Devil, or Yugoloth. The spirit uses the Fiendish "
        "Spirit stat block, and the form determines certain traits and "
        "attacks in it. " + COMMON_EN,
        {"kind": "statblock",
         "options": [{"name": "恶魔", "statblock": "fiendish-spirit-demon"},
                     {"name": "魔鬼", "statblock": "fiendish-spirit-devil"},
                     {"name": "尤格罗斯",
                      "statblock": "fiendish-spirit-yugoloth"}],
         "note": "恶魔死亡时爆炸，魔鬼带魔鬼视界，尤格罗斯 HP 最高。"}),
]

# 已有法术的 summon 映射（statblock 型给 options，filter 型给筛选条件）
EXISTING = {
    "summon-dragon": {
        "kind": "statblock",
        "options": [{"name": "巨龙", "statblock": "draconic-spirit"}],
        "note": "召唤时选择一种伤害类型，精魂与你在法术结束前都获得该抗性。"},
    "find-steed": {
        "kind": "statblock",
        "options": [{"name": "天界",
                     "statblock": "otherworldly-steed-celestial"},
                    {"name": "妖精", "statblock": "otherworldly-steed-fey"},
                    {"name": "邪魔", "statblock": "otherworldly-steed-fiend"}],
        "note": "座骑可骑乘；用更高环级施放时 AC 与 HP 随之提升。"},
    "animate-objects": {
        "kind": "statblock",
        "options": [{"name": "活化物件", "statblock": "animated-object"}],
        "note": "可控物件数 = 施法属性调整值；中型或更小算 1 件、大型算 2 件、"
                "巨型算 3 件。"},
    "giant-insect": {
        "kind": "statblock",
        "options": [{"name": "蜈蚣",
                     "statblock": "giant-insect-centipede"},
                    {"name": "蜘蛛", "statblock": "giant-insect-spider"},
                    {"name": "黄蜂", "statblock": "giant-insect-wasp"}],
        "note": "形态在施法时选定，决定速度与附赠动作。"},
    "polymorph": {
        "kind": "filter", "type": "beast",
        "cr": "target", "size": "任意", "exclude": ["swarm"],
        "note": "只能变为野兽，且 CR 不得超过目标原本的 CR（无 CR 时用其等级）；"
                "排除虫群。可从怪物图鉴的野兽里挑，德鲁伊形态表是最好的候选来源。"},
    "true-polymorph": {
        "kind": "filter", "type": "any",
        "cr": "target", "size": "任意", "exclude": [],
        "note": "可变为任意生物（不限野兽），CR 不得超过目标原本的 CR 或等级；"
                "也可把物件变为 CR ≤ 9 的生物。"},
    "animal-shapes": {
        "kind": "filter", "type": "beast",
        "cr": "4", "size": "大型或更小", "exclude": ["swarm"],
        "note": "每个目标可各选一种形态，CR 不得超过 4 且体型为大型或更小；"
                "之后每回合可用魔法动作再换形态。"},
}


def load():
    with io.open(PATH, encoding="utf-8") as f:
        return json.load(f)


def save(d):
    # 原文件是 CRLF，保持原样以免整份 diff
    with io.open(PATH, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")


def main():
    d = load()
    spells = d["spells"]
    ids = {s["id"] for s in spells}

    added = 0
    for ns in NEW:
        if ns["id"] in ids:
            # 已存在则只更新 summon 字段
            for s in spells:
                if s["id"] == ns["id"]:
                    s["summon"] = ns["summon"]
            continue
        spells.append(ns)
        ids.add(ns["id"])
        added += 1

    touched = 0
    for s in spells:
        if s["id"] in EXISTING and s.get("summon") != EXISTING[s["id"]]:
            s["summon"] = EXISTING[s["id"]]
            touched += 1

    spells.sort(key=lambda s: (s["level"], s["name"]))
    d["count"] = len(spells)
    save(d)
    print(f"新增 {added} 个召唤法术；更新 {touched} 条已有法术的 summon 字段")
    print(f"法术总数：{d['count']}")
    with_summon = [s for s in spells if "summon" in s]
    print(f"带 summon 字段：{len(with_summon)} 条")
    for s in with_summon:
        kind = s["summon"]["kind"]
        n = len(s["summon"].get("options") or [])
        print(f"  L{s['level']} {s['id']:24s} {kind:9s} options={n}")


if __name__ == "__main__":
    main()
