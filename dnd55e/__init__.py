# -*- coding: utf-8 -*-
"""D&D 5R (5.5e / 2024) 人物卡 —— 包入口。

本项目只做 5R (2024 修订版): 属性加值来自背景、战斗风格是专长、
力竭每级 d20 −2 / 速度 −5 尺、武器专精、法术配额查职业表。
代码里残留的 `5.5e` / `dnd55e` 命名指的都是同一个 5R。

分层 (下层不依赖上层):

  ── 基础层 ──────────────────────────────────────────────
  paths        文件路径
  data         按需加载 data/*.json (唯一读盘的地方)
  consts       静态数据懒代理 + 文案小工具
  util         纯函数工具 (骰子 / 调整值)
  rules        规则数据查询
  theme        暗色主题 / HintText 提示框 / ScrollFrame

  ── 领域层 (零 UI) ──────────────────────────────────────
  character    角色模型门面 (组合下面 15 个 mixin)
  core/        base / derived / checks / features / resources / serialize
               combat/(weapons, offhand) / items
  classes/     一职业一文件 + 注册表: 想加新职业只要新建一个文件并 @register
  spellcasting/ slots / prepare / fixed / metamagic / font / spellbook
               types (full/half/third/pact) / levels (0-9 环规则)
  wildshape    荒野变形形态筛选 (纯函数)

  ── 表现层 ──────────────────────────────────────────────
  ui_shell     门面 -> ui/shell + ui/panels + ui/tabs (六个标签页)
  ui_sheet     门面 -> ui/refresh + ui/classtab + ui/featpanel
  ui_actions   门面 -> ui/actions/ 8 个 mixin (骰子/数值/提示/专长/装备/
                      职业选项/法术/杂项)
  ui_io        存档 / 升级 / 长休短休
  dialogs/     六个对话框各一文件 + 门面
  wizard_steps/ 建卡向导八步各一文件; wizard.py 是门面

  ── 组合 ────────────────────────────────────────────────
  app          主窗口 = AppShell + AppSheet + AppActions + AppIO + tk.Tk
  selftest     自检
"""
from .app import App
from .character import Character
from .dialogs import DiceDialog, LevelUpDialog
from .rules import Rules
from .wizard import Wizard

__all__ = ["App", "Character", "DiceDialog", "LevelUpDialog", "Rules",
           "Wizard"]


