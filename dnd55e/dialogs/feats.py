"""专长选择对话框。"""
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


class FeatPickerDialog(tk.Toplevel):
    """从专长表里选一个：通用 / 战斗风格 / 传奇恩惠。
    会按职业与等级过滤（职业限定的战斗风格、19 级传奇恩惠等）。"""

    SECTIONS = (("general", "通用专长"), ("fighting_style", "战斗风格"),
                ("epic_boon", "传奇恩惠"))

    def __init__(self, master, char, selftest=False):
        super().__init__(master)
        self.char = char
        self._selftest = selftest
        self.result = None
        self._rows = []
        self.title("选择专长")
        self.geometry("720x520")
        self.transient(master)
        self.configure(bg=BG)
        if not selftest:
            try:
                self.grab_set()
            except tk.TclError:
                pass

        ttk.Label(self, text=f"{char.name} · 选择专长",
                  font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        ttk.Label(self, foreground=DIM, wraplength=660, justify="left",
                  text="只列出当前职业与等级可选的专长；"
                       "背景给的起源专长不在这里（建卡时已确定）。").pack(
            anchor="w", padx=12, pady=(2, 6))

        body = ttk.Frame(self, padding=(12, 0))
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="可选专长", padding=6)
        left.pack(side="left", fill="both", expand=True)
        self.lst = tk.Listbox(left, width=32, exportselection=False,
                             **LISTBOX_STYLE)
        self.lst.pack(fill="both", expand=True)
        self.lst.bind("<<ListboxSelect>>", self._show)

        right = ttk.LabelFrame(body, text="效果", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.detail = tk.Text(right, wrap="word", state="disabled",
                              **TEXT_STYLE, width=1)
        self.detail.pack(fill="both", expand=True)

        for sec, label in self.SECTIONS:
            rows = []
            for name, info in (consts.GENERAL_FEATS.get(sec) or {}).items():
                cls_ok = info.get("classes")
                if cls_ok and char.class_id not in cls_ok:
                    continue
                lv = int((info.get("prereq") or {}).get("level") or 0)
                if lv and char.level < lv:
                    continue
                rows.append((sec, name, info))
            if not rows:
                continue
            self.lst.insert("end", f"— {label} —")
            self._rows.append(None)
            for sec2, name, info in rows:
                self.lst.insert("end", f"  {info.get('cn', '')} {name}")
                self._rows.append((name, info))

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="选择", command=self._take).pack(
            side="right", padx=4)
        ttk.Button(bar, text="取消", command=self._close).pack(
            side="right", padx=4)
        ttk.Button(bar, text="手动输入…", command=self._manual).pack(
            side="left", padx=4)

    def _sel(self):
        cur = self.lst.curselection()
        if not cur:
            return None
        row = self._rows[cur[0]]
        return row

    def _show(self, _e=None):
        row = self._sel()
        if not row:
            return
        name, info = row
        pq = info.get("prereq") or {}
        bits = [f"{info.get('cn', '')} {name}", ""]
        pre = []
        if pq.get("level"):
            pre.append(f"{pq['level']} 级")
        for ab, v in (pq.get("abilities") or []):
            pre.append(f"{ABILITY_CN.get(ab, ab)} {v}")
        if pq.get("feature"):
            pre.append(str(pq["feature"]))
        if pre:
            bits.append("前提：" + "、".join(pre))
        bits.append("")
        bits.append(info.get("desc", ""))
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(bits))
        self.detail.config(state="disabled")

    def _take(self):
        row = self._sel()
        if not row:
            return
        self.result = row[0]
        self._close()

    def _manual(self):
        from tkinter.simpledialog import askstring
        name = askstring("手动输入专长", "专长名称:", parent=self)
        if name and name.strip():
            self.result = name.strip()
            self._close()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
