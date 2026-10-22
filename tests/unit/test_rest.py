# -*- coding: utf-8 -*-
"""休息：短休的「回 1 次」与长休的「全回」，两条最容易写错的规则。"""

import unittest

from dnd5r.kernel.rng import ScriptedRng
from dnd5r.kernel.text import Text
from dnd5r.model.actor import Actor, ActorKind, HpPool
from dnd5r.model.effect_instance import ActiveEffect, Duration, DurationKind
from dnd5r.model.profile import Profile
from dnd5r.model.resources import Pool, PoolKind, Refresh
from dnd5r.model.statblock import Abilities, Statblock
from dnd5r.rules.rest import hit_dice_left, long_rest, short_rest

SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


def build() -> Actor:
    stat = Statblock(name=Text.of("测试者", "Tester"), abilities=Abilities.of(**SCORES))
    actor = Actor(
        id="pc.test", kind=ActorKind.PC, statblock=stat,
        hp=HpPool(maximum=20, current=20),
        profile=Profile.single("demo.class_a", 5),
    )
    actor.resources.add(Pool(id="demo.short", kind=PoolKind.CHARGE, capacity=1,
                             refresh=Refresh.SHORT_REST))
    actor.resources.add(Pool(id="demo.long", kind=PoolKind.CHARGE, capacity=3,
                             refresh=Refresh.LONG_REST))
    actor.resources.add(Pool(id="demo.partial", kind=PoolKind.CHARGE, capacity=2,
                             refresh=Refresh.LONG_REST, recover_on_short_rest=1))
    actor.resources.add(Pool(id="demo.none", kind=PoolKind.POINT, capacity=2,
                             refresh=Refresh.NONE))
    actor.resources.add(Pool(id="hit_dice.demo.class_a", kind=PoolKind.DICE, capacity=5,
                             refresh=Refresh.LONG_REST, owner_class="demo.class_a"))
    return actor


HIT_DIES = {"demo.class_a": 10}


class ShortRestTest(unittest.TestCase):
    def test_recovers_only_one_use(self):
        actor = build()
        actor.resources.spend("demo.partial", 2)
        result = short_rest(actor, HIT_DIES)
        self.assertEqual(actor.resources.get("demo.partial").available, 1)
        self.assertIn("partial +1", result.summary)

    def test_short_rest_pool_refills(self):
        actor = build()
        actor.resources.spend("demo.short", 1)
        short_rest(actor, HIT_DIES)
        self.assertEqual(actor.resources.get("demo.short").available, 1)

    def test_long_rest_pool_untouched(self):
        actor = build()
        actor.resources.spend("demo.long", 2)
        short_rest(actor, HIT_DIES)
        self.assertEqual(actor.resources.get("demo.long").available, 1)

    def test_none_pool_never_recovers(self):
        actor = build()
        actor.resources.spend("demo.none", 2)
        short_rest(actor, HIT_DIES)
        long_rest(actor)
        self.assertEqual(actor.resources.get("demo.none").available, 0)

    def test_spend_hit_dice_heals(self):
        actor = build()
        actor.hp.current = 5
        result = short_rest(actor, HIT_DIES, spend=2, rng=ScriptedRng([10, 1]))
        # 10+2 与 1+2（下限保护后仍是 3）
        self.assertEqual(result.dice_spent, 2)
        self.assertEqual(actor.hp.current, 5 + 12 + 3)
        self.assertEqual(hit_dice_left(actor), 3)

    def test_average_when_no_rng(self):
        actor = build()
        actor.hp.current = 5
        short_rest(actor, HIT_DIES, spend=1)
        self.assertEqual(actor.hp.current, 5 + 8)  # 10//2+1 + 2

    def test_no_more_dice_than_available(self):
        actor = build()
        actor.hp.current = 1
        result = short_rest(actor, HIT_DIES, spend=99)
        self.assertEqual(result.dice_spent, 5)
        self.assertEqual(hit_dice_left(actor), 0)

    def test_heal_does_not_exceed_max(self):
        actor = build()
        actor.hp.current = 18
        short_rest(actor, HIT_DIES, spend=3)
        self.assertEqual(actor.hp.current, 20)

    def test_short_effects_expire(self):
        actor = build()
        actor.effects.append(ActiveEffect(id="x", duration=Duration(DurationKind.SHORT_REST)))
        actor.effects.append(ActiveEffect(id="y", duration=Duration(DurationKind.LONG_REST)))
        result = short_rest(actor, HIT_DIES)
        self.assertIn("x", result.expired)
        self.assertEqual([item.id for item in actor.effects], ["y"])

    def test_permanent_effect_survives(self):
        actor = build()
        actor.effects.append(ActiveEffect(id="perm", duration=Duration(DurationKind.PERMANENT)))
        short_rest(actor, HIT_DIES)
        long_rest(actor)
        self.assertEqual([item.id for item in actor.effects], ["perm"])

    def test_negative_spend_rejected(self):
        from dnd5r.kernel.errors import RuleError

        with self.assertRaises(RuleError):
            short_rest(build(), HIT_DIES, spend=-1)


class LongRestTest(unittest.TestCase):
    def test_restores_everything(self):
        actor = build()
        actor.hp.current = 3
        actor.hp.temp = 9
        actor.resources.spend("demo.long", 3)
        actor.resources.spend("hit_dice.demo.class_a", 4)
        result = long_rest(actor)
        self.assertEqual(actor.hp.current, 20)
        self.assertEqual(actor.hp.temp, 0)
        self.assertEqual(actor.resources.get("demo.long").available, 3)
        self.assertEqual(hit_dice_left(actor), 5)
        self.assertIn("生命骰全回", result.summary)

    def test_hit_dice_reported_once(self):
        """生命骰不该同时出现在「生命骰全回」和「资源回满」里。"""
        actor = build()
        actor.resources.spend("hit_dice.demo.class_a", 1)
        result = long_rest(actor)
        self.assertEqual(result.summary.count("生命骰全回"), 1)
        self.assertNotIn("资源回满：class_a", result.summary)


if __name__ == "__main__":
    unittest.main()
