# -*- coding: utf-8 -*-
"""P8e 验收：按法术计次的资源池 + 免法术位施放（G16）。

原文有两句很容易被写错的话：

  1. 「你可以不消耗法术位的方式**各**施放这两道法术一次」——
     **各**一次，不是「一共两次」。所以不能建一个 capacity 2 的池：
     那样玩家能连放两次迷踪步，而祝福术一次都用不掉。
  2. 「施法属性为你以此专长**提升**的属性」——
     所以战士拿了妖精触碰，迷踪步照样按魅力算 DC；用职业的施法属性算
     会得到一个规则里不存在的数。

这两条都不是「差不多对」的事：第一条差一次施放，第二条差 2–4 点 DC。
所以下面的断言都带反证 —— 证明「迷踪步扣了次数」还不够，
要同时证明「祝福术的次数没被动过」。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import parse_resource
from dnd5r.kernel.errors import PluginError, RuleError
from dnd5r.model.resources import PoolKind, Refresh

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 12, "dex": 14, "con": 14, "int": 16, "wis": 12, "cha": 16}

FIGHTER = "dnd2024.class.fighter"
WIZARD = "dnd2024.class.wizard"
FEY = "dnd2024.feat.fey_touched"
SHADOW = "dnd2024.feat.shadow_touched"
TELEPATHIC = "dnd2024.feat.telepathic"
MI_WIZARD = "dnd2024.feat.magic_initiate_wizard"

MISTY = "dnd2024.spell.misty_step"
BLESS = "dnd2024.spell.bless"
SHIELD = "dnd2024.spell.shield"
MAGIC_MISSILE = "dnd2024.spell.magic_missile"
FIRE_BOLT = "dnd2024.spell.fire_bolt"
LIGHT = "dnd2024.spell.light"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def actor(self, class_id=FIGHTER, level=4, feats=(), choices=None, scores=None):
        return api.new_character(self.bundle, class_id, level, scores or SCORES,
                                 name_zh="测试", name_en="Test",
                                 feats=tuple(feats), choices=choices or {})

    def fey(self, class_id=FIGHTER, spell=BLESS, ability="cha"):
        return self.actor(class_id, 4, [FEY], {
            FEY + ".boost": (ability,),
            FEY + ".spell": (spell,),
        })

    def bound(self, actor):
        """角色身上**绑了法术**的池：{spell id: pool}。"""
        return {pool.spell: pool for pool in actor.root().resources.pools.values()
                if pool.spell}


# --- 一、池的形状 -------------------------------------------------------
class PerSpellPoolTest(Base):
    def test_two_spells_two_pools(self):
        pools = self.bound(self.fey())
        self.assertEqual(set(pools), {MISTY, BLESS})
        for spell_id, pool in pools.items():
            self.assertEqual(pool.capacity, 1, "%s 不是 1 次" % spell_id)
            self.assertEqual(pool.refresh, Refresh.LONG_REST)
            self.assertIn(spell_id.rsplit(".", 1)[-1], pool.id)

    def test_pool_label_is_the_spell_name(self):
        """两行「免费施放次数」都写专长名的话，玩家分不出哪行是哪道法术。"""
        pools = self.bound(self.fey())
        self.assertEqual(pools[MISTY].label.zh, "迷踪步")
        self.assertEqual(pools[BLESS].label.zh, "祝福术")

    def test_using_one_does_not_touch_the_other(self):
        """「各一次」的核心断言：迷踪步用掉，祝福术还剩一次。"""
        actor = self.fey()
        api.roll_spell(actor, self.bundle, MISTY, free=True, apply=True, seed=1)
        pools = self.bound(actor)
        self.assertEqual(pools[MISTY].available, 0)
        self.assertEqual(pools[BLESS].available, 1)

    def test_cantrips_get_no_pool(self):
        """戏法本来就能无限放，给它一个「1 次」的池等于凭空加了个限制。"""
        actor = self.actor(FIGHTER, 4, [MI_WIZARD], {
            MI_WIZARD + ".spell": (SHIELD,),
            MI_WIZARD + ".cantrips": (FIRE_BOLT, LIGHT),
            MI_WIZARD + ".casting_ability": ("int",),
        })
        self.assertEqual(set(self.bound(actor)), {SHIELD})

    def test_pending_choice_builds_only_the_fixed_pool(self):
        """还没选那道法术 —— 就没有它的池，而不是一个永远用不掉的 1 次。"""
        actor = self.actor(FIGHTER, 4, [FEY], {FEY + ".boost": ("cha",)})
        self.assertEqual(set(self.bound(actor)), {MISTY})

    def test_long_rest_refills(self):
        actor = self.fey()
        api.roll_spell(actor, self.bundle, MISTY, free=True, apply=True, seed=1)
        self.assertEqual(self.bound(actor)[MISTY].available, 0)
        actor.root().resources.refill_all()
        self.assertEqual(self.bound(actor)[MISTY].available, 1)

    def test_repeatable_feat_binds_its_own_spells(self):
        """魔法入门登记两次：两道不同的法术各一个池，用掉一道不影响另一道。"""
        actor = self.actor(FIGHTER, 4, [MI_WIZARD, MI_WIZARD], {
            MI_WIZARD + ".spell": (SHIELD,),
            MI_WIZARD + "#1.spell": (MAGIC_MISSILE,),
            MI_WIZARD + ".cantrips": (FIRE_BOLT, LIGHT),
            MI_WIZARD + "#1.cantrips": (FIRE_BOLT, LIGHT),
            MI_WIZARD + ".casting_ability": ("int",),
            MI_WIZARD + "#1.casting_ability": ("int",),
        })
        pools = self.bound(actor)
        self.assertEqual(set(pools), {SHIELD, MAGIC_MISSILE})
        api.roll_spell(actor, self.bundle, SHIELD, free=True, apply=True, seed=1)
        self.assertEqual(self.bound(actor)[SHIELD].available, 0)
        self.assertEqual(self.bound(actor)[MAGIC_MISSILE].available, 1)


# --- 二、免法术位施放 ---------------------------------------------------
class FreeCastTest(Base):
    def test_free_cast_spends_exactly_one(self):
        actor = self.fey()
        report = api.roll_spell(actor, self.bundle, MISTY, free=True, apply=True, seed=1)
        self.assertEqual(report["free"]["spent"], 1)
        self.assertEqual(report["free"]["left"], 0)
        self.assertEqual(report["free"]["capacity"], 1)

    def test_preview_does_not_spend(self):
        """`apply=False` 只算不记账 —— 与伤害同一条规矩。"""
        actor = self.fey()
        report = api.roll_spell(actor, self.bundle, MISTY, free=True, seed=1)
        self.assertEqual(report["free"]["spent"], 0)
        self.assertEqual(report["free"]["left"], 1)
        self.assertEqual(self.bound(actor)[MISTY].available, 1)

    def test_second_free_cast_raises(self):
        actor = self.fey()
        api.roll_spell(actor, self.bundle, MISTY, free=True, apply=True, seed=1)
        with self.assertRaises(RuleError):
            api.roll_spell(actor, self.bundle, MISTY, free=True, seed=1)

    def test_pool_only_pays_for_its_own_spell(self):
        """只有迷踪步的池时，不能用它去放祝福术。"""
        actor = self.actor(FIGHTER, 4, [FEY], {FEY + ".boost": ("cha",)})
        with self.assertRaises(RuleError):
            api.roll_spell(actor, self.bundle, BLESS, free=True, seed=1)

    def test_free_cast_rejects_slot_and_class(self):
        actor = self.fey()
        with self.assertRaises(RuleError):
            api.roll_spell(actor, self.bundle, MISTY, 3, free=True, seed=1)
        with self.assertRaises(RuleError):
            api.roll_spell(actor, self.bundle, MISTY, free=True, class_id=FIGHTER,
                           seed=1)

    def test_free_cast_keeps_the_spell_s_own_level(self):
        """免位施放按法术自身环级结算 —— 迷踪步是 2 环，不能因为「免费」变成 1 环。"""
        report = api.roll_spell(self.fey(), self.bundle, MISTY, free=True, seed=1)
        self.assertEqual(report["slot"], 2)

    def test_fighter_casts_with_the_feat_ability(self):
        """战士没有施法属性；妖精触碰把魅力 +1 了，就用魅力算 DC。

        CHA 16 +1 = 17（+3），熟练 +2 → DC 13。
        """
        report = api.roll_spell(self.fey(), self.bundle, MISTY, free=True, seed=1)
        self.assertEqual(report["casting"]["ability"], "cha")
        self.assertEqual(report["casting"]["dc"], 13)
        self.assertEqual(report["casting"]["source"], FEY)
        self.assertEqual(report["casting"]["class"], "")

    def test_wizard_feat_cast_differs_from_class_cast(self):
        """同一个法师放迷踪步：职业路子用智力，专长路子用被提升的魅力。

        两条路都合法，但**不是同一个数** —— 所以不能只算一条。
        """
        scores = dict(SCORES, int=16, cha=12)      # 智力 +3、魅力 +1（专长 +1 后）
        actor = self.actor(WIZARD, 4, [FEY], {
            FEY + ".boost": ("cha",),
            FEY + ".spell": (BLESS,),
        }, scores=scores)
        by_class = api.casting_for(self.bundle, actor, self.bundle.spell(MISTY))
        by_feat = api.casting_for(self.bundle, actor, self.bundle.spell(MISTY),
                                  source=FEY)
        self.assertEqual(by_class.ability, "int")
        self.assertEqual(by_feat.ability, "cha")
        self.assertEqual(by_class.dc, 13)
        self.assertEqual(by_feat.dc, 11)
        # 免位施放走的是专长那条
        free = api.roll_spell(actor, self.bundle, MISTY, free=True, seed=1)
        self.assertEqual(free["casting"]["dc"], 11)

    def test_magic_initiate_needs_the_ability_choice(self):
        """魔法入门的施法属性是**选**的：没选就不能猜一个。"""
        actor = self.actor(FIGHTER, 4, [MI_WIZARD], {
            MI_WIZARD + ".spell": (SHIELD,),
            MI_WIZARD + ".cantrips": (FIRE_BOLT, LIGHT),
        })
        with self.assertRaises(RuleError) as caught:
            api.roll_spell(actor, self.bundle, SHIELD, free=True, seed=1)
        self.assertIn("还没选", str(caught.exception))

    def test_magic_initiate_uses_the_chosen_ability(self):
        actor = self.actor(FIGHTER, 4, [MI_WIZARD], {
            MI_WIZARD + ".spell": (SHIELD,),
            MI_WIZARD + ".cantrips": (FIRE_BOLT, LIGHT),
            MI_WIZARD + ".casting_ability": ("wis",),
        })
        report = api.roll_spell(actor, self.bundle, SHIELD, free=True, seed=1)
        self.assertEqual(report["casting"]["ability"], "wis")
        # WIS 12（+1） → DC 11；若错误地用了 INT 16（+3）会是 13
        self.assertEqual(report["casting"]["dc"], 11)

    def test_shadow_touched_pool_binds_invisibility(self):
        actor = self.actor(FIGHTER, 4, [SHADOW], {
            SHADOW + ".boost": ("int",),
            SHADOW + ".spell": ("dnd2024.spell.color_spray",),
        })
        self.assertEqual(set(self.bound(actor)),
                         {"dnd2024.spell.invisibility", "dnd2024.spell.color_spray"})

    def test_telepathic_pool_binds_detect_thoughts(self):
        actor = self.actor(FIGHTER, 4, [TELEPATHIC], {TELEPATHIC + ".boost": ("wis",)})
        self.assertEqual(set(self.bound(actor)), {"dnd2024.spell.detect_thoughts"})


# --- 三、角色卡与存档 ---------------------------------------------------
class FreeCastSheetTest(Base):
    def test_sheet_exposes_per_spell_pools(self):
        sheet = api.character_sheet(self.fey(), self.bundle)
        rows = {row["spell"]: row for row in sheet["pools"] if row["spell"]}
        self.assertEqual(set(rows), {MISTY, BLESS})
        self.assertEqual(rows[MISTY]["source"], FEY)
        self.assertEqual(rows[MISTY]["left"], 1)

    def test_free_casts_summary(self):
        actor = self.fey()
        api.roll_spell(actor, self.bundle, MISTY, free=True, apply=True, seed=1)
        rows = api.free_casts(actor, self.bundle)
        self.assertEqual([row["spell"] for row in rows], [BLESS, MISTY])  # 按环级排
        left = {row["spell"]: row["left"] for row in rows}
        self.assertEqual(left, {BLESS: 1, MISTY: 0})
        self.assertEqual(rows[0]["name"], "祝福术")

    def test_save_round_trip_keeps_used_count(self):
        actor = self.fey()
        api.roll_spell(actor, self.bundle, MISTY, free=True, apply=True, seed=1)
        again = api.load_character(self.bundle, api.save_character(actor))
        pools = {pool.spell: pool for pool in again.root().resources.pools.values()
                 if pool.spell}
        self.assertEqual(pools[MISTY].available, 0)
        self.assertEqual(pools[BLESS].available, 1)

    def test_feat_row_shows_each_pool_by_name(self):
        sheet = api.character_sheet(self.fey(), self.bundle)
        row = next(item for item in sheet["feats"] if item["id"] == FEY)
        self.assertEqual(sorted(pool["label"] for pool in row["resources"]),
                         ["祝福术", "迷踪步"])


# --- 四、内容护栏 -------------------------------------------------------
class ResourceGuardTest(unittest.TestCase):
    def _resource(self, **over):
        data = {"id": "dnd2024.feat.demo.free_cast", "kind": "charge",
                "refresh": "long_rest", "capacity": 1, "per_spell": True}
        data.update(over)
        return parse_resource(data, owner_class="dnd2024.feat.demo")

    def test_per_spell_requires_capacity_one(self):
        with self.assertRaises(PluginError):
            self._resource(capacity=2)

    def test_per_spell_requires_charge_kind(self):
        with self.assertRaises(PluginError):
            self._resource(kind=PoolKind.POINT.value)

    def test_per_spell_rejects_by_level(self):
        data = {"id": "dnd2024.feat.demo.free_cast", "kind": "charge", "per_spell": True,
                "by_level": {1: 1, 5: 2}}
        with self.assertRaises(PluginError):
            parse_resource(data, owner_class="dnd2024.feat.demo")

    def test_plain_resource_still_allows_any_capacity(self):
        # 反证：没有 per_spell 的资源不该被这条限制误伤
        plain = parse_resource({"id": "dnd2024.feat.demo.points", "kind": "point",
                                "capacity": 5}, owner_class="dnd2024.feat.demo")
        self.assertFalse(plain.per_spell)
        self.assertEqual(plain.capacity.flat, 5)


class CastingAbilityGuardTest(Base):
    def _feat(self, **over):
        from dnd5r.content import parse_feat
        data = {
            "id": "dnd2024.feat.demo", "kind": "general",
            "name": {"zh": "示例", "en": "Demo"},
            "text": {"zh": "示例", "en": "Demo"},
            "choices": [{"id": "spell", "kind": "spell", "count": 1,
                         "spell_list": "wizard", "spell_level": 1}],
        }
        data.update(over)
        return parse_feat(data, "demo")

    def test_unknown_ability_rejected(self):
        with self.assertRaises(PluginError):
            self._feat(casting_ability="luck")

    def test_boost_without_ability_choice_rejected(self):
        with self.assertRaises(PluginError):
            self._feat(casting_ability="boost")

    def test_choose_without_choice_rejected(self):
        with self.assertRaises(PluginError):
            self._feat(casting_ability="choose")

    def test_choose_choice_is_narrowed_to_the_three_abilities(self):
        feat = self._feat(casting_ability="choose", choices=[
            {"id": "spell", "kind": "spell", "count": 1,
             "spell_list": "wizard", "spell_level": 1},
            {"id": "ability", "kind": "casting_ability", "count": 1,
             "from": ["int", "wis", "cha"]},
        ])
        self.assertEqual(feat.choice("ability").options, ("int", "wis", "cha"))


if __name__ == "__main__":
    unittest.main()
