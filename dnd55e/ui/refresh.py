"""整卡刷新: 英雄区 / HP / XP / 属性卡 / 护甲 / 技能 / 法术位 / 装备 / 专长。"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, util
from ..consts import (ABILITIES, feat_cn, feat_desc, mastery_cn, size_cn,
                      subclass_cn, tool_cn)
from ..theme import DIM, GOLD2, PURPLE, TEXT, UI_FONT
from ..util import ability_mod, mod_str


class RefreshMixin():
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

    @staticmethod
    def _reset_text(r):
        short = {0: "短休不回", 1: "短休回 1", "all": "短休全回"}
        s = short.get(r.get("short"), "")
        if r.get("short_after_level"):
            s += f"（{r['short_after_level']} 级起全回）"
        return f"{s} · 长休全回"
