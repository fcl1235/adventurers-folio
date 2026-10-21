# -*- coding: utf-8 -*-
"""领域数据层：只描述「是什么」，不判断「能不能」。"""

from .levels import TotalLevel, ClassLevel, as_class_level, as_total_level
from .statblock import Abilities, Statblock
from .profile import ClassEntry, Profile
from .resources import Pool, PoolKind, Refresh, ResourcePool
from .conditions import ConditionSet
from .inventory import Inventory, ItemRef, EquipSlot
from .actor import Actor, ActorKind, HpPool

__all__ = [
    "TotalLevel", "ClassLevel", "as_class_level", "as_total_level",
    "Abilities", "Statblock",
    "ClassEntry", "Profile",
    "Pool", "PoolKind", "Refresh", "ResourcePool",
    "ConditionSet",
    "Inventory", "ItemRef", "EquipSlot",
    "Actor", "ActorKind", "HpPool",
]
