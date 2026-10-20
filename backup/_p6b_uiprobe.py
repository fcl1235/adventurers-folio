# -*- coding: utf-8 -*-
"""P6b 界面探针: 传奇恩惠面板 + 抗性显示是否真的出现在界面上。

跑法: python backup/_p6b_uiprobe.py   (需 PYTHONIOENCODING=utf-8)
"""
import importlib.util
import os
import sys

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "cb", os.path.join(DIR, "dnd55e_character_builder.py"))
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)
for fn in ("showwarning", "showinfo", "showerror"):
    setattr(cb.messagebox, fn, lambda *a, **k: None)

FAIL = []


def check(ok, msg):
    print(("  \u2713 " if ok else "  \u2717 ") + msg)
    if not ok:
        FAIL.append(msg)


r = cb.Rules()
app = cb.App(selftest=True)
app.update_idletasks()

c = cb.Character(r)
c.class_id, c.background_id, c.species_id = "wizard", "sage", "human"
c.base_scores = {"STR": 8, "DEX": 14, "CON": 14, "INT": 17, "WIS": 12, "CHA": 10}
c.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
c.skill_prof = {"arcana", "history", "insight", "persuasion"}
c.feats = ["Boon of Fortitude", "Boon of Energy Resistance",
           "Boon of Skill", "Boon of Truesight"]
c.level = 20
c.subclass = "Evoker"
c.hp_current = c.hp_max()
app.set_character(c)
app.update_idletasks()


def texts(widget):
    out = []
    for w in widget.winfo_children():
        try:
            t = w.cget("text")
            if t:
                out.append(str(t))
        except Exception:
            pass
        out.extend(texts(w))
    return out


print("[1] 职业页出现「传奇恩惠」面板")
blob = "\n".join(texts(app.class_body))
check("传奇恩惠（19 级获得）" in blob, "有面板标题")
for nm in ("强健之恩惠", "能量抗性之恩惠", "技艺之恩惠", "真实视觉之恩惠"):
    check(nm in blob, f"列出 {nm}")
check("属性 +1 →" in blob, "有属性 +1 下拉")

print("[2] 抗性勾选框与保存")
check("选 2 种伤害抗性" in blob, "有抗性选择提示")
app._boon_res_toggle("fire", type("V", (), {"get": lambda self: True,
                                           "set": lambda self, v: None})())
check(c.boon_resist == ["fire"], f"选了火焰: {c.boon_resist}")
check("抗性: 火焰" in app.bonus_text.get("1.0", "end"),
      "装备·加成页显示抗性行")
print("[3] 超出上限被拒绝")
for r2 in ("cold", "lightning"):
    app._boon_res_toggle(r2, type("V", (), {"get": lambda self: True,
                                            "set": lambda self, v: None})())
check(sorted(c.boon_resist) == ["cold", "fire"],
      f"最多 2 项: {c.boon_resist}")

print("[4] 专精下拉 + 属性下拉")
app._boon_exp_set("arcana")
check(c.boon_expertise == ["arcana"], f"专精: {c.boon_expertise}")
check(app.char.skill_mod("arcana") >
      app.char.skill_mod("history"), "奥秘因专精高于历史")
app._boon_ab_set("Boon of Fortitude", "CON")
check(c.boon_ability.get("Boon of Fortitude") == "CON", "属性 +1 记为 CON")

print("[5] 真实视觉")
check(c.truesight() == 60, f"truesight {c.truesight()}")
check("真实视觉 60 尺" in app.bonus_text.get("1.0", "end"),
      "界面显示真实视觉")

print("[6] 布局未被撑破")
app.update_idletasks()
check(app.class_body.winfo_reqwidth() <= 560,
      f"职业页宽 {app.class_body.winfo_reqwidth()} ≤ 560")

print()
if FAIL:
    print("UIPROBE FAIL — %d 项" % len(FAIL))
    for f in FAIL:
        print("  · " + f)
    sys.exit(1)
print("UIPROBE OK — 恩惠面板与抗性显示均正常")
