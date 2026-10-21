"""法师法术书对话框: 抄录 / 准备 / 仪式施法。"""
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


class SpellbookDialog(tk.Toplevel):
    """法师法术书 (2024 PHB): 左边书内、右边可抄录。
    抄录 2 小时/环、50 gp/环; 升级免费 2 个 (book_pending)。"""

    def __init__(self, master, char, selftest=False):
        super().__init__(master)
        self.char = char
        self._selftest = selftest
        self._left_ids = []
        self._right_ids = []
        self.title("法术书")
        self.transient(master)
        self.configure(bg=BG)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        ttk.Label(self, text=f"{char.name} · 法师法术书",
                  font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        self.head = ttk.Label(self, text="", foreground=GOLD2)
        self.head.pack(anchor="w", padx=12)
        ttk.Label(self, wraplength=740, justify="left", foreground=DIM,
                  text="长休后要从书里准备法术（书外的不能准备）；"
                       "抄录任意法师法术 2 小时/环、50 gp/环；"
                       "书里的仪式法术可以不准备直接施放"
                       "（额外 10 分钟，不耗环位）。").pack(
            anchor="w", padx=12, pady=(2, 6))

        body = ttk.Frame(self, padding=(12, 0))
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="书内", padding=6)
        left.pack(side="left", fill="both", expand=True)
        self.left_lbl = ttk.Label(left, text="", style="Dim.TLabel")
        self.left_lbl.pack(anchor="w")
        self.left_list = tk.Listbox(left, height=14, exportselection=False,
                                    **LISTBOX_STYLE)
        self.left_list.pack(fill="both", expand=True)
        self.left_list.bind("<<ListboxSelect>>", self._show_left)

        ttk.Frame(body, width=8).pack(side="left")

        right = ttk.LabelFrame(body, text="可抄录", padding=6)
        right.pack(side="left", fill="both", expand=True)
        self.right_lbl = ttk.Label(right, text="", style="Dim.TLabel")
        self.right_lbl.pack(anchor="w")
        self.right_list = tk.Listbox(right, height=14, exportselection=False,
                                     **LISTBOX_STYLE)
        self.right_list.pack(fill="both", expand=True)
        self.right_list.bind("<<ListboxSelect>>", self._show_right)
        self.cost_lbl = ttk.Label(right, text="", foreground=GOLD2,
                                  wraplength=330, justify="left")
        self.cost_lbl.pack(anchor="w", pady=(4, 0))

        self.info = ttk.Label(self, text="", foreground=GOLD2, wraplength=760,
                              justify="left")
        self.info.pack(anchor="w", padx=12, pady=(6, 0))

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x", side="bottom")
        self.free_btn = ttk.Button(bar, text="免费抄录", style="Mini.TButton",
                                   command=self._do_free)
        self.free_btn.pack(side="left")
        ttk.Button(bar, text="花钱抄录", style="Mini.TButton",
                   command=self._do_pay).pack(side="left", padx=6)
        ttk.Button(bar, text="移出法术书", style="Mini.TButton",
                   command=self._do_remove).pack(side="left")
        ttk.Button(bar, text="关闭", command=self.destroy).pack(side="right")
        self._refresh()
        fit(self, 800, 580)
        center_on(self, master)

    # ---- 列表 ----

    def _refresh(self):
        c = self.char
        prev_l, prev_r = self._sel_left(), self._sel_right()
        prepared = set(c.spells.get("prepared") or [])
        wiz = {s["id"]: s for s in c.r.class_spells("wizard")}
        self._left_ids = [s["id"] for s in c.book_spells()]
        self._right_ids = [sid for sid, s in
                           sorted(wiz.items(), key=lambda kv: (kv[1]["level"],
                                                               kv[1]["name"]))
                           if s["level"] >= 1
                           and sid not in (c.spellbook or [])]
        self.left_list.delete(0, "end")
        for sid in self._left_ids:
            s = c.r.spell(sid)
            marks = ""
            if sid in prepared:
                marks += " ◉已准备"
            if s["ritual"]:
                marks += " ［仪式］"
            self.left_list.insert("end", f"[{s['level']}环] {s['name']}{marks}")
        self.right_list.delete(0, "end")
        for sid in self._right_ids:
            s = c.r.spell(sid)
            self.right_list.insert("end", f"[{s['level']}环] {s['name']}"
                                          + ("  ［仪式］" if s["ritual"] else ""))
        self.head.config(
            text=f"书内 {len(self._left_ids)} 个 · 可免费抄录 "
                 f"{c.book_pending} 个 · 当前可抄最高 {c.book_max_level()} 环")
        self.left_lbl.config(text=f"共 {len(self._left_ids)} 个"
                                  f"（长休后从这里准备）")
        self.right_lbl.config(text=f"共 {len(self._right_ids)} 个法师法术尚未抄录")
        self.free_btn.config(text=f"免费抄录（剩 {c.book_pending} 次）")
        # 抄录/移除后保持原来的选中项, 方便连续操作
        if prev_l in self._left_ids:
            self.left_list.selection_set(self._left_ids.index(prev_l))
        if prev_r in self._right_ids:
            self.right_list.selection_set(self._right_ids.index(prev_r))
            self._show_right()
        elif not self.right_list.curselection():
            self.cost_lbl.config(text="选中右侧法术查看抄录花费")

    def _sel_left(self):
        s = self.left_list.curselection()
        if not s or s[0] >= len(self._left_ids):
            return None
        return self._left_ids[s[0]]

    def _sel_right(self):
        s = self.right_list.curselection()
        if not s or s[0] >= len(self._right_ids):
            return None
        return self._right_ids[s[0]]

    def _show_left(self, _e=None):
        sid = self._sel_left()
        if not sid:
            return
        s = self.char.r.spell(sid)
        self.cost_lbl.config(text=f"{s['name']} 已在书中 · "
                                  f"可准备 / 仪式施放")

    def _show_right(self, _e=None):
        sid = self._sel_right()
        if not sid:
            return
        c = self.char
        top = c.book_max_level()
        s = c.r.spell(sid)
        txt = (f"抄录：{c.copy_cost(sid)} gp / {c.copy_hours(sid)} 小时")
        if s["level"] > top:
            txt += f"\n⚠ 超出当前可抄环级（最高 {top} 环）"
        self.cost_lbl.config(text=txt)

    # ---- 动作 ----

    def _say(self, ok, msg):
        self.info.config(text=msg, foreground=(GOLD2 if ok else RED))
        if not ok and not self._selftest:
            messagebox.showwarning("法术书", msg, parent=self)

    def _after_change(self):
        self._refresh()
        hook = getattr(self.master, "refresh", None)
        if callable(hook):
            hook()

    def _do_free(self):
        sid = self._sel_right()
        if not sid:
            self._say(False, "请先在右侧选中要抄录的法术")
            return False
        ok, msg = self.char.book_add(sid, free=True)
        self._say(ok, msg)
        if ok:
            self._after_change()
        return ok

    def _do_pay(self):
        sid = self._sel_right()
        if not sid:
            self._say(False, "请先在右侧选中要抄录的法术")
            return False
        c = self.char
        cost, hours = c.copy_cost(sid), c.copy_hours(sid)
        ok, msg = c.book_add(sid)
        if ok:
            msg += f"（请自行扣除 {cost} gp）"
        self._say(ok, msg)
        if ok:
            self._after_change()
        return ok

    def _do_remove(self):
        sid = self._sel_left()
        if not sid:
            self._say(False, "请先在左侧选中要移出的法术")
            return False
        ok, msg = self.char.book_remove(sid)
        self._say(ok, msg)
        if ok:
            self._after_change()
        return ok
