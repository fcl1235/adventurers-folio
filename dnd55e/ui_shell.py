"""窗口外壳 (菜单 / 工具栏 / 主区 / 左右栏 / 状态栏) —— 组合层。

原 661 行的单文件已按职责拆开:
    ui/shell.py    —— ShellMixin: 窗口骨架 / 菜单 / 工具栏 / 主区切换 / 中栏装配
    ui/panels.py   —— PanelsMixin: 英雄卡 / 左栏 / 右栏 / 状态栏
    ui/tabs.py     —— 中栏六个标签页 (已是函数式, 由 ShellMixin 调用)
本模块保留原名与位置, 因为 app.py 与 _layoutcheck.py 从这里取 AppShell。
"""
from .ui.panels import PanelsMixin
from .ui.shell import ShellMixin


class AppShell(ShellMixin, PanelsMixin):
    """原来的方法已按模块拆到其它文件, 这里只做组合。"""
