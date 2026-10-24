# -*- coding: utf-8 -*-
"""武器攻击结算：命中 → 伤害 → 额外伤害 → 抗性 → 落 HP。

在此之前全项目**没有攻击的伤害管线**：`api.roll_check(kind="attack")` 只掷
一个 d20 加值（连「打到没有」都判不了，因为它没有目标），角色卡上的攻击卡
只有算式。于是两条规则无处安放：

  * 月华形态「每回合一次 +2d10」—— 没有地方加这 2d10
  * 月光步「下一次攻击优势」—— 优势是掷骰形状，掷完该消失

## 三件事必须分开写

1. **命中判定**：d20 + 攻击加值 vs AC，门槛用 `attack.crit_min`（19-20 重击）
2. **伤害**：武器骰 + 属性调整值，重击**加骰不加定值**
3. **额外伤害**：每段单独掷、单独算抗性 —— 光耀那 2d10 不该被「挥砍抗性」减半

额外伤害为什么默认**不加**：原文写的是 "you can deal an extra 2d10"，
是玩家的选择。默认自动加等于替玩家决定，而且会让「这回合想留着打别人」
变成做不到。所以默认只把可用项列出来（`extras_available`），
要加就显式传 `extras=["…"]` 或 `extras="all"`。

## 状态改动只在 apply=True 时发生

`apply=False`（缺省）是预览：掷骰、算数、什么都不改 —— 包括不消耗优势标记、
不记「每回合一次」的账。与 `resolve_spell` 同一条规矩。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from ..content import ContentBundle
from ..kernel.dice import Dice, parse as parse_dice, roll_d20
from ..kernel.errors import RuleError
from ..kernel.predicate import evaluate
from ..kernel.rng import Rng, SeededRng
from ..model.actor import Actor
from ..model.marks import Mark
from .armor import loadout_for
from .advantage import consume_marks, merge
from .build import available_powers
from .combat import Target
from .contributions import (
    facts_for, modifiers_for, passive_advantage_modes, passive_modifiers,
    passive_proficiencies,
)
from .derived import resolver_for
from .effects.onhit import ExtraDamage
from .resolver import CRIT_ON_20
from .weapons import AttackProfile, damage_name, is_ranged, profiles_for

__all__ = [
    "attack_profile", "extra_damage_options", "resolve_attack",
]


def _tokens(bundle: ContentBundle, actor: Actor) -> set[str]:
    tokens = set(actor.profile.proficiencies) if actor.profile else set()
    tokens |= passive_proficiencies(bundle, actor)
    return tokens


def attack_profile(
    bundle: ContentBundle,
    attacker: Actor,
    weapon_id: str = "",
    off_hand: bool = False,
    locale: str = "zh",
) -> AttackProfile:
    """取这次攻击用哪条算式。

    与角色卡**同一套**输入（`profiles_for` + 远程/近战加值），否则会出现
    「卡上写 +7、掷的时候 +5」—— 这类分叉是这套代码里最难发现的错。
    """
    resolver = resolver_for(attacker, bundle.armors)
    top = attacker.top()
    mods = passive_modifiers(bundle, attacker, locale)
    morphed = top.layer is not None
    # 变形期间武器加值不生效（形态攻击不是武器攻击），与角色卡同一条件
    ranged = 0 if morphed else resolver.bonus(
        modifiers_for(mods, "attack.ranged")).total
    melee = 0 if morphed else resolver.bonus(
        modifiers_for(mods, "attack.melee")).total
    found = profiles_for(
        attacker, bundle.weapons, top.statblock.abilities,
        resolver.ctx.prof_bonus, _tokens(bundle, attacker),
        ranged_bonus=ranged, melee_bonus=melee,
    )
    return _pick(found, weapon_id, off_hand, attacker, bundle)


def _pick(found: Sequence[AttackProfile], weapon_id: str, off_hand: bool,
          attacker: Actor, bundle: ContentBundle) -> AttackProfile:
    if weapon_id:
        for item in found:
            if item.weapon_id == weapon_id:
                return item
        if attacker.top().layer is not None:
            raise RuleError("变形期间只能用形态攻击，不能用武器（%s）" % weapon_id)
        names = "、".join(item.weapon_id for item in found) or "（无）"
        raise RuleError("这个角色没有拿出 %s（可用：%s）" % (weapon_id, names))
    if off_hand:
        for item in found:
            if item.off_hand:
                return item
        raise RuleError("副手没有武器")
    return found[0]


# --- 额外伤害通道 -------------------------------------------------------
def _extra_key(power) -> str:
    return "extra:%s" % power.id


def extra_damage_options(
    bundle: ContentBundle,
    attacker: Actor,
    locale: str = "zh",
) -> list[dict]:
    """命中时可选的额外伤害（来自常驻能力的 `extra_damage`）。

    `limit: turn` 的项在本回合用过以后 `available` 变 False —— 记账在
    `Actor.marks.spent`，回合结束时清。`when` 在这里判（「以荒野形态的攻击」
    这类条件），条件不满足的项**不列出**：列出来等于说它可以选。
    """
    root = attacker.root()
    facts = facts_for(attacker, None, loadout_for(attacker, bundle.armors))
    rows: list[dict] = []
    for power in available_powers(bundle, attacker):
        for effect in power.effects:
            if not isinstance(effect, ExtraDamage):
                continue
            if effect.when is not None and not evaluate(effect.when, facts):
                continue
            key = _extra_key(power)
            used = root.marks.spent_on(key)
            rows.append({
                "key": key,
                "power": power.id,
                "name": power.name.get(locale),
                "dice": effect.dice,
                "damage_type": effect.damage_type,
                "limit": effect.limit,
                "available": effect.limit != "turn" or used == 0,
                "used_this_turn": used,
            })
    return rows


def _chosen_extras(options: list[dict], extras: "str | Iterable[str]") -> list[dict]:
    """`extras` 的三种写法：空 = 不加；"all" = 全部可用项；列表 = 指定 key/power/id。

    **空就等于一项都不加**，包括 `limit: attack`（每次命中都算）那种。
    规则上那一类确实是自动的，但当前内容里还没有这种条目 —— 没有用例就先
    不猜，宁可少算（报告里会列出来）也不要凭空多算别人的血。
    等真有内容时，这里要改成分「自动段」与「可选段」两摞。
    """
    if not extras:
        return []
    if isinstance(extras, str):
        if extras != "all":
            wanted = {extras}
        else:
            wanted = None
    else:
        wanted = {str(item) for item in extras}
    picked: list[dict] = []
    for row in options:
        if wanted is not None and not (wanted & {row["key"], row["power"], row["name"]}):
            continue
        if not row["available"]:
            raise RuleError("《%s》本回合已经用过了（每回合一次）" % row["name"])
        picked.append(row)
    if wanted is not None:
        missing = wanted - {row["key"] for row in picked} - {row["power"] for row in picked} \
            - {row["name"] for row in picked}
        if missing:
            raise RuleError("没有这些可加的额外伤害：%s" % "、".join(sorted(missing)))
    return picked


# --- 结算 ---------------------------------------------------------------
def resolve_attack(
    bundle: ContentBundle,
    attacker: Actor,
    target: Target,
    weapon_id: str = "",
    off_hand: bool = False,
    rng: Rng | None = None,
    apply: bool = False,
    locale: str = "zh",
    extras: "str | Iterable[str]" = (),
) -> dict[str, Any]:
    """掷一次武器攻击。

    `apply=True` 才扣目标 HP、消耗优势标记、记「每回合一次」的账。
    `extras` 见模块注释（默认不加额外伤害，只列出可用项）。
    """
    profile = attack_profile(bundle, attacker, weapon_id, off_hand, locale)
    resolver = resolver_for(attacker, bundle.armors)
    top = attacker.top()
    mods = passive_modifiers(bundle, attacker, locale)
    roller = rng or SeededRng()

    query = "attack.ranged" if _is_ranged(profile, bundle) else "attack.melee"
    mode, sources = passive_advantage_modes(bundle, attacker, query)
    modes = [mode]
    source_list = list(sources)
    if profile.disadvantage:
        # 重型武器力量不足 13：这是规则给的劣势，不是内容给的
        modes.append("dis")
        source_list.append("重型武器（属性不足 13）")
    mode = merge(modes)

    crit = resolver.crit_range(top, modifiers_for(mods, "attack.crit_min"))
    crit_min = max(2, int(crit.total))
    roll = roll_d20(roller, mode)
    total = roll.total + profile.attack
    if roll.total >= crit_min:
        outcome = "critical"
    elif roll.total == 1 or total < int(target.ac):
        outcome = "miss"
    else:
        outcome = "hit"

    options = extra_damage_options(bundle, attacker, locale)
    picked = _chosen_extras(options, extras) if outcome != "miss" else []
    hit = outcome != "miss"

    segments: list[dict] = []
    total_damage = 0
    if hit:
        multiplier = 2 if outcome == "critical" else 1
        segments.append(_segment(
            label=profile.name.get(locale),
            dice=profile.damage, bonus=profile.damage_bonus,
            damage_type=profile.damage_type,
            multiplier=multiplier, target=target, rng=roller, locale=locale,
        ))
        for row in picked:
            segments.append(_segment(
                label=row["name"], dice=parse_dice(row["dice"]), bonus=0,
                damage_type=row["damage_type"], multiplier=multiplier,
                target=target, rng=roller, locale=locale,
            ))
        total_damage = sum(int(item["damage"]) for item in segments)

    marks_spent: list[Mark] = []
    if apply:
        if hit or outcome == "miss":
            # 「下一次攻击检定」已经发生过了 —— 不管中没中都算用掉
            marks_spent = consume_marks(attacker, query)
        for row in picked:
            if row["limit"] == "turn":
                attacker.root().marks.spend(row["key"])

    hp_before = hp_after = applied = None
    if apply and target.actor is not None and total_damage:
        pool = target.actor.root().hp
        hp_before = pool.current + pool.temp
        pool.damage(total_damage)
        hp_after = pool.current + pool.temp
        applied = hp_before - hp_after

    notes = _notes(outcome, profile, segments, picked, options, apply)
    return {
        "attacker": {"id": attacker.id,
                     "name": top.statblock.name.get(locale),
                     "morphed": top.layer is not None},
        "weapon": {"id": profile.weapon_id,
                   "name": profile.name.get(locale),
                   "ability": profile.ability,
                   "proficient": profile.proficient,
                   "off_hand": profile.off_hand,
                   "mastery": profile.mastery},
        "target": {"label": target.label or "目标", "ac": int(target.ac)},
        "attack": {
            "bonus": int(profile.attack),
            "detail": _attack_detail(profile),
            "mode": mode, "mode_sources": source_list,
            "die": roll.total,
            "kept": list(roll.parts[0].rolls),
            "dropped": list(roll.parts[0].dropped),
            "total": int(total),
            "crit_min": crit_min,
            "crit_text": ("20" if crit_min >= CRIT_ON_20
                          else "%d-%d" % (crit_min, CRIT_ON_20)),
        },
        "outcome": outcome,
        "hit": hit,
        "damage": {
            "total": int(total_damage),
            "breakdown": segments,
            "type": damage_name(profile.damage_type, locale),
            "defense": segments[0]["defense"] if segments else "",
        },
        "extras": {
            "chosen": [row["key"] for row in picked],
            "available": options,
        },
        "marks": {"spent": [item.to_dict() for item in marks_spent],
                  "preview": not apply},
        "hp": {"before": hp_before, "after": hp_after, "applied": applied},
        "notes": notes,
    }


def _is_ranged(profile: AttackProfile, bundle: ContentBundle) -> bool:
    weapon = bundle.weapons.get(profile.weapon_id)
    return is_ranged(weapon) if weapon is not None else False


def _attack_detail(profile: AttackProfile) -> str:
    """加值明细。攻击总值在 `attack.bonus`，这里说明它是怎么凑出来的。"""
    bits = ["%s 调整值" % profile.ability.upper()]
    if profile.proficient:
        bits.append("熟练")
    if profile.misc:
        bits.append("能力加值 %+d" % profile.misc)
    if profile.off_hand:
        bits.append("副手")
    return " + ".join(bits)


def _segment(label: str, dice: Dice, bonus: int, damage_type: str, multiplier: int,
             target: Target, rng: Rng, locale: str) -> dict:
    """一段伤害：重击加骰 → 掷 → 抗性/免疫。每段单独算，不加总后再减。"""
    rolled_dice = dice
    if multiplier > 1:
        from ..kernel.dice import Die

        rolled_dice = Dice(
            dice=tuple(Die(count=die.count * multiplier, sides=die.sides)
                       for die in dice.dice),
            flat=dice.flat,
        )
    rolled = rolled_dice.roll(rng)
    # 伤害不为负：力量 3 的猫徒手是「1 + (-4)」，规则上这是 0 点，不是 -3。
    # 负数会让「受到伤害」变成治疗，这是必须在这里挡住的一条。
    raw = max(0, rolled.total + int(bonus))
    kind = _defense(damage_type, target)
    damage = raw
    if kind == "immunity":
        damage = 0
    elif kind == "resistance":
        damage //= 2
    return {
        "label": label,
        "dice": str(rolled_dice),
        "bonus": int(bonus),
        "roll": rolled.describe(),
        "raw": int(raw),
        "damage": int(damage),
        "damage_type": damage_type,
        "damage_type_zh": damage_name(damage_type, locale) if damage_type else "",
        "defense": kind,
        "crit": multiplier > 1,
    }


def _defense(damage_type: str, target: Target) -> str:
    if not damage_type:
        return ""
    if damage_type in target.immunities:
        return "immunity"
    if damage_type in target.resistances:
        return "resistance"
    return ""


def _notes(outcome: str, profile: AttackProfile, segments: list[dict],
           picked: list[dict], options: list[dict], apply: bool) -> list[str]:
    notes: list[str] = []
    if outcome == "miss":
        notes.append("未命中，不掷伤害")
    if outcome == "critical":
        notes.append("重击：所有伤害骰翻倍，定值不翻")
    if profile.disadvantage:
        notes.append("重型武器属性不足 13，本次攻击有劣势")
    if profile.mastery:
        notes.append("武器专精「%s」的实际效果（推、削、拖）要按位置结算，"
                     "这里只记名字" % profile.mastery)
    if profile.weapon_id == "unarmed":
        notes.append("按徒手（1 + 属性调整值）算 —— 怪物与野兽形态的天然武器还没建模，"
                     "兽形的真实攻击骰要按形态数据手填")
    if outcome != "miss" and not picked:
        ready = [row["name"] for row in options if row["available"]]
        if ready:
            notes.append("这次没加额外伤害；可用：%s（要加请显式指定）"
                         % "、".join(ready))
    for item in segments:
        if item["defense"] == "resistance":
            notes.append("%s 抗性：%s 段伤害减半" % (item["damage_type_zh"], item["label"]))
        if item["defense"] == "immunity":
            notes.append("%s 免疫：%s 段伤害归零" % (item["damage_type_zh"], item["label"]))
    if not apply:
        notes.append("预览：目标 HP、优势标记、每回合一次的记账都没有动")
    return notes


# --- 怪物攻击 -----------------------------------------------------------
def resolve_monster_attack(
    attacker: Actor,
    attack: "MonsterAttack",
    target: Target,
    rng: Rng | None = None,
    apply: bool = False,
    locale: str = "zh",
    mode: str = "flat",
    mode_sources: Sequence[str] = (),
) -> dict[str, Any]:
    """掷一次怪物动作。

    与 `resolve_attack` 的差别只有三处，都是「怪物不是玩家」带来的：

    1. **命中加值直接用卡上的数**（`attack.attack_bonus`），不经过 Resolver ——
       见 `rules/monsters.py` 开头的实测：85/95 条推不出来。
    2. **优势/劣势由调用方算好传入**（`mode` / `mode_sources`）：特性的
       「群体战术」要问遭遇战的阵营与位置，那部分在 api 层折算
       （`rules.monsters.trait_attack_mode`），这里只管按模式掷骰。
    3. **重击只看 20**：`attack.crit_min` 是玩家能力的通道，怪物没有。

    豁免类动作（`kind="save"`）**不替你掷**：原文里「成功则半伤」「失败则被束缚」
    这些后果写在说明里，不是结构化数据。硬编一个「失败全伤」就是编规则。
    `multiattack` / `other` 同理 —— 只回报这是哪一类，不假装结算过。
    """
    from .monsters import MonsterAttack  # noqa: F401  仅为类型与取值

    roller = rng or SeededRng()
    name = attack.name.get(locale)
    base = {
        "attacker": {"id": attacker.id,
                     "name": attacker.top().statblock.name.get(locale),
                     # 变形中的角色也走这条结算，所以「怪物」这个标志要按要求算，
                     # 不能写死 True —— 报告是给人核对的，先得自己不撒谎。
                     "monster": attacker.top().kind.value == "monster",
                     "kind": attacker.top().kind.value},
        "action": {"key": "", "name": name, "kind": attack.kind,
                   "attack_bonus": attack.attack_bonus,
                   "reach": attack.reach, "range": attack.range,
                   "long_range": attack.long_range,
                   "save": attack.save, "save_dc": attack.save_dc},
        "target": {"label": target.label or "目标", "ac": int(target.ac)},
    }

    if attack.kind in ("multiattack", "other"):
        # 「多重攻击」本身不掷骰：真正的结算是它下面列的那几条。
        base.update({
            "rolled": False, "outcome": "not_rolled", "hit": False,
            "damage": {"total": 0, "breakdown": [], "type": "", "defense": ""},
            "hp": {"before": None, "after": None, "applied": None},
            "notes": ["这条动作没有可掷的数值（%s）" % attack.kind],
        })
        return base

    if attack.kind == "save":
        base.update({
            "rolled": False, "outcome": "save_required", "hit": False,
            "damage": {"total": 0, "breakdown": [], "type": "", "defense": ""},
            "hp": {"before": None, "after": None, "applied": None},
            "notes": [
                "要目标掷 %s 豁免（DC %d），后果写在说明里 —— 本程序不替你判"
                % (attack.save.upper(), int(attack.save_dc)),
            ],
        })
        return base

    bonus = int(attack.attack_bonus or 0)
    roll = roll_d20(roller, mode)
    total = roll.total + bonus
    if roll.total == CRIT_ON_20:
        outcome = "critical"
    elif roll.total == 1 or total < int(target.ac):
        outcome = "miss"
    else:
        outcome = "hit"
    hit = outcome != "miss"

    segments: list[dict] = []
    if hit:
        multiplier = 2 if outcome == "critical" else 1
        for part in attack.damage:
            segments.append(_segment(
                label=name, dice=parse_dice(part.dice), bonus=0,
                damage_type=part.type, multiplier=multiplier,
                target=target, rng=roller, locale=locale,
            ))
    total_damage = sum(int(item["damage"]) for item in segments)

    hp_before = hp_after = applied = None
    if apply and target.actor is not None and total_damage:
        pool = target.actor.root().hp
        hp_before = pool.current + pool.temp
        pool.damage(total_damage)
        hp_after = pool.current + pool.temp
        applied = hp_before - hp_after

    notes: list[str] = []
    if outcome == "miss":
        notes.append("未命中，不掷伤害")
    if outcome == "critical":
        notes.append("重击：伤害骰翻倍，定值不翻")
    if not attack.damage:
        notes.append("这条动作没有登记伤害（原文可能只写了控制效果）")
    if mode_sources and mode != "flat":
        word = "优势" if mode == "adv" else "劣势"
        notes.append("本次攻击带%s（来自：%s）" % (word, "、".join(mode_sources)))
    for item in segments:
        if item["defense"] == "resistance":
            notes.append("%s 抗性：伤害减半" % item["damage_type_zh"])
        if item["defense"] == "immunity":
            notes.append("%s 免疫：伤害归零" % item["damage_type_zh"])
    if not apply:
        notes.append("预览：目标 HP 没有动")

    base.update({
        "rolled": True,
        "attack": {
            "bonus": bonus,
            "die": roll.total,
            "total": int(total),
            "mode": mode,
            "mode_sources": list(mode_sources),
            "kept": list(roll.parts[0].rolls),
            "dropped": list(roll.parts[0].dropped),
            "crit_min": CRIT_ON_20,
        },
        "outcome": outcome,
        "hit": hit,
        "damage": {
            "total": int(total_damage),
            "breakdown": segments,
            "type": damage_name(attack.damage[0].type, locale) if attack.damage else "",
            "defense": segments[0]["defense"] if segments else "",
        },
        "hp": {"before": hp_before, "after": hp_after, "applied": applied},
        "notes": notes,
    })
    return base
