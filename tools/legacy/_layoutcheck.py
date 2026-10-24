# -*- coding: utf-8 -*-
"""
布局体检 (完全后台运行, 不显示/不抢焦点)
=========================================
用 reqwidth / reqheight 判断控件是否撑破容器:
  * 主界面五个标签页 不得超过中栏可用宽度
  * 向导每一步内容 不得超过内容区高度
"""
import importlib.util
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "cb", os.path.join(DIR, "dnd55e_character_builder.py"))
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)
for fn in ("showwarning", "showinfo", "showerror"):
    setattr(cb.messagebox, fn, lambda *a, **k: None)

r = cb.Rules()
app = cb.App(selftest=True)          # withdraw, 不显示窗口
app.update_idletasks()

c = cb.Character(r)
c.class_id, c.background_id, c.species_id = "wizard", "sage", "human"
c.base_scores = {"STR": 8, "DEX": 14, "CON": 13, "INT": 15, "WIS": 12, "CHA": 10}
c.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
c.skill_prof = {"arcana", "history", "insight"}
c.feats = ["Alert"]
c.level = 3
c.subclass = "Evoker"
c.hp_current = c.hp_max()
app.set_character(c)
app.update_idletasks()

WORST_WIDTH = 606      # 1340 窗口下中栏实际可用宽度 (实测 610, 留 4px 余量)
FAIL = []
print("主界面标签页 (可用宽度 %d):" % WORST_WIDTH)
for tab in app.nb.tabs():
    w = app.nametowidget(tab)
    title = app.nb.tab(tab, "text").strip()
    rw, rh = w.winfo_reqwidth(), w.winfo_reqheight()
    ok = rw <= WORST_WIDTH and rh <= 574
    flag = "OK " if ok else "OVER"
    if rw > WORST_WIDTH:
        FAIL.append(f"标签「{title}」需要 {rw}px > {WORST_WIDTH}px")
    if rh > 574:
        FAIL.append(f"标签「{title}」需要高 {rh}px > 574px")
    print(f"  [{flag}] {title:8s} 需要 {rw:4d} x {rh:4d}")

# ---- 满物品: 物品区自己滚动, 不能把装备页撑高 ----
print("\n满物品检查 (物品表 %d 件):" % len(cb.MAGIC_ITEMS))
_cells = len(app.item_scroll.body.winfo_children())
_iw, _ih = (app.item_scroll.body.winfo_reqwidth(),
            app.item_scroll.body.winfo_reqheight())
print(f"  物品格 {_cells} 个 · 滚动内容 {_iw} x {_ih} · "
      f"可视高度 {app.item_scroll.canvas.cget('height')}")
if _cells != len(cb.MAGIC_ITEMS):
    FAIL.append(f"物品格 {_cells} 个，与物品表 {len(cb.MAGIC_ITEMS)} 件不符")
if _iw > 560:
    FAIL.append(f"物品滚动区需宽 {_iw}px > 560px")
if app.item_hint.master is app.item_scroll.body:
    FAIL.append("物品提示行应放在滚动区外（否则会压在物品格上）")
# 标签重名检查: 依赖 ui_shell 里「只取中文名」的截断规则
# (re.split(r"\s+(?=[A-Za-z])", name, 1)[0]); 那条规则一旦改动,
# 这里的期望值也要跟着改, 否则会变成假绿。
_labels = [w.cget("text") for w in app.item_scroll.body.winfo_children()]
_dup = sorted({x for x in _labels if _labels.count(x) > 1})
if _dup:
    FAIL.append(f"物品标签重名 (分不清 +1/+2/+3): {_dup}")

# 向导各步骤内容高度 (内容区实测 646px)
WIZ_H = 646
print("\n建卡向导各步骤 (内容区可用高度 %d):" % WIZ_H)
wiz = cb.Wizard(app, r, lambda ch: None)
wiz.withdraw()
wiz.update_idletasks()
wiz.cb_class.set("法师 Wizard")
wiz._show_class()

names = {wiz._step_class: "职业", wiz._step_background: "背景",
         wiz._step_species: "种族", wiz._step_abilities: "属性",
         wiz._step_skills: "技能", wiz._step_mastery: "专精",
         wiz._step_spells: "法术", wiz._step_summary: "摘要"}

guard = 0
while True:
    guard += 1
    if guard > 12:
        break
    fn = wiz.steps[wiz.step]
    nm = names.get(fn, "?")
    # 先填好本页需要的数据, 再量高度
    if fn == wiz._step_background:
        wiz.cb_bg.set("贤者 Sage")
        wiz._render_bg_ui()
        nms = [f"{cb.ABILITY_CN[a]}({a})" for a in wiz._bg_abs]
        wiz.bg_p2.set(nms[0])
        wiz.bg_p1.set(nms[1])
    elif fn == wiz._step_species:
        wiz.cb_sp.set("人类 Human")
        wiz._show_species()
        wiz.cb_hfeat.set("Alert")
        wiz._show_hfeat_desc()
    elif fn == wiz._step_abilities:
        wiz.ab_method.set("standard")
        wiz._render_ab_ui()
        for ab, v in zip(cb.ABILITIES, cb.STANDARD_ARRAY):
            wiz.ab_picks[ab].set(str(v))
        wiz._ab_preview()
    elif fn == wiz._step_skills:
        for sid in list(wiz.skill_vars)[:wiz._skill_need]:
            wiz.skill_vars[sid].set(True)
        picked = {s for s, v in wiz.skill_vars.items() if v.get()}
        cand = [s for s in wiz.sp_skill_vars if s not in picked]
        if cand:
            wiz.sp_skill_vars[cand[0]].set(True)
    elif fn == wiz._step_spells:
        n0, n1 = cb.SPELL_COUNTS.get("wizard", (0, 0))
        wiz._sp_buckets["cantrip"] = [x["id"] for x in
                                      wiz.r.class_spells("wizard", 0)[:n0]]
        wiz._sp_buckets["lvl1"] = [x["id"] for x in
                                   wiz.r.class_spells("wizard", 1)[:n1]]
        wiz._sp_detail_set(cb.spell_detail(
            wiz.r.class_spells("wizard", 1)[0]))
    wiz.update_idletasks()
    h = wiz.container.winfo_reqheight()
    w = wiz.container.winfo_reqwidth()
    flag = "OK " if h <= WIZ_H and w <= 716 else "OVER"
    if h > WIZ_H:
        FAIL.append(f"向导「{nm}」内容高 {h} > {WIZ_H}")
    if w > 716:
        FAIL.append(f"向导「{nm}」内容宽 {w} > 716")
    print(f"  [{flag}] {nm:4s} {w:4d} x {h:4d}")
    if fn == wiz._step_summary:
        break
    wiz.next()

wiz.destroy()

# ---- 抖动检查: 悬停长文案不应改变布局尺寸 ----
print("\n悬停/点选时的布局稳定性:")
app.update_idletasks()
targets = {
    "属性栏": app.ab_hint.master,
    "技能页": app.tab_skills,
    "状态栏": app.cond_hint.master,
    "专长页": app.tab_feats,
}
before = {k: (v.winfo_reqheight(), v.winfo_reqwidth())
          for k, v in targets.items()}
app._ability_hint("CHA")
app._skill_hover("persuasion")
app._cond_hint("力竭(另计)")
app._item_hint(cb.MAGIC_ITEMS[0])
app.feat_info.config(text=cb.feat_desc("Musician"))
app.update_idletasks()
bad = 0
for k, v in targets.items():
    after = (v.winfo_reqheight(), v.winfo_reqwidth())
    if after != before[k]:
        bad += 1
        FAIL.append(f"{k} 在提示文字变化后重排: {before[k]} -> {after}")
        print(f"  ✗ {k}: {before[k]} -> {after}")
    else:
        print(f"  ✓ {k} 尺寸不变 {after}")
app.destroy()

# ---- 弹窗: 内容不能被挤出可视区 ----
# 历史 bug: 变形对话框写死 760x540, 内容要 674 高, 底部「变形」按钮整条被裁,
# 用户表现为「德鲁伊不能变身」。所有弹窗改为 fit() 自适应, 这里逐个体检。
from dnd55e.dialogs import (DiceDialog, FeatPickerDialog,  # noqa: E402
                            InvocationDialog, ItemCardDialog, LevelUpDialog,
                            MetamagicDialog, SpellbookDialog,
                            SummonCardDialog, WildShapeDialog)

print("\n弹窗尺寸 (内容 req 必须 <= 窗口):")


def _mk(role, level, sub=None):
    ch = cb.Character(r)
    ch.class_id, ch.level = role, level
    ch.subclass = sub
    ch.background_id, ch.species_id = "sage", "human"
    ch.hp_current = ch.hp_max()
    return ch


_d19 = _mk("druid", 19, "Circle of the Moon")
_d2 = _mk("druid", 2)
_w5 = _mk("wizard", 5, "Evoker")
_s5 = _mk("sorcerer", 5)
_s5.metamagic = ["empowered", "quickened"]
_f2 = _mk("fighter", 2)
_f18 = _mk("fighter", 18)
_spell = {"name": "火球术", "level": 3, "school": "塑能", "id": "fireball"}
_w12 = _mk("warlock", 12, "Fiend")
_summon = next((s for s in r.spells.values() if s.get("summon")), None)

_app2 = cb.App(selftest=True)
_cases = [("骰子工具", lambda: DiceDialog(_app2)),
          ("专长选择", lambda: FeatPickerDialog(_app2, _d19, selftest=True)),
          ("荒野变形(19级月环)",
           lambda: WildShapeDialog(_app2, _d19, selftest=True)),
          ("法师法术书", lambda: SpellbookDialog(_app2, _w5, selftest=True)),
          ("升级 2→3", lambda: LevelUpDialog(_app2, _f2)),
          ("升级 18→19", lambda: LevelUpDialog(_app2, _f18)),
          ("物品效果卡", lambda: ItemCardDialog(
              _app2, next(iter(cb.ITEMS_BY_ID.values())), selftest=True)),
          ("超魔法", lambda: MetamagicDialog(_app2, _s5, _spell)),
          ("魔能祈唤", lambda: InvocationDialog(
              _app2, _w12, selftest=True))]
if _summon:
    _cases.append(("召唤物卡",
                   lambda: SummonCardDialog(_app2, _summon, selftest=True)))

for _nm, _factory in _cases:
    _d = _factory()
    _d.update_idletasks()
    _fw, _fh = getattr(_d, "_fit_size", (0, 0))
    _rw, _rh = _d.winfo_reqwidth(), _d.winfo_reqheight()
    _ok = _fw >= _rw and _fh >= _rh
    print(f"  [{'OK ' if _ok else 'OVER'}] {_nm:16s} 内容 {_rw:4d}x{_rh:4d}"
          f" 窗口 {_fw:4d}x{_fh:4d}")
    if not _ok:
        FAIL.append(f"弹窗「{_nm}」内容 {_rw}x{_rh} 超出窗口 {_fw}x{_fh}")
    _d.destroy()

# 主窗口: 全部角色下内容都装得下 (窗口会按 req 自动放大)
for _role, _lv, _sub, _tag in (("druid", 19, "Circle of the Moon", "德鲁伊19"),
                               ("druid", 3, "Circle of the Moon", "德鲁伊3"),
                               ("sorcerer", 2, None, "术士2"),
                               ("wizard", 20, "Evoker", "法师20")):
    _ch = _mk(_role, _lv, _sub)
    _app2.set_character(_ch)
    _app2.update_idletasks()
    _fw, _fh = getattr(_app2, "_fit_size", (1340, 860))
    _rw, _rh = _app2.winfo_reqwidth(), _app2.winfo_reqheight()
    _ok = _fw >= _rw and _fh >= _rh
    print(f"  [{'OK ' if _ok else 'OVER'}] 主窗口 {_tag:8s} 内容 {_rw:4d}x{_rh:4d}"
          f" 窗口 {_fw:4d}x{_fh:4d}")
    if not _ok:
        FAIL.append(f"主窗口({_tag}) 内容 {_rw}x{_rh} 超出 {_fw}x{_fh}")

# 法术位: 9 个环位排成两行 (单行要 1008px, 中栏只有 610)
_w20 = _mk("wizard", 20, "Evoker")   # 9 个环位才有说服力
_app2.set_character(_w20)
_app2.refresh()
_app2.update_idletasks()
_rows = {w.grid_info().get("row") for w in _app2.slots_frame.winfo_children()}
_tab_w = _app2.tab_spells.winfo_reqwidth()
print(f"  [{'OK ' if max(_rows, default=0) >= 1 else 'OVER'}] 法术位 9 环分 "
      f"{max(_rows, default=0) + 1} 行 · 法术页需要宽 {_tab_w}")
if max(_rows, default=0) < 1:
    FAIL.append("法术位仍是单行 (会被中栏横向裁掉)")
if _tab_w > 608:
    FAIL.append(f"法术页需要宽 {_tab_w} > 608")
# ---- 邪术师 10 个祈唤 / 野蛮人攻击选项: 职业页不能被撑宽 ----
print("\n职业页新增块 (可用宽度 606):")
for _role, _lv, _sub, _tag in (("warlock", 20, "Fiend", "邪术师20·10祈唤"),
                               ("barbarian", 17, None, "野蛮人17·攻击选项")):
    _ch = _mk(_role, _lv, _sub)
    if _role == "warlock":
        _ch.invocations = [x["id"] for x in cb.INVOCATIONS[:10]]
    _app2.set_character(_ch)
    _app2.refresh()
    _app2.update_idletasks()
    _bw = _app2.class_body.winfo_reqwidth()
    _tw = _app2.tab_class.winfo_reqwidth()
    _ok = _bw <= 600 and _tw <= 608
    print(f"  [{'OK ' if _ok else 'OVER'}] {_tag:16s} 内容 {_bw:4d} · "
          f"标签页 {_tw:4d}")
    if not _ok:
        FAIL.append(f"职业页({_tag}) 内容宽 {_bw} / 标签页 {_tw} 超出中栏")
_app2.destroy()

print("\n" + "=" * 50)
if FAIL:
    for f in FAIL:
        print("✗", f)
    sys.exit(1)
print("LAYOUT OK — 无内容溢出")
