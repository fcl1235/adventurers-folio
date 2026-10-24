# -*- coding: utf-8 -*-
"""召唤物 / 变形形态 stat block 构建工具。

用法：
  python _build_summons.py            # 生成 dnd55e/data/summons.json
  python _build_summons.py --check    # 只校验现有文件

数据来源：data/raw/_5e_bestiary_phb.json（5etools PHB 2024 快照，15 条
「由法术/职业召出」的 stat block）。AC / HP 在 2024 版是随施法环级变化的公式，
所以这里存的是**公式字符串**而不是固定数字 —— 与 monsters.json（真怪物，固定
数值）刻意分开，避免把「召唤物」混进荒野变形的形态表。

本脚本是 summons.json 的唯一来源：改公式 / 补 variant 都改这里再重跑。
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "dnd55e", "data", "summons.json")

SIZE = {"T": "微型", "S": "小型", "M": "中型", "L": "大型", "H": "巨型"}

NOTE = (
    "法术召唤物数据，供召唤法术 / 变形术 / 寻获坐骑 / 活化物件的详情卡使用。"
    "仅收录 2024 PHB 中「由法术召出、拥有独立 stat block」的生物；"
    "AC 与 HP 在 2024 版是随施法环级变化的公式，因此以字符串保存，"
    "由界面按实际环级展示，不参与角色本体的数值计算。"
)


def senses(dark=0, blind=0, passive=10):
    return {"darkvision": dark, "blindsight": blind, "tremorsense": 0,
            "truesight": 0, "passive_perception": passive}


def speed(walk=0, climb=0, fly=0, swim=0, burrow=0, hover=False):
    return {"walk": walk, "climb": climb, "fly": fly, "swim": swim,
            "burrow": burrow, "hover": hover}


def ab(s, d, c, i, w, ch):
    return {"STR": s, "DEX": d, "CON": c, "INT": i, "WIS": w, "CHA": ch}


def act(name, kind, desc, reach=None, rng=None):
    return {"name": name, "kind": kind, "attack_bonus": None,
            "reach": reach, "range": rng, "damage": None,
            "damage_type": None, "save": None, "dc": None, "desc": desc}


def tr(name, desc):
    return {"name": name, "desc": desc}


MULTI = act("多重攻击 Multiattack", "multiattack",
            "该精魂发动的攻击次数等于「法术环级 ÷ 2」（向下取整）。")

SPEED_DESC = act("速度说明", "other",
                 "该生物的速度、抗性与部分特性随你施法时选择的环境 / 形态变化，"
                 "见上方「形态」说明。")

ENTRIES = []


def add(sid, name_cn, name_en, spell, variant, ctype, size,
        ac, hp, hp_dice, spd, abilities, sns, lang, traits, actions,
        bonus=None, reactions=None, note=""):
    ENTRIES.append({
        "id": sid,
        "name": f"{name_cn} {name_en}",
        "name_cn": name_cn,
        "name_en": name_en,
        "spell": spell,
        "variant": variant,
        "type": ctype,
        "size": size,
        "ac": ac,
        "hp": hp,
        "hp_dice": hp_dice,
        "speed": spd,
        "abilities": abilities,
        "senses": sns,
        "languages": lang,
        "traits": traits,
        "actions": actions,
        "bonus_actions": bonus or [],
        "reactions": reactions or [],
        "note": note,
    })


# ---------------------------------------------------------------- Summon Beast
BESTIAL_LANG = "理解你的语言但不会说"
BESTIAL = dict(spell="summon-beast", ctype="beast", size="小型",
               hp_dice="—",
               abilities=ab(18, 11, 16, 4, 14, 5),
               sns=senses(dark=60), lang=BESTIAL_LANG,
               actions=[MULTI,
                        act("撕裂 Rend", "melee",
                            "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                            "命中造成 1d8 + 4 + 法术环级 点穿刺伤害。",
                            reach=5)])
add("bestial-spirit-land", "陆行精魂兽", "Bestial Spirit (Land)",
    variant="陆行", ac="11 + 法术环级", hp="30 + 5 × 超出 2 级的环级",
    spd=speed(walk=30, climb=30),
    traits=[tr("集群战术 Pack Tactics",
               "若该精魂的至少一个盟友位于目标 5 尺内且该盟友未处于失能状态，"
               "精魂对该目标的攻击检定具有优势。")], **BESTIAL)
add("bestial-spirit-water", "水栖精魂兽", "Bestial Spirit (Water)",
    variant="水栖", ac="11 + 法术环级", hp="30 + 5 × 超出 2 级的环级",
    spd=speed(walk=30, swim=30),
    traits=[tr("集群战术 Pack Tactics",
               "若该精魂的至少一个盟友位于目标 5 尺内且该盟友未处于失能状态，"
               "精魂对该目标的攻击检定具有优势。"),
            tr("水陆呼吸 Water Breathing", "该精魂只能在水下呼吸。")], **BESTIAL)
add("bestial-spirit-air", "飞行精魂兽", "Bestial Spirit (Air)",
    variant="空中", ac="11 + 法术环级", hp="20 + 5 × 超出 2 级的环级",
    spd=speed(walk=30, fly=60),
    traits=[tr("飞掠 Flyby",
               "该精魂飞出敌人触及范围时不会引发借机攻击。")], **BESTIAL)

# ------------------------------------------------------------ Summon Aberration
ABERRANT_LANG = "深潜语；理解你的语言但不会说"
ABERRANT = dict(spell="summon-aberration", ctype="aberration", size="中型",
                ac="11 + 法术环级", hp="40 + 10 × 超出 4 级的环级",
                hp_dice="—", abilities=ab(16, 10, 15, 16, 10, 6),
                sns=senses(dark=60), lang=ABERRANT_LANG)
add("aberrant-spirit-slaad", "异怪精魂·史拉蟾", "Aberrant Spirit (Slaad)",
    variant="史拉蟾", spd=speed(walk=30),
    traits=[tr("再生 Regeneration", "若该精魂至少还有 1 点生命值，"
                                    "它在自己回合开始时回复 5 点生命值。")],
    actions=[MULTI,
             act("利爪 Claw", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                 "造成 1d10 + 3 + 法术环级 点挥砍伤害，且目标在精魂下个回合开始前"
                 "无法回复生命值。", reach=5)],
    **ABERRANT)
add("aberrant-spirit-mind-flayer", "异怪精魂·夺心魔",
    "Aberrant Spirit (Mind Flayer)",
    variant="夺心魔", spd=speed(walk=30),
    traits=[tr("低语灵光 Whispering Aura",
               "在精魂每个回合开始时，若它未处于失能状态，它散发灵能："
               "距它 5 尺内除你以外的每个生物做 DC = 你的法术豁免 DC 的"
               "感知豁免，失败受 2d6 点心灵伤害。")],
    actions=[MULTI,
             act("心灵重击 Psychic Slam", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                 "造成 1d8 + 3 + 法术环级 点心灵伤害。", reach=5)],
    **ABERRANT)
add("aberrant-spirit-beholderkin", "异怪精魂·眼魔亲族",
    "Aberrant Spirit (Beholderkin)",
    variant="眼魔亲族", spd=speed(walk=30, fly=30, hover=True),
    traits=[tr("悬浮 Hover", "该精魂可悬浮于原地，即使失去移动力也不会坠落。")],
    actions=[MULTI,
             act("眼光射线 Eye Ray", "ranged",
                 "远程攻击：命中 = 你的法术攻击加值，射程 150 尺，"
                 "造成 1d8 + 3 + 法术环级 点心灵伤害。", rng=150)],
    **ABERRANT)

# ------------------------------------------------------------- Summon Celestial
CELESTIAL_LANG = "天界语；理解你的语言但不会说"
CELESTIAL = dict(spell="summon-celestial", ctype="celestial", size="大型",
                 hp="40 + 10 × 超出 5 级的环级", hp_dice="—",
                 abilities=ab(16, 14, 16, 10, 14, 16),
                 sns=senses(dark=60), lang=CELESTIAL_LANG)
HEALING_TOUCH = act("治疗触碰 Healing Touch（1/日）", "other",
                    "该精魂触碰另一个生物，目标回复 2d8 + 法术环级 点生命值。")
add("celestial-spirit-avenger", "天界精魂·复仇者", "Celestial Spirit (Avenger)",
    variant="复仇者", ac="11 + 法术环级", spd=speed(walk=30, fly=40),
    traits=[],
    actions=[MULTI,
             act("光耀长弓 Radiant Bow", "ranged",
                 "远程攻击：命中 = 你的法术攻击加值，射程 600 尺，"
                 "造成 2d6 + 2 + 法术环级 点光耀伤害。", rng=600),
             HEALING_TOUCH],
    **CELESTIAL)
add("celestial-spirit-defender", "天界精魂·守卫者", "Celestial Spirit (Defender)",
    variant="守卫者", ac="11 + 法术环级 + 2（仅守卫者）",
    spd=speed(walk=30, fly=40), traits=[],
    actions=[MULTI,
             act("光耀硬头锤 Radiant Mace", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                 "造成 1d10 + 3 + 法术环级 点光耀伤害；你可以让该精魂自己或"
                 "目标 10 尺内另一个它看得见的生物获得 1d10 点临时生命值。",
                 reach=5),
             HEALING_TOUCH],
    **CELESTIAL)

# ------------------------------------------------------------- Summon Construct
CONSTRUCT = dict(spell="summon-construct", ctype="construct", size="中型",
                 ac="13 + 法术环级", hp="40 + 15 × 超出 4 级的环级",
                 hp_dice="—", abilities=ab(18, 10, 18, 14, 11, 5),
                 sns=senses(dark=60), lang="理解你的语言但不会说")
CONSTRUCT_ATTACK = act("重击 Slam", "melee",
                       "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                       "造成 1d8 + 4 + 法术环级 点钝击伤害。", reach=5)
add("construct-spirit-clay", "构装精魂·黏土", "Construct Spirit (Clay)",
    variant="黏土", spd=speed(walk=30),
    traits=[tr("泥形 Soften", "该精魂为黏土质地，外观由你决定。")],
    actions=[MULTI, CONSTRUCT_ATTACK],
    reactions=[act("狂怒抽打 Berserk Lashing（仅黏土）", "other",
                   "触发：该精魂受到某个生物的伤害。"
                   "响应：若可能，它对该生物发动一次重击，或朝该生物移动至多"
                   "其一半速度且不引发借机攻击。")],
    **CONSTRUCT)
add("construct-spirit-metal", "构装精魂·金属", "Construct Spirit (Metal)",
    variant="金属", spd=speed(walk=30),
    traits=[tr("灼热之躯 Heated Body（仅金属）",
               "以近战攻击命中该精魂、或在其擒抱中开始回合的生物，"
               "受到 1d10 点火焰伤害。")],
    actions=[MULTI, CONSTRUCT_ATTACK], **CONSTRUCT)
add("construct-spirit-stone", "构装精魂·石质", "Construct Spirit (Stone)",
    variant="石质", spd=speed(walk=30),
    traits=[tr("迟缓石化 Stony Lethargy（仅石质）",
               "当生物在距该精魂 10 尺内开始回合时，精魂若能看见它，"
               "可以魔法能量笼罩它：目标做 DC = 你的法术豁免 DC 的感知豁免，"
               "失败则在其下个回合开始前不能发动借机攻击，且速度减半。")],
    actions=[MULTI, CONSTRUCT_ATTACK], **CONSTRUCT)

# ---------------------------------------------------------------- Summon Dragon
add("draconic-spirit", "龙之精魂", "Draconic Spirit", spell="summon-dragon",
    variant="—", ctype="dragon", size="大型", ac="14 + 法术环级",
    hp="50 + 10 × 超出 5 级的环级", hp_dice="—",
    spd=speed(walk=30, fly=60, swim=30), abilities=ab(19, 14, 17, 10, 14, 14),
    sns=senses(dark=60, blind=30), lang="龙语；理解你的语言但不会说",
    traits=[tr("共享抗性 Shared Resistances",
               "召唤时选择该精魂的一种抗性，在你法术结束前你获得该伤害类型的抗性。")],
    actions=[act("多重攻击 Multiattack", "multiattack",
                 "该精魂发动的撕裂攻击次数等于「法术环级 ÷ 2」（向下取整），"
                 "并使用一次吐息武器。"),
             act("撕裂 Rend", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 10 尺，"
                 "造成 1d6 + 4 + 法术环级 点穿刺伤害。", reach=10),
             act("吐息武器 Breath Weapon", "save",
                 "该精魂呼出 30 尺锥形能量：范围内每个生物做 DC = 你的法术豁免 DC 的"
                 "敏捷豁免，失败受 2d6 点伤害（伤害类型为它拥有抗性的类型，"
                 "施法时选定），成功则伤害减半。")])

# ------------------------------------------------------------- Summon Elemental
ELEMENTAL = dict(spell="summon-elemental", ctype="elemental", size="中型",
                 ac="11 + 法术环级", hp="50 + 10 × 超出 4 级的环级",
                 hp_dice="—", abilities=ab(18, 15, 17, 4, 10, 16),
                 sns=senses(dark=60), lang="原初语；理解你的语言但不会说")
AMORPHOUS = tr("无定形 Amorphous Form（仅气、火、水）",
               "该精魂可以穿过窄至 1 寸宽的缝隙，且该处不视为困难地形。")


def elemental_slam(dtype):
    return act("重击 Slam", "melee",
               "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
               f"造成 1d10 + 4 + 法术环级 点{dtype}伤害。", reach=5)


add("elemental-spirit-air", "元素精魂·气", "Elemental Spirit (Air)",
    variant="气", spd=speed(walk=40, fly=40, hover=True),
    traits=[AMORPHOUS], actions=[MULTI, elemental_slam("闪电")], **ELEMENTAL)
add("elemental-spirit-earth", "元素精魂·土", "Elemental Spirit (Earth)",
    variant="土", spd=speed(walk=40, burrow=40),
    traits=[], actions=[MULTI, elemental_slam("钝击")], **ELEMENTAL)
add("elemental-spirit-fire", "元素精魂·火", "Elemental Spirit (Fire)",
    variant="火", spd=speed(walk=40, hover=True),
    traits=[AMORPHOUS], actions=[MULTI, elemental_slam("火焰")], **ELEMENTAL)
add("elemental-spirit-water", "元素精魂·水", "Elemental Spirit (Water)",
    variant="水", spd=speed(walk=40, swim=40),
    traits=[AMORPHOUS], actions=[MULTI, elemental_slam("寒冷")], **ELEMENTAL)

# ------------------------------------------------------------------- Summon Fey
FEY = dict(spell="summon-fey", ctype="fey", size="小型", ac="12 + 法术环级",
           hp="30 + 10 × 超出 3 级的环级", hp_dice="—",
           abilities=ab(13, 16, 14, 14, 11, 16),
           sns=senses(dark=60), lang="木族语；理解你的语言但不会说")
FEY_BLADE = act("妖精之刃 Fey Blade", "melee",
                "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                "造成 2d6 + 3 + 法术环级 点力场伤害。", reach=5)
FEY_STEP = {
    "fuming": act("妖精步 Fey Step（仅暴躁）", "other",
                  "该精魂传送至多 30 尺到它看得见的空地，然后：暴躁 —— "
                  "它在本回合结束前发动的下一次攻击检定具有优势。"),
    "mirthful": act("妖精步 Fey Step（仅欢愉）", "other",
                    "该精魂传送至多 30 尺到它看得见的空地，然后：欢愉 —— "
                    "距它 10 尺内一个它看得见的生物做 DC = 你的法术豁免 DC 的"
                    "感知豁免，失败被你与该精魂魅惑 1 分钟，或在受到伤害时提前结束。"),
    "tricksy": act("妖精步 Fey Step（仅狡黠）", "other",
                   "该精魂传送至多 30 尺到它看得见的空地，然后：狡黠 —— "
                   "它在 5 尺内一个 10 尺立方体区域填满魔法黑暗，"
                   "持续到它下个回合结束。"),
}
for _v, _cn in (("fuming", "暴躁"), ("mirthful", "欢愉"), ("tricksy", "狡黠")):
    add(f"fey-spirit-{_v}", f"妖精精魂·{_cn}", f"Fey Spirit ({_v.title()})",
        variant=_cn, spd=speed(walk=30, fly=30), traits=[],
        actions=[MULTI, FEY_BLADE], bonus=[FEY_STEP[_v]], **FEY)

# ----------------------------------------------------------------- Summon Fiend
FIEND = dict(spell="summon-fiend", ctype="fiend", size="大型",
             ac="12 + 法术环级", hp_dice="—",
             abilities=ab(13, 16, 15, 10, 10, 16),
             sns=senses(dark=60), lang="深渊语、炼狱语；心灵感应 60 尺")
FIEND_TRAITS = [tr("魔法抗性 Magic Resistance",
                   "该精魂对抗法术与其他魔法效应的豁免具有优势。")]
add("fiendish-spirit-demon", "邪魔精魂·恶魔", "Fiendish Spirit (Demon)",
    variant="恶魔", hp="50 + 15 × 超出 6 级的环级",
    spd=speed(walk=40, climb=40),
    traits=FIEND_TRAITS + [
        tr("死亡回响 Death Throes（仅恶魔）",
           "当该精魂生命值归零或法术结束时，它爆炸：以它为中心 10 尺光环内"
           "每个生物做 DC = 你的法术豁免 DC 的敏捷豁免，失败受 2d10 + 法术环级 "
           "点火焰伤害，成功则减半。")],
    actions=[MULTI,
             act("啃咬 Bite", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                 "造成 1d12 + 3 + 法术环级 点黯蚀伤害。", reach=5)], **FIEND)
add("fiendish-spirit-devil", "邪魔精魂·魔鬼", "Fiendish Spirit (Devil)",
    variant="魔鬼", hp="40 + 15 × 超出 6 级的环级",
    spd=speed(walk=40, fly=60),
    traits=FIEND_TRAITS + [
        tr("魔鬼视界 Devil's Sight（仅魔鬼）",
           "魔法黑暗不会妨碍该精魂的黑暗视觉。")],
    actions=[MULTI,
             act("炽焰打击 Fiery Strike", "melee",
                 "近战或远程攻击：命中 = 你的法术攻击加值，触及 5 尺或射程 150 尺，"
                 "造成 2d6 + 3 + 法术环级 点火焰伤害。", reach=5, rng=150)], **FIEND)
add("fiendish-spirit-yugoloth", "邪魔精魂·尤格罗斯", "Fiendish Spirit (Yugoloth)",
    variant="尤格罗斯", hp="60 + 15 × 超出 6 级的环级",
    spd=speed(walk=40), traits=list(FIEND_TRAITS),
    actions=[MULTI,
             act("爪击 Claws", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                 "造成 1d8 + 3 + 法术环级 点挥砍伤害；命中或失手后，"
                 "该精魂可立即传送至多 30 尺到它看得见的空地。", reach=5)], **FIEND)

# ----------------------------------------------------------------- Summon Undead
UNDEAD = dict(spell="summon-undead", ctype="undead", size="中型",
              ac="11 + 法术环级", hp_dice="—",
              abilities=ab(12, 16, 15, 4, 10, 9),
              sns=senses(dark=60), lang="理解你的语言但不会说")
add("undead-spirit-ghostly", "亡灵精魂·幽魂", "Undead Spirit (Ghostly)",
    variant="幽魂", hp="30 + 10 × 超出 3 级的环级",
    spd=speed(walk=30, fly=40, hover=True),
    traits=[tr("虚体穿行 Incorporeal Passage（仅幽魂）",
               "该精魂可如穿越困难地形般穿过其他生物与物件；"
               "若它在物件内结束回合，会被挤到最近的空地，"
               "并每移动 5 尺受到 1d10 点力场伤害。")],
    actions=[MULTI,
             act("死亡之触 Deathly Touch", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                 "造成 1d8 + 3 + 法术环级 点黯蚀伤害，"
                 "且目标在其下个回合结束前处于恐惧状态。", reach=5)],
    **UNDEAD)
add("undead-spirit-skeletal", "亡灵精魂·骷髅", "Undead Spirit (Skeletal)",
    variant="骷髅", hp="20 + 10 × 超出 3 级的环级", spd=speed(walk=30),
    traits=[],
    actions=[MULTI,
             act("墓穴箭矢 Grave Bolt", "ranged",
                 "远程攻击：命中 = 你的法术攻击加值，射程 150 尺，"
                 "造成 2d4 + 3 + 法术环级 点黯蚀伤害。", rng=150)],
    **UNDEAD)
add("undead-spirit-putrid", "亡灵精魂·腐尸", "Undead Spirit (Putrid)",
    variant="腐尸", hp="30 + 10 × 超出 3 级的环级", spd=speed(walk=30),
    traits=[tr("溃烂灵光 Festering Aura（仅腐尸）",
               "以该精魂为中心 5 尺光环内、除你以外的生物在其回合开始时做 "
               "DC = 你的法术豁免 DC 的体质豁免，失败在其下个回合开始前中毒。")],
    actions=[MULTI,
             act("腐朽之爪 Rotting Claw", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
                 "造成 1d6 + 3 + 法术环级 点挥砍伤害；若目标已中毒，"
                 "则在其下个回合结束前麻痹。", reach=5)],
    **UNDEAD)

# --------------------------------------------------------------- Animate Objects
add("animated-object", "活化物件", "Animated Object", spell="animate-objects",
    variant="—", ctype="construct", size="微型/小型/中型/大型/巨型",
    ac="15", hp="10（中型或更小）／20（大型）／40（巨型）", hp_dice="—",
    spd=speed(walk=30), abilities=ab(16, 10, 10, 3, 3, 1),
    sns=senses(blind=30), lang="理解你的语言但不会说",
    traits=[tr("构装本质 Construct Nature",
               "该物件活化后视为构装生物，使用本 stat block 的全部数据。")],
    actions=[act("重击 Slam", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，造成力场伤害："
                 "中型或更小为（法术环级 − 4）d4 + 3，大型为（法术环级 − 3）d6 + 3，"
                 "巨型为（法术环级 − 3）d12 + 3，再加上你的施法属性调整值。",
                 reach=5)])

# ----------------------------------------------------------------- Giant Insect
INSECT = dict(spell="giant-insect", ctype="beast", size="大型",
              ac="11 + 法术环级", hp="30 + 10 × 超出 4 级的环级", hp_dice="—",
              abilities=ab(17, 13, 15, 4, 14, 3),
              sns=senses(dark=60), lang="理解你的语言但不会说")
POISON_JAB = act("毒刺 Poison Jab", "melee",
                 "近战攻击：命中 = 你的法术攻击加值，触及 10 尺，"
                 "造成 1d6 + 3 + 法术环级 点穿刺伤害，外加 1d4 点毒素伤害。",
                 reach=10)
SPIDER_CLIMB = tr("蛛行 Spider Climb",
                  "该昆虫可以攀爬困难表面（包括天花板）而无需属性检定。")
add("giant-insect-centipede", "巨型昆虫·蜈蚣", "Giant Insect (Centipede)",
    variant="蜈蚣", spd=speed(walk=40, climb=40), traits=[SPIDER_CLIMB],
    bonus=[act("毒液喷吐 Venomous Spew（仅蜈蚣）", "save",
               "该昆虫对 10 尺内一个它看得见的生物喷出毒液："
               "目标做 DC = 你的法术豁免 DC 的体质豁免，"
               "失败在其下个回合开始前中毒。")],
    actions=[MULTI, POISON_JAB], **INSECT)
add("giant-insect-spider", "巨型昆虫·蜘蛛", "Giant Insect (Spider)",
    variant="蜘蛛", spd=speed(walk=40, climb=40), traits=[SPIDER_CLIMB],
    actions=[MULTI, POISON_JAB,
             act("蛛网弹 Web Bolt（仅蜘蛛）", "ranged",
                 "远程攻击：命中 = 你的法术攻击加值，射程 60 尺，"
                 "造成 1d10 + 3 + 法术环级 点钝击伤害，"
                 "且目标速度降为 0 直到该昆虫下个回合开始。", rng=60)],
    **INSECT)
add("giant-insect-wasp", "巨型昆虫·黄蜂", "Giant Insect (Wasp)",
    variant="黄蜂", spd=speed(walk=40, climb=40, fly=40), traits=[SPIDER_CLIMB],
    actions=[MULTI, POISON_JAB], **INSECT)

# ----------------------------------------------------------- Otherworldly Steed
STEED = dict(spell="find-steed", ctype="celestial/fey/fiend", size="大型",
             ac="10 + 每法术环级 1 点", hp="5 + 10 × 法术环级",
             hp_dice="d10（数量 = 法术环级）",
             spd=speed(walk=60), abilities=ab(18, 12, 14, 6, 12, 8),
             sns=senses(passive=11), lang="心灵感应 1 里（仅与你）",
             traits=[tr("生命纽带 Life Bond",
                        "当你因 1 环或更高环级的法术回复生命值时，"
                        "若坐骑在你 5 尺内，它回复同等的生命值。")])


def steed_slam(dtype):
    return act("异界重击 Otherworldly Slam", "melee",
               "近战攻击：命中 = 你的法术攻击加值，触及 5 尺，"
               f"造成 1d8 + 法术环级 点{dtype}伤害。", reach=5)


def _steed(**kw):
    d = dict(STEED)
    d.update(kw)
    return d


add("otherworldly-steed-celestial", "异界坐骑·天界",
    "Otherworldly Steed (Celestial)", variant="天界",
    bonus=[act("治疗触碰 Healing Touch（仅天界，长休后恢复）", "other",
               "坐骑 5 尺内一个生物回复 2d8 + 法术环级 点生命值。")],
    actions=[steed_slam("光耀")], **_steed())
add("otherworldly-steed-fey", "异界坐骑·妖精",
    "Otherworldly Steed (Fey)", variant="妖精",
    bonus=[act("妖精步 Fey Step（仅妖精，长休后恢复）", "other",
               "坐骑连同其骑乘者传送到 60 尺内你选定的空地。")],
    actions=[steed_slam("心灵")], **_steed())
add("otherworldly-steed-fiend", "异界坐骑·邪魔",
    "Otherworldly Steed (Fiend)", variant="邪魔",
    bonus=[act("邪眼凝视 Fell Glare（仅邪魔，长休后恢复）", "save",
               "坐骑 60 尺内一个它看得见的生物做 DC = 你的法术豁免 DC 的"
               "感知豁免，失败在其下个回合结束前处于恐惧状态。")],
    actions=[steed_slam("黯蚀")], **_steed(spd=speed(walk=60, fly=60)))


def build():
    ids = [e["id"] for e in ENTRIES]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit(f"重复 id: {sorted(dup)}")
    data = {"_note": NOTE, "count": len(ENTRIES), "summons": ENTRIES}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {OUT}: {len(ENTRIES)} summons")


if __name__ == "__main__":
    if "--check" in sys.argv:
        with io.open(OUT, encoding="utf-8") as f:
            d = json.load(f)
        print(f"{OUT}: {d['count']} summons")
    else:
        build()
