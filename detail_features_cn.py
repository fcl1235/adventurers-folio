#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""职业特性 / 资源池的中文释义（构建期数据，运行时由 dnd55e_classes_detail.json 提供）。

键 = SRD 5.2 features 的 index；值 = (中文名, 一句话效果)。
效果文字尽量保留规则关键数值，界面里鼠标停靠或展开即可看到。
"""

FEATURE_CN = {
    # ---------------- 野蛮人 ----------------
    "barbarian-rage": ("狂暴 Rage",
                       "附赠动作进入狂暴（不穿重甲）：钝击/穿刺/挥砍抗性、力量攻击伤害加值、"
                       "力量检定与豁免优势。次数见「职业资源」。"),
    "barbarian-unarmored-defense": ("无甲防御",
                                    "未穿护甲时 AC = 10 + 敏捷调整值 + 体质调整值（可用盾牌）。"),
    "barbarian-weapon-mastery": ("武器专精",
                                 "选 2 件熟练武器启用其专精属性（数量随等级提升）。"),
    "barbarian-danger-sense": ("危险感知",
                               "未失能时，对可见危险（陷阱、法术等）的敏捷豁免有优势。"),
    "barbarian-reckless-attack": ("鲁莽攻击",
                                  "本回合首次力量攻击可选择优势；代价是到你下回合开始前，"
                                  "对你也全部有优势。"),
    "barbarian-subclass": ("子职：道途",
                           "3 级选择一个道途（子职），获得其 3 级特性。"),
    "barbarian-primal-knowledge": ("原始知识",
                                   "额外获得 1 项技能熟练（驯兽/威吓/自然/察觉/生存）；"
                                   "狂暴时可用力量代替该检定的属性。"),
    "barbarian-ability-score-improvement": ("属性提升 / 专长",
                                            "属性 +2/+1（或 +1/+1/+1，上限 20），或换 1 个专长。"),
    "barbarian-extra-attack": ("额外攻击", "执行攻击动作时可攻击 2 次。"),
    "barbarian-fast-movement": ("快速移动", "不穿重甲时速度 +10 尺。"),
    "barbarian-feral-instinct": ("野性本能",
                                 "先攻有优势；若先攻掷出时未狂暴，可立即免费进入狂暴。"),
    "barbarian-instinctive-pounce": ("本能扑击",
                                     "进入狂暴时，可作为该附赠动作的一部分移动至多半速。"),
    "barbarian-brutal-strike": ("凶蛮打击",
                                "可放弃攻击优势，换取 +1d10 伤害并附加击退 15 尺或击倒等效果。"),
    "barbarian-relentless-rage": ("不屈狂怒",
                                  "狂暴中降到 0 HP 时，可做 DC 10 体质豁免（每次递增 5），"
                                  "成功则保持 1 HP。"),
    "barbarian-improved-brutal-strike-1": ("强化凶蛮打击",
                                           "凶蛮打击可再选一种效果（削弱目标的下次豁免等）。"),
    "barbarian-persistent-rage": ("持久狂暴",
                                  "狂暴不再需要每回合维持；长休时直接恢复全部狂暴次数。"),
    "barbarian-improved-brutal-strike-2": ("强化凶蛮打击（17 级）",
                                           "凶蛮打击的额外伤害提升到 2d10。"),
    "barbarian-indomitable-might": ("不屈之力",
                                    "力量检定可把 d20 结果视为你的力量值（不掷骰）。"),
    "barbarian-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "barbarian-primal-champion": ("原始冠军",
                                  "力量与体质各 +4，上限提升到 25。"),

    # ---------------- 吟游诗人 ----------------
    "bard-bardic-inspiration": ("吟游诗人灵感",
                                "附赠动作给 60 尺内一名生物一颗灵感骰（d6；5/10/15 级"
                                "升为 d8/d10/d12），1 小时内一次 d20 检定失败可加上骰值。"
                                "次数 = 魅力调整值（至少 1），5 级起短休也全恢复。"),
    "bard-spellcasting": ("施法", "以魅力施法，法术列表见吟游诗人。"),
    "bard-expertise": ("专精", "选 2 项已熟练的技能，熟练加值翻倍。"),
    "bard-jack-of-all-trades": ("万事通",
                                "任何未熟练的属性检定，加一半熟练加值（向下取整）。"),
    "bard-subclass": ("子职：学院", "3 级选择一个学院（子职）。"),
    "bard-ability-score-improvement": ("属性提升 / 专长",
                                       "属性 +2/+1（上限 20），或换 1 个专长。"),
    "bard-font-of-inspiration": ("灵感泉源", "短休后也能恢复全部灵感次数。"),
    "bard-countercharm": ("反迷惑",
                          "反应：30 尺内你或友军对魅惑/恐慌的豁免失败时，可重掷。"),
    "bard-magical-secrets": ("魔法秘密",
                             "从任意职业法术列表中选 2 个法术，视为吟游诗人法术常备。"),
    "bard-superior-inspiration": ("卓越灵感",
                                  "掷先攻时若没有灵感次数，立刻获得 1 次。"),
    "bard-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "bard-words-of-creation": ("创世之言",
                               "可免费施放 Power Word Heal 与 Power Word Kill 各 1 次/长休。"),

    # ---------------- 牧师 ----------------
    "cleric-divine-order": ("神圣职阶",
                            "二选一：保护者（军用武器 + 重甲熟练）或 施法者（额外 1 个戏法，"
                            "宗教检定可用智力）。"),
    "cleric-spellcasting": ("施法", "以感知施法，长休后准备法术。"),
    "cleric-channel-divinity": ("引导神力",
                                "神圣火花（治疗或造成光耀/死灵伤害）与驱散不死；"
                                "2 级 2 次、6 级 3 次、18 级 4 次，短休恢复 1 次。"),
    "cleric-subclass": ("子职：领域", "3 级选择一个领域（子职）。"),
    "cleric-ability-score-improvement": ("属性提升 / 专长",
                                         "属性 +2/+1（上限 20），或换 1 个专长。"),
    "cleric-sear-undead": ("灼烧不死",
                           "驱散不死时，豁免失败的不死生物额外受光耀伤害。"),
    "cleric-blessed-strikes": ("祝福打击",
                               "戏法或武器攻击命中时，额外造成 1d8 光耀或死灵伤害（二选一）。"),
    "cleric-divine-intervention": ("神意干预",
                                   "无需法术位与材料，直接施放 1 个 5 环以下牧师法术（1 次/长休）。"),
    "cleric-improved-blessed-strikes": ("强化祝福打击",
                                        "祝福打击的额外伤害提升到 2d8。"),
    "cleric-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "cleric-greater-divine-intervention": ("强效神意干预",
                                           "可施放 Wish；之后 2d4 天内不能再用。"),

    # ---------------- 德鲁伊 ----------------
    "druid-druidic": ("德鲁伊语", "掌握德鲁伊秘密语言，并自带动物交谈。"),
    "druid-primal-order": ("原始职阶",
                           "二选一：魔术师（额外 1 个戏法，自然检定可用智力）"
                           "或 守护者（军用武器 + 中甲熟练）。"),
    "druid-spellcasting": ("施法", "以感知施法，长休后准备法术。"),
    "druid-wild-shape": ("荒野变形",
                         "附赠动作变为已学会的野兽形态，持续「德鲁伊等级一半」小时；"
                         "2 级 2 次、6 级 3 次、17 级 4 次，短休恢复 1 次。"),
    "druid-wild-companion": ("荒野伙伴",
                             "可消耗 1 次荒野变形次数，施放 Find Familiar 召出魔宠。"),
    "druid-subclass": ("子职：结社", "3 级选择一个结社（子职）。"),
    "druid-ability-score-improvement": ("属性提升 / 专长",
                                        "属性 +2/+1（上限 20），或换 1 个专长。"),
    "druid-wild-resurgence": ("荒野复苏",
                              "可消耗 1 个法术位换回 1 次荒野变形（1 次/长休）。"),
    "druid-elemental-fury": ("元素之怒",
                             "戏法与野兽攻击额外 +1d8 元素伤害；或让 10 尺内目标受伤。"),
    "druid-improved-elemental-fury": ("强化元素之怒",
                                      "所选元素之怒强化：强力施法（10 尺以上射程的"
                                      "德鲁伊戏法 +300 尺）/ 原始打击（额外伤害升到 2d8）。"),
    "druid-beast-spells": ("野兽施法", "野兽形态下也能施放法术。"),
    "druid-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "druid-archdruid": ("大德鲁伊",
                        "荒野变形次数恢复更灵活，并且衰老速度变为每 10 年 1 岁。"),

    # ---------------- 战士 ----------------
    "fighter-fighting-style": ("战斗风格",
                               "从战斗风格专长中选 1 个（仅战士/圣武士/游侠拥有此特性）。"),
    "fighter-second-wind": ("回气",
                            "附赠动作恢复 1d10 + 战士等级 的 HP；次数见「职业资源」，"
                            "短休恢复 1 次。"),
    "fighter-weapon-mastery": ("武器专精",
                               "选 3 件熟练武器启用其专精属性（数量随等级提升）。"),
    "fighter-action-surge": ("行动激增",
                             "本回合额外获得 1 个动作（不能是魔法动作）；短休或长休后恢复。"),
    "fighter-tactical-mind": ("战术思维",
                              "检定失败时消耗 1 次回气，加 1d10（可能翻盘）。"),
    "fighter-subclass": ("子职", "3 级选择一个子职。"),
    "fighter-ability-score-improvement": ("属性提升 / 专长",
                                          "属性 +2/+1（上限 20），或换 1 个专长。"),
    "fighter-extra-attack": ("额外攻击", "攻击动作可攻击 2 次。"),
    "fighter-tactical-shift": ("战术转移",
                               "使用回气时，可移动至多半速且不引发借机攻击。"),
    "fighter-indomitable": ("不屈",
                            "豁免失败可重掷并加战士等级加值；次数见「职业资源」（长休恢复）。"),
    "fighter-tactical-master": ("战术大师",
                                "武器专精可临时改为 Push / Sap / Slow。"),
    "fighter-two-extra-attacks": ("双重额外攻击", "攻击动作可攻击 3 次。"),
    "fighter-studied-attacks": ("研究攻击",
                                "连续两次攻击同一目标时，若上次失手，本次有优势。"),
    "fighter-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "fighter-three-extra-attacks": ("三重额外攻击", "攻击动作可攻击 4 次。"),

    # ---------------- 武僧 ----------------
    "monk-martial-arts": ("武艺",
                          "徒手与武僧武器可用敏捷代替力量，伤害骰随等级提升；"
                          "攻击动作后可附赠动作再打 1 次。"),
    "monk-unarmored-defense": ("无甲防御",
                               "无甲且无盾时 AC = 10 + 敏捷 + 感知调整值。"),
    "monk-monks-focus": ("气",
                         "气点数量 = 武僧等级；可用于 疾风连击 /  Patient Defense / "
                         "Step of the Wind。短休或长休全部恢复。"),
    "monk-unarmored-movement": ("无甲移动",
                                "无甲且无盾时速度提升（数值见职业表，10 级起可垂直移动）。"),
    "monk-uncanny-metabolism": ("奇异代谢",
                                "掷先攻时回满气点并回复 1 个生命骰（1 次/长休）。"),
    "monk-subclass": ("子职：宗派", "3 级选择一个宗派（子职）。"),
    "monk-deflect-attacks": ("拨挡攻击",
                             "反应：减免 1d10+敏捷+等级 的钝/穿/砍伤害；减至 0 可花 1 气点反掷。"),
    "monk-ability-score-improvement": ("属性提升 / 专长",
                                       "属性 +2/+1（上限 20），或换 1 个专长。"),
    "monk-slow-fall": ("轻身坠",
                       "反应：减少 5 × 武僧等级 的坠落伤害。"),
    "monk-extra-attack": ("额外攻击", "攻击动作可攻击 2 次。"),
    "monk-stunning-strike": ("震慑打击",
                             "命中后花 1 气点：目标体质豁免，失败则被震慑到你的下回合。"),
    "monk-empowered-strikes": ("强化打击",
                               "徒手打击可造成力场伤害，无视对钝击的抵抗。"),
    "monk-evasion": ("闪避",
                     "敏捷豁免成功则不受伤害，失败只受一半。"),
    "monk-acrobatic-movement": ("杂技移动",
                                "战斗中可在垂直面或液面上移动而不坠落。"),
    "monk-heightened-focus": ("专注强化",
                              "疾风连击 3 次攻击、闪避附带移动、疾行可带一名同伴。"),
    "monk-self-restoration": ("自我恢复",
                              "每回合结束自动解除 1 项：魅惑、恐慌、中毒。"),
    "monk-deflect-energy": ("拨挡能量",
                            "拨挡攻击可用于任意伤害类型（含火焰、力场）。"),
    "monk-disciplined-survivor": ("自律生还者",
                                  "获得全部豁免的熟练；豁免失败时可花 1 气点重掷"
                                  "（必须采用新结果）。"),
    "monk-perfect-focus": ("完美专注",
                           "掷先攻时若气点为 0，立刻恢复 4 点。"),
    "monk-superior-defense": ("卓越防御",
                              "附赠动作花 3 气点：1 分钟内对所有伤害有抗性。"),
    "monk-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "monk-body-and-mind": ("身心合一", "敏捷与感知各 +4，上限提升到 25。"),

    # ---------------- 圣武士 ----------------
    "paladin-lay-on-hands": ("圣疗",
                             "治疗池 = 5 × 圣武士等级（长休回满）；附赠动作治疗，"
                             "或花 5 点解除中毒。"),
    "paladin-spellcasting": ("施法", "以魅力施法（1 级起即有法术位）。"),
    "paladin-weapon-mastery": ("武器专精", "选 2 件熟练武器启用其专精属性。"),
    "paladin-fighting-style": ("战斗风格",
                               "2 级：从战斗风格专长中选 1 个。"),
    "paladin-paladins-smite": ("圣武士斩击",
                               "命中后可消耗 1 个法术位追加 2d8 光耀伤害（每回合 1 次）。"),
    "paladin-channel-divinity": ("引导神力",
                                 "神圣感知与子职效果；3 级 2 次、11 级 3 次，"
                                 "短休恢复 1 次。"),
    "paladin-subclass": ("子职：誓约", "3 级选择一个誓约（子职）。"),
    "paladin-ability-score-improvement": ("属性提升 / 专长",
                                          "属性 +2/+1（上限 20），或换 1 个专长。"),
    "paladin-extra-attack": ("额外攻击", "攻击动作可攻击 2 次。"),
    "paladin-faithful-steed": ("忠诚坐骑",
                               "可免费施放 Find Steed（1 次/长休，无需材料）。"),
    "paladin-aura-of-protection": ("守护灵光",
                                   "10 尺灵光内，你与友军的豁免 + 魅力调整值。"),
    "paladin-abjure-foes": ("斥退敌人",
                            "引导神力：30 尺内敌人感知豁免，失败则恐慌 1 分钟。"),
    "paladin-aura-of-courage": ("勇气灵光", "灵光内友军免疫恐慌。"),
    "paladin-radiant-strikes": ("光耀打击",
                                "武器或徒手命中额外 +1d8 光耀伤害。"),
    "paladin-restoring-touch": ("恢复之触",
                                "圣疗可额外解除中毒、疾病、麻痹、目盲、失聪等。"),
    "paladin-aura-expansion": ("灵光扩张", "守护灵光 / 勇气灵光范围扩大到 30 尺。"),
    "paladin-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),

    # ---------------- 游侠 ----------------
    "ranger-favored-enemy": ("宿敌",
                             "始终准备 Hunter's Mark，可不耗法术位施放 2 次；"
                             "5/9/13/17 级增至 3/4/5/6 次，长休全部恢复。"),
    "ranger-spellcasting": ("施法", "以感知施法。"),
    "ranger-weapon-mastery": ("武器专精", "选 2 件熟练武器启用其专精属性。"),
    "ranger-deft-explorer": ("灵巧探索者",
                             "1 项技能专精，并额外掌握 2 门语言。"),
    "ranger-fighting-style": ("战斗风格",
                              "2 级：从战斗风格专长中选 1 个。"),
    "ranger-subclass": ("子职", "3 级选择一个子职。"),
    "ranger-ability-score-improvement": ("属性提升 / 专长",
                                         "属性 +2/+1（上限 20），或换 1 个专长。"),
    "ranger-extra-attack": ("额外攻击", "攻击动作可攻击 2 次。"),
    "ranger-roving": ("游荡",
                      "不穿重甲时速度 +10 尺；攀爬与游泳速度等于你的速度。"),
    "ranger-expertise": ("专精", "再选 2 项已熟练技能，熟练加值翻倍。"),
    "ranger-tireless": ("不倦",
                        "附赠动作给自己 1d8 + 感知调整值 的临时 HP；短休可减 1 级力竭。"),
    "ranger-relentless-hunter": ("无情猎手",
                                 "受到伤害时，为维持 Hunter's Mark 的专注豁免自动成功。"),
    "ranger-natures-veil": ("自然面纱",
                            "附赠动作变为隐形，持续到你的下回合结束。"),
    "ranger-precise-hunter": ("精准猎手",
                              "对 Hunter's Mark 目标的攻击有优势。"),
    "ranger-feral-senses": ("野性感官",
                            "可察觉 30 尺内的隐形生物，且看不见时攻击不再有劣势。"),
    "ranger-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "ranger-foe-slayer": ("灭敌者",
                          "Hunter's Mark 的额外伤害骰从 d6 提升为 d10。"),

    # ---------------- 游荡者 ----------------
    "rogue-expertise": ("专精", "选 2 项已熟练技能，熟练加值翻倍。"),
    "rogue-sneak-attack": ("偷袭",
                           "每回合 1 次：有优势或目标旁边有你的盟友时，额外造成伤害（见职业表）。"),
    "rogue-thieves-cant": ("盗贼黑话", "掌握盗贼暗语与暗号。"),
    "rogue-weapon-mastery": ("武器专精", "选 2 件熟练武器启用其专精属性。"),
    "rogue-cunning-action": ("灵巧动作",
                             "附赠动作执行 疾行 / 撤离 / 躲藏。"),
    "rogue-subclass": ("子职", "3 级选择一个子职。"),
    "rogue-steady-aim": ("稳定瞄准",
                         "附赠动作：本回合攻击有优势，但速度归 0（不能移动）。"),
    "rogue-ability-score-improvement": ("属性提升 / 专长",
                                        "属性 +2/+1（上限 20），或换 1 个专长。"),
    "rogue-cunning-strike": ("灵巧打击",
                             "可牺牲 1d6 偷袭骰换取效果：中毒、绊倒、撤离等。"),
    "rogue-uncanny-dodge": ("直觉闪避",
                            "反应：把一次攻击的伤害减半。"),
    "rogue-evasion": ("闪避", "敏捷豁免成功不受伤害，失败只受一半。"),
    "rogue-reliable-talent": ("可靠天赋",
                              "熟练技能的检定，d20 掷出 9 或以下按 10 计算。"),
    "rogue-improved-cunning-strike": ("强化灵巧打击",
                                      "灵巧打击可同时施加 2 种效果（多付偷袭骰）。"),
    "rogue-devious-strikes": ("诡诈打击",
                              "灵巧打击新增高阶选项：眩晕(2d6)、遮蔽(3d6)、"
                              "击昏(6d6)，代价从偷袭骰里扣。"),
    "rogue-slippery-mind": ("滑溜心智", "获得感知与魅力豁免熟练。"),
    "rogue-elusive": ("飘忽不定",
                      "未被失能时，任何攻击对你都没有优势。"),
    "rogue-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "rogue-stroke-of-luck": ("幸运一击",
                             "检定失败可改为 20，或攻击失手改为命中（1 次/短休）。"),

    # ---------------- 术士 ----------------
    "sorcerer-innate-sorcery": ("先天魔法",
                                "附赠动作，1 分钟内术士法术豁免 DC +1、"
                                "法术攻击掷骰有优势（2 次/长休，全部次数随长休恢复）。"),
    "sorcerer-spellcasting": ("施法", "以魅力施法，已知法术。"),
    "sorcerer-font-of-magic": ("魔法源泉",
                               "术法点数量 = 术士等级；可在法术位与术法点之间互换。"),
    "sorcerer-metamagic": ("超魔法",
                           "2 级选 2 个超魔法选项（法术强化、孪生、瞬发等），"
                           "10 级与 17 级各再 +2；使用需付术法点，每个法术只能用 1 个。"),
    "sorcerer-subclass": ("子职：血脉", "3 级选择一个血脉（子职）。"),
    "sorcerer-ability-score-improvement": ("属性提升 / 专长",
                                           "属性 +2/+1（上限 20），或换 1 个专长。"),
    "sorcerer-sorcerous-restoration": ("魔法恢复",
                              "短休时恢复不超过「术士等级一半(向下取整)」点术法点，"
                              "1 次/长休。"),
    "sorcerer-sorcery-incarnate": ("魔法化身",
                                   "先天魔法次数用完时，可花 2 点术法点激活；"
                                   "先天魔法期间每个法术可同时应用 2 个超魔法。"),
    "sorcerer-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "sorcerer-arcane-apotheosis": ("奥术神化",
                                   "先天魔法期间，每回合可免费使用 1 个超魔法"
                                   "（不消耗术法点）。"),

    # ---------------- 邪术师 ----------------
    "warlock-eldritch-invocations": ("魔能祈唤",
                                     "选择魔能祈唤（数量见职业表），如 痛苦冲击、魔鬼视界 等。"),
    "warlock-pact-magic": ("契约魔法",
                           "契约法术位数量少但全部为最高环，短休即恢复。"),
    "warlock-magical-cunning": ("魔法狡黠",
                                "1 分钟仪式恢复一半契约法术位（1 次/长休）。"),
    "warlock-subclass": ("子职：宗主", "3 级选择一个宗主（子职）。"),
    "warlock-ability-score-improvement": ("属性提升 / 专长",
                                          "属性 +2/+1（上限 20），或换 1 个专长。"),
    "warlock-contact-patron": ("联络宗主",
                               "可免费施放 Contact Other Plane（1 次/长休）。"),
    "warlock-mystic-arcanum": ("秘法奥义",
                               "11/13/15/17 级各获得 1 个 6/7/8/9 环法术，各 1 次/长休。"),
    "warlock-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "warlock-eldritch-master": ("魔能大师",
                                "短休即可恢复全部契约法术位（1 次/长休）。"),

    # ---------------- 法师 ----------------
    "wizard-arcane-recovery": ("奥术回想",
                               "短休时恢复总环级不超过「一半法师等级（向上取整）」的法术位，"
                               "且不含 6 环以上；1 次/长休。"),
    "wizard-ritual-adept": ("仪式大师",
                            "法术书中的仪式法术可不准备直接仪式施放。"),
    "wizard-spellcasting": ("施法", "以智力施法，法术书写入法术。"),
    "wizard-scholar": ("学者",
                       "选 1 项知识技能专精（奥秘/历史/调查/自然/宗教），抄录法术更快更省。"),
    "wizard-subclass": ("子职：学派", "3 级选择一个学派（子职）。"),
    "wizard-ability-score-improvement": ("属性提升 / 专长",
                                         "属性 +2/+1（上限 20），或换 1 个专长。"),
    "wizard-memorize-spell": ("记忆法术",
                              "短休时可替换 1 个已准备法术。"),
    "wizard-spell-mastery": ("法术精通",
                             "选 1 个 1 环与 1 个 2 环法术，可不耗法术位随意施放。"),
    "wizard-epic-boon": ("传奇恩惠", "获得 1 个传奇恩惠专长（19 级）。"),
    "wizard-signature-spells": ("招牌法术",
                                "选 2 个 3 环法术，各可免费施放 1 次/短休。"),
}

# ---------------------------------------------------------------------------
# 职业资源池
#   max:  {等级阈值: 数值} 逐档提升；或字符串公式 "level" / "5*level" / "cha_mod"
#   die:  随等级变化的骰面 {等级阈值: 骰面}
#   short: 短休恢复方式: 0 = 不恢复, 1 = 恢复 1 次, "all" = 全部恢复
#   long:  长休恢复方式: "all" = 全部恢复
#   from_level: 该资源从几级开始出现
# ---------------------------------------------------------------------------
RESOURCES = {
    "barbarian": [{
        "id": "rage", "name": "狂暴 Rage", "from_level": 1,
        "max": {1: 2, 3: 3, 6: 4, 12: 5, 17: 6},
        "short": 1, "long": "all", "icon": "🔥",
        "note": "附赠动作进入（不穿重甲）：钝/穿/砍抗性，力量攻击伤害 +2(9级+3/16级+4)，"
                "力量检定与豁免优势。短休恢复 1 次。",
    }],
    "bard": [{
        "id": "inspiration", "name": "吟游诗人灵感 Bardic Inspiration", "from_level": 1,
        "max": "cha_mod_min1", "die": {1: 6, 5: 8, 10: 10, 15: 12},
        "short": 0, "long": "all", "icon": "🎵",
        "note": "附赠动作给 60 尺内一名生物一颗灵感骰（d6→d8→d10→d12），"
                "1 小时内一次 d20 失败可加上骰值。次数 = 魅力调整值（至少 1）。"
                "5 级「灵感泉源」后短休也会全部恢复。",
        "short_after_level": 5, "short_after": "all",
    }],
    "cleric": [{
        "id": "channel", "name": "引导神力 Channel Divinity", "from_level": 2,
        "max": {2: 2, 6: 3, 18: 4},
        "short": 1, "long": "all", "icon": "✨",
        "note": "神圣火花（治疗或光耀/死灵伤害）与驱散不死，子职还会追加选项。"
                "短休恢复 1 次。",
    }],
    "druid": [{
        "id": "wildshape", "name": "荒野变形 Wild Shape", "from_level": 2,
        "max": {2: 2, 6: 3, 17: 4},
        "short": 1, "long": "all", "icon": "🐺",
        "note": "附赠动作变为已学会的野兽形态，持续「等级一半」小时。短休恢复 1 次。",
    }],
    "fighter": [
        {"id": "second_wind", "name": "回气 Second Wind", "from_level": 1,
         "max": {1: 2, 4: 3, 10: 4}, "short": 1, "long": "all", "icon": "💨",
         "note": "附赠动作恢复 1d10 + 战士等级 的 HP。短休恢复 1 次。"},
        {"id": "action_surge", "name": "行动激增 Action Surge", "from_level": 2,
         "max": {2: 1, 17: 2}, "short": "all", "long": "all", "icon": "⚡",
         "note": "本回合额外 1 个动作（不能是魔法动作）；17 级起每长休 2 次，"
                 "但一回合只能用 1 次。短休或长休全部恢复。"},
        {"id": "indomitable", "name": "不屈 Indomitable", "from_level": 9,
         "max": {9: 1, 13: 2, 17: 3}, "short": 0, "long": "all", "icon": "🗿",
         "note": "豁免失败可重掷并加战士等级加值，必须接受新结果。长休全部恢复。"},
    ],
    "monk": [{
        "id": "focus", "name": "气 Focus Points", "from_level": 2,
        "max": "level", "short": "all", "long": "all", "icon": "☯",
        "note": "气点 = 武僧等级。疾风连击 1 点、Patient Defense 1 点、"
                "Step of the Wind 1 点、震慑打击 1 点。短休或长休全部恢复。",
    }],
    "paladin": [
        {"id": "lay_on_hands", "name": "圣疗 Lay On Hands", "from_level": 1,
         "max": "5*level", "short": 0, "long": "all", "icon": "🕊",
         "note": "治疗池 = 5 × 圣武士等级（长休回满）。附赠动作治疗，"
                 "或花 5 点解除中毒。"},
        {"id": "channel", "name": "引导神力 Channel Divinity", "from_level": 3,
         "max": {3: 2, 11: 3}, "short": 1, "long": "all", "icon": "✨",
         "note": "神圣感知与子职效果。短休恢复 1 次。"},
    ],
    "ranger": [{
        "id": "favored_enemy", "name": "宿敌（免环 Hunter's Mark）", "from_level": 1,
        "max": {1: 2, 5: 3, 9: 4, 13: 5, 17: 6}, "short": 0, "long": "all",
        "icon": "🏹",
        "note": "Hunter's Mark 始终准备；可不耗法术位施放的次数见职业表"
                "（1级2次 / 5级3 / 9级4 / 13级5 / 17级6）；长休全部恢复。",
    }],
    "sorcerer": [{
        "id": "sorcery", "name": "术法点 Sorcery Points", "from_level": 2,
        "max": "level", "short": 0, "long": "all", "icon": "🌀",
        "note": "术法点 = 术士等级。超魔法、法术位互换都消耗它；长休全部恢复"
                "（5 级起短休可恢复一半，1 次/长休）。",
    }],
    "warlock": [{
        "id": "pact_slots", "name": "契约法术位 Pact Magic", "from_level": 1,
        "max": "pact_slots", "short": "all", "long": "all", "icon": "🔮",
        "note": "契约法术位数量少但全为最高环，短休即全部恢复。",
    }],
    "wizard": [{
        "id": "arcane_recovery", "name": "奥术回想 Arcane Recovery", "from_level": 1,
        "max": "half_level_ceil", "short": 0, "long": "all", "icon": "📖",
        "note": "每天 1 次（长休重置）：短休时恢复总环级 ≤ 一半法师等级"
                "（向上取整）的法术位，不含 6 环以上。这里的数字是可恢复的"
                "环级总量。",
    }],
}

# 每职业「资源类」的骰子提示（无资源但有关键骰的也列出来）
DICE_NOTES = {
    "monk": "武艺伤害骰 {d}（徒手/武僧武器）",
    "rogue": "偷袭 {n}d6",
    "fighter": "武器专精 {n} 件",
    "barbarian": "武器专精 {n} 件 · 狂暴伤害 +{rd}",
}
