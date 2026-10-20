# -*- coding: utf-8 -*-
"""角色数据模型门面。真正的实现分散在 core/ 与 spellcasting/ 的 mixin 里。

直接 import Character 使用即可, 方法名与拆分前完全一致。
"""
from .core.base import BaseMixin
from .core.checks import ChecksMixin
from .core.combat.offhand import OffhandMixin
from .core.combat.weapons import WeaponsMixin
from .core.derived import DerivedMixin
from .core.features import FeaturesMixin
from .core.items import ItemsMixin
from .core.resources import ResourcesMixin
from .core.serialize import SerializeMixin
from .spellcasting.fixed import FixedMixin
from .spellcasting.font import FontMixin
from .spellcasting.metamagic import MetamagicMixin
from .spellcasting.prepare import PrepareMixin
from .spellcasting.slots import SlotsMixin
from .spellcasting.spellbook import SpellbookMixin


class Character(BaseMixin, DerivedMixin, ChecksMixin, WeaponsMixin,
                OffhandMixin, ItemsMixin, FeaturesMixin,
                ResourcesMixin, SerializeMixin, SlotsMixin,
                PrepareMixin, FixedMixin, MetamagicMixin, FontMixin,
                SpellbookMixin):
    """角色数据模型 (mixin 组装)。"""
