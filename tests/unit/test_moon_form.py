# -*- coding: utf-8 -*-
"""P8f 验收：月亮结社「圆月形态」真的改写了荒野变形（G17）。

原文（XPHB，`data/raw/_5e_class-druid.json`）三条数值：

  挑战等级  形态的 CR 上限 = 德鲁伊等级 ÷ 3（向下取整）
  护甲等级  AC 取「13 + 感知调整值」与形态 AC 的**较高者**（不是覆盖）
  临时生命  3 × 德鲁伊等级（基础规则是 1 × 等级）

三条都挂在同一个 morph 效果上，而这个效果**还会被 18 级的野兽施法改写**
（解除施法禁令）。所以这组测试里最要紧的一条不是「3 级算对了」，
而是「18 级时前一条没被后一条冲掉」—— 整条替换式 patch 在这里会静默丢规则。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import IllegalAction, PluginError
from dnd5r.model.levels import ClassLevel
from dnd5r.rules.build import morph_axis_for
from dnd5r.rules.morph import forbidden

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
DRUID = "dnd2024.class.druid"
MOON = "dnd2024.subclass.druid.circle_of_the_moon"
WILD_SHAPE = "dnd2024.class.druid.wild_shape"

# 感知 16（+3）：AC 下限 16，比任何形态的 AC 都高
SCORES = {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 16, "cha": 12}
# 感知 10（+0）：AC 下限 13，巨型蜘蛛（AC 14）会保留形态自己的 AC
PLAIN_WIS = dict(SCORES, wis=10)

CAT = "dnd2024.form.beast.cat"                # AC 12, CR 0
SPIDER = "dnd2024.form.beast.giant_spider"    # AC 14, CR 1（还带攀爬，不带飞行）
EAGLE = "dnd2024.form.beast.giant_eagle"      # CR 1，有飞行 → 8 级才解禁


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def druid(self, level, subclass=MOON, scores=None):
        return api.new_character(self.bundle, DRUID, level, scores or SCORES,
                                 name_zh="德鲁伊", name_en="Druid",
                                 subclass=subclass)

    def morph(self, actor, form_id):
        return api.use_power(actor, self.bundle, WILD_SHAPE,
                             choice={"form_id": form_id})


class CircleFormsTest(Base):
    """3 级：临时生命 3×、AC 下限、CR 轴三件事。"""

    def test_temp_hp_is_three_times_level(self):
        actor = self.druid(3)
        self.morph(actor, CAT)
        self.assertEqual(actor.root().hp.temp, 9)      # 3 × 3
        # 反证：没有月亮结社的德鲁伊仍是 1 × 等级
        plain = self.druid(3, subclass=None)
        self.morph(plain, CAT)
        self.assertEqual(plain.root().hp.temp, 3)

    def test_ac_floor_wins_when_higher(self):
        actor = self.druid(3)             # 感知 +3 → 下限 16 > 猫的 12
        self.morph(actor, CAT)
        self.assertEqual(api.character_sheet(actor, self.bundle)["ac"]["total"], 16)

    def test_form_ac_kept_when_higher(self):
        """下限不是覆盖：巨型蜘蛛 AC 14 > 13，仍用 14。"""
        actor = self.druid(3, scores=PLAIN_WIS)   # 感知 +0 → 下限 13
        self.morph(actor, SPIDER)
        self.assertEqual(api.character_sheet(actor, self.bundle)["ac"]["total"], 14)
        # 同一只德鲁伊变猫：12 < 13，被下限顶到 13
        fresh = self.druid(3, scores=PLAIN_WIS)
        self.morph(fresh, CAT)
        self.assertEqual(api.character_sheet(fresh, self.bundle)["ac"]["total"], 13)

    def test_cr_limit_is_level_divided_by_three(self):
        axis = morph_axis_for(self.druid(3), self.bundle)
        self.assertEqual(axis.max_cr(ClassLevel(3)), 1.0)
        self.assertEqual(axis.max_cr(ClassLevel(8)), 2.0)
        self.assertEqual(axis.max_cr(ClassLevel(18)), 6.0)
        # 反证：基础德鲁伊的轴完全不同（3 级还是 1/4）
        plain = morph_axis_for(self.druid(3, subclass=None), self.bundle)
        self.assertEqual(plain.max_cr(ClassLevel(3)), 0.25)

    def test_cr_limit_expands_the_form_list(self):
        moon = {form.id for form in api.eligible_forms_for(self.druid(3), self.bundle)}
        plain = {form.id for form in api.eligible_forms_for(
            self.druid(3, subclass=None), self.bundle)}
        self.assertIn(SPIDER, moon)          # CR 1：月环能变
        self.assertNotIn(SPIDER, plain)      # 基础德鲁伊 3 级只能到 CR 1/4
        self.assertTrue(moon > plain)

    def test_swim_and_fly_gates_are_not_lifted(self):
        """CR 轴上去了，不代表飞行也解禁 —— 那两条仍取职业轴。"""
        forms = {form.id for form in api.eligible_forms_for(self.druid(3), self.bundle)}
        self.assertNotIn(EAGLE, forms)
        later = {form.id for form in api.eligible_forms_for(self.druid(8), self.bundle)}
        self.assertIn(EAGLE, later)

    def test_no_forms_before_wild_shape_unlocks(self):
        """1 级德鲁伊还没有荒野变形 —— 不能因为职业数据里有 morph 轴就列出形态。"""
        self.assertIsNone(morph_axis_for(self.druid(1), self.bundle))
        self.assertEqual(api.eligible_forms_for(self.druid(1), self.bundle), [])


class BeastSpellsStackTest(Base):
    """18 级野兽施法改写同一个 morph：两处 patch 必须叠加，不能互相冲掉。"""

    def test_lunar_temp_hp_survives_beast_spells(self):
        actor = self.druid(18)
        self.morph(actor, CAT)
        self.assertEqual(actor.root().hp.temp, 54)      # 3 × 18，不是 18
        self.assertFalse(forbidden(actor, "spellcasting"))   # 野兽施法解禁

    def test_plain_druid_still_cannot_cast_in_form(self):
        """「野兽施法」是德鲁伊 18 级的本职特性，不是月环专属 —— 17 级时仍然禁施法。"""
        actor = self.druid(17, subclass=None)
        self.morph(actor, CAT)
        self.assertTrue(forbidden(actor, "spellcasting"))
        self.assertEqual(actor.root().hp.temp, 17)      # 1 × 等级

    def test_ac_floor_survives_beast_spells(self):
        actor = self.druid(18)
        self.morph(actor, CAT)
        self.assertEqual(api.character_sheet(actor, self.bundle)["ac"]["total"], 16)

    def test_cr_axis_survives_beast_spells(self):
        axis = morph_axis_for(self.druid(18), self.bundle)
        self.assertEqual(axis.max_cr(ClassLevel(18)), 6.0)


class ImprovedCircleFormsTest(Base):
    """6 级坚韧增强：只**在变形期间**给体质豁免加感知调整值。"""

    def test_bonus_only_while_morphed(self):
        actor = self.druid(6)
        before = api.character_sheet(actor, self.bundle)["saves"]["con"]["total"]
        self.morph(actor, CAT)
        after = api.character_sheet(actor, self.bundle)["saves"]["con"]["total"]
        # 猫的体质 10（+0），加感知 +3 → 3；本体是体质 14（+2）且没有这条加值
        self.assertEqual(before, 2)
        self.assertEqual(after, 3)
        self.assertNotEqual(before, after)

    def test_absent_below_level_six(self):
        actor = self.druid(5)
        self.morph(actor, CAT)
        self.assertEqual(api.character_sheet(actor, self.bundle)["saves"]["con"]["total"], 0)


class MoonlightStepTest(Base):
    """10 级：能力是「按钮 + 诚实标注」，不能假装算过次数。"""

    def test_is_a_bonus_action_button(self):
        actor = self.druid(10)
        sheet = api.character_sheet(actor, self.bundle)
        row = next(item for item in sheet["powers"]
                   if item["id"].endswith("moonlight_step"))
        self.assertTrue(row["button"])
        # 有按钮、确实花一个附赠动作 = `active`（不是「算过了」也不是「没算」）。
        # 次数不建池，所以能力原文里必须写清「手动记」。
        self.assertEqual(row["status"], "active")
        power = next(item for item in api.available_powers(self.bundle, actor)
                     if item.id.endswith("moonlight_step"))
        notes = " ".join(effect.text.zh for effect in power.effects
                         if getattr(effect, "op", "") == "note")
        self.assertIn("手动", notes)
        # 反证：6 级还没有这个能力
        early = api.character_sheet(self.druid(6), self.bundle)["powers"]
        self.assertFalse([item for item in early if item["id"].endswith("moonlight_step")])

    def test_unknown_form_is_rejected(self):
        # 形态不在可选集里时，`use_power` 是「返回 ok=False」而不是抛异常
        report = self.morph(self.druid(3), "dnd2024.form.beast.tarrasque")
        self.assertFalse(report["ok"])
        self.assertIn("不可选", report["message"])


class PatchMergeTest(unittest.TestCase):
    """字段合并的机制本身：只写一个字段的 patch 不许清掉别的字段。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_patch_only_forbid_keeps_temp_hp(self):
        from dnd5r.rules.effects.morph import Morph
        from dnd5r.rules.powers import apply_patch, parse_power

        target = parse_power({
            "id": "demo.class.wild", "name": {"zh": "变形", "en": "Wild"},
            "text": {"zh": "变形", "en": "Wild"},
            "level": 2, "kind": "activated", "target": "self",
            "effects": [{"morph": {"temp_hp": {"plus": "class_level"},
                                   "forbid": ["spellcasting"]}}],
        }, owner="demo.class")
        augment = parse_power({
            "id": "demo.class.cast_in_form", "name": {"zh": "野兽施法", "en": "Beast Spells"},
            "text": {"zh": "野兽施法", "en": "Beast Spells"},
            "level": 18, "kind": "passive", "target": "self",
            "augments": ["demo.class.wild"],
            "patch": {"effects": {"morph": {"forbid": []}}},
        }, owner="demo.class")
        merged = apply_patch(target, augment)
        morph = next(e for e in merged.effects if isinstance(e, Morph))
        self.assertEqual(morph.forbid, ())
        self.assertIsNotNone(morph.temp_hp, "合并把临时 HP 冲掉了")
        self.assertEqual(morph.keep, ("int", "wis", "cha"))

    def test_cr_axis_can_be_patched(self):
        from dnd5r.rules.effects.morph import Morph
        from dnd5r.rules.powers import apply_patch, parse_power

        target = parse_power({
            "id": "demo.class.wild", "name": {"zh": "变形", "en": "Wild"},
            "text": {"zh": "变形", "en": "Wild"},
            "level": 2, "kind": "activated", "target": "self",
            "effects": [{"morph": {"temp_hp": {"plus": "class_level"}}}],
        }, owner="demo.class")
        augment = parse_power({
            "id": "demo.sub.moon", "name": {"zh": "圆月", "en": "Moon"},
            "text": {"zh": "圆月", "en": "Moon"},
            "level": 3, "kind": "passive", "target": "self",
            "augments": ["demo.class.wild"],
            "patch": {"effects": {"morph": {"cr_by_level": {3: 1, 6: 2}}}},
        }, owner="demo.sub")
        morph = next(e for e in apply_patch(target, augment).effects
                     if isinstance(e, Morph))
        self.assertEqual(dict(morph.cr_by_level), {3: 1, 6: 2})
        self.assertIsNotNone(morph.temp_hp)

    def test_bad_cr_axis_rejected(self):
        from dnd5r.rules.effects.morph import Morph
        with self.assertRaises(PluginError):
            Morph.from_payload({"cr_by_level": []}, where="demo")
        with self.assertRaises(PluginError):
            Morph.from_payload({"cr_by_level": {"three": 1}}, where="demo")


if __name__ == "__main__":
    unittest.main()
