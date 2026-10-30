# -*- coding: utf-8 -*-
"""运行时状态：状态（conditions）、力竭、濒死、专注 DC。

这一层存在的理由：这三样都是**玩家操作出来的事实**，界面只许改事实、不许改数值。
力竭的 −2/级由 `rules/resolver.py` 现算；状态则**只是记录**（见 `set_condition`
的说明），界面必须把这条差别说出来，否则就是撒谎型 UI。
"""

from __future__ import annotations

from ..kernel.errors import RuleError
from ..kernel.rng import Rng
from ..model.actor import MAX_EXHAUSTION, Actor
from ..model.death import DeathSaves
from ..rules import death as death_rules

# 专注豁免：受伤害就掷，DC = max(10, 伤害 // 2)
CONCENTRATION_MIN_DC = 10


def _saves_of(actor: Actor) -> DeathSaves:
    """濒死记分挂在**身体**上：变形层不该有第二份死亡豁免。"""
    return actor.root().death_saves


def set_condition(actor: Actor, condition_id: str, on: bool = True) -> bool:
    """记上/取下一条状态。返回是否真的变了（重复点不报错）。

    **只记录，不计入数值。** 这一点是有意的：状态的规则效果大半要看具体情形
    （麻痹=自动失手近战命中、束缚=速度 0、隐形=攻击优势），在没有目标模型的
    前端里硬算反而会算错。所以界面写明「已记录，未计入数值」，
    要比偷偷算一半诚实得多。
    """
    ident = str(condition_id or "").strip()
    if not ident:
        raise RuleError("状态 id 不能为空")
    had = actor.conditions.has(ident)
    if on and not had:
        actor.conditions.add(ident)
        return True
    if not on and had:
        actor.conditions.remove(ident)
        return True
    return False


def clear_conditions(actor: Actor) -> tuple[str, ...]:
    """清空全部状态，返回被清掉的 id（状态行要能说出来清了什么）。"""
    gone = actor.conditions.ids()
    actor.conditions.clear()
    return gone


def set_exhaustion(actor: Actor, level: int) -> int:
    """设力竭等级（0–6）。**这个是真的计入数值的**：每级全部 d20 −2、速度 −5 尺。

    写的永远是 `root()`：变形层是临时外壳，力竭是身体的负担。
    """
    if isinstance(level, bool) or not isinstance(level, int):
        raise RuleError("力竭等级必须是整数：%r" % (level,))
    if not 0 <= level <= MAX_EXHAUSTION:
        raise RuleError("力竭等级必须在 0–%d：%r" % (MAX_EXHAUSTION, level))
    actor.root().exhaustion = level
    return level


def roll_death_save(actor: Actor, rng: Rng | None = None) -> dict:
    """掷一次死亡豁免。**HP 没到 0 时拒绝** —— 活着掷它只会误导。

    骰点与记分都在 `rules/death.py`，这里只负责「回魂时把 HP 抬到 1」这一步
    （那是 HP 池的事，记分卡够不着）。
    """
    if not actor.hp.is_down:
        raise RuleError("HP 还没到 0（当前 %d），不需要掷死亡豁免" % actor.hp.current)
    saves = _saves_of(actor)
    if rng is None:
        from ..kernel.rng import SeededRng
        rng = SeededRng()
    result = death_rules.roll_death_save(saves, rng)
    if result["revived"] and actor.hp.current <= 0:
        actor.hp.current = 1
    return result


def reset_death_saves(actor: Actor) -> None:
    """清空记分（回满血、稳定后休整、或玩家手动纠错）。"""
    _saves_of(actor).reset()


def death_save_view(actor: Actor) -> dict:
    saves = _saves_of(actor)
    return {
        "succeeded": saves.succeeded,
        "failed": saves.failed,
        "succeeded_of": death_rules.STABLE_AT,
        "failed_of": death_rules.DEAD_AT,
        "dead": saves.dead,
        "stable": saves.stable,
    }


def concentration_dc(damage: int) -> int:
    """专注豁免 DC = max(10, 伤害 // 2)。伤害 0 或负数按 10 算（下限就是 10）。"""
    try:
        amount = int(damage)
    except (TypeError, ValueError):
        raise RuleError("伤害必须是整数：%r" % (damage,))
    if amount < 0:
        raise RuleError("伤害不能为负：%r" % (amount,))
    return max(CONCENTRATION_MIN_DC, amount // 2)
