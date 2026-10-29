#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒险者手帖 · D&D 5R (5.5e / 2024 规则) 角色卡
===================================
零第三方依赖，仅需 Python 标准库 (tkinter)。
只做 2024 修订版 (5R)：属性加值来自背景、战斗风格是专长、
力竭每级 d20 −2 / 速度 −5 尺、武器专精、法术配额查职业表。

代码按职责拆到 dnd55e/ 包里 (见 dnd55e/__init__.py 的模块说明),
规则数据都在 JSON 里按需加载, 不再堆在代码中:
  dnd55e_core_data.json          职业/种族/背景/法术位等核心规则
  dnd55e_classes_detail.json     12 职业 × 174 条特性 / 48 子职
  dnd55e_spells.json             347 个法术 (含召唤物映射)
  dnd55e/data/*.json             界面用静态表 (武器/护甲/物品/专长/文案…)

用法: python dnd55e_character_builder.py [--selftest]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk                                    # noqa: E402
from tkinter import messagebox                          # noqa: E402

from dnd55e import consts, paths                         # noqa: E402
from dnd55e.app import App                              # noqa: E402
from dnd55e.character import Character                  # noqa: E402
from dnd55e.consts import (feat_cn, feat_desc, mastery_cn,  # noqa: E402
                           size_cn, subclass_cn, tool_cn)
from dnd55e.dialogs import DiceDialog, LevelUpDialog    # noqa: E402
from dnd55e.paths import (CHAR_DIR, DATA_FILE, DETAIL_FILE,  # noqa: E402
                          LAST_PTR, SPELL_FILE)
from dnd55e.rules import Rules                          # noqa: E402
from dnd55e.util import (ability_mod, mod_str, proficiency_bonus,  # noqa: E402
                         spell_detail)
from dnd55e.wizard import Wizard                        # noqa: E402

__version__ = "2.0"


def __getattr__(name):
    """静态表 (WEAPONS/ARMORS/FIGHTING_STYLES…) 一律转发给 consts, 保持按需加载。"""
    return getattr(consts, name)


def run_selftest():
    from dnd55e.selftest import run_selftest as _run
    return _run()


def main():
    if "--selftest" in sys.argv:
        run_selftest()
        return
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
