import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)
from .util import ability_mod, mod_str, proficiency_bonus

# 拆分后需要的内部依赖
from .consts import ABILITIES, ABILITY_CN
from .theme import (BG, DIM, GOLD2, LISTBOX_STYLE, RED, TEXT, TEXT_STYLE,
                    TXT_BG)
from .util import ab_from_display, roll_dice


class MetamagicDialog(tk.Toplevel):
    """2024 超魔法: 施法时选 1 个 (强化/探秘可与其他叠加)。
    result: None=取消施法, []=不应用超魔法, [id, ...]=应用"""

    def __init__(self, master, char, spell):
        super().__init__(master)
        self.char = char
        self.spell = spell
        self.result = None
        self.title("超魔法")
        self.geometry("480x400")
        self.transient(master)
        self.configure(bg=BG)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        ttk.Label(self, text=f"施放: {spell['name']}（{spell['level']} 环）",
                  font=("", 11, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        cap = char.metamagic_per_spell()
        ttk.Label(self, text=f"术法点 {char.sorcery_left()}/{char.sorcery_max()}"
                             f"　每道法术最多 {cap} 个（强化/探秘可叠加）"
                             + ("　奥术神化: 其中 1 个免费"
                                if char.mm_free() else ""),
                  style="Dim.TLabel").pack(anchor="w", padx=12)

        self.vars = {}
        f = ttk.Frame(self, padding=10)
        f.pack(fill="both", expand=True)
        for mid in char.metamagic_known():
            nm, cost, desc, _stack = consts.METAMAGIC[mid]
            v = tk.BooleanVar()
            self.vars[mid] = v
            ttk.Checkbutton(f, text=f"{nm}（{cost} 点）", variable=v,
                            command=self._sync).pack(anchor="w")
            ttk.Label(f, text="   " + desc, foreground=DIM,
                      wraplength=410, justify="left").pack(anchor="w")

        self.info = ttk.Label(self, text="", foreground=GOLD2)
        self.info.pack(anchor="w", padx=12)
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=8, padx=12)
        ttk.Button(bar, text="取消", command=self._cancel).pack(side="right")
        ttk.Button(bar, text="施放", style="Gold.TButton",
                   command=self._ok).pack(side="right", padx=6)
        ttk.Button(bar, text="不用超魔法",
                   command=self._none).pack(side="left")
        self._sync()

    def _picked(self):
        return [m for m, v in self.vars.items() if v.get()]

    def _sync(self):
        ids = self._picked()
        if not ids:
            self.info.config(text="未选择超魔法", foreground=GOLD2)
            return
        ok, why, cost = self.char.mm_validate(ids)
        self.info.config(text=(f"合计 {cost} 点术法点" if ok else why),
                         foreground=(GOLD2 if ok else RED))

    def _ok(self):
        ids = self._picked()
        ok, why, _cost = self.char.mm_validate(ids)
        if not ok:
            messagebox.showwarning("不可用", why, parent=self)
            return
        self.result = ids
        self.destroy()

    def _none(self):
        self.result = []
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


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
        self.geometry("800x580")
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


class WildShapeDialog(tk.Toplevel):
    """德鲁伊荒野变形: 按等级/子职列出可选野兽形态。
    只记录当前形态, 不改角色本体数值 (AC/HP/攻击按形态数据单独看)。
    result: None=取消, ""=恢复本体, else=monster id"""

    def __init__(self, master, char, selftest=False):
        super().__init__(master)
        from . import wildshape as _ws
        self.char = char
        self._selftest = selftest
        self.result = None
        self._rows = char.wild_shapes()
        self.title("野兽形态")
        self.geometry("760x540")
        self.transient(master)
        self.configure(bg=BG)
        if not selftest:
            try:
                self.grab_set()
            except tk.TclError:
                pass

        ttk.Label(self, text=f"{char.name} · 荒野变形",
                  font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        cap = _ws.cap_for(char.level, char.subclass)
        cur = char.wild_shape()
        self.head = ttk.Label(
            self, foreground=GOLD2,
            text=f"可选 {len(self._rows)} 种 · CR 上限 {cap}"
                 + (f" · 当前：{cur['name']}" if cur else " · 当前：本体"))
        self.head.pack(anchor="w", padx=12)
        ttk.Label(self, wraplength=700, justify="left", foreground=DIM,
                  text="2 级不能选带飞行/游泳速度的形态，4 级起解除；"
                       "大地结社按 3/6/9/12/15/18 级放宽 CR 上限。"
                       "变形后按这里的 AC/HP/攻击结算，角色本体数值不变。").pack(
            anchor="w", padx=12, pady=(2, 6))

        body = ttk.Frame(self, padding=(12, 0))
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="可选形态", padding=6)
        left.pack(side="left", fill="y")
        self.lst = tk.Listbox(left, width=30, height=16, exportselection=False,
                             **LISTBOX_STYLE)
        self.lst.pack(fill="both", expand=True)
        self.lst.bind("<<ListboxSelect>>", self._show)
        for m in self._rows:
            self.lst.insert("end", f"{m['name']}  (CR {m['cr']})")

        right = ttk.LabelFrame(body, text="形态详情", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.detail = tk.Text(right, wrap="word", state="disabled",
                              **TEXT_STYLE, width=1)
        self.detail.pack(fill="both", expand=True)

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="变形", command=self._take).pack(
            side="right", padx=4)
        ttk.Button(bar, text="恢复本体", command=self._revert).pack(
            side="right", padx=4)
        ttk.Button(bar, text="关闭", command=self._close).pack(
            side="right", padx=4)
        if self._rows:
            self.lst.selection_set(0)
            self._show()

    def _sel(self):
        cur = self.lst.curselection()
        return self._rows[cur[0]] if cur else None

    def _show(self, _e=None):
        from . import wildshape as _ws
        m = self._sel()
        if not m:
            return
        ab = m.get("abilities") or {}
        lines = [_ws.summary(m), ""]
        lines.append("力量 {} 敏捷 {} 体质 {} 智力 {} 感知 {} 魅力 {}".format(
            ab.get("STR", 0), ab.get("DEX", 0), ab.get("CON", 0),
            ab.get("INT", 0), ab.get("WIS", 0), ab.get("CHA", 0)))
        for tr in (m.get("traits") or []):
            lines.append(f"· {tr.get('name')}：{tr.get('desc', '')}")
        if m.get("actions"):
            lines.append("")
            lines.append("动作：")
            for a in m["actions"]:
                lines.append("  " + _ws.attack_line(a))
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))
        self.detail.config(state="disabled")

    def _take(self):
        m = self._sel()
        if not m:
            return
        self.char.wild_shape_id = m["id"]
        self.result = m["id"]
        self._close()

    def _revert(self):
        self.char.wild_shape_id = None
        self.result = ""
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


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

        # 传奇恩惠
        self.boan_entry = None
        if new_lv == 19:
            bf = ttk.LabelFrame(f, text="传奇恩惠 Epic Boon (输入名称)", padding=6)
            bf.pack(fill="x", pady=6)
            self.boan_entry = ttk.Entry(bf, width=34)
            self.boan_entry.pack(anchor="w")

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
            rec["boon"] = self.boan_entry.get().strip() or "传奇恩惠(未命名)"
            rec["asi"] = {"type": "feat", "name": rec["boon"]}

        self.result = rec
        self.destroy()


# ----------------------------------------------------------------------------
# 骰子工具
# ----------------------------------------------------------------------------

class DiceDialog(tk.Toplevel):

    def __init__(self, master):
        super().__init__(master)
        if not master.winfo_viewable():   # 后台测试: 父窗口不可见时不弹出
            self.withdraw()
        self.title("骰子工具")
        self.geometry("420x300")
        self.transient(master)
        self.configure(bg=BG)
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="表达式: 如 1d20, 2d6+3, 4d6 (4d6取高三请自行取舍)",
                  foreground=DIM).pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        self.e = ttk.Entry(row, width=14)
        self.e.insert(0, "1d20")
        self.e.pack(side="left")
        ttk.Button(row, text="掷!", command=self.roll).pack(side="left", padx=6)
        for txt in ["1d20", "1d20+5", "2d6+3", "1d8", "1d4"]:
            ttk.Button(f, text=txt, width=8,
                       command=lambda t=txt: (self.e.delete(0, "end"),
                                              self.e.insert(0, t),
                                              self.roll())).pack(
                side="left", padx=3, pady=6)
        self.out = tk.Text(f, height=8, state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        self.out.pack(fill="both", expand=True)
        self.e.bind("<Return>", lambda e: self.roll())

    def roll(self):
        try:
            total, detail = roll_dice(self.e.get().strip())
        except Exception:
            messagebox.showerror("错误", "无法解析表达式", parent=self)
            return
        self.out.config(state="normal")
        self.out.insert("end", detail + "\n")
        self.out.see("end")
        self.out.config(state="disabled")
