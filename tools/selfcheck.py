# -*- coding: utf-8 -*-
"""重构自检：一条命令跑完全部守护，任何一项红就退出非零。

  1. 单元测试（tests/unit）
  2. 分层与硬约束（C1 C2 C3 C4 C6 C8）
  3. 插件与内容校验（清单、id、双语 C7、术语）
  4. 黄金对账（新旧内核 AC/HP/攻击/豁免）
  5. 桌面布局（reqsize 口径，窗口全程不显示）
  6. 布局 · 英文（同样的检查跑一遍英文界面）
  7. 界面文案（中文有没有全接进 T()）
  8. 接口层文案（规则算出来的句子有没有接进 tr()）
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
    # 英文不是中文的等长替身：同一套检查要在英文界面再跑一遍，
    # 否则「中文塞得下」会被当成「布局没问题」。
    ("布局·英文", [PY, "tools/uicheck.py", "--lang", "en"]),
    ("界面文案", [PY, "tools/i18n_audit.py"]),
    ("接口层文案", [PY, "tools/i18n_audit.py", "--api"]),
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
