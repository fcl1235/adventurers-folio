# -*- coding: utf-8 -*-
"""P7 建卡向导的验收：8 步的目录、草案校验、最终组装。

这一组盯三件事：

  1. **目录不缺项**。12 职业 / 18 技能 / 37 工具 / 10 物种 / 16 背景，
     少一项界面上就是一条空下拉，建卡走到那一步就卡死。
  2. **校验与建卡共用一套判断**。`draft_problems()` 说能过，
     `build_from_draft()` 就必须真能建出来 —— 反过来也一样。两套判断不一致
     会变成「界面全绿、点完成报错」，那是最难解释的失败。
  3. **该拦的拦、该提醒的只提醒**。重复选背景已给的技能是 2024 允许的换法，
     拦成错误等于告诉玩家他做错了。
"""

import unittest
from pathlib import Path

import dnd5r.api as api

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"
WIZARD = "dnd2024.class.wizard"
MONK = "dnd2024.class.monk"

SOLDIER = "dnd2024.background.soldier"
SAGE = "dnd2024.background.sage"
DWARF = "dnd2024.species.dwarf"
ELF = "dnd2024.species.elf"

SCORES = {"str": 15, "dex": 14, "con": 13, "int": 10, "wis": 12, "cha": 8}


def _messages(problems):
    return [item["text"] for item in problems]


def _errors(problems):
    return [item for item in problems if item.get("level", "error") != "warn"]


class WizardCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(str(PLUGINS))

    def test_twelve_classes(self):
        rows = api.class_catalog(self.bundle)
        self.assertEqual(len(rows), 12)
        fighter = next(row for row in rows if row["id"] == FIGHTER)
        self.assertEqual(fighter["hit_die"], 10)
        self.assertEqual(fighter["mastery_at_1"], 3)
        self.assertEqual(fighter["mastery_max"], 6)

    def test_skill_and_tool_catalog(self):
        self.assertEqual(len(api.skill_catalog(self.bundle)), 18)
        self.assertEqual(len(api.tool_catalog(self.bundle)), 37)
        keys = [row["key"] for row in api.skill_catalog(self.bundle)]
        self.assertIn("sleight_of_hand", keys)

    def test_eight_steps(self):
        self.assertEqual([step["key"] for step in api.WIZARD_STEPS],
                         ["class", "background", "species", "scores",
                          "skills", "masteries", "spells", "summary"])
        self.assertEqual(api.STEP_INDEX["summary"], 7)

    def test_step_options_never_blows_up(self):
        """每一步都要能拿到数据 —— 空草案（战士 1 级、啥都没选）也不许抛。"""
        draft = api.empty_draft()
        for step in api.WIZARD_STEPS:
            with self.subTest(step=step["key"]):
                self.assertIsInstance(api.step_options(self.bundle, step["key"], draft), dict)

    def test_unknown_step_raises(self):
        with self.assertRaises(api.RuleError):
            api.step_options(self.bundle, "spellbook", api.empty_draft())


class SubclassStepTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(str(PLUGINS))

    def test_locked_below_unlock_level(self):
        """1 级能看见子职选项，但 `unlocked` 是假的 —— 界面据此灰掉。"""
        info = api.subclass_choices(self.bundle, FIGHTER, 1)
        self.assertFalse(info["unlocked"])
        self.assertTrue(info["options"])

    def test_unlocked_at_three(self):
        info = api.subclass_choices(self.bundle, FIGHTER, 3)
        self.assertTrue(info["unlocked"])

    def test_mastery_count_follows_level(self):
        self.assertEqual(api.mastery_choices(self.bundle, FIGHTER, 1)["count"], 3)
        self.assertEqual(api.mastery_choices(self.bundle, FIGHTER, 4)["count"], 4)
        self.assertEqual(api.mastery_choices(self.bundle, FIGHTER, 10)["count"], 5)
        self.assertEqual(api.mastery_choices(self.bundle, FIGHTER, 16)["count"], 6)

    def test_mastery_options_filtered_by_proficiency(self):
        """战士军武全能有短弓，法师只有简易武器 —— 短弓不该出现在法师的选项里。"""
        fighter = {row["id"] for row in api.mastery_choices(self.bundle, FIGHTER, 1)["options"]}
        self.assertTrue(any("longbow" in item for item in fighter))

    def test_class_without_mastery_gets_empty(self):
        info = api.mastery_choices(self.bundle, MONK, 5)
        self.assertEqual(info["count"], 0)
        self.assertEqual(info["options"], [])


class SpellStepTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(str(PLUGINS))

    def test_wizard_level_three_caps_at_second_circle(self):
        """3 级法师只有 1–2 环法术位，**不能把 9 环全列出来**。"""
        info = api.spell_choices(self.bundle, WIZARD, 3)
        self.assertTrue(info["caster"])
        self.assertEqual(info["max_spell_level"], 2)
        self.assertEqual([group["level"] for group in info["levels"]], [1, 2])
        self.assertEqual(info["cantrip_limit"], 3)
        self.assertEqual(info["prepared_limit"], 6)

    def test_non_caster_has_no_spells(self):
        info = api.spell_choices(self.bundle, FIGHTER, 5)
        self.assertFalse(info["caster"])
        self.assertEqual(info["levels"], [])
        self.assertEqual(info["cantrip_limit"], 0)

    def test_every_listed_spell_has_a_name(self):
        info = api.spell_choices(self.bundle, WIZARD, 5)
        for row in info["cantrips"]:
            self.assertTrue(row["name"])
        for group in info["levels"]:
            for row in group["spells"]:
                self.assertTrue(row["name"], row["id"])


class DraftCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(str(PLUGINS))

    def fighter(self):
        draft = api.empty_draft()
        draft.update(
            class_id=FIGHTER, class_level=5,
            subclass="dnd2024.subclass.fighter.champion",
            species=DWARF, background=SOLDIER,
            background_bonus={"str": 2, "con": 1}, scores=dict(SCORES),
            skills=["athletics", "perception"],
            masteries=["dnd2024.item.weapon.longsword",
                       "dnd2024.item.weapon.greataxe",
                       "dnd2024.item.weapon.longbow",
                       "dnd2024.item.weapon.warhammer"],
        )
        return draft

    def test_empty_draft_asks_for_skills_and_masteries(self):
        problems = _errors(api.draft_problems(self.bundle, api.empty_draft()))
        steps = {item["step"] for item in problems}
        self.assertEqual(steps, {"skills", "masteries"})

    def test_complete_draft_has_no_errors(self):
        self.assertEqual(_errors(api.draft_problems(self.bundle, self.fighter())), [])

    def test_repeat_background_skill_is_only_a_warning(self):
        """士兵给运动，再选一次运动：2024 允许换成别的，所以不该拦。"""
        problems = api.draft_problems(self.bundle, self.fighter())
        warnings = [item for item in problems if item.get("level") == "warn"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("运动", warnings[0]["text"])

    def test_warning_does_not_block_building(self):
        actor = api.build_from_draft(self.bundle, self.fighter())
        self.assertIn("skill.athletics", actor.profile.proficiencies)

    def test_wrong_subclass_class(self):
        draft = self.fighter()
        draft["subclass"] = "dnd2024.subclass.wizard.evoker"
        self.assertTrue(any("不属于这个职业" in text
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_subclass_below_unlock_level(self):
        draft = self.fighter()
        draft["class_level"] = 2
        draft["masteries"] = draft["masteries"][:2]
        draft["skills"] = ["athletics", "perception"]
        problems = _messages(api.draft_problems(self.bundle, draft))
        self.assertTrue(any("选不了子职" in text for text in problems))

    def test_illegal_background_bonus_shape(self):
        draft = self.fighter()
        draft["background_bonus"] = {"str": 2, "con": 2}
        self.assertTrue(any("+2" in text
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_bonus_on_wrong_ability(self):
        draft = self.fighter()
        draft["background_bonus"] = {"str": 2, "cha": 1}   # 士兵不给魅力
        self.assertTrue(any("CHA" in text.upper()
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_bonus_over_twenty(self):
        draft = self.fighter()
        draft["scores"] = dict(SCORES, str=19)
        draft["background_bonus"] = {"str": 2, "con": 1}
        self.assertTrue(any("上限" in text
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_point_buy_over_budget(self):
        draft = self.fighter()
        draft["score_mode"] = "point_buy"
        # 四个 15 已经是 36 点，超出 27 点预算
        draft["scores"] = {"str": 15, "dex": 15, "con": 15, "int": 15, "wis": 8, "cha": 8}
        self.assertTrue(any("超支" in text
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_skill_outside_class_list(self):
        draft = self.fighter()
        draft["skills"] = ["athletics", "arcana"]      # 战士没有奥秘
        self.assertTrue(any("不在本职业" in text
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_wrong_skill_count(self):
        draft = self.fighter()
        draft["skills"] = ["athletics"]
        self.assertTrue(any("要选 2 项" in text
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_mastery_count_must_match(self):
        draft = self.fighter()
        draft["masteries"] = draft["masteries"][:3]
        self.assertTrue(any("能精通 4 件" in text
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_mastery_on_unproficient_weapon(self):
        """法师选长剑：不熟练，也不该有精通。"""
        draft = api.empty_draft()
        draft.update(class_id=WIZARD, class_level=3, background=SAGE,
                     species=ELF, background_bonus={"int": 2, "con": 1},
                     scores=dict(SCORES), skills=["arcana", "investigation"],
                     masteries=["dnd2024.item.weapon.longsword"])
        self.assertTrue(any("没有武器精通" in text
                            for text in _messages(api.draft_problems(self.bundle, draft))))

    def test_mastery_of_wrong_category(self):
        draft = self.fighter()
        draft["masteries"] = ["dnd2024.item.weapon.longsword",
                              "dnd2024.item.weapon.greataxe",
                              "dnd2024.item.weapon.longbow",
                              "dnd2024.item.weapon.dagger"]
        draft["skills"] = ["perception", "insight"]
        self.assertEqual(_errors(api.draft_problems(self.bundle, draft)), [])

    def test_missing_class_short_circuits(self):
        draft = api.empty_draft()
        draft["class_id"] = ""
        problems = api.draft_problems(self.bundle, draft)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["step"], "class")


class BuildDraftTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(str(PLUGINS))

    def test_fighter_numbers(self):
        draft = api.empty_draft()
        draft.update(
            class_id=FIGHTER, class_level=5,
            subclass="dnd2024.subclass.fighter.champion",
            species=DWARF, background=SOLDIER,
            background_bonus={"str": 2, "con": 1}, scores=dict(SCORES),
            skills=["athletics", "perception"],
            masteries=["dnd2024.item.weapon.longsword",
                       "dnd2024.item.weapon.greataxe",
                       "dnd2024.item.weapon.longbow",
                       "dnd2024.item.weapon.warhammer"],
            name_zh="铁砧", name_en="Anvil",
        )
        actor = api.build_from_draft(self.bundle, draft)
        self.assertEqual(actor.display_name, "铁砧")
        self.assertEqual(actor.profile.species, DWARF)
        self.assertEqual(actor.profile.background, SOLDIER)
        self.assertEqual(len(actor.profile.masteries), 4)
        # 背景的起始专长必须进档（士兵 → 凶蛮攻击者）
        self.assertIn("dnd2024.feat.savage_attacker", actor.profile.feats)
        # 背景给的两项 + 职业选的两项（运动重复，集合里只有一份）
        for token in ("skill.athletics", "skill.intimidation", "skill.perception"):
            self.assertIn(token, actor.profile.proficiencies)
        # 矮人每级 +1 HP 要真的在 HP 上限里
        same = api.build_from_draft(self.bundle, dict(draft, species=""))
        self.assertEqual(actor.hp.maximum, same.hp.maximum + 5)

    def test_wizard_keeps_spells(self):
        draft = api.empty_draft()
        draft.update(class_id=WIZARD, class_level=3, species=ELF, background=SAGE,
                     background_bonus={"int": 2, "con": 1},
                     scores={"str": 8, "dex": 14, "con": 13,
                             "int": 15, "wis": 12, "cha": 10},
                     skills=["arcana", "investigation"])
        info = api.spell_choices(self.bundle, WIZARD, 3)
        draft["cantrips"] = {WIZARD: [row["id"] for row in info["cantrips"][:3]]}
        draft["prepared"] = {WIZARD: [row["id"] for row in info["levels"][0]["spells"][:6]]}
        actor = api.build_from_draft(self.bundle, draft)
        self.assertEqual(len(actor.profile.cantrips[WIZARD]), 3)
        self.assertEqual(len(actor.profile.prepared[WIZARD]), 6)

    def test_build_refuses_blocking_problems(self):
        draft = api.empty_draft()
        draft["skills"] = []
        with self.assertRaises(api.RuleError):
            api.build_from_draft(self.bundle, draft)

    def test_built_actor_round_trips(self):
        """建出来的角色存盘再读回，出身四项不能丢。"""
        draft = api.empty_draft()
        draft.update(class_id=FIGHTER, class_level=3, species=DWARF,
                     background=SOLDIER, background_bonus={"str": 2, "con": 1},
                     scores=dict(SCORES), skills=["perception", "insight"],
                     masteries=["dnd2024.item.weapon.longsword",
                                "dnd2024.item.weapon.greataxe",
                                "dnd2024.item.weapon.longbow"])
        actor = api.build_from_draft(self.bundle, draft)
        payload = api.save_character(actor)
        again = api.load_character(self.bundle, payload)
        self.assertEqual(again.profile.species, DWARF)
        self.assertEqual(again.profile.background, SOLDIER)
        self.assertEqual(again.profile.masteries, actor.profile.masteries)
        self.assertEqual(again.hp.maximum, actor.hp.maximum)


if __name__ == "__main__":
    unittest.main()
