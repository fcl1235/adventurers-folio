import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)
from .util import ability_mod, mod_str

# 拆分后需要的内部依赖
import random
from .consts import ABILITIES, ABILITY_CN
from .dialogs import (FeatPickerDialog, MetamagicDialog, SpellbookDialog,
                      WildShapeDialog)
from .rules import Rules
from .theme import BG, GOLD2
from .util import roll_dice, roll_dice_reroll, spell_detail


class AppActions:
    def _log_roll(self, text):
        self.roll_log.insert(0, text)
        if self.roll_log.size() > 60:
            self.roll_log.delete(60, "end")
        self.status.config(text="🎲 " + text)

    def _d20_log(self, label, mod, floor_value=None):
        c = self.char
        raw = random.randint(1, 20)
        total = raw + c.d20_mod_total(mod)
        floor = ""
        if floor_value is not None and total < floor_value:
            floor = f"（不屈之力→{floor_value}）"
            total = floor_value
        ex = (f"（修正中已含力竭 -{2 * c.exhaustion}）"
              if c.exhaustion else "")
        crit = " 🎯大成功!" if raw == 20 else (" 💀大失败" if raw == 1 else "")
        self._log_roll(
            f"{label}: d20={raw} {mod_str(mod)}{ex} ⇒ {total}{floor}{crit}")

    def _roll_check(self, ab):
        if not self.char:
            return
        floor = (self.char.score("STR")
                 if self.char.indomitable_might(ab) else None)
        self._d20_log(f"{ABILITY_CN[ab]}({ab})检定",
                      self.char.ability_check_mod(ab), floor)

    def _roll_save(self, ab):
        if not self.char:
            return
        floor = (self.char.score("STR")
                 if self.char.indomitable_might(ab) else None)
        self._d20_log(f"{ABILITY_CN[ab]}豁免", self.char.save_mod(ab), floor)

    def _roll_init(self):
        if not self.char:
            return
        self._d20_log("先攻", self.char.initiative())

    def _roll_skill(self, sid):
        """技能检定 —— 游荡者 7 级起「可靠天赋」: d20≤9 按 10 计"""
        c = self.char
        if not c:
            return
        sk = self.rules.skill_by_id[sid]
        mod = c.skill_mod(sid)
        raw = random.randint(1, 20)
        note = ""
        if c.reliable_talent(sid) and raw <= 9:
            note = f"（可靠天赋 {raw}→10）"
            raw = 10
        total = raw + c.d20_mod_total(mod)
        ex = (f"（修正中已含力竭 -{2 * c.exhaustion}）"
              if c.exhaustion else "")
        crit = " 🎯大成功!" if raw == 20 else ""
        self._log_roll(f"{sk['name']}检定: d20={raw}{note} "
                       f"{mod_str(mod)}{ex} ⇒ {total}{crit}")

    def _quick_die(self, n):
        self._log_roll(f"d{n} ⇒ {random.randint(1, n)}")

    # ---- 事件处理 ----

    def _score_edited(self):
        """手动微调属性 — 常规上限 20; 20 级野蛮人/武僧的压轴属性上限 25"""
        c = self.char
        if not c:
            return
        capped = False
        for a in ABILITIES:
            try:
                val = self.ab_entries[a].get()
            except tk.TclError:
                continue
            cap = c.ability_cap(a)
            if val > cap:
                val = cap
                capped = True
            delta = val - c.score(a)
            if delta:
                c.base_scores[a] = max(1, min(20, c.base_scores[a] + delta))
        self.refresh()
        if capped:
            messagebox.showinfo(
                "属性上限",
                "2024 规则：基础值 + 背景 + ASI 合计上限为 20。\n"
                "20 级野蛮人（力/体）与武僧（敏/感）经职业特性可到 25；\n"
                "魔法物品的「设定值」（如力量腰带 21）也可超过 20。",
                parent=self)

    def _hp_add(self, n):
        if not self.char:
            return
        c = self.char
        absorbed = 0
        if n < 0:
            # 2024: 临时生命先吸收伤害, 剩余才扣本体 HP
            dmg = -n
            if c.hp_temp > 0:
                absorbed = min(c.hp_temp, dmg)
                c.hp_temp -= absorbed
                dmg -= absorbed
            c.hp_current = max(0, c.hp_current - dmg)
        else:
            c.hp_current = max(0, min(c.hp_max(), c.hp_current + n))
        self.refresh()
        if n < 0:
            note = f"（临时生命吸收 {absorbed}）" if absorbed else ""
            self._log_roll(f"受到伤害 {abs(n)}{note} → "
                           f"HP {c.hp_current}/{c.hp_max()}"
                           + (f" · 临时 {c.hp_temp}" if c.hp_temp else ""))
        elif n > 0:
            self._log_roll(f"恢复生命 {n} → HP {c.hp_current}/{c.hp_max()}")

    def _hp_temp_changed(self):
        if not self.char:
            return
        try:
            self.char.hp_temp = max(0, self.hp_temp_var.get())
        except tk.TclError:
            pass

    def _skill_toggled(self, sid):
        c = self.char
        if not c:
            return
        sk = self.rules.skill_by_id[sid]["name"]
        bg, auto = c.bg_skills(), set(c.auto_skills())
        pool = c.class_skill_pool()
        on = self.skill_vars[sid].get()
        # 背景/种族/专长给的熟练不能在这里取消
        if sid in bg or sid in auto or sid in c.bonus_skills:
            self.skill_vars[sid].set(True)
            messagebox.showinfo(
                "固定熟练", f"「{sk}」来自背景/种族/专长，不能在这里取消。",
                parent=self)
            return
        # 只能增删本职业技能列表里的项
        if sid not in pool:
            self.skill_vars[sid].set(sid in c.skill_prof)
            messagebox.showinfo(
                "不在职业列表",
                f"「{sk}」不在 {c.cls()['name']} 的技能列表里。\n"
                "专长/子职给的熟练会直接计入，但不能在这里手动增删。", parent=self)
            return
        if on:
            if c.class_skill_picks() >= c.skill_quota():
                self.skill_vars[sid].set(False)
                messagebox.showwarning(
                    "已达上限",
                    f"{c.cls()['name']} 只能选 {c.skill_quota()} 项技能"
                    f"（当前已选 {c.class_skill_picks()} 项）。\n"
                    "想换别的请先取消一项。", parent=self)
                return
            c.skill_prof.add(sid)
        else:
            c.skill_prof.discard(sid)
            c.expertise.discard(sid)
        self.refresh()

    def _toggle_expertise(self, sid):
        c = self.char
        if not c:
            return
        allow = c.expertise_allowance()
        if allow <= 0:
            messagebox.showinfo(
                "专精",
                f"{c.cls()['name']} 没有「专精 Expertise」特性。\n"
                "（游荡者 1 级、吟游诗人 2 级、游侠 2 级才有）", parent=self)
            return
        if sid in c.expertise:
            c.expertise.discard(sid)
        elif sid not in c.skill_prof:
            messagebox.showinfo("提示", "只有已熟练的技能才能设为专精 (Expertise)",
                                parent=self)
            return
        elif len(c.expertise) >= allow:
            messagebox.showwarning(
                "专精已满",
                f"当前等级最多 {allow} 项专精（随等级提升："
                f"游荡者 6 级 +2、吟游诗人 9 级 +2、游侠 9 级 +2）。",
                parent=self)
            return
        else:
            c.expertise.add(sid)
        self.refresh()

    def _armor_changed(self):
        c = self.char
        if not c:
            return
        c.armor_index = self.armor_cb.current()
        c.shield = self.shield_var.get()
        self.refresh()

    def _tough_changed(self):
        c = self.char
        if not c:
            return
        c.tough_feat = self.tough_var.get()
        self.refresh()

    def _slot_spend(self, lv):
        c = self.char
        if not c:
            return
        mx = c.spell_slots().get(lv, 0)
        used = c.spell_slots_used.get(lv, 0)
        if used >= mx:
            messagebox.showwarning("提示", f"{lv} 环法术位已用尽 (长休恢复)",
                                   parent=self)
            return
        c.spell_slots_used[lv] = used + 1
        self._log_roll(f"施放法术 → {lv}环位 剩 {mx - used - 1}/{mx}")
        self.refresh()

    def _slot_restore(self, lv):
        c = self.char
        if not c:
            return
        used = c.spell_slots_used.get(lv, 0)
        if used > 0:
            c.spell_slots_used[lv] = used - 1
            self.refresh()

    def _cond_toggled(self, cond):
        c = self.char
        if not c:
            return
        key = cond.replace("(另计)", "")
        if self.cond_vars[cond].get():
            c.conditions.add(key)
        else:
            c.conditions.discard(key)
        self._status()

    def _ability_hint(self, ab):
        self.ab_hint.config(
            text=f"{ABILITY_CN[ab]} ({ab}): {consts.ABILITY_DESC.get(ab, '')}",
            foreground=GOLD2)

    def _skill_hover(self, sid):
        sk = self.rules.skill_by_id[sid]
        c = self.char
        extra = ""
        if c:
            extra = f" · 当前 {mod_str(c.skill_mod(sid))}"
            if sid in c.expertise:
                extra += " (专精 ×2)"
            elif sid in c.skill_prof:
                extra += " (熟练)"
        self.skill_hint.config(
            text=f"{sk['name']} ({ABILITY_CN[sk['ability']]}) —— "
                 f"{consts.SKILL_DESC.get(sid, '')}{extra}",
            foreground=GOLD2)

    def _cond_hint(self, cond):
        self.cond_hint.config(
            text=f"{cond}: {consts.CONDITION_DESC.get(cond, '')}", foreground=GOLD2)

    def _exh_warn_text(self):
        c = self.char
        if not c or c.exhaustion == 0:
            self.exh_warn.config(text="")
        elif c.exhaustion >= 6:
            self.exh_warn.config(text="☠ 力竭 6 级 —— 角色死亡!")
        else:
            self.exh_warn.config(
                text=f"当前惩罚: d20 检定 -{2 * c.exhaustion}, "
                     f"速度 -{5 * c.exhaustion} 尺")

    def _exh_changed(self):
        c = self.char
        if not c:
            return
        c.exhaustion = max(0, min(6, self.exh_var.get()))
        self._exh_warn_text()
        if c.exhaustion >= 6:
            messagebox.showwarning("警告", "力竭 6 级 —— 角色死亡!", parent=self)
        self._status()

    def _death_save(self):
        """死亡豁免 (2024): 10+ 成功, 9- 失败; 20 直接回 1 HP; 1 记 2 次失败"""
        c = self.char
        if not c:
            return
        if not c.is_dying:
            messagebox.showinfo("提示", "HP 大于 0 时不需要死亡豁免。", parent=self)
            return
        raw = random.randint(1, 20)
        if raw == 20:
            c.hp_current = 1
            c.death_success = c.death_fail = 0
            msg = "d20=20 → 恢复 1 HP，立刻脱离濒死"
        elif raw == 1:
            c.death_fail = min(3, c.death_fail + 2)
            msg = "d20=1 → 记 2 次失败"
        elif raw >= 10:
            c.death_success = min(3, c.death_success + 1)
            msg = f"d20={raw} → 成功 +1"
        else:
            c.death_fail = min(3, c.death_fail + 1)
            msg = f"d20={raw} → 失败 +1"
        if c.death_success >= 3:
            msg += " · 已稳定（昏迷但不再恶化）"
        if c.death_fail >= 3:
            msg += " · ☠ 三次失败，角色死亡"
        self.refresh()
        self._log_roll("💀 死亡豁免: " + msg)

    def _death_reset(self):
        c = self.char
        if not c:
            return
        c.death_success = c.death_fail = 0
        self.refresh()
        self._log_roll("死亡豁免计数已重置")

    def _conc_check(self):
        """受伤后的专注检定: DC = max(10, 伤害/2), 掷体质豁免"""
        c = self.char
        if not c:
            return
        if not c.concentration:
            messagebox.showinfo("提示", "当前没有正在专注的法术。", parent=self)
            return
        if getattr(self, "_selftest", False):
            dmg = 10
        else:
            dmg = askinteger("专注检定", "受到的伤害值（用于算 DC）:",
                             parent=self, minvalue=0, maxvalue=9999,
                             initialvalue=10)
            if dmg is None:
                return
        dc = c.concentration_dc(dmg)
        mod = c.save_mod("CON")
        raw = random.randint(1, 20)
        tot = raw + c.d20_mod_total(mod)
        ok = raw == 20 or (raw != 1 and tot >= dc)
        s = c.r.spell(c.concentration)
        if not ok:
            c.concentration = None
        self.refresh()
        self._log_roll(
            f"🧠 专注检定 (DC {dc}): d20={raw} {mod_str(mod)} ⇒ {tot} "
            f"{'保持' if ok else '中断'} · {s['name'] if s else ''}")

    def _xp_changed(self):
        c = self.char
        if not c:
            return
        try:
            c.xp = max(0, self.xp_var.get())
        except tk.TclError:
            return
        if c.level >= 20:
            self.xp_hint.config(text="已满级 (20)")
            self.xp_bar.config(maximum=1, value=1)
            return
        base = self._xp_th[c.level]
        nxt = self._xp_th[c.level + 1]
        span = max(1, nxt - base)
        self.xp_bar.config(maximum=span,
                           value=max(0, min(span, c.xp - base)))
        if c.xp >= nxt:
            self.xp_hint.config(
                text=f"⚑ 可升至 {c.level + 1} 级! → 点工具栏「⬆ 升级」")
        else:
            self.xp_hint.config(text=f"(下一级 {nxt} XP, 还差 {nxt - c.xp})")

    def _add_feat(self):
        c = self.char
        if not c:
            return
        dlg = FeatPickerDialog(self, c, selftest=self._selftest)
        if not self._selftest:
            self.wait_window(dlg)
        if dlg.result:
            c.feats.append(dlg.result)
            if "tough" in dlg.result.lower() or "坚忍" in dlg.result:
                c.tough_feat = True
            self.refresh()

    def _del_feat(self):
        c = self.char
        if not c:
            return
        sel = self.feat_list.curselection()
        if not sel:
            return
        names = self._feat_names()
        name = names[sel[0]] if sel[0] < len(names) else None
        if name in c.feats:
            c.feats.remove(name)
        self.refresh()

    def _edit_mastery(self):
        c = self.char
        if not c:
            return
        pool = Rules.class_mastery_pool(c.cls())
        n = c.mastery_count()
        if n == 0:
            messagebox.showinfo(
                "提示",
                f"{c.cls()['name']} 没有「武器专精 Weapon Mastery」特性，不能选。\n"
                "（野蛮人/战士/圣武士/游侠/游荡者才有；也可用 Weapon Master 专长）",
                parent=self)
            return
        win = tk.Toplevel(self)
        win.title(f"编辑武器专精 (选 {n} 件, 长休可换)")
        win.geometry("560x520")
        win.transient(self)
        win.configure(bg=BG)
        try:
            win.grab_set()
        except tk.TclError:
            pass
        f = ttk.Frame(win, padding=10)
        f.pack(fill="both", expand=True)
        vars_ = {}
        for i, w in enumerate(pool):
            wname, cat, dmg, mst = w[0], w[1], w[2], w[3]
            v = tk.BooleanVar(value=wname in c.weapon_mastery)
            vars_[wname] = v
            ttk.Checkbutton(f, text=f"{wname} · {dmg} · {mastery_cn(mst)}",
                            variable=v).grid(row=i // 2, column=i % 2,
                                             sticky="w", padx=8, pady=2)

        def ok():
            chosen = [w for w, v in vars_.items() if v.get()]
            if len(chosen) != n:
                messagebox.showwarning(
                    "提示", f"须恰好选择 {n} 件 (已选 {len(chosen)})", parent=win)
                return
            c.weapon_mastery = chosen
            win.destroy()
            self.refresh()

        ttk.Button(f, text="确认", style="Gold.TButton",
                   command=ok).grid(columnspan=2, pady=8)

    # ---- 装备 / 攻击 / 魔法物品 ----

    WEP_SUFFIX = (" ✓熟练", " ✗未熟练")

    def _weapon_label(self, name):
        """下拉里显示的武器名 + 熟练标记"""
        c = self.char
        if not c or not name:
            return "（未装备）"
        return name + (" ✓熟练" if c.has_weapon_prof(name) else " ✗未熟练")

    @classmethod
    def _weapon_strip(cls, label):
        for suf in cls.WEP_SUFFIX:
            if label.endswith(suf):
                return label[:-len(suf)]
        return label

    def _weapon_changed(self):
        c = self.char
        if not c:
            return
        name = self._weapon_strip(self.weapon_cb.get()).strip()
        if name in {w[0] for w in consts.WEAPONS}:
            if not c.has_weapon_prof(name):     # 未熟练: 允许但明确警告
                messagebox.showwarning(
                    "未熟练武器",
                    f"{c.cls()['name']} 不熟练「{name}」。\n"
                    "可以装备，但攻击检定不加熟练加值，"
                    "部分特性（如偷袭）也可能无法使用。", parent=self)
            c.weapon = name
        else:
            c.weapon = ""
        if not c.is_versatile_weapon():
            c.two_handed_grip = False
        try:
            c.weapon_magic = max(0, min(3, int(self.wmagic_var.get())))
        except (tk.TclError, ValueError):
            pass
        self.refresh()

    def _order_set(self, key):
        """1 级职阶 (牧师/德鲁伊): 立即重算护甲/武器熟练与戏法数"""
        c = self.char
        if not c:
            return
        c.order = key if key in (c.order_options() or {}) else None
        self.refresh()

    def _land_set(self, key):
        """大地结社地形 (长休时可改): 换一套「始终准备」的法术"""
        c = self.char
        if not c:
            return
        ok = {k for k, _ in c.land_options()}
        c.land = key if key in ok else "temperate"
        c.prune_fixed()
        self.refresh()

    def _wild_shape_open(self):
        """荒野变形: 选野兽形态 (只记录形态, 不动本体数值)"""
        c = self.char
        if not c or c.class_id != "druid":
            return
        dlg = WildShapeDialog(self, c, selftest=self._selftest)
        if not self._selftest:
            self.wait_window(dlg)
        if dlg.result is not None:
            self.refresh()

    # ---- 超魔法 / 先天魔法 / 法师自选法术 ----

    def _mm_toggle(self, mid, var):
        c = self.char
        if not c:
            return
        cur = [m for m in c.metamagic if m in consts.METAMAGIC]
        if var.get():
            if mid in cur:
                return
            if len(cur) >= c.metamagic_cap():
                var.set(False)
                messagebox.showinfo(
                    "超魔法已满",
                    f"最多同时掌握 {c.metamagic_cap()} 个超魔法"
                    f"（10 级 / 17 级各会再 +2）。\n先取消一个再选。",
                    parent=self)
                return
            cur.append(mid)
        else:
            cur = [m for m in cur if m != mid]
        c.metamagic = cur
        self.refresh()

    def _innate_toggle(self):
        c = self.char
        if not c:
            return
        if c.innate_active:
            c.innate_off()
        else:
            ok, msg = c.innate_on()
            if not ok:
                if hasattr(self, "innate_var"):
                    self.innate_var.set(False)
                messagebox.showinfo("提示", msg, parent=self)
                return
        self.refresh()

    def _mastery_set(self, lv, sid):
        """法师 18 级法术精通: 1 环 / 2 环各 1 个"""
        c = self.char
        if not c:
            return
        keep = [s for s in c.mastery_spells
                if (c.r.spell(s) or {}).get("level") != lv]
        if sid:
            keep.append(sid)
        c.mastery_spells = keep[:2]
        c.prune_fixed()
        self.refresh()

    def _signature_set(self, idx, sid):
        """法师 20 级招牌法术: 2 个 3 环"""
        c = self.char
        if not c:
            return
        cur = [s for s in c.signature_spells if s]
        if idx == 0:
            new = ([sid] if sid else []) + cur[1:]
        else:
            new = cur[:1] + ([sid] if sid else [])
        c.signature_spells = [s for s in new if s][:2]
        c.signature_used = [s for s in c.signature_used
                            if s in c.signature_spells]
        c.prune_fixed()
        self.refresh()

    def _grip_changed(self):
        """两用武器: 单手 (1d8) / 双手 (1d10) 切换"""
        c = self.char
        if not c:
            return
        c.two_handed_grip = bool(self.grip_var.get()) \
            and c.is_versatile_weapon()
        self.refresh()

    def _style_changed(self):
        c = self.char
        if not c:
            return
        if not c.can_fighting_style():
            c.fighting_style = None
            self.refresh()
            messagebox.showinfo(
                "战斗风格",
                "战斗风格是战士(1级)/圣武士(2级)/游侠(2级) 的职业特性，"
                f"{c.cls()['name']} 不能选择。", parent=self)
            return
        txt = self.style_cb.get()
        key = next((k for k, v in consts.FIGHTING_STYLES.items() if v[0] == txt), None)
        if key is None and c.fighting_style:
            c.fighting_style = None          # 选「（无）」= 取消
        elif key:
            c.fighting_style = key
        self.refresh()

    def _item_changed(self, iid):
        c = self.char
        if not c:
            return
        if self.item_vars[iid].get():
            if iid not in c.items:
                # 同调上限 3 件 (2024): 只有「需同调」的物品占名额
                need = consts.ITEMS_BY_ID.get(iid, {}).get("attune", True)
                if need and len(c.attuned_items()) >= c.attunement_cap():
                    self.item_vars[iid].set(False)
                    it = consts.ITEMS_BY_ID.get(iid, {})
                    messagebox.showwarning(
                        "同调已满",
                        f"同时最多同调 {c.attunement_cap()} 件魔法物品"
                        f"（已同调 {len(c.attuned_items())} 件）。\n"
                        f"「{it.get('name', iid)}」需要同调，请先取消一件。",
                        parent=self)
                    return
                c.items.append(iid)
        elif iid in c.items:
            c.items.remove(iid)
        self.refresh()

    def _item_hint(self, it):
        # 新物品只有 desc、没有 note (note 是旧 12 条的短摘要), 两者取其一
        note = it.get("note") or it.get("desc", "")
        if len(note) > 76:                # 提示行固定 2 行高, 超长截断防止撑开
            note = note[:75] + "…"
        self.item_hint.config(text=f"{it['name']} —— {note}",
                              foreground=GOLD2)

    def _attack_roll(self):
        c = self.char
        if not c:
            return
        label = c.weapon or "徒手打击"
        note = ""
        if c.heavy_penalty():
            note = "　⚠ 重武器且属性不足 13：本次攻击带劣势"
        elif c.is_ranged_weapon():
            note = "　（5 尺内有敌人 / 超出常规射程时带劣势）"
        n = c.attacks_per_action()
        if n <= 1:
            self._d20_log(f"攻击·{label}{note}", c.attack_bonus())
            return
        # 额外攻击: 一次投 n 个 d20, 分别结算命中
        mod = c.attack_bonus()
        parts, crit = [], 0
        for i in range(n):
            raw = random.randint(1, 20)
            tot = raw + c.d20_mod_total(mod)
            crit += 1 if raw == 20 else 0
            parts.append(f"#{i + 1} d20={raw}⇒{tot}")
        self._log_roll(
            f"攻击·{label} ×{n} 次 (命中 {mod_str(mod)}){note}: "
            + " | ".join(parts) + (f" · 🎯暴击 {crit}" if crit else ""))

    def _offhand_changed(self):
        c = self.char
        if not c:
            return
        name = self.offhand_cb.get().replace("（无）", "").strip()
        c.offhand_weapon = name if name in {w[0] for w in consts.WEAPONS} else ""
        self.refresh()

    def _offhand_attack(self):
        """双武器战斗: 附赠动作, 用另一把轻型武器再打一下"""
        c = self.char
        if not c:
            return
        if not c.offhand_weapon:
            messagebox.showinfo("提示", "先在「副手」里选一把武器。", parent=self)
            return
        if not c.offhand_can_dual():
            messagebox.showwarning("提示", c.offhand_note(), parent=self)
            return
        self._d20_log(f"攻击·副手 {c.offhand_weapon}（附赠动作）",
                      c.offhand_attack_bonus())
        expr = c.offhand_damage_dice()
        if c.offhand_damage_bonus():
            expr += mod_str(c.offhand_damage_bonus())
        total, detail = roll_dice(expr)
        tip = ""
        if c.fighting_style != "two_weapon":
            tip = "（副手不加属性调整值；双武器战斗风格才加）"
        self._log_roll(f"⚔ 副手伤害: {detail} = {total} "
                       f"{c.offhand_damage_type()}{tip}")

    def _damage_roll(self):
        c = self.char
        if not c:
            return
        label = c.weapon or "徒手打击"
        dice = c.damage_dice()
        bonus = c.damage_bonus()
        expr = f"{dice}{mod_str(bonus)}" if bonus else dice
        # 2024 巨武器战斗: 双手/双手持用武器, 伤害骰出 1 或 2 可重掷
        gwf = (c.fighting_style == "great_weapon"
               and (c.is_two_handed_weapon()
                    or (c.two_handed_grip and c.is_versatile_weapon())))
        if gwf:
            total, detail = roll_dice_reroll(expr, 2)
        else:
            total, detail = roll_dice(expr)
        extra = ""
        if c.class_id == "rogue" and self.sneak_var.get():
            n = c.sneak_dice()
            s_total, s_detail = roll_dice(f"{n}d6")
            total += s_total
            extra = f" + 偷袭 {s_detail}"
        self._log_roll(f"⚔ 伤害·{label}: {detail}{extra} "
                       f"= {total} {c.damage_type()}")

    # ---- 法术 ----

    def _spell_rows(self):
        c = self.char
        rows = []
        if not c:
            return rows
        fixed = set(c.fixed_spells())
        for key in ("cantrips", "prepared"):
            for sid in (c.spells or {}).get(key, []):
                if sid in fixed:             # 已由特性授予, 不重复列出
                    continue
                s = c.r.spell(sid)
                if s:
                    rows.append(dict(s, _src="职业"))
        for sid in c.fixed_spells():         # 职业特性 / 子职「始终准备」
            s = c.r.spell(sid)
            if s:
                rows.append(dict(s, _src=f"{c.fixed_source(sid)}固定"))
        for unlock, sid in c.species_spells():       # 种族自带, 不占职业位
            s = c.r.spell(sid)
            if s:
                rows.append(dict(s, _src="种族"))
        # 法师: 书里的仪式法术不用准备也能施放 (仪式施法, 不耗环位)
        if c.class_id == "wizard":
            shown = {r["id"] for r in rows}
            for sid in (c.spellbook or []):
                if sid in shown:
                    continue
                s = c.r.spell(sid)
                if s and s.get("ritual"):
                    rows.append(dict(s, _src="仪式"))
        rows.sort(key=lambda s: (s["level"], s["name"]))
        self._spell_cache = rows
        return rows

    def _spell_refresh(self):
        c = self.char
        if not c or not hasattr(self, "spell_list"):
            return
        prev = self._selected_spell()
        prev_id = prev["id"] if prev else None
        rows = self._spell_rows()
        self.spell_list.delete(0, "end")
        keep = None
        for i, s in enumerate(rows):
            tag = "戏法" if s["level"] == 0 else f"{s['level']}环"
            src = "[种族] " if s.get("_src") == "种族" else ""
            if str(s.get("_src", "")).endswith("固定"):
                src = f"✦{s['_src']} "
            elif s.get("_src") == "仪式":
                src = "[仪式] "
            mark = "  ◉专注中" if c.concentration == s["id"] else ""
            self.spell_list.insert("end", f"[{tag}] {src}{s['name']}{mark}")
            if s["id"] == prev_id:
                keep = i
        if keep is not None:          # 刷新后保持原选中项, 便于连续施法
            self.spell_list.selection_set(keep)
            self.spell_list.see(keep)
        learned = {s["id"] for s in rows}
        prepared = set(c.spells.get("prepared") or [])
        fixed = set(c.fixed_spells())
        maxlv = c.learnable_max_level()
        if c.class_id == "wizard":
            # 法师: 下拉框只列「法术书里、还没准备」的法术; 戏法仍从职业表学
            top = max(c.book_max_level(), 1)
            opts = [s for s in c.book_spells()
                    if s["level"] >= 1 and s["id"] not in prepared
                    and s["level"] <= top]
            opts += [s for s in c.r.class_spells("wizard", 0)
                     if s["id"] not in learned]
            opts.sort(key=lambda s: (s["level"], s["name"]))
        else:
            opts = [s for s in c.r.class_spells(c.spell_list_class() or "")
                    if s["id"] not in learned and s["id"] not in fixed
                    and (s["level"] == 0 or s["level"] <= max(maxlv, 1))]
        self._spell_opts = opts
        self.spell_add_cb["values"] = [f"{s['name']} {s['name_en']}"
                                       for s in opts]
        # 法师才显示法术书按钮 / 把「学习」改成「准备」
        if hasattr(self, "spellbook_btn"):
            if c.class_id == "wizard":
                self.spellbook_btn.config(
                    text=f"📖 法术书 ({len(c.spellbook or [])})")
                if not self.spellbook_btn.winfo_manager():
                    self.spellbook_btn.pack(side="right")
            elif self.spellbook_btn.winfo_manager():
                self.spellbook_btn.pack_forget()
        if hasattr(self, "spell_add_btn"):
            self.spell_add_btn.config(
                text="＋ 准备" if c.class_id == "wizard" else "＋ 学习")
        # 配额提示: 戏法硬上限 / 准备法术上限 (2024 职业表)
        if hasattr(self, "spell_quota_lbl"):
            if not c.casting():
                self.spell_quota_lbl.config(
                    text="该职业没有施法能力（若子职给法术，选子职后这里会自动出现）")
            else:
                n_c = len(c.spells.get("cantrips") or [])
                n_p = c.prepared_count()
                arc = c.arcanum_levels()
                extra = (f"　秘契 {max(arc)} 环（不占准备数）" if arc else "")
                n_fx = len(c.fixed_spells())
                fx = (f"　✦固定 {n_fx} 个（不占格）" if n_fx else "")
                n_mm = len(c.metamagic_known())
                mm = (f"　⚙超魔法 {n_mm} 个（施法时选）" if n_mm else "")
                bk = (f"　📖书内 {len(c.spellbook or [])} 个"
                      if c.class_id == "wizard" else "")
                self.spell_quota_lbl.config(
                    text=f"戏法 {n_c}/{c.cantrip_cap()}　"
                         f"法术 {n_p}/{c.prepared_hint()}（职业表）　"
                         f"最高可用 {c.max_spell_level()} 环{extra}{fx}{mm}{bk}")
        if not rows:
            tip = ("法术书里还没有能用的法术。点右上角「📖 法术书」抄录，"
                   "再从下拉框里「＋ 准备」。"
                   if c.class_id == "wizard" else
                   "本角色尚无法术。用上方下拉框选择本职业法术，点「＋ 学习」加入。"
                   "（法师/牧师等准备施法者也可按 DM 允许随时调整）")
            self._spell_detail_set(tip)

    def _spell_detail_set(self, text):
        self.spell_detail.config(state="normal")
        self.spell_detail.delete("1.0", "end")
        self.spell_detail.insert("1.0", text)
        self.spell_detail.config(state="disabled")

    def _selected_spell(self):
        sel = self.spell_list.curselection()
        rows = getattr(self, "_spell_cache", [])
        if sel and sel[0] < len(rows):
            return rows[sel[0]]
        return None

    def _spell_show(self, _e=None):
        s = self._selected_spell()
        txt = spell_detail(s)
        c = self.char
        if s and c and c.spell_dc() is not None:
            txt += f"\n\n你的法术豁免 DC {c.spell_dc()} · 法术攻击 {mod_str(c.spell_attack())}"
        self._spell_detail_set(txt)

    def _spellbook_open(self):
        """打开法师法术书 (抄录 / 移出)"""
        c = self.char
        if not c or c.class_id != "wizard":
            return
        dlg = SpellbookDialog(self, c, selftest=getattr(self, "_selftest", False))
        self.wait_window(dlg)
        self.refresh()

    def _spell_add(self):
        c = self.char
        if not c:
            return
        idx = self.spell_add_cb.current()
        if idx < 0 or idx >= len(getattr(self, "_spell_opts", [])):
            return
        s = self._spell_opts[idx]
        if s["id"] in set(c.fixed_spells()):
            messagebox.showinfo(
                "提示", f"{s['name']} 已由职业/子职特性「始终准备」，"
                        f"不需要再学，也不占准备数。", parent=self)
            return
        key = "cantrips" if s["level"] == 0 else "prepared"
        cur = list(c.spells.get(key) or [])
        # 法师: 只能准备法术书里的法术
        if key == "prepared" and c.class_id == "wizard" \
                and not c.can_prepare(s["id"]):
            messagebox.showwarning(
                "不在法术书里",
                f"{s['name']} 不在你的法术书里，不能准备。\n"
                "请先点「📖 法术书」把它抄进书里。", parent=self)
            return
        # 戏法: 数量由职业固定, 不能超
        if key == "cantrips" and len(cur) >= c.cantrip_cap():
            messagebox.showwarning(
                "戏法已满",
                f"{c.cls()['name']} 目前只能掌握 {c.cantrip_cap()} 个戏法"
                f"（已学 {len(cur)} 个）。\n4 级与 10 级各会再 +1。", parent=self)
            return
        # 法术环级不能超过你能施放的最高环 (含秘契 6–9 环)
        if s["level"] > max(c.learnable_max_level(), 1):
            messagebox.showwarning(
                "环级不足",
                f"你目前最高只能施放 {c.learnable_max_level()} 环法术，"
                f"还不能学习 {s['name']}（{s['level']} 环）。", parent=self)
            return
        # 准备法术: 数量由职业表定死, 不能超; 秘契法术不占这份额度
        arcanum = s["level"] > c.max_spell_level()
        if key == "prepared" and not arcanum \
                and c.prepared_count() >= c.prepared_hint():
            messagebox.showwarning(
                "已到准备上限",
                f"{c.cls()['name']} {c.level} 级最多准备 "
                f"{c.prepared_hint()} 个法术（2024 职业表，已准备 "
                f"{c.prepared_count()} 个）。\n"
                "想换法术请先移除一个；长休时可以重新准备。", parent=self)
            return
        if s["id"] not in cur:
            c.spells.setdefault(key, []).append(s["id"])
        self.refresh()
        self._spell_detail_set(spell_detail(s))

    def _spell_del(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        if s.get("_src") == "种族":
            messagebox.showinfo(
                "提示", f"{s['name']} 是种族自带法术，不能移除。\n"
                        f"（{self.char.lineage_cn() or '种族'}特性，始终备好）",
                parent=self)
            return
        if str(s.get("_src", "")).endswith("固定"):
            src = s["_src"][:-2]           # "职业固定" -> "职业"
            messagebox.showinfo(
                "提示", f"{s['name']} 由{src}特性「始终准备」，不能移除。\n"
                        "它也不占用准备法术的数量。", parent=self)
            return
        if s.get("_src") == "仪式":
            messagebox.showinfo(
                "提示", f"{s['name']} 还在法术书里（未准备），可以直接仪式施放。\n"
                        "要删掉请点「📖 法术书」把书里的这个法术移出。",
                parent=self)
            return
        for key in ("cantrips", "prepared"):
            if s["id"] in c.spells.get(key, []):
                c.spells[key].remove(s["id"])
        if c.concentration == s["id"]:
            c.concentration = None
        self.refresh()

    def _spell_cast(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        # 2024: 穿着未熟练的护甲/盾牌时无法施法
        if not c.has_armor_prof() or (c.shield and not c.has_shield_prof()):
            messagebox.showwarning(
                "提示", "穿着未熟练的护甲或盾牌时无法施法（2024 规则）。\n"
                        "请在「装备·加成」页更换护甲或卸下盾牌。", parent=self)
            return
        if c.condition_blocks_action():
            messagebox.showwarning(
                "提示", "当前状态（失能/麻痹/震慑/昏迷/石化）无法执行动作，"
                        "因此不能施法。", parent=self)
            return
        if c.raging:
            messagebox.showwarning(
                "提示", "狂暴期间不能施放任何法术（2024 Rage）。\n"
                        "要施法请先结束狂暴。", parent=self)
            return
        # 仪式施法: 书里的仪式法术不用准备, 也不耗环位 (额外 10 分钟)
        if s.get("_src") == "仪式":
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ 仪式施放 {s['name']}（10 分钟，不耗环位）")
            return
        # 超魔法: 施法前选 (取消则整个施法取消)
        mm = self._mm_pick(s)
        if mm is None:
            return
        ok, why, _cost = c.mm_validate(mm)
        if not ok:
            messagebox.showwarning("超魔法不可用", why, parent=self)
            return
        mm_msg = ""
        if mm:
            _ok2, mm_msg = c.mm_apply(mm)
        tail = f" · {mm_msg}" if mm_msg else ""
        if s["level"] == 0:
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            tag = "（种族）" if s.get("_src") == "种族" else ""
            self._log_roll(f"✨ 施放戏法{tag} {s['name']}{tail}")
            return
        # 法师 18 级「法术精通」: 最低环随意施放, 不耗环位
        if c.is_mastery_spell(s["id"]):
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ {s['name']}（法术精通：随意施放，不耗环位）{tail}")
            return
        # 法师 20 级「招牌法术」: 每个短休免费施放 1 次 (3 环)
        if c.signature_left(s["id"]):
            c.signature_used.append(s["id"])
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ {s['name']}（招牌法术：3 环免费，短休恢复）{tail}")
            return
        # 种族法术: 每项每长休可免费施放 1 次
        if s.get("_src") == "种族" and s["id"] not in c.race_free_used:
            c.race_free_used.append(s["id"])
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ 种族法术 {s['name']}（免费，1/长休）{tail}")
            return
        slots = c.spell_slots()
        avail = [x for x in sorted(slots)
                 if x >= s["level"] and slots[x] - c.spell_slots_used.get(x, 0) > 0]
        if not avail:
            messagebox.showwarning(
                "提示", f"{s['level']} 环及以上已无剩余法术位（长休恢复）",
                parent=self)
            return
        use = avail[0]
        c.spell_slots_used[use] = c.spell_slots_used.get(use, 0) + 1
        if s["concentration"]:
            c.concentration = s["id"]
        self.refresh()
        extra = ""
        sc = s.get("scaling") or {}
        if s["damage"] and str(use) in sc:
            extra = f" · {sc[str(use)]} {s['damage_type']}"
        self._log_roll(f"✨ 施放 {s['name']}（{use} 环位）{extra}{tail}")

    def _mm_pick(self, spell):
        """选超魔法: None=取消施法, []=不应用"""
        c = self.char
        if not c or not c.metamagic_known() or c.sorcery_left() <= 0:
            return []
        if getattr(self, "_selftest", False):
            return []                       # 后台测试不弹窗
        dlg = MetamagicDialog(self, c, spell)
        self.wait_window(dlg)
        return dlg.result

    def _spell_focus(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        if c.concentration == s["id"]:
            c.concentration = None
            self._log_roll(f"◯ 结束专注: {s['name']}")
        else:
            c.concentration = s["id"]
            self._log_roll(f"◉ 开始专注: {s['name']}")
        self.refresh()

    def _lang_changed(self):
        if self.char:
            self.char.languages = self.lang_entry.get()

    def _notes_changed(self):
        if self.char:
            self.char.equipment = self.eq_text.get("1.0", "end").strip()
            self.char.notes = self.note_text.get("1.0", "end").strip()
