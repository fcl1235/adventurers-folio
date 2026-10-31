# -*- coding: utf-8 -*-
"""建卡向导（P7）：8 步要选的目录 + 最终的权威校验与组装。

向导的每一步只改一个 `draft` 字典，**直到最后一步才建角色**。这样建卡中途
永远不会留下半截 actor：3 级错选 5 环法术这种问题在「点完成」时一次性报出来，
而不是在填到第 7 步时炸掉前面的所有输入。

`draft_problems()` 与 `build_from_draft()` 共用同一份检查 —— 前者给界面标红，
后者在真正建角色前再挡一次。**两处不许各写一套**：「界面说没问题、点完成却
报错」是最难向用户解释的失败。

法术语义（与 `rules/spellcasting` 一致）：戏法数量与准备数量按**职业等级**查表，
不按总等级；兼职时每个职业各算各的。这一点向导不重复实现，只把上限读出来给
界面显示「已选 2 / 3」，权威校验仍然在建角色时由 `check_spell_picks` 做。
"""

from __future__ import annotations

from typing import Any, Mapping

from ..content import CasterKind, ContentBundle, SKILL_KEYS
from ..kernel.errors import DndError, RuleError
from ..model.actor import Actor
from ..model.levels import as_class_level
from ..model.statblock import ABILITY_KEYS, SCORE_MIN
from ..rules.abilities import (
    CHARACTER_SCORE_MAX, background_bonus, score_range_ok, validate_point_buy,
)
from ..rules.spellcasting import check_spell_picks
from .character import new_character
from .origin import (
    SCORE_MODES, SCORE_MODE_ZH, background_catalog, bonus_shapes, species_catalog,
)

# 八个步骤。界面按这个顺序画导航，`draft_problems()` 用 `step` 字段指回这里。
WIZARD_STEPS: tuple[dict, ...] = (
    {"key": "class", "title": "职业", "hint": "先定职业与等级 —— 生命骰、豁免熟练、资源池都由它决定。"},
    {"key": "background", "title": "背景", "hint": "背景给三项属性各一点加值（或一项 +2 一项 +1）、两项技能、一件工具和一个起始专长。"},
    {"key": "species", "title": "物种", "hint": "物种只给特性（黑暗视觉、抗性、速度、每级生命），**不**给属性加值。"},
    {"key": "scores", "title": "属性", "hint": "点买 27 点、标准数组、或掷 4d6 弃最低。上限 15 是购买上限，16 以上只能靠背景与专长。"},
    {"key": "skills", "title": "技能", "hint": "从本职业技能表里选；背景已经给的那几项不用重复选。"},
    {"key": "masteries", "title": "武器精通", "hint": "从本职业熟练的武器里选。精通效果**只记录、不结算** —— 都要在命中后做选择。"},
    {"key": "spells", "title": "法术", "hint": "施法职业才需要；非施法职业这一步自动跳过。"},
    {"key": "summary", "title": "汇总", "hint": "起个名字，然后建卡。"},
)

STEP_INDEX = {step["key"]: index for index, step in enumerate(WIZARD_STEPS)}


# --- 索引小工具 -------------------------------------------------------
def _skill_def(content: ContentBundle, key: str):
    for item in content.skills.values():
        if item.key == key:
            return item
    return None


def _tool_def(content: ContentBundle, key: str):
    for item in content.tools.values():
        if item.key == key:
            return item
    return None


def _skill_name(content: ContentBundle, key: str, locale: str) -> str:
    item = _skill_def(content, key)
    # 查不到就退回 key：编一个中文名比显示 key 更难查（用户会以为是内容缺失）
    return item.name.get(locale) if item is not None else key


def _weapon_categories(class_def) -> set[str]:
    """本职业熟练的武器类别（`weapon.simple` → `simple`）。"""
    return {token.split(".", 1)[1] for token in class_def.proficiencies
            if token.startswith("weapon.")}


# --- 目录 -------------------------------------------------------------
def class_catalog(content: ContentBundle, locale: str = "zh") -> list[dict]:
    """12 个职业：建卡第一步要看的全部信息。

    `mastery_at_1` 是**1 级**的精通件数，用来判断这一步要不要出现；
    具体某级能选几件走 `mastery_choices()`。
    """
    rows = []
    for class_id in sorted(content.classes):
        item = content.classes[class_id]
        rows.append({
            "id": item.id,
            "name": item.name.get(locale),
            "hit_die": int(item.hit_die),
            "primary": list(item.primary),
            "saves": list(item.saves),
            "caster": item.caster.value,
            "casting_ability": item.casting_ability,
            "skill_choices": int(item.skill_choices),
            "skills": [{"key": key, "name": _skill_name(content, key, locale)}
                       for key in item.skill_list],
            "subclass_level": int(item.subclass_level),
            "subclass_count": len(content.subclasses_for(item.id)),
            "mastery_at_1": item.mastery_count_at(as_class_level(1)),
            "mastery_max": item.mastery_count_at(as_class_level(20)),
        })
    return rows


def skill_catalog(content: ContentBundle, locale: str = "zh") -> list[dict]:
    """18 项技能，顺序按内核的 `SKILL_KEYS`（卡上一直是这个顺序，不按字典序）。"""
    order = {key: index for index, key in enumerate(SKILL_KEYS)}
    rows = []
    for item in content.skills.values():
        rows.append({"key": item.key, "name": item.name.get(locale),
                     "ability": item.ability})
    rows.sort(key=lambda row: order.get(row["key"], 99))
    return rows


def tool_catalog(content: ContentBundle, locale: str = "zh") -> list[dict]:
    rows = []
    for item in sorted(content.tools.values(), key=lambda entry: (entry.kind, entry.id)):
        rows.append({"key": item.key, "name": item.name.get(locale),
                     "kind": item.kind, "ability": item.ability})
    return rows


def subclass_choices(content: ContentBundle, class_id: str,
                     class_level: int = 1, locale: str = "zh") -> dict:
    """该职业的子职选项，附「这一级能不能选」。

    3 级才解锁子职，但向导里 1–2 级也要能**看见**它 —— 否则玩家不知道为什么
    第 8 步汇总里没有子职。界面上按 `unlocked` 灰掉即可。
    """
    class_def = content.class_def(class_id)
    unlocked = int(class_level) >= int(class_def.subclass_level)
    rows = []
    for sub in content.subclasses_for(class_id):
        rows.append({
            "id": sub.id,
            "name": sub.name.get(locale),
            "summary": sub.summary.get(locale),
            "unlock_level": int(sub.unlock_level),
            "unlocked": unlocked,
        })
    return {"unlock_level": int(class_def.subclass_level),
            "unlocked": unlocked, "options": rows}


def mastery_choices(content: ContentBundle, class_id: str,
                    class_level: int = 1, locale: str = "zh") -> dict:
    """武器精通的可选项：件数 + 武器表（按本职业熟练类别过滤）。

    过滤是必须的：圣武士不会精通短弓。`count == 0` 时 `options` 为空，
    界面据此跳过这一步（武僧、法师没有武器精通）。
    """
    class_def = content.class_def(class_id)
    count = class_def.mastery_count_at(as_class_level(int(class_level)))
    allowed = _weapon_categories(class_def)
    options = []
    if count and allowed:
        for item in content.weapons.values():
            if item.category not in allowed:
                continue
            options.append({
                "id": item.id,
                "name": item.name.get(locale),
                "category": item.category,
                "damage": item.damage,
                "mastery": item.mastery,
            })
    # 简易武器在前：向导里从「最常用的那把」开始挑，比字母序有用得多
    options.sort(key=lambda row: (row["category"] != "simple", row["name"]))
    return {"count": int(count), "options": options}


def spell_choices(content: ContentBundle, class_id: str,
                  class_level: int = 1, locale: str = "zh") -> dict:
    """该职业在这一级能选的法术：戏法与 1–9 环分组，附数量上限与法术位。

    数量上限取「不超过当前等级的最大档」（与资源表同规则），所以 3 级法师
    看到的是 3 级那一行，不是 1 级那一行。
    """
    class_def = content.class_def(class_id)
    level = int(class_level)
    if class_def.caster is CasterKind.NONE:
        return {"caster": False, "cantrip_limit": 0, "prepared_limit": 0,
                "max_spell_level": 0, "casting_ability": "",
                "cantrips": [], "levels": [], "slots": [0] * 9}

    def _limit(table: Mapping[int, int]) -> int:
        usable = [int(key) for key in table if int(key) <= level]
        return int(table[max(usable)]) if usable else 0

    slots = class_def.slots_at(as_class_level(level))
    # 这一级能准备的最高环 = 法术位表里非零的最大环。**不能把 9 环全列出来**：
    # 3 级法师的界面列出「九环法术」是个错，虽然建卡时会被校验挡住，
    # 但玩家会先花时间选完再被打回来。
    top = max((index + 1 for index, value in enumerate(slots) if value), default=0)

    cantrips, groups = [], {}
    for spell_id in content.spell_list(class_id):
        spell = content.spells.get(spell_id)
        if spell is None:
            continue
        if int(spell.level) > top:
            continue
        row = {"id": spell.id, "name": spell.name.get(locale),
               "level": int(spell.level), "school": spell.school,
               "concentration": bool(spell.concentration), "ritual": bool(spell.ritual)}
        if int(spell.level) == 0:
            cantrips.append(row)
        else:
            groups.setdefault(int(spell.level), []).append(row)
    cantrips.sort(key=lambda row: row["name"])
    levels = [{"level": key, "spells": sorted(groups[key], key=lambda row: row["name"])}
              for key in sorted(groups)]
    return {
        "caster": True,
        "casting_ability": class_def.casting_ability,
        "cantrip_limit": _limit(class_def.cantrips),
        "prepared_limit": _limit(class_def.prepared),
        "max_spell_level": top,
        "cantrips": cantrips,
        "levels": levels,
        # 法术位是只读信息：建卡时不需要选，但玩家想知道「我现在有几个位」
        "slots": list(slots),
    }


def step_options(content: ContentBundle, step: str, draft: Mapping[str, Any],
                 locale: str = "zh") -> dict:
    """一步的全部选项，键随步骤变。界面只需要「拿到数据 → 画」，不再自己查内容。"""
    class_id = str(draft.get("class_id") or "")
    level = int(draft.get("class_level") or 1)
    if step == "class":
        return {"classes": class_catalog(content, locale),
                "subclasses": subclass_choices(content, class_id, level, locale)
                if class_id else {"unlock_level": 3, "unlocked": False, "options": []}}
    if step == "background":
        return {"backgrounds": background_catalog(content, locale)}
    if step == "species":
        return {"species": species_catalog(content, locale)}
    if step == "scores":
        return {"modes": list(SCORE_MODES), "mode_zh": dict(SCORE_MODE_ZH),
                # 上限用**角色**的 20，不是 statblock 的 30 —— 界面照这个画输入框
                "keys": list(ABILITY_KEYS), "min": SCORE_MIN,
                "max": CHARACTER_SCORE_MAX}
    if step == "skills":
        if not class_id:
            return {"choices": 0, "options": [], "provided": []}
        class_def = content.class_def(class_id)
        provided = _background_skills(content, str(draft.get("background") or ""))
        return {
            "choices": int(class_def.skill_choices),
            "options": [{"key": key, "name": _skill_name(content, key, locale),
                         "ability": getattr(_skill_def(content, key), "ability", ""),
                         "provided": key in provided}
                        for key in class_def.skill_list],
            "provided": sorted(provided),
        }
    if step == "masteries":
        if not class_id:
            return {"count": 0, "options": []}
        return mastery_choices(content, class_id, level, locale)
    if step == "spells":
        if not class_id:
            return {"caster": False, "cantrip_limit": 0, "prepared_limit": 0,
                    "max_spell_level": 0, "casting_ability": "",
                    "cantrips": [], "levels": [], "slots": [0] * 9}
        return spell_choices(content, class_id, level, locale)
    if step == "summary":
        return {"steps": [dict(item) for item in WIZARD_STEPS]}
    raise RuleError("不认识的建卡步骤：%r" % (step,))


def _background_skills(content: ContentBundle, background_id: str) -> set[str]:
    item = content.backgrounds.get(background_id) if background_id else None
    return set(item.skills) if item is not None else set()


# --- 校验 -------------------------------------------------------------
def draft_problems(content: ContentBundle, draft: Mapping[str, Any],
                   locale: str = "zh") -> list[dict]:
    """把不合法的地方逐条列出来（空 = 可以建卡）。

    每条带 `step`（步骤 key）、`text`（人话）与 `level`：`error` 必须改，
    `warn` 只是提醒（例如重复选背景已给的技能 —— 2024 规则允许换一项，
    所以那不是错）。界面据此跳回那一步并标色，**不是**弹一个「有错误」
    然后让人自己找。

    只拦 `error` 是有意的：把可选项当错误拦下来，玩家会以为自己做错了。
    """
    problems: list[dict] = []

    def add(step: str, text: str, level: str = "error") -> None:
        problems.append({"step": step, "text": text, "level": level})

    class_id = str(draft.get("class_id") or "")
    class_def = content.classes.get(class_id) if class_id else None
    if class_def is None:
        add("class", "还没选职业")
        return problems                    # 没有职业，后面的检查全部无意义

    level = int(draft.get("class_level") or 0)
    if not 1 <= level <= 20:
        add("class", "职业等级必须在 1–20 之间：%d" % level)

    subclass = str(draft.get("subclass") or "")
    if subclass:
        if subclass not in content.subclasses:
            add("class", "没有这个子职：%s" % subclass)
        elif content.subclasses[subclass].class_id != class_id:
            add("class", "子职 %s 不属于这个职业" % subclass)
        elif level < int(class_def.subclass_level):
            add("class", "%d 级还选不了子职（%d 级解锁）"
                % (level, int(class_def.subclass_level)))
    elif level >= int(class_def.subclass_level):
        # 到解锁等级还没选：子职特性一条都不会有，卡是残的。这不是「可选项」——
        # 2024 的每个职业在解锁等级都必须选一个（解锁等级 1 的职业连 1 级就要）。
        add("class", "%d 级必须选子职（%d 级解锁，这个职业有 %d 个可选）"
            % (level, int(class_def.subclass_level),
               len(content.subclasses_for(class_id))))

    background_id = str(draft.get("background") or "")
    if background_id and background_id not in content.backgrounds:
        add("background", "没有这个背景：%s" % background_id)

    species_id = str(draft.get("species") or "")
    if species_id and species_id not in content.species:
        add("species", "没有这个物种：%s" % species_id)

    # --- 属性 ---
    scores = {str(key): value for key, value in (draft.get("scores") or {}).items()}
    for text in score_range_ok(scores):
        add("scores", text)
    # `score_range_ok` 放的是 statblock 的 1–30（怪物也走它），角色卡还要夹到 20
    for key, value in scores.items():
        if isinstance(value, int) and not isinstance(value, bool) \
                and value > CHARACTER_SCORE_MAX:
            add("scores", "%s 超过角色属性上限 %d：%d"
                % (key.upper(), CHARACTER_SCORE_MAX, value))
    mode = str(draft.get("score_mode") or "")
    if mode == "point_buy":
        for text in validate_point_buy(scores):
            add("scores", text)
    elif mode and mode not in SCORE_MODES:
        add("scores", "不认识的属性生成方式：%s" % mode)

    bonus = dict(draft.get("background_bonus") or {})
    if bonus:
        if not background_id:
            add("background", "有背景加值却没选背景")
        else:
            item = content.backgrounds[background_id]
            try:
                background_bonus(item.abilities, bonus)
            except RuleError as exc:
                add("scores", str(exc))
            else:
                # 加完不能超上限：20 是硬顶，超了要在这里说，不能等建卡时夹掉
                for key, value in bonus.items():
                    if key in scores and int(scores[key]) + int(value) > CHARACTER_SCORE_MAX:
                        add("scores", "%s 加完超过上限 %d"
                            % (key.upper(), CHARACTER_SCORE_MAX))

    # --- 技能 ---
    skills = [str(item) for item in (draft.get("skills") or ())]
    provided = _background_skills(content, background_id)
    if len(set(skills)) != len(skills):
        add("skills", "同一项技能选了两次")
    outside = [key for key in skills if key not in class_def.skill_list]
    if outside:
        add("skills", "这些技能不在本职业的技能表里：%s"
            % "、".join(_skill_name(content, key, locale) for key in outside))
    # 背景已经给的再选一次 = 白白浪费一个名额（2024 规则允许换一项，所以不拦，只提醒）
    wasted = [key for key in skills if key in provided]
    if wasted:
        add("skills", "%s 已由背景提供，再选一次等于浪费名额（可以换成别的）"
            % "、".join(_skill_name(content, key, locale) for key in wasted),
            level="warn")
    need = int(class_def.skill_choices)
    if len(skills) != need and not outside:
        add("skills", "要选 %d 项技能，现在选了 %d 项" % (need, len(skills)))

    # --- 武器精通 ---
    masteries = [str(item) for item in (draft.get("masteries") or ())]
    count = class_def.mastery_count_at(as_class_level(max(1, level)))
    if masteries and not count:
        add("masteries", "这个职业没有武器精通")
    elif count:
        allowed = _weapon_categories(class_def)
        unknown = [item for item in masteries if item not in content.weapons]
        if unknown:
            add("masteries", "没有这些武器：%s" % "、".join(unknown))
        wrong = [content.weapons[item].name.get(locale) for item in masteries
                 if item in content.weapons and content.weapons[item].category not in allowed]
        if wrong:
            add("masteries", "本职业不熟练这些武器：%s" % "、".join(wrong))
        if len(set(masteries)) != len(masteries):
            add("masteries", "同一件武器选了两遍")
        elif len(masteries) != count and not unknown:
            add("masteries", "%d 级能精通 %d 件武器，现在选了 %d 件"
                % (level, count, len(masteries)))

    # --- 法术 ---
    # 配额、环级上限、是否本职业法术表 —— 全都由 `check_spell_picks` 说了算，
    # 这里只**转述**它的话并标成 spells 步。不转述就会出现「汇总页说没问题、
    # 点完成却报错」，而界面不知道该跳回哪一步（实测：选了重复戏法只在状态行
    # 留一句话，人卡在汇总页）。两处共用一份规则，正是本模块开头的约定。
    cantrips_map = {str(key): [str(item) for item in value]
                    for key, value in (draft.get("cantrips") or {}).items() if value}
    prepared_map = {str(key): [str(item) for item in value]
                    for key, value in (draft.get("prepared") or {}).items() if value}
    if cantrips_map or prepared_map:
        usable_level = as_class_level(max(1, min(level, 20)))
        for text in check_spell_picks(content, {class_id: usable_level},
                                      cantrips_map, prepared_map, locale):
            add("spells", text)

    return problems


def _clean_draft(draft: Mapping[str, Any]) -> dict:
    """草案 → `new_character` 的参数。**只搬运，不补默认值**。"""
    return {
        "name_zh": str(draft.get("name_zh") or "").strip() or "无名冒险者",
        "name_en": str(draft.get("name_en") or "").strip() or "Unnamed Adventurer",
        "scores": {str(key): int(value) for key, value in (draft.get("scores") or {}).items()},
        "class_level": int(draft.get("class_level") or 1),
        "subclass": str(draft.get("subclass") or "") or None,
        "species": str(draft.get("species") or ""),
        "background": str(draft.get("background") or ""),
        "background_bonus": {str(key): int(value)
                             for key, value in (draft.get("background_bonus") or {}).items()},
        "masteries": [str(item) for item in (draft.get("masteries") or ())],
        # 技能选择走熟练 token：`skill.stealth`，与背景给的是同一套
        "extra_proficiencies": ["skill.%s" % key for key in (draft.get("skills") or ())],
        # 空的法术表要**丢掉整个键**，不能留 `{class_id: []}` —— 非施法职业
        # 带着空表进 `new_character` 会被判成「战士不该有戏法」。
        "cantrips": {str(key): [str(item) for item in value]
                     for key, value in (draft.get("cantrips") or {}).items() if value},
        "prepared": {str(key): [str(item) for item in value]
                     for key, value in (draft.get("prepared") or {}).items() if value},
    }


def build_from_draft(content: ContentBundle, draft: Mapping[str, Any],
                     locale: str = "zh") -> Actor:
    """按草案建角色。**先校验再建** —— 校验通过才可能走到 `new_character`。"""
    blocking = [item for item in draft_problems(content, draft, locale)
                if item.get("level") != "warn"]
    if blocking:
        raise RuleError("建卡失败：" + "；".join(item["text"] for item in blocking))
    params = _clean_draft(draft)
    class_id = str(draft.get("class_id") or "")
    try:
        return new_character(content, class_id=class_id, **params)
    except DndError:
        raise                                  # 已经是 RuleError，别包第二层
    except (TypeError, ValueError) as exc:     # 兜底：界面传了脏数据
        raise RuleError("建卡失败：%s" % exc)


def empty_draft() -> dict:
    """一张空草案：战士 1 级 + 标准数组。

    它不是「能直接建卡」的草案 —— 技能与武器精通还要玩家选（这正是向导存在的
    理由），但除此之外的每一步都已经填好，界面可以从任意一步开始改。
    """
    return {
        "name_zh": "无名冒险者",
        "name_en": "Unnamed Adventurer",
        "class_id": "dnd2024.class.fighter",
        "class_level": 1,
        "subclass": "",
        "species": "",
        "background": "",
        "background_bonus": {},
        "score_mode": "standard_array",
        "scores": {"str": 15, "dex": 14, "con": 13, "int": 12, "wis": 10, "cha": 8},
        "skills": [],
        "masteries": [],
        "cantrips": {},
        "prepared": {},
    }


def bonus_plans(background_id: str, content: ContentBundle) -> list[dict]:
    """背景加值的全部合法分配方式（「+2/+1」的 6 种 +「各 +1」的 1 种）。

    界面拿它画下拉，玩家不用自己算「一项 +2 一项 +1」怎么摆。
    """
    return bonus_shapes(background_id, content)
