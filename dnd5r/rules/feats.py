# -*- coding: utf-8 -*-
"""专长：把「玩家选择」变成可结算的加成。

专长分两半：

  静态原语（`powers`）—— 与职业特性**完全同一套** modifier / effect 管道，
      所以「防御 +1 AC」「速行 +10 尺」「坚毅 +40 HP」不需要任何新机制。
  玩家选择（`choices`）—— 选完才知道加多少，只能在建角色时结算。

为什么选择项不写成 power 里的占位符（`score.$choice`）：可选集合、选几项、
上限都是**数据**。写进字符串模板等于把规则搬进模板语法，校验期什么都查不出来。
在这里每条 choice 的语义是封闭的（`CHOICE_KINDS`），选错立刻报错。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ..content import SPELL_LIST_ANY, ContentBundle, FeatChoice, FeatDef
from ..kernel.errors import RuleError
from ..kernel.text import Text
from .scores import ScoreBonus

# 候选**来自内容**而不是 `CHOICE_UNIVERSE` 的选择项：判不了在 `picks_for` 里
# （那时还没有 bundle），只能在 build 时用 `check_feat_choices` 校验。
_CONTENT_DRIVEN = ("spell", "proficiency")


@dataclass(frozen=True)
class FeatPicks:
    """一组专长在当前选择下能兑现的东西。"""

    score: tuple[ScoreBonus, ...] = ()
    proficiencies: frozenset[str] = frozenset()
    expertise: frozenset[str] = frozenset()
    resistances: frozenset[str] = frozenset()
    # 专长给的法术（法术内容 id）。**不占职业的准备名额** —— 它来自专长，
    # 与 `Profile.prepared` 是两条账，混起来会让「魔法入门」把法师的准备位吃掉。
    spells: tuple[str, ...] = ()
    # 还没选完的选择项（`<专长 id>.<选择项 id>`）。空 = 都选好了。
    pending: tuple[str, ...] = ()

    def merged(self, other: "FeatPicks") -> "FeatPicks":
        # 法术按「始终准备的清单」理解：重复取同一个专长不该在界面上出现两行同一道法术。
        # 熟练/专精本来就是 frozenset，天然去重；这里补上唯一的例外。
        spells = list(self.spells)
        spells += [item for item in other.spells if item not in spells]
        return FeatPicks(
            score=self.score + other.score,
            proficiencies=self.proficiencies | other.proficiencies,
            expertise=self.expertise | other.expertise,
            resistances=self.resistances | other.resistances,
            spells=tuple(spells),
            pending=self.pending + other.pending,
        )

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "score": [{"ability": item.ability, "amount": item.amount,
                       "cap": item.cap, "source": item.source} for item in self.score],
            "proficiencies": sorted(self.proficiencies),
            "expertise": sorted(self.expertise),
            "resistances": sorted(self.resistances),
            "spells": list(self.spells),
            "pending": list(self.pending),
        }


def _label(feat: FeatDef, locale: str) -> str:
    """加成明细里显示的来源：专长名，不是 id。"""
    return feat.name.get(locale) or feat.id


def pick_key(feat_id: str, choice_id: str, index: int = 0) -> str:
    """选择项在 `Profile.choices` 里的键。

    同一个专长可以登记多次（属性提升：4 级一次、8 级一次）。第一次仍用
    `<专长>.<选择项>`（旧档不用改），第二次起加 `#序号` ——
    否则两次选择共用一格，第二次的 +2 会把第一次覆盖掉。
    """
    return ("%s#%d.%s" % (feat_id, index, choice_id) if index
            else "%s.%s" % (feat_id, choice_id))


def picks_for(
    feat: FeatDef,
    choices: Mapping[str, tuple[str, ...]],
    locale: str = "zh",
    index: int = 0,
) -> FeatPicks:
    """结算一个专长的选择项。

    「还没选」不是错误：建角色时可以只登记专长、稍后再选（界面上的待办）。
    但「选了不存在的项」「选多了」是错误 —— 那是数据问题，必须当场炸。
    """
    score: list[ScoreBonus] = []
    prof: set[str] = set()
    expertise: set[str] = set()
    resist: set[str] = set()
    spells: list[str] = []
    pending: list[str] = []

    for choice in feat.choices:
        key = pick_key(feat.id, choice.id, index)
        picked = tuple(str(item) for item in (choices.get(key) or ()))
        if not picked and index == 0:
            # 写成 `#0` 也认 —— 界面统一按序号生成键时不用特判第一条
            picked = tuple(str(item) for item in
                           (choices.get("%s#0.%s" % (feat.id, choice.id)) or ()))
        if not picked:
            pending.append(key)
            continue
        # `spell` / `proficiency` 的候选来自内容（法术表、工具表），不在
        # `choice.options` 里 —— 拿到 FeatDef 时还没有 bundle，判不了，
        # 交给 `check_feat_choices` 在 build 时校验。
        allowed = set(choice.options)
        unknown = [] if choice.kind in _CONTENT_DRIVEN else [
            item for item in picked if item not in allowed]
        if unknown:
            raise RuleError("专长「%s」的 %s 选了不存在的项：%s（可选：%s）"
                            % (_label(feat, locale), choice.id, ", ".join(unknown),
                               ", ".join(sorted(allowed)) or "无"))
        if len(picked) > choice.count:
            raise RuleError("专长「%s」的 %s 最多选 %d 项，实际选了 %d 项"
                            % (_label(feat, locale), choice.id, choice.count, len(picked)))
        if not choice.repeat and len(set(picked)) != len(picked):
            raise RuleError("专长「%s」的 %s 不能重复选同一项：%s"
                            % (_label(feat, locale), choice.id, ", ".join(picked)))
        if len(picked) < choice.count:
            pending.append(key)
            continue
        _land(choice, picked, _label(feat, locale), score, prof, expertise, resist, spells)

    return FeatPicks(
        score=tuple(score),
        proficiencies=frozenset(prof),
        expertise=frozenset(expertise),
        resistances=frozenset(resist),
        # 写死的「始终准备」排在前面：内容里定了顺序，界面上就别抖
        spells=tuple(feat.spells) + tuple(spells),
        pending=tuple(pending),
    )


def _land(
    choice: FeatChoice,
    picked: tuple[str, ...],
    source: str,
    score: list[ScoreBonus],
    prof: set[str],
    expertise: set[str],
    resist: set[str],
    spells: list[str],
) -> None:
    """把选好的项落成具体加成。每种 kind 一行，别在这里加第二套判断。"""
    if choice.kind == "ability_boost":
        for ability in picked:
            score.append(ScoreBonus(
                ability=ability,
                amount=choice.amount,
                cap=choice.cap or None,
                source=source,
            ))
    elif choice.kind == "save":
        prof.update("save.%s" % ability for ability in picked)
        if choice.boost:
            # 坚毅：选中哪一项豁免，那一项属性也 +1（不是另选一项）
            for ability in picked:
                score.append(ScoreBonus(ability=ability, amount=choice.boost,
                                        cap=choice.boost_cap or None, source=source))
    elif choice.kind == "skill":
        prof.update("skill.%s" % skill for skill in picked)
    elif choice.kind == "expertise":
        # 专精必须是「已熟练」的子集，Profile 会校验；这里只落 token
        expertise.update("skill.%s" % skill for skill in picked)
    elif choice.kind == "resistance":
        resist.update(picked)
    elif choice.kind == "spell":
        spells.extend(picked)
    elif choice.kind == "proficiency":
        # 混选：`skill.stealth` 与 `tool.thieves_tools` 都已经是完整 token
        prof.update(picked)


def collect_picks(
    feats: Iterable[FeatDef],
    choices: Mapping[str, tuple[str, ...]],
    locale: str = "zh",
) -> FeatPicks:
    total = FeatPicks()
    seen: dict[str, int] = {}
    for feat in feats:
        index = seen.get(feat.id, 0)
        seen[feat.id] = index + 1
        total = total.merged(picks_for(feat, choices, locale, index=index))
    return total


def spell_pool(bundle: ContentBundle, choice: FeatChoice) -> tuple[str, ...]:
    """`kind: spell` 的候选：**该职业法术表**里、**该环级**（可再按学派收窄）的法术 id。

    候选不写进内容：法术表本身就是权威，抄一份到专长里必然漂。
    排序用 id，界面上的顺序才稳定（不受加载顺序影响）。
    """
    if choice.kind != "spell":
        return ()
    if choice.spell_list == SPELL_LIST_ANY:
        # 「任选一道某学派的 1 环法术」—— 不限职业法术表。收窄全靠环级 + 学派，
        # 所以这里必须有学派，否则候选会是全部法术（那是给玩家一整个法术库）
        if not choice.spell_school:
            raise RuleError("选择项 %s 写了 spell_list: any 却没写 spell_school，候选会是全部法术"
                            % choice.id)
        allowed = set(bundle.spells)
    else:
        class_id = "dnd2024.class.%s" % choice.spell_list
        if class_id not in bundle.classes:
            raise RuleError("选择项 %s 的 spell_list 指向不存在的职业：%s"
                            % (choice.id, choice.spell_list))
        allowed = set(bundle.spell_list(class_id))
        if not allowed:
            raise RuleError("职业 %s 没有法术表，不能作为 spell_list" % choice.spell_list)
    schools = set(choice.spell_school)
    return tuple(sorted(
        spell.id for spell in bundle.spells.values()
        if spell.id in allowed and int(spell.level) == int(choice.spell_level)
        and (not schools or spell.school in schools)
    ))


def proficiency_pool(bundle: ContentBundle) -> tuple[str, ...]:
    """`kind: proficiency` 的候选：全部技能 + 全部工具，都写成**完整 token**。

    顺序固定（先技能后工具，各自按 key 排）：界面上选项的顺序不该随加载顺序抖。
    两者都是内容，所以不放进 `CHOICE_UNIVERSE`（那张表是规则词汇的闭环）。
    """
    skills = sorted("skill.%s" % skill.key for skill in bundle.skills.values())
    tools = sorted("tool.%s" % tool.key for tool in bundle.tools.values())
    return tuple(skills) + tuple(tools)


def check_feat_choices(
    bundle: ContentBundle,
    feats: Iterable[FeatDef],
    choices: Mapping[str, tuple[str, ...]],
    repeats: Mapping[str, int] | None = None,
    locale: str = "zh",
) -> list[str]:
    """专长里「候选来自内容」的那几种选择项（`spell` / `proficiency`）是否合法。

    「选错」与「还没选」要分开：没选只是 `pending`（界面上的待办），
    选了一个不在候选里的项才是数据错误 —— 后者会让卡片上出现一个
    永远算不出来的熟练，比报错难查得多。
    """
    problems: list[str] = []
    for feat in feats:
        # 可重复登记的专长每次登记是一轮独立选择，键带 `#序号` ——
        # 次数从 `repeats` 来，别在这里自己数（`feats` 是去重后的）
        for index in range(int((repeats or {}).get(feat.id, 1))):
            for choice in feat.choices:
                if choice.kind not in _CONTENT_DRIVEN:
                    continue
                picked = tuple(str(item) for item in
                               (choices.get(pick_key(feat.id, choice.id, index)) or ()))
                if not picked:
                    continue
                problems += _check_pool(bundle, feat, choice, picked, locale)
    return problems


def _check_pool(bundle: ContentBundle, feat: FeatDef, choice: FeatChoice,
                picked: tuple[str, ...], locale: str) -> list[str]:
    if choice.kind == "proficiency":
        legal = set(proficiency_pool(bundle))
        unknown = [item for item in picked if item not in legal]
        if not unknown:
            return []
        return ["专长「%s」的 %s 选了不存在的熟练项：%s（可选：%d 项技能 + %d 件工具）"
                % (_label(feat, locale), choice.id, ", ".join(unknown),
                   len(bundle.skills), len(bundle.tools))]
    legal = set(spell_pool(bundle, choice))
    where = ("任意法术表" if choice.spell_list == SPELL_LIST_ANY
             else "%s 法术表" % choice.spell_list)
    return ["专长「%s」的 %s 选了 %s，但它不在候选里（%s的 %d 环%s法术）"
            % (_label(feat, locale), choice.id, item, where, choice.spell_level,
               "（限%s）" % "/".join(choice.spell_school)
               if choice.spell_school else "")
            for item in picked if item not in legal]


def hard_problems(
    feat: FeatDef,
    total_level: int,
    class_ids: Iterable[str] = (),
) -> list[str]:
    """**硬**前提：等级与职业。建角色时直接拒绝。

    「这个角色现在能不能拿这个专长」是可判定的；不能判定的一律不进这里。
    """
    problems: list[str] = []
    if feat.level and int(total_level) < int(feat.level):
        problems.append("需要 %d 级（当前 %d 级）" % (feat.level, int(total_level)))
    if feat.classes:
        allowed = set(feat.classes)
        if not (set(class_ids) & allowed):
            problems.append("只有 %s 能选" % "、".join(sorted(allowed)))
    return problems


def soft_problems(feat: FeatDef, scores: Mapping[str, int] | None) -> list[str]:
    """**软**前提：属性门槛。只在选单里提示，不拦建角色。

    理由是属性提升类专长本身就会改属性：按「加值前」的分数判能否选取，
    会出现「想拿属性提升，所以属性不够」的死循环。
    """
    if not feat.abilities or not scores:
        return []
    need = feat.min_score or 13
    if any(int(scores.get(key, 0)) >= need for key in feat.abilities):
        return []
    names = "、".join(key.upper() for key in feat.abilities)
    if len(feat.abilities) == 1:
        return ["需要 %s 达到 %d" % (names, need)]
    return ["需要 %s 中至少一项达到 %d" % (names, need)]


def prereq_report(
    feat: FeatDef,
    total_level: int,
    class_ids: Iterable[str] = (),
    scores: Mapping[str, int] | None = None,
) -> list[str]:
    """全部前提检查结果（空 = 满足）——给选单用。"""
    return hard_problems(feat, total_level, class_ids) + soft_problems(feat, scores)


def choice_prompt(feat: FeatDef, choice: FeatChoice, locale: str = "zh") -> Text:
    """给界面的一句话：这个专长还要你选什么。"""
    if choice.label is not None:
        return choice.label
    if choice.kind == "ability_boost":
        return Text.of("选 %d 项属性，各 +%d（上限 %d）"
                       % (choice.count, choice.amount, choice.cap or 20),
                       "Choose %d ability score%s, +%d each (max %d)"
                       % (choice.count, "" if choice.count == 1 else "s",
                          choice.amount, choice.cap or 20))
    if choice.kind == "save":
        return Text.of("选 %d 项豁免熟练" % choice.count,
                       "Choose %d saving throw proficiency" % choice.count)
    if choice.kind == "skill":
        return Text.of("选 %d 项技能熟练" % choice.count,
                       "Choose %d skill proficiency" % choice.count)
    if choice.kind == "expertise":
        return Text.of("选 %d 项已有熟练的技能获得专精" % choice.count,
                       "Choose %d skill proficiency to gain Expertise" % choice.count)
    if choice.kind == "proficiency":
        return Text.of("选 %d 项技能**或**工具熟练（可自由混合）" % choice.count,
                       "Choose %d skill or tool proficiencies (any combination)"
                       % choice.count)
    if choice.kind == "resistance":
        return Text.of("选 %d 种伤害抗性" % choice.count,
                       "Choose %d damage resistances" % choice.count)
    return Text.of(feat.name.get(locale), feat.name.get("en"))


__all__ = [
    "FeatPicks", "picks_for", "collect_picks", "pick_key",
    "hard_problems", "soft_problems", "proficiency_pool", "check_feat_choices", "prereq_report", "choice_prompt",
]
