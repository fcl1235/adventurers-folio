# -*- coding: utf-8 -*-
"""抓取 SRD 5.2 (2024) 法术并生成 dnd55e_spells.json (中文名 + 中文一句话效果)"""
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://www.dnd5eapi.co/api/2024/spells/"
OUT = r"E:\workbuddycache\test1\dnd55e_spells.json"

SCHOOL = {"abjuration": "防护", "conjuration": "咒法", "divination": "预言",
          "enchantment": "附魔", "evocation": "塑能", "illusion": "幻术",
          "necromancy": "死灵", "transmutation": "变化"}
DMG = {"acid": "强酸", "bludgeoning": "钝击", "cold": "寒冷", "fire": "火焰",
       "force": "力场", "lightning": "闪电", "necrotic": "黯蚀", "piercing": "穿刺",
       "poison": "毒素", "psychic": "心灵", "radiant": "光耀", "slashing": "挥砍",
       "thunder": "雷鸣"}
SAVE = {"strength": "力量", "dexterity": "敏捷", "constitution": "体质",
        "intelligence": "智力", "wisdom": "感知", "charisma": "魅力"}
CLASSES = {"bard": "bard", "cleric": "cleric", "druid": "druid",
           "paladin": "paladin", "ranger": "ranger", "sorcerer": "sorcerer",
           "warlock": "warlock", "wizard": "wizard"}

# ---- 中文名 ----
NAMES = {
 "acid-splash": "酸液飞溅", "chill-touch": "寒颤之触", "dancing-lights": "舞光术",
 "druidcraft": "德鲁伊伎俩", "eldritch-blast": "魔能爆", "elementalism": "元素伎俩",
 "fire-bolt": "火焰箭", "guidance": "神导术", "light": "光亮术", "mage-hand": "法师之手",
 "mending": "修复术", "message": "传讯术", "minor-illusion": "次级幻影",
 "poison-spray": "毒液喷溅", "prestidigitation": "魔法伎俩", "produce-flame": "燃火术",
 "ray-of-frost": "冻寒之触", "resistance": "抗性术", "sacred-flame": "圣火术",
 "shillelagh": "橡棍术", "shocking-grasp": "电爪", "sorcerous-burst": "术法爆发",
 "spare-the-dying": "维生术", "starry-wisp": "星辉之光", "thaumaturgy": "奇术",
 "true-strike": "克敌先击", "vicious-mockery": "恶言相加",
 "alarm": "警报术", "animal-friendship": "化兽为友", "bane": "灾祸术", "bless": "祝福术",
 "burning-hands": "燃烧之手", "charm-person": "魅惑人类", "chromatic-orb": "色彩球",
 "color-spray": "七彩喷射", "command": "命令术", "comprehend-languages": "通晓语言",
 "create-or-destroy-water": "造水/枯水术", "cure-wounds": "治疗 wounds",
 "detect-evil-and-good": "侦测善恶", "detect-magic": "侦测魔法",
 "detect-poison-and-disease": "侦测毒性与疾病", "disguise-self": "易容术",
 "dissonant-whispers": "不谐低语", "divine-favor": "神恩", "divine-smite": "至圣斩",
 "ensnaring-strike": "缠绕打击", "entangle": "纠缠术", "expeditious-retreat": "疾走术",
 "faerie-fire": "妖火", "false-life": "虚假生命", "feather-fall": "羽落术",
 "find-familiar": "寻获魔宠", "floating-disk": "浮空碟", "fog-cloud": "云雾术",
 "goodberry": "神莓术", "grease": "油腻术", "guiding-bolt": "指引之光",
 "healing-word": "治愈真言", "hellish-rebuke": "炼狱叱喝", "heroism": "英雄气概",
 "hex": "脆弱诅咒", "hideous-laughter": "狂笑术", "hunters-mark": "猎人印记",
 "ice-knife": "冰刃", "identify": "鉴定术", "illusory-script": "幻影文字",
 "inflict-wounds": "致伤术", "jump": "跳跃术", "longstrider": "大步奔行",
 "mage-armor": "法师护甲", "magic-missile": "魔法飞弹",
 "protection-from-evil-and-good": "防护善恶", "purify-food-and-drink": "净化食粮",
 "ray-of-sickness": "致病射线", "sanctuary": "圣域术", "searing-smite": "灼热斩",
 "shield": "护盾术", "shield-of-faith": "信仰之盾", "silent-image": "无声幻影",
 "sleep": "睡眠术", "speak-with-animals": "动物交谈", "thunderwave": "雷鸣波",
 "unseen-servant": "隐形仆役",
 "acid-arrow": "强酸箭", "aid": "援助术", "alter-self": "变身术",
 "animal-messenger": "动物信使", "arcane-lock": "秘法锁",
 "arcanists-magic-aura": "奥术魔法灵光", "augury": "占卜术", "barkskin": "树皮术",
 "blindness-deafness": "目盲/失聪术", "blur": "朦胧术", "calm-emotions": "安定心神",
 "continual-flame": "恒久火焰", "darkness": "黑暗术", "darkvision": "黑暗视觉",
 "detect-thoughts": "侦测思想", "dragons-breath": "龙息术", "enhance-ability": "强化属性",
 "enlarge-reduce": "变巨/缩小术", "enthrall": "迷魂术", "find-steed": "寻获坐骑",
 "find-traps": "寻找陷阱", "flame-blade": "火焰刀", "flaming-sphere": "烈焰球",
 "gentle-repose": "遗体防腐", "gust-of-wind": "造风术", "heat-metal": "灼热金属",
 "hold-person": "人类定身术", "invisibility": "隐形术", "knock": "敲击术",
 "lesser-restoration": "次等复原术", "levitate": "浮空术",
 "locate-animals-or-plants": "动植物定位术", "locate-object": "物品定位术",
 "magic-mouth": "魔嘴术", "magic-weapon": "魔化武器", "mind-spike": "心灵尖刺",
 "mirror-image": "镜影术", "misty-step": "迷踪步", "moonbeam": "月华之光",
 "pass-without-trace": "行踪无痕", "phantasmal-force": "幻影之力",
 "prayer-of-healing": "治疗祷言", "protection-from-poison": "防护毒素",
 "ray-of-enfeeblement": "衰弱射线", "rope-trick": "绳技", "scorching-ray": "灼热射线",
 "see-invisibility": "识破隐形", "shatter": "粉碎音波", "shining-smite": "闪耀斩",
 "silence": "沉默术", "spider-climb": "蛛行术", "spike-growth": "荆棘丛生",
 "spiritual-weapon": "灵体武器", "suggestion": "暗示术", "warding-bond": "守护之链",
 "web": "蛛网术", "zone-of-truth": "诚实之域",
 "animate-dead": "操纵死尸", "beacon-of-hope": "希望灯塔", "bestow-curse": "降咒",
 "blink": "闪现术", "call-lightning": "召雷术", "clairvoyance": "鹰眼术",
 "conjure-animals": "召兽术", "counterspell": "法术反制", "create-food-and-water": "造食术",
 "daylight": "昼明术", "dispel-magic": "解除魔法", "fear": "恐惧术", "fireball": "火球术",
 "fly": "飞行术", "gaseous-form": "气化形体", "glyph-of-warding": "守卫刻文",
 "haste": "加速术", "hypnotic-pattern": "催眠图纹", "lightning-bolt": "闪电束",
 "magic-circle": "魔法圈", "major-image": "高级幻影", "mass-healing-word": "群体治愈真言",
 "meld-into-stone": "融身入石", "nondetection": "防探测", "phantom-steed": "幽灵骏马",
 "plant-growth": "植物滋长", "protection-from-energy": "防护能量", "remove-curse": "移除诅咒",
 "revivify": "回生术", "sending": "短讯术", "sleet-storm": "冰风暴", "slow": "缓慢术",
 "speak-with-dead": "死者交谈", "speak-with-plants": "植物交谈",
 "spirit-guardians": "灵体卫士", "stinking-cloud": "臭云术", "tiny-hut": "小屋术",
 "tongues": "通晓语言(万语)", "vampiric-touch": "吸血鬼之触", "water-breathing": "水下呼吸",
 "water-walk": "水面行走", "wind-wall": "风墙术",
 "arcane-eye": "奥术之眼", "aura-of-life": "生命灵光", "banishment": "放逐术",
 "black-tentacles": "黑触手", "blight": "枯萎术", "charm-monster": "魅惑怪物",
 "compulsion": "强制术", "confusion": "困惑术", "conjure-minor-elementals": "召唤次等元素",
 "conjure-woodland-beings": "召唤林地生物", "control-water": "操控水体",
 "death-ward": "防死结界", "dimension-door": "任意门", "divination": "预言术",
 "dominate-beast": "支配野兽", "fabricate": "造物术", "faithful-hound": "忠犬术",
 "fire-shield": "火焰护盾", "freedom-of-movement": "行动自如",
 "giant-insect": "巨虫术", "greater-invisibility": "高等隐形", "guardian-of-faith": "信仰守卫",
 "hallucinatory-terrain": "幻景地形", "ice-storm": "冰风暴(4环)", "locate-creature": "生物定位",
 "phantasmal-killer": "幻影杀手", "polymorph": "变形术", "private-sanctum": "私人圣所",
 "resilient-sphere": "弹性球", "secret-chest": "秘藏箱", "stone-shape": "塑石术",
 "stoneskin": "石肤术", "vitriolic-sphere": "强酸球", "wall-of-fire": "火墙术",
 "animate-objects": "活化物件", "antilife-shell": "反生命外壳", "arcane-hand": "奥术之手",
 "awaken": "启蒙术", "cloudkill": "死亡之云", "commune": "通神术",
 "commune-with-nature": "自然通神", "cone-of-cold": "寒冰锥", "conjure-elemental": "召唤元素",
 "contact-other-plane": "异界接触", "contagion": "疫病术", "creation": "创造术",
 "dispel-evil-and-good": "驱散善恶", "dominate-person": "支配人类", "dream": "托梦术",
 "flame-strike": "焰击术", "geas": "指使术", "greater-restoration": "高等复原术",
 "hallow": "圣居术", "hold-monster": "怪物定身术", "insect-plague": "虫群瘟疫",
 "legend-lore": "通晓传奇", "mass-cure-wounds": "群体治疗 wounds", "mislead": "误导术",
 "modify-memory": "修改记忆", "passwall": "穿墙术", "planar-binding": "异界誓缚",
 "raise-dead": "死者复活", "reincarnate": "转生术", "scrying": "探知术", "seeming": "幻容术",
 "summon-dragon": "召唤巨龙", "telekinesis": "念力", "telepathic-bond": "心灵联结",
 "teleportation-circle": "传送法阵", "tree-stride": "树跃术", "wall-of-force": "力场墙",
 "wall-of-stone": "石墙术",
 "blade-barrier": "剑刃屏障", "chain-lightning": "闪电链", "circle-of-death": "死亡法阵",
 "conjure-fey": "召唤精类", "contingency": "意外术", "create-undead": "创造不死生物",
 "disintegrate": "解离术", "eyebite": "邪眼", "find-the-path": "寻路术",
 "flesh-to-stone": "石化术", "forbiddance": "禁制术", "freezing-sphere": "冰封球",
 "globe-of-invulnerability": "无敌法球", "guards-and-wards": "守卫结界", "harm": "伤害术",
 "heal": "治疗术", "heroes-feast": "英雄宴", "instant-summons": "即刻召唤",
 "irresistible-dance": "难拒之舞", "magic-jar": "魔魂壶", "mass-suggestion": "群体暗示",
 "move-earth": "移土术", "planar-ally": "异界盟友", "programmed-illusion": "预设幻影",
 "sunbeam": "阳炎射线", "transport-via-plants": "植物传送", "true-seeing": "真实视界",
 "wall-of-ice": "冰墙术", "wall-of-thorns": "荆棘墙", "wind-walk": "御风而行",
 "word-of-recall": "回返真言",
 "arcane-sword": "奥术剑", "conjure-celestial": "召唤天界生物",
 "delayed-blast-fireball": "延迟爆裂火球", "divine-word": "神圣真言", "etherealness": "以太化",
 "finger-of-death": "死亡一指", "fire-storm": "火焰风暴", "forcecage": "力场牢笼",
 "magnificent-mansion": "华丽府邸", "mirage-arcane": "奥术幻景", "plane-shift": "位面转移",
 "prismatic-spray": "虹光喷射", "project-image": "投影术", "regenerate": "再生术",
 "resurrection": "复生术", "reverse-gravity": "逆转重力", "sequester": "隐匿术",
 "simulacrum": "拟像术", "symbol": "法术徽记", "teleport": "传送术",
 "animal-shapes": "动物形态", "antimagic-field": "反魔法场", "antipathy-sympathy": "厌恶/同情",
 "befuddlement": "心智迷乱", "clone": "克隆术", "control-weather": "操控天气",
 "demiplane": "半位面", "dominate-monster": "支配怪物", "earthquake": "地震术",
 "glibness": "巧言术", "holy-aura": "神圣灵光", "incendiary-cloud": "燃焰之云",
 "maze": "迷宫术", "mind-blank": "心灵屏障", "power-word-stun": "律令震慑",
 "sunburst": "阳炎爆", "tsunami": "海啸术",
 "astral-projection": "星界投射", "foresight": "预知术", "gate": "异界之门",
 "imprisonment": "禁锢术", "mass-heal": "群体治疗术", "meteor-swarm": "陨石雨",
 "power-word-heal": "律令治疗", "power-word-kill": "律令死亡", "prismatic-wall": "虹光墙",
 "shapechange": "形体变化", "storm-of-vengeance": "复仇风暴", "time-stop": "时间停止",
 "true-polymorph": "完全变形术", "true-resurrection": "完全复生术", "weird": "怪异术",
 "wish": "祈愿术",
}
# 修正几处笔误
NAMES["cure-wounds"] = "治疗之伤"
NAMES["mass-cure-wounds"] = "群体治疗之伤"
NAMES["tongues"] = "万语通"

# ---- 中文一句话效果 (覆盖常用法术; 未覆盖的用结构化信息自动生成) ----
DESC = {
 "acid-splash": "对 60 尺内 1 个生物或 2 个相邻生物造成 1d6 强酸伤害(敏捷豁免免伤)。",
 "chill-touch": "触碰造成 1d10 黯蚀伤害, 目标无法恢复 HP 至你下回合结束。",
 "dancing-lights": "造出至多 4 个光源, 可随意移动, 照亮 10 尺。",
 "druidcraft": "小型自然效果: 预测天气、催开花蕾、点燃/熄灭小火焰等。",
 "eldritch-blast": "射程 120 尺, 1 道 1d10 力场伤害光束; 5 级起 2 道, 11 级 3 道, 17 级 4 道。",
 "elementalism": "操控少量元素: 造风、点火、塑水、弄土等小型效果。",
 "fire-bolt": "远程法术攻击, 命中造成 1d10 火焰伤害(5 级起递增)。",
 "guidance": "专注 1 分钟, 目标下一次属性检定 +1d4。",
 "light": "让一件物品发出 20 尺明亮/20 尺微光, 持续 1 小时。",
 "mage-hand": "造出一只幽灵手, 可隔 30 尺操作物件、开门、取物(不能攻击)。",
 "mending": "修复物件上一处破损或裂缝(1 尺以内)。",
 "message": "对 120 尺内目标耳语, 只有它能听见, 可悄悄回话。",
 "minor-illusion": "造出声音或一个 5 尺见方的静态幻影, 持续 1 分钟。",
 "poison-spray": "对 30 尺内目标造成 1d12 毒素伤害(体质豁免免伤)。",
 "prestidigitation": "小型魔法戏法: 点燃、清洁、调味、造出小物件等。",
 "produce-flame": "手中生出火焰, 可照明, 也可投掷造成 1d8 火焰伤害。",
 "ray-of-frost": "远程法术攻击, 1d8 寒冷伤害并使目标速度 -10 尺。",
 "resistance": "专注 1 分钟, 目标下一次豁免 +1d4。",
 "sacred-flame": "目标 60 尺内, 敏捷豁免失败受 1d8 光耀伤害(无掩体加成)。",
 "shillelagh": "让木棍/长棍以施法属性攻击, 伤害变 1d8+施法属性, 持续 1 分钟。",
 "shocking-grasp": "近战法术攻击, 1d8 闪电伤害, 目标无法借机攻击。",
 "sorcerous-burst": "远程法术攻击, 1d8 伤害(类型自选), 掷出 8 可追加骰。",
 "spare-the-dying": "触碰一个 0 HP 生物, 使其稳定(不再做死亡豁免)。",
 "starry-wisp": "发出星辉, 造成 1d8 光耀伤害, 并让目标显形(防隐形)。",
 "thaumaturgy": "小型奇迹: 声音放大、火焰摇曳、地面震动等。",
 "true-strike": "用施法属性做一次武器攻击, 伤害类型改为光耀, 可附加 1d6。",
 "vicious-mockery": "目标感知豁免失败: 1d6 心灵伤害, 且下次攻击劣势。",

 "alarm": "结界 20 尺, 有人进入即发出警报(可设为心理提醒)。",
 "animal-friendship": "说服一只野兽不攻击你, 持续 24 小时。",
 "bane": "专注 1 分钟, 至多 3 个目标攻击与豁免 -1d4。",
 "bless": "专注 1 分钟, 至多 3 个目标攻击与豁免 +1d4。",
 "burning-hands": "15 尺锥形, 2d6 火焰伤害(敏捷豁免减半)。",
 "charm-person": "一个人形生物感知豁免失败则被你魅惑 1 小时。",
 "chromatic-orb": "3d8 元素伤害(自选类型), 远程法术攻击。",
 "color-spray": "15 尺锥形, 体质豁免失败者目盲至你下回合结束。",
 "command": "命令一个生物执行一个词: 来/丢/逃/趴/停等(感知豁免否定)。",
 "comprehend-languages": "1 小时内听懂任何语言, 阅读任何文字。",
 "create-or-destroy-water": "造出/毁掉 10 加仑水(可扩大)。",
 "cure-wounds": "触碰治疗 2d8+施法属性 HP(不死/构装无效)。",
 "detect-evil-and-good": "专注 10 分钟, 感知 30 尺内异界生物/圣徽/邪祟。",
 "detect-magic": "专注 10 分钟, 感知 30 尺内魔法及其学派。",
 "detect-poison-and-disease": "感知 30 尺内毒物、疾病与中毒生物。",
 "disguise-self": "1 小时内改变外貌与衣着(限于同体型)。",
 "dissonant-whispers": "目标感知豁免失败: 3d6 心灵伤害并用反应逃离。",
 "divine-favor": "1 分钟内你的武器伤害 +1d4 光耀。",
 "divine-smite": "命中后消耗法术位追加 2d8 光耀伤害(不死/邪魔 +1d8)。",
 "ensnaring-strike": "命中后目标力量豁免, 失败被藤蔓束缚(专注)。",
 "entangle": "20 尺方形地面长出藤蔓, 力量豁免失败被束缚(专注)。",
 "expeditious-retreat": "专注 10 分钟, 可用附赠动作疾走。",
 "faerie-fire": "20 尺立方内目标敏捷豁免失败则被照亮, 攻击对其优势。",
 "false-life": "获得 1d4+4 临时 HP, 持续 1 小时。",
 "feather-fall": "反应: 5 个坠落生物下坠速度降至 60 尺/轮且不受坠落伤害。",
 "find-familiar": "召唤魔宠(蝙蝠/猫/乌鸦等), 可共享感官、传递触碰法术。",
 "floating-disk": "造出跟随你的浮空碟, 载重 500 磅, 持续 1 小时。",
 "fog-cloud": "20 尺半径浓雾, 重度遮蔽, 持续 1 小时(专注)。",
 "goodberry": "造出 10 颗莓果, 每颗回复 1 HP 并提供一日营养。",
 "grease": "10 尺方形地面变滑, 敏捷豁免失败倒地。",
 "guiding-bolt": "远程法术攻击, 4d6 光耀, 下次对该目标攻击优势。",
 "healing-word": "附赠动作, 60 尺内治疗 2d4+施法属性 HP。",
 "hellish-rebuke": "反应: 受到伤害时反伤 2d10 火焰(敏捷豁免减半)。",
 "heroism": "专注 1 分钟, 目标免疫恐慌并获得每回合临时 HP。",
 "hex": "专注 1 小时, 你的攻击对目标 +1d6 黯蚀, 目标某项检定劣势。",
 "hideous-laughter": "目标感知豁免失败则倒地狂笑, 无法行动(专注)。",
 "hunters-mark": "专注 1 小时, 对目标攻击 +1d6 伤害, 便于追踪。",
 "ice-knife": "1d10 穿刺 + 爆炸 2d6 寒冷(敏捷豁免)。",
 "identify": "辨识魔法物品的属性、用途与是否受诅咒。",
 "illusory-script": "写下一段只有指定对象能读的文字, 其余人看到的是乱码。",
 "inflict-wounds": "近战法术攻击, 2d10 黯蚀伤害。",
 "jump": "目标跳跃距离变为三倍, 持续 1 分钟。",
 "longstrider": "目标速度 +10 尺, 持续 1 小时。",
 "mage-armor": "无甲时 AC 变为 13+敏捷, 持续 8 小时。",
 "magic-missile": "3 支必中飞弹, 每支 1d4+1 力场伤害(可分散或集中)。",
 "protection-from-evil-and-good": "专注 10 分钟, 异界生物对你攻击劣势, 免疫其魅惑/恐慌。",
 "purify-food-and-drink": "净化 5 尺半径内的食物与饮水。",
 "ray-of-sickness": "远程法术攻击, 2d8 毒素并使目标中毒。",
 "sanctuary": "1 分钟内攻击你的人需感知豁免, 失败则改选目标。",
 "searing-smite": "命中后追加 1d6 火焰, 并每回合持续燃烧(专注)。",
 "shield": "反应: AC +5 直到你下回合开始。",
 "shield-of-faith": "专注 10 分钟, 目标 AC +2。",
 "silent-image": "造出 15 尺立方的视觉幻影(无声), 可用动作移动。",
 "sleep": "5 尺半径内生物感知豁免失败则陷入沉睡(专注 1 分钟)。",
 "speak-with-animals": "1 小时内与野兽交谈, 可影响其行为。",
 "thunderwave": "15 尺立方, 2d8 雷鸣并推开 10 尺(体质豁免减半)。",
 "unseen-servant": "召唤隐形仆役, 可做简单劳务, 持续 1 小时。",

 "acid-arrow": "远程法术攻击, 4d4 强酸, 下回合再受 2d4。",
 "aid": "至多 3 个生物 HP 上限 +5, 持续 8 小时。",
 "alter-self": "专注 1 小时, 改变外貌、获得水下呼吸或天生武器。",
 "animal-messenger": "让一只小动物替你送一条 25 字以内的讯息。",
 "arcane-lock": "魔法锁住门/箱, 直至被解除。",
 "arcanists-magic-aura": "伪造或掩盖目标的魔法灵光, 持续 24 小时。",
 "augury": "询问一次 30 分钟内行动的吉凶, 得到预兆。",
 "barkskin": "目标皮肤变树皮, AC 不低于 16(专注 1 小时)。",
 "blindness-deafness": "目标体质豁免失败则目盲或失聪(专注 1 分钟)。",
 "blur": "专注 1 分钟, 对你的攻击劣势。",
 "calm-emotions": "平息 20 尺内人形生物的敌意或情绪(专注 1 分钟)。",
 "continual-flame": "造出一支永不熄灭的火焰(等同火炬, 可遮蔽)。",
 "darkness": "15 尺半径魔法黑暗, 黑暗视觉也无法看穿(专注 10 分钟)。",
 "darkvision": "目标获得 150 尺黑暗视觉, 持续 8 小时。",
 "detect-thoughts": "专注 1 分钟, 读取 30 尺内生物表层思想。",
 "dragons-breath": "触碰目标获得吐息武器(2d6 元素伤害, 专注 1 分钟)。",
 "enhance-ability": "专注 1 小时, 目标某项属性检定优势, 并附加对应增益。",
 "enlarge-reduce": "使目标变大(伤害 +1d4)或变小, 持续 1 分钟(专注)。",
 "enthrall": "专注 1 分钟, 听众感知豁免失败则注意力被你吸引。",
 "find-steed": "召唤一匹精魂坐骑, 持续至你再次施法。",
 "find-traps": "感知 120 尺内陷阱的位置与性质。",
 "flame-blade": "造出一把火焰弯刀, 造成 3d6 火焰伤害(专注 10 分钟)。",
 "flaming-sphere": "滚动的火球, 2d6 火焰伤害(敏捷豁免, 专注 1 分钟)。",
 "gentle-repose": "保护尸体 10 天不腐, 延长复活时限。",
 "gust-of-wind": "60 尺直线强风, 推退生物并吹散雾气(专注 1 分钟)。",
 "heat-metal": "加热金属物件, 触碰者受 2d8 火焰伤害(专注 1 分钟)。",
 "hold-person": "人形生物感知豁免失败则麻痹(专注 1 分钟)。",
 "invisibility": "目标隐形 1 小时(攻击或施法即结束)。",
 "knock": "打开一扇被锁/卡住的门或解除一个魔法锁。",
 "lesser-restoration": "结束目标的目盲/失聪/中毒/麻痹或一种疾病。",
 "levitate": "使一个生物或物件垂直升降 20 尺(专注 10 分钟)。",
 "locate-animals-or-plants": "得知 5 里内某类动植物的大致方位。",
 "locate-object": "得知 1000 尺内某件熟悉物品的方位(专注 10 分钟)。",
 "magic-mouth": "让一个物件在触发条件满足时播放你预设的 25 字讯息。",
 "magic-weapon": "武器变为魔法武器, 攻击与伤害 +1(专注 1 小时)。",
 "mind-spike": "目标感知豁免失败受 3d8 心灵伤害, 且你能感知其位置。",
 "mirror-image": "造出 3 个镜像, 使攻击可能打空, 持续 1 分钟。",
 "misty-step": "附赠动作, 传送至 30 尺内可见空地。",
 "moonbeam": "5 尺半径光柱, 2d10 光耀伤害(体质豁免, 专注 1 分钟)。",
 "pass-without-trace": "专注 1 小时, 你与同伴隐匿 +10, 不留痕迹。",
 "phantasmal-force": "目标智力豁免失败则相信一个幻影为真(专注 1 分钟)。",
 "prayer-of-healing": "10 分钟内治疗至多 6 个生物各 2d8+施法属性 HP。",
 "protection-from-poison": "目标中毒状态结束, 毒素豁免优势, 毒素伤害抗性。",
 "ray-of-enfeeblement": "目标力量豁免失败则力量检定与攻击 -1d4(专注 1 分钟)。",
 "rope-trick": "绳子立起通往异次元空间, 可容纳 8 人, 持续 1 小时。",
 "scorching-ray": "3 道火焰射线, 每道 2d6 火焰(远程法术攻击)。",
 "see-invisibility": "1 小时内看见隐形生物与以太生物。",
 "shatter": "10 尺半径巨响, 3d8 雷鸣伤害(体质豁免减半, 构装劣势)。",
 "shining-smite": "命中后目标被光标记, 下次攻击对其优势(专注 1 分钟)。",
 "silence": "20 尺半径无声, 无法施放有言语成分的法术(专注 10 分钟)。",
 "spider-climb": "目标获得攀爬速度, 可倒挂行走(专注 1 小时)。",
 "spike-growth": "20 尺半径地面布满尖刺, 移动受 2d4 穿刺伤害。",
 "spiritual-weapon": "造出浮动武器, 附赠动作攻击, 1d8+施法属性力场伤害。",
 "suggestion": "专注 8 小时, 目标感知豁免失败则执行一个合理建议。",
 "warding-bond": "目标 AC 与豁免 +1, 并分担其受到的伤害(需佩戴配对戒指)。",
 "web": "20 尺立方蛛网, 敏捷豁免失败被束缚(专注 1 小时)。",
 "zone-of-truth": "15 尺半径内生物不能说谎(魅力豁免否定, 专注 10 分钟)。",

 "animate-dead": "唤起一具骷髅或僵尸为你服务 24 小时。",
 "beacon-of-hope": "专注 1 分钟, 范围内治疗取最大值, 死亡豁免优势。",
 "bestow-curse": "诅咒目标: 检定劣势/额外黯蚀伤害/浪费动作等(专注 1 分钟)。",
 "blink": "每回合末有 50% 几率进入以太位面躲避攻击(1 分钟)。",
 "call-lightning": "专注 10 分钟, 每回合召雷 3d10 闪电伤害(敏捷豁免)。",
 "clairvoyance": "在 1 里内造出隐形传感器, 可看或听(专注 10 分钟)。",
 "conjure-animals": "召唤精魂兽群, 造成 3d10 伤害或提供骑乘(专注 10 分钟)。",
 "counterspell": "反应: 打断 60 尺内一个正在施放的法术(高环可反制高环)。",
 "create-food-and-water": "造出 45 磅食物与 30 加仑清水。",
 "daylight": "60 尺半径明亮光照, 驱散魔法黑暗(1 小时)。",
 "dispel-magic": "解除 120 尺内一个法术效果(高环可解高环)。",
 "fear": "30 尺锥形, 感知豁免失败者恐慌并逃跑(专注 1 分钟)。",
 "fireball": "20 尺半径爆炸, 8d6 火焰伤害(敏捷豁免减半)。",
 "fly": "专注 10 分钟, 目标获得 60 尺飞行速度。",
 "gaseous-form": "目标化为雾体, 可穿缝隙飞行(专注 1 小时)。",
 "glyph-of-warding": "在物件/地面刻下符文, 触发时释放储存的法术。",
 "haste": "专注 1 分钟, 目标速度翻倍、AC +2、额外一次攻击。",
 "hypnotic-pattern": "30 尺立方彩色图纹, 感知豁免失败者被魅惑(专注 1 分钟)。",
 "lightning-bolt": "100 尺直线, 8d6 闪电伤害(敏捷豁免减半)。",
 "magic-circle": "10 尺半径法阵, 特定类型生物无法进入或魅惑你。",
 "major-image": "造出 20 尺立方幻影(含声音/气味), 可移动(专注 10 分钟)。",
 "mass-healing-word": "附赠动作, 30 尺内至多 6 人各回复 1d4+施法属性 HP。",
 "meld-into-stone": "融入石头 8 小时, 无法被普通手段察觉。",
 "nondetection": "目标 8 小时内无法被预言魔法探知。",
 "phantom-steed": "召唤幽灵坐骑, 速度 100 尺, 持续 1 小时。",
 "plant-growth": "使植物茂密生长: 区域移动费 4 倍, 或作物增产一年。",
 "protection-from-energy": "专注 1 小时, 目标获得一种元素伤害抗性。",
 "remove-curse": "解除目标身上的一个诅咒或同调。",
 "revivify": "复活 1 分钟内死亡的生物, 回复 1 HP。",
 "sending": "向任意位面的熟悉目标发送 25 字讯息并收到回复。",
 "sleet-storm": "40 尺半径冰雨, 地面湿滑, 专注 1 分钟。",
 "slow": "40 尺立方, 感知豁免失败者速度减半、无反应(专注 1 分钟)。",
 "speak-with-dead": "向一具尸体问 5 个问题(答案简短且可能含糊)。",
 "speak-with-plants": "与植物交谈, 获取周围情报(10 分钟)。",
 "spirit-guardians": "15 尺半径灵体环绕, 敌人受 3d8 光耀/黯蚀伤害(专注 10 分钟)。",
 "stinking-cloud": "20 尺半径恶臭, 体质豁免失败者浪费动作(专注 1 分钟)。",
 "tiny-hut": "造出 10 尺半径穹顶小屋, 可容纳 10 人, 持续 8 小时。",
 "tongues": "1 小时内听懂并说出任何语言。",
 "vampiric-touch": "近战法术攻击, 3d6 黯蚀伤害并回复等量 HP(专注 1 分钟)。",
 "water-breathing": "至多 10 个生物 24 小时内水下呼吸。",
 "water-walk": "10 个生物可在水面/液体表面行走 1 小时。",
 "wind-wall": "造出风墙, 阻挡箭矢与小型飞行物, 持续 1 分钟。",

 "arcane-eye": "造出隐形眼, 可飞行侦查 30 分钟。",
 "aura-of-life": "30 尺内同伴免疫死尸化, 并每回合回复 1 HP(专注 10 分钟)。",
 "banishment": "魅力豁免失败则目标被放逐到无害半位面(专注 1 分钟)。",
 "black-tentacles": "20 尺半径触手, 力量豁免失败被束缚并受 3d6 钝击(专注 1 分钟)。",
 "blight": "目标体质豁免失败受 8d8 黯蚀伤害(植物劣势)。",
 "charm-monster": "魅惑一个任意类型生物 1 小时。",
 "compulsion": "专注 1 分钟, 目标必须按你指定的方向移动。",
 "confusion": "10 尺半径内生物行为混乱(专注 1 分钟)。",
 "conjure-minor-elementals": "召唤精魂元素, 造成 4d8 元素伤害(专注 10 分钟)。",
 "conjure-woodland-beings": "召唤精魂精类, 可传送并造成伤害(专注 10 分钟)。",
 "control-water": "操控 100 尺内的水体(洪水/分流/漩涡, 专注 10 分钟)。",
 "death-ward": "目标首次降到 0 HP 时改为 1 HP, 持续 8 小时。",
 "dimension-door": "传送你与 1 个同伴至 500 尺内任意位置。",
 "divination": "向神祇询问一个关于 7 天内事件的问题。",
 "dominate-beast": "支配一只野兽(专注 1 分钟)。",
 "fabricate": "把原料变成成品(武器/护甲/家具等)。",
 "faithful-hound": "造出隐形猎犬看守区域, 发现入侵者会吠叫并咬击。",
 "fire-shield": "10 分钟内, 攻击者受 2d8 火焰/寒冷反伤。",
 "freedom-of-movement": "目标移动不受困难地形/束缚/麻痹限制, 持续 1 小时。",
 "giant-insect": "把昆虫变为巨型版本为你作战(专注 10 分钟)。",
 "greater-invisibility": "目标隐形 1 分钟且攻击不破隐(专注)。",
 "guardian-of-faith": "造出守卫, 10 尺内敌人受 20 点光耀伤害。",
 "hallucinatory-terrain": "把 150 尺地形变为幻景, 持续 24 小时。",
 "ice-storm": "20 尺半径冰雹, 2d8 钝击 + 4d6 寒冷(敏捷豁免减半)。",
 "locate-creature": "得知 1000 尺内某类生物的方向(专注 1 小时)。",
 "phantasmal-killer": "目标感知豁免失败则恐惧并每回合受 4d10 心灵伤害(专注 1 分钟)。",
 "polymorph": "把目标变成野兽(专注 1 小时)。",
 "private-sanctum": "保护一片区域不被探知/传送/窥视, 持续 24 小时。",
 "resilient-sphere": "把目标封在力场球内 1 分钟(专注)。",
 "secret-chest": "把箱子藏入以太位面 60 天。",
 "stone-shape": "把石块塑成任意形状。",
 "stoneskin": "目标获得钝击/穿刺/挥砍抗性(专注 1 小时)。",
 "vitriolic-sphere": "15 尺半径强酸, 10d4 强酸伤害(敏捷豁免减半)。",
 "wall-of-fire": "造出火墙, 穿过者受 5d8 火焰伤害(专注 1 分钟)。",

 "animate-objects": "活化至多 10 件小物件为你作战(专注 1 分钟)。",
 "antilife-shell": "10 尺半径屏障, 生物无法进入(专注 1 小时)。",
 "arcane-hand": "造出巨大的力场手, 可抓握/推击(专注 1 分钟)。",
 "awaken": "赋予野兽/植物智力与语言, 持续 30 天。",
 "cloudkill": "20 尺半径毒云, 体质豁免失败受 5d8 毒素伤害(专注 10 分钟)。",
 "commune": "向神祇问 3 个是非问题。",
 "commune-with-nature": "获取 3 里内地形/生物/建筑的情报。",
 "cone-of-cold": "60 尺锥形, 8d8 寒冷伤害(体质豁免减半)。",
 "conjure-elemental": "召唤元素生物为你作战(专注 1 小时)。",
 "contact-other-plane": "向异界存在问 5 个问题, 有智力受损风险。",
 "contagion": "使目标感染疾病(体质豁免失败)。",
 "creation": "造出不超过 5 尺立方的物件, 持续数小时。",
 "dispel-evil-and-good": "异界生物被驱散, 你免疫其魅惑/恐慌(专注 1 分钟)。",
 "dominate-person": "支配一个人形生物(专注 1 分钟)。",
 "dream": "进入目标梦境传递讯息或制造噩梦(8 小时)。",
 "flame-strike": "10 尺半径火柱, 5d6 火焰 + 5d6 光耀(敏捷豁免减半)。",
 "geas": "命令目标执行/禁行某事, 违者受 5d10 心灵伤害(30 天)。",
 "greater-restoration": "解除石化/力竭/魅惑/诅咒或属性减损。",
 "hallow": "圣化一片区域, 附加守护效果(持续至解除)。",
 "hold-monster": "任意类型生物感知豁免失败则麻痹(专注 1 分钟)。",
 "insect-plague": "20 尺半径虫群, 4d10 穿刺伤害(体质豁免减半)。",
 "legend-lore": "得知一件人/物/地点的传奇信息。",
 "mass-cure-wounds": "30 尺内至多 6 人各回复 5d8+施法属性 HP。",
 "mislead": "你隐形并可操控一个幻影分身(专注 1 小时)。",
 "modify-memory": "修改目标最近 24 小时的记忆(感知豁免否定)。",
 "passwall": "在墙面开出一条 5 尺宽通道, 持续 1 小时。",
 "planar-binding": "束缚一个异界生物为你服务 24 小时。",
 "raise-dead": "复活 10 天内死亡的生物, 回复 1 HP。",
 "reincarnate": "复活死者但换一副新身体。",
 "scrying": "窥视 10 里内一个目标(感知豁免否定, 专注 10 分钟)。",
 "seeming": "改变至多 12 个生物的外貌, 持续 8 小时。",
 "summon-dragon": "召唤精魂巨龙, 可吐息(专注 1 小时)。",
 "telekinesis": "念力移动 1000 磅物体或一个生物(专注 10 分钟)。",
 "telepathic-bond": "8 小时内与至多 8 个生物心灵沟通(任意距离同一位面)。",
 "teleportation-circle": "造出永久传送法阵, 通往你指定的另一法阵。",
 "tree-stride": "在树木之间瞬间移动(专注 1 分钟)。",
 "wall-of-force": "造出力场墙, 无法被普通手段破坏(专注 10 分钟)。",
 "wall-of-stone": "造出石墙, 可塑形(专注 10 分钟)。",

 "blade-barrier": "造出旋转刀刃墙, 穿过者受 6d10 挥砍伤害。",
 "chain-lightning": "闪电在至多 3 个目标间跳跃, 各 10d8 闪电(敏捷豁免减半)。",
 "circle-of-death": "60 尺半径负能量, 8d6 黯蚀伤害(体质豁免减半)。",
 "conjure-fey": "召唤精类生物为你作战(专注 1 小时)。",
 "contingency": "预设一个 5 环以下法术, 在条件满足时自动触发。",
 "create-undead": "创造食尸鬼等强力不死生物为你服务。",
 "disintegrate": "敏捷豁免失败受 10d6+40 力场伤害, 可能化为灰烬。",
 "eyebite": "每回合以目光使目标恐惧/生病/沉睡(专注 1 分钟)。",
 "find-the-path": "得知通往某地的最短路线(专注 1 天)。",
 "flesh-to-stone": "体质豁免失败者逐渐石化(专注 1 分钟)。",
 "forbiddance": "禁止特定生物进入区域, 并造成伤害。",
 "freezing-sphere": "60 尺半径冰爆, 10d6 寒冷(体质豁免减半)。",
 "globe-of-invulnerability": "5 尺半径球内免疫 5 环以下法术(专注 1 分钟)。",
 "guards-and-wards": "大范围守护结界: 迷雾、警报、锁门等。",
 "harm": "体质豁免失败受 14d6 黯蚀伤害, HP 上限降低。",
 "heal": "治疗 70 HP 并结束目盲/失聪/疾病。",
 "heroes-feast": "造出盛宴, 参与者获得免疫毒素/恐慌与 HP 上限提升。",
 "instant-summons": "把一件标记过的物品瞬间召到手中。",
 "irresistible-dance": "目标无法控制地跳舞(专注 1 分钟)。",
 "magic-jar": "把灵魂转移进容器, 可夺取他人身体。",
 "mass-suggestion": "12 个目标同时接受一个合理建议(专注 24 小时)。",
 "move-earth": "重塑 40 尺见方的土地(专注 2 小时)。",
 "planar-ally": "召唤异界存在为你服务, 需支付报酬。",
 "programmed-illusion": "预设一个幻影, 条件满足时播放。",
 "sunbeam": "60 尺直线阳炎, 6d8 光耀并使目标目盲(专注 1 分钟)。",
 "transport-via-plants": "通过两株植物瞬间跨越距离。",
 "true-seeing": "看穿隐形、幻术与变形, 持续 1 小时。",
 "wall-of-ice": "造出冰墙, 可造成寒冷伤害。",
 "wall-of-thorns": "造出荆棘墙, 穿过者受 7d8 穿刺并减速。",
 "wind-walk": "8 小时内化为云雾飞行, 速度 300 尺。",
 "word-of-recall": "与至多 5 个同伴瞬间回到你的圣所。",

 "arcane-sword": "造出浮动力场剑, 每回合攻击 3d10 力场伤害(专注 1 分钟)。",
 "conjure-celestial": "召唤天界生物为你作战(专注 1 小时)。",
 "delayed-blast-fireball": "延迟爆炸的火球, 每回合增伤 1d6(专注 1 分钟)。",
 "divine-word": "神圣一词使敌人目盲/失聪/震慑或死亡(按 HP)。",
 "etherealness": "进入以太位面, 可穿越物体(8 小时)。",
 "finger-of-death": "体质豁免失败受 7d8+30 黯蚀伤害, 死者化为僵尸。",
 "fire-storm": "10 个 10 尺立方火焰, 各 7d10 火焰(敏捷豁免减半)。",
 "forcecage": "造出力场牢笼, 无法逃脱(1 小时)。",
 "magnificent-mansion": "造出豪华异次元府邸, 持续 24 小时。",
 "mirage-arcane": "把 1 平方里地形变为幻景, 持续 10 天。",
 "plane-shift": "把至多 8 个生物传送到另一存在位面。",
 "prismatic-spray": "60 尺锥形七彩光, 随机颜色造成不同效果。",
 "project-image": "造出你的幻影分身, 可从其位置施法(专注 1 天)。",
 "regenerate": "目标回复 4d8+15 HP 并再生断肢(1 小时)。",
 "resurrection": "复活 100 年内死者, 回复全部 HP。",
 "reverse-gravity": "50 尺半径重力逆转, 生物与物件上浮(专注 1 分钟)。",
 "sequester": "使目标隐形并沉睡, 无法被探知。",
 "simulacrum": "造出目标生物的複制品为你服务。",
 "symbol": "刻下致命徽记, 触发时造成范围伤害或控制。",
 "teleport": "把至多 8 个生物传送到任意已知地点。",

 "animal-shapes": "把至多 10 个生物变为野兽(专注 24 小时)。",
 "antimagic-field": "10 尺半径内魔法失效(专注 1 小时)。",
 "antipathy-sympathy": "使一片区域对特定生物产生强烈吸引或排斥。",
 "befuddlement": "智力豁免失败受 10d12 心灵伤害且无法施法。",
 "clone": "培育克隆体, 死亡后灵魂转入其中。",
 "control-weather": "改变 5 里内天气(专注 8 小时)。",
 "demiplane": "造出半位面房间, 持续 1 小时。",
 "dominate-monster": "支配任意类型生物(专注 1 小时)。",
 "earthquake": "100 尺半径地震, 建筑倒塌, 生物倒地(专注 1 分钟)。",
 "glibness": "1 小时内魅力检定至少 15。",
 "holy-aura": "30 尺内同伴豁免优势, 敌人攻击劣势(专注 1 分钟)。",
 "incendiary-cloud": "20 尺半径火云, 每回合 10d8 火焰伤害(专注 1 分钟)。",
 "maze": "把目标困入迷宫位面(专注 10 分钟)。",
 "mind-blank": "24 小时内免疫心灵伤害与探知。",
 "power-word-stun": "一个 HP 150 以下目标被震慑。",
 "sunburst": "60 尺半径光爆, 12d6 光耀并目盲(体质豁免减半)。",
 "tsunami": "造出 300 尺长海啸墙, 造成 6d10 钝击伤害(专注 6 轮)。",

 "astral-projection": "灵魂进入星界, 肉身留在原地。",
 "foresight": "8 小时内目标攻击/检定/豁免优势, 敌人对其攻击劣势。",
 "gate": "打开通往另一存在位面的传送门。",
 "imprisonment": "永久囚禁一个生物(多种形式)。",
 "mass-heal": "至多 6 个生物回复 700 HP 并结束疾病/目盲等。",
 "meteor-swarm": "4 颗陨石各 20 尺半径, 40d6 火焰+钝击(敏捷豁免减半)。",
 "power-word-heal": "一个生物回复全部 HP 并结束相关状态。",
 "power-word-kill": "一个 HP 100 以下的目标立即死亡。",
 "prismatic-wall": "造出七色光墙, 每层有不同效果。",
 "shapechange": "变成任意生物(CR ≤ 等级), 专注 1 小时。",
 "storm-of-vengeance": "大范围复仇风暴: 雷鸣、闪电、酸雨(专注 1 分钟)。",
 "time-stop": "时间停止 1d4+1 回合, 只有你能行动。",
 "true-polymorph": "把生物或物件永久变为另一形态。",
 "true-resurrection": "复活 200 年内死者, 无需尸体。",
 "weird": "制造恐惧幻象, 感知豁免失败者恐慌并受 10d10 心灵伤害。",
 "wish": "实现一个愿望: 复制任意 8 环以下法术或改变现实。",
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def num_cn(s):
    return (s.replace("feet", "尺").replace("foot", "尺").replace("miles", "里")
             .replace("mile", "里").replace("Self", "自身").replace("Touch", "触碰")
             .replace("Unlimited", "无限").replace("Sight", "视线")
             .replace("Special", "特殊").replace("Willing", "自愿"))


def cast_cn(s):
    t = s.lower()
    if t == "action":
        return "1 动作"
    if "bonus action" in t:
        return "1 附赠动作"
    if "reaction" in t:
        return "1 反应"
    return num_cn(s.replace("minutes", "分钟").replace("minute", "分钟")
                  .replace("hours", "小时").replace("hour", "小时")
                  .replace("seconds", "秒"))


def dur_cn(s):
    t = s.replace("Concentration, up to", "专注，至多")
    for a, b in [("Instantaneous", "瞬发"), ("Until dispelled or triggered", "直至解除或触发"),
                 ("Until dispelled", "直至解除"), ("Special", "特殊"),
                 ("Permanent", "永久"), ("minutes", "分钟"), ("minute", "分钟"),
                 ("hours", "小时"), ("hour", "小时"), ("rounds", "轮"),
                 ("round", "轮"), ("days", "天"), ("day", "天")]:
        t = t.replace(a, b)
    return t.strip()


def comp_cn(comps, material):
    m = {"V": "语", "S": "姿", "M": "材"}
    base = "/".join(m.get(c, c) for c in comps)
    return f"{base}（{material}）" if material else base


def parse_save(desc):
    m = re.search(r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) "
                  r"saving throw", desc)
    return SAVE.get(m.group(1).lower(), "") if m else ""


def build_one(idx_name):
    idx, name = idx_name
    d = get(API + idx)
    dmg = ""
    dtype = ""
    scaling = {}
    if d.get("damage"):
        dd = d["damage"]
        dtype = DMG.get((dd.get("damage_type") or {}).get("index", ""), "")
        for k, v in (dd.get("damage_at_slot_level") or {}).items():
            scaling[int(k)] = v
        for k, v in (dd.get("damage_at_character_level") or {}).items():
            scaling[int(k)] = v
        if scaling:
            dmg = scaling[min(scaling)]
    desc_en = d.get("description", "")
    save = parse_save(desc_en)
    area = d.get("area_of_effect") or {}
    return {
        "id": idx,
        "name_en": name,
        "name": NAMES.get(idx, name),
        "level": d.get("level", 0),
        "school": SCHOOL.get((d.get("school") or {}).get("index", ""), ""),
        "classes": [CLASSES[c["index"]] for c in (d.get("classes") or [])
                    if c["index"] in CLASSES],
        "cast": cast_cn(d.get("casting_time", "")),
        "range": num_cn(d.get("range", "")),
        "comp": comp_cn(d.get("components") or [], d.get("material") or ""),
        "duration": dur_cn(d.get("duration", "")),
        "concentration": bool(d.get("concentration")),
        "ritual": bool(d.get("ritual")),
        "damage": dmg,
        "damage_type": dtype,
        "save": save,
        "attack": "spell attack" in desc_en,
        "area": (f"{area.get('size')} 尺" if area else ""),
        "area_type": area.get("type", ""),
        "scaling": {str(k): v for k, v in sorted(scaling.items())},
        "desc": DESC.get(idx, ""),
        "desc_en": desc_en[:900],
    }


def main():
    if os.path.exists(OUT) and os.path.getsize(OUT) > 5000 and "--force" not in sys.argv:
        n = len(json.load(open(OUT, encoding="utf-8"))["spells"])
        print(f"local spell db already exists ({n} spells), skip. use --force to refetch")
        return
    lst = get(API)["results"]
    pairs = [(s["index"], s["name"]) for s in lst]
    print("fetching", len(pairs), "spells ...")
    out = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, rec in enumerate(ex.map(build_one, pairs), 1):
            out.append(rec)
            if i % 40 == 0:
                print("  ", i)
    out.sort(key=lambda x: (x["level"], x["name"]))
    json.dump({"system": "srp-5.2", "count": len(out), "spells": out},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with_desc = sum(1 for s in out if s["desc"])
    print("saved", OUT, len(out), "spells,", with_desc, "with CN desc")


if __name__ == "__main__":
    main()
