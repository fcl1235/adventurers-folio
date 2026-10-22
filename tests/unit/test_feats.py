# -*- coding: utf-8 -*-
"""P5g 验收：79 个专长。

专长之前只有 `Profile.feats` 一个空元组，谁也不读。这一组把
「专长是内容、静态效果走原语、玩家选择走 choices」变成可验的：

  1. 79 条全部加载（12 起源 + 43 通用 + 12 战斗风格 + 12 传奇恩惠），双语齐全
  2. 静态原语：坚韧（HP 每级 +2）、防御（穿甲才有 AC）、箭术（只给远程）
  3. 玩家选择：属性提升的两种模式、坚毅的「豁免与属性同选」、技艺专家的专精
  4. 传奇恩惠：+1 上限 30（不是 20）、坚毅 +40 HP、速行 +30、真实视觉、抗性
  5. 前提：等级 / 职业限制要拒绝，属性前提只提示不拦
  6. 选择没选完不是错误（留在 choices_needed 里），选错了要报错
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import PluginError, RuleError
from dnd5r.model.inventory import EquipSlot

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}

ASI = "dnd2024.feat.ability_score_improvement"
DEFENSE = "dnd2024.feat.defense"
ARCHERY = "dnd2024.feat.archery"
TOUGH = "dnd2024.feat.tough"
SPEEDY = "dnd2024.feat.speedy"
RESILIENT = "dnd2024.feat.resilient"
SKILL_EXPERT = "dnd2024.feat.skill_expert"
BOON_STRENGTH = "dnd2024.feat.boon_of_fortitude"
BOON_SPEED = "dnd2024.feat.boon_of_speed"
BOON_TRUESIGHT = "dnd2024.feat.boon_of_truesight"
BOON_RESIST = "dnd2024.feat.boon_of_energy_resistance"


class FeatDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_table_loaded(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertEqual(len(self.bundle.feats), 79)

    def test_kinds(self):
        counts = {kind: len(self.bundle.feats_of_kind(kind))
                  for kind in ("origin", "general", "fighting_style", "epic_boon")}
        self.assertEqual(counts, {"origin": 12, "general": 43,
                                  "fighting_style": 12, "epic_boon": 12})

    def test_ids_wellformed(self):
        for feat in self.bundle.feats.values():
            self.assertTrue(feat.id.startswith("dnd2024.feat."), feat.id)
            self.assertNotIn(" ", feat.id)
            for power in feat.powers:
                self.assertEqual(power.owner, feat.id, power.id)
                self.assertTrue(power.id.startswith(feat.id + "."), power.id)

    def test_all_texts_bilingual(self):
        for feat in self.bundle.feats.values():
            self.assertTrue(feat.name.zh, feat.id)
            self.assertTrue(feat.name.en, feat.id)
            self.assertTrue(feat.text.zh, feat.id)
            self.assertTrue(feat.text.en, feat.id)
            # en 里出现汉字说明「英文」其实是硬塞的中文，比缺英文更糟
            self.assertIsNone(_first_cjk(feat.text.en), "%s 的英文里混了中文" % feat.id)
            for power in feat.powers:
                self.assertTrue(power.name.zh and power.name.en, power.id)
                self.assertTrue(power.text.zh and power.text.en, power.id)
                self.assertTrue(power.effects, power.id)

    def test_fighting_style_needs_no_level(self):
        for feat in self.bundle.feats_of_kind("fighting_style"):
            self.assertEqual(int(feat.level), 0, feat.id)

    def test_boons_need_level_19(self):
        for feat in self.bundle.feats_of_kind("epic_boon"):
            self.assertEqual(int(feat.level), 19, feat.id)
            caps = [choice.cap for choice in feat.choices if choice.kind == "ability_boost"]
            self.assertEqual(caps, [30], "%s 的恩惠加值上限应是 30" % feat.id)


def _first_cjk(text: str) -> str | None:
    for char in text or "":
        if "\u4e00" <= char <= "\u9fff":
            return char
    return None


class FeatMechanicsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _fighter(self, level=5, feats=(), choices=None, scores=None):
        return api.new_character(
            self.bundle, "dnd2024.class.fighter", level, scores or SCORES,
            name_zh="测试", name_en="Test", feats=feats, choices=choices or {},
        )

    def _sheet(self, actor):
        return api.character_sheet(actor, self.bundle)

    # --- 静态原语 ---------------------------------------------------
    def test_tough_adds_two_hp_per_level(self):
        plain = self._sheet(self._fighter(5))
        tough = self._sheet(self._fighter(5, feats=[TOUGH]))
        self.assertEqual(tough["hp"]["maximum"] - plain["hp"]["maximum"], 10)

    def test_defense_requires_armor(self):
        actor = self._fighter(5, feats=[DEFENSE])
        unarmored = self._sheet(actor)["ac"]["total"]
        actor.inventory.equip(EquipSlot.ARMOR, "dnd2024.item.armor.chain_mail")
        armored = self._sheet(actor)["ac"]["total"]
        plain = self._fighter(5)
        plain.inventory.equip(EquipSlot.ARMOR, "dnd2024.item.armor.chain_mail")
        self.assertEqual(armored, self._sheet(plain)["ac"]["total"] + 1)
        self.assertEqual(unarmored, self._sheet(self._fighter(5))["ac"]["total"])

    def test_archery_only_boosts_ranged(self):
        actor = self._fighter(5, feats=[ARCHERY])
        plain = self._fighter(5)
        for item, slot in (("dnd2024.item.weapon.longbow", EquipSlot.MAIN_HAND),
                           ("dnd2024.item.weapon.longsword", EquipSlot.MAIN_HAND)):
            actor.inventory.equip(slot, item)
            plain.inventory.equip(slot, item)
            bonus = self._sheet(actor)["attacks"][0]["attack"] - self._sheet(plain)["attacks"][0]["attack"]
            expected = 2 if "longbow" in item else 0
            self.assertEqual(bonus, expected, item)

    def test_speedy_adds_ten_feet(self):
        plain = self._sheet(self._fighter(5))["speed"]["walk"]
        fast = self._sheet(self._fighter(5, feats=[SPEEDY],
                                         choices={SPEEDY + ".boost": ["dex"]}))["speed"]["walk"]
        self.assertEqual(fast - plain, 10)

    # --- 玩家选择 ---------------------------------------------------
    def test_ability_score_improvement_two_in_one(self):
        actor = self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str", "str"]})
        self.assertEqual(actor.top().statblock.abilities.score("str"), 18)
        sheet = self._sheet(actor)
        self.assertEqual(sheet["abilities"]["str"]["bonus"], 2)

    def test_ability_score_improvement_two_abilities(self):
        actor = self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str", "dex"]})
        self.assertEqual(actor.top().statblock.abilities.score("str"), 17)
        self.assertEqual(actor.top().statblock.abilities.score("dex"), 15)

    def test_ability_score_improvement_caps_at_20(self):
        actor = self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str", "str"]},
                              scores=dict(SCORES, str=19))
        self.assertEqual(actor.top().statblock.abilities.score("str"), 20)

    def test_ability_score_improvement_needs_two_picks(self):
        actor = self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str"]})
        self.assertEqual(actor.top().statblock.abilities.score("str"), 16)
        self.assertIn(ASI + ".boost", self._sheet(actor)["choices_needed"])

    def test_too_many_picks_rejected(self):
        with self.assertRaises(RuleError):
            self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str", "dex", "con"]})

    def test_unknown_pick_rejected(self):
        with self.assertRaises(RuleError):
            self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["luck", "luck"]})

    def test_resilient_pins_boost_to_chosen_save(self):
        # 战士本来熟练力量与体质豁免，所以选魅力才看得出「新熟练」
        actor = self._fighter(8, feats=[RESILIENT], choices={RESILIENT + ".save": ["cha"]})
        self.assertEqual(actor.top().statblock.abilities.score("cha"), 9)
        self.assertEqual(actor.top().statblock.abilities.score("wis"), 12)
        sheet = self._sheet(actor)
        self.assertTrue(sheet["saves"]["cha"]["proficient"])
        self.assertFalse(sheet["saves"]["dex"]["proficient"])

    def test_skill_expert_gives_skill_and_expertise(self):
        actor = self._fighter(8, feats=[SKILL_EXPERT], choices={
            SKILL_EXPERT + ".skill": ["stealth"],
            SKILL_EXPERT + ".expertise": ["stealth"],
            SKILL_EXPERT + ".boost": ["dex"],
        })
        self.assertIn("skill.stealth", actor.profile.proficiencies)
        self.assertIn("skill.stealth", actor.profile.expertise)

    def test_expertise_requires_proficiency(self):
        # 选了不熟练的技能做专精 → Profile 的集合约束拒绝（不是静默忽略）
        with self.assertRaises(RuleError):
            self._fighter(8, feats=[SKILL_EXPERT], choices={
                SKILL_EXPERT + ".skill": ["stealth"],
                SKILL_EXPERT + ".expertise": ["arcana"],
                SKILL_EXPERT + ".boost": ["dex"],
            })

    # --- 传奇恩惠 ---------------------------------------------------
    def test_boon_ability_cap_is_thirty(self):
        scores = dict(SCORES, str=20)
        actor = self._fighter(19, feats=[BOON_STRENGTH],
                              choices={BOON_STRENGTH + ".boost": ["str"]}, scores=scores)
        self.assertEqual(actor.top().statblock.abilities.score("str"), 21)

    def test_boon_fortitude_flat_hp(self):
        plain = self._sheet(self._fighter(19))["hp"]["maximum"]
        tough = self._sheet(self._fighter(19, feats=[BOON_STRENGTH],
                                          choices={BOON_STRENGTH + ".boost": ["str"]}))
        # +40 HP 与 +1 力量（体质没动）—— 差值就是 40
        self.assertEqual(tough["hp"]["maximum"] - plain, 40)

    def test_boon_speed(self):
        plain = self._sheet(self._fighter(19))["speed"]["walk"]
        fast = self._sheet(self._fighter(19, feats=[BOON_SPEED],
                                         choices={BOON_SPEED + ".boost": ["dex"]}))
        self.assertEqual(fast["speed"]["walk"] - plain, 30)

    def test_boon_truesight(self):
        sheet = self._sheet(self._fighter(19, feats=[BOON_TRUESIGHT],
                                          choices={BOON_TRUESIGHT + ".boost": ["wis"]}))
        self.assertEqual(sheet["senses"].get("truesight"), 60)

    def test_boon_energy_resistance(self):
        picks = {BOON_RESIST + ".boost": ["con"], BOON_RESIST + ".resist": ["fire", "cold"]}
        sheet = self._sheet(self._fighter(19, feats=[BOON_RESIST], choices=picks))
        self.assertEqual(sheet["resistances"], ["cold", "fire"])

    # --- 前提与登记 -------------------------------------------------
    def test_level_prereq_rejected(self):
        with self.assertRaises(RuleError):
            self._fighter(3, feats=[BOON_STRENGTH])

    def test_class_prereq_rejected(self):
        # 受祝福的勇士只给圣武士
        with self.assertRaises(RuleError):
            self._fighter(5, feats=["dnd2024.feat.blessed_warrior"])

    def test_unknown_feat_rejected(self):
        with self.assertRaises(PluginError):
            self._fighter(5, feats=["dnd2024.feat.does_not_exist"])

    def test_duplicate_feat_rejected_unless_repeatable(self):
        with self.assertRaises(RuleError):
            self._fighter(8, feats=[TOUGH, TOUGH])
        # 属性提升可重复选取
        actor = self._fighter(8, feats=[ASI, ASI],
                              choices={ASI + ".boost": ["str", "str"]})
        self.assertEqual(actor.profile.feats.count(ASI), 2)

    def test_feat_powers_are_available(self):
        actor = self._fighter(5, feats=[TOUGH])
        ids = {power.id for power in api.available_powers(self.bundle, actor)}
        self.assertIn("dnd2024.feat.tough.hp", ids)

    # --- 选单 -------------------------------------------------------
    def test_feat_options_filter_by_prereq(self):
        actor = self._fighter(5)
        options = api.feat_options(self.bundle, actor)
        self.assertEqual(options["count"], 79)
        rows = {row["id"]: row for row in options["feats"]}
        self.assertFalse(rows[BOON_STRENGTH]["selectable"], "19 级恩惠不该在 5 级可选")
        self.assertFalse(rows["dnd2024.feat.blessed_warrior"]["selectable"])
        self.assertTrue(rows[TOUGH]["selectable"])
        # 属性前提只提示不拦：力量 16 的战士能看到「演员」但标注 CHA 不足
        self.assertFalse(rows["dnd2024.feat.actor"]["selectable"])
        self.assertTrue(any("CHA" in item for item in rows["dnd2024.feat.actor"]["blocked"]))

    def test_taken_feat_not_selectable_again(self):
        actor = self._fighter(8, feats=[TOUGH])
        rows = {row["id"]: row for row in api.feat_options(self.bundle, actor)["feats"]}
        self.assertTrue(rows[TOUGH]["taken"])
        self.assertFalse(rows[TOUGH]["selectable"])

    def test_sheet_lists_feats_and_pending_choices(self):
        # 只选了技能：专精的候选就该只剩这一个已熟练的技能
        actor = self._fighter(8, feats=[SKILL_EXPERT],
                             choices={SKILL_EXPERT + ".skill": ["stealth"]})
        sheet = self._sheet(actor)
        self.assertEqual([row["id"] for row in sheet["feats"]], [SKILL_EXPERT])
        self.assertTrue(sheet["feats"][0]["pending"])
        self.assertEqual(len(sheet["choices_needed"]), 2)   # 专精 + 属性
        row = sheet["feats"][0]
        self.assertEqual(len(row["choices"]), 3)
        expertise = [item for item in row["choices"] if item["id"] == "expertise"][0]
        self.assertEqual(expertise["options"], ["stealth"])
        self.assertEqual(expertise["remaining"], 1)


if __name__ == "__main__":
    unittest.main()
