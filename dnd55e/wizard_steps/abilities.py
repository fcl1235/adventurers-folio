"""步骤 3: 属性生成 (点买 / 标准数组 / 4d6 掷)。"""
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


class AbilitiesMixin():
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
