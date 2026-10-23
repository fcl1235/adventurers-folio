# -*- coding: utf-8 -*-
"""P8h 反向验证：法术位四处注入必须都变红。

    python tools/inject_slots.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inject_common import ROOT, run

COMBAT = ROOT / "dnd5r/rules/combat.py"
CASTING = ROOT / "dnd5r/rules/spellcasting.py"

CASES = [
    ("apply 时不扣法术位", COMBAT,
     "    if apply:\n        pool = spend_slot(caster, int(slot), owner)",
     "    if False:\n        pool = spend_slot(caster, int(slot), owner)"),
    ("不看指定环级，永远扣第一个池", CASTING,
     "    for level, pool in pools:\n        if level == index:",
     "    for level, pool in pools:\n        if level == pools[0][0]:"),
    ("「或更高」从最高的挑", CASTING,
     "    for level, pool in slot_pools(actor, class_id):\n"
     "        if level >= int(min_level) and pool.available > 0:",
     "    for level, pool in reversed(slot_pools(actor, class_id)):\n"
     "        if level >= int(min_level) and pool.available > 0:"),
    ("位用光时悄悄放行", CASTING,
     '            if not pool.can_spend(1):\n'
     '                raise IllegalAction("没有可用的 %d 环法术位（已用光）" % index)',
     '            if not pool.can_spend(1):\n'
     '                return pool'),
]

if __name__ == "__main__":
    sys.exit(run(CASES, ["tests.unit.test_slots"]))
