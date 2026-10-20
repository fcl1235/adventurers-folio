"""升级对话框: ASI / 子职 / 传奇恩惠。"""
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


class LevelUpDialog(tk.Toplevel):

    # 2024 属性加值等级: 通用 4/8/12/16, 战士额外 6/14, 游荡者额外 10
    @staticmethod
    def asi_levels(cls_id):
        lv = {4, 8, 12, 16}
        if cls_id == "fighter":
            lv |= {6, 14}
        elif cls_id == "rogue":
            lv.add(10)
        return lv

    def __init__(self, master, char):
        super().__init__(master)
        if not master.winfo_viewable():   # 后台测试: 父窗口不可见时不弹出
            self.withdraw()
        self.char = char
        self.result = None
        self.title(f"升级: {char.level} → {char.level + 1} 级")
        self.geometry("640x640" if char.level + 1 == 3 else "560x560")
        self.transient(master)
        self.configure(bg=BG)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        new_lv = char.level + 1
        # 确认按钮先 pack 到底部, 内容再多也不会被挤出窗口
        ttk.Button(self, text="确认升级", style="Gold.TButton",
                   command=self._ok).pack(side="bottom", pady=8)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)

        info = [f"{char.name} · {char.cls()['name']}  {char.level} → {new_lv} 级",
                f"熟练加值: {mod_str(char.pb())} → {mod_str(proficiency_bonus(new_lv))}",
                f"生命值上限: {char.hp_max()} → "
                f"{char.hp_max() + char.cls()['hit_die'] // 2 + 1 + ability_mod(char.score('CON'))}"
                f" (自动取固定值)"]
        if new_lv == 3:
            info.append("★ 3 级: 解锁子职!")
        if new_lv in self.asi_levels(char.class_id):
            info.append("★ 属性加值/专长 (ASI)!")
        if new_lv == 19:
            info.append("★ 19 级: 传奇恩惠 Epic Boon!")
        if new_lv == 20:
            info.append("★ 20 级: 职业压轴特性 (见PHB职业表)")
        ttk.Label(f, text="\n".join(info), justify="left").pack(anchor="w")

        # 子职选择 (含每个方向的介绍与 3 级起的效果)
        self.subclass_cb = None
        self._sub_map = {}
        if new_lv == 3:
            lf = ttk.LabelFrame(f, text="选择子职（点选查看介绍与效果）", padding=6)
            lf.pack(fill="both", expand=True, pady=6)
            self._sub_map = {subclass_cn(s): s
                             for s in char.cls()["subclasses"]}
            self.subclass_cb = ttk.Combobox(
                lf, state="readonly", width=40,
                values=list(self._sub_map))
            self.subclass_cb.pack(anchor="w", fill="x")
            self.subclass_cb.bind("<<ComboboxSelected>>",
                                  lambda e: self._sub_preview())
            self._sub_text = tk.Text(lf, height=9, wrap="word", width=1,
                                     **TEXT_STYLE)
            self._sub_text.pack(fill="both", expand=True, pady=(4, 0))
            self.subclass_cb.set(list(self._sub_map)[0])
            self._sub_preview()

        # ASI 选择
        self.asi_frame = None
        if new_lv in self.asi_levels(char.class_id):
            self.asi_frame = ttk.LabelFrame(f, text="属性加值 或 专长", padding=6)
            self.asi_frame.pack(fill="both", expand=True, pady=6)
            self.asi_mode = tk.StringVar(value="asi")
            ttk.Radiobutton(self.asi_frame, text="属性加值 (上限20)",
                            variable=self.asi_mode, value="asi",
                            command=self._render_asi).pack(anchor="w")
            ttk.Radiobutton(self.asi_frame, text="改为选择专长",
                            variable=self.asi_mode, value="feat",
                            command=self._render_asi).pack(anchor="w")
            self.asi_body = ttk.Frame(self.asi_frame)
            self.asi_body.pack(anchor="w", fill="x", pady=4)
            self._render_asi()

        # 传奇恩惠: 下拉列出全部 12 条 (也允许手输), 再选「哪一项属性 +1」
        self.boan_entry = None
        self.boon_ability_cb = None
        self._boon_map = {}
        if new_lv == 19:
            bf = ttk.LabelFrame(f, text="传奇恩惠 Epic Boon", padding=6)
            bf.pack(fill="x", pady=6)
            boons = consts.GENERAL_FEATS.get("epic_boon") or {}
            self._boon_map = {f"{v.get('cn', '')} {k}".strip(): k
                              for k, v in boons.items()}
            self.boan_entry = ttk.Combobox(bf, width=34,
                                           values=list(self._boon_map))
            self.boan_entry.pack(anchor="w")
            self.boan_entry.bind("<<ComboboxSelected>>",
                                 lambda e: self._render_boon_ability())
            row = ttk.Frame(bf)
            row.pack(anchor="w", pady=(4, 0))
            ttk.Label(row, text="属性 +1 →").pack(side="left")
            self.boon_ability_cb = ttk.Combobox(
                row, state="readonly", width=16,
                values=[f"{ABILITY_CN[a]}({a})" for a in ABILITIES])
            self.boon_ability_cb.pack(side="left", padx=4)
            self._boon_hint = ttk.Label(bf, text="", wraplength=520,
                                        justify="left", foreground=DIM)
            self._boon_hint.pack(anchor="w", pady=(4, 0))
            self._render_boon_ability()

    def _boon_info(self):
        """当前选中的恩惠条目 (手输的未知名字返回 None)"""
        raw = self.boan_entry.get().strip()
        name = self._boon_map.get(raw, raw)
        return name, (consts.GENERAL_FEATS.get("epic_boon") or {}).get(name)

    def _render_boon_ability(self):
        """按恩惠的 ability_boost.from 限制可选的 +1 属性"""
        name, info = self._boon_info()
        boost = (info or {}).get("effects", {}).get("ability_boost") or {}
        allowed = boost.get("from") or list(ABILITIES)
        self.boon_ability_cb.configure(
            values=[f"{ABILITY_CN[a]}({a})" for a in allowed])
        if self.boon_ability_cb.get() and \
                ab_from_display(self.boon_ability_cb.get()) not in allowed:
            self.boon_ability_cb.set("")
        if info:
            self._boon_hint.config(text=f"{info.get('cn', '')} {name}: "
                                        f"{info.get('desc', '')}")
        else:
            self._boon_hint.config(
                text="下拉选择恩惠可自动生效；手输的恩惠请在「笔记」页记录效果")

    def _sub_preview(self):
        """升级弹窗里显示子职定位 + 各级效果"""
        name = self._sub_map.get(self.subclass_cb.get()) if self._sub_map else None
        info = self.char.r.sub_info(name) if name else None
        if not info:
            return
        lines = [f"【{subclass_cn(name)}】", info["summary"], ""]
        for f in info["features"]:
            lines.append(f"Lv{f['level']} · {f['name']}")
            lines.append(f"    {f['desc']}")
        self._sub_text.config(state="normal")
        self._sub_text.delete("1.0", "end")
        self._sub_text.insert("1.0", "\n".join(lines))
        self._sub_text.config(state="disabled")

    def _render_asi(self):
        for w in self.asi_body.winfo_children():
            w.destroy()
        if self.asi_mode.get() == "feat":
            row = ttk.Frame(self.asi_body)
            row.pack(anchor="w")
            ttk.Label(row, text="专长:").pack(side="left")
            self._feat_map = {f"{v[0]} {k}": k
                              for k, v in consts.FEAT_INFO.items()}
            self.feat_cb = ttk.Combobox(row, width=30,
                                        values=list(self._feat_map))
            self.feat_cb.pack(side="left", padx=4)
            self.feat_cb.bind("<<ComboboxSelected>>",
                              lambda e: self._feat_hint())
            self.feat_cb.bind("<KeyRelease>", lambda e: self._feat_hint())
            self.feat_desc = ttk.Label(self.asi_body, wraplength=500,
                                       justify="left", foreground=DIM)
            self.feat_desc.pack(anchor="w", pady=(4, 0))
            self._feat_hint()
            return
        self.asi_submode = tk.StringVar(value="2+1")
        ttk.Radiobutton(self.asi_body, text="+2/+1", variable=self.asi_submode,
                        value="2+1", command=self._render_asi_picks).pack(side="left")
        ttk.Radiobutton(self.asi_body, text="+1/+1/+1", variable=self.asi_submode,
                        value="111", command=self._render_asi_picks).pack(side="left",
                                                                          padx=8)
        self.asi_picks = ttk.Frame(self.asi_body)
        self.asi_picks.pack(anchor="w", pady=4)
        self._render_asi_picks()

    def _feat_hint(self):
        disp = self.feat_cb.get().strip()
        raw = self._feat_map.get(disp, disp)
        info = consts.FEAT_INFO.get(raw)
        self.feat_desc.config(
            text=(f"{info[0]} {raw}: {info[1]}" if info
                  else "自定义专长: 请在角色卡「笔记」页记录其效果"))

    def _render_asi_picks(self):
        for w in self.asi_picks.winfo_children():
            w.destroy()
        names = [f"{ABILITY_CN[a]}({a})" for a in ABILITIES]
        if self.asi_submode.get() == "2+1":
            ttk.Label(self.asi_picks, text="+2 →").pack(side="left")
            self.asi_p2 = ttk.Combobox(self.asi_picks, state="readonly",
                                       width=13, values=names)
            self.asi_p2.pack(side="left", padx=4)
            self.asi_p2.bind("<<ComboboxSelected>>",
                             lambda e: self._asi_dedup("p2"))
            ttk.Label(self.asi_picks, text="+1 →").pack(side="left",
                                                        padx=(10, 0))
            self.asi_p1 = ttk.Combobox(self.asi_picks, state="readonly",
                                       width=13, values=names)
            self.asi_p1.pack(side="left", padx=4)
            self.asi_p1.bind("<<ComboboxSelected>>",
                             lambda e: self._asi_dedup("p1"))
        else:
            self.asi_o = []
            for i in range(3):
                ttk.Label(self.asi_picks, text="+1 →").pack(
                    side="left", padx=(0 if i == 0 else 10, 0))
                cb = ttk.Combobox(self.asi_picks, state="readonly", width=13,
                                  values=names)
                cb.pack(side="left", padx=4)
                cb.bind("<<ComboboxSelected>>",
                        lambda e, box=cb: self._asi_dedup(box))
                self.asi_o.append(cb)

    def _asi_dedup(self, source):
        """同一加值不可重复选同一属性: 实时清掉冲突的另一项"""
        if self.asi_submode.get() == "2+1":
            if self.asi_p2.get() and self.asi_p1.get() \
                    and self.asi_p2.get() == self.asi_p1.get():
                (self.asi_p1 if source == "p2" else self.asi_p2).set("")
        else:
            cur = source.get()
            if cur:
                for cb in self.asi_o:
                    if cb is not source and cb.get() == cur:
                        cb.set("")

    def _ok(self):
        new_lv = self.char.level + 1
        rec = {"level": new_lv, "subclass": None, "asi": None, "boon": None}

        if new_lv == 3 and self.subclass_cb is not None:
            if not self.subclass_cb.get():
                messagebox.showwarning("提示", "请选择子职", parent=self)
                return
            rec["subclass"] = self._sub_map.get(self.subclass_cb.get(),
                                                self.subclass_cb.get())

        if new_lv in self.asi_levels(self.char.class_id):
            if self.asi_mode.get() == "feat":
                disp = self.feat_cb.get().strip()
                if not disp:
                    messagebox.showwarning("提示", "请选择或输入专长名称",
                                           parent=self)
                    return
                name = self._feat_map.get(disp, disp)
                rec["asi"] = {"type": "feat", "name": name}
                if name == "Tough" or "tough" in name.lower() \
                        or "坚忍" in disp or "坚韧" in disp:
                    self.char.tough_feat = True
            else:
                ch = self.char
                if self.asi_submode.get() == "2+1":
                    a, b = self.asi_p2.get(), self.asi_p1.get()
                    if not a or not b or a == b:
                        messagebox.showwarning("提示", "+2/+1 须选两项不同属性",
                                               parent=self)
                        return
                    ab2, ab1 = ab_from_display(a), ab_from_display(b)
                    if ch.score(ab2) + 2 > 20 or ch.score(ab1) + 1 > 20:
                        messagebox.showwarning("提示", "属性不可超过 20", parent=self)
                        return
                    rec["asi"] = {"type": "asi", "plus2": ab2, "plus1": ab1}
                else:
                    vals = [cb.get() for cb in self.asi_o]
                    if any(not v for v in vals) or len(set(vals)) != 3:
                        messagebox.showwarning("提示", "+1/+1/+1 须选三项不同属性",
                                               parent=self)
                        return
                    abs_ = [ab_from_display(v) for v in vals]
                    if any(ch.score(a) + 1 > 20 for a in abs_):
                        messagebox.showwarning("提示", "属性不可超过 20", parent=self)
                        return
                    rec["asi"] = {"type": "asi", "ones": abs_}

        if new_lv == 19:
            raw = self.boan_entry.get().strip()
            name, info = self._boon_info()
            rec["boon"] = name or "传奇恩惠(未命名)"
            rec["asi"] = {"type": "feat", "name": rec["boon"]}
            disp_ab = self.boon_ability_cb.get().strip()
            ab = ab_from_display(disp_ab) if disp_ab else None
            allowed = ((info or {}).get("effects", {})
                       .get("ability_boost") or {}).get("from") or list(ABILITIES)
            rec["boon_ability"] = ab if ab in allowed else None
            if info and not raw:
                messagebox.showwarning("提示", "请选择传奇恩惠", parent=self)
                return

        self.result = rec
        self.destroy()
