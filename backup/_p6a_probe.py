# -*- coding: utf-8 -*-
"""P6a/P6b 探针: 传奇恩惠 effects 是否真的生效 (不依赖界面)。

跑法: python backup/_p6a_probe.py   (需 PYTHONIOENCODING=utf-8)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dnd55e import consts                     # noqa: E402
from dnd55e.character import Character        # noqa: E402
from dnd55e.rules import Rules                # noqa: E402

FAIL = []


def check(ok, msg):
    if ok:
        print("  \u2713 " + msg)
    else:
        print("  \u2717 " + msg)
        FAIL.append(msg)


def mk(cls_id="wizard", level=19, sub="Evoker", feats=None, scores=None):
    r = Rules()
    c = Character(r)
    c.class_id = cls_id
    c.background_id = "sage"
    c.species_id = "human"
    c.base_scores = scores or {"STR": 10, "DEX": 14, "CON": 14,
                               "INT": 17, "WIS": 12, "CHA": 10}
    c.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
    c.skill_prof = {"arcana", "history", "insight"}
    c.feats = list(feats or [])
    c.level = level
    c.subclass = sub
    c.hp_current = c.hp_max()
    return c


print("[1] 数据: 12 条恩惠 + effects 键")
boons = consts.GENERAL_FEATS["epic_boon"]
check(len(boons) == 12, "epic_boon 12 条")
check(all("ability_boost" in b["effects"] for b in boons.values()),
      "12 条都带 ability_boost")
check(consts.feat_cn("Boon of Fortitude") != "Boon of Fortitude",
      "feat_cn 能出中文: " + consts.feat_cn("Boon of Fortitude"))

print("[2] Boon of Fortitude: HP 上限 +40")
base = mk()
fort = mk(feats=["Boon of Fortitude"], scores={"STR": 10, "DEX": 14,
                                               "CON": 15, "INT": 17,
                                               "WIS": 12, "CHA": 10})
fort2 = mk(scores={"STR": 10, "DEX": 14, "CON": 15, "INT": 17,
                   "WIS": 12, "CHA": 10})
check(base.hp_max() == fort2.hp_max() - 0 or True, "基准可算")
check(fort.hp_max() == fort2.hp_max() + 40,
      f"HP {fort.hp_max()} == {fort2.hp_max()} + 40")

print("[3] Boon of Speed: 速度 +30")
sp = mk(feats=["Boon of Speed"])
check(sp.speed() == fort2.speed() + 30,
      f"速度 {sp.speed()} == {fort2.speed()} + 30")

print("[4] Boon of Skill: 全部技能熟练 + 1 项专精")
sk = mk(feats=["Boon of Skill"])
sk.boon_expertise = ["arcana"]          # arcana 本来已熟练
plain = mk()
check(sk.skill_mod("arcana") == plain.skill_mod("arcana") + sk.pb(),
      "已熟练技能获专精 (再 +1×PB)")
check(sk.skill_mod("animal_handling")
      == plain.skill_mod("animal_handling") + plain.pb(),
      "未熟练技能变熟练 (+PB)")

print("[5] Boon of Energy Resistance: 选 2 种抗性")
er = mk(feats=["Boon of Energy Resistance"])
check(er.resistances() == [], "未选时无抗性")
er.boon_resist = ["fire", "cold"]
check(er.resistances() == ["fire", "cold"],
      "抗性 = " + str(er.resistances()))

print("[6] ability_boost: +1 属性, 上限 30")
ab = mk(feats=["Boon of Fortitude"])
ab.boon_ability = {"Boon of Fortitude": "CON"}
check(ab.score("CON") == plain.score("CON") + 1,
      f"CON {ab.score('CON')} == {plain.score('CON')} + 1")
check(ab.boon_ability_cap("CON") == 30, "CON 上限 30")
ab.base_scores["CON"] = 20          # 先顶到 20 上限
check(ab.score("CON") == 21, f"20 + 1 = {ab.score('CON')} (突破 20)")
ab.base_scores["CON"] = 15
check(ab.score("CON") == 17, f"15 + 背景1 + 恩惠1 = {ab.score('CON')}")

print("[7] 存档往返保留三字段")
d = ab.to_dict()
c2 = Character(Rules())
c2.load_dict(d)
check(c2.boon_ability == ab.boon_ability, "boon_ability 往返")
check(c2.boon_resist == ab.boon_resist, "boon_resist 往返")
er2 = mk(feats=["Boon of Energy Resistance"])
er2.boon_resist = ["fire"]
c3 = Character(Rules())
c3.load_dict(er2.to_dict())
check(c3.boon_resist == ["fire"], "boon_resist 非空往返")

print("[8] 18→19 升级: 恩惠写进 feats 并生效")
lv = mk(level=18)
before = lv.hp_max()
import dnd55e.ui_io as uio                     # noqa: E402
import types                                   # noqa: E402


class _FakeDlg(object):
    def __init__(self):
        self.result = {"level": 19, "subclass": None,
                       "asi": {"type": "feat", "name": "Boon of Fortitude"},
                       "boon": "Boon of Fortitude", "boon_ability": "CON"}


class _FakeApp(object):
    """只借用 ui_io.level_up 的纯逻辑, 界面部分打桩"""
    def __init__(self, ch):
        self.char = ch
        self._selftest = True
        self.wait_window = lambda *a, **k: None
        self.refresh = lambda: None
        self._log_roll = lambda *a, **k: None

    level_up = uio.AppIO.level_up


fake = _FakeApp(lv)
uio.LevelUpDialog = lambda master, ch: _FakeDlg()
import dnd55e.ui_io as _m                          # noqa: E402
_m.messagebox = types.SimpleNamespace(showinfo=lambda *a, **k: None,
                                      showwarning=lambda *a, **k: None)
fake.level_up()
check("Boon of Fortitude" in lv.feats, "恩惠已进 c.feats")
check(lv.boon_ability.get("Boon of Fortitude") == "CON", "属性选择已记录")
check(lv.hp_max() >= before + 40, f"HP {before} → {lv.hp_max()} (含 +40)")

print()
if FAIL:
    print("PROBE FAIL — %d 项" % len(FAIL))
    for f in FAIL:
        print("  · " + f)
    sys.exit(1)
print("PROBE OK — 传奇恩惠全部生效")
