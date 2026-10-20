"""步骤 6: 法术与戏法 (非施法者自动跳过)。"""
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


class SpellStepMixin():
    def _spell_detail_text(self, s):
        return spell_detail(s)

    def _spell_quota(self, cid):
        """1 级建卡时可选的戏法数 / 1 环法术数 (2024 职业表)"""
        can = (consts.CANTRIPS_KNOWN.get(cid) or {}).get(1)
        prep = (consts.PREPARED_SPELLS.get(cid) or {}).get(1)
        fallback = consts.SPELL_COUNTS.get(cid, (0, 0))
        return (can if can is not None else fallback[0],
                prep if prep is not None else fallback[1])

    def _step_spells(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        cid = self.data["class_id"]
        cls = self.r.cls(cid)
        cast = cls.get("casting") or {}
        n_can, n_l1 = self._spell_quota(cid)
        ttk.Label(f, text="⑥ 选择法术", font=("", 13, "bold")).pack(anchor="w")
        ttk.Label(f, text=f"{cls['name']} · 施法属性 {ABILITY_CN.get(cast.get('ability'), '-')}"
                          f" · 戏法 {n_can} 个 · 1 环法术 {n_l1} 个"
                          f"（法术库共 {len(self.r.spells)} 条，建卡后可继续在本页外增删）",
                  foreground=DIM).pack(anchor="w", pady=(2, 6))

        if "spells" not in self.data:
            self.data["spells"] = {"cantrips": [], "prepared": []}
        self._sp_buckets = {}
        self._sp_labels = {}
        self._sp_lists = {}
        self._sp_combos = {}

        def make_bucket(key, title, need, level):
            lf = ttk.LabelFrame(f, text=f"{title}（{need} 个）", padding=6)
            lf.pack(fill="x", pady=3)
            head = ttk.Frame(lf)
            head.pack(fill="x")
            lbl = ttk.Label(head, text="", font=("", 10, "bold"))
            lbl.pack(side="left")
            cb = ttk.Combobox(head, state="readonly", width=30)
            cb.pack(side="right", padx=4)
            btns = ttk.Frame(head)
            btns.pack(side="right")
            lb = tk.Listbox(lf, height=4, **LISTBOX_STYLE)
            lb.pack(fill="x", pady=3)

            def avail():
                chosen = self._sp_buckets[key]
                return [s for s in self.r.class_spells(cid, level)
                        if s["id"] not in chosen]

            def refresh():
                cb["values"] = [f"{s['name']} {s['name_en']}" for s in avail()]
                lb.delete(0, "end")
                for sid in self._sp_buckets[key]:
                    s = self.r.spell(sid)
                    lb.insert("end", f"{s['name']} · {s['level']}环 · {s['cast']}")
                n = len(self._sp_buckets[key])
                lbl.config(text=f"已选 {n} / {need}",
                           foreground="#58b368" if n == need else GOLD2)

            def add(*_):
                idx = cb.current()
                if idx < 0:
                    return
                s = avail()[idx]
                if len(self._sp_buckets[key]) >= need:
                    lbl.config(text=f"已达上限 {need} 个 —— 请先移除",
                               foreground="#e05c4d")
                    return
                self._sp_buckets[key].append(s["id"])
                refresh()
                self._sp_detail_set(self._spell_detail_text(s))

            def rm(*_):
                sel = lb.curselection()
                if not sel:
                    return
                sid = self._sp_buckets[key].pop(sel[0])
                refresh()
                self._sp_detail_set(self._spell_detail_text(self.r.spell(sid)))

            def show(*_):
                sel = lb.curselection()
                if sel:
                    sid = self._sp_buckets[key][sel[0]]
                    self._sp_detail_set(
                        self._spell_detail_text(self.r.spell(sid)))

            ttk.Button(btns, text="＋ 添加", style="Mini.TButton",
                       command=add).pack(side="left", padx=2)
            ttk.Button(btns, text="－ 移除", style="Mini.TButton",
                       command=rm).pack(side="left")
            lb.bind("<<ListboxSelect>>", show)
            self._sp_buckets[key] = list(
                self.data["spells"].get("cantrips" if key == "cantrip" else "prepared", []))
            self._sp_labels[key] = lbl
            self._sp_lists[key] = lb
            self._sp_combos[key] = cb
            refresh()

        # 戏法 (0 环)
        if n_can:
            make_bucket("cantrip", "戏法 Cantrip（无限次施放）", n_can, 0)
        # 1 环
        if n_l1:
            make_bucket("lvl1", "1 环法术", n_l1, 1)

        ttk.Label(f, text="法术详情", style="H2.TLabel").pack(anchor="w",
                                                              pady=(6, 0))
        self._sp_detail = tk.Text(f, height=6, wrap="word", state="disabled",
                                  background=TXT_BG, foreground=TEXT,
                                  insertbackground=TEXT, relief="flat", width=1)
        self._sp_detail.pack(fill="both", expand=True, pady=3)

    def _sp_detail_set(self, text):
        self._sp_detail.config(state="normal")
        self._sp_detail.delete("1.0", "end")
        self._sp_detail.insert("1.0", text)
        self._sp_detail.config(state="disabled")

    def _validate_6(self):
        spells = {"cantrips": [], "prepared": []}
        for key, store in (("cantrip", "cantrips"), ("lvl1", "prepared")):
            if key in self._sp_buckets:
                spells[store] = list(self._sp_buckets[key])
        n_can, n_l1 = self._spell_quota(self.data["class_id"])
        if n_can and len(spells["cantrips"]) != n_can:
            messagebox.showwarning(
                "提示", f"戏法须恰好选择 {n_can} 个", parent=self)
            return False
        if n_l1 and len(spells["prepared"]) != n_l1:
            messagebox.showwarning(
                "提示", f"1 环法术须恰好选择 {n_l1} 个", parent=self)
            return False
        self.data["spells"] = spells
        return True
