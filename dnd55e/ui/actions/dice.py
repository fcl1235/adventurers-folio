"""掷骰: 属性检定 / 豁免 / 先攻 / 技能 / 快捷骰 / 攻击 / 伤害 / 副手。"""
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


class DiceMixin:
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
