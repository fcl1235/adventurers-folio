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

from ..content import FeatChoice, FeatDef
from ..kernel.errors import RuleError
from ..kernel.text import Text
from .scores import ScoreBonus


@dataclass(frozen=True)
class FeatPicks:
    """一组专长在当前选择下能兑现的东西。"""

    score: tuple[ScoreBonus, ...] = ()
    proficiencies: frozenset[str] = frozenset()
    expertise: frozenset[str] = frozenset()
    resistances: frozenset[str] = frozenset()
    # 还没选完的选择项（`<专长 id>.<选择项 id>`）。空 = 都选好了。
    pending: tuple[str, ...] = ()

    def merged(self, other: "FeatPicks") -> "FeatPicks":
        return FeatPicks(
            score=self.score + other.score,
            proficiencies=self.proficiencies | other.proficiencies,
            expertise=self.expertise | other.expertise,
            resistances=self.resistances | other.resistances,
            pending=self.pending + other.pending,
        )

    def to_dict(self, locale: str = "zh") -> dict:
        return {
            "score": [{"ability": item.ability, "amount": item.amount,
                       "cap": item.cap, "source": item.source} for item in self.score],
            "proficiencies": sorted(self.proficiencies),
            "expertise": sorted(self.expertise),
            "resistances": sorted(self.resistances),
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
        allowed = set(choice.options)
        unknown = [item for item in picked if item not in allowed]
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
        _land(choice, picked, _label(feat, locale), score, prof, expertise, resist)

    return FeatPicks(
        score=tuple(score),
        proficiencies=frozenset(prof),
        expertise=frozenset(expertise),
        resistances=frozenset(resist),
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
    if choice.kind == "resistance":
        return Text.of("选 %d 种伤害抗性" % choice.count,
                       "Choose %d damage resistances" % choice.count)
    return Text.of(feat.name.get(locale), feat.name.get("en"))


__all__ = [
    "FeatPicks", "picks_for", "collect_picks", "pick_key",
    "hard_problems", "soft_problems", "prereq_report", "choice_prompt",
]
