"""职业专属选项: 1 级职阶 / 德鲁伊地形 / 荒野变形 / 超魔法 / 先天魔法 / 法师自选。"""
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


class ClassOptsMixin:
    def _companion_set(self, disp_name):
        """切换野兽伙伴形态 (只改 id, 数值由职业模块现算)"""
        c = self.char
        comp = c.companion() if c else None
        if not comp:
            return
        for o in comp["options"]:
            if o["name"] == disp_name:
                c.companion_id = o["id"]
                break
        self.refresh()

    def _companion_strike(self):
        """掷野兽打击: 攻击 d20 + 你的法术攻击, 命中后掷伤害 + 感知"""
        c = self.char
        comp = c.companion() if c else None
        if not comp:
            return
        raw = random.randint(1, 20)
        hit = raw + c.spell_attack()
        crit = " 🎯大成功!" if raw == 20 else (" 💀大失败" if raw == 1 else "")
        st = comp.get("strike_parts") or {}
        die = st.get("damage") or "1d4"
        bonus = int(st.get("flat") or 0) + int(comp.get("wis_mod") or 0)
        total, detail = roll_dice(die)
        dmg = total + bonus
        if raw == 20:
            dmg += roll_dice(die)[0]
        self._log_roll(
            f"{comp['name']}·野兽打击: d20={raw} {mod_str(c.spell_attack())}"
            f" ⇒ {hit}{crit} ｜ 伤害 {detail} + {bonus} = {dmg}"
            f" {st.get('damage_type', '')}")
        extra = st.get("extra") or ""
        if extra and raw != 1:
            self.status.config(text=f"🎲 {comp['name']} 命中 ⇒ {dmg} —— {extra}")

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

    def _boon_ab_set(self, name, ab):
        """传奇恩惠的「属性 +1」落到哪一项 (上限 30)"""
        c = self.char
        if not c or name not in c.boon_names():
            return
        info = consts.FEATS_BY_NAME.get(name) or {}
        allowed = ((info.get("effects") or {}).get("ability_boost") or {}
                   ).get("from") or list(ABILITIES)
        if ab in allowed:
            c.boon_ability[name] = ab
        self.refresh()

    def _boon_res_toggle(self, dtype, var):
        """能量抗性之恩惠: 最多 limit 项, 超了就回退并提示"""
        c = self.char
        if not c:
            return
        pool = c.boon_resist_pool()
        limit = c.boon_resist_limit()
        got = list(c.boon_resist)
        if var.get():
            if dtype in pool and dtype not in got:
                if len(got) >= limit:
                    var.set(False)
                    messagebox.showinfo(
                        "已达上限", f"这个恩惠只能选 {limit} 种抗性", parent=self)
                    return
                got.append(dtype)
        else:
            got = [r for r in got if r != dtype]
        c.boon_resist = [r for r in pool if r in got]
        self.refresh()

    def _boon_exp_set(self, sid):
        """技艺之恩惠: 1 项已熟练技能获得专精"""
        c = self.char
        if not c:
            return
        if sid and (sid not in c.skill_prof or sid in c.expertise):
            return
        c.boon_expertise = [sid] if sid else []
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
