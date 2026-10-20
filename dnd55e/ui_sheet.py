import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)
from .util import ability_mod, mod_str

# 拆分后需要的内部依赖
from .consts import ABILITIES
from .theme import DIM, GOLD2, PURPLE, TEXT, UI_FONT


class AppSheet:
    def set_character(self, char):
        self.char = char
        self._show_view()
        self.refresh()
        # 建卡完成后立即写入固定目录, 下次启动可直接读到
        if not getattr(self, "_selftest", False) and char is not None:
            try:
                path = self._char_path()
                self._write_char(path)
                self._remember_last(path)
            except OSError:
                pass

    def refresh(self):
        c = self.char
        if not c:
            return
        cls = c.cls()
        sp = c.r.sp(c.species_id)
        bg = c.r.bg(c.background_id)

        # 英雄区
        sub = subclass_cn(c.subclass) if c.subclass else \
            ("(3级解锁子职)" if c.level < 3 else "(未选子职)")
        self.hero_name.config(text=f"❖ {c.name}")
        ordtxt = f"{c.order_label()} · " if c.order_label() else ""
        self.hero_sub.config(
            text=f"{cls['name']} {c.level} 级 · {ordtxt}{sub}   ｜   "
                 f"{sp['name']} · {bg['name']}")
        self.chip_ac.config(text=str(c.ac()))
        self.chip_init.config(text=mod_str(c.initiative()))
        self.chip_speed.config(text=f"{c.speed()}尺")
        self.chip_pb.config(text=mod_str(c.pb()))
        self.chip_pp.config(text=str(c.passive_perception()))

        # HP
        hp, mx = c.hp_current, c.hp_max()
        frac = hp / mx if mx else 0
        color = "#7bc47f" if frac > 0.5 else (
            "#e8c34a" if frac > 0.25 else "#ff8a75")
        self.hp_big.config(text=f"{hp} / {mx}", foreground=color)
        self.hp_bar.config(maximum=mx, value=hp)
        self.hp_temp_var.set(c.hp_temp)

        # XP
        self.xp_var.set(c.xp)
        self._xp_changed()

        # 属性卡
        for a in ABILITIES:
            self.ab_entries[a].set(c.score(a))
            self.ab_modlbls[a].config(
                text=mod_str(ability_mod(c.score(a))))
            prof = a in c.save_profs()
            self.ab_savelbls[a].config(
                text=f"豁免 {mod_str(c.save_mod(a))}",
                foreground=PURPLE if prof else DIM)

        # 护甲
        self.armor_cb.current(c.armor_index)
        self.shield_var.set(c.shield)
        self.tough_var.set(c.tough_feat)

        # 技能
        allow_exp = c.expertise_allowance() > 0
        for sid in self.skill_vars:
            prof = sid in c.skill_prof
            exp = sid in c.expertise
            self.skill_vars[sid].set(prof)
            self.skill_modlbls[sid].config(text=mod_str(c.skill_mod(sid)))
            self.skill_namelbls[sid].config(
                foreground=PURPLE if exp else (GOLD2 if prof else TEXT))
            self.skill_expbtns[sid].config(
                text="◆" if exp else "◇",
                state=("normal" if allow_exp else "disabled"))

        # 法术位
        for w in self.slots_frame.winfo_children():
            w.destroy()
        self.slots_widgets = {}
        slots = c.spell_slots()
        if not slots:
            self.slots_head.config(text="（该职业无施法能力）")
        else:
            cast = c.casting()
            tag = {"full": "全施法", "half": "半施法",
                   "pact": "契约魔法", "third": "1/3 施法"}.get(cast["type"], "")
            self.slots_head.config(
                text=f"{tag} · 施法属性 {cast['ability']} · "
                     f"法术DC {c.spell_dc()} · 法术命中 {mod_str(c.spell_attack())}")
            for i, (lv, mx2) in enumerate(sorted(slots.items())):
                used = c.spell_slots_used.get(lv, 0)
                box = ttk.Frame(self.slots_frame, style="Card.TFrame",
                                padding=8)
                box.grid(row=0, column=i, padx=4, pady=4)
                arc = lv in c.arcanum_levels()
                ttk.Label(box, text=(f"秘契 {lv} 环" if arc else f"{lv} 环"),
                          style="DimCard.TLabel").pack()
                pips = "●" * (mx2 - used) + "○" * used
                lbl = ttk.Label(box, text=pips, style="Card.TLabel",
                                font=(UI_FONT, 13, "bold"), foreground=GOLD2)
                lbl.pack()
                self.slots_widgets[lv] = lbl
                brow = ttk.Frame(box, style="Card.TFrame")
                brow.pack(pady=(3, 0))
                ttk.Button(brow, text="施法", width=4, style="Mini.TButton",
                           command=lambda l=lv: self._slot_spend(l)
                           ).pack(side="left", padx=1)
                ttk.Button(brow, text="恢复", width=4, style="Mini.TButton",
                           command=lambda l=lv: self._slot_restore(l)
                           ).pack(side="left", padx=1)

        # 护甲下拉: 未熟练项标 ✗ (用 index 取值, 加后缀不影响)
        self.armor_cb["values"] = [
            a[0] + ("" if c.has_armor_prof_at(i) else " ✗未熟练")
            for i, a in enumerate(consts.ARMORS)]
        self.armor_cb.current(c.armor_index)
        self.shield_var.set(c.shield)

        # 武器 / 战斗风格 / 魔法物品 / 加成明细
        # 武器下拉与护甲一致: 选项里直接标 ✓熟练 / ✗未熟练
        self.weapon_cb["values"] = ["（未装备）"] + [
            w[0] + (" ✓熟练" if c.has_weapon_prof(w[0]) else " ✗未熟练")
            for w in consts.WEAPONS]
        self.weapon_cb.set(self._weapon_label(c.weapon) if c.weapon
                           else "（未装备）")
        self.wmagic_var.set(c.weapon_magic)
        self.grip_var.set(bool(c.two_handed_grip))
        self.grip_chk.config(
            state=("normal" if c.is_versatile_weapon() else "disabled"))
        self.offhand_cb["values"] = ["（无）"] + [
            w[0] + ("" if "light" in consts.WEAPON_PROPS.get(w[0], [])
                    else " ✗非轻型")
            for w in consts.WEAPONS]
        self.offhand_cb.set(c.offhand_weapon or "（无）")
        if c.weapon:
            prof = "✓熟练" if c.has_weapon_prof() else "✗未熟练"
            txt = (f"攻击 {mod_str(c.attack_bonus())} · 伤害 "
                   f"{c.damage_dice()}{mod_str(c.damage_bonus())} "
                   f"{c.damage_type()} · {prof}")
            alt = consts.WEAPON_VERSATILE.get(c.weapon)
            if alt:
                txt += ("（双手持用）" if c.two_handed_grip
                        else f"（双手 {alt}）")
            if c.heavy_penalty():
                txt += " · ⚠重武器劣势"
            if c.is_ranged_weapon():
                txt += " · 远程"
            if c.offhand_weapon:
                if c.offhand_can_dual():
                    txt += (f"　｜　副手 {c.offhand_weapon} "
                            f"攻击 {mod_str(c.offhand_attack_bonus())} · "
                            f"伤害 {c.offhand_damage_dice()}"
                            f"{mod_str(c.offhand_damage_bonus())}（附赠动作）")
                else:
                    txt += f"　｜　⚠ {c.offhand_note()}"
            self.atk_lbl.config(text=txt)
        else:
            self.atk_lbl.config(
                text=f"徒手打击 · 攻击 {mod_str(c.attack_bonus())} · "
                     f"伤害 {c.damage_dice()}{mod_str(c.damage_bonus())} 钝击")
        if c.fighting_style in consts.FIGHTING_STYLES:
            nm, note, _ = consts.FIGHTING_STYLES[c.fighting_style]
            self.style_cb.set(nm)
            self.style_note.config(text=note)
        else:
            self.style_cb.set("（无）")
            self.style_note.config(text="")
        # 战斗风格是职业特性: 非战士/圣武士/游侠 (或等级不够) 锁死
        if c.can_fighting_style():
            self.style_cb.config(
                state="readonly",
                values=["（无）"] + [v[0] for v in consts.FIGHTING_STYLES.values()])
        else:
            need = c.style_level_need()
            why = (f"仅战士(1级)/圣武士(2级)/游侠(2级) 拥有"
                   if need is None else f"{need} 级起解锁")
            self.style_cb.config(state="disabled",
                                 values=["（本职业没有战斗风格）"])
            self.style_cb.set("（本职业没有战斗风格）")
            self.style_note.config(text=why)
        for iid, v in self.item_vars.items():
            v.set(iid in c.items)
        self.bonus_text.config(state="normal")
        self.bonus_text.delete("1.0", "end")
        bonus_lines = c.bonus_breakdown()
        ac, ac_notes = c.ac_breakdown()
        self.bonus_text.insert("1.0", "\n".join(
            [f"AC {ac} = " + " + ".join(ac_notes),
             f"先攻 {mod_str(c.initiative())} · 速度 {c.speed()} 尺 · "
             f"HP {c.hp_max()}",
             f"负重上限 {c.carry_capacity()[0]} 磅 "
             f"(推/拉/举 {c.carry_capacity()[1]} 磅) · "
             f"生命骰 d{c.hit_die()} {c.hit_dice_left()}/{c.hit_dice_max()}"]
            + ([""] + ["• " + x for x in bonus_lines] if bonus_lines
               else ["", "（当前无额外加成来源）"])))
        self.bonus_text.config(state="disabled")
        self._spell_refresh()

        # 专长 / 武器专精
        self.feat_list.delete(0, "end")
        for i, ft in enumerate(self._feat_names()):
            self.feat_list.insert("end", self._feat_display(ft, i))
        self.mastery_list.delete(0, "end")
        for wname in c.weapon_mastery:
            for w in consts.WEAPONS:
                if w[0] == wname:
                    extra = (f" · DC {c.mastery_dc(wname)}"
                             if w[3] in ("Topple", "Push") else "")
                    self.mastery_list.insert(
                        "end", f"{wname} · {w[2]} · {mastery_cn(w[3])}{extra}")
                    break
        # 种族特性 / 背景
        lines = [f"【{sp['name']}】 体型 {size_cn(sp['size'])} · "
                 f"速度 {sp.get('speed', 30)} 尺"]
        lines += ["• " + t for t in sp["traits"]]
        lines += ["", f"【背景·{bg['name']}】 起源专长: {feat_cn(bg['origin_feat'])}",
                  f"专长效果: {feat_desc(bg['origin_feat']).split(': ', 1)[-1]}"]
        lines += ["", "【熟练项】"] + ["• " + x for x in c.proficiency_report()]
        self.trait_text.config(state="normal")
        self.trait_text.delete("1.0", "end")
        self.trait_text.insert("1.0", "\n".join(lines))
        self.trait_text.config(state="disabled")
        self._render_class_tab()

        # 语言 / 装备 / 备注
        self.lang_entry.delete(0, "end")
        self.lang_entry.insert(0, c.languages)
        if self.eq_text.get("1.0", "end").strip() != c.equipment.strip():
            self.eq_text.delete("1.0", "end")
            self.eq_text.insert("1.0", c.equipment)
        if self.note_text.get("1.0", "end").strip() != c.notes.strip():
            self.note_text.delete("1.0", "end")
            self.note_text.insert("1.0", c.notes)

        # 状态 / 力竭
        for cond, v in self.cond_vars.items():
            v.set(cond.replace("(另计)", "") in c.conditions)
        self.exh_var.set(c.exhaustion)
        self._exh_warn_text()
        self.death_lbl.config(
            text=f"✓{c.death_success} ✗{c.death_fail}",
            foreground=("#e05c4d" if c.is_dying else DIM))
        conc = c.r.spell(c.concentration) if c.concentration else None
        self.conc_lbl.config(
            text=(f"专注: {conc['name']} (体质 {mod_str(c.save_mod('CON'))})"
                  if conc else "专注: 无"))
        self._status()

    def _feat_names(self):
        """原始专长名列表 (英文键), 显示时用 feat_cn 美化"""
        c = self.char
        names = []
        for asi in c.asi_history:
            if asi.get("type") == "feat":
                names.append(asi["name"])
        names += c.feats
        bg = c.r.bg(c.background_id)
        names.insert(0, bg["origin_feat"])
        return names

    def _feat_display(self, raw, idx):
        prefix = "[背景] " if idx == 0 else ""
        return prefix + feat_cn(raw)

    # ---- 职业页: 资源 / 特性 / 子职 ----

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
            from . import wildshape as _ws
            wsf = ttk.Frame(body)
            wsf.pack(fill="x", pady=(10, 0))
            ttk.Label(wsf, text="野兽形态 · 荒野变形",
                      style="H2.TLabel").pack(anchor="w")
            wrow = ttk.Frame(wsf)
            wrow.pack(fill="x")
            cur = c.wild_shape()
            ttk.Label(wrow, foreground=GOLD2,
                      text=f"可选 {len(c.wild_shapes())} 种"
                           + (f" · 当前：{cur['name']}" if cur
                              else " · 当前：本体")).pack(side="left")
            ttk.Button(wrow, text="形态", style="Mini.TButton",
                       command=self._wild_shape_open).pack(side="left", padx=6)
            if cur:
                ttk.Label(wsf, text=_ws.summary(cur), foreground=DIM,
                          wraplength=540,
                          justify="left").pack(anchor="w")
                for a in (cur.get("actions") or [])[:3]:
                    ttk.Label(wsf, text="  " + _ws.attack_line(a),
                              style="Dim.TLabel", wraplength=540,
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

    @staticmethod
    def _reset_text(r):
        short = {0: "短休不回", 1: "短休回 1", "all": "短休全回"}
        s = short.get(r.get("short"), "")
        if r.get("short_after_level"):
            s += f"（{r['short_after_level']} 级起全回）"
        return f"{s} · 长休全回"

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

    def _on_feat_select(self, _e=None):
        sel = self.feat_list.curselection()
        if not sel:
            return
        names = self._feat_names()
        if sel[0] < len(names):
            self.feat_info.config(text=feat_desc(names[sel[0]]))

    def _status(self):
        c = self.char
        if not c:
            return
        slots = c.spell_slots()
        sl = ", ".join(
            f"{lv}环 {slots[lv] - c.spell_slots_used.get(lv, 0)}/{slots[lv]}"
            for lv in sorted(slots)) or "无施法"
        self.status.config(
            text=f"{c.name} · {c.cls()['name']} {c.level}级 · "
                 f"HP {c.hp_current}/{c.hp_max()} · AC {c.ac()} · "
                 f"熟练{mod_str(c.pb())} · 法术位: {sl}"
                 + (f" · ☠ 濒死 ✗{c.death_fail}/3 ✓{c.death_success}/3"
                    if c.is_dying else ""))

    # ---- 掷骰 (结果进日志, 不弹窗) ----
