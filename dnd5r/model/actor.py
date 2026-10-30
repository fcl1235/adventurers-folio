# -*- coding: utf-8 -*-
"""Actor：玩家、怪物、野兽形态、召唤物统一表示。

变形不是「改三个属性」，而是压栈：本体在下层，形态成为顶层。
查询走顶层，HP 池留在本体（见 §3.1）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..kernel.errors import RuleError
from .conditions import ConditionSet
from .death import DeathSaves
from .inventory import Inventory
from .marks import MarkSet
from .profile import Profile
from .resources import ResourcePool
from .statblock import Statblock


class ActorKind(str, Enum):
    PC = "pc"
    NPC = "npc"
    MONSTER = "monster"
    FORM = "form"
    SUMMON = "summon"


# 2024：力竭 6 级即死亡。每级 −2 全部 d20、−5 尺速度（数值在 rules/resolver.py）
MAX_EXHAUSTION = 6


@dataclass
class HpPool:
    maximum: int
    current: int | None = None
    temp: int = 0

    def __post_init__(self) -> None:
        if self.maximum < 0:
            raise RuleError("HP 上限不能为负")
        if self.current is None:
            self.current = self.maximum

    def damage(self, amount: int) -> int:
        """先扣临时 HP，再扣当前 HP。返回实际扣除量。"""
        if amount < 0:
            raise RuleError("伤害不能为负")
        remaining = amount
        if self.temp > 0:
            absorbed = min(self.temp, remaining)
            self.temp -= absorbed
            remaining -= absorbed
        applied = min(self.current, remaining)
        self.current -= applied
        return applied + (amount - remaining)

    def heal(self, amount: int) -> int:
        if amount < 0:
            raise RuleError("治疗量不能为负")
        before = self.current
        self.current = min(self.maximum, self.current + amount)
        return self.current - before

    def grant_temp(self, amount: int) -> int:
        """临时 HP 取大不叠加。返回实际生效值。"""
        if amount <= self.temp:
            return self.temp
        self.temp = amount
        return self.temp

    @property
    def is_down(self) -> bool:
        return self.current <= 0

    def to_dict(self) -> dict:
        return {"maximum": self.maximum, "current": self.current, "temp": self.temp}


@dataclass
class Actor:
    id: str
    kind: ActorKind
    statblock: Statblock
    hp: HpPool
    profile: Profile | None = None
    resources: ResourcePool = field(default_factory=ResourcePool)
    inventory: Inventory = field(default_factory=Inventory)
    conditions: ConditionSet = field(default_factory=ConditionSet)
    effects: list = field(default_factory=list)
    layer: "Actor | None" = None      # 指向被替换的本体（变形/附身）
    above: "Actor | None" = field(default=None, repr=False)  # 指向压在自己上面的层
    display_name: str = ""
    # 变形：形态层记下「这次给了多少临时 HP」，回本体时要收回那部分
    morph_temp: int = 0
    # 变形期间的禁令（如 spellcasting）；空表示没有额外限制
    forbid: tuple[str, ...] = ()
    # 一次性标记（本回合的下一次攻击优势、待用的额外伤害）与「每回合一次」的记账。
    # **不进存档**：关掉程序就不该记得上一轮那个优势还没用（见 model/marks.py）。
    marks: MarkSet = field(default_factory=MarkSet)
    # 力竭等级 0–6。**这是事实不是派生值**：每级 −2 全部 d20、−5 尺速度由
    # `rules/resolver.py` 现算，这里只记「几级」。6 级是死亡，夹在上限内。
    exhaustion: int = 0
    # 濒死记分（0 HP 之后掷死亡豁免）。稳定/死亡之后由 `reset()` 清零。
    death_saves: DeathSaves = field(default_factory=DeathSaves)

    def __post_init__(self) -> None:
        if not self.id:
            raise RuleError("Actor.id 不能为空")
        if not isinstance(self.kind, ActorKind):
            raise RuleError("kind 必须是 ActorKind：%r" % (self.kind,))
        if not isinstance(self.statblock, Statblock):
            raise RuleError("statblock 必须是 Statblock")
        if not isinstance(self.hp, HpPool):
            raise RuleError("hp 必须是 HpPool")
        if isinstance(self.exhaustion, bool) or not isinstance(self.exhaustion, int):
            raise RuleError("exhaustion 必须是整数：%r" % (self.exhaustion,))
        if not 0 <= self.exhaustion <= MAX_EXHAUSTION:
            raise RuleError("力竭等级必须在 0–%d：%r" % (MAX_EXHAUSTION, self.exhaustion))

    # --- 层 -----------------------------------------------------------
    @property
    def is_morphed(self) -> bool:
        return self.layer is not None

    def top(self) -> "Actor":
        """最上层：所有派生查询的入口。"""
        node = self
        while node.above is not None:
            node = node.above
        return node

    def root(self) -> "Actor":
        """本体：HP 池与资源所在的那一层。"""
        node = self
        while node.layer is not None:
            node = node.layer
        return node

    def morph_into(self, form: "Actor") -> "Actor":
        """把本体压到下层，form 成为新的顶层。"""
        if self.above is not None:
            raise RuleError("当前层已有上层，不能再压栈")
        if form.layer is not None or form.above is not None:
            raise RuleError("形态不能已经处在层链里")
        form.layer = self
        self.above = form
        return form

    def unmorph(self) -> "Actor":
        """弹出顶层，返回本体。

        临时 HP 只收回「形态给的那部分」—— 施法者自己喝药得来的临时 HP 不该被吞掉。
        """
        if self.layer is None:
            return self
        body = self.layer
        body.above = None
        if self.morph_temp:
            body.hp.temp = max(0, body.hp.temp - int(self.morph_temp))
            self.morph_temp = 0
        self.layer = None
        return body

    @property
    def name_text(self):
        return self.statblock.name

    def forbids(self, action: str) -> bool:
        """变形期间的禁令沿层链叠加，任何一层说不行就是不行。"""
        node: Actor | None = self
        while node is not None:
            if action in node.forbid:
                return True
            node = node.layer
        return False

    # --- 便捷读取 -----------------------------------------------------
    def ability_mod(self, key: str) -> int:
        return self.statblock.abilities.mod(key)

    def pool(self, pool_id: str):
        return self.root().resources.get(pool_id)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "display_name": self.display_name,
            "statblock": {
                "name": self.statblock.name.to_dict(),
                "abilities": self.statblock.abilities.to_dict(),
                "ac_base": self.statblock.ac_base,
                "speeds": dict(self.statblock.speeds),
                "senses": dict(self.statblock.senses),
                "size": self.statblock.size,
                "cr": self.statblock.cr,
            },
            "hp": self.hp.to_dict(),
            "profile": self.profile.to_dict() if self.profile else None,
            "resources": self.resources.to_dict(),
            "inventory": self.inventory.to_dict(),
            "conditions": self.conditions.to_dict(),
            "layer_chain": self._layer_chain(),
        }

    def _layer_chain(self) -> list[str]:
        chain = []
        node = self
        while node.layer is not None:
            chain.append(node.layer.id)
            node = node.layer
        return chain
