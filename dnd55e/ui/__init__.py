"""界面构件子包 (只放"搭控件"的代码, 不放事件处理)。

    tabs.py    —— 中间栏六个标签页
    panels.py  —— 顶部英雄卡 / 左右栏 / 状态栏
    class_tab.py —— 职业页内容渲染

事件处理仍在 dnd55e/ui_actions.py 等 mixin 里, 因为它们要访问 self.char。

本包 __init__ 故意留空: 各模块用 `from .ui import tabs` 直取子模块,
避免 `dnd55e.ui` ↔ `dnd55e.ui_shell` 的循环导入。
"""
