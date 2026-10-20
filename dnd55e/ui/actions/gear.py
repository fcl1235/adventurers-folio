"""武器 / 副手 / 战斗风格 / 魔法物品 / 武器专精。"""
import random
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from ... import consts, util
from ...consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                       size_cn, subclass_cn, tool_cn)
from ...dialogs import (FeatPickerDialog, ItemCardDialog, MetamagicDialog,
                        SpellbookDialog, WildShapeDialog)
from ...rules import Rules
from ...theme import BG, GOLD2
from ...util import (ability_mod, mod_str, roll_dice, roll_dice_reroll,
                     spell_detail)


class GearMixin:
    WEP_SUFFIX = (" ✓熟练", " ✗未熟练")

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

    def _item_card_open(self, iid):
        """物品完整效果卡: 63 条 note_only 的叙述性效果只能在这里读全。"""
        it = consts.ITEMS_BY_ID.get(iid)
        if not it:
            return None
        dlg = ItemCardDialog(self, it, char=self.char,
                             selftest=self._selftest,
                             on_toggle=self._item_card_toggle)
        if not self._selftest:
            self.wait_window(dlg)
        return dlg

    def _item_card_toggle(self, iid):
        """详情卡里的「装备/卸下」: 复用勾选逻辑, 再同步勾选框。"""
        if iid not in self.item_vars:
            return
        self.item_vars[iid].set(not self.item_vars[iid].get())
        self._item_changed(iid)

    def _offhand_changed(self):
        c = self.char
        if not c:
            return
        name = self.offhand_cb.get().replace("（无）", "").strip()
        c.offhand_weapon = name if name in {w[0] for w in consts.WEAPONS} else ""
        self.refresh()
