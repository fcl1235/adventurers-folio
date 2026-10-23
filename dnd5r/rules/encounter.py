# -*- coding: utf-8 -*-
"""遭遇战：谁在场上、按什么顺序行动、彼此离多远。

**它不进存档**，和 `ActionEconomy` 是同一条理由：关掉程序就不该记得
「上一轮谁先攻」这件事。角色本身的派生值仍然现算。

三条设计取舍，都不是随手定的：

1. **坐标是 5 尺整数格，距离用切比雪夫**。5e 的标准规则是「对角线交替
   计 5/10 尺」，剧场心智（TotM）用的是「每格 5 尺」。后者误差在
   30 尺内不超过 1 格，但不需要记「这是第几条对角线」——这本册子算的
   是「够不够得着」，不是战术推演。
2. **不做寻路**。`move` 的消耗直接取直线格数，绕柱子请分两段走。
   偷偷加一层 A* 会让人以为程序在管障碍物，其实它不知道墙在哪。
3. **位置默认 (0,0)**。所有人挤在原点时距离为 0，于是「30 尺内」
   一律成立 —— 这是**宽松**的默认：宁可放过，不可误拦。报告里会写
   `placed=False`，让界面有机会说「位置还没摆」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..kernel.errors import IllegalAction, RuleError
from ..kernel.rng import Rng
from ..model.actor import Actor
from .actioneconomy import ActionEconomy

# 一格 = 5 尺。对内算格数，对外一律报尺 —— 规则书里说的是尺。
FOOT = 5


def _dex_mod(actor: Actor) -> int:
    """先攻用敏捷调整值。变形后取顶层（猫的敏捷不是德鲁伊的敏捷）。"""
    return int(actor.top().statblock.abilities.mod("dex"))


@dataclass
class Combatant:
    """场上的一个人。`actor` 是本体引用，不复制 —— 血量和资源只有一份。"""

    actor: Actor
    initiative: int = 0
    x: int = 0
    y: int = 0
    placed: bool = False          # 有没有真的摆过位置（还是默认挤在原点）
    economy: ActionEconomy = field(default_factory=ActionEconomy)
    # 加入顺序。排序的最后一档 tiebreak 用它，而不是「当前列表里的位置」——
    # 后者在第二次排序时已经变了，会让同分的人来回换位。
    seq: int = 0

    @property
    def id(self) -> str:
        return self.actor.id

    @property
    def label(self) -> str:
        return self.actor.display_name or self.actor.statblock.name.zh

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "initiative": int(self.initiative),
            "x": int(self.x),
            "y": int(self.y),
            "placed": self.placed,
            "economy": self.economy.to_dict(),
            "down": self.actor.root().hp.is_down,
        }


@dataclass
class Encounter:
    """一场遭遇战。参与者、先攻序、当前回合指针、轮数。

    生命周期：`Encounter.of(...)` → `roll_initiative()` → `begin()` →
    `next_turn()` …。`begin()` 之前 `current()` 是 None。
    """

    combatants: list[Combatant] = field(default_factory=list)
    round: int = 0
    turn: int = -1

    # --- 组装 ---------------------------------------------------------
    @classmethod
    def of(cls, actors: Iterable[Actor]) -> "Encounter":
        found = cls()
        for actor in actors:
            found.add(actor)
        return found

    def add(self, actor: Actor, x: int = 0, y: int = 0) -> Combatant:
        if any(item.id == actor.id for item in self.combatants):
            raise RuleError("参与者重复：%s" % actor.id)
        combatant = Combatant(
            actor=actor, x=int(x), y=int(y), placed=False,
            economy=ActionEconomy(movement=self._walk_speed(actor)),
            seq=len(self.combatants),
        )
        self.combatants.append(combatant)
        return combatant

    @staticmethod
    def _walk_speed(actor: Actor) -> int:
        return int(actor.top().statblock.speed("walk") or 30)

    def roll_initiative(self, rng: Rng) -> list[Combatant]:
        """每人掷 d20 + 敏捷调整值。

        同分时**不掷硬币**：先看敏捷调整值（反应快的人先动），再按加入顺序。
        随机化的同分排序每次跑出来不一样，测试就没法断言了。
        """
        for combatant in self.combatants:
            if combatant.actor.root().hp.is_down:
                combatant.initiative = -1      # 倒地的不参与排序，排在最后
                continue
            combatant.initiative = int(rng.randint(1, 20)) + _dex_mod(combatant.actor)
        self._sort()
        return list(self.combatants)

    def _sort(self) -> None:
        self.combatants.sort(key=lambda c: (
            c.actor.root().hp.is_down,
            -int(c.initiative),
            -_dex_mod(c.actor),
            c.seq,
        ))

    def begin(self) -> Combatant | None:
        """开始第一轮：轮数置 1，指针落到第一个人，他的额度恢复。

        其余人**先清空额度**再等着轮到自己 —— 建场时每人一份「满额度」看着方便，
        但那等于让所有人都在第一轮白拿一个动作（谁先攻都一样）。反应例外：
        第一轮开始就该有，被偷袭的人也得能借机攻击。
        """
        if not self.combatants:
            return None
        if self.round:
            raise IllegalAction("这场遭遇战已经开始了")
        self.round = 1
        self.turn = 0
        for combatant in self.combatants:
            combatant.economy.action = 0
            combatant.economy.bonus = 0
            combatant.economy.movement = 0
            combatant.economy.reaction = 1
        self._start_for(self.combatants[0])
        return self.combatants[0]

    # --- 查询 ---------------------------------------------------------
    def current(self) -> Combatant | None:
        if 0 <= self.turn < len(self.combatants):
            return self.combatants[self.turn]
        return None

    def get(self, who: "str | Actor | Combatant") -> Combatant:
        """`who` 可以是 id、Actor 或 Combatant 本身 —— 调用方三种都会顺手传。"""
        if isinstance(who, Combatant):
            return who
        ident = who.id if isinstance(who, Actor) else str(who)
        for combatant in self.combatants:
            if combatant.id == ident:
                return combatant
        raise RuleError("场上没有这个人：%s" % ident)

    def has(self, who: "str | Actor | Combatant") -> bool:
        try:
            self.get(who)
        except RuleError:
            return False
        return True

    def occupant_at(self, x: int, y: int) -> Combatant | None:
        for combatant in self.combatants:
            if combatant.x == int(x) and combatant.y == int(y) \
                    and not combatant.actor.root().hp.is_down:
                return combatant
        return None

    @staticmethod
    def cells_between(a: Combatant, b: Combatant) -> int:
        """切比雪夫距离（格）：斜着走不算远。"""
        return max(abs(a.x - b.x), abs(a.y - b.y))

    @classmethod
    def distance(cls, a: Combatant, b: Combatant) -> int:
        """两人相距多少尺。"""
        return cls.cells_between(a, b) * FOOT

    def distance_between(self, one, other) -> int:
        return self.distance(self.get(one), self.get(other))

    def within(self, one, other, feet: int) -> bool:
        return self.distance_between(one, other) <= int(feet)

    def placed_count(self) -> int:
        """摆过位置的人数。全 0 说明这场遭遇战只是「谁先攻」，没有地图含义。"""
        return sum(1 for item in self.combatants if item.placed)

    # --- 移动 ---------------------------------------------------------
    def place(self, who, x: int, y: int) -> Combatant:
        """直接摆位，不花移动力（开场布阵、DM 改判都走这条）。"""
        combatant = self.get(who)
        combatant.x, combatant.y = int(x), int(y)
        combatant.placed = True
        return combatant

    def move(self, who, x: int, y: int) -> dict:
        """走过去：消耗移动力 = 直线格数 × 5 尺。**不做寻路**，绕障碍请分段走。"""
        combatant = self.get(who)
        if combatant.actor.root().hp.is_down:
            raise IllegalAction("%s 已经倒地，不能移动" % combatant.label)
        if self.current() is not combatant:
            raise IllegalAction("现在不是 %s 的回合" % combatant.label)
        target = (int(x), int(y))
        occupied = self.occupant_at(*target)
        if occupied is not None and occupied is not combatant:
            raise IllegalAction("%s 已经在 (%d, %d)" % (occupied.label, target[0], target[1]))
        feet = max(abs(combatant.x - target[0]), abs(combatant.y - target[1])) * FOOT
        left = int(combatant.economy.movement)
        if feet > left:
            raise IllegalAction("%s 只剩 %d 尺移动力，走不过去 %d 尺"
                                % (combatant.label, left, feet))
        combatant.economy.movement = left - feet
        combatant.x, combatant.y = target
        combatant.placed = True
        return {
            "id": combatant.id, "label": combatant.label,
            "x": target[0], "y": target[1],
            "feet": feet, "left": int(combatant.economy.movement),
        }

    def teleport(self, who, x: int, y: int, max_feet: int) -> dict:
        """传送：**不花移动力**，但要过距离与占位两道检查。

        距离按直线格数算（不是路径）—— 传送本来就不受地形影响。
        """
        combatant = self.get(who)
        target = (int(x), int(y))
        occupied = self.occupant_at(*target)
        if occupied is not None and occupied is not combatant:
            raise IllegalAction("%s 已经在 (%d, %d)" % (occupied.label, target[0], target[1]))
        feet = max(abs(combatant.x - target[0]), abs(combatant.y - target[1])) * FOOT
        if feet > int(max_feet):
            raise IllegalAction("传送距离 %d 尺，超过上限 %d 尺" % (feet, int(max_feet)))
        combatant.x, combatant.y = target
        combatant.placed = True
        return {
            "id": combatant.id, "label": combatant.label,
            "x": target[0], "y": target[1], "feet": feet,
        }

    def nearest_within(self, who, feet: int) -> list[Combatant]:
        """`feet` 尺内的人（不含自己、不含倒地）。

        「愿意与否」**不在这里判** —— Actor 上没有这个字段，硬加一个
        `willing` 布尔就等于让程序替 DM 决定 NPC 的心意。这里只回答
        「谁在范围内」，剩下的交给桌上。
        """
        source = self.get(who)
        return [
            item for item in self.combatants
            if item is not source
            and not item.actor.root().hp.is_down
            and self.distance(source, item) <= int(feet)
        ]

    # --- 推进 ---------------------------------------------------------
    def next_turn(self) -> Combatant | None:
        """结束当前回合，轮到下一个人；走完最后一个人就进下一轮。

        回合结束只清**未用完的额度**（动作/附赠/移动不能攒），
        反应不在回合结束清 —— 它按轮恢复，见 `_start_round`。
        """
        if not self.combatants:
            return None
        if not self.round:
            return self.begin()
        current = self.current()
        if current is not None:
            current.economy.end_turn()
        index = self.turn + 1
        if index >= len(self.combatants):
            index = 0
            self.round += 1
            self._start_round()
        self.turn = index
        nxt = self.combatants[index]
        self._start_for(nxt)
        return nxt

    def _start_for(self, combatant: Combatant) -> None:
        """回合开始：动作、附赠、移动恢复。移动速度**现算** —— 变形前后不一样。"""
        combatant.economy.start_turn(movement=self._walk_speed(combatant.actor))

    def _start_round(self) -> None:
        """一轮开始：所有人的反应恢复（自己的回合还没轮到时也能借机攻击）。"""
        for combatant in self.combatants:
            combatant.economy.start_round()

    # --- 输出 ---------------------------------------------------------
    def order(self) -> list[dict]:
        current = self.current()
        rows = []
        for index, combatant in enumerate(self.combatants):
            row = combatant.to_dict()
            row["active"] = current is not None and combatant is current
            rows.append(row)
        return rows

    def to_dict(self) -> dict:
        current = self.current()
        return {
            "round": int(self.round),
            "turn": int(self.turn),
            "started": bool(self.round),
            "current": current.id if current else "",
            "placed": self.placed_count(),
            "order": self.order(),
        }
