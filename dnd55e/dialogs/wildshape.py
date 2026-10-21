"""荒野变形形态选择对话框。"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, util
from ..consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                      size_cn, subclass_cn, tool_cn)
from ..theme import (BG, DIM, GOLD2, LISTBOX_STYLE, RED, TEXT, TEXT_STYLE,
                     TXT_BG)
from ..util import (ab_from_display, ability_mod, mod_str,
                    proficiency_bonus, roll_dice)

from ._fit import center_on, fit


class WildShapeDialog(tk.Toplevel):
    """德鲁伊荒野变形: 按等级/子职列出可选野兽形态。

    确认变形会: ①扣 1 次荒野变形 ②按形态给临时 HP ③把角色数值
    切换到野兽面板 (STR/DEX/CON/AC/速度/感官/攻击)。
    result: None=取消, ""=恢复本体, else=monster id"""

    def __init__(self, master, char, selftest=False):
        super().__init__(master)
        from .. import wildshape as _ws
        self.char = char
        self._selftest = selftest
        self.result = None
        self._rows = char.wild_shapes()
        self._left = char.wild_shape_left()
        self.title("野兽形态")
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
                 f" · 已知形态 {_ws.known_forms(char.level)} 种"
                 f" · 剩余次数 {self._left}"
                 + (f" · 当前：{cur['name']}" if cur else " · 当前：本体"))
        self.head.pack(anchor="w", padx=12)
        ttk.Label(self, wraplength=700, justify="left", foreground=DIM,
                  text="2 级不能选带飞行/游泳速度的形态，4 级起解除游泳、"
                       "8 级起解除飞行；大地结社只放宽 CR 上限，不放宽速度限制。"
                       "确认变形消耗 1 次荒野变形（短休回 1、长休全回），"
                       f"并获得临时 HP {_ws.temp_hp(char.level, char.subclass)} 点"
                       + ("（大地结社 3×等级）" if char.subclass ==
                          "Circle of the Moon" and char.level >= 3 else "")
                       + "。变形后力量/敏捷/体质、AC、速度、感官与攻击"
                       "改用形态数据，智力/感知/魅力与 HP 保留本体。").pack(
            anchor="w", padx=12, pady=(2, 6))

        # 按钮栏先 pack 到最下方: 窗口再矮也不会被内容挤出去
        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x", side="bottom")
        ttk.Button(bar, text="变形", command=self._take).pack(
            side="right", padx=4)
        ttk.Button(bar, text="恢复本体", command=self._revert).pack(
            side="right", padx=4)
        ttk.Button(bar, text="关闭", command=self._close).pack(
            side="right", padx=4)
        self.bar = bar

        body = ttk.Frame(self, padding=(12, 0))
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="可选形态", padding=6)
        left.pack(side="left", fill="y")
        lbwrap = ttk.Frame(left)
        lbwrap.pack(fill="both", expand=True)
        self.lst = tk.Listbox(lbwrap, width=30, height=16, exportselection=False,
                             selectmode="browse", **LISTBOX_STYLE)
        # 形态可能几十种 (19 级 88 种), 没有滚动条就只能看到前 16 个
        sb = ttk.Scrollbar(lbwrap, orient="vertical", command=self.lst.yview)
        self.lst.config(yscrollcommand=sb.set)
        self.lst.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.lst.bind("<MouseWheel>", self._wheel)
        self.lst.bind("<<ListboxSelect>>", self._show)
        for m in self._rows:
            self.lst.insert("end", f"{m['name']}  (CR {m['cr']})")

        right = ttk.LabelFrame(body, text="形态详情", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.detail = tk.Text(right, wrap="word", state="disabled",
                              **TEXT_STYLE, width=1)
        self.detail.pack(fill="both", expand=True)

        if self._rows:
            self.lst.selection_set(0)
            self._show()

        # 尺寸按内容给 (曾写死 540, 内容要 674, 底部按钮栏被挤出可视区)
        fit(self, 760, 560)
        center_on(self, master)

    def _wheel(self, e):
        self.lst.yview_scroll(-1 if e.delta > 0 else 1, "units")
        return "break"

    def _sel(self):
        cur = self.lst.curselection()
        return self._rows[cur[0]] if cur else None

    def _show(self, _e=None):
        from .. import wildshape as _ws
        m = self._sel()
        if not m:
            return
        ab = m.get("abilities") or {}
        wis_mod = ability_mod(self.char.score("WIS"))
        ac, ac_note = _ws.ac_for(m, wis_mod, self.char.level,
                                 self.char.subclass)
        lines = [_ws.summary(m), ""]
        lines.append(f"变形后 AC {ac} —— {ac_note}")
        thp = _ws.temp_hp(self.char.level, self.char.subclass)
        lines.append(f"变形时获得临时 HP {thp} 点（与已有临时 HP 取大，不叠加）")
        sp = _ws.speeds(m)
        cn = {"walk": "步行", "climb": "攀爬", "fly": "飞行",
              "swim": "游泳", "burrow": "掘地"}
        lines.append("速度：" + "、".join(f"{cn[k]} {v} 尺"
                                        for k, v in sp.items()
                                        if k in cn and v)
                     + ("（悬浮）" if sp.get("hover") else ""))
        sn = _ws.senses(m)
        if sn:
            sn_cn = {"darkvision": "黑暗视觉", "blindsight": "盲视",
                     "tremorsense": "震颤感知", "truesight": "真实视觉"}
            lines.append("感官：" + "、".join(f"{sn_cn[k]} {v} 尺"
                                            for k, v in sn.items()))
        lines.append("")
        lines.append("力量/敏捷/体质 换成形态值，智力/感知/魅力 保留本体：")
        for key, abbr in (("STR", "力量"), ("DEX", "敏捷"), ("CON", "体质"),
                          ("INT", "智力"), ("WIS", "感知"), ("CHA", "魅力")):
            cur = int(ab.get(key) or 0)
            own = self.char.base_score(key)
            if key in ("STR", "DEX", "CON"):
                lines.append(f"  {abbr} {own} → {cur}"
                             f"（调整值 {mod_str(ability_mod(own))} → "
                             f"{mod_str(ability_mod(cur))}）")
            else:
                lines.append(f"  {abbr} {own}（保留本体）")
        lines.append(f"  熟练加值 +{self.char.pb()}、豁免/技能熟练、专长与"
                     "语言全部保留本体的")
        if _ws.skill_note(m):
            lines.append(f"  形态自带技能（参考，不叠加）：{_ws.skill_note(m)}")
        lines.append(f"  变形期间不能施法（18 级「野兽法术」除外）；"
                     f"HP 上限仍为 {self.char.hp_max()}")
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
        from .. import wildshape as _ws
        if not self.char.wild_shape_use():
            self.head.config(
                text=f"⚠ 荒野变形次数已用完（剩余 {self.char.wild_shape_left()}）："
                     "短休恢复 1 次、长休全部恢复")
            if not self._selftest:
                messagebox.showinfo(
                    "次数不足",
                    "荒野变形的次数已用完。\n短休恢复 1 次，长休全部恢复。",
                    parent=self)
            return
        self.char.wild_shape_id = m["id"]
        # 变形获得临时 HP: 与已有临时 HP 取大 (临时 HP 不叠加),
        # 记住这部分是形态给的, 恢复本体时只收回它
        grant = _ws.temp_hp(self.char.level, self.char.subclass)
        self.char.hp_temp = max(int(self.char.hp_temp or 0), grant)
        self.char.ws_temp_granted = grant
        self.result = m["id"]
        self._close()

    def _revert(self):
        self.char.wild_shape_exit()
        self.result = ""
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
