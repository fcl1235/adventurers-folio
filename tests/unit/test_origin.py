# -*- coding: utf-8 -*-
"""P6 验收：物种、背景、武器精通、属性生成。

这一组盯的是「出身真的算进数值了吗」，所以每条都尽量断言到具体数字：

  1. 物种特性走**和职业特性同一套原语** —— 矮人韧性 +1/级要出现在 HP 上，
     黑暗视觉 120 要出现在常驻 Modifier 里，天界抗性要出现在被动防御里。
     只写进内容文件、没进管道，就是「卡上写了但没算」的老毛病。
  2. 背景的属性加值**跟着背景走**（2024 口径），而且必须赶在算 HP 之前：
     加在体质上的那一点要抬高 HP 上限。
  3. 加值的三种形态（+2/+1、+1/+1/+1、乱写）只有前两种能过。
  4. 武器精通只记录、不结算 —— 断言 `origin_view` 明说 `masteries_settled=False`。
"""

import json
import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.rules.abilities import (
    POINT_BUY_BUDGET, background_bonus, point_buy_cost, roll_scores,
)
from dnd5r.rules.contributions import (
    passive_advantage_modes, passive_defenses, passive_modifiers,
)

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"
SCORES = {"str": 15, "dex": 14, "con": 13, "int": 10, "wis": 12, "cha": 8}

DWARF = "dnd2024.species.dwarf"
GOLIATH = "dnd2024.species.goliath"
AASIMAR = "dnd2024.species.aasimar"
GNOME = "dnd2024.species.gnome"
HALFLING = "dnd2024.species.halfling"

SOLDIER = "dnd2024.background.soldier"
ACOLYTE = "dnd2024.background.acolyte"

LONGSWORD = "dnd2024.item.weapon.longsword"


class OriginContentTest(unittest.TestCase):
    """内容装得进来、数得清。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_species_count(self):
        self.assertEqual(len(self.bundle.species), 10)

    def test_background_count(self):
        self.assertEqual(len(self.bundle.backgrounds), 16)

    def test_every_background_has_three_abilities(self):
        for item in self.bundle.backgrounds.values():
            self.assertEqual(len(set(item.abilities)), 3, item.id)
            for key in item.abilities:
                self.assertIn(key, ("str", "dex", "con", "int", "wis", "cha"))

    def test_background_origin_feat_exists(self):
        """起始专长必须是真专长 —— 写错 id 时不能等建卡才炸。"""
        for item in self.bundle.backgrounds.values():
            self.assertTrue(item.origin_feat, item.id)
            self.assertIn(item.origin_feat, self.bundle.feats, item.id)

    def test_background_tool_token_only_when_real(self):
        """`tool` 只在工具表里真有这一件时才写 key，否则留空（自选类别）。"""
        keys = {tool.key for tool in self.bundle.tools.values()}
        for item in self.bundle.backgrounds.values():
            if item.tool:
                self.assertIn(item.tool, keys, item.id)
            self.assertIsNotNone(item.tool_label, item.id)

    def test_species_traits_are_powers_in_book(self):
        for item in self.bundle.species.values():
            self.assertTrue(item.powers, item.id)
            for power in item.powers:
                self.assertTrue(self.bundle.book.has(power.id), power.id)


class SpeciesMechanicsTest(unittest.TestCase):
    """物种特性真的进了数值管道。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def make(self, species, level=5):
        return api.new_character(self.bundle, FIGHTER, level, SCORES,
                                 species=species)

    def test_dwarven_toughness_adds_hp_per_level(self):
        plain = self.make("")
        dwarf = self.make(DWARF)
        self.assertEqual(dwarf.hp.maximum - plain.hp.maximum, 5)

    def test_darkvision_reaches_passive_modifiers(self):
        mods = [mod for mod in passive_modifiers(self.bundle, self.make(DWARF))
                if mod.target == "sense.darkvision"]
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0].value, 120)

    def test_celestial_resistance(self):
        resist, _immune = passive_defenses(self.bundle, self.make(AASIMAR))
        self.assertEqual(set(resist), {"necrotic", "radiant"})

    def test_dwarven_resilience_poison(self):
        resist, _immune = passive_defenses(self.bundle, self.make(DWARF))
        self.assertIn("poison", resist)

    def test_gnomish_cunning_gives_three_saves(self):
        """优势走贡献点断言，别绕 Resolver —— 口径只有一处。"""
        actor = self.make(GNOME)
        for ability in ("int", "wis", "cha"):
            mode, sources = passive_advantage_modes(self.bundle, actor,
                                                    "save.%s" % ability)
            self.assertEqual(mode, "adv", ability)
            self.assertIn("侏儒狡黠", sources, ability)
        # 力量豁免不该被这条特性影响
        mode, _sources = passive_advantage_modes(self.bundle, actor, "save.str")
        self.assertEqual(mode, "flat")

    def test_goliath_speed_and_size(self):
        actor = self.make(GOLIATH)
        self.assertEqual(actor.statblock.speed("walk"), 35)
        self.assertEqual(actor.statblock.size, "medium")

    def test_halfling_is_small(self):
        self.assertEqual(self.make(HALFLING).statblock.size, "small")

    def test_level_gated_trait_waits(self):
        """龙裔 5 级的龙族飞行在 1 级时不该出现。"""
        low = api.available_powers(self.bundle, self.make("dnd2024.species.dragonborn", 1))
        high = api.available_powers(self.bundle, self.make("dnd2024.species.dragonborn", 5))
        fly = "dnd2024.species.dragonborn.dragon_wings"
        self.assertNotIn(fly, [power.id for power in low])
        self.assertIn(fly, [power.id for power in high])


class BackgroundBonusTest(unittest.TestCase):
    """背景加值：形态、上限、赶在 HP 之前。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_plus_two_plus_one(self):
        self.assertEqual(background_bonus(("str", "dex", "con"), {"str": 2, "con": 1}),
                         {"str": 2, "con": 1})

    def test_three_plus_ones(self):
        self.assertEqual(background_bonus(("str", "dex", "con"),
                                          {"str": 1, "dex": 1, "con": 1}),
                         {"str": 1, "dex": 1, "con": 1})

    def test_two_plus_two_rejected(self):
        with self.assertRaises(api.RuleError):
            background_bonus(("str", "dex", "con"), {"str": 2, "dex": 2})

    def test_mixed_shape_rejected(self):
        """+2 加两个 +1 = 4 点，不是合法形态。"""
        with self.assertRaises(api.RuleError):
            background_bonus(("str", "dex", "con"), {"str": 2, "dex": 1, "con": 1})

    def test_ability_outside_background_rejected(self):
        with self.assertRaises(api.RuleError):
            background_bonus(("str", "dex", "con"), {"str": 2, "int": 1})

    def test_bonus_lands_before_hp(self):
        """体质 +2 必须抬高 HP 上限，否则 20 级能差 10 点。"""
        base = api.new_character(self.bundle, FIGHTER, 5, SCORES,
                                 background=SOLDIER)
        boosted = api.new_character(self.bundle, FIGHTER, 5, SCORES,
                                    background=SOLDIER,
                                    background_bonus={"con": 2, "str": 1})
        self.assertEqual(boosted.statblock.abilities.score("con"),
                         base.statblock.abilities.score("con") + 2)
        # 5 级：体质调整值 +1 → 每级多 1 点，1 级也含在内
        self.assertEqual(boosted.hp.maximum - base.hp.maximum, 5)

    def test_cap_at_twenty(self):
        """18 + 2 = 20，不能再高。"""
        scores = dict(SCORES, con=18)
        actor = api.new_character(self.bundle, FIGHTER, 3, scores,
                                  background=SOLDIER,
                                  background_bonus={"con": 2, "str": 1})
        self.assertEqual(actor.statblock.abilities.score("con"), 20)

    def test_set_origin_rebuilds_hp(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        dwarf = api.set_origin(actor, self.bundle, DWARF)
        self.assertEqual(dwarf.hp.maximum - actor.hp.maximum, 5)

    def test_bonus_without_background_rejected(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES)
        with self.assertRaises(api.RuleError):
            api.set_origin(actor, self.bundle, bonus={"str": 2, "dex": 1})

    def test_bonus_picks_revalidated_on_background_switch(self):
        """换了背景，旧分配必须重验（新背景可能不给那些属性）。"""
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES,
                                  background=SOLDIER,
                                  background_bonus={"str": 2, "con": 1})
        with self.assertRaises(api.RuleError):
            # 侍僧给 INT/WIS/CHA，没有 STR
            api.set_origin(actor, self.bundle, background=ACOLYTE)

    def test_origin_feat_from_background(self):
        actor = api.new_character(self.bundle, FIGHTER, 3, SCORES,
                                  background=SOLDIER)
        self.assertEqual(actor.profile.feats, ("dnd2024.feat.savage_attacker",))

    def test_origin_feat_not_double_counted(self):
        """玩家自选同一个专长时，不该被当成「可重复选取」多给一轮选择。"""
        actor = api.new_character(self.bundle, FIGHTER, 3, SCORES,
                                  background=SOLDIER,
                                  feats=["dnd2024.feat.savage_attacker"])
        self.assertEqual(actor.profile.feats, ("dnd2024.feat.savage_attacker",))

    def test_background_skills_become_proficiencies(self):
        actor = api.new_character(self.bundle, FIGHTER, 3, SCORES,
                                  background=SOLDIER)
        self.assertIn("skill.intimidation", actor.profile.proficiencies)
        self.assertIn("skill.athletics", actor.profile.proficiencies)


class MasteryTest(unittest.TestCase):
    """武器精通：只记录，界面要照实说「没结算」。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_masteries_recorded_without_rebuild(self):
        actor = api.new_character(self.bundle, FIGHTER, 3, SCORES)
        actor.hp.current = 7
        same = api.set_masteries(actor, [LONGSWORD])
        self.assertIs(same, actor)                     # 不重建：同一个对象
        self.assertEqual(actor.profile.masteries, frozenset({LONGSWORD}))
        self.assertEqual(actor.hp.current, 7)          # 运行时状态没动

    def test_origin_view_says_not_settled(self):
        actor = api.new_character(self.bundle, FIGHTER, 3, SCORES,
                                  masteries=[LONGSWORD])
        view = api.origin_view(actor, self.bundle)
        self.assertFalse(view["masteries_settled"])
        self.assertEqual(view["masteries"][0]["name"], "长剑")
        self.assertEqual(view["masteries"][0]["mastery"], "sap")

    def test_empty_masteries(self):
        actor = api.new_character(self.bundle, FIGHTER, 3, SCORES)
        self.assertEqual(api.set_masteries(actor, []).profile.masteries, frozenset())


class ScoreGenerationTest(unittest.TestCase):
    """点买 / 标准数组 / 掷骰。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_point_buy_standard_cost(self):
        self.assertEqual(point_buy_cost(api.score_presets()["standard"]), 27)

    def test_point_buy_over_budget(self):
        problems = api.check_scores("point_buy",
                                    {"str": 15, "dex": 15, "con": 15,
                                     "int": 8, "wis": 10, "cha": 8})
        self.assertTrue(problems)

    def test_point_buy_out_of_range(self):
        problems = api.check_scores("point_buy",
                                    {"str": 16, "dex": 15, "con": 13,
                                     "int": 8, "wis": 8, "cha": 8})
        self.assertTrue(problems)

    def test_standard_array_must_be_used_exactly(self):
        self.assertEqual(api.check_scores("standard_array",
                                          api.score_presets()["standard"]), [])
        self.assertTrue(api.check_scores("standard_array",
                                         {"str": 15, "dex": 15, "con": 13,
                                          "int": 12, "wis": 10, "cha": 8}))

    def test_roll_scores_in_range(self):
        class Fixed:
            def randint(self, low, high):
                return 4

        scores = roll_scores(Fixed())
        self.assertEqual(set(scores.values()), {12})    # 4d6 弃最低 → 12

    def test_bonus_shapes_count(self):
        # 三项各 +1，以及 3×2 的「一项 +2 一项 +1」
        self.assertEqual(len(api.bonus_shapes(SOLDIER, self.bundle)), 7)


class OriginPersistenceTest(unittest.TestCase):
    """出身必须进档：读回来 HP、速度、精通都要在。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_round_trip(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES,
                                  species=DWARF, background=SOLDIER,
                                  background_bonus={"str": 2, "con": 1},
                                  masteries=[LONGSWORD])
        data = json.loads(json.dumps(api.save_character(actor)))
        self.assertEqual(data["version"], api.SAVE_VERSION)
        back = api.load_character(self.bundle, data)
        self.assertEqual(back.profile.species, DWARF)
        self.assertEqual(back.profile.background, SOLDIER)
        self.assertEqual(back.profile.background_bonus, {"str": 2, "con": 1})
        self.assertEqual(back.profile.masteries, frozenset({LONGSWORD}))
        self.assertEqual(back.hp.maximum, actor.hp.maximum)

    def test_old_save_without_origin(self):
        """v2 及更早的档没有出身四项 —— 取默认，不报错。"""
        actor = api.new_character(self.bundle, FIGHTER, 3, SCORES, species=DWARF)
        data = json.loads(json.dumps(api.save_character(actor)))
        data["version"] = 2
        for key in ("species", "background", "background_bonus", "masteries"):
            data["profile"].pop(key, None)
        back = api.load_character(self.bundle, data)
        self.assertEqual(back.profile.species, "")
        self.assertEqual(back.profile.background_bonus, {})

    def test_sheet_has_origin_block(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, SCORES,
                                  species=DWARF, background=SOLDIER,
                                  background_bonus={"str": 2, "con": 1})
        origin = api.character_sheet(actor, self.bundle)["origin"]
        self.assertEqual(origin["species"]["name"], "矮人")
        self.assertEqual(origin["species"]["speed"], 30)
        self.assertEqual(origin["background"]["name"], "士兵")
        self.assertEqual(origin["background"]["origin_feat_name"], "凶蛮攻击者")
        names = {trait["name"]: trait["settled"]
                 for trait in origin["species"]["traits"]}
        self.assertTrue(names["黑暗视觉"])          # 真结算了
        self.assertFalse(names["石中机警"])         # 只有规则登记


if __name__ == "__main__":
    unittest.main()
