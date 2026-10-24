# -*- coding: utf-8 -*-
"""
文案审计 (隐藏运行)
===================
遍历所有控件的 text / 菜单项 / 标签页标题, 找出「含英文但无中文」的界面文案。
白名单: 骰子记号(d20/2d6)、属性缩写、AC/HP/XP/DC 等游戏术语。
"""
import importlib.util
import os
import re

DIR = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "cb", os.path.join(DIR, "dnd55e_character_builder.py"))
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)
for fn in ("showwarning", "showinfo", "showerror"):
    setattr(cb.messagebox, fn, lambda *a, **k: None)

ALLOW = re.compile(r"^(d\d+|\d+d\d+([+-]\d+)?|AC|HP|XP|DC|STR|DEX|CON|INT|WIS|CHA"
                   r"|PB|dnd\d+(\.\d+)?|v\d+|Ctrl\+[A-Z])$", re.I)
CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]{2,}")

bad = []


def scan_text(txt, where):
    if not txt:
        return
    txt = str(txt).strip()
    if not txt or CJK.search(txt) or ALLOW.match(txt):
        return
    if LATIN.search(txt):
        bad.append((where, txt))


def walk(w, depth=0):
    try:
        cls = w.winfo_class()
    except Exception:
        return
    try:
        if "text" in w.keys():
            scan_text(w.cget("text"), cls)
        elif cls in ("TCombobox",):
            pass
    except Exception:
        pass
    for ch in w.winfo_children():
        walk(ch, depth + 1)


r = cb.Rules()
app = cb.App(selftest=True)
app.update_idletasks()
walk(app)

# 菜单
for mi in ("文件", "角色", "工具", "帮助"):
    pass
try:
    menubar = app.nametowidget(app.cget("menu"))
    for i in range(menubar.index("end") + 1):
        if menubar.type(i) == "tearoff":
            continue
        name = menubar.entrycget(i, "label")
        sub = app.nametowidget(menubar.entrycget(i, "menu"))
        for j in range(sub.index("end") + 1):
            try:
                scan_text(sub.entrycget(j, "label"), "菜单/" + str(name))
            except Exception:
                pass
except Exception as e:
    print("菜单读取失败:", e)

# 建卡向导各步骤
c = cb.Character(r)
c.class_id, c.background_id, c.species_id = "fighter", "soldier", "human"
c.base_scores = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 8}
c.bg_bonus = {"mode": "2+1", "plus2": "STR", "plus1": "CON"}
c.skill_prof = {"athletics", "perception"}
c.hp_current = c.hp_max()
app.set_character(c)
app.update_idletasks()
walk(app)

wiz = cb.Wizard(app, r, lambda ch: None)
wiz.withdraw()
wiz.update_idletasks()
steps = ["职业", "背景", "种族", "属性", "技能", "专精", "摘要"]
for i, nm in enumerate(steps):
    if i == 0:
        wiz.cb_class.set("战士 Fighter")
        wiz._show_class()
    elif i == 1:
        wiz.cb_bg.set("士兵 Soldier")
        wiz._render_bg_ui()
        nms = [f"{cb.ABILITY_CN[a]}({a})" for a in wiz._bg_abs]
        wiz.bg_p2.set(nms[0])
        wiz.bg_p1.set(nms[1])
    elif i == 2:
        wiz.cb_sp.set("人类 Human")
        wiz._show_species()
        wiz.cb_hfeat.set("Alert")
        wiz._show_hfeat_desc()
    elif i == 3:
        wiz.ab_method.set("standard")
        wiz._render_ab_ui()
        for ab, v in zip(cb.ABILITIES, cb.STANDARD_ARRAY):
            wiz.ab_picks[ab].set(str(v))
    elif i == 4:
        for sid in list(wiz.skill_vars)[:wiz._skill_need]:
            wiz.skill_vars[sid].set(True)
    wiz.update_idletasks()
    walk(wiz)
    if i < 6:
        wiz.next()
wiz.destroy()
app.destroy()

seen = set()
print("可疑英文文案:")
for where, txt in bad:
    key = (where, txt)
    if key in seen:
        continue
    seen.add(key)
    print(f"  [{where}] {txt}")
print(f"\n共 {len(seen)} 条")
