# -*- coding: utf-8 -*-
"""契约测试：遍历**每一条**内容，而不是手写几个样例。

内容会越来越多，手写测试必然漏。所以这里只做一件事：
把插件里每一个职业、每一个能力都真的构造并执行一次，凡是
「能加载但一执行就炸」的内容，在这里全部暴露。

新增职业/能力不需要改这个文件。
"""

import unittest
from pathlib import Path
from typing import Mapping

import dnd5r.api as api
from dnd5r.kernel.errors import DndError
from dnd5r.kernel.ids import is_valid
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.kernel.text import Text
from dnd5r.model.levels import ClassLevel
from dnd5r.rules.actioneconomy import ActionEconomy
from dnd5r.rules.effects import EffectContext
from dnd5r.rules.powers import PowerKind, can_use, use_power

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
RESERVE = [3] * 300  # 足够长的脚本随机序列，避免契约测试因骰子耗尽而假失败


class ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_content_loads_clean(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertTrue(self.bundle.classes)

    def test_every_id_is_namespaced(self):
        for class_id, class_def in self.bundle.classes.items():
            self.assertTrue(is_valid(class_id), class_id)
            for power in class_def.powers:
                self.assertTrue(is_valid(power.id), power.id)
            for resource in class_def.resources:
                self.assertTrue(is_valid(resource.id), resource.id)

    def test_every_entry_has_bilingual_text(self):
        for class_def in self.bundle.classes.values():
            for text, label in _texts_of(class_def):
                self.assertIsInstance(text, Text, label)
                self.assertTrue(text.zh.strip(), label)
                self.assertTrue(text.en.strip(), label)
                self.assertNotEqual(text.zh, text.en, "%s 的英文缺失或照抄中文" % label)

    def test_power_owner_matches_class(self):
        for class_id, class_def in self.bundle.classes.items():
            for power in class_def.powers:
                self.assertEqual(power.owner, class_id, power.id)

    def test_every_power_can_execute(self):
        """每个能力都在「刚好够用」的最小场景里跑一遍。

        两处需要摆状态的地方，都在这里显式摆，不在规则里开特例：
          - 变形类能力要先有一个可选形态（scratch 注入）
          - 前置写 `morphed: true` 的能力要先把角色真的变形一次
        """
        for class_id, class_def in self.bundle.classes.items():
            level = max(int(power.level) for power in class_def.powers) if class_def.powers else 1
            for power in class_def.powers:
                with self.subTest(power=power.id):
                    actor = api.new_character(self.bundle, class_id, level, SCORES,
                                              name_zh="契约", name_en="Contract")
                    context = self._context(actor, power, level)
                    economy = ActionEconomy()
                    if _needs_morph(power):
                        self.assertTrue(_morph(actor, class_def, level, self.bundle),
                                        "%s 需要变形状态，但 %s 没有可用的变形能力"
                                        % (power.id, class_id))
                        context = self._context(actor, power, level)
                    if power.is_button:
                        self.assertEqual(can_use(power, context, economy), [], power.id)
                        report = use_power(power, context, economy)
                        self.assertTrue(report.ok)
                    else:
                        for effect in power.effects:
                            effect.apply(context)

    def _context(self, actor, power, level):
        context = EffectContext(
            actor=actor, rng=ScriptedRng(list(RESERVE)),
            prof_bonus=api.resolver_for(actor).ctx.prof_bonus,
            total_level=actor.profile.total,
            class_level=ClassLevel(level),
            source=power.id,
        )
        forms = _forms_of(self.bundle, actor)
        if forms and any(getattr(effect, "op", "") == "morph" for effect in power.effects):
            context.scratch["forms"] = {form.id: form for form in forms}
            context.scratch["form_id"] = forms[0].id
        return context

    def test_triggered_powers_are_not_buttons(self):
        for power in self.bundle.book.all():
            if power.kind is PowerKind.TRIGGERED:
                self.assertFalse(power.is_button, power.id)
                self.assertIsNotNone(power.phase, power.id)

    def test_passive_powers_produce_no_button(self):
        for power in self.bundle.book.all():
            if power.kind is PowerKind.PASSIVE:
                self.assertFalse(power.is_button, power.id)

    def test_every_power_is_reachable_at_its_level(self):
        """能力声明的等级必须真的在职业表里解锁，不能挂在 0 级或 99 级上。"""
        for class_id, class_def in self.bundle.classes.items():
            for power in class_def.powers:
                self.assertGreaterEqual(int(power.level), 1, power.id)
                self.assertLessEqual(int(power.level), 20, power.id)
                unlocked = [item.id for item in class_def.powers_at(power.level)]
                self.assertIn(power.id, unlocked)


def _texts_of(class_def):
    yield class_def.name, "%s name" % class_def.id
    for resource in class_def.resources:
        if resource.label is not None:
            yield resource.label, "%s label" % resource.id
    for power in class_def.powers:
        yield power.name, "%s name" % power.id
        yield power.text, "%s text" % power.id


def _needs_morph(power) -> bool:
    prereq = power.prereq
    return isinstance(prereq, Mapping) and "morphed" in prereq


def _forms_of(bundle, actor):
    from dnd5r.rules.morph import eligible_forms

    for entry in actor.profile.classes:
        class_def = bundle.classes.get(entry.class_id)
        if class_def is not None and class_def.morph is not None:
            return eligible_forms(bundle.forms.values(), class_def.morph, entry.class_level)
    return []


def _morph(actor, class_def, level, bundle) -> bool:
    """用该职业自己的变形能力把角色真的变形一次（给「需要变形状态」的能力铺路）。"""
    forms = _forms_of(bundle, actor)
    if not forms:
        return False
    for candidate in class_def.powers_at(ClassLevel(level)):
        if not any(getattr(effect, "op", "") == "morph" for effect in candidate.effects):
            continue
        context = EffectContext(
            actor=actor, rng=ScriptedRng(list(RESERVE)),
            prof_bonus=2, total_level=actor.profile.total,
            class_level=ClassLevel(level), source=candidate.id,
        )
        context.scratch["forms"] = {form.id: form for form in forms}
        context.scratch["form_id"] = forms[0].id
        for effect in candidate.effects:
            effect.apply(context)
        return True
    return False


if __name__ == "__main__":
    unittest.main()
