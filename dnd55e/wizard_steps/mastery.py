"""步骤 5: 武器专精选择。"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, util
from ..character import Character
from ..consts import (ABILITIES, ABILITY_CN, ARMOR_PROF_CN, CAST_MODE_CN,
                      CAST_TYPE_CN, WEAPON_PROF_CN, feat_cn, feat_desc,
                      mastery_cn, size_cn, subclass_cn, tool_cn)
from ..rules import Rules
from ..theme import (BG, DIM, GOLD2, LISTBOX_STYLE, PURPLE, TEXT, TXT_BG,
                     HintText)
from ..util import (ab_from_display, ability_mod, mod_str,
                    proficiency_bonus, roll_4d6kh3, spell_detail)


class MasteryMixin():
    def _step_mastery(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        cls = self.r.cls(self.data["class_id"])
        n = cls["weapon_mastery_count"]
        if n == 0:
            self.data["weapon_mastery"] = []     # 换到无专精职业: 清掉旧选择
            ttk.Label(f, text="⑤/⑥ 武器专精", font=("", 13, "bold")).pack(anchor="w")
            ttk.Label(f, text=f"{cls['name']} 没有武器专精特性，直接下一步。\n"
                              f"(4级起可用 Weapon Master 专长补足)",
                      foreground=DIM).pack(anchor="w", pady=10)
            return
        ttk.Label(f, text=f"⑤/⑥ 选择武器专精 (须恰好 {n} 件, 长休可换)",
                  font=("", 13, "bold")).pack(anchor="w")
        pool = Rules.class_mastery_pool(cls)
        head = ttk.Frame(f)
        head.pack(anchor="w", fill="x")
        ttk.Label(head, text=f"可选范围: {cls['name']} 的武器熟练 "
                             f"({', '.join(WEAPON_PROF_CN.get(w, w) for w in cls['weapons'])})",
                  foreground=DIM).pack(side="left")
        self._mastery_count_lbl = ttk.Label(head, text="", font=("", 10, "bold"))
        self._mastery_count_lbl.pack(side="left", padx=10)
        self.mastery_vars = {}
        grid = ttk.Frame(f)
        grid.pack(anchor="w", pady=6)
        for i, w in enumerate(pool):
            wname, cat, dmg, mst = w[0], w[1], w[2], w[3]
            v = tk.BooleanVar(value=wname in self.data["weapon_mastery"])
            self.mastery_vars[wname] = v
            ttk.Checkbutton(grid, text=f"{wname} · {dmg} · {mastery_cn(mst)}",
                            variable=v,
                            command=lambda w2=wname: self._on_mastery(w2)
                            ).grid(row=i // 2, column=i % 2,
                                   sticky="w", padx=8, pady=2)
        self._mastery_need = n
        self._update_mastery_count()
        ttk.Label(f, text="专精效果:", foreground=DIM).pack(anchor="w")
        txt = tk.Text(f, height=6, wrap="word", state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        txt.pack(fill="both", expand=True)
        masts = {w[3] for w in pool}
        txt.config(state="normal")
        txt.insert("1.0", "\n".join(consts.MASTERY_DESC[m] for m in sorted(masts)))
        txt.config(state="disabled")

    def _update_mastery_count(self):
        n = sum(1 for v in self.mastery_vars.values() if v.get())
        ok = (n == self._mastery_need)
        self._mastery_count_lbl.config(
            text=f"已选 {n} / {self._mastery_need}",
            foreground="#58b368" if ok else GOLD2)

    def _on_mastery(self, wname):
        """武器专精多选实时控制: 超出上限自动回退本次勾选"""
        v = self.mastery_vars[wname]
        if v.get():
            n = sum(1 for x in self.mastery_vars.values() if x.get())
            if n > self._mastery_need:
                v.set(False)
                self._mastery_count_lbl.config(
                    text=f"已达上限 {self._mastery_need} 件 —— 请先取消一件再选",
                    foreground="#e05c4d")
                return
        self._update_mastery_count()

    def _validate_5(self):
        cls = self.r.cls(self.data["class_id"])
        if cls["weapon_mastery_count"] == 0:
            self.data["weapon_mastery"] = []
            return True
        chosen = [w for w, v in self.mastery_vars.items() if v.get()]
        if len(chosen) != self._mastery_need:
            messagebox.showwarning(
                "提示", f"须恰好选择 {self._mastery_need} 件武器 (已选 {len(chosen)})",
                parent=self)
            return False
        self.data["weapon_mastery"] = chosen
        return True
