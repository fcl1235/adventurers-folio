# -*- coding: utf-8 -*-
"""P6 生成器：10 个物种 + 16 个背景 → 插件 YAML（一条目一文件）。

数据源：
  dnd55e_core_data.json   背景的 属性/起始专长/技能/工具（2024 口径，已核对）
                          + 物种的体积/速度/特性清单（只当**清单**用，正文自己写）

为什么物种特性不直接搬旧程序的字符串：旧程序那十条是「中文摘要 + 括号备注」，
既不是规则原文，也拆不出结构化效果。这里按 2024 原文逐条重写中文，并把
**能结算的部分接上原语**（黑暗视觉 / 伤害抗性 / 每级 HP / 速度），
结算不了的写进 note —— 而不是假装算过了。

两种内容的英文处理不一样，别混淆：
  * `summary`（这是什么）与英文名：作者自述，照写英文。
  * 特性 / 背景的**规则正文** `text`：一句也不搬。SRD 5.2 只覆盖 9 物种
    （阿斯莫不在）与 4 背景（侍僧/罪犯/贤者/士兵），其余 12 个背景没有原文；
    带原文的 13 条也没有逐字复制进本仓库。统一用 NO_ENGLISH 说明
    「英文原句不在本插件里，中文版是权威文本」。

用法：
  python tools/gen_origins.py              # 生成缺失的文件
  python tools/gen_origins.py --force      # 连已有文件一起覆盖
  python tools/gen_origins.py --only dwarf soldier
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_SPECIES = ROOT / "plugins" / "dnd2024-core" / "species"
OUT_BACKGROUNDS = ROOT / "plugins" / "dnd2024-core" / "backgrounds"

# 手写过的条目：生成器绝不覆盖
HAND_WRITTEN: set[str] = set()

NO_ENGLISH = (
    "%s — this plugin does not carry the SRD 5.2 English wording of this rule; "
    "the normalized Chinese text above is the authoritative copy."
)


# --- 文本工具（与 gen_subclasses.py 同一套） --------------------------
def slug(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip().lower())
    return re.sub(r"_+", "_", value).strip("_")


def block(text: str, indent: int) -> str:
    pad = " " * indent
    body = (text or "").replace("\r", "").strip() or "—"
    return "|-\n" + "\n".join(pad + line for line in body.splitlines())


def flow(pairs: list[tuple[str, Any]]) -> str:
    return "{" + ", ".join("%s: %s" % (key, _scalar(value)) for key, value in pairs) + "}"


def _scalar(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)


def render_effects(effects: list[dict]) -> list[str]:
    lines: list[str] = []
    for item in effects:
        ((op, payload),) = item.items()
        if isinstance(payload, dict):
            lines.append("      - %s: %s" % (op, flow(list(payload.items()))))
        elif isinstance(payload, (list, tuple)):
            lines.append("      - %s: %s" % (op, _scalar(payload)))
        else:
            lines.append("      - %s: %s" % (op, payload))
    return lines


def render_note(zh: str, en: str) -> list[str]:
    return [
        "      - note:",
        "          zh: " + block(zh, 12),
        "          en: " + block(en, 12),
    ]


def header(source: str, srd: bool, extra: str = "") -> list[str]:
    lines = [
        "# 由 tools/gen_origins.py 从 dnd55e_core_data.json + 2024 规则重写生成。",
        "# 重跑生成器会覆盖本文件；要长期改动请改数据源，或在文件里写一个 hand-edited 注释让它别碰。",
        "# SRD 5.2 %s：%s" % ("覆盖这一条" if srd else "不含这一条",
                              source),
    ]
    if extra:
        lines.append("# " + extra)
    return lines


# --- 物种 -------------------------------------------------------------
# traits 里每条 = (id 片段, 中文名, 英文名, 解锁等级, 中文正文, 效果列表, 未结算说明)
# 效果为空 = 只有规则原文与 note；有效果时仍未接的部分写在第 7 项。


def darkvision(feet: int) -> tuple:
    """黑暗视觉是 7 个物种共用的同一条特性，正文只写一次 —— 逐处复制迟早写出
    两种说法（60 尺的写成「微光下视物」、120 尺的写成「等同微光」）。

    **取高不叠加**（`stack: max`）：物种给 60、法术再给 120 时，正确结果是 120。
    写成 add 会得到 180 —— 一个不会报错、只是错的数。
    """
    return (
        "darkvision", "黑暗视觉", "Darkvision", 1,
        "你在 %d 尺内的微光光照中视为明亮光照，在黑暗中视为微光光照，"
        "只能分辨灰阶，无法分辨颜色。" % feet,
        [{"grant_modifier": {"target": "sense.darkvision", "value": feet, "stack": "max"}}], "",
    )


SPECIES: list[dict] = [
    dict(
        id="aasimar", zh="阿斯莫", en="Aasimar",
        size=["medium", "small"], speed=30, srd=False,
        summary_zh="血脉里带着天界光辉的凡人：能治愈、能发光，也能在瞬间展开翅膀或让敌人看见自己身上的恐怖。",
        summary_en="Mortals touched by the Upper Planes, able to heal, to shine, "
                   "and to reveal a sliver of celestial power.",
        traits=[
            ("celestial_resistance", "天界抗性", "Celestial Resistance", 1,
             "你具有黯蚀伤害与光耀伤害的抗性。",
             [{"grant_defense": {"resistance": ["necrotic", "radiant"]}}], ""),
            darkvision(60),
            ("healing_hands", "治愈之手", "Healing Hands", 1,
             "以一个动作触碰一个生物，掷等于你熟练加值数量的 d4，目标恢复等量生命值。"
             "使用后需完成长休才能再次使用。",
             [], "治疗池按熟练加值取骰，需要「掷骰 + 目标」管道，尚未接入。"),
            ("light_bearer", "承光者", "Light Bearer", 1,
             "你习得戏法 光亮术（Light），施法属性为魅力。",
             [], "戏法来自物种而非职业，记法术配额时需要一个「物种法术」来源，尚未接入。"),
            ("celestial_revelation", "天界启示", "Celestial Revelation", 3,
             "3 级起，你可以用一个附赠动作变身 1 分钟：天界之翼（飞行 30 尺）、"
             "死灵帷幕（黯蚀抗性 + 每回合对周围造成黯蚀伤害）或内在光耀（发光 + 每回合灼烧周围）。"
             "完成长休后才能再次使用。",
             [], "三种形态都是限时效果，需要效果时长与回合流程，尚未接入。"),
        ],
    ),
    dict(
        id="dragonborn", zh="龙裔", en="Dragonborn",
        size=["medium"], speed=30, srd=True,
        summary_zh="龙血后裔：一口吐息、一身与血统同源的抗性，5 级后还能短暂展翼。",
        summary_en="Heirs of dragon blood, with a breath weapon, a matching resistance, "
                   "and wings that unfurl at 5th level.",
        traits=[
            ("draconic_ancestry", "龙族血脉", "Draconic Ancestry", 1,
             "选择一种龙类血统（如红龙→火焰、白龙→寒冷）。它决定你的吐息形状与伤害类型。",
             [], "血统是建卡时的选择项，需要一个「血统」选择管道，尚未接入。"),
            ("breath_weapon", "吐息武器", "Breath Weapon", 1,
             "以攻击动作的一部分替换一次攻击，呼出 15 尺锥形或 30 尺直线吐息："
             "范围内生物做敏捷豁免，失败受 1d10 伤害（5 级 2d10、11 级 3d10、17 级 4d10），"
             "成功减半。次数等于熟练加值，长休恢复。",
             [], "吐息是范围攻击，需要一个「范围 + 群体豁免」结算入口，尚未接入。"),
            ("damage_resistance", "伤害抗性", "Damage Resistance", 1,
             "你具有与龙族血统相同类型的伤害抗性。",
             [], "抗性类型跟随血统选择，选择管道接入后自动生效。"),
            darkvision(60),
            ("dragon_wings", "龙族飞行", "Dragon Wings", 5,
             "5 级起，你可以用一个附赠动作展开龙翼，获得等于当前速度的飞行速度，持续 10 分钟。"
             "完成长休后才能再次使用。",
             [], "限时飞行速度需要效果时长管道，尚未接入。"),
        ],
    ),
    dict(
        id="dwarf", zh="矮人", en="Dwarf",
        size=["medium"], speed=30, srd=True,
        summary_zh="石头里长出来的人：黑暗视觉 120 尺、每级多 1 点生命、抗毒，还会在石面上感知四周。",
        summary_en="A stout folk of stone: superior darkvision, extra Hit Points every level, "
                   "poison resistance, and tremorsense on stone.",
        traits=[
            darkvision(120),
            ("dwarven_toughness", "矮人韧性", "Dwarven Toughness", 1,
             "你的生命值上限每级 +1。",
             [{"grant_modifier": {"target": "hp.per_level", "value": 1}}], ""),
            ("dwarven_resilience", "矮人体魄", "Dwarven Resilience", 1,
             "你具有毒素伤害的抗性。此外，你对抗中毒状态的豁免检定有优势。",
             [{"grant_defense": {"resistance": ["poison"]}}],
             "「对抗中毒状态的豁免有优势」要按状态来源判定，尚未接入。"),
            ("stonecunning", "石中机警", "Stonecunning", 1,
             "以一个附赠动作，你获得 60 尺颤动感知，持续 10 分钟 —— 前提是你站在石质表面上。"
             "次数等于熟练加值，长休恢复。",
             [], "颤动感知是限时感官，需要效果时长与地形判定，尚未接入。"),
        ],
    ),
    dict(
        id="elf", zh="精灵", en="Elf",
        size=["medium"], speed=30, srd=True,
        summary_zh="长寿的魔法民族：黑暗视觉、对抗魅惑的优势、4 小时出神代替睡眠，血脉再送三个法术。",
        summary_en="A long-lived magical people: darkvision, advantage against being charmed, "
                   "trance instead of sleep, and spells from an elven lineage.",
        traits=[
            darkvision(60),
            ("fey_ancestry", "妖精血统", "Fey Ancestry", 1,
             "你对抗魅惑状态的豁免检定有优势。",
             [], "「对抗魅惑状态的豁免」要按状态来源判定，尚未接入。"),
            ("keen_senses", "敏锐感官", "Keen Senses", 1,
             "你从 洞悉、察觉、生存 中选择一项，获得其技能熟练。",
             [], "这一项是玩家选择，可在建卡时作为额外熟练登记；物种特性本身不自动给。"),
            ("trance", "出神", "Trance", 1,
             "你不需睡眠。以 4 小时冥想完成长休，且冥想期间保持清醒。",
             [], "长休时长属于休整流程，尚未接入。"),
            ("elven_lineage", "精灵血脉", "Elven Lineage", 1,
             "选择卓尔、高等或木精灵：获得对应戏法，3 级与 5 级各获得一个对应法术，"
             "每个法术可用次数为 1 次，长休恢复。",
             [], "物种法术来源与「免费施放次数」池都需要「物种法术」通道，尚未接入。"),
        ],
    ),
    dict(
        id="gnome", zh="侏儒", en="Gnome",
        size=["small"], speed=30, srd=True,
        summary_zh="小个子的魔法工匠：黑暗视觉、智力/感知/魅力豁免有优势，血脉再送戏法与法术。",
        summary_en="Small magical tinkerers with darkvision, advantage on Intelligence, "
                   "Wisdom and Charisma saves, and lineage spells.",
        traits=[
            darkvision(60),
            ("gnomish_cunning", "侏儒狡黠", "Gnomish Cunning", 1,
             "你对智力、感知、魅力豁免检定有优势。",
             [{"grant_advantage": {"target": "save.int", "mode": "adv"}},
              {"grant_advantage": {"target": "save.wis", "mode": "adv"}},
              {"grant_advantage": {"target": "save.cha", "mode": "adv"}}], ""),
            ("gnomish_lineage", "侏儒血脉", "Gnomish Lineage", 1,
             "选择森林侏儒（戏法 次级幻影；动物交谈 始终备好并可用熟练加值次数免费施放）"
             "或岩地侏儒（戏法 修复术 与 魔法伎俩）。",
             [], "物种法术来源与免费施放次数池尚未接入。"),
        ],
    ),
    dict(
        id="goliath", zh="巨人", en="Goliath",
        size=["medium"], speed=35, srd=True,
        summary_zh="山岭巨人的后裔：跑得更快、力气更大，血统与巨躯形态各给一段爆发。",
        summary_en="Descendants of giants: faster on their feet, powerful of build, "
                   "with a giant ancestry boon and a large-form burst.",
        traits=[
            ("giant_ancestry", "巨人血统", "Giant Ancestry", 1,
             "选择一种巨人血统（云/火/霜/山岭/石/风暴），获得对应的短时增益，"
             "次数等于熟练加值，长休恢复。",
             [], "六种增益各是限时效果，需要效果时长管道，尚未接入。"),
            ("powerful_build", "强力体格", "Powerful Build", 1,
             "你在结束擒抱的豁免检定上有优势。计算负重与推、拖、举的重量时，视为大体型生物。",
             [], "负重上限未在卡上计算，擒抱豁免的优势要按检定名判定，尚未接入。"),
            ("large_form", "巨躯形态", "Large Form", 5,
             "5 级起，你可以用一个附赠动作变为大体型，持续 10 分钟：力量检定有优势、"
             "速度 +10 尺。完成长休后才能再次使用。",
             [], "体型变化与限时速度需要变形/效果时长管道，尚未接入。"),
        ],
    ),
    dict(
        id="halfling", zh="半身人", en="Halfling",
        size=["small"], speed=30, srd=True,
        summary_zh="幸运的小个子：掷出 1 可以重掷，不怕吓，还能钻过大个子让出的空隙。",
        summary_en="Small and improbably lucky: reroll a 1, shrug off fear, "
                   "and slip through the space of larger creatures.",
        traits=[
            ("brave", "勇敢", "Brave", 1,
             "你对抗恐慌状态的豁免检定有优势。",
             [], "「对抗恐慌状态的豁免」要按状态来源判定，尚未接入。"),
            ("halfling_nimbleness", "半身人灵巧", "Halfling Nimbleness", 1,
             "你可以穿过体型比你大的生物所占据的空间。",
             [], "属于移动规则，尚未接入。"),
            ("luck", "幸运", "Luck", 1,
             "当你在一次 d20 检定（攻击、属性检定或豁免）中掷出 1 时，可以重掷一次，"
             "并且必须使用新结果。",
             [], "「掷出 1 时重掷」要在每次 d20 结算后挂一个重掷提示，尚未接入。"),
            ("naturally_stealthy", "天生隐匿", "Naturally Stealthy", 1,
             "当有至少一个体型比你大的生物遮蔽你时，你可以尝试躲藏。",
             [], "属于躲藏条件判定，尚未接入。"),
        ],
    ),
    dict(
        id="human", zh="人类", en="Human",
        size=["medium", "small"], speed=30, srd=True,
        summary_zh="什么都会一点：长休后拿到英雄激励、多一项技能熟练、多一个起源专长。",
        summary_en="Adaptable generalists: Heroic Inspiration after every long rest, "
                   "an extra skill proficiency, and an extra Origin feat.",
        traits=[
            ("resourceful", "足智多谋", "Resourceful", 1,
             "你每次完成长休后获得英雄激励。",
             [], "英雄激励是休整流程的产物，尚未接入。"),
            ("skillful", "多才多艺", "Skillful", 1,
             "你获得一项自选技能的熟练。",
             [], "这一项是玩家选择，可在建卡时作为额外熟练登记；物种特性本身不自动给。"),
            ("versatile", "全能", "Versatile", 1,
             "你获得一个自选的起源专长。",
             [], "专长选择走专长通道，建卡时在专长页挑一个即可；物种特性本身不重复给。"),
        ],
    ),
    dict(
        id="orc", zh="兽人", en="Orc",
        size=["medium"], speed=30, srd=True,
        summary_zh="为冲撞而生：黑暗视觉 120 尺、附赠动作冲刺带临时生命、倒下了还能硬撑一次。",
        summary_en="Built to charge: superior darkvision, a bonus-action rush with Temporary "
                   "Hit Points, and one refusal to fall.",
        traits=[
            ("adrenaline_rush", "肾上腺素冲刺", "Adrenaline Rush", 1,
             "以一个附赠动作，你可以冲刺，并获得等于熟练加值的临时生命值。"
             "次数等于熟练加值，短休或长休恢复。",
             [], "临时生命值按熟练加值取数，需要一个「按加值给临时 HP」的入口，尚未接入。"),
            darkvision(120),
            ("relentless_endurance", "坚韧不屈", "Relentless Endurance", 1,
             "当你的生命值将降为 0 而不是直接死亡时，你可以改为降到 1 点。"
             "完成长休后才能再次使用。",
             [], "「将降为 0 时改为 1」要在伤害结算处插一个钩子，尚未接入。"),
        ],
    ),
    dict(
        id="tiefling", zh="提夫林", en="Tiefling",
        size=["medium", "small"], speed=30, srd=True,
        summary_zh="下界血脉的凡人：黑暗视觉、奇术戏法，炼狱血脉再给一份抗性与两个法术。",
        summary_en="Mortals touched by the Lower Planes: darkvision, the Thaumaturgy cantrip, "
                   "and a fiendish legacy of resistance and spells.",
        traits=[
            darkvision(60),
            ("otherworldly_presence", "异界威仪", "Otherworldly Presence", 1,
             "你习得戏法 奇术（Thaumaturgy），施法属性为魅力。",
             [], "物种法术来源尚未接入。"),
            ("fiendish_legacy", "炼狱血脉", "Fiendish Legacy", 1,
             "选择深渊（毒素抗性；戏法 毒液喷溅，3 级 致病射线，5 级 人类定身）、"
             "幽冥（黯蚀抗性；戏法 冻寒之触，3 级 虚假生命，5 级 衰弱射线）或"
             "炼狱（火焰抗性；戏法 火焰箭，3 级 炼狱叱喝，5 级 黑暗术）。",
             [], "抗性跟随选择、法术按等级解锁，需要血统选择与物种法术通道，尚未接入。"),
        ],
    ),
]


def render_species(row: dict) -> str:
    ident = "dnd2024.species.%s" % row["id"]
    out = header("dnd55e_core_data.json 的 species 清单只用来确认条目，正文按 2024 原文重写",
                 row["srd"])
    out += [
        "",
        "id: %s" % ident,
        "name: %s" % flow([("zh", row["zh"]), ("en", row["en"])]),
        "summary:",
        "  zh: " + block(row["summary_zh"], 4),
        "  en: " + block(row["summary_en"], 4),
        "size: %s" % _scalar(row["size"]),
        "speed: %d" % row["speed"],
        "",
        "powers:",
    ]
    for key, zh_name, en_name, level, text, effects, unsettled in row["traits"]:
        out += [
            "  - id: %s.%s" % (ident, key),
            "    name: %s" % flow([("zh", zh_name), ("en", en_name)]),
            "    level: %d" % level,
            "    kind: passive",
            "    target: self",
            "    text:",
            "      zh: " + block(text, 8),
            "      en: " + block(NO_ENGLISH % en_name, 8),
            "    effects:",
        ]
        out += render_effects(effects)
        if unsettled:
            out += render_note(unsettled,
                               "The mechanical part of this trait is not wired yet; "
                               "the rule text above is the source.")
        elif not effects:
            out += render_note("本条只登记规则原文，没有可结算的数值。",
                               "This trait carries no numeric effect.")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# --- 背景 -------------------------------------------------------------
# 16 个背景的中文摘要（作者自述，不是规则原文）
BACKGROUND_ZH = {
    "acolyte": "在神庙里长大，替神明跑腿、抄经、安抚信徒。",
    "artisan": "靠一门手艺吃饭：锻、织、木、陶，你挑一样拿得出手的。",
    "charlatan": "把假身份穿在身上，靠一张嘴和一双快手活到今天。",
    "criminal": "在黑的那一面有熟人，知道哪扇门不上锁。",
    "entertainer": "台上三分钟，台下十年功 —— 你走到哪儿都能把场子热起来。",
    "farmer": "土地教会你耐心、力气，以及怎么跟牲口打交道。",
    "guard": "站过岗、巡过夜、见过事，知道该先看哪一眼。",
    "guide": "你把荒野当自家后院，认得路、认得天、认得脚印。",
    "hermit": "离开人群很久，回来时带了一身没人听得懂的道理。",
    "merchant": "讨价还价是你的母语，账本比剑更常用。",
    "noble": "出身给了你名号、义务，和一群等着看你笑话的人。",
    "sage": "书堆里泡大的：你读过的东西，比大多数人见过的多。",
    "sailor": "在甲板上站过风暴，绳子与风向比地面更让你安心。",
    "scribe": "抄、校、归档：你眼里的错字比别人的多一倍。",
    "soldier": "军队教会你三件事：队形、服从，以及怎么活下来。",
    "wayfarer": "你一直在路上，靠打零工与看人脸色吃饭。",
}

BACKGROUND_EN = {
    "acolyte": "Raised in a temple, running errands for a god and copying its texts.",
    "artisan": "You live by a craft — smithing, weaving, wood or clay — and you are good at it.",
    "charlatan": "You wear a false name well, and live on a quick tongue and quicker hands.",
    "criminal": "You know the other side of the city, and which doors are never locked.",
    "entertainer": "You can warm a room in three minutes; the practice took ten years.",
    "farmer": "The land taught you patience, strength, and how to handle animals.",
    "guard": "You have stood watch, walked the night rounds, and seen enough to know what to check first.",
    "guide": "The wild is your backyard: you read trails, weather and tracks.",
    "hermit": "You left people behind for a long time, and came back with ideas nobody shares.",
    "merchant": "Haggling is your first language; the ledger sees more use than the sword.",
    "noble": "Birth gave you a title, a duty, and a crowd waiting for you to fail.",
    "sage": "Raised among books: you have read more than most people have seen.",
    "sailor": "You have stood a deck through a storm; rope and wind feel safer than ground.",
    "scribe": "Copy, collate, file: you spot twice as many errors as anyone else.",
    "soldier": "The army taught you three things: formation, obedience, and how to survive.",
    "wayfarer": "Always on the road, living on odd jobs and reading faces.",
}

# 起始专长的英文名（旧数据里是显示名）→ 内容 id 片段
FEAT_IDS = {
    "alert": "alert",
    "crafter": "crafter",
    "healer": "healer",
    "lucky": "lucky",
    "musician": "musician",
    "savage attacker": "savage_attacker",
    "skilled": "skilled",
    "tough": "tough",
    "tavern brawler": "tavern_brawler",
    "magic initiate (cleric)": "magic_initiate_cleric",
    "magic initiate (druid)": "magic_initiate_druid",
    "magic initiate (wizard)": "magic_initiate_wizard",
}

# 工具：显示名 → 插件里的工具 key（None = 这一类要玩家自选具体工具，没有固定 key）
TOOL_KEYS = {
    "calligrapher's supplies": "calligraphers_supplies",
    "carpenter's tools": "carpenters_tools",
    "cartographer's tools": "cartographer_tools",
    "navigator's tools": "navigators_tools",
    "thieves' tools": "thieves_tools",
    "forgery kit": "forgery_kit",
    "herbalism kit": "herbalism_kit",
    "gaming set": None,
    "gambling set": None,
    "musical instrument": None,
    "artisan's tools": None,
}

TOOL_ZH = {
    "calligrapher's supplies": "书法工具",
    "carpenter's tools": "木工工具",
    "cartographer's tools": "制图工具",
    "navigator's tools": "航海工具",
    "thieves' tools": "盗贼工具",
    "forgery kit": "伪造工具",
    "herbalism kit": "草药工具",
    "gaming set": "博弈用具（自选一种）",
    "gambling set": "赌具（自选一种）",
    "musical instrument": "乐器（自选一种）",
    "artisan's tools": "工匠工具（自选一种）",
}

SRD_BACKGROUNDS = {"acolyte", "criminal", "sage", "soldier"}


def render_background(row: dict) -> str:
    ident = "dnd2024.background.%s" % row["id"]
    abilities = [item.lower() for item in row["abilities"]]
    feat_key = FEAT_IDS[row["origin_feat"].lower()]
    tool_key = TOOL_KEYS[row["tool"].lower()]
    tool_zh = TOOL_ZH[row["tool"].lower()]
    srd = row["id"] in SRD_BACKGROUNDS
    out = header("dnd55e_core_data.json 的 backgrounds 条目（属性/专长/技能/工具均已核对）", srd)
    out += [
        "",
        "id: %s" % ident,
        "name: %s" % flow([("zh", row["zh"]), ("en", row["en"])]),
        "summary:",
        "  zh: " + block(BACKGROUND_ZH[row["id"]], 4),
        "  en: " + block(BACKGROUND_EN[row["id"]], 4),
        "abilities: %s" % _scalar(abilities),
        "origin_feat: dnd2024.feat.%s" % feat_key,
        "skills: %s" % _scalar(row["skills"]),
        "tool: %s" % (tool_key if tool_key else ""),
        "tool_label: %s" % flow([("zh", tool_zh), ("en", row["tool"])]),
    ]
    if tool_key is None:
        out.append("# 这一类工具不固定具体物件（原文写的是「自选一种」），故 tool 留空："
                   "不登记熟练 token，只在卡上显示类别。")
    return "\n".join(out).rstrip() + "\n"


# --- 主程序 -----------------------------------------------------------
def load_backgrounds() -> list[dict]:
    data = json.loads((ROOT / "dnd55e_core_data.json").read_text(encoding="utf-8"))
    rows = []
    for item in data["backgrounds"]:
        zh_full = item["name"]
        en = zh_full.split()[-1] if zh_full.split() else ""
        zh = zh_full[:len(zh_full) - len(en)].strip() or zh_full
        rows.append(dict(id=item["id"], zh=zh, en=en,
                         abilities=item["abilities"], origin_feat=item["origin_feat"],
                         skills=item["skills"], tool=item["tool"]))
    return rows


def write(path: Path, text: str, force: bool, only: set[str] | None) -> str:
    if only and path.stem not in only:
        return "skip"
    if path.exists():
        if "# hand-edited" in path.read_text(encoding="utf-8"):
            return "hand"
        if not force:
            return "exists"
    path.write_text(text, encoding="utf-8")
    return "written"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 10 物种 + 16 背景的插件 YAML")
    parser.add_argument("--only", nargs="*", default=None, help="只生成这些条目（按 id 片段）")
    parser.add_argument("--force", action="store_true", help="覆盖已生成的文件")
    args = parser.parse_args(argv)
    only = set(args.only) if args.only else None

    OUT_SPECIES.mkdir(parents=True, exist_ok=True)
    OUT_BACKGROUNDS.mkdir(parents=True, exist_ok=True)

    stats: dict[str, list[str]] = {}
    for row in SPECIES:
        path = OUT_SPECIES / ("%s.yaml" % row["id"])
        state = write(path, render_species(row), args.force, only)
        stats.setdefault(state, []).append("species/" + row["id"])
    for row in load_backgrounds():
        path = OUT_BACKGROUNDS / ("%s.yaml" % row["id"])
        state = write(path, render_background(row), args.force, only)
        stats.setdefault(state, []).append("backgrounds/" + row["id"])

    for state, label in (("written", "生成"), ("exists", "跳过（已存在，加 --force 覆盖）"),
                         ("hand", "跳过（已手改）")):
        if state in stats:
            print("%s：%s" % (label, "、".join(stats[state])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
