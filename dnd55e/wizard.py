import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)
from .util import ability_mod, mod_str, proficiency_bonus, spell_detail

# 拆分后需要的内部依赖
from .consts import (ABILITIES, ABILITY_CN, ARMOR_PROF_CN, CAST_MODE_CN,
                     CAST_TYPE_CN, WEAPON_PROF_CN)
from .character import Character
from .rules import Rules
from .theme import (BG, DIM, GOLD2, LISTBOX_STYLE, PURPLE, TEXT, TXT_BG,
                    HintText)
from .util import ab_from_display, roll_4d6kh3


class Wizard(tk.Toplevel):
    """六步建卡向导 (模态)"""

    def __init__(self, master, rules, on_finish):
        super().__init__(master)
        if not master.winfo_viewable():   # 后台测试: 父窗口不可见时不弹出
            self.withdraw()
        self.r = rules
        self.on_finish = on_finish
        self.title("新建角色 · D&D 5.5e 建卡向导")
        self.geometry("740x720")
        self.minsize(700, 560)
        self.transient(master)
        self.configure(bg=BG)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        self.data = {
            "name": "", "class_id": None, "background_id": None,
            "species_id": None, "base_scores": {}, "bg_bonus": None,
            "skill_prof": set(), "bonus_skills": set(),
            "weapon_mastery": [], "human_feat": None, "order": None,
        }
        self.step = 0
        self.steps = [self._step_class, self._step_background, self._step_species,
                      self._step_abilities, self._step_skills]
        if True:  # 武器专精步骤按职业条件插入
            self.steps.append(self._step_mastery)
        self.steps.append(self._step_spells)      # 仅施法职业显示
        self.steps.append(self._step_summary)

        # 底部导航必须先 pack (side=bottom): pack 按顺序分配空间,
        # 后 pack 的侧栏永远先拿到空间, 内容再高也不会把导航挤出窗口
        self.progress = ttk.Label(self, text="", anchor="center",
                                  padding=(0, 4))
        self.progress.pack(fill="x", side="bottom")
        nav = ttk.Frame(self, padding=(10, 4))
        nav.pack(fill="x", side="bottom")
        self.btn_prev = ttk.Button(nav, text="← 上一步", command=self.prev,
                                   state="disabled")
        self.btn_prev.pack(side="left", padx=4)
        self.btn_next = ttk.Button(nav, text="下一步 →", command=self.next)
        self.btn_next.pack(side="right", padx=4)

        self.container = ttk.Frame(self, padding=10)
        self.container.pack(fill="both", expand=True)
        self.render_step()

    # ---- 流程控制 ----

    def render_step(self):
        for w in self.container.winfo_children():
            w.destroy()
        vis = [i for i in range(len(self.steps)) if not self._skip(i)]
        pos = vis.index(self.step) + 1 if self.step in vis else 1
        self.progress.config(text=f"第 {pos} / {len(vis)} 步")
        self.btn_prev.config(state="normal" if vis[0] != self.step else "disabled")
        self.btn_next.config(
            text="完成 ✓" if self.step == vis[-1] else "下一步 →")
        self.steps[self.step]()

    def _skip(self, idx):
        """某些步骤按职业条件跳过 (如无法术职业跳过选法术)"""
        fn = self.steps[idx]
        if fn == self._step_spells:
            cid = self.data.get("class_id")
            if not (cid and self.r.cls(cid).get("casting")):
                return True
            # 本地法术库缺失时不卡住建卡, 直接跳过
            return not self.r.class_spells(cid)
        return False

    def prev(self):
        prv = self.step - 1
        while prv > 0 and self._skip(prv):
            prv -= 1
        if prv >= 0:
            self.step = prv
            self.render_step()

    def next(self):
        if not self.validate_step():
            return
        vis = [i for i in range(len(self.steps)) if not self._skip(i)]
        if self.step == vis[-1]:
            self.finish()
            return
        nxt = self.step + 1
        while nxt < len(self.steps) - 1 and self._skip(nxt):
            nxt += 1
        self.step = nxt
        self.render_step()

    def validate_step(self):
        fn = getattr(self, f"_validate_{self.step}", None)
        return fn() if fn else True

    # ---- Step 0: 职业 ----

    def _step_class(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="① 选择职业", font=("", 13, "bold")).pack(anchor="w")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="角色姓名:").pack(side="left")
        self.e_name = ttk.Entry(row, width=18)
        self.e_name.insert(0, self.data["name"])
        self.e_name.pack(side="left", padx=6)
        ttk.Label(row, text="职业:").pack(side="left", padx=(10, 2))
        self.cb_class = ttk.Combobox(row, state="readonly", width=22,
                                     values=[c["name"] for c in self.r.d["classes"]])
        if self.data["class_id"]:
            self.cb_class.set(self.r.cls(self.data["class_id"])["name"])
        self.cb_class.pack(side="left")
        self.cb_class.bind("<<ComboboxSelected>>", lambda e: self._show_class())

        self.txt_class = tk.Text(f, height=16, wrap="word", state="disabled",
                                 background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        self.txt_class.pack(fill="both", expand=True, pady=(6, 0))
        # 1 级职阶 (牧师/德鲁伊): 选中职业后动态填充, 其它职业整块隐藏
        self.order_frame = ttk.LabelFrame(f, text="1 级职阶")
        self.order_var = tk.StringVar(value=self.data.get("order") or "")
        self._order_radios = []
        self._show_class()

    def _show_class(self):
        name = self.cb_class.get()
        found = False
        for c in self.r.d["classes"]:
            if c["name"] == name:
                found = True
                self.data["class_id"] = c["id"]
                cast = c.get("casting")
                cast_s = (f"施法: {CAST_TYPE_CN.get(cast['type'], cast['type'])} / "
                          f"施法属性 {ABILITY_CN.get(cast['ability'], cast['ability'])} / "
                          f"{CAST_MODE_CN.get(cast['mode'], cast['mode'])}"
                          if cast else "无施法能力")
                weapons = "、".join(WEAPON_PROF_CN.get(w, w)
                                    for w in c["weapons"])
                armor = "、".join(ARMOR_PROF_CN.get(a, a)
                                  for a in c["armor"]) or "无"
                pool_txt = ("任意 18 项技能" if c["skill_options"] == "*any*"
                            else "、".join(self.r.skill_by_id[s]["name"]
                                          for s in c["skill_options"]
                                          if s in self.r.skill_by_id))
                text = (
                    f"{c['name']}\n{'-' * 46}\n"
                    f"生命骰: d{c['hit_die']}    1级HP: {c['hit_die']}+体质调整值"
                    f"    每级固定HP: {c['fixed_hp_per_level']}\n"
                    f"主属性: {' / '.join(ABILITY_CN[a] for a in c['primary'])}    "
                    f"豁免熟练: {' / '.join(ABILITY_CN[a] for a in c['saves'])}\n"
                    f"技能选择数: {c['skill_count']} 项    "
                    f"武器专精: {(str(c['weapon_mastery_count']) + ' 件') if c['weapon_mastery_count'] else '无'}\n"
                    f"武器熟练: {weapons}\n"
                    f"护甲训练: {armor}\n"
                    f"{cast_s}\n\n"
                    f"子职 (3级选): {' / '.join(subclass_cn(s) for s in c['subclasses'])}\n"
                    + (("1级职阶: " + " / ".join(v[0] for v in
                        consts.ORDERS[c['id']].values()) + "（见下方单选）\n")
                       if consts.ORDERS.get(c["id"]) else "")
                    + f"\n"
                    f"技能候选池 ({len(c['skill_options']) if c['skill_options'] != '*any*' else 18} 项):\n{pool_txt}"
                )
                self.txt_class.config(state="normal")
                self.txt_class.delete("1.0", "end")
                self.txt_class.insert("1.0", text)
                self.txt_class.config(state="disabled")
                self._render_order(c["id"])
                break
        if not found:
            self._render_order(None)
            self.txt_class.config(state="normal")
            self.txt_class.delete("1.0", "end")
            self.txt_class.insert("1.0",
                "\n\n  ⬆ 从上方下拉框选择一个职业，\n"
                "     这里会显示生命骰 / 豁免 / 技能池 / 子职 / 施法等完整详情。")
            self.txt_class.config(state="disabled")

    def _render_order(self, class_id):
        """牧师/德鲁伊 1 级职阶单选; 更换职业时清空旧选择"""
        for w in self.order_frame.winfo_children():
            w.destroy()
        self._order_radios = []
        opts = consts.ORDERS.get(class_id or "", {})
        if not opts:
            self.order_frame.pack_forget()
            self.data["order"] = None
            self.order_var.set("")
            return
        if self.order_var.get() not in opts:
            self.order_var.set(next(iter(opts)))
        for key, (name, desc) in opts.items():
            rb = ttk.Radiobutton(self.order_frame, value=key,
                                 variable=self.order_var,
                                 text=f"{name} —— {desc}",
                                 command=self._order_picked)
            rb.pack(anchor="w", padx=6, pady=1)
            self._order_radios.append(rb)
        self.order_frame.pack(fill="x", pady=(6, 0))
        self.data["order"] = self.order_var.get()

    def _order_picked(self):
        # 只记录选择: 重建控件会销毁正在响应点击的单选框, 交给下一步校验
        self.data["order"] = self.order_var.get()

    def _validate_0(self):
        self.data["name"] = self.e_name.get().strip() or "无名冒险者"
        if not self.data["class_id"]:
            messagebox.showwarning("提示", "请选择一个职业", parent=self)
            return False
        # 牧师/德鲁伊必须选定 1 级职阶
        opts = consts.ORDERS.get(self.data["class_id"]) or {}
        if opts and self.data.get("order") not in opts:
            messagebox.showwarning("提示", "请选择 1 级职阶（神圣职阶 / 原始职阶）",
                                   parent=self)
            return False
        if not opts:
            self.data["order"] = None
        return True

    # ---- Step 1: 背景 ----

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

    # ---- Step 2: 种族 ----

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

    # ---- Step 3: 属性 ----

    def _step_abilities(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="④ 生成属性值 (背景加值稍后自动叠加)",
                  font=("", 13, "bold")).pack(anchor="w")

        self.ab_method = tk.StringVar(value=getattr(self, "_last_ab_method",
                                                    "standard"))
        if self.data["base_scores"]:
            self.ab_method.set(getattr(self, "_last_ab_method", "standard"))
        row = ttk.Frame(f)
        row.pack(fill="x", pady=4)
        for val, txt in [("standard", "标准数组"), ("pointbuy", "购点法(27点)"),
                         ("roll", "掷骰法(4d6取三)")]:
            ttk.Radiobutton(row, text=txt, value=val, variable=self.ab_method,
                            command=self._render_ab_ui).pack(side="left", padx=8)
        self.ab_frame = ttk.Frame(f)
        self.ab_frame.pack(fill="both", expand=True, pady=6)
        self._rolled = getattr(self, "_rolled", None)
        self._render_ab_ui()

        # ---- 2024 规则说明: 属性加值只来自背景 ----
        spf = ttk.LabelFrame(f, text="属性加值来源", padding=6)
        spf.pack(fill="x", pady=(4, 0))
        sp_id = self.data["species_id"]
        sp_name = self.r.sp(sp_id)["name"] if sp_id else "种族"
        ttk.Label(spf, text="※ 2024 规则（5.5e / 5R）：属性加值只来自背景（上方 +2/+1 或 +1/+1/+1），"
                           f"种族本身不给属性加值。{sp_name} 的特殊能力体现在速度、感官、"
                           "抗性、自带法术与技能熟练上，在建卡向导的种族页可查看。",
                  style="Dim.TLabel", wraplength=680,
                  justify="left").pack(anchor="w")
        self.ab_preview = ttk.Label(f, text="", font=("", 10, "bold"),
                                    foreground=GOLD2, wraplength=690,
                                    justify="left")
        self.ab_preview.pack(anchor="w", pady=(4, 0))
        self._ab_preview()

    def _current_picks(self):
        """读取属性页当前的分配结果 (未分配项为 None)"""
        out = {}
        method = self.ab_method.get()
        if method == "pointbuy":
            for ab, v in getattr(self, "pb_vars", {}).items():
                try:
                    out[ab] = v.get()
                except tk.TclError:
                    pass
        else:
            for ab, cb in getattr(self, "ab_picks", {}).items():
                val = cb.get()
                out[ab] = int(val) if val.isdigit() else None
        return out

    def _ab_preview(self):
        if not hasattr(self, "ab_preview"):
            return
        picks = self._current_picks()
        bg = self.data.get("bg_bonus") or {}
        parts, unset = [], []
        for ab in ABILITIES:
            base = picks.get(ab)
            if base is None:
                unset.append(ABILITY_CN[ab])
                continue
            v = base
            if bg.get("mode") == "2+1":
                v += 2 if bg.get("plus2") == ab else (1 if bg.get("plus1") == ab else 0)
            elif bg.get("mode") == "111":
                v += 1 if ab in bg.get("ones", []) else 0
            v = max(1, min(20, v))
            parts.append(f"{ABILITY_CN[ab]} {v}({mod_str(ability_mod(v))})")
        txt = "最终属性(基础 + 背景加值): " + "   ".join(parts)
        if unset:
            txt += f"   ｜ 未分配: {'、'.join(unset)}"
        self.ab_preview.config(text=txt)

    def _render_ab_ui(self):
        for w in self.ab_frame.winfo_children():
            w.destroy()
        method = self.ab_method.get()
        self._last_ab_method = method

        if method == "standard":
            ttk.Label(self.ab_frame, text="为数组 15 / 14 / 13 / 12 / 10 / 8 分配属性:",
                      foreground=DIM).pack(anchor="w")
            self.ab_picks = {}
            grid = ttk.Frame(self.ab_frame)
            grid.pack(anchor="w", pady=8)
            for i, ab in enumerate(ABILITIES):
                ttk.Label(grid, text=f"{ABILITY_CN[ab]} {ab}").grid(
                    row=i // 3, column=(i % 3) * 2, sticky="w", padx=6, pady=3)
                cb = ttk.Combobox(grid, state="readonly", width=4,
                                  values=[str(v) for v in consts.STANDARD_ARRAY])
                cb.grid(row=i // 3, column=(i % 3) * 2 + 1, padx=6, pady=3)
                cb.bind("<<ComboboxSelected>>", lambda e: self._ab_preview())
                self.ab_picks[ab] = cb

        elif method == "pointbuy":
            self.pb_vars = {}
            self.pb_costlbl = {}
            ttk.Label(self.ab_frame, text="27 购点，各项 8–15（费用 9→1 … 15→9）:",
                      foreground=DIM).pack(anchor="w")
            grid = ttk.Frame(self.ab_frame)
            grid.pack(anchor="w", pady=8)
            for i, ab in enumerate(ABILITIES):
                v = tk.IntVar(value=self.data["base_scores"].get(ab, 8))
                v.trace_add("write", lambda *a: self._pb_update())
                self.pb_vars[ab] = v
                ttk.Label(grid, text=f"{ABILITY_CN[ab]}").grid(
                    row=i // 3, column=(i % 3) * 3, sticky="w", padx=4, pady=3)
                sp = ttk.Spinbox(grid, from_=8, to=15, textvariable=v, width=4,
                                 command=self._pb_update)
                sp.grid(row=i // 3, column=(i % 3) * 3 + 1, padx=4)
                self.pb_costlbl[ab] = ttk.Label(grid, text="(0)")
                self.pb_costlbl[ab].grid(row=i // 3, column=(i % 3) * 3 + 2, padx=4)
            self.pb_left = ttk.Label(self.ab_frame, text="", font=("", 11, "bold"))
            self.pb_left.pack(anchor="w", pady=4)
            self._pb_update()

        else:  # roll
            bar = ttk.Frame(self.ab_frame)
            bar.pack(anchor="w", pady=4)
            ttk.Button(bar, text="🎲 掷 6 组 4d6(取高三)",
                       command=self._do_roll).pack(side="left")
            self.roll_result = ttk.Label(self.ab_frame, text="先掷骰，再分配",
                                         foreground=DIM)
            self.roll_result.pack(anchor="w", pady=4)
            self.ab_picks = {}
            grid = ttk.Frame(self.ab_frame)
            grid.pack(anchor="w", pady=4)
            for i, ab in enumerate(ABILITIES):
                ttk.Label(grid, text=f"{ABILITY_CN[ab]}").grid(
                    row=i // 3, column=(i % 3) * 2, sticky="w", padx=6, pady=3)
                cb = ttk.Combobox(grid, state="readonly", width=4)
                cb.grid(row=i // 3, column=(i % 3) * 2 + 1, padx=6, pady=3)
                cb.bind("<<ComboboxSelected>>", lambda e: self._ab_preview())
                self.ab_picks[ab] = cb
            if self._rolled:
                self._show_rolled()

    def _pb_update(self):
        total = 0
        for ab, v in self.pb_vars.items():
            try:
                val = v.get()
            except tk.TclError:
                continue
            total += consts.POINT_COST.get(val, 99)
            self.pb_costlbl[ab].config(text=f"({consts.POINT_COST.get(val, '?')})")
        left = 27 - total
        color = "#1a7f37" if left >= 0 else "#e05c4d"
        self.pb_left.config(text=f"剩余点数: {left} / 27", foreground=color)
        self._ab_preview()

    def _do_roll(self):
        self._rolled = sorted((roll_4d6kh3() for _ in range(6)), reverse=True)
        self._show_rolled()

    def _show_rolled(self):
        vals = [str(v) for v in self._rolled]
        self.roll_result.config(text="掷得: " + " / ".join(vals) + "（自行分配）")
        for cb in self.ab_picks.values():
            cb.config(values=vals)

    def _validate_3(self):
        method = self.ab_method.get()
        scores = {}
        if method == "standard" or method == "roll":
            vals = []
            for ab, cb in self.ab_picks.items():
                if not cb.get():
                    messagebox.showwarning("提示", "请完成所有属性分配", parent=self)
                    return False
                vals.append(int(cb.get()))
                scores[ab] = int(cb.get())
            if method == "standard" and sorted(vals, reverse=True) != consts.STANDARD_ARRAY:
                messagebox.showwarning("提示", "标准数组必须恰好用完 15/14/13/12/10/8",
                                       parent=self)
                return False
            if method == "roll" and sorted(vals, reverse=True) != self._rolled:
                messagebox.showwarning("提示", "只能使用掷出的六个数值", parent=self)
                return False
        else:
            total = 0
            for ab, v in self.pb_vars.items():
                try:
                    val = v.get()
                except tk.TclError:
                    messagebox.showwarning("提示", "属性值无效", parent=self)
                    return False
                if not 8 <= val <= 15:
                    messagebox.showwarning("提示", "购点属性必须在 8–15 之间", parent=self)
                    return False
                total += consts.POINT_COST[val]
                scores[ab] = val
            if total > 27:
                messagebox.showwarning("提示", f"超预算: 已用 {total} 点 (上限 27)",
                                       parent=self)
                return False
        self.data["base_scores"] = scores
        # 基础值 + 背景加值 不得超 20 (2024: 种族不加属性)
        for ab in ABILITIES:
            v = scores[ab]
            bgv = self.data.get("bg_bonus") or {}
            if bgv.get("mode") == "2+1":
                v += 2 if bgv.get("plus2") == ab else (1 if bgv.get("plus1") == ab else 0)
            elif bgv.get("mode") == "111":
                v += 1 if ab in bgv.get("ones", []) else 0
            if v > 20:
                messagebox.showwarning(
                    "提示", f"{ABILITY_CN[ab]} 最终值 {v} 超过 20 上限，请调低基础值",
                    parent=self)
                return False
        return True

    # ---- Step 4: 技能 ----

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

    # ---- Step 5: 武器专精 ----

    def _step_mastery(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        cls = self.r.cls(self.data["class_id"])
        n = cls["weapon_mastery_count"]
        if n == 0:
            self.data["weapon_mastery"] = []     # 换到无专精职业: 清掉旧选择
            ttk.Label(f, text="⑤/⑥ 武器专精", font=("", 13, "bold")).pack(anchor="w")
            ttk.Label(f, text=f"{cls['name']} 没有武器专精特性，直接下一步。\n"
                              f"(4级起可用 Weapon Master 专长补足)",
                      foreground=DIM).pack(anchor="w", pady=10)
            return
        ttk.Label(f, text=f"⑤/⑥ 选择武器专精 (须恰好 {n} 件, 长休可换)",
                  font=("", 13, "bold")).pack(anchor="w")
        pool = Rules.class_mastery_pool(cls)
        head = ttk.Frame(f)
        head.pack(anchor="w", fill="x")
        ttk.Label(head, text=f"可选范围: {cls['name']} 的武器熟练 "
                             f"({', '.join(WEAPON_PROF_CN.get(w, w) for w in cls['weapons'])})",
                  foreground=DIM).pack(side="left")
        self._mastery_count_lbl = ttk.Label(head, text="", font=("", 10, "bold"))
        self._mastery_count_lbl.pack(side="left", padx=10)
        self.mastery_vars = {}
        grid = ttk.Frame(f)
        grid.pack(anchor="w", pady=6)
        for i, w in enumerate(pool):
            wname, cat, dmg, mst = w[0], w[1], w[2], w[3]
            v = tk.BooleanVar(value=wname in self.data["weapon_mastery"])
            self.mastery_vars[wname] = v
            ttk.Checkbutton(grid, text=f"{wname} · {dmg} · {mastery_cn(mst)}",
                            variable=v,
                            command=lambda w2=wname: self._on_mastery(w2)
                            ).grid(row=i // 2, column=i % 2,
                                   sticky="w", padx=8, pady=2)
        self._mastery_need = n
        self._update_mastery_count()
        ttk.Label(f, text="专精效果:", foreground=DIM).pack(anchor="w")
        txt = tk.Text(f, height=6, wrap="word", state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        txt.pack(fill="both", expand=True)
        masts = {w[3] for w in pool}
        txt.config(state="normal")
        txt.insert("1.0", "\n".join(consts.MASTERY_DESC[m] for m in sorted(masts)))
        txt.config(state="disabled")

    def _update_mastery_count(self):
        n = sum(1 for v in self.mastery_vars.values() if v.get())
        ok = (n == self._mastery_need)
        self._mastery_count_lbl.config(
            text=f"已选 {n} / {self._mastery_need}",
            foreground="#58b368" if ok else GOLD2)

    def _on_mastery(self, wname):
        """武器专精多选实时控制: 超出上限自动回退本次勾选"""
        v = self.mastery_vars[wname]
        if v.get():
            n = sum(1 for x in self.mastery_vars.values() if x.get())
            if n > self._mastery_need:
                v.set(False)
                self._mastery_count_lbl.config(
                    text=f"已达上限 {self._mastery_need} 件 —— 请先取消一件再选",
                    foreground="#e05c4d")
                return
        self._update_mastery_count()

    def _validate_5(self):
        cls = self.r.cls(self.data["class_id"])
        if cls["weapon_mastery_count"] == 0:
            self.data["weapon_mastery"] = []
            return True
        chosen = [w for w, v in self.mastery_vars.items() if v.get()]
        if len(chosen) != self._mastery_need:
            messagebox.showwarning(
                "提示", f"须恰好选择 {self._mastery_need} 件武器 (已选 {len(chosen)})",
                parent=self)
            return False
        self.data["weapon_mastery"] = chosen
        return True

    # ---- Step 6: 法术 ----

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

    # ---- Step 7: 摘要 ----

    def _step_summary(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="摘要确认", font=("", 13, "bold")).pack(anchor="w")
        txt = tk.Text(f, height=22, wrap="word", state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        txt.pack(fill="both", expand=True, pady=6)

        cls = self.r.cls(self.data["class_id"])
        bg = self.r.bg(self.data["background_id"])
        sp = self.r.sp(self.data["species_id"])
        tmp = self._build_char()
        scores = tmp.scores()
        mods = tmp.mods()
        skills = "、".join(
            self.r.skill_by_id[s]["name"]
            for s in sorted(self.data["skill_prof"],
                            key=lambda x: self.r.skill_by_id[x]["name"]))
        sp_note = "（背景加值, 种族不加属性）"
        spells = self.data.get("spells") or {}
        spell_lines = []
        if spells.get("cantrips"):
            spell_lines.append("戏法: " + "、".join(
                self.r.spell(s)["name"] for s in spells["cantrips"] if self.r.spell(s)))
        if spells.get("prepared"):
            spell_lines.append("1 环: " + "、".join(
                self.r.spell(s)["name"] for s in spells["prepared"] if self.r.spell(s)))
        lines = [
            f"姓名: {self.data['name']}    等级: 1",
            f"职业: {cls['name']}    子职: (3级解锁)",
            f"背景: {bg['name']} [专长 {feat_cn(bg['origin_feat'])}]    "
            f"种族: {sp['name']}",
            "",
            f"属性{sp_note}: " + "   ".join(
                f"{ABILITY_CN[a]} {scores[a]}({mod_str(mods[a])})"
                for a in ABILITIES),
            f"生命值: {tmp.hp_max()}    AC: {tmp.ac()}    "
            f"先攻: {mod_str(tmp.initiative())}",
            f"熟练加值: +2    被动察觉: {tmp.passive_perception()}",
            f"豁免熟练: {'、'.join(ABILITY_CN[a] for a in cls['saves'])}",
            f"技能熟练 ({len(self.data['skill_prof'])} 项): {skills}",
            f"工具熟练: {tool_cn(bg['tool'])}",
            f"武器专精: {', '.join(self.data['weapon_mastery']) or '— (该职业无)'}",
            f"种族额外专长: {feat_cn(self.data['human_feat'])}"
            if self.data.get("human_feat") else "",
            ("法术 —— " + " ｜ ".join(spell_lines)) if spell_lines else "",
            "",
            "说明: 装备、魔法物品与加成明细请在角色卡「装备·武器」页设置;",
            "      法术可在角色卡「法 术」页随时增删与施放。",
        ]
        txt.config(state="normal")
        txt.insert("1.0", "\n".join(lines))
        txt.config(state="disabled")

    def _build_char(self):
        """按向导当前数据构造角色 —— 摘要页与 finish 共用同一份逻辑,
        避免两处字段不同步 (曾因漏设字段导致摘要页崩)。"""
        char = Character(self.r)
        char.name = self.data.get("name") or "无名冒险者"
        char.class_id = self.data.get("class_id") or char.class_id
        char.background_id = self.data.get("background_id") or char.background_id
        char.species_id = self.data.get("species_id") or char.species_id
        char.base_scores = dict(self.data.get("base_scores") or char.base_scores)
        char.bg_bonus = self.data.get("bg_bonus")
        char.skill_prof = set(self.data.get("skill_prof") or set())
        char.bonus_skills = set(self.data.get("bonus_skills") or set())
        char.weapon_mastery = list(self.data.get("weapon_mastery") or [])
        char.order = self.data.get("order") or None
        char.spells = dict(self.data.get("spells") or
                           {"cantrips": [], "prepared": []})
        # 法师: 1 级法术书应有 6 个法术, 向导只挑了 4 个「已准备」的法术,
        # 差额记成免费抄录次数, 让玩家自己在「法术书」里补齐
        if char.class_id == "wizard":
            char.spellbook = [sid for sid in (char.spells.get("prepared") or [])
                              if (self.r.spell(sid) or {}).get("level", 0) >= 1]
            char.book_pending = max(0, 6 - len(char.spellbook))
        char.lineage = self.data.get("lineage")
        char.skill_prof |= set(char.auto_skills())
        # 默认装备: 该职业熟练的第一件武器
        pool = Rules.class_mastery_pool(char.cls()) or consts.WEAPONS
        char.weapon = pool[0][0]
        char.fighting_style = None      # 由角色卡「装备」页选择
        if self.data.get("human_feat"):
            char.feats.append(self.data["human_feat"])
        char.hp_current = char.hp_max()
        return char

    def finish(self):
        char = self._build_char()
        self.destroy()
        self.on_finish(char)
