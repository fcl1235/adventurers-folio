"""2024 超魔法选择对话框。"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, util
from ..consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                      size_cn, subclass_cn, tool_cn)
from ..theme import (BG, DIM, GOLD2, LISTBOX_STYLE, RED, TEXT, TEXT_STYLE,
                     TXT_BG)
from ..util import (ab_from_display, ability_mod, mod_str,
                    proficiency_bonus, roll_dice)

from ._fit import center_on, fit


class MetamagicDialog(tk.Toplevel):
    """2024 超魔法: 施法时选 1 个 (强化/探秘可与其他叠加)。
    result: None=取消施法, []=不应用超魔法, [id, ...]=应用"""

    def __init__(self, master, char, spell):
        super().__init__(master)
        self.char = char
        self.spell = spell
        self.result = None
        self.title("超魔法")
        self.transient(master)
        self.configure(bg=BG)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        ttk.Label(self, text=f"施放: {spell['name']}（{spell['level']} 环）",
                  font=("", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        cap = char.metamagic_per_spell()
        ttk.Label(self, text=f"术法点 {char.sorcery_left()}/{char.sorcery_max()}"
                             f"　每道法术最多 {cap} 个（强化/探秘可叠加）"
                             + ("　奥术神化: 其中 1 个免费"
                                if char.mm_free() else ""),
                  style="Dim.TLabel").pack(anchor="w", padx=12)

        self.vars = {}
        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)
        for mid in char.metamagic_known():
            nm, cost, desc, _stack = consts.METAMAGIC[mid]
            v = tk.BooleanVar()
            self.vars[mid] = v
            ttk.Checkbutton(f, text=f"{nm}（{cost} 点）", variable=v,
                            command=self._sync).pack(anchor="w")
            ttk.Label(f, text="   " + desc, foreground=DIM,
                      wraplength=410, justify="left").pack(anchor="w")

        self.info = ttk.Label(self, text="", foreground=GOLD2)
        self.info.pack(anchor="w", padx=12)
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=8, padx=12)
        ttk.Button(bar, text="取消", command=self._cancel).pack(side="right")
        ttk.Button(bar, text="施放", style="Gold.TButton",
                   command=self._ok).pack(side="right", padx=6)
        ttk.Button(bar, text="不用超魔法",
                   command=self._none).pack(side="left")
        self._sync()
        fit(self, 480, 400)
        center_on(self, master)

    def _picked(self):
        return [m for m, v in self.vars.items() if v.get()]

    def _sync(self):
        ids = self._picked()
        if not ids:
            self.info.config(text="未选择超魔法", foreground=GOLD2)
            return
        ok, why, cost = self.char.mm_validate(ids)
        self.info.config(text=(f"合计 {cost} 点术法点" if ok else why),
                         foreground=(GOLD2 if ok else RED))

    def _ok(self):
        ids = self._picked()
        ok, why, _cost = self.char.mm_validate(ids)
        if not ok:
            messagebox.showwarning("不可用", why, parent=self)
            return
        self.result = ids
        self.destroy()

    def _none(self):
        self.result = []
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
