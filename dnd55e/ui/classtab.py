"""职业页: 资源池 / 生命骰 / 术法源泉 / 超魔法 / 法师自选 / 职阶 / 荒野变形 / 子职 / 特性。"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, util
from ..consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                      size_cn, subclass_cn, tool_cn)
from ..theme import DIM, GOLD2, PURPLE, TEXT, UI_FONT
from ..util import ability_mod, mod_str


class ClassTabMixin():
    def _render_class_tab(self):
        c = self.char
        if not c or not hasattr(self, "class_body"):
            return
        for w in self.class_body.winfo_children():
            w.destroy()
        body = self.class_body
        cls = c.cls()

        # ===== 1. 资源池 =====
        res = c.resources()
        hdr = ttk.Frame(body)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="职业资源", style="H2.TLabel").pack(side="left")
        ttk.Button(hdr, text="全部回满", style="Mini.TButton",
                   command=lambda: self._res_act(None, "full")
                   ).pack(side="right")
        ttk.Button(hdr, text="短休", style="Mini.TButton",
                   command=self.short_rest).pack(side="right", padx=4)
        ttk.Button(hdr, text="长休", style="Mini.TButton",
                   command=self.long_rest).pack(side="right")
        if not res:
            ttk.Label(body, text=f"{cls['name']} 没有需要逐次记录的资源池"
                                "（该职业靠法术位与特性本身运转）。",
                      style="Dim.TLabel").pack(anchor="w", pady=2)
        # 生命骰 (短休回血用; 2024 长休全回)
        hd = ttk.Frame(body)
        hd.pack(fill="x", pady=(3, 0))
        ttk.Label(hd, text=f"生命骰 d{c.hit_die()}　剩余 "
                           f"{c.hit_dice_left()}/{c.hit_dice_max()}",
                  foreground=GOLD2).pack(side="left")
        ttk.Button(hd, text="花 1 颗回血", style="Mini.TButton",
                   command=lambda: self._spend_hd(1)
                   ).pack(side="left", padx=6)
        if c.class_id == "barbarian":
            rv = tk.BooleanVar(value=c.raging)
            ttk.Checkbutton(hd, text=f"狂暴中 (伤害 +{c.rage_damage()})",
                            variable=rv,
                            command=lambda v=rv: self._toggle_rage(v)
                            ).pack(side="left", padx=8)
        if c.class_id == "rogue":
            ttk.Checkbutton(hd, text=f"含偷袭 (+{c.sneak_dice()}d6)",
                            variable=self.sneak_var
                            ).pack(side="left", padx=8)
        dice = c.class_dice_text()
        if dice:
            ttk.Label(body, text="关键数值: " + dice, foreground=GOLD2,
                      wraplength=540, justify="left").pack(anchor="w", pady=(2, 2))
        for r in res:
            card = ttk.Frame(body, style="Card.TFrame", padding=8)
            card.pack(fill="x", pady=3)
            top = ttk.Frame(card, style="Card.TFrame")
            top.pack(fill="x")
            nm = f"{r['icon']} {r['name']}".strip()
            ttk.Label(top, text=nm, style="Card.TLabel",
                      font=(UI_FONT, 10, "bold")).pack(side="left")
            txt = f"{r['left']} / {r['max']}"
            if r["die"]:
                txt += f"   d{r['die']}"
            ttk.Label(top, text=txt, style="Card.TLabel", foreground=GOLD2,
                      font=(UI_FONT, 12, "bold")).pack(side="right")
            bar = ttk.Frame(card, style="Card.TFrame")
            bar.pack(fill="x", pady=(4, 0))
            for label, act, n in (("用 1", "spend", 1), ("回 1", "restore", 1)):
                ttk.Button(bar, text=label, width=5, style="Mini.TButton",
                           command=lambda rid=r["id"], a=act, k=n:
                           self._res_act(rid, a, k)).pack(side="left", padx=2)
            if r["max"] >= 10:      # 圣疗池这类大池子, 一次 5 点更常用
                ttk.Button(bar, text="用 5", width=5, style="Mini.TButton",
                           command=lambda rid=r["id"]:
                           self._res_act(rid, "spend", 5)).pack(side="left", padx=2)
            ttk.Button(bar, text="回满", width=5, style="Mini.TButton",
                       command=lambda rid=r["id"]:
                       self._res_act(rid, "full")).pack(side="left", padx=2)
            ttk.Label(bar, text=self._reset_text(r), style="Card.TLabel",
                      foreground=DIM).pack(side="right")
            ttk.Label(card, text=r["note"], style="Card.TLabel",
                      foreground=DIM, wraplength=520, justify="left"
                      ).pack(anchor="w", pady=(4, 0))

        # ===== 1.4 术士·术法源泉 (2 级): 术法点 ↔ 法术位 =====
        if c.font_can_use():
            fo = ttk.Frame(body)
            fo.pack(fill="x", pady=(8, 0))
            ttk.Label(fo, text=f"术法源泉（术法点 {c.sorcery_left()}/"
                               f"{c.sorcery_max()}）",
                      foreground=GOLD2).pack(side="left")
            ttk.Button(fo, text="术法点 → 法术位", style="Mini.TButton",
                       command=self._font_create).pack(side="left", padx=6)
            ttk.Button(fo, text="法术位 → 术法点", style="Mini.TButton",
                       command=self._font_burn).pack(side="left")
            if c.font_slots:
                ttk.Label(body, text="已兑换临时位: " + "、".join(
                    f"{lv} 环 ×{n}" for lv, n in sorted(c.font_slots.items())),
                    style="Dim.TLabel", wraplength=540,
                    justify="left").pack(anchor="w", pady=(2, 0))
            ttk.Label(body, text=consts.FONT_OF_MAGIC["note"], style="Dim.TLabel",
                      wraplength=540, justify="left").pack(anchor="w")

        # ===== 1.45 超魔法 (2 级) / 先天魔法 =====
        if c.metamagic_cap():
            mm = ttk.Frame(body)
            mm.pack(fill="x", pady=(8, 0))
            ttk.Label(mm, text=f"超魔法（{len(c.metamagic_known())}/"
                               f"{c.metamagic_cap()} 个，施法时选用）",
                      style="H2.TLabel").pack(anchor="w")
            grid = ttk.Frame(mm)
            grid.pack(fill="x")
            known = set(c.metamagic_known())
            for i, (mid, (nm, cost, desc, stack)) in enumerate(
                    consts.METAMAGIC.items()):
                v = tk.BooleanVar(value=mid in known)
                ttk.Checkbutton(
                    grid, text=f"{nm.split(' ')[0]} {cost}点", variable=v,
                    command=lambda m=mid, var=v: self._mm_toggle(m, var)
                ).grid(row=i // 2, column=i % 2, sticky="w", padx=2)
            for mid in c.metamagic_known():
                nm, cost, desc, stack = consts.METAMAGIC[mid]
                ttk.Label(mm, text=f"· {nm}：{desc}", style="Dim.TLabel",
                          wraplength=500, justify="left").pack(anchor="w")
            inv = ttk.Frame(mm)
            inv.pack(fill="x", pady=(4, 0))
            ttk.Label(inv, text=f"先天魔法 剩 {c.innate_left()}/2 次",
                      foreground=GOLD2).pack(side="left")
            self.innate_var = tk.BooleanVar(value=c.innate_active)
            ttk.Checkbutton(inv, text="生效中", variable=self.innate_var,
                            command=self._innate_toggle).pack(side="left", padx=6)
            tip = "先天魔法 1 分钟内法术 DC +1、法术攻击有优势。"
            tip += "7 级起生效期间每个法术可叠 2 个超魔法"
            if c.level >= 20:
                tip += "；20 级奥术神化：每回合 1 个超魔法免费"
            ttk.Label(mm, text=tip, style="Dim.TLabel", wraplength=500,
                      justify="left").pack(anchor="w")

        # ===== 1.46 法师 18/20 级自选法术 =====
        if c.mastery_cap() or c.signature_cap():
            wz = ttk.Frame(body)
            wz.pack(fill="x", pady=(8, 0))
            ttk.Label(wz, text="18 / 20 级自选法术（始终准备，不占配额）",
                      style="H2.TLabel").pack(anchor="w")
            if c.mastery_cap():
                for lv in (1, 2):
                    cur = next((s for s in c.mastery_spells
                                if (c.r.spell(s) or {}).get("level") == lv), "")
                    self._pick_row(
                        wz, f"法术精通 · {lv} 环（随意施放，不耗环位）",
                        c.book_spells(lv), cur,
                        lambda sid, L=lv: self._mastery_set(L, sid))
            if c.signature_cap():
                for i in (0, 1):
                    cur = (c.signature_spells[i]
                           if i < len(c.signature_spells) else "")
                    self._pick_row(
                        wz, f"招牌法术 {i + 1}（3 环，短休回 1 次免费）",
                        c.book_spells(3), cur,
                        lambda sid, k=i: self._signature_set(k, sid))

        # ===== 1.47 传奇恩惠 (19 级起): 属性 +1 / 抗性 / 专精 在这里改 =====
        if c.boon_names():
            self._render_boons(body, c)

        # ===== 1.5 1 级职阶 (牧师 神圣职阶 / 德鲁伊 原始职阶) =====
        opts = c.order_options()
        if opts:
            of = ttk.Frame(body)
            of.pack(fill="x", pady=(10, 0))
            ttk.Label(of, text="1 级职阶", style="H2.TLabel").pack(anchor="w")
            self.order_var = tk.StringVar(value=c.order or "")
            for key, (nm, desc) in opts.items():
                ttk.Radiobutton(of, value=key, variable=self.order_var,
                                text=f"{nm} —— {desc}",
                                command=lambda k=key: self._order_set(k)
                                ).pack(anchor="w", pady=1)
            if not c.order:
                ttk.Label(of, text="※ 尚未选择职阶：护甲/武器熟练与戏法数还没加成。",
                          style="Dim.TLabel").pack(anchor="w", pady=(2, 0))

        # ===== 1.9 荒野变形 (德鲁伊 2 级起) =====
        if c.class_id == "druid" and c.level >= 2:
            from .. import wildshape as _ws
            wsf = ttk.Frame(body)
            wsf.pack(fill="x", pady=(10, 0))
            ttk.Label(wsf, text="野兽形态 · 荒野变形",
                      style="H2.TLabel").pack(anchor="w")
            wrow = ttk.Frame(wsf)
            wrow.pack(fill="x")
            cur = c.wild_shape()
            ttk.Label(wrow, foreground=GOLD2,
                      text=f"可选 {len(c.wild_shapes())} 种"
                           f" · 已知形态 {_ws.known_forms(c.level)} 种"
                           f" · 临时 HP {_ws.temp_hp(c.level, c.subclass)}"
                           + (f" · 当前：{cur['name']}" if cur
                              else " · 当前：本体")).pack(side="left")
            ttk.Button(wrow, text="形态", style="Mini.TButton",
                       command=self._wild_shape_open).pack(side="left", padx=6)
            ttk.Label(wsf, text="2024 规则：2 级不可带飞行/游泳，4 级解游泳、"
                                "8 级解飞行（大地结社只放宽 CR）。"
                                "此处按 CR 列出全部符合条件形态供参考。",
                      style="Dim.TLabel", wraplength=540,
                      justify="left").pack(anchor="w")
            if cur:
                ttk.Label(wsf, text=_ws.summary(cur), foreground=DIM,
                          wraplength=540,
                          justify="left").pack(anchor="w")
                for a in (cur.get("actions") or [])[:3]:
                    ttk.Label(wsf, text="  " + _ws.attack_line(a),
                              style="Dim.TLabel", wraplength=540,
                              justify="left").pack(anchor="w")

        # ===== 1.95 野兽伙伴 (游侠·驯兽师 3 级起) =====
        comp = c.companion()
        if comp:
            pf = ttk.Frame(body)
            pf.pack(fill="x", pady=(10, 0))
            ttk.Label(pf, text="原始伙伴 · 野兽伙伴",
                      style="H2.TLabel").pack(anchor="w")
            prow = ttk.Frame(pf)
            prow.pack(fill="x")
            cbox = ttk.Combobox(prow, width=22, state="readonly",
                                values=[o["name"] for o in comp["options"]])
            names = [o["name"] for o in comp["options"]]
            if comp["name"] in names:
                cbox.current(names.index(comp["name"]))
            cbox.pack(side="left")
            cbox.bind("<<ComboboxSelected>>",
                      lambda e, v=cbox: self._companion_set(v.get()))
            ttk.Button(prow, text="掷野兽打击", style="Mini.TButton",
                       command=self._companion_strike).pack(side="left",
                                                            padx=6)
            ttk.Label(pf, foreground=GOLD2,
                      text=f"当前：{comp['name']}  "
                           f"AC {comp['ac']}（{comp['ac_note']}）"
                           f" · HP {comp['hp']}（{comp['hp_formula']}）",
                      wraplength=540,
                      justify="left").pack(anchor="w")
            ttk.Label(pf, text=comp["strike"], foreground=TEXT,
                      wraplength=540,
                      justify="left").pack(anchor="w")
            ttk.Label(pf, text=comp["note"], style="Dim.TLabel",
                      wraplength=540,
                      justify="left").pack(anchor="w")

        # ===== 2. 子职 =====
        sf = ttk.Frame(body)
        sf.pack(fill="x", pady=(10, 0))
        info = c.r.sub_info(c.subclass) if c.subclass else None
        title = (f"子职 · {subclass_cn(c.subclass)}" if c.subclass
                 else "子职（3 级选择）")
        ttk.Label(sf, text=title, style="H2.TLabel").pack(anchor="w")
        if info:
            ttk.Label(sf, text=info["summary"], foreground=PURPLE,
                      wraplength=560, justify="left").pack(anchor="w")
            if c.subclass == "Circle of the Land":
                lf = ttk.Frame(sf)
                lf.pack(fill="x", pady=(3, 2))
                ttk.Label(lf, text="当前地形（长休时可改）",
                          style="Dim.TLabel").pack(side="left")
                lands = c.land_options()
                cb = ttk.Combobox(lf, state="readonly", width=18,
                                  values=[cn for _k, cn in lands])
                keys = [k for k, _cn in lands]
                cb.current(keys.index(c.land or "temperate")
                           if (c.land or "temperate") in keys else 0)
                cb.bind("<<ComboboxSelected>>",
                        lambda e, b=cb, ks=keys: self._land_set(ks[b.current()]))
                cb.pack(side="left", padx=6)
                ttk.Label(sf, text="该地形的法术始终准备，不占准备数："
                                   + "、".join(
                                       (c.r.spell(s) or {}).get("name", s)
                                       for s in c.fixed_spells()
                                       if c.fixed_source(s) == "子职"),
                          foreground=GOLD2, wraplength=540,
                          justify="left").pack(anchor="w")
            else:
                granted = [s for s in c.fixed_spells()
                           if c.fixed_source(s) == "子职"]
                if granted:
                    ttk.Label(sf, text="始终准备（不占准备数）：" + "、".join(
                                  (c.r.spell(s) or {}).get("name", s)
                                  for s in granted),
                              foreground=GOLD2, wraplength=500,
                              justify="left").pack(anchor="w")
            self._feature_rows(sf, c.subclass_features())
        else:
            hint = ("升级到 3 级时会弹出子职选择；下面是本职业 4 个方向，"
                    "先了解各自定位再决定。" if c.level < 3
                    else "已到 3 级但还没选子职 —— 下次升级时会让你选。")
            ttk.Label(sf, text=hint, style="Dim.TLabel", wraplength=560,
                      justify="left").pack(anchor="w")
            for en, cn, summary in c.r.sub_options(c.class_id):
                row = ttk.Frame(sf)
                row.pack(fill="x", pady=2)
                ttk.Label(row, text="• " + cn, foreground=GOLD2).pack(anchor="w")
                if summary:
                    ttk.Label(row, text="   " + summary, style="Dim.TLabel",
                              wraplength=540, justify="left").pack(anchor="w")

        # ===== 3. 职业特性 =====
        cf = ttk.Frame(body)
        cf.pack(fill="x", pady=(10, 0))
        ttk.Label(cf, text=f"{cls['name']} 职业特性", style="H2.TLabel"
                  ).pack(anchor="w")
        self._feature_rows(cf, c.class_features())

    def _render_boons(self, body, c):
        """传奇恩惠面板: 显示已持有的恩惠 + 需要玩家选择的项
        (属性 +1 / 抗性 2 选 / 专精 1 项)"""
        bf = ttk.Frame(body)
        bf.pack(fill="x", pady=(10, 0))
        ttk.Label(bf, text="传奇恩惠（19 级获得）",
                  style="H2.TLabel").pack(anchor="w")
        for name in c.boon_names():
            info = dict(consts.FEATS_BY_NAME.get(name) or {})
            eff = info.get("effects") or {}
            box = ttk.Frame(bf)
            box.pack(fill="x", pady=(4, 0))
            ttk.Label(box, text=feat_cn(name), foreground=GOLD2,
                      wraplength=540, justify="left").pack(anchor="w")
            # --- 属性 +1 (12 条共通) ---
            boost = eff.get("ability_boost") or {}
            if boost:
                allowed = boost.get("from") or list(ABILITIES)
                row = ttk.Frame(box)
                row.pack(anchor="w", pady=1)
                ttk.Label(row, text="属性 +1 →", style="Dim.TLabel",
                          ).pack(side="left")
                cb = ttk.Combobox(
                    row, state="readonly", width=14,
                    values=[f"{ABILITY_CN[a]}({a})" for a in allowed])
                cur_ab = c.boon_ability.get(name)
                if cur_ab in allowed:
                    cb.set(f"{ABILITY_CN[cur_ab]}({cur_ab})")
                    cb.current(allowed.index(cur_ab))
                cb.bind("<<ComboboxSelected>>",
                        lambda e, b=cb, n=name, al=allowed:
                        self._boon_ab_set(n, al[b.current()]))
                cb.pack(side="left", padx=4)
            # --- 抗性 2 选 (能量抗性之恩惠) ---
            rc = eff.get("resist_choice") or {}
            if rc:
                pool = [r for r in (rc.get("from") or [])
                        if r in consts.DAMAGE_TYPES_CN]
                limit = int(rc.get("count") or 0)
                ttk.Label(box, text=f"选 {limit} 种伤害抗性（每次长休可重选）:",
                          style="Dim.TLabel").pack(anchor="w", pady=(2, 0))
                grid = ttk.Frame(box)
                grid.pack(anchor="w")
                for i, r in enumerate(pool):
                    v = tk.BooleanVar(value=r in c.boon_resist)
                    ttk.Checkbutton(
                        grid, text=consts.damage_cn(r), variable=v,
                        command=lambda rt=r, var=v: self._boon_res_toggle(rt, var)
                    ).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 12))
            # --- 专精 1 项 (技艺之恩惠) ---
            if eff.get("expertise_choice"):
                cand = [s for s in sorted(c.skill_prof)
                        if s not in c.expertise and s not in c.boon_expertise]
                row = ttk.Frame(box)
                row.pack(anchor="w", pady=1)
                ttk.Label(row, text="专精 1 项 →", style="Dim.TLabel",
                          ).pack(side="left")
                names = ["（未选）"] + [
                    f"{c.r.skill_by_id[s]['name']}" for s in cand]
                cb = ttk.Combobox(row, state="readonly", width=16, values=names)
                cur = (c.boon_expertise[0] if c.boon_expertise else None)
                cb.current(cand.index(cur) + 1 if cur in cand else 0)
                cb.bind("<<ComboboxSelected>>",
                        lambda e, b=cb, cs=cand:
                        self._boon_exp_set(cs[b.current() - 1]
                                            if b.current() > 0 else None))
                cb.pack(side="left", padx=4)
            if info.get("desc"):
                ttk.Label(box, text=info["desc"], style="Dim.TLabel",
                          wraplength=540, justify="left").pack(anchor="w")

    def _pick_row(self, parent, label, spells, cur, on_pick):
        """一行「说明 + 下拉」, 用于法师的法术精通 / 招牌法术"""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, style="Dim.TLabel").pack(side="left")
        cb = ttk.Combobox(row, state="readonly", width=20,
                          values=["（未选）"] +
                          [f"{s['name']} {s['name_en']}" for s in spells])
        idx = 0
        for i, s in enumerate(spells):
            if s["id"] == cur:
                idx = i + 1
        cb.current(idx)
        cb.bind("<<ComboboxSelected>>",
                lambda e, b=cb: on_pick(spells[b.current() - 1]["id"]
                                        if b.current() > 0 else ""))
        cb.pack(side="left", padx=4)
        if not spells:
            cb.config(state="disabled")

    def _feature_rows(self, parent, rows):
        for lv, name, desc, unlocked in rows:
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=1)
            tag = f"L{lv}"
            head = f"{'●' if unlocked else '○'} {tag}  {name}"
            ttk.Label(row, text=head, foreground=(GOLD2 if unlocked else DIM),
                      font=(UI_FONT, 10, "bold" if unlocked else "normal")
                      ).pack(anchor="w")
            if desc:
                ttk.Label(row, text="     " + desc, style="Dim.TLabel",
                          wraplength=540, justify="left").pack(anchor="w")

    def _spend_hd(self, n=1):
        """花生命骰回血 (短休核心动作)"""
        c = self.char
        if not c:
            return
        if c.hit_dice_left() <= 0:
            messagebox.showinfo("提示", "生命骰已用尽，长休后恢复。", parent=self)
            return
        used, heal, detail = c.spend_hit_dice(n)
        if used:
            self.refresh()
            self._log_roll(f"🎲 花 {used} 颗生命骰: {'、'.join(detail)} "
                           f"→ 回复 {heal} HP (HP {c.hp_current}/{c.hp_max()})")

    def _toggle_rage(self, var):
        c = self.char
        if not c:
            return
        want = bool(var.get())
        if want and not c.raging:
            # 2024: 进入狂暴消耗 1 次狂暴 (结束不返还)
            rage = next((r for r in c.resources() if r["id"] == "rage"), None)
            if rage is not None and rage["left"] <= 0:
                var.set(False)
                messagebox.showinfo(
                    "狂暴已用尽", "狂暴次数已用完（长休恢复）。", parent=self)
                return
            c.res_spend("rage", 1)
        c.raging = want
        if c.raging:
            if c.concentration:
                c.concentration = None
            self._log_roll(f"🔥 进入狂暴 (消耗 1 次): 伤害 +{c.rage_damage()} · "
                           "物理伤害抗性 · 力量检定/豁免优势 · 无法专注")
        else:
            self._log_roll("◯ 结束狂暴")
        self.refresh()

    def _res_act(self, rid, act, n=1):
        c = self.char
        if not c:
            return
        pos = self.class_scroll.canvas.yview()[0]
        if act == "full":
            if rid is None:
                c.res_used = {}
            else:
                c.res_spend(rid, -999)
        elif act == "spend":
            c.res_spend(rid, n)
        else:
            c.res_spend(rid, -n)
        self._render_class_tab()
        self.class_scroll.canvas.yview_moveto(pos)
        self._status()

    def _font_create(self):
        """术士·术法源泉: 术法点 → 临时法术位"""
        c = self.char
        if not c or not c.font_can_use():
            return
        lv = 1
        if not getattr(self, "_selftest", False):
            lv = askinteger("术法源泉", "要兑换几环的法术位？(1–5)",
                            initialvalue=1, minvalue=1, maxvalue=5,
                            parent=self)
            if not lv:
                return
        ok, msg = c.font_create_slot(lv)
        self._render_class_tab()
        self._status()
        self._log_roll(("✨ " if ok else "⚠ ") + msg)

    def _font_burn(self):
        """术士·术法源泉: 法术位 → 等量术法点"""
        c = self.char
        if not c or not c.font_can_use():
            return
        have = sorted(lv for lv, n in c.spell_slots().items() if n > 0)
        if not have:
            return
        lv = have[0]
        if not getattr(self, "_selftest", False):
            lv = askinteger("术法源泉", f"要烧掉几环的法术位？({have[0]}–{have[-1]})",
                            initialvalue=have[0], minvalue=have[0],
                            maxvalue=have[-1], parent=self)
            if not lv:
                return
        ok, msg = c.font_burn_slot(lv)
        self._render_class_tab()
        self._status()
        self._log_roll(("✨ " if ok else "⚠ ") + msg)
