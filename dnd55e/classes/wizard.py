# -*- coding: utf-8 -*-
"""法师：法术书、法术精通、招牌法术、仪式施法。"""
from . import registry
from .base import ClassModule


@registry.register("wizard")
class Wizard(ClassModule):
    name_cn = "法师"

    def owns_spellbook(self, ch):
        return True

    def mastery_cap(self, ch):
        """18 级法术精通: 1 环 1 个 + 2 环 1 个"""
        return 2 if ch.level >= 18 else 0

    def signature_cap(self, ch):
        """20 级招牌法术: 2 个 3 环"""
        return 2 if ch.level >= 20 else 0

    def post_state(self, ch, d):
        """旧存档没有法术书 → 用已准备好的法师法术补齐。"""
        ch.book_auto_fill()
        return True
