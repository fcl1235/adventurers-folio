# -*- coding: utf-8 -*-
"""P10a 反向验证：把「兽形天然武器」这条链故意写错七处，测试必须变红。

七处都挑「看起来合理、其实会算错」的写法：

  1. **动作表不认形态**           变熊以后又回到「你手上没有天然武器」
  2. **形态不带印着的豁免**        猫的敏捷豁免 +4 退回 +2，火球 DC 差两点
  3. **命中加值按属性推**          猫的抓挠 +4 被算成 -2
  4. **解析形态时丢掉动作**        `actions` 全空，界面只列得出一个空清单
  5. **界面按 kind 分支**          变形中的玩家仍被当成「还在挥长剑」
  6. **形态数据手抄漂移**          巨鳄 HP 回到 2014 的 19（数据保真测试的意义）
  7. **生成器没重跑**              改生成器源码不改产物 —— 由 `--check` 抓

第 6 条注入的是数据文件本身，不是代码：`DataFidelityTest` 存在的理由就是
「两边各存一份、迟早各说各话」，它必须能抓到这种漂移。

跑法：python tools/inject_forms.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from inject_common import run

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "dnd5r/api/__init__.py"
MORPH = ROOT / "dnd5r/rules/morph.py"
CONTENT = ROOT / "dnd5r/content.py"
ATTACK = ROOT / "dnd5r/rules/attack.py"
PAGE = ROOT / "apps/desktop/pages_encounter.py"
BEASTS = ROOT / "plugins/dnd2024-core/bestiary/beasts.yaml"
GEN = ROOT / "tools/gen_beasts.py"

CASES = [
    (
        "动作表不认形态（变熊后没有天然武器）",
        API,
        "    if top.kind is ActorKind.FORM:",
        "    if False:",
    ),
    (
        "形态不带印着的豁免加值",
        MORPH,
        "        saves=dict(form.saves or {}),",
        "        saves={},",
    ),
    (
        "命中加值按属性推（不用卡上的数）",
        ATTACK,
        "    bonus = int(attack.attack_bonus or 0)",
        '    bonus = attacker.top().statblock.abilities.mod("str") + 2',
    ),
    (
        "解析形态时丢掉动作",
        CONTENT,
        '        actions=rows("actions"),',
        "        actions=(),",
    ),
    (
        "界面按 kind 分支（变形中仍列武器）",
        PAGE,
        '            if kind == "pc" and not form.get("morphed"):',
        '            if kind == "pc":',
    ),
    (
        "形态数据漂回 2014（巨鳄 HP 19）",
        BEASTS,
        "  hp: 13\n  cr: 0.5\n  abilities: { str: 15, dex: 10, con: 13",
        "  hp: 19\n  cr: 0.5\n  abilities: { str: 15, dex: 10, con: 13",
    ),
    (
        "生成器没重跑（改表不改产物）",
        GEN,
        '    ("crocodile", "crocodile"),',
        '    ("crocodile", "black_bear"),',
    ),
]

TESTS = ["tests.unit.test_form_attacks"]


if __name__ == "__main__":
    sys.exit(run(CASES, TESTS, timeout=300))
