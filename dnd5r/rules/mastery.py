# -*- coding: utf-8 -*-
"""武器精通（2024 的八种精通属性）：名字、效果、以及**能算出来的那几个数**。

## 为什么单独一个模块

精通曾在两处各写半份：数据里是 `mastery: topple` 一个 slug，界面里是
`MASTERY_ZH` 一张中文名表，规则层只在攻击报告里印一句「这里只记名字」。
三方都不知道对方在说什么 —— 玩家看到「精通：击倒」却不知道 DC 是多少，
也不知道自己到底有没有这件武器的精通（建卡时选的那三件才作数）。

所以这里把三件事一次说清：

1. **目录**：八种精通的双语名 + 一句话效果（`MASTERY_DEFS`）
2. **资格**：`usable()` —— 武器有精通属性 **且** 你建卡时选过它
3. **数字**：`effect_plan()` —— 击倒的 DC、擦伤的伤害、劈砍第二击的算式

## 结算到什么程度（这是本模块最重要的一段）

八种里只有三种是**不需要第二个生物、不需要战斗地图**就能落地的，它们真结算：

  * **擦伤 graze**：未命中时补 `最大(0, 属性调整值)` 点伤害。
    它进伤害管线，所以抗性/免疫照常减 —— 这是唯一一条「没命中也有伤害」的规则，
    以前引擎完全没有这条路。
  * **击倒 topple**：DC 算得出来（8 + 熟练 + 属性调整值），目标的体质豁免
    加值也在 `Target` 里，于是这一掷可以真掷；`apply=True` 时失败就把
    **倒地**写进目标的状态集合（状态页看得见）。
  * **扰乱 vex / 削弱 sap**：它们就是「下一次攻击的优势/劣势」，而引擎本来
    就有一次性标记（`model/marks.py`）。所以挂成真标记，下一次攻击真的会变。

剩下四种**不假算**，只把参数算好交给玩家：

  * **劈砍 cleave**：要「第二个生物」。没有目标模型，但我们能给出第二击的
    攻击加值与伤害骰（武器骰、不加属性调整值）—— 玩家照着自己掷。
  * **快手 nick**：要「双持轻型武器」这个持握事实。`Profile` 里没有记录
    「这一轮是怎么持的」，所以只说明它省的是附赠动作。
  * **推撞 push / 迟缓 slow**：要位置与速度的具体数字。推 10 尺、减 10 尺
    这两个数是确定的，但「往哪推」「目标现在速度多少」不在引擎里。

`resolved=False` 的四项会在报告里写明缺什么 —— 与 `set_condition` 那句
「已记录，未计入数值」同一条规矩：宁可少算，也不许让玩家以为算过了。
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol

from ..kernel.text import Text
from .text import tr

__all__ = [
    "MasteryDef", "MASTERY_DEFS", "MASTERY_KEYS", "MASTERY_KINDS",
    "MANEUVER_DC_BASE", "mastery_def", "mastery_name", "mastery_summary",
    "usable", "maneuver_dc", "effect_plan", "ABILITY_NAMES", "save_name",
]

# 击倒/推撞这类「动作豁免」的 DC 基数。8 是规则给的，不是随便挑的。
MANEUVER_DC_BASE = 8

# 结算类别。前四种是真算的（resolved=True），后四种只给参数。
MASTERY_KINDS = (
    "miss_damage",       # 擦伤
    "save_prone",        # 击倒
    "attack_advantage",  # 扰乱
    "attack_disadvantage",  # 削弱
    "extra_attack",      # 劈砍、快手
    "forced_move",       # 推撞
    "speed_penalty",     # 迟缓
)

RESOLVED_KINDS = frozenset({
    "miss_damage", "save_prone", "attack_advantage", "attack_disadvantage",
})


class WeaponLike(Protocol):
    """只需要这三样。独立写一份 Protocol 是为了让本模块**不被** weapons 反向依赖
    —— `rules/weapons.py` 不该 import 精通表（它只负责算式）。"""

    id: str
    name: Text
    mastery: str


@dataclass(frozen=True, slots=True)
class MasteryDef:
    key: str
    name: Text
    summary: Text
    kind: str
    # 结算时缺的东西（缺了就只能给参数）。写给人看的一句话。
    needs: Text | None = None

    @property
    def resolved(self) -> bool:
        return self.kind in RESOLVED_KINDS


_T = Text.of

MASTERY_DEFS: Mapping[str, MasteryDef] = MappingProxyType({
    "cleave": MasteryDef(
        key="cleave", name=_T("劈砍", "Cleave"), kind="extra_attack",
        summary=_T(
            "近战命中后，可对第一个目标 5 尺内、也在你触及内的第二个生物再掷一次"
            "攻击；命中则造成武器伤害，但不加属性调整值。每回合一次。",
            "After a melee hit, roll one attack against a second creature within "
            "5 feet of the first that is also within your reach. On a hit it takes "
            "the weapon's damage without your ability modifier. Once per turn."),
        needs=_T("第二个生物的位置", "the position of a second creature"),
    ),
    "graze": MasteryDef(
        key="graze", name=_T("擦伤", "Graze"), kind="miss_damage",
        summary=_T(
            "攻击未命中时，造成等于攻击所用属性调整值的伤害（与武器同类型，最低 0）。",
            "When your attack roll misses, deal damage equal to the ability "
            "modifier used for the roll. Same type as the weapon, never below 0."),
    ),
    "nick": MasteryDef(
        key="nick", name=_T("快手", "Nick"), kind="extra_attack",
        summary=_T(
            "轻型武器的那次额外攻击并入攻击动作，不占附赠动作。每回合一次。",
            "The extra attack of the Light property becomes part of the Attack "
            "action instead of a Bonus Action. Once per turn."),
        needs=_T("这一轮的持握方式", "how the weapons are held this turn"),
    ),
    "push": MasteryDef(
        key="push", name=_T("推撞", "Push"), kind="forced_move",
        summary=_T(
            "命中后把目标推离你至多 10 尺（体型须为大型或更小）。",
            "On a hit, push the target up to 10 feet away from you if it is "
            "Large or smaller."),
        needs=_T("战场位置", "battlefield positions"),
    ),
    "sap": MasteryDef(
        key="sap", name=_T("削弱", "Sap"), kind="attack_disadvantage",
        summary=_T(
            "命中后，目标的下一次攻击检定有劣势，直到你的下回合开始。",
            "On a hit, the target has Disadvantage on its next attack roll "
            "before the start of your next turn."),
    ),
    "slow": MasteryDef(
        key="slow", name=_T("迟缓", "Slow"), kind="speed_penalty",
        summary=_T(
            "命中后，目标速度减 10 尺，直到你的下回合开始（不叠加）。",
            "On a hit, reduce the target's Speed by 10 feet until the start of "
            "your next turn. The reduction doesn't stack."),
        needs=_T("目标当前速度", "the target's current Speed"),
    ),
    "topple": MasteryDef(
        key="topple", name=_T("击倒", "Topple"), kind="save_prone",
        summary=_T(
            "命中后可强制目标做体质豁免"
            "（DC = 8 + 熟练加值 + 攻击所用属性调整值），失败则倒地。",
            "On a hit, force a Constitution saving throw (DC 8 + your "
            "Proficiency Bonus + the ability modifier used for the attack). "
            "On a failure the target has the Prone condition."),
    ),
    "vex": MasteryDef(
        key="vex", name=_T("扰乱", "Vex"), kind="attack_advantage",
        summary=_T(
            "命中后，你对该目标的下一次攻击检定有优势，直到你的下回合结束。",
            "On a hit, you have Advantage on your next attack roll against that "
            "creature before the end of your next turn."),
    ),
})

MASTERY_KEYS: tuple[str, ...] = tuple(MASTERY_DEFS)

# 数据里可能写错的 slug：加载期不校验（内容包可能自带新精通），
# 但取不到定义时**必须**让调用方知道，不能静默当成「没有精通」。
def mastery_def(key: str) -> MasteryDef | None:
    return MASTERY_DEFS.get(str(key or "").lower())


# 六项属性的双语名。只给「体质豁免 DC」这类报告句用 —— 界面有自己的
# `ABILITY_ZH`，但规则层算出来的句子必须在规则层翻，不能指望界面再拆。
ABILITY_NAMES: Mapping[str, Text] = MappingProxyType({
    "str": _T("力量", "Strength"), "dex": _T("敏捷", "Dexterity"),
    "con": _T("体质", "Constitution"), "int": _T("智力", "Intelligence"),
    "wis": _T("感知", "Wisdom"), "cha": _T("魅力", "Charisma"),
})


def save_name(ability: str, locale: str = "zh") -> str:
    item = ABILITY_NAMES.get(str(ability or "").lower())
    return item.get(locale) if item is not None else str(ability or "").upper()


def mastery_name(key: str, locale: str = "zh") -> str:
    item = mastery_def(key)
    return item.name.get(locale) if item is not None else str(key or "")


def mastery_summary(key: str, locale: str = "zh") -> str:
    item = mastery_def(key)
    return item.summary.get(locale) if item is not None else ""


def usable(weapon: WeaponLike | None, masteries: Iterable[str]) -> bool:
    """这件武器上的精通属性，你能不能真的用出来。

    两个条件缺一不可：武器写了精通属性（38 件都有），**且**建卡时选的精通
    里包含它。以前只看前者 —— 于是任何拿巨剑的人都被报告成「武器专精：击倒」，
    包括根本没选过精通、甚至职业没有武器精通特性的法师。
    """
    if weapon is None or not getattr(weapon, "mastery", ""):
        return False
    return str(weapon.id) in set(masteries or ())


def maneuver_dc(prof_bonus: int, ability_mod: int) -> int:
    """击倒这类强制豁免的 DC。8 + 熟练加值 + 攻击所用属性调整值。"""
    return int(MANEUVER_DC_BASE) + int(prof_bonus) + int(ability_mod)


def effect_plan(
    weapon: WeaponLike | None,
    masteries: Iterable[str],
    *,
    prof_bonus: int = 0,
    ability_mod: int = 0,
    attack_bonus: int = 0,
    damage_dice: str = "",
    damage_type: str = "",
    locale: str = "zh",
) -> dict:
    """这次攻击的精通「计划书」：能不能用、要掷什么、数字是多少。

    没有武器 / 武器没有精通属性 → 返回空 dict（`{}`，调用方 `if not plan` 跳过）。
    有属性但没选过 → 返回带 `usable: False` 与 `reason` 的 dict —— **要报告出来**，
    静默丢弃会让「我明明选了击倒却没用」变成一个查不出来的 bug。
    """
    if weapon is None:
        return {}
    key = str(getattr(weapon, "mastery", "") or "").lower()
    if not key:
        return {}
    item = mastery_def(key)
    name = item.name.get(locale) if item is not None else key
    plan: dict = {
        "key": key,
        "name": name,
        "kind": item.kind if item is not None else "",
        "resolved": bool(item.resolved) if item is not None else False,
        "summary": item.summary.get(locale) if item is not None else "",
        "usable": usable(weapon, masteries),
        "reason": "",
    }
    if item is None:
        # 内容包写了本程序不认识的精通属性：如实说，不要假装它有效果
        plan["reason"] = tr("这本程序不认识这个精通属性：%s（只支持 %s）",
                            locale) % (key, "、".join(MASTERY_KEYS))
        return plan
    if not plan["usable"]:
        plan["reason"] = tr("你没有这件武器的精通 —— 精通效果只在建卡（或升级）时"
                            "选过的武器上生效", locale)
        return plan
    if item.needs is not None:
        plan["needs"] = item.needs.get(locale)

    kind = item.kind
    if kind == "miss_damage":
        # 擦伤：不掷骰，只加定值。最低 0 —— 力量 3 的角色不该被「补」成负数。
        plan["damage"] = max(0, int(ability_mod))
        plan["damage_type"] = damage_type
    elif kind == "save_prone":
        plan["dc"] = maneuver_dc(prof_bonus, ability_mod)
        plan["save"] = "con"
    elif kind == "attack_advantage":
        plan["expires"] = "next"
    elif kind == "attack_disadvantage":
        plan["expires"] = "next"
    elif kind == "extra_attack":
        plan["attack"] = int(attack_bonus)
        plan["damage_dice"] = str(damage_dice)
        plan["damage_type"] = damage_type
        plan["without_ability_modifier"] = True
    elif kind == "forced_move":
        plan["distance"] = 10
    elif kind == "speed_penalty":
        plan["distance"] = 10
    return plan
