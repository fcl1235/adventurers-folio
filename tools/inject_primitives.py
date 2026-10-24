# -*- coding: utf-8 -*-
"""P13/P13b 反向验证：把新原语故意写错八处，测试必须变红。

八处都是「看起来合理、其实会算错」的写法：

  1. 保底不看熟练          不熟练的检定也按 10 计，白送半个专精
  2. 保底没有低面门槛      骰出 18 也改成 10，等于 nerf 玩家
  3. 兑换不扣点            造位白送，点池成了摆设
  4. 创造的位长休回满      原文是 vanishes（蒸发），回满等于永久白送
  5. 召唤物不进场          法术放完场上没有这只生物，报告却说召唤了
  6. 灵感骰不进合计        消耗了骰、报了数，加值却没加上
  7. 灵感能给自己          原文 another creature，白送一颗自用骰
  8. 没骰也不报错          use_inspiration 静默无效，玩家以为加了

跑法：python tools/inject_primitives.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from inject_common import run

ROOT = Path(__file__).resolve().parents[1]
COMBAT = ROOT / "dnd5r/api/combat.py"
EXCHANGE = ROOT / "dnd5r/rules/effects/exchange.py"
REST = ROOT / "dnd5r/rules/rest.py"

TOKEN = ROOT / "dnd5r/rules/effects/token.py"

CASES = [
    (
        "保底不看熟练（不熟练也按 10 计）",
        COMBAT,
        """            if effect.when_proficient and not proficient:""",
        """            if effect.when_proficient and False:""",
    ),
    (
        "保底没有低面门槛（高面也被改写）",
        COMBAT,
        """            if die <= effect.when_die_lte:""",
        """            if True:""",
    ),
    (
        "兑换不扣点（造位白送）",
        EXCHANGE,
        """        points.spend(option.cost)""",
        """        pass""",
    ),
    (
        "创造的位长休回满（不蒸发）",
        REST,
        """        del root.resources.pools[pool_id]""",
        """        root.resources.pools[pool_id].refill()""",
    ),
    (
        "召唤物不进场（法术放完场上没这只生物）",
        COMBAT,
        """    combatant = encounter.join(body, roller, side=side)""",
        """    combatant = encounter.combatants[0]""",
    ),
    (
        "灵感骰不进合计（消耗了却没加）",
        COMBAT,
        '        "total": die + resolution.total + (inspiration["roll"] if inspiration else 0),',
        '        "total": die + resolution.total,',
    ),
    (
        "灵感能给自己",
        TOKEN,
        "        if self.forbid_self and combatant.actor.root() is ctx.actor.root():",
        "        if False and combatant.actor.root() is ctx.actor.root():",
    ),
    (
        "没骰也不报错（静默无效）",
        COMBAT,
        '        raise RuleError("身上没有待用的灵感骰（诗人要先用附赠动作给你一颗）")',
        "        return None",
    ),
]

TESTS = ["tests.unit.test_primitives", "tests.unit.test_tokens"]


if __name__ == "__main__":
    sys.exit(run(CASES, TESTS, timeout=240))
