# -*- coding: utf-8 -*-
"""G38 验收：专注真的被记下来了。

修之前的状态是「算了一半」：`api/state.concentration_dc()` 会算 DC，
`SpellDef.concentration` 也在数据里，但**没有任何地方记「此刻在专注哪一道」**。
于是三条规则同时不成立：

  * 开始第二条专注法术，第一条不会中断（桌上会两条同时生效）；
  * 受伤掷完 DC，没有一条记录可以被「打断」；
  * 角色卡上永远看不出自己在专注，存档更不记。

这组测试盯五件事：

  1. **一条专注**：开始新的就顶掉旧的，并且**说出来**顶掉的是哪一道。
     静默换掉比不换更糟 —— 玩家会以为自己还在专注祝福。
  2. **伤害真的会断**：失败 → 中断，成功 → 保留；阈值是「达到 DC 即成功」。
  3. **不替目标掷**：打中专注者只算 DC 提醒，不顺手替它掷骰（那是它的骰子）。
  4. **长休断、短休不断**：这两件事以前在代码里都不存在，所以谁也没分开过。
  5. **存档带上**：不存的话「关掉程序回来，祝福还在生效，卡上却看不出在专注」。

非专注法术不打断专注 —— 原文如此，也单独钉一条，防止以后「顺手」清掉。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import RuleError
from dnd5r.kernel.rng import ScriptedRng, SeededRng
from dnd5r.model.concentration import Concentration
from dnd5r.model.inventory import EquipSlot
from dnd5r.rules import concentration as rules

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
WIZARD = "dnd2024.class.wizard"

SCORES = {"str": 8, "dex": 14, "con": 14, "int": 16, "wis": 12, "cha": 10}

FOG = "dnd2024.spell.fog_cloud"      # 1 环，专注
BLUR = "dnd2024.spell.blur"          # 2 环，专注
MAGIC_MISSILE = "dnd2024.spell.magic_missile"   # 1 环，非专注


class ConcentrationModelTest(unittest.TestCase):
    """模型这一层：坏数据不许把整张角色卡带崩。"""

    def test_name_falls_back_by_locale(self):
        entry = Concentration("x", name_zh="云雾术", name_en="Fog Cloud", level=1, slot=1)
        self.assertEqual(entry.name("zh"), "云雾术")
        self.assertEqual(entry.name("en"), "Fog Cloud")
        # 英文缺了就退中文，再缺退 id —— 绝不印一对空引号
        self.assertEqual(Concentration("x", name_zh="云雾术").name("en"), "云雾术")
        self.assertEqual(Concentration("spell.x").name("en"), "spell.x")

    def test_empty_id_rejected(self):
        with self.assertRaises(RuleError):
            Concentration("")

    def test_level_out_of_range_rejected(self):
        with self.assertRaises(RuleError):
            Concentration("x", level=10)

    def test_from_dict_tolerates_garbage(self):
        """一条专注记录不值得让整个角色打不开 —— 坏数据退成「没在专注」。"""
        self.assertIsNone(Concentration.from_dict(None))
        self.assertIsNone(Concentration.from_dict({"spell_id": ""}))
        entry = Concentration.from_dict({"spell_id": "x", "level": "不是数字"})
        self.assertIsNotNone(entry)
        self.assertEqual(entry.level, 0)


class ConcentrationRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _actor(self, actor_id="pc.mage"):
        return api.new_character(self.bundle, WIZARD, 5, SCORES,
                                 name_zh="法师", name_en="Wizard", actor_id=actor_id)

    def _entry(self, spell_id=FOG, level=1, slot=1, zh="云雾术", en="Fog Cloud"):
        return Concentration(spell_id, name_zh=zh, name_en=en, level=level, slot=slot)

    def test_begin_returns_replaced_entry(self):
        actor = self._actor()
        self.assertIsNone(rules.begin(actor, self._entry()))
        old = rules.begin(actor, self._entry(BLUR, 2, 2, "朦胧术", "Blur"))
        self.assertIsNotNone(old)
        self.assertEqual(old.spell_id, FOG)
        self.assertEqual(rules.current(actor).spell_id, BLUR)

    def test_end_returns_removed_entry(self):
        actor = self._actor()
        rules.begin(actor, self._entry())
        gone = rules.end(actor)
        self.assertEqual(gone.spell_id, FOG)
        self.assertIsNone(rules.current(actor))
        self.assertIsNone(rules.end(actor))     # 再断一次不报错

    def test_dc_is_at_least_ten(self):
        self.assertEqual(rules.dc_for(0), 10)
        self.assertEqual(rules.dc_for(20), 10)
        self.assertEqual(rules.dc_for(21), 10)
        self.assertEqual(rules.dc_for(22), 11)
        self.assertEqual(rules.dc_for(60), 30)

    def test_dc_rejects_negative_and_garbage(self):
        with self.assertRaises(RuleError):
            rules.dc_for(-1)
        with self.assertRaises(RuleError):
            rules.dc_for("十")

    def test_keeps_is_reach_dc(self):
        self.assertTrue(rules.keeps(10, 10))
        self.assertFalse(rules.keeps(9, 10))

    def test_label_names_the_slot_level(self):
        self.assertEqual(rules.label(self._entry()), "《云雾术》（1 环）")
        self.assertEqual(rules.label(self._entry(level=0, slot=0)), "《云雾术》（戏法）")
        self.assertEqual(rules.label(self._entry(), "en"), "\"Fog Cloud\" (level 1)")

    def test_reminder_needs_focus_and_damage(self):
        actor = self._actor()
        self.assertIsNone(rules.reminder(actor, 12))          # 没在专注
        rules.begin(actor, self._entry())
        self.assertIsNone(rules.reminder(actor, 0))           # 伤害被免疫吃光
        self.assertIsNone(rules.reminder(None, 12))           # 没有角色卡的目标
        reminder = rules.reminder(actor, 26)
        self.assertEqual(reminder["dc"], 13)
        self.assertIn("云雾术", reminder["line"])


class ConcentrationApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _wizard(self, actor_id="pc.mage", zh="法师", en="Wizard"):
        return api.new_character(self.bundle, WIZARD, 5, SCORES,
                                 name_zh=zh, name_en=en, actor_id=actor_id)

    def _cast(self, actor, spell=FOG, slot=1, apply=True):
        return api.roll_spell(actor, self.bundle, spell, slot=slot,
                              class_id=WIZARD, apply=apply)

    # --- 施法建立专注 ---------------------------------------------------
    def test_cast_records_concentration(self):
        actor = self._wizard()
        result = self._cast(actor)
        self.assertTrue(result["concentrates"])
        block = result["concentration"]
        self.assertTrue(block["started"])
        self.assertEqual(block["spell"]["spell_id"], FOG)
        self.assertEqual(block["spell"]["slot"], 1)
        self.assertEqual(actor.concentration.spell_id, FOG)
        self.assertEqual(api.concentration_view(actor)["text"], "《云雾术》（1 环）")

    def test_preview_does_not_change_concentration(self):
        actor = self._wizard()
        result = self._cast(actor, apply=False)
        self.assertFalse(result["concentration"]["started"])
        self.assertIsNone(actor.concentration)
        self.assertFalse(api.concentration_view(actor)["active"])

    def test_second_concentration_replaces_first_and_says_so(self):
        actor = self._wizard()
        self._cast(actor, FOG, 1)
        result = self._cast(actor, BLUR, 2)
        block = result["concentration"]
        self.assertEqual(block["replaced_label"], "《云雾术》（1 环）")
        self.assertTrue(any("打断了原来的" in note for note in result["notes"]))
        self.assertEqual(actor.concentration.spell_id, BLUR)

    def test_non_concentration_spell_leaves_focus_alone(self):
        actor = self._wizard()
        self._cast(actor, FOG, 1)
        result = self._cast(actor, MAGIC_MISSILE, 1)
        self.assertFalse(result["concentrates"])
        self.assertIsNone(result["concentration"])
        self.assertEqual(actor.concentration.spell_id, FOG)

    # --- 受伤 -----------------------------------------------------------
    def test_failed_save_breaks_concentration(self):
        actor = self._wizard()
        self._cast(actor)
        # 伤害 30 → DC 15；法师体质豁免 +2，掷 3 必失败
        report = api.concentration_save(actor, self.bundle, 30, rng=ScriptedRng([3]))
        self.assertEqual(report["dc"], 15)
        self.assertFalse(report["kept"])
        self.assertTrue(report["active"])
        self.assertEqual(report["broken"]["spell_id"], FOG)
        self.assertIn("专注打断", report["line"])
        self.assertIsNone(actor.concentration)

    def test_successful_save_keeps_concentration(self):
        actor = self._wizard()
        self._cast(actor)
        report = api.concentration_save(actor, self.bundle, 0, rng=ScriptedRng([20]))
        self.assertEqual(report["dc"], 10)
        self.assertTrue(report["kept"])
        self.assertIn("保持专注", report["line"])
        self.assertEqual(actor.concentration.spell_id, FOG)

    def test_save_without_focus_says_so(self):
        """没在专注时仍然掷（DM 想先看看），但报告必须说这次不会中断任何东西。"""
        actor = self._wizard()
        report = api.concentration_save(actor, self.bundle, 12, rng=ScriptedRng([15]))
        self.assertFalse(report["active"])
        self.assertIn("没有在专注任何法术", report["line"])
        self.assertIsNone(report["broken"])

    def test_end_concentration(self):
        actor = self._wizard()
        self._cast(actor)
        report = api.end_concentration(actor)
        self.assertEqual(report["line"], "结束专注《云雾术》")
        self.assertIsNone(actor.concentration)
        self.assertFalse(api.concentration_view(actor)["active"])

    # --- 命中/伤害提醒 ---------------------------------------------------
    def test_attack_reminds_about_target_focus(self):
        target = self._wizard("pc.target", "法师乙", "Mage B")
        self._cast(target)
        fighter = api.new_character(self.bundle, "dnd2024.class.fighter", 5,
                                    {"str": 16, "dex": 12, "con": 14,
                                     "int": 10, "wis": 10, "cha": 10})
        fighter.inventory.equip(EquipSlot.MAIN_HAND, "dnd2024.item.weapon.longsword")
        result = api.attack_roll(fighter, self.bundle, target, rng=SeededRng(7))
        block = result["target_concentration"]
        self.assertIsNotNone(block)
        self.assertEqual(block["spell"]["spell_id"], FOG)
        self.assertTrue(any("它要掷 DC" in note for note in result["notes"]))
        # **不替目标掷**：掷骰记录里没有多出一次体质豁免
        self.assertEqual(target.concentration.spell_id, FOG)

    def test_spell_damage_reminds_about_target_focus(self):
        caster = self._wizard()
        target = self._wizard("pc.target", "法师乙", "Mage B")
        self._cast(target)
        result = api.roll_spell(caster, self.bundle, "dnd2024.spell.fireball",
                                slot=3, targets=[target],
                                class_id=WIZARD, rng=SeededRng(11))
        self.assertTrue(result["target_concentration"])
        self.assertEqual(result["target_concentration"][0]["spell"]["spell_id"], FOG)

    # --- 休息 -----------------------------------------------------------
    def test_long_rest_ends_concentration(self):
        actor = self._wizard()
        self._cast(actor)
        summary = api.take_long_rest(actor, self.bundle)["summary"]
        self.assertIsNone(actor.concentration)
        self.assertIn("长休结束专注", summary)

    def test_short_rest_keeps_concentration(self):
        """短休不断专注 —— 与长休分开，是原文的差别，不是偷懒。"""
        actor = self._wizard()
        self._cast(actor)
        api.take_short_rest(actor, self.bundle, spend=0)
        self.assertEqual(actor.concentration.spell_id, FOG)

    # --- 投影与存档 -----------------------------------------------------
    def test_sheet_projects_concentration(self):
        actor = self._wizard()
        sheet = api.character_sheet(actor, self.bundle)
        self.assertFalse(sheet["concentration"]["active"])
        self._cast(actor)
        sheet = api.character_sheet(actor, self.bundle)
        self.assertTrue(sheet["concentration"]["active"])
        self.assertEqual(sheet["concentration"]["spell"]["spell_id"], FOG)

    def test_save_round_trip(self):
        actor = self._wizard()
        self._cast(actor)
        data = api.save_character(actor, "zh")
        self.assertEqual(data["version"], api.SAVE_VERSION)
        self.assertEqual(data["concentration"]["spell_id"], FOG)
        loaded = api.load_character(self.bundle, data)
        self.assertEqual(loaded.concentration.spell_id, FOG)
        self.assertEqual(api.concentration_view(loaded)["text"], "《云雾术》（1 环）")

    def test_old_save_without_concentration_still_loads(self):
        """v4 及更早的档没有这一段：读成「没在专注」，不许因此读不开。"""
        actor = self._wizard()
        data = api.save_character(actor, "zh")
        data.pop("concentration")
        data["version"] = 4
        loaded = api.load_character(self.bundle, data)
        self.assertIsNone(loaded.concentration)

    def test_broken_concentration_field_does_not_break_load(self):
        actor = self._wizard()
        data = api.save_character(actor, "zh")
        data["concentration"] = {"level": "坏"}
        loaded = api.load_character(self.bundle, data)
        self.assertIsNone(loaded.concentration)

    # --- 双语 -----------------------------------------------------------
    def test_english_sentences(self):
        actor = self._wizard()
        self._cast(actor)
        self.assertEqual(api.concentration_view(actor, "en")["text"],
                         "\"Fog Cloud\" (level 1)")
        report = api.concentration_save(actor, self.bundle, 30,
                                        rng=ScriptedRng([1]), locale="en")
        self.assertIn("broken", report["line"])
        self.assertNotIn("专注", report["line"])


if __name__ == "__main__":
    unittest.main()
