# -*- coding: utf-8 -*-
"""遭遇战操作：建场 / 视图 / 回合推进 / 摆位移动传送 / 阵营。

战斗不进存档（与 rules.encounter 同一条理由）。拆自 P11 之前的巨型 __init__。"""
from __future__ import annotations

from typing import Any, Sequence

from ..kernel.errors import RuleError
from ..content import ContentBundle
from ..kernel.rng import Rng, SeededRng
from ..model.actor import Actor
from ..rules.encounter import Encounter

def join_encounter(
    encounter: Encounter,
    content: ContentBundle,
    actor: Actor,
    rng: Rng | None = None,
    seed: int | None = None,
    x: int = 0,
    y: int = 0,
) -> dict:
    """中途加入一个人（增援、召唤物、DM 临时放进来的怪）。

    `content` 只为与其它入口保持一致（现在不需要查内容），保留这个参数
    是为了以后要按内容算「加入时的先攻加值」时不用改调用方。
    """
    combatant = encounter.join(actor, rng or SeededRng(seed), x, y)
    return {
        "id": combatant.id,
        "label": combatant.label,
        "initiative": int(combatant.initiative),
        "current": (encounter.current().id if encounter.current() else ""),
        "order": encounter.order(),
    }


def new_encounter(
    actors: Sequence[Actor],
    rng: Rng | None = None,
    begin: bool = True,
) -> Encounter:
    """建一场遭遇战：加入参与者 → 掷先攻 → 开始第一轮。"""
    encounter = Encounter.of(actors)
    if not encounter.combatants:
        raise RuleError("遭遇战里没有人")
    encounter.roll_initiative(rng or SeededRng())
    if begin:
        encounter.begin()
    return encounter


def encounter_view(
    encounter: Encounter,
    content: ContentBundle | None = None,
    locale: str = "zh",
) -> dict:
    """给界面的先攻条。`distance_hint` 非空时，说明距离现在没有意义。

    传了 `content` 就顺手把每个人的 **AC 与 HP** 填进 `order` 行：
    先攻条上不显示血量的话，界面只能自己算一遍，那必然与角色卡分叉。
    不传时这些键不出现（引擎层与单测不需要它们）。
    """
    from ..rules.combat import target_from_actor

    view = encounter.to_dict()
    if content is not None:
        for row in view["order"]:
            combatant = encounter.get(row["id"])
            target = target_from_actor(content, combatant.actor, locale)
            row["ac"] = int(target.ac)
            row["hp"] = combatant.actor.root().hp.to_dict()
            row["kind"] = combatant.actor.kind.value
    placed = int(view["placed"])
    view["distance_hint"] = (
        "" if placed >= 2
        else "位置还没摆，所有人按 (0,0) 算 —— 距离为 0，"
             "「30 尺内」会一律成立。要判距离请先摆位。"
    )
    return view


def advance_turn(encounter: Encounter) -> dict:
    """结束当前回合，轮到下一个人（走完末尾就进下一轮）。"""
    who = encounter.next_turn()
    return {
        "round": int(encounter.round),
        "current": who.id if who else "",
        "label": who.label if who else "",
        "order": encounter.order(),
    }


def place_combatant(encounter: Encounter, who: Any, x: int, y: int) -> dict:
    """摆位：不花移动力（开场布阵、DM 改判）。"""
    return encounter.place(who, x, y).to_dict()


def move_combatant(encounter: Encounter, who: Any, x: int, y: int) -> dict:
    """走过去：消耗移动力 = 直线格数 × 5 尺，不做寻路。"""
    return encounter.move(who, x, y)


def teleport_combatant(
    encounter: Encounter, who: Any, x: int, y: int, max_feet: int,
) -> dict:
    """传送：不花移动力，但要过距离与占位两道检查。"""
    return encounter.teleport(who, x, y, max_feet)


def encounter_distance(encounter: Encounter, one: Any, other: Any) -> int:
    """两人相距多少尺（5 尺一格，斜着走不算远）。"""
    return encounter.distance_between(one, other)


def set_combatant_side(encounter: Encounter, who: Any, side: str) -> dict:
    """改阵营（party / foes）。群体战术的「盟友」只认它 —— 谁跟谁是一伙
    只有桌上知道，程序只负责记住，不负责猜。"""
    return encounter.set_side(who, side).to_dict()


def nearby(encounter: Encounter, who: Any, feet: int) -> list[dict]:
    """`feet` 尺内的人。共享月光这类「捎一个」的能力用它列候选。"""
    source = encounter.get(who)
    return [
        {
            "id": item.id,
            "label": item.label,
            "feet": encounter.distance(source, item),
        }
        for item in encounter.nearest_within(who, feet)
    ]
