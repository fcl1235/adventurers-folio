"""笔记页: 语言与备注。"""
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


class MiscMixin:
    def _lang_changed(self):
        if self.char:
            self.char.languages = self.lang_entry.get()

    def _notes_changed(self):
        if self.char:
            self.char.equipment = self.eq_text.get("1.0", "end").strip()
            self.char.notes = self.note_text.get("1.0", "end").strip()
