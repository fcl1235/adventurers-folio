# -*- coding: utf-8 -*-
"""P12 验收：兼职（§12 从纸面进内容）。

期望值**全部从规则推导**，不从实现抄 —— 这就是这一层的「黄金对账」：
旧程序（oracle）没有兼职能力，六个组合的数值以规则书算术为准
（先按规则写期望，跑不过就是实现错）。

盯八件事：

  1. HP 分段：只有起始职业的 1 级取满骰，兼职职业每一级都是固定增量；
  2. 豁免熟练只来自**起始职业**（§12.3）；
  3. 前置属性：非起始职业逐个校验（战士 力量或敏捷 / 武僧 敏捷且感知）；
  4. 熟练只给 grants 那一份，不给起始熟练；
  5. 法术位：≥2 个非契约施法职业查合并表；契约位永远独立；单职业不变；
  6. 资源池按**所属职业**等级（术法点 = 术士等级，不是主职业等级）；
  7. 无甲防御互斥组：两个公式取较好的一个，不是加起来（§12.3）；
  8. 存档 / 重建往返：兼职档案读回来还是同一个角色。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import RuleError

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"
WIZARD = "dnd2024.class.wizard"
PALADIN = "dnd2024.class.paladin"
WARLOCK = "dnd2024.class.warlock"
CLERIC = "dnd2024.class.cleric"
BARBARIAN = "dnd2024.class.barbarian"
MONK = "dnd2024.class.monk"
ROGUE = "dnd2024.class.rogue"
SORCERER = "dnd2024.class.sorcerer"

# 各组合的属性都先满足兼职前置，再谈数值 —— 前置本身也是测试对象。
HEROIC = {"str": 16, "dex": 14, "con": 14, "int": 14, "wis": 10, "cha": 8}
PALADIN_SCORES = {"str": 16, "dex": 10, "con": 12, "int": 10, "wis": 10, "cha": 14}
SKIRMISHER = {"str": 10, "dex": 14, "con": 12, "int": 10, "wis": 14, "cha": 8}
ARCANE = {"str": 10, "dex": 12, "con": 14, "int": 14, "wis": 10, "cha": 14}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def make(self, first, first_level, extras, scores, name_zh="兼职者"):
        return api.new_character(
            self.bundle, first, first_level, scores,
            name_zh=name_zh, name_en="Multiclassed",
            extra_classes=extras)

    def sheet(self, actor):
        return api.character_sheet(actor, self.bundle)

    def pool(self, actor, pool_id):
        return next(row for row in self.sheet(actor)["pools"]
                    if row["id"] == pool_id)

    def slot_pools(self, actor):
        return sorted((row["id"], row["left"], row["max"])
                      for row in self.sheet(actor)["pools"]
                      if row["id"].startswith("dnd2024.slot."))

    def proficient_saves(self, actor):
        return sorted(key for key, row in self.sheet(actor)["saves"].items()
                      if row["proficient"])


class TwelvePointSixTest(Base):
    """§12.6 的六个黄金组合（期望值按规则书算术手推）。"""

    def test_fighter5_wizard3(self):
        """额外攻击只 1 次；位表按法师 3 级；熟练 +3；豁免只看战士。"""
        actor = self.make(FIGHTER, 5, [(WIZARD, 3)], HEROIC)
        sheet = self.sheet(actor)
        self.assertEqual(sheet["total_level"], 8)
        self.assertEqual(sheet["proficiency_bonus"], 3)
        # HP：战士 d10 体+2：(10+2) + 4×(5+1+2) = 44；法师 d6：3×(3+1+2) = 18
        self.assertEqual(sheet["hp"]["maximum"], 44 + 18)
        self.assertEqual(sheet["attacks_per_action"], 2)      # 战士 5 级二打，不叠加
        self.assertEqual(self.proficient_saves(actor), ["con", "str"])
        # 法师是唯一的非契约施法职业 → 用它自己的位表（3 级：4×1 环 + 2×2 环）
        self.assertEqual(self.slot_pools(actor),
                         [("dnd2024.slot.wizard.1", 4, 4), ("dnd2024.slot.wizard.2", 2, 2)])

    def test_paladin6_warlock2(self):
        """圣武士位表照旧（它仍是非契约施法者里唯一的一个）；契约位独立。"""
        actor = self.make(PALADIN, 6, [(WARLOCK, 2)], PALADIN_SCORES)
        slots = dict((row[0], row[2]) for row in self.slot_pools(actor))
        self.assertIn("dnd2024.slot.paladin.1", slots)        # 圣武士自己的位表
        self.assertEqual(slots["dnd2024.slot.paladin.1"], 4)  # 6 级圣武士 4×1 环
        self.assertEqual(slots["dnd2024.slot.paladin.2"], 2)
        # 契约位独立：邪术师 2 级 = 2 个 1 环，短休恢复
        pact = self.pool(actor, "dnd2024.slot.warlock.1")
        self.assertEqual((pact["left"], pact["max"]), (2, 2))
        self.assertEqual(pact["refresh"], "short_rest")
        self.assertFalse(any(row[0].startswith("dnd2024.slot.spellcasting")
                             for row in self.slot_pools(actor)))   # 没进合并表
        self.assertEqual(self.proficient_saves(actor), ["cha", "wis"])

    def test_cleric1_wizard5(self):
        """两个全职施法者 → 合并表：caster 6 级 = 4/3/3，位池不属于任何职业。"""
        actor = self.make(CLERIC, 1, [(WIZARD, 5)],
                          {"str": 10, "dex": 12, "con": 14, "int": 14, "wis": 14, "cha": 8})
        self.assertEqual(self.slot_pools(actor),
                         [("dnd2024.slot.spellcasting.1", 4, 4),
                          ("dnd2024.slot.spellcasting.2", 3, 3),
                          ("dnd2024.slot.spellcasting.3", 3, 3)])
        # 豁免熟练只来自牧师（感知/魅力），不带法师的智力/感知
        self.assertEqual(self.proficient_saves(actor), ["cha", "wis"])
        # HP：牧师 d8 体+2 = 10；法师 5×(3+1+2) = 30
        self.assertEqual(self.sheet(actor)["hp"]["maximum"], 40)

    def test_barbarian3_fighter2(self):
        """狂暴按野蛮人 3 级（3 次）；行动激增可用；无甲防御用野蛮人公式。"""
        actor = self.make(BARBARIAN, 3, [(FIGHTER, 2)], HEROIC)
        sheet = self.sheet(actor)
        self.assertEqual((self.pool(actor, "dnd2024.resource.barbarian.rage")["max"]), 3)
        self.assertTrue(any(row["id"].endswith("action_surge")
                            for row in sheet["powers"]))
        self.assertEqual(sheet["hp"]["maximum"], 48)          # (12+2)+2×9 + 2×8
        self.assertEqual(sheet["ac"]["total"], 14)            # 10+敏2+体2
        self.assertEqual(self.proficient_saves(actor), ["con", "str"])

    def test_rogue3_monk2(self):
        """气 = 武僧等级（2）；AC 用武僧的无甲防御；豁免只看游荡者。"""
        actor = self.make(ROGUE, 3, [(MONK, 2)], SKIRMISHER)
        sheet = self.sheet(actor)
        self.assertEqual(self.pool(actor, "dnd2024.resource.monk.focus")["max"], 2)
        self.assertEqual(sheet["ac"]["total"], 14)            # 10+敏2+感2（无盾）
        self.assertEqual(self.proficient_saves(actor), ["dex", "int"])
        # HP：游荡者 d8 体+1 = 9 + 2×6；武僧 2×6 → 33
        self.assertEqual(sheet["hp"]["maximum"], 33)

    def test_wizard5_sorcerer1(self):
        """合并表 6 级 = 4/3/3；术法点 = 术士等级（1），不是总等级。"""
        actor = self.make(WIZARD, 5, [(SORCERER, 1)], ARCANE)
        self.assertEqual(self.slot_pools(actor),
                         [("dnd2024.slot.spellcasting.1", 4, 4),
                          ("dnd2024.slot.spellcasting.2", 3, 3),
                          ("dnd2024.slot.spellcasting.3", 3, 3)])
        self.assertEqual(self.pool(actor, "dnd2024.resource.sorcerer.sorcery")["max"], 1)
        # HP：法师 d6 体+2 = 8 + 4×6；术士 d6 1×6 → 38
        self.assertEqual(self.sheet(actor)["hp"]["maximum"], 38)


class PrereqTest(Base):
    def test_wizard_needs_intelligence(self):
        with self.assertRaises(RuleError) as caught:
            self.make(FIGHTER, 5, [(WIZARD, 3)],
                      {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 10, "cha": 8})
        self.assertIn("INT 10 < 13", str(caught.exception))

    def test_monk_needs_both_dex_and_wis(self):
        with self.assertRaises(RuleError) as caught:
            self.make(ROGUE, 3, [(MONK, 2)],
                      {"str": 10, "dex": 14, "con": 12, "int": 10, "wis": 12, "cha": 8})
        self.assertIn("WIS 12 < 13", str(caught.exception))

    def test_fighter_accepts_either_str_or_dex(self):
        """战士的前置是「力量或敏捷 13」—— 敏捷型也能进。"""
        actor = self.make(WIZARD, 5, [(FIGHTER, 1)],
                          {"str": 8, "dex": 16, "con": 14, "int": 14, "wis": 10, "cha": 8})
        self.assertEqual(len(actor.profile.classes), 2)

    def test_first_class_has_no_prereq(self):
        """起始职业不吃前置：敏捷 8 的野蛮人当第一职业合法（规则如此）。"""
        actor = self.make(BARBARIAN, 1, [],
                          {"str": 16, "dex": 6, "con": 14, "int": 10, "wis": 10, "cha": 8})
        self.assertEqual(actor.profile.classes[0].class_id, BARBARIAN)


class HpSegmentTest(Base):
    def test_only_the_first_class_gets_max_die_at_level_one(self):
        """兼职职业的 1 级取固定值，不是满骰 —— 算满骰会白送起始 HP。"""
        actor = self.make(BARBARIAN, 1, [(FIGHTER, 1)], HEROIC)
        # 野蛮人 1 级满骰：12+2；战士 1 级固定：5+1+2 → 22（算满骰会是 26）
        self.assertEqual(self.sheet(actor)["hp"]["maximum"], 22)

    def test_three_segments(self):
        actor = self.make(FIGHTER, 8, [(WIZARD, 3), (ROGUE, 2)],
                          {"str": 16, "dex": 14, "con": 14, "int": 14, "wis": 10, "cha": 8})
        # 战士：(10+2) + 7×8 = 68；法师 3×6 = 18；游荡者 d8 体+2 2×7 = 14 → 100
        self.assertEqual(self.sheet(actor)["hp"]["maximum"], 100)
        self.assertEqual([item.class_id for item in actor.profile.classes],
                         [FIGHTER, WIZARD, ROGUE])

    def test_total_level_cap(self):
        with self.assertRaises(RuleError) as caught:
            self.make(FIGHTER, 18, [(WIZARD, 3)], HEROIC)
        self.assertIn("总等级超过上限", str(caught.exception))

    def test_duplicate_class_rejected(self):
        with self.assertRaises(RuleError) as caught:
            self.make(FIGHTER, 5, [(FIGHTER, 3)], HEROIC)
        self.assertIn("登记了两次", str(caught.exception))


class UnarmoredDefenseTest(Base):
    """§12.3：同类公式不叠加 —— 互斥组取较高的一条。"""

    def make_barb_monk(self, con, wis):
        # 感知必须 ≥ 13：这是武僧的兼职前置，不满足根本建不出这个组合
        assert wis >= 13
        return self.make(BARBARIAN, 1, [(MONK, 1)],
                         {"str": 14, "dex": 14, "con": con, "int": 8,
                          "wis": wis, "cha": 8})

    def test_takes_the_better_formula(self):
        # 体 16(+3) 感 14(+2)：野蛮人公式更好 → 10+2+3 = 15，不是 10+2+3+2
        self.assertEqual(self.sheet(self.make_barb_monk(16, 14))["ac"]["total"], 15)

    def test_takes_the_better_formula_either_way(self):
        # 体 8(-1) 感 16(+3)：武僧公式更好 → 10+2+3 = 15（与职业顺序无关）
        self.assertEqual(self.sheet(self.make_barb_monk(8, 16))["ac"]["total"], 15)

    def test_shield_disables_only_the_monk_formula(self):
        """武僧的公式要求无盾，野蛮人的不要求：持盾时只剩野蛮人那条。"""
        from dnd5r.model.inventory import EquipSlot
        actor = self.make_barb_monk(8, 16)
        actor.inventory.equip(EquipSlot.SHIELD, "dnd2024.item.armor.shield")
        # 有盾：AC = 10 + 敏2 + 体(-1) + 盾2 = 13（武僧条款因持盾失效）
        self.assertEqual(self.sheet(actor)["ac"]["total"], 13)


class SlotsBehaviorTest(Base):
    def test_merged_slots_are_spendable(self):
        """合并位池真的能花：按环级挑最低的扣（§14.24 位不认职业）。"""
        from dnd5r.rules.spellcasting import lowest_slot, spend_slot
        actor = self.make(WIZARD, 5, [(SORCERER, 1)], ARCANE)
        self.assertEqual(lowest_slot(actor, 1), 1)
        spend_slot(actor, 1)
        self.assertEqual(self.pool(actor, "dnd2024.slot.spellcasting.1")["left"], 3)

    def test_single_class_slots_unchanged(self):
        """单职业的位池 id / owner / 数量与 P5a 起完全一致（golden 层 0 的口径）。"""
        actor = api.new_character(self.bundle, WIZARD, 5, ARCANE,
                                  name_zh="法师", name_en="Wizard")
        self.assertEqual(self.slot_pools(actor),
                         [("dnd2024.slot.wizard.1", 4, 4),
                          ("dnd2024.slot.wizard.2", 3, 3),
                          ("dnd2024.slot.wizard.3", 2, 2)])

    def test_progression_table_matches_the_full_caster_table(self):
        """DataFidelity：合并表 == 全职表（规则里它就是同一张表，抄错会静默错位）。"""
        from dnd5r.model.levels import ClassLevel
        wizard = self.bundle.classes[WIZARD]
        progression = self.bundle.caster_progression
        for level in range(1, 21):
            own = wizard.slots_at(ClassLevel(level))
            merged = tuple(progression.get(level, {}).get(slot, 0)
                           for slot in range(1, len(own) + 1))
            self.assertEqual(own, merged, "第 %d 级：合并表 %s != 法师表 %s"
                             % (level, merged, own))


class RoundTripTest(Base):
    def test_save_and_load(self):
        actor = self.make(FIGHTER, 5, [(WIZARD, 3)], HEROIC)
        actor.hp.damage(9)
        data = api.save_character(actor)
        loaded = api.load_character(self.bundle, data)
        sheet_old, sheet_new = self.sheet(actor), self.sheet(loaded)
        self.assertEqual(sheet_new["classes"], sheet_old["classes"])
        self.assertEqual(sheet_new["hp"]["maximum"], sheet_old["hp"]["maximum"])
        self.assertEqual(sheet_new["hp"]["current"], sheet_old["hp"]["current"])
        self.assertEqual(self.slot_pools(loaded), self.slot_pools(actor))

    def test_rebuild_keeps_runtime_state(self):
        actor = self.make(BARBARIAN, 3, [(FIGHTER, 2)], HEROIC)
        actor.hp.damage(7)
        fresh = api.rebuild_actor(self.bundle, actor)
        self.assertEqual([item.class_id for item in fresh.profile.classes],
                         [BARBARIAN, FIGHTER])
        self.assertEqual(fresh.hp.maximum, actor.hp.maximum)
        self.assertEqual(fresh.hp.current, actor.hp.current)


if __name__ == "__main__":
    unittest.main()
