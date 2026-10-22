# -*- coding: utf-8 -*-
"""P5f 验收：339 个法术 + 8 张职业法术表 + 施法数值。

法术最容易做成「一堆看着像、其实没人读的 YAML」。这一组测试盯四件事：

  1. 每条法术都真的被解析成结构化字段（环级/学派/施法时间/距离/成分/持续）
  2. 伤害是「环位 → 骰式」的查表，不是正则拼出来的字符串
  3. 法术表与法术条目一致，且表里的 id 都存在
  4. 施法数值（DC/攻击加值/法位/准备上限）真的算得出来
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import SpellDef, lookup_dice, parse_spell
from dnd5r.kernel.errors import RuleError
from dnd5r.model.profile import Profile

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
INT_SCORES = {"str": 8, "dex": 14, "con": 14, "int": 17, "wis": 12, "cha": 10}
CHA_SCORES = {"str": 8, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 17}


class SpellDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_table_loaded(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertEqual(len(self.bundle.spells), 339)
        self.assertEqual(len(self.bundle.spell_lists), 8)

    def test_levels_cover_zero_to_nine(self):
        levels = {}
        for spell in self.bundle.spells.values():
            levels[spell.level] = levels.get(spell.level, 0) + 1
        self.assertEqual(sorted(levels), list(range(0, 10)))
        self.assertEqual(sum(levels.values()), 339)

    def test_schools_are_canonical(self):
        schools = {spell.school for spell in self.bundle.spells.values()}
        self.assertEqual(schools, {
            "abjuration", "conjuration", "divination", "enchantment",
            "evocation", "illusion", "necromancy", "transmutation",
        })

    def test_all_bilingual(self):
        for spell in self.bundle.spells.values():
            self.assertTrue(spell.name.zh and spell.name.en, spell.id)
            self.assertTrue(spell.text.zh and spell.text.en, spell.id)

    def test_cantrips_have_zero_bracket(self):
        for spell in self.bundle.spells.values():
            if spell.is_cantrip and spell.damage:
                self.assertIn(0, spell.damage, spell.id)

    def test_damage_table_is_dice(self):
        for spell in self.bundle.spells.values():
            for level, dice in spell.damage.items():
                self.assertRegex(dice, r"^\d+d\d+$", "%s@%s" % (spell.id, level))

    def test_fireball_shape(self):
        spell = self.bundle.spell("dnd2024.spell.fireball")
        self.assertEqual(spell.name.zh, "火球术")
        self.assertEqual(spell.level, 3)
        self.assertEqual(spell.school, "evocation")
        self.assertEqual(spell.cast_kind, "action")
        self.assertEqual(spell.range_feet, 150)
        self.assertEqual(spell.components, ("v", "s", "m"))
        self.assertEqual(spell.save, "dex")
        self.assertEqual(spell.area, ("sphere", 20))
        self.assertEqual(spell.damage, {3: "8d6"})
        self.assertEqual(spell.damage_type, "fire")
        self.assertFalse(spell.concentration)

    def test_spell_lists_reference_existing_ids(self):
        for class_id, spells in self.bundle.spell_lists.items():
            self.assertTrue(spells, class_id)
            for ident in spells:
                self.assertIn(ident, self.bundle.spells, class_id)
            self.assertEqual(len(set(spells)), len(spells), class_id)

    def test_spell_lists_cover_all_casters(self):
        casters = {class_id for class_id, item in self.bundle.classes.items()
                   if item.caster.value != "none"}
        self.assertEqual(set(self.bundle.spell_lists), casters)

    def test_classes_for_spell_is_inverted(self):
        self.assertEqual(self.bundle.classes_for_spell("dnd2024.spell.fireball"),
                         ("dnd2024.class.sorcerer", "dnd2024.class.wizard"))
        self.assertEqual(self.bundle.classes_for_spell("dnd2024.spell.nope"), ())


class SpellParseTest(unittest.TestCase):
    """解析期要挡住的坏数据 —— 这些错误不会崩，只会让某个法术算错。"""

    def _base(self, **kwargs):
        data = {
            "id": "homebrew.spell.test",
            "name": {"zh": "测试", "en": "Test"},
            "level": 1,
            "school": "evocation",
            "text": {"zh": "测试", "en": "Test"},
        }
        data.update(kwargs)
        return data

    def test_rejects_unknown_school(self):
        from dnd5r.kernel.errors import PluginError

        with self.assertRaises(PluginError):
            parse_spell(self._base(school="fire"))

    def test_rejects_bad_components(self):
        from dnd5r.kernel.errors import PluginError

        with self.assertRaises(PluginError):
            parse_spell(self._base(components=["v", "x"]))

    def test_rejects_bad_dice(self):
        from dnd5r.kernel.errors import PluginError

        with self.assertRaises(PluginError):
            parse_spell(self._base(damage={"1": "eight d six"}))

    def test_rejects_unknown_range(self):
        from dnd5r.kernel.errors import PluginError

        with self.assertRaises(PluginError):
            parse_spell(self._base(range="far away"))

    def test_range_mapping(self):
        self.assertEqual(parse_spell(self._base(range={"feet": 60})).range_feet, 60)
        self.assertIsNone(parse_spell(self._base(range="touch")).range_feet)

    def test_lookup_dice_takes_floor(self):
        self.assertEqual(lookup_dice({3: "8d6", 4: "9d6"}, 5), "9d6")
        self.assertEqual(lookup_dice({3: "8d6", 4: "9d6"}, 3), "8d6")
        self.assertEqual(lookup_dice({3: "8d6"}, 1), "")

    def test_upcast_uses_table(self):
        spell = parse_spell(self._base(level=3, damage={"3": "8d6", "4": "9d6", "5": "10d6"}))
        self.assertEqual(spell.damage_at(3), "8d6")
        self.assertEqual(spell.damage_at(5), "10d6")


class CastingNumbersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _sheet(self, class_id, level, scores):
        actor = api.new_character(self.bundle, class_id, level, scores,
                                  name_zh="施法", name_en="Caster")
        return api.character_sheet(actor, self.bundle)

    def test_wizard_dc_and_attack(self):
        sheet = self._sheet("dnd2024.class.wizard", 5, INT_SCORES)
        block = sheet["spellcasting"][0]
        self.assertEqual(block["ability"], "int")
        self.assertEqual(block["dc"]["total"], 14)      # 8 + 3 + 3
        self.assertEqual(block["attack"]["total"], 6)   # 3 + 3

    def test_sorcerer_uses_charisma(self):
        sheet = self._sheet("dnd2024.class.sorcerer", 1, CHA_SCORES)
        block = sheet["spellcasting"][0]
        self.assertEqual(block["ability"], "cha")
        self.assertEqual(block["dc"]["total"], 13)      # 8 + 2 + 3

    def test_non_caster_has_no_block(self):
        sheet = self._sheet("dnd2024.class.fighter", 5, INT_SCORES)
        self.assertEqual(sheet["spellcasting"], [])

    def test_slots_match_class_table(self):
        sheet = self._sheet("dnd2024.class.wizard", 5, INT_SCORES)
        block = sheet["spellcasting"][0]
        self.assertEqual([row["level"] for row in block["slots"]], [1, 2, 3])
        self.assertEqual([row["max"] for row in block["slots"]], [4, 3, 2])
        self.assertEqual(block["highest_slot"], 3)

    def test_prepared_and_cantrip_limits(self):
        sheet = self._sheet("dnd2024.class.wizard", 5, INT_SCORES)
        block = sheet["spellcasting"][0]
        self.assertEqual(block["cantrips"]["max"], 4)
        self.assertEqual(block["prepared"]["max"], 9)
        self.assertTrue(block["cantrips"]["options"])
        self.assertTrue(block["prepared"]["options"])

    def test_options_respect_highest_slot(self):
        sheet = self._sheet("dnd2024.class.wizard", 5, INT_SCORES)
        block = sheet["spellcasting"][0]
        levels = {row["level"] for row in block["prepared"]["options"]}
        self.assertEqual(levels, {1, 2, 3})
        for row in block["prepared"]["options"]:
            self.assertIn(row["id"], self.bundle.spell_list("dnd2024.class.wizard"))

    def test_half_caster_has_slots_from_level_one(self):
        # 2024 的圣武士 1 级就会施法（2 个一环位），与 2014 不同 —— 拿表验，别凭印象
        first = self._sheet("dnd2024.class.paladin", 1, CHA_SCORES)["spellcasting"][0]
        self.assertEqual([(row["level"], row["max"]) for row in first["slots"]], [(1, 2)])
        self.assertEqual(first["highest_slot"], 1)
        # 半施法者的环位成长更慢：5 级才有 2 环
        fifth = self._sheet("dnd2024.class.paladin", 5, CHA_SCORES)["spellcasting"][0]
        self.assertEqual([row["level"] for row in fifth["slots"]], [1, 2])

    def test_catalog_filter(self):
        catalog = api.spell_catalog(self.bundle, "dnd2024.class.druid", 0)
        self.assertGreater(catalog["count"], 0)
        for row in catalog["spells"]:
            self.assertEqual(row["level"], 0)
            self.assertIn(row["id"], self.bundle.spell_list("dnd2024.class.druid"))


WIZARD = "dnd2024.class.wizard"


class SpellPlanTest(unittest.TestCase):
    """P6a：准备法术落库（G5）。

    在这之前 `max_prepared` 只报上限，「选哪 9 个」无处可存 —— 法术页只能看不能选。
    现在配额与环级上限都走 `check_spell_picks`，界面与建角色共用一份规则。
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _wizard(self, level=5):
        return api.new_character(self.bundle, WIZARD, level, INT_SCORES)

    def test_plan_reports_quota_and_chosen(self):
        plan = api.spell_plan(self._wizard(), self.bundle)[0]
        self.assertEqual(plan["prepared"]["max"], 9)      # 5 级法师准备表
        self.assertEqual(plan["prepared"]["remaining"], 9)
        self.assertEqual(plan["prepared"]["chosen"], [])
        self.assertEqual(plan["dc"]["total"], 14)         # 8 + 3 熟练 + 3 智力

    def test_prepare_and_recount(self):
        actor = self._wizard()
        options = [row["id"] for row in
                   api.spell_plan(actor, self.bundle)[0]["prepared"]["options"]]
        plan = api.plan_spells(actor, self.bundle, WIZARD, prepared=options[:3])
        self.assertEqual([row["id"] for row in plan["prepared"]["chosen"]], options[:3])
        self.assertEqual(plan["prepared"]["remaining"], 6)
        self.assertEqual(actor.profile.spells_of(WIZARD), tuple(options[:3]))

    def test_quota_rejected(self):
        actor = self._wizard()
        options = [row["id"] for row in
                   api.spell_plan(actor, self.bundle)[0]["prepared"]["options"]]
        with self.assertRaises(RuleError) as ctx:
            api.plan_spells(actor, self.bundle, WIZARD, prepared=options[:10])
        self.assertIn("超出上限", str(ctx.exception))
        # 抛错不该留下半截状态
        self.assertEqual(actor.profile.spells_of(WIZARD), ())

    def test_spell_outside_class_list_rejected(self):
        with self.assertRaises(RuleError):
            api.plan_spells(self._wizard(), self.bundle, WIZARD,
                            prepared=["dnd2024.spell.cure_wounds"])

    def test_cantrip_cannot_be_prepared(self):
        with self.assertRaises(RuleError) as ctx:
            api.plan_spells(self._wizard(), self.bundle, WIZARD,
                            prepared=["dnd2024.spell.fire_bolt"])
        self.assertIn("戏法", str(ctx.exception))

    def test_leveled_spell_cannot_be_cantrip(self):
        with self.assertRaises(RuleError):
            api.plan_spells(self._wizard(), self.bundle, WIZARD,
                            cantrips=["dnd2024.spell.magic_missile"])

    def test_too_high_level_rejected(self):
        # 3 级法师最高 2 环，火球（3 环）不该能准备
        actor = api.new_character(self.bundle, WIZARD, 3, INT_SCORES)
        with self.assertRaises(RuleError) as ctx:
            api.plan_spells(actor, self.bundle, WIZARD, prepared=["dnd2024.spell.fireball"])
        self.assertIn("最高只有", str(ctx.exception))

    def test_non_caster_rejected(self):
        fighter = api.new_character(self.bundle, "dnd2024.class.fighter", 5,
                                    {"str": 16, "dex": 14, "con": 14,
                                     "int": 10, "wis": 12, "cha": 8})
        self.assertEqual(api.spell_plan(fighter, self.bundle), [])
        with self.assertRaises(RuleError):
            api.plan_spells(fighter, self.bundle, "dnd2024.class.fighter",
                            prepared=["dnd2024.spell.alarm"])

    def test_build_actor_validates_spells(self):
        with self.assertRaises(RuleError):
            api.new_character(self.bundle, WIZARD, 5, INT_SCORES,
                              prepared={WIZARD: ["dnd2024.spell.cure_wounds"]})
        actor = api.new_character(self.bundle, WIZARD, 5, INT_SCORES,
                                  prepared={WIZARD: ["dnd2024.spell.alarm"]},
                                  cantrips={WIZARD: ["dnd2024.spell.fire_bolt"]})
        self.assertEqual(actor.profile.spells_of(WIZARD), ("dnd2024.spell.alarm",))
        self.assertEqual(actor.profile.cantrips_of(WIZARD), ("dnd2024.spell.fire_bolt",))

    def test_sheet_carries_spell_plan(self):
        actor = self._wizard()
        api.plan_spells(actor, self.bundle, WIZARD, prepared=["dnd2024.spell.alarm"])
        sheet = api.character_sheet(actor, self.bundle)
        block = sheet["spellcasting"][0]
        self.assertEqual(block["class"], WIZARD)
        self.assertEqual([row["name"] for row in block["prepared"]["chosen"]], ["警报术"])

    def test_profile_roundtrip_keeps_spells(self):
        actor = api.new_character(self.bundle, WIZARD, 5, INT_SCORES,
                                  prepared={WIZARD: ["dnd2024.spell.alarm"]},
                                  cantrips={WIZARD: ["dnd2024.spell.fire_bolt"]})
        again = Profile.from_dict(actor.profile.to_dict())
        self.assertEqual(again.to_dict(), actor.profile.to_dict())


if __name__ == "__main__":
    unittest.main()
