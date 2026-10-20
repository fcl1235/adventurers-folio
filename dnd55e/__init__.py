# -*- coding: utf-8 -*-
"""D&D 5.5e (2024) 人物卡 —— 包入口。

模块划分:
  paths     文件路径
  data      按需加载 data/*.json
  consts    静态数据懒代理 + 文案小工具
  rules     规则数据查询
  character 角色模型 (纯逻辑)
  util      纯函数工具
  theme     暗色主题 / 滚动容器
  wizard    建卡向导
  dialogs   升级弹窗 / 骰子工具
  ui_*      主窗口的布局 / 渲染 / 交互 / 存档
  app       主窗口组合
  selftest  自检
"""
from .app import App
from .character import Character
from .dialogs import DiceDialog, LevelUpDialog
from .rules import Rules
from .wizard import Wizard

__all__ = ["App", "Character", "DiceDialog", "LevelUpDialog", "Rules",
           "Wizard"]


