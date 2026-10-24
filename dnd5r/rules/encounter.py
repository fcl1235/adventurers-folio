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
4. **阵营是一条输入，不是判断**。「盟友」在 `Actor` 上不存在（同 `willing`），
   所以 `Combatant.side` 按本体类型给默认值、界面上看得见、DM 能改。
   群体战术这类「盟友站在目标旁边」的特性只认它，不猜「怪物都是同伙」。
   反过来，**没摆位就不算相邻** —— 这条默认是收紧的：宽的那条会白送优势。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..kernel.errors import IllegalAction, RuleError
from ..kernel.rng import Rng
from ..model.actor import Actor, ActorKind
from .actioneconomy import ActionEconomy

# 一格 = 5 尺。对内算格数，对外一律报尺 —— 规则书里说的是尺。
FOOT = 5
# 触及范围：暂时固定 5 尺。内容里「触及 10 尺」的怪物还没建模，
# 所以这里不能假装知道 —— 报告里照实说这是 5 尺口径。
REACH_FEET = 5

# 阵营：只有两边。**不是**「好人/坏人」，是「谁的盟友算谁的」——
# 群体战术（G23）要回答「目标旁边有没有这只狼的盟友」，而「盟友」这个词
# 在 `Actor` 上不存在（与 `willing` 同一条理由：心意由 DM 定）。
# 所以它是一条**摆明了的**输入：加入时按本体类型给个默认值（玩家→我方、
# 怪物→敌方），先攻条上看得见，DM 随时能改。默认值不是判断，是起点。
SIDES: tuple[str, ...] = ("party", "foes")


def _default_side(actor: Actor) -> str:
    """默认阵营看**本体**：变熊的德鲁伊还是玩家这边的人（形态层不算另一伙）。"""
    return "party" if actor.root().kind is ActorKind.PC else "foes"


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
    # 阵营：`party` / `foes`。默认按本体类型给，`Encounter.set_side` 可改。
    side: str = ""

    def __post_init__(self) -> None:
        if not self.side:
            self.side = _default_side(self.actor)
        elif self.side not in SIDES:
            raise RuleError("阵营只能是 %s：%r" % ("/".join(SIDES), self.side))

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
            "side": self.side,
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

    def add(self, actor: Actor, x: int = 0, y: int = 0, side: str = "") -> Combatant:
        if any(item.id == actor.id for item in self.combatants):
            raise RuleError("参与者重复：%s" % actor.id)
        combatant = Combatant(
            actor=actor, x=int(x), y=int(y), placed=False, side=side,
            economy=ActionEconomy(movement=self._walk_speed(actor)),
            seq=len(self.combatants),
        )
        self.combatants.append(combatant)
        return combatant

    def set_side(self, who, side: str) -> Combatant:
        """改阵营。**不猜**：谁跟谁是一伙的只有桌上知道，程序只负责记住。"""
        if side not in SIDES:
            raise RuleError("阵营只能是 %s：%r" % ("/".join(SIDES), side))
        combatant = self.get(who)
        combatant.side = side
        return combatant

    @staticmethod
    def _walk_speed(actor: Actor) -> int:
        return int(actor.top().statblock.speed("walk") or 30)

    def join(self, actor: Actor, rng: Rng, x: int = 0, y: int = 0,
             side: str = "") -> Combatant:
        """中途加入一个人（增援、召唤物、DM 临时放进来的一只）。

        三件事必须一起做，少一件就出鬼：

        1. **掷先攻**：新来的人用 1d20 + 敏捷调整值，与开场同一条规则；
        2. **重新排序**：他可能插在中间；
        3. **把回合指针挪回原来那个人**：排序会改变下标，不重新定位的话
           「当前回合」会毫无理由地跳到别人身上 —— 这是最容易漏的一步。
        """
        combatant = self.add(actor, x, y, side)
        if not self.round:
            return combatant
        if actor.root().hp.is_down:
            combatant.initiative = -1
        else:
            combatant.initiative = int(rng.randint(1, 20)) + _dex_mod(actor)
        held = self.current()
        self._sort()
        if held is not None:
            self.turn = self.combatants.index(held)
        return combatant

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
        """走过去：消耗移动力 = 直线格数 × 5 尺。**不做寻路**，绕障碍请分段走。

        走出别人的触及范围时，报告里会列出「谁可以对他借机攻击」——
        **不自动扣反应、也不自动掷骰**：打不打是桌上决定的，
        程序只负责算准「谁够得着、谁还留着反应」。
        """
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
        before = {item.id: self.distance(combatant, item)
                  for item in self.combatants if item is not combatant}
        combatant.economy.movement = left - feet
        combatant.x, combatant.y = target
        combatant.placed = True
        return {
            "id": combatant.id, "label": combatant.label,
            "x": target[0], "y": target[1],
            "feet": feet, "left": int(combatant.economy.movement),
            "left_reach": self._left_reach(combatant, before),
        }

    def _left_reach(self, combatant: Combatant, before: dict[str, int]) -> list[dict]:
        """移动前在 5 尺内、移动后不在的人 —— 借机攻击的候选。

        `reaction` 为 False 也要列出来（只是打不了）：界面上「够得着但没反应」
        与「够不着」是两件不同的事，混成一条会让人以为距离算错了。
        """
        found: list[dict] = []
        for item in self.combatants:
            if item is combatant or item.id not in before:
                continue
            if item.actor.root().hp.is_down:
                continue
            if before[item.id] > REACH_FEET:
                continue
            if self.distance(combatant, item) <= REACH_FEET:
                continue
            found.append({
                "id": item.id,
                "label": item.label,
                "reaction": int(item.economy.reaction) > 0,
            })
        return found

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

    def allies_of(self, who) -> list[Combatant]:
        """同阵营、没倒地、不是自己。**阵营是输入**（见 `SIDES`），不是判断。"""
        source = self.get(who)
        return [
            item for item in self.combatants
            if item is not source
            and item.side == source.side
            and not item.actor.root().hp.is_down
        ]

    def allies_near(self, who, target, feet: int = REACH_FEET) -> list[Combatant]:
        """「谁站在**目标**旁边」—— 不是站在自己旁边。

        群体战术的原文是 "an ally is within 5 feet of that creature"，
        判的是目标身边，写成「自己身边」在双方贴身时会碰巧一样，
        一旦分成两堆就全错，而且错得看不出来（G23 的原文坑）。

        只算**摆过位**的人：默认全员挤在 (0,0) 时人人相邻，
        那会让每只狼白拿优势 —— 宁可算不了，也不能算错。
        """
        mark = self.get(target)
        return [item for item in self.allies_of(who)
                if item.placed and self.distance(mark, item) <= int(feet)]

    # --- 推进 ---------------------------------------------------------
    def next_turn(self) -> Combatant | None:
        """结束当前回合，轮到下一个人；走完最后一个人就进下一轮。

        回合结束只清**未用完的额度**（动作/附赠/移动不能攒）与**本回合到期的一次性标记**
        （「本回合结束前下一次攻击优势」就在这里失效）。反应不在回合结束清 ——
        它按轮恢复，见 `_start_round`。
        """
        if not self.combatants:
            return None
        if not self.round:
            return self.begin()
        current = self.current()
        if current is not None:
            current.economy.end_turn()
            current.actor.root().marks.end_turn()
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
            # `round` 作用域的标记（在别人回合里被挂上的）到这一轮结束就失效
            combatant.actor.root().marks.end_round()

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
