# -*- coding: utf-8 -*-
"""找出各模块里「引用了但没定义/没导入」的全局名 (symtable 近似检查)

递归扫描 dnd55e/ 下所有 .py (含 core/ classes/ spellcasting/ ui/ 等子包)。
"""
import builtins
import symtable
import sys
import os

BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__",
                                 "__path__", "__spec__", "__loader__"}

def check(path):
    src = open(path, encoding="utf-8").read()
    top = symtable.symtable(src, path, "exec")
    # 模块级已定义的名字
    defined = {s.get_name() for s in top.get_symbols()
               if s.is_assigned() or s.is_imported() or s.is_namespace()}
    # 星号导入 -> 放行 (entry 用)
    star = "import *" in src
    missing = {}

    def walk(tab):
        for sym in tab.get_symbols():
            name = sym.get_name()
            if sym.is_global() and not sym.is_assigned():
                if name not in defined and name not in BUILTINS:
                    missing.setdefault(name, set()).add(tab.get_name())
        for ch in tab.get_children():
            walk(ch)

    walk(top)
    return missing, star

def sources():
    for root, dirs, files in os.walk("dnd55e"):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in sorted(files):
            if f.endswith(".py"):
                yield os.path.join(root, f)


bad = 0
count = 0
for p in sorted(sources()):
    count += 1
    miss, star = check(p)
    if miss and not star:
        bad += 1
        print(f"{p}: {', '.join(sorted(miss))}")
print("OK (%d 个模块)" % count if not bad else f"{bad} 个模块有未定义名")
sys.exit(1 if bad else 0)
