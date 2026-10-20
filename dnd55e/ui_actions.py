"""界面动作 (用户操作 -> 角色数据)。

原本 1097 行的单文件已按主题拆到 dnd55e/ui/actions/ 下, 这里只做组合:
    dice.py       掷骰与攻击/伤害
    stats.py      HP / 属性 / 技能 / 状态 / 濒死 / 环位
    hints.py      悬停提示文案
    feats.py      专长的增删
    gear.py       武器 / 副手 / 战斗风格 / 物品 / 武器专精
    classopts.py  1 级职阶 / 荒野变形 / 超魔法 / 先天魔法 / 法师自选
    spells.py     法术页的全部操作
    misc.py       语言与备注
"""
from .ui.actions.classopts import ClassOptsMixin
from .ui.actions.dice import DiceMixin
from .ui.actions.feats import FeatActionsMixin
from .ui.actions.gear import GearMixin
from .ui.actions.hints import HintsMixin
from .ui.actions.misc import MiscMixin
from .ui.actions.spells import SpellActionsMixin
from .ui.actions.stats import StatsMixin


class AppActions(DiceMixin, StatsMixin, HintsMixin, FeatActionsMixin,
                 GearMixin, ClassOptsMixin, SpellActionsMixin, MiscMixin):
    """原来的方法已按模块拆到 dnd55e/ui/actions/ 下, 这里只做组合。"""
