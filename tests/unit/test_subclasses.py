# -*- coding: utf-8 -*-
"""P5e 验收：48 个子职。

子职之前只是 `Profile` 上的一个自由字符串，谁也不读 —— 等于没有。
这一组测试把「子职是内容、特性按父职业等级解锁」变成可验的：

  1. 48 个子职全部加载，每个职业 4 个，双语齐全
  2. 特性按**父职业**等级解锁（2 级没有，3 级才有）
  3. 子职特性进入 `available_powers` / 角色卡 / 会话卡片
  4. 真实机制：冠军勇士的重击门槛（min 叠，不是相加）
  5. 真实机制：龙裔血脉的 HP 通道与无甲 AC（穿甲就失效）
  6. `Profile.subclasses` 存档往返 + 旧档单数字段兼容
  7. 挂错职业 / 未知子职要报错，不是静默忽略
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import ContentBundle, SubclassDef
from dnd5r.kernel.errors import PluginError, RuleError
from dnd5r.kernel.text import Text
from dnd5r.model.inventory import EquipSlot
from dnd5r.model.levels import ClassLevel

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
CHAMPION = "dnd2024.subclass.fighter.champion"
DRACONIC = "dnd2024.subclass.sorcerer.draconic_sorcery"


class SubclassDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_table_loaded(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertEqual(len(self.bundle.subclasses), 48)

    def test_every_class_has_four(self):
        for class_id in self.bundle.classes:
            found = self.bundle.subclasses_for(class_id)
            self.assertEqual(len(found), 4, class_id)

    def test_ids_and_owning_class(self):
        for subclass in self.bundle.subclasses.values():
            self.assertIn(subclass.class_id, self.bundle.classes, subclass.id)
            # id 的第三段应该就是职业短名，免得「战士的子职挂在法师下」这种错
            self.assertEqual(subclass.id.split(".")[2], subclass.class_id.split(".")[-1],
                             "%s 与 %s 不匹配" % (subclass.id, subclass.class_id))
            self.assertEqual(int(subclass.unlock_level), 3, subclass.id)

    def test_all_texts_bilingual(self):
        for subclass in self.bundle.subclasses.values():
            self.assertTrue(subclass.name.zh and subclass.name.en, subclass.id)
            self.assertTrue(subclass.summary.zh and subclass.summary.en, subclass.id)
            self.assertTrue(subclass.powers, "%s 一个特性都没有" % subclass.id)
            for power in subclass.powers:
                self.assertTrue(power.name.zh and power.name.en, power.id)
                self.assertTrue(power.text.zh and power.text.en, power.id)
                self.assertTrue(power.effects, "%s 没有 effects" % power.id)

    def test_power_owner_is_subclass(self):
        for subclass in self.bundle.subclasses.values():
            for power in subclass.powers:
                self.assertEqual(power.owner, subclass.id)
                self.assertTrue(power.id.startswith(subclass.id + "."), power.id)

    def test_every_subclass_builds_a_sheet(self):
        """48 个子职 × 4 个关键等级：建角色与出卡都不许抛异常。

        子职数据是生成的，最容易出的错是「某个特性的原语参数写错」
        这种只在选中它时才炸的问题 —— 全量冒烟是唯一能提前发现的办法。
        """
        scores = dict(SCORES, cha=16)
        for class_id in sorted(self.bundle.classes):
            for subclass in self.bundle.subclasses_for(class_id):
                for level in (1, 3, 10, 20):
                    actor = api.new_character(
                        self.bundle, class_id, level, scores,
                        name_zh="冒烟", name_en="Smoke", subclass=subclass.id)
                    sheet = api.character_sheet(actor, self.bundle)
                    self.assertGreater(sheet["hp"]["maximum"], 0, subclass.id)
                    self.assertGreater(sheet["ac"]["total"], 0, subclass.id)
                    self.assertEqual(len(sheet["subclasses"]), 1, subclass.id)

    def test_unknown_class_reported(self):
        bundle = ContentBundle()
        bundle.subclasses["dnd2024.subclass.noclass.x"] = SubclassDef(
            id="dnd2024.subclass.noclass.x",
            class_id="dnd2024.class.noclass",
            name=Text.of("无", "None"),
            summary=Text.of("无", "None"),
        )
        from dnd5r.content import _check_subclass_classes

        _check_subclass_classes(bundle)
        self.assertEqual(len(bundle.errors), 1)
        self.assertIn("未知职业", bundle.errors[0])


class SubclassUnlockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _actor(self, class_id, level, subclass):
        return api.new_character(self.bundle, class_id, level, SCORES,
                                 name_zh="子职", name_en="Subclass", subclass=subclass)

    def test_locked_below_unlock_level(self):
        sub = self.bundle.subclass(CHAMPION)
        self.assertEqual(sub.powers_at(ClassLevel(2)), ())
        self.assertTrue(sub.powers_at(ClassLevel(3)))

    def test_no_subclass_no_powers(self):
        plain = self._actor("dnd2024.class.fighter", 5, None)
        with_sub = self._actor("dnd2024.class.fighter", 5, CHAMPION)
        self.assertGreater(len(api.available_powers(self.bundle, with_sub)),
                           len(api.available_powers(self.bundle, plain)))

    def test_powers_gated_by_class_level(self):
        low = self._actor("dnd2024.class.fighter", 3, CHAMPION)
        high = self._actor("dnd2024.class.fighter", 15, CHAMPION)
        low_ids = {power.id for power in api.available_powers(self.bundle, low)}
        high_ids = {power.id for power in api.available_powers(self.bundle, high)}
        self.assertIn(CHAMPION + ".improved_critical", low_ids)
        self.assertNotIn(CHAMPION + ".superior_critical", low_ids)
        self.assertIn(CHAMPION + ".superior_critical", high_ids)

    def test_sheet_lists_subclass(self):
        actor = self._actor("dnd2024.class.fighter", 3, CHAMPION)
        sheet = api.character_sheet(actor, self.bundle)
        self.assertEqual(len(sheet["subclasses"]), 1)
        row = sheet["subclasses"][0]
        self.assertEqual(row["id"], CHAMPION)
        self.assertEqual(row["name"], "冠军勇士")
        self.assertTrue(row["unlocked"])
        ids = {power["id"] for power in sheet["powers"]}
        self.assertIn(CHAMPION + ".improved_critical", ids)

    def test_wrong_class_rejected(self):
        with self.assertRaises(RuleError):
            self._actor("dnd2024.class.wizard", 3, CHAMPION)

    def test_unknown_subclass_rejected(self):
        with self.assertRaises(PluginError):
            self._actor("dnd2024.class.fighter", 3, "dnd2024.subclass.fighter.nope")

    def test_session_cards_include_subclass(self):
        session = api.Session.open(str(PLUGINS), seed=1)
        session.create_character("dnd2024.class.fighter", 3, SCORES, subclass=CHAMPION)
        titles = [card.title for card in session.view().cards]
        self.assertIn("强化重击", titles)


class ChampionCritTest(unittest.TestCase):
    """重击门槛是**门槛**不是加值：19 与 18 叠加应得 18（取低），不是 17 或 37。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _crit(self, level):
        actor = api.new_character(self.bundle, "dnd2024.class.fighter", level, SCORES,
                                  name_zh="重击", name_en="Crit", subclass=CHAMPION)
        return api.character_sheet(actor, self.bundle)["crit"]

    def test_default_is_twenty(self):
        actor = api.new_character(self.bundle, "dnd2024.class.fighter", 5, SCORES,
                                  name_zh="无子职", name_en="No Subclass")
        sheet = api.character_sheet(actor, self.bundle)
        self.assertEqual(sheet["crit"]["min"], 20)
        self.assertEqual(sheet["crit"]["text"], "20")

    def test_improved_critical(self):
        crit = self._crit(3)
        self.assertEqual(crit["min"], 19)
        self.assertEqual(crit["text"], "19-20")
        self.assertIn("强化重击", crit["detail"])

    def test_superior_critical_stacks_by_min(self):
        crit = self._crit(15)
        self.assertEqual(crit["min"], 18)
        self.assertEqual(crit["text"], "18-20")
        self.assertIn("卓越重击", crit["detail"])

    def test_attack_card_shows_range(self):
        session = api.Session.open(str(PLUGINS), seed=1)
        session.create_character("dnd2024.class.fighter", 15, SCORES, subclass=CHAMPION)
        details = [line for card in session.view().attacks for line in card.detail]
        self.assertTrue(any("重击范围 18-20" in line for line in details), details)


class DraconicResilienceTest(unittest.TestCase):
    """HP 走 `hp.per_level` + `hp.flat`，AC 走「无甲时追加魅力」。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    # 魅力要给到 16：龙族韧性的 AC 加的就是魅力调整值，8 魅力会让这条测试测不出东西
    SCORES_CHA = dict(SCORES, cha=16)

    def _sheet(self, level, subclass=DRACONIC, armor=None, scores=None):
        actor = api.new_character(self.bundle, "dnd2024.class.sorcerer", level,
                                  scores or self.SCORES_CHA, name_zh="龙裔", name_en="Draconic",
                                  subclass=subclass)
        if armor:
            actor.inventory.equip(EquipSlot.ARMOR, "dnd2024.item.armor." + armor)
        return api.character_sheet(actor, self.bundle)

    def test_hp_without_subclass(self):
        # 1 级术士没有子职：d6 + 2 = 8
        self.assertEqual(self._sheet(1, subclass=None)["hp"]["maximum"], 8)

    def test_hp_bonus_is_level_plus_two(self):
        # 3 级：8 + 6 + 6 + (3 + 2) = 25
        self.assertEqual(self._sheet(3)["hp"]["maximum"], 25)
        # 20 级：8 + 6×19 + (20 + 2) = 144
        self.assertEqual(self._sheet(20)["hp"]["maximum"], 144)

    def test_unarmored_ac_adds_charisma(self):
        sheet = self._sheet(3)
        self.assertEqual(sheet["ac"]["total"], 15)      # 10 + 2 敏捷 + 3 魅力
        self.assertIn("龙族韧性", sheet["ac"]["detail"])

    def test_armor_cancels_charisma(self):
        sheet = self._sheet(3, armor="leather")
        self.assertEqual(sheet["ac"]["total"], 13)      # 11 + 2，没有魅力
        self.assertNotIn("龙族韧性", sheet["ac"]["detail"])

    def test_below_unlock_level_gets_nothing(self):
        sheet = self._sheet(2)
        self.assertEqual(sheet["ac"]["total"], 12)      # 只有 10 + 2
        self.assertEqual(sheet["subclasses"][0]["unlocked"], False)


class ProfileSubclassTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_round_trip(self):
        actor = api.new_character(self.bundle, "dnd2024.class.fighter", 3, SCORES,
                                  name_zh="存档", name_en="Save", subclass=CHAMPION)
        data = actor.profile.to_dict()
        self.assertEqual(data["subclasses"], [CHAMPION])
        from dnd5r.model.profile import Profile

        restored = Profile.from_dict(data)
        self.assertEqual(restored.subclasses, (CHAMPION,))
        self.assertEqual(restored.to_dict(), data)

    def test_legacy_single_field(self):
        from dnd5r.model.profile import Profile

        data = {"classes": [{"id": "dnd2024.class.fighter", "class_level": 3}],
                "subclass": CHAMPION}
        self.assertEqual(Profile.from_dict(data).subclasses, (CHAMPION,))

    def test_idempotent_and_removable(self):
        from dnd5r.model.profile import Profile

        profile = Profile.single("dnd2024.class.fighter", 3)
        profile = profile.with_subclass(CHAMPION).with_subclass(CHAMPION)
        self.assertEqual(profile.subclasses, (CHAMPION,))
        self.assertTrue(profile.has_subclass(CHAMPION))
        self.assertEqual(profile.without_subclass(CHAMPION).subclasses, ())
        self.assertEqual(profile.without_subclass().subclasses, ())

    def test_bad_id_rejected(self):
        from dnd5r.model.profile import Profile

        with self.assertRaises(RuleError):
            Profile(classes=Profile.single("dnd2024.class.fighter", 3).classes,
                    subclasses=("不是 id",))


if __name__ == "__main__":
    unittest.main()
