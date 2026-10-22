# -*- coding: utf-8 -*-
"""P7d 验收：专长给的法术真的能选、能查、能校验（G3）。

`spell_grants` 在旧数据里只出现在两条战斗风格上，而且从来没有消费方 ——
「受祝福的勇士给你两道牧师戏法」在旧程序里就是一句中文说明。这一组盯住：

  1. 候选集**由法术表 + 环级现算**，内容里不抄 id（抄了必然和法术表漂）
  2. 学派收窄（妖精触碰 = 1 环预言/惑控）真的起作用，也真的排除别的
  3. 「不限法术表」不等于「不限一切」：不写学派时必须报错，否则候选是全部法术
  4. 选错法术当场抛错；**没选只是待办**，不是错误
  5. 「始终准备」清单与免费施放次数进得了角色卡，且 `to_dict` 往返一致

断言一律挑**本来不成立**的样本：证明「牧师戏法候选 7 条」不算数，
要同时证明「火球术不在里面」。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import SPELL_LIST_ANY
from dnd5r.kernel.errors import PluginError, RuleError
from dnd5r.rules.feats import check_feat_spells, spell_pool

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 16, "cha": 12}
CLERIC = "dnd2024.class.cleric"

BLESSED = "dnd2024.feat.blessed_warrior"
DRUIDIC = "dnd2024.feat.druidic_warrior"
MI_CLERIC = "dnd2024.feat.magic_initiate_cleric"
MI_WIZARD = "dnd2024.feat.magic_initiate_wizard"
FEY = "dnd2024.feat.fey_touched"
SHADOW = "dnd2024.feat.shadow_touched"
TELEPATHIC = "dnd2024.feat.telepathic"


class FeatSpellPoolTest(unittest.TestCase):
    """候选集是**算出来的**，不是抄的。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def _pool(self, feat_id, choice_id):
        feat = self.bundle.feats[feat_id]
        choice = next(item for item in feat.choices if item.id == choice_id)
        return spell_pool(self.bundle, choice)

    def test_cantrip_pool_matches_spell_list(self):
        pool = self._pool(BLESSED, "cantrips")
        self.assertTrue(pool)
        official = set(self.bundle.spell_list(CLERIC))
        self.assertTrue(set(pool) <= official, "候选里出现了不在牧师法术表里的法术")
        for spell_id in pool:
            self.assertEqual(int(self.bundle.spells[spell_id].level), 0)
        # 反证：1 环的祝福术不是戏法，不在戏法候选里
        self.assertNotIn("dnd2024.spell.bless", pool)

    def test_level1_pool_is_level1_only(self):
        pool = self._pool(MI_CLERIC, "spell")
        self.assertIn("dnd2024.spell.bless", pool)
        self.assertNotIn("dnd2024.spell.fireball", pool)     # 3 环
        self.assertNotIn("dnd2024.spell.guidance", pool)     # 0 环
        for spell_id in pool:
            self.assertEqual(int(self.bundle.spells[spell_id].level), 1)

    def test_wizard_and_cleric_pools_differ(self):
        # 两个变体必须是**两张不同的表** —— 否则「选哪张表」这件事没落地
        cleric = set(self._pool(MI_CLERIC, "cantrips"))
        wizard = set(self._pool(MI_WIZARD, "cantrips"))
        self.assertNotEqual(cleric, wizard)
        self.assertIn("dnd2024.spell.fire_bolt", wizard)
        self.assertNotIn("dnd2024.spell.fire_bolt", cleric)
        self.assertIn("dnd2024.spell.sacred_flame", cleric)
        self.assertNotIn("dnd2024.spell.sacred_flame", wizard)

    def test_school_filter_narrows(self):
        pool = self._pool(FEY, "spell")
        self.assertTrue(pool)
        for spell_id in pool:
            spell = self.bundle.spells[spell_id]
            self.assertEqual(int(spell.level), 1)
            self.assertIn(spell.school, ("divination", "enchantment"))
            self.assertNotIn(spell.school, ("evocation", "necromancy"))
        self.assertIn("dnd2024.spell.bless", pool)          # 惑控
        self.assertNotIn("dnd2024.spell.cure_wounds", pool)  # 防护
        # 影界触碰是另一对学派，两份候选不该相同
        shadow = set(self._pool(SHADOW, "spell"))
        self.assertNotEqual(set(pool), shadow)
        self.assertIn("dnd2024.spell.color_spray", shadow)   # 幻术
        self.assertNotIn("dnd2024.spell.color_spray", pool)

    def test_fixed_spells_are_on_the_feat(self):
        self.assertEqual(self.bundle.feats[FEY].spells, ("dnd2024.spell.misty_step",))
        self.assertEqual(self.bundle.feats[SHADOW].spells, ("dnd2024.spell.invisibility",))
        self.assertEqual(self.bundle.feats[TELEPATHIC].spells,
                         ("dnd2024.spell.detect_thoughts",))
        # 反证：受祝福的勇士没有写死法术（它的两道法术是选出来的）
        self.assertEqual(self.bundle.feats[BLESSED].spells, ())

    def test_free_cast_pool_is_one_per_long_rest(self):
        feat = self.bundle.feats[MI_CLERIC]
        self.assertEqual(len(feat.resources), 1)
        pool = feat.resources[0]
        self.assertEqual(pool.id, "dnd2024.feat.magic_initiate_cleric.free_cast")
        self.assertEqual(pool.refresh.value, "long_rest")
        # 「两道法术各一次」的专长**不许**建池 —— 合成 2 次会让人连放两次同一道
        self.assertEqual(self.bundle.feats[FEY].resources, ())


class FeatSpellPickTest(unittest.TestCase):
    """选择项校验：选错炸，没选只是待办。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def _actor(self, feats, choices=None):
        return api.new_character(self.bundle, CLERIC, 4, SCORES,
                                 name_zh="测试", name_en="Test",
                                 feats=tuple(feats), choices=choices or {})

    def test_unpicked_is_pending_not_error(self):
        actor = self._actor([FEY])
        sheet = api.character_sheet(actor, self.bundle)
        self.assertIn("dnd2024.feat.fey_touched.spell", sheet["choices_needed"])
        # 待办不等于失败：角色建出来了，属性加值也已生效
        self.assertTrue(sheet["feats"])

    def test_pick_outside_pool_raises(self):
        with self.assertRaises(RuleError):
            self._actor([FEY], {"dnd2024.feat.fey_touched.spell": ["dnd2024.spell.fireball"]})
        with self.assertRaises(RuleError):
            self._actor([MI_CLERIC], {"dnd2024.feat.magic_initiate_cleric.spell":
                                      ["dnd2024.spell.misty_step"]})  # 2 环，不是 1 环

    def test_pick_inside_pool_lands(self):
        actor = self._actor([FEY], {"dnd2024.feat.fey_touched.spell": ["dnd2024.spell.bless"],
                                    "dnd2024.feat.fey_touched.boost": ["wis"]})
        sheet = api.character_sheet(actor, self.bundle)
        names = [row["name"] for row in sheet["feats"][0]["spells"]]
        self.assertEqual(names, ["迷踪步", "祝福术"])
        self.assertNotIn("dnd2024.feat.fey_touched.spell", sheet["choices_needed"])

    def test_set_feat_choice_validates(self):
        actor = self._actor([FEY])
        with self.assertRaises(RuleError):
            api.set_feat_choice(actor, self.bundle, FEY, "spell",
                                ["dnd2024.spell.cure_wounds"])
        updated = api.set_feat_choice(actor, self.bundle, FEY, "spell",
                                      ["dnd2024.spell.bless"])
        sheet = api.character_sheet(updated, self.bundle)
        self.assertIn("祝福术", [row["name"] for row in sheet["feats"][0]["spells"]])
        # 失败的那一次不许改到原角色
        self.assertEqual(
            [row["id"] for row in api.character_sheet(actor, self.bundle)["feats"][0]["spells"]],
            ["dnd2024.spell.misty_step"])

    def test_feat_spells_do_not_eat_prepared_slots(self):
        """专长给的法术不占职业准备名额 —— 两条账不能混。"""
        plain = self._actor([MI_CLERIC], {"dnd2024.feat.magic_initiate_cleric.spell":
                                          ["dnd2024.spell.bless"]})
        picks = api.feat_picks(self.bundle, plain.profile)
        self.assertIn("dnd2024.spell.bless", picks.spells)
        self.assertEqual(plain.profile.prepared.get(CLERIC, ()), ())

    def test_repeatable_feat_gets_two_pools(self):
        """魔法入门可重复登记：登记两次就该有**两个**免费施放，不是一个。"""
        actor = self._actor([MI_CLERIC, MI_CLERIC], {
            "dnd2024.feat.magic_initiate_cleric.spell": ["dnd2024.spell.bless"],
            "dnd2024.feat.magic_initiate_cleric#1.spell": ["dnd2024.spell.cure_wounds"],
            "dnd2024.feat.magic_initiate_cleric.cantrips":
                ["dnd2024.spell.guidance", "dnd2024.spell.light"],
            "dnd2024.feat.magic_initiate_cleric#1.cantrips":
                ["dnd2024.spell.mending", "dnd2024.spell.resistance"],
        })
        root = actor.root()
        pools = [pool_id for pool_id in root.resources.pools
                 if pool_id.startswith("dnd2024.feat.magic_initiate_cleric.")]
        self.assertEqual(len(pools), 2, pools)
        self.assertTrue(all(root.resources.pools[key].capacity == 1 for key in pools))

    def test_save_round_trip_keeps_feat_spells(self):
        actor = self._actor([FEY], {"dnd2024.feat.fey_touched.spell": ["dnd2024.spell.bless"],
                                    "dnd2024.feat.fey_touched.boost": ["wis"]})
        data = api.save_character(actor)
        again = api.load_character(self.bundle, data)
        left = api.character_sheet(actor, self.bundle)["feats"][0]["spells"]
        right = api.character_sheet(again, self.bundle)["feats"][0]["spells"]
        self.assertEqual(left, right)


class FeatSpellContentGuardTest(unittest.TestCase):
    """坏内容必须当场炸，不能静默变成空下拉框。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def _choice(self, **over):
        from dnd5r.content import parse_feat_choice
        data = {"id": "spell", "kind": "spell", "count": 1,
                "spell_list": "cleric", "spell_level": 1}
        data.update(over)
        return parse_feat_choice(data, "dnd2024.feat.demo")

    def test_missing_spell_list_rejected(self):
        with self.assertRaises(PluginError):
            self._choice(spell_list="")

    def test_unknown_school_rejected(self):
        with self.assertRaises(PluginError):
            self._choice(spell_school=["evokation"])   # 拼错一个字母

    def test_school_on_cantrip_rejected(self):
        # 2024 的戏法不限学派，写了就是内容作者搞错了
        with self.assertRaises(PluginError):
            self._choice(spell_level=0, spell_school=["evocation"])

    def test_any_list_without_school_rejected(self):
        """「不限法术表」+「不限学派」= 整个法术库，那是没做功能而不是做了。"""
        choice = self._choice(spell_list=SPELL_LIST_ANY, spell_level=1)
        with self.assertRaises(RuleError):
            spell_pool(self.bundle, choice)

    def test_unknown_class_rejected(self):
        with self.assertRaises(RuleError):
            spell_pool(self.bundle, self._choice(spell_list="mystic"))

    def test_check_feat_spells_reports_problems(self):
        feat = self.bundle.feats[FEY]
        problems = check_feat_spells(
            self.bundle, [feat],
            {"dnd2024.feat.fey_touched.spell": ("dnd2024.spell.fireball",)})
        self.assertEqual(len(problems), 1)
        self.assertIn("fireball", problems[0])
        # 反证：合法的选项不该报问题
        self.assertEqual(check_feat_spells(
            self.bundle, [feat],
            {"dnd2024.feat.fey_touched.spell": ("dnd2024.spell.bless",)}), [])


if __name__ == "__main__":
    unittest.main()
