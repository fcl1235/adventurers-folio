"""P3/P4 验收冒烟: 4 个施法职业的数值 + 3 个角色的界面渲染。

P3 验收要求「术士/法师/邪术师/游侠 4 个角色各冒烟」;
P4 验收要求「开 3 个角色看六个页」。本脚本把这两条自动化。

用法: python backup/_p4_smoke.py
"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dnd55e_character_builder as cb   # noqa: E402

CASTERS = [
    # (职业, 子职, 等级, 期望有的东西)
    ("sorcerer", "Draconic Sorcery", 6, "术法源泉 / 超魔法"),
    ("wizard", "Evoker", 5, "法术书 / 法术精通"),
    ("warlock", "Fiend Patron", 11, "秘契位 / 玄奥秘法"),
    ("ranger", "Hunter", 9, "半施法者法术位"),
]


def make(r, cid, sub, lv):
    c = cb.Character(r)
    c.class_id = cid
    c.background_id = "sage"
    c.species_id = "human"
    c.subclass = sub
    c.level = lv
    c.base_scores = {"STR": 12, "DEX": 15, "CON": 14,
                     "INT": 13, "WIS": 10, "CHA": 15}
    c.bg_bonus = {"mode": "2+1", "plus2": "DEX", "plus1": "CON"}
    c.skill_prof = {"arcana", "insight"}
    c.feats = []
    c.hp_current = c.hp_max()
    return c


def caster_smoke(r):
    print("== P3 施法职业冒烟 ==")
    bad = 0
    for cid, sub, lv, want in CASTERS:
        c = make(r, cid, sub, lv)
        casting = c.casting()
        slots = c.spell_slots()
        n_slots = sum(slots.values()) if slots else 0
        caps = (c.cantrip_cap(), c.prepared_hint())
        print("  %-9s lv%-2d type=%-6s 环位 %-2d 戏法上限 %-2d 可准备 %-3d  %s"
              % (cid, lv, (casting or {}).get("type", "-"), n_slots,
                 caps[0], caps[1], want))
        if cid == "wizard":
            assert c.book_spells() or c.spellbook is not None, "法师没法术书"
        if cid == "warlock":
            assert c.pact_level() >= 1, "邪术师没有秘契位"
            assert c.arcanum_levels(), "邪术师 11 级应有玄奥秘法"
        if not casting:
            print("    ✗ %s 应能施法却没有 casting 配置" % cid)
            bad += 1
        if n_slots == 0:
            print("    ✗ %s 没有任何法术位" % cid)
            bad += 1
    return bad


def ui_smoke(r):
    print("== P4 界面冒烟 (3 个角色 x 六个标签页) ==")
    app = cb.App(selftest=True)
    cases = [("wizard", "Evoker", 3), ("sorcerer", "Draconic Sorcery", 6),
             ("barbarian", "Path of the Berserker", 12)]
    bad = 0
    for cid, sub, lv in cases:
        c = make(r, cid, sub, lv)
        app.set_character(c)
        app.update_idletasks()
        tabs = app.nb.tabs()
        if len(tabs) != 6:
            print("  ✗ %s 标签页数量 %d != 6" % (cid, len(tabs)))
            bad += 1
        overs = []
        for i, tid in enumerate(tabs):
            w = app.nametowidget(tid)
            app.nb.select(tid)
            app.update_idletasks()
            rw, rh = w.winfo_reqwidth(), w.winfo_reqheight()
            if rw > 606 or rh > 574:
                overs.append("%d:%dx%d" % (i, rw, rh))
        name = app.nb.tab(tabs[0], "text").strip()
        print("  %-9s lv%-2d 六页 %s  首标签=%s %s"
              % (cid, lv, "OK" if not overs else "溢出 " + ",".join(overs),
                 name, "" if not overs else "<-- 超框"))
        if overs:
            bad += 1
        # 职业页必须能被 _render_class_tab 填满而不报错
        app.nb.select(tabs[3])
        app.update_idletasks()
        kids = len(app.class_body.winfo_children())
        if kids == 0:
            print("  ✗ %s 职业页空白" % cid)
            bad += 1
        print("    职业页控件 %d 个, 宽 %d" % (kids,
                                              app.class_body.winfo_reqwidth()))
    app.destroy()
    return bad


def main():
    r = cb.Rules()
    bad = caster_smoke(r) + ui_smoke(r)
    print("=" * 52)
    if bad:
        print("SMOKE FAILED — %d 处问题" % bad)
        return 1
    print("SMOKE OK — 4 个施法职业数值正常, 3 个角色六页均无溢出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
