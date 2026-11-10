# -*- coding: utf-8 -*-
"""G36 验收：语言整条线（内容 → 建档 → 卡面 → 存档）。

修之前的状态是「字段在、管道通、内容空」：`Profile.languages` 早就有，
`grant_proficiency` 也会把 `language.elvish` 拆出来，但**内容里一条语言都没有**，
而且拆出来的那一步改的是「建卡时并不存在的 profile」—— 于是：

  * 高精灵不会精灵语，盗贼没有黑话（2024 的语言根本不是物种给的，是建卡时选的）；
  * 卡面上一个字都看不到（`character_sheet` 没有语言段）；
  * 建卡向导没有语言这一步，`Profile.languages` 永远是空集。

这组测试盯五件事：

  1. **账目**：通用语自动 + 2 门标准自选 + 职业给的门数（盗贼 1、游侠 2 级 2）；
  2. **落库**：`language.*` token 必须进 `languages`，不能停在 `proficiencies` 里
     —— 停在那里等于「会这门语言但查不到名字」；
  3. **改卡不丢**：换专长走一次重建，语言不能掉（`rebuild_actor` 的差值收敛）；
  4. **改卡能换**：把精灵语换成矮人语要真的换掉（草案优先，不是并集）；
  5. **存档往返**：不存的话关掉程序回来语言就没了。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.api.languages import (
    BASIC_LANGUAGE_SLOTS, check_draft, class_fixed_keys, common_key,
    granted_slots, language_options, need_of, sheet_languages,
)
from dnd5r.content import load_all
from dnd5r.content.languages import LanguageDef, parse_language
from dnd5r.kernel.errors import PluginError, RuleError
from dnd5r.kernel.text import Text
from dnd5r.model.profile import ClassEntry, Profile
from dnd5r.rules import languages as rules

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

SCORES = {"str": 15, "dex": 14, "con": 13, "int": 12, "wis": 10, "cha": 8}

FIGHTER = "dnd2024.class.fighter"
ROGUE = "dnd2024.class.rogue"
RANGER = "dnd2024.class.ranger"
DRUID = "dnd2024.class.druid"

DAGGER = "dnd2024.item.weapon.dagger"
SLING = "dnd2024.item.weapon.sling"


def _bundle():
    return load_all(PLUGINS)


def _profile(**kwargs):
    """最小合法档案：`Profile` 至少要有 1 级职业，否则直接报错。"""
    return Profile(classes=(ClassEntry.make("dnd2024.class.fighter", 1),), **kwargs)


def _weapons(bundle, class_id, level, count):
    """按内容取前 N 件可精通的武器：写死 id 会在内容调整时碎，且各职业件数不同。"""
    rows = api.mastery_choices(bundle, class_id, level)["options"]
    return [row["id"] for row in rows][:count]


def _draft(bundle, class_id, **extra):
    draft = api.empty_draft()
    draft["class_id"] = class_id
    draft.update(extra)
    return draft


class LanguageContentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = _bundle()

    def test_table_size_and_split(self):
        """19 门：标准 10（含通用语）+ 稀有 9。少一条就是抄漏了 SRD 的表。"""
        rows = list(self.bundle.languages.values())
        self.assertEqual(len(rows), 19)
        self.assertEqual(sum(1 for row in rows if row.rare), 9)
        self.assertEqual(sum(1 for row in rows if not row.rare), 10)

    def test_exactly_one_common(self):
        """通用语只能有一条：两条会让「自动会」变成两份。"""
        common = [row for row in self.bundle.languages.values() if row.common]
        self.assertEqual(len(common), 1)
        self.assertEqual(common[0].key, "common")
        self.assertFalse(common[0].rare)

    def test_keys_are_token_safe(self):
        """key 必须是 `[a-z0-9_]`：带连字符的 key 进不了熟练 token。"""
        for row in self.bundle.languages.values():
            self.assertEqual(row.key, row.id.rsplit(".", 1)[-1])
            self.assertNotIn("-", row.key)

    def test_primordial_carries_dialect_note(self):
        """原初语的「含四种方言」必须跟着走，否则玩家会以为要学四次。"""
        item = self.bundle.languages["dnd2024.language.primordial"]
        self.assertIsNotNone(item.note)
        self.assertIn("Aquan", item.note.get("en"))
        self.assertIn("方言", item.note.get("zh"))
        # 其余语言没有 note，界面上不该冒出空括号
        others = [row for row in self.bundle.languages.values()
                  if row.key != "primordial"]
        self.assertTrue(all(row.note is None for row in others))

    def test_common_cannot_be_rare(self):
        with self.assertRaises(PluginError):
            LanguageDef(id="dnd2024.language.x", name=Text.of("某语", "X"),
                        rare=True, common=True)

    def test_parse_rejects_missing_name(self):
        with self.assertRaises(PluginError):
            parse_language({"id": "dnd2024.language.x"})


class LanguageRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = _bundle()

    def test_split_tokens(self):
        langs, others = rules.split_tokens(
            ["weapon.martial", "language.elvish", "skill.stealth", "language.druidic"])
        self.assertEqual(langs, {"elvish", "druidic"})
        self.assertEqual(others, {"weapon.martial", "skill.stealth"})

    def test_with_proficiencies_routes_language_tokens(self):
        """熟练与语言是两个集合。塞进熟练里就永远查不到名字。"""
        profile = _profile()
        merged = profile.with_proficiencies(add=["skill.stealth", "language.elvish"])
        self.assertEqual(set(merged.languages), {"elvish"})
        self.assertEqual(set(merged.proficiencies), {"skill.stealth"})

    def test_with_proficiencies_can_drop_language(self):
        profile = _profile().with_languages(add=["elvish"])
        gone = profile.with_proficiencies(remove=["language.elvish"])
        self.assertEqual(set(gone.languages), set())

    def test_normalized_migrates_stale_tokens(self):
        """旧档案可能把 language 留在熟练里：重建前要挪回来，否则差值收敛永远差一项。"""
        stale = _profile(proficiencies=frozenset({"language.elvish",
                                                  "skill.stealth"}))
        clean = stale.normalized()
        self.assertEqual(set(clean.languages), {"elvish"})
        self.assertEqual(set(clean.proficiencies), {"skill.stealth"})

    def test_granted_picks_up_class_languages(self):
        druid = api.new_character(self.bundle, DRUID, 1, SCORES)
        self.assertIn("druidic", rules.granted(self.bundle, druid))
        rogue = api.new_character(self.bundle, ROGUE, 1, SCORES)
        self.assertIn("thieves_cant", rules.granted(self.bundle, rogue))
        fighter = api.new_character(self.bundle, FIGHTER, 1, SCORES)
        self.assertEqual(set(), rules.granted(self.bundle, fighter))

    def test_known_is_stored_plus_granted(self):
        druid = api.new_character(self.bundle, DRUID, 1, SCORES,
                                  extra_languages=["common"])
        self.assertEqual(rules.known(self.bundle, druid), {"common", "druidic"})

    def test_name_falls_back_to_key(self):
        """内容包里没有的语言不能让卡面崩掉。"""
        self.assertEqual(rules.name_of(self.bundle, "klingon"), "klingon")

    def test_check_picks_reports_universe_and_count(self):
        problems = rules.check_picks(
            self.bundle, ["elvish", "klingon"], known_keys={"common"},
            allowed={"elvish", "dwarvish"}, need=3)
        joined = " / ".join(problems)
        self.assertIn("klingon", joined)
        self.assertIn("要选 3 门", joined)

    def test_check_picks_reports_duplicates(self):
        problems = rules.check_picks(
            self.bundle, ["elvish", "elvish"], known_keys={"common"},
            allowed={"elvish", "dwarvish"}, need=2)
        self.assertTrue(any("两次" in item for item in problems))


class LanguageSlotsTest(unittest.TestCase):
    """「谁给几门」必须按等级算：游侠 1 级 0 门、2 级 2 门。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = _bundle()

    def test_granted_slots_by_level(self):
        self.assertEqual(granted_slots(self.bundle, ROGUE, 1), 1)
        self.assertEqual(granted_slots(self.bundle, RANGER, 1), 0)
        self.assertEqual(granted_slots(self.bundle, RANGER, 2), 2)
        self.assertEqual(granted_slots(self.bundle, DRUID, 20), 0)

    def test_need_includes_two_standard(self):
        self.assertEqual(need_of(self.bundle, FIGHTER, 1), BASIC_LANGUAGE_SLOTS)
        self.assertEqual(need_of(self.bundle, ROGUE, 1), BASIC_LANGUAGE_SLOTS + 1)
        self.assertEqual(need_of(self.bundle, RANGER, 2), BASIC_LANGUAGE_SLOTS + 2)

    def test_common_key(self):
        self.assertEqual(common_key(self.bundle), "common")

    def test_fixed_keys_are_class_scoped(self):
        self.assertEqual(class_fixed_keys(self.bundle, ROGUE, 1), ["thieves_cant"])
        self.assertEqual(class_fixed_keys(self.bundle, FIGHTER, 1), [])
        # 德鲁伊语 1 级就有，升到 20 级也只出现一次
        self.assertEqual(class_fixed_keys(self.bundle, DRUID, 20), ["druidic"])


class LanguageStepTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = _bundle()

    def test_options_exclude_what_you_already_know(self):
        draft = _draft(self.bundle, ROGUE, class_level=1)
        options = language_options(self.bundle, draft)
        standard = {row["key"] for row in options["standard"]}
        rare = {row["key"] for row in options["rare"]}
        self.assertNotIn("common", standard | rare)      # 通用语自动会
        self.assertNotIn("thieves_cant", standard | rare)  # 盗贼黑话职业已给
        self.assertEqual(options["need"], 3)
        self.assertEqual(options["fixed"][0]["key"], "thieves_cant")
        self.assertEqual(options["common"]["key"], "common")

    def test_options_localised(self):
        draft = _draft(self.bundle, FIGHTER, class_level=1)
        zh = language_options(self.bundle, draft, "zh")
        en = language_options(self.bundle, draft, "en")
        self.assertEqual(zh["common"]["name"], "通用语")
        self.assertEqual(en["common"]["name"], "Common")
        self.assertEqual(en["fixed"], [])          # 战士没有职业语言

    def test_missing_languages_blocks(self):
        draft = _draft(self.bundle, FIGHTER, class_level=1, skills=["athletics"],
                       masteries=[])
        problems = api.draft_problems(self.bundle, draft)
        self.assertTrue(any(item["step"] == "languages" for item in problems))

    def test_standard_quota_enforced(self):
        """盗贼 3 门：1 标准 + 2 稀有虽然总数够，标准仍然不够。"""
        draft = _draft(self.bundle, ROGUE, class_level=1,
                       languages=["elvish", "abyssal", "celestial"])
        problems = check_draft(self.bundle, draft)
        self.assertTrue(any("标准语言至少要选 2 门" in item for item in problems))

    def test_duplicate_language_blocks(self):
        draft = _draft(self.bundle, ROGUE, class_level=1,
                       languages=["elvish", "elvish", "dwarvish"])
        problems = check_draft(self.bundle, draft)
        self.assertTrue(any("两次" in item for item in problems))

    def test_unknown_language_blocks(self):
        draft = _draft(self.bundle, FIGHTER, class_level=1,
                       languages=["elvish", "klingon"])
        problems = check_draft(self.bundle, draft)
        self.assertTrue(any("klingon" in item for item in problems))

    def test_editing_does_not_demand_quota(self):
        """老存档（G36 之前建的卡）语言是空的，改卡不能因此被挡住。"""
        draft = _draft(self.bundle, FIGHTER, class_level=1, languages=[])
        self.assertEqual(check_draft(self.bundle, draft, editing=True), [])


class LanguageBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = _bundle()

    def _build(self, class_id, picks, level=1, **extra):
        draft = _draft(self.bundle, class_id, class_level=level,
                       skills=list(extra.pop("skills", [])),
                       masteries=list(extra.pop("masteries", [])),
                       languages=picks, **extra)
        return api.build_from_draft(self.bundle, draft)

    def test_common_is_added_automatically(self):
        actor = self._build(FIGHTER, ["elvish", "dwarvish"],
                            skills=["athletics", "perception"],
                            masteries=_weapons(self.bundle, FIGHTER, 1, 3))
        self.assertEqual(sorted(actor.profile.languages), ["common", "dwarvish", "elvish"])

    def test_class_language_lands_in_profile_on_rebuild(self):
        actor = self._build(ROGUE, ["elvish", "dwarvish", "orc"],
                            skills=["stealth", "perception", "acrobatics", "insight"],
                            masteries=[DAGGER, SLING])
        self.assertEqual(sorted(actor.profile.languages),
                         ["common", "dwarvish", "elvish", "orc"])
        # 固定给的盗贼黑话不在档案里，由能力管道现算
        self.assertNotIn("thieves_cant", actor.profile.languages)
        self.assertIn("thieves_cant", rules.known(self.bundle, actor))

    def test_no_language_token_left_in_proficiencies(self):
        """`extra_proficiencies` 里混进来的语言也必须落到 `languages`。

        建卡向导走 `extra_languages`，但底层调用方（对账、造 NPC）习惯把一切
        带前缀的 token 都塞进熟练 —— 那条路以前会把 `language.giant` 留在
        熟练集合里，卡上永远查不到。
        """
        actor = api.new_character(self.bundle, FIGHTER, 1, SCORES,
                                  extra_languages=["common"],
                                  extra_proficiencies=["skill.athletics",
                                                       "language.giant"])
        self.assertFalse([token for token in actor.profile.proficiencies
                          if token.startswith("language.")])
        self.assertIn("giant", actor.profile.languages)

    def test_sheet_marks_source(self):
        actor = self._build(ROGUE, ["elvish", "dwarvish", "orc"],
                            skills=["stealth", "perception", "acrobatics", "insight"],
                            masteries=[DAGGER, SLING])
        rows = {row["key"]: row["source"]
                for row in api.character_sheet(actor, self.bundle)["languages"]}
        self.assertEqual(rows["common"], "common")
        self.assertEqual(rows["thieves_cant"], "class")
        self.assertEqual(rows["elvish"], "chosen")

    def test_sheet_localised(self):
        actor = self._build(FIGHTER, ["elvish", "dwarvish"],
                            skills=["athletics", "perception"],
                            masteries=_weapons(self.bundle, FIGHTER, 1, 3))
        rows = api.character_sheet(actor, self.bundle, "en")["languages"]
        self.assertIn("Common", [row["name"] for row in rows])

    def test_ranger_two_languages_at_level_two(self):
        actor = self._build(RANGER, ["elvish", "dwarvish", "orc", "giant"],
                            level=2, skills=["survival", "perception", "stealth"],
                            masteries=_weapons(self.bundle, RANGER, 2, 2))
        self.assertEqual(len(actor.profile.languages), 5)

    def test_short_of_quota_raises(self):
        with self.assertRaises(RuleError):
            self._build(ROGUE, ["elvish"],
                        skills=["stealth", "perception", "acrobatics", "insight"],
                        masteries=[DAGGER, SLING])


class LanguageEditTest(unittest.TestCase):
    """改卡：重建不能丢语言，也不能把旧语言焊死在档案上。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = _bundle()
        fake = api.new_character(cls.bundle, ROGUE, 1, SCORES,
                                 extra_languages=["common", "elvish", "dwarvish", "orc"])
        cls.actor = api.new_character(
            cls.bundle, ROGUE, 1, SCORES,
            extra_languages=["common", "elvish", "dwarvish", "orc"],
            extra_proficiencies=["skill.stealth", "skill.perception",
                                 "skill.acrobatics", "skill.insight"],
            masteries=[DAGGER, SLING])

    def test_rebuild_keeps_languages(self):
        before = set(self.actor.profile.languages)
        rebuilt = api.rebuild_actor(self.bundle, self.actor)
        self.assertEqual(set(rebuilt.profile.languages), before)

    def test_apply_draft_can_swap(self):
        draft = api.draft_from_actor(self.bundle, self.actor)
        draft["languages"] = ["gnomish", "halfling", "giant"]
        changed = api.apply_draft(self.bundle, self.actor, draft)
        self.assertEqual(sorted(changed.profile.languages),
                         ["common", "giant", "gnomish", "halfling"])

    def test_apply_draft_without_key_keeps_old(self):
        """没带 `languages` 的调用方（老接口）不能让语言凭空消失。"""
        draft = api.draft_from_actor(self.bundle, self.actor)
        draft.pop("languages", None)
        changed = api.apply_draft(self.bundle, self.actor, draft)
        self.assertEqual(sorted(changed.profile.languages),
                         sorted(self.actor.profile.languages))


class LanguagePersistenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = _bundle()

    def test_save_load_round_trip(self):
        actor = api.new_character(self.bundle, ROGUE, 1, SCORES,
                                  extra_languages=["common", "elvish", "dwarvish", "orc"])
        data = api.save_character(actor)
        self.assertIn("languages", data["profile"])
        back = api.load_character(self.bundle, data)
        self.assertEqual(set(back.profile.languages), set(actor.profile.languages))

    def test_sheet_languages_use_scope(self):
        actor = api.new_character(self.bundle, DRUID, 1, SCORES,
                                  extra_languages=["common", "elvish", "dwarvish"])
        rows = sheet_languages(self.bundle, actor)
        self.assertEqual(rows[0]["key"], "common")     # 通用语排最前
        self.assertIn("druidic", [row["key"] for row in rows])


if __name__ == "__main__":
    unittest.main()
