"""专长页交互与底部状态栏。"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, util
from ..consts import (ABILITIES, feat_cn, feat_desc, mastery_cn, size_cn,
                      subclass_cn, tool_cn)
from ..theme import DIM, GOLD2, PURPLE, TEXT, UI_FONT
from ..util import ability_mod, mod_str


class FeatPanelMixin():
    def _on_feat_select(self, _e=None):
        sel = self.feat_list.curselection()
        if not sel:
            return
        names = self._feat_names()
        if sel[0] < len(names):
            self.feat_info.config(text=feat_desc(names[sel[0]]))

    def _status(self):
        c = self.char
        if not c:
            return
        slots = c.spell_slots()
        sl = ", ".join(
            f"{lv}环 {slots[lv] - c.spell_slots_used.get(lv, 0)}/{slots[lv]}"
            for lv in sorted(slots)) or "无施法"
        self.status.config(
            text=f"{c.name} · {c.cls()['name']} {c.level}级 · "
                 f"HP {c.hp_current}/{c.hp_max()} · AC {c.ac()} · "
                 f"熟练{mod_str(c.pb())} · 法术位: {sl}"
                 + (f" · ☠ 濒死 ✗{c.death_fail}/3 ✓{c.death_success}/3"
                    if c.is_dying else ""))
