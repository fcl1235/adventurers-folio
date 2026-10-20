"""专长增删。"""
import random
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from ... import consts, util
from ...consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                       size_cn, subclass_cn, tool_cn)
from ...dialogs import (FeatPickerDialog, MetamagicDialog, SpellbookDialog,
                        WildShapeDialog)
from ...rules import Rules
from ...theme import BG, GOLD2
from ...util import (ability_mod, mod_str, roll_dice, roll_dice_reroll,
                     spell_detail)


class FeatActionsMixin:
    def _add_feat(self):
        c = self.char
        if not c:
            return
        dlg = FeatPickerDialog(self, c, selftest=self._selftest)
        if not self._selftest:
            self.wait_window(dlg)
        if dlg.result:
            c.feats.append(dlg.result)
            if "tough" in dlg.result.lower() or "坚忍" in dlg.result:
                c.tough_feat = True
            self.refresh()

    def _del_feat(self):
        c = self.char
        if not c:
            return
        sel = self.feat_list.curselection()
        if not sel:
            return
        names = self._feat_names()
        name = names[sel[0]] if sel[0] < len(names) else None
        if name in c.feats:
            c.feats.remove(name)
        self.refresh()
