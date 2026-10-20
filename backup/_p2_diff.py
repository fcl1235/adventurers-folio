# -*- coding: utf-8 -*-
"""逐键对比两份快照, 只报告差异。"""
import json
import sys


def walk(a, b, path, out):
    if type(a) is not type(b):
        out.append("%s: 类型 %s != %s" % (path, type(a).__name__, type(b).__name__))
        return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append("%s.%s: 新增 %r" % (path, k, b[k]))
            elif k not in b:
                out.append("%s.%s: 丢失 %r" % (path, k, a[k]))
            else:
                walk(a[k], b[k], "%s.%s" % (path, k), out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append("%s: 长度 %d != %d" % (path, len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, "%s[%d]" % (path, i), out)
    else:
        if a != b:
            out.append("%s: %r != %r" % (path, a, b))


def main():
    a = json.load(open(sys.argv[1], encoding="utf-8"))
    b = json.load(open(sys.argv[2], encoding="utf-8"))
    out = []
    walk(a, b, "", out)
    if not out:
        print("快照完全一致 (%d 组)" % len(a))
        return 0
    print("差异 %d 处:" % len(out))
    for line in out[:60]:
        print("  " + line)
    return 1


if __name__ == "__main__":
    sys.exit(main())
