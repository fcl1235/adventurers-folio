# -*- coding: utf-8 -*-
"""主窗口: 由四块 mixin 组合, 各自负责布局/渲染/交互/存档。"""
import tkinter as tk

from .ui_actions import AppActions
from .ui_io import AppIO
from .ui_sheet import AppSheet
from .ui_shell import AppShell


class App(AppShell, AppSheet, AppActions, AppIO, tk.Tk):
    """D&D 5.5e 人物卡主窗口"""


