# -*- coding: utf-8 -*-
"""怪物（野兽）数据构建工具。

用法：
  python _build_monsters.py fetch   # 抓取 data/raw/monsters-<edition>/（2024 + 2014）
  python _build_monsters.py build   # 生成 dnd55e/data/monsters.json

数值全部来自 dnd5eapi 原始 JSON，中文文案由本脚本的模板 + 人工骑乘文本拼装，
不手写任何骰子/加值。
"""
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from _path import PROJECT_ROOT as ROOT           # 项目根（本脚本在 tools/legacy/）
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "dnd55e", "data", "monsters.json")
UA = {"User-Agent": "Mozilla/5.0 (dnd55e data builder)"}


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------
def get_json(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 + i * 1.5)
    raise RuntimeError(f"failed {url}: {last}")


def fetch_edition(edition):
    out = os.path.join(RAW, f"monsters-{edition}")
    os.makedirs(out, exist_ok=True)
    idx_path = os.path.join(out, "_index.json")
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = get_json(f"https://www.dnd5eapi.co/api/{edition}/monsters")
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=1)
    results = index["results"]
    print(f"{edition}: listing {len(results)} monsters", flush=True)

    def one(item):
        idx = item["index"]
        path = os.path.join(out, idx + ".json")
        if os.path.exists(path) and os.path.getsize(path) > 200:
            return idx, "cached"
        data = get_json(f"https://www.dnd5eapi.co{item['url']}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return idx, "ok"

    ok = cached = 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        for _idx, st in ex.map(one, results):
            if st == "ok":
                ok += 1
            else:
                cached += 1
    print(f"{edition}: fetched={ok} cached={cached}")
    return len(results)


# --------------------------------------------------------------------------
# 词表
# --------------------------------------------------------------------------
SIZE_CN = {"Tiny": "微型", "Small": "小型", "Medium": "中型",
           "Large": "大型", "Huge": "巨型", "Gargantuan": "超巨型"}
DMG_CN = {"piercing": "穿刺", "slashing": "挥砍", "bludgeoning": "钝击",
          "poison": "毒素", "acid": "强酸", "fire": "火焰", "cold": "冷冻",
          "lightning": "闪电", "thunder": "雷鸣", "necrotic": "黯蚀",
          "radiant": "光耀", "psychic": "心灵", "force": "力场"}
ABIL_CN = {"STR": "力量", "DEX": "敏捷", "CON": "体质",
           "INT": "智力", "WIS": "感知", "CHA": "魅力"}
ABIL_EN = {"Strength": "STR", "Dexterity": "DEX", "Constitution": "CON",
           "Intelligence": "INT", "Wisdom": "WIS", "Charisma": "CHA"}
SKILL_CN = {"perception": "察觉", "stealth": "隐匿", "acrobatics": "特技",
            "athletics": "运动", "insight": "洞悉", "survival": "求生",
            "nature": "自然", "animal-handling": "驯兽",
            "intimidation": "威吓", "investigation": "调查"}

ACT_CN = {
    "Bite": "啃咬", "Claw": "爪击", "Claws": "爪击", "Rend": "撕抓",
    "Gore": "抵撞", "Tail": "尾击", "Sting": "尾刺", "Hooves": "蹄击",
    "Beak": "喙啄", "Talons": "利爪", "Fist": "拳击", "Rock": "投石",
    "Ram": "撞击", "Tentacles": "触手", "Scratch": "抓挠",
    "Multiattack": "多重攻击", "Roar": "咆哮", "Web": "吐丝",
    "Swallow": "吞咽", "Constrict": "紧勒", "Trample": "践踏",
    "Nimble Escape": "灵巧脱身", "Rampage": "暴走", "Ink Cloud": "墨云",
    "Bubble Dash": "气泡冲刺",
}

# 同名不同义的动作按怪物覆盖
ACT_CN_OVERRIDE = {
    ("crab", "Claw"): "钳击", ("giant-crab", "Claw"): "钳击",
    ("giant-scorpion", "Claw"): "钳击",
    ("giant-eagle", "Talons"): "爪击", ("giant-vulture", "Talons"): "爪击",
    ("giant-vulture", "Beak"): "喙啄",
}

TRAIT_CN = {
    "Pack Tactics": "群体战术", "Jumper": "跳跃者", "Amphibious": "水陆两栖",
    "Agile": "灵巧", "Standing Leap": "立定跳跃", "Illumination": "发光",
    "Spider Climb": "蛛行", "Web Walker": "蛛网行者", "Flyby": "飞掠",
    "Water Breathing": "水下呼吸", "Mimicry": "模仿",
    "Bloodied Fury": "浴血狂怒", "Hold Breath": "屏息",
    "Running Leap": "助跑跳跃", "Keen Sight": "敏锐视觉",
    "Keen Hearing and Sight": "敏锐听觉与视觉",
    "Keen Sight and Smell": "敏锐视觉与嗅觉", "Charge": "冲锋",
    "Blood Frenzy": "血之狂热", "Underwater Camouflage": "水下伪装",
    "Compression": "压缩身体",
}

TRAIT_DESC = {
    "Pack Tactics": "若目标 5 尺内至少有{n}的一个未失能盟友，{n}对该目标的攻击检定具有优势。",
    "Jumper": "{n}的跳跃距离以敏捷而非力量计算。",
    "Amphibious": "{n}可以在空气和水中呼吸。",
    "Agile": "{n}移动离开敌人触及范围时不会引发借机攻击。",
    "Standing Leap": "{n}的跳远距离至多 {jump} 尺、跳高至多 {high} 尺，无论是否有助跑。",
    "Illumination": "{n}散发 10 尺半径的明亮光照，以及其外 10 尺的微光光照。",
    "Spider Climb": "{n}可以攀爬困难表面（包括沿天花板），无需进行属性检定。",
    "Web Walker": "{n}无视蛛网造成的移动限制，并知晓任何接触同一蛛网的生物的位置。",
    "Flyby": "{n}飞离敌人触及范围时不会引发借机攻击。",
    "Water Breathing": "{n}只能在水下呼吸。",
    "Mimicry": "{n}可以模仿听过的简单声音（如低语、虫鸣）；听者通过 DC 10 感知（洞悉）检定可辨出这是模仿。",
    "Bloodied Fury": "{n}处于浴血状态（HP 不足上限一半）时，其攻击检定具有优势。",
    "Hold Breath": "{n}可以屏息 {breath}。",
    "Running Leap": "有 10 尺助跑时，{n}的跳远距离至多 25 尺。",
    "Keen Sight": "{n}依赖视觉的感知检定具有优势。",
    "Keen Hearing and Sight": "{n}依赖听觉或视觉的感知检定具有优势。",
    "Keen Sight and Smell": "{n}依赖视觉或嗅觉的感知检定具有优势。",
    "Charge": "若{n}直线移动至少 20 尺后在同回合以撞击命中目标，目标额外受到 7（2d6）点伤害；若目标是生物，须通过 DC 14 力量豁免，否则倒地。",
    "Blood Frenzy": "{n}对 HP 未满的生物进行近战攻击时具有优势。",
    "Underwater Camouflage": "{n}在水下进行的敏捷（隐匿）检定具有优势。",
    "Compression": "{n}可以穿过最窄 1 寸的缝隙，无需为此消耗额外移动。",
}

TRAIT_PARAM = {
    ("frog", "Standing Leap"): {"jump": 10, "high": 5},
    ("giant-frog", "Standing Leap"): {"jump": 20, "high": 10},
    ("giant-toad", "Standing Leap"): {"jump": 20, "high": 10},
    ("crocodile", "Hold Breath"): {"breath": "1 小时"},
    ("giant-crocodile", "Hold Breath"): {"breath": "1 小时"},
    ("plesiosaurus", "Hold Breath"): {"breath": "1 小时"},
    ("killer-whale", "Hold Breath"): {"breath": "30 分钟"},
    ("hippopotamus", "Hold Breath"): {"breath": "10 分钟"},
    ("octopus", "Hold Breath"): {"breath": "30 分钟"},
}

TRAIT_EXTRA = {
    ("giant-octopus", "Water Breathing"): "离开水面后可以屏息 1 小时。",
}

# --------------------------------------------------------------------------
# 收录清单：(id, edition)
# --------------------------------------------------------------------------
MONSTERS = [
    # ---- CR 0 ----
    ("baboon", "2024"), ("badger", "2024"), ("bat", "2024"), ("cat", "2024"),
    ("crab", "2024"), ("deer", "2024"), ("eagle", "2024"), ("frog", "2024"),
    ("giant-fire-beetle", "2024"), ("goat", "2024"), ("hawk", "2024"),
    ("hyena", "2024"), ("jackal", "2024"), ("lizard", "2024"), ("owl", "2024"),
    ("piranha", "2024"), ("rat", "2024"), ("raven", "2024"),
    ("scorpion", "2024"), ("seahorse", "2024"), ("spider", "2024"),
    ("vulture", "2024"), ("weasel", "2024"),
    ("octopus", "2014"), ("quipper", "2014"),
    # ---- CR 1/8 ----
    ("blood-hawk", "2024"), ("camel", "2024"), ("giant-crab", "2024"),
    ("giant-rat", "2024"), ("giant-weasel", "2024"), ("mastiff", "2024"),
    ("pony", "2024"), ("venomous-snake", "2024"),
    ("flying-snake", "2014"),
    # ---- CR 1/4 ----
    ("boar", "2024"), ("constrictor-snake", "2024"), ("draft-horse", "2024"),
    ("elk", "2024"), ("giant-badger", "2024"), ("giant-bat", "2024"),
    ("giant-centipede", "2024"), ("giant-frog", "2024"), ("giant-lizard", "2024"),
    ("giant-venomous-snake", "2024"), ("giant-wolf-spider", "2024"),
    ("panther", "2024"), ("pteranodon", "2024"), ("riding-horse", "2024"),
    ("wolf", "2024"),
    ("axe-beak", "2014"), ("giant-owl", "2014"),
    # ---- CR 1/2 ----
    ("ape", "2024"), ("black-bear", "2024"), ("crocodile", "2024"),
    ("giant-goat", "2024"), ("giant-seahorse", "2024"), ("giant-wasp", "2024"),
    ("reef-shark", "2024"), ("warhorse", "2024"),
    # ---- CR 1 ----
    ("brown-bear", "2024"), ("dire-wolf", "2024"), ("giant-hyena", "2024"),
    ("giant-octopus", "2024"), ("giant-spider", "2024"), ("giant-toad", "2024"),
    ("lion", "2024"), ("tiger", "2024"),
    ("giant-eagle", "2014"), ("giant-vulture", "2014"),
    # ---- CR 2 ----
    ("allosaurus", "2024"), ("giant-boar", "2024"),
    ("giant-constrictor-snake", "2024"), ("hunter-shark", "2024"),
    ("plesiosaurus", "2024"), ("polar-bear", "2024"), ("rhinoceros", "2024"),
    ("saber-toothed-tiger", "2024"),
    ("giant-elk", "2014"),
    # ---- CR 3 ----
    ("ankylosaurus", "2024"), ("giant-scorpion", "2024"), ("killer-whale", "2024"),
    # ---- CR 4 ----
    ("archelon", "2024"), ("elephant", "2024"), ("hippopotamus", "2024"),
    # ---- CR 5 ----
    ("giant-crocodile", "2024"), ("giant-shark", "2024"), ("triceratops", "2024"),
    # ---- CR 6 ----
    ("mammoth", "2024"),
]

NAME_CN = {
    "baboon": "狒狒", "badger": "獾", "bat": "蝙蝠", "cat": "猫", "crab": "螃蟹",
    "deer": "鹿", "eagle": "鹰", "frog": "青蛙", "giant-fire-beetle": "巨型萤火虫",
    "goat": "山羊", "hawk": "隼", "hyena": "鬣狗", "jackal": "胡狼",
    "lizard": "蜥蜴", "owl": "猫头鹰", "piranha": "食人鱼", "rat": "老鼠",
    "raven": "渡鸦", "scorpion": "蝎子", "seahorse": "海马", "spider": "蜘蛛",
    "vulture": "秃鹫", "weasel": "鼬", "octopus": "章鱼", "quipper": "食人鲤",
    "blood-hawk": "血鹰", "camel": "骆驼", "giant-crab": "巨型螃蟹",
    "giant-rat": "巨鼠", "giant-weasel": "巨鼬", "mastiff": "獒犬",
    "pony": "小马", "venomous-snake": "毒蛇", "flying-snake": "飞天蛇",
    "boar": "野猪", "constrictor-snake": "蟒蛇", "draft-horse": "役马",
    "elk": "麋鹿", "giant-badger": "巨型獾", "giant-bat": "巨蝠",
    "giant-centipede": "巨型蜈蚣", "giant-frog": "巨蛙", "giant-lizard": "巨蜥",
    "giant-venomous-snake": "巨型毒蛇", "giant-wolf-spider": "巨狼蛛",
    "panther": "黑豹", "pteranodon": "无齿翼龙", "riding-horse": "乘马",
    "wolf": "狼", "axe-beak": "斧嘴鸟", "giant-owl": "巨枭",
    "ape": "猿", "black-bear": "黑熊", "crocodile": "鳄鱼",
    "giant-goat": "巨山羊", "giant-seahorse": "巨型海马", "giant-wasp": "巨蜂",
    "reef-shark": "礁鲨", "warhorse": "战马",
    "brown-bear": "棕熊", "dire-wolf": "恐狼", "giant-hyena": "巨鬣狗",
    "giant-octopus": "巨型章鱼", "giant-spider": "巨蜘蛛", "giant-toad": "巨蟾",
    "lion": "狮", "tiger": "虎", "giant-eagle": "巨鹰", "giant-vulture": "巨秃鹫",
    "allosaurus": "异特龙", "giant-boar": "巨野猪",
    "giant-constrictor-snake": "巨型蟒蛇", "hunter-shark": "猎鲨",
    "plesiosaurus": "蛇颈龙", "polar-bear": "北极熊", "rhinoceros": "犀牛",
    "saber-toothed-tiger": "剑齿虎", "giant-elk": "巨麋鹿",
    "ankylosaurus": "甲龙", "giant-scorpion": "巨蝎", "killer-whale": "虎鲸",
    "archelon": "古巨龟", "elephant": "象", "hippopotamus": "河马",
    "giant-crocodile": "巨鳄", "giant-shark": "巨鲨", "triceratops": "三角龙",
    "mammoth": "猛犸象",
}

LANG_CN = {
    "Giant Eagle, understands Common and Auran but can't speak":
        "巨人鹰语，能听懂通用语与风族语但不能说",
    "Giant Elk, understands Common, Elvish, and Sylvan but can't speak":
        "巨人麋鹿语，能听懂通用语、精灵语与木族语但不能说",
    "Giant Owl, understands Common, Elvish, and Sylvan but can't speak":
        "巨人枭语，能听懂通用语、精灵语与木族语但不能说",
    "understands Common but can't speak": "能听懂通用语但不能说",
}

# --------------------------------------------------------------------------
# 动作文案
# --------------------------------------------------------------------------
# 附加效果（拼在自动生成的命中句后面）
ACTION_EXTRA = {
    ("goat", "Ram"): "",  # 见 ACTION_FULL
    ("piranha", "Bite"): "若目标 HP 未满，该攻击检定具有优势。",
    ("mastiff", "Bite"): "若目标为中型或更小生物，则陷入倒地状态。",
    ("wolf", "Bite"): "若目标为中型或更小生物，则陷入倒地状态。",
    ("giant-crab", "Claw"): "若目标为中型或更小生物，则被一只钳子擒抱（逃脱 DC 11）。",
    ("boar", "Gore"): "若目标为中型或更小生物，且野猪在此次攻击前直线移动 20 尺以上靠近它，则目标额外受到 1d6 点穿刺伤害并陷入倒地状态。",
    ("elk", "Ram"): "若目标为大型或更小生物，且麋鹿在此次攻击前直线移动 20 尺以上靠近它，则目标额外受到 1d6 点钝击伤害并陷入倒地状态。",
    ("giant-centipede", "Bite"): "目标陷入中毒状态，直至巨型蜈蚣的下个回合开始。",
    ("giant-frog", "Bite"): "若目标为中型或更小生物，则陷入被擒抱状态（逃脱 DC 11）。",
    ("giant-toad", "Bite"): "若目标为中型或更小生物，则陷入被擒抱状态（逃脱 DC 12）。",
    ("giant-goat", "Ram"): "若目标为大型或更小生物，且巨山羊在此次攻击前直线移动 20 尺以上靠近它，则目标额外受到 2d4 点钝击伤害并陷入倒地状态。",
    ("crocodile", "Bite"): "若目标为中型或更小生物，则陷入被擒抱状态（逃脱 DC 12）；被擒抱期间同时处于束缚状态。",
    ("warhorse", "Hooves"): "若目标为大型或更小生物，且战马在此次攻击前直线移动 20 尺以上靠近它，则目标额外受到 2d4 点钝击伤害并陷入倒地状态。",
    ("brown-bear", "Claw"): "若目标为大型或更小生物，则陷入倒地状态。",
    ("dire-wolf", "Bite"): "若目标为大型或更小生物，则陷入倒地状态。",
    ("giant-octopus", "Tentacles"): "若目标为中型或更小生物，则被八条触手擒抱（逃脱 DC 13）；被擒抱期间同时处于束缚状态。",
    ("tiger", "Rend"): "若目标为大型或更小生物，则陷入倒地状态。",
    ("allosaurus", "Claws"): "若目标为大型或更小生物，且异特龙在此次攻击前直线移动 30 尺以上靠近它，则目标陷入倒地状态，异特龙还可对它发动一次啃咬攻击。",
    ("giant-boar", "Gore"): "若目标为大型或更小生物，且巨野猪在此次攻击前直线移动 20 尺以上靠近它，则目标额外受到 2d6 点穿刺伤害并陷入倒地状态。",
    ("hunter-shark", "Bite"): "若目标 HP 未满，该攻击检定具有优势。",
    ("rhinoceros", "Gore"): "若目标为大型或更小生物，且犀牛在此次攻击前直线移动 20 尺以上靠近它，则目标额外受到 2d8 点穿刺伤害并陷入倒地状态。",
    ("ankylosaurus", "Tail"): "若目标为巨型或更小生物，则陷入倒地状态。",
    ("giant-scorpion", "Claw"): "若目标为大型或更小生物，则被一只钳子擒抱（逃脱 DC 13）。",
    ("elephant", "Gore"): "若目标为巨型或更小生物，且象在此次攻击前直线移动 20 尺以上靠近它，则目标陷入倒地状态。",
    ("giant-crocodile", "Bite"): "若目标为大型或更小生物，则陷入被擒抱状态（逃脱 DC 15）；被擒抱期间同时处于束缚状态，且不能被巨鳄的尾击选为目标。",
    ("giant-crocodile", "Tail"): "若目标为大型或更小生物，则陷入倒地状态。",
    ("giant-shark", "Bite"): "若目标 HP 未满，该攻击检定具有优势。",
    ("triceratops", "Gore"): "若目标为巨型或更小生物，且三角龙在此次攻击前直线移动 20 尺以上靠近它，则目标额外受到 2d8 点穿刺伤害并陷入倒地状态。",
    ("mammoth", "Gore"): "若目标为巨型或更小生物，且猛犸在此次攻击前直线移动 20 尺以上靠近它，则目标陷入倒地状态。",
    ("giant-elk", "Ram"): "",
}

# 上游 damage 数组把「条件触发的额外伤害/替代伤害」也拆成了第二段，
# 这些额外伤害已写入 desc 的触发条件里，不应作为常驻第二段伤害。
TRUNCATE_PARTS = {
    ("blood-hawk", "Beak"), ("giant-seahorse", "Ram"),
    ("boar", "Gore"), ("elk", "Ram"), ("giant-goat", "Ram"),
    ("warhorse", "Hooves"), ("giant-boar", "Gore"),
    ("rhinoceros", "Gore"), ("triceratops", "Gore"),
}

# 上游 damage 数组漏掉的前段伤害（描述里有、数组里没有）
PARTS_OVERRIDE = {
    ("scorpion", "Sting"): [("1", "穿刺"), ("1d6", "毒素")],
    ("spider", "Bite"): [("1", "穿刺"), ("1d4", "毒素")],
}

# 完整覆盖（豁免类、多段伤害、特殊机制）
ACTION_FULL = {
    ("goat", "Ram"): "近战攻击：命中 +2，触及 5 尺，命中造成 1 点钝击伤害；若山羊在此次攻击前直线移动 20 尺以上靠近目标，则改为 2（1d4）点钝击伤害。",
    ("blood-hawk", "Beak"): "近战攻击：命中 +4，触及 5 尺，命中造成 1d4+2 点穿刺伤害；若目标处于浴血状态，则改为 1d8+2 点穿刺伤害。",
    ("giant-seahorse", "Ram"): "近战攻击：命中 +4，触及 5 尺，命中造成 2d6+2 点钝击伤害；若巨型海马在此次攻击前直线移动 20 尺以上靠近目标，则改为 2d8+2 点钝击伤害。",
    ("constrictor-snake", "Constrict"): "豁免：DC 12 力量豁免，5 尺内一个蟒蛇可见的中型或更小生物；失败则受到 3d4 点钝击伤害并陷入被擒抱状态（逃脱 DC 12）。",
    ("giant-frog", "Swallow"): "巨蛙吞咽一个正被它擒抱的小型或更小目标。被吞咽期间目标不再被擒抱，但处于目盲与束缚状态，对巨蛙体外的攻击与效果具有全身掩护。巨蛙吞咽时不能使用啃咬；巨蛙死亡时，被吞咽者不再束缚，可花费 5 尺移动从尸体中脱出并处于倒地状态。巨蛙下个回合结束时，被吞咽者受到 2d4 点强酸伤害；若未因此死亡，巨蛙将其吐出，吐出的目标处于倒地状态。",
    ("giant-toad", "Swallow"): "巨蟾吞咽一个正被它擒抱的中型或更小目标。被吞咽期间目标不再被擒抱，但处于目盲与束缚状态，对巨蟾体外的攻击与效果具有全身掩护。目标在巨蟾每个回合结束时受到 3d6 点强酸伤害。巨蟾同时只能吞咽一个目标，且吞咽期间不能使用啃咬；巨蟾死亡时，被吞咽者不再束缚，可花费 5 尺移动从尸体中脱出并处于倒地状态。",
    ("lion", "Roar"): "豁免：DC 11 感知豁免，15 尺内一个生物；失败则陷入恐惧状态，直至狮的下个回合开始。",
    ("giant-spider", "Web"): "豁免：DC 13 敏捷豁免，60 尺内一个巨蜘蛛可见的生物；失败则陷入束缚状态，直至蛛网被摧毁（AC 10；HP 5；对火焰伤害易伤；免疫毒素与心灵伤害）。",
    ("giant-constrictor-snake", "Constrict"): "豁免：DC 14 力量豁免，10 尺内一个巨型蟒蛇可见的大型或更小生物；失败则受到 2d8+4 点钝击伤害并陷入被擒抱状态（逃脱 DC 14）。",
    ("elephant", "Trample"): "豁免：DC 16 敏捷豁免，5 尺内一个处于倒地状态的生物；失败则受到 2d10+6 点钝击伤害，成功则伤害减半。",
    ("mammoth", "Trample"): "豁免：DC 18 敏捷豁免，5 尺内一个处于倒地状态的生物；失败则受到 4d10+7 点钝击伤害，成功则伤害减半。",
    ("giant-hyena", "Rampage"): "对已经处于浴血状态的生物造成伤害后，巨鬣狗可以立即移动至多其速度一半的距离，并发动一次啃咬攻击。",
    ("panther", "Nimble Escape"): "黑豹执行撤离或躲藏动作。",
    ("tiger", "Nimble Escape"): "虎执行撤离或躲藏动作。",
    ("saber-toothed-tiger", "Nimble Escape"): "剑齿虎执行撤离或躲藏动作。",
    ("giant-seahorse", "Bubble Dash"): "在水下时，巨型海马可以移动至多其游泳速度一半的距离，且不会引发借机攻击。",
    ("seahorse", "Bubble Dash"): "在水下时，海马可以移动至多其游泳速度的距离，且不会引发借机攻击。",
    ("giant-elk", "Hooves"): "近战攻击：命中 +6，触及 5 尺，只能以处于倒地状态的生物为目标，命中造成 4d8+4 点钝击伤害。",
    ("giant-octopus", "Ink Cloud"): "触发：巨型章鱼在水下受到伤害。响应：它喷出墨水，填满以自身为中心的 10 尺立方区域，并移动至多其游泳速度。该区域处于重度遮蔽，持续 1 分钟，或被强水流等效果驱散。",
    ("octopus", "Ink Cloud"): "若章鱼在水下，可在周身喷出 5 尺半径的墨云。该区域处于重度遮蔽，持续 1 分钟，强水流可将其驱散。喷墨后章鱼可以用附赠动作执行疾走。",
    ("octopus", "Tentacles"): "近战攻击：命中 +4，触及 5 尺，命中造成 1 点钝击伤害，且目标被擒抱（逃脱 DC 10）；擒抱结束前章鱼不能对其他目标使用触手。",
    ("giant-eagle", "Multiattack"): "该鹰发动两次攻击：一次喙啄和一次爪击。",
    ("giant-vulture", "Multiattack"): "该秃鹫发动两次攻击：一次喙啄和一次爪击。",
    ("ape", "Multiattack"): "该猿发动两次拳击攻击。",
    ("black-bear", "Multiattack"): "该熊发动两次撕抓攻击。",
    ("brown-bear", "Multiattack"): "该熊发动一次啃咬攻击和一次爪击攻击。",
    ("polar-bear", "Multiattack"): "该熊发动两次撕抓攻击。",
    ("lion", "Multiattack"): "该狮发动两次撕抓攻击；可将其中一次替换为一次咆哮。",
    ("saber-toothed-tiger", "Multiattack"): "该虎发动两次撕抓攻击。",
    ("giant-constrictor-snake", "Multiattack"): "该蛇发动一次啃咬攻击，并使用紧勒。",
    ("ankylosaurus", "Multiattack"): "该甲龙发动两次尾击攻击。",
    ("giant-scorpion", "Multiattack"): "该蝎发动两次钳击攻击和一次尾刺攻击。",
    ("archelon", "Multiattack"): "该古巨龟发动两次啃咬攻击。",
    ("elephant", "Multiattack"): "该象发动两次抵撞攻击。",
    ("hippopotamus", "Multiattack"): "该河马发动两次啃咬攻击。",
    ("giant-crocodile", "Multiattack"): "该鳄发动一次啃咬攻击和一次尾击攻击。",
    ("giant-shark", "Multiattack"): "该鲨发动两次啃咬攻击。",
    ("triceratops", "Multiattack"): "该三角龙发动两次抵撞攻击。",
    ("mammoth", "Multiattack"): "该猛犸发动两次抵撞攻击。",
    ("giant-poisonous-snake", "Bite"): "",
}


# --------------------------------------------------------------------------
# 解析小工具
# --------------------------------------------------------------------------
def parse_ft(val):
    if isinstance(val, dict):
        val = val.get("number", 0)
    if not val:
        return 0
    m = re.search(r"(\d+)", str(val))
    return int(m.group(1)) if m else 0


def norm_dice(s):
    if not s:
        return None
    s = str(s).replace("\u2212", "-").replace("\u2013", "-").replace(" ", "")
    return s.lower()


def cr_str(v):
    if v == 0.125:
        return "1/8"
    if v == 0.25:
        return "1/4"
    if v == 0.5:
        return "1/2"
    return str(int(v)) if float(v).is_integer() else str(v)


def cr_num(v):
    return 0.125 if v == 0.125 else (0.25 if v == 0.25 else (0.5 if v == 0.5 else int(v)))


def speed_obj(raw_speed):
    sp = {"walk": 0, "climb": 0, "fly": 0, "swim": 0, "hover": False}
    for k in ("walk", "climb", "fly", "swim", "burrow"):
        if k in raw_speed:
            v = raw_speed[k]
            if k == "fly" and isinstance(v, dict) and v.get("hover"):
                sp["hover"] = True
            sp[k] = parse_ft(v)
    return sp


def dmg_sentence(parts):
    if not parts:
        return ""
    d, t = parts[0]
    s = f"命中造成 {d} 点{t}伤害"
    if len(parts) > 1:
        s += "，外加 " + "、".join(f"{dd} 点{tt}伤害" for dd, tt in parts[1:])
    return s + "。"


def build_action(mid, cn_name, raw_action):
    en = raw_action["name"]
    desc = raw_action.get("desc", "")
    bonus = raw_action.get("attack_bonus")
    parts = []
    for p in raw_action.get("damage") or []:
        d = norm_dice(p.get("damage_dice"))
        if not d:
            continue
        dt = DMG_CN.get(p["damage_type"]["index"], p["damage_type"]["name"])
        parts.append((d, dt))
    if not parts:
        # 2024 部分低 CR 生物只有固定伤害，damage 数组为空，从描述里取
        m = re.search(r"Hit: (\d+) \(([^)]+)\) (\w+) damage", desc)
        if m:
            parts = [(norm_dice(m.group(2)), DMG_CN.get(m.group(3).lower(), m.group(3)))]
        else:
            m = re.search(r"Hit: (\d+) (\w+) damage", desc)
            if m:
                parts = [(m.group(1), DMG_CN.get(m.group(2).lower(), m.group(2)))]

    if en == "Multiattack":
        kind = "multiattack"
    elif "Saving Throw:" in desc:
        kind = "save"
    elif desc.startswith("Melee"):
        kind = "melee"
    elif desc.startswith("Ranged"):
        kind = "ranged"
    else:
        kind = "other"

    reach = None
    m = re.search(r"reach (\d+) ?f(?:ee)?t", desc)
    if m:
        reach = int(m.group(1))
    rng = None
    m = re.search(r"range ([\d]+)/([\d]+) ?f(?:ee)?t", desc)
    if m:
        rng = [int(m.group(1)), int(m.group(2))]

    if kind == "melee" and reach is None:
        raise SystemExit(f"无法解析触及距离：{mid} / {en}")
    if kind == "ranged" and rng is None:
        raise SystemExit(f"无法解析射程：{mid} / {en}")

    save = None
    dc = None
    m = re.search(r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) Saving Throw: DC (\d+)", desc)
    if m:
        save = ABIL_EN[m.group(1)]
        dc = int(m.group(2))

    key = (mid, en)
    if key in PARTS_OVERRIDE:
        parts = PARTS_OVERRIDE[key]
    elif key in TRUNCATE_PARTS:
        parts = parts[:1]
    if key in ACTION_FULL and ACTION_FULL[key]:
        text = ACTION_FULL[key]
    elif kind == "melee":
        text = f"近战攻击：命中 +{bonus}，触及 {reach} 尺，" + dmg_sentence(parts)
        text += ACTION_EXTRA.get(key, "")
    elif kind == "ranged":
        text = f"远程攻击：命中 +{bonus}，射程 {rng[0]}/{rng[1]} 尺，" + dmg_sentence(parts)
        text += ACTION_EXTRA.get(key, "")
    else:
        raise SystemExit(f"缺少动作文案：{mid} / {en}（kind={kind}）")

    action = {
        "name": f"{ACT_CN_OVERRIDE.get(key) or ACT_CN.get(en, en)} {en}",
        "kind": kind,
        "attack_bonus": bonus if kind in ("melee", "ranged") else None,
        "reach": reach if kind == "melee" else None,
        "range": rng if kind == "ranged" else None,
        "damage": parts[0][0] if parts else None,
        "damage_type": parts[0][1] if parts else None,
        "save": save,
        "dc": dc,
        "desc": text,
    }
    if len(parts) > 1:
        action["damage_parts"] = [{"damage": d, "damage_type": t} for d, t in parts]
    return action


def build_trait(mid, cn_name, raw_trait):
    en = raw_trait["name"]
    tpl = TRAIT_DESC.get(en)
    if not tpl:
        raise SystemExit(f"缺少特性文案：{mid} / {en}")
    text = tpl.format(n=cn_name, **TRAIT_PARAM.get((mid, en), {}))
    extra = TRAIT_EXTRA.get((mid, en))
    if extra:
        text += extra
    return {"name": f"{TRAIT_CN.get(en, en)} {en}", "desc": text}


def build_monster(mid, edition):
    path = os.path.join(RAW, f"monsters-{edition}", mid + ".json")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    cn = NAME_CN[mid]
    en_name = raw["name"]

    saves, skills = {}, {}
    for p in raw.get("proficiencies", []):
        pname = p["proficiency"]["name"]
        if pname.startswith("Saving Throw:"):
            ab = pname.split(":", 1)[1].strip()
            saves[ABIL_EN.get(ab, ab.upper())] = p["value"]
        elif pname.startswith("Skill:"):
            sidx = p["proficiency"]["index"].replace("skill-", "")
            skills[SKILL_CN.get(sidx, sidx)] = p["value"]

    senses_raw = raw.get("senses") or {}
    senses = {
        "darkvision": parse_ft(senses_raw.get("darkvision")),
        "blindsight": parse_ft(senses_raw.get("blindsight")),
        "tremorsense": parse_ft(senses_raw.get("tremorsense")),
        "truesight": parse_ft(senses_raw.get("truesight")),
        "passive_perception": int(senses_raw.get("passive_perception") or 10),
    }

    lang = (raw.get("languages") or "").strip()
    lang = LANG_CN.get(lang, lang) if lang and lang != "None" else "—"
    if lang.lower() in ("none", ""):
        lang = "—"

    ac0 = raw["armor_class"][0]
    AC_NOTE = {"natural armor": "天生护甲", "dex": "敏捷调整", "armor": "护甲",
               "shield": "盾牌", "leather": "皮甲", "hide": "兽皮甲"}
    ac_note = AC_NOTE.get(ac0.get("type") or "", "天生护甲")
    hp_dice = raw.get("hit_points_roll") or raw.get("hit_dice") or ""
    hp_dice = hp_dice.replace(" ", "")

    m = {
        "id": mid,
        "name": f"{cn} {en_name}",
        "cr": cr_str(raw["challenge_rating"]),
        "cr_num": cr_num(raw["challenge_rating"]),
        "xp": raw.get("xp"),
        "size": SIZE_CN[raw["size"]],
        "ac": ac0["value"],
        "ac_note": ac_note,
        "hp": raw["hit_points"],
        "hp_dice": hp_dice,
        "speed": speed_obj(raw.get("speed") or {}),
        "abilities": {
            "STR": raw["strength"], "DEX": raw["dexterity"], "CON": raw["constitution"],
            "INT": raw["intelligence"], "WIS": raw["wisdom"], "CHA": raw["charisma"],
        },
        "saves": saves,
        "skills": skills,
        "senses": senses,
        "languages": lang,
        "traits": [build_trait(mid, cn, t) for t in raw.get("special_abilities") or []],
        "actions": [build_action(mid, cn, a) for a in raw.get("actions") or []],
        "bonus_actions": [build_action(mid, cn, a) for a in raw.get("bonus_actions") or []],
        "reactions": [build_action(mid, cn, a) for a in raw.get("reactions") or []],
        "edition": edition,
        "source": "srd" if edition == "2024" else "srd-2014",
    }
    return m


def build():
    out = []
    for mid, edition in MONSTERS:
        out.append(build_monster(mid, edition))
    out.sort(key=lambda x: (x["cr_num"], x["name"]))
    data = {
        "_note": "野兽形态数据，供德鲁伊荒野变形、游侠野兽伙伴、法师变形术使用。仅收录 Beast 类型、CR 0-6。数值取自 dnd5eapi（2024 优先，SRD 5.2；2014 补录标记 edition=2014）。",
        "monsters": out,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"wrote {OUT}: {len(out)} monsters")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "fetch":
        for ed in (sys.argv[2:] or ["2024", "2014"]):
            fetch_edition(ed)
    elif cmd == "build":
        build()
    else:
        print(__doc__)
