# -*- coding: utf-8 -*-
"""P9b 反向验证：把攻击管线的五处关键判断改错，测试必须真红。

每条注入都对着一个「写错了会不会被发现」的担心：

1. 重击门槛从 `>=` 改成 `>` —— 掷出 20 不算重击，伤害少一倍的骰子；
2. 抗性不减半 —— 抗性形同虚设，而且「先加总再减半」也会被这条抓出来；
3. 标记消费去掉 —— 「下一次攻击优势」变成永久优势；
4. 预览也消费标记 —— 看一眼就丢了优势；
5. 额外伤害默认全加 —— 替玩家做了 "you can" 的选择。

跑法：`python tools/inject_attack.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.inject_common import run  # noqa: E402

ATTACK = ROOT / "dnd5r/rules/attack.py"
API = ROOT / "dnd5r/api/__init__.py"

CASES = [
    (
        "重击门槛写成 >（20 不再重击）",
        ATTACK,
        "    if roll.total >= crit_min:",
        "    if roll.total > crit_min:",
    ),
    (
        "抗性不减半",
        ATTACK,
        """    elif kind == "resistance":
        damage //= 2""",
        """    elif kind == "resistance":
        damage = damage""",
    ),
    (
        "优势标记不消费（变成永久优势）",
        ATTACK,
        "            marks_spent = consume_marks(attacker, query)",
        "            marks_spent = []",
    ),
    (
        "预览也消费标记",
        ATTACK,
        """    if apply:
        if hit or outcome == "miss":""",
        """    if True:
        if hit or outcome == "miss":""",
    ),
    (
        "额外伤害默认全加（替玩家决定）",
        ATTACK,
        """    if not extras:
        return []""",
        """    if not extras:
        return [row for row in options if row["available"]]""",
    ),
    (
        "借机攻击不扣反应",
        API,
        """    if apply:
        combatant.economy.pay(ActionType.REACTION, combatant.label)""",
        """    if apply:
        pass""",
    ),
    (
        "借机攻击预览也扣反应",
        API,
        """    if apply:
        combatant.economy.pay(ActionType.REACTION, combatant.label)""",
        """    if True:
        combatant.economy.pay(ActionType.REACTION, combatant.label)""",
    ),
]

# 撤掉过一条「把反应检查改成 if False」的注入：`ActionEconomy.pay` 自己就
# 会拒绝 reaction<=0，删掉显式检查行为完全一样，测试照旧通过（GREEN 是对的）。
# 显式检查留着只是为了错误信息更好读（「这一轮的反应已经用掉了」），
# 它不是唯一的护栏 —— 所以这里注入它证明不了任何事。

TESTS = ["tests.unit.test_attack"]

if __name__ == "__main__":
    sys.exit(run(CASES, TESTS))
