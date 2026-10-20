"""步骤 0: 职业选择与 1 级职阶。"""
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


class ClassStepMixin():
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
