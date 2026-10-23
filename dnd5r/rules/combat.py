# -*- coding: utf-8 -*-
"""施法结算：一次施法 → 每个目标一行结果。

P5 只做到「算得出 DC 与攻击加值」为止，从没掷过骰子 —— 因为**没有目标**：
AC、豁免加值、抗性都长在「另一个 Actor」身上，而引擎只有一个角色。

这里补上目标这一侧，并把三件事分开：

  1. **命中判定** d20 + 施法攻击加值 vs 目标 AC
  2. **豁免判定** 目标 d20 + 豁免加值 vs 施法者 DC
  3. **伤害** 骰式 → 抗性/免疫 → 落到 HP

三条通道各自的骰子都来自可注入的 `Rng`，所以结算可复现（测试拿同一个种子）。

## 为什么 `save_effect` 空着就不算伤害

有些法术的 `save` 与 `damage` 是两件事：灼热金属的伤害是接触就吃、豁免只管
能不能拿住；纠缠打击的伤害来自之后每回合。这些条目里**没有**「豁免成功吃多少」
这个信息，硬填 `none` 会让「豁免成功 = 0 伤害」这句假话成立 —— 比「不知道」
更糟，因为它看上去像个答案。所以照样掷豁免（DM 想知道结果），
但伤害不落库、结论写「需人工判定」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ..content import ContentBundle, SpellDef
from ..kernel.dice import Dice, parse as parse_dice, roll_d20
from ..kernel.errors import RuleError
from ..kernel.rng import Rng, SeededRng
from ..model.actor import Actor
from ..model.statblock import ABILITY_KEYS
from .contributions import passive_advantage_modes, passive_defenses, passive_proficiencies
from .build import feat_spell_grants
from .derived import resolver_for
from .resolver import CRIT_ON_20
from .spellcasting import (
    casting_ability, free_cast_pool, slot_pools, spend_slot,
)

# 结算的四种形状。`manual` 不是「没结算」，是「原文里没有可自动判的结论」——
# 界面上必须与「这道法术本来就不掷伤害」分开写。
RESOLUTION_KINDS = ("attack", "save", "auto", "none")

__all__ = [
    "Target", "Casting", "RESOLUTION_KINDS",
    "target_from_actor", "casting_for", "resolution_kind",
    "damage_expression", "resolve_spell",
]


@dataclass(frozen=True)
class Target:
    """结算目标只需要四个数：AC、六项豁免、抗性、免疫。

    不强制要有 `Actor` —— DM 手里常常只有一句「哥布林，AC 15，敏捷 +2」。
    给了 `actor` 才有 HP 可扣、也才读得到它自己的优势（被束缚时敏捷豁免劣势）。
    """

    label: str = ""
    ac: int = 10
    saves: Mapping[str, int] = field(default_factory=dict)
    resistances: frozenset[str] = frozenset()
    immunities: frozenset[str] = frozenset()
    actor: Actor | None = None

    def __post_init__(self) -> None:
        if int(self.ac) < 0:
            raise RuleError("目标 AC 不能为负：%r" % (self.ac,))
        bad = [key for key in self.saves if key not in ABILITY_KEYS]
        if bad:
            raise RuleError("目标的豁免加值只能按 %s 写：%r"
                            % ("/".join(ABILITY_KEYS), bad))

    def save_bonus(self, ability: str) -> int:
        """没登记这项豁免就按 +0 —— 大多数杂兵也确实就是 +0。"""
        return int(self.saves.get(ability, 0))


@dataclass(frozen=True)
class Casting:
    """施法者这一侧的三个数。法术 DC 与攻击加值都取决于**用哪个职业施放**。

    `class_id` 与 `source` 至少有一个非空：前者是职业施法，后者是专长给的法术
    （妖精触碰的迷踪步、魔法入门的 1 环法术）。专长施法时属性由专长定，
    与角色的职业无关 —— 战士拿了妖精触碰，迷踪步照样按魅力算 DC。
    """

    class_id: str
    ability: str
    dc: int
    attack: int
    dc_detail: str = ""
    attack_detail: str = ""
    source: str = ""


# --- 目标 ---------------------------------------------------------------
def target_from_actor(
    bundle: ContentBundle,
    actor: Actor,
    locale: str = "zh",
) -> Target:
    """把一个 Actor 读成结算目标：AC、六项豁免、抗性/免疫、HP。

    豁免加值与角色卡**用同一个 Resolver**：卡上写 +5、结算按 +3 算，
    是这类代码最难发现的错，而两边各写一遍必然有一天会分叉。
    """
    resolver = resolver_for(actor, bundle.armors)
    top = actor.top()
    proficient = _save_proficiencies(bundle, actor)
    # 卡上印着豁免加值就直接用（怪物），否则按「属性 + 熟练」推（玩家）。
    # 不分开这两条会出这种事：巨蜘蛛的敏捷豁免写 +5，按 +1 敏捷 +2 熟练推成 +3，
    # 玩家扔火球时的 DC 差两点，而界面上两个数字都「看着对」。
    printed = dict(top.statblock.saves)
    saves = {
        ability: (int(printed[ability]) if ability in printed
                  else resolver.saving_throw(top, ability,
                                             proficient=ability in proficient).total)
        for ability in ABILITY_KEYS
    }
    resist, immune = passive_defenses(bundle, actor)
    profile = actor.profile
    if profile is not None:
        resist |= set(profile.resistances)
    return Target(
        label=top.statblock.name.get(locale) or actor.id,
        ac=resolver.armor_class(top).total,
        saves=saves,
        resistances=frozenset(resist),
        immunities=frozenset(immune),
        actor=actor,
    )


def _save_proficiencies(bundle: ContentBundle, actor: Actor) -> set[str]:
    """豁免熟练：角色选择里的 `save.dex` 与被动能力给的 `save.dex` 都算。"""
    profile = actor.profile
    tokens = set(profile.proficiencies if profile else ())
    tokens |= passive_proficiencies(bundle, actor)
    return {token.split(".", 1)[1] for token in tokens if token.startswith("save.")}


# --- 施法者 -------------------------------------------------------------
def casting_for(
    bundle: ContentBundle,
    caster: Actor,
    spell: SpellDef,
    class_id: str = "",
    locale: str = "zh",
    source: str = "",
) -> Casting:
    """这道法术该用哪个职业的 DC / 攻击加值。

    兼职角色可能有两个职业都能放同一道法术（两个职业表都收录了它），
    这时 DC 与攻击加值**不一样** —— 猜一个就是给玩家一个错的数。
    所以宁可报错让他指定，也不挑「最高的那个」。

    `source` 是「由哪个专长授予的」：专长给的法术按**专长**的施法属性算
    （原文写「施法属性为你以此专长提升的属性」），跟角色有没有施法职业无关。
    一个只会挥剑的战士拿了妖精触碰，迷踪步的 DC 也是魅力 DC。
    """
    profile = caster.profile
    if profile is None:
        raise RuleError("caster 没有职业档案，算不出法术 DC：%r" % (caster.id,))
    name = spell.name.get(locale) or spell.id

    if source:
        grants = [item for item in feat_spell_grants(bundle, profile, locale)
                  if item.feat == source]
        if not any(item.spell == spell.id for item in grants):
            raise RuleError("《%s》不是 %s 给的法术" % (name, source))
        return _feat_casting(bundle, caster, name, grants)

    holders = [entry.class_id for entry in profile.classes
               if spell.id in bundle.spell_list(entry.class_id)]
    if class_id:
        if class_id not in holders:
            raise RuleError("《%s》不在 %s 的法术表里" % (name, class_id))
        picked = class_id
    elif len(holders) > 1:
        raise RuleError("《%s》同时在 %s 的法术表里，请指定用哪个职业施放"
                        % (name, "／".join(holders)))
    elif holders:
        picked = holders[0]
    else:
        # 没有职业能放它 —— 那它只可能是专长给的（战士的妖精触碰迷踪步）。
        # 这条兜底不是「猜」：属性由内容里的 casting_ability 决定，没写就报错。
        grants = [item for item in feat_spell_grants(bundle, profile, locale)
                  if item.spell == spell.id]
        if not grants:
            raise RuleError("这个角色没有能施放《%s》的职业（不在任何已选职业的法术表里）"
                            "也没有专长授予它" % name)
        return _feat_casting(bundle, caster, name, grants)

    ability = casting_ability(bundle.class_def(picked))
    resolver = resolver_for(caster, bundle.armors)
    dc = resolver.spell_dc(caster.top(), ability)
    attack = resolver.spell_attack(caster.top(), ability)
    return Casting(
        class_id=picked,
        ability=ability,
        dc=dc.total,
        attack=attack.total,
        dc_detail=dc.describe(),
        attack_detail=attack.describe(),
    )


def _feat_casting(bundle: ContentBundle, caster: Actor, name: str,
                  grants) -> Casting:
    """专长给的法术：属性由 `casting_ability` 定，没写就不许猜。"""
    abilities = sorted({item.ability for item in grants if item.ability})
    if not abilities:
        feat = bundle.feats.get(grants[0].feat)
        token = feat.casting_ability if feat is not None else ""
        if token in ("boost", "choose"):
            # 「还没选」不是数据错误，是玩家还没做完选择 —— 界面显示待办，
            # 这里也不该说成「内容缺字段」
            raise RuleError("《%s》是专长 %s 给的法术，但这个专长的施法属性还没选"
                            "（先选完专长的选择项）" % (name, grants[0].feat))
        raise RuleError("《%s》是专长 %s 给的法术，但这个专长没有声明施法属性"
                        "（内容里补 casting_ability），算不出 DC"
                        % (name, grants[0].feat))
    if len(abilities) > 1:
        raise RuleError("《%s》同时被 %s 授予，且施法属性不同（%s），请指定来源"
                        % (name, "／".join(sorted({item.feat for item in grants})),
                           "／".join(abilities)))
    ability = abilities[0]
    resolver = resolver_for(caster, bundle.armors)
    dc = resolver.spell_dc(caster.top(), ability)
    attack = resolver.spell_attack(caster.top(), ability)
    return Casting(
        class_id="",
        ability=ability,
        dc=dc.total,
        attack=attack.total,
        dc_detail=dc.describe(),
        attack_detail=attack.describe(),
        source=grants[0].feat,
    )


# --- 法术这一侧 ---------------------------------------------------------
def resolution_kind(spell: SpellDef) -> str:
    """这道法术怎么判：攻击 / 豁免 / 必中 / 不结算。

    两条判定轴里攻击优先：同时有 `attack` 与 `save` 的法术（命中后再炸一次），
    伤害表对应的是**攻击命中**那一段。

    「必中」必须内容显式声明（`auto_damage`），**不能**从「有伤害骰、
    没有 save/attack」推出来：斩击、诅咒、印记这类增益的伤害表里也有骰子，
    但它们要等到命中才结算。推出来的必中会在施法瞬间扣一次还没发生的伤害。
    """
    if spell.attack:
        return "attack"
    if spell.save:
        return "save"
    if spell.auto_damage:
        return "auto"
    return "none"


def damage_expression(caster: Actor, spell: SpellDef, slot_level: int) -> str:
    """这一发实际掷的骰式。升环查环位表，戏法成长查**角色等级**表。

    两条轴不能混（见 `SpellDef` 的注释）。`beams` 与 `range` 这类成长
    不改伤害骰，这里原样返回基础值 —— 光束数在 `_shots` 里单独处理。
    """
    expr = spell.damage_at(slot_level)
    if not spell.is_cantrip or not spell.scaling:
        return expr
    total = int(caster.profile.total) if caster.profile else 1
    scaled = spell.scaling_at(total)
    if spell.scaling_kind == "damage":
        return scaled or expr
    if spell.scaling_kind == "extra_damage":
        return _add_dice(expr, scaled)
    return expr


def _add_dice(first: str, second: str) -> str:
    """两段骰式相加（`1d8` + `1d8` → `2d8`）。任一段为空就返回另一段。"""
    if not first:
        return second
    if not second:
        return first
    left, right = parse_dice(first), parse_dice(second)
    return str(Dice(dice=left.dice + right.dice, flat=left.flat + right.flat))


def _shots(caster: Actor, spell: SpellDef) -> int:
    """一次施法掷几次攻击。魔能爆的成长是**光束数**，不是更大的骰子。"""
    if spell.scaling_kind != "beams" or not spell.scaling:
        return 1
    total = int(caster.profile.total) if caster.profile else 1
    try:
        return max(1, int(spell.scaling_at(total) or 1))
    except (TypeError, ValueError):
        return 1


def _slot_for(spell: SpellDef, slot_level: int | None) -> int:
    if spell.is_cantrip:
        return 0
    slot = int(spell.level) if slot_level is None else int(slot_level)
    if slot < int(spell.level):
        raise RuleError("《%s》至少要用 %d 环位施放，收到 %d"
                        % (spell.name.get("zh") or spell.id, int(spell.level), slot))
    if slot > 9:
        raise RuleError("法术环位最高 9：%r" % (slot,))
    return slot


# --- 结算 ---------------------------------------------------------------
def resolve_spell(
    bundle: ContentBundle,
    caster: Actor,
    spell_id: str,
    slot_level: int | None = None,
    targets: Iterable[Target] = (),
    rng: Rng | None = None,
    locale: str = "zh",
    class_id: str = "",
    apply: bool = False,
    free: bool = False,
) -> dict[str, Any]:
    """掷一次施法结算。

    `apply=False`（缺省）**只算不落库** —— 界面预览「这一发打出去会怎样」；
    `apply=True` 才把伤害扣到目标 HP 上、把免费施放次数记上。默认不改状态，
    是因为误点一下就改了别人的角色卡，比多点一次麻烦得多。

    `free=True` 表示**不消耗法术位**：用专长给的那一次（妖精触碰、魔法入门）。
    它按法术自身环级结算（没有位就没法升环），属性用专长的施法属性。
    """
    if free and slot_level is not None:
        raise RuleError("免费施放按法术自身环级结算，不能同时指定环位")
    if free and class_id:
        raise RuleError("免费施放用的是专长给的次数，不能同时指定用某个职业施放")
    spell = bundle.spell(spell_id)
    slot = _slot_for(spell, slot_level)
    pool = None
    if free:
        pool = free_cast_pool(caster, spell.id)
        if pool is None:
            raise RuleError("《%s》没有可用的免费施放次数（长休恢复）"
                            % (spell.name.get(locale) or spell.id))
        casting = casting_for(bundle, caster, spell, "", locale, source=pool.source)
    else:
        casting = casting_for(bundle, caster, spell, class_id, locale)
    kind = resolution_kind(spell)
    dice_text = damage_expression(caster, spell, slot)
    dice = parse_dice(dice_text) if dice_text else None
    shots = _shots(caster, spell)
    roller = rng or SeededRng()
    picked = list(targets)
    # 法术位在**这里**记账：一次施放不管打没打中都要花掉那一环。
    # 与免费次数同一条规矩 —— `apply=False` 只报「会扣哪一环」，不动状态。
    slot_block = _slot_block(caster, spell, slot, class_id, casting, apply, free)

    rows: list[dict[str, Any]] = []
    for target in picked:
        for shot in range(shots):
            rows.append(_one_row(bundle, caster, spell, target, casting, dice, kind,
                                 shot, shots, roller, apply, locale))

    notes = _notes(spell, kind, dice is not None, shots)
    free_block = _free_block(spell, pool, apply)
    if free_block is not None and not free_block["spent"]:
        notes.append("预览：这次免费施放还没记账（确认后才会扣除次数）")
    return {
        "spell": {"id": spell.id,
                  "name": spell.name.get(locale),
                  "level": int(spell.level),
                  "school": spell.school},
        "slot": slot,
        "casting": {"class": casting.class_id, "ability": casting.ability,
                    "dc": casting.dc, "attack": casting.attack,
                    "dc_detail": casting.dc_detail,
                    "attack_detail": casting.attack_detail,
                    "source": casting.source},
        "kind": kind,
        "dice": dice_text,
        "damage_type": spell.damage_type,
        "save": spell.save,
        "save_effect": spell.save_effect,
        "attack_kind": spell.attack,
        "concentration": bool(spell.concentration),
        "shots": shots,
        # 不消耗法术位的那一次：池 id、这次有没有真的扣、还剩几次
        "free": free_block,
        # 法术位的记账：扣了哪一环、还剩几个。戏法与免费施放为 None
        "slot_spend": slot_block,
        "rows": rows,
        "total_damage": sum(int(row["damage"] or 0) for row in rows),
        "notes": notes,
    }


def _slot_block(
    caster: Actor,
    spell: SpellDef,
    slot: int,
    class_id: str,
    casting,
    apply: bool,
    free: bool,
) -> dict[str, Any] | None:
    """法术位的记账。`apply=False` 时**不扣** —— 与伤害、免费次数同一条规矩。

    戏法没有位、免费施放用的也不是位，两种都返回 None（界面据此不显示这一行）。
    主动施法却「找不到这个环级」是错，要当场报：让它可以免费放出去，
    是比报错更糟的沉默。
    """
    if free or spell.is_cantrip:
        return None
    owner = casting.class_id or class_id
    if apply:
        pool = spend_slot(caster, int(slot), owner)
        if pool is None:
            return None                 # 没有位账本的角色（怪物、随意施法）
        return {"pool": pool.id, "level": int(slot), "spent": 1,
                "left": pool.available, "capacity": pool.capacity}
    # 预览：只说会扣哪一环、扣完还剩几个，不动状态
    for level, pool in slot_pools(caster, owner):
        if level == int(slot):
            return {"pool": pool.id, "level": level, "spent": 0,
                    "left": pool.available, "capacity": pool.capacity,
                    "preview": True}
    return None


def _free_block(spell: SpellDef, pool, apply: bool) -> dict[str, Any] | None:
    """免费施放的记账。`apply=False` 时**不扣** —— 与伤害同一条规矩。"""
    if pool is None:
        return None
    spent = 0
    if apply:
        pool.spend(1)
        spent = 1
    return {
        "pool": pool.id,
        "spell": spell.id,
        "capacity": int(pool.capacity),
        "spent": spent,
        "left": int(pool.available),
        "refresh": pool.refresh.value,
    }


def _one_row(bundle, caster, spell, target, casting, dice, kind, shot, shots,
             rng, apply, locale) -> dict[str, Any]:
    row: dict[str, Any] = {
        "target": target.label or "目标",
        "shot": shot + 1,
        "kind": kind,
        "against": "",
        "target_number": 0,
        "die": 0, "kept": [], "dropped": [],
        "bonus": 0, "mode": "flat", "mode_sources": [],
        "outcome": "",
        "damage_dice": str(dice) if dice else "",
        "damage_roll": "",
        "raw": 0,
        "damage": 0,
        "defense": "",
        "applied": None,
        "hp_before": None,
        "hp_after": None,
        "note": "",
    }
    if kind == "none":
        row["outcome"] = "none"
        row["note"] = "这道法术不掷伤害，也没有豁免"
        return row

    if kind == "attack":
        mode, sources = passive_advantage_modes(bundle, caster, "attack.spell")
        roll = roll_d20(rng, mode)
        total = roll.total + casting.attack
        row.update({"against": "AC", "target_number": int(target.ac),
                    "die": roll.total, "kept": list(roll.parts[0].rolls),
                    "dropped": list(roll.parts[0].dropped),
                    "bonus": casting.attack, "mode": mode,
                    "mode_sources": list(sources)})
        # 2024：d20 出 20 即重击，出 1 必然失手。重击门槛 20 是 spell attack
        # 自己的规则 —— 职业给的 `attack.crit_min` 只管武器与徒手，别串过来。
        if roll.total >= CRIT_ON_20:
            row["outcome"] = "critical"
        elif roll.total == 1 or total < int(target.ac):
            row["outcome"] = "miss"
        else:
            row["outcome"] = "hit"
        if row["outcome"] == "miss":
            row["note"] = "未命中"
            return row
        multiplier = 2 if row["outcome"] == "critical" else 1
        _land_damage(row, dice, spell, target, multiplier, rng=rng)
        _maybe_apply(row, target, apply)
        return row

    if kind == "save":
        ability = spell.save
        mode, sources = (passive_advantage_modes(bundle, target.actor, "save.%s" % ability)
                         if target.actor is not None else ("flat", ()))
        bonus = target.save_bonus(ability)
        roll = roll_d20(rng, mode)
        total = roll.total + bonus
        row.update({"against": "%s 豁免" % ability.upper(),
                    "target_number": int(casting.dc),
                    "die": roll.total, "kept": list(roll.parts[0].rolls),
                    "dropped": list(roll.parts[0].dropped),
                    "bonus": bonus, "mode": mode, "mode_sources": list(sources)})
        row["outcome"] = "failed" if total < casting.dc else "succeeded"
        if dice is None:
            row["note"] = "这道法术不掷伤害"
            return row
        if row["outcome"] == "failed":
            _land_damage(row, dice, spell, target, 1, rng=rng)
            row["note"] = "豁免失败，全额伤害"
            _maybe_apply(row, target, apply)
            return row
        if spell.save_effect == "half":
            _land_damage(row, dice, spell, target, 1, halve=True, rng=rng)
            row["note"] = "豁免成功，伤害减半"
            _maybe_apply(row, target, apply)
            return row
        if spell.save_effect == "none":
            row["note"] = "豁免成功，不受伤害"
            return row
        # 未判定：掷出骰子给人看，但不落库（见模块注释）
        rolled = dice.roll(rng)
        row["raw"] = rolled.total
        row["damage_roll"] = rolled.describe()
        row["damage"] = 0
        row["note"] = "豁免成功后的伤害未判定（原文里伤害与豁免是两件事），需人工结算"
        return row

    # auto：必中且无豁免
    row["outcome"] = "auto"
    _land_damage(row, dice, spell, target, 1, rng=rng)
    _maybe_apply(row, target, apply)
    return row


def _land_damage(row, dice, spell, target, multiplier: int,
                 halve: bool = False, rng: Rng | None = None) -> None:
    """掷伤害 → 重击加骰 → 半伤 → 抗性/免疫。写清每一步，别只给最后那个数。"""
    if dice is None:
        return
    rolled_dice = dice
    if multiplier > 1:
        # 重击**加骰不加定值**：2d6+3 重击是 4d6+3，不是 (2d6+3)×2
        rolled_dice = Dice(dice=tuple(
            die for die in dice.dice for _ in range(multiplier)), flat=dice.flat)
    rolled = rolled_dice.roll(rng or SeededRng())
    raw = rolled.total
    if halve:
        raw //= 2
    kind = _defense_of(spell.damage_type, target)
    damage = raw
    if kind == "immunity":
        damage = 0
    elif kind == "resistance":
        damage //= 2
    row["damage_roll"] = rolled.describe()
    row["damage_dice"] = str(rolled_dice)
    row["raw"] = rolled.total if not halve else rolled.total // 2
    row["damage"] = damage
    row["defense"] = kind


def _defense_of(damage_type: str, target: Target) -> str:
    if not damage_type:
        return ""
    if damage_type in target.immunities:
        return "immunity"
    if damage_type in target.resistances:
        return "resistance"
    return ""


def _maybe_apply(row, target: Target, apply: bool) -> None:
    if not apply or target.actor is None or not row["damage"]:
        return
    pool = target.actor.root().hp
    before = pool.current + pool.temp
    pool.damage(int(row["damage"]))
    after = pool.current + pool.temp
    row["hp_before"] = before
    row["hp_after"] = after
    row["applied"] = before - after


def _notes(spell: SpellDef, kind: str, has_dice: bool, shots: int) -> list[str]:
    notes = []
    if kind == "none":
        notes.append("内容里没有能自动结算的伤害或豁免（增益、召唤、条件性伤害都属于这类），"
                     "按原文手动处理")
    if kind == "save" and has_dice and not spell.save_effect:
        notes.append("豁免成功后的伤害未判定：原文里伤害与豁免可能不是一件事，需人工结算")
    if kind == "attack" and spell.save:
        notes.append("这道法术另有一次 %s 豁免的效果，不在这里结算，见原文" % spell.save.upper())
    if kind in ("attack", "save", "auto") and not has_dice:
        notes.append("这道法术没有可直接掷的伤害骰（伤害取决于选项或目标），只结算判定")
    if shots > 1:
        notes.append("共 %d 道光束，每道单独掷攻击" % shots)
    return notes
