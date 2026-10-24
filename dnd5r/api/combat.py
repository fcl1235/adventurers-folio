# -*- coding: utf-8 -*-
"""掷骰与出手：检定 / 施法 / 武器攻击 / 借机 / 怪物攻击。

优势/劣势在 `roll_check` 才真的变成「掷两次留一个」；怪物攻击的掷骰模式
按特性事实现场判定（P10b）。拆自 P11 之前的巨型 __init__。"""
from __future__ import annotations

from typing import Any, Sequence

from ..content import ContentBundle
from ..kernel.errors import IllegalAction, PluginError, RuleError
from ..kernel.rng import Rng, SeededRng
from ..model.actor import Actor
from ..rules.contributions import (
    modifiers_for, passive_modifiers, save_modifiers, skill_modifiers,
)
from ..rules.encounter import Encounter
from ._support import (
    ABILITY_KEYS, _dice_mode, _need_ability, _proficiency_sets, resolver_for,
)
from .catalog import _action_table

CHECK_KINDS = ("save", "skill", "ability", "tool", "initiative", "attack")


def roll_check(
    actor: Actor,
    content: ContentBundle,
    kind: str,
    key: str = "",
    rng: Rng | None = None,
    locale: str = "zh",
    ability: str = "",
    use_inspiration: bool = False,
) -> dict:
    """掷一次 d20 检定 —— **优势/劣势在这里才真的变成「掷两次留一个」**。

    `kind` 与 `key`：
      save       key = str/dex/con/int/wis/cha
      skill      key = 技能 key（stealth / athletics …）—— 属性检定 + 熟练 + 专精
      ability    key = str/dex/…（裸属性检定）
      tool       key = 工具 id 或 key（thieves_tools …）；**属性可换**，见下
      initiative 不需要 key
      attack     key = str 或 dex，缺省取调整值较高的那个

    工具的规则是「DM 决定用哪项属性」，所以工具检定允许显式传 `ability` 覆盖
    内容里的**建议属性**；不传就用建议值。

    `use_inspiration=True` 消耗身上一颗灵感骰（别人给的，诗人灵感这类）：
    掷出骰面加进合计。**要不要加是玩家的选择**（原文是「看到失败之后决定」，
    DC 在桌上、不在引擎里）—— 预览一次不带参数看总数，再决定重掷还是加骰。

    返回值里 **`advantage: true`** 就是「该掷两次、取高」这件事本身；
    加值和明细来自与角色卡**同一个** `Resolver`，不会出现「卡上 +7、掷的时候 +5」。
    """
    from ..kernel.dice import roll_d20

    if kind not in CHECK_KINDS:
        raise RuleError("不认识的检定类型：%r（可选 %s）" % (kind, "/".join(CHECK_KINDS)))
    resolver = resolver_for(actor, content)
    top = actor.top()
    mods = passive_modifiers(content, actor, locale)
    saves_prof, skill_tokens, expertise_tokens = _proficiency_sets(actor, content)
    label = ""

    if kind == "save":
        ability = str(key).lower()
        _need_ability(ability)
        mode, mode_sources = _dice_mode(content, actor, "save.%s" % ability)
        resolution = resolver.saving_throw(
            top, ability, proficient=ability in saves_prof,
            modifiers=save_modifiers(mods, ability),
            mode=mode, mode_sources=mode_sources)
        label = "save.%s" % ability
    elif kind == "skill":
        # 两种写法都认：内容 id（`dnd2024.skill.stealth`）与内核 key（`stealth`）。
        # 界面手里多半是 id，手写脚本/测试多半是 key —— 只认一种就会有人踩空。
        skill = content.skills.get(str(key))
        if skill is None:
            skill = next((item for item in content.skills.values()
                          if item.key == str(key)), None)
        if skill is None:
            raise RuleError("不认识的技能：%r" % (key,))
        token = "skill.%s" % skill.key
        proficient = token in skill_tokens      # 保底原语（可靠天赋）要看熟练
        mode, mode_sources = _dice_mode(content, actor, "check.%s" % skill.key)
        resolution = resolver.ability_check(
            top, skill.ability, proficient=proficient,
            expertise=token in expertise_tokens,
            modifiers=skill_modifiers(mods, skill.key),
            mode=mode, mode_sources=mode_sources)
        label = skill.name.get(locale) or skill.key
    elif kind == "ability":
        ability = str(key).lower()
        _need_ability(ability)
        mode, mode_sources = _dice_mode(content, actor, "check.%s" % ability)
        resolution = resolver.ability_check(top, ability, mode=mode, mode_sources=mode_sources)
        label = ability.upper()
    elif kind == "tool":
        # 两种写法都认：内容 id（`dnd2024.tool.thieves_tools`）与 key（`thieves_tools`）
        tool = content.tools.get(str(key))
        if tool is None:
            tool = next((item for item in content.tools.values()
                         if item.key == str(key)), None)
        if tool is None:
            raise RuleError("不认识的工具：%r" % (key,))
        # 规则里工具**不绑属性**（「DM 决定用哪项」），内容里的只是建议值。
        # 所以这里允许覆盖，而不是拿建议值当唯一答案。
        picked = str(ability).lower() or tool.ability
        _need_ability(picked)
        token = "tool.%s" % tool.key
        proficient = token in skill_tokens      # 同上
        mode, mode_sources = _dice_mode(content, actor, "check.%s" % picked)
        # 加值只取「这件工具」与「所有属性检定」两档：技能专属的加值不该串过来
        resolution = resolver.ability_check(
            top, picked, proficient=token in skill_tokens,
            modifiers=(modifiers_for(mods, token)
                       + modifiers_for(mods, "skill_check")),
            mode=mode, mode_sources=mode_sources)
        label = "%s（%s）" % (tool.name.get(locale) or tool.key, picked.upper())
    elif kind == "initiative":
        mode, mode_sources = _dice_mode(content, actor, "initiative")
        resolution = resolver.initiative(top, mode=mode, mode_sources=mode_sources)
        label = "先攻"
    else:
        ability = str(key).lower() or (
            "str" if top.statblock.abilities.mod("str") >= top.statblock.abilities.mod("dex")
            else "dex")
        _need_ability(ability)
        mode, mode_sources = _dice_mode(content, actor, "attack.%s" % ability)
        resolution = resolver.attack_bonus(top, ability, proficient=True,
                                           modifiers=modifiers_for(mods, "attack"),
                                           mode=mode, mode_sources=mode_sources)
        label = "攻击（%s）" % ability.upper()

    roller = rng or SeededRng()
    roll = roll_d20(roller, resolution.mode)
    die = roll.total
    override = _apply_override_outcome(
        content, actor, kind, locals().get("proficient", False), die)
    if override:
        die = override[0]
    inspiration = _spend_inspiration(actor, roller, use_inspiration)
    kept = roll.parts[0].rolls
    dropped = roll.parts[0].dropped if roll.parts else ()
    return {
        "kind": kind,
        "key": key,
        "label": label,
        "mode": resolution.mode,
        "advantage": resolution.mode == "adv",
        "disadvantage": resolution.mode == "dis",
        "mode_sources": list(resolution.mode_sources),
        "die": die,
        "die_raw": roll.total,
        "kept": list(kept),
        "dropped": list(dropped),
        "modifier": resolution.total,
        "total": die + resolution.total + (inspiration["roll"] if inspiration else 0),
        "detail": resolution.describe(),
        # 一次性标记**不在这里消费**：这是通用的掷骰工具（预览、补掷都用它），
        # 悄悄改状态会让人「随便掷一下就丢了优势」。真打要走 `attack_roll`。
        # 但优势确实按标记算进去了，所以必须提示它还在。
        "marks_pending": marks_of(actor) if kind == "attack" else [],
        "inspiration": inspiration,
        "tokens_pending": tokens_of(actor),
        "notes": ([override[1]] if override else [])
                 + ([inspiration["note"]] if inspiration else []),
    }


def tokens_of(actor: Actor) -> list[dict]:
    """身上还挂着的授予骰（诗人灵感这类）。与 marks_of 同一个口径：只读。"""
    rows = []
    for mark in actor.root().marks.matching(lambda item: item.kind == "token"):
        rows.append({
            "id": mark.id, "label": mark.label or mark.source,
            "dice": mark.dice, "uses": int(mark.uses),
            "source": mark.source, "expires": mark.expires,
            "text": "%s：下一次 d20 检定可加 %s（%s）"
                    % (mark.label or "授予骰", mark.dice, mark.source),
        })
    return rows


def _spend_inspiration(actor: Actor, roller, enabled: bool):
    """掷并消耗一颗灵感骰。没有骰却要求用 = 报错（不是静默不加）。"""
    if not enabled:
        return None
    from ..kernel.dice import parse as parse_dice
    from ..kernel.errors import RuleError

    held = actor.root().marks.matching(lambda item: item.kind == "token")
    if not held:
        raise RuleError("身上没有待用的灵感骰（诗人要先用附赠动作给你一颗）")
    token = held[0]
    result = parse_dice(token.dice).roll(roller)
    actor.root().marks.consume(lambda item: item is token)
    return {
        "label": token.label or token.source,
        "dice": token.dice,
        "roll": result.total,
        "detail": result.describe(),
        "note": "%s %s 掷出 %d，加进本次合计" % (token.label or "灵感骰",
                                               token.dice, result.total),
    }


def _apply_override_outcome(content, actor, kind: str, proficient: bool, die: int):
    """结算后修正：可靠天赋这类「低面保底」。返回 (保底后的骰面, 说明) 或 None。

    只对 check（技能/工具）挂这一版 —— save/attack 的用例（闪避、幸运一击）
    还没有内容条目，通道先留着。优势/劣势取高/低之后的**保留骰**是判定面。
    """
    if kind not in ("skill", "tool"):
        return None
    from ..rules.build import available_powers
    from ..rules.effects.outcome import OverrideOutcome

    best = None
    label = ""
    for power in available_powers(content, actor):
        for effect in power.effects:
            if not isinstance(effect, OverrideOutcome):
                continue
            if effect.applies_to != "check":
                continue
            if effect.when_proficient and not proficient:
                continue
            if die <= effect.when_die_lte:
                if best is None or effect.set_die > best.set_die:
                    best = effect
                    label = power.name.zh
    if best is None:
        return None
    return best.set_die, "%s：骰出 %d 按 %d 计（d20 ≤ %d 保底）" % (
        label, die, best.set_die, best.when_die_lte)


def roll_spell(

    actor: Actor,
    content: ContentBundle,
    spell_id: str,
    slot: int | None = None,
    targets: Sequence[Any] = (),
    rng: Rng | None = None,
    locale: str = "zh",
    class_id: str = "",
    apply: bool = False,
    seed: int | None = None,
    free: bool = False,
    encounter: "Encounter | None" = None,
    summon_id: str = "",
    summon_size: str = "",
) -> dict:
    """掷一次施法结算：命中/豁免 → 伤害骰 → 抗性 → （可选）落到 HP。

    `targets` 既收 `Target`（DM 手填的「AC 15、敏捷 +2」），也收 `Actor`
    （建好的怪、召唤物、队友）。

    `apply=False` 是**只算不落库**：界面预览「这一发打出去会怎样」，
    点确认才用 `apply=True` 真扣血、真记免费施放次数。默认不改状态，是因为
    误点一下就动了别人的血条，比多点一次麻烦得多。

    `free=True` 用专长给的那一次免费施放（不消耗法术位）：扣的是
    `resources` 里**绑在这道法术上**的那个池。
    """
    from ..rules.combat import Target, casting_for, resolve_spell, target_from_actor

    prepared = [item if isinstance(item, Target)
                else target_from_actor(content, item, locale)
                for item in targets]
    roller = rng or SeededRng(seed)
    result = resolve_spell(content, actor, spell_id, slot, prepared,
                           roller, locale, class_id, apply, free)
    _join_summons(content, actor, spell_id, slot, class_id, apply,
                  encounter, summon_id, summon_size, roller, locale, result)
    return result


def attack_roll(
    attacker: Actor,
    content: ContentBundle,
    target: Any,
    weapon: str = "",
    off_hand: bool = False,
    rng: Rng | None = None,
    seed: int | None = None,
    locale: str = "zh",
    apply: bool = False,
    extras: Any = (),
    encounter: "Encounter | None" = None,
) -> dict:
    """掷一次武器攻击：命中 → 伤害 → 额外伤害 → 抗性 →（可选）落到 HP。

    `target` 既收 `Target`（DM 手填的「AC 15」），也收 `Actor`（建好的怪、队友）。

    `apply=False` 是**只算不落库**：不扣血、不消耗优势标记、不记「每回合一次」的账。
    这与 `roll_spell` 同一条规矩 —— 误点一下就动了别人的血条，比多点一次麻烦。

    `extras` 是这次要不要加额外伤害（月华形态的「每回合一次 +2d10」这类）。
    默认**不加**，只把可用项列在 `extras.available` 里：原文写的是
    "you can deal an extra 2d10"，加不加是玩家的选择。

    传了 `encounter` 就**必须用它的动作额度**：自己回合、还有动作（副手用附赠）。
    不传 = 不记账（老调用方与单测都还在用这条路），报告里 `economy.preview=True`。
    """
    from ..rules.actioneconomy import ActionType
    from ..rules.attack import resolve_attack
    from ..rules.combat import Target, target_from_actor

    prepared = target if isinstance(target, Target) \
        else target_from_actor(content, target, locale)
    kind = ActionType.BONUS if off_hand else ActionType.ACTION
    combatant = None
    if encounter is not None:
        combatant = encounter.get(attacker)
        if encounter.current() is not combatant:
            raise IllegalAction("现在不是 %s 的回合" % combatant.label)
        if apply and not combatant.economy.can_pay(kind):
            raise IllegalAction("%s 没有可用的%s" % (combatant.label, kind.value))
    result = resolve_attack(
        content, attacker, prepared, weapon, off_hand,
        rng or SeededRng(seed), apply=apply, locale=locale, extras=extras)
    if combatant is not None:
        if apply:
            combatant.economy.pay(kind, combatant.label)
        result["economy"] = {"kind": kind.value,
                             "after": combatant.economy.to_dict(),
                             "preview": not apply}
    else:
        result["economy"] = {"kind": "", "after": None, "preview": True}
    return result


def opportunity_attack(
    encounter: Encounter,
    content: ContentBundle,
    attacker: Actor,
    target: Any,
    rng: Rng | None = None,
    seed: int | None = None,
    locale: str = "zh",
    apply: bool = False,
    extras: Any = (),
) -> dict:
    """借机攻击：花掉攻击者的**反应**，掷一次武器攻击。

    触发条件（走出触及范围）由 `move()` 报的 `left_reach` 判断 —— **这里不再判距离**：
    移动已经发生，两人现在多半已经超过 5 尺，用现在的位置判会永远说「够不着」。
    这是「借机攻击」最容易写错的一点，所以把判断留在移动那一步。

    `apply=False` 预览：掷骰但不扣反应、不扣血。
    """
    from ..rules.actioneconomy import ActionType
    from ..rules.attack import resolve_attack
    from ..rules.combat import Target, target_from_actor

    combatant = encounter.get(attacker)
    if int(combatant.economy.reaction) <= 0:
        raise IllegalAction("%s 这一轮的反应已经用掉了" % combatant.label)
    prepared = target if isinstance(target, Target) \
        else target_from_actor(content, target, locale)
    result = resolve_attack(
        content, attacker, prepared, "", False,
        rng or SeededRng(seed), apply=apply, locale=locale, extras=extras)
    before = int(combatant.economy.reaction)
    if apply:
        combatant.economy.pay(ActionType.REACTION, combatant.label)
    result["reaction"] = {"before": before,
                          "after": int(combatant.economy.reaction),
                          "preview": not apply}
    result["notes"] = list(result["notes"]) + [
        "借机攻击走反应额度，不占动作" + ("（预览：反应未扣）" if not apply else "")]
    return result


# --- 怪物 ---------------------------------------------------------------


def monster_attack(
    encounter: Encounter,
    content: ContentBundle,
    who: Any,
    key: str,
    target: Any,
    rng: Rng | None = None,
    seed: int | None = None,
    locale: str = "zh",
    apply: bool = False,
    mode: str = "",
) -> dict:
    """怪物（或变形中的角色）打一次：`key` 是 `monster_actions` 里的 `action:0` 这种键。

    三条与玩家武器攻击不同的地方，都是「怪物不是玩家」带来的：

    1. **命中加值用卡上的数**（见 `rules/monsters.py`），不经过 Resolver
    2. **优势/劣势按特性事实现场判定**（群体战术：目标的 5 尺内有没有它这一伙
       的人 —— 阵营 + 位置）。判不了（没摆位、手填目标）就平掷并在报告里说明，
       `mode="adv"/"dis"/"flat"` 可手动指定，手动值优先于特性判定。
    3. **动作额度按槽位付**：`action` / `bonus` / `reaction`。反应可以在别人回合用，
       动作与附赠必须是自己回合 —— 与玩家同一条规矩。

    **变形中的角色也走这一条**：荒野变形的天然武器是三槽动作里的一种，
    与怪物同一套形状、同一条结算。所以这里看的是 `actor.top()`（谁现在长着爪子），
    不是本体是 pc 还是 monster。

    `apply=False` 预览：掷骰但不扣额度、不扣血。
    """
    from ..rules.actioneconomy import ActionType
    from ..rules.attack import resolve_monster_attack
    from ..rules.combat import Target, target_from_actor
    from ..rules.monsters import find_attack, trait_attack_mode

    combatant = encounter.get(who)
    monster = _action_table(content, combatant.actor)
    try:
        slot, raw_index = str(key).split(":", 1)
        attack = find_attack(monster, slot, int(raw_index))
    except (ValueError, PluginError) as exc:
        raise RuleError("动作键不认识：%r（应形如 action:0，原因：%s）" % (key, exc))

    kind = {"action": ActionType.ACTION, "bonus": ActionType.BONUS,
            "reaction": ActionType.REACTION}.get(slot, ActionType.NONE)
    # 「多重攻击」「其余」只是一句说明，不是一次行动 —— 不替 DM 记账。
    pays = attack.kind in ("melee", "ranged", "save")
    if kind is not ActionType.REACTION and encounter.current() is not combatant:
        raise IllegalAction("现在不是 %s 的回合；只有反应能在别人回合里用"
                            % combatant.label)
    if apply and pays and not combatant.economy.can_pay(kind):
        raise IllegalAction("%s 没有可用的%s" % (combatant.label, kind.value))

    prepared = target if isinstance(target, Target) \
        else target_from_actor(content, target, locale)
    # 掷骰模式：特性事实先折一版（群体战术这类）；判不了的说明放进 notes。
    # 手动指定优先 —— DM 说这掷有优势，程序不跟他争「你旁边其实没有狼」。
    chosen, sources, pending = "flat", (), ()
    if attack.is_attack_roll:
        if mode:
            if mode not in ("flat", "adv", "dis"):
                raise RuleError("掷骰模式只能是 flat/adv/dis：%r" % (mode,))
            chosen, sources, pending = mode, (), (
                "掷骰模式按手动指定（%s），未看特性" % mode,)
        else:
            chosen, sources, pending = trait_attack_mode(
                getattr(monster, "traits", ()) or (),
                encounter, combatant.actor,
                getattr(prepared, "actor", None), locale)
    result = resolve_monster_attack(
        combatant.actor, attack, prepared, rng or SeededRng(seed),
        apply=apply, locale=locale, mode=chosen, mode_sources=sources)
    if pending:
        result["notes"] = list(result["notes"]) + list(pending)
    result["action"]["key"] = key
    result["action"]["slot"] = slot
    if pays:
        if apply:
            combatant.economy.pay(kind, combatant.label)
        result["economy"] = {"kind": kind.value,
                             "after": combatant.economy.to_dict(),
                             "preview": not apply}
    else:
        result["economy"] = {"kind": "", "after": combatant.economy.to_dict(),
                             "preview": not apply}
        result["notes"] = list(result["notes"]) + [
            "这条只是说明（%s），没有占用动作额度" % attack.kind]
    return result


def attack_options(actor: Actor, content: ContentBundle, locale: str = "zh") -> dict:
    """出手前能选什么：额外伤害清单 + 身上待用的一次性标记。

    界面拿它画「勾选项」与「优势待用」的提示。两边读的是同一份状态
    （`Actor.marks` + 常驻能力的 `extra_damage`），不另存计数器。
    """
    from ..rules.attack import extra_damage_options

    return {
        "extras": extra_damage_options(content, actor, locale),
        "marks": marks_of(actor),
    }


def marks_of(actor: Actor) -> list[dict]:
    """身上还没用掉的一次性标记（本回合的下一次攻击优势这类）。"""
    labels = {
        "turn": "本回合结束前", "round": "本轮结束前", "never": "直到被移除",
    }
    rows: list[dict] = []
    for mark in actor.root().marks.active():
        word = "优势" if mark.mode == "adv" else "劣势"
        rows.append({
            "id": mark.id,
            "kind": mark.kind,
            "target": mark.target,
            "mode": mark.mode,
            "source": mark.source,
            "label": mark.label,
            "uses": int(mark.uses),
            "expires": mark.expires,
            "text": "%s：%s（%s，%d 次）"
                    % (word, mark.target, labels.get(mark.expires, mark.expires),
                       int(mark.uses)),
        })
    return rows


def _join_summons(content, actor, spell_id, slot, class_id, apply,
                  encounter, summon_id, summon_size, roller, locale, result) -> None:
    """召唤法术 apply 后把生物真的放进遭遇战（P13）。

    没有遭遇战就明说「未结算」—— 生物卡在法术详情里仍然完整可读。
    多个变体（巨虫三选一 / 异界坐骑三种）用 `summon_id` 挑，缺省取第一个
    并在报告里说明还有哪些可选。
    """
    summons = content.summons_for_spell(spell_id)
    if not summons or not apply:
        return
    notes = result.setdefault("notes", [])
    if encounter is None:
        notes.append("召唤未结算：没有遭遇战（生物卡见法术详情，AC/HP 都是算好的）")
        return
    from ..rules.combat import casting_for
    from ..rules.summon import build_summon_actor

    spell = content.spell(spell_id)
    casting = casting_for(content, actor, spell, class_id, locale)
    picked = next((row for row in summons if row.id == summon_id), summons[0])
    used_slot = int(slot or spell.level)
    body, table = build_summon_actor(picked, used_slot, casting.attack,
                                     casting.dc, summon_size, 1, locale)
    body.summon_table = table
    side = encounter.get(actor).side if encounter.has(actor) else "party"
    combatant = encounter.join(body, roller, side=side)
    result["summon"] = {
        "id": body.id, "label": combatant.label,
        "ac": int(body.statblock.ac_base + body.statblock.abilities.mod("dex")),
        "hp": int(body.hp.maximum),
        "initiative": int(combatant.initiative),
        "side": combatant.side,
        "options": [row.id for row in summons if row.id != picked.id],
    }
    extra = ("（其余可选：%s，要换请传 summon_id）"
             % "、".join(result["summon"]["options"])) if result["summon"]["options"] else ""
    notes.append("召唤出 %s（AC %d / HP %d / 先攻 %d，%s 阵营）%s"
                 % (combatant.label, result["summon"]["ac"], result["summon"]["hp"],
                    combatant.initiative,
                    "我方" if combatant.side == "party" else "敌方", extra))
