# -*- coding: utf-8 -*-
"""G19 反向验证：四处注入必须都变红，否则测试等于没测。

每个注入都从**开头一次性读下的基线**还原 —— 逐例读当前文件会把上一例的
注入当成基线，后面的例就成了假绿（P8e 踩过这个坑）。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
YAML = ROOT / "plugins/dnd2024-core/subclasses/druid.circle_of_the_moon.yaml"
CONTENT = ROOT / "dnd5r/content.py"
BUILD = ROOT / "dnd5r/rules/build.py"
PY = sys.executable

CASES = [
    ("池没有等级门槛（3 级就有月光步次数）", CONTENT,
     "        if int(self.level) and int(level) < int(self.level):\n            return 0",
     "        if False:\n            return 0"),
    ("去掉 floor: 1（感知 8 变成 0 次）", YAML,
     "capacity: {plus: ability.wis, floor: 1}",
     "capacity: {plus: ability.wis}"),
    ("能力不接池（cost 里没有 resource）", YAML,
     "cost: { action: bonus, resource: dnd2024.resource.druid.circle_of_the_moon.moonlight_step, label: 月光步 }",
     "cost: { action: bonus, label: 月光步 }"),
    ("建造时不建子职的池", BUILD,
     "    for resource in (sub.resources_at(level) if sub is not None else ()):",
     "    for resource in ():"),
]

baseline = {path: path.read_bytes() for path, _, _, _ in
            [(case[1], case[1], case[2], case[3]) for case in CASES]}


def restore():
    for path, data in baseline.items():
        path.write_bytes(data)


failed = 0
for label, path, old, new in CASES:
    text = baseline[path].decode("utf-8")
    if old not in text:
        print("[SKIP] 找不到注入点：%s" % label)
        failed += 1
        continue
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    proc = subprocess.run(
        [PY, "-m", "unittest", "tests.unit.test_subclass_resources"],
        cwd=str(ROOT), capture_output=True, text=True)
    restore()
    tail = [line for line in proc.stderr.splitlines() if line.startswith("FAILED")]
    if proc.returncode == 0:
        print("[GREEN] %s —— 注入没被抓到！" % label)
        failed += 1
    else:
        print("[RED  ] %s —— %s" % (label, tail[0] if tail else "返回码非零"))

restore()
print("\n反向验证完成：%d 处注入，%d 处没红" % (len(CASES), failed))
sys.exit(1 if failed else 0)
