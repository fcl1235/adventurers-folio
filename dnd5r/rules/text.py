# -*- coding: utf-8 -*-
"""规则层 / 接口层给玩家看的文案：中文原文为键，英文挂在 `EN`。

为什么需要这一层：`apps/desktop/i18n.py` 只管界面自己写的字（`T("技能")`），
但它翻不了**规则算出来的句子** —— 「要选 3 项技能，现在选了 2 项」里的 3 和 2
是算出来的，等界面拿到手时它已经是一整句格式化好的中文，按整句查表永远查不到。
所以文案必须在**格式化之前**翻译：调用点写成 `tr("要选 %d 项…", locale) % (...)`，
`tr` 先把模板换成英文，再交给 `%` 填数。

键用中文原文（不用 `skills.count` 这类编号）：
  * 改文案时不会出现「改了字忘了改键」；
  * 缺译时回退中文就是**当前这句人话**，不是一句错误码；
  * `tools/i18n_audit.py --api` 直接把两张表比对出漏译。

`locale` 一律显式传（默认 `"zh"`），与本包其它函数一致 —— 不设模块级全局语言：
全局状态会让「同一进程里两种语言并存」（例如导出英文卡同时开着中文界面）变成
看调用顺序的运气。少数深层规则函数（`spend_slot` 之类）拿不到 `locale`，它们
的报错就留在中文 —— 宁可少翻两句，不往规则里塞隐式状态。
"""

from __future__ import annotations

# 缺译的中文原文（en 下被回退成中文的那些）。审计与探针读它。
MISSING: set[str] = set()

EN: dict[str, str] = {

    # --- 建卡向导：八步的标题与提示（`api` 的 WIZARD_STEPS）----------------
    "职业": "Class",
    "先定职业与等级 —— 生命骰、豁免熟练、资源池都由它决定。":
        "Class and level come first — Hit Dice, saving throw proficiencies, "
        "and resource pools all follow from them.",
    "背景": "Background",
    "背景给三项属性各一点加值（或一项 +2 一项 +1）、两项技能、一件工具和一个起始专长。":
        "A background grants +1 to three abilities (or +2 to one and +1 to another), "
        "two skills, one tool, and a starting feat.",
    "物种": "Species",
    "物种只给特性（黑暗视觉、抗性、速度、每级生命），**不**给属性加值。":
        "Species grants traits only (Darkvision, resistances, speed, HP per level) — "
        "**not** ability bonuses.",
    "属性": "Ability Scores",
    "点买 27 点、标准数组、或掷 4d6 弃最低。上限 15 是购买上限，16 以上只能靠背景与专长。":
        "Point buy (27 points), standard array, or 4d6 drop lowest. 15 is the purchase "
        "cap; anything above 16 has to come from background and feats.",
    "技能": "Skills",
    "从本职业技能表里选；背景已经给的那几项不用重复选。":
        "Pick from your class list; skills your background already grants need not be "
        "picked again.",
    "武器精通": "Weapon Mastery",
    "从本职业熟练的武器里选。精通效果**只记录、不结算** —— 都要在命中后做选择。":
        "Choose from weapons your class is proficient with. Mastery effects are "
        "**recorded, not resolved** — each one is a choice made after a hit.",
    "法术": "Spells",
    "施法职业才需要；非施法职业这一步自动跳过。":
        "Only for spellcasting classes; skipped automatically for the rest.",
    "汇总": "Summary",
    "起个名字，然后建卡。": "Name your character, then create it.",

    # --- 建卡向导：属性生成方式（api/origin.SCORE_MODE_ZH）-----------------
    "点数购买（27 点，8–15）": "Point buy (27 points, 8–15)",
    "标准数组（15/14/13/12/10/8）": "Standard array (15/14/13/12/10/8)",
    "掷骰（4d6 弃最低）": "Roll (4d6, drop lowest)",

    # --- 建卡向导：校验（`api` 的 draft_problems）------------------------
    "不认识的建卡步骤：%r": "Unknown build step: %r",
    "还没选职业": "No class chosen yet",
    "职业等级必须在 1–20 之间：%d": "Class level must be between 1 and 20: %d",
    "没有这个子职：%s": "No such subclass: %s",
    "子职 %s 不属于这个职业": "Subclass %s does not belong to this class",
    "%d 级还选不了子职（%d 级解锁）":
        "No subclass at level %d (it unlocks at level %d)",
    "%d 级必须选子职（%d 级解锁，这个职业有 %d 个可选）":
        "A subclass is required at level %d (unlocks at level %d; this class has %d)",
    "没有这个背景：%s": "No such background: %s",
    "没有这个物种：%s": "No such species: %s",
    "「改卡」不是建卡用的属性生成方式，请选点数购买 / 标准数组 / 掷骰":
        "\"Edit\" is not an ability score generation method for new characters — "
        "use point buy, standard array, or roll",
    "不认识的属性生成方式：%s": "Unknown ability score generation method: %s",
    "%s 超过角色属性上限 %d：%d": "%s exceeds the character ability cap %d: %d",
    "有背景加值却没选背景": "Background bonuses are set but no background is chosen",
    "%s 加完超过上限 %d": "%s goes over the cap %d once bonuses are added",
    "同一项技能选了两次": "The same skill is picked twice",
    "这些技能不在本职业的技能表里：%s":
        "These skills are not on this class's list: %s",
    "%s 已由背景提供，再选一次等于浪费名额（可以换成别的）":
        "%s is already granted by your background; picking it again wastes a slot "
        "(you may swap it for another)",
    "要选 %d 项技能，现在选了 %d 项": "Choose %d skills; %d selected",
    "这个职业没有武器精通": "This class has no Weapon Mastery",
    "没有这些武器：%s": "No such weapons: %s",
    "本职业不熟练这些武器：%s": "This class is not proficient with: %s",
    "同一件武器选了两遍": "The same weapon is picked twice",
    "%d 级能精通 %d 件武器，现在选了 %d 件":
        "Level %d allows %d mastered weapons; %d selected",
    "还没选满：%s（可以留空，稍后在法术页补）":
        "Not filled yet: %s (you can leave it empty and finish later on the Spells page)",
    "没有这组起始装备：%s": "No such starting equipment pack: %s",
    "建卡失败：": "Build failed: ",
    "建卡失败：%s": "Build failed: %s",

    # --- 属性生成与背景加值（rules/abilities、api/origin）-----------------
    "缺属性：%s": "Missing abilities: %s",
    "缺属性 %s": "Missing ability %s",
    "%s 必须是整数：%r": "%s must be an integer: %r",
    "%s 超出 %d–%d：%d": "%s is out of range %d–%d: %d",
    "%s 的点买值必须在 %d–%d 之间：%d":
        "Point-buy value for %s must be between %d and %d: %d",
    "点买超支：花 %d 点，上限 %d":
        "Point buy overspent: %d points spent, cap is %d",
    "标准数组必须正好用完 %s": "The standard array must use exactly %s",
    "掷骰结果必须在 3–18 之间：%s": "Rolled scores must be between 3 and 18: %s",
    "未知的属性生成方式：%r": "Unknown ability score generation method: %r",
    "这个背景没有属性加值": "This background grants no ability score bonuses",
    "背景只给 %s 的加值，不能加在 %s":
        "The background only boosts %s, so it cannot go on %s",
    "背景加值只能是 +1 或 +2：%r": "Background bonuses must be +1 or +2: %r",
    "背景加值的两种合法形态：一项 +2 加一项 +1，或三项各 +1；现在是 %d 个 +2、%d 个 +1":
        "Two legal shapes for background bonuses: one +2 and one +1, or three +1s; "
        "got %d +2 and %d +1",
    "角色没有职业档案，无法设出身":
        "The character has no class levels, so its origin cannot be set",
    "角色没有职业档案，无法记录武器精通":
        "The character has no class levels, so Weapon Mastery cannot be recorded",
    "没有选背景就不能有背景加值":
        "Background bonuses require a background",

    # --- 法术选点（rules/spellcasting.check_spell_picks）----------------
    "职业 %s 没有声明 casting_ability":
        "Class %s declares no casting_ability",
    "戏法": "cantrips",
    "准备法术": "prepared spells",
    "%s 里的职业 %s 不在角色档案中":
        "%s refers to class %s, which is not in the character's profile",
    "内容里没有职业 %s": "No such class in the content: %s",
    "%s（%s）不是施法职业，不该有%s": "%s (%s) is not a spellcasting class and has no %s",
    "%s里有重复法术：%s": "Duplicate spells in %s: %s",
    "%s超出上限：选了 %d 个，上限 %d": "%s over the limit: %d picked, limit %d",
    "%s里的 %s 不存在": "No such spell in %s: %s",
    "%s不在 %s 的法术表里": "%s is not on the %s spell list",
    "%s 不是戏法（%d 环），不能放进已知戏法":
        "%s is not a cantrip (level %d) and cannot be a known cantrip",
    "%s 是戏法，不能准备": "%s is a cantrip and cannot be prepared",
    "%s 是 %d 环，当前最高只有 %d 环":
        "%s is level %d; the highest slot available is level %d",

    # --- 起始装备（rules/starting）-------------------------------------
    "%s 不是 %s 的起始装备": "%s is not a starting pack for %s",
    "没有这组起始装备：%s（%s 有 %s）": "No such starting pack: %s (%s has %s)",
    "%s 里的 %s 不是已知物品": "%s contains an unknown item: %s",

    # --- 升级与改卡（api/progress）--------------------------------------
    "角色没有职业档案，不能升级":
        "The character has no class levels and cannot level up",
    "角色没有职业档案": "The character has no class levels",
    "这个职业已经 20 级了": "This class is already level 20",
    "总等级已达上限 %d，不能再升": "Total level is at the cap of %d",
    "改卡不能换主职业（%s → %s）：要换职业请新建角色":
        "Editing cannot change the primary class (%s → %s); create a new character "
        "to change class",
    "%d 级解锁子职，还没选": "Subclass unlocks at level %d and is not chosen yet",
    "%d 级可以精通 %d 件武器，现在记了 %d 件":
        "Level %d allows %d mastered weapons; %d recorded",
    "还没选满：": "Not filled yet: ",

    # --- 属性提升 / 专长（api/character、api/progress）-------------------
    "还有 %d 次属性提升没用（到「专长」页加）":
        "%d Ability Score Improvement not spent yet (add it on the Feats page)",
    "角色没有职业档案，加不了专长":
        "The character has no class levels, so no feat can be added",
    "角色没有职业档案，去不了专长":
        "The character has no class levels, so no feat can be removed",
    "没有这个专长：%s": "No such feat: %s",
    "角色没有这个专长：%s": "The character does not have this feat: %s",
    "「%s」不是属性提升可以选的专长（%s 类由背景或职业特性给）":
        "\"%s\" cannot be taken with an Ability Score Improvement "
        "(%s feats come from a background or a class feature)",
    "现在不能选「%s」：%s": "Cannot take \"%s\" now: %s",
    "还没有可用的属性提升名额（%s 级各一次；已用 %d / 共 %d）":
        "No Ability Score Improvement left (one at each of levels %s; "
        "%d used of %d)",
    "「%s」没有这些选择项：%s": "\"%s\" has no such choices: %s",
    "「%s」由背景或职业特性给，不能在这里去掉":
        "\"%s\" comes from a background or a class feature and cannot be removed here",
}


def join_list(items, locale: str = "zh") -> str:
    """把名字连成一句：中文用「、」，英文用「, 」。空串直接跳过。"""
    words = [str(item) for item in items if str(item)]
    return ("、" if locale == "zh" else ", ").join(words)


def tr(text: str, locale: str = "zh") -> str:
    """把一句中文原文换成 `locale` 的版本。未收录的英文回退中文并记进 `MISSING`。

    只翻**模板**，不翻已经填好数的句子：调用点写 `tr("…%d…", locale) % (n,)`。
    反过来（先 %，再 tr）永远查不到，因为键里是 `%d` 不是 `3`。
    """
    if locale == "zh" or not text:
        return text
    value = EN.get(text)
    if value is None:
        MISSING.add(text)
        return text
    return value
