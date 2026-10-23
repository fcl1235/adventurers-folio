# -*- coding: utf-8 -*-
"""P8g 反向验证：子职资源池四处注入必须都变红。

    python tools/inject_g19.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.inject_common import ROOT, run

YAML = ROOT / "plugins/dnd2024-core/subclasses/druid.circle_of_the_moon.yaml"
CONTENT = ROOT / "dnd5r/content.py"
BUILD = ROOT / "dnd5r/rules/build.py"

CASES = [
    ("池没有等级门槛（3 级就有月光步次数）", CONTENT,
     "        if int(self.level) and int(level) < int(self.level):\n            return 0",
     "        if False:\n            return 0"),
    ("去掉 floor: 1（感知 8 变成 0 次）", YAML,
     "capacity: {plus: ability.wis, floor: 1}",
     "capacity: {plus: ability.wis}"),
    ("能力不接池（cost 里没有 resource）", YAML,
     "cost: { action: bonus, resource: "
     "dnd2024.resource.druid.circle_of_the_moon.moonlight_step, label: 月光步 }",
     "cost: { action: bonus, label: 月光步 }"),
    ("建造时不建子职的池", BUILD,
     "    for resource in (sub.resources_at(level) if sub is not None else ()):",
     "    for resource in ():"),
]

if __name__ == "__main__":
    sys.exit(run(CASES, ["tests.unit.test_subclass_resources"]))
