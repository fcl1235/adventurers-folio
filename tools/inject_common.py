# -*- coding: utf-8 -*-
"""反向验证的公共壳：注入 → 跑测试 → 还原，一条都不许留。

两条踩过的坑，写进这个壳里：

1. **基线要一次性读**。以前逐例读「当前文件」当基线，同一文件有两处注入时，
   第二例的基线里含着第一例的注入 —— 后面的「红」是在被污染的代码上跑出来的。
2. **跑到一半被杀要能自愈**。超时或 Ctrl-C 会跳过还原，文件里就留着注入，
   下一轮会拿它当基线。所以备份落盘（`.workbuddy/tmp/inject-backup/` 镜像相对路径），
   每次启动先把上一次的残局还原。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / ".workbuddy/tmp/inject-backup"


def _heal() -> None:
    """上一次没跑完留下的注入，先还原掉。"""
    if not BACKUP.exists():
        return
    healed = 0
    for saved in BACKUP.rglob("*"):
        if not saved.is_file():
            continue
        target = ROOT / saved.relative_to(BACKUP)
        if not target.exists() or target.read_bytes() != saved.read_bytes():
            target.write_bytes(saved.read_bytes())
            healed += 1
    if healed:
        print("[HEAL] 上一次的注入已还原 %d 个文件" % healed)


def _save(paths) -> dict[Path, bytes]:
    """把基线写进备份目录，同时返回内存副本。"""
    baseline = {}
    for path in paths:
        data = path.read_bytes()
        baseline[path] = data
        saved = BACKUP / path.relative_to(ROOT)
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(data)
    return baseline


def _clear() -> None:
    if not BACKUP.exists():
        return
    for saved in sorted(BACKUP.rglob("*"), reverse=True):
        saved.unlink() if saved.is_file() else saved.rmdir()
    BACKUP.rmdir()


def run(cases, tests, timeout: int = 180) -> int:
    """`cases` 是 (说明, 文件, 原文, 替换)。全红返回 0，有一处没红返回非零。"""
    _heal()
    baseline = _save({case[1] for case in cases})
    failed = 0
    try:
        for label, path, old, new in cases:
            text = baseline[path].decode("utf-8")
            if old not in text:
                print("[SKIP] 找不到注入点：%s" % label)
                failed += 1
                continue
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            try:
                proc = subprocess.run([sys.executable, "-m", "unittest", *tests],
                                      cwd=str(ROOT), capture_output=True,
                                      text=True, timeout=timeout)
                ok, detail = proc.returncode == 0, proc.stderr
            except subprocess.TimeoutExpired:
                ok, detail = False, "TIMEOUT（测试自己卡住了，也算没通过）"
            finally:
                for target, data in baseline.items():
                    target.write_bytes(data)
            if ok:
                print("[GREEN] %s —— 注入没被抓到！" % label)
                failed += 1
            else:
                first = next((line for line in detail.splitlines()
                              if line.startswith(("FAILED", "TIMEOUT"))), "")
                red = sum(1 for line in detail.splitlines()
                          if line.startswith(("FAIL:", "ERROR:")))
                print("[RED  ] %s —— %s" % (label, first or "测试失败"))
                if red:
                    print("         变红的用例 %d 条" % red)
    finally:
        for target, data in baseline.items():
            target.write_bytes(data)
        _clear()
    print("\n反向验证完成：%d 处注入，%d 处没红" % (len(cases), failed))
    return 1 if failed else 0
