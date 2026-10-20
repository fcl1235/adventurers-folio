# -*- coding: utf-8 -*-
"""无 GUI 自检: 规则数值 + 建卡向导 + 升级 + 存档往返。"""
import json
import os
import random
import tempfile

import tkinter as tk
from tkinter import messagebox

from . import consts
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                     subclass_cn, tool_cn)
from .app import App
from .character import Character
from .dialogs import LevelUpDialog
from .rules import Rules
from .wizard import Wizard

# 拆分后需要的内部依赖
from .consts import ABILITIES, ABILITY_CN
from .util import ability_mod, proficiency_bonus


def run_selftest():
    """无 GUI 冒烟测试: 规则引擎 + 建卡向导端到端 + 升级流程 + 窗体构建"""
    # 弹窗打桩: 自检中不允许出现阻塞式系统对话框
    messagebox.showwarning = lambda *a, **k: None
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: None
    messagebox.askyesno = lambda *a, **k: True
    r = Rules()
    assert proficiency_bonus(1) == 2 and proficiency_bonus(5) == 3 \
        and proficiency_bonus(17) == 6 and proficiency_bonus(20) == 6
    assert ability_mod(8) == -1 and ability_mod(10) == 0 and ability_mod(20) == 5

    c = Character(r)
    c.name = "测试"
    c.class_id, c.background_id, c.species_id = "fighter", "soldier", "dwarf"
    c.base_scores = {"STR": 15, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10,
                     "CHA": 8}
    c.bg_bonus = {"mode": "2+1", "plus2": "STR", "plus1": "CON"}
    c.skill_prof = {"athletics", "perception"}
    assert c.score("STR") == 17 and c.score("CON") == 14
    # 战士1级: 10 + 2(Con) + 矮人1 = 13
    assert c.hp_max() == 13, c.hp_max()
    c.level = 3
    # 3级: 10+2 (1级) + 2*(6+2) (2-3级固定值) + 矮人韧性3 = 31
    assert c.hp_max() == 31, c.hp_max()
    c.level = 1

    m = Character(r)
    m.class_id, m.background_id, m.species_id = "wizard", "sage", "elf"
    m.base_scores = {"STR": 8, "DEX": 14, "CON": 13, "INT": 15, "WIS": 12,
                     "CHA": 10}
    m.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
    assert m.spell_slots() == {1: 2}
    m.level = 5
    assert m.spell_slots() == {1: 4, 2: 3, 3: 2}, m.spell_slots()
    assert m.spell_dc() == 8 + 3 + 3

    w = Character(r)
    w.class_id, w.background_id, w.species_id = "warlock", "charlatan", "tiefling"
    w.base_scores = {"STR": 8, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12,
                     "CHA": 15}
    w.bg_bonus = {"mode": "2+1", "plus2": "CHA", "plus1": "DEX"}
    w.level = 5
    assert w.spell_slots() == {3: 2}, w.spell_slots()
    w.level = 13
    # 11级6环秘契, 13级7环秘契
    assert w.spell_slots() == {5: 3, 6: 1, 7: 1}, w.spell_slots()

    p = Character(r)
    p.class_id = "paladin"
    p.level = 5
    assert p.spell_slots() == {1: 4, 2: 2}, p.spell_slots()

    # 序列化往返
    d = c.to_dict()
    c2 = Character(r)
    c2.load_dict(d)
    assert c2.hp_max() == c.hp_max() and c2.score("STR") == 17

    # ---- GUI 构建 ----
    app = App(selftest=True)
    app.set_character(c)
    app.update()
    app.update_idletasks()

    # ---- 端到端: 建卡向导六步走完 ----
    got = {}
    wiz = Wizard(app, r, lambda ch: got.setdefault("c", ch))
    wiz.withdraw()
    # ① 职业
    wiz.e_name.delete(0, "end")
    wiz.e_name.insert(0, "E2E·矮人战士")
    fname = next(x["name"] for x in r.d["classes"] if x["id"] == "fighter")
    wiz.cb_class.set(fname)
    wiz._show_class()
    assert wiz.data["class_id"] == "fighter"
    wiz.next()
    assert wiz.step == 1, "向导①→② 失败"
    # ② 背景 (+2/+1 分配)
    bname = next(x["name"] for x in r.d["backgrounds"] if x["id"] == "soldier")
    wiz.cb_bg.set(bname)
    wiz._render_bg_ui()
    cand_names = [f"{ABILITY_CN[a]}({a})" for a in wiz._bg_abs]
    wiz.bg_p2.set(cand_names[0])
    wiz.bg_p1.set(cand_names[1])
    wiz.next()
    assert wiz.step == 2, "向导②→③ 失败"
    # ③ 种族
    sname = next(x["name"] for x in r.d["species"] if x["id"] == "dwarf")
    wiz.cb_sp.set(sname)
    wiz._show_species()
    wiz.next()
    assert wiz.step == 3, "向导③→④ 失败"
    # ④ 属性 (标准数组)
    wiz.ab_method.set("standard")
    wiz._render_ab_ui()
    for ab, val in zip(ABILITIES, consts.STANDARD_ARRAY):
        wiz.ab_picks[ab].set(str(val))
    wiz.next()
    assert wiz.step == 4, "向导④→⑤ 失败"
    # ⑤ 技能
    for sid in list(wiz.skill_vars)[:wiz._skill_need]:
        wiz.skill_vars[sid].set(True)
    wiz.next()
    assert wiz.step == 5, "向导⑤→⑥ 失败"
    # ⑥ 武器专精
    for wname in list(wiz.mastery_vars)[:wiz._mastery_need]:
        wiz.mastery_vars[wname].set(True)
    wiz.next()
    assert wiz.step == 7, "向导⑥→摘要 失败"
    # ⑦ 摘要 → 完成
    wiz.next()
    ec = got.get("c")
    assert ec is not None, "向导完成未回调"
    assert ec.class_id == "fighter" and ec.species_id == "dwarf"
    assert ec.hp_current == ec.hp_max()
    assert len(ec.weapon_mastery) == 3 and len(ec.skill_prof) >= 2
    app.set_character(ec)
    app.update()

    # ---- 端到端: 升级到 3 级 (选子职) ----
    ec.level = 2
    dlg = LevelUpDialog(app, ec)
    dlg.withdraw()
    dlg.subclass_cb.current(0)
    dlg._ok()
    assert dlg.result and dlg.result["subclass"], "3级子职未记录"
    ec.level = dlg.result["level"]
    ec.subclass = dlg.result["subclass"]
    app.refresh()
    app.update()

    # ---- 端到端: 4 级 ASI (+2/+1) ----
    before_str = ec.score("STR")
    dlg2 = LevelUpDialog(app, ec)
    dlg2.withdraw()
    dlg2.asi_p2.set(f"{ABILITY_CN['STR']}(STR)")
    dlg2.asi_p1.set(f"{ABILITY_CN['CON']}(CON)")
    dlg2._ok()
    rec = dlg2.result
    assert rec and rec["asi"] == {"type": "asi", "plus2": "STR",
                                  "plus1": "CON"}, rec
    ec.level = rec["level"]
    ec.asi_history.append(rec["asi"])
    assert ec.score("STR") == min(20, before_str + 2)

    # ---- 存档钳制: 脏数据不崩 ----
    dirty = {
        "name": "脏数据", "level": 99, "xp": -50,
        "class_id": "不存在的职业", "subclass": "NotASub",
        "background_id": "??", "species_id": "x",
        "base_scores": {"STR": 99, "DEX": "abc", "CON": -5},
        "skill_prof": ["athletics", "假的技能", None],
        "expertise": ["假的技能", "athletics"],
        "weapon_mastery": ["长剑 Longsword", "歼星舰"],
        "armor_index": 999, "hp_current": 9999, "hp_temp": -3,
        "exhaustion": 42, "conditions": ["恐慌", "石化(假)"],
        "spell_slots_used": {"1": 99, "abc": 2},
    }
    dc = Character(ec.r)
    dc.load_dict(dirty)
    assert dc.level == 20 and dc.xp == 0
    assert dc.class_id == "barbarian", dc.class_id     # 回退到第一个职业
    assert dc.subclass is None
    assert dc.base_scores["STR"] == 20 and dc.base_scores["DEX"] == 10
    assert dc.base_scores["CON"] == 1
    assert dc.skill_prof == {"athletics"}
    assert dc.expertise == set(), "野蛮人没有专精特性, 脏数据应被清空"
    assert dc.weapon_mastery == ["长剑 Longsword"]
    assert dc.armor_index == len(consts.ARMORS) - 1
    assert 0 <= dc.hp_current <= dc.hp_max() and dc.hp_temp == 0
    assert dc.exhaustion == 6 and dc.conditions == {"恐慌"}
    assert all(k in dc.spell_slots() for k in dc.spell_slots_used)

    # ---- 人类「全能」必填校验 ----
    got2 = {}
    wiz2 = Wizard(app, ec.r, lambda c: got2.setdefault("c", c))
    wiz2.withdraw()
    wiz2.cb_class.set("法师 Wizard")
    wiz2._show_class()
    wiz2.next()
    wiz2.cb_bg.set("贤者 Sage")
    wiz2._render_bg_ui()
    nms = [f"{ABILITY_CN[a]}({a})" for a in wiz2._bg_abs]
    wiz2.bg_p2.set(nms[0])
    wiz2.bg_p1.set(nms[1])
    wiz2.next()
    wiz2.cb_sp.set("人类 Human")
    wiz2._show_species()
    step_before = wiz2.step
    wiz2.next()                      # 未选全能专长 → 应被拦下
    assert wiz2.step == step_before, "人类未选专长不应放行"
    wiz2.cb_hfeat.set("Alert")
    wiz2._show_hfeat_desc()
    wiz2.next()
    assert wiz2.step == step_before + 1, "选好专长后应放行"

    app.refresh()
    app.update()
    app.update_idletasks()
    app.destroy()
    print("SELFTEST OK")
