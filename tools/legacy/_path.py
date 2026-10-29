# -*- coding: utf-8 -*-
"""项目根定位（tools/legacy/ 下的脚本共用）

为什么需要它
------------
这些脚本原先放在项目根目录，一律用 `os.path.dirname(__file__)` 当项目根。
P6 重构时它们被归档到 `tools/legacy/`，那行代码就指向了 `tools/legacy/`：

  * `import dnd55e` 失败（ModuleNotFoundError）
  * `open(os.path.join(DIR, "data/raw/..."))` 指向不存在的路径

所以基路径改为「向上找标记文件」，脚本以后再搬家也不会坏。

导入副作用
----------
把项目根插进 `sys.path`，这样 `import dnd55e` 在任何工作目录下都能用。
（一次性开发脚本，不用管模块化洁癖；写明在这里，免得后来者以为是巧合。）
"""
import os
import sys

#: 只有项目根目录才会有这个文件
MARKER = "dnd55e_character_builder.py"


def find_root(start=None):
    """从 start（默认本文件所在目录）向上查找项目根。

    找不到就抛错，而不是退回当前目录 —— 静默用错目录会让脚本
    在错误的位置读写数据，比直接报错危险得多。
    """
    here = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    probe = here
    for _ in range(6):
        if os.path.exists(os.path.join(probe, MARKER)):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:                      # 已到盘符根
            break
        probe = parent
    raise RuntimeError(
        "找不到项目根：从 %s 起向上 6 层都没有 %s" % (here, MARKER))


PROJECT_ROOT = find_root()

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
