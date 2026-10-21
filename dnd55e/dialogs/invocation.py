# -*- coding: utf-8 -*-
"""邪术师·魔能祈唤选择对话框。

2024 规则: 1 级起每级按表递增已知数 (1/3/5/6/7/8/9/10),
每条祈唤有等级前提; 本对话框在同一处完成勾选与数量校验。
result: None=取消, list=保存后的 id 列表
"""
import tkinter as tk
from tkinter import ttk, messagebox

from .. import consts
from ..theme import BG, DIM, GOLD2, RED, ScrollFrame

from ._fit import center_on, fit


class InvocationDialog(tk.Toplevel):
    """勾选魔能祈唤 (有数量上限与等级前提)"""

    def __init__(self, master, char, selftest=False):
        super().__init__(master)
        self.char = char
        self._selftest = selftest
        self.result = None
        self.title("魔能祈唤")
        self.transient(master)
        self.configure(bg=BG)
        if selftest:
            self.withdraw()          # 测试里绝不显示窗口
        else:
            try:
                self.grab_set()
            except tk.TclError:
                pass

        cap = char.invocation_cap()
        ttk.Label(self, text=f"{char.name} · 魔能祈唤（邪术师 {char.level} 级）",
                  font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        ttk.Label(self, text=f"最多 {cap} 个 · 只有等级到要求的祈唤才会出现；"
                             "带「手动」的要自己按说明操作。",
                  style="Dim.TLabel").pack(anchor="w", padx=12)

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="保存", style="Gold.TButton",
                   command=self._ok).pack(side="right", padx=4)
        ttk.Button(bar, text="取消", command=self._cancel).pack(side="right")
        self.info = ttk.Label(self, text="", foreground=GOLD2)
        self.info.pack(side="bottom", anchor="w", padx=12)

        sf = ScrollFrame(self, height=380)
        sf.pack(fill="both", expand=True, padx=8, pady=(6, 0))
        self.sf = sf
        body = sf.body

        self.vars = {}
        for inv in char.invocation_options():
            iid = inv["id"]
            v = tk.BooleanVar(value=char.has_invocation(iid))
            self.vars[iid] = v
            lv = int(inv.get("level", 1))
            tag = "手动" if not (inv.get("effects") or {}) else "已接入数值"
            ttk.Checkbutton(
                body, text=f"{inv['name']}　(需 {lv} 级 · {tag})",
                variable=v, command=self._sync,
            ).pack(anchor="w", pady=(4, 0))
            ttk.Label(body, text=inv.get("desc", ""), foreground=DIM,
                      wraplength=620, justify="left").pack(anchor="w", padx=(22, 0))

        self._sync()
        fit(self, 700, 560)
        center_on(self, master)

    def _picked(self):
        return [i for i, v in self.vars.items() if v.get()]

    def _sync(self):
        ids = self._picked()
        cap = self.char.invocation_cap()
        if len(ids) > cap:
            self.info.config(text=f"已选 {len(ids)}/{cap}：超出上限，请先取消几个",
                             foreground=RED)
        else:
            self.info.config(text=f"已选 {len(ids)}/{cap}", foreground=GOLD2)

    def _ok(self):
        ids = self._picked()
        cap = self.char.invocation_cap()
        if len(ids) > cap:
            messagebox.showwarning(
                "超出上限", f"最多只能有 {cap} 个魔能祈唤。", parent=self)
            return
        self.result = ids
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
