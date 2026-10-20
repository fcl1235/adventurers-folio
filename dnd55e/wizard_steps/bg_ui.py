"""步骤 1: 背景选择与技能熟练去重。"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, util
from ..character import Character
from ..consts import (ABILITIES, ABILITY_CN, ARMOR_PROF_CN, CAST_MODE_CN,
                      CAST_TYPE_CN, WEAPON_PROF_CN, feat_cn, feat_desc,
                      mastery_cn, size_cn, subclass_cn, tool_cn)
from ..rules import Rules
from ..theme import (BG, DIM, GOLD2, LISTBOX_STYLE, PURPLE, TEXT, TXT_BG,
                     HintText)
from ..util import (ab_from_display, ability_mod, mod_str,
                    proficiency_bonus, roll_4d6kh3, spell_detail)


class BackgroundMixin():
    def _step_background(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="② 选择背景 (决定属性加值 / 起源专长 / 技能 / 工具)",
                  font=("", 13, "bold")).pack(anchor="w")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="背景:").pack(side="left")
        self.cb_bg = ttk.Combobox(row, state="readonly", width=24,
                                  values=[b["name"] for b in self.r.d["backgrounds"]])
        if self.data["background_id"]:
            self.cb_bg.set(self.r.bg(self.data["background_id"])["name"])
        self.cb_bg.pack(side="left", padx=6)
        self.cb_bg.bind("<<ComboboxSelected>>", lambda e: self._render_bg_ui())

        self.bg_info = ttk.Label(f, text="", justify="left", wraplength=640)
        self.bg_info.pack(anchor="w", pady=4)
        self.bg_frame = ttk.LabelFrame(f, text="属性加值分配 (候选三项)")
        self.bg_frame.pack(fill="x", pady=6)
        self._render_bg_ui()

    def _render_bg_ui(self):
        for w in self.bg_frame.winfo_children():
            w.destroy()
        name = self.cb_bg.get()
        bg = None
        for b in self.r.d["backgrounds"]:
            if b["name"] == name:
                bg = b
                self.data["background_id"] = b["id"]
        if not bg:
            self.bg_info.config(text="请选择背景")
            return
        skills = "、".join(self.r.skill_by_id[s]["name"] for s in bg["skills"])
        feat_raw = bg["origin_feat"]
        self.bg_info.config(text=(
            f"{bg['name']}  |  专长: {feat_cn(feat_raw)}  |  "
            f"技能: {skills}  |  工具: {tool_cn(bg['tool'])}\n"
            f"专长效果: {feat_desc(feat_raw)}\n"
            f"装备包或 50gp；种族不再提供属性加值。"))

        self.bg_mode = tk.StringVar(value="2+1")
        r1 = ttk.Frame(self.bg_frame)
        r1.pack(anchor="w", fill="x", pady=2)
        ttk.Radiobutton(r1, text="+2 加一项, +1 加另一项", variable=self.bg_mode,
                        value="2+1", command=self._render_bg_picks).pack(side="left")
        ttk.Radiobutton(r1, text="三项各 +1", variable=self.bg_mode,
                        value="111", command=self._render_bg_picks).pack(side="left", padx=12)

        self.bg_picks = ttk.Frame(self.bg_frame)
        self.bg_picks.pack(anchor="w", pady=4)
        self._bg_abs = bg["abilities"]
        self._render_bg_picks()

    def _render_bg_picks(self):
        for w in self.bg_picks.winfo_children():
            w.destroy()
        names = [f"{ABILITY_CN[a]}({a})" for a in self._bg_abs]
        if self.bg_mode.get() == "2+1":
            ttk.Label(self.bg_picks, text="+2 →").pack(side="left")
            self.bg_p2 = ttk.Combobox(self.bg_picks, state="readonly", width=13,
                                      values=names)
            self.bg_p2.pack(side="left", padx=4)
            self.bg_p2.bind("<<ComboboxSelected>>",
                            lambda e: self._bg_dedup("p2"))
            ttk.Label(self.bg_picks, text="+1 →").pack(side="left", padx=(12, 0))
            self.bg_p1 = ttk.Combobox(self.bg_picks, state="readonly", width=13,
                                      values=names)
            self.bg_p1.pack(side="left", padx=4)
            self.bg_p1.bind("<<ComboboxSelected>>",
                            lambda e: self._bg_dedup("p1"))
        else:
            self.bg_o = []
            for i in range(3):
                ttk.Label(self.bg_picks, text=f"+1 →").pack(side="left",
                                                            padx=(0 if i == 0 else 12, 0))
                cb = ttk.Combobox(self.bg_picks, state="readonly", width=13,
                                  values=names)
                cb.pack(side="left", padx=4)
                cb.bind("<<ComboboxSelected>>",
                        lambda e, box=cb: self._bg_dedup(box))
                self.bg_o.append(cb)

    def _bg_dedup(self, source):
        """同一加值不可重复选同一属性: 实时清掉冲突的另一项"""
        if self.bg_mode.get() == "2+1":
            if self.bg_p2.get() and self.bg_p1.get() \
                    and self.bg_p2.get() == self.bg_p1.get():
                (self.bg_p1 if source == "p2" else self.bg_p2).set("")
        else:
            cur = source.get()
            if cur:
                for cb in self.bg_o:
                    if cb is not source and cb.get() == cur:
                        cb.set("")

    def _validate_1(self):
        if not self.data["background_id"]:
            messagebox.showwarning("提示", "请选择一个背景", parent=self)
            return False
        mode = self.bg_mode.get()
        if mode == "2+1":
            a, b = self.bg_p2.get(), self.bg_p1.get()
            if not a or not b:
                messagebox.showwarning("提示", "请完成 +2 / +1 分配", parent=self)
                return False
            if a == b:
                messagebox.showwarning("提示", "+2 和 +1 必须分配给不同属性", parent=self)
                return False
            ab2, ab1 = ab_from_display(a), ab_from_display(b)
            if ab2 not in self._bg_abs or ab1 not in self._bg_abs:
                messagebox.showwarning("提示", "只能从背景候选的三项属性中选择",
                                       parent=self)
                return False
            self.data["bg_bonus"] = {"mode": "2+1", "plus2": ab2, "plus1": ab1}
        else:
            vals = [cb.get() for cb in self.bg_o]
            if any(not v for v in vals) or len(set(vals)) != 3:
                messagebox.showwarning("提示", "三项 +1 必须各不相同", parent=self)
                return False
            abs_ = [ab_from_display(v) for v in vals]
            if any(x not in self._bg_abs for x in abs_):
                messagebox.showwarning("提示", "只能从背景候选的三项属性中选择",
                                       parent=self)
                return False
            self.data["bg_bonus"] = {"mode": "111", "ones": abs_}
        return True
