# -*- coding: utf-8 -*-
"""角色模型分片: core/items.py (由 character.py 物理拆分, P1 纯搬运)。"""
from .. import consts


class ItemsMixin:
    """ItemsMixin"""

    def attunement_cap(self):
        """同调上限: 3 件 (2024 通用规则; 盗贼的「使用魔法装置」只放宽
        使用物品的条件, 并不增加同调数)"""
        return 3

    def attuned_items(self):
        """当前需要同调的物品 (精灵斗篷/精灵靴等不需要同调)"""
        return [i for i in self.items
                if consts.ITEMS_BY_ID.get(i, {}).get("attune", True)]
