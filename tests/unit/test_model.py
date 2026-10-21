# -*- coding: utf-8 -*-
"""模型测试：属性、双等级、池、HP、变形压栈。"""

import unittest

from dnd5r.kernel.errors import IllegalAction, RuleError
from dnd5r.kernel.text import Text
from dnd5r.model.actor import Actor, ActorKind, HpPool
from dnd5r.model.profile import ClassEntry, Profile
from dnd5r.model.resources import Pool, PoolKind, Refresh, ResourcePool
from dnd5r.model.statblock import Abilities, Statblock, ability_mod


class AbilitiesTest(unittest.TestCase):
    def test_mod_floor(self):
        self.assertEqual(ability_mod(10), 0)
        self.assertEqual(ability_mod(11), 0)
        self.assertEqual(ability_mod(8), -1)
        self.assertEqual(ability_mod(15), 2)

    def test_requires_all_six(self):
        with self.assertRaises(RuleError):
            Abilities(scores={"str": 10})

    def test_score_range(self):
        with self.assertRaises(RuleError):
            Abilities.of(str=31, dex=10, con=10, int=10, wis=10, cha=10)

    def test_replace_is_copy(self):
        base = Abilities.of(str=10, dex=10, con=10, int=10, wis=10, cha=10)
        other = base.replace(str=18)
        self.assertEqual(base.score("str"), 10)
        self.assertEqual(other.score("str"), 18)


class ProfileTest(unittest.TestCase):
    def test_single_class_total(self):
        profile = Profile.single("demo.class_a", 5)
        self.assertEqual(int(profile.total), 5)
        self.assertFalse(profile.is_multiclass)
        self.assertEqual(int(profile.class_level("demo.class_a")), 5)

    def test_multiclass_total_is_derived(self):
        profile = Profile.single("demo.class_a", 5).add_class("demo.class_b", 3)
        self.assertEqual(int(profile.total), 8)
        self.assertTrue(profile.is_multiclass)
        self.assertEqual(int(profile.class_level("demo.class_b")), 3)

    def test_absent_class_is_zero(self):
        profile = Profile.single("demo.class_a", 5)
        self.assertEqual(int(profile.class_level("demo.other")), 0)
        self.assertFalse(profile.has_class("demo.other"))

    def test_duplicate_class_rejected(self):
        with self.assertRaises(RuleError):
            Profile(classes=(
                ClassEntry.make("demo.class_a", 1),
                ClassEntry.make("demo.class_a", 2),
            ))

    def test_expertise_must_be_subset(self):
        with self.assertRaises(RuleError):
            Profile(classes=(ClassEntry.make("demo.class_a", 1),), expertise=frozenset({"stealth"}))

    def test_dict_round_trip_has_no_total_field(self):
        profile = Profile.single("demo.class_a", 4).add_class("demo.class_b", 2)
        data = profile.to_dict()
        self.assertNotIn("level", data)
        self.assertEqual(data["classes"][1]["class_level"], 2)
        self.assertEqual(Profile.from_dict(data), profile)


class ResourceTest(unittest.TestCase):
    def test_spend_and_insufficient(self):
        pool = Pool(id="demo.pool.ki", kind=PoolKind.POINT, capacity=3, refresh=Refresh.SHORT_REST)
        pool.spend(2)
        self.assertEqual(pool.available, 1)
        with self.assertRaises(IllegalAction):
            pool.spend(2)

    def test_recover_clamps(self):
        pool = Pool(id="p", kind=PoolKind.CHARGE, capacity=2, used=2)
        pool.recover(5)
        self.assertEqual(pool.used, 0)

    def test_refill_by_refresh(self):
        pools = ResourcePool()
        pools.add(Pool(id="a", kind=PoolKind.CHARGE, capacity=2, used=1, refresh=Refresh.SHORT_REST))
        pools.add(Pool(id="b", kind=PoolKind.CHARGE, capacity=2, used=1, refresh=Refresh.LONG_REST))
        touched = pools.refill(Refresh.SHORT_REST)
        self.assertEqual([p.id for p in touched], ["a"])
        self.assertEqual(pools.get("b").used, 1)

    def test_zero_resources_is_legal(self):
        self.assertEqual(ResourcePool().ids(), ())


class HpAndActorTest(unittest.TestCase):
    def make_actor(self, actor_id="pc.hero", max_hp=20):
        return Actor(
            id=actor_id,
            kind=ActorKind.PC,
            statblock=Statblock(name=Text.of("本体", "Body"), abilities=Abilities.of(
                str=10, dex=12, con=14, int=10, wis=10, cha=10)),
            hp=HpPool(maximum=max_hp),
        )

    def test_temp_hp_absorbs_first(self):
        hp = HpPool(maximum=20)
        hp.grant_temp(5)
        hp.damage(8)
        self.assertEqual(hp.temp, 0)
        self.assertEqual(hp.current, 17)

    def test_grant_temp_takes_max(self):
        hp = HpPool(maximum=20)
        hp.grant_temp(5)
        hp.grant_temp(3)
        self.assertEqual(hp.temp, 5)

    def test_heal_clamps(self):
        hp = HpPool(maximum=20, current=18)
        self.assertEqual(hp.heal(10), 2)
        self.assertEqual(hp.current, 20)

    def test_morph_layer_stack(self):
        body = self.make_actor()
        form = Actor(
            id="pc.form",
            kind=ActorKind.FORM,
            statblock=Statblock(name=Text.of("狼", "Wolf"), abilities=Abilities.of(
                str=14, dex=15, con=12, int=10, wis=10, cha=10), speeds={"walk": 40}),
            hp=HpPool(maximum=20),
        )
        top = body.morph_into(form)
        self.assertIs(top.top(), form)
        self.assertIs(body.top(), form)
        self.assertIs(top.root(), body)
        self.assertTrue(top.is_morphed)
        self.assertEqual(top.statblock.speed("walk"), 40)
        self.assertEqual(body.statblock.speed("walk"), 30)

        restored = top.unmorph()
        self.assertIs(restored, body)
        self.assertIsNone(body.above)
        self.assertIs(body.top(), body)

    def test_double_morph_rejected(self):
        body = self.make_actor()
        form = self.make_actor("pc.form")
        body.morph_into(form)
        with self.assertRaises(RuleError):
            body.morph_into(self.make_actor("pc.form2"))


if __name__ == "__main__":
    unittest.main()
