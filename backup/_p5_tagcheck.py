"""逐个 tag 回验证: 每个阶段的代码在它自己的提交上是否真的全绿。

《重构方案.md》的铁律是「每阶段结束跑一次 7 步自检 + 打 tag」。本脚本用
`git worktree` 把每个 tag 检出到临时目录, 在那里跑自检并记录结果, 从而
证明「每个 tag 都是绿的」而不是「只有最新代码是绿的」。

用法: python backup/_p5_tagcheck.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

STEPS = [
    ("_data_sync.py", ["--check"], "全部数据已在本地"),
    ("dnd55e_character_builder.py", ["--selftest"], "SELFTEST OK"),
    ("_flowtest.py", [], "FLOWTEST ALL PASS"),
    ("_resourcecheck.py", [], "RESOURCECHECK OK"),
    ("_layoutcheck.py", [], "LAYOUT OK"),
    ("_hintcheck.py", [], "HINTCHECK OK"),
    ("_namecheck.py", [], "OK"),
]

# 这个 tag 之前还没有的脚本 (新加的自检)
INTRODUCED = {
    "_hintcheck.py": "P4a",
}


def run(cwd, args, env):
    p = subprocess.run([PY] + args, cwd=cwd, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def main():
    tags = subprocess.run(["git", "tag", "-l"], cwd=ROOT,
                          stdout=subprocess.PIPE).stdout.decode().split()
    order = [t for t in ("baseline", "P1", "P2", "P3", "P4a", "P5")
             if t in tags]
    # P4b/P4c/P5 是 P4 的后续拆分, 也一起验
    for extra in ("P4b", "P4c", "P5"):
        if extra in tags and extra not in order:
            order.append(extra)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONHASHSEED"] = "0"
    env["DND_NO_PAUSE"] = "1"

    tmp = tempfile.mkdtemp(prefix="tagcheck_")
    rows, bad = [], 0
    try:
        for tag in order:
            wt = os.path.join(tmp, tag)
            r = subprocess.run(["git", "worktree", "add", "--detach", wt, tag],
                               cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
            if r.returncode != 0:
                print("worktree 失败 (%s): %s"
                      % (tag, r.stdout.decode("utf-8", "replace")[:200]))
                bad += 1
                continue
            results = []
            for script, args, want in STEPS:
                if not os.path.exists(os.path.join(wt, script)):
                    results.append((script, "-", "脚本尚未存在"))
                    continue
                rc, out = run(wt, [script] + args, env)
                ok = rc == 0 and want in out
                if not ok:
                    bad += 1
                results.append((script, "OK" if ok else "FAIL",
                                out.strip().splitlines()[-1][:52]
                                if out.strip() else ""))
            rows.append((tag, results))
            subprocess.run(["git", "worktree", "remove", "--force", wt],
                           cwd=ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    w = max(len(s.split(".")[0]) for s, _a, _w in STEPS) + 1
    print("阶段".ljust(9) + "".join(s.replace(".py", "").ljust(w + 3)
                                    for s, _a, _w in STEPS))
    for tag, results in rows:
        line = tag.ljust(9)
        for _s, st, _msg in results:
            line += st.ljust(w + 3)
        print(line)
    print("-" * 60)
    for tag, results in rows:
        for script, st, msg in results:
            if st == "FAIL":
                print("  %s / %s : %s" % (tag, script, msg))
    print("=" * 60)
    if bad:
        print("TAGCHECK FAILED — %d 处失败" % bad)
        return 1
    print("TAGCHECK OK — %d 个 tag 各自全绿" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
