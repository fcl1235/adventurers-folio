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


class WildShapeDialog(tk.Toplevel):
    """德鲁伊荒野变形: 按等级/子职列出可选野兽形态。
    只记录当前形态, 不改角色本体数值 (AC/HP/攻击按形态数据单独看)。
    result: None=取消, ""=恢复本体, else=monster id"""

    def __init__(self, master, char, selftest=False):
        super().__init__(master)
        from .. import wildshape as _ws
        self.char = char
        self._selftest = selftest
        self.result = None
        self._rows = char.wild_shapes()
        self.title("野兽形态")
        self.geometry("760x540")
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
                 + (f" · 当前：{cur['name']}" if cur else " · 当前：本体"))
        self.head.pack(anchor="w", padx=12)
        ttk.Label(self, wraplength=700, justify="left", foreground=DIM,
                  text="2 级不能选带飞行/游泳速度的形态，4 级起解除；"
                       "大地结社按 3/6/9/12/15/18 级放宽 CR 上限。"
                       "变形后按这里的 AC/HP/攻击结算，角色本体数值不变。").pack(
            anchor="w", padx=12, pady=(2, 6))

        body = ttk.Frame(self, padding=(12, 0))
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="可选形态", padding=6)
        left.pack(side="left", fill="y")
        self.lst = tk.Listbox(left, width=30, height=16, exportselection=False,
                             **LISTBOX_STYLE)
        self.lst.pack(fill="both", expand=True)
        self.lst.bind("<<ListboxSelect>>", self._show)
        for m in self._rows:
            self.lst.insert("end", f"{m['name']}  (CR {m['cr']})")

        right = ttk.LabelFrame(body, text="形态详情", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.detail = tk.Text(right, wrap="word", state="disabled",
                              **TEXT_STYLE, width=1)
        self.detail.pack(fill="both", expand=True)

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="变形", command=self._take).pack(
            side="right", padx=4)
        ttk.Button(bar, text="恢复本体", command=self._revert).pack(
            side="right", padx=4)
        ttk.Button(bar, text="关闭", command=self._close).pack(
            side="right", padx=4)
        if self._rows:
            self.lst.selection_set(0)
            self._show()

    def _sel(self):
        cur = self.lst.curselection()
        return self._rows[cur[0]] if cur else None

    def _show(self, _e=None):
        from .. import wildshape as _ws
        m = self._sel()
        if not m:
            return
        ab = m.get("abilities") or {}
        lines = [_ws.summary(m), ""]
        lines.append("力量 {} 敏捷 {} 体质 {} 智力 {} 感知 {} 魅力 {}".format(
            ab.get("STR", 0), ab.get("DEX", 0), ab.get("CON", 0),
            ab.get("INT", 0), ab.get("WIS", 0), ab.get("CHA", 0)))
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
        self.char.wild_shape_id = m["id"]
        self.result = m["id"]
        self._close()

    def _revert(self):
        self.char.wild_shape_id = None
        self.result = ""
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
