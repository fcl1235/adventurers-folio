"""骰子工具对话框。"""
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


class DiceDialog(tk.Toplevel):

    def __init__(self, master):
        super().__init__(master)
        if not master.winfo_viewable():   # 后台测试: 父窗口不可见时不弹出
            self.withdraw()
        self.title("骰子工具")
        self.geometry("420x300")
        self.transient(master)
        self.configure(bg=BG)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="表达式: 如 1d20, 2d6+3, 4d6 (4d6取高三请自行取舍)",
                  foreground=DIM).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        self.e = ttk.Entry(row, width=14)
        self.e.insert(0, "1d20")
        self.e.pack(side="left")
        ttk.Button(row, text="掷!", command=self.roll).pack(side="left", padx=6)
        for txt in ["1d20", "1d20+5", "2d6+3", "1d8", "1d4"]:
            ttk.Button(f, text=txt, width=8,
                       command=lambda t=txt: (self.e.delete(0, "end"),
                                              self.e.insert(0, t),
                                              self.roll())).pack(
                side="left", padx=3, pady=6)
        self.out = tk.Text(f, height=8, state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        self.out.pack(fill="both", expand=True)
        self.e.bind("<Return>", lambda e: self.roll())

    def roll(self):
        try:
            total, detail = roll_dice(self.e.get().strip())
        except Exception:
            messagebox.showerror("错误", "无法解析表达式", parent=self)
            return
        self.out.config(state="normal")
        self.out.insert("end", detail + "\n")
        self.out.see("end")
        self.out.config(state="disabled")
