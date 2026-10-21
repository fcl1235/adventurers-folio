# -*- coding: utf-8 -*-
"""P5b 验收之一：属性加值通道。

这条通道改的是**属性值本身**，所以它的正确性不能只看属性栏 ——
HP（体质）、AC（敏捷/体质）、攻击、豁免必须同时跟着变，否则就是
「面板写着 20 力，攻击加值还按 16 算」。

五条不变量：
  1. 加值落在属性值上（16 → 20），不是加在检定上
  2. 体质变了 HP 上限必须重算（20 级野蛮人 +40 点上下，肉眼可辨）
  3. cap 生效：上限 25 的角色再怎么加也到不了 30
  4. 未到等级不给：19 级野蛮人没有原始冠军
  5. 变形期间形态的力敏体不被本体加值污染
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.model.statblock import Abilities
from dnd5r.rules.scores import (
    ScoreBonus, apply_score_bonuses, score_bonus_of, score_bonuses,
)

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


class ScoreBonusTest(unittest.TestCase):
    def test_apply_and_clamp(self):
        self.assertEqual(ScoreBonus("str", 4).apply_to(16), 20)
        self.assertEqual(ScoreBonus("str", 4, cap=25).apply_to(24), 25)
        self.assertEqual(ScoreBonus("str", 4, cap=25).apply_to(22), 25)
        # 缺省上限是 SCORE_MAX（30），不是 20 —— 属性能过 20 正是这条通道的用途
        self.assertEqual(ScoreBonus("str", 10).apply_to(21), 30)
        self.assertEqual(ScoreBonus("str", 4).apply_to(28), 30)

    def test_rejects_nonsense(self):
        with self.assertRaises(ValueError):
            ScoreBonus("luck", 2)
        with self.assertRaises(ValueError):
            ScoreBonus("str", 0)
        with self.assertRaises(ValueError):
            ScoreBonus("str", "+2")     # 属性加值必须是整数，不接受符号引用

    def test_bonus_order_is_narrow_cap_first(self):
        """上限窄的先结算。反了就会把「24 +1 → 25」算成「顶到 25 后 +1 无效」。"""
        powers = [_power(score="str", value=4, cap=25, ident="capstone"),
                  _power(score="str", value=1, cap=30, ident="boon")]
        ordered = score_bonuses(powers)
        self.assertEqual([item.limit for item in ordered], [25, 30])
        self.assertEqual(apply_score_bonuses(Abilities.of(**SCORES), ordered).score("str"), 21)

    def test_non_integer_bonus_is_rejected(self):
        bad = _power(score="str", value="ability.cha", ident="weird")
        with self.assertRaises(ValueError):
            score_bonuses([bad])


class ScoreChannelContentTest(unittest.TestCase):
    """真内容：两条 20 级压轴能力。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _sheet(self, class_id, level, scores=None):
        actor = api.new_character(self.bundle, class_id, level, scores or SCORES,
                                  name_zh="加值检", name_en="Score Check")
        return actor, api.character_sheet(actor, self.bundle)

    def test_barbarian_capstone(self):
        actor, sheet = self._sheet("dnd2024.class.barbarian", 20)
        self.assertEqual(sheet["abilities"]["str"]["score"], 20)
        self.assertEqual(sheet["abilities"]["con"]["score"], 18)
        self.assertEqual(sheet["abilities"]["str"]["bonus"], 4)
        # 体质 14 → 18，调整值 +2 → +4：HP 必须按 +4 重算
        self.assertEqual(sheet["hp"]["maximum"], 225)
        self.assertEqual(sheet["ac"]["total"], 16)
        self.assertEqual(sheet["attack"]["total"], 11)
        # 面板与派生值必须自洽：面板 20 力就不能按 16 力算攻击
        self.assertEqual(sheet["attack"]["total"], sheet["abilities"]["str"]["mod"] + 6)

    def test_monk_capstone(self):
        _, sheet = self._sheet("dnd2024.class.monk", 20)
        self.assertEqual(sheet["abilities"]["dex"]["score"], 18)
        self.assertEqual(sheet["abilities"]["wis"]["score"], 16)
        self.assertEqual(sheet["ac"]["total"], 17)       # 10 + 4(敏) + 3(感)
        self.assertEqual(sheet["hp"]["maximum"], 143)

    def test_not_before_twentieth(self):
        _, sheet = self._sheet("dnd2024.class.barbarian", 19)
        self.assertEqual(sheet["abilities"]["str"]["score"], 16)
        self.assertEqual(sheet["abilities"]["str"]["bonus"], 0)
        self.assertEqual(sheet["hp"]["maximum"], 176)

    def test_cap_is_25_not_30(self):
        """压轴的上限是 25：24 力 +4 就该停在 25，不是 28。"""
        high = dict(SCORES, str=24)
        _, sheet = self._sheet("dnd2024.class.barbarian", 20, high)
        self.assertEqual(sheet["abilities"]["str"]["score"], 25)

    def test_score_bonus_of_only_reports_unlocked(self):
        low = api.new_character(self.bundle, "dnd2024.class.barbarian", 19, SCORES,
                                name_zh="十九", name_en="Nineteen")
        self.assertEqual(score_bonus_of(api.available_powers(self.bundle, low)), {})
        high = api.new_character(self.bundle, "dnd2024.class.barbarian", 20, SCORES,
                                 name_zh="二十", name_en="Twenty")
        self.assertEqual(score_bonus_of(api.available_powers(self.bundle, high)),
                         {"str": 4, "con": 4})

    def test_morph_keeps_form_scores(self):
        """变形换掉力敏体：本体的加值不该渗进野兽的数值。"""
        actor = api.new_character(self.bundle, "dnd2024.class.druid", 4, SCORES,
                                  name_zh="德鲁伊", name_en="Druid")
        before = api.character_sheet(actor, self.bundle)["abilities"]
        result = api.use_power(actor, self.bundle, "dnd2024.class.druid.wild_shape",
                               choice={"form_id": "dnd2024.form.beast.boar"})
        self.assertTrue(result["ok"], result["message"])
        after = result["sheet"]["abilities"]
        self.assertEqual(after["str"]["score"], 13)          # 野猪的力量
        self.assertEqual(after["int"]["score"], before["int"]["score"])  # 心智保留
        self.assertEqual(after["str"]["bonus"], 0)


def _power(score, value, cap=None, ident="probe"):
    """造一条只有属性加值的假能力：用来单独验证通道，不牵扯任何职业。"""
    from dnd5r.rules.powers import parse_power

    payload = {
        "id": "probe.%s" % ident,
        "name": {"zh": "探针", "en": "Probe"},
        "text": {"zh": "探针能力。", "en": "Probe power."},
        "level": 1,
        "kind": "passive",
        "effects": [_raw_modifier(score, value, cap)],
    }
    return parse_power(payload, owner="probe.class", source="probe.yaml")


def _raw_modifier(score, value, cap):
    payload = {"target": "score.%s" % score, "value": value}
    if cap is not None:
        payload["cap"] = cap
    return {"grant_modifier": {"modifiers": [payload]}}


if __name__ == "__main__":
    unittest.main()
