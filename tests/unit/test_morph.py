# -*- coding: utf-8 -*-
"""P4 验收：变形的四条不变量 + CR 轴 + 叠层按等级生效。

四条不变量（设计文档 §3.1）：
  1. 属性：力/敏/体换成形态值，智/感/魅保留本体
  2. AC：完全来自形态，护甲通道不参与
  3. HP：上限留在本体不变，临时 HP 按 policy 给，回本体时只收回形态给的那部分
  4. 动作：变形期间被禁止的事沿层链生效，18 级「野兽施法」解除

这些是「变形写错最常见」的四类错误，所以单独成文件、逐条断言。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import IllegalAction, PluginError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.model.levels import ClassLevel
from dnd5r.rules.actioneconomy import ActionEconomy
from dnd5r.rules.effects import EffectContext
from dnd5r.rules.morph import (
    CrAxis,
    build_form,
    eligible_forms,
    enter_form,
    is_morphed,
    leave_form,
    max_cr,
    reasons_for,
)
from dnd5r.rules.powers import can_use, parse_power

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
TEXT = {"zh": "测试", "en": "Test"}
DRUID = "dnd2024.class.druid"
WILD_SHAPE = "dnd2024.class.druid.wild_shape"
REVERT = "dnd2024.class.druid.wild_shape_revert"
BROWN_BEAR = "dnd2024.form.beast.brown_bear"
CAT = "dnd2024.form.beast.cat"


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        cls.druid = cls.bundle.class_def(DRUID)
        cls.axis = cls.druid.morph

    def actor(self, level=8):
        return api.new_character(self.bundle, DRUID, level, SCORES,
                                 name_zh="测试德鲁伊", name_en="Test Druid")

    def form(self, form_id):
        return self.bundle.forms[form_id]

    def context(self, actor, power=None):
        return EffectContext(
            actor=actor, rng=ScriptedRng([3] * 40),
            prof_bonus=2, total_level=actor.profile.total,
            class_level=ClassLevel(8), source=power.id if power else "",
        )

    def morph(self, actor, form_id, temp_hp=8):
        # forbid 与德鲁伊数据一致；数据本身是否声明由 PatchLevelGateTest 检查
        return enter_form(actor, self.form(form_id), temp_hp, forbid=("spellcasting",))


class CrAxisTest(_Fixture):
    def test_steps(self):
        """2024：2 级 CR1/4、4 级 1/2、8 级 1；1 级还没有变形所以是 0。"""
        self.assertEqual(max_cr(self.axis, ClassLevel(1)), 0.0)
        self.assertEqual(max_cr(self.axis, ClassLevel(2)), 0.25)
        self.assertEqual(max_cr(self.axis, ClassLevel(3)), 0.25)
        self.assertEqual(max_cr(self.axis, ClassLevel(4)), 0.5)
        self.assertEqual(max_cr(self.axis, ClassLevel(8)), 1.0)
        self.assertEqual(max_cr(self.axis, ClassLevel(20)), 1.0)

    def test_swim_gate_at_4(self):
        """有游泳速度的形态 4 级才解禁 —— 这条最常被漏掉。"""
        low = {form.id for form in eligible_forms(self.bundle.forms.values(), self.axis, ClassLevel(2))}
        mid = {form.id for form in eligible_forms(self.bundle.forms.values(), self.axis, ClassLevel(4))}
        frog = "dnd2024.form.beast.frog"
        self.assertNotIn(frog, low)
        self.assertIn(frog, mid)
        self.assertIn("游泳速度要 4 级才解禁",
                      reasons_for(self.axis, ClassLevel(2), self.form(frog)))

    def test_fly_gate_at_8(self):
        owl = "dnd2024.form.beast.owl"
        at7 = {form.id for form in eligible_forms(self.bundle.forms.values(), self.axis, ClassLevel(7))}
        at8 = {form.id for form in eligible_forms(self.bundle.forms.values(), self.axis, ClassLevel(8))}
        self.assertNotIn(owl, at7)
        self.assertIn(owl, at8)

    def test_cr_limit_reason(self):
        reasons = reasons_for(self.axis, ClassLevel(2), self.form(BROWN_BEAR))
        self.assertTrue(any("CR" in reason for reason in reasons), reasons)

    def test_every_form_is_eligible_somewhere(self):
        """每只野兽都必须在某个等级可选，否则就是死数据。"""
        reachable = set()
        for level in range(1, 21):
            reachable |= {form.id for form in eligible_forms(
                self.bundle.forms.values(), self.axis, ClassLevel(level))}
        self.assertEqual(reachable, set(self.bundle.forms))


class AttributesTest(_Fixture):
    def test_physical_replaced_mental_kept(self):
        actor = self.actor()
        layer = self.morph(actor, BROWN_BEAR)
        abilities = layer.statblock.abilities
        # 棕熊 17/12/15，德鲁伊 10/12/8
        self.assertEqual((abilities.score("str"), abilities.score("dex"), abilities.score("con")),
                         (17, 12, 15))
        self.assertEqual((abilities.score("int"), abilities.score("wis"), abilities.score("cha")),
                         (10, 12, 8))
        # 本体不受影响
        self.assertEqual(actor.statblock.abilities.score("str"), 16)
        self.assertEqual(actor.statblock.abilities.score("int"), 10)

    def test_query_goes_to_top(self):
        actor = self.actor()
        self.morph(actor, BROWN_BEAR)
        self.assertEqual(actor.top().statblock.abilities.score("str"), 17)
        self.assertEqual(actor.root().statblock.abilities.score("str"), 16)


class ArmorClassTest(_Fixture):
    def test_ac_is_form_ac_exactly(self):
        """AC 全部来自形态层：不准把本体的敏捷或护甲再叠一次。"""
        actor = self.actor()
        layer = self.morph(actor, BROWN_BEAR)
        stat = layer.statblock
        self.assertEqual(stat.ac_base + stat.abilities.mod("dex"), 11)

    def test_high_dex_form_keeps_its_ac(self):
        cat = self.form(CAT)          # AC 12，敏捷 +2 → 基础 10
        self.assertEqual(build_form(cat).statblock.ac_base, 10)

    def test_ac_min_is_a_floor_not_an_override(self):
        """月之环的 13+感知 是下限：形态自带更高 AC 时不该被压低。"""
        bear = self.form(BROWN_BEAR)   # AC 11，敏捷 +1
        low = build_form(bear, ac_min=13).statblock
        self.assertEqual(low.ac_base + low.abilities.mod("dex"), 13)
        spider = self.form("dnd2024.form.beast.giant_spider")   # AC 14
        high = build_form(spider, ac_min=13).statblock
        self.assertEqual(high.ac_base + high.abilities.mod("dex"), 14)


class HitPointsTest(_Fixture):
    def test_maximum_stays_on_body(self):
        actor = self.actor()
        before = actor.hp.maximum
        layer = self.morph(actor, BROWN_BEAR)
        self.assertEqual(actor.hp.maximum, before)
        self.assertEqual(layer.hp.maximum, 22)       # 形态自己的池，仅作展示
        self.assertEqual(actor.hp.temp, 8)           # 等于德鲁伊等级

    def test_damage_eats_temp_first(self):
        actor = self.actor()
        self.morph(actor, CAT, temp_hp=8)
        applied = actor.hp.damage(5)
        self.assertEqual((applied, actor.hp.temp, actor.hp.current),
                         (5, 3, actor.hp.maximum))

    def test_revert_only_reclaims_morph_temp(self):
        """先喝药得的临时 HP 不能被变形吞掉 —— 这是最容易写错的一行。"""
        actor = self.actor()
        actor.hp.grant_temp(6)
        self.morph(actor, CAT, temp_hp=8)            # 取大不叠加 → 仍是 8
        self.assertEqual(actor.hp.temp, 8)
        leave_form(actor)
        # 形态只「贡献」了 8-6=2，收回 2 之后剩下 6
        self.assertEqual(actor.hp.temp, 6)

    def test_revert_when_not_morphed_raises(self):
        with self.assertRaises(IllegalAction):
            leave_form(self.actor())


class ForbidTest(_Fixture):
    def test_spell_blocked_while_morphed(self):
        actor = self.actor()
        spell = parse_power({
            "id": "demo.power.spell", "name": TEXT, "text": TEXT,
            "level": 1, "kind": "activated", "tags": ["spell"],
        })
        context = self.context(actor)
        self.assertEqual(can_use(spell, context, ActionEconomy()), [])

        self.morph(actor, CAT)
        context = self.context(actor)
        self.assertIn("变形期间无法施法", can_use(spell, context, ActionEconomy()))

    def test_revert_clears_forbid(self):
        actor = self.actor()
        spell = parse_power({
            "id": "demo.power.spell", "name": TEXT, "text": TEXT,
            "level": 1, "kind": "activated", "tags": ["spell"],
        })
        self.morph(actor, CAT)
        leave_form(actor)
        self.assertEqual(can_use(spell, self.context(actor), ActionEconomy()), [])


class PatchLevelGateTest(_Fixture):
    def _forbid_at(self, level):
        for power in self.druid.powers_at(ClassLevel(level)):
            if power.id != WILD_SHAPE:
                continue
            return [effect.forbid for effect in power.effects
                    if getattr(effect, "op", "") == "morph"][0]
        raise AssertionError("荒野变形在 %d 级未解锁" % level)

    def test_beast_spells_only_from_18(self):
        """叠层按「本职业等级」现算：18 级才解除施法禁令。"""
        self.assertEqual(self._forbid_at(17), ("spellcasting",))
        self.assertEqual(self._forbid_at(18), ())
        self.assertEqual(self._forbid_at(20), ())

    def test_patch_does_not_leak_into_low_levels(self):
        """加载期的 book 里那份是原版，任何等级读 powers_at 都不会互相污染。"""
        low = self.druid.powers_at(ClassLevel(2))
        high = self.druid.powers_at(ClassLevel(20))
        self.assertEqual(len([p for p in low if p.id == WILD_SHAPE]), 1)
        self.assertEqual(len([p for p in high if p.id == WILD_SHAPE]), 1)
        self.assertEqual(self._forbid_at(2), ("spellcasting",))


class LayerStackTest(_Fixture):
    def test_second_morph_does_not_stack_layers(self):
        actor = self.actor()
        self.morph(actor, CAT, temp_hp=8)
        self.morph(actor, BROWN_BEAR, temp_hp=8)
        top = actor.top()
        self.assertIs(actor.above, top)
        self.assertIsNone(top.above)               # 只有一层，不是叠罗汉
        self.assertEqual(top.statblock.abilities.score("str"), 17)
        self.assertEqual(actor.hp.temp, 8)

    def test_is_morphed(self):
        actor = self.actor()
        self.assertFalse(is_morphed(actor))
        self.morph(actor, CAT)
        self.assertTrue(is_morphed(actor))
        leave_form(actor)
        self.assertFalse(is_morphed(actor))


class MorphEffectTest(_Fixture):
    def _morph_power(self, level=8):
        for power in self.druid.powers_at(ClassLevel(level)):
            if power.id == WILD_SHAPE:
                return power
        raise AssertionError("荒野变形未解锁")

    def test_without_form_choice_raises(self):
        actor = self.actor()
        context = self.context(actor, self._morph_power())
        with self.assertRaises(IllegalAction) as caught:
            for effect in self._morph_power().effects:
                effect.apply(context)
        self.assertIn("选一个形态", str(caught.exception))

    def test_form_outside_eligible_list_raises(self):
        """scratch 里只放 2 级可选形态，却硬塞棕熊 → 当场拒绝。"""
        actor = self.actor(level=2)
        power = self._morph_power(2)
        context = self.context(actor, power)
        context.scratch["forms"] = {
            form.id: form for form in eligible_forms(
                self.bundle.forms.values(), self.axis, ClassLevel(2))
        }
        context.scratch["form_id"] = BROWN_BEAR
        with self.assertRaises(IllegalAction) as caught:
            for effect in power.effects:
                effect.apply(context)
        self.assertIn("不可选", str(caught.exception))

    def test_unknown_keep_key_rejected(self):
        with self.assertRaises(PluginError):
            parse_power({
                "id": "demo.power.morph", "name": TEXT, "text": TEXT, "level": 1,
                "kind": "activated",
                "effects": [{"morph": {"temp_hp": 1, "keep": ["str", "luck"]}}],
            })

    def test_unknown_field_rejected(self):
        with self.assertRaises(PluginError):
            parse_power({
                "id": "demo.power.morph", "name": TEXT, "text": TEXT, "level": 1,
                "kind": "activated",
                "effects": [{"morph": {"temp_hp": 1, "cr": 3}}],
            })


class SessionMorphTest(_Fixture):
    """P11 起 Session 没有自己的投影：看角色读 api.character_sheet。"""

    def session(self, level):
        from dnd5r.session import Session

        session = Session(self.bundle, seed=7)
        session.create_character(DRUID, level, SCORES)
        return session

    def sheet(self, session) -> dict:
        return api.character_sheet(session.character, session.bundle)

    def test_no_forms_before_wild_shape_unlocks(self):
        session = self.session(1)
        self.assertEqual(api.eligible_forms_for(session.character, session.bundle), [])

    def test_forms_follow_cr_axis(self):
        session = self.session(4)
        names = {form.id
                 for form in api.eligible_forms_for(session.character, session.bundle)}
        self.assertIn(CAT, names)
        self.assertNotIn(BROWN_BEAR, names)

    def test_flow_morph_then_revert(self):
        from dnd5r.session import NewTurn, UsePower

        session = self.session(8)
        before = self.sheet(session)
        report = session.dispatch(UsePower(WILD_SHAPE, {"form_id": BROWN_BEAR}))
        self.assertTrue(report.ok, report.message)
        sheet = self.sheet(session)
        self.assertEqual(sheet["name"], "棕熊")
        self.assertEqual(sheet["ac"]["total"], 11)
        self.assertEqual(sheet["hp"]["temp"], 8)
        self.assertEqual(sheet["hp"]["maximum"], before["hp"]["maximum"])  # 上限不变
        self.assertEqual(sheet["speed"], {"walk": 40, "climb": 30})

        session.dispatch(NewTurn())                        # 变形与恢复都要附赠动作
        report = session.dispatch(UsePower(REVERT))
        self.assertTrue(report.ok, report.message)
        after = self.sheet(session)
        self.assertFalse(after["morphed"])
        self.assertEqual(after["name"], before["name"])
        self.assertEqual(after["hp"]["temp"], 0)

    def test_revert_requires_morph(self):
        from dnd5r.session import UsePower

        report = self.session(8).dispatch(UsePower(REVERT))
        self.assertFalse(report.ok)
        self.assertIn("morphed", report.message)


if __name__ == "__main__":
    unittest.main()
