"""召唤物 stat block 详情卡（只读）。

用于法术页「查看召唤物」与法术书里的入口。展示的是召唤物本身的数值，
不修改角色 —— 召唤物的 AC / HP 是随施法环级变化的公式，由玩家按实际环级读。
"""
import tkinter as tk
from tkinter import ttk

from .. import summoning
from ..theme import BG, DIM, GOLD2, TEXT_STYLE


class SummonCardDialog(tk.Toplevel):
    """显示一个或多个召唤物 stat block。

    char 参数可为 None（纯查阅，不需要角色）。
    blocks: summoning.statblocks(spell) 的返回值，或单个 statblock 条目。
    result: 恒为 None（纯查阅对话框）
    """

    def __init__(self, master, spell=None, blocks=None, selftest=False,
                 title=None):
        super().__init__(master)
        self._selftest = selftest
        self.result = None
        self._blocks = list(blocks or [])
        if spell is not None and not self._blocks:
            self._blocks = summoning.statblocks(spell)
        self._spell = spell or {}
        self.title(title or "召唤物")
        self.geometry("720x580")
        self.transient(master)
        self.configure(bg=BG)
        if not selftest:
            try:
                self.grab_set()
            except tk.TclError:
                pass

        head = self._spell.get("name") or "召唤物"
        ttk.Label(self, text=f"{head} · 召唤物详情",
                  font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        self.count_lbl = ttk.Label(self, foreground=GOLD2,
                                   text=self._summary_line())
        self.count_lbl.pack(anchor="w", padx=12)
        ttk.Label(self, wraplength=680, justify="left", foreground=DIM,
                  text="AC 与 HP 是随施法环级变化的公式，按你实际使用的环级读取；"
                       "本卡只查阅，不改动角色数值。").pack(
            anchor="w", padx=12, pady=(2, 6))

        body = ttk.Frame(self, padding=(12, 0))
        body.pack(fill="both", expand=True)
        self._side = None
        if len(self._blocks) > 1:
            left = ttk.LabelFrame(body, text="形态", padding=6)
            left.pack(side="left", fill="y")
            self.lst = tk.Listbox(left, width=22, height=16,
                                  exportselection=False)
            self.lst.pack(fill="both", expand=True)
            self.lst.bind("<<ListboxSelect>>", self._show)
            for b in self._blocks:
                self.lst.insert("end", b.get("_option") or b.get("variant")
                                or b.get("name_cn") or b.get("name"))
            self._side = left

        right = ttk.LabelFrame(body, text="Stat Block", padding=6)
        right.pack(side="left", fill="both", expand=True,
                   padx=(8, 0) if self._side else 0)
        self.text = tk.Text(right, wrap="word", state="disabled",
                            width=1, **TEXT_STYLE)
        self.text.pack(fill="both", expand=True)

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="关闭", command=self._close).pack(side="right",
                                                              padx=4)

        if self._blocks:
            if self._side:
                self.lst.selection_set(0)
            self._show()

    def _summary_line(self):
        n = len(self._blocks)
        if not n:
            return "该法术没有登记召唤物数据"
        return f"共 {n} 种形态"

    def _show(self, _e=None):
        sb = self._blocks[0] if self._blocks else None
        if self._side:
            cur = self.lst.curselection()
            if cur:
                sb = self._blocks[cur[0]]
        txt = summoning.card_text(sb) if sb else "该法术没有登记召唤物数据。"
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", txt)
        self.text.config(state="disabled")

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
