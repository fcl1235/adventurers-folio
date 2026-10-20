# -*- coding: utf-8 -*-
"""P6e 验收：召唤法术 / 变形映射 / 召唤物详情卡。"""
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

from dnd55e import summoning
from dnd55e.dialogs import SummonCardDialog
from dnd55e.rules import Rules

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


r = Rules()

print("[1] 8 个 Summon 法术已入库")
for sid, lv, cls in (("summon-beast", 2, "druid"),
                     ("summon-fey", 3, "wizard"),
                     ("summon-undead", 3, "warlock"),
                     ("summon-aberration", 4, "warlock"),
                     ("summon-construct", 4, "wizard"),
                     ("summon-elemental", 4, "ranger"),
                     ("summon-celestial", 5, "cleric"),
                     ("summon-fiend", 6, "wizard")):
    s = r.spell(sid)
    check(bool(s), f"{sid} 存在")
    check(s and s["level"] == lv, f"{sid} 等级 {lv}")
    check(s and cls in (s or {}).get("classes", []), f"{sid} 含 {cls}")

print("[2] 带 summon 的法术共 15 条")
with_summon = [s for s in r.spells.values() if "summon" in s]
check(len(with_summon) == 15, f"共 {len(with_summon)} 条")
sb_count = sum(1 for s in with_summon if s["summon"]["kind"] == "statblock")
fl_count = sum(1 for s in with_summon if s["summon"]["kind"] == "filter")
check(sb_count == 12, f"statblock 型 {sb_count} 条")
check(fl_count == 3, f"filter 型 {fl_count} 条 (polymorph/true-polymorph/animal-shapes)")

print("[3] 召唤物数据齐备")
check(len(cb.consts.SUMMONS) == 32, f"SUMMONS {len(cb.consts.SUMMONS)} 条")
check(len(cb.consts.SUMMONS_BY_ID) == 32, "SUMMONS_BY_ID 索引完整")
for s in with_summon:
    sm = s["summon"]
    if sm["kind"] != "statblock":
        continue
    sbs = summoning.statblocks(s)
    check(len(sbs) == len(sm.get("options") or []),
          f"{s['id']} 的 options 全部能解析 ({len(sbs)})")

print("[4] 召唤物详情节渲染")
for sid in ("summon-beast", "polymorph", "animate-objects", "animal-shapes"):
    s = r.spell(sid)
    block = summoning.summon_block(s)
    check(bool(block), f"{sid} 有召唤段")
    if s["summon"]["kind"] == "statblock":
        # Animate Object 的 AC 是固定值、HP 按体型分档
        check("AC " in block and "HP " in block, f"{sid} 段内含 AC/HP")
    else:
        # 变形类法术没有固定 stat block，只给筛选条件
        check("可变形态" in block and "CR" in block,
              f"{sid} 段内含形态筛选条件")
# 不带召唤的法术不能多出段落
for sid in ("fireball", "conjure-animals", "magic-missile"):
    check(summoning.summon_block(r.spell(sid)) == "", f"{sid} 无召唤段")

print("[5] stat block 文本")
for sid in ("summon-beast", "summon-fiend", "summon-elemental"):
    sbs = summoning.statblocks(r.spell(sid))
    for sb in sbs:
        txt = summoning.card_text(sb)
        check(len(txt) > 120, f"{sb['id']} 卡片文本 {len(txt)} 字")
        check("AC " in txt and "HP " in txt, f"{sb['id']} 含 AC/HP")
        check("动作" in txt, f"{sb['id']} 含动作段")
        for k in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
            check(k in txt, f"{sb['id']} 含 {k}")

print("[6] 完整法术详情")
from dnd55e.util import spell_detail
txt = spell_detail(r.spell("summon-beast"))
check("召唤物" in txt, "详情含召唤物段")
check("Bestial Spirit" in txt, "详情含英文名")
check(txt.index("召唤物") < txt.index("升环") if "升环" in txt else True,
      "召唤段在升环之前")
txt2 = spell_detail(r.spell("polymorph"))
check("变形 / 召唤范围" in txt2, "变形术走 filter 段")
check("虫群" in txt2, "变形术标注排除虫群")

print("[7] 界面按钮")
app = cb.App(selftest=True)
try:
    c = cb.Character(app.rules)
    c.class_id, c.background_id, c.species_id = "wizard", "sage", "human"
    c.base_scores = {"STR": 8, "DEX": 14, "CON": 13, "INT": 15, "WIS": 12,
                     "CHA": 10}
    c.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
    c.skill_prof = {"arcana", "history", "insight"}
    c.feats = ["Alert"]
    c.level = 9
    c.subclass = "Evoker"
    c.spells["prepared"] = ["summon-beast", "fireball"]
    c.hp_current = c.hp_max()
    app.set_character(c)
    app.update_idletasks()

    check(hasattr(app, "summon_btn"), "有 summon_btn 按钮")
    rows = getattr(app, "_spell_cache", [])
    idx_sb = next((i for i, s in enumerate(rows)
                   if s["id"] == "summon-beast"), None)
    idx_fb = next((i for i, s in enumerate(rows)
                   if s["id"] == "fireball"), None)
    check(idx_sb is not None, "列表里有 summon-beast")
    check(idx_fb is not None, "列表里有 fireball")

    # selftest 下主窗口 withdraw, winfo_ismapped 恒为 0 → 用 pack 信息判断
    if idx_sb is not None:
        app.spell_list.selection_clear(0, "end")
        app.spell_list.selection_set(idx_sb)
        app._spell_show()
        app.update_idletasks()
        check(app.summon_btn.winfo_manager() == "pack", "选中召唤法术时按钮出现")
        txt = app.spell_detail.get("1.0", "end")
        check("召唤物" in txt, "详情框显示召唤物段")

    if idx_fb is not None:
        app.spell_list.selection_clear(0, "end")
        app.spell_list.selection_set(idx_fb)
        app._spell_show()
        app.update_idletasks()
        check(app.summon_btn.winfo_manager() == "", "普通法术时按钮隐藏")

    # 打开卡片
    if idx_sb is not None:
        app.spell_list.selection_clear(0, "end")
        app.spell_list.selection_set(idx_sb)
        app._spell_show()
        app._spell_summon()
        app.update_idletasks()
        kids = [w for w in app.winfo_children()
                if isinstance(w, SummonCardDialog)]
        check(len(kids) == 1, "弹出了 SummonCardDialog")
        if kids:
            dlg = kids[0]
            body = dlg.text.get("1.0", "end")
            check("Bestial Spirit" in body, "卡片含 stat block")
            check(dlg.count_lbl.cget("text").endswith("种形态"),
                  "卡片显示形态数")
            dlg._close()
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
