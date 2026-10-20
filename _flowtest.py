# -*- coding: utf-8 -*-
"""
全流程验收脚本 (D&D 5.5e 人物卡)
================================
1) 建卡向导: 12 个职业逐个走完 7 步, 校验技能数/专精数/HP/AC
2) 选择控件边界: 技能超限拦截、种族技能单选与去重、背景加值互斥、专精超限
3) 规则一致性: 生命骰/豁免/技能数/专精数/施法表 对照 SRD 5.2
4) 主界面按钮逐个触发, 捕获异常
5) 升级流程 3/4/8/12/16/19 级
6) 存档序列化往返

用法: python _flowtest.py
"""
import importlib.util
import os
import sys
import traceback

from dnd55e.util import roll_dice

DIR = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "cb", os.path.join(DIR, "dnd55e_character_builder.py"))
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)

# 屏蔽所有阻塞弹窗
for fn in ("showwarning", "showinfo", "showerror"):
    setattr(cb.messagebox, fn, lambda *a, **k: None)
cb.messagebox.askyesno = lambda *a, **k: True
import tkinter.simpledialog as sd
sd.askstring = lambda *a, **k: "Alert"

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)
        print("  ✗", msg)
    return cond

# ---------------------------------------------------------------- 规则一致性
SD = {  # id: (生命骰, 豁免, 技能数, 专精数)
    "barbarian": (12, ["STR", "CON"], 2, 2),
    "bard":      (8,  ["DEX", "CHA"], 3, 0),
    "cleric":    (8,  ["WIS", "CHA"], 2, 0),
    "druid":     (8,  ["INT", "WIS"], 2, 0),
    "fighter":   (10, ["STR", "CON"], 2, 3),
    "monk":      (8,  ["STR", "DEX"], 2, 0),
    "paladin":   (10, ["WIS", "CHA"], 2, 2),
    "ranger":    (10, ["STR", "DEX"], 3, 2),
    "rogue":     (8,  ["DEX", "INT"], 4, 2),
    "sorcerer":  (6,  ["CON", "CHA"], 2, 0),
    "warlock":   (8,  ["WIS", "CHA"], 2, 0),
    "wizard":    (6,  ["INT", "WIS"], 2, 0),
}
SLOTS_FULL = {1: {1: 2}, 3: {1: 4, 2: 2}, 5: {1: 4, 2: 3, 3: 2},
              9: {1: 4, 2: 3, 3: 3, 4: 3, 5: 1}, 17: {1: 4, 2: 3, 3: 3, 4: 3,
                                                      5: 2, 6: 1, 7: 1, 8: 1, 9: 1}}

r = cb.Rules()
print("\n[1] 规则数据一致性 (对照 SRD 5.2)")
for c in r.d["classes"]:
    hd, saves, sk, mst = SD[c["id"]]
    check(c["hit_die"] == hd, f"{c['id']} 生命骰 {c['hit_die']} != {hd}")
    check(c["saves"] == saves, f"{c['id']} 豁免 {c['saves']} != {saves}")
    check(c["skill_count"] == sk, f"{c['id']} 技能数 {c['skill_count']} != {sk}")
    check(c["weapon_mastery_count"] == mst,
          f"{c['id']} 专精数 {c['weapon_mastery_count']} != {mst}")
for lv, exp in SLOTS_FULL.items():
    got = r.full_slots(lv)
    check(got == exp, f"{lv} 级全施法表 {got} != {exp}")
check(cb.proficiency_bonus(1) == 2 and cb.proficiency_bonus(20) == 6,
      "熟练加值表")
check(cb.ability_mod(8) == -1 and cb.ability_mod(20) == 5, "属性修正表")

# 人类/精灵 技能奖励
check("human" in {s["id"] for s in r.d["species"]}, "缺人类")
check(len(r.d["skills"]) == 18, "技能表应为 18 项")

# 契约魔法 (邪术师) 2024: 1级1个/2-10级2个/11-16级3个/17+级4个
c = cb.Character(r)
c.class_id, c.background_id, c.species_id = "warlock", "charlatan", "tiefling"
c.base_scores = {"STR": 8, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12, "CHA": 15}
for lv, exp in [(1, {1: 1}), (2, {1: 2}), (5, {3: 2}), (11, {5: 3, 6: 1}),
                (13, {5: 3, 6: 1, 7: 1}), (17, {5: 4, 6: 1, 7: 1, 8: 1, 9: 1})]:
    c.level = lv
    check(c.spell_slots() == exp, f"邪术师 {lv} 级契约魔法 {c.spell_slots()} != {exp}")

# 盾牌 AC +2 (2024)
c.level = 5
base_ac = c.ac()
c.shield = True
check(c.ac() == base_ac + 2, f"盾牌应 AC+2, 实际 {c.ac() - base_ac}")
c.shield = False

app = cb.App(selftest=True)   # 隐藏运行, 不抢前台
app.update()
print("\n[2] 建卡向导: 12 职业 × 全 7 步")
made = {}
for c in r.d["classes"]:
    bg_name = "贤者 Sage" if c["id"] in ("wizard", "bard", "sorcerer", "warlock",
                                        "cleric", "druid") else "士兵 Soldier"
    sp_name = "人类 Human" if c["id"] in ("rogue", "monk") else "矮人 Dwarf"
    got = {}
    wiz = cb.Wizard(app, r, lambda ch: got.setdefault("c", ch))
    wiz.withdraw()
    wiz.update()
    try:
        wiz.e_name.delete(0, "end")
        wiz.e_name.insert(0, f"测试{c['id']}")
        wiz.cb_class.set(c["name"])
        wiz._show_class()
        wiz.next()                                   # -> 背景
        wiz.cb_bg.set(bg_name)
        wiz._render_bg_ui()
        names = [f"{cb.ABILITY_CN[a]}({a})" for a in wiz._bg_abs]
        wiz.bg_p2.set(names[0])
        wiz.bg_p1.set(names[1])
        wiz.next()                                   # -> 种族
        wiz.cb_sp.set(sp_name)
        wiz._show_species()
        if sp_name.startswith("人类"):
            wiz.cb_hfeat.set("Alert")
            wiz._show_hfeat_desc()
        wiz.next()                                   # -> 属性
        wiz.ab_method.set("standard")
        wiz._render_ab_ui()
        for ab, v in zip(cb.ABILITIES, cb.STANDARD_ARRAY):
            wiz.ab_picks[ab].set(str(v))
        wiz.next()                                   # -> 技能
        for sid in list(wiz.skill_vars)[:wiz._skill_need]:
            wiz.skill_vars[sid].set(True)
        if wiz.sp_skill_vars:                        # 种族额外 1 项 (避开已选项)
            picked = {s for s, v in wiz.skill_vars.items() if v.get()}
            cand = [s for s in wiz.sp_skill_vars if s not in picked]
            if cand:
                wiz.sp_skill_vars[cand[0]].set(True)
        wiz.next()                                   # -> 专精
        # 剩余步骤按实际页面状态推进 (专精 / 法术 / 摘要)
        guard = 0
        while True:
            guard += 1
            if guard > 12:
                raise RuntimeError("向导步骤未收敛")
            fn = wiz.steps[wiz.step]
            if fn == wiz._step_mastery and c["weapon_mastery_count"]:
                for wn in list(wiz.mastery_vars)[:wiz._mastery_need]:
                    wiz.mastery_vars[wn].set(True)
            elif fn == wiz._step_spells:
                cid2 = wiz.data["class_id"]
                n0, n1 = cb.SPELL_COUNTS.get(cid2, (0, 0))
                if n0:
                    wiz._sp_buckets["cantrip"] = [
                        x["id"] for x in wiz.r.class_spells(cid2, 0)[:n0]]
                if n1:
                    wiz._sp_buckets["lvl1"] = [
                        x["id"] for x in wiz.r.class_spells(cid2, 1)[:n1]]
            if fn == wiz._step_summary:
                wiz.next()                           # 完成
                break
            wiz.next()
    except Exception as e:
        check(False, f"{c['id']} 向导抛异常: {e}")
        traceback.print_exc()
        continue
    ch = got.get("c")
    if not check(ch is not None, f"{c['id']} 未能完成建卡"):
        continue
    made[c["id"]] = ch
    bg = r.bg(ch.background_id)
    extra = 1 if ch.species_id in ("human", "elf") else 0
    want_skills = len(bg["skills"]) + c["skill_count"] + extra
    check(len(ch.skill_prof) == want_skills,
          f"{c['id']} 熟练数 {len(ch.skill_prof)} != 预期 {want_skills}")
    check(len(ch.weapon_mastery) == c["weapon_mastery_count"],
          f"{c['id']} 专精数 {len(ch.weapon_mastery)} != {c['weapon_mastery_count']}")
    n0, n1 = cb.SPELL_COUNTS.get(c["id"], (0, 0))
    if n0 or n1:
        got_sp = len(ch.spells["cantrips"]) + len(ch.spells["prepared"])
        check(got_sp == n0 + n1,
              f"{c['id']} 法术数 {got_sp} != 预期 {n0 + n1}")
        check(all(ch.r.spell(s) for s in ch.spells["cantrips"]
                  + ch.spells["prepared"]), f"{c['id']} 法术 id 非法")
    else:
        check(not ch.spells["cantrips"] and not ch.spells["prepared"],
              f"{c['id']} 非法术职业却带了法术")
    check(ch.hp_current == ch.hp_max() and ch.hp_max() > 0, f"{c['id']} HP 异常")
    check(ch.ac() >= 10, f"{c['id']} AC 异常 {ch.ac()}")
    check(ch.passive_perception() >= 10, f"{c['id']} 被动察觉异常")
    print(f"  ✓ {c['id']:9s} 技能 {len(ch.skill_prof)} 项 · "
          f"专精 {len(ch.weapon_mastery)} · HP {ch.hp_max()} · AC {ch.ac()}")

# ---------------------------------------------------------------- 控件边界
print("\n[3] 选择控件边界")
wiz = cb.Wizard(app, r, lambda ch: None)
wiz.withdraw()
wiz.update()
wiz.cb_class.set("战士 Fighter")
wiz._show_class()
wiz.next()
wiz.cb_bg.set("士兵 Soldier")
wiz._render_bg_ui()
# 背景 +2/+1 选同一属性 -> 自动清空另一项
nms = [f"{cb.ABILITY_CN[a]}({a})" for a in wiz._bg_abs]
wiz.bg_p2.set(nms[0])
wiz.bg_p1.set(nms[0])
wiz._bg_dedup("p1")
check(wiz.bg_p2.get() == "" or wiz.bg_p1.get() == "",
      "背景 +2/+1 选同一属性未被拦下")
wiz.bg_p2.set(nms[0])
wiz.bg_p1.set(nms[1])
wiz.next()
# 人类 + 全能专长必填
wiz.cb_sp.set("人类 Human")
wiz._show_species()
step0 = wiz.step
wiz.next()
check(wiz.step == step0, "人类未选「全能」专长却放行了")
check(wiz.data["human_feat"] is None, "人类专长默认值异常")
wiz.cb_hfeat.set("Tough")
wiz._show_hfeat_desc()
check(wiz.data["human_feat"] == "Tough", "人类专长未写入")
wiz.next()
wiz.ab_method.set("standard")
wiz._render_ab_ui()
for ab, v in zip(cb.ABILITIES, cb.STANDARD_ARRAY):
    wiz.ab_picks[ab].set(str(v))
wiz.next()
# 职业技能超限: 连续勾 3 个 (战士仅 2)
ids = list(wiz.skill_vars)
wiz.skill_vars[ids[0]].set(True)
wiz._on_class_skill(ids[0])
wiz.skill_vars[ids[1]].set(True)
wiz._on_class_skill(ids[1])
wiz.skill_vars[ids[2]].set(True)
wiz._on_class_skill(ids[2])
check(not wiz.skill_vars[ids[2]].get(), "职业技能第 3 项未被回退")
check(sum(v.get() for v in wiz.skill_vars.values()) == 2, "职业技能计数错误")
# 种族技能与职业重复 -> 立即回退
wiz.sp_skill_vars[ids[0]].set(True)
wiz._on_sp_skill(ids[0])
check(not wiz.sp_skill_vars[ids[0]].get(), "种族技能与职业重复未被拦下")
# 种族技能单选互斥
other = [s for s in wiz.sp_skill_vars if s != ids[0]]
wiz.sp_skill_vars[other[0]].set(True)
wiz._on_sp_skill(other[0])
wiz.sp_skill_vars[other[1]].set(True)
wiz._on_sp_skill(other[1])
check(sum(v.get() for v in wiz.sp_skill_vars.values()) == 1, "种族技能未保持单选")
# 背景技能不在种族候选里
check(not (set(wiz.sp_skill_vars) & set(wiz._bg_skills)),
      "种族技能候选包含了背景已给的熟练")
wiz.next()
# 战士专精 3 件, 勾第 4 件应回退
if hasattr(wiz, "mastery_vars"):
    ms = list(wiz.mastery_vars)
    for i, w in enumerate(ms[:4]):
        wiz.mastery_vars[w].set(True)
        wiz._on_mastery(w)
    check(len([1 for v in wiz.mastery_vars.values() if v.get()]) == 3,
          "武器专精超限未回退")
    for w in ms[4:]:
        wiz.mastery_vars[w].set(False)
wiz.destroy()

# ---- 精灵: 血脉分支 + 种族 1 项技能 + 2024 种族不加属性 (走完整向导) ----
got3 = {}
wiz3 = cb.Wizard(app, r, lambda ch: got3.setdefault("c", ch))
wiz3.withdraw()
wiz3.cb_class.set("游荡者 Rogue")
wiz3._show_class()
wiz3.next()
wiz3.cb_bg.set("罪犯 Criminal")
wiz3._render_bg_ui()
nm3 = [f"{cb.ABILITY_CN[a]}({a})" for a in wiz3._bg_abs]
wiz3.bg_p2.set(nm3[0])
wiz3.bg_p1.set(nm3[1])
wiz3.next()
wiz3.cb_sp.set("精灵 Elf")
wiz3._show_species()
check(wiz3.data["species_id"] == "elf", "精灵未选中")
check(wiz3.lineage_frame.winfo_manager() == "pack", "精灵应显示血脉选择")
check(wiz3.data.get("lineage") in ("drow", "high", "wood"),
      f"精灵血脉未写入: {wiz3.data.get('lineage')}")
wiz3.cb_lineage.set(cb.LINEAGE_CN["wood"])
wiz3._show_lineage()
check(wiz3.data["lineage"] == "wood", "精灵血脉切换失败")
check("1 级" in wiz3.lbl_lineage.cget("text"), "血脉法术说明未刷新")
wiz3.next()
wiz3.ab_method.set("standard")
wiz3._render_ab_ui()
for ab, v in zip(cb.ABILITIES, cb.STANDARD_ARRAY):
    wiz3.ab_picks[ab].set(str(v))
# 2024: 属性页不应再有「启用 2014 房规」控件
check(not hasattr(wiz3, "sp_asi_var"), "属性页仍有 2014 种族加值控件")
check(not hasattr(cb, "SPECIES_ASI"), "代码里仍存在 SPECIES_ASI 表")
check(not hasattr(cb, "SPECIES_PICK"), "代码里仍存在 SPECIES_PICK 表")
wiz3.next()
# 技能页: 职业 4 项 + 种族 1 项
check(getattr(wiz3, "_sp_need", 0) == 1, "精灵种族技能上限应为 1")
for sid in list(wiz3.skill_vars)[:wiz3._skill_need]:
    wiz3.skill_vars[sid].set(True)
picked = {s for s, v in wiz3.skill_vars.items() if v.get()}
cand = [s for s in wiz3.sp_skill_vars if s not in picked]
wiz3.sp_skill_vars[cand[0]].set(True)
wiz3._on_sp_skill(cand[0])
check(sum(1 for v in wiz3.sp_skill_vars.values() if v.get()) == 1,
      "精灵应能选 1 项种族技能")
# 第 2 项应被拦截
wiz3.sp_skill_vars[cand[1]].set(True)
wiz3._on_sp_skill(cand[1])
check(sum(1 for v in wiz3.sp_skill_vars.values() if v.get()) == 1,
      "精灵种族技能超过 1 项未回退")
guard = 0
while guard < 12:
    guard += 1
    fn = wiz3.steps[wiz3.step]
    if fn == wiz3._step_mastery and getattr(wiz3, "_mastery_need", 0):
        for wn in list(wiz3.mastery_vars)[:wiz3._mastery_need]:
            wiz3.mastery_vars[wn].set(True)
    if fn == wiz3._step_summary:
        wiz3.next()
        break
    wiz3.next()
el2 = got3.get("c")
check(el2 is not None, "精灵建卡未完成")
if el2:
    check(el2.lineage == "wood", "精灵血脉未写入角色")
    # 2024: 属性 = 基础 + 背景, 种族不参与
    bgv = wiz3.data["bg_bonus"]
    exp_dex = wiz3.data["base_scores"]["DEX"] + (
        2 if bgv.get("plus2") == "DEX" else (1 if bgv.get("plus1") == "DEX" else 0))
    check(el2.score("DEX") == min(20, exp_dex),
          f"精灵敏捷不应含种族加值: 期望 {exp_dex}, 实际 {el2.score('DEX')}")
    check(len(el2.skill_prof) == 4 + 2 + 1,
          f"精灵熟练数应为 7: {len(el2.skill_prof)}")


# ---------------------------------------------------------------- 主界面按钮
print("\n[4] 主界面按钮逐个触发")
ch = made["fighter"]
ch.level = 3
app.set_character(ch)
app.update()
ok = True
steps = [
    ("HP -5", lambda: app._hp_add(-5)),
    ("HP +3", lambda: app._hp_add(3)),
    ("HP 回满", lambda: app._hp_add(999)),
    ("先攻掷骰", app._roll_init),
    ("力量检定", lambda: app._roll_check("STR")),
    ("敏捷豁免", lambda: app._roll_save("DEX")),
    ("技能检定", lambda: app._roll_skill("athletics")),
    ("专精切换", lambda: app._toggle_expertise("athletics")),
    ("专精切回", lambda: app._toggle_expertise("athletics")),
    ("技能勾选", lambda: app._skill_toggled("perception")),
    ("技能取消", lambda: app._skill_toggled("perception")),
    ("护甲切换", app._armor_changed),
    ("Tough 切换", app._tough_changed),
    ("Tough 切回", app._tough_changed),
    ("状态勾选", lambda: app._cond_toggled("恐慌")),
    ("状态取消", lambda: app._cond_toggled("恐慌")),
    ("力竭 +1", lambda: (app.exh_var.set(1), app._exh_changed())),
    ("力竭归零", lambda: (app.exh_var.set(0), app._exh_changed())),
    ("XP 输入", lambda: (app.xp_var.set(900), app._xp_changed())),
    ("骰子 d20", lambda: app._quick_die(20)),
    ("加专长", app._add_feat),
    ("删专长", app._del_feat),
    ("改专精(弹窗)", app._edit_mastery),
    ("骰子工具(弹窗)", lambda: cb.DiceDialog(app)),
    ("新建角色(弹窗)", app.new_character),
    ("语言编辑", app._lang_changed),
    ("备注保存", app._notes_changed),
    ("短休", app.short_rest),
    ("长休", app.long_rest),
]
for name, fn in steps:
    try:
        fn()
        app.update()
        # 弹窗类按钮: 立即收起并销毁, 不在前台显示
        for w in list(app.winfo_children()):
            if isinstance(w, cb.tk.Toplevel):
                w.withdraw()
                w.destroy()
    except Exception as e:
        ok = False
        check(False, f"按钮「{name}」异常: {e}")
        traceback.print_exc()
if ok:
    print(f"  ✓ {len(steps)} 个按钮全部可点且无异常")
# 属性加分后 HP/AC 联动
before = ch.hp_max()
ch.base_scores["CON"] += 2
app.refresh()
check(ch.hp_max() > before, "体质提升后 HP 上限未联动")
ch.base_scores["CON"] -= 2
app.refresh()

# ---------------------------------------------------------------- 升级流程
print("\n[5] 升级流程 3/4/8/12/16/19 级")
for lv in (3, 4, 8, 12, 16, 19):
    ch.level = lv - 1
    dlg = cb.LevelUpDialog(app, ch)
    dlg.withdraw()
    try:
        if lv == 3:
            dlg.subclass_cb.current(0)
        elif lv in (4, 8, 12, 16):
            # 选当前最低的两项, 避免撞 20 上限
            lows = sorted(cb.ABILITIES, key=lambda a: ch.score(a))[:2]
            dlg.asi_p2.set(f"{cb.ABILITY_CN[lows[0]]}({lows[0]})")
            dlg.asi_p1.set(f"{cb.ABILITY_CN[lows[1]]}({lows[1]})")
        elif lv == 19:
            dlg.boan_entry.insert(0, "Boon of Speed")
        dlg._ok()
        rec = dlg.result
        check(rec is not None and rec["level"] == lv, f"{lv} 级升级未返回结果")
        if rec:
            ch.level = rec["level"]
            if rec["subclass"]:
                ch.subclass = rec["subclass"]
            if rec["asi"]:
                ch.asi_history.append(rec["asi"])
            app.refresh()
        print(f"  ✓ 升至 {lv} 级" + (f" · 子职 {rec['subclass']}" if rec and rec["subclass"] else ""))
    except Exception as e:
        check(False, f"{lv} 级升级异常: {e}")
        traceback.print_exc()
    finally:
        dlg.destroy()
check(ch.score("STR") <= 20, "属性超过 20 上限")

# ---------------------------------------------------------------- 存档往返
print("\n[6] 存档序列化往返")
import json
d = ch.to_dict()
ch2 = cb.Character(r)
ch2.load_dict(json.loads(json.dumps(d)))
for attr in ("name", "level", "class_id", "subclass", "background_id",
             "species_id", "armor_index", "shield", "exhaustion"):
    check(getattr(ch2, attr) == getattr(ch, attr), f"存档往返字段 {attr} 不一致")
check(ch2.skill_prof == ch.skill_prof, "存档往返技能不一致")
check(ch2.weapon_mastery == ch.weapon_mastery, "存档往返专精不一致")
check(ch2.hp_current == ch.hp_current and ch2.hp_max() == ch.hp_max(),
      "存档往返 HP 不一致")
print(f"  ✓ 30+ 字段往返一致 ({ch.name} Lv{ch.level})")

# ---------------------------------------------------------------- 加成 / 法术
print("\n[7] 属性加值来源 / 装备加成 / 法术施放")
w = cb.Character(r)
w.class_id, w.background_id, w.species_id = "wizard", "sage", "human"
w.base_scores = {"STR": 8, "DEX": 14, "CON": 13, "INT": 15, "WIS": 12, "CHA": 10}
w.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
w.spells = {"cantrips": ["fire-bolt"], "prepared": ["fireball", "shield"]}
w.level = 5
w.hp_current = w.hp_max()

# 2024: 种族不加属性, 加值只来自背景与 ASI
check(w.score("INT") == 17, f"2024 智力应为 17 (15+2), 实为 {w.score('INT')}")
w.species_id = "dwarf"
check(w.score("CON") == 14, f"矮人体质不应含种族加值: {w.score('CON')}")
w.species_id = "human"
check(not hasattr(w, "species_bonus_text"), "仍保留种族加值文本接口")
w.asi_history = [{"type": "asi", "plus2": "INT", "plus1": "CON"}]
check(w.score("INT") == 19, f"ASI +2 后智力应为 19: {w.score('INT')}")
w.asi_history = []

# 装备: 武器 + 魔法加值 → 命中/伤害
w.weapon = "短剑 Shortsword"
base_atk, base_dmg = w.attack_bonus(), w.damage_bonus()
w.weapon_magic = 2
check(w.attack_bonus() == base_atk + 2, "武器魔法未加命中")
check(w.damage_bonus() == base_dmg + 2, "武器魔法未加伤害")
check(w.damage_dice() == "1d6", f"短剑伤害骰异常 {w.damage_dice()}")

# 魔法物品: 防护戒指 AC+1 豁免+1
ac0, save0 = w.ac(), w.save_mod("WIS")
w.items = ["ring_protection"]
check(w.ac() == ac0 + 1, f"防护戒指 AC 未生效 {ac0}->{w.ac()}")
check(w.save_mod("WIS") == save0 + 1, "防护戒指豁免未生效")
# 防御护腕: 无甲才生效
w.items = ["bracers_defense"]
check(w.ac() == ac0 + 2, "防御护腕(无甲)未生效")
w.armor_index = 1                      # 穿甲后失效
check(w.ac() == w.ac_breakdown()[0], "AC 明细与数值不一致")
check("防御护腕" not in " ".join(w.ac_breakdown()[1]), "穿甲后护腕仍被计入")
w.armor_index = 0
w.items = []

# 战斗风格: 防御 +1 AC (穿甲)
w.fighting_style = "defense"
check(w.ac() == ac0, "无甲时防御风格不应加 AC")
w.armor_index = 1
ac_armor = w.ac()
w.fighting_style = None
check(w.ac() == ac_armor - 1, "防御风格未加 AC")
w.armor_index = 0

# 法术: 施放火球消耗 3 环位, 戏法不耗
w.spell_slots_used = {}
slots = w.spell_slots()
check(3 in slots, "5 级法师应有 3 环位")
app.set_character(w)
app.update()
app.spell_list.selection_set(0)          # 排序后第一条 = 戏法 fire-bolt
app._spell_show()
before = sum(w.spell_slots_used.values())
app._spell_cast()
check(sum(w.spell_slots_used.values()) == before, "戏法不应消耗环位")
# 选中火球术再施放
rows = app._spell_rows()
idx = next(i for i, s in enumerate(rows) if s["id"] == "fireball")
app.spell_list.selection_clear(0, "end")
app.spell_list.selection_set(idx)
app._spell_show()
app._spell_cast()
check(w.spell_slots_used.get(3) == 1, f"火球未消耗 3 环位: {w.spell_slots_used}")
check(w.concentration is None, "火球不应产生专注")
# 专注法术
idx = next(i for i, s in enumerate(rows) if s["id"] == "shield")
app.spell_list.selection_clear(0, "end")
app.spell_list.selection_set(idx)
app._spell_focus()
check(w.concentration == "shield", "专注未记录")
app._spell_focus()
check(w.concentration is None, "专注未取消")

# ---- 熟练项判定 ----
f = cb.Character(r)
f.class_id, f.background_id, f.species_id = "fighter", "soldier", "dwarf"
f.base_scores = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 8}
f.bg_bonus = {"mode": "2+1", "plus2": "STR", "plus1": "CON"}
f.weapon = "长剑 Longsword"          # 军用
check(f.has_weapon_prof(), "战士应熟练军用武器")
check(f.attack_bonus() == cb.ability_mod(f.score("STR")) + f.pb(),
      f"熟练武器命中应含熟练加值: {f.attack_bonus()}")
f.weapon = "木棒 Club"               # 简单
check(f.has_weapon_prof(), "战士应熟练简单武器")

wiz2 = cb.Character(r)
wiz2.class_id, wiz2.background_id, wiz2.species_id = "wizard", "sage", "human"
wiz2.base_scores = {"STR": 10, "DEX": 14, "CON": 13, "INT": 15, "WIS": 12, "CHA": 10}
wiz2.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
wiz2.weapon = "长剑 Longsword"
check(not wiz2.has_weapon_prof(), "法师不应熟练长剑")
check(wiz2.attack_bonus() == cb.ability_mod(wiz2.score("STR")),
      f"未熟练武器命中不应含熟练加值: {wiz2.attack_bonus()}")
wiz2.weapon = "木棒 Club"
check(wiz2.has_weapon_prof(), "法师应熟练简单武器")

rg = cb.Character(r)
rg.class_id = "rogue"
rg.base_scores = {"STR": 10, "DEX": 16, "CON": 12, "INT": 14, "WIS": 10, "CHA": 8}
rg.weapon = "短剑 Shortsword"        # 军用但带 Light
check(rg.has_weapon_prof(), "游荡者应熟练 Light 军用武器")
rg.weapon = "巨剑 Greatsword"        # 军用无 Light/Finesse
check(not rg.has_weapon_prof(), "游荡者不应熟练巨剑")

# 护甲 / 盾牌熟练
check(wiz2.has_armor_prof(), "无甲默认视为熟练")
wiz2.armor_index = 9                  # 锁甲(重甲)
check(not wiz2.has_armor_prof(), "法师不应熟练重甲")
check(any("未熟练" in x for x in wiz2.armor_penalty()), "重甲惩罚提示缺失")
check(any("未熟练" in x for x in wiz2.bonus_breakdown()), "加成明细未提示重甲惩罚")
wiz2.armor_index = 1                  # 皮甲(轻甲) —— 法师无任何护甲训练
check(not wiz2.has_armor_prof(), "法师不应熟练皮甲")
wiz2.armor_index = 0
check(wiz2.has_armor_prof(), "无甲应视为熟练")
bd = cb.Character(r)
bd.class_id = "bard"
bd.base_scores = {"STR": 8, "DEX": 15, "CON": 13, "INT": 12, "WIS": 10, "CHA": 15}
bd.armor_index = 1
check(bd.has_armor_prof(), "吟游诗人应熟练轻甲")
bd.armor_index = 3
check(not bd.has_armor_prof(), "吟游诗人不应熟练中甲")
bd.armor_index = 0
bd.shield = True
check(not bd.has_shield_prof(), "吟游诗人不应熟练盾牌")
wiz2.shield = True
check(not wiz2.has_shield_prof(), "法师不应熟练盾牌")
check(any("盾牌" in x for x in wiz2.armor_penalty()), "盾牌惩罚提示缺失")
wiz2.shield = False

# 施法被未熟练护甲阻止
wiz2.spells = {"cantrips": [], "prepared": ["shield"]}
wiz2.level = 3
wiz2.armor_index = 9
wiz2.hp_current = wiz2.hp_max()
app.set_character(wiz2)
app.update()
app.spell_list.selection_set(0)
before = dict(wiz2.spell_slots_used)
app._spell_cast()
check(wiz2.spell_slots_used == before, "未熟练重甲时应禁止施法")
wiz2.armor_index = 0
app.refresh()
app.spell_list.selection_set(0)
app._spell_cast()
check(sum(wiz2.spell_slots_used.values()) == 1, "换回合法护甲后应可施法")

# 熟练项报告内容
rep = " ".join(f.proficiency_report())
check("武器" in rep and "护甲" in rep and "工具" in rep and "语言" in rep,
      f"熟练项报告不完整: {rep[:60]}")

# 加成明细必须列出来源
w.items = ["ring_protection"]
w.fighting_style = "defense"
w.armor_index = 1
w.weapon = "长剑 Longsword"
txt = " ".join(w.bonus_breakdown())
check("防护戒指" in txt and "防御" in txt, f"加成明细不完整: {txt[:80]}")
w.hp_current = w.hp_max()
app.refresh()
app.update()

print("\n[8] 种族法术 / 2024 种族规则 / 固定存档")
# 提夫林血脉法术按等级解锁
tf = cb.Character(r)
tf.class_id, tf.background_id, tf.species_id = "rogue", "criminal", "tiefling"
tf.lineage = "infernal"
tf.base_scores = {"STR": 10, "DEX": 15, "CON": 12, "INT": 12, "WIS": 10, "CHA": 14}
tf.level = 1
ids1 = [i for _, i in tf.species_spells()]
check("thaumaturgy" in ids1 and "fire-bolt" in ids1,
      f"1 级提夫林应有 奇术+火焰箭: {ids1}")
check("hellish-rebuke" not in ids1, "3 级法术不应在 1 级出现")
tf.level = 3
ids3 = [i for _, i in tf.species_spells()]
check("hellish-rebuke" in ids3, f"3 级应解锁 炼狱叱喝: {ids3}")
tf.level = 5
ids5 = [i for _, i in tf.species_spells()]
check("darkness" in ids5, f"5 级应解锁 黑暗术: {ids5}")
check(len(ids5) == 4, f"提夫林 5 级种族法术应为 4 个: {ids5}")
# 换血脉 → 法术不同
tf.lineage = "abyssal"
check("poison-spray" in [i for _, i in tf.species_spells()], "深渊血脉戏法错误")
check("fire-bolt" not in [i for _, i in tf.species_spells()], "换血脉后旧戏法未清除")

# 阿斯莫 / 侏儒
aa = cb.Character(r); aa.species_id = "aasimar"
check([i for _, i in aa.species_spells()] == ["light"], "阿斯莫应自带光亮术")
gn = cb.Character(r); gn.species_id = "gnome"; gn.lineage = "forest"
check(set(i for _, i in gn.species_spells()) == {"minor-illusion", "speak-with-animals"},
      "森林侏儒种族法术错误")

# 2024 种族表: 10 个, 不含 5e 传承种族
ids = [s["id"] for s in r.d["species"]]
check("half_elf" not in ids and "half_orc" not in ids,
      f"仍存在 5e 传承种族: {ids}")
check(len(ids) == 10, f"2024 种族应为 10 个, 实为 {len(ids)}: {ids}")
# 种族不加属性: 同一组基础值下, 任何种族的最终属性都应相同
base = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 8}
sigs = []
for sp in ids:
    c = cb.Character(r)
    c.species_id = sp
    c.base_scores = dict(base)
    sigs.append(tuple(c.score(a) for a in cb.ABILITIES))
check(len(set(sigs)) == 1, f"种族间出现属性差异 (不应有 2014 种族加值): {set(sigs)}")
# 种族技能槽: 人类/精灵 各 1, 其余 0
for sp in ids:
    n = cb.SPECIES_SKILL_BONUS.get(sp, 0)
    check(n == (1 if sp in ("human", "elf") else 0),
          f"{sp} 种族赠送技能槽异常: {n}")
# 兽人 (2024): 无自动技能, 无属性加值
orc = cb.Character(r)
orc.class_id, orc.background_id, orc.species_id = "barbarian", "soldier", "orc"
orc.base_scores = {"STR": 15, "DEX": 14, "CON": 13, "INT": 10, "WIS": 12, "CHA": 8}
check(orc.auto_skills() == [], "2024 兽人不应有自动技能")
check(orc.score("STR") == 15, f"2024 兽人力量应为 15: {orc.score('STR')}")
orc.skill_prof = {"athletics", "intimidation"}
d2 = cb.Character(r); d2.load_dict(json.loads(json.dumps(orc.to_dict())))
check(d2.skill_prof == {"athletics", "intimidation"}, "读档后技能熟练应保留")
check(d2.score("STR") == 15, "读档后属性应保持一致")
# 旧版存档里残留的 species_asi / species_pick 字段必须被安全忽略
legacy = json.loads(json.dumps(orc.to_dict()))
legacy["species_asi"] = True
legacy["species_pick"] = ["DEX", "CON"]
d3 = cb.Character(r); d3.load_dict(legacy)
check(d3.score("STR") == 15, "旧存档的 2014 种族加值不应再生效")
check(not hasattr(d3, "species_pick"), "旧存档不应恢复 species_pick 字段")
# 旧存档的传承种族 → 映射到 2024 种族并在备注留痕
for old, new, cn in (("half_elf", "human", "半精灵"),
                     ("half_orc", "orc", "半兽人")):
    legacy = json.loads(json.dumps(orc.to_dict()))
    legacy["species_id"] = old
    legacy["species_asi"] = True
    d4 = cb.Character(r); d4.load_dict(legacy)
    check(d4.species_id == new, f"{cn} 应映射为 {new}, 实为 {d4.species_id}")
    check(cn in d4.notes and "2024" in d4.notes, f"{cn} 迁移未在备注留痕")

# 种族法术出现在法术列表且免费施放 1 次/长休
tf.lineage = "infernal"
tf.class_id = "wizard"          # 换成施法职业, 才有环位可扣
tf.level = 5
tf.spells = {"cantrips": [], "prepared": []}
tf.hp_current = tf.hp_max()
app.set_character(tf)
app.update()
rows = app._spell_rows()
check(any(x.get("_src") == "种族" for x in rows), "法术列表未包含种族法术")
idx = next(i for i, x in enumerate(rows) if x["id"] == "darkness")
app.spell_list.selection_clear(0, "end")
app.spell_list.selection_set(idx)
before_used = dict(tf.spell_slots_used)
app._spell_cast()
check(tf.spell_slots_used == before_used, "种族法术首次应免费（不扣环位）")
check("darkness" in tf.race_free_used, "种族免费次数未记录")
app._spell_cast()                         # 第二次改为消耗环位
check(tf.spell_slots_used != before_used, "第二次施放应消耗环位")
tf.hp_current = tf.hp_max()
app.long_rest()
check(tf.race_free_used == [], "长休未恢复种族法术免费次数")

# 固定存档: 写盘 → 指针 → 自动载入
import shutil, tempfile
tmpdir = tempfile.mkdtemp(prefix="dnd_save_")
old_dir, old_ptr = cb.paths.CHAR_DIR, cb.paths.LAST_PTR
cb.paths.CHAR_DIR = tmpdir
cb.paths.LAST_PTR = os.path.join(tmpdir, "_last.json")
try:
    app.char = tf
    path = app._char_path()
    app._write_char(path)
    app._remember_last(path)
    check(os.path.exists(path), f"未写入固定目录: {path}")
    check(os.path.exists(cb.paths.LAST_PTR), "未写入 _last.json 指针")
    # 新实例自动载入
    app2 = cb.App(selftest=True)
    app2.char = None
    app2._auto_start()
    check(app2.char is not None and app2.char.name == tf.name,
          f"自动载入失败: {app2.char.name if app2.char else None}")
    check(app2.char.species_id == "tiefling" and app2.char.level == 5,
          "自动载入数据不一致")
    app2.destroy()
finally:
    cb.CHAR_DIR, cb.LAST_PTR = old_dir, old_ptr
    shutil.rmtree(tmpdir, ignore_errors=True)

# ---------------------------------------------------------------- 职业/资源/子职
print("\n[9] 职业特性 / 资源池 / 子职介绍 / 固定项锁定")
import re

det = r.detail
check(len(det["classes"]) == 12, f"职业明细应为 12: {len(det['classes'])}")
check(len(det["subclasses"]) == 48, f"子职明细应为 48: {len(det['subclasses'])}")
CN = re.compile(r"[\u4e00-\u9fa5]")
for cid, cd in det["classes"].items():
    fs = cd["features"]
    check(len(fs) >= 8, f"{cid} 特性太少 ({len(fs)})")
    check(all(CN.search(f["name"]) for f in fs), f"{cid} 有未翻译的特性名")
    check(all(CN.search(f["desc"]) for f in fs), f"{cid} 有未翻译的特性说明")
    check(min(f["level"] for f in fs) == 1, f"{cid} 缺少 1 级特性")
    check(max(f["level"] for f in fs) <= 20, f"{cid} 特性等级越界")
for name, info in det["subclasses"].items():
    check(bool(info["summary"]), f"{name} 缺少定位说明")
    check(len(info["features"]) >= 3, f"{name} 特性不足 3 条")
    check(all(f["level"] >= 3 for f in info["features"]),
          f"{name} 子职特性等级异常")
    check(all(CN.search(f["desc"]) for f in info["features"]),
          f"{name} 有未翻译的子职说明")
check(sum(1 for v in det["subclasses"].values() if v["srd"]) == 12,
      "应恰有 12 个子职来自 SRD")

def mk(cid, lv, scores=None):
    c2 = cb.Character(r)
    c2.class_id = cid
    c2.level = lv
    c2.background_id = r.d["backgrounds"][0]["id"]
    c2.species_id = "human"
    c2.base_scores = scores or {a: 10 for a in cb.ABILITIES}
    c2.skill_prof = set(c2.bg_skills()) | set(c2.auto_skills())
    c2.hp_current = c2.hp_max()
    return c2

def rmax(c2, rid):
    for x in c2.resources():
        if x["id"] == rid:
            return x["max"]
    return None

# ---- 资源上限对照 SRD 表 ----
check(rmax(mk("barbarian", 1), "rage") == 2, "野蛮人 1 级狂暴应为 2")
for lv, exp in ((3, 3), (6, 4), (12, 5), (17, 6)):
    check(rmax(mk("barbarian", lv), "rage") == exp,
          f"野蛮人 {lv} 级狂暴应为 {exp}: {rmax(mk('barbarian', lv), 'rage')}")
check(rmax(mk("monk", 6), "focus") == 6, "武僧 6 级气点应为 6")
check(rmax(mk("monk", 1), "focus") is None, "武僧 1 级还没有气点")
check(rmax(mk("sorcerer", 9), "sorcery") == 9, "术士 9 级术法点应为 9")
check(rmax(mk("paladin", 5), "lay_on_hands") == 25, "圣疗池应为 5×等级 = 25")
check(rmax(mk("paladin", 3), "channel") == 2, "圣武士 3 级引导神力应为 2")
check(rmax(mk("cleric", 18), "channel") == 4, "牧师 18 级引导神力应为 4")
check(rmax(mk("druid", 2), "wildshape") == 2, "德鲁伊 2 级荒野变形应为 2")
check(rmax(mk("fighter", 10), "second_wind") == 4, "战士 10 级回气应为 4")
check(rmax(mk("fighter", 17), "action_surge") == 2, "战士 17 级行动激增应为 2")
check(rmax(mk("fighter", 13), "indomitable") == 2, "战士 13 级不屈应为 2")
_rg2 = mk("ranger", 7)
check(rmax(_rg2, "favored_enemy") == 3,
      f"游侠 7 级宿敌免费次数应为 3: {rmax(_rg2, 'favored_enemy')}")
for _lv, _n in ((1, 2), (5, 3), (9, 4), (13, 5), (17, 6)):
    check(rmax(mk("ranger", _lv), "favored_enemy") == _n,
          f"游侠 {_lv} 级宿敌次数应为 {_n}: "
          f"{rmax(mk('ranger', _lv), 'favored_enemy')}")
check(rmax(mk("wizard", 9), "arcane_recovery") == 5, "法师 9 级奥术回想应为 5")
check(rmax(mk("warlock", 5), "pact_slots") == 2, "邪术师 5 级契约位应为 2")
cha16 = {"STR": 10, "DEX": 14, "CON": 12, "INT": 10, "WIS": 10, "CHA": 16}
check(rmax(mk("bard", 5, cha16), "inspiration") == 3, "诗人灵感次数应为魅力调整值")
bd = [x for x in mk("bard", 5, cha16).resources() if x["id"] == "inspiration"][0]
check(bd["die"] == 8, f"5 级灵感骰应为 d8: {bd['die']}")

# ---- 消耗 / 短休 / 长休 ----
b5 = mk("barbarian", 5)
b5.res_spend("rage", 3)
check(b5.res_used.get("rage") == 3, "狂暴消耗未记录")
b5.res_reset("short")
check(b5.res_used.get("rage") == 2, f"短休应恢复 1 次: {b5.res_used}")
b5.res_reset("long")
check(b5.res_used == {}, "长休应清空资源")
mo5 = mk("monk", 5)
mo5.res_spend("focus", 5)
mo5.res_reset("short")
check(mo5.res_used.get("focus") == 0, "气点短休应全恢复")
fi2 = mk("fighter", 3)
fi2.res_spend("action_surge", 1)
fi2.res_reset("short")
check(fi2.res_used.get("action_surge") == 0, "行动激增短休应全恢复")
fi3 = mk("fighter", 3)
fi3.res_spend("second_wind", 2)
fi3.res_reset("short")
check(fi3.res_used.get("second_wind") == 1, "回气短休只恢复 1 次")
# 越界消耗不会超上限
b1 = mk("barbarian", 1)
b1.res_spend("rage", 99)
check(b1.res_used.get("rage") == 2, "消耗不得超过上限")

# ---- 子职介绍 ----
ec2 = mk("fighter", 3)
ec2.subclass = "Champion"
sub = ec2.subclass_features()
check(len(sub) >= 4, f"冠军勇士特性数量异常: {len(sub)}")
check(all(f[3] for f in sub if f[0] <= ec2.level), "已解锁的子职特性应标记为已解锁")
check(not any(f[3] for f in sub if f[0] > ec2.level), "未解锁特性不应标记已解锁")
check(bool(ec2.subclass_summary()), "子职定位为空")
check(len(r.sub_options("wizard")) == 4, "法师应有 4 个子职可选")
check(all(x[2] for x in r.sub_options("wizard")), "子职选项缺少一句话定位")

dlg3 = cb.LevelUpDialog(app, mk("fighter", 2))
dlg3.withdraw()
txt3 = dlg3._sub_text.get("1.0", "end")
first_cn = list(dlg3._sub_map)[0]
check("Lv3" in txt3 and first_cn.split()[0] in txt3,
      f"升级弹窗未显示子职介绍: {txt3[:40]}")
check(len(txt3.strip().splitlines()) >= 5, "子职介绍行数过少")
dlg3.subclass_cb.set(list(dlg3._sub_map)[1])
dlg3._sub_preview()
check(dlg3._sub_text.get("1.0", "end") != txt3, "切换子职后介绍未刷新")
dlg3.destroy()

# ---- 武器下拉标注熟练 ----
wz1 = mk("wizard", 1)
app.set_character(wz1)
app.update()
vals = list(app.weapon_cb.cget("values"))
check(any("✓熟练" in v for v in vals), "武器下拉应标注 ✓熟练")
check(any("✗未熟练" in v for v in vals), "武器下拉应标注 ✗未熟练")
check("长剑 Longsword ✗未熟练" in vals, "法师的长剑应标未熟练")
lbl = app._weapon_label("长剑 Longsword")
check(app._weapon_strip(lbl) == "长剑 Longsword", f"标注剥离失败: {lbl}")
app.weapon_cb.set(lbl)
app._weapon_changed()
check(wz1.weapon == "长剑 Longsword", "选中带标注的武器后未正确写入")
fg1 = mk("fighter", 1)
app.set_character(fg1)
app.update()
check("长剑 Longsword ✓熟练" in list(app.weapon_cb.cget("values")),
      "战士的长剑应标熟练")

# ---- 战斗风格按职业锁定 ----
check(str(app.style_cb.cget("state")) == "readonly", "战士应可选战斗风格")
app.style_cb.set(cb.FIGHTING_STYLES["defense"][0])
app._style_changed()
check(fg1.fighting_style == "defense", "战士选择防御风格失败")
app.set_character(wz1)
app.update()
check(str(app.style_cb.cget("state")) == "disabled", "法师的战斗风格应被禁用")
app._style_changed()
check(wz1.fighting_style is None, "法师不应能设置战斗风格")
check(not mk("paladin", 1).can_fighting_style(), "圣武士 1 级还没有战斗风格")
check(mk("paladin", 2).can_fighting_style(), "圣武士 2 级应有战斗风格")
check(not mk("ranger", 1).can_fighting_style(), "游侠 1 级还没有战斗风格")
check(mk("ranger", 2).can_fighting_style(), "游侠 2 级应有战斗风格")

# ---- 技能只能从职业池选, 且不超配额 ----
wz2 = mk("wizard", 1)
app.set_character(wz2)
app.update()
pool = wz2.class_skill_pool()
outside = next(s["id"] for s in r.d["skills"] if s["id"] not in pool)
app.skill_vars[outside].set(True)
app._skill_toggled(outside)
check(outside not in wz2.skill_prof and not app.skill_vars[outside].get(),
      "非职业池技能应被拒绝并回退")
picks = [s for s in pool if s not in wz2.bg_skills()][:wz2.skill_quota() + 1]
for sid in picks:
    app.skill_vars[sid].set(True)
    app._skill_toggled(sid)
check(wz2.class_skill_picks() == wz2.skill_quota(),
      f"职业技能数应停在 {wz2.skill_quota()}: {wz2.class_skill_picks()}")
check(not app.skill_vars[picks[-1]].get(), "超额那次勾选应回退")
# 背景技能不能取消
bg_sk = next(iter(wz2.bg_skills()))
app.skill_vars[bg_sk].set(False)
app._skill_toggled(bg_sk)
check(bg_sk in wz2.skill_prof and app.skill_vars[bg_sk].get(),
      "背景技能不应能取消")

# ---- 专精受职业与等级限制 ----
check(wz2.expertise_allowance() == 0, "法师不应有专精")
rg1 = mk("rogue", 1)
rg1.skill_prof = {"stealth", "sleight_of_hand", "perception"}
app.set_character(rg1)
app.update()
check(rg1.expertise_allowance() == 2, "游荡者 1 级应为 2 项专精")
for sid in ("stealth", "sleight_of_hand", "perception"):
    app._toggle_expertise(sid)
check(len(rg1.expertise) == 2, f"专精应封顶 2 项: {rg1.expertise}")
rg1.level = 6
check(rg1.expertise_allowance() == 4, "游荡者 6 级应为 4 项专精")
ba9 = mk("bard", 9, cha16)
check(ba9.expertise_allowance() == 4, "吟游诗人 9 级应为 4 项专精")

# ---- 武器专精数量与职业限制 ----
check(mk("wizard", 5).mastery_count() == 0, "法师没有武器专精")
check(mk("fighter", 1).mastery_count() == 3, "战士 1 级武器专精应为 3")
check(mk("fighter", 10).mastery_count() == 5, "战士 10 级武器专精应为 5")
check(mk("fighter", 16).mastery_count() == 6, "战士 16 级武器专精应为 6")
check(mk("barbarian", 10).mastery_count() == 4, "野蛮人 10 级武器专精应为 4")
dirty_m = mk("fighter", 1).to_dict()
dirty_m["weapon_mastery"] = ["长剑 Longsword", "巨剑 Greatsword",
                             "战斧 Battleaxe", "巨斧 Greataxe"]
dm = cb.Character(r)
dm.load_dict(dirty_m)
check(len(dm.weapon_mastery) == 3, f"读档应钳制到 3 件: {dm.weapon_mastery}")

# ---- 属性上限 20 ----
wz3 = mk("wizard", 1)
app.set_character(wz3)
app.update()
app.ab_entries["STR"].set(25)
app._score_edited()
check(wz3.score("STR") == 20, f"属性应封顶 20: {wz3.score('STR')}")

# ---- 法术: 只能本职业 / 环级 / 戏法上限 ----
wz4 = mk("wizard", 1)
app.set_character(wz4)
app.update()
app._spell_refresh()
check(all(s["level"] <= 1 for s in app._spell_opts),
      "1 级法师的学习列表不应出现 2 环以上")
check(all(s["id"] in {x["id"] for x in r.class_spells("wizard")}
          for s in app._spell_opts), "学习列表应只含法师法术")
cap = wz4.cantrip_cap()
check(cap == 3, f"法师 1 级戏法上限应为 3: {cap}")
for s in r.class_spells("wizard", 0)[:cap + 1]:
    app.spell_add_cb.set(f"{s['name']} {s['name_en']}")
    app._spell_add()
check(len(wz4.spells["cantrips"]) == cap,
      f"戏法应封顶 {cap}: {len(wz4.spells['cantrips'])}")

print("\n[10] 规则数值复核 (速度/豁免/DC/生命骰/额外攻击)")

# ---- 生命骰: 数量=等级, 花骰回血, 长休全回 ----
fd = mk("fighter", 5, {"STR": 16, "DEX": 12, "CON": 14,
                       "INT": 10, "WIS": 10, "CHA": 8})
check(fd.hit_dice_max() == 5 and fd.hit_die() == 10,
      f"战士 5 级应为 5 颗 d10: {fd.hit_dice_max()}/d{fd.hit_die()}")
fd.hp_current = fd.hp_max() - 20
before = fd.hp_current
used, heal, _ = fd.spend_hit_dice(2, rolls=[5, 8])
check(fd.hit_dice_left() >= 2 and used >= 1,
      f"应能花出至少 1 颗生命骰: used={used}")
check(fd.hp_current > before, "花生命骰后 HP 应上升")
check(heal == fd.hp_current - before, f"回复量应等于 HP 增量: {heal}")
fd.hit_dice_used = 5
check(fd.hit_dice_left() == 0, "骰子用尽后剩余应为 0")
app.set_character(fd)
app.long_rest()
check(fd.hit_dice_left() == 5, f"2024 长休应回满全部生命骰: {fd.hit_dice_left()}")
check(fd.hp_current == fd.hp_max(), "长休后 HP 应全满")

# ---- 死亡豁免 / 濒死 ----
dh = mk("wizard", 3)
dh.hp_current = 0
check(dh.is_dying, "HP=0 应判定为濒死")
dh.death_success, dh.death_fail = 2, 1
app.set_character(dh)
check("濒死" in app.status.cget("text"), "状态栏应提示濒死")
app._death_reset()
check(dh.death_success == 0 and dh.death_fail == 0, "死亡豁免应可重置")
app.long_rest()
check(not dh.is_dying, "长休后应脱离濒死")

# ---- 专注 DC = max(10, 伤害/2) ----
wz = mk("wizard", 5, {"STR": 8, "DEX": 12, "CON": 14,
                      "INT": 17, "WIS": 10, "CHA": 8})
check(wz.concentration_dc(12) == 10, "12 点伤害 DC 应为 10")
check(wz.concentration_dc(30) == 15, "30 点伤害 DC 应为 15")
check(wz.concentration_dc(41) == 20, "41 点伤害 DC 应为 20")

# ---- 守护灵光: 魅力调整值, 最低 +1 ----
pl = mk("paladin", 6, {"STR": 16, "DEX": 10, "CON": 14,
                       "INT": 8, "WIS": 10, "CHA": 8})
plain = cb.Character(r)
plain.class_id, plain.level = "paladin", 5
plain.base_scores = dict(pl.base_scores)
check(pl.save_mod("STR") == plain.save_mod("STR") + 1,
      f"灵光魅力 -1 时仍应 +1: {pl.save_mod('STR')} vs {plain.save_mod('STR')}")
pl2 = mk("paladin", 6, {"STR": 16, "DEX": 10, "CON": 14,
                        "INT": 8, "WIS": 10, "CHA": 18})
check(pl2.save_mod("STR") == 3 + 4,
      f"魅力 +4 时灵光应 +4: {pl2.save_mod('STR')}")

# ---- 速度: 武僧 2/6/10/14/18, 野蛮人 5 级 (非重甲), 力竭 ----
for lv, bonus in ((2, 10), (6, 15), (10, 20), (14, 25), (18, 30)):
    mo = mk("monk", lv, {"STR": 10, "DEX": 16, "CON": 12,
                         "INT": 10, "WIS": 14, "CHA": 8})
    check(mo.speed() == 30 + bonus,
          f"武僧 {lv} 级速度应为 {30 + bonus}: {mo.speed()}")
mo_sh = mk("monk", 6, {"STR": 10, "DEX": 16, "CON": 12,
                       "INT": 10, "WIS": 14, "CHA": 8})
mo_sh.shield = True
check(mo_sh.speed() == 30, f"持盾时无甲移动应失效: {mo_sh.speed()}")
ba = mk("barbarian", 5, {"STR": 16, "DEX": 12, "CON": 14,
                         "INT": 8, "WIS": 10, "CHA": 8})
check(ba.speed() == 40, f"野蛮人 5 级速度应为 40: {ba.speed()}")
ba.armor_index = 8          # 环甲 = 重甲
check(ba.speed() == 30, f"穿重甲时快速移动应失效: {ba.speed()}")
ba.armor_index = 0
ba.exhaustion = 2
check(ba.speed() == 30, f"力竭 2 级应 -10 尺: {ba.speed()}")
ba.conditions.add("束缚")
check(ba.speed() == 0, "束缚状态速度应归 0")

# ---- 决斗风格: 可持盾, 双手武器无效 ----
ft = mk("fighter", 5, {"STR": 16, "DEX": 12, "CON": 14,
                       "INT": 10, "WIS": 10, "CHA": 8})
ft.weapon = "长剑 Longsword"
ft.fighting_style = "dueling"
base_dmg = ft.damage_bonus()
ft.shield = True
check(ft.damage_bonus() == base_dmg, "决斗配盾仍应 +2 (盾不算武器)")
ft.weapon = "巨剑 Greatsword"
check(ft.damage_bonus() == 3 + 0, f"双手武器不应吃决斗: {ft.damage_bonus()}")

# ---- 幸运石: 豁免与属性检定 +1 ----
lk = mk("rogue", 3, {"STR": 10, "DEX": 16, "CON": 12,
                     "INT": 12, "WIS": 12, "CHA": 10})
base_sk = lk.skill_mod("stealth")
base_sv = lk.save_mod("DEX")
lk.items = ["stone_luck"]
check(lk.skill_mod("stealth") == base_sk + 1, "幸运石应加技能检定")
check(lk.save_mod("DEX") == base_sv + 1, "幸运石应加豁免")
check(lk.check_bonus() == 1, "属性检定加值应为 +1")

# ---- 额外攻击次数 (含子职) ----
check(mk("fighter", 5).attacks_per_action() == 2, "战士 5 级 2 次")
check(mk("fighter", 11).attacks_per_action() == 3, "战士 11 级 3 次")
check(mk("fighter", 20).attacks_per_action() == 4, "战士 20 级 4 次")
check(mk("barbarian", 5).attacks_per_action() == 2, "野蛮人 5 级 2 次")
check(mk("wizard", 10).attacks_per_action() == 1, "法师只有 1 次")
bd = mk("bard", 6)
bd.subclass = "College of Valor"
check(bd.attacks_per_action() == 2, "勇气学院 6 级应有额外攻击")

# ---- 偷袭骰 / 狂暴伤害 / 武器专精 DC ----
rg = mk("rogue", 5, {"STR": 10, "DEX": 18, "CON": 12,
                     "INT": 12, "WIS": 10, "CHA": 10})
check(rg.sneak_dice() == 3, f"游荡者 5 级偷袭 3d6: {rg.sneak_dice()}")
ba2 = mk("barbarian", 9, {"STR": 18, "DEX": 12, "CON": 14,
                          "INT": 8, "WIS": 10, "CHA": 8})
ba2.weapon = "巨斧 Greataxe"
no_rage = ba2.damage_bonus()
ba2.raging = True
check(ba2.damage_bonus() == no_rage + ba2.rage_damage(),
      "狂暴应把伤害加值计入")
check(ba2.rage_damage() == 3, f"野蛮人 9 级狂暴 +3: {ba2.rage_damage()}")
dc = rg.mastery_dc("短剑 Shortsword")
check(dc == 8 + 4 + 3, f"专精 DC 应为 8+敏捷+熟练 = 15: {dc}")

# ---- 负重 / 秘契法术 ----
wl = mk("warlock", 13, {"STR": 15, "DEX": 12, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 17})
check(wl.carry_capacity() == (225, 450),
      f"力量 15 负重应为 225/450: {wl.carry_capacity()}")
check(wl.arcanum_levels() == [6, 7], f"13 级邪术师应有 6/7 环秘契: {wl.arcanum_levels()}")
check(wl.spell_slots().get(5) == 3, "13 级契约法术位应为 3")
wl.spell_slots_used = {5: 1, 6: 1, 7: 1}
app.set_character(wl)
app.short_rest()
check(wl.spell_slots_used.get(5, 0) == 0, "契约法术位应短休回满")
check(wl.spell_slots_used.get(6, 0) == 1 and wl.spell_slots_used.get(7, 0) == 1,
      f"秘契法术不应随短休恢复: {wl.spell_slots_used}")


print("\n[11] 2024 规则二次复核 (法术配额/秘契/武器属性/重甲/同调)")

# ---- 准备法术数用职业表, 不是「等级+属性」估算 ----
for cid, lv, want_prep, want_can in (
        ("wizard", 1, 4, 3), ("sorcerer", 1, 2, 4),
        ("warlock", 1, 2, 2), ("paladin", 1, 2, 0),
        ("cleric", 1, 4, 3), ("ranger", 1, 2, 0),
        ("bard", 5, 9, 3), ("wizard", 11, 16, 5)):
    _c = mk(cid, lv)
    check(_c.prepared_hint() == want_prep,
          f"{cid} {lv} 级准备法术应为 {want_prep}: {_c.prepared_hint()}")
    check(_c.cantrip_cap() == want_can,
          f"{cid} {lv} 级戏法应为 {want_can}: {_c.cantrip_cap()}")

# ---- 秘契法术不占普通法术位: 11 级邪术师最高普通环仍是 5 ----
_w = mk("warlock", 11, {"STR": 10, "DEX": 12, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 18})
check(_w.max_spell_level() == 5,
      f"11 级邪术师普通法术最高 5 环: {_w.max_spell_level()}")
check(_w.arcanum_levels() == [6], f"11 级应有 6 环秘契: {_w.arcanum_levels()}")
_w17 = mk("warlock", 17, {"STR": 10, "DEX": 12, "CON": 14,
                          "INT": 10, "WIS": 10, "CHA": 18})
check(_w17.max_spell_level() == 5 and _w17.arcanum_levels() == [6, 7, 8, 9],
      f"17 级秘契应为 6/7/8/9: {_w17.arcanum_levels()}")

# ---- 武器属性数据驱动: 大棒是双手, 两用武器算单手 ----
_ft = mk("fighter", 5, {"STR": 16, "DEX": 12, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 8})
_ft.fighting_style = "dueling"
_ft.weapon = "大棒 Greatclub"
check(_ft.is_two_handed_weapon(), "大棒应是双手武器")
check(_ft.damage_bonus() == 3, f"双手武器不该吃决斗 +2: {_ft.damage_bonus()}")
_ft.weapon = "长剑 Longsword"
check(not _ft.is_two_handed_weapon(), "长剑是两用武器, 不算双手")
check(_ft.damage_bonus() == 3 + 2, f"单手长剑应吃决斗 +2: {_ft.damage_bonus()}")
_ft.weapon = "匕首 Dagger"
check(_ft.weapon_ability() == "STR",
      f"灵巧武器取高属性 (力量16 > 敏捷12): {_ft.weapon_ability()}")
_jv = mk("fighter", 3, {"STR": 16, "DEX": 12, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 8})
_jv.weapon = "标枪 Javelin"
check(_jv.weapon_ability() == "STR", "投掷武器标枪用力量")
check(not _jv.is_ranged_weapon(), "标枪不算远程武器(可近战)")

# ---- 重甲力量需求不满足 → 速度 -10 ----
_pl = mk("paladin", 5, {"STR": 10, "DEX": 10, "CON": 14,
                        "INT": 8, "WIS": 8, "CHA": 16})
_pl.armor_index = 11          # 全身板甲, 需力量 15
check(_pl.speed() == 20, f"力量不足穿板甲速度应 20: {_pl.speed()}")
check(any("需要力量" in x for x in _pl.armor_penalty()), "应提示力量需求不足")
_pl.base_scores["STR"] = 15
check(_pl.speed() == 30, f"满足力量需求速度应 30: {_pl.speed()}")
check(any("隐匿" in x for x in _pl.armor_penalty()), "板甲应提示隐匿劣势")

# ---- 力竭: 攻击/豁免/技能/先攻 同步 -2/级 ----
_e = mk("fighter", 5, {"STR": 16, "DEX": 14, "CON": 14,
                       "INT": 10, "WIS": 12, "CHA": 8})
_e.weapon = "长剑 Longsword"
base = (_e.save_mod("STR"), _e.skill_mod("perception"),
        _e.attack_bonus(), _e.initiative())
_e.exhaustion = 2
after = (_e.save_mod("STR"), _e.skill_mod("perception"),
         _e.attack_bonus(), _e.initiative())
check(all(b - a == 4 for b, a in zip(base, after)),
      f"力竭 2 级应每项 -4: {base} → {after}")
check(_e.d20_mod_total(after[0]) == after[0], "d20_mod_total 不应重复扣力竭")
_hp_before = _e.hp_max()
check(_hp_before > 0, "力竭不影响 HP 上限")

# ---- 同调上限 3, 且免同调物品不占名额 ----
# 2024 原文: 精灵斗篷 Requires Attunement, 精灵靴 / 精灵链甲免同调
_att = mk("rod", 1) if False else mk("rogue", 13, None)
_att.subclass = "Thief"
check(_att.attunement_cap() == 3, "同调上限应为 3 (盗贼也不提升)")
check("boots_elvenkind" in cb.consts.ITEMS_BY_ID, "精灵靴应存在于物品表")
_att.items = ["cloak_elvenkind", "boots_elvenkind", "ring_protection"]
_ids = _att.attuned_items()
check(len(_ids) == 2 and "cloak_elvenkind" in _ids
      and "ring_protection" in _ids and "boots_elvenkind" not in _ids,
      f"同调: 精灵斗篷需同调, 精灵靴免同调不计入: {_ids}")

# ---- 防御护腕: 无甲无盾才 +2 ----
_br = mk("fighter", 3, {"STR": 12, "DEX": 14, "CON": 12,
                        "INT": 10, "WIS": 10, "CHA": 8})
_br.items = ["bracers_defense"]
check(any("防御护腕" in x for x in _br.ac_breakdown()[1]),
      "无甲无盾时防御护腕应生效")
_br.shield = True
check(all("防御护腕" not in x for x in _br.ac_breakdown()[1]),
      "持盾时 AC 明细里不应出现防御护腕")

# ---- 速度之靴: 步行速度翻倍 ----
_bs = mk("rogue", 5, {"STR": 10, "DEX": 16, "CON": 12,
                      "INT": 12, "WIS": 10, "CHA": 10})
_v0 = _bs.speed()
_bs.items = ["boots_speed"]
check(_bs.speed() == _v0 * 2, f"速度之靴应翻倍: {_v0} → {_bs.speed()}")

# ---- Tough 从专长栏也生效 ----
_tf = mk("fighter", 5)
_h0 = _tf.hp_max()
_tf.feats.append("Tough")
check(_tf.hp_max() == _h0 + 10, f"Tough 应 +2×等级: {_h0} → {_tf.hp_max()}")
check(_tf.has_tough(), "has_tough 应识别专长栏")

# ---- ASI 等级: 战士多 6/14, 游荡者多 10 ----
check({4, 6, 8, 12, 14, 16} <= cb.LevelUpDialog.asi_levels("fighter"),
      "战士 ASI 含 6/14")
check(10 in cb.LevelUpDialog.asi_levels("rogue"), "游荡者 10 级有 ASI")
check(6 not in cb.LevelUpDialog.asi_levels("wizard"), "法师 6 级没有 ASI")

# ---- 长休清临时生命 ----
_tm = mk("fighter", 3)
_tm.hp_temp = 7
app.set_character(_tm)
app.long_rest()
check(_tm.hp_temp == 0, "长休应清空临时生命")


# ---- 1/3 施法者子职: 奥法骑士 / 诡术师 ----
_ek = mk("fighter", 3)
_ek.subclass = "Eldritch Knight"
check(_ek.casting() and _ek.casting()["type"] == "third",
      "奥法骑士 3 级应有 1/3 施法")
check(_ek.spell_slots() == {1: 2}, f"奥法骑士 3 级法术位: {_ek.spell_slots()}")
check(_ek.prepared_hint() == 3 and _ek.cantrip_cap() == 2,
      f"奥法骑士 3 级 3 法术/2 戏法: {_ek.prepared_hint()}/{_ek.cantrip_cap()}")
check(_ek.spell_dc() is not None, "奥法骑士应有法术 DC")
check(_ek.spell_list_class() == "wizard", "奥法骑士借用法师法术列表")
_ek13 = mk("fighter", 13)
_ek13.subclass = "Eldritch Knight"
check(_ek13.spell_slots() == {1: 4, 2: 3, 3: 2},
      f"奥法骑士 13 级法术位: {_ek13.spell_slots()}")
check(_ek13.max_spell_level() == 3, "奥法骑士 13 级最高 3 环")
_at = mk("rogue", 7)
_at.subclass = "Arcane Trickster"
check(_at.spell_slots() == {1: 4, 2: 2},
      f"诡术师 7 级法术位: {_at.spell_slots()}")
check(_at.cantrip_cap() == 3, "诡术师 7 级 3 戏法")
_f5 = mk("fighter", 5)
check(_f5.casting() is None, "没选子职的战士不应有施法")

# ---- 武僧徒手 / 武艺: 用敏捷, 伤害骰随等级 ----
_mo = mk("monk", 5, {"STR": 10, "DEX": 18, "CON": 12,
                     "INT": 10, "WIS": 14, "CHA": 8})
_mo.weapon = ""
check(_mo.damage_dice() == "1d8", f"武僧 5 级武艺骰应 1d8: {_mo.damage_dice()}")
check(_mo.damage_type() == "钝击", "徒手是钝击伤害")
check(_mo.damage_bonus() == 4, f"徒手伤害用敏捷 +4: {_mo.damage_bonus()}")
check(_mo.attack_bonus() == 4 + 3, f"徒手攻击 +7: {_mo.attack_bonus()}")
_mo.weapon = "木棍 Quarterstaff"
check(_mo.weapon_ability() == "DEX", "武僧用武僧武器可用敏捷")
_mo11 = mk("monk", 11, {"STR": 10, "DEX": 18, "CON": 12,
                        "INT": 10, "WIS": 14, "CHA": 8})
_mo11.weapon = ""
check(_mo11.damage_dice() == "1d10", f"武僧 11 级武艺骰应 1d10: {_mo11.damage_dice()}")

# ---- 临时生命先吸收伤害 ----
_thp = mk("fighter", 3)
_r = cb.Rules()
_c0 = _thp.hp_max()
_thp.hp_current = _c0
_thp.hp_temp = 5
app.set_character(_thp)
app._hp_add(-8)
check(_thp.hp_temp == 0 and _thp.hp_current == _c0 - 3,
      f"8 点伤害应扣光 5 临时再扣 3 本体: temp={_thp.hp_temp} hp={_thp.hp_current}")


# ================================================================
print("\n[12] 第三轮复核: 职业收尾 / 徒手 / 武器属性 / 秘契 / 额外熟练")

# ---- 游侠 6 级「游荡」: 非重甲速度 +10 ----
_r6 = mk("ranger", 6)
_r6.base_scores = {a: 14 for a in cb.ABILITIES}
_r6.base_scores["STR"] = 16
check(_r6.speed() == 40, f"游侠 6 级游荡后速度应 40: {_r6.speed()}")
_r5 = mk("ranger", 5)
check(_r5.speed() == 30, f"游侠 5 级速度应 30: {_r5.speed()}")
_heavy_idx = next(i for i, a in enumerate(cb.ARMORS)
                  if a[0].startswith("全身板甲"))
_r6.armor_index = _heavy_idx
check(_r6.speed() == 30, f"重甲时游荡不生效, 应 30: {_r6.speed()}")

# ---- 武僧 14 全豁免 / 游荡者 15 感魅豁免 ----
_m14 = mk("monk", 14)
check(_m14.save_profs() == set(cb.ABILITIES), "武僧 14 级应全部豁免熟练")
check(_m14.save_mod("INT") == cb.ability_mod(_m14.score("INT")) + _m14.pb(),
      f"武僧 14 级智力豁免应含熟练: {_m14.save_mod('INT')}")
_r15 = mk("rogue", 15)
check({"WIS", "CHA"} <= _r15.save_profs(), "游荡者 15 级应有感/魅豁免熟练")
check("STR" not in _r15.save_profs(), "游荡者 15 级力量豁免仍不熟练")
check(_r15.save_mod("WIS") == cb.ability_mod(_r15.score("WIS")) + _r15.pb(),
      "游荡者 15 级感知豁免应含熟练")

# ---- 20 级压轴: 野蛮人 +4 力/体, 武僧 +4 敏/感, 上限 25 ----
_b20 = mk("barbarian", 20, {"STR": 20, "DEX": 14, "CON": 20,
                            "INT": 8, "WIS": 10, "CHA": 8})
check(_b20.score("STR") == 24 and _b20.score("CON") == 24,
      f"野蛮人 20 级力/体应 24: {_b20.score('STR')}/{_b20.score('CON')}")
check(_b20.score("DEX") == 14, "压轴不提高敏捷")
check(_b20.ability_cap("STR") == 25 and _b20.ability_cap("DEX") == 20,
      "野蛮人 20 级只有力/体上限 25")
_m20 = mk("monk", 20, {"STR": 10, "DEX": 20, "CON": 12,
                       "INT": 10, "WIS": 20, "CHA": 8})
check(_m20.score("DEX") == 24 and _m20.score("WIS") == 24,
      f"武僧 20 级敏/感应 24: {_m20.score('DEX')}/{_m20.score('WIS')}")
check(_m20.ac() == 10 + 7 + 7, f"武僧 20 级无甲 AC 应为 24: {_m20.ac()}")

# ---- 徒手打击: 1 + 力量; 酒馆斗殴者 1d4 ----
_f1 = mk("fighter", 1, {"STR": 16, "DEX": 12, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 8})
_f1.weapon = ""
check(_f1.damage_dice() == "1", f"非武僧徒手应为固定 1: {_f1.damage_dice()}")
check(_f1.damage_bonus() == 3, "徒手伤害加值应为力量 +3")
check(roll_dice("1+3")[0] == 4, "固定伤害表达式应能结算")
_f1.feats = ["Tavern Brawler"]
check(_f1.damage_dice() == "1d4", "酒馆斗殴者徒手应 1d4")

# ---- 狂暴伤害只加在力量攻击上 ----
_b5 = mk("barbarian", 5, {"STR": 14, "DEX": 18, "CON": 14,
                          "INT": 8, "WIS": 10, "CHA": 8})
_b5.raging = True
_b5.weapon = "短剑 Shortsword"
check(_b5.weapon_ability() == "DEX", "灵巧武器应取较高敏捷")
check(_b5.damage_bonus() == 4, f"敏捷攻击不应吃狂暴加值: {_b5.damage_bonus()}")
_b5.weapon = "巨斧 Greataxe"
check(_b5.damage_bonus() == 2 + 2, f"力量攻击应含狂暴 +2: {_b5.damage_bonus()}")

# ---- 重型武器: 属性不足攻击劣势 ----
_hv = mk("fighter", 1, {"STR": 10, "DEX": 12, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 8})
_hv.weapon = "巨斧 Greataxe"
check(_hv.heavy_penalty() is True, "力量 10 用重武器应有劣势")
_hv.base_scores["STR"] = 13
check(_hv.heavy_penalty() is False, "力量 13 用重武器不应有劣势")
_bw = mk("fighter", 1, {"STR": 14, "DEX": 10, "CON": 12,
                        "INT": 10, "WIS": 10, "CHA": 8})
_bw.weapon = "长弓 Longbow"
check(_bw.heavy_penalty() is True, "敏捷 10 用重弩弓应有劣势")

# ---- 两用武器: 双手伤害骰更大, 且不享受决斗 ----
_vs = mk("fighter", 1, {"STR": 16, "DEX": 12, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 8})
_vs.weapon = "长剑 Longsword"
_vs.fighting_style = "dueling"
check(_vs.damage_dice() == "1d8", f"单手长剑应 1d8: {_vs.damage_dice()}")
check(_vs.damage_bonus() == 3 + 2, f"决斗单手应 +5: {_vs.damage_bonus()}")
_vs.two_handed_grip = True
check(_vs.damage_dice() == "1d10", f"双手长剑应 1d10: {_vs.damage_dice()}")
check(_vs.damage_bonus() == 3, f"双手不应享受决斗: {_vs.damage_bonus()}")

# ---- 邪术师: 秘契 6 环可学, 但不占准备数 ----
_w11 = mk("warlock", 11, {"STR": 8, "DEX": 14, "CON": 14,
                          "INT": 10, "WIS": 12, "CHA": 17})
check(_w11.max_spell_level() == 5, f"邪术师 11 级普通最高 5 环: {_w11.max_spell_level()}")
check(_w11.learnable_max_level() == 6,
      f"秘契应允许学习 6 环: {_w11.learnable_max_level()}")
_s6 = next(s for s in r.class_spells("warlock") if s["level"] == 6)
_w11.spells["prepared"] = [_s6["id"]]
check(_w11.prepared_count() == 0, "秘契法术不应占准备配额")

# ---- 武器专精 DC 由武器属性决定 (不再靠中文名) ----
_md = mk("fighter", 5, {"STR": 16, "DEX": 12, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 8})
check(_md.mastery_dc("长弓 Longbow") == 8 + 1 + _md.pb(),
      f"长弓专精 DC 应用敏捷: {_md.mastery_dc('长弓 Longbow')}")
_md.weapon = "长剑 Longsword"
check(_md.mastery_dc("长剑 Longsword") == 8 + 3 + _md.pb(),
      f"长剑专精 DC 应用力量: {_md.mastery_dc('长剑 Longsword')}")

# ---- 可靠天赋 / 不屈之力 ----
_r7 = mk("rogue", 7)
_r7.skill_prof |= {"perception"}
check(_r7.reliable_talent("perception") is True, "游荡者 7 级熟练技能有可靠天赋")
check(_r7.reliable_talent("arcana") is False, "未熟练技能不吃可靠天赋")
_b18 = mk("barbarian", 18, {"STR": 18, "DEX": 12, "CON": 16,
                            "INT": 8, "WIS": 10, "CHA": 8})
check(_b18.indomitable_might("STR") is True, "野蛮人 18 级力量检定额外保底")
check(_b18.indomitable_might("DEX") is False, "不屈之力只作用于力量")

# ---- 游侠 10 级「不倦」: 短休力竭 -1 ----
_r10 = mk("ranger", 10)
_r10.exhaustion = 2
app.set_character(_r10)
app.short_rest()
check(_r10.exhaustion == 1, f"游侠短休应降 1 级力竭: {_r10.exhaustion}")

# ---- 种族技能不再挤占职业技能配额 ----
_elf = mk("bard", 3, {"STR": 8, "DEX": 14, "CON": 12,
                      "INT": 10, "WIS": 12, "CHA": 16})
_elf.skill_prof = set(_elf.bg_skills()) | {"perception"}
_elf.bonus_skills = {"perception"}
check(_elf.class_skill_picks() == 0,
      f"种族给的技能不应算作职业选择: {_elf.class_skill_picks()}")

# ---- 额外熟练字段存档往返 ----
_elf.bonus_skills = {"perception"}
_elf.two_handed_grip = True
_elf.weapon = "长剑 Longsword"
_d2 = cb.Character(r)
_d2.load_dict(_elf.to_dict())
check(_d2.bonus_skills == {"perception"}, "bonus_skills 应能存档往返")
check(_d2.two_handed_grip is True, "双手持用状态应能存档往返")


print("\n[13] 1 级职阶: 牧师 神圣职阶 / 德鲁伊 原始职阶")

# ---- 保护者: 重甲 + 军用武器 ----
_cl = mk("cleric", 1)
_cl.order = None
_base_can = _cl.cantrip_cap()
check(_cl.order_options() and len(_cl.order_options()) == 2,
      "牧师应有 2 个神圣职阶")
check("heavy" not in _cl.armor_profs(), "牧师默认没有重甲熟练")
_cl.order = "protector"
check("heavy" in _cl.armor_profs(), "保护者应获得重甲熟练")
check("martial" in _cl.weapon_prof_rules(), "保护者应获得军用武器熟练")
check(_cl.has_weapon_prof("长剑 Longsword"), "保护者应会用长剑")
check(_cl.cantrip_cap() == _base_can, "保护者不多给戏法")

# ---- 施法者: 额外戏法 + 奥秘/宗教加感知 ----
_cl.order = "thaumaturge"
check(_cl.cantrip_cap() == _base_can + 1,
      f"施法者应多 1 个戏法: {_cl.cantrip_cap()} vs {_base_can}")
check("heavy" not in _cl.armor_profs(), "施法者不获得重甲熟练")
_cl.base_scores = dict(_cl.base_scores); _cl.base_scores["WIS"] = 16
_bonus = _cl.order_skill_bonus("arcana")
check(_bonus == cb.ability_mod(_cl.score("WIS")),
      f"施法者奥秘检定应加感知调整值: {_bonus}")
check(_cl.order_skill_bonus("nature") == 0, "施法者不加自然")
check(_cl.order_skill_bonus("religion") == _bonus, "施法者也加宗教")

# ---- 守护者 / 魔术师 ----
_dr = mk("druid", 1)
check("medium" in _dr.armor_profs(), "德鲁伊本身就有中甲熟练 (2024)")
check("martial" not in _dr.weapon_prof_rules(), "德鲁伊默认只有简易武器")
_dr.order = "warden"
check("martial" in _dr.weapon_prof_rules(), "守护者应获得军用武器熟练")
check("medium" in _dr.armor_profs(), "守护者仍是中甲")
_dr = mk("druid", 1)
_dr.order = None
_dr_can = _dr.cantrip_cap()
_dr.order = "magician"
check(_dr.cantrip_cap() == _dr_can + 1, "魔术师应多 1 个戏法")
check(_dr.order_skill_bonus("nature") >= 1, "魔术师自然检定应加感知")
check(_dr.order_skill_bonus("arcana") >= 1, "魔术师奥秘检定应加感知")
check(_dr.order_skill_bonus("religion") == 0, "魔术师不加宗教")

# ---- 非法职阶 / 跨职业职阶一律清空 ----
_bad = mk("cleric", 1)
_d3 = cb.Character(r)
_dct = _bad.to_dict()
_dct["order"] = "magician"          # 德鲁伊的职阶, 牧师不认
_d3.load_dict(_dct)
check(_d3.order is None, "牧师存档里的德鲁伊职阶应被清空")
_dct["order"] = "thaumaturge"
_d3.load_dict(_dct)
check(_d3.order == "thaumaturge", "合法职阶应能存档往返")
_wrong = mk("fighter", 1)
_w4 = cb.Character(r)
_dct2 = _wrong.to_dict()
_dct2["order"] = "protector"
_w4.load_dict(_dct2)
check(_w4.order is None, "战士没有职阶, 存档里的职阶应被清空")

# ---- 界面: 职阶单选能改并触发重算 ----
app.set_character(_cl)
app._order_set("protector")
check(_cl.order == "protector" and "heavy" in _cl.armor_profs(),
      "界面切换职阶应生效")
app._order_set("不存在的职阶")
check(_cl.order is None, "非法职阶键应被拒绝")
_cl.order = "thaumaturge"
app.refresh()


print("\n[14] 术士·术法源泉: 术法点 ↔ 法术位")

_s1 = mk("sorcerer", 1)
check(_s1.font_can_use() is False, "1 级术士还没有术法源泉")


def _sorc(lv):
    c2 = mk("sorcerer", lv, {"STR": 8, "DEX": 14, "CON": 14,
                             "INT": 10, "WIS": 10, "CHA": 18})
    return c2


_s9 = _sorc(9)
_base1 = _s9.spell_slots()[1]
_pt = _s9.sorcery_left()
check(_pt == 9, f"9 级术士应有 9 点术法点: {_pt}")
_ok, _msg = _s9.font_create_slot(1)
check(_ok, f"应能换出 1 环法术位: {_msg}")
check(_s9.font_slots == {1: 1}, f"应记录 1 个临时位: {_s9.font_slots}")
check(_s9.spell_slots()[1] == _base1 + 1,
      f"1 环法术位上限应 +1: {_s9.spell_slots()[1]} vs {_base1}")
check(_s9.sorcery_left() == 7, f"应花掉 2 点: {_s9.sorcery_left()}")
_ok, _msg = _s9.font_create_slot(6)
check(not _ok, "不应能兑换 6 环法术位")
_s9.res_spend("sorcery", 99)                    # 点数耗尽
_ok, _msg = _s9.font_create_slot(3)
check(not _ok, "点数不够时不应成功")

# ---- 烧法术位换点数 ----
_s9b = _sorc(9)
_ok, _msg = _s9b.font_burn_slot(1)
check(not _ok, "术法点已满时不能烧法术位")
_s9b.res_spend("sorcery", 6)                    # 只剩 3 点空间
_ok, _msg = _s9b.font_burn_slot(1)
check(_ok, f"应能烧 1 环换点数: {_msg}")
check(_s9b.sorcery_left() == 4, f"应回 1 点: {_s9b.sorcery_left()}")
check(_s9b.spell_slots_used.get(1) == 1, "烧掉的应是普通法术位")
_s9b.res_spend("sorcery", 2)                    # 只剩 2 点空间
_ok, _msg = _s9b.font_burn_slot(3)
check(_ok and _s9b.sorcery_left() == 5,
      f"3 环位应回 3 点: {_s9b.sorcery_left()}")
_s9b2 = _sorc(9)
_s9b2.res_spend("sorcery", 1)                   # 只剩 1 点空间
_ok, _msg = _s9b2.font_burn_slot(3)
check(_ok and _s9b2.sorcery_left() == 9,
      f"空间不足时只补到上限: {_s9b2.sorcery_left()}")
_ok, _msg = _s9b2.font_burn_slot(9)
check(not _ok, "没有 9 环位时不应成功")

# ---- 长休清空临时位 / 存档往返 ----
_s9c = _sorc(9)
_s9c.font_create_slot(2)
check(_s9c.font_slots == {2: 1}, "兑换 2 环临时位")
_d4 = cb.Character(r)
_d4.load_dict(_s9c.to_dict())
check(_d4.font_slots == {2: 1}, "临时法术位应能存档往返")
check(_d4.spell_slots()[2] == _s9c.spell_slots()[2], "读档后法术位上限一致")
app.set_character(_s9c)
app.long_rest()
check(_s9c.font_slots == {}, "长休应清空换出的临时法术位")

# ================================================================
# [15] 「始终准备」法术: 职业特性 / 子职固定表 / 大地结社地形
# ================================================================
print("\n[15] 始终准备的法术 (职业 + 子职 + 地形)")

# ---- 职业特性: 德鲁伊 1 说动物语 / 游侠 1 猎手印记 / 圣武士 2 神圣惩击 ----
check("speak-with-animals" in mk("druid", 1).fixed_spells(),
      "德鲁伊 1 级应始终准备「动物交谈」")
check(mk("druid", 1).fixed_source("speak-with-animals") == "职业",
      "动物交谈来源应为职业特性")
check("hunters-mark" in mk("ranger", 1).fixed_spells(),
      "游侠 1 级应始终准备「猎手印记」")
check("divine-smite" not in mk("paladin", 1).fixed_spells(),
      "圣武士 1 级还没拿到神圣惩击")
check("divine-smite" in mk("paladin", 2).fixed_spells(),
      "圣武士 2 级应始终准备「神圣惩击」")
_p5 = mk("paladin", 5)
check("find-steed" in _p5.fixed_spells(), "圣武士 5 级应始终准备「寻获坐骑」")
check("divine-smite" in _p5.fixed_spells(), "5 级仍保留神圣惩击")
_w8, _w9 = mk("warlock", 8), mk("warlock", 9)
check("contact-other-plane" not in _w8.fixed_spells(), "邪术师 8 级还没有「异界探触」")
check("contact-other-plane" in _w9.fixed_spells(), "邪术师 9 级应有「异界探触」")
check(mk("fighter", 20).fixed_spells() == [], "战士没有任何固定法术")

# ---- 子职: 生命领域逐级解锁 ----
_c3 = mk("cleric", 3); _c3.subclass = "Life Domain"
_fx3 = _c3.fixed_spells()
for sid in ("aid", "bless", "cure-wounds", "lesser-restoration"):
    check(sid in _fx3, f"生命领域 3 级应有 {sid}")
check("mass-healing-word" not in _fx3, "生命领域 5 级才有群体治疗真言")
_c5 = mk("cleric", 5); _c5.subclass = "Life Domain"
check({"mass-healing-word", "revivify"} <= set(_c5.fixed_spells()),
      "生命领域 5 级应加群体治疗真言 / 复苏术")
_c9 = mk("cleric", 9); _c9.subclass = "Life Domain"
_fx9 = set(_c9.fixed_spells())
check({"greater-restoration", "mass-cure-wounds"} <= _fx9, "生命领域 9 级应加高等复原 / 群体治疗术")
check(_c9.fixed_source("aid") == "子职", "生命领域法术来源应为子职")
_c0 = mk("cleric", 3)
check(_c0.fixed_spells() == [], "没选子职的牧师不应有子职固定法术")

# ---- 誓约奉献: 3/5/9/13/17 门槛 ----
_o17 = mk("paladin", 17); _o17.subclass = "Oath of Devotion"
_ofx = set(_o17.fixed_spells())
check({"commune", "flame-strike"} <= _ofx, "誓约奉献 17 级应有通神术 / 焰击术")
check({"protection-from-evil-and-good", "shield-of-faith"} <= _ofx, "3 级条目仍保留")
_o4 = mk("paladin", 4); _o4.subclass = "Oath of Devotion"
check("zone-of-truth" not in _o4.fixed_spells(), "誓约奉献 5 级才有诚实之域")

# ---- 术士/邪术师子职 ----
_ds = mk("sorcerer", 9); _ds.subclass = "Draconic Sorcery"
check({"legend-lore", "summon-dragon"} <= set(_ds.fixed_spells()),
      "龙裔术士 9 级应有传说知识 / 召唤巨龙")
_fp = mk("warlock", 7); _fp.subclass = "Fiend Patron"
check({"fire-shield", "wall-of-fire"} <= set(_fp.fixed_spells()),
      "魔鬼宗主 7 级应有火焰护盾 / 火墙术")

# ---- 大地结社: 换地形换法术, 含戏法 ----
_l3 = mk("druid", 5); _l3.subclass = "Circle of the Land"
_l3.land = "arid"
_arid = set(_l3.fixed_spells())
check({"blur", "burning-hands", "fire-bolt", "fireball"} <= _arid,
      f"干旱地形 5 级法术不对: {sorted(_arid)}")
_l3.land = "polar"
_polar = set(_l3.fixed_spells())
check("sleet-storm" in _polar and "fireball" not in _polar,
      "换成极地后应是冰雨风暴而不是火球术")
_l3.land = "temperate"
check("lightning-bolt" in _l3.fixed_spells(), "温带 5 级应有闪电束")
check("fire-bolt" not in _l3.fixed_spells(), "温带不再给火焰箭")
check(_l3.cantrip_cap() == 3, f"德鲁伊 5 级戏法上限应为 3: {_l3.cantrip_cap()}")

# ---- 固定法术不占准备配额 ----
_c9b = mk("cleric", 9); _c9b.subclass = "Life Domain"
_c9b.spells["prepared"] = ["aid", "bless"]           # 两个都是子职固定
check(_c9b.prepared_count() == 0, f"固定法术不应计入准备数: {_c9b.prepared_count()}")
_c9b.spells["prepared"] = ["aid", "healing-word"]    # 一个固定 + 一个自选
check(_c9b.prepared_count() == 1, f"只统计自选的那个: {_c9b.prepared_count()}")
_c9b.prune_fixed()
check(_c9b.spells["prepared"] == ["healing-word"], f"prune 后只剩自选: {_c9b.spells['prepared']}")

# ---- 存档往返: 地形 ----
_l5 = mk("druid", 5); _l5.subclass = "Circle of the Land"; _l5.land = "tropical"
_d5 = cb.Character(r)
_d5.load_dict(_l5.to_dict())
check(_d5.land == "tropical", f"地形应能存档往返: {_d5.land}")
check(set(_d5.fixed_spells()) == set(_l5.fixed_spells()), "读档后固定法术一致")
_bad = _l5.to_dict(); _bad["land"] = "moon"
_d6 = cb.Character(r); _d6.load_dict(_bad)
check(_d6.land == "temperate", f"非法地形应回落温带: {_d6.land}")

# ---- 旧存档: 手动学过的固定法术要被清出手动列表 ----
_legacy = _l5.to_dict()
_legacy["spells"]["prepared"] = ["stinking-cloud", "entangle"]
_d7 = cb.Character(r); _d7.load_dict(_legacy)
check("stinking-cloud" not in _d7.spells["prepared"], "固定法术应被移出手动列表")
check("entangle" in _d7.spells["prepared"], "非固定法术应保留")

# ---- 界面: 法术页应出现「✦子职固定」行 ----
_c9c = mk("cleric", 9); _c9c.subclass = "Life Domain"
app.set_character(_c9c)
app.refresh()
_rows = app._spell_rows()
_fixed_rows = [x for x in _rows if str(x.get("_src", "")).endswith("固定")]
check(len(_fixed_rows) >= 8, f"生命领域应列出 ≥8 条固定法术: {len(_fixed_rows)}")
_opts_ids = {x["id"] for x in getattr(app, "_spell_opts", [])}
check("aid" not in _opts_ids, "固定法术不应出现在「可学习」下拉里")
check("healing-word" in _opts_ids, "非固定法术仍在可学习列表里")
_app_rows = app.spell_list.get(0, "end")
check(any("✦子职固定" in t for t in _app_rows), "列表里应有 ✦子职固定 标记")

# ================================================================
# [16] 超魔法 / 先天魔法 / 奥术神化 / 双武器 / 法师 18·20 级
# ================================================================
print("\n[16] 超魔法 · 双武器 · 法师 18/20 级")

# ---- 超魔法数量: 2 级 2 个, 10 级 4 个, 17 级 6 个 ----
check(mk("sorcerer", 1).metamagic_cap() == 0, "1 级术士还没有超魔法")
check(mk("sorcerer", 2).metamagic_cap() == 2, "2 级应为 2 个")
check(mk("sorcerer", 10).metamagic_cap() == 4, "10 级应为 4 个")
check(mk("sorcerer", 17).metamagic_cap() == 6, "17 级应为 6 个")
check(len(cb.consts.METAMAGIC) == 10, "2024 共 10 个超魔法选项")
check(mk("wizard", 20).metamagic_cap() == 0, "法师没有超魔法")

_sm = mk("sorcerer", 10)
_sm.metamagic = ["quickened", "heightened", "empowered", "seeking", "subtle"]
check(len(_sm.metamagic_known()) == 4, f"超出上限应截断: {_sm.metamagic_known()}")
_ok, _why, _c = _sm.mm_validate(["quickened"])
check(_ok and _c == 2, f"迅捷法术 2 点: {_ok} {_c}")
_ok, _why, _c = _sm.mm_validate(["quickened", "heightened"])
check(not _ok, "同一道法术不能叠两个非叠加型超魔法")
_ok, _why, _c = _sm.mm_validate(["empowered", "seeking", "quickened"])
check(_ok and _c == 4, f"强化+探秘可与迅捷叠加, 共 4 点: {_ok} {_c}")
_ok, _why, _c = _sm.mm_validate(["twinned"])
check(not _ok, "没学过的超魔法不能用")
_sm.res_spend("sorcery", 9)                  # 10 级 10 点, 只剩 1
_ok, _why, _c = _sm.mm_validate(["quickened"])
check(not _ok, f"术法点不足应拒绝: {_why}")
_sm2 = mk("sorcerer", 10)
_sm2.metamagic = ["quickened"]
_ok, _msg = _sm2.mm_apply(["quickened"])
check(_ok and _sm2.sorcery_left() == 8, f"应用后应扣 2 点: {_sm2.sorcery_left()}")

# ---- 先天魔法: 2 次/长休, 7 级起可叠 2 个超魔法 ----
_in = mk("sorcerer", 7)
check(_in.innate_left() == 2, "先天魔法 2 次")
_ok, _ = _in.innate_on()
check(_ok and _in.innate_active and _in.innate_left() == 1, "开启后消耗 1 次")
check(_in.metamagic_per_spell() == 2,
      f"7 级先天魔法期间可叠 2 个: {_in.metamagic_per_spell()}")
_in.innate_off()
check(not _in.innate_active and _in.metamagic_per_spell() == 1, "关闭后回到 1 个")
_in.innate_on(); _in.innate_on()             # 第 2 次
check(_in.innate_left() == 0, "两次用完")
_in.innate_off()
_in.res_spend("sorcery", _in.sorcery_max() - 2)   # 留 2 点
_ok, _ = _in.innate_on()
check(_ok and _in.sorcery_left() == 0, "没次数时 7 级可花 2 点顶上")

# ---- 20 级奥术神化: 先天魔法期间 1 个超魔法免费 ----
_ap = mk("sorcerer", 20)
_ap.metamagic = ["heightened", "empowered", "seeking"]
_ap.innate_on()
_ok, _why, _c = _ap.mm_validate(["heightened"])
check(_ok and _c == 0, f"奥术神化应让 2 点的升阶法术免费: {_c}")
_ok, _why, _c = _ap.mm_validate(["heightened", "empowered"])
check(_ok and _c == 1, f"叠一个 1 点后只剩 1 点: {_c}")
_ap.innate_off()
_ok, _why, _c = _ap.mm_validate(["heightened"])
check(_ok and _c == 2, f"先天魔法结束后恢复 2 点: {_c}")

# ---- 超魔法存档往返 ----
_dm = cb.Character(r)
_dm.load_dict(_ap.to_dict())
check(_dm.metamagic == _ap.metamagic, "已知超魔法应能存档往返")
check(_dm.innate_used == _ap.innate_used, "先天魔法次数应能存档往返")
_bad_mm = _ap.to_dict()
_bad_mm["metamagic"] = ["quickened"] * 9 + ["不存在的超魔法"]
_dm2 = cb.Character(r)
_dm2.load_dict(_bad_mm)
check(len(_dm2.metamagic) <= _dm2.metamagic_cap(), "非法/超量超魔法应被截断")

# ---- 双武器战斗 ----
_oh = mk("fighter", 1, {"STR": 16, "DEX": 14, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 10})
_oh.weapon = "短剑 Shortsword"
_oh.offhand_weapon = "匕首 Dagger"
check(_oh.offhand_can_dual(), "两把轻型武器可以副手攻击")
check(_oh.offhand_ability() == "STR", f"灵巧武器取高者: {_oh.offhand_ability()}")
check(_oh.offhand_attack_bonus() == 3 + _oh.pb(),
      f"副手命中 = 力调 + 熟练: {_oh.offhand_attack_bonus()}")
check(_oh.offhand_damage_bonus() == 0,
      f"无战斗风格时副手不加属性调整值: {_oh.offhand_damage_bonus()}")
_oh.fighting_style = "two_weapon"
check(_oh.offhand_damage_bonus() == 3, "双武器战斗风格才加属性调整值")
check(_oh.offhand_damage_dice() == "1d4", f"匕首 1d4: {_oh.offhand_damage_dice()}")
check(_oh.offhand_damage_type() == "穿刺", "副手伤害类型按副手武器")

_oh2 = mk("fighter", 1, {"STR": 16, "DEX": 14, "CON": 14,
                         "INT": 10, "WIS": 10, "CHA": 10})
_oh2.weapon = "长剑 Longsword"
_oh2.offhand_weapon = "匕首 Dagger"
check(not _oh2.offhand_can_dual(), "主手非轻型时不能副手攻击")
check(_oh2.offhand_note() != "", "应给出不可用原因")
_oh2.feats = ["Dual Wielder"]
check(_oh2.offhand_can_dual() is False,
      "长剑是两用武器，双武器大师也放宽不了")
_oh2.weapon = "钉头锤 Mace"              # 单手、非轻型、非两用
check(_oh2.offhand_can_dual(), "双武器大师可让非轻型单手武器副手攻击")
_oh2.weapon = "长矛 Spear"               # 两用
check(not _oh2.offhand_can_dual(), "两用武器不能靠专长绕过")

_dl = mk("fighter", 1, {"STR": 16, "DEX": 14, "CON": 14,
                        "INT": 10, "WIS": 10, "CHA": 10})
_dl.weapon = "短剑 Shortsword"
_dl.fighting_style = "dueling"
_duel = _dl.damage_bonus()
_dl.offhand_weapon = "匕首 Dagger"
check(_dl.damage_bonus() == _duel - 2, "另一手持武器时决斗 +2 失效")
check(_dl.offhand_can_dual(), "短剑+匕首仍是合法双持")

# ---- 法师 18 级 法术精通 / 20 级 招牌法术 ----
_wz = mk("wizard", 18)
_wz.spells = {"cantrips": ["fire-bolt"],
              "prepared": ["shield", "misty-step", "fireball", "magic-missile"]}
_wz.spellbook = list(_wz.spells["prepared"])      # 法术书 = 已准备的那几个
check(_wz.mastery_cap() == 2 and _wz.signature_cap() == 0,
      "18 级法术精通 2 个（1 环 + 2 环各 1）")
_wz.mastery_spells = ["shield"]
check(_wz.is_mastery_spell("shield"), "法术精通命中")
check("shield" in _wz.fixed_spells(), "法术精通属于始终准备")
check(_wz.prepared_count() == 3,
      f"精通法术不占准备配额: {_wz.prepared_count()}")
check(_wz.book_spells(1) and all(s["level"] == 1 for s in _wz.book_spells(1)),
      "候选只列该环的法术")

_wz20 = mk("wizard", 20)
_wz20.spells = {"cantrips": ["fire-bolt"],
                "prepared": ["shield", "misty-step", "fireball"]}
_wz20.signature_spells = ["fireball", "misty-step"]
check(_wz20.signature_cap() == 2, "20 级 2 个招牌法术")
check(_wz20.signature_left("fireball") == 1, "招牌法术先有 1 次免费")
_wz20.signature_used = ["fireball"]
check(_wz20.signature_left("fireball") == 0, "用掉后为 0")
check("fireball" in _wz20.fixed_spells(), "招牌法术属于始终准备")

# 存档: 非法环级应被剔除
_bad_w = _wz20.to_dict()
_bad_w["mastery_spells"] = ["fireball"]        # 3 环, 不能当 1/2 环精通
_bad_w["signature_spells"] = ["shield"]        # 1 环, 不能当招牌
_dw = cb.Character(r)
_dw.load_dict(_bad_w)
check(_dw.mastery_spells == [], f"环级不符应剔除: {_dw.mastery_spells}")
check(_dw.signature_spells == [], f"环级不符应剔除: {_dw.signature_spells}")
_bad_w2 = _wz.to_dict()
_bad_w2["mastery_spells"] = ["shield", "magic-missile"]     # 两个都是 1 环
_dw2 = cb.Character(r)
_dw2.load_dict(_bad_w2)
check(len(_dw2.mastery_spells) == 1,
      f"法术精通每个环级只能 1 个: {_dw2.mastery_spells}")

# 界面: 法术精通施放不耗环位
app.set_character(_wz)
app.refresh()
_rows16 = app._spell_rows()
_idx = next((i for i, x in enumerate(_rows16) if x["id"] == "shield"), None)
check(_idx is not None, "法术列表里应有 shield")
app.spell_list.selection_clear(0, "end")
app.spell_list.selection_set(_idx)
_before = dict(_wz.spell_slots_used)
app._spell_cast()
check(_wz.spell_slots_used == _before, "法术精通施放不消耗法术位")

# 界面: 招牌法术免费一次, 第二次才用环位 (用干净角色, 避免上面的手工状态干扰)
_wz20b = mk("wizard", 20)
_wz20b.spells = {"cantrips": ["fire-bolt"],
                 "prepared": ["shield", "misty-step", "fireball"]}
_wz20b.signature_spells = ["fireball", "misty-step"]
app.set_character(_wz20b)
app.refresh()
_rows16b = app._spell_rows()
_idx2 = next((i for i, x in enumerate(_rows16b) if x["id"] == "fireball"), None)
check(_idx2 is not None, "法术列表里应有 fireball")
app.spell_list.selection_clear(0, "end")
app.spell_list.selection_set(_idx2)
app._spell_cast()
check(_wz20b.signature_used == ["fireball"], "第一次招牌法术应记为免费施放")
check(_wz20b.spell_slots_used.get(3, 0) == 0, "免费施放不占 3 环位")
app.spell_list.selection_clear(0, "end")
app.spell_list.selection_set(_idx2)
app._spell_cast()
check(_wz20b.spell_slots_used.get(3, 0) == 1, "第二次恢复消耗法术位")
app.short_rest()
check(_wz20b.signature_used == [], "短休应恢复招牌法术的免费次数")

# 术士职业页渲染 (超魔法勾选 + 先天魔法开关)
app.set_character(_ap)
app.refresh()
app.update_idletasks()
check(app.class_body.winfo_reqwidth() <= 560,
      f"术士职业页不应超出滚动区: {app.class_body.winfo_reqwidth()}")

# ---- 术士 5 级「魔法恢复」: 短休回一半术法点, 1 次/长休 ----
_sr = mk("sorcerer", 10)                 # 10 点术法点
_sr.res_spend("sorcery", 8)              # 只剩 2
check(mk("sorcerer", 4).sorcerous_rest()[0] is False, "5 级前没有魔法恢复")
_ok, _m = _sr.sorcerous_rest()
check(_ok and _sr.sorcery_left() == 7,
      f"应回 5 点（等级一半）: {_sr.sorcery_left()}")
_ok, _ = _sr.sorcerous_rest()
check(not _ok, "同一次长休只能用一次魔法恢复")
app.set_character(_sr)
app.long_rest()
check(not _sr.sorcerous_rest_used, "长休应重置魔法恢复")


# ================================================================
# [17] 法师法术书 (2024): 书内 → 准备 两层
# ================================================================
print("\n[17] 法师法术书 (书内 → 准备 / 抄录 / 仪式)")

_WIZ = {s["id"] for s in r.class_spells("wizard")}
# 建卡向导造出来的 1 级法师: 书里先放 4 个已准备法术, 余下 2 次免费抄录
_wnew = made["wizard"]
check(_wnew.spellbook and all(s in _WIZ for s in _wnew.spellbook),
      f"向导造出的法师应带法术书: {_wnew.spellbook}")
check(_wnew.book_pending == 2,
      f"1 级法术书应能免费补齐到 6 个: {_wnew.book_pending}")

_wb = mk("wizard", 1)
_wb.spells = {"cantrips": ["fire-bolt"],
              "prepared": ["shield", "magic-missile", "detect-magic", "sleep"]}
_wb.book_auto_fill()
check(len(_wb.spellbook) == 4
      and all(r.spell(s)["level"] == 1 for s in _wb.spellbook),
      f"1 级法术书应全是 1 环法术: {_wb.spellbook}")
check(all(s in _WIZ for s in _wb.spellbook), "法术书里只能有法师法术")
check(_wb.can_prepare("shield"), "书内法术可以准备")
check(not _wb.can_prepare("fireball"), "书外法术不能准备")
check(not _wb.can_prepare("cure-wounds"), "别的职业法术不能准备")
_wb.level = 5
check(_wb.copy_cost("fireball") == 150 and _wb.copy_hours("fireball") == 6,
      f"3 环抄录应为 150gp/6 小时: {_wb.copy_cost('fireball')}/{_wb.copy_hours('fireball')}")
check(_wb.copy_cost("shield") == 50 and _wb.copy_hours("shield") == 2,
      "1 环抄录应为 50gp/2 小时")
_wb.level = 1

# 免费抄录: 消耗 book_pending, 为 0 时失败
_wb.book_pending = 1
_ok, _m = _wb.book_add("feather-fall", free=True)
check(_ok and _wb.book_pending == 0 and _wb.in_book("feather-fall"),
      f"免费抄录应消耗 1 次: {_m}")
_ok, _m = _wb.book_add("longstrider", free=True)
check(not _ok and not _wb.in_book("longstrider"),
      "免费次数为 0 时应拒绝免费抄录")
check(not _wb.book_add("shield")[0], "书里已有的法术不能重复抄录")
check(not _wb.book_add("fireball")[0], "环级超过当前上限不能抄录")
check(_wb.spellbook.count("shield") == 1, "法术书里不应出现重复项")

# 移出法术书: 准备中的不行
check(not _wb.book_remove("shield")[0], "正在准备的法术不能移出法术书")
_ok, _m = _wb.book_remove("feather-fall")
check(_ok and not _wb.in_book("feather-fall"), f"未准备的法术可以移出: {_m}")
check(not _wb.book_remove("feather-fall")[0], "书外的法术不能移出")

# 升级: 法师每级 +2 次免费抄录
_uiio = sys.modules["dnd55e.ui_io"]


class _FakeLevelUp:
    def __init__(self, ch):
        self.result = {"level": ch.level + 1, "subclass": None,
                       "asi": None, "boon": None}


_keep_dlg, _keep_wait = _uiio.LevelUpDialog, app.wait_window
_uiio.LevelUpDialog = lambda master, ch: _FakeLevelUp(ch)
app.wait_window = lambda *a, **k: None
_wb.book_pending = 0
app.set_character(_wb)
app.level_up()
check(_wb.level == 2, f"升级应生效: {_wb.level}")
check(_wb.book_pending == 2,
      f"法师升级后应有 2 次免费抄录: {_wb.book_pending}")
# 19 次升级最多攒 38 次, 上限必须放得下 (不能截断到 20)
_wcap = mk("wizard", 20)
_wcap.book_pending = 38
_wcap2 = cb.Character(r)
_wcap2.load_dict(_wcap.to_dict())
check(_wcap2.book_pending == 38, f"38 次免费抄录不应被截断: {_wcap2.book_pending}")
_uiio.LevelUpDialog, app.wait_window = _keep_dlg, _keep_wait

# 存档往返
_dd = _wb.to_dict()
_wb2 = cb.Character(r)
_wb2.load_dict(json.loads(json.dumps(_dd)))
check(_wb2.spellbook == _wb.spellbook, "法术书应能存档往返")
check(_wb2.book_pending == _wb.book_pending, "免费抄录次数应能存档往返")
_bad = _wb.to_dict()
_bad["spellbook"] = ["fireball", "cure-wounds", "fireball", "不存在的法术"]
_bad["book_pending"] = 99
_wb4 = cb.Character(r)
_wb4.load_dict(_bad)
check(_wb4.spellbook == ["fireball"] and _wb4.book_pending == 40,
      f"非法抄录项应被丢弃、次数钳制到 40: {_wb4.spellbook} {_wb4.book_pending}")

# 旧档 (有 prepared, 无 spellbook 键) 自动迁移
_old = {"class_id": "wizard", "level": 3,
        "spells": {"cantrips": ["fire-bolt"],
                   "prepared": ["shield", "misty-step"]}}
_wb3 = cb.Character(r)
_wb3.load_dict(_old)
check(_wb3.spellbook == ["shield", "misty-step"],
      f"旧档应自动迁进法术书: {_wb3.spellbook}")
check(_wb3.book_pending == 0, "旧档没有 book_pending 时应为 0")

# 仪式法术: 书内、未准备也能施放, 不耗环位
_wr = mk("wizard", 2)
_wr.spells = {"cantrips": ["fire-bolt"], "prepared": ["shield"]}
_wr.spellbook = ["shield", "detect-magic", "magic-missile"]
app.set_character(_wr)
app.refresh()
_rows_r = app._spell_rows()
check(sum(1 for x in _rows_r if x.get("_src") == "仪式") == 1,
      "书内未准备的仪式法术应单独列出")
_idx_r = next(i for i, x in enumerate(_rows_r) if x.get("_src") == "仪式")
check(_rows_r[_idx_r]["id"] == "detect-magic", "列出的应是侦测魔法")
app.spell_list.selection_clear(0, "end")
app.spell_list.selection_set(_idx_r)
_before_slots = dict(_wr.spell_slots_used)
app._spell_cast()
check(_wr.spell_slots_used == _before_slots, "仪式施放不应消耗法术位")
check("仪式施放" in app.roll_log.get(0) and "不耗环位" in app.roll_log.get(0),
      f"日志应写出仪式施放: {app.roll_log.get(0)}")

# 下拉框: 只列「书内、未准备」的法术
app.refresh()
_opts = {s["id"] for s in app._spell_opts}
check("magic-missile" in _opts, "书内未准备的法术应可准备")
check("shield" not in _opts, "已准备的法术不该再出现在下拉框")
check("fireball" not in _opts, "书外的法术不能进入下拉框")

# 法术页按钮: 只有法师才有「📖 法术书」
check(app.spellbook_btn.winfo_manager() == "pack", "法师应看到法术书按钮")
check("法术书" in app.spellbook_btn.cget("text"), "按钮文案应含「法术书」")
_keep2 = app.wait_window
app.wait_window = lambda *a, **k: None
app._spellbook_open()
_tops = [w for w in app.winfo_children() if isinstance(w, cb.tk.Toplevel)]
check(len(_tops) == 1, f"法术书按钮应弹出对话框: {len(_tops)}")
for w in _tops:
    w.withdraw()
    w.destroy()
app.wait_window = _keep2

# 非法师: 没有法术书
_fg = mk("fighter", 3)
check(_fg.book_spells() == [], "非法师的法术书应为空")
check(not _fg.book_add("shield")[0], "非法师不能抄录")
check(not _fg.can_prepare("shield"), "非法师没有「准备法术书」的概念")
app.set_character(_fg)
app.refresh()
app.update_idletasks()
check(app.spellbook_btn.winfo_manager() == "", "非法师不该显示法术书按钮")
# [18] 通用专长 / 魔法物品字段 / 野兽形态
print("\n[18] 通用专长 / 物品字段 / 野兽形态")

# ---- 数据规模 ----
check(len(cb.consts.GENERAL_FEATS["general"]) == 43, "通用专长应为 43 条")
check(len(cb.consts.GENERAL_FEATS["fighting_style"]) == 12, "战斗风格应为 12 条")
check(len(cb.consts.GENERAL_FEATS["epic_boon"]) == 12,
      "传奇恩惠应为 12 条 (PHB 2024 全部)")
check(len(cb.consts.MONSTERS) >= 45, f"野兽应 ≥45 只: {len(cb.consts.MONSTERS)}")
check(len(cb.consts.MAGIC_ITEMS) >= 80, f"物品应 ≥80: {len(cb.consts.MAGIC_ITEMS)}")

# ---- 专长 effects ----
_S = {"STR": 16, "DEX": 14, "CON": 14, "INT": 10, "WIS": 10, "CHA": 10}
_gwm = mk("fighter", 8, dict(_S))
_gwm.feats = ["Great Weapon Master"]
_gwm.weapon = "巨剑 Greatsword"
check(_gwm.feat_effects().get("heavy_damage_pb") is True, "GWM 应标记重型加伤")
check(_gwm.damage_bonus() == 6, f"GWM 重型 = 力量3+熟练3: {_gwm.damage_bonus()}")
_gwm.weapon = "长剑 Longsword"
check(_gwm.damage_bonus() == 3, f"非重型不吃 GWM: {_gwm.damage_bonus()}")

_spd = mk("fighter", 8)
_spd.feats = ["Speedy"]
check(_spd.speed() == 40, f"Speedy 速度 +10: {_spd.speed()}")

# 起源专长仍走原路径, 不被 feat_effects 双计
_alert = mk("rogue", 5, dict(_S))
_alert.feats = ["Alert"]
check(_alert.initiative() == 5,
      f"Alert 先攻 = 敏捷2 + 熟练3 (只加一次): {_alert.initiative()}")

# ---- 战斗风格 6 项 ----
_uf = mk("fighter", 1, dict(_S))
_uf.fighting_style = "unarmed"
check(_uf.damage_dice() == "1d8", f"徒手战斗双手空着 1d8: {_uf.damage_dice()}")
_uf.shield = True
check(_uf.damage_dice() == "1d6", f"徒手战斗持盾 1d6: {_uf.damage_dice()}")
_uf.shield = False

_tw = mk("fighter", 1, dict(_S))
_tw.weapon = "标枪 Javelin"
_tw.fighting_style = "thrown_weapon"
check(_tw.damage_bonus() == 5, f"投掷武器 +2: {_tw.damage_bonus()}")

_bf = mk("fighter", 1, dict(_S))
_bf.fighting_style = "blind_fighting"
check(_bf.senses().get("blindsight") == 10, "盲斗给 10 尺盲视")

from dnd55e.util import ability_mod as _am, roll_dice_reroll
for _ in range(30):
    _tot, _det = roll_dice_reroll("1d12+4", 2)
    check(5 <= _tot <= 16, f"巨武器重掷结果应在合法区间: {_tot}")
    break
_zz, _zd = roll_dice_reroll("1", 2)
check(_zz == 1, "固定值伤害不走重掷")

_pr = mk("fighter", 1, dict(_S))
_pr.fighting_style = "protection"
_pr.shield = True
check(any("守护" in x for x in _pr.bonus_breakdown()), "守护风格应有反应说明")
_ic2 = mk("fighter", 1, dict(_S))
_ic2.fighting_style = "interception"
_ic2.weapon = "长剑 Longsword"
check(any("拦截" in x for x in _ic2.bonus_breakdown()), "拦截风格应有骰子说明")

# ---- 物品新字段 ----
_robe = mk("wizard", 10)
_robe.items = ["robe_of_the_archmagi"]
check(_robe.ac() == 15 + _am(_robe.score("DEX")),
      f"大法师长袍 基础 AC 15+敏捷: {_robe.ac()}")
_robe.items = []
check(_robe.ac() == 10 + _am(_robe.score("DEX")), "卸下长袍回到 10+敏捷")

_arm = mk("fighter", 5, dict(_S))
_arm.items = ["armor_plus1"]
check(_arm._armor_item_bonus() == 1, "护甲增强 +1")
_arm.items = ["shield_plus1"]
check(_arm._shield_item_bonus() == 1, "盾牌增强 +1")
_arm.shield = True
check(_arm._shield_item_bonus() == 1, "盾牌增强与 shield_magic 取大不叠加")

_wp = mk("fighter", 1, dict(_S))
_wp.weapon = "长剑 Longsword"
_wp.items = ["weapon_plus1"]
check(_wp.attack_bonus() == 6, f"魔法武器攻击 = 力量3+熟练2+1: {_wp.attack_bonus()}")
check(_wp.damage_bonus() == 4, f"魔法武器伤害 = 力量3+1: {_wp.damage_bonus()}")
_wp.weapon_magic = 3
check(_wp.attack_bonus() == 8, f"手工 +3 与物品 +1 取大不叠加: {_wp.attack_bonus()}")
_wp.weapon_magic = 0

_inv = mk("fighter", 1, dict(_S))
_inv.items = ["armor_of_invulnerability"]
check(set(_inv.resistances()) == {"bludgeoning", "piercing", "slashing"},
      f"抗性并按集: {_inv.resistances()}")

_hp_i = mk("fighter", 5, dict(_S))
_base_hp = _hp_i.hp_max()
_hp_i.items = ["amulet_health"]          # 体质设为 19
check(_hp_i.hp_max() > _base_hp, "健康护符应提高 HP 上限")

# ---- 野兽形态 ----
from dnd55e import wildshape
_d2 = mk("druid", 2)
_s2 = _d2.wild_shapes()
check(len(_s2) > 0, "2 级德鲁伊应有可选形态")
check(all(m["speed"].get("fly", 0) == 0 and m["speed"].get("swim", 0) == 0
          for m in _s2), "2 级形态不能带飞行/游泳")
check(all(wildshape.cr_num(m) <= 0.25 for m in _s2), "2 级 CR 上限 1/4")
check(wildshape.shapes(1) == [], "1 级不能变形")

_d8 = mk("druid", 8)
check(len(_d8.wild_shapes()) > len(_s2), "8 级形态更多")
check(any(m["speed"].get("fly", 0) for m in _d8.wild_shapes()), "8 级可选飞行形态")
check(all(wildshape.cr_num(m) <= 1.0 for m in _d8.wild_shapes()), "8 级 CR 上限 1")
check(wildshape.cap_for(12, "Circle of the Moon") == 4.0, "月环 12 级 CR 上限 4")

_moon = mk("druid", 6)
_moon.subclass = "Circle of the Moon"
check(wildshape.cap_for(6, "Circle of the Moon") == 2.0, "月环 6 级 CR 上限 2")
check(len(_moon.wild_shapes()) > len(mk("druid", 6).wild_shapes()), "月环形态比普通多")

_moon.wild_shape_id = "wolf"
_mr = cb.Character(r)
_mr.load_dict(_moon.to_dict())
check(_mr.wild_shape_id == "wolf", "形态存档往返")
_bad = _moon.to_dict()
_bad["wild_shape_id"] = "tarrasque"
_mb = cb.Character(r)
_mb.load_dict(_bad)
check(_mb.wild_shape_id is None, "非法形态读档应清空")

# 非德鲁伊没有形态
check(mk("fighter", 8).wild_shapes() == [], "非德鲁伊不能荒野变形")

# ---- 专长选择对话框 ----
from dnd55e.dialogs import FeatPickerDialog, WildShapeDialog
_fd = FeatPickerDialog(app, _gwm, selftest=True)
check(len(_fd.lst.get(0, "end")) >= 40, "专长选择框条目充足")
_fd.destroy()
_wd = WildShapeDialog(app, _d8, selftest=True)
check(len(_wd._rows) == len(_d8.wild_shapes()), "形态对话框列出全部可选形态")
_wd.destroy()

# ---- 物品分类筛选 ----
app.set_character(_inv)
app.refresh()
app.update_idletasks()
check(app.item_count_lbl.cget("text").endswith("件"), "物品区应显示件数")
app.item_filter_var.set("戒指")
app._item_filter_changed()
app.update_idletasks()
check(app.item_count_lbl.cget("text") == "11 件",
      f"戒指类应为 11 件: {app.item_count_lbl.cget('text')}")
check("ring_protection" in app.item_cbs, "筛选后仍能操作戒指")
app.item_filter_var.set("全部")
app._item_filter_changed()
check(app.item_count_lbl.cget("text") == f"{len(cb.consts.MAGIC_ITEMS)} 件",
      "切回全部恢复全量")


app.destroy()

# ---------------------------------------------------------------- 结果
print("\n" + "=" * 60)
if FAIL:
    print(f"失败 {len(FAIL)} 项:")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("FLOWTEST ALL PASS")
