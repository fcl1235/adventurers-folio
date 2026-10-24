# -*- coding: utf-8 -*-
"""会话：CLI 剧本与单测的便捷壳。

2026-10（P11，§14.32）**降位**：正式的前后端契约是 `dnd5r.api` 的函数门面，
桌面端从它直取；Session 只保留「命令 → 报告」的剧本用法（CLI `play`
无头跑流程）。它**没有自己的投影** —— 要看角色就 `api.character_sheet`，
同一个数不会有第二个算法（G24 的正解；原先那套 Card 投影已删）。

一条铁律不变：**前端不发方法名，发意图**。`dispatch(UsePower("..."))`
返回 Report；角色本身的派生值仍然现算，回合状态（动作经济、遭遇战指针）
由这里持有 —— 所以 CLI 能无头跑完整个流程，这本身就是后端独立的证明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .content import ClassDef, ContentBundle, load_all
from .kernel.errors import DndError, IllegalAction
from .kernel.events import Report
from .kernel.rng import Rng, SeededRng
from .model.actor import Actor
from .model.profile import ClassEntry
from .rules.actioneconomy import ActionEconomy
from .rules.encounter import Encounter
from .rules.rest import RestResult, long_rest, short_rest


# --- 命令 -------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class UsePower:
    """用能力。`choice` 是这次操作需要玩家做的选择（如变形选哪个形态）。"""

    power_id: str
    choice: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ShortRest:
    dice: int = 0


@dataclass(frozen=True, slots=True)
class LongRest:
    pass


@dataclass(frozen=True, slots=True)
class NewTurn:
    pass


@dataclass(frozen=True, slots=True)
class TakeDamage:
    amount: int


@dataclass(frozen=True, slots=True)
class Regain:
    amount: int


Command = (UsePower, ShortRest, LongRest, NewTurn, TakeDamage, Regain)


class Session:
    def __init__(
        self,
        bundle: ContentBundle,
        locale: str = "zh",
        seed: int | None = None,
        rng: Rng | None = None,
    ) -> None:
        self.bundle = bundle
        self.locale = locale
        self.rng = rng or SeededRng(seed)
        self.economy = ActionEconomy()
        self.encounter: Encounter | None = None
        self.actor: Actor | None = None
        self.log: list[str] = []
        self.last_report: Report = Report()

    # --- 打开 ---------------------------------------------------------
    @classmethod
    def open(cls, root: str = "plugins", locale: str = "zh", seed: int | None = None) -> "Session":
        return cls(load_all(root), locale=locale, seed=seed)

    def create_character(
        self,
        class_id: str,
        class_level: int,
        scores: Mapping[str, int],
        name_zh: str = "无名冒险者",
        name_en: str = "Unnamed Adventurer",
        actor_id: str = "pc.hero",
        subclass: str | None = None,
        extra_classes: Sequence[tuple[str, int]] = (),
    ) -> Actor:
        from .api import new_character

        self.actor = new_character(
            self.bundle, class_id=class_id, class_level=class_level,
            scores=scores, name_zh=name_zh, name_en=name_en,
            actor_id=actor_id, subclass=subclass,
            extra_classes=tuple(extra_classes),
        )
        self.economy.reset(movement=self.actor.statblock.speed("walk"))
        self.encounter = None
        self.log = []
        return self.actor

    def start_encounter(
        self,
        others: Sequence[Actor] = (),
        rng: Rng | None = None,
    ) -> Encounter:
        """把主角和 `others` 拉进一场遭遇战：掷先攻，开始第一轮。

        主角的额度对象**就是** `self.economy` 那一份（同一个引用），不是另建一套。
        两份各记一套的结果是「角色卡上写着动作还在，遭遇战里说他用完了」。
        """
        from .api import new_encounter

        actor = self.character
        encounter = new_encounter([actor, *others], rng=rng or self.rng)
        encounter.get(actor).economy = self.economy
        self.encounter = encounter
        return encounter

    @property
    def character(self) -> Actor:
        if self.actor is None:
            raise IllegalAction("会话里还没有角色")
        return self.actor

    # --- 上下文 -------------------------------------------------------
    def hit_dies(self) -> dict[str, int]:
        found: dict[str, int] = {}
        profile = self.character.profile
        if profile is None:
            return found
        for entry in profile.classes:
            class_def = self.bundle.classes.get(entry.class_id)
            if class_def is not None:
                found[entry.class_id] = class_def.hit_die
        return found

    # --- 派发 ---------------------------------------------------------
    def dispatch(self, command: Any) -> Report:
        """执行一条命令。失败不抛出 —— Report.ok=False + 人话原因。"""
        try:
            report = self._handle(command)
        except DndError as exc:
            report = Report(ok=False, message=str(exc))
        if report.message:
            self.log.append(report.message)
            self.log = self.log[-12:]       # 剧本日志只留最近 12 条
        self.last_report = report
        return report

    def _handle(self, command: Any) -> Report:
        if isinstance(command, UsePower):
            return self._use_power(command.power_id, command.choice)
        if isinstance(command, ShortRest):
            return self._rest(short_rest(self.character, self.hit_dies(),
                                        spend=command.dice, rng=self.rng))
        if isinstance(command, LongRest):
            return self._rest(long_rest(self.character))
        if isinstance(command, NewTurn):
            if self.encounter is not None:
                who = self.encounter.next_turn()
                if who is None:
                    return Report(ok=False, message="遭遇战里没有人")
                note = "" if who.actor is self.character else "（还没轮到你）"
                return Report(ok=True, message="第 %d 轮 · 轮到 %s%s"
                              % (self.encounter.round, who.label, note))
            # 没有遭遇战时没有别人可以推进 —— 只推进自己的回合，
            # 「本回合结束前」的一次性标记（下一次攻击优势）在这里失效
            self.character.root().marks.end_turn()
            self.economy.start_turn(movement=self.character.statblock.speed("walk"))
            return Report(ok=True, message="新回合：动作与附赠动作已恢复")
        if isinstance(command, TakeDamage):
            applied = self.character.root().hp.damage(int(command.amount))
            return Report(ok=True, message="受到 %d 点伤害" % applied)
        if isinstance(command, Regain):
            healed = self.character.root().hp.heal(int(command.amount))
            return Report(ok=True, message="恢复 %d 点生命" % healed)
        raise IllegalAction("不认识的命令：%r" % (command,))

    def _use_power(self, power_id: str, choice: Mapping[str, Any] | None = None) -> Report:
        """转发到 `api.use_power` —— 那是唯一的能力执行入口，桌面端走同一条。

        延迟导入是因为 api 的门面反过来 re-export 本模块（Session 在 `api.__all__`
        里），顶层互相 import 会在包初始化时成环。
        """
        from .api import use_power as api_use_power

        result = api_use_power(
            self.character, self.bundle, power_id,
            economy=self.economy, rng=self.rng, locale=self.locale,
            choice=dict(choice or {}), encounter=self.encounter)
        return Report(ok=bool(result["ok"]), message=result["message"])

    def _rest(self, result: RestResult) -> Report:
        # 用 reset 而不是换新对象：遭遇战里的 Combatant 拿着同一个引用，
        # 换了对象会出现「休息完还能再动一次」。
        self.economy.reset(movement=self.character.statblock.speed("walk"))
        # 休息之后「本回合」的标记都没有意义了；`never` 作用域的（诅咒）
        # 不该被一次短休清掉，所以只清两个有时限的作用域。
        marks = self.character.root().marks
        marks.end_turn()
        marks.end_round()
        return Report(ok=True, message=result.summary)


__all__ = [
    "Session", "UsePower", "ShortRest", "LongRest", "NewTurn", "TakeDamage", "Regain",
]
