"""角色数值变动: HP / 属性编辑 / 技能熟练 / 护甲 / 状态 / 濒死 / 环位。"""
import random
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from ... import consts, util
from ...consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                       size_cn, subclass_cn, tool_cn)
from ...dialogs import (FeatPickerDialog, MetamagicDialog, SpellbookDialog,
                        WildShapeDialog)
from ...rules import Rules
from ...theme import BG, GOLD2
from ...util import (ability_mod, mod_str, roll_dice, roll_dice_reroll,
                     spell_detail)


class StatsMixin:
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
