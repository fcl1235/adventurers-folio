"""魔法物品详情卡 (只读 + 一件装/卸)。

为什么需要: 物品格的悬停提示只有 2 行高，140 件里有 63 件的效果是纯文字
（`note_only`），塞进提示行必然要截断，效果根本读不全。这里给出完整正文
与所有已机械计算的字段。

数据只读：本卡不修改 items.json，写回角色的是 `char.items` 列表。
"""
import tkinter as tk
from tkinter import ttk

from .. import consts
from ..theme import BG, DIM, GOLD2, TEXT_STYLE

# (字段, 标签, 格式化方式) —— 顺序即展示顺序
INT_FIELDS = [
    ("ac", "AC", "+{}"),
    ("ac_bonus_armor", "护甲 AC 加值", "+{}"),
    ("attack", "攻击加值", "+{}"),
    ("damage", "伤害加值", "+{}"),
    ("save", "豁免", "+{}"),
    ("check", "属性检定", "+{}"),
    ("spell_dc", "法术豁免 DC", "+{}"),
    ("spell_attack", "法术攻击", "+{}"),
    ("speed_bonus", "速度", "+{} 尺"),
    ("hp_bonus", "HP 上限", "+{}"),
]

SET_FIELDS = [
    ("set_str", "力量"), ("set_dex", "敏捷"), ("set_con", "体质"),
    ("set_int", "智力"), ("set_wis", "感知"), ("set_cha", "魅力"),
]


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def mech_lines(it):
    """把一件物品能机械计算的字段拍平成文字行。"""
    out = []
    for key, label, fmt in INT_FIELDS:
        v = it.get(key)
        if _num(v) and v:
            out.append(f"{label} {fmt.format(v)}")
    if _num(it.get("base_ac")):
        tail = "（不可穿甲）" if it.get("no_armor") else ""
        out.append(f"基础 AC = {it['base_ac']}{tail}")
    if _num(it.get("speed_mult")) and it["speed_mult"] != 1:
        out.append(f"速度 ×{it['speed_mult']}")
    for key, label in SET_FIELDS:
        v = it.get(key)
        if _num(v):
            out.append(f"{label} 固定为 {v}")
    for key, label in (("resist", "抗性"), ("immune", "免疫")):
        vals = it.get(key) or []
        if vals:
            out.append(f"{label} " + "、".join(consts.damage_cn(x) for x in vals))
    conds = it.get("condition_immune") or []
    if conds:
        out.append("状态免疫 " + "、".join(consts.condition_cn(x) for x in conds))
    if _num(it.get("charges")) and it["charges"]:
        note = it.get("charge_note") or ""
        out.append(f"充能 {it['charges']} 次" + (f"（{note}）" if note else ""))
    return out


def card_text(it):
    """完整详情卡的纯文本形式（测试与导出复用）。"""
    head = [it.get("name", it.get("id", "")),
            f"{consts.rarity_cn(it.get('rarity'))} · "
            f"{consts.kind_cn(it.get('kind'))} · "
            + ("需同调" if it.get("attune") else "无需同调")]
    body = [it.get("note") or "", it.get("desc") or ""]
    mech = mech_lines(it)
    if mech:
        body.append("")
        body.append("已计入数值：")
        body += ["· " + x for x in mech]
    if it.get("note_only"):
        body.append("")
        body.append("（此物品还有无法自动计算的叙述性效果，见上方说明。）")
    lines = [head[0], head[1], ""] + body
    return "\n".join(x for x in lines if x is not None)


class ItemCardDialog(tk.Toplevel):
    """魔法物品详情。

    char: 角色（可为 None，纯查阅时不给装/卸按钮）
    on_toggle: 回调 (iid) -> None，点「装备」「卸下」时调用
    result: 恒为 None
    """

    def __init__(self, master, item, char=None, selftest=False,
                 on_toggle=None, title=None):
        super().__init__(master)
        self._selftest = selftest
        self._item = item or {}
        self._char = char
        self._on_toggle = on_toggle
        self.result = None
        self.title(title or "魔法物品")
        self.geometry("660x560")
        self.transient(master)
        self.configure(bg=BG)
        if not selftest:
            try:
                self.grab_set()
            except tk.TclError:
                pass

        it = self._item
        ttk.Label(self, text=it.get("name", "魔法物品"),
                  font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        self.meta_lbl = ttk.Label(self, foreground=GOLD2,
                                  text=self._meta_line())
        self.meta_lbl.pack(anchor="w", padx=12)

        wrap = ttk.Frame(self, padding=(12, 6))
        wrap.pack(fill="both", expand=True)
        self.text = tk.Text(wrap, wrap="word", state="disabled", width=1,
                            **TEXT_STYLE)
        self.text.pack(fill="both", expand=True)
        self._fill()

        bar = ttk.Frame(self, padding=(12, 8))
        bar.pack(fill="x")
        self.toggle_btn = ttk.Button(bar, text="", command=self._toggle)
        if char is not None:
            self.toggle_btn.pack(side="left")
            self._sync_btn()
        ttk.Button(bar, text="关闭", command=self._close).pack(side="right",
                                                              padx=4)

    # ---- 内部 ----
    def _meta_line(self):
        it = self._item
        parts = [consts.rarity_cn(it.get("rarity")),
                 consts.kind_cn(it.get("kind")),
                 "需同调" if it.get("attune") else "无需同调"]
        if it.get("note_only"):
            parts.append("含无法自动计算的效果")
        return " · ".join(p for p in parts if p)

    def _fill(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", card_text(self._item))
        self.text.config(state="disabled")

    def _equipped(self):
        if self._char is None:
            return False
        return self._item.get("id") in (self._char.items or [])

    def _sync_btn(self):
        self.toggle_btn.config(text="卸下" if self._equipped() else "装备")

    def _toggle(self):
        iid = self._item.get("id")
        if not iid or self._on_toggle is None:
            return
        self._on_toggle(iid)
        self._sync_btn()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
