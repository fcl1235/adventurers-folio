"""步骤 4: 技能选择 (职业 + 背景)。"""
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


class SkillsMixin():
    def _step_skills(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        cls = self.r.cls(self.data["class_id"])
        bg = self.r.bg(self.data["background_id"])
        self._bg_skills = set(bg["skills"])
        ttk.Label(f, text="⑤ 选择技能熟练", font=("", 13, "bold")).pack(anchor="w")

        auto = [self.r.skill_by_id[s]["name"] for s in bg["skills"]]
        ttk.Label(f, text=f"① 背景自动获得 {len(auto)} 项: {'、'.join(auto)}",
                  foreground="#58b368").pack(anchor="w", pady=2)

        need = cls["skill_count"]
        pool_ids = ([s["id"] for s in self.r.d["skills"]]
                    if cls["skill_options"] == "*any*" else cls["skill_options"])
        head = ttk.Frame(f)
        head.pack(anchor="w", fill="x")
        ttk.Label(head, text=f"② 职业任选 {need} 项 (多选, 达上限自动拦截):",
                  foreground=DIM).pack(side="left")
        self._skill_count_lbl = ttk.Label(head, text="", font=("", 10, "bold"))
        self._skill_count_lbl.pack(side="left", padx=10)

        self.skill_vars = {}
        grid = ttk.Frame(f)
        grid.pack(anchor="w", pady=4)
        pool_ids = [sid for sid in pool_ids if sid not in bg["skills"]]
        for i, sid in enumerate(pool_ids):
            sk = self.r.skill_by_id[sid]
            v = tk.BooleanVar(value=sid in self.data["skill_prof"])
            self.skill_vars[sid] = v
            cb = ttk.Checkbutton(grid, text=f"{sk['name']} ({ABILITY_CN[sk['ability']]})",
                                 variable=v,
                                 command=lambda s2=sid: self._on_class_skill(s2))
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=10, pady=2)
            cb.bind("<Enter>", lambda e, s2=sid: self._hint_skill(s2))

        # ---- 种族赠送技能 (额外 +1, 与职业技能独立) ----
        self.sp_skill_vars = {}
        spf = ttk.Frame(f)
        spf.pack(anchor="w", pady=(6, 0))
        sp_id = self.data["species_id"]
        sp_name = self.r.sp(sp_id)["name"]
        n_sp = consts.SPECIES_SKILL_BONUS.get(sp_id, 0)
        self._sp_need = n_sp
        self._sp_note = ""
        if n_sp:
            flavor = {"human": "「多才多艺」", "elf": "「敏锐感官」"}.get(sp_id, "")
            scope = ("任意技能" if sp_id == "human" else "洞察/察觉/生存")
            self._sp_note = (f"③ {sp_name} {flavor}: 在职业技能之外, "
                             f"额外获得 {n_sp} 项熟练（{scope}, "
                             f"{'可多选' if n_sp > 1 else '单选'}, 不与已有熟练重复）")
        if self._sp_note:
            ttk.Label(spf, text=self._sp_note, foreground=PURPLE).pack(anchor="w")
            opts = ([s["id"] for s in self.r.d["skills"]]
                    if sp_id == "human"
                    else ["insight", "perception", "survival"])
            opts = [s for s in opts if s not in self._bg_skills]
            spg = ttk.Frame(spf)          # 独立内层框, 避免 pack/grid 混用
            spg.pack(anchor="w")
            cols = 4                      # 人类 18 项按 4 列排, 避免横向溢出窗口
            for i, sid in enumerate(opts):
                sk = self.r.skill_by_id[sid]
                v = tk.BooleanVar(value=False)
                self.sp_skill_vars[sid] = v
                cbs = ttk.Checkbutton(spg, text=sk["name"], variable=v,
                                      command=lambda s2=sid: self._on_sp_skill(s2))
                cbs.grid(row=i // cols, column=i % cols, sticky="w",
                         padx=(0, 10), pady=1)
                cbs.bind("<Enter>", lambda e, s2=sid: self._hint_skill(s2))

        # ---- 起源专长「多面手 Skilled」: 额外 3 项技能 (不占职业配额) ----
        self.bonus_vars = []
        feats = [self.data.get("human_feat"),
                 bg.get("origin_feat") if bg else None]
        self._skilled_n = 3 if any(f and "Skilled" in str(f) for f in feats) else 0
        if self._skilled_n:
            skf = ttk.LabelFrame(
                f, text="④ 多面手 Skilled：任选 3 项技能熟练"
                        "（不占职业配额；若想选工具请记在备注）", padding=4)
            skf.pack(anchor="w", fill="x", pady=(6, 0))
            row = ttk.Frame(skf)
            row.pack(anchor="w")
            names = ["（空）"] + [s["name"] for s in self.r.d["skills"]]
            prev = list(self.data.get("bonus_skills") or [])
            for i in range(self._skilled_n):
                cb = ttk.Combobox(row, state="readonly", width=14, values=names)
                if i < len(prev) and prev[i] in self.r.skill_by_id:
                    cb.set(self.r.skill_by_id[prev[i]]["name"])
                else:
                    cb.set("（空）")
                cb.pack(side="left", padx=3)
                self.bonus_vars.append(cb)

        self._skill_need = need
        self._skill_summary = ttk.Label(f, text="", font=("", 10, "bold"))
        self._skill_summary.pack(anchor="w", pady=(6, 0))
        self._skill_hint = HintText(f, text="把鼠标停在技能上可看它管什么检定",
                                    fg=DIM, height=2, wraplength=680)
        self._skill_hint.pack(anchor="w", pady=(4, 0))
        self._update_skill_count()

    def _hint_skill(self, sid):
        sk = self.r.skill_by_id[sid]
        self._skill_hint.config(
            text=f"{sk['name']} ({ABILITY_CN[sk['ability']]}) —— "
                 f"{consts.SKILL_DESC.get(sid, '')}",
            foreground=GOLD2)

    def _update_skill_count(self):
        n = sum(1 for v in self.skill_vars.values() if v.get())
        ok = (n == self._skill_need)
        self._skill_count_lbl.config(
            text=f"已选 {n} / {self._skill_need}",
            foreground="#58b368" if ok else GOLD2)
        # 熟练汇总: 背景 + 职业 + 种族
        sp_n = sum(1 for v in self.sp_skill_vars.values() if v.get())
        bg_n = len(self._bg_skills)
        need_sp = getattr(self, "_sp_need", 0)
        extra = (f" · 种族 {sp_n}/{need_sp}" if self.sp_skill_vars else "")
        bonus_n = sum(1 for cb in getattr(self, "bonus_vars", [])
                      if cb.get() not in ("", "（空）"))
        if getattr(self, "_skilled_n", 0):
            extra += f" · 多面手 {bonus_n}/{self._skilled_n}"
        total = bg_n + n + sp_n + bonus_n
        self._skill_summary.config(
            text=f"熟练总数: 背景 {bg_n} + 职业 {n}/{self._skill_need}{extra}"
                 f" = {total} 项",
            foreground="#58b368" if ok else TEXT)

    def _on_class_skill(self, sid):
        """职业技能多选实时控制: 超出上限自动回退本次勾选"""
        v = self.skill_vars[sid]
        if v.get():
            # 种族已选的同一技能 → 自动让位给职业技能
            if sid in self.sp_skill_vars and self.sp_skill_vars[sid].get():
                self.sp_skill_vars[sid].set(False)
            n = sum(1 for x in self.skill_vars.values() if x.get())
            if n > self._skill_need:
                v.set(False)
                self._skill_count_lbl.config(
                    text=f"已达上限 {self._skill_need} 项 —— 请先取消一项再选",
                    foreground="#e05c4d")
                return
        self._update_skill_count()

    def _on_sp_skill(self, sid):
        """种族赠送技能: 最多选 _sp_need 项; 与职业已选重复则立即回退"""
        v = self.sp_skill_vars[sid]
        if v.get():
            if sid in self.skill_vars and self.skill_vars[sid].get():
                v.set(False)
                self._skill_hint.config(
                    text=f"{self.r.skill_by_id[sid]['name']} 已由「职业技能」获得, "
                         f"不能重复吃熟练 —— 请换一项", foreground="#e05c4d")
                self._update_skill_count()
                return
            n = sum(1 for x in self.sp_skill_vars.values() if x.get())
            need_sp = getattr(self, "_sp_need", 1)
            if n > need_sp:
                v.set(False)
                self._skill_hint.config(
                    text=f"种族技能最多 {need_sp} 项 —— 请先取消一项",
                    foreground="#e05c4d")
        self._update_skill_count()

    def _validate_4(self):
        chosen = [sid for sid, v in self.skill_vars.items() if v.get()]
        if len(chosen) != self._skill_need:
            messagebox.showwarning(
                "提示", f"职业技能须恰好选择 {self._skill_need} 项 (已选 {len(chosen)})",
                parent=self)
            return False
        sp = [sid for sid, v in self.sp_skill_vars.items() if v.get()]
        need_sp = getattr(self, "_sp_need", 1)
        if need_sp and len(sp) != need_sp:
            messagebox.showwarning(
                "提示", f"种族额外技能须恰好选 {need_sp} 项 (已选 {len(sp)})",
                parent=self)
            return False
        # 去重: 职业 / 种族 / 背景 三者不可重复
        dup = (set(chosen) & set(sp)) | (set(chosen) & self._bg_skills) \
            | (set(sp) & self._bg_skills)
        if dup:
            names = "、".join(self.r.skill_by_id[s]["name"] for s in dup)
            messagebox.showwarning(
                "提示", f"技能熟练不可重复: {names}\n请换一项", parent=self)
            return False
        # 起源专长「多面手 Skilled」: 3 项额外技能
        name2id = {s["name"]: s["id"] for s in self.r.d["skills"]}
        sk_pick = [name2id[cb.get()] for cb in getattr(self, "bonus_vars", [])
                   if cb.get() in name2id]
        need_sk = getattr(self, "_skilled_n", 0)
        if need_sk and len(sk_pick) != need_sk:
            messagebox.showwarning(
                "提示", f"多面手须选 {need_sk} 项技能 (已选 {len(sk_pick)})",
                parent=self)
            return False
        if len(set(sk_pick)) != len(sk_pick):
            messagebox.showwarning("提示", "多面手的 3 项技能不能重复",
                                   parent=self)
            return False
        dup2 = set(sk_pick) & (set(chosen) | set(sp) | self._bg_skills)
        if dup2:
            names = "、".join(self.r.skill_by_id[s]["name"] for s in dup2)
            messagebox.showwarning(
                "提示", f"多面手与已有熟练重复: {names}\n请换一项", parent=self)
            return False
        prof = set(chosen) | set(sp) | self._bg_skills | set(sk_pick)
        self.data["skill_prof"] = prof
        self.data["bonus_skills"] = set(sp) | set(sk_pick)
        return True
