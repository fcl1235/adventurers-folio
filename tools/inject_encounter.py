# -*- coding: utf-8 -*-
"""P9a 反向验证：把遭遇战的五处关键判断改错，测试必须真红。

每条注入都对应一个「如果写错会不会被发现」的担心：

1. 开场给所有人满额度 —— 谁先攻都一样，等于先攻白掷；
2. 回合结束不清额度 —— 动作能攒，一轮变两轮；
3. 距离改成曼哈顿 —— 斜着走变远，30 尺内的法术会误判成够不着；
4. 传送不做距离检查 —— 「30 尺」形同虚设；
5. 失败不回滚代价 —— 超距白扣一次次数与附赠动作。

跑法：`python tools/inject_encounter.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.inject_common import run  # noqa: E402

ENCOUNTER = ROOT / "dnd5r/rules/encounter.py"
POWERS = ROOT / "dnd5r/rules/powers.py"

CASES = [
    (
        "开场给所有人满额度（不清零）",
        ENCOUNTER,
        """        for combatant in self.combatants:
            combatant.economy.action = 0
            combatant.economy.bonus = 0
            combatant.economy.movement = 0
            combatant.economy.reaction = 1""",
        """        for combatant in self.combatants:
            combatant.economy.action = 1
            combatant.economy.bonus = 1
            combatant.economy.reaction = 1""",
    ),
    (
        "回合结束不清额度（动作能攒）",
        ENCOUNTER,
        """        if current is not None:
            current.economy.end_turn()""",
        """        if current is not None:
            pass""",
    ),
    (
        "距离改成曼哈顿（斜着走变远）",
        ENCOUNTER,
        """        return max(abs(a.x - b.x), abs(a.y - b.y))""",
        """        return abs(a.x - b.x) + abs(a.y - b.y)""",
    ),
    (
        "传送不检查距离上限",
        ENCOUNTER,
        """        if feet > int(max_feet):
            raise IllegalAction("传送距离 %d 尺，超过上限 %d 尺" % (feet, int(max_feet)))""",
        """        if False:
            raise IllegalAction("传送距离 %d 尺，超过上限 %d 尺" % (feet, int(max_feet)))""",
    ),
    (
        "能力失败不回滚代价",
        POWERS,
        """    except DndError:
        for kind, amount in paid_actions:
            if economy is not None:
                economy.refund(kind, amount)
        for pool, amount in paid_pools:
            pool.recover(amount)
        raise""",
        """    except DndError:
        raise""",
    ),
]

TESTS = ["tests.unit.test_encounter"]

if __name__ == "__main__":
    sys.exit(run(CASES, TESTS))
