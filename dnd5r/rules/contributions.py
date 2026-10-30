# -*- coding: utf-8 -*-
"""常驻贡献：把「被动能力写下的东西」变成 Resolver 的输入。

为什么需要这一层：`grant_modifier` 的 `apply()` 只在**用一次能力**的时候跑
（狂暴、光环的临时层）。可被动的无甲防御、守护灵光从不需要「用」——
它们必须每次都算进去。P2 只实现了「用的时候给」，没实现「一直都在」，
所以 12 职业对账时 AC 与豁免全对不上。

这一层不做规则判断，只做收集：
  1. 已解锁被动的 grant_modifier / grant_defense / grant_proficiency
  2. 角色身上生效中的 ActiveEffect（狂暴这类有时限的）
  3. **属性加值通道**（`score.<属性>`）：它改的是属性值本身，不进 d20 管道，
     由 `score_bonuses()` 收集、`apply_score_bonuses()` 在建角色时一次算清

`when` 条件仍由 resolve() 求值，facts 由 `facts_for()` 提供。
"""

from __future__ import annotations

from dataclasses import replace

from typing import Any

from ..kernel.predicate import evaluate
from ..kernel.errors import DndError, RuleError
from ..model.actor import Actor
from ..rules.progression import proficiency_bonus
from ..model.levels import ClassLevel
from .armor import Loadout
from .build import available_powers, owner_class_id
from .modifiers import Modifier
from .powers import Power
from .scores import (
    ScoreBonus, apply_score_bonuses, score_bonus_of, score_bonuses,
)


def facts_for(
    actor: Actor,
    class_level: ClassLevel | None = None,
    loadout: Loadout | None = None,
) -> dict[str, Any]:
    """条件求值用的事实。少写一个事实 = 条件永远是 False，所以这里只放确定的。

    `unarmored` 是「没穿护甲」，`shield` 是「拿着盾」，`armor` 是护甲类别
    （light / medium / heavy / None）——
    野蛮人的无甲防御允许持盾、武僧的不允许；野蛮人与游侠的快速移动只禁**重型**护甲。
    这些差别全靠这几条事实 + 内容里的 `when` 表达，代码里不出现职业判断。
    """
    pool = actor.root().hp
    top = actor.top()
    gear = loadout if loadout is not None else Loadout()
    facts: dict[str, Any] = {
        "hp": pool.current,
        "hp_max": pool.maximum,
        "temp_hp": pool.temp,
        "morphed": top.layer is not None,
        "unarmored": gear.unarmored,
        "shield": gear.shielded,
        "armor": None if gear.armor is None else gear.armor.category,
        "conditions": set(actor.conditions.ids()),
    }
    if class_level is not None:
        facts["class_level"] = int(class_level)
    return facts


# --- 属性加值通道 -----------------------------------------------------
# 实现在 rules/scores.py：本模块要 import build，build 建角色又要用这套函数，
# 直接写在这里就成环了。


def _unlocked(bundle, actor: Actor) -> list[Power]:
    return list(available_powers(bundle, actor))


def passive_modifiers(bundle, actor: Actor, locale: str = "zh") -> tuple[Modifier, ...]:
    """角色当前所有常驻 Modifier。

    `source` 用**能力的显示名**而不是 id：它会出现在明细里（
    「14 = 12 基础 +2 无甲防御」），id 出现在玩家眼前只是噪音。
    """
    found: list[Modifier] = []
    profile = actor.profile
    prof = proficiency_bonus(profile.total) if profile else 2
    for power in _unlocked(bundle, actor):
        label = power.name.get(locale) or power.id
        owner_lv = None
        if profile is not None:
            owner = owner_class_id(bundle, power)
            if owner is not None and profile.has_class(owner):
                owner_lv = profile.class_level(owner)
        for effect in power.effects:
            for mod in getattr(effect, "modifiers", ()):
                mod = _bind_class_level(mod, actor, owner_lv, prof)
                found.append(mod if mod.source else _with_source(mod, label))
    for node in (actor.root(), actor.top()):
        for effect in node.effects:
            for mod in getattr(effect, "modifiers", ()):
                found.append(mod if mod.source else _with_source(mod, effect.id))
    return tuple(found)


def _with_source(mod: Modifier, source: str) -> Modifier:
    return Modifier(
        target=mod.target, value=mod.value, stack=mod.stack, source=source,
        scope=mod.scope, direction=mod.direction, when=mod.when, cap=mod.cap,
        exclusive=mod.exclusive,
    )


def _bind_class_level(mod: Modifier, actor: Actor, owner_lv, prof: int) -> Modifier:
    """把引用 class_level 的 Amount 按**所属职业**的等级先算成数。

    修饰值管道不带「这条来自哪个职业」：多职业时 resolver 的 ctx 给不出
    正确的 class_level（武僧的移动表要按武僧等级查，不是主职业等级）。
    在收集点绑定一次 —— 明细里显示的也就是这个数，不另有一套。
    算不了的（带骰子之类）保持原样，让 resolve 报它本来就有的错。
    """
    if owner_lv is None:
        return mod
    evaluate = getattr(mod.value, "evaluate", None)
    if not callable(evaluate) or isinstance(mod.value, (int, bool)):
        return mod
    top = actor.top()
    ctx = {
        "prof_bonus": int(prof),
        "total_level": int(actor.profile.total) if actor.profile else 1,
        "class_level": int(owner_lv),
        "abilities": top.statblock.abilities,
        "speeds": dict(top.statblock.speeds),
    }
    try:
        return replace(mod, value=int(evaluate(ctx)))
    except (RuleError, DndError):
        return mod


def passive_proficiencies(bundle, actor: Actor) -> set[str]:
    """被动给的永久熟练（无甲防御之外的「全部豁免熟练」这类）。

    临时熟练（有时限或条件）不走这里 —— 它们留在 ActiveEffect 里。
    """
    tokens: set[str] = set()
    for power in _unlocked(bundle, actor):
        for effect in power.effects:
            tokens |= set(getattr(effect, "tokens", ()) or ())
    return tokens


def passive_defenses(bundle, actor: Actor) -> tuple[set[str], set[str]]:
    """被动能力给的抗性与免疫（`grant_defense`）。

    返回 (抗性集合, 免疫集合)。这两个是**集合**，不是加减法 ——
    与熟练同一类，所以不走 Modifier 管道。
    """
    resist: set[str] = set()
    immune: set[str] = set()
    for power in _unlocked(bundle, actor):
        for effect in power.effects:
            resist |= set(getattr(effect, "resistance", ()) or ())
            immune |= set(getattr(effect, "immunity", ()) or ())
    return resist, immune


def modifiers_for(modifiers, target: str) -> list[Modifier]:
    """按 target 过滤。`resolve()` 不做过滤，调用方必须自己分开。"""
    return [mod for mod in modifiers if mod.target == target]


def passive_advantage_modes(bundle, actor: Actor, query: str) -> tuple[str, tuple[str, ...]]:
    """被动能力给的掷骰模式：`query` 是这次检定的名字（`save.dex` / `initiative` / …）。

    四条来源合并成一次判断（`rules/advantage.merge`）：

      1. 常驻能力里的 `grant_advantage`
      2. 能力的 `when` 条件 —— 在**这里**判，用 `facts_for` 的事实（含失能状态）
      3. 运行期挂在角色身上、还没过期的标记（狂暴、法术效果）
      4. 一次性标记（`Actor.marks`，如「本回合下一次攻击优势」）—— 只读，
         消费发生在真正掷过之后（`advantage.consume_marks`）

    返回 (模式, 来源列表)。`flat` 就是「什么都没发生」。
    """
    from .advantage import merge, mark_modes, modes_from_effects, target_matches
    from .effects.grants import GrantAdvantage

    facts = facts_for(actor)
    modes: list[str] = []
    sources: list[str] = []
    for power in _unlocked(bundle, actor):
        for effect in power.effects:
            if not isinstance(effect, GrantAdvantage):
                continue
            if effect.when is not None and not evaluate(effect.when, facts):
                continue
            if not target_matches(effect.target, query):
                continue
            modes.append(effect.mode)
            sources.append(power.name.get("zh") or power.id)
    runtime_mode, runtime_sources = modes_from_effects(actor, query)
    modes.append(runtime_mode)
    sources.extend(runtime_sources)
    marked_mode, marked_sources = mark_modes(actor, query)
    modes.append(marked_mode)
    sources.extend(marked_sources)
    return merge(modes), tuple(sources)


def save_modifiers(modifiers, ability: str) -> list[Modifier]:
    return modifiers_for(modifiers, "save.%s" % ability)


def skill_modifiers(modifiers, skill_key: str) -> list[Modifier]:
    """技能检定的加值：通用（`skill_check`）+ 指定技能（`skill.stealth`）两档。

    两档都收，是因为内容里两种写法都自然：「所有感知检定 +2」与
    「隐匿检定 +2」。合成一份交给 `ability_check`，加值明细里才看得见来源。
    """
    return (modifiers_for(modifiers, "skill.%s" % skill_key)
            + modifiers_for(modifiers, "skill_check"))


# --- 诚实标记 ---------------------------------------------------------
# 界面上必须能回答一个问题：「这条能力真的进了数值，还是只是规则文字？」
# 不标出来的后果是玩家以为已经算过了 —— 那比不算更糟。
APPLIED_CHANNELS = ("defense", "modifier", "proficiency", "score")
# 影响**掷骰形状**而不是静态数值的通道：优势 / 劣势。P7 起有消费方
# （`rules/advantage.py` + `api.roll_check`），但它永远不进合计 ——
# 所以既不能报「已计入数值」，也不能再报「没人消费」。
ROLL_CHANNELS = ("advantage",)
# 命中时才结算的通道（`extra_damage`）。它没有按钮，但也不是「没算」——
# 攻击结算（`rules/attack`）会把它列进「可以加的额外伤害」。
HIT_CHANNELS = ("on_hit",)
# 认得出来但**还没有消费方**的通道。P7 之前这里是 `("advantage",)` ——
# 优势有了掷骰消费方以后就空了。留着这个空元组是为了让 `power_status` 的分支
# 与将来新出现的「认得但没算」通道共用一条路，而不是临时加 if。
MANUAL_CHANNELS: tuple[str, ...] = ()
CHANNEL_ZH = {"modifier": "加值", "score": "属性", "proficiency": "熟练",
              "defense": "抗性/免疫", "advantage": "优势/劣势（掷骰时生效）",
              "on_hit": "命中时结算", "text": "说明文字"}


def power_channels(power: Power) -> tuple[str, ...]:
    """这个能力实际触碰了哪些通道。空 = 只有说明文字。"""
    from .effects.grants import (      # 局部导入：effects 会 import 本包的 Modifier
        GrantAdvantage, GrantDefense, GrantModifier, GrantProficiency,
    )
    from .effects.exchange import Exchange
    from .effects.morph import Morph
    from .effects.onhit import ExtraDamage
    from .effects.state import MarkAdvantage
    from .effects.token import GrantToken

    found: set[str] = set()
    for effect in power.effects:
        if isinstance(effect, (Exchange, GrantToken)):
            # 兑换要选环级、授予要指认受益者 —— 界面据 channels 出选择行
            found.add("exchange" if isinstance(effect, Exchange) else "token")
        elif isinstance(effect, Morph):
            # 变形要先选形态。没有这条，界面上的「使用」按钮一定失败
            # （effects/morph.py 会抛「变形需要先选一个形态」）
            found.add("form")
        elif isinstance(effect, GrantModifier):
            targets = {str(item.target) for item in effect.modifiers}
            # `score.<属性>` 改的是属性值本身，与 d20 加值是两条路
            found.add("score" if any(item.startswith("score.") for item in targets)
                      else "modifier")
        elif isinstance(effect, GrantProficiency):
            found.add("proficiency")
        elif isinstance(effect, GrantDefense):
            found.add("defense")
        elif isinstance(effect, (GrantAdvantage, MarkAdvantage)):
            # 一次性标记与常驻优势是同一条掷骰形状通道，只是有没有「用完即消」
            found.add("advantage")
        elif isinstance(effect, ExtraDamage):
            found.add("on_hit")
    return tuple(sorted(found))


def power_status(power: Power) -> str:
    """六种状态，别合并：

    - `counted` 已经进了常驻数值（加值/属性/熟练/抗性）
    - `dice`    影响掷骰形状（优势/劣势）——**不进合计**，但掷骰时会生效
    - `active`  有按钮，数值在**使用那一刻**结算（回气、行动激增）
    - `onhit`   命中时结算（`extra_damage`，「每回合一次 +2d10」那种）——
                没有按钮，也不进常驻数值，攻击结算里会列出来
    - `manual`  认得出但还没有消费方
    - `text`    只有说明文字，什么都没算

    `dice` 必须与 `counted` 分开：把优势算进数值加成会直接算错（那不是 +5），
    而归进 `text` 又是另一种撒谎（它明明已经生效了）。

    `onhit` 必须与 `active` 分开：`active` 的界面文案是「点按钮才结算」，
    而月华形态根本没有按钮 —— 归进 `active` 会让玩家到处找那个按钮。

    **有按钮的排在最前**：玩家最需要知道的是「这个能力现在能不能点」，
    点下去之后优势会自己生效。月光步既挂一次性优势（dice）又是按钮，
    标成 dice 会让人以为它是被动能力。
    """
    channels = set(power_channels(power))
    if power.is_button:
        return "active"
    if channels & set(HIT_CHANNELS):
        return "onhit"
    if channels & set(ROLL_CHANNELS):
        return "dice"
    if channels & set(APPLIED_CHANNELS):
        return "counted"
    if channels & set(MANUAL_CHANNELS):
        return "manual"
    return "text"


__all__ = [
    "facts_for", "passive_modifiers", "passive_proficiencies", "passive_defenses",
    "modifiers_for", "save_modifiers", "skill_modifiers",
    "ScoreBonus", "score_bonuses", "score_bonus_of", "apply_score_bonuses",
    "passive_advantage_modes", "power_channels", "power_status",
    "APPLIED_CHANNELS", "ROLL_CHANNELS", "HIT_CHANNELS",
    "MANUAL_CHANNELS", "CHANNEL_ZH",
]
