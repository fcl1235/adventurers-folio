"""六步建卡向导 (模态) —— 组合层。

原 1253 行的单文件已按步骤拆开:
    wizard_steps/core.py     —— 向导骨架: 初始化 / 步骤切换 / 校验派发 / 目标角色组装
    wizard_steps/class_ui.py —— 步骤 0: 职业选择 + 1 级职阶
    wizard_steps/bg_ui.py    —— 步骤 1: 背景 (含熟练去重)
    wizard_steps/species.py  —— 步骤 2: 种族 / 血统 / 传承专长
    wizard_steps/abilities.py—— 步骤 3: 属性 (点 buy / 标准数组 / 4d6 掷)
    wizard_steps/skills.py   —— 步骤 4: 技能 (职业 + 背景)
    wizard_steps/mastery.py  —— 步骤 5: 武器专精
    wizard_steps/spells.py   —— 步骤 6: 法术与戏法
    wizard_steps/summary.py  —— 步骤 7: 汇总

**步骤序号是硬耦合**: validate_step() 用 getattr(self, f"_validate_{self.step}")
动态取校验函数, 新增步骤必须同步加上 `_validate_N`。
本模块保留原名与位置, 因为 app.py 与 _layoutcheck.py 从这里取 Wizard。
"""
import tkinter as tk

from .wizard_steps.abilities import AbilitiesMixin
from .wizard_steps.bg_ui import BackgroundMixin
from .wizard_steps.class_ui import ClassStepMixin
from .wizard_steps.core import WizardCore
from .wizard_steps.mastery import MasteryMixin
from .wizard_steps.skills import SkillsMixin
from .wizard_steps.species import SpeciesMixin
from .wizard_steps.spells import SpellStepMixin
from .wizard_steps.summary import SummaryMixin


class Wizard(WizardCore, ClassStepMixin, BackgroundMixin, SpeciesMixin,
             AbilitiesMixin, SkillsMixin, MasteryMixin, SpellStepMixin,
             SummaryMixin, tk.Toplevel):
    """原来的方法已按模块拆到其它文件, 这里只做组合。"""
