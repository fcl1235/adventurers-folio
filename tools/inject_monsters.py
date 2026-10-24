# -*- coding: utf-8 -*-
"""P9c / P10b 反向验证：把怪物那条链故意写错十一处，测试必须变红。

每处都挑「看起来合理、其实会算错」的写法 —— 不是随便删个分号：

   1. 命中加值按「属性 + 熟练」推     巨鳄 +8 会被算成 +7，玩家白挨一下
   2. 忽略卡上印着的豁免              猫的敏捷豁免 +4 被算成 +2，火球 DC 差两点
   3. 预览也扣动作额度（怪物那条路）   点一下「预览」就少了一个动作
   4. 预览也扣动作额度（玩家武器那条） 同一句话的另一段代码，必须各验一次
   5. 「多重攻击」也扣动作            那只是一句说明，扣了等于一张卡打两次
   6. 抗性不减半                      石像鬼对穿刺抗性形同虚设
   7. 豁免动作假装成攻击掷骰          「吐丝」会被算成一次命中，凭空多掷伤害
   8. unknown 折叠成 false            没摆位就当「没有盟友」，玩家的优势被悄悄吃掉
   9. 特性模式没接进结算              报告写着 adv，骰子还是平掷一颗
  10. 报了模式丢了来源                「（优势）」不知道来自群体战术，核对不了
  11. 判「自己身边」而不是「目标身边」 狼俩互相挨着、目标在远处也白拿优势

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
MONSTERS = ROOT / "dnd5r/rules/monsters.py"

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
        "预览也扣动作额度（怪物那条路）",
        API,
        """    if pays:
        if apply:
            combatant.economy.pay(kind, combatant.label)""",
        """    if pays:
        if True:
            combatant.economy.pay(kind, combatant.label)""",
    ),
    (
        "预览也扣动作额度（玩家武器那条路）",
        API,
        """    if combatant is not None:
        if apply:
            combatant.economy.pay(kind, combatant.label)""",
        """    if combatant is not None:
        if True:
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
    (
        "unknown 折叠成 false（未摆位当没有盟友）",
        MONSTERS,
        """        if not mark.placed:
            return UNKNOWN          # 目标没摆位，5 尺无从量起""",
        """        if not mark.placed:
            return "false" """.rstrip(),
    ),
    (
        "特性模式没接进结算（永远平掷）",
        ATTACK,
        """    roll = roll_d20(roller, mode)
    total = roll.total + bonus""",
        """    roll = roll_d20(roller, "flat")
    total = roll.total + bonus""",
    ),
    (
        "报了模式丢了来源",
        ATTACK,
        '            "mode_sources": list(mode_sources),',
        '            "mode_sources": [],',
    ),
    (
        "判自己身边而不是目标身边",
        MONSTERS,
        '        return "true" if encounter.allies_near(source, mark) else "false"',
        '        return "true" if encounter.allies_near(source, source) else "false"',
    ),
]

TESTS = ["tests.unit.test_monsters", "tests.unit.test_attack"]


if __name__ == "__main__":
    sys.exit(run(CASES, TESTS, timeout=240))
