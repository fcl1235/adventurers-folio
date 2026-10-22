# -*- coding: utf-8 -*-
"""重构自检：一条命令跑完全部守护，任何一项红就退出非零。

  1. 单元测试（tests/unit）
  2. 分层与硬约束（C1 C2 C3 C4 C6 C8）
  3. 插件与内容校验（清单、id、双语 C7、术语）
  4. 黄金对账（新旧内核 AC/HP/攻击/豁免）
  5. 桌面布局（reqsize 口径，窗口全程不显示）
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

STEPS = [
    ("单元测试", [PY, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"]),
    ("分层约束", [PY, "tools/lint_layers.py"]),
    ("插件内容", [PY, "-m", "tools.plugins_cli", "check", "--root", "plugins", "--terms"]),
    ("黄金对账", [PY, "tools/golden.py"]),
    ("桌面布局", [PY, "tools/uicheck.py"]),
]


def main() -> int:
    failed = []
    for index, (label, cmd) in enumerate(STEPS, 1):
        print("\n[%d/%d] %s" % (index, len(STEPS), label))
        proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            failed.append(label)
    print("\n" + "=" * 48)
    if failed:
        print("SELFCHECK FAILED：%s" % "、".join(failed))
        return 1
    print("SELFCHECK OK（%d 步全绿）" % len(STEPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
