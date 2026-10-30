# -*- coding: utf-8 -*-
"""P7 升级与「改现有角色」：改等级不丢东西，还差什么说得清。

这一组盯的是**不该被升级弄丢的东西**：背包、装备带来的 AC、当前 HP、
用掉的资源、状态与死亡豁免。升级本身很简单（改一个数字），难的是
`rebuild_actor` 保不住这些时没人发现 —— 所以每条都断言一次。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.model.profile import Profile

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"
WIZARD = "dnd2024.class.wizard"
DWARF = "dnd2024.species.dwarf"
SOLDIER = "dnd2024.background.soldier"
CHAMPION = "dnd2024.subclass.fighter.champion"
CHAIN_MAIL = "dnd2024.item.armor.chain_mail"
LONGSWORD = "dnd2024.item.weapon.longsword"
GREATAXE = "dnd2024.item.weapon.greataxe"
LONGBOW = "dnd2024.item.weapon.longbow"

SCORES = {"str": 15, "dex": 14, "con": 13, "int": 10, "wis": 12, "cha": 8}
INT_SCORES = {"str": 8, "dex": 14, "con": 13, "int": 15, "wis": 12, "cha": 10}


class LevelUpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def fighter(self, level=2, **kwargs):
        params = dict(
            name_zh="铁砧", name_en="Anvil",
            species=DWARF, background=SOLDIER,
            background_bonus={"str": 2, "con": 1},
            # 背景给的是 运动 + 威吓，这里挑不重叠的两项，方便验「改卡后技能不变」
            extra_proficiencies=["skill.perception", "skill.insight"],
        )
        params.update(kwargs)
        return api.new_character(self.bundle, FIGHTER, level, SCORES, **params)

    # --- 等级本身 ---------------------------------------------------
    def test_level_up_bumps_primary_class_only(self):
        actor = self.fighter(2)
        after = api.level_up(self.bundle, actor)
        self.assertEqual(int(after.profile.classes[0].class_level), 3)
        self.assertEqual(int(after.profile.total), 3)
        # 原来的 actor 不许被就地改掉（调用方可能还留着旧的那份）
        self.assertEqual(int(actor.profile.classes[0].class_level), 2)

    def test_level_up_refuses_at_cap(self):
        for level in (20,):
            actor = self.fighter(level)
            with self.assertRaises(api.RuleError):
                api.level_up(self.bundle, actor)
        # 兼职：单职业都没到 20，但总等级 20 也不许再升
        mixed = api.new_character(
            self.bundle, FIGHTER, 10,
            {"str": 15, "dex": 14, "con": 13, "int": 14, "wis": 12, "cha": 8},
            name_zh="兼职", name_en="MC", extra_classes=[(WIZARD, 10)])
        with self.assertRaises(api.RuleError) as caught:
            api.level_up(self.bundle, mixed)
        self.assertIn("上限", str(caught.exception))

    # --- 运行时事实 -------------------------------------------------
    def test_runtime_state_survives_level_up(self):
        actor = self.fighter(2)
        api.equip_item(actor, self.bundle, "armor", CHAIN_MAIL)
        actor.hp.current = 7
        api.set_exhaustion(actor, 2)
        api.set_condition(actor, "poisoned")
        before = api.character_sheet(actor, self.bundle)
        after = api.level_up(self.bundle, actor)
        sheet = api.character_sheet(after, self.bundle)

        self.assertEqual(sheet["hp"]["current"], 7)
        self.assertGreater(sheet["hp"]["maximum"], before["hp"]["maximum"],
                           "升级要加生命上限（多一个生命骰）")
        self.assertEqual(sheet["ac"]["total"], before["ac"]["total"],
                         "升级把护甲脱了 —— 装备没有被搬过去")
        self.assertEqual(sheet["exhaustion"]["level"], 2)
        self.assertIn("poisoned", sheet["conditions"])

    def test_death_saves_survive_level_up(self):
        actor = self.fighter(2)
        actor.hp.current = 0
        api.roll_death_save(actor, rng=ScriptedRng([1]))
        failed = int(actor.root().death_saves.failed)
        after = api.level_up(self.bundle, actor)
        self.assertEqual(int(after.root().death_saves.failed), failed,
                         "升级把死亡豁免的失败次数抹掉了")

    def test_used_resources_survive(self):
        actor = api.new_character(self.bundle, "dnd2024.class.barbarian", 3,
                                  {"str": 16, "dex": 14, "con": 15, "int": 8,
                                   "wis": 12, "cha": 10}, name_zh="蛮", name_en="Barb")
        pool = next(iter(actor.resources.pools))
        actor.resources.pools[pool].spend(1)
        used = actor.resources.pools[pool].capacity - actor.resources.pools[pool].available
        after = api.level_up(self.bundle, actor)
        self.assertIn(pool, after.resources.pools)
        self.assertGreaterEqual(
            after.resources.pools[pool].capacity - after.resources.pools[pool].available,
            used, "升级把已经用掉的资源次数吐回来了")

    # --- 预告 -------------------------------------------------------
    def test_view_reports_hp_and_proficiency(self):
        actor = self.fighter(4)
        view = api.level_up_view(self.bundle, actor)
        self.assertEqual((view["from_level"], view["to_level"]), (4, 5))
        self.assertGreater(view["hp_after"], view["hp_before"])
        # 熟练加值 5 级从 +2 涨到 +3
        self.assertEqual((view["prof_before"], view["prof_after"]), (2, 3))

    def test_view_lists_subclass_and_mastery_gaps(self):
        actor = self.fighter(2)
        view = api.level_up_view(self.bundle, actor)
        steps = {item["step"] for item in view["needs"]}
        self.assertIn("class", steps, "3 级解锁子职，预告里要说")
        self.assertIn("masteries", steps, "精通件数从 2 变 3，预告里要说")

    def test_view_lists_spell_gaps_for_caster(self):
        mage = api.new_character(self.bundle, WIZARD, 4, INT_SCORES,
                                 name_zh="法师", name_en="Mage")
        view = api.level_up_view(self.bundle, mage)
        steps = {item["step"] for item in view["needs"]}
        self.assertIn("spells", steps)
        self.assertIn("还没选满", "".join(item["text"] for item in view["needs"]))

    def test_view_has_no_needs_when_all_settled(self):
        actor = self.fighter(2, subclass=CHAMPION,
                             masteries=[LONGSWORD, GREATAXE, LONGBOW])
        view = api.level_up_view(self.bundle, actor)
        self.assertEqual([item["step"] for item in view["needs"]], [])

    # --- 草案往返 ---------------------------------------------------
    def test_draft_excludes_background_skills(self):
        actor = self.fighter(2)
        draft = api.draft_from_actor(self.bundle, actor)
        granted = set(self.bundle.backgrounds[SOLDIER].skills)
        self.assertFalse(granted & set(draft["skills"]),
                         "背景已给的技能又出现在「已选」里，向导会报数量不对")
        self.assertEqual(sorted(draft["skills"]), ["insight", "perception"])

    def test_draft_uses_base_scores(self):
        # 背景 +2 力量之后显示是 17，草案必须是 15（加值会被再算一遍）
        actor = self.fighter(2)
        self.assertEqual(api.character_sheet(actor, self.bundle)["abilities"]["str"]["score"],
                         SCORES["str"] + 2)
        self.assertEqual(api.draft_from_actor(self.bundle, actor)["scores"]["str"],
                         SCORES["str"])

    def test_draft_of_caster_has_no_empty_spell_tables(self):
        # 空表要整个键都没有：非施法职业带 `{class: []}` 被判成「战士不该有戏法」
        caster = api.new_character(self.bundle, WIZARD, 3, INT_SCORES,
                                   name_zh="法师", name_en="Mage",
                                   extra_proficiencies=["skill.arcana",
                                                        "skill.investigation"])
        draft = api.draft_from_actor(self.bundle, caster)
        self.assertEqual(draft["cantrips"], {})
        self.assertEqual(draft["prepared"], {})
        self.assertEqual(api.draft_problems(self.bundle, draft), [])

    def test_apply_draft_round_trip_keeps_everything(self):
        actor = self.fighter(3, subclass=CHAMPION,
                             masteries=[LONGSWORD, GREATAXE, LONGBOW])
        api.equip_item(actor, self.bundle, "armor", CHAIN_MAIL)
        actor.hp.current = 5
        before = api.character_sheet(actor, self.bundle)

        draft = api.draft_from_actor(self.bundle, actor)
        self.assertEqual(api.draft_problems(self.bundle, draft), [],
                         "现有角色转成的草案自己过不了校验，升级后会被卡住")
        after = api.character_sheet(api.apply_draft(self.bundle, actor, draft),
                                    self.bundle)

        for key in ("ac", "abilities", "skills", "saves", "origin", "classes"):
            self.assertEqual(after[key], before[key], "改卡把 %s 改了" % key)
        self.assertEqual(after["hp"]["current"], 5, "改卡把当前 HP 回满了")
        self.assertEqual(after["hp"]["maximum"], before["hp"]["maximum"])

    def test_apply_draft_changes_only_what_was_edited(self):
        actor = self.fighter(3, subclass=CHAMPION,
                             masteries=[LONGSWORD, GREATAXE, LONGBOW])
        api.equip_item(actor, self.bundle, "armor", CHAIN_MAIL)
        before_ac = api.character_sheet(actor, self.bundle)["ac"]["total"]
        draft = api.draft_from_actor(self.bundle, actor)
        draft["masteries"] = [LONGSWORD, LONGBOW, GREATAXE]
        after = api.character_sheet(api.apply_draft(self.bundle, actor, draft),
                                    self.bundle)
        self.assertEqual(after["ac"]["total"], before_ac)
        self.assertEqual(len(after["origin"]["masteries"]), 3)


class WithClassLevelTest(unittest.TestCase):
    """`Profile.with_class_level`：改等级只有这一处。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_changes_target_class(self):
        profile = Profile.single(FIGHTER, 3)
        self.assertEqual(int(profile.with_class_level(FIGHTER, 7).class_level(FIGHTER)), 7)

    def test_unknown_class_raises(self):
        profile = Profile.single(FIGHTER, 3)
        with self.assertRaises(api.RuleError):
            profile.with_class_level(WIZARD, 1)

    def test_multiclass_keeps_other_entries(self):
        profile = Profile.single(FIGHTER, 3).add_class(WIZARD, 2)
        updated = profile.with_class_level(WIZARD, 5)
        self.assertEqual(int(updated.class_level(FIGHTER)), 3)
        self.assertEqual(int(updated.class_level(WIZARD)), 5)
        self.assertEqual(int(updated.total), 8)


if __name__ == "__main__":
    unittest.main()
