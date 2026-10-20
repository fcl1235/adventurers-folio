"""各类弹出的对话框 (原来 820 行的单文件已按对话框拆开)。

    dialogs/metamagic.py  —— MetamagicDialog  2024 超魔法选择
    dialogs/spellbook.py  —— SpellbookDialog  法师法术书 (抄录/准备/仪式)
    dialogs/feats.py      —— FeatPickerDialog 专长选择
    dialogs/wildshape.py  —— WildShapeDialog  荒野变形形态选择
    dialogs/levelup.py    —— LevelUpDialog    升级 (ASI / 子职 / 传奇恩惠)
    dialogs/dice.py       —— DiceDialog       骰子工具

本包保留 `dnd55e.dialogs` 这个名字与全部类名, 外部导入方式不变。
"""

from .metamagic import MetamagicDialog  # noqa: F401,E402
from .spellbook import SpellbookDialog  # noqa: F401,E402
from .feats import FeatPickerDialog  # noqa: F401,E402
from .wildshape import WildShapeDialog  # noqa: F401,E402
from .levelup import LevelUpDialog  # noqa: F401,E402
from .dice import DiceDialog  # noqa: F401,E402

__all__ = [
    "MetamagicDialog",
    "SpellbookDialog",
    "FeatPickerDialog",
    "WildShapeDialog",
    "LevelUpDialog",
    "DiceDialog",
]
