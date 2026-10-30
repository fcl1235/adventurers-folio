# -*- coding: utf-8 -*-
"""升级：改等级 → 重建，并把「新解锁了什么」「还差选什么」说清楚。

四条设计决定，各因为一个具体问题：

1. **升级不走建卡向导重来一遍**。向导是「从零建一张卡」，走它会把背包、装备、
   当前 HP、已用的资源、力竭与死亡豁免全部丢掉（`new_character` 造的是新角色）。
   升级走 `rebuild_actor`，它专门保这些运行时事实。
2. **但「还差选什么」不能自己判**。子职解锁、精通件数、法术上限各有各的来源，
   这里只把**已有的**表和校验问一遍，不写第二套规则。
3. **升级到 20 级之后不许静默成功**。夹到 20 再返回会让界面欢天喜地地报
   「升到 20 级」，而角色其实一点没变。
4. **熟练加值只看总等级**（C8）：`proficiency_bonus()` 收的是 `TotalLevel`，
   这里不能用「这个职业几级」喂它 —— 兼职角色会算少。
"""

from __future__ import annotations

from typing import Any, Mapping

from ..content import ContentBundle
from ..kernel.errors import RuleError
from ..model.actor import Actor
from ..model.levels import ClassLevel, TotalLevel
from ..model.profile import Profile
from ..rules.build import available_powers, rebuild_actor
from ..rules.progression import MAX_TOTAL_LEVEL, proficiency_bonus


def _power_rows(content: ContentBundle, actor: Actor, locale: str) -> dict[str, dict]:
    """当前角色已解锁的能力，按 id 索引 —— 升级前后取差集就知道新增了什么。"""
    rows: dict[str, dict] = {}
    for power in available_powers(content, actor):
        rows[power.id] = {"id": power.id, "name": power.name.get(locale),
                          "level": int(power.level), "owner": power.owner}
    return rows


def level_up_view(content: ContentBundle, actor: Actor, locale: str = "zh") -> dict:
    """下一级会发生什么：新解锁的能力 + 还需要补的选择。

    `needs` 里的 `step` 直接用建卡向导的步骤 key —— 界面照着它跳过去，
    不需要再维护一张「哪个选择属于哪一步」的映射表。
    """
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案，不能升级")
    primary = profile.classes[0]
    class_id = primary.class_id
    level = int(primary.class_level)
    if level >= 20:
        raise RuleError("这个职业已经 20 级了")
    if int(profile.total) >= MAX_TOTAL_LEVEL:
        raise RuleError("总等级已达上限 %d，不能再升" % MAX_TOTAL_LEVEL)

    class_def = content.class_def(class_id)
    target = level + 1
    upgraded = profile.with_class_level(class_id, target)

    before = _power_rows(content, actor, locale)
    preview = rebuild_actor(content, actor, upgraded)
    after = _power_rows(content, preview, locale)
    # 只看「新出现的」；`row["level"] <= target` 兜住叠层 patch 带来的同 id 旧条目
    unlocks = [row for key, row in sorted(after.items())
               if key not in before and row["level"] <= target]

    needs: list[dict] = []
    if target >= int(class_def.subclass_level) and not profile.subclasses:
        needs.append({"step": "class",
                      "text": "%d 级解锁子职，还没选" % int(class_def.subclass_level)})
    mastery_need = class_def.mastery_count_at(ClassLevel(target))
    if mastery_need and len(profile.masteries) < mastery_need:
        needs.append({"step": "masteries",
                      "text": "%d 级可以精通 %d 件武器，现在记了 %d 件"
                              % (target, mastery_need, len(profile.masteries))})
    gaps = _spell_gaps(class_def, ClassLevel(target), profile, class_id)
    if gaps:
        needs.append({"step": "spells", "text": "还没选满：" + "、".join(gaps)})

    return {
        "class_id": class_id,
        "class_name": class_def.name.get(locale),
        "from_level": level,
        "to_level": target,
        # 熟练加值每 4 级涨一点 —— 升级最直观的那个数字（看总等级，不看单职业）
        "prof_before": proficiency_bonus(TotalLevel(int(profile.total))),
        "prof_after": proficiency_bonus(TotalLevel(int(profile.total) + 1)),
        "hit_die": int(class_def.hit_die),
        "unlocks": unlocks,
        "needs": needs,
        # 生命上限会变（升级加一个生命骰），提前给出来，玩家好判断值不值
        "hp_before": int(actor.root().hp.maximum),
        "hp_after": int(preview.root().hp.maximum),
    }


def _spell_gaps(class_def, level: ClassLevel, profile: Profile,
                class_id: str) -> list[str]:
    """这个等级的法术上限与已选数的差。非施法职业返回空 —— 没有「没选满」这种事。"""
    gaps = []
    want_cantrips = _table_at(class_def.cantrips, int(level))
    want_prepared = _table_at(class_def.prepared, int(level))
    if want_cantrips > len(profile.cantrips_of(class_id)):
        gaps.append("戏法 %d/%d" % (len(profile.cantrips_of(class_id)), want_cantrips))
    if want_prepared > len(profile.spells_of(class_id)):
        gaps.append("法术 %d/%d" % (len(profile.spells_of(class_id)), want_prepared))
    return gaps


def _table_at(table: Mapping[int, int], level: int) -> int:
    """等级表查值：取「不超过 level 的最大那一行」，不是精确匹配。"""
    usable = [int(key) for key in table if int(key) <= int(level)]
    return int(table[max(usable)]) if usable else 0


def level_up(content: ContentBundle, actor: Actor, locale: str = "zh") -> Actor:
    """升一级（主职业）。**保留当前 HP、资源、背包、状态** —— 见模块头注释。"""
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案，不能升级")
    primary = profile.classes[0]
    view = level_up_view(content, actor, locale)      # 顺带把各种上限判掉
    return rebuild_actor(content, actor,
                         profile.with_class_level(primary.class_id, view["to_level"]))


# --- 把现有角色变成一份「草案」，供向导编辑 ---------------------------------
def draft_from_actor(content: ContentBundle, actor: Actor) -> dict:
    """现有角色 → 建卡草案。用于「升级后发现还差选择」时把向导开到那一步。

    两处必须扣掉，否则草案一进向导就报错：

    * **属性取 `base_scores`**（加值之前的原始值）：草案里的 `scores` 表示
      「玩家填进输入框的数」，读显示值会让背景/专长的加值被算第二遍。
    * **技能要扣掉背景已给的那几项**：`Profile.proficiencies` 是合并后的全集，
      而向导里的「已选 N 项」只数**玩家自己挑的**。士兵背景给运动和威吓，
      不扣就会变成「要选 2 项、现在选了 3 项」—— 实测踩到。
    """
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案")
    primary = profile.classes[0]
    class_id = primary.class_id
    name = actor.statblock.name
    background = content.backgrounds.get(profile.background)
    granted = set(background.skills) if background is not None else set()
    picked = [token.split(".", 1)[1] for token in profile.proficiencies
              if token.startswith("skill.")]
    # **空列表不能写成 `{class_id: []}`**：非施法职业带着一个空的戏法表进
    # `new_character`，会被判成「战士不该有戏法」—— 空和没有是两件事。
    cantrips = list(profile.cantrips_of(class_id))
    prepared = list(profile.spells_of(class_id))
    return {
        "name_zh": name.zh,
        "name_en": name.en,
        "class_id": class_id,
        "class_level": int(primary.class_level),
        "subclass": profile.subclasses[0] if profile.subclasses else "",
        "species": profile.species,
        "background": profile.background,
        "background_bonus": dict(profile.background_bonus),
        # 属性是「重新生成」的：标准数组只是初值，玩家可以改成他当初填的那组数。
        # 这里不需要知道当初用的是哪种方式 —— 校验只看数在这一级合不合法。
        "score_mode": "standard_array",
        "scores": {key: int(value) for key, value in profile.base_scores.items()},
        "skills": sorted(key for key in picked if key not in granted),
        "masteries": sorted(profile.masteries),
        "cantrips": {class_id: cantrips} if cantrips else {},
        "prepared": {class_id: prepared} if prepared else {},
    }


def apply_draft(content: ContentBundle, actor: Actor, draft: Mapping[str, Any],
                locale: str = "zh") -> Actor:
    """按草案**改造现有角色**：先造一份新档案，再 `rebuild_actor` 保住运行时状态。

    与建卡向导的 `build_from_draft` 的区别就在这一点：那条路造新角色（背包清空），
    这条路改现有角色。改完 `str` 不该把护甲脱了、血也不该回满。
    """
    from .wizard import build_from_draft      # 循环导入：wizard 侧不反向依赖本模块

    fresh = build_from_draft(content, draft, locale)
    profile: Profile = fresh.profile
    return rebuild_actor(content, actor, profile)
