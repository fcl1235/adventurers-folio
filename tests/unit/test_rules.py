# -*- coding: utf-8 -*-
"""规则测试：Modifier 管道、双等级换算、Resolver。"""

import unittest

from dnd5r.kernel.errors import RuleError
from dnd5r.kernel.text import Text
from dnd5r.model.actor import Actor, ActorKind, HpPool
from dnd5r.model.levels import ClassLevel, TotalLevel
from dnd5r.model.profile import Profile
from dnd5r.model.statblock import Abilities, Statblock
from dnd5r.rules.modifiers import (
    Direction, Modifier, Ref, Scope, Stack, resolve, resolve_ref,
)
from dnd5r.rules.progression import (
    CasterKind, caster_level, check_prereq, effective_caster_level,
    proficiency_bonus, slots_from_table,
)
from dnd5r.rules.resolver import RefContext, Resolver


def make_ctx(prof=3):
    return {
        "prof_bonus": prof,
        "total_level": 8,
        "class_level": 5,
        "abilities": Abilities.of(str=16, dex=14, con=12, int=10, wis=12, cha=8),
        "speeds": {"walk": 30},
    }


class ModifierTest(unittest.TestCase):
    def test_add_and_terms(self):
        mods = [
            Modifier(target="ac", value=1, source="item.shield"),
            Modifier(target="ac", value=2, source="class.style"),
        ]
        result = resolve(mods, base=12)
        self.assertEqual(result.total, 15)
        self.assertIn("15 =", result.describe())
        self.assertIn("item.shield", result.sources())

    def test_set_overrides_base(self):
        result = resolve([Modifier(target="ac", value=13, stack=Stack.SET, source="class.unarmored")], base=11)
        self.assertEqual(result.total, 13)

    def test_conflicting_sets_raise(self):
        mods = [
            Modifier(target="ac", value=13, stack=Stack.SET, source="a"),
            Modifier(target="ac", value=15, stack=Stack.SET, source="b"),
        ]
        with self.assertRaises(RuleError):
            resolve(mods, base=10)

    def test_max_does_not_stack(self):
        mods = [
            Modifier(target="attack.count", value=2, stack=Stack.MAX, source="class.extra"),
            Modifier(target="attack.count", value=3, stack=Stack.MAX, source="class.more"),
        ]
        self.assertEqual(resolve(mods, base=1).total, 3)

    def test_ref_values(self):
        ctx = make_ctx(prof=5)
        self.assertEqual(resolve_ref(Ref("prof/2"), ctx), 2)
        self.assertEqual(resolve_ref(Ref("prof*2"), ctx), 10)
        self.assertEqual(resolve_ref(Ref("ability.str"), ctx), 3)
        self.assertEqual(resolve_ref(Ref("speed.walk"), ctx), 30)
        self.assertEqual(resolve_ref(Ref("total_level"), ctx), 8)

    def test_ref_without_context_raises(self):
        with self.assertRaises(RuleError):
            resolve([Modifier(target="save.wis", value=Ref("prof"), source="x")], base=0)

    def test_when_filters_modifier(self):
        mods = [Modifier(target="speed.walk", value=10, source="fast", when={"raging": True})]
        self.assertEqual(resolve(mods, base=30, ctx={"raging": False}).total, 30)
        self.assertEqual(resolve(mods, base=30, ctx={"raging": True}).total, 40)

    def test_scope_and_direction_kept(self):
        mod = Modifier(target="attack.against", value=1, scope=Scope.ATTACKERS,
                       direction=Direction.TAKEN, source="reckless")
        self.assertIs(mod.scope, Scope.ATTACKERS)
        self.assertIs(mod.direction, Direction.TAKEN)


class ProgressionTest(unittest.TestCase):
    def test_proficiency_table(self):
        expected = {1: 2, 4: 2, 5: 3, 8: 3, 9: 4, 12: 4, 13: 5, 16: 5, 17: 6, 20: 6}
        for level, bonus in expected.items():
            self.assertEqual(proficiency_bonus(TotalLevel(level)), bonus, level)

    def test_caster_level_mixes(self):
        entries = [
            (ClassLevel(6), CasterKind.HALF),
            (ClassLevel(5), CasterKind.FULL),
            (ClassLevel(6), CasterKind.THIRD),
            (ClassLevel(2), CasterKind.PACT),
        ]
        # 3 + 5 + 2 = 10，契约等级不计入
        self.assertEqual(caster_level(entries), 10)

    def test_effective_caster_level_keeps_pact_separate(self):
        profile = Profile.single("demo.alpha", 6).add_class("demo.beta", 2)
        kinds = {"demo.alpha": CasterKind.HALF, "demo.beta": CasterKind.PACT}
        combined, pact = effective_caster_level(profile, kinds)
        self.assertEqual(combined, 3)
        self.assertEqual(pact, 2)

    def test_slots_from_table(self):
        table = {3: {1: 4, 2: 2}, 4: {1: 4, 2: 3}}
        self.assertEqual(slots_from_table(3, table), {1: 4, 2: 2})
        self.assertEqual(slots_from_table(0, table), {})

    def test_prereq(self):
        abilities = Abilities.of(str=13, dex=10, con=14, int=8, wis=10, cha=12)
        self.assertEqual(check_prereq(abilities, {"str": 13}), [])
        self.assertEqual(len(check_prereq(abilities, {"int": 13})), 1)


class ResolverTest(unittest.TestCase):
    def setUp(self):
        self.actor = Actor(
            id="pc.hero",
            kind=ActorKind.PC,
            statblock=Statblock(
                name=Text.of("冒险者", "Adventurer"),
                abilities=Abilities.of(str=16, dex=14, con=12, int=10, wis=12, cha=8),
            ),
            hp=HpPool(maximum=20),
        )
        self.resolver = Resolver(RefContext(
            prof_bonus=3,
            total_level=TotalLevel(5),
            class_level=ClassLevel(5),
            abilities=self.actor.statblock.abilities,
            speeds={"walk": 30},
        ))

    def test_ac_base_is_10_plus_dex(self):
        self.assertEqual(self.resolver.armor_class(self.actor).total, 12)

    def test_ac_with_modifier_keeps_breakdown(self):
        mods = [Modifier(target="ac", value=1, source="item.leather")]
        result = self.resolver.armor_class(self.actor, mods)
        self.assertEqual(result.total, 13)
        self.assertIn("item.leather", result.describe())

    def test_save_and_attack(self):
        self.assertEqual(self.resolver.saving_throw(self.actor, "wis").total, 1)
        self.assertEqual(self.resolver.saving_throw(self.actor, "wis", proficient=True).total, 4)
        self.assertEqual(self.resolver.attack_bonus(self.actor).total, 6)

    def test_spell_dc(self):
        self.assertEqual(self.resolver.spell_dc(self.actor, "int").total, 11)

    def test_expertise_doubles_prof(self):
        plain = self.resolver.ability_check(self.actor, "dex", proficient=True).total
        expert = self.resolver.ability_check(self.actor, "dex", expertise=True).total
        self.assertEqual(plain, 2 + 3)
        self.assertEqual(expert, 2 + 6)

    def test_passive_score(self):
        self.assertEqual(self.resolver.passive_score(self.actor, "wis"), 11)


if __name__ == "__main__":
    unittest.main()
