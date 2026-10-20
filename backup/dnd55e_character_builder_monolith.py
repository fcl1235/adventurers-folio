#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D&D 5.5e (2024 规则) 人物卡 · 桌面应用
=====================================
零第三方依赖，仅需 Python 标准库 (tkinter)。
数据源: 同目录 dnd55e_core_data.json (基于 SRD 5.2 / PHB 2024 公开资料整理)

功能:
  * 建卡向导: 职业 -> 背景(属性加值) -> 种族(血脉) -> 属性
    -> 技能(职业/种族分栏) -> 武器专精 -> 法术(施法职业)
  * 角色卡: 属性/技能/豁免/HP/AC/先攻/被动察觉/法术位/法术施放/专注
  * 装备: 武器魔法加值、护甲/盾牌、魔法物品、战斗风格、熟练项判定与惩罚
  * 加成引擎: 背景属性加值、专长(Tough/Alert)、职业特性(无甲防御/灵光/万事通)、物品
  * 升级器(子职@3, 专长/ASI@4/8/12/16, 传奇恩惠@19, 自动HP与法术位)
  * 长休/短休(契约魔法、种族法术免费次数)、状态与力竭、骰子工具
  * 存档: 默认写入 characters/ 并在下次启动自动载入; 另存为/导出 JSON 可自选路径
  * 数据: 本地 dnd55e_core_data.json + dnd55e_spells.json (SRD 5.2, 339 法术)

用法: python dnd55e_character_builder.py [--selftest]
"""

import json
import os
import random
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

# ----------------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------------

ABILITIES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
ABILITY_CN = {"STR": "力量", "DEX": "敏捷", "CON": "体质",
              "INT": "智力", "WIS": "感知", "CHA": "魅力"}
ABILITY_DESC = {
    "STR": "近战命中与伤害、运动(攀爬/游泳/推拉/擒抱)、负重上限",
    "DEX": "AC、先攻、远程命中、特技/巧手/隐匿、敏捷豁免(躲火球)",
    "CON": "HP 上限、专注检定(维持法术)、体质豁免(抗毒/抗疲惫)",
    "INT": "奥秘/历史/调查/自然知识、法师法术、智力豁免",
    "WIS": "察觉/洞察/生存、被动察觉、牧师/德鲁伊/游侠法术、感知豁免",
    "CHA": "欺瞒/威吓/表演/说服、术士/邪术师/吟游诗人法术",
}

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "dnd55e_core_data.json")
SPELL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "dnd55e_spells.json")
DETAIL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "dnd55e_classes_detail.json")
CHAR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "characters")          # 角色卡固定存放目录
LAST_PTR = os.path.join(CHAR_DIR, "_last.json")

POINT_COST = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]

CONDITIONS = ["目盲", "魅惑", "失聪", "力竭(另计)", "恐慌", "擒抱", "失能",
              "隐形", "麻痹", "石化", "中毒", "倒地", "束缚", "震慑", "昏迷"]

# 状态效果 (2024 规则摘要) —— 界面悬浮/点选时展示
CONDITION_DESC = {
    "目盲": "看不见: 攻击检定劣势; 对它的攻击检定优势",
    "魅惑": "不能攻击魅惑者, 魅惑者对其社交检定优势",
    "失聪": "听不见: 依赖听觉的检定自动失败",
    "力竭(另计)": "每级: d20 检定 -2、速度 -5尺 (6 级死亡) —— 单独用下方等级条记录",
    "恐慌": "恐惧源可见时: 检定与攻击劣势, 不能主动靠近",
    "擒抱": "速度归 0, 可被移动; 挣脱需动作做力量/敏捷检定",
    "失能": "不能做动作/附赠动作/反应, 集中力中断",
    "隐形": "对看不见它的生物: 攻击优势, 被攻击劣势",
    "麻痹": "失能 + 不能移动/说话; 5尺内被击中即重击",
    "石化": "变为石头: 失能、体重 ×10、停止衰老",
    "中毒": "攻击检定与属性检定劣势",
    "倒地": "只能爬行; 近战对其攻击优势, 远程劣势; 起身耗半速",
    "束缚": "速度 0; 攻击与敏捷豁免劣势; 对其攻击优势",
    "震慑": "失能 + 不能移动; 力量/敏捷豁免自动失败",
    "昏迷": "失能、倒地、不能移动; 5尺内被击中即重击",
}

# 18 项技能管什么 (鼠标停靠时显示)
SKILL_DESC = {
    "acrobatics": "翻滚、平衡、狭处穿行 — 对抗擒抱、脱离危险地形",
    "animal_handling": "安抚/驱使动物、骑乘控制、判断动物意图",
    "arcana": "辨识法术/魔法物品/位面知识、解读符文",
    "athletics": "攀爬、游泳、跳跃、推拉、擒抱与挣脱",
    "deception": "说谎、伪装身份、误导他人",
    "history": "历史事件、王朝、战争、古代遗迹的来历",
    "insight": "判断对方是否说谎、揣摩动机与情绪",
    "intimidation": "威胁、恫吓、以气势逼人让步",
    "investigation": "搜查线索、推理、验尸、找密门",
    "medicine": "稳定濒死、诊断疾病、处理中毒",
    "nature": "地形/植物/动物/天气知识, 追踪野兽",
    "perception": "察觉躲藏者、听声、找显眼物 (被动察觉用它)",
    "performance": "表演、演奏、演讲取悦观众",
    "persuasion": "说服、谈判、外交礼节",
    "religion": "神祇/教义/仪式/不死生物知识",
    "sleight_of_hand": "扒窃、藏物、手上小戏法",
    "stealth": "潜行、躲藏、悄然接近",
    "survival": "追踪、觅食、辨向、预测天气",
}

MASTERY_DESC = {
    "Cleave": "劈砍: 近战命中后可对5尺内第二目标再攻击一次(无属性加值), 1次/回合",
    "Graze": "擦伤: 未命中仍造成等同攻击属性调整值的伤害",
    "Nick": "疾刺: 轻武器副手攻击并入攻击动作而非附赠动作, 1次/回合",
    "Push": "推撞: 命中可将大体型以下目标直线推离10尺",
    "Sap": "削弱: 命中后目标下回合前的下次攻击检定劣势",
    "Slow": "迟缓: 命中并造成伤害后目标速度-10尺(不叠加)",
    "Topple": "撂倒: 命中后目标Con豁免(DC8+属性+熟练)否则倒地",
    "Vex": "迷扰: 命中并造成伤害后, 对同一目标下次攻击优势",
}

MASTERY_CN = {"Cleave": "劈砍", "Graze": "擦伤", "Nick": "疾刺", "Push": "推撞",
              "Sap": "削弱", "Slow": "迟缓", "Topple": "撂倒", "Vex": "迷扰"}


def mastery_cn(key):
    return f"{MASTERY_CN[key]} {key}" if key in MASTERY_CN else key


# ---- 2024 规则 (5.5e / 5R): 种族不再给属性加值, 加值全部来自背景 ----
# 下方仅保留"种族附赠技能数", 供建卡向导计算可选技能槽位。
# 种族附赠技能数 (2024: 人类/精灵 各 1 项)
SPECIES_SKILL_BONUS = {"human": 1, "elf": 1}
# 种族自动获得的技能熟练 (2024 种族无此项; 保留空表以便扩展)
SPECIES_AUTO_SKILLS = {}
# 已从 2024 规则中移除的 5e 传承种族: 读旧存档时映射到最接近的现行种族,
# 免得静默变成列表第一个种族(阿斯莫)让人一头雾水。
LEGACY_SPECIES = {"half_elf": "human", "half_orc": "orc"}
LEGACY_SPECIES_CN = {"half_elf": "半精灵 Half-Elf", "half_orc": "半兽人 Half-Orc"}


# ---- 种族自带法术 (含血脉分支) ----
SPECIES_SPELLS = {
    "aasimar": [(1, "light")],                       # 承光者
    "elf": {
        "drow": [(1, "dancing-lights"), (3, "faerie-fire"), (5, "darkness")],
        "high": [(1, "prestidigitation"), (3, "detect-magic"), (5, "misty-step")],
        "wood": [(1, "druidcraft"), (3, "longstrider"),
                 (5, "pass-without-trace")],
    },
    "gnome": {
        "forest": [(1, "minor-illusion"), (1, "speak-with-animals")],
        "rock": [(1, "mending"), (1, "prestidigitation")],
    },
    "tiefling": {
        "abyssal": [(1, "thaumaturgy"), (1, "poison-spray"),
                    (3, "ray-of-sickness"), (5, "hold-person")],
        "chthonic": [(1, "thaumaturgy"), (1, "chill-touch"),
                     (3, "false-life"), (5, "ray-of-enfeeblement")],
        "infernal": [(1, "thaumaturgy"), (1, "fire-bolt"),
                     (3, "hellish-rebuke"), (5, "darkness")],
    },
}
# 血脉选项的中文名
LINEAGE_CN = {
    "drow": "卓尔 Drow", "high": "高等 High", "wood": "木精灵 Wood",
    "forest": "森林 Forest", "rock": "岩土 Rock",
    "abyssal": "深渊 Abyssal", "chthonic": "幽冥 Chthonic",
    "infernal": "炼狱 Infernal",
}

# 各施法职业 1 级: (戏法数, 1环法术数)
SPELL_COUNTS = {"bard": (2, 4), "cleric": (3, 4), "druid": (2, 4),
                "paladin": (0, 2), "ranger": (0, 2), "sorcerer": (4, 2),
                "warlock": (2, 2), "wizard": (3, 4)}

# 战斗风格 (2024: 战士1级/圣武士1级/游侠1级 各选一)
# 2024: 战斗风格是「专长」(Fighting Style feat), 共 10 种
FIGHTING_STYLES = {
    "defense": ("防御 Defense", "穿甲时 AC +1", {"ac": 1}),
    "archery": ("箭术 Archery", "远程武器攻击 +2", {"ranged_attack": 2}),
    "dueling": ("决斗 Dueling", "单手近战武器且另一手无武器时伤害 +2（可持盾）",
                {"dueling_dmg": 2}),
    "great_weapon": ("巨武器战斗 Great Weapon Fighting",
                     "双手/双手持用武器伤害骰掷出 1 或 2 可重掷（须采用新结果）", {}),
    "two_weapon": ("双武器战斗 Two-Weapon Fighting",
                   "双持轻武器时，副手攻击伤害加属性调整值", {}),
    "protection": ("守护 Protection", "持盾时反应: 使对同伴的攻击检定劣势", {}),
    "blind_fighting": ("盲斗 Blind Fighting", "获得 10 尺盲视", {"blindsight": 10}),
    "interception": ("拦截 Interception",
                     "持盾或武器时反应: 使同伴受到的伤害减 1d10+熟练加值", {}),
    "thrown_weapon": ("投掷武器战斗 Thrown Weapon Fighting",
                      "投掷武器伤害 +2；拔出投掷武器可作为攻击动作的一部分", {}),
    "unarmed": ("徒手战斗 Unarmed Fighting",
                "徒手打击 1d6（另一手空着则 1d8）；抓握目标每回合额外 1d4", {}),
}
# 战斗风格 (2024: 战士1级 / 圣武士2级 / 游侠2级 各选一, 其他职业没有)
STYLE_MIN_LEVEL = {"fighter": 1, "paladin": 2, "ranger": 2}

# 魔法物品 (影响 AC / 豁免 / 速度 / 属性设定值)
MAGIC_ITEMS = [
    {"id": "ring_protection", "name": "防护戒指 Ring of Protection",
     "ac": 1, "save": 1, "note": "AC +1，豁免 +1（需同调）"},
    {"id": "cloak_protection", "name": "防护斗篷 Cloak of Protection",
     "ac": 1, "save": 1, "note": "AC +1，豁免 +1（需同调）"},
    {"id": "bracers_defense", "name": "防御护腕 Bracers of Defense",
     "ac": 2, "no_armor": True, "note": "无甲且无盾时 AC +2"},
    {"id": "cloak_elvenkind", "name": "精灵斗篷 Cloak of Elvenkind",
     "note": "隐匿检定优势（隐蔽时）"},
    {"id": "boots_elvenkind", "name": "精灵靴 Boots of Elvenkind",
     "note": "潜行移动不发出声音"},
    {"id": "boots_speed", "name": "速度之靴 Boots of Speed",
     "speed": 30, "note": "速度 +30 尺（可消耗附赠动作疾走）"},
    {"id": "gauntlets_ogre", "name": "食人魔力量手套 Gauntlets of Ogre Power",
     "set_str": 19, "note": "力量变为 19（不叠加）"},
    {"id": "belt_hill_giant", "name": "山丘巨人力量腰带 Belt of Hill Giant Strength",
     "set_str": 21, "note": "力量变为 21"},
    {"id": "headband_intellect", "name": "智力头带 Headband of Intellect",
     "set_int": 19, "note": "智力变为 19"},
    {"id": "amulet_health", "name": "健康护符 Amulet of Health",
     "set_con": 19, "note": "体质变为 19"},
    {"id": "ring_free_action", "name": "自由行动戒指 Ring of Free Action",
     "note": "免疫束缚与麻痹、移动不受魔法限制"},
    {"id": "stone_luck", "name": "幸运石 Stone of Good Luck",
     "save": 1, "check": 1, "note": "豁免与属性检定 +1（需同调）"},
]
ITEMS_BY_ID = {i["id"]: i for i in MAGIC_ITEMS}


# ---- 起源专长 Origin Feat: 中文名 + 效果说明 ----
FEAT_INFO = {
    "Alert": ("警觉", "先攻检定 +熟练加值; 你掷先攻后可与一名自愿盟友交换先攻顺序"),
    "Crafter": ("巧匠", "获 3 种工匠工具熟练; 长休后可急造一件简单物品(持续到下次长休); "
                        "购买相关非魔法装备享折扣"),
    "Healer": ("医师", "医师工具熟练; 可用治疗包以动作为生物恢复生命值并稳定濒死者"),
    "Lucky": ("幸运", "幸运点 = 熟练加值(长休恢复); 自己的 d20 检定可花 1 点取优势, "
                      "或使攻击你的敌人该次攻击劣势"),
    "Magic Initiate (Cleric)": ("魔法入门·牧师", "习得牧师 2 个戏法 + 1 个 1 环法术; "
                                "每长休可不耗法术位施放该 1 环法术 1 次"),
    "Magic Initiate (Druid)": ("魔法入门·德鲁伊", "习得德鲁伊 2 个戏法 + 1 个 1 环法术; "
                               "每长休可不耗法术位施放该 1 环法术 1 次"),
    "Magic Initiate (Wizard)": ("魔法入门·法师", "习得法师 2 个戏法 + 1 个 1 环法术; "
                                "每长休可不耗法术位施放该 1 环法术 1 次"),
    "Musician": ("乐师", "3 种乐器熟练; 短休/长休后演奏, 为至多等同熟练加值数量的盟友"
                        "赋予英雄激励"),
    "Savage Attacker": ("凶蛮攻击者", "每回合 1 次: 武器伤害骰掷两次, 取较高值"),
    "Skilled": ("多面手", "任选 3 项技能或工具熟练 (可自由混合)"),
    "Tavern Brawler": ("酒馆斗殴者", "徒手打击伤害 1d4+力量; 徒手命中可将目标推离 5 尺; "
                              "徒手伤害骰掷出 1 可重掷"),
    "Tough": ("坚韧", "HP 上限 +2×当前等级, 此后每升 1 级再 +2"),
}

# ---- 其它英文 → 中文映射 ----
WEAPON_PROF_CN = {"simple": "简单武器", "martial": "军用武器",
                  "martial-light-property": "军用武器(轻型)",
                  "martial-finesse-or-light": "军用武器(灵巧/轻型)"}
ARMOR_PROF_CN = {"light": "轻甲", "medium": "中甲", "heavy": "重甲",
                 "shields": "盾牌"}
CAST_TYPE_CN = {"full": "全施法", "half": "半施法", "pact": "契约魔法"}
CAST_MODE_CN = {"prepared": "准备法术", "known": "已知法术",
                "spellbook": "法术书"}
SIZE_CN = {"Medium": "中型", "Small": "小型", "Large": "大型"}

TOOL_CN = {
    "Artisan's Tools": "工匠工具", "Calligrapher's Supplies": "书法家工具",
    "Carpenter's Tools": "木匠工具", "Cartographer's Tools": "制图师工具",
    "Forgery Kit": "伪造工具", "Gambling Set": "赌具", "Gaming Set": "游戏工具",
    "Herbalism Kit": "草药工具", "Musical Instrument": "乐器",
    "Navigator's Tools": "领航工具", "Thieves' Tools": "盗贼工具",
}

SUBCLASS_CN = {
    "Path of the Berserker": "狂战士道途", "Path of the Wild Heart": "荒野之心道途",
    "Path of the World Tree": "世界树道途", "Path of the Zealot": "狂热者道途",
    "College of Dance": "舞艺学院", "College of Glamour": "魅力学院",
    "College of Lore": "学识学院", "College of Valor": "勇气学院",
    "Life Domain": "生命领域", "Light Domain": "光明领域",
    "Trickery Domain": "诡术领域", "War Domain": "战争领域",
    "Circle of the Land": "大地结社", "Circle of the Moon": "月亮结社",
    "Circle of the Sea": "海洋结社", "Circle of the Stars": "星辰结社",
    "Battle Master": "战斗大师", "Champion": "冠军勇士",
    "Eldritch Knight": "魔能骑士", "Psi Warrior": "灵能武士",
    "Warrior of Mercy": "慈悲宗", "Warrior of Shadow": "暗影宗",
    "Warrior of the Elements": "元素宗", "Warrior of the Open Hand": "散打宗",
    "Oath of Devotion": "奉献之誓", "Oath of Glory": "荣耀之誓",
    "Oath of the Ancients": "远古之誓", "Oath of Vengeance": "复仇之誓",
    "Beast Master": "驯兽师", "Fey Wanderer": "妖精漫游者",
    "Gloom Stalker": "幽暗追猎者", "Hunter": "猎人",
    "Arcane Trickster": "奥法诡术师", "Assassin": "刺客",
    "Soulknife": "魂刃", "Thief": "盗贼",
    "Aberrant Sorcery": "异怪血脉", "Clockwork Sorcery": "机关血脉",
    "Draconic Sorcery": "龙族血脉", "Wild Magic": "狂野魔法",
    "Archfey Patron": "至高妖精宗主", "Celestial Patron": "天界宗主",
    "Fiend Patron": "邪魔宗主", "Great Old One Patron": "旧日支配者宗主",
    "Abjurer": "防护师", "Diviner": "预言师",
    "Evoker": "塑能师", "Illusionist": "幻术师",
}


def feat_cn(name):
    """'Musician' -> '乐师 Musician'"""
    info = FEAT_INFO.get(name)
    return f"{info[0]} {name}" if info else name


def feat_desc(name):
    """专长完整说明: '乐师 Musician: 3 种乐器熟练; ...'"""
    info = FEAT_INFO.get(name)
    return f"{info[0]} {name}: {info[1]}" if info else name


def tool_cn(name):
    cn = TOOL_CN.get(name)
    return f"{cn} {name}" if cn else name


def subclass_cn(name):
    cn = SUBCLASS_CN.get(name)
    return f"{cn} {name}" if cn else name


def size_cn(sizes):
    return "/".join(SIZE_CN.get(s, s) for s in sizes)

# (名称, 类别, 伤害, 专精)
WEAPONS = [
    ("木棒 Club", "简单", "1d4 钝击", "Slow"),
    ("匕首 Dagger", "简单", "1d4 穿刺", "Nick"),
    ("大棒 Greatclub", "简单", "1d8 钝击", "Push"),
    ("手斧 Handaxe", "简单", "1d6 挥砍", "Vex"),
    ("标枪 Javelin", "简单", "1d6 穿刺", "Slow"),
    ("轻锤 Light Hammer", "简单", "1d4 钝击", "Nick"),
    ("钉头锤 Mace", "简单", "1d6 钝击", "Sap"),
    ("木棍 Quarterstaff", "简单", "1d6 钝击", "Topple"),
    ("短镰 Sickle", "简单", "1d4 挥砍", "Nick"),
    ("长矛 Spear", "简单", "1d6 穿刺", "Sap"),
    ("飞镖 Dart", "简单", "1d4 穿刺", "Vex"),
    ("轻弩 Light Crossbow", "简单", "1d8 穿刺", "Slow"),
    ("投石索 Sling", "简单", "1d4 钝击", "Slow"),
    ("战斧 Battleaxe", "军用", "1d8 挥砍", "Topple"),
    ("连枷 Flail", "军用", "1d8 钝击", "Sap"),
    ("关刀 Glaive", "军用", "1d10 挥砍", "Graze"),
    ("巨斧 Greataxe", "军用", "1d12 挥砍", "Cleave"),
    ("巨剑 Greatsword", "军用", "2d6 挥砍", "Graze"),
    ("戟 Halberd", "军用", "1d10 挥砍", "Cleave"),
    ("骑枪 Lance", "军用", "1d12 穿刺", "Topple"),
    ("长剑 Longsword", "军用", "1d8 挥砍", "Sap"),
    ("大锤 Maul", "军用", "2d6 钝击", "Topple"),
    ("晨星 Morningstar", "军用", "1d8 穿刺", "Sap"),
    ("长枪 Pike", "军用", "1d10 穿刺", "Push"),
    ("细剑 Rapier", "军用", "1d8 穿刺", "Vex"),
    ("弯刀 Scimitar", "军用", "1d6 挥砍", "Nick"),
    ("短剑 Shortsword", "军用", "1d6 穿刺", "Vex"),
    ("三叉戟 Trident", "军用", "1d8 穿刺", "Topple"),
    ("战镐 War Pick", "军用", "1d8 穿刺", "Sap"),
    ("战锤 Warhammer", "军用", "1d8 钝击", "Push"),
    ("长鞭 Whip", "军用", "1d4 挥砍", "Slow"),
    ("吹箭 Blowgun", "军用", "1 穿刺", "Vex"),
    ("手弩 Hand Crossbow", "军用", "1d6 穿刺", "Vex"),
    ("重弩 Heavy Crossbow", "军用", "1d10 穿刺", "Push"),
    ("长弓 Longbow", "军用", "1d8 穿刺", "Slow"),
    ("火枪 Musket", "军用", "1d12 穿刺", "Slow"),
    ("手枪 Pistol", "军用", "1d10 穿刺", "Vex"),
]

# 灵巧武器(游荡者武器熟练范围)
FINESSSE_SET = {"匕首 Dagger", "短镰 Sickle", "飞镖 Dart", "细剑 Rapier",
                "弯刀 Scimitar", "短剑 Shortsword", "长鞭 Whip", "手弩 Hand Crossbow",
                "吹箭 Blowgun", "手枪 Pistol"}

ARMORS = [("无甲", None, None), ("布甲/皮甲(11+敏)", 11, None),
          ("镶钉皮甲(12+敏)", 12, None), ("兽皮甲(12+敏2)", 12, 2),
          ("锁链衫(13+敏2)", 13, 2), ("鳞甲(14+敏2)", 14, 2),
          ("胸板甲(14+敏2)", 14, 2), ("半身板甲(15+敏2)", 15, 2),
          ("环甲(14)", 14, 0), ("锁甲(16)", 16, 0),
          ("板条甲(17)", 17, 0), ("全身板甲(18)", 18, 0)]

# 与 ARMORS 一一对应的护甲类别 (熟练判定用)
ARMOR_CAT = [None, "light", "light", "medium", "medium", "medium",
             "medium", "medium", "heavy", "heavy", "heavy", "heavy"]
ARMOR_CAT_CN = {"light": "轻甲", "medium": "中甲", "heavy": "重甲",
                "shields": "盾牌"}

# 具备 Light 属性的武器 (2024)
LIGHT_WEAPONS = {"木棒 Club", "匕首 Dagger", "手斧 Handaxe", "轻锤 Light Hammer",
                 "短镰 Sickle", "短剑 Shortsword", "弯刀 Scimitar",
                 "手弩 Hand Crossbow"}

# 半施法者法术位 (2024: 圣武士/游侠从1级起施法)
HALF_SLOTS = {
    1: {1: 2}, 2: {1: 2}, 3: {1: 3}, 4: {1: 3}, 5: {1: 4, 2: 2},
    6: {1: 4, 2: 2}, 7: {1: 4, 2: 3}, 8: {1: 4, 2: 3}, 9: {1: 4, 2: 3, 3: 2},
    10: {1: 4, 2: 3, 3: 2}, 11: {1: 4, 2: 3, 3: 3}, 12: {1: 4, 2: 3, 3: 3},
    13: {1: 4, 2: 3, 3: 3, 4: 1}, 14: {1: 4, 2: 3, 3: 3, 4: 1},
    15: {1: 4, 2: 3, 3: 3, 4: 2}, 16: {1: 4, 2: 3, 3: 3, 4: 2},
    17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1}, 18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2}, 20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
}


# ----------------------------------------------------------------------------
# 界面主题 (暗色·龙与地下城风)
# ----------------------------------------------------------------------------

BG = "#17151c"        # 主背景
PANEL = "#211e29"     # 面板
CARD = "#2a2734"      # 卡片
CARD2 = "#353145"     # 按钮
BORDER = "#453f52"    # 边框
GOLD = "#c9a227"      # 主强调·金
GOLD2 = "#e8c34a"     # 亮金
RED = "#c0392b"       # 危险/扣血
RED2 = "#8e2f24"
GREEN = "#4e9a51"
TEXT = "#e8e6df"      # 主文字
DIM = "#9a97a3"       # 次要文字
PURPLE = "#b39ddb"    # 专精/豁免标记
INK = "#1a1512"       # 金底上的深字
TXT_BG = "#26242f"    # 文本框底

UI_FONT = "Microsoft YaHei UI"

TEXT_STYLE = dict(background=TXT_BG, foreground=TEXT, insertbackground=TEXT,
                  relief="flat", highlightthickness=1,
                  highlightbackground=BORDER, highlightcolor=GOLD,
                  font=(UI_FONT, 10))
LISTBOX_STYLE = dict(background=CARD, foreground=TEXT, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER,
                     highlightcolor=GOLD, selectbackground=GOLD,
                     selectforeground=INK, activestyle="none",
                     font=(UI_FONT, 10))


class ScrollFrame(ttk.Frame):
    """竖向滚动容器: 内容统一放进 self.body, 避免长列表撑破标签页。"""

    def __init__(self, master, height=400, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, height=height, highlightthickness=0,
                                bg=BG, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical",
                                 command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.body,
                                              anchor="nw")
        self.body.bind("<Configure>", self._sync_scroll)
        self.canvas.bind("<Configure>", self._sync_width)
        self.canvas.bind("<Enter>", self._wheel_on)
        self.canvas.bind("<Leave>", self._wheel_off)
        self.body.bind("<Enter>", self._wheel_on)
        self.body.bind("<Leave>", self._wheel_off)

    def _sync_scroll(self, _e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)

    def _wheel_on(self, _e=None):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _wheel_off(self, _e=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e):
        delta = -1 * (e.delta // 120) if e.delta else 0
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def to_top(self):
        self.canvas.yview_moveto(0)


# ----------------------------------------------------------------------------
# 规则引擎 (纯函数)
# ----------------------------------------------------------------------------

def ability_mod(score):
    return (score - 10) // 2


def mod_str(m):
    return ("+" if m >= 0 else "") + str(m)


def proficiency_bonus(level):
    return 2 + (level - 1) // 4


def roll_dice(expr):
    """解析 'NdM' / 'NdM+K' / 'NdM-K'，返回 (总数, 明细字符串)"""
    expr = expr.replace(" ", "")
    sign, k = 0, 0
    if "+" in expr:
        expr, ks = expr.split("+")
        sign, k = 1, int(ks)
    elif "-" in expr:
        expr, ks = expr.split("-")
        sign, k = -1, int(ks)
    n, m = expr.lower().split("d")
    n, m = int(n), int(m)
    rolls = [random.randint(1, m) for _ in range(n)]
    total = sum(rolls) + sign * k
    detail = "+".join(map(str, rolls))
    if n > 1:
        detail = f"({detail})"
    if sign:
        detail += ("+" if sign > 0 else "-") + str(k)
    return total, f"{expr}: [{detail}] = {total}"


def roll_4d6kh3():
    d = [random.randint(1, 6) for _ in range(4)]
    return sum(sorted(d, reverse=True)[:3])


def spell_detail(s):
    """法术详情文本 (向导与角色卡共用)"""
    if not s:
        return "选择法术查看详情。"
    lines = [f"{s['name']}  {s['name_en']}",
             f"{s['level']} 环 · {s['school']}    {s['cast']}    {s['range']}",
             f"成分: {s['comp']}    持续: {s['duration']}"
             + ("    【专注】" if s["concentration"] else "")
             + ("    【仪式】" if s["ritual"] else "")]
    extra = []
    if s["save"]:
        extra.append(f"{s['save']}豁免")
    if s["damage"]:
        extra.append(f"伤害 {s['damage']} {s['damage_type']}")
    if s["attack"]:
        extra.append("法术攻击")
    if s["area"]:
        extra.append(f"范围 {s['area']}")
    if extra:
        lines.append(" ｜ ".join(extra))
    lines.append("")
    lines.append(s["desc"] or "（效果见 SRD 原文）")
    sc = s.get("scaling") or {}
    if len(sc) > 1:
        up = "、".join(f"{k}环:{v}" for k, v in list(sc.items())[1:4])
        lines.append(f"升环: {up}")
    return "\n".join(lines)


class Rules:
    """封装 dnd55e_core_data.json"""

    def __init__(self, path=DATA_FILE):
        with open(path, encoding="utf-8") as f:
            self.d = json.load(f)
        self.classes_by_id = {c["id"]: c for c in self.d["classes"]}
        self.bg_by_id = {b["id"]: b for b in self.d["backgrounds"]}
        self.sp_by_id = {s["id"]: s for s in self.d["species"]}
        self.skill_by_id = {s["id"]: s for s in self.d["skills"]}
        self.armor_by_id = {a["id"]: a for a in self.d["armor"]}
        # 法术库 (SRD 5.2 快照; 文件缺失时降级为空库, 程序仍可用)
        self.spells = {}
        self.spells_by_class = {}
        self.spells_by_level = {}
        try:
            with open(SPELL_FILE, encoding="utf-8") as f:
                for s in json.load(f)["spells"]:
                    self.spells[s["id"]] = s
                    self.spells_by_level.setdefault(s["level"], []).append(s)
                    for c in s["classes"]:
                        self.spells_by_class.setdefault(c, []).append(s)
        except (OSError, ValueError, KeyError) as e:
            print("法术库载入失败:", e)
        # 职业特性 / 资源池 / 子职介绍 (SRD 5.2 抓取 + 中文整理)
        self.detail = {"classes": {}, "subclasses": {}}
        try:
            with open(DETAIL_FILE, encoding="utf-8") as f:
                self.detail = json.load(f)
        except (OSError, ValueError) as e:
            print("职业明细载入失败:", e)

    # ---- 职业明细 ----

    def class_detail(self, cid):
        return self.detail["classes"].get(cid) or {"features": [],
                                                   "resources": []}

    def class_features(self, cid):
        return self.class_detail(cid)["features"]

    def class_resources(self, cid):
        return self.class_detail(cid)["resources"]

    def sub_info(self, name):
        return self.detail["subclasses"].get(name)

    def sub_options(self, cid):
        """[(英文字职名, 中文名, 一句话定位)]"""
        out = []
        for s in self.cls(cid)["subclasses"]:
            info = self.sub_info(s)
            out.append((s, subclass_cn(s),
                        info["summary"] if info else ""))
        return out

    def spell(self, sid):
        return self.spells.get(sid)

    def class_spells(self, cid, level=None):
        out = self.spells_by_class.get(cid, [])
        if level is not None:
            out = [s for s in out if s["level"] == level]
        return sorted(out, key=lambda s: (s["level"], s["name"]))

    def cls(self, cid):
        return self.classes_by_id[cid]

    def bg(self, bid):
        return self.bg_by_id[bid]

    def sp(self, sid):
        return self.sp_by_id[sid]

    def full_slots(self, level):
        return {int(k): v for k, v in
                self.d["spell_slots"]["full_caster"][str(level)].items()}

    @staticmethod
    def class_mastery_pool(cls):
        """该职业可选武器专精的武器名单"""
        wep = cls.get("weapons", [])
        if "martial" in wep:
            return [w for w in WEAPONS]
        if cls["id"] == "rogue":
            return [w for w in WEAPONS
                    if w[1] == "简单" or w[0] in FINESSSE_SET]
        return [w for w in WEAPONS if w[1] == "简单"]


class Character:
    """角色数据模型"""

    def __init__(self, rules):
        self.r = rules
        self.name = "无名冒险者"
        self.level = 1
        self.xp = 0
        self.class_id = None
        self.subclass = None
        self.background_id = None
        self.species_id = None
        self.base_scores = {a: 10 for a in ABILITIES}
        self.bg_bonus = None          # {"mode":"2+1","plus2":ab,"plus1":ab} / {"mode":"111","ones":[..]}
        self.asi_history = []         # 每次ASI: {"type":"asi",...} 或 {"type":"feat","name":..}
        self.skill_prof = set()
        self.expertise = set()
        self.weapon_mastery = []      # 武器名列表
        self.armor_index = 0          # ARMORS 下标
        self.shield = False
        self.tough_feat = False       # Tough 专长
        self.hp_current = 1
        self.hp_temp = 0
        self.spell_slots_used = {}    # {环级: 已用}
        self.feats = []               # 其他专长名
        self.languages = "通用语, "
        self.equipment = ""
        self.notes = ""
        self.exhaustion = 0
        self.conditions = set()
        # ---- 2024 扩展: 法术 / 装备与加成来源 ----
        self.spells = {"cantrips": [], "prepared": []}
        self.weapon = ""              # 当前武器装备 (WEAPONS[0] 名称)
        self.weapon_magic = 0         # 武器魔法加值 +0..+3
        self.shield_magic = 0         # 盾牌魔法加值
        self.items = []               # MAGIC_ITEMS 的 id 列表
        self.fighting_style = None    # FIGHTING_STYLES key
        self.concentration = None     # 当前专注的法术 id
        self.lineage = None           # 精灵/侏儒/提夫林 血脉分支
        self.race_free_used = []      # 种族法术的「每长休免费一次」已用
        self.res_used = {}            # 职业资源已用点数 {资源 id: 已用}
        # ---- 2024 休息 / 濒死 / 战斗状态 ----
        self.hit_dice_used = 0        # 已消耗的生命骰 (总数 = 等级)
        self.death_success = 0        # 死亡豁免成功数 (3 即稳定)
        self.death_fail = 0           # 死亡豁免失败数 (3 即死亡)
        self.raging = False           # 野蛮人是否处于狂暴

    # ---- 派生数值 ----

    def score(self, ab):
        s = self.base_scores[ab]
        b = self.bg_bonus
        if b:
            if b["mode"] == "2+1":
                if b["plus2"] == ab:
                    s += 2
                elif b["plus1"] == ab:
                    s += 1
            else:
                if ab in b["ones"]:
                    s += 1
        for c in self.asi_history:
            if c.get("type") == "asi":
                if c.get("plus2") == ab:
                    s += 2
                if c.get("plus1") == ab:
                    s += 1
                if ab in c.get("ones", []):
                    s += 1
        s = min(20, s)
        # 魔法物品的属性设定值 (如力量腰带 21) 可突破 20 上限
        for iid in self.items:
            v = ITEMS_BY_ID.get(iid, {}).get("set_" + ab.lower())
            if v and v > s:
                s = v
        return s

    # ---- 种族自带法术 / 自动熟练 ----

    def species_spells(self, level=None):
        """[(解锁等级, 法术 id)] —— 按血脉分支与当前等级过滤"""
        lv = self.level if level is None else level
        ent = SPECIES_SPELLS.get(self.species_id or "")
        if not ent:
            return []
        if isinstance(ent, dict):                 # 有血脉分支
            ent = ent.get(self.lineage or "") or []
        return [(u, sid) for (u, sid) in ent
                if u <= lv and self.r.spell(sid)]

    def race_spell_ids(self):
        return [sid for _, sid in self.species_spells()]

    def auto_skills(self):
        return list(SPECIES_AUTO_SKILLS.get(self.species_id or "", []))

    # ---- 建卡/升级期的固定配额 (用于锁定「定死的东西」) ----

    def skill_quota(self):
        """职业允许自选的技能数"""
        return int(self.cls().get("skill_count") or 0)

    def class_skill_pool(self):
        return set(self.cls().get("skill_options") or [])

    def bg_skills(self):
        if not self.background_id:
            return set()
        return set(self.r.bg(self.background_id).get("skills") or [])

    def class_skill_picks(self):
        """已选的「职业技能」数量 (不含背景/种族)"""
        return len(self.skill_prof & self.class_skill_pool() - self.bg_skills())

    def expertise_allowance(self):
        """专精 (Expertise) 允许项数 —— 只有游荡者/吟游诗人/游侠拥有"""
        lv, n = self.level, 0
        if self.class_id == "rogue":
            n = 2 + (2 if lv >= 6 else 0)
        elif self.class_id == "bard":
            n = (2 if lv >= 2 else 0) + (2 if lv >= 9 else 0)
        elif self.class_id == "ranger":
            n = (1 if lv >= 2 else 0) + (2 if lv >= 9 else 0)
        return n

    def weapon_mastery_pool(self):
        return {w[0] for w in Rules.class_mastery_pool(self.cls())}

    def class_dice_text(self):
        """职业关键数值 (骰子/次数), 让没有资源池的职业也有信息可看"""
        parts = []
        d = self.class_stat("martial_arts_die", 0)
        if d:
            parts.append(f"武艺伤害骰 1d{d}")
        sa = self.class_stat("sneak_attack", None)
        if isinstance(sa, dict) and sa.get("dice_count"):
            parts.append(f"偷袭 {sa['dice_count']}d{sa.get('dice_value', 6)}")
        rd = self.class_stat("rage_damage_bonus", 0)
        if rd:
            parts.append(f"狂暴伤害 +{rd}")
        mv = self.class_stat("unarmored_movement_bonus", 0)
        if mv:
            parts.append(f"无甲移动 +{mv} 尺")
        bi = self.class_stat("bardic_inspiration_die", 0)
        if bi:
            parts.append(f"灵感骰 d{bi}")
        mc = self.mastery_count()
        if mc:
            parts.append(f"武器专精 {mc} 件")
        return "　·　".join(parts)

    def attunement_cap(self):
        """同调上限: 3 件 (盗贼 13 级「使用魔法装置」提升到 4)"""
        if (self.class_id == "rogue" and self.subclass == "Thief"
                and self.level >= 13):
            return 4
        return 3

    # ---- 法术配额 ----

    def max_spell_level(self):
        """当前能施放的最高环级 (由法术位表决定)"""
        slots = self.spell_slots()
        return max(slots) if slots else 0

    def cantrip_cap(self):
        """戏法数量: 职业基础值, 4 级/10 级各 +1 (2024)"""
        base = SPELL_COUNTS.get(self.class_id, (0, 0))[0]
        if base <= 0:
            return 0
        return base + (1 if self.level >= 4 else 0) + (1 if self.level >= 10 else 0)

    def prepared_hint(self):
        """准备/已知法术的参考数量 = 等级 + 施法属性调整值"""
        cst = self.casting()
        if not cst:
            return 0
        return max(1, self.level + ability_mod(self.score(cst["ability"])))

    def lineage_cn(self):
        return LINEAGE_CN.get(self.lineage or "", "")

    # ---- 职业特性 / 资源池 ----

    def class_features(self):
        """[(等级, 名称, 效果, 是否已解锁)] —— 只列本职业, 不含子职"""
        return [(f["level"], f["name"], f["desc"], f["level"] <= self.level)
                for f in self.r.class_features(self.class_id)]

    def subclass_summary(self):
        info = self.r.sub_info(self.subclass) if self.subclass else None
        return info["summary"] if info else ""

    def subclass_features(self):
        """[(等级, 名称, 效果, 是否已解锁)] —— 未选子职时为空"""
        info = self.r.sub_info(self.subclass) if self.subclass else None
        if not info:
            return []
        return [(f["level"], f["name"], f["desc"], f["level"] <= self.level)
                for f in info["features"]]

    def class_stat(self, key, default=0):
        """取 SRD 职业表中的数值 (如 martial_arts_die / sneak_attack)"""
        tbl = self.r.class_detail(self.class_id).get("class_specific") or {}
        row = tbl.get(str(self.level)) or tbl.get(self.level) or {}
        v = row.get(key, default)
        return v if v is not None else default

    def mastery_count(self):
        """武器专精件数: 优先用 SRD 逐级表, 否则退回核心数据"""
        v = self.class_stat("weapon_mastery", None)
        if v is not None and int(v) >= 0:
            return int(v)
        return int(self.cls().get("weapon_mastery_count") or 0)

    def resource_max(self, res):
        """资源上限: 表驱动或公式驱动"""
        tbl = res.get("table")
        if tbl:
            v = tbl.get(str(self.level), tbl.get(self.level))
            return max(0, int(v or 0))
        f = res.get("formula")
        if f == "level":
            return self.level
        if f == "cha_mod_min1":
            return max(1, ability_mod(self.score("CHA")))
        if f == "5*level":
            return 5 * self.level
        if f == "half_level_ceil":
            return (self.level + 1) // 2
        if f == "pact_slots":
            slots = self.spell_slots()
            return max(slots.values()) if slots else 0
        return 0

    def _res_die(self, res):
        die = res.get("die")
        if not die:
            return None
        best = None
        for k, v in die.items():
            if self.level >= int(k):
                best = v if best is None else max(best, v)
        return best

    def resources(self):
        """当前职业可用的资源池 (按等级过滤, 已含消耗状态)"""
        out = []
        for res in self.r.class_resources(self.class_id):
            if self.level < int(res.get("from_level", 1)):
                continue
            mx = self.resource_max(res)
            if mx <= 0 and not res.get("die"):
                continue
            used = max(0, min(mx, int(self.res_used.get(res["id"], 0))))
            out.append({
                "id": res["id"], "name": res["name"], "icon": res.get("icon", ""),
                "max": mx, "used": used, "left": mx - used,
                "die": self._res_die(res), "note": res.get("note", ""),
                "short": res.get("short", 0), "long": res.get("long", "all"),
                "short_after_level": res.get("short_after_level"),
                "short_after": res.get("short_after"),
            })
        return out

    def res_spend(self, rid, n=1):
        for res in self.r.class_resources(self.class_id):
            if res["id"] != rid:
                continue
            mx = self.resource_max(res)
            used = int(self.res_used.get(rid, 0))
            self.res_used[rid] = max(0, min(mx, used + n))
            return self.res_used[rid]
        return 0

    def res_restore(self, rid, n=1):
        return self.res_spend(rid, -n)

    def res_reset(self, rest="long"):
        """短休: 按每条资源的规则恢复; 长休: 清空"""
        if rest == "long":
            self.res_used = {}
            return
        for res in self.r.class_resources(self.class_id):
            rid = res["id"]
            if rid not in self.res_used:
                continue
            mx = self.resource_max(res)
            if res.get("short") == "all":
                self.res_used[rid] = 0
            elif res.get("short") == 1:
                self.res_used[rid] = max(0, int(self.res_used.get(rid, 0)) - 1)
            # 达到特定等级后短休也全恢复 (如诗人 5 级灵感泉源)
            lvl = res.get("short_after_level")
            if lvl and self.level >= int(lvl) and res.get("short_after") == "all":
                self.res_used[rid] = 0
            self.res_used[rid] = min(mx, self.res_used.get(rid, 0))

    def scores(self):
        return {a: self.score(a) for a in ABILITIES}

    def mods(self):
        return {a: ability_mod(self.score(a)) for a in ABILITIES}

    def pb(self):
        return proficiency_bonus(self.level)

    def cls(self):
        return self.r.cls(self.class_id)

    def casting(self):
        return self.cls().get("casting")

    def can_fighting_style(self):
        """战斗风格只有战士/圣武士/游侠拥有, 且需达到对应等级"""
        need = STYLE_MIN_LEVEL.get(self.class_id)
        return need is not None and self.level >= need

    def style_level_need(self):
        return STYLE_MIN_LEVEL.get(self.class_id)

    def hp_max(self):
        c = self.cls()
        hd = c["hit_die"]
        con = ability_mod(self.score("CON"))
        hp = hd + con + (self.level - 1) * (hd // 2 + 1 + con)
        if self.species_id == "dwarf":       # 矮人韧性
            hp += self.level
        if self.tough_feat:                  # Tough 专长
            hp += 2 * self.level
        return max(1, hp)

    def spell_slots(self):
        """返回 {环级: 最大次数}"""
        c = self.casting()
        if not c:
            return {}
        lv = self.level
        if c["type"] == "full":
            return self.r.full_slots(lv)
        if c["type"] == "half":
            return dict(HALF_SLOTS[lv])
        # pact magic (2024: 1级 1 个; 2–10级 2 个; 11–16级 3 个; 17+ 4 个)
        if lv == 1:
            n = 1
        elif lv >= 17:
            n = 4
        elif lv >= 11:
            n = 3
        else:
            n = 2
        sl = min(5, (lv + 1) // 2)
        slots = {sl: n}
        if lv >= 11:
            slots[6] = 1   # 秘契法术 Mystic Arcanum
        if lv >= 13:
            slots[7] = 1
        if lv >= 15:
            slots[8] = 1
        if lv >= 17:
            slots[9] = 1
        return slots

    def slots_recharge_short_rest(self):
        return bool(self.casting() and self.casting()["type"] == "pact")

    def arcanum_levels(self):
        """秘契法术 (Mystic Arcanum, 邪术师 11/13/15/17 级) —— 1 次/长休,
        不属于契约法术位, 短休不恢复。"""
        c = self.casting()
        if not c or c["type"] != "pact":
            return []
        return [lv for lv in (6, 7, 8, 9) if lv in self.spell_slots()]

    def ac(self):
        return self.ac_breakdown()[0]

    def has_feat(self, *keys):
        """专长是否持有 (英文原名或中文关键字命中任一即可)"""
        names = [str(f) for f in getattr(self, "feats", [])]
        bid = getattr(self, "background_id", None)
        if bid:
            bg = next((b for b in self.r.d["backgrounds"]
                       if b["id"] == bid), None)
            if bg:
                names.append(bg["origin_feat"])
        for f in names:
            low = f.lower()
            if any(k.lower() in low for k in keys):
                return True
        return False

    def initiative(self):
        m = ability_mod(self.score("DEX")) + self.check_bonus()
        if self.has_feat("Alert", "警觉"):      # 2024 Alert: 先攻 + 熟练加值
            m += self.pb()
        return m

    def check_bonus(self):
        """物品对「属性检定」的加值 (幸运石 +1, 同时加豁免)"""
        return sum(ITEMS_BY_ID.get(i, {}).get("check", 0) for i in self.items)

    def save_mod(self, ab):
        m = ability_mod(self.score(ab))
        if ab in self.cls()["saves"]:
            m += self.pb()
        for iid in self.items:                       # 防护戒指/斗篷/幸运石
            m += ITEMS_BY_ID.get(iid, {}).get("save", 0)
        # 守护灵光 (圣武士 6 级): 魅力调整值, 最低 +1
        if self.class_id == "paladin" and self.level >= 6:
            m += max(1, ability_mod(self.score("CHA")))
        return m

    def skill_mod(self, sid):
        sk = self.r.skill_by_id[sid]
        m = ability_mod(self.score(sk["ability"])) + self.check_bonus()
        if sid in self.expertise:
            m += 2 * self.pb()
        elif sid in self.skill_prof:
            m += self.pb()
        elif self.class_id == "bard" and self.level >= 2:    # 万事通: 半熟练
            m += self.pb() // 2
        return m

    # ---- 装备/攻击 ----

    def weapon_entry(self):
        for w in WEAPONS:
            if w[0] == self.weapon:
                return w
        return None

    def weapon_ability(self):
        """武器用哪个属性: 灵巧武器取高者; 远程用敏捷"""
        w = self.weapon_entry()
        if not w:
            return "STR"
        name = w[0]
        ranged = any(k in name for k in ("弩", "弓", "飞镖", "吹箭", "投石索"))
        if ranged:
            return "DEX"
        if name in FINESSSE_SET:
            return "STR" if self.score("STR") >= self.score("DEX") else "DEX"
        return "STR"

    def is_ranged_weapon(self):
        w = self.weapon_entry()
        return bool(w) and any(k in w[0] for k in ("弩", "弓", "飞镖", "吹箭", "投石索"))

    def is_two_handed_weapon(self):
        w = self.weapon_entry()
        return bool(w) and any(k in w[0] for k in ("巨", "大剑", "大锤", "长柄", "戟",
                                                    "关刀", "骑枪", "长枪", "重弩", "长弓"))

    # ---- 熟练判定 (武器/护甲/盾牌/工具) ----

    def weapon_prof_rules(self):
        try:
            return self.cls().get("weapons", [])
        except Exception:
            return []

    def has_weapon_prof(self, name=None):
        name = name or self.weapon
        w = next((x for x in WEAPONS if x[0] == name), None)
        if not w:
            return False
        rules = self.weapon_prof_rules()
        if "martial" in rules:
            return True
        cat = w[1]
        if cat == "简单" and "simple" in rules:
            return True
        if cat == "军用":
            if "martial-light-property" in rules and name in LIGHT_WEAPONS:
                return True
            if "martial-finesse-or-light" in rules and \
                    (name in LIGHT_WEAPONS or name in FINESSSE_SET):
                return True
        return False

    def armor_cat(self):
        return ARMOR_CAT[self.armor_index]

    def has_armor_prof_at(self, idx):
        cat = ARMOR_CAT[idx]
        if cat is None:
            return True
        return cat in self.cls().get("armor", [])

    def has_armor_prof(self):
        return self.has_armor_prof_at(self.armor_index)

    def has_shield_prof(self):
        return "shields" in self.cls().get("armor", [])

    def armor_penalty(self):
        """未熟练护甲/盾牌时的惩罚提示 (2024 规则)"""
        out = []
        if not self.has_armor_prof():
            out.append(f"⚠ 未熟练{ARMOR_CAT_CN.get(self.armor_cat(), '护甲')}："
                       "力量/敏捷 检定与豁免、攻击检定劣势，且无法施法")
        if self.shield and not self.has_shield_prof():
            out.append("⚠ 未熟练盾牌：力量/敏捷 检定与豁免、攻击检定劣势，且无法施法")
        return out

    def tool_profs(self):
        out = []
        if self.background_id:
            bg = next((b for b in self.r.d["backgrounds"]
                       if b["id"] == self.background_id), None)
            if bg:
                out.append(tool_cn(bg["tool"]))
        for t in (self.cls().get("tools") or []):
            out.append(tool_cn(t))
        return out

    def proficiency_report(self):
        """熟练项汇总 (角色卡展示)"""
        out = []
        rules = self.weapon_prof_rules()
        if "martial" in rules:
            wtxt = "简单武器 + 全部军用武器"
        elif "simple" in rules:
            extra = ""
            if "martial-light-property" in rules:
                extra = " + 带 Light 的军用武器"
            elif "martial-finesse-or-light" in rules:
                extra = " + 带 Finesse/Light 的军用武器"
            wtxt = "简单武器" + extra
        else:
            wtxt = "无"
        cur = f"当前：{self.weapon}" if self.weapon else "当前未装备"
        if self.weapon:
            cur += " ✓" if self.has_weapon_prof() else " ✗未熟练"
        out.append(f"武器：{wtxt}　｜　{cur}")
        arm = self.cls().get("armor", [])
        atxt = "、".join(ARMOR_CAT_CN[a] for a in arm) or "无"
        acur = ARMORS[self.armor_index][0] + (" ✓" if self.has_armor_prof()
                                              else " ✗未熟练")
        if self.shield:
            acur += "　｜　盾牌" + ("✓" if self.has_shield_prof() else "✗未熟练")
        out.append(f"护甲：{atxt}　｜　{acur}")
        tools = self.tool_profs()
        out.append("工具：" + ("、".join(f"{t} (+{self.pb()})" for t in tools)
                               if tools else "无"))
        out.append("语言：" + (self.languages.strip(" ,，") or "通用语"))
        out.append("豁免熟练：" + "、".join(ABILITY_CN[a]
                                           for a in self.cls()["saves"]))
        out.extend(self.armor_penalty())
        return out

    def attack_bonus(self):
        w = self.weapon_entry()
        if not w:
            return 0
        pb = self.pb() if self.has_weapon_prof(w[0]) else 0   # 未熟练不加熟练加值
        m = ability_mod(self.score(self.weapon_ability())) + pb + self.weapon_magic
        if self.fighting_style == "archery" and self.is_ranged_weapon():
            m += 2
        return m

    def damage_dice(self):
        w = self.weapon_entry()
        return w[2].split(" ")[0] if w else "1d4"

    def damage_type(self):
        w = self.weapon_entry()
        return w[2].split(" ")[1] if w and len(w[2].split(" ")) > 1 else ""

    def damage_bonus(self):
        w = self.weapon_entry()
        if not w:
            return 0
        m = ability_mod(self.score(self.weapon_ability())) + self.weapon_magic
        # 决斗: 单手近战武器且另一手没有武器（盾牌不算武器, 可以同时用）
        if self.fighting_style == "dueling" and not self.is_two_handed_weapon() \
                and not self.is_ranged_weapon():
            m += 2
        if self.class_id == "barbarian" and self.raging:   # 狂暴伤害加值
            m += self.rage_damage()
        return m

    def speed(self):
        """速度 = 种族基础 + 职业/物品加值 - 力竭(5×级) ；束缚类状态归零"""
        sp = 30
        if self.species_id:
            sp = self.r.sp(self.species_id).get("speed", 30)
        no_armor = self.armor_cat() is None
        # 野蛮人·快速移动 (5级, 非重甲)
        if self.class_id == "barbarian" and self.level >= 5 \
                and self.armor_cat() != "heavy":
            sp += 10
        # 武僧·无甲移动 (2/6/10/14/18 级 → +10/+15/+20/+25/+30, 需无甲无盾)
        if self.class_id == "monk" and self.level >= 2 and no_armor \
                and not self.shield:
            sp += (30 if self.level >= 18 else 25 if self.level >= 14
                   else 20 if self.level >= 10 else 15 if self.level >= 6
                   else 10)
        for iid in self.items:
            sp += ITEMS_BY_ID.get(iid, {}).get("speed", 0)
        sp -= 5 * self.exhaustion
        for cond in ("擒抱", "束缚", "麻痹", "震慑", "昏迷", "石化"):
            if cond in self.conditions:
                return 0
        return max(0, sp)

    def carry_capacity(self):
        """负重上限 = 力量 × 15 磅；推/拉/举 = 力量 × 30 磅"""
        s = self.score("STR")
        return s * 15, s * 30

    # ---- 2024 休息 / 濒死 / 专注 ----

    def hit_die(self):
        return self.cls()["hit_die"]

    def hit_dice_max(self):
        return max(1, self.level)          # 单职业: 生命骰数 = 等级

    def hit_dice_left(self):
        return max(0, self.hit_dice_max() - self.hit_dice_used)

    def spend_hit_dice(self, n=1, rolls=None):
        """短休花生命骰回血: 每颗 = d{生命骰} + 体质调整值
        rolls 可传入预先掷好的点数(测试用), 返回 (实际消耗, 回复量, 明细)"""
        n = max(0, min(n, self.hit_dice_left()))
        if n <= 0:
            return 0, 0, []
        con = ability_mod(self.score("CON"))
        die = self.hit_die()
        detail, total = [], 0
        for i in range(n):
            raw = rolls[i] if rolls and i < len(rolls) else random.randint(1, die)
            heal = max(1, raw + con)
            total += heal
            detail.append(f"d{die}={raw}{mod_str(con)}→{heal}")
        self.hit_dice_used += n
        self.hp_current = min(self.hp_max(), self.hp_current + total)
        return n, total, detail

    @property
    def is_dying(self):
        return self.hp_current <= 0

    def concentration_dc(self, damage):
        """受伤专注豁免 DC = max(10, 伤害 // 2)"""
        return max(10, int(damage) // 2)

    def condition_blocks_action(self):
        """这些状态下不能执行动作/施法"""
        return bool(self.conditions & {"失能", "麻痹", "震慑", "昏迷", "石化"})

    def attacks_per_action(self):
        """攻击动作的挥击次数 (含职业与子职的额外攻击)"""
        n = 1
        for lv, name, _d, unlocked in self.class_features():
            if not unlocked:
                continue
            if "三重额外攻击" in name:
                n = max(n, 4)
            elif "双重额外攻击" in name:
                n = max(n, 3)
            elif "额外攻击" in name:
                n = max(n, 2)
        for lv, name, _d, unlocked in self.subclass_features():
            if unlocked and "额外攻击" in name:
                n = max(n, 2)
        return n

    def sneak_dice(self):
        """偷袭骰数 (游荡者): 优先取 SRD 逐级表, 否则 1 级起每 2 级 +1d6"""
        if self.class_id != "rogue":
            return 0
        sa = self.class_stat("sneak_attack", None)
        if isinstance(sa, dict) and sa.get("dice_count"):
            return int(sa["dice_count"])
        return (self.level + 1) // 2

    def mastery_dc(self, wname):
        """武器专精的豁免 DC (撂倒/推撞等) = 8 + 攻击属性调整值 + 熟练加值"""
        w = next((x for x in WEAPONS if x[0] == wname), None)
        ab = "STR"
        if w:
            name = w[0]
            if any(k in name for k in ("弩", "弓", "飞镖", "吹箭", "投石索")):
                ab = "DEX"
            elif name in FINESSSE_SET:
                ab = "STR" if self.score("STR") >= self.score("DEX") else "DEX"
        pb = self.pb() if self.has_weapon_prof(wname) else 0
        return 8 + ability_mod(self.score(ab)) + pb

    def rage_damage(self):
        return self.class_stat("rage_damage_bonus", 0) or 0


    def ac_breakdown(self):
        """返回 (AC, [来源说明...])"""
        name, base, cap = ARMORS[self.armor_index]
        dex = ability_mod(self.score("DEX"))
        notes = []
        if base is None:
            if self.class_id == "barbarian":
                ac = 10 + dex + ability_mod(self.score("CON"))
                notes.append("无甲防御(野蛮人) 10+敏捷+体质")
            elif self.class_id == "monk" and not self.shield:
                ac = 10 + dex + ability_mod(self.score("WIS"))
                notes.append("无甲防御(武僧) 10+敏捷+感知")
            else:
                ac = 10 + dex
                notes.append(f"无甲 10+敏捷({mod_str(dex)})")
        else:
            used = dex if cap is None else min(dex, cap)
            ac = base + used
            notes.append(f"{name} {base}{mod_str(used)}")
        if self.shield:
            ac += 2 + self.shield_magic
            notes.append(f"盾牌 +{2 + self.shield_magic}")
        if self.fighting_style == "defense" and base is not None:
            ac += 1
            notes.append("战斗风格·防御 +1")
        for iid in self.items:
            it = ITEMS_BY_ID.get(iid, {})
            if it.get("no_armor") and base is not None:
                continue
            if it.get("ac"):
                ac += it["ac"]
                notes.append(f"{it['name'].split(' ')[0]} +{it['ac']}")
        return ac, notes

    def passive_perception(self):
        return 10 + self.skill_mod("perception")

    def spell_dc(self):
        c = self.casting()
        if not c:
            return None
        return 8 + ability_mod(self.score(c["ability"])) + self.pb()

    def spell_attack(self):
        c = self.casting()
        if not c:
            return None
        return ability_mod(self.score(c["ability"])) + self.pb()

    def bonus_breakdown(self):
        """列出所有自动生效的加值来源, 便于核对"""
        out = []
        if self.species_id:
            sp = self.r.sp(self.species_id)
            if self.species_id == "dwarf":
                out.append(f"种族·矮人韧性: HP 上限 +{self.level}")
            if self.species_id in ("human", "elf"):
                out.append(f"种族·{sp['name']}: 额外 1 项技能熟练")
        if self.tough_feat or self.has_feat("Tough", "坚忍"):
            out.append(f"专长·Tough: HP 上限 +{2 * self.level}")
        if self.has_feat("Alert", "警觉"):
            out.append(f"专长·Alert: 先攻 +{self.pb()} (熟练加值)")
        if self.class_id in ("barbarian", "monk") and ARMORS[self.armor_index][1] is None:
            out.append("职业·无甲防御: AC 计入第二属性")
        if self.class_id == "barbarian" and self.level >= 5:
            out.append("职业·快速移动: 速度 +10 尺")
        if self.class_id == "monk" and self.level >= 2:
            out.append("职业·无甲移动: 速度提升")
        if self.class_id == "paladin" and self.level >= 6:
            out.append(f"职业·守护灵光(10尺): 豁免 "
                       f"+{max(1, ability_mod(self.score('CHA')))} (魅力, 最低 +1)")
        if self.class_id == "bard" and self.level >= 2:
            out.append(f"职业·万事通: 非熟练检定 +{self.pb() // 2}")
        if self.fighting_style:
            nm, desc, _ = FIGHTING_STYLES[self.fighting_style]
            out.append(f"战斗风格·{nm}: {desc}")
        for iid in self.items:
            it = ITEMS_BY_ID.get(iid, {})
            out.append(f"物品·{it.get('name')}: {it.get('note', '')}")
        if self.weapon_magic:
            out.append(f"武器魔法加值: 命中/伤害 +{self.weapon_magic}")
        if self.shield_magic:
            out.append(f"盾牌魔法加值: AC +{self.shield_magic}")
        # 熟练项提醒
        if self.weapon and not self.has_weapon_prof(self.weapon):
            out.append(f"⚠ 未熟练武器「{self.weapon}」：攻击检定不加熟练加值"
                       f"（当前命中 {mod_str(self.attack_bonus())}）")
        out.extend(self.armor_penalty())
        # 职业里程碑 (信息提示, 数值需按情境判定)
        lv = self.level
        n_atk = self.attacks_per_action()
        if n_atk > 1:
            out.append(f"职业·额外攻击: 攻击动作可攻击 {n_atk} 次 "
                       f"（掷攻击会一次投 {n_atk} 个 d20）")
        if self.class_id == "barbarian" and lv >= 1:
            rd = self.rage_damage()
            if self.raging:
                out.append(f"职业·狂暴(进行中): 伤害 +{rd} 已计入 · "
                           "物理伤害抗性 · 力量检定/豁免优势 · 不能专注")
            else:
                out.append(f"职业·狂暴: 伤害 +{rd}，物理伤害抗性 "
                           "（在「职业」页点开狂暴后再算）")
        if self.class_id == "rogue":
            n = self.sneak_dice()
            out.append(f"职业·偷袭: 额外 {n}d6 (优势或同伴相邻时，"
                       "勾选「含偷袭」后掷伤害会加上)")
        if self.class_id == "monk":
            d = self.class_stat("martial_arts_die", 0)
            out.append(f"职业·武艺: 徒手/武僧武器伤害骰 "
                       f"{('1d%d' % d) if d else '1d4'}（附赠动作可再攻击 1 次）")
        if self.class_id == "paladin" and lv >= 2:
            out.append("职业·至圣斩: 命中后可用法术位追加 2d8 光耀 (每击一次)")
        # 其余专长: 明确提示需手动应用, 避免误以为已计入
        auto = ("tough", "alert", "坚忍", "坚韧", "警觉")
        manual = [f for f in list(self.feats)
                  if not any(k in f.lower() for k in auto)]
        if manual:
            out.append("其余专长 (需手动应用): " + "、".join(feat_cn(f) for f in manual))
        return out

    # ---- 检定 ----

    def d20_mod_total(self, mod):
        """d20 检定附加修正(含力竭惩罚)"""
        return mod - 2 * self.exhaustion

    def roll_d20(self, label, mod):
        raw = random.randint(1, 20)
        total = raw + self.d20_mod_total(mod)
        ex = f" (力竭-{2 * self.exhaustion})" if self.exhaustion else ""
        return f"{label}\nd20: {raw} {mod_str(mod)}{ex} = {total}"

    # ---- 序列化 ----

    def to_dict(self):
        return {
            "system": "dnd55e-character v1",
            "name": self.name, "level": self.level, "xp": self.xp,
            "class_id": self.class_id, "subclass": self.subclass,
            "background_id": self.background_id, "species_id": self.species_id,
            "base_scores": self.base_scores, "bg_bonus": self.bg_bonus,
            "asi_history": self.asi_history,
            "skill_prof": sorted(self.skill_prof),
            "expertise": sorted(self.expertise),
            "weapon_mastery": self.weapon_mastery,
            "armor_index": self.armor_index, "shield": self.shield,
            "tough_feat": self.tough_feat,
            "hp_current": self.hp_current, "hp_temp": self.hp_temp,
            "spell_slots_used": self.spell_slots_used,
            "feats": self.feats, "languages": self.languages,
            "equipment": self.equipment, "notes": self.notes,
            "exhaustion": self.exhaustion,
            "conditions": sorted(self.conditions),
            "spells": self.spells,
            "weapon": self.weapon, "weapon_magic": self.weapon_magic,
            "shield_magic": self.shield_magic,
            "items": self.items, "fighting_style": self.fighting_style,
            "concentration": self.concentration,
            "lineage": self.lineage,
            "race_free_used": self.race_free_used,
            "res_used": self.res_used,
            "hit_dice_used": self.hit_dice_used,
            "death_success": self.death_success,
            "death_fail": self.death_fail,
            "raging": self.raging,
        }

    def load_dict(self, d):
        """从存档字典恢复, 所有字段做边界钳制/白名单校验, 坏数据不崩。"""
        def _int(v, default, lo, hi):
            try:
                return max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                return default

        known_cls = {c["id"] for c in self.r.d["classes"]}
        known_bg = {b["id"] for b in self.r.d["backgrounds"]}
        known_sp = {s["id"] for s in self.r.d["species"]}
        known_sk = {s["id"] for s in self.r.d["skills"]}
        known_wp = {w[0] for w in WEAPONS}

        self.name = str(d.get("name") or self.name)[:40]
        self.level = _int(d.get("level"), 1, 1, 20)
        self.xp = _int(d.get("xp"), 0, 0, 10 ** 9)
        cid = d.get("class_id")
        self.class_id = cid if cid in known_cls else self.r.d["classes"][0]["id"]
        sub = d.get("subclass")
        valid_subs = self.cls()["subclasses"] + [subclass_cn(s) for s in
                                                 self.cls()["subclasses"]]
        self.subclass = sub if sub in valid_subs else None
        bid = d.get("background_id")
        self.background_id = bid if bid in known_bg else self.r.d["backgrounds"][0]["id"]
        sid = d.get("species_id")
        legacy_sp = LEGACY_SPECIES.get(sid)
        if legacy_sp:                # 旧存档里的 5e 传承种族 → 2024 对应种族
            sid = legacy_sp
        self.species_id = sid if sid in known_sp else self.r.d["species"][0]["id"]

        bs = d.get("base_scores") or {}
        self.base_scores = {a: _int(bs.get(a), 10, 1, 20) for a in ABILITIES}

        bg = d.get("bg_bonus")
        if isinstance(bg, dict) and bg.get("mode") in ("2+1", "111"):
            if bg["mode"] == "2+1":
                p2, p1 = bg.get("plus2"), bg.get("plus1")
                if p2 in ABILITIES and p1 in ABILITIES and p2 != p1:
                    self.bg_bonus = {"mode": "2+1", "plus2": p2, "plus1": p1}
            else:
                ones = [a for a in (bg.get("ones") or []) if a in ABILITIES]
                if len(ones) == 3 and len(set(ones)) == 3:
                    self.bg_bonus = {"mode": "111", "ones": ones}

        self.asi_history = [x for x in (d.get("asi_history") or [])
                            if isinstance(x, dict)]
        self.skill_prof = {s for s in (d.get("skill_prof") or [])
                           if s in known_sk}
        self.expertise = {s for s in (d.get("expertise") or [])
                          if s in self.skill_prof}
        # 专精数量不得超过职业/等级的允许值
        exp_allow = self.expertise_allowance()
        if len(self.expertise) > exp_allow:
            ordered = [s["id"] for s in self.r.d["skills"]
                       if s["id"] in self.expertise]
            self.expertise = set(ordered[:exp_allow])
        # 武器专精: 数量按等级, 且只能取本职业熟练范围内的武器
        mc = self.mastery_count()
        pool = self.weapon_mastery_pool()
        self.weapon_mastery = [w for w in (d.get("weapon_mastery") or [])
                               if w in known_wp and (not pool or w in pool)][:mc]
        self.armor_index = _int(d.get("armor_index"), 0, 0, len(ARMORS) - 1)
        self.shield = bool(d.get("shield", False))
        self.tough_feat = bool(d.get("tough_feat", False))
        self.spell_slots_used = {}
        max_slots = self.spell_slots()
        for k, v in (d.get("spell_slots_used") or {}).items():
            kk = _int(k, 0, 1, 9)
            if kk in max_slots:
                self.spell_slots_used[kk] = _int(v, 0, 0, max_slots[kk])
        self.feats = [str(x)[:40] for x in (d.get("feats") or [])][:20]
        self.languages = str(d.get("languages") or "通用语")[:120]
        self.equipment = str(d.get("equipment") or "")[:4000]
        self.notes = str(d.get("notes") or "")[:20000]
        if legacy_sp:                # 迁移说明写进备注, 不静默改动
            tip = (f"※ 旧存档中的「{LEGACY_SPECIES_CN.get(d.get('species_id'), '')}」"
                   f"已按 2024 规则改为「{self.r.sp(self.species_id)['name']}」"
                   f"（5.5e 种族不加属性），请复核种族与属性。")
            if tip not in self.notes:
                self.notes = (tip + "\n" + self.notes)[:20000]
        self.exhaustion = _int(d.get("exhaustion"), 0, 0, 6)
        self.conditions = {c for c in (d.get("conditions") or [])
                           if c in CONDITIONS}
        # ---- 2024 扩展字段 (全部白名单校验) ----
        known_sp_ids = set(self.r.spells)
        sp = d.get("spells") or {}
        def _sp_list(key, lv_filter=None):
            out = []
            for sid in (sp.get(key) or []):
                rec = self.r.spell(sid)
                if not rec:
                    continue
                if lv_filter is not None and rec["level"] != lv_filter:
                    continue
                if rec["level"] == 0 and lv_filter is None and key == "prepared":
                    continue
                out.append(sid)
            return out[:40]
        self.spells = {"cantrips": _sp_list("cantrips", 0),
                       "prepared": _sp_list("prepared")}
        self.weapon = d.get("weapon") if d.get("weapon") in known_wp else ""
        self.weapon_magic = _int(d.get("weapon_magic"), 0, 0, 3)
        self.shield_magic = _int(d.get("shield_magic"), 0, 0, 3)
        self.items = [i for i in (d.get("items") or []) if i in ITEMS_BY_ID][:20]
        fs = d.get("fighting_style")
        self.fighting_style = fs if fs in FIGHTING_STYLES else None
        if self.fighting_style and not self.can_fighting_style():
            self.fighting_style = None       # 该职业/等级没有战斗风格特性
        conc = d.get("concentration")
        self.concentration = conc if conc in known_sp_ids else None
        lin = d.get("lineage")
        ent = SPECIES_SPELLS.get(self.species_id or "")
        self.lineage = lin if (isinstance(ent, dict) and lin in ent) else None
        self.race_free_used = [s for s in (d.get("race_free_used") or [])
                               if s in known_sp_ids][:10]
        # 职业资源: 只接受本职业真实存在的资源 id, 并钳制到上限
        self.res_used = {}
        raw_res = d.get("res_used")
        if isinstance(raw_res, dict):
            for res in self.r.class_resources(self.class_id):
                rid = res["id"]
                if rid in raw_res:
                    mx = self.resource_max(res)
                    self.res_used[rid] = _int(raw_res.get(rid), 0, 0, mx)
        self.skill_prof |= set(self.auto_skills())
        # 休息 / 濒死 / 姿态
        self.hit_dice_used = _int(d.get("hit_dice_used"), 0,
                                  0, self.hit_dice_max())
        self.death_success = _int(d.get("death_success"), 0, 0, 3)
        self.death_fail = _int(d.get("death_fail"), 0, 0, 3)
        self.raging = bool(d.get("raging", False)) and self.class_id == "barbarian"
        # 最后钳制 HP (依赖上面的 level/scores/species/tough)
        self.hp_temp = _int(d.get("hp_temp"), 0, 0, 999)
        self.hp_current = _int(d.get("hp_current"), self.hp_max(),
                               0, self.hp_max())


# ----------------------------------------------------------------------------
# 建卡向导
# ----------------------------------------------------------------------------

class Wizard(tk.Toplevel):
    """六步建卡向导 (模态)"""

    def __init__(self, master, rules, on_finish):
        super().__init__(master)
        if not master.winfo_viewable():   # 后台测试: 父窗口不可见时不弹出
            self.withdraw()
        self.r = rules
        self.on_finish = on_finish
        self.title("新建角色 · D&D 5.5e 建卡向导")
        self.geometry("740x720")
        self.minsize(700, 560)
        self.transient(master)
        self.configure(bg=BG)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        self.data = {
            "name": "", "class_id": None, "background_id": None,
            "species_id": None, "base_scores": {}, "bg_bonus": None,
            "skill_prof": set(), "weapon_mastery": [], "human_feat": None,
        }
        self.step = 0
        self.steps = [self._step_class, self._step_background, self._step_species,
                      self._step_abilities, self._step_skills]
        if True:  # 武器专精步骤按职业条件插入
            self.steps.append(self._step_mastery)
        self.steps.append(self._step_spells)      # 仅施法职业显示
        self.steps.append(self._step_summary)

        # 底部导航必须先 pack (side=bottom): pack 按顺序分配空间,
        # 后 pack 的侧栏永远先拿到空间, 内容再高也不会把导航挤出窗口
        self.progress = ttk.Label(self, text="", anchor="center",
                                  padding=(0, 4))
        self.progress.pack(fill="x", side="bottom")
        nav = ttk.Frame(self, padding=(10, 4))
        nav.pack(fill="x", side="bottom")
        self.btn_prev = ttk.Button(nav, text="← 上一步", command=self.prev,
                                   state="disabled")
        self.btn_prev.pack(side="left", padx=4)
        self.btn_next = ttk.Button(nav, text="下一步 →", command=self.next)
        self.btn_next.pack(side="right", padx=4)

        self.container = ttk.Frame(self, padding=10)
        self.container.pack(fill="both", expand=True)
        self.render_step()

    # ---- 流程控制 ----

    def render_step(self):
        for w in self.container.winfo_children():
            w.destroy()
        vis = [i for i in range(len(self.steps)) if not self._skip(i)]
        pos = vis.index(self.step) + 1 if self.step in vis else 1
        self.progress.config(text=f"第 {pos} / {len(vis)} 步")
        self.btn_prev.config(state="normal" if vis[0] != self.step else "disabled")
        self.btn_next.config(
            text="完成 ✓" if self.step == vis[-1] else "下一步 →")
        self.steps[self.step]()

    def _skip(self, idx):
        """某些步骤按职业条件跳过 (如无法术职业跳过选法术)"""
        fn = self.steps[idx]
        if fn == self._step_spells:
            cid = self.data.get("class_id")
            if not (cid and self.r.cls(cid).get("casting")):
                return True
            # 本地法术库缺失时不卡住建卡, 直接跳过
            return not self.r.class_spells(cid)
        return False

    def prev(self):
        prv = self.step - 1
        while prv > 0 and self._skip(prv):
            prv -= 1
        if prv >= 0:
            self.step = prv
            self.render_step()

    def next(self):
        if not self.validate_step():
            return
        vis = [i for i in range(len(self.steps)) if not self._skip(i)]
        if self.step == vis[-1]:
            self.finish()
            return
        nxt = self.step + 1
        while nxt < len(self.steps) - 1 and self._skip(nxt):
            nxt += 1
        self.step = nxt
        self.render_step()

    def validate_step(self):
        fn = getattr(self, f"_validate_{self.step}", None)
        return fn() if fn else True

    # ---- Step 0: 职业 ----

    def _step_class(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="① 选择职业", font=("", 13, "bold")).pack(anchor="w")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="角色姓名:").pack(side="left")
        self.e_name = ttk.Entry(row, width=18)
        self.e_name.insert(0, self.data["name"])
        self.e_name.pack(side="left", padx=6)
        ttk.Label(row, text="职业:").pack(side="left", padx=(10, 2))
        self.cb_class = ttk.Combobox(row, state="readonly", width=22,
                                     values=[c["name"] for c in self.r.d["classes"]])
        if self.data["class_id"]:
            self.cb_class.set(self.r.cls(self.data["class_id"])["name"])
        self.cb_class.pack(side="left")
        self.cb_class.bind("<<ComboboxSelected>>", lambda e: self._show_class())

        self.txt_class = tk.Text(f, height=20, wrap="word", state="disabled",
                                 background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        self.txt_class.pack(fill="both", expand=True, pady=(6, 0))
        self._show_class()

    def _show_class(self):
        name = self.cb_class.get()
        found = False
        for c in self.r.d["classes"]:
            if c["name"] == name:
                found = True
                self.data["class_id"] = c["id"]
                cast = c.get("casting")
                cast_s = (f"施法: {CAST_TYPE_CN.get(cast['type'], cast['type'])} / "
                          f"施法属性 {ABILITY_CN.get(cast['ability'], cast['ability'])} / "
                          f"{CAST_MODE_CN.get(cast['mode'], cast['mode'])}"
                          if cast else "无施法能力")
                weapons = "、".join(WEAPON_PROF_CN.get(w, w)
                                    for w in c["weapons"])
                armor = "、".join(ARMOR_PROF_CN.get(a, a)
                                  for a in c["armor"]) or "无"
                pool_txt = ("任意 18 项技能" if c["skill_options"] == "*any*"
                            else "、".join(self.r.skill_by_id[s]["name"]
                                          for s in c["skill_options"]
                                          if s in self.r.skill_by_id))
                text = (
                    f"{c['name']}\n{'-' * 46}\n"
                    f"生命骰: d{c['hit_die']}    1级HP: {c['hit_die']}+体质调整值"
                    f"    每级固定HP: {c['fixed_hp_per_level']}\n"
                    f"主属性: {' / '.join(ABILITY_CN[a] for a in c['primary'])}    "
                    f"豁免熟练: {' / '.join(ABILITY_CN[a] for a in c['saves'])}\n"
                    f"技能选择数: {c['skill_count']} 项    "
                    f"武器专精: {(str(c['weapon_mastery_count']) + ' 件') if c['weapon_mastery_count'] else '无'}\n"
                    f"武器熟练: {weapons}\n"
                    f"护甲训练: {armor}\n"
                    f"{cast_s}\n\n"
                    f"子职 (3级选): {' / '.join(subclass_cn(s) for s in c['subclasses'])}\n\n"
                    f"技能候选池 ({len(c['skill_options']) if c['skill_options'] != '*any*' else 18} 项):\n{pool_txt}"
                )
                self.txt_class.config(state="normal")
                self.txt_class.delete("1.0", "end")
                self.txt_class.insert("1.0", text)
                self.txt_class.config(state="disabled")
                break
        if not found:
            self.txt_class.config(state="normal")
            self.txt_class.delete("1.0", "end")
            self.txt_class.insert("1.0",
                "\n\n  ⬆ 从上方下拉框选择一个职业，\n"
                "     这里会显示生命骰 / 豁免 / 技能池 / 子职 / 施法等完整详情。")
            self.txt_class.config(state="disabled")

    def _validate_0(self):
        self.data["name"] = self.e_name.get().strip() or "无名冒险者"
        if not self.data["class_id"]:
            messagebox.showwarning("提示", "请选择一个职业", parent=self)
            return False
        return True

    # ---- Step 1: 背景 ----

    def _step_background(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="② 选择背景 (决定属性加值 / 起源专长 / 技能 / 工具)",
                  font=("", 13, "bold")).pack(anchor="w")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="背景:").pack(side="left")
        self.cb_bg = ttk.Combobox(row, state="readonly", width=24,
                                  values=[b["name"] for b in self.r.d["backgrounds"]])
        if self.data["background_id"]:
            self.cb_bg.set(self.r.bg(self.data["background_id"])["name"])
        self.cb_bg.pack(side="left", padx=6)
        self.cb_bg.bind("<<ComboboxSelected>>", lambda e: self._render_bg_ui())

        self.bg_info = ttk.Label(f, text="", justify="left", wraplength=640)
        self.bg_info.pack(anchor="w", pady=4)
        self.bg_frame = ttk.LabelFrame(f, text="属性加值分配 (候选三项)")
        self.bg_frame.pack(fill="x", pady=6)
        self._render_bg_ui()

    def _render_bg_ui(self):
        for w in self.bg_frame.winfo_children():
            w.destroy()
        name = self.cb_bg.get()
        bg = None
        for b in self.r.d["backgrounds"]:
            if b["name"] == name:
                bg = b
                self.data["background_id"] = b["id"]
        if not bg:
            self.bg_info.config(text="请选择背景")
            return
        skills = "、".join(self.r.skill_by_id[s]["name"] for s in bg["skills"])
        feat_raw = bg["origin_feat"]
        self.bg_info.config(text=(
            f"{bg['name']}  |  专长: {feat_cn(feat_raw)}  |  "
            f"技能: {skills}  |  工具: {tool_cn(bg['tool'])}\n"
            f"专长效果: {feat_desc(feat_raw)}\n"
            f"装备包或 50gp；种族不再提供属性加值。"))

        self.bg_mode = tk.StringVar(value="2+1")
        r1 = ttk.Frame(self.bg_frame)
        r1.pack(anchor="w", fill="x", pady=2)
        ttk.Radiobutton(r1, text="+2 加一项, +1 加另一项", variable=self.bg_mode,
                        value="2+1", command=self._render_bg_picks).pack(side="left")
        ttk.Radiobutton(r1, text="三项各 +1", variable=self.bg_mode,
                        value="111", command=self._render_bg_picks).pack(side="left", padx=12)

        self.bg_picks = ttk.Frame(self.bg_frame)
        self.bg_picks.pack(anchor="w", pady=4)
        self._bg_abs = bg["abilities"]
        self._render_bg_picks()

    def _render_bg_picks(self):
        for w in self.bg_picks.winfo_children():
            w.destroy()
        names = [f"{ABILITY_CN[a]}({a})" for a in self._bg_abs]
        if self.bg_mode.get() == "2+1":
            ttk.Label(self.bg_picks, text="+2 →").pack(side="left")
            self.bg_p2 = ttk.Combobox(self.bg_picks, state="readonly", width=13,
                                      values=names)
            self.bg_p2.pack(side="left", padx=4)
            self.bg_p2.bind("<<ComboboxSelected>>",
                            lambda e: self._bg_dedup("p2"))
            ttk.Label(self.bg_picks, text="+1 →").pack(side="left", padx=(12, 0))
            self.bg_p1 = ttk.Combobox(self.bg_picks, state="readonly", width=13,
                                      values=names)
            self.bg_p1.pack(side="left", padx=4)
            self.bg_p1.bind("<<ComboboxSelected>>",
                            lambda e: self._bg_dedup("p1"))
        else:
            self.bg_o = []
            for i in range(3):
                ttk.Label(self.bg_picks, text=f"+1 →").pack(side="left",
                                                            padx=(0 if i == 0 else 12, 0))
                cb = ttk.Combobox(self.bg_picks, state="readonly", width=13,
                                  values=names)
                cb.pack(side="left", padx=4)
                cb.bind("<<ComboboxSelected>>",
                        lambda e, box=cb: self._bg_dedup(box))
                self.bg_o.append(cb)

    def _bg_dedup(self, source):
        """同一加值不可重复选同一属性: 实时清掉冲突的另一项"""
        if self.bg_mode.get() == "2+1":
            if self.bg_p2.get() and self.bg_p1.get() \
                    and self.bg_p2.get() == self.bg_p1.get():
                (self.bg_p1 if source == "p2" else self.bg_p2).set("")
        else:
            cur = source.get()
            if cur:
                for cb in self.bg_o:
                    if cb is not source and cb.get() == cur:
                        cb.set("")

    def _validate_1(self):
        if not self.data["background_id"]:
            messagebox.showwarning("提示", "请选择一个背景", parent=self)
            return False
        mode = self.bg_mode.get()
        if mode == "2+1":
            a, b = self.bg_p2.get(), self.bg_p1.get()
            if not a or not b:
                messagebox.showwarning("提示", "请完成 +2 / +1 分配", parent=self)
                return False
            if a == b:
                messagebox.showwarning("提示", "+2 和 +1 必须分配给不同属性", parent=self)
                return False
            ab2, ab1 = ab_from_display(a), ab_from_display(b)
            if ab2 not in self._bg_abs or ab1 not in self._bg_abs:
                messagebox.showwarning("提示", "只能从背景候选的三项属性中选择",
                                       parent=self)
                return False
            self.data["bg_bonus"] = {"mode": "2+1", "plus2": ab2, "plus1": ab1}
        else:
            vals = [cb.get() for cb in self.bg_o]
            if any(not v for v in vals) or len(set(vals)) != 3:
                messagebox.showwarning("提示", "三项 +1 必须各不相同", parent=self)
                return False
            abs_ = [ab_from_display(v) for v in vals]
            if any(x not in self._bg_abs for x in abs_):
                messagebox.showwarning("提示", "只能从背景候选的三项属性中选择",
                                       parent=self)
                return False
            self.data["bg_bonus"] = {"mode": "111", "ones": abs_}
        return True

    # ---- Step 2: 种族 ----

    def _step_species(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="③ 选择种族 Species (体型/速度/特性, 无属性加值)",
                  font=("", 13, "bold")).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="种族:").pack(side="left")
        self.cb_sp = ttk.Combobox(row, state="readonly", width=24,
                                  values=[s["name"] for s in self.r.d["species"]])
        if self.data["species_id"]:
            self.cb_sp.set(self.r.sp(self.data["species_id"])["name"])
        self.cb_sp.pack(side="left", padx=6)
        self.cb_sp.bind("<<ComboboxSelected>>", lambda e: self._show_species())
        self.txt_sp = tk.Text(f, height=13, wrap="word", state="disabled",
                              background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        self.txt_sp.pack(fill="both", expand=True)
        # 种族血脉 (精灵/侏儒/提夫林): 影响自带法术
        self.lineage_frame = ttk.LabelFrame(f, text="血脉 / 传承 (决定种族自带法术)",
                                            padding=6)
        self.cb_lineage = ttk.Combobox(self.lineage_frame, state="readonly",
                                       width=26)
        self.cb_lineage.pack(anchor="w")
        self.cb_lineage.bind("<<ComboboxSelected>>",
                             lambda e: self._show_lineage())
        self.lbl_lineage = tk.Label(self.lineage_frame, text="", bg=BG, fg=DIM,
                                    wraplength=640, justify="left", anchor="nw",
                                    height=3)
        self.lbl_lineage.pack(anchor="w", pady=(4, 0))
        # 人类「全能」: 自选 1 个 Origin 专长
        self.human_frame = ttk.LabelFrame(f, text="人类 · 全能 (自选 1 个起源专长)",
                                          padding=6)
        self.cb_hfeat = ttk.Combobox(self.human_frame, state="readonly",
                                     width=30, values=sorted(FEAT_INFO))
        self.cb_hfeat.pack(anchor="w")
        self.cb_hfeat.bind("<<ComboboxSelected>>",
                           lambda e: self._show_hfeat_desc())
        if self.data.get("human_feat"):
            self.cb_hfeat.set(self.data["human_feat"])
        self.lbl_hfeat = tk.Label(self.human_frame, text="", wraplength=640,
                                  bg=BG, fg=DIM, justify="left", anchor="nw",
                                  height=3)
        self.lbl_hfeat.pack(anchor="w", pady=(4, 0))
        self._show_species()

    def _show_hfeat_desc(self):
        raw = self.cb_hfeat.get()
        self.data["human_feat"] = raw or None
        self.lbl_hfeat.config(text=feat_desc(raw) if raw else "")

    def _show_species(self):
        name = self.cb_sp.get()
        found = False
        for s in self.r.d["species"]:
            if s["name"] == name:
                found = True
                self.data["species_id"] = s["id"]
                size = size_cn(s["size"])
                text = (f"{s['name']}   体型: {size}   速度: {s['speed']} 尺\n"
                        f"{'-' * 40}\n" + "\n• ".join(["特性:"] + s["traits"]))
                self.txt_sp.config(state="normal")
                self.txt_sp.delete("1.0", "end")
                self.txt_sp.insert("1.0", text)
                self.txt_sp.config(state="disabled")
                # 人类才显示「全能」专长选择
                if s["id"] == "human":
                    self.human_frame.pack(fill="x", pady=6)
                    self._show_hfeat_desc()
                else:
                    self.human_frame.pack_forget()
                    self.data["human_feat"] = None
                # 血脉分支
                ent = SPECIES_SPELLS.get(s["id"])
                if isinstance(ent, dict):
                    if s["id"] == "human":       # 人类帧已 pack, 血脉排在它上面
                        self.lineage_frame.pack(fill="x", pady=6,
                                                before=self.human_frame)
                    else:
                        self.lineage_frame.pack(fill="x", pady=6)
                    keys = [k for k in ent]
                    labels = [LINEAGE_CN.get(k, k) for k in keys]
                    self._lineage_keys = keys
                    self.cb_lineage["values"] = labels
                    cur = self.data.get("lineage")
                    if cur in keys:
                        self.cb_lineage.set(LINEAGE_CN.get(cur, cur))
                    else:
                        self.cb_lineage.set(labels[0])
                        self.data["lineage"] = keys[0]
                    self._show_lineage()
                else:
                    self.lineage_frame.pack_forget()
                    self.data["lineage"] = None
                break
        if not found:
            self.human_frame.pack_forget()
            self.txt_sp.config(state="normal")
            self.txt_sp.delete("1.0", "end")
            self.txt_sp.insert("1.0",
                "\n\n  ⬆ 从上方下拉框选择一个种族，\n"
                "     这里会显示体型 / 速度 / 全部种族特性。")
            self.txt_sp.config(state="disabled")

    def _show_lineage(self):
        ent = SPECIES_SPELLS.get(self.data.get("species_id") or "")
        if not isinstance(ent, dict):
            return
        label = self.cb_lineage.get()
        key = next((k for k, v in LINEAGE_CN.items()
                    if v == label and k in ent), None)
        if not key:
            return
        self.data["lineage"] = key
        lines = []
        for unlock, sid in ent[key]:
            sp = self.r.spell(sid)
            if sp:
                tag = "戏法" if sp["level"] == 0 else f"{sp['level']} 环"
                lines.append(f"{unlock} 级：{sp['name']}（{tag}）")
        self.lbl_lineage.config(
            text="种族自带（始终备好，每项可免费施放 1 次/长休）：\n"
                 + "　".join(lines))

    def _validate_2(self):
        if not self.data["species_id"]:
            messagebox.showwarning("提示", "请选择一个种族", parent=self)
            return False
        if self.data["species_id"] == "human" and not self.data.get("human_feat"):
            messagebox.showwarning("提示", "人类「全能」需要自选 1 个起源专长",
                                   parent=self)
            return False
        ent = SPECIES_SPELLS.get(self.data["species_id"])
        if isinstance(ent, dict) and not self.data.get("lineage"):
            messagebox.showwarning("提示", "请选择一个血脉分支", parent=self)
            return False
        return True

    # ---- Step 3: 属性 ----

    def _step_abilities(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="④ 生成属性值 (背景加值稍后自动叠加)",
                  font=("", 13, "bold")).pack(anchor="w")

        self.ab_method = tk.StringVar(value=getattr(self, "_last_ab_method",
                                                    "standard"))
        if self.data["base_scores"]:
            self.ab_method.set(getattr(self, "_last_ab_method", "standard"))
        row = ttk.Frame(f)
        row.pack(fill="x", pady=4)
        for val, txt in [("standard", "标准数组"), ("pointbuy", "购点法(27点)"),
                         ("roll", "掷骰法(4d6取三)")]:
            ttk.Radiobutton(row, text=txt, value=val, variable=self.ab_method,
                            command=self._render_ab_ui).pack(side="left", padx=8)
        self.ab_frame = ttk.Frame(f)
        self.ab_frame.pack(fill="both", expand=True, pady=6)
        self._rolled = getattr(self, "_rolled", None)
        self._render_ab_ui()

        # ---- 2024 规则说明: 属性加值只来自背景 ----
        spf = ttk.LabelFrame(f, text="属性加值来源", padding=6)
        spf.pack(fill="x", pady=(4, 0))
        sp_id = self.data["species_id"]
        sp_name = self.r.sp(sp_id)["name"] if sp_id else "种族"
        ttk.Label(spf, text="※ 2024 规则（5.5e / 5R）：属性加值只来自背景（上方 +2/+1 或 +1/+1/+1），"
                           f"种族本身不给属性加值。{sp_name} 的特殊能力体现在速度、感官、"
                           "抗性、自带法术与技能熟练上，在建卡向导的种族页可查看。",
                  style="Dim.TLabel", wraplength=680,
                  justify="left").pack(anchor="w")
        self.ab_preview = ttk.Label(f, text="", font=("", 10, "bold"),
                                    foreground=GOLD2, wraplength=690,
                                    justify="left")
        self.ab_preview.pack(anchor="w", pady=(4, 0))
        self._ab_preview()

    def _current_picks(self):
        """读取属性页当前的分配结果 (未分配项为 None)"""
        out = {}
        method = self.ab_method.get()
        if method == "pointbuy":
            for ab, v in getattr(self, "pb_vars", {}).items():
                try:
                    out[ab] = v.get()
                except tk.TclError:
                    pass
        else:
            for ab, cb in getattr(self, "ab_picks", {}).items():
                val = cb.get()
                out[ab] = int(val) if val.isdigit() else None
        return out

    def _ab_preview(self):
        if not hasattr(self, "ab_preview"):
            return
        picks = self._current_picks()
        bg = self.data.get("bg_bonus") or {}
        parts, unset = [], []
        for ab in ABILITIES:
            base = picks.get(ab)
            if base is None:
                unset.append(ABILITY_CN[ab])
                continue
            v = base
            if bg.get("mode") == "2+1":
                v += 2 if bg.get("plus2") == ab else (1 if bg.get("plus1") == ab else 0)
            elif bg.get("mode") == "111":
                v += 1 if ab in bg.get("ones", []) else 0
            v = max(1, min(20, v))
            parts.append(f"{ABILITY_CN[ab]} {v}({mod_str(ability_mod(v))})")
        txt = "最终属性(基础 + 背景加值): " + "   ".join(parts)
        if unset:
            txt += f"   ｜ 未分配: {'、'.join(unset)}"
        self.ab_preview.config(text=txt)

    def _render_ab_ui(self):
        for w in self.ab_frame.winfo_children():
            w.destroy()
        method = self.ab_method.get()
        self._last_ab_method = method

        if method == "standard":
            ttk.Label(self.ab_frame, text="为数组 15 / 14 / 13 / 12 / 10 / 8 分配属性:",
                      foreground=DIM).pack(anchor="w")
            self.ab_picks = {}
            grid = ttk.Frame(self.ab_frame)
            grid.pack(anchor="w", pady=8)
            for i, ab in enumerate(ABILITIES):
                ttk.Label(grid, text=f"{ABILITY_CN[ab]} {ab}").grid(
                    row=i // 3, column=(i % 3) * 2, sticky="w", padx=6, pady=3)
                cb = ttk.Combobox(grid, state="readonly", width=4,
                                  values=[str(v) for v in STANDARD_ARRAY])
                cb.grid(row=i // 3, column=(i % 3) * 2 + 1, padx=6, pady=3)
                cb.bind("<<ComboboxSelected>>", lambda e: self._ab_preview())
                self.ab_picks[ab] = cb

        elif method == "pointbuy":
            self.pb_vars = {}
            self.pb_costlbl = {}
            ttk.Label(self.ab_frame, text="27 购点，各项 8–15（费用 9→1 … 15→9）:",
                      foreground=DIM).pack(anchor="w")
            grid = ttk.Frame(self.ab_frame)
            grid.pack(anchor="w", pady=8)
            for i, ab in enumerate(ABILITIES):
                v = tk.IntVar(value=self.data["base_scores"].get(ab, 8))
                v.trace_add("write", lambda *a: self._pb_update())
                self.pb_vars[ab] = v
                ttk.Label(grid, text=f"{ABILITY_CN[ab]}").grid(
                    row=i // 3, column=(i % 3) * 3, sticky="w", padx=4, pady=3)
                sp = ttk.Spinbox(grid, from_=8, to=15, textvariable=v, width=4,
                                 command=self._pb_update)
                sp.grid(row=i // 3, column=(i % 3) * 3 + 1, padx=4)
                self.pb_costlbl[ab] = ttk.Label(grid, text="(0)")
                self.pb_costlbl[ab].grid(row=i // 3, column=(i % 3) * 3 + 2, padx=4)
            self.pb_left = ttk.Label(self.ab_frame, text="", font=("", 11, "bold"))
            self.pb_left.pack(anchor="w", pady=4)
            self._pb_update()

        else:  # roll
            bar = ttk.Frame(self.ab_frame)
            bar.pack(anchor="w", pady=4)
            ttk.Button(bar, text="🎲 掷 6 组 4d6(取高三)",
                       command=self._do_roll).pack(side="left")
            self.roll_result = ttk.Label(self.ab_frame, text="先掷骰，再分配",
                                         foreground=DIM)
            self.roll_result.pack(anchor="w", pady=4)
            self.ab_picks = {}
            grid = ttk.Frame(self.ab_frame)
            grid.pack(anchor="w", pady=4)
            for i, ab in enumerate(ABILITIES):
                ttk.Label(grid, text=f"{ABILITY_CN[ab]}").grid(
                    row=i // 3, column=(i % 3) * 2, sticky="w", padx=6, pady=3)
                cb = ttk.Combobox(grid, state="readonly", width=4)
                cb.grid(row=i // 3, column=(i % 3) * 2 + 1, padx=6, pady=3)
                cb.bind("<<ComboboxSelected>>", lambda e: self._ab_preview())
                self.ab_picks[ab] = cb
            if self._rolled:
                self._show_rolled()

    def _pb_update(self):
        total = 0
        for ab, v in self.pb_vars.items():
            try:
                val = v.get()
            except tk.TclError:
                continue
            total += POINT_COST.get(val, 99)
            self.pb_costlbl[ab].config(text=f"({POINT_COST.get(val, '?')})")
        left = 27 - total
        color = "#1a7f37" if left >= 0 else "#e05c4d"
        self.pb_left.config(text=f"剩余点数: {left} / 27", foreground=color)
        self._ab_preview()

    def _do_roll(self):
        self._rolled = sorted((roll_4d6kh3() for _ in range(6)), reverse=True)
        self._show_rolled()

    def _show_rolled(self):
        vals = [str(v) for v in self._rolled]
        self.roll_result.config(text="掷得: " + " / ".join(vals) + "（自行分配）")
        for cb in self.ab_picks.values():
            cb.config(values=vals)

    def _validate_3(self):
        method = self.ab_method.get()
        scores = {}
        if method == "standard" or method == "roll":
            vals = []
            for ab, cb in self.ab_picks.items():
                if not cb.get():
                    messagebox.showwarning("提示", "请完成所有属性分配", parent=self)
                    return False
                vals.append(int(cb.get()))
                scores[ab] = int(cb.get())
            if method == "standard" and sorted(vals, reverse=True) != STANDARD_ARRAY:
                messagebox.showwarning("提示", "标准数组必须恰好用完 15/14/13/12/10/8",
                                       parent=self)
                return False
            if method == "roll" and sorted(vals, reverse=True) != self._rolled:
                messagebox.showwarning("提示", "只能使用掷出的六个数值", parent=self)
                return False
        else:
            total = 0
            for ab, v in self.pb_vars.items():
                try:
                    val = v.get()
                except tk.TclError:
                    messagebox.showwarning("提示", "属性值无效", parent=self)
                    return False
                if not 8 <= val <= 15:
                    messagebox.showwarning("提示", "购点属性必须在 8–15 之间", parent=self)
                    return False
                total += POINT_COST[val]
                scores[ab] = val
            if total > 27:
                messagebox.showwarning("提示", f"超预算: 已用 {total} 点 (上限 27)",
                                       parent=self)
                return False
        self.data["base_scores"] = scores
        # 基础值 + 背景加值 不得超 20 (2024: 种族不加属性)
        for ab in ABILITIES:
            v = scores[ab]
            bgv = self.data.get("bg_bonus") or {}
            if bgv.get("mode") == "2+1":
                v += 2 if bgv.get("plus2") == ab else (1 if bgv.get("plus1") == ab else 0)
            elif bgv.get("mode") == "111":
                v += 1 if ab in bgv.get("ones", []) else 0
            if v > 20:
                messagebox.showwarning(
                    "提示", f"{ABILITY_CN[ab]} 最终值 {v} 超过 20 上限，请调低基础值",
                    parent=self)
                return False
        return True

    # ---- Step 4: 技能 ----

    def _step_skills(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        cls = self.r.cls(self.data["class_id"])
        bg = self.r.bg(self.data["background_id"])
        self._bg_skills = set(bg["skills"])
        ttk.Label(f, text="⑤ 选择技能熟练", font=("", 13, "bold")).pack(anchor="w")

        auto = [self.r.skill_by_id[s]["name"] for s in bg["skills"]]
        ttk.Label(f, text=f"① 背景自动获得 {len(auto)} 项: {'、'.join(auto)}",
                  foreground="#58b368").pack(anchor="w", pady=2)

        need = cls["skill_count"]
        pool_ids = ([s["id"] for s in self.r.d["skills"]]
                    if cls["skill_options"] == "*any*" else cls["skill_options"])
        head = ttk.Frame(f)
        head.pack(anchor="w", fill="x")
        ttk.Label(head, text=f"② 职业任选 {need} 项 (多选, 达上限自动拦截):",
                  foreground=DIM).pack(side="left")
        self._skill_count_lbl = ttk.Label(head, text="", font=("", 10, "bold"))
        self._skill_count_lbl.pack(side="left", padx=10)

        self.skill_vars = {}
        grid = ttk.Frame(f)
        grid.pack(anchor="w", pady=4)
        pool_ids = [sid for sid in pool_ids if sid not in bg["skills"]]
        for i, sid in enumerate(pool_ids):
            sk = self.r.skill_by_id[sid]
            v = tk.BooleanVar(value=sid in self.data["skill_prof"])
            self.skill_vars[sid] = v
            cb = ttk.Checkbutton(grid, text=f"{sk['name']} ({ABILITY_CN[sk['ability']]})",
                                 variable=v,
                                 command=lambda s2=sid: self._on_class_skill(s2))
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=10, pady=2)
            cb.bind("<Enter>", lambda e, s2=sid: self._hint_skill(s2))

        # ---- 种族赠送技能 (额外 +1, 与职业技能独立) ----
        self.sp_skill_vars = {}
        spf = ttk.Frame(f)
        spf.pack(anchor="w", pady=(6, 0))
        sp_id = self.data["species_id"]
        sp_name = self.r.sp(sp_id)["name"]
        n_sp = SPECIES_SKILL_BONUS.get(sp_id, 0)
        self._sp_need = n_sp
        self._sp_note = ""
        if n_sp:
            flavor = {"human": "「多才多艺」", "elf": "「敏锐感官」"}.get(sp_id, "")
            scope = ("任意技能" if sp_id == "human" else "洞察/察觉/生存")
            self._sp_note = (f"③ {sp_name} {flavor}: 在职业技能之外, "
                             f"额外获得 {n_sp} 项熟练（{scope}, "
                             f"{'可多选' if n_sp > 1 else '单选'}, 不与已有熟练重复）")
        if self._sp_note:
            ttk.Label(spf, text=self._sp_note, foreground=PURPLE).pack(anchor="w")
            opts = ([s["id"] for s in self.r.d["skills"]]
                    if sp_id == "human"
                    else ["insight", "perception", "survival"])
            opts = [s for s in opts if s not in self._bg_skills]
            spg = ttk.Frame(spf)          # 独立内层框, 避免 pack/grid 混用
            spg.pack(anchor="w")
            cols = 4                      # 人类 18 项按 4 列排, 避免横向溢出窗口
            for i, sid in enumerate(opts):
                sk = self.r.skill_by_id[sid]
                v = tk.BooleanVar(value=False)
                self.sp_skill_vars[sid] = v
                cbs = ttk.Checkbutton(spg, text=sk["name"], variable=v,
                                      command=lambda s2=sid: self._on_sp_skill(s2))
                cbs.grid(row=i // cols, column=i % cols, sticky="w",
                         padx=(0, 10), pady=1)
                cbs.bind("<Enter>", lambda e, s2=sid: self._hint_skill(s2))

        self._skill_need = need
        self._skill_summary = ttk.Label(f, text="", font=("", 10, "bold"))
        self._skill_summary.pack(anchor="w", pady=(6, 0))
        self._skill_hint = tk.Label(f, text="把鼠标停在技能上可看它管什么检定",
                                    bg=BG, fg=DIM, wraplength=680,
                                    justify="left", anchor="nw", height=2)
        self._skill_hint.pack(anchor="w", pady=(4, 0))
        self._update_skill_count()

    def _hint_skill(self, sid):
        sk = self.r.skill_by_id[sid]
        self._skill_hint.config(
            text=f"{sk['name']} ({ABILITY_CN[sk['ability']]}) —— "
                 f"{SKILL_DESC.get(sid, '')}",
            foreground=GOLD2)

    def _update_skill_count(self):
        n = sum(1 for v in self.skill_vars.values() if v.get())
        ok = (n == self._skill_need)
        self._skill_count_lbl.config(
            text=f"已选 {n} / {self._skill_need}",
            foreground="#58b368" if ok else GOLD2)
        # 熟练汇总: 背景 + 职业 + 种族
        sp_n = sum(1 for v in self.sp_skill_vars.values() if v.get())
        bg_n = len(self._bg_skills)
        need_sp = getattr(self, "_sp_need", 0)
        extra = (f" · 种族 {sp_n}/{need_sp}" if self.sp_skill_vars else "")
        total = bg_n + n + sp_n
        self._skill_summary.config(
            text=f"熟练总数: 背景 {bg_n} + 职业 {n}/{self._skill_need}{extra}"
                 f" = {total} 项",
            foreground="#58b368" if ok else TEXT)

    def _on_class_skill(self, sid):
        """职业技能多选实时控制: 超出上限自动回退本次勾选"""
        v = self.skill_vars[sid]
        if v.get():
            # 种族已选的同一技能 → 自动让位给职业技能
            if sid in self.sp_skill_vars and self.sp_skill_vars[sid].get():
                self.sp_skill_vars[sid].set(False)
            n = sum(1 for x in self.skill_vars.values() if x.get())
            if n > self._skill_need:
                v.set(False)
                self._skill_count_lbl.config(
                    text=f"已达上限 {self._skill_need} 项 —— 请先取消一项再选",
                    foreground="#e05c4d")
                return
        self._update_skill_count()

    def _on_sp_skill(self, sid):
        """种族赠送技能: 最多选 _sp_need 项; 与职业已选重复则立即回退"""
        v = self.sp_skill_vars[sid]
        if v.get():
            if sid in self.skill_vars and self.skill_vars[sid].get():
                v.set(False)
                self._skill_hint.config(
                    text=f"{self.r.skill_by_id[sid]['name']} 已由「职业技能」获得, "
                         f"不能重复吃熟练 —— 请换一项", foreground="#e05c4d")
                self._update_skill_count()
                return
            n = sum(1 for x in self.sp_skill_vars.values() if x.get())
            need_sp = getattr(self, "_sp_need", 1)
            if n > need_sp:
                v.set(False)
                self._skill_hint.config(
                    text=f"种族技能最多 {need_sp} 项 —— 请先取消一项",
                    foreground="#e05c4d")
        self._update_skill_count()

    def _validate_4(self):
        chosen = [sid for sid, v in self.skill_vars.items() if v.get()]
        if len(chosen) != self._skill_need:
            messagebox.showwarning(
                "提示", f"职业技能须恰好选择 {self._skill_need} 项 (已选 {len(chosen)})",
                parent=self)
            return False
        sp = [sid for sid, v in self.sp_skill_vars.items() if v.get()]
        need_sp = getattr(self, "_sp_need", 1)
        if need_sp and len(sp) != need_sp:
            messagebox.showwarning(
                "提示", f"种族额外技能须恰好选 {need_sp} 项 (已选 {len(sp)})",
                parent=self)
            return False
        # 去重: 职业 / 种族 / 背景 三者不可重复
        dup = (set(chosen) & set(sp)) | (set(chosen) & self._bg_skills) \
            | (set(sp) & self._bg_skills)
        if dup:
            names = "、".join(self.r.skill_by_id[s]["name"] for s in dup)
            messagebox.showwarning(
                "提示", f"技能熟练不可重复: {names}\n请换一项", parent=self)
            return False
        prof = set(chosen) | set(sp) | self._bg_skills
        self.data["skill_prof"] = prof
        return True

    # ---- Step 5: 武器专精 ----

    def _step_mastery(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        cls = self.r.cls(self.data["class_id"])
        n = cls["weapon_mastery_count"]
        if n == 0:
            self.data["weapon_mastery"] = []     # 换到无专精职业: 清掉旧选择
            ttk.Label(f, text="⑤/⑥ 武器专精", font=("", 13, "bold")).pack(anchor="w")
            ttk.Label(f, text=f"{cls['name']} 没有武器专精特性，直接下一步。\n"
                              f"(4级起可用 Weapon Master 专长补足)",
                      foreground=DIM).pack(anchor="w", pady=10)
            return
        ttk.Label(f, text=f"⑤/⑥ 选择武器专精 (须恰好 {n} 件, 长休可换)",
                  font=("", 13, "bold")).pack(anchor="w")
        pool = Rules.class_mastery_pool(cls)
        head = ttk.Frame(f)
        head.pack(anchor="w", fill="x")
        ttk.Label(head, text=f"可选范围: {cls['name']} 的武器熟练 "
                             f"({', '.join(WEAPON_PROF_CN.get(w, w) for w in cls['weapons'])})",
                  foreground=DIM).pack(side="left")
        self._mastery_count_lbl = ttk.Label(head, text="", font=("", 10, "bold"))
        self._mastery_count_lbl.pack(side="left", padx=10)
        self.mastery_vars = {}
        grid = ttk.Frame(f)
        grid.pack(anchor="w", pady=6)
        for i, (wname, cat, dmg, mst) in enumerate(pool):
            v = tk.BooleanVar(value=wname in self.data["weapon_mastery"])
            self.mastery_vars[wname] = v
            ttk.Checkbutton(grid, text=f"{wname} · {dmg} · {mastery_cn(mst)}",
                            variable=v,
                            command=lambda w2=wname: self._on_mastery(w2)
                            ).grid(row=i // 2, column=i % 2,
                                   sticky="w", padx=8, pady=2)
        self._mastery_need = n
        self._update_mastery_count()
        ttk.Label(f, text="专精效果:", foreground=DIM).pack(anchor="w")
        txt = tk.Text(f, height=6, wrap="word", state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        txt.pack(fill="both", expand=True)
        masts = {m for (_, _, _, m) in pool}
        txt.config(state="normal")
        txt.insert("1.0", "\n".join(MASTERY_DESC[m] for m in sorted(masts)))
        txt.config(state="disabled")

    def _update_mastery_count(self):
        n = sum(1 for v in self.mastery_vars.values() if v.get())
        ok = (n == self._mastery_need)
        self._mastery_count_lbl.config(
            text=f"已选 {n} / {self._mastery_need}",
            foreground="#58b368" if ok else GOLD2)

    def _on_mastery(self, wname):
        """武器专精多选实时控制: 超出上限自动回退本次勾选"""
        v = self.mastery_vars[wname]
        if v.get():
            n = sum(1 for x in self.mastery_vars.values() if x.get())
            if n > self._mastery_need:
                v.set(False)
                self._mastery_count_lbl.config(
                    text=f"已达上限 {self._mastery_need} 件 —— 请先取消一件再选",
                    foreground="#e05c4d")
                return
        self._update_mastery_count()

    def _validate_5(self):
        cls = self.r.cls(self.data["class_id"])
        if cls["weapon_mastery_count"] == 0:
            self.data["weapon_mastery"] = []
            return True
        chosen = [w for w, v in self.mastery_vars.items() if v.get()]
        if len(chosen) != self._mastery_need:
            messagebox.showwarning(
                "提示", f"须恰好选择 {self._mastery_need} 件武器 (已选 {len(chosen)})",
                parent=self)
            return False
        self.data["weapon_mastery"] = chosen
        return True

    # ---- Step 6: 法术 ----

    def _spell_detail_text(self, s):
        return spell_detail(s)

    def _step_spells(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        cid = self.data["class_id"]
        cls = self.r.cls(cid)
        cast = cls.get("casting") or {}
        n_can, n_l1 = SPELL_COUNTS.get(cid, (0, 0))
        ttk.Label(f, text="⑥ 选择法术", font=("", 13, "bold")).pack(anchor="w")
        ttk.Label(f, text=f"{cls['name']} · 施法属性 {ABILITY_CN.get(cast.get('ability'), '-')}"
                          f" · 戏法 {n_can} 个 · 1 环法术 {n_l1} 个"
                          f"（法术库共 {len(self.r.spells)} 条，建卡后可继续在本页外增删）",
                  foreground=DIM).pack(anchor="w", pady=(2, 6))

        if "spells" not in self.data:
            self.data["spells"] = {"cantrips": [], "prepared": []}
        self._sp_buckets = {}
        self._sp_labels = {}
        self._sp_lists = {}
        self._sp_combos = {}

        def make_bucket(key, title, need, level):
            lf = ttk.LabelFrame(f, text=f"{title}（{need} 个）", padding=6)
            lf.pack(fill="x", pady=3)
            head = ttk.Frame(lf)
            head.pack(fill="x")
            lbl = ttk.Label(head, text="", font=("", 10, "bold"))
            lbl.pack(side="left")
            cb = ttk.Combobox(head, state="readonly", width=30)
            cb.pack(side="right", padx=4)
            btns = ttk.Frame(head)
            btns.pack(side="right")
            lb = tk.Listbox(lf, height=4, **LISTBOX_STYLE)
            lb.pack(fill="x", pady=3)

            def avail():
                chosen = self._sp_buckets[key]
                return [s for s in self.r.class_spells(cid, level)
                        if s["id"] not in chosen]

            def refresh():
                cb["values"] = [f"{s['name']} {s['name_en']}" for s in avail()]
                lb.delete(0, "end")
                for sid in self._sp_buckets[key]:
                    s = self.r.spell(sid)
                    lb.insert("end", f"{s['name']} · {s['level']}环 · {s['cast']}")
                n = len(self._sp_buckets[key])
                lbl.config(text=f"已选 {n} / {need}",
                           foreground="#58b368" if n == need else GOLD2)

            def add(*_):
                idx = cb.current()
                if idx < 0:
                    return
                s = avail()[idx]
                if len(self._sp_buckets[key]) >= need:
                    lbl.config(text=f"已达上限 {need} 个 —— 请先移除",
                               foreground="#e05c4d")
                    return
                self._sp_buckets[key].append(s["id"])
                refresh()
                self._sp_detail_set(self._spell_detail_text(s))

            def rm(*_):
                sel = lb.curselection()
                if not sel:
                    return
                sid = self._sp_buckets[key].pop(sel[0])
                refresh()
                self._sp_detail_set(self._spell_detail_text(self.r.spell(sid)))

            def show(*_):
                sel = lb.curselection()
                if sel:
                    sid = self._sp_buckets[key][sel[0]]
                    self._sp_detail_set(
                        self._spell_detail_text(self.r.spell(sid)))

            ttk.Button(btns, text="＋ 添加", style="Mini.TButton",
                       command=add).pack(side="left", padx=2)
            ttk.Button(btns, text="－ 移除", style="Mini.TButton",
                       command=rm).pack(side="left")
            lb.bind("<<ListboxSelect>>", show)
            self._sp_buckets[key] = list(
                self.data["spells"].get("cantrips" if key == "cantrip" else "prepared", []))
            self._sp_labels[key] = lbl
            self._sp_lists[key] = lb
            self._sp_combos[key] = cb
            refresh()

        # 戏法 (0 环)
        if n_can:
            make_bucket("cantrip", "戏法 Cantrip（无限次施放）", n_can, 0)
        # 1 环
        if n_l1:
            make_bucket("lvl1", "1 环法术", n_l1, 1)

        ttk.Label(f, text="法术详情", style="H2.TLabel").pack(anchor="w",
                                                              pady=(6, 0))
        self._sp_detail = tk.Text(f, height=6, wrap="word", state="disabled",
                                  background=TXT_BG, foreground=TEXT,
                                  insertbackground=TEXT, relief="flat", width=1)
        self._sp_detail.pack(fill="both", expand=True, pady=3)

    def _sp_detail_set(self, text):
        self._sp_detail.config(state="normal")
        self._sp_detail.delete("1.0", "end")
        self._sp_detail.insert("1.0", text)
        self._sp_detail.config(state="disabled")

    def _validate_6(self):
        spells = {"cantrips": [], "prepared": []}
        for key, store in (("cantrip", "cantrips"), ("lvl1", "prepared")):
            if key in self._sp_buckets:
                spells[store] = list(self._sp_buckets[key])
        n_can, n_l1 = SPELL_COUNTS.get(self.data["class_id"], (0, 0))
        if n_can and len(spells["cantrips"]) != n_can:
            messagebox.showwarning(
                "提示", f"戏法须恰好选择 {n_can} 个", parent=self)
            return False
        if n_l1 and len(spells["prepared"]) != n_l1:
            messagebox.showwarning(
                "提示", f"1 环法术须恰好选择 {n_l1} 个", parent=self)
            return False
        self.data["spells"] = spells
        return True

    # ---- Step 7: 摘要 ----

    def _step_summary(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="摘要确认", font=("", 13, "bold")).pack(anchor="w")
        txt = tk.Text(f, height=22, wrap="word", state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        txt.pack(fill="both", expand=True, pady=6)

        cls = self.r.cls(self.data["class_id"])
        bg = self.r.bg(self.data["background_id"])
        sp = self.r.sp(self.data["species_id"])
        tmp = Character.__new__(Character)
        tmp.__dict__.update({
            "r": self.r, "level": 1, "class_id": self.data["class_id"],
            "background_id": self.data["background_id"],
            "species_id": self.data["species_id"],
            "base_scores": self.data["base_scores"],
            "bg_bonus": self.data["bg_bonus"],
            "asi_history": [], "skill_prof": self.data["skill_prof"],
            "expertise": set(), "armor_index": 0, "shield": False,
            "tough_feat": False,
            "items": [], "feats": [], "weapon_magic": 0, "fighting_style": None,
            "weapon": "", "shield_magic": 0,
        })
        scores = tmp.scores()
        mods = tmp.mods()
        skills = "、".join(
            self.r.skill_by_id[s]["name"]
            for s in sorted(self.data["skill_prof"],
                            key=lambda x: self.r.skill_by_id[x]["name"]))
        sp_note = "（背景加值, 种族不加属性）"
        spells = self.data.get("spells") or {}
        spell_lines = []
        if spells.get("cantrips"):
            spell_lines.append("戏法: " + "、".join(
                self.r.spell(s)["name"] for s in spells["cantrips"] if self.r.spell(s)))
        if spells.get("prepared"):
            spell_lines.append("1 环: " + "、".join(
                self.r.spell(s)["name"] for s in spells["prepared"] if self.r.spell(s)))
        lines = [
            f"姓名: {self.data['name']}    等级: 1",
            f"职业: {cls['name']}    子职: (3级解锁)",
            f"背景: {bg['name']} [专长 {feat_cn(bg['origin_feat'])}]    "
            f"种族: {sp['name']}",
            "",
            f"属性{sp_note}: " + "   ".join(
                f"{ABILITY_CN[a]} {scores[a]}({mod_str(mods[a])})"
                for a in ABILITIES),
            f"生命值: {tmp.hp_max()}    AC: {tmp.ac()}    "
            f"先攻: {mod_str(tmp.initiative())}",
            f"熟练加值: +2    被动察觉: {tmp.passive_perception()}",
            f"豁免熟练: {'、'.join(ABILITY_CN[a] for a in cls['saves'])}",
            f"技能熟练 ({len(self.data['skill_prof'])} 项): {skills}",
            f"工具熟练: {tool_cn(bg['tool'])}",
            f"武器专精: {', '.join(self.data['weapon_mastery']) or '— (该职业无)'}",
            f"种族额外专长: {feat_cn(self.data['human_feat'])}"
            if self.data.get("human_feat") else "",
            ("法术 —— " + " ｜ ".join(spell_lines)) if spell_lines else "",
            "",
            "说明: 装备、魔法物品与加成明细请在角色卡「装备·武器」页设置;",
            "      法术可在角色卡「法 术」页随时增删与施放。",
        ]
        txt.config(state="normal")
        txt.insert("1.0", "\n".join(lines))
        txt.config(state="disabled")

    def finish(self):
        char = Character(self.r)
        char.name = self.data["name"]
        char.class_id = self.data["class_id"]
        char.background_id = self.data["background_id"]
        char.species_id = self.data["species_id"]
        char.base_scores = self.data["base_scores"]
        char.bg_bonus = self.data["bg_bonus"]
        char.skill_prof = set(self.data["skill_prof"])
        char.weapon_mastery = list(self.data["weapon_mastery"])
        char.spells = dict(self.data.get("spells") or
                           {"cantrips": [], "prepared": []})
        char.lineage = self.data.get("lineage")
        char.skill_prof |= set(char.auto_skills())
        # 默认装备: 该职业熟练的第一件武器
        cls = self.r.cls(char.class_id)
        pool = Rules.class_mastery_pool(cls) or WEAPONS
        char.weapon = pool[0][0]
        char.fighting_style = None      # 由角色卡「装备」页选择
        if self.data.get("human_feat"):
            char.feats.append(self.data["human_feat"])
        char.hp_current = char.hp_max()
        self.destroy()
        self.on_finish(char)


# ----------------------------------------------------------------------------
# 升级对话框
# ----------------------------------------------------------------------------

class LevelUpDialog(tk.Toplevel):

    def __init__(self, master, char):
        super().__init__(master)
        if not master.winfo_viewable():   # 后台测试: 父窗口不可见时不弹出
            self.withdraw()
        self.char = char
        self.result = None
        self.title(f"升级: {char.level} → {char.level + 1} 级")
        self.geometry("640x640" if char.level + 1 == 3 else "560x560")
        self.transient(master)
        self.configure(bg=BG)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        new_lv = char.level + 1
        # 确认按钮先 pack 到底部, 内容再多也不会被挤出窗口
        ttk.Button(self, text="确认升级", style="Gold.TButton",
                   command=self._ok).pack(side="bottom", pady=8)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        info = [f"{char.name} · {char.cls()['name']}  {char.level} → {new_lv} 级",
                f"熟练加值: {mod_str(char.pb())} → {mod_str(proficiency_bonus(new_lv))}",
                f"生命值上限: {char.hp_max()} → "
                f"{char.hp_max() + char.cls()['hit_die'] // 2 + 1 + ability_mod(char.score('CON'))}"
                f" (自动取固定值)"]
        if new_lv == 3:
            info.append("★ 3 级: 解锁子职!")
        if new_lv in (4, 8, 12, 16):
            info.append("★ 属性加值/专长 (ASI)!")
        if new_lv == 19:
            info.append("★ 19 级: 传奇恩惠 Epic Boon!")
        if new_lv == 20:
            info.append("★ 20 级: 职业压轴特性 (见PHB职业表)")
        ttk.Label(f, text="\n".join(info), justify="left").pack(anchor="w")

        # 子职选择 (含每个方向的介绍与 3 级起的效果)
        self.subclass_cb = None
        self._sub_map = {}
        if new_lv == 3:
            lf = ttk.LabelFrame(f, text="选择子职（点选查看介绍与效果）", padding=6)
            lf.pack(fill="both", expand=True, pady=6)
            self._sub_map = {subclass_cn(s): s
                             for s in char.cls()["subclasses"]}
            self.subclass_cb = ttk.Combobox(
                lf, state="readonly", width=40,
                values=list(self._sub_map))
            self.subclass_cb.pack(anchor="w", fill="x")
            self.subclass_cb.bind("<<ComboboxSelected>>",
                                  lambda e: self._sub_preview())
            self._sub_text = tk.Text(lf, height=9, wrap="word", width=1,
                                     **TEXT_STYLE)
            self._sub_text.pack(fill="both", expand=True, pady=(4, 0))
            self.subclass_cb.set(list(self._sub_map)[0])
            self._sub_preview()

        # ASI 选择
        self.asi_frame = None
        if new_lv in (4, 8, 12, 16):
            self.asi_frame = ttk.LabelFrame(f, text="属性加值 或 专长", padding=6)
            self.asi_frame.pack(fill="both", expand=True, pady=6)
            self.asi_mode = tk.StringVar(value="asi")
            ttk.Radiobutton(self.asi_frame, text="属性加值 (上限20)",
                            variable=self.asi_mode, value="asi",
                            command=self._render_asi).pack(anchor="w")
            ttk.Radiobutton(self.asi_frame, text="改为选择专长",
                            variable=self.asi_mode, value="feat",
                            command=self._render_asi).pack(anchor="w")
            self.asi_body = ttk.Frame(self.asi_frame)
            self.asi_body.pack(anchor="w", fill="x", pady=4)
            self._render_asi()

        # 传奇恩惠
        self.boan_entry = None
        if new_lv == 19:
            bf = ttk.LabelFrame(f, text="传奇恩惠 Epic Boon (输入名称)", padding=6)
            bf.pack(fill="x", pady=6)
            self.boan_entry = ttk.Entry(bf, width=34)
            self.boan_entry.pack(anchor="w")

    def _sub_preview(self):
        """升级弹窗里显示子职定位 + 各级效果"""
        name = self._sub_map.get(self.subclass_cb.get()) if self._sub_map else None
        info = self.char.r.sub_info(name) if name else None
        if not info:
            return
        lines = [f"【{subclass_cn(name)}】", info["summary"], ""]
        for f in info["features"]:
            lines.append(f"Lv{f['level']} · {f['name']}")
            lines.append(f"    {f['desc']}")
        self._sub_text.config(state="normal")
        self._sub_text.delete("1.0", "end")
        self._sub_text.insert("1.0", "\n".join(lines))
        self._sub_text.config(state="disabled")

    def _render_asi(self):
        for w in self.asi_body.winfo_children():
            w.destroy()
        if self.asi_mode.get() == "feat":
            row = ttk.Frame(self.asi_body)
            row.pack(anchor="w")
            ttk.Label(row, text="专长:").pack(side="left")
            self._feat_map = {f"{v[0]} {k}": k
                              for k, v in FEAT_INFO.items()}
            self.feat_cb = ttk.Combobox(row, width=30,
                                        values=list(self._feat_map))
            self.feat_cb.pack(side="left", padx=4)
            self.feat_cb.bind("<<ComboboxSelected>>",
                              lambda e: self._feat_hint())
            self.feat_cb.bind("<KeyRelease>", lambda e: self._feat_hint())
            self.feat_desc = ttk.Label(self.asi_body, wraplength=500,
                                       justify="left", foreground=DIM)
            self.feat_desc.pack(anchor="w", pady=(4, 0))
            self._feat_hint()
            return
        self.asi_submode = tk.StringVar(value="2+1")
        ttk.Radiobutton(self.asi_body, text="+2/+1", variable=self.asi_submode,
                        value="2+1", command=self._render_asi_picks).pack(side="left")
        ttk.Radiobutton(self.asi_body, text="+1/+1/+1", variable=self.asi_submode,
                        value="111", command=self._render_asi_picks).pack(side="left",
                                                                          padx=8)
        self.asi_picks = ttk.Frame(self.asi_body)
        self.asi_picks.pack(anchor="w", pady=4)
        self._render_asi_picks()

    def _feat_hint(self):
        disp = self.feat_cb.get().strip()
        raw = self._feat_map.get(disp, disp)
        info = FEAT_INFO.get(raw)
        self.feat_desc.config(
            text=(f"{info[0]} {raw}: {info[1]}" if info
                  else "自定义专长: 请在角色卡「笔记」页记录其效果"))

    def _render_asi_picks(self):
        for w in self.asi_picks.winfo_children():
            w.destroy()
        names = [f"{ABILITY_CN[a]}({a})" for a in ABILITIES]
        if self.asi_submode.get() == "2+1":
            ttk.Label(self.asi_picks, text="+2 →").pack(side="left")
            self.asi_p2 = ttk.Combobox(self.asi_picks, state="readonly",
                                       width=13, values=names)
            self.asi_p2.pack(side="left", padx=4)
            self.asi_p2.bind("<<ComboboxSelected>>",
                             lambda e: self._asi_dedup("p2"))
            ttk.Label(self.asi_picks, text="+1 →").pack(side="left",
                                                        padx=(10, 0))
            self.asi_p1 = ttk.Combobox(self.asi_picks, state="readonly",
                                       width=13, values=names)
            self.asi_p1.pack(side="left", padx=4)
            self.asi_p1.bind("<<ComboboxSelected>>",
                             lambda e: self._asi_dedup("p1"))
        else:
            self.asi_o = []
            for i in range(3):
                ttk.Label(self.asi_picks, text="+1 →").pack(
                    side="left", padx=(0 if i == 0 else 10, 0))
                cb = ttk.Combobox(self.asi_picks, state="readonly", width=13,
                                  values=names)
                cb.pack(side="left", padx=4)
                cb.bind("<<ComboboxSelected>>",
                        lambda e, box=cb: self._asi_dedup(box))
                self.asi_o.append(cb)

    def _asi_dedup(self, source):
        """同一加值不可重复选同一属性: 实时清掉冲突的另一项"""
        if self.asi_submode.get() == "2+1":
            if self.asi_p2.get() and self.asi_p1.get() \
                    and self.asi_p2.get() == self.asi_p1.get():
                (self.asi_p1 if source == "p2" else self.asi_p2).set("")
        else:
            cur = source.get()
            if cur:
                for cb in self.asi_o:
                    if cb is not source and cb.get() == cur:
                        cb.set("")

    def _ok(self):
        new_lv = self.char.level + 1
        rec = {"level": new_lv, "subclass": None, "asi": None, "boon": None}

        if new_lv == 3 and self.subclass_cb is not None:
            if not self.subclass_cb.get():
                messagebox.showwarning("提示", "请选择子职", parent=self)
                return
            rec["subclass"] = self._sub_map.get(self.subclass_cb.get(),
                                                self.subclass_cb.get())

        if new_lv in (4, 8, 12, 16):
            if self.asi_mode.get() == "feat":
                disp = self.feat_cb.get().strip()
                if not disp:
                    messagebox.showwarning("提示", "请选择或输入专长名称",
                                           parent=self)
                    return
                name = self._feat_map.get(disp, disp)
                rec["asi"] = {"type": "feat", "name": name}
                if name == "Tough" or "tough" in name.lower() \
                        or "坚忍" in disp or "坚韧" in disp:
                    self.char.tough_feat = True
            else:
                ch = self.char
                if self.asi_submode.get() == "2+1":
                    a, b = self.asi_p2.get(), self.asi_p1.get()
                    if not a or not b or a == b:
                        messagebox.showwarning("提示", "+2/+1 须选两项不同属性",
                                               parent=self)
                        return
                    ab2, ab1 = ab_from_display(a), ab_from_display(b)
                    if ch.score(ab2) + 2 > 20 or ch.score(ab1) + 1 > 20:
                        messagebox.showwarning("提示", "属性不可超过 20", parent=self)
                        return
                    rec["asi"] = {"type": "asi", "plus2": ab2, "plus1": ab1}
                else:
                    vals = [cb.get() for cb in self.asi_o]
                    if any(not v for v in vals) or len(set(vals)) != 3:
                        messagebox.showwarning("提示", "+1/+1/+1 须选三项不同属性",
                                               parent=self)
                        return
                    abs_ = [ab_from_display(v) for v in vals]
                    if any(ch.score(a) + 1 > 20 for a in abs_):
                        messagebox.showwarning("提示", "属性不可超过 20", parent=self)
                        return
                    rec["asi"] = {"type": "asi", "ones": abs_}

        if new_lv == 19:
            rec["boon"] = self.boan_entry.get().strip() or "传奇恩惠(未命名)"
            rec["asi"] = {"type": "feat", "name": rec["boon"]}

        self.result = rec
        self.destroy()


def ab_from_display(display_name):
    for ab in ABILITIES:
        if display_name == f"{ABILITY_CN[ab]}({ab})":
            return ab
    return ABILITIES[0]


# ----------------------------------------------------------------------------
# 骰子工具
# ----------------------------------------------------------------------------

class DiceDialog(tk.Toplevel):

    def __init__(self, master):
        super().__init__(master)
        if not master.winfo_viewable():   # 后台测试: 父窗口不可见时不弹出
            self.withdraw()
        self.title("骰子工具")
        self.geometry("420x300")
        self.transient(master)
        self.configure(bg=BG)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="表达式: 如 1d20, 2d6+3, 4d6 (4d6取高三请自行取舍)",
                  foreground=DIM).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        self.e = ttk.Entry(row, width=14)
        self.e.insert(0, "1d20")
        self.e.pack(side="left")
        ttk.Button(row, text="掷!", command=self.roll).pack(side="left", padx=6)
        for txt in ["1d20", "1d20+5", "2d6+3", "1d8", "1d4"]:
            ttk.Button(f, text=txt, width=8,
                       command=lambda t=txt: (self.e.delete(0, "end"),
                                              self.e.insert(0, t),
                                              self.roll())).pack(
                side="left", padx=3, pady=6)
        self.out = tk.Text(f, height=8, state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        self.out.pack(fill="both", expand=True)
        self.e.bind("<Return>", lambda e: self.roll())

    def roll(self):
        try:
            total, detail = roll_dice(self.e.get().strip())
        except Exception:
            messagebox.showerror("错误", "无法解析表达式", parent=self)
            return
        self.out.config(state="normal")
        self.out.insert("end", detail + "\n")
        self.out.see("end")
        self.out.config(state="disabled")


# ----------------------------------------------------------------------------
# 主窗口 · 角色卡
# ----------------------------------------------------------------------------

class App(tk.Tk):

    def __init__(self, selftest=False):
        super().__init__()
        self._selftest = selftest
        self.title("D&D 5.5e 人物卡 · Character Builder")
        self.geometry("1340x860")
        self.minsize(1200, 760)
        self.configure(bg=BG)
        self.rules = Rules()
        self.char = None
        self.sneak_var = tk.BooleanVar(value=False)   # 掷伤害时是否附加偷袭
        self._xp_th = {int(k): int(v) for k, v in
                       self.rules.d["progression"]["xp_thresholds"].items()}

        self._setup_style()
        self._build_menu()
        self._build_toolbar()
        self._build_main()
        self._build_status()

        try:
            os.makedirs(CHAR_DIR, exist_ok=True)
        except OSError:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if selftest:
            self.withdraw()
        else:
            self.after(300, self._auto_start)

    # ---- 样式 ----

    def _setup_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        F = UI_FONT
        st.configure(".", font=(F, 10), background=BG, foreground=TEXT,
                     fieldbackground=CARD, troughcolor=PANEL,
                     bordercolor=BORDER, insertcolor=TEXT,
                     selectbackground=GOLD, selectforeground=INK)
        st.configure("TFrame", background=BG)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        st.configure("Card.TLabel", background=CARD, foreground=TEXT)
        st.configure("Dim.TLabel", background=BG, foreground=DIM)
        st.configure("DimPanel.TLabel", background=PANEL, foreground=DIM)
        st.configure("DimCard.TLabel", background=CARD, foreground=DIM)
        st.configure("GoldPanel.TLabel", background=PANEL, foreground=GOLD2)
        st.configure("Title.TLabel", font=(F, 22, "bold"),
                     background=BG, foreground=GOLD2)
        st.configure("H2.TLabel", font=(F, 11, "bold"),
                     background=BG, foreground=GOLD2)
        st.configure("TLabelframe", background=BG, bordercolor=BORDER)
        st.configure("TLabelframe.Label", background=BG, foreground=GOLD2,
                     font=(F, 10, "bold"))
        # 按钮
        st.configure("TButton", background=CARD2, foreground=TEXT,
                     bordercolor=BORDER, padding=(10, 5))
        st.map("TButton",
               background=[("active", "#403b4e"), ("pressed", "#4a4459"),
                           ("disabled", "#26232e")],
               foreground=[("disabled", "#5c5967")])
        st.configure("Gold.TButton", background="#8a6d1a",
                     foreground="#ffe9a8", font=(F, 10, "bold"))
        st.map("Gold.TButton", background=[("active", "#a8871f"),
                                           ("pressed", GOLD)])
        st.configure("Hero.TButton", background="#8a6d1a", padding=(24, 12),
                     foreground="#ffe9a8", font=(F, 13, "bold"))
        st.map("Hero.TButton", background=[("active", "#a8871f"),
                                           ("pressed", GOLD)])
        st.configure("Red.TButton", background=RED2, foreground="#ffd9d2")
        st.map("Red.TButton", background=[("active", "#a83a2c"),
                                          ("pressed", RED)])
        st.configure("Green.TButton", background="#2f6b3a",
                     foreground="#d8f2dc")
        st.map("Green.TButton", background=[("active", "#3a8348"),
                                            ("pressed", GREEN)])
        st.configure("Mini.TButton", padding=(4, 1), font=(F, 9))
        # 选项卡
        st.configure("TNotebook", background=BG, bordercolor=BORDER)
        st.configure("TNotebook.Tab", background=PANEL, foreground=DIM,
                     padding=(14, 6))
        st.map("TNotebook.Tab", background=[("selected", CARD2)],
               foreground=[("selected", GOLD2)])
        # 输入控件
        st.configure("TEntry", fieldbackground=CARD, foreground=TEXT,
                     insertcolor=TEXT, bordercolor=BORDER)
        st.configure("TSpinbox", fieldbackground=CARD, foreground=TEXT,
                     insertcolor=TEXT, bordercolor=BORDER, arrowcolor=TEXT)
        st.configure("TCombobox", fieldbackground=CARD, foreground=TEXT,
                     insertcolor=TEXT, bordercolor=BORDER, arrowcolor=TEXT)
        # readonly 状态在 clam 下必须显式 map, 否则输入框仍是白底
        st.map("TCombobox",
               fieldbackground=[("readonly", CARD), ("!disabled", CARD)],
               foreground=[("readonly", TEXT)],
               selectbackground=[("readonly", CARD)],
               selectforeground=[("readonly", TEXT)],
               arrowcolor=[("readonly", GOLD2)])
        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", GOLD)
        self.option_add("*TCombobox*Listbox.selectForeground", INK)
        # 勾选/单选
        for name in ("TCheckbutton", "TRadiobutton"):
            st.configure(name, background=BG, foreground=TEXT)
            st.map(name, background=[("active", BG)],
                   foreground=[("active", GOLD2)])
        # 进度条
        st.configure("HP.Horizontal.TProgressbar", troughcolor="#3a2126",
                     background=RED, bordercolor=BORDER)
        st.configure("XP.Horizontal.TProgressbar", troughcolor="#33302a",
                     background=GOLD, bordercolor=BORDER)
        st.configure("TSeparator", background=BORDER)

    # ---- 菜单 ----

    def _build_menu(self):
        mk = dict(bg=PANEL, fg=TEXT, activebackground=GOLD,
                  activeforeground=INK, bd=0)
        m = tk.Menu(self, **mk)
        filem = tk.Menu(m, tearoff=0, **mk)
        filem.add_command(label="新建角色…", command=self.new_character)
        filem.add_separator()
        filem.add_command(label="保存角色 (Ctrl+S)",
                          command=self.save_character, accelerator="Ctrl+S")
        filem.add_command(label="另存为…",
                          command=self.save_character_as)
        filem.add_command(label="打开存档文件夹",
                          command=self.open_char_folder)
        filem.add_separator()
        filem.add_command(label="载入角色… (Ctrl+O)",
                          command=self.load_character, accelerator="Ctrl+O")
        filem.add_command(label="导出角色JSON副本…",
                          command=self.export_character)
        m.add_cascade(label="文件", menu=filem)

        chm = tk.Menu(m, tearoff=0, **mk)
        chm.add_command(label="升级…", command=self.level_up)
        chm.add_separator()
        chm.add_command(label="长休 (回复HP与全部法术位)", command=self.long_rest)
        chm.add_command(label="短休 (邪术师回复法术位)", command=self.short_rest)
        m.add_cascade(label="角色", menu=chm)

        tm = tk.Menu(m, tearoff=0, **mk)
        tm.add_command(label="骰子工具", command=lambda: DiceDialog(self))
        m.add_cascade(label="工具", menu=tm)

        self.config(menu=m)
        self.bind("<Control-s>", lambda e: self.save_character())
        self.bind("<Control-o>", lambda e: self.load_character())

    # ---- 顶部工具栏: 所有常用功能一排直达 ----

    def _build_toolbar(self):
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(10, 7))
        bar.pack(fill="x")
        ttk.Label(bar, text="🎲 D&D 5.5e 人物卡", style="GoldPanel.TLabel",
                  font=(UI_FONT, 13, "bold")).pack(side="left", padx=(2, 16))

        def b(txt, cmd, style="TButton"):
            ttk.Button(bar, text=txt, command=cmd,
                       style=style).pack(side="left", padx=3)

        b("✦ 新建角色", self.new_character, "Gold.TButton")
        b("💾 保存", self.save_character)
        b("📂 打开", self.load_character)
        b("⬇ 导出JSON", self.export_character)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                   padx=10)
        b("⬆ 升级", self.level_up, "Gold.TButton")
        b("🌙 长休", self.long_rest)
        b("☕ 短休", self.short_rest)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y",
                                                   padx=10)
        b("🎲 骰子工具", lambda: DiceDialog(self))

    # ---- 主区域: 欢迎页 / 角色卡 二选一 ----

    def _build_main(self):
        self.main_area = ttk.Frame(self)
        self.main_area.pack(fill="both", expand=True)
        self._build_empty_view()
        self._build_sheet_view()
        self._show_view()

    def _show_view(self):
        self.empty_view.pack_forget()
        self.sheet_view.pack_forget()
        view = self.sheet_view if self.char else self.empty_view
        view.pack(fill="both", expand=True)

    def _build_empty_view(self):
        v = ttk.Frame(self.main_area)
        self.empty_view = v
        inner = ttk.Frame(v)
        inner.place(relx=0.5, rely=0.42, anchor="center")
        ttk.Label(inner, text="⚔  🎲  ⚔", font=(UI_FONT, 36),
                  foreground=GOLD2, background=BG).pack(pady=(0, 8))
        ttk.Label(inner, text="D&D 5.5e 人物卡", style="Title.TLabel").pack()
        ttk.Label(inner, text="2024 版规则 · 建卡向导 / 升级 / 战斗追踪 一站式",
                  style="Dim.TLabel", font=(UI_FONT, 11)).pack(pady=(4, 28))
        ttk.Button(inner, text="✦  创建新角色 (六步向导)", style="Hero.TButton",
                   command=self.new_character).pack(pady=7)
        ttk.Button(inner, text="📂  打开角色存档 (.json)", style="Hero.TButton",
                   command=self.load_character).pack(pady=7)
        ttk.Label(inner,
                  text="内置: 12 职业 · 16 背景 · 10 种族 · 武器专精 · 法术位追踪 · "
                       "状态/力竭 · 快捷骰子与掷骰日志",
                  style="Dim.TLabel").pack(pady=(26, 0))

    # ---- 角色卡布局 ----

    def _build_sheet_view(self):
        v = ttk.Frame(self.main_area, padding=(10, 8))
        self.sheet_view = v
        self._build_hero(v)
        cols = ttk.Frame(v)
        cols.pack(fill="both", expand=True, pady=(8, 0))
        cols.columnconfigure(0, minsize=320)
        cols.columnconfigure(1, weight=1)
        cols.columnconfigure(2, minsize=320)
        cols.rowconfigure(0, weight=1)
        self.col_left = ttk.Frame(cols)
        self.col_left.grid(row=0, column=0, sticky="ns")
        self.col_mid = ttk.Frame(cols)
        self.col_mid.grid(row=0, column=1, sticky="nsew", padx=8)
        self.col_right = ttk.Frame(cols)
        self.col_right.grid(row=0, column=2, sticky="ns")
        self._build_left()
        self._build_mid()
        self._build_right()

    def _chip(self, parent, title, cmd=None):
        f = ttk.Frame(parent, style="Card.TFrame", padding=(10, 6))
        f.pack(side="left", padx=4)
        ttk.Label(f, text=title, style="DimCard.TLabel").pack()
        val = ttk.Label(f, text="—", style="Card.TLabel",
                        font=(UI_FONT, 16, "bold"))
        val.pack()
        if cmd:
            ttk.Button(f, text="🎲 掷", style="Mini.TButton",
                       command=cmd).pack(pady=(2, 0))
        return val

    def _build_hero(self, parent):
        F = UI_FONT
        hero = ttk.Frame(parent, style="Panel.TFrame", padding=12)
        hero.pack(fill="x")

        # 左: 身份 + XP
        idf = ttk.Frame(hero, style="Panel.TFrame")
        idf.pack(side="left", fill="y")
        self.hero_name = ttk.Label(idf, text="—", style="GoldPanel.TLabel",
                                   font=(F, 17, "bold"))
        self.hero_name.pack(anchor="w")
        self.hero_sub = ttk.Label(idf, text="", style="DimPanel.TLabel")
        self.hero_sub.pack(anchor="w", pady=(1, 6))
        xpf = ttk.Frame(idf, style="Panel.TFrame")
        xpf.pack(anchor="w")
        ttk.Label(xpf, text="经验 XP", style="DimPanel.TLabel").pack(side="left")
        self.xp_var = tk.IntVar()
        sp = ttk.Spinbox(xpf, from_=0, to=999999, width=8,
                         textvariable=self.xp_var, command=self._xp_changed)
        sp.pack(side="left", padx=4)
        sp.bind("<Return>", lambda e: self._xp_changed())
        sp.bind("<FocusOut>", lambda e: self._xp_changed())
        self.xp_hint = ttk.Label(xpf, text="", style="GoldPanel.TLabel")
        self.xp_hint.pack(side="left", padx=(6, 0))
        self.xp_bar = ttk.Progressbar(idf, style="XP.Horizontal.TProgressbar",
                                      length=240, mode="determinate")
        self.xp_bar.pack(anchor="w", pady=(5, 0))

        # 中: HP 大面板
        hpf = ttk.Frame(hero, style="Panel.TFrame")
        hpf.pack(side="left", padx=30)
        ttk.Label(hpf, text="❤ 生命值", style="DimPanel.TLabel").pack(anchor="w")
        self.hp_big = ttk.Label(hpf, text="0 / 0", background=PANEL,
                                foreground="#ff8a75", font=(F, 20, "bold"))
        self.hp_big.pack(anchor="w")
        self.hp_bar = ttk.Progressbar(hpf, style="HP.Horizontal.TProgressbar",
                                      length=235, mode="determinate")
        self.hp_bar.pack(anchor="w", pady=3)
        row = ttk.Frame(hpf, style="Panel.TFrame")
        row.pack(anchor="w")
        for txt, n, sty in [("−5", -5, "Red.TButton"), ("−1", -1, "Red.TButton"),
                            ("+1", 1, "Green.TButton"),
                            ("+5", 5, "Green.TButton")]:
            ttk.Button(row, text=txt, width=4, style=sty,
                       command=lambda v=n: self._hp_add(v)).pack(side="left",
                                                                 padx=2)
        ttk.Button(row, text="回满", width=5,
                   command=lambda: self._hp_add(99999)).pack(side="left",
                                                             padx=(8, 2))
        ttk.Label(row, text="临时HP", style="DimPanel.TLabel").pack(
            side="left", padx=(10, 2))
        self.hp_temp_var = tk.IntVar()
        tsp = ttk.Spinbox(row, from_=0, to=99, width=4,
                          textvariable=self.hp_temp_var,
                          command=self._hp_temp_changed)
        tsp.pack(side="left")
        tsp.bind("<FocusOut>", lambda e: self._hp_temp_changed())

        # 右: 数值徽章
        chips = ttk.Frame(hero, style="Panel.TFrame")
        chips.pack(side="right")
        self.chip_ac = self._chip(chips, "🛡 护甲 AC")
        self.chip_init = self._chip(chips, "⚡ 先攻", cmd=self._roll_init)
        self.chip_speed = self._chip(chips, "👣 速度")
        self.chip_pb = self._chip(chips, "✦ 熟练")
        self.chip_pp = self._chip(chips, "👁 被动察觉")

    def _build_left(self):
        F = UI_FONT
        ab = ttk.LabelFrame(self.col_left,
                            text=" 属性 (卡片内一键掷检定/豁免) ", padding=8)
        ab.pack(fill="x")
        self.ab_entries, self.ab_modlbls, self.ab_savelbls = {}, {}, {}
        for i, a in enumerate(ABILITIES):
            card = ttk.Frame(ab, style="Card.TFrame", padding=8)
            card.grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="nsew")
            top = ttk.Frame(card, style="Card.TFrame")
            top.pack(fill="x")
            nm = ttk.Label(top, text=f"{ABILITY_CN[a]} {a}",
                           style="DimCard.TLabel")
            nm.pack(side="left")
            nm.bind("<Enter>", lambda e, x=a: self._ability_hint(x))
            sv = ttk.Label(top, text="", style="Card.TLabel",
                           foreground=PURPLE)
            sv.pack(side="right")
            self.ab_savelbls[a] = sv
            self.ab_modlbls[a] = ttk.Label(card, text="+0", style="Card.TLabel",
                                           font=(F, 18, "bold"))
            self.ab_modlbls[a].pack()
            bot = ttk.Frame(card, style="Card.TFrame")
            bot.pack(pady=(2, 0))
            v = tk.IntVar()
            sb = ttk.Spinbox(bot, from_=1, to=20, width=3, textvariable=v,
                             command=self._score_edited)
            sb.pack(side="left")
            sb.bind("<FocusOut>", lambda e: self._score_edited())
            self.ab_entries[a] = v
            ttk.Button(bot, text="检🎲", style="Mini.TButton", width=5,
                       command=lambda x=a: self._roll_check(x)
                       ).pack(side="left", padx=(4, 1))
            ttk.Button(bot, text="豁🎲", style="Mini.TButton", width=5,
                       command=lambda x=a: self._roll_save(x)
                       ).pack(side="left", padx=1)

        self.ab_hint = tk.Label(ab, text="鼠标停在属性名上可看该属性的用途",
                                bg=BG, fg=DIM, wraplength=286, justify="left",
                                anchor="nw", height=2)
        self.ab_hint.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ar = ttk.LabelFrame(self.col_left, text=" 护甲与防御 ", padding=8)
        ar.pack(fill="x", pady=(8, 0))
        self.armor_cb = ttk.Combobox(ar, state="readonly", width=20,
                                     values=[a[0] for a in ARMORS])
        self.armor_cb.current(0)
        self.armor_cb.pack(anchor="w", pady=2)
        self.armor_cb.bind("<<ComboboxSelected>>",
                           lambda e: self._armor_changed())
        self.shield_var = tk.BooleanVar()
        ttk.Checkbutton(ar, text="盾牌 (AC +2)", variable=self.shield_var,
                        command=self._armor_changed).pack(anchor="w", pady=2)
        self.tough_var = tk.BooleanVar()
        ttk.Checkbutton(ar, text="Tough 专长 (每级 +2 HP)",
                        variable=self.tough_var,
                        command=self._tough_changed).pack(anchor="w", pady=2)

    def _build_mid(self):
        F = UI_FONT
        self.nb = ttk.Notebook(self.col_mid)
        nb = self.nb
        nb.pack(fill="both", expand=True)

        # ---- 技能 ----
        t1 = ttk.Frame(nb, padding=8)
        self.tab_skills = t1
        nb.add(t1, text=" 技 能 ")
        ttk.Label(t1, text="🎲=掷检定   ✓=熟练   ◇/◆=专精 Expertise (需先熟练, 双倍熟练加值)",
                  style="Dim.TLabel").pack(anchor="w", pady=(0, 2))
        self.skill_hint = tk.Label(t1, text="鼠标停在技能名上可看它管什么检定",
                                   bg=BG, fg=DIM, wraplength=430,
                                   justify="left", anchor="nw", height=2)
        self.skill_hint.pack(anchor="w", pady=(0, 6))
        grid = ttk.Frame(t1)
        grid.pack(fill="both", expand=True)
        self.skill_vars, self.skill_modlbls = {}, {}
        self.skill_namelbls, self.skill_expbtns = {}, {}
        for i, s in enumerate(self.rules.d["skills"]):
            sid = s["id"]
            r, col = i % 9, i // 9
            row = ttk.Frame(grid)
            row.grid(row=r, column=col, sticky="w", padx=(0, 26), pady=3)
            ttk.Button(row, text="🎲", width=3, style="Mini.TButton",
                       command=lambda x=sid: self._roll_skill(x)
                       ).pack(side="left")
            v = tk.BooleanVar()
            self.skill_vars[sid] = v
            ttk.Checkbutton(row, variable=v, width=2,
                            command=lambda x=sid: self._skill_toggled(x)
                            ).pack(side="left")
            nl = ttk.Label(row, text=s["name"].split(" ")[0], width=8,
                           anchor="w")
            nl.pack(side="left")
            nl.bind("<Enter>", lambda e, x=sid: self._skill_hover(x))
            ab = ttk.Label(row, text=ABILITY_CN[s["ability"]], width=3,
                           style="Dim.TLabel")
            ab.pack(side="left")
            self.skill_namelbls[sid] = nl
            ml = ttk.Label(row, text="+0", width=4, font=(F, 10, "bold"))
            ml.pack(side="left")
            self.skill_modlbls[sid] = ml
            eb = ttk.Button(row, text="◇", width=3, style="Mini.TButton",
                            command=lambda x=sid: self._toggle_expertise(x))
            eb.pack(side="left", padx=(2, 0))
            self.skill_expbtns[sid] = eb

        # ---- 法术 ----
        t2 = ttk.Frame(nb, padding=8)
        self.tab_spells = t2
        nb.add(t2, text=" 法 术 ")
        self.slots_head = ttk.Label(t2, text="", style="H2.TLabel")
        self.slots_head.pack(anchor="w")
        self.slots_frame = ttk.Frame(t2)
        self.slots_frame.pack(anchor="nw", pady=(2, 4))
        self.slots_widgets = {}

        bar = ttk.Frame(t2)
        bar.pack(fill="x", pady=2)
        self.spell_add_cb = ttk.Combobox(bar, state="readonly", width=24)
        self.spell_add_cb.pack(side="left")
        ttk.Button(bar, text="＋ 学习", style="Mini.TButton",
                   command=self._spell_add).pack(side="left", padx=3)
        ttk.Button(bar, text="－ 移除", style="Mini.TButton",
                   command=self._spell_del).pack(side="left")
        ttk.Button(bar, text="▶ 施放", style="Gold.TButton",
                   command=self._spell_cast).pack(side="right")
        ttk.Button(bar, text="◉ 专注", style="Mini.TButton",
                   command=self._spell_focus).pack(side="right", padx=3)
        self.spell_quota_lbl = ttk.Label(t2, text="", style="Dim.TLabel")
        self.spell_quota_lbl.pack(anchor="w", pady=(2, 0))

        self.spell_list = tk.Listbox(t2, height=7, **LISTBOX_STYLE)
        self.spell_list.pack(fill="x", pady=2)
        self.spell_list.bind("<<ListboxSelect>>", self._spell_show)
        ttk.Label(t2, text="法术详情", style="H2.TLabel").pack(anchor="w", pady=(2, 0))
        self.spell_detail = tk.Text(t2, height=7, wrap="word", state="disabled",
                                    **TEXT_STYLE, width=1)
        self.spell_detail.pack(fill="both", expand=True, pady=2)
        ttk.Label(t2, text="● 剩余环位 ○ 已用；戏法不耗环位；专注法术同时只能维持一个。",
                  style="Dim.TLabel", wraplength=520,
                  justify="left").pack(anchor="w", side="bottom")

        # ---- 装备 / 攻击 / 加成 ----
        t3 = ttk.Frame(nb, padding=8)
        nb.add(t3, text=" 装备·加成 ")
        wf = ttk.LabelFrame(t3, text="武器与攻击", padding=6)
        wf.pack(fill="x")
        r1 = ttk.Frame(wf)
        r1.pack(fill="x")
        ttk.Label(r1, text="武器:").pack(side="left")
        self.weapon_cb = ttk.Combobox(r1, state="readonly", width=19,
                                      values=["（未装备）"]
                                      + [w[0] for w in WEAPONS])
        self.weapon_cb.pack(side="left", padx=4)
        self.weapon_cb.bind("<<ComboboxSelected>>",
                            lambda e: self._weapon_changed())
        ttk.Label(r1, text="魔法 +").pack(side="left", padx=(6, 0))
        self.wmagic_var = tk.IntVar(value=0)
        ttk.Spinbox(r1, from_=0, to=3, width=3, textvariable=self.wmagic_var,
                    command=self._weapon_changed).pack(side="left")
        self.atk_lbl = ttk.Label(r1, text="", font=("", 10, "bold"),
                                 foreground=GOLD2)
        self.atk_lbl.pack(side="left", padx=8)
        ttk.Button(r1, text="掷攻击", style="Mini.TButton",
                   command=self._attack_roll).pack(side="right", padx=2)
        ttk.Button(r1, text="掷伤害", style="Mini.TButton",
                   command=self._damage_roll).pack(side="right")
        r2 = ttk.Frame(wf)
        r2.pack(fill="x", pady=(4, 0))
        ttk.Label(r2, text="战斗风格:").pack(side="left")
        self.style_cb = ttk.Combobox(
            r2, state="readonly", width=26,
            values=["（无）"] + [v[0] for v in FIGHTING_STYLES.values()])
        self.style_cb.pack(side="left", padx=4)
        self.style_cb.bind("<<ComboboxSelected>>",
                           lambda e: self._style_changed())
        self.style_note = ttk.Label(r2, text="", style="Dim.TLabel")
        self.style_note.pack(side="left", padx=6)

        mf = ttk.LabelFrame(t3, text="魔法物品 / 饰品 (勾选即自动计入)", padding=6)
        mf.pack(fill="x", pady=(6, 0))
        self.item_vars = {}
        for i, it in enumerate(MAGIC_ITEMS):
            v = tk.BooleanVar()
            self.item_vars[it["id"]] = v
            cb = ttk.Checkbutton(mf, text=it["name"].split(" ")[0],
                                 variable=v,
                                 command=lambda i2=it["id"]: self._item_changed(i2))
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=4)
            cb.bind("<Enter>", lambda e, i2=it: self._item_hint(i2))
        self.item_hint = tk.Label(mf, text="鼠标停在物品上可看效果",
                                  bg=BG, fg=DIM, wraplength=520,
                                  justify="left", anchor="nw", height=2)
        self.item_hint.grid(row=4, column=0, columnspan=3, sticky="w")

        ttk.Label(t3, text="加成明细 (自动计算来源)", style="H2.TLabel").pack(
            anchor="w", pady=(6, 0))
        self.bonus_text = tk.Text(t3, height=4, wrap="word", state="disabled",
                                  **TEXT_STYLE, width=1)
        self.bonus_text.pack(fill="x", pady=2)

        lw = ttk.Frame(t3)
        lw.pack(fill="x", pady=(4, 0))
        ttk.Label(lw, text="武器专精 (长休可换)", style="H2.TLabel"
                  ).pack(side="left")
        ttk.Button(lw, text="编辑…", style="Mini.TButton",
                   command=self._edit_mastery).pack(side="left", padx=8)
        self.mastery_list = tk.Listbox(t3, height=2, **LISTBOX_STYLE)
        self.mastery_list.pack(fill="x", pady=2)

        ttk.Label(t3, text="装备清单 (自由文本)", style="H2.TLabel").pack(
            anchor="w", pady=(4, 0))
        self.eq_text = tk.Text(t3, height=2, wrap="word", **TEXT_STYLE, width=1)
        self.eq_text.pack(fill="both", expand=True, pady=2)
        self.eq_text.bind("<FocusOut>", lambda e: self._notes_changed())

        # ---- 职业: 资源池 / 职业特性 / 子职介绍 ----
        t6 = ttk.Frame(nb, padding=8)
        self.tab_class = t6
        nb.add(t6, text=" 职 业 ")
        ttk.Label(t6, text="资源可手动增减；短休/长休会按规则自动恢复。",
                  style="Dim.TLabel").pack(anchor="w", side="bottom")
        self.class_scroll = ScrollFrame(t6, height=462)
        self.class_scroll.pack(fill="both", expand=True)
        self.class_body = self.class_scroll.body

        # ---- 专长·特性 ----
        t4 = ttk.Frame(nb, padding=8)
        self.tab_feats = t4
        nb.add(t4, text=" 专长·特性 ")
        ttk.Label(t4, text="专长 (点选看效果)", style="H2.TLabel").pack(anchor="w")
        fr = ttk.Frame(t4)
        fr.pack(fill="x", pady=(4, 0))
        self.feat_list = tk.Listbox(fr, height=5, **LISTBOX_STYLE)
        self.feat_list.pack(side="left", fill="both", expand=True)
        self.feat_list.bind("<<ListboxSelect>>", self._on_feat_select)
        fb = ttk.Frame(fr)
        fb.pack(side="left", padx=(6, 0))
        ttk.Button(fb, text="+ 添加", command=self._add_feat
                   ).pack(fill="x", pady=2)
        ttk.Button(fb, text="− 移除", command=self._del_feat
                   ).pack(fill="x", pady=2)
        self.feat_info = tk.Label(t4, text="点选专长查看效果说明",
                                  bg=BG, fg=DIM, wraplength=560,
                                  justify="left", anchor="nw", height=3)
        self.feat_info.pack(anchor="w", pady=(4, 0))
        ttk.Label(t4, text="※ 自动计入数值: Tough (每级 HP+2)、Alert (先攻 +熟练)；"
                           "其余专长按说明手动应用。",
                  style="Dim.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(2, 0))
        ttk.Label(t4, text="种族特性 / 背景", style="H2.TLabel").pack(
            anchor="w", pady=(8, 0))
        self.trait_text = tk.Text(t4, height=10, wrap="word", state="disabled",
                                  **TEXT_STYLE, width=1)
        self.trait_text.pack(fill="both", expand=True, pady=4)

        # ---- 笔记 ----
        t5 = ttk.Frame(nb, padding=8)
        nb.add(t5, text=" 笔 记 ")
        ttk.Label(t5, text="语言 (通用语外自选 2 门, 逗号分隔):",
                  style="H2.TLabel").pack(anchor="w")
        self.lang_entry = ttk.Entry(t5)
        self.lang_entry.pack(fill="x", pady=2)
        self.lang_entry.bind("<FocusOut>", lambda e: self._lang_changed())
        ttk.Label(t5, text="备注 / 法术列表 / 背景故事:",
                  style="H2.TLabel").pack(anchor="w", pady=(8, 0))
        self.note_text = tk.Text(t5, wrap="word", **TEXT_STYLE, width=1)
        self.note_text.pack(fill="both", expand=True, pady=2)
        self.note_text.bind("<FocusOut>", lambda e: self._notes_changed())

    def _build_right(self):
        # 状态
        cf = ttk.LabelFrame(self.col_right, text=" 状态 (会与检定联动) ", padding=8)
        cf.pack(fill="x")
        self.cond_vars = {}
        grid = ttk.Frame(cf)
        grid.pack(anchor="w")
        for i, cond in enumerate(CONDITIONS):
            v = tk.BooleanVar()
            self.cond_vars[cond] = v
            cb = ttk.Checkbutton(grid, text=cond, variable=v,
                                 command=lambda cn=cond: self._cond_toggled(cn))
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=4)
            cb.bind("<Enter>", lambda e, cn=cond: self._cond_hint(cn))
        self.cond_hint = tk.Label(cf, text="鼠标停在状态名上可看效果",
                                  bg=BG, fg=DIM, wraplength=262,
                                  justify="left", anchor="nw", height=2)
        self.cond_hint.pack(anchor="w", pady=(4, 0))
        exf = ttk.Frame(cf)
        exf.pack(anchor="w", pady=(8, 0))
        ttk.Label(exf, text="力竭等级:").pack(side="left")
        self.exh_var = tk.IntVar()
        ttk.Spinbox(exf, from_=0, to=6, width=3, textvariable=self.exh_var,
                    command=self._exh_changed).pack(side="left", padx=4)
        ttk.Label(exf, text="(每级 d20-2 · 速度-5尺)",
                  style="Dim.TLabel").pack(side="left")
        self.exh_warn = ttk.Label(cf, text="", foreground="#e05c4d")
        self.exh_warn.pack(anchor="w")

        # 濒死 / 死亡豁免 (2024: 3 成功稳定, 3 失败死亡)
        dyf = ttk.Frame(cf)
        dyf.pack(anchor="w", pady=(6, 0))
        ttk.Label(dyf, text="☠ 濒死").pack(side="left")
        self.death_lbl = ttk.Label(dyf, text="✓0 ✗0", foreground="#e05c4d")
        self.death_lbl.pack(side="left", padx=4)
        ttk.Button(dyf, text="掷", width=3, style="Mini.TButton",
                   command=self._death_save).pack(side="left", padx=2)
        ttk.Button(dyf, text="重置", width=4, style="Mini.TButton",
                   command=self._death_reset).pack(side="left")

        # 专注检定 (受伤时 DC = max(10, 伤害/2))
        ccf = ttk.Frame(cf)
        ccf.pack(anchor="w", pady=(4, 0))
        ttk.Button(ccf, text="专注检定", style="Mini.TButton",
                   command=self._conc_check).pack(side="left")
        self.conc_lbl = ttk.Label(ccf, text="专注: —", style="Dim.TLabel")
        self.conc_lbl.pack(side="left", padx=6)

        # 快捷骰子
        qf = ttk.LabelFrame(self.col_right, text=" 快捷骰子 ", padding=8)
        qf.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(qf)
        row.pack()
        for n in (4, 6, 8, 10, 12, 20):
            ttk.Button(row, text=f"d{n}", width=4, style="Mini.TButton",
                       command=lambda x=n: self._quick_die(x)
                       ).pack(side="left", padx=2, pady=2)

        # 掷骰记录
        lg = ttk.LabelFrame(self.col_right, text=" 掷骰记录 ", padding=8)
        lg.pack(fill="both", expand=True, pady=(8, 0))
        self.roll_log = tk.Listbox(lg, **LISTBOX_STYLE)
        self.roll_log.pack(fill="both", expand=True)
        ttk.Button(lg, text="清空记录", style="Mini.TButton",
                   command=lambda: self.roll_log.delete(0, "end")
                   ).pack(anchor="e", pady=(4, 0))

    def _build_status(self):
        self.status = ttk.Label(
            self, text="欢迎来到 D&D 5.5e 人物卡 —— 点击工具栏「✦ 新建角色」开始冒险",
            style="Dim.TLabel", anchor="w", padding=(12, 5))
        self.status.pack(fill="x", side="bottom")

    # ---- 刷新 ----

    def set_character(self, char):
        self.char = char
        self._show_view()
        self.refresh()
        # 建卡完成后立即写入固定目录, 下次启动可直接读到
        if not getattr(self, "_selftest", False) and char is not None:
            try:
                path = self._char_path()
                self._write_char(path)
                self._remember_last(path)
            except OSError:
                pass

    def refresh(self):
        c = self.char
        if not c:
            return
        cls = c.cls()
        sp = c.r.sp(c.species_id)
        bg = c.r.bg(c.background_id)

        # 英雄区
        sub = subclass_cn(c.subclass) if c.subclass else \
            ("(3级解锁子职)" if c.level < 3 else "(未选子职)")
        self.hero_name.config(text=f"❖ {c.name}")
        self.hero_sub.config(
            text=f"{cls['name']} {c.level} 级 · {sub}   ｜   "
                 f"{sp['name']} · {bg['name']}")
        self.chip_ac.config(text=str(c.ac()))
        self.chip_init.config(text=mod_str(c.initiative()))
        self.chip_speed.config(text=f"{c.speed()}尺")
        self.chip_pb.config(text=mod_str(c.pb()))
        self.chip_pp.config(text=str(c.passive_perception()))

        # HP
        hp, mx = c.hp_current, c.hp_max()
        frac = hp / mx if mx else 0
        color = "#7bc47f" if frac > 0.5 else (
            "#e8c34a" if frac > 0.25 else "#ff8a75")
        self.hp_big.config(text=f"{hp} / {mx}", foreground=color)
        self.hp_bar.config(maximum=mx, value=hp)
        self.hp_temp_var.set(c.hp_temp)

        # XP
        self.xp_var.set(c.xp)
        self._xp_changed()

        # 属性卡
        for a in ABILITIES:
            self.ab_entries[a].set(c.score(a))
            self.ab_modlbls[a].config(
                text=mod_str(ability_mod(c.score(a))))
            star = "豁免★" if a in cls["saves"] else ""
            self.ab_savelbls[a].config(text=star)

        # 护甲
        self.armor_cb.current(c.armor_index)
        self.shield_var.set(c.shield)
        self.tough_var.set(c.tough_feat)

        # 技能
        allow_exp = c.expertise_allowance() > 0
        for sid in self.skill_vars:
            prof = sid in c.skill_prof
            exp = sid in c.expertise
            self.skill_vars[sid].set(prof)
            self.skill_modlbls[sid].config(text=mod_str(c.skill_mod(sid)))
            self.skill_namelbls[sid].config(
                foreground=PURPLE if exp else (GOLD2 if prof else TEXT))
            self.skill_expbtns[sid].config(
                text="◆" if exp else "◇",
                state=("normal" if allow_exp else "disabled"))

        # 法术位
        for w in self.slots_frame.winfo_children():
            w.destroy()
        self.slots_widgets = {}
        slots = c.spell_slots()
        if not slots:
            self.slots_head.config(text="（该职业无施法能力）")
        else:
            cast = c.casting()
            tag = {"full": "全施法", "half": "半施法",
                   "pact": "契约魔法"}.get(cast["type"], "")
            self.slots_head.config(
                text=f"{tag} · 施法属性 {cast['ability']} · "
                     f"法术DC {c.spell_dc()} · 法术命中 {mod_str(c.spell_attack())}")
            for i, (lv, mx2) in enumerate(sorted(slots.items())):
                used = c.spell_slots_used.get(lv, 0)
                box = ttk.Frame(self.slots_frame, style="Card.TFrame",
                                padding=8)
                box.grid(row=0, column=i, padx=4, pady=4)
                arc = lv in c.arcanum_levels()
                ttk.Label(box, text=(f"秘契 {lv} 环" if arc else f"{lv} 环"),
                          style="DimCard.TLabel").pack()
                pips = "●" * (mx2 - used) + "○" * used
                lbl = ttk.Label(box, text=pips, style="Card.TLabel",
                                font=(UI_FONT, 13, "bold"), foreground=GOLD2)
                lbl.pack()
                self.slots_widgets[lv] = lbl
                brow = ttk.Frame(box, style="Card.TFrame")
                brow.pack(pady=(3, 0))
                ttk.Button(brow, text="施法", width=4, style="Mini.TButton",
                           command=lambda l=lv: self._slot_spend(l)
                           ).pack(side="left", padx=1)
                ttk.Button(brow, text="恢复", width=4, style="Mini.TButton",
                           command=lambda l=lv: self._slot_restore(l)
                           ).pack(side="left", padx=1)

        # 护甲下拉: 未熟练项标 ✗ (用 index 取值, 加后缀不影响)
        self.armor_cb["values"] = [
            a[0] + ("" if c.has_armor_prof_at(i) else " ✗未熟练")
            for i, a in enumerate(ARMORS)]
        self.armor_cb.current(c.armor_index)
        self.shield_var.set(c.shield)

        # 武器 / 战斗风格 / 魔法物品 / 加成明细
        # 武器下拉与护甲一致: 选项里直接标 ✓熟练 / ✗未熟练
        self.weapon_cb["values"] = ["（未装备）"] + [
            w[0] + (" ✓熟练" if c.has_weapon_prof(w[0]) else " ✗未熟练")
            for w in WEAPONS]
        self.weapon_cb.set(self._weapon_label(c.weapon) if c.weapon
                           else "（未装备）")
        self.wmagic_var.set(c.weapon_magic)
        if c.weapon:
            prof = "✓熟练" if c.has_weapon_prof() else "✗未熟练"
            self.atk_lbl.config(
                text=f"攻击 {mod_str(c.attack_bonus())} · 伤害 "
                     f"{c.damage_dice()}{mod_str(c.damage_bonus())} {c.damage_type()}"
                     f" · {prof}")
        else:
            self.atk_lbl.config(text="未装备武器")
        if c.fighting_style in FIGHTING_STYLES:
            nm, note, _ = FIGHTING_STYLES[c.fighting_style]
            self.style_cb.set(nm)
            self.style_note.config(text=note)
        else:
            self.style_cb.set("（无）")
            self.style_note.config(text="")
        # 战斗风格是职业特性: 非战士/圣武士/游侠 (或等级不够) 锁死
        if c.can_fighting_style():
            self.style_cb.config(
                state="readonly",
                values=["（无）"] + [v[0] for v in FIGHTING_STYLES.values()])
        else:
            need = c.style_level_need()
            why = (f"仅战士(1级)/圣武士(2级)/游侠(2级) 拥有"
                   if need is None else f"{need} 级起解锁")
            self.style_cb.config(state="disabled",
                                 values=["（本职业没有战斗风格）"])
            self.style_cb.set("（本职业没有战斗风格）")
            self.style_note.config(text=why)
        for iid, v in self.item_vars.items():
            v.set(iid in c.items)
        self.bonus_text.config(state="normal")
        self.bonus_text.delete("1.0", "end")
        bonus_lines = c.bonus_breakdown()
        ac, ac_notes = c.ac_breakdown()
        self.bonus_text.insert("1.0", "\n".join(
            [f"AC {ac} = " + " + ".join(ac_notes),
             f"先攻 {mod_str(c.initiative())} · 速度 {c.speed()} 尺 · "
             f"HP {c.hp_max()}",
             f"负重上限 {c.carry_capacity()[0]} 磅 "
             f"(推/拉/举 {c.carry_capacity()[1]} 磅) · "
             f"生命骰 d{c.hit_die()} {c.hit_dice_left()}/{c.hit_dice_max()}"]
            + ([""] + ["• " + x for x in bonus_lines] if bonus_lines
               else ["", "（当前无额外加成来源）"])))
        self.bonus_text.config(state="disabled")
        self._spell_refresh()

        # 专长 / 武器专精
        self.feat_list.delete(0, "end")
        for i, ft in enumerate(self._feat_names()):
            self.feat_list.insert("end", self._feat_display(ft, i))
        self.mastery_list.delete(0, "end")
        for wname in c.weapon_mastery:
            for w in WEAPONS:
                if w[0] == wname:
                    extra = (f" · DC {c.mastery_dc(wname)}"
                             if w[3] in ("Topple", "Push") else "")
                    self.mastery_list.insert(
                        "end", f"{wname} · {w[2]} · {mastery_cn(w[3])}{extra}")
                    break
        # 种族特性 / 背景
        lines = [f"【{sp['name']}】 体型 {size_cn(sp['size'])} · "
                 f"速度 {sp.get('speed', 30)} 尺"]
        lines += ["• " + t for t in sp["traits"]]
        lines += ["", f"【背景·{bg['name']}】 起源专长: {feat_cn(bg['origin_feat'])}",
                  f"专长效果: {feat_desc(bg['origin_feat']).split(': ', 1)[-1]}"]
        lines += ["", "【熟练项】"] + ["• " + x for x in c.proficiency_report()]
        self.trait_text.config(state="normal")
        self.trait_text.delete("1.0", "end")
        self.trait_text.insert("1.0", "\n".join(lines))
        self.trait_text.config(state="disabled")
        self._render_class_tab()

        # 语言 / 装备 / 备注
        self.lang_entry.delete(0, "end")
        self.lang_entry.insert(0, c.languages)
        if self.eq_text.get("1.0", "end").strip() != c.equipment.strip():
            self.eq_text.delete("1.0", "end")
            self.eq_text.insert("1.0", c.equipment)
        if self.note_text.get("1.0", "end").strip() != c.notes.strip():
            self.note_text.delete("1.0", "end")
            self.note_text.insert("1.0", c.notes)

        # 状态 / 力竭
        for cond, v in self.cond_vars.items():
            v.set(cond.replace("(另计)", "") in c.conditions)
        self.exh_var.set(c.exhaustion)
        self._exh_warn_text()
        self.death_lbl.config(
            text=f"✓{c.death_success} ✗{c.death_fail}",
            foreground=("#e05c4d" if c.is_dying else DIM))
        conc = c.r.spell(c.concentration) if c.concentration else None
        self.conc_lbl.config(
            text=(f"专注: {conc['name']} (体质 {mod_str(c.save_mod('CON'))})"
                  if conc else "专注: 无"))
        self._status()

    def _feat_names(self):
        """原始专长名列表 (英文键), 显示时用 feat_cn 美化"""
        c = self.char
        names = []
        for asi in c.asi_history:
            if asi.get("type") == "feat":
                names.append(asi["name"])
        names += c.feats
        bg = c.r.bg(c.background_id)
        names.insert(0, bg["origin_feat"])
        return names

    def _feat_display(self, raw, idx):
        prefix = "[背景] " if idx == 0 else ""
        return prefix + feat_cn(raw)

    # ---- 职业页: 资源 / 特性 / 子职 ----

    def _render_class_tab(self):
        c = self.char
        if not c or not hasattr(self, "class_body"):
            return
        for w in self.class_body.winfo_children():
            w.destroy()
        body = self.class_body
        cls = c.cls()

        # ===== 1. 资源池 =====
        res = c.resources()
        hdr = ttk.Frame(body)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="职业资源", style="H2.TLabel").pack(side="left")
        ttk.Button(hdr, text="全部回满", style="Mini.TButton",
                   command=lambda: self._res_act(None, "full")
                   ).pack(side="right")
        ttk.Button(hdr, text="短休", style="Mini.TButton",
                   command=self.short_rest).pack(side="right", padx=4)
        ttk.Button(hdr, text="长休", style="Mini.TButton",
                   command=self.long_rest).pack(side="right")
        if not res:
            ttk.Label(body, text=f"{cls['name']} 没有需要逐次记录的资源池"
                                "（该职业靠法术位与特性本身运转）。",
                      style="Dim.TLabel").pack(anchor="w", pady=2)
        # 生命骰 (短休回血用; 2024 长休全回)
        hd = ttk.Frame(body)
        hd.pack(fill="x", pady=(3, 0))
        ttk.Label(hd, text=f"生命骰 d{c.hit_die()}　剩余 "
                           f"{c.hit_dice_left()}/{c.hit_dice_max()}",
                  foreground=GOLD2).pack(side="left")
        ttk.Button(hd, text="花 1 颗回血", style="Mini.TButton",
                   command=lambda: self._spend_hd(1)
                   ).pack(side="left", padx=6)
        if c.class_id == "barbarian":
            rv = tk.BooleanVar(value=c.raging)
            ttk.Checkbutton(hd, text=f"狂暴中 (伤害 +{c.rage_damage()})",
                            variable=rv,
                            command=lambda v=rv: self._toggle_rage(v)
                            ).pack(side="left", padx=8)
        if c.class_id == "rogue":
            ttk.Checkbutton(hd, text=f"含偷袭 (+{c.sneak_dice()}d6)",
                            variable=self.sneak_var
                            ).pack(side="left", padx=8)
        dice = c.class_dice_text()
        if dice:
            ttk.Label(body, text="关键数值: " + dice, foreground=GOLD2,
                      wraplength=540, justify="left").pack(anchor="w", pady=(2, 2))
        for r in res:
            card = ttk.Frame(body, style="Card.TFrame", padding=8)
            card.pack(fill="x", pady=3)
            top = ttk.Frame(card, style="Card.TFrame")
            top.pack(fill="x")
            nm = f"{r['icon']} {r['name']}".strip()
            ttk.Label(top, text=nm, style="Card.TLabel",
                      font=(UI_FONT, 10, "bold")).pack(side="left")
            txt = f"{r['left']} / {r['max']}"
            if r["die"]:
                txt += f"   d{r['die']}"
            ttk.Label(top, text=txt, style="Card.TLabel", foreground=GOLD2,
                      font=(UI_FONT, 12, "bold")).pack(side="right")
            bar = ttk.Frame(card, style="Card.TFrame")
            bar.pack(fill="x", pady=(4, 0))
            for label, act, n in (("用 1", "spend", 1), ("回 1", "restore", 1)):
                ttk.Button(bar, text=label, width=5, style="Mini.TButton",
                           command=lambda rid=r["id"], a=act, k=n:
                           self._res_act(rid, a, k)).pack(side="left", padx=2)
            if r["max"] >= 10:      # 圣疗池这类大池子, 一次 5 点更常用
                ttk.Button(bar, text="用 5", width=5, style="Mini.TButton",
                           command=lambda rid=r["id"]:
                           self._res_act(rid, "spend", 5)).pack(side="left", padx=2)
            ttk.Button(bar, text="回满", width=5, style="Mini.TButton",
                       command=lambda rid=r["id"]:
                       self._res_act(rid, "full")).pack(side="left", padx=2)
            ttk.Label(bar, text=self._reset_text(r), style="Card.TLabel",
                      foreground=DIM).pack(side="right")
            ttk.Label(card, text=r["note"], style="Card.TLabel",
                      foreground=DIM, wraplength=520, justify="left"
                      ).pack(anchor="w", pady=(4, 0))

        # ===== 2. 子职 =====
        sf = ttk.Frame(body)
        sf.pack(fill="x", pady=(10, 0))
        info = c.r.sub_info(c.subclass) if c.subclass else None
        title = (f"子职 · {subclass_cn(c.subclass)}" if c.subclass
                 else "子职（3 级选择）")
        ttk.Label(sf, text=title, style="H2.TLabel").pack(anchor="w")
        if info:
            ttk.Label(sf, text=info["summary"], foreground=PURPLE,
                      wraplength=560, justify="left").pack(anchor="w")
            self._feature_rows(sf, c.subclass_features())
        else:
            hint = ("升级到 3 级时会弹出子职选择；下面是本职业 4 个方向，"
                    "先了解各自定位再决定。" if c.level < 3
                    else "已到 3 级但还没选子职 —— 下次升级时会让你选。")
            ttk.Label(sf, text=hint, style="Dim.TLabel", wraplength=560,
                      justify="left").pack(anchor="w")
            for en, cn, summary in c.r.sub_options(c.class_id):
                row = ttk.Frame(sf)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text="• " + cn, foreground=GOLD2).pack(anchor="w")
                if summary:
                    ttk.Label(row, text="   " + summary, style="Dim.TLabel",
                              wraplength=540, justify="left").pack(anchor="w")

        # ===== 3. 职业特性 =====
        cf = ttk.Frame(body)
        cf.pack(fill="x", pady=(10, 0))
        ttk.Label(cf, text=f"{cls['name']} 职业特性", style="H2.TLabel"
                  ).pack(anchor="w")
        self._feature_rows(cf, c.class_features())

    def _feature_rows(self, parent, rows):
        for lv, name, desc, unlocked in rows:
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=1)
            tag = f"L{lv}"
            head = f"{'●' if unlocked else '○'} {tag}  {name}"
            ttk.Label(row, text=head, foreground=(GOLD2 if unlocked else DIM),
                      font=(UI_FONT, 10, "bold" if unlocked else "normal")
                      ).pack(anchor="w")
            if desc:
                ttk.Label(row, text="     " + desc, style="Dim.TLabel",
                          wraplength=540, justify="left").pack(anchor="w")

    def _spend_hd(self, n=1):
        """花生命骰回血 (短休核心动作)"""
        c = self.char
        if not c:
            return
        if c.hit_dice_left() <= 0:
            messagebox.showinfo("提示", "生命骰已用尽，长休后恢复。", parent=self)
            return
        used, heal, detail = c.spend_hit_dice(n)
        if used:
            self.refresh()
            self._log_roll(f"🎲 花 {used} 颗生命骰: {'、'.join(detail)} "
                           f"→ 回复 {heal} HP (HP {c.hp_current}/{c.hp_max()})")

    def _toggle_rage(self, var):
        c = self.char
        if not c:
            return
        c.raging = bool(var.get())
        if c.raging:
            if c.concentration:
                c.concentration = None
            self._log_roll(f"🔥 进入狂暴: 伤害 +{c.rage_damage()} · "
                           "物理伤害抗性 · 力量检定/豁免优势 · 无法专注")
        else:
            self._log_roll("◯ 结束狂暴")
        self.refresh()

    @staticmethod
    def _reset_text(r):
        short = {0: "短休不回", 1: "短休回 1", "all": "短休全回"}
        s = short.get(r.get("short"), "")
        if r.get("short_after_level"):
            s += f"（{r['short_after_level']} 级起全回）"
        return f"{s} · 长休全回"

    def _res_act(self, rid, act, n=1):
        c = self.char
        if not c:
            return
        pos = self.class_scroll.canvas.yview()[0]
        if act == "full":
            if rid is None:
                c.res_used = {}
            else:
                c.res_spend(rid, -999)
        elif act == "spend":
            c.res_spend(rid, n)
        else:
            c.res_spend(rid, -n)
        self._render_class_tab()
        self.class_scroll.canvas.yview_moveto(pos)
        self._status()

    def _on_feat_select(self, _e=None):
        sel = self.feat_list.curselection()
        if not sel:
            return
        names = self._feat_names()
        if sel[0] < len(names):
            self.feat_info.config(text=feat_desc(names[sel[0]]))

    def _status(self):
        c = self.char
        if not c:
            return
        slots = c.spell_slots()
        sl = ", ".join(
            f"{lv}环 {slots[lv] - c.spell_slots_used.get(lv, 0)}/{slots[lv]}"
            for lv in sorted(slots)) or "无施法"
        self.status.config(
            text=f"{c.name} · {c.cls()['name']} {c.level}级 · "
                 f"HP {c.hp_current}/{c.hp_max()} · AC {c.ac()} · "
                 f"熟练{mod_str(c.pb())} · 法术位: {sl}"
                 + (f" · ☠ 濒死 ✗{c.death_fail}/3 ✓{c.death_success}/3"
                    if c.is_dying else ""))

    # ---- 掷骰 (结果进日志, 不弹窗) ----

    def _log_roll(self, text):
        self.roll_log.insert(0, text)
        if self.roll_log.size() > 60:
            self.roll_log.delete(60, "end")
        self.status.config(text="🎲 " + text)

    def _d20_log(self, label, mod):
        c = self.char
        raw = random.randint(1, 20)
        total = raw + c.d20_mod_total(mod)
        ex = f" 力竭-{2 * c.exhaustion}" if c.exhaustion else ""
        crit = " 🎯大成功!" if raw == 20 else (" 💀大失败" if raw == 1 else "")
        self._log_roll(
            f"{label}: d20={raw} {mod_str(mod)}{ex} ⇒ {total}{crit}")

    def _roll_check(self, ab):
        if not self.char:
            return
        self._d20_log(f"{ABILITY_CN[ab]}({ab})检定",
                      ability_mod(self.char.score(ab))
                      + self.char.check_bonus())

    def _roll_save(self, ab):
        if not self.char:
            return
        self._d20_log(f"{ABILITY_CN[ab]}豁免", self.char.save_mod(ab))

    def _roll_init(self):
        if not self.char:
            return
        self._d20_log("先攻", self.char.initiative())

    def _roll_skill(self, sid):
        if not self.char:
            return
        sk = self.rules.skill_by_id[sid]
        self._d20_log(f"{sk['name']}检定", self.char.skill_mod(sid))

    def _quick_die(self, n):
        self._log_roll(f"d{n} ⇒ {random.randint(1, n)}")

    # ---- 事件处理 ----

    def _score_edited(self):
        """手动微调属性 — 2024 上限 20, 只有魔法物品的「设定值」能超过"""
        c = self.char
        if not c:
            return
        capped = False
        for a in ABILITIES:
            try:
                val = self.ab_entries[a].get()
            except tk.TclError:
                continue
            if val > 20:
                val = 20
                capped = True
            delta = val - c.score(a)
            if delta:
                c.base_scores[a] = max(1, min(20, c.base_scores[a] + delta))
        self.refresh()
        if capped:
            messagebox.showinfo(
                "属性上限",
                "2024 规则：属性值上限为 20（基础值 + 背景 + ASI 合计）。\n"
                "只有魔法物品的「设定值」（如力量腰带 21）能超过 20。",
                parent=self)

    def _hp_add(self, n):
        if not self.char:
            return
        c = self.char
        c.hp_current = max(0, min(c.hp_max(), c.hp_current + n))
        self.refresh()
        if n < 0:
            self._log_roll(f"受到伤害 {abs(n)} → HP {c.hp_current}/{c.hp_max()}")
        elif n > 0:
            self._log_roll(f"恢复生命 {n} → HP {c.hp_current}/{c.hp_max()}")

    def _hp_temp_changed(self):
        if not self.char:
            return
        try:
            self.char.hp_temp = max(0, self.hp_temp_var.get())
        except tk.TclError:
            pass

    def _skill_toggled(self, sid):
        c = self.char
        if not c:
            return
        sk = self.rules.skill_by_id[sid]["name"]
        bg, auto = c.bg_skills(), set(c.auto_skills())
        pool = c.class_skill_pool()
        on = self.skill_vars[sid].get()
        # 背景/种族给的熟练不能在这里取消
        if sid in bg or sid in auto:
            self.skill_vars[sid].set(True)
            messagebox.showinfo(
                "固定熟练", f"「{sk}」来自背景/种族，不能在这里取消。", parent=self)
            return
        # 只能增删本职业技能列表里的项
        if sid not in pool:
            self.skill_vars[sid].set(sid in c.skill_prof)
            messagebox.showinfo(
                "不在职业列表",
                f"「{sk}」不在 {c.cls()['name']} 的技能列表里。\n"
                "专长/子职给的熟练会直接计入，但不能在这里手动增删。", parent=self)
            return
        if on:
            if c.class_skill_picks() >= c.skill_quota():
                self.skill_vars[sid].set(False)
                messagebox.showwarning(
                    "已达上限",
                    f"{c.cls()['name']} 只能选 {c.skill_quota()} 项技能"
                    f"（当前已选 {c.class_skill_picks()} 项）。\n"
                    "想换别的请先取消一项。", parent=self)
                return
            c.skill_prof.add(sid)
        else:
            c.skill_prof.discard(sid)
            c.expertise.discard(sid)
        self.refresh()

    def _toggle_expertise(self, sid):
        c = self.char
        if not c:
            return
        allow = c.expertise_allowance()
        if allow <= 0:
            messagebox.showinfo(
                "专精",
                f"{c.cls()['name']} 没有「专精 Expertise」特性。\n"
                "（游荡者 1 级、吟游诗人 2 级、游侠 2 级才有）", parent=self)
            return
        if sid in c.expertise:
            c.expertise.discard(sid)
        elif sid not in c.skill_prof:
            messagebox.showinfo("提示", "只有已熟练的技能才能设为专精 (Expertise)",
                                parent=self)
            return
        elif len(c.expertise) >= allow:
            messagebox.showwarning(
                "专精已满",
                f"当前等级最多 {allow} 项专精（随等级提升："
                f"游荡者 6 级 +2、吟游诗人 9 级 +2、游侠 9 级 +2）。",
                parent=self)
            return
        else:
            c.expertise.add(sid)
        self.refresh()

    def _armor_changed(self):
        c = self.char
        if not c:
            return
        c.armor_index = self.armor_cb.current()
        c.shield = self.shield_var.get()
        self.refresh()

    def _tough_changed(self):
        c = self.char
        if not c:
            return
        c.tough_feat = self.tough_var.get()
        self.refresh()

    def _slot_spend(self, lv):
        c = self.char
        if not c:
            return
        mx = c.spell_slots().get(lv, 0)
        used = c.spell_slots_used.get(lv, 0)
        if used >= mx:
            messagebox.showwarning("提示", f"{lv} 环法术位已用尽 (长休恢复)",
                                   parent=self)
            return
        c.spell_slots_used[lv] = used + 1
        self._log_roll(f"施放法术 → {lv}环位 剩 {mx - used - 1}/{mx}")
        self.refresh()

    def _slot_restore(self, lv):
        c = self.char
        if not c:
            return
        used = c.spell_slots_used.get(lv, 0)
        if used > 0:
            c.spell_slots_used[lv] = used - 1
            self.refresh()

    def _cond_toggled(self, cond):
        c = self.char
        if not c:
            return
        key = cond.replace("(另计)", "")
        if self.cond_vars[cond].get():
            c.conditions.add(key)
        else:
            c.conditions.discard(key)
        self._status()

    def _ability_hint(self, ab):
        self.ab_hint.config(
            text=f"{ABILITY_CN[ab]} ({ab}): {ABILITY_DESC.get(ab, '')}",
            foreground=GOLD2)

    def _skill_hover(self, sid):
        sk = self.rules.skill_by_id[sid]
        c = self.char
        extra = ""
        if c:
            extra = f" · 当前 {mod_str(c.skill_mod(sid))}"
            if sid in c.expertise:
                extra += " (专精 ×2)"
            elif sid in c.skill_prof:
                extra += " (熟练)"
        self.skill_hint.config(
            text=f"{sk['name']} ({ABILITY_CN[sk['ability']]}) —— "
                 f"{SKILL_DESC.get(sid, '')}{extra}",
            foreground=GOLD2)

    def _cond_hint(self, cond):
        self.cond_hint.config(
            text=f"{cond}: {CONDITION_DESC.get(cond, '')}", foreground=GOLD2)

    def _exh_warn_text(self):
        c = self.char
        if not c or c.exhaustion == 0:
            self.exh_warn.config(text="")
        elif c.exhaustion >= 6:
            self.exh_warn.config(text="☠ 力竭 6 级 —— 角色死亡!")
        else:
            self.exh_warn.config(
                text=f"当前惩罚: d20 检定 -{2 * c.exhaustion}, "
                     f"速度 -{5 * c.exhaustion} 尺")

    def _exh_changed(self):
        c = self.char
        if not c:
            return
        c.exhaustion = max(0, min(6, self.exh_var.get()))
        self._exh_warn_text()
        if c.exhaustion >= 6:
            messagebox.showwarning("警告", "力竭 6 级 —— 角色死亡!", parent=self)
        self._status()

    def _death_save(self):
        """死亡豁免 (2024): 10+ 成功, 9- 失败; 20 直接回 1 HP; 1 记 2 次失败"""
        c = self.char
        if not c:
            return
        if not c.is_dying:
            messagebox.showinfo("提示", "HP 大于 0 时不需要死亡豁免。", parent=self)
            return
        raw = random.randint(1, 20)
        if raw == 20:
            c.hp_current = 1
            c.death_success = c.death_fail = 0
            msg = "d20=20 → 恢复 1 HP，立刻脱离濒死"
        elif raw == 1:
            c.death_fail = min(3, c.death_fail + 2)
            msg = "d20=1 → 记 2 次失败"
        elif raw >= 10:
            c.death_success = min(3, c.death_success + 1)
            msg = f"d20={raw} → 成功 +1"
        else:
            c.death_fail = min(3, c.death_fail + 1)
            msg = f"d20={raw} → 失败 +1"
        if c.death_success >= 3:
            msg += " · 已稳定（昏迷但不再恶化）"
        if c.death_fail >= 3:
            msg += " · ☠ 三次失败，角色死亡"
        self.refresh()
        self._log_roll("💀 死亡豁免: " + msg)

    def _death_reset(self):
        c = self.char
        if not c:
            return
        c.death_success = c.death_fail = 0
        self.refresh()
        self._log_roll("死亡豁免计数已重置")

    def _conc_check(self):
        """受伤后的专注检定: DC = max(10, 伤害/2), 掷体质豁免"""
        c = self.char
        if not c:
            return
        if not c.concentration:
            messagebox.showinfo("提示", "当前没有正在专注的法术。", parent=self)
            return
        dmg = askinteger("专注检定", "受到的伤害值（用于算 DC）:",
                         parent=self, minvalue=0, maxvalue=9999,
                         initialvalue=10)
        if dmg is None:
            return
        dc = c.concentration_dc(dmg)
        mod = c.save_mod("CON")
        raw = random.randint(1, 20)
        tot = raw + c.d20_mod_total(mod)
        ok = raw == 20 or (raw != 1 and tot >= dc)
        s = c.r.spell(c.concentration)
        if not ok:
            c.concentration = None
        self.refresh()
        self._log_roll(
            f"🧠 专注检定 (DC {dc}): d20={raw} {mod_str(mod)} ⇒ {tot} "
            f"{'保持' if ok else '中断'} · {s['name'] if s else ''}")

    def _xp_changed(self):
        c = self.char
        if not c:
            return
        try:
            c.xp = max(0, self.xp_var.get())
        except tk.TclError:
            return
        if c.level >= 20:
            self.xp_hint.config(text="已满级 (20)")
            self.xp_bar.config(maximum=1, value=1)
            return
        base = self._xp_th[c.level]
        nxt = self._xp_th[c.level + 1]
        span = max(1, nxt - base)
        self.xp_bar.config(maximum=span,
                           value=max(0, min(span, c.xp - base)))
        if c.xp >= nxt:
            self.xp_hint.config(
                text=f"⚑ 可升至 {c.level + 1} 级! → 点工具栏「⬆ 升级」")
        else:
            self.xp_hint.config(text=f"(下一级 {nxt} XP, 还差 {nxt - c.xp})")

    def _add_feat(self):
        c = self.char
        if not c:
            return
        from tkinter.simpledialog import askstring
        name = askstring("添加专长", "专长名称:", parent=self)
        if name and name.strip():
            c.feats.append(name.strip())
            if "tough" in name.lower() or "坚忍" in name or "坚韧" in name:
                c.tough_feat = True
            self.refresh()

    def _del_feat(self):
        c = self.char
        if not c:
            return
        sel = self.feat_list.curselection()
        if not sel:
            return
        names = self._feat_names()
        name = names[sel[0]] if sel[0] < len(names) else None
        if name in c.feats:
            c.feats.remove(name)
        self.refresh()

    def _edit_mastery(self):
        c = self.char
        if not c:
            return
        pool = Rules.class_mastery_pool(c.cls())
        n = c.mastery_count()
        if n == 0:
            messagebox.showinfo(
                "提示",
                f"{c.cls()['name']} 没有「武器专精 Weapon Mastery」特性，不能选。\n"
                "（野蛮人/战士/圣武士/游侠/游荡者才有；也可用 Weapon Master 专长）",
                parent=self)
            return
        win = tk.Toplevel(self)
        win.title(f"编辑武器专精 (选 {n} 件, 长休可换)")
        win.geometry("560x520")
        win.transient(self)
        win.configure(bg=BG)
        try:
            win.grab_set()
        except tk.TclError:
            pass
        f = ttk.Frame(win, padding=10)
        f.pack(fill="both", expand=True)
        vars_ = {}
        for i, (wname, cat, dmg, mst) in enumerate(pool):
            v = tk.BooleanVar(value=wname in c.weapon_mastery)
            vars_[wname] = v
            ttk.Checkbutton(f, text=f"{wname} · {dmg} · {mastery_cn(mst)}",
                            variable=v).grid(row=i // 2, column=i % 2,
                                             sticky="w", padx=8, pady=2)

        def ok():
            chosen = [w for w, v in vars_.items() if v.get()]
            if len(chosen) != n:
                messagebox.showwarning(
                    "提示", f"须恰好选择 {n} 件 (已选 {len(chosen)})", parent=win)
                return
            c.weapon_mastery = chosen
            win.destroy()
            self.refresh()

        ttk.Button(f, text="确认", style="Gold.TButton",
                   command=ok).grid(columnspan=2, pady=8)

    # ---- 装备 / 攻击 / 魔法物品 ----

    WEP_SUFFIX = (" ✓熟练", " ✗未熟练")

    def _weapon_label(self, name):
        """下拉里显示的武器名 + 熟练标记"""
        c = self.char
        if not c or not name:
            return "（未装备）"
        return name + (" ✓熟练" if c.has_weapon_prof(name) else " ✗未熟练")

    @classmethod
    def _weapon_strip(cls, label):
        for suf in cls.WEP_SUFFIX:
            if label.endswith(suf):
                return label[:-len(suf)]
        return label

    def _weapon_changed(self):
        c = self.char
        if not c:
            return
        name = self._weapon_strip(self.weapon_cb.get()).strip()
        if name in {w[0] for w in WEAPONS}:
            if not c.has_weapon_prof(name):     # 未熟练: 允许但明确警告
                messagebox.showwarning(
                    "未熟练武器",
                    f"{c.cls()['name']} 不熟练「{name}」。\n"
                    "可以装备，但攻击检定不加熟练加值，"
                    "部分特性（如偷袭）也可能无法使用。", parent=self)
            c.weapon = name
        else:
            c.weapon = ""
        try:
            c.weapon_magic = max(0, min(3, int(self.wmagic_var.get())))
        except (tk.TclError, ValueError):
            pass
        self.refresh()

    def _style_changed(self):
        c = self.char
        if not c:
            return
        if not c.can_fighting_style():
            c.fighting_style = None
            self.refresh()
            messagebox.showinfo(
                "战斗风格",
                "战斗风格是战士(1级)/圣武士(2级)/游侠(2级) 的职业特性，"
                f"{c.cls()['name']} 不能选择。", parent=self)
            return
        txt = self.style_cb.get()
        key = next((k for k, v in FIGHTING_STYLES.items() if v[0] == txt), None)
        if key is None and c.fighting_style:
            c.fighting_style = None          # 选「（无）」= 取消
        elif key:
            c.fighting_style = key
        self.refresh()

    def _item_changed(self, iid):
        c = self.char
        if not c:
            return
        if self.item_vars[iid].get():
            if iid not in c.items:
                # 同调上限 3 件 (2024): 超出的勾选直接回退
                if len(c.items) >= c.attunement_cap():
                    self.item_vars[iid].set(False)
                    it = ITEMS_BY_ID.get(iid, {})
                    messagebox.showwarning(
                        "同调已满",
                        f"同时最多同调 {c.attunement_cap()} 件魔法物品"
                        f"（已同调 {len(c.items)} 件）。\n"
                        f"「{it.get('name', iid)}」需要同调，请先取消一件。",
                        parent=self)
                    return
                c.items.append(iid)
        elif iid in c.items:
            c.items.remove(iid)
        self.refresh()

    def _item_hint(self, it):
        self.item_hint.config(text=f"{it['name']} —— {it['note']}",
                              foreground=GOLD2)

    def _attack_roll(self):
        c = self.char
        if not c or not c.weapon:
            messagebox.showinfo("提示", "先在「装备·加成」页选择武器", parent=self)
            return
        n = c.attacks_per_action()
        if n <= 1:
            self._d20_log(f"攻击·{c.weapon}", c.attack_bonus())
            return
        # 额外攻击: 一次投 n 个 d20, 分别结算命中
        mod = c.attack_bonus()
        parts, crit = [], 0
        for i in range(n):
            raw = random.randint(1, 20)
            tot = raw + c.d20_mod_total(mod)
            crit += 1 if raw == 20 else 0
            parts.append(f"#{i + 1} d20={raw}⇒{tot}")
        self._log_roll(
            f"攻击·{c.weapon} ×{n} 次 (命中 {mod_str(mod)}): "
            + " | ".join(parts) + (f" · 🎯暴击 {crit}" if crit else ""))

    def _damage_roll(self):
        c = self.char
        if not c or not c.weapon:
            return
        dice = c.damage_dice()
        bonus = c.damage_bonus()
        expr = f"{dice}{mod_str(bonus)}" if bonus else dice
        total, detail = roll_dice(expr)
        extra = ""
        if c.class_id == "rogue" and self.sneak_var.get():
            n = c.sneak_dice()
            s_total, s_detail = roll_dice(f"{n}d6")
            total += s_total
            extra = f" + 偷袭 {s_detail}"
        self._log_roll(f"⚔ 伤害·{c.weapon}: {detail}{extra} "
                       f"= {total} {c.damage_type()}")

    # ---- 法术 ----

    def _spell_rows(self):
        c = self.char
        rows = []
        if not c:
            return rows
        for key in ("cantrips", "prepared"):
            for sid in (c.spells or {}).get(key, []):
                s = c.r.spell(sid)
                if s:
                    rows.append(dict(s, _src="职业"))
        for unlock, sid in c.species_spells():       # 种族自带, 不占职业位
            s = c.r.spell(sid)
            if s:
                rows.append(dict(s, _src="种族"))
        rows.sort(key=lambda s: (s["level"], s["name"]))
        self._spell_cache = rows
        return rows

    def _spell_refresh(self):
        c = self.char
        if not c or not hasattr(self, "spell_list"):
            return
        prev = self._selected_spell()
        prev_id = prev["id"] if prev else None
        rows = self._spell_rows()
        self.spell_list.delete(0, "end")
        keep = None
        for i, s in enumerate(rows):
            tag = "戏法" if s["level"] == 0 else f"{s['level']}环"
            src = "[种族] " if s.get("_src") == "种族" else ""
            mark = "  ◉专注中" if c.concentration == s["id"] else ""
            self.spell_list.insert("end", f"[{tag}] {src}{s['name']}{mark}")
            if s["id"] == prev_id:
                keep = i
        if keep is not None:          # 刷新后保持原选中项, 便于连续施法
            self.spell_list.selection_set(keep)
            self.spell_list.see(keep)
        learned = {s["id"] for s in rows}
        maxlv = c.max_spell_level()
        opts = [s for s in c.r.class_spells(c.class_id or "")
                if s["id"] not in learned
                and (s["level"] == 0 or s["level"] <= max(maxlv, 1))]
        self._spell_opts = opts
        self.spell_add_cb["values"] = [f"{s['name']} {s['name_en']}"
                                       for s in opts]
        # 配额提示: 戏法硬上限 / 准备法术参考值
        if hasattr(self, "spell_quota_lbl"):
            n_c = len(c.spells.get("cantrips") or [])
            n_p = len(c.spells.get("prepared") or [])
            self.spell_quota_lbl.config(
                text=f"戏法 {n_c}/{c.cantrip_cap()}　"
                     f"法术 {n_p}/{c.prepared_hint()}（参考值）　"
                     f"最高可用 {maxlv} 环")
        if not rows:
            self._spell_detail_set(
                "本角色尚无法术。用上方下拉框选择本职业法术，点「＋ 学习」加入。"
                "（法师/牧师等准备施法者也可按 DM 允许随时调整）")

    def _spell_detail_set(self, text):
        self.spell_detail.config(state="normal")
        self.spell_detail.delete("1.0", "end")
        self.spell_detail.insert("1.0", text)
        self.spell_detail.config(state="disabled")

    def _selected_spell(self):
        sel = self.spell_list.curselection()
        rows = getattr(self, "_spell_cache", [])
        if sel and sel[0] < len(rows):
            return rows[sel[0]]
        return None

    def _spell_show(self, _e=None):
        s = self._selected_spell()
        txt = spell_detail(s)
        c = self.char
        if s and c and c.spell_dc() is not None:
            txt += f"\n\n你的法术豁免 DC {c.spell_dc()} · 法术攻击 {mod_str(c.spell_attack())}"
        self._spell_detail_set(txt)

    def _spell_add(self):
        c = self.char
        if not c:
            return
        idx = self.spell_add_cb.current()
        if idx < 0 or idx >= len(getattr(self, "_spell_opts", [])):
            return
        s = self._spell_opts[idx]
        key = "cantrips" if s["level"] == 0 else "prepared"
        cur = list(c.spells.get(key) or [])
        # 戏法: 数量由职业固定, 不能超
        if key == "cantrips" and len(cur) >= c.cantrip_cap():
            messagebox.showwarning(
                "戏法已满",
                f"{c.cls()['name']} 目前只能掌握 {c.cantrip_cap()} 个戏法"
                f"（已学 {len(cur)} 个）。\n4 级与 10 级各会再 +1。", parent=self)
            return
        # 法术环级不能超过你能施放的最高环
        if s["level"] > max(c.max_spell_level(), 1):
            messagebox.showwarning(
                "环级不足",
                f"你目前最高只能施放 {c.max_spell_level()} 环法术，"
                f"还不能学习 {s['name']}（{s['level']} 环）。", parent=self)
            return
        # 准备法术: 超出参考值需确认（各职业表为准）
        if key == "prepared" and len(cur) >= c.prepared_hint():
            if not messagebox.askyesno(
                    "超出参考数量",
                    f"已准备 {len(cur)} 个法术，参考上限为 "
                    f"{c.prepared_hint()}（等级 + 施法属性调整值）。\n"
                    "若你的职业表允许更多（或 DM 允许），可继续添加。\n\n"
                    "仍然学习吗？", parent=self):
                return
        if s["id"] not in cur:
            c.spells.setdefault(key, []).append(s["id"])
        self.refresh()
        self._spell_detail_set(spell_detail(s))

    def _spell_del(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        if s.get("_src") == "种族":
            messagebox.showinfo(
                "提示", f"{s['name']} 是种族自带法术，不能移除。\n"
                        f"（{self.char.lineage_cn() or '种族'}特性，始终备好）",
                parent=self)
            return
        for key in ("cantrips", "prepared"):
            if s["id"] in c.spells.get(key, []):
                c.spells[key].remove(s["id"])
        if c.concentration == s["id"]:
            c.concentration = None
        self.refresh()

    def _spell_cast(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        # 2024: 穿着未熟练的护甲/盾牌时无法施法
        if not c.has_armor_prof() or (c.shield and not c.has_shield_prof()):
            messagebox.showwarning(
                "提示", "穿着未熟练的护甲或盾牌时无法施法（2024 规则）。\n"
                        "请在「装备·加成」页更换护甲或卸下盾牌。", parent=self)
            return
        if c.condition_blocks_action():
            messagebox.showwarning(
                "提示", "当前状态（失能/麻痹/震慑/昏迷/石化）无法执行动作，"
                        "因此不能施法。", parent=self)
            return
        if c.raging and s.get("concentration"):
            messagebox.showwarning(
                "提示", "狂暴中无法维持专注（2024 规则）。\n"
                        "要施放这个专注法术，请先结束狂暴。", parent=self)
            return
        if s["level"] == 0:
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            tag = "（种族）" if s.get("_src") == "种族" else ""
            self._log_roll(f"✨ 施放戏法{tag} {s['name']}")
            return
        # 种族法术: 每项每长休可免费施放 1 次
        if s.get("_src") == "种族" and s["id"] not in c.race_free_used:
            c.race_free_used.append(s["id"])
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ 种族法术 {s['name']}（免费，1/长休）")
            return
        slots = c.spell_slots()
        avail = [x for x in sorted(slots)
                 if x >= s["level"] and slots[x] - c.spell_slots_used.get(x, 0) > 0]
        if not avail:
            messagebox.showwarning(
                "提示", f"{s['level']} 环及以上已无剩余法术位（长休恢复）",
                parent=self)
            return
        use = avail[0]
        c.spell_slots_used[use] = c.spell_slots_used.get(use, 0) + 1
        if s["concentration"]:
            c.concentration = s["id"]
        self.refresh()
        extra = ""
        sc = s.get("scaling") or {}
        if s["damage"] and str(use) in sc:
            extra = f" · {sc[str(use)]} {s['damage_type']}"
        self._log_roll(f"✨ 施放 {s['name']}（{use} 环位）{extra}")

    def _spell_focus(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        if c.concentration == s["id"]:
            c.concentration = None
            self._log_roll(f"◯ 结束专注: {s['name']}")
        else:
            c.concentration = s["id"]
            self._log_roll(f"◉ 开始专注: {s['name']}")
        self.refresh()

    def _lang_changed(self):
        if self.char:
            self.char.languages = self.lang_entry.get()

    def _notes_changed(self):
        if self.char:
            self.char.equipment = self.eq_text.get("1.0", "end").strip()
            self.char.notes = self.note_text.get("1.0", "end").strip()

    # ---- 工具栏 / 菜单动作 ----

    def new_character(self):
        Wizard(self, self.rules, self.set_character)

    # ---- 存档 (固定目录 + 自动载入) ----

    @staticmethod
    def _safe_name(name):
        bad = '\\/:*?"<>|'
        out = "".join(("_" if ch in bad else ch) for ch in (name or "角色"))
        return out.strip() or "角色"

    def _char_path(self, name=None):
        return os.path.join(CHAR_DIR, self._safe_name(name or self.char.name)
                            + ".json")

    def _remember_last(self, path):
        try:
            os.makedirs(CHAR_DIR, exist_ok=True)
            with open(LAST_PTR, "w", encoding="utf-8") as f:
                json.dump({"file": os.path.basename(path)}, f,
                          ensure_ascii=False)
        except OSError:
            pass

    def _write_char(self, path):
        self._notes_changed()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.char.to_dict(), f, ensure_ascii=False, indent=2)

    def save_character(self):
        """保存到固定目录 characters/ (不弹窗)"""
        if not self.char:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        path = self._char_path()
        try:
            self._write_char(path)
        except OSError as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return
        self._remember_last(path)
        self._log_roll(f"💾 已保存: {os.path.basename(path)}")
        self.status.config(text=f"💾 已保存到 {path}")

    def save_character_as(self):
        """另存为任意路径"""
        if not self.char:
            return
        os.makedirs(CHAR_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".json", initialdir=CHAR_DIR,
            initialfile=f"{self._safe_name(self.char.name)}.json",
            filetypes=[("D&D 5.5e 角色档", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self._write_char(path)
        except OSError as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return
        self._remember_last(path)
        self._log_roll(f"💾 已另存: {path}")

    def _load_path(self, path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        char = Character(self.rules)
        char.load_dict(d)
        self.set_character(char)
        self._remember_last(path)
        self._log_roll(f"📂 已载入: {char.name} ({os.path.basename(path)})")

    def load_character(self):
        os.makedirs(CHAR_DIR, exist_ok=True)
        path = filedialog.askopenfilename(
            parent=self, initialdir=CHAR_DIR,
            filetypes=[("D&D 5.5e 角色档", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self._load_path(path)
        except Exception as e:
            messagebox.showerror("错误", f"载入失败: {e}", parent=self)

    def _auto_start(self):
        """启动时优先读取上次的角色卡, 没有才打开建卡向导"""
        path = None
        try:
            with open(LAST_PTR, encoding="utf-8") as f:
                cand = os.path.join(CHAR_DIR, json.load(f).get("file", ""))
            if os.path.exists(cand):
                path = cand
        except (OSError, ValueError):
            path = None
        if not path and os.path.isdir(CHAR_DIR):
            files = [os.path.join(CHAR_DIR, f) for f in os.listdir(CHAR_DIR)
                     if f.endswith(".json") and not f.startswith("_")]
            if files:
                path = max(files, key=os.path.getmtime)
        if path:
            try:
                self._load_path(path)
                return
            except Exception as e:
                print("自动载入失败:", e)
        self.new_character()

    def open_char_folder(self):
        try:
            os.makedirs(CHAR_DIR, exist_ok=True)
            os.startfile(CHAR_DIR)
        except OSError as e:
            messagebox.showerror("错误", str(e), parent=self)

    def export_character(self):
        if not self.char:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".json",
            initialfile=f"{self.char.name}_export.json")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.char.to_dict(), f, ensure_ascii=False, indent=2)
        self._log_roll(f"⬇ 已导出: {path}")

    def level_up(self):
        c = self.char
        if not c:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        if c.level >= 20:
            messagebox.showinfo("提示", "已到 20 级上限", parent=self)
            return
        dlg = LevelUpDialog(self, c)
        self.wait_window(dlg)
        rec = dlg.result
        if not rec:
            return
        c.level = rec["level"]
        if rec["subclass"]:
            c.subclass = rec["subclass"]
        if rec["asi"]:
            c.asi_history.append(rec["asi"])
        gain = max(1, c.cls()["hit_die"] // 2 + 1 +
                   ability_mod(c.score("CON")))
        c.hp_current += gain
        self.refresh()
        msg = [f"升至 {c.level} 级!",
               f"HP +{gain} (当前 {c.hp_current}/{c.hp_max()})"]
        if rec["subclass"]:
            msg.append(f"子职: {subclass_cn(rec['subclass'])}")
        if rec["boon"]:
            msg.append(f"传奇恩惠: {rec['boon']}")
        self._log_roll(f"⬆ 升级! 现在是 {c.level} 级, HP +{gain}")
        messagebox.showinfo("升级完成", "\n".join(msg), parent=self)

    def long_rest(self):
        c = self.char
        if not c:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        c.spell_slots_used = {}
        c.race_free_used = []          # 种族法术的免费次数随长休恢复
        c.res_reset("long")            # 职业资源全部回满 (狂暴/气/术法点/圣疗池…)
        c.hp_current = c.hp_max()
        c.hit_dice_used = 0            # 2024: 长休恢复全部生命骰
        c.death_success = c.death_fail = 0
        c.raging = False
        if c.exhaustion > 0:
            c.exhaustion -= 1
        self.refresh()
        self._log_roll("🌙 长休: HP 全满 · 法术位/秘契/职业资源全恢复 · "
                       "生命骰全回 · 力竭 -1")
        messagebox.showinfo(
            "长休", "长休结束:\n• HP 全满\n"
                    "• 法术位与秘契法术全部恢复\n"
                    "• 职业资源全部回满 (狂暴/气/术法点/圣疗池…)\n"
                    f"• 生命骰全部恢复 (d{c.hit_die()} ×{c.hit_dice_max()})\n"
                    "• 死亡豁免清零 · 结束狂暴\n• 力竭 -1 级",
            parent=self)

    def short_rest(self):
        c = self.char
        if not c:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        c.res_reset("short")           # 按各资源规则恢复 (恢复 1 次 / 全部)
        c.raging = False
        msg = []
        if c.slots_recharge_short_rest():
            # 契约法术位短休回满；秘契法术 (6–9 环) 只随长休恢复
            arc = set(c.arcanum_levels())
            for lv in list(c.spell_slots_used):
                if lv not in arc:
                    c.spell_slots_used.pop(lv, None)
            msg.append("契约法术位已恢复（秘契法术仍需长休）")
        for r in c.resources():
            if r["short"] == "all":
                msg.append(f"{r['name']} 已全部恢复")
            elif r["short"] == 1:
                msg.append(f"{r['name']} 恢复 1 次")
        # 花生命骰回血 (2024 短休核心)
        left = c.hit_dice_left()
        if left > 0:
            n = askinteger(
                "短休 · 花生命骰",
                f"你有 {left} 颗 d{c.hit_die()} 生命骰（共 {c.hit_dice_max()} 颗）。\n"
                f"每颗恢复 d{c.hit_die()}+体质调整值，花几颗？\n（输入 0 表示不花）",
                parent=self, minvalue=0, maxvalue=left,
                initialvalue=0)
            if n:
                used, heal, detail = c.spend_hit_dice(n)
                msg.append(f"花 {used} 颗生命骰回复 {heal} HP（"
                           + "、".join(detail) + "）")
        else:
            msg.append("生命骰已用尽（长休恢复）")
        self.refresh()
        self._log_roll("☕ 短休: " + ("; ".join(msg) if msg else "无自动恢复项"))
        messagebox.showinfo("短休", "短休结束:\n" +
                            ("\n".join("• " + m for m in msg) if msg
                             else "该职业短休无自动恢复的资源；法术位需长休恢复。"),
                            parent=self)

    def _on_close(self):
        self._notes_changed()
        if self.char is not None and not getattr(self, "_selftest", False):
            try:
                path = self._char_path()
                self._write_char(path)
                self._remember_last(path)
            except OSError:
                pass
        self.destroy()


# ----------------------------------------------------------------------------
# 自检 & 入口
# ----------------------------------------------------------------------------

def run_selftest():
    """无 GUI 冒烟测试: 规则引擎 + 建卡向导端到端 + 升级流程 + 窗体构建"""
    # 弹窗打桩: 自检中不允许出现阻塞式系统对话框
    messagebox.showwarning = lambda *a, **k: None
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None
    messagebox.askyesno = lambda *a, **k: True
    r = Rules()
    assert proficiency_bonus(1) == 2 and proficiency_bonus(5) == 3 \
        and proficiency_bonus(17) == 6 and proficiency_bonus(20) == 6
    assert ability_mod(8) == -1 and ability_mod(10) == 0 and ability_mod(20) == 5

    c = Character(r)
    c.name = "测试"
    c.class_id, c.background_id, c.species_id = "fighter", "soldier", "dwarf"
    c.base_scores = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10,
                     "CHA": 8}
    c.bg_bonus = {"mode": "2+1", "plus2": "STR", "plus1": "CON"}
    c.skill_prof = {"athletics", "perception"}
    assert c.score("STR") == 17 and c.score("CON") == 14
    # 战士1级: 10 + 2(Con) + 矮人1 = 13
    assert c.hp_max() == 13, c.hp_max()
    c.level = 3
    # 3级: 10+2 (1级) + 2*(6+2) (2-3级固定值) + 矮人韧性3 = 31
    assert c.hp_max() == 31, c.hp_max()
    c.level = 1

    m = Character(r)
    m.class_id, m.background_id, m.species_id = "wizard", "sage", "elf"
    m.base_scores = {"STR": 8, "DEX": 14, "CON": 13, "INT": 15, "WIS": 12,
                     "CHA": 10}
    m.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
    assert m.spell_slots() == {1: 2}
    m.level = 5
    assert m.spell_slots() == {1: 4, 2: 3, 3: 2}, m.spell_slots()
    assert m.spell_dc() == 8 + 3 + 3

    w = Character(r)
    w.class_id, w.background_id, w.species_id = "warlock", "charlatan", "tiefling"
    w.base_scores = {"STR": 8, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12,
                     "CHA": 15}
    w.bg_bonus = {"mode": "2+1", "plus2": "CHA", "plus1": "DEX"}
    w.level = 5
    assert w.spell_slots() == {3: 2}, w.spell_slots()
    w.level = 13
    # 11级6环秘契, 13级7环秘契
    assert w.spell_slots() == {5: 3, 6: 1, 7: 1}, w.spell_slots()

    p = Character(r)
    p.class_id = "paladin"
    p.level = 5
    assert p.spell_slots() == {1: 4, 2: 2}, p.spell_slots()

    # 序列化往返
    d = c.to_dict()
    c2 = Character(r)
    c2.load_dict(d)
    assert c2.hp_max() == c.hp_max() and c2.score("STR") == 17

    # ---- GUI 构建 ----
    app = App(selftest=True)
    app.set_character(c)
    app.update()
    app.update_idletasks()

    # ---- 端到端: 建卡向导六步走完 ----
    got = {}
    wiz = Wizard(app, r, lambda ch: got.setdefault("c", ch))
    wiz.withdraw()
    # ① 职业
    wiz.e_name.delete(0, "end")
    wiz.e_name.insert(0, "E2E·矮人战士")
    fname = next(x["name"] for x in r.d["classes"] if x["id"] == "fighter")
    wiz.cb_class.set(fname)
    wiz._show_class()
    assert wiz.data["class_id"] == "fighter"
    wiz.next()
    assert wiz.step == 1, "向导①→② 失败"
    # ② 背景 (+2/+1 分配)
    bname = next(x["name"] for x in r.d["backgrounds"] if x["id"] == "soldier")
    wiz.cb_bg.set(bname)
    wiz._render_bg_ui()
    cand_names = [f"{ABILITY_CN[a]}({a})" for a in wiz._bg_abs]
    wiz.bg_p2.set(cand_names[0])
    wiz.bg_p1.set(cand_names[1])
    wiz.next()
    assert wiz.step == 2, "向导②→③ 失败"
    # ③ 种族
    sname = next(x["name"] for x in r.d["species"] if x["id"] == "dwarf")
    wiz.cb_sp.set(sname)
    wiz._show_species()
    wiz.next()
    assert wiz.step == 3, "向导③→④ 失败"
    # ④ 属性 (标准数组)
    wiz.ab_method.set("standard")
    wiz._render_ab_ui()
    for ab, val in zip(ABILITIES, STANDARD_ARRAY):
        wiz.ab_picks[ab].set(str(val))
    wiz.next()
    assert wiz.step == 4, "向导④→⑤ 失败"
    # ⑤ 技能
    for sid in list(wiz.skill_vars)[:wiz._skill_need]:
        wiz.skill_vars[sid].set(True)
    wiz.next()
    assert wiz.step == 5, "向导⑤→⑥ 失败"
    # ⑥ 武器专精
    for wname in list(wiz.mastery_vars)[:wiz._mastery_need]:
        wiz.mastery_vars[wname].set(True)
    wiz.next()
    assert wiz.step == 7, "向导⑥→摘要 失败"
    # ⑦ 摘要 → 完成
    wiz.next()
    ec = got.get("c")
    assert ec is not None, "向导完成未回调"
    assert ec.class_id == "fighter" and ec.species_id == "dwarf"
    assert ec.hp_current == ec.hp_max()
    assert len(ec.weapon_mastery) == 3 and len(ec.skill_prof) >= 2
    app.set_character(ec)
    app.update()

    # ---- 端到端: 升级到 3 级 (选子职) ----
    ec.level = 2
    dlg = LevelUpDialog(app, ec)
    dlg.withdraw()
    dlg.subclass_cb.current(0)
    dlg._ok()
    assert dlg.result and dlg.result["subclass"], "3级子职未记录"
    ec.level = dlg.result["level"]
    ec.subclass = dlg.result["subclass"]
    app.refresh()
    app.update()

    # ---- 端到端: 4 级 ASI (+2/+1) ----
    before_str = ec.score("STR")
    dlg2 = LevelUpDialog(app, ec)
    dlg2.withdraw()
    dlg2.asi_p2.set(f"{ABILITY_CN['STR']}(STR)")
    dlg2.asi_p1.set(f"{ABILITY_CN['CON']}(CON)")
    dlg2._ok()
    rec = dlg2.result
    assert rec and rec["asi"] == {"type": "asi", "plus2": "STR",
                                  "plus1": "CON"}, rec
    ec.level = rec["level"]
    ec.asi_history.append(rec["asi"])
    assert ec.score("STR") == min(20, before_str + 2)

    # ---- 存档钳制: 脏数据不崩 ----
    dirty = {
        "name": "脏数据", "level": 99, "xp": -50,
        "class_id": "不存在的职业", "subclass": "NotASub",
        "background_id": "??", "species_id": "x",
        "base_scores": {"STR": 99, "DEX": "abc", "CON": -5},
        "skill_prof": ["athletics", "假的技能", None],
        "expertise": ["假的技能", "athletics"],
        "weapon_mastery": ["长剑 Longsword", "歼星舰"],
        "armor_index": 999, "hp_current": 9999, "hp_temp": -3,
        "exhaustion": 42, "conditions": ["恐慌", "石化(假)"],
        "spell_slots_used": {"1": 99, "abc": 2},
    }
    dc = Character(ec.r)
    dc.load_dict(dirty)
    assert dc.level == 20 and dc.xp == 0
    assert dc.class_id == "barbarian", dc.class_id     # 回退到第一个职业
    assert dc.subclass is None
    assert dc.base_scores["STR"] == 20 and dc.base_scores["DEX"] == 10
    assert dc.base_scores["CON"] == 1
    assert dc.skill_prof == {"athletics"}
    assert dc.expertise == set(), "野蛮人没有专精特性, 脏数据应被清空"
    assert dc.weapon_mastery == ["长剑 Longsword"]
    assert dc.armor_index == len(ARMORS) - 1
    assert 0 <= dc.hp_current <= dc.hp_max() and dc.hp_temp == 0
    assert dc.exhaustion == 6 and dc.conditions == {"恐慌"}
    assert all(k in dc.spell_slots() for k in dc.spell_slots_used)

    # ---- 人类「全能」必填校验 ----
    got2 = {}
    wiz2 = Wizard(app, ec.r, lambda c: got2.setdefault("c", c))
    wiz2.withdraw()
    wiz2.cb_class.set("法师 Wizard")
    wiz2._show_class()
    wiz2.next()
    wiz2.cb_bg.set("贤者 Sage")
    wiz2._render_bg_ui()
    nms = [f"{ABILITY_CN[a]}({a})" for a in wiz2._bg_abs]
    wiz2.bg_p2.set(nms[0])
    wiz2.bg_p1.set(nms[1])
    wiz2.next()
    wiz2.cb_sp.set("人类 Human")
    wiz2._show_species()
    step_before = wiz2.step
    wiz2.next()                      # 未选全能专长 → 应被拦下
    assert wiz2.step == step_before, "人类未选专长不应放行"
    wiz2.cb_hfeat.set("Alert")
    wiz2._show_hfeat_desc()
    wiz2.next()
    assert wiz2.step == step_before + 1, "选好专长后应放行"

    app.refresh()
    app.update()
    app.update_idletasks()
    app.destroy()
    print("SELFTEST OK")


def main():
    if "--selftest" in sys.argv:
        run_selftest()
        return
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
