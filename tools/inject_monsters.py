# -*- coding: utf-8 -*-
"""P9c 反向验证：把怪物那条链故意写错六处，测试必须变红。

六处都挑「看起来合理、其实会算错」的写法 —— 不是随便删个分号：

  1. 命中加值按「属性 + 熟练」推     巨鳄 +8 会被算成 +7，玩家白挨一下
  2. 忽略卡上印着的豁免              猫的敏捷豁免 +4 被算成 +2，火球 DC 差两点
  3. 预览也扣动作额度                点一下「预览」就少了一个动作
  4. 「多重攻击」也扣动作            那只是一句说明，扣了等于一张卡打两次
  5. 抗性不减半                      石像鬼对穿刺抗性形同虚设
  6. 豁免动作假装成攻击掷骰          「吐丝」会被算成一次命中，凭空多掷伤害

跑法：python tools/inject_monsters.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from inject_common import run

ROOT = Path(__file__).resolve().parents[1]
ATTACK = ROOT / "dnd5r/rules/attack.py"
COMBAT = ROOT / "dnd5r/rules/combat.py"
API = ROOT / "dnd5r/api/__init__.py"

CASES = [
    (
        "命中加值按属性推（不用卡上的数）",
        ATTACK,
        "    bonus = int(attack.attack_bonus or 0)",
        "    bonus = max(attacker.statblock.abilities.mod(\"str\"),"
        " attacker.statblock.abilities.mod(\"dex\")) + 2",
    ),
    (
        "忽略卡上印着的豁免加值",
        COMBAT,
        "    printed = dict(top.statblock.saves)",
        "    printed = {}",
    ),
    (
        "预览也扣动作额度",
        API,
        """        if apply:
            combatant.economy.pay(kind, combatant.label)""",
        """        if True:
            combatant.economy.pay(kind, combatant.label)""",
    ),
    (
        "「多重攻击」也扣动作",
        API,
        """    pays = attack.kind in ("melee", "ranged", "save")""",
        """    pays = True""",
    ),
    (
        "抗性不减半",
        ATTACK,
        "        damage //= 2",
        "        damage = int(damage)",
    ),
    (
        "豁免动作假装成攻击掷骰",
        ATTACK,
        '    if attack.kind == "save":',
        "    if False:",
    ),
]

TESTS = ["tests.unit.test_monsters"]


if __name__ == "__main__":
    sys.exit(run(CASES, TESTS, timeout=240))
