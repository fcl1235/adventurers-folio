# -*- coding: utf-8 -*-
"""P6f 验收：63 条 note_only 物品的完整效果可查看。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "cb", os.path.join(ROOT, "dnd55e_character_builder.py"))
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)

from dnd55e import consts
from dnd55e.dialogs import ItemCardDialog
from dnd55e.dialogs.item_card import card_text, mech_lines

FAIL = []
N = 0


def check(ok, msg):
    global N
    N += 1
    if ok:
        print(f"  ✓ {msg}")
    else:
        print(f"  ✗ {msg}")
        FAIL.append(msg)


items = consts.MAGIC_ITEMS
by_id = consts.ITEMS_BY_ID
note_only = [it for it in items if it.get("note_only")]

print("[1] note_only 物品总量")
check(len(note_only) == 63, f"note_only {len(note_only)} 条 (应为 63)")

print("[2] 提示行不再截断")
app = cb.App(selftest=True)
try:
    c = cb.Character(app.rules)
    c.class_id, c.background_id, c.species_id = "wizard", "sage", "human"
    c.base_scores = {"STR": 8, "DEX": 14, "CON": 13, "INT": 15, "WIS": 12,
                     "CHA": 10}
    c.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
    c.skill_prof = {"arcana", "history", "insight"}
    c.feats = ["Alert"]
    c.level = 5
    c.subclass = "Evoker"
    c.hp_current = c.hp_max()
    app.set_character(c)
    app.update_idletasks()

    longest = max(note_only, key=lambda it: len(it.get("desc") or ""))
    note = longest.get("note") or longest.get("desc") or ""
    app._item_hint(longest)
    got = app.item_hint.cget("text")
    check(got == f"{longest['name']} —— {note}", "提示行是完整原文")
    check("…" not in got, "提示行没有省略号截断")
    check(len(note) > 76, f"选取的文案长度 {len(note)} > 76 (原截断阈值)")

    # 所有 note_only 的提示行都完整
    bad = []
    for it in note_only:
        app._item_hint(it)
        want = f"{it['name']} —— {it.get('note') or it.get('desc') or ''}"
        if app.item_hint.cget("text") != want:
            bad.append(it["id"])
    check(not bad, f"63 条提示行全部完整 (坏 {len(bad)})")

    print("[3] 详情卡文本")
    no_desc = []
    for it in note_only:
        txt = card_text(it)
        if not (it.get("desc") or it.get("note")):
            no_desc.append(it["id"])
        if it["name"] not in txt:
            bad.append(it["id"])
    check(not no_desc, f"每条都有正文 (缺 {len(no_desc)})")
    check(not bad, "每条卡片文本都含物品名")

    print("[4] 机械字段不丢")
    fb = by_id["frost_brand"]
    lines = mech_lines(fb)
    check(any("抗性" in x and "火焰" in x for x in lines),
          "霜之刃卡片显示抗性 火焰")
    vorpal = by_id["vorpal_sword"]
    lines = mech_lines(vorpal)
    check(any("攻击加值 +3" in x for x in lines), "斩首剑显示攻击加值 +3")
    check(any("伤害加值 +3" in x for x in lines), "斩首剑显示伤害加值 +3")
    robe = by_id["robe_of_the_archmagi"]
    lines = mech_lines(robe)
    check(any("基础 AC" in x for x in lines), "大法师长袍显示基础 AC")
    check(any("法术豁免 DC" in x for x in lines), "大法师长袍显示法术 DC")
    plain = by_id["animated_shield"]
    check(mech_lines(plain) == [], "纯叙述物品没有机械字段")

    print("[5] 对话框")
    dlg = app._item_card_open("frost_brand")
    app.update_idletasks()
    body = dlg.text.get("1.0", "end")
    check("Frost Brand" in body, "卡片含英文名")
    check(fb["desc"][:20] in body, "卡片含完整 desc 开头")
    check("极稀有" in dlg.meta_lbl.cget("text"), "标注稀有度")
    check("需同调" in dlg.meta_lbl.cget("text"), "标注需同调")
    check(dlg.toggle_btn.cget("text") == "装备", "初始按钮为「装备」")
    dlg._toggle()
    app.update_idletasks()
    check("frost_brand" in c.items, "点装备后进入角色物品列表")
    check(dlg.toggle_btn.cget("text") == "卸下", "按钮变为「卸下」")
    dlg._toggle()
    app.update_idletasks()
    check("frost_brand" not in c.items, "再点一次移出")
    check(dlg.toggle_btn.cget("text") == "装备", "按钮变回「装备」")
    dlg._close()

    # 纯查阅模式（无角色）不给装/卸按钮
    dlg2 = ItemCardDialog(app, plain, selftest=True)
    app.update_idletasks()
    check(dlg2.toggle_btn.winfo_manager() == "", "无角色时不显示装/卸按钮")
    check(card_text(plain).count("（此物品还有") == 1, "note_only 提示只出现一次")
    dlg2._close()

    print("[6] 物品格右键绑定")
    app.nb.select(2)
    app.update_idletasks()
    a_cb = app.item_cbs.get("frost_brand")
    check(a_cb is not None, "物品格存在 frost_brand")
    check(bool(a_cb.bind("<Button-3>")), "左键勾选之外绑定了右键详情")
    app._item_card_open("frost_brand")
    app.update_idletasks()
    cards = [w for w in app.winfo_children() if isinstance(w, ItemCardDialog)]
    check(len(cards) == 1, "右键打开详情卡")
    if cards:
        cards[0]._close()
finally:
    try:
        app.destroy()
    except Exception:
        pass

print()
if FAIL:
    print(f"UIPROBE FAIL — {len(FAIL)}/{N} 项失败")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print(f"UIPROBE OK — {N} 项全部通过")
