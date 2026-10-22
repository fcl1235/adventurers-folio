# -*- coding: utf-8 -*-
"""Power 与动作经济：四种 kind 的区别、支付、等级过滤、叠层。"""

import unittest

from dnd5r.kernel.errors import IllegalAction, PluginError, RuleError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.kernel.text import Text
from dnd5r.model.actor import Actor, ActorKind, HpPool
from dnd5r.model.profile import Profile
from dnd5r.model.resources import Pool, PoolKind, Refresh
from dnd5r.model.statblock import Abilities, Statblock
from dnd5r.rules.actioneconomy import ActionEconomy, ActionType
from dnd5r.rules.effects import EffectContext
from dnd5r.rules.powers import (
    Cost,
    Phase,
    Power,
    PowerBook,
    PowerKind,
    apply_patch,
    can_use,
    parse_power,
    use_power,
)

SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
TEXT = {"zh": "测试", "en": "Test"}


def actor_with_pool(level=3, capacity=2, hp_max=30, current=None) -> Actor:
    stat = Statblock(name=Text.of("测试者", "Tester"), abilities=Abilities.of(**SCORES))
    actor = Actor(
        id="pc.test", kind=ActorKind.PC, statblock=stat,
        hp=HpPool(maximum=hp_max, current=current),
        profile=Profile.single("demo.class_a", level),
    )
    actor.resources.add(Pool(id="demo.pool", kind=PoolKind.CHARGE,
                             capacity=capacity, refresh=Refresh.LONG_REST))
    return actor


def ctx_for(actor, values=(), source="demo.power"):
    return EffectContext(
        actor=actor, rng=ScriptedRng(list(values)), prof_bonus=2,
        total_level=actor.profile.total, class_level=actor.profile.classes[0].class_level,
        source=source,
    )


def simple_power(overrides=None, **kwargs) -> Power:
    data = {
        "id": "demo.power.heal",
        "name": TEXT,
        "text": TEXT,
        "level": 1,
        "kind": "activated",
        "cost": {"action": "bonus", "resource": "demo.pool"},
        "effects": [{"heal": {"dice": "1d10"}}],
    }
    data.update(overrides or {})
    data.update(kwargs)
    return parse_power(data, owner="demo.class_a", source="test")


class PowerParseTest(unittest.TestCase):
    def test_basic(self):
        power = simple_power()
        self.assertEqual(power.kind, PowerKind.ACTIVATED)
        self.assertEqual(power.cost.action, ActionType.BONUS)
        self.assertTrue(power.is_button)
        self.assertEqual(power.subtitle(), "附赠动作 · pool ×1")

    def test_triggered_requires_phase(self):
        with self.assertRaises(RuleError):
            simple_power(kind="triggered", phase=None, cost=None)

    def test_passive_requires_effects_or_augments(self):
        with self.assertRaises(RuleError):
            simple_power(kind="passive", cost=None, effects=[])

    def test_unknown_kind(self):
        with self.assertRaises(PluginError):
            simple_power(kind="reactionary")

    def test_unknown_phase(self):
        with self.assertRaises(PluginError):
            simple_power(kind="triggered", phase="on_sneeze", cost=None)

    def test_missing_text(self):
        with self.assertRaises(PluginError):
            parse_power({"id": "demo.power.x", "name": TEXT})

    def test_bilingual_required(self):
        from dnd5r.kernel.errors import TextError

        with self.assertRaises(TextError):
            parse_power({"id": "demo.power.x", "name": {"zh": "只有中文"}, "text": TEXT})

    def test_cost_rejects_unknown_key(self):
        with self.assertRaises(PluginError):
            Cost.parse({"action": "bonus", "spell_slot": 1})

    def test_cost_from_string(self):
        self.assertEqual(Cost.parse("reaction").action, ActionType.REACTION)


class ActionEconomyTest(unittest.TestCase):
    def test_default_turn(self):
        economy = ActionEconomy()
        self.assertTrue(economy.can_pay(ActionType.ACTION))
        self.assertTrue(economy.can_pay(ActionType.FREE))

    def test_pay_and_exhaust(self):
        economy = ActionEconomy()
        economy.pay(ActionType.ACTION)
        self.assertFalse(economy.can_pay(ActionType.ACTION))
        with self.assertRaises(IllegalAction):
            economy.pay(ActionType.ACTION)

    def test_free_never_consumes(self):
        economy = ActionEconomy(action=0)
        economy.pay(ActionType.FREE)
        self.assertEqual(economy.action, 0)

    def test_turn_and_round_reset(self):
        economy = ActionEconomy()
        economy.pay(ActionType.ACTION)
        economy.pay(ActionType.REACTION)
        economy.start_turn()
        self.assertEqual(economy.action, 1)
        self.assertEqual(economy.reaction, 0)  # 反应要等下一轮
        economy.start_round()
        self.assertEqual(economy.reaction, 1)

    def test_grant_extra_action(self):
        economy = ActionEconomy()
        economy.pay(ActionType.ACTION)
        economy.grant(ActionType.ACTION)
        self.assertEqual(economy.action, 1)

    def test_end_turn_clears_but_keeps_reaction(self):
        """反应是一轮一次，不随自己回合结束作废 —— 这条规则写错会让借机攻击白给。"""
        economy = ActionEconomy()
        economy.end_turn()
        self.assertEqual(economy.action, 0)
        self.assertEqual(economy.bonus, 0)
        self.assertEqual(economy.reaction, 1)
        self.assertEqual(economy.describe(), "反应×1")


class PowerUseTest(unittest.TestCase):
    def test_use_spends_action_and_resource(self):
        actor = actor_with_pool(current=1)
        context = ctx_for(actor, [7])
        economy = ActionEconomy()
        report = use_power(simple_power(), context, economy)
        self.assertTrue(report.ok)
        self.assertEqual(actor.resources.get("demo.pool").used, 1)
        self.assertEqual(economy.action, 1)
        self.assertEqual(economy.bonus, 0)
        self.assertEqual(actor.hp.current, 8)  # 1 + 7

    def test_cannot_use_without_resource(self):
        actor = actor_with_pool(capacity=0)
        with self.assertRaises(IllegalAction):
            use_power(simple_power(), ctx_for(actor), ActionEconomy())

    def test_cannot_use_without_action(self):
        actor = actor_with_pool()
        economy = ActionEconomy(bonus=0)
        with self.assertRaises(IllegalAction):
            use_power(simple_power(), ctx_for(actor), economy)

    def test_can_use_returns_reasons(self):
        actor = actor_with_pool(capacity=0)
        reasons = can_use(simple_power(), ctx_for(actor), ActionEconomy())
        self.assertTrue(any("剩余" in item for item in reasons))

    def test_passive_has_no_button(self):
        power = simple_power(kind="passive", cost=None,
                             effects=[{"note": TEXT}])
        self.assertFalse(power.is_button)
        self.assertTrue(any("不是主动能力" in item
                            for item in can_use(power, ctx_for(actor_with_pool()), None)))

    def test_when_condition_blocks(self):
        actor = actor_with_pool()
        power = parse_power({
            "id": "demo.power.cond", "name": TEXT, "text": TEXT, "level": 1,
            "kind": "activated", "when": {"hp_lte": 5},
            "effects": [{"heal": {"flat": 1}}],
        })
        with self.assertRaises(IllegalAction):
            use_power(power, ctx_for(actor), ActionEconomy())


class PowerBookTest(unittest.TestCase):
    def book(self) -> PowerBook:
        book = PowerBook()
        book.add(simple_power({"id": "demo.power.a", "level": 1}))
        book.add(simple_power({"id": "demo.power.b", "level": 5}))
        book.add(simple_power({"id": "demo.power.c", "level": 9}))
        return book

    def test_level_filter(self):
        book = self.book()
        from dnd5r.model.levels import ClassLevel

        self.assertEqual([p.id for p in book.for_class("demo.class_a", ClassLevel(4))],
                         ["demo.power.a"])
        self.assertEqual(len(book.for_class("demo.class_a", ClassLevel(9))), 3)

    def test_duplicate_rejected(self):
        book = self.book()
        with self.assertRaises(PluginError):
            book.add(simple_power({"id": "demo.power.a"}))

    def test_augments_patch_cost(self):
        book = PowerBook()
        base = book.add(simple_power({"id": "demo.power.base", "level": 1,
                                      "cost": {"action": "bonus", "resource": "demo.pool"}}))
        upgrade = book.add(parse_power({
            "id": "demo.power.upgrade", "name": TEXT, "text": TEXT, "level": 3,
            "kind": "passive", "augments": ["demo.power.base"],
            "patch": {"cost": {"action": "free", "resource": "demo.pool"}},
        }))
        book.validate_augments()
        self.assertEqual(apply_patch(base, upgrade).cost.action, ActionType.FREE)

    def test_augments_unknown_field(self):
        book = PowerBook()
        base = book.add(simple_power({"id": "demo.power.base"}))
        upgrade = book.add(parse_power({
            "id": "demo.power.bad", "name": TEXT, "text": TEXT, "level": 3,
            "kind": "passive", "augments": ["demo.power.base"],
            "patch": {"damage": "2d10"},
        }))
        with self.assertRaises(PluginError):
            book.validate_augments()
        with self.assertRaises(PluginError):
            apply_patch(base, upgrade)

    def test_augments_missing_target(self):
        book = PowerBook()
        book.add(parse_power({
            "id": "demo.power.orphan", "name": TEXT, "text": TEXT, "level": 3,
            "kind": "passive", "augments": ["demo.power.nope"], "patch": {"target": "self"},
        }))
        with self.assertRaises(PluginError):
            book.validate_augments()

    def test_augments_can_replace_effects(self):
        """按 op 整条替换；目标没有这类效果要报错，不能静默无视。"""
        base = simple_power({"id": "demo.power.base", "level": 1})   # 自带 heal
        upgrade = parse_power({
            "id": "demo.power.up", "name": TEXT, "text": TEXT, "level": 3,
            "kind": "passive", "augments": ["demo.power.base"],
            "patch": {"effects": {"heal": {"dice": "2d4"}}},
        })
        patched = apply_patch(base, upgrade)
        self.assertEqual([effect.op for effect in patched.effects], ["heal"])
        self.assertEqual(str(patched.effects[0].amount.dice), "2d4")

        wrong = parse_power({
            "id": "demo.power.wrong", "name": TEXT, "text": TEXT, "level": 3,
            "kind": "passive", "augments": ["demo.power.base"],
            "patch": {"effects": {"note": {"zh": "a", "en": "a"}}},
        })
        with self.assertRaises(PluginError):
            apply_patch(base, wrong)

    def test_stats(self):
        book = self.book()
        self.assertEqual(book.stats()["activated"], 3)


if __name__ == "__main__":
    unittest.main()
