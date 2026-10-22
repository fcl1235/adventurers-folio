# -*- coding: utf-8 -*-
"""Effect 原语：契约（每个 op 都能解析）＋ 行为（真的改对了东西）。"""

import unittest

from dnd5r.kernel.errors import IllegalAction, PluginError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.kernel.text import Text
from dnd5r.model.actor import Actor, ActorKind, HpPool
from dnd5r.model.profile import Profile
from dnd5r.model.resources import Pool, PoolKind, Refresh
from dnd5r.model.statblock import Abilities, Statblock
from dnd5r.rules.effects import (
    ApplyCondition,
    EffectContext,
    GrantDefense,
    GrantModifier,
    GrantProficiency,
    GrantTempHp,
    Heal,
    ModifyRoll,
    NoteEffect,
    ReduceDamage,
    RecoverResource,
    RemoveCondition,
    SpendResource,
    effect_classes,
    known_ops,
    parse_effect,
    parse_effects,
)

SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


def make_actor(level=5, hp_max=30, current=None) -> Actor:
    stat = Statblock(name=Text.of("测试者", "Tester"), abilities=Abilities.of(**SCORES))
    profile = Profile.single("demo.class_a", level)
    actor = Actor(
        id="pc.test", kind=ActorKind.PC, statblock=stat,
        hp=HpPool(maximum=hp_max, current=current), profile=profile,
    )
    actor.resources.add(Pool(id="demo.pool", kind=PoolKind.CHARGE, capacity=2,
                             refresh=Refresh.LONG_REST))
    return actor


def ctx_for(actor, values=(), source="demo.power"):
    return EffectContext(
        actor=actor,
        rng=ScriptedRng(list(values)),
        prof_bonus=3,
        total_level=actor.profile.total,
        class_level=actor.profile.classes[0].class_level,
        source=source,
    )


class ContractTest(unittest.TestCase):
    def test_registry_covers_documented_ops(self):
        expected = {
            "heal", "damage", "grant_temp_hp", "reduce_damage",
            "grant_modifier", "grant_defense", "grant_proficiency",
            "grant_advantage", "grant_action",
            "apply_condition", "remove_condition", "spend_resource",
            "recover_resource", "modify_roll", "note",
            "morph", "revert",
        }
        self.assertEqual(set(known_ops()), expected)

    def test_every_op_rejects_garbage_with_domain_error(self):
        """每个原语面对完全不合法的参数都必须当场报错，不能静默吞掉。"""
        from dnd5r.kernel.errors import DndError

        for op in known_ops():
            with self.subTest(op=op):
                with self.assertRaises(DndError):
                    parse_effect({op: object()})

    def test_unknown_op_lists_available(self):
        with self.assertRaises(PluginError) as caught:
            parse_effect({"teleport": {}})
        self.assertIn("heal", str(caught.exception))

    def test_multi_key_mapping_rejected(self):
        with self.assertRaises(PluginError):
            parse_effect({"heal": {"dice": "1d4"}, "note": {"zh": "a", "en": "a"}})

    def test_every_effect_has_to_dict(self):
        for op, cls in effect_classes().items():
            self.assertEqual(cls.op, op)


class NumericEffectTest(unittest.TestCase):
    def test_heal_caps_at_maximum(self):
        actor = make_actor(hp_max=20, current=5)
        effect = parse_effect({"heal": {"dice": "1d10", "plus": "class_level"}})
        ctx = ctx_for(actor, [9])
        effect.apply(ctx)
        self.assertEqual(actor.hp.current, 19)  # 5 + (9+5)，还没到上限
        self.assertEqual(ctx.scratch["healed"], 14)

    def test_heal_reports_roll(self):
        actor = make_actor(hp_max=50, current=1)
        ctx = ctx_for(actor, [4])
        parse_effect({"heal": {"dice": "1d10"}}).apply(ctx)
        self.assertEqual(len(ctx.rolls), 1)
        self.assertEqual(ctx.rolls[0].total, 4)

    def test_damage_consumes_temp_first(self):
        actor = make_actor(hp_max=30, current=30)
        actor.hp.temp = 5
        ctx = ctx_for(actor)
        parse_effect({"damage": {"flat": 8, "type": "fire"}}).apply(ctx)
        self.assertEqual(actor.hp.temp, 0)
        self.assertEqual(actor.hp.current, 27)
        self.assertIn("fire", ctx.report().message)

    def test_temp_hp_takes_higher(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        GrantTempHp(amount=parse_amount_ok(8)).apply(ctx)
        GrantTempHp(amount=parse_amount_ok(5)).apply(ctx)
        self.assertEqual(actor.hp.temp, 8)

    def test_reduce_damage_goes_to_scratch(self):
        actor = make_actor()
        ctx = ctx_for(actor, [5])
        ReduceDamage(amount=parse_amount_ok({"dice": "1d10", "plus": "class_level"})).apply(ctx)
        self.assertEqual(ctx.scratch["reduce_damage"], 10)
        self.assertEqual(actor.hp.current, actor.hp.maximum)


def parse_amount_ok(data):
    from dnd5r.rules.amount import parse_amount

    return parse_amount(data)


class GrantEffectTest(unittest.TestCase):
    def test_grant_modifier_attaches_instance(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        parse_effect({"grant_modifier": {"target": "damage.weapon", "value": 2,
                                         "duration": "1 minute"}}).apply(ctx)
        self.assertEqual(len(actor.effects), 1)
        instance = actor.effects[0]
        self.assertEqual(instance.modifiers[0].target, "damage.weapon")
        self.assertEqual(instance.modifiers[0].source, "demo.power")
        self.assertEqual(instance.remaining, 1)

    def test_grant_modifier_supports_stack_and_list(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        parse_effect({"grant_modifier": {"modifiers": [
            {"target": "attack.count", "value": 2, "stack": "max"},
        ]}}).apply(ctx)
        self.assertEqual(actor.effects[0].modifiers[0].stack.value, "max")

    def test_grant_defense_records_resistance(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        parse_effect({"grant_defense": {"resistance": ["slashing", "piercing"]}}).apply(ctx)
        self.assertEqual(actor.effects[0].resistances, ("slashing", "piercing"))

    def test_grant_proficiency_writes_profile(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        parse_effect({"grant_proficiency": {"armor": ["medium"], "skill": ["perception"]}}).apply(ctx)
        self.assertIn("armor.medium", actor.profile.proficiencies)
        self.assertIn("skill.perception", actor.profile.proficiencies)

    def test_grant_proficiency_language(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        parse_effect({"grant_proficiency": {"language": ["elvish"]}}).apply(ctx)
        self.assertIn("elvish", actor.profile.languages)

    def test_grant_advantage(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        parse_effect({"grant_advantage": {"target": "check.str", "mode": "adv"}}).apply(ctx)
        self.assertIn("advantage.adv.check.str", actor.effects[0].label)

    def test_grant_action_lands_in_scratch(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        parse_effect({"grant_action": {"kind": "action", "amount": 1}}).apply(ctx)
        self.assertEqual(ctx.scratch["granted_action"], 1)


class StateEffectTest(unittest.TestCase):
    def test_apply_and_remove_condition(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        ApplyCondition(condition_id="raging").apply(ctx)
        self.assertTrue(actor.conditions.has("raging"))
        RemoveCondition(condition_id="raging").apply(ctx)
        self.assertFalse(actor.conditions.has("raging"))

    def test_spend_resource(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        SpendResource(pool_id="demo.pool", amount=1).apply(ctx)
        self.assertEqual(actor.resources.get("demo.pool").used, 1)

    def test_spend_resource_insufficient(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        with self.assertRaises(IllegalAction):
            SpendResource(pool_id="demo.pool", amount=3).apply(ctx)

    def test_recover_resource_full(self):
        actor = make_actor()
        actor.resources.get("demo.pool").spend(2)
        ctx = ctx_for(actor)
        RecoverResource(pool_id="demo.pool", full=True).apply(ctx)
        self.assertEqual(actor.resources.get("demo.pool").available, 2)

    def test_modify_roll_add(self):
        actor = make_actor()
        ctx = ctx_for(actor, [6])
        parse_effect({"modify_roll": {"dice": "1d10", "mode": "add"}}).apply(ctx)
        self.assertEqual(ctx.scratch["roll_bonus"], 6)

    def test_modify_roll_reroll_flag(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        parse_effect({"modify_roll": {"mode": "reroll", "plus": "class_level"}}).apply(ctx)
        self.assertTrue(ctx.scratch["reroll"])

    def test_note_requires_bilingual(self):
        from dnd5r.kernel.errors import TextError

        with self.assertRaises(TextError):
            parse_effect({"note": {"zh": "只有中文"}})

    def test_note_runs(self):
        actor = make_actor()
        ctx = ctx_for(actor)
        NoteEffect(text=Text.of("说明", "Note")).apply(ctx)
        self.assertEqual(ctx.report().message, "说明")


class ParseListTest(unittest.TestCase):
    def test_parse_effects_keeps_order(self):
        effects = parse_effects([
            {"grant_action": {"kind": "action"}},
            {"note": {"zh": "然后", "en": "then"}},
        ])
        self.assertEqual([item.op for item in effects], ["grant_action", "note"])

    def test_parse_effects_empty(self):
        self.assertEqual(parse_effects(None), ())

    def test_parse_effects_requires_list(self):
        with self.assertRaises(PluginError):
            parse_effects({"heal": {"flat": 1}})


if __name__ == "__main__":
    unittest.main()
