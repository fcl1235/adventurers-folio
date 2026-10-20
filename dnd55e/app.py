# -*- coding: utf-8 -*-
"""主窗口: 由四块 mixin 组合, 各自负责布局/渲染/交互/存档。

四块各自再按区域拆到子包, 这里只做组合:

    AppShell   ← ui/shell.py    窗口骨架 / 菜单 / 工具栏 / 主区切换
               ← ui/panels.py   英雄卡 / 左右栏 / 状态栏
               (中栏六页由 ui/tabs.py 建)

    AppSheet   ← ui/refresh.py    整卡刷新
               ← ui/classtab.py   职业页
               ← ui/featpanel.py  专长页 / 状态栏

    AppActions ← ui/actions/{dice,stats,hints,feats,gear,classopts,spells,misc}.py

    AppIO      ← ui_io.py        存档 / 升级 / 休息
"""
import tkinter as tk

from .ui_actions import AppActions
from .ui_io import AppIO
from .ui_sheet import AppSheet
from .ui_shell import AppShell


class App(AppShell, AppSheet, AppActions, AppIO, tk.Tk):
    """D&D 5.5e 人物卡主窗口"""


