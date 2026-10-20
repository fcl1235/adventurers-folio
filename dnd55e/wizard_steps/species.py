"""步骤 2: 种族 / 血统 / 传承专长。"""
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


class SpeciesMixin():
    def _step_species(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="③ 选择种族 Species (体型/速度/特性, 无属性加值)",
                  font=("", 13, "bold")).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="种族:").pack(side="left")
        self.cb_sp = ttk.Combobox(row, state="readonly", width=24,
                                  values=[s["name"] for s in self.r.d["species"]])
        if self.data["species_id"]:
            self.cb_sp.set(self.r.sp(self.data["species_id"])["name"])
        self.cb_sp.pack(side="left", padx=6)
        self.cb_sp.bind("<<ComboboxSelected>>", lambda e: self._show_species())
        self.txt_sp = tk.Text(f, height=13, wrap="word", state="disabled",
                              background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        self.txt_sp.pack(fill="both", expand=True)
        # 种族血脉 (精灵/侏儒/提夫林): 影响自带法术
        self.lineage_frame = ttk.LabelFrame(f, text="血脉 / 传承 (决定种族自带法术)",
                                            padding=6)
        self.cb_lineage = ttk.Combobox(self.lineage_frame, state="readonly",
                                       width=26)
        self.cb_lineage.pack(anchor="w")
        self.cb_lineage.bind("<<ComboboxSelected>>",
                             lambda e: self._show_lineage())
        self.lbl_lineage = HintText(self.lineage_frame, text="", fg=DIM,
                                    height=3, wraplength=640)
        self.lbl_lineage.pack(anchor="w", pady=(4, 0))
        # 人类「全能」: 自选 1 个 Origin 专长
        self.human_frame = ttk.LabelFrame(f, text="人类 · 全能 (自选 1 个起源专长)",
                                          padding=6)
        self.cb_hfeat = ttk.Combobox(self.human_frame, state="readonly",
                                     width=30, values=sorted(consts.FEAT_INFO))
        self.cb_hfeat.pack(anchor="w")
        self.cb_hfeat.bind("<<ComboboxSelected>>",
                           lambda e: self._show_hfeat_desc())
        if self.data.get("human_feat"):
            self.cb_hfeat.set(self.data["human_feat"])
        self.lbl_hfeat = HintText(self.human_frame, text="", fg=DIM,
                                  height=3, wraplength=640)
        self.lbl_hfeat.pack(anchor="w", pady=(4, 0))
        self._show_species()

    def _show_hfeat_desc(self):
        raw = self.cb_hfeat.get()
        self.data["human_feat"] = raw or None
        self.lbl_hfeat.config(text=feat_desc(raw) if raw else "")

    def _show_species(self):
        name = self.cb_sp.get()
        found = False
        for s in self.r.d["species"]:
            if s["name"] == name:
                found = True
                self.data["species_id"] = s["id"]
                size = size_cn(s["size"])
                text = (f"{s['name']}   体型: {size}   速度: {s['speed']} 尺\n"
                        f"{'-' * 40}\n" + "\n• ".join(["特性:"] + s["traits"]))
                self.txt_sp.config(state="normal")
                self.txt_sp.delete("1.0", "end")
                self.txt_sp.insert("1.0", text)
                self.txt_sp.config(state="disabled")
                # 人类才显示「全能」专长选择
                if s["id"] == "human":
                    self.human_frame.pack(fill="x", pady=6)
                    self._show_hfeat_desc()
                else:
                    self.human_frame.pack_forget()
                    self.data["human_feat"] = None
                # 血脉分支
                ent = consts.SPECIES_SPELLS.get(s["id"])
                if isinstance(ent, dict):
                    if s["id"] == "human":       # 人类帧已 pack, 血脉排在它上面
                        self.lineage_frame.pack(fill="x", pady=6,
                                                before=self.human_frame)
                    else:
                        self.lineage_frame.pack(fill="x", pady=6)
                    keys = [k for k in ent]
                    labels = [consts.LINEAGE_CN.get(k, k) for k in keys]
                    self._lineage_keys = keys
                    self.cb_lineage["values"] = labels
                    cur = self.data.get("lineage")
                    if cur in keys:
                        self.cb_lineage.set(consts.LINEAGE_CN.get(cur, cur))
                    else:
                        self.cb_lineage.set(labels[0])
                        self.data["lineage"] = keys[0]
                    self._show_lineage()
                else:
                    self.lineage_frame.pack_forget()
                    self.data["lineage"] = None
                break
        if not found:
            self.human_frame.pack_forget()
            self.txt_sp.config(state="normal")
            self.txt_sp.delete("1.0", "end")
            self.txt_sp.insert("1.0",
                "\n\n  ⬆ 从上方下拉框选择一个种族，\n"
                "     这里会显示体型 / 速度 / 全部种族特性。")
            self.txt_sp.config(state="disabled")

    def _show_lineage(self):
        ent = consts.SPECIES_SPELLS.get(self.data.get("species_id") or "")
        if not isinstance(ent, dict):
            return
        label = self.cb_lineage.get()
        key = next((k for k, v in consts.LINEAGE_CN.items()
                    if v == label and k in ent), None)
        if not key:
            return
        self.data["lineage"] = key
        lines = []
        for unlock, sid in ent[key]:
            sp = self.r.spell(sid)
            if sp:
                tag = "戏法" if sp["level"] == 0 else f"{sp['level']} 环"
                lines.append(f"{unlock} 级：{sp['name']}（{tag}）")
        self.lbl_lineage.config(
            text="种族自带（始终备好，每项可免费施放 1 次/长休）：\n"
                 + "　".join(lines))

    def _validate_2(self):
        if not self.data["species_id"]:
            messagebox.showwarning("提示", "请选择一个种族", parent=self)
            return False
        if self.data["species_id"] == "human" and not self.data.get("human_feat"):
            messagebox.showwarning("提示", "人类「全能」需要自选 1 个起源专长",
                                   parent=self)
            return False
        ent = consts.SPECIES_SPELLS.get(self.data["species_id"])
        if isinstance(ent, dict) and not self.data.get("lineage"):
            messagebox.showwarning("提示", "请选择一个血脉分支", parent=self)
            return False
        return True
