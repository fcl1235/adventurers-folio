# -*- coding: utf-8 -*-
"""P13 验收：结算后修正 / 兑换 / 召唤 三个原语（G27 的三缺）。

期望值从规则原文推导。GrantToken（诗人灵感）不在这里 —— 它要「把效果
交给另一个角色」的目标通道，等有了目标模型再做（G30，见 §14.34）。

盯三组事：

  1. 可靠天赋（OverrideOutcome）：熟练的技能/工具检定 d20 ≤ 9 按 10 计；
     不熟练不吃、高面不吃、没到 7 级不吃；报告里要写明「按 10 计」。
  2. 魔法源泉（Exchange）：位→点（等量、无动作）；点→位（按表、附赠动作、
     长休**蒸发**、有最低术士等级门槛）；点不够一位不扣；造出的位真能花。
  3. 召唤（Summon）：施法 apply 后生物真的进遭遇战 —— 我方阵营、AC/HP
     与法术详情同一套数、动作表走怪物同一条结算；预览不入場；没有遭遇战
     就明说未结算。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import DndError
from dnd5r.kernel.rng import ScriptedRng

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

ROGUE = "dnd2024.class.rogue"
SORCERER = "dnd2024.class.sorcerer"
WIZARD = "dnd2024.class.wizard"
SORCERY = "dnd2024.resource.sorcerer.sorcery"
CREATE_SLOT = "dnd2024.class.sorcerer.create_spell_slot"
CONVERT_SLOT = "dnd2024.class.sorcerer.convert_slot_to_points"
SUMMON_DRAGON = "dnd2024.spell.summon_dragon"

ROGUE_SCORES = {"str": 10, "dex": 16, "con": 12, "int": 10, "wis": 10, "cha": 8}
SORC_SCORES = {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 16}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors


class ReliableTalentTest(Base):
    """原文：凡用到技能或工具熟练的属性检定，d20 掷出 9 或更低按 10 计。"""

    def rogue(self, level=7):
        actor = api.new_character(self.bundle, ROGUE, level, ROGUE_SCORES,
                                  name_zh="游荡者", name_en="Rogue")
        # 游荡者的技能是建卡自选的，这里按「选了隐匿」处理 —— 熟练与否正是本组测试的变量
        import dataclasses
        actor.profile = dataclasses.replace(
            actor.profile,
            proficiencies=actor.profile.proficiencies | {"skill.stealth"})
        return actor

    def test_proficient_low_roll_floor(self):
        result = api.roll_check(self.rogue(), self.bundle, "skill", "stealth",
                                rng=ScriptedRng([5]))
        self.assertEqual(result["die_raw"], 5)
        self.assertEqual(result["die"], 10)
        self.assertEqual(result["total"], 10 + result["modifier"])
        self.assertTrue(any("按 10 计" in note for note in result["notes"]))

    def test_non_proficient_check_untouched(self):
        result = api.roll_check(self.rogue(), self.bundle, "skill", "arcana",
                                rng=ScriptedRng([5]))
        self.assertEqual(result["die"], 5)

    def test_high_roll_untouched(self):
        result = api.roll_check(self.rogue(), self.bundle, "skill", "stealth",
                                rng=ScriptedRng([15]))
        self.assertEqual(result["die"], 15)
        self.assertEqual(result["notes"], [])

    def test_below_level_seven_has_no_floor(self):
        result = api.roll_check(self.rogue(level=6), self.bundle, "skill", "stealth",
                                rng=ScriptedRng([5]))
        self.assertEqual(result["die"], 5)

    def test_saving_throw_untouched(self):
        """原文只管属性检定（技能/工具熟练），豁免与攻击不吃保底。"""
        result = api.roll_check(self.rogue(), self.bundle, "save", "dex",
                                rng=ScriptedRng([3]))
        self.assertEqual(result["die"], 3)
        self.assertEqual(result["notes"], [])


class ExchangeTest(Base):
    """2024 魔法源泉：位→点等量无动作；点→位按表、长休蒸发、有等级门槛。"""

    def sorcerer(self, level=5):
        return api.new_character(self.bundle, SORCERER, level, SORC_SCORES,
                                 name_zh="术士", name_en="Sorcerer")

    def pools(self, actor):
        return {row["id"]: (row["left"], row["max"])
                for row in api.character_sheet(actor, self.bundle)["pools"]}

    def test_create_slot_spends_points(self):
        """5 级术士 5 点：造 1 环位花 2 点，得一个「长休消失」的独立位池。"""
        actor = self.sorcerer(5)
        out = api.use_power(actor, self.bundle, CREATE_SLOT, seed=1,
                            choice={"slot_level": 1})
        self.assertTrue(out["ok"], out["message"])
        pools = self.pools(actor)
        self.assertEqual(pools[SORCERY], (3, 5))            # 5 − 2
        self.assertEqual(pools["engine.slot.created.1"], (1, 1))

    def test_created_slot_is_spendable(self):
        """造出来的位真的能花：职业位耗尽后，花的就是创造的位。"""
        from dnd5r.rules.spellcasting import lowest_slot, spend_slot
        actor = self.sorcerer(5)
        for _ in range(4):                      # 5 级术士 4 个 1 环职业位，全花光
            spend_slot(actor, 1)
        api.use_power(actor, self.bundle, CREATE_SLOT, seed=1,
                      choice={"slot_level": 1})
        self.assertEqual(lowest_slot(actor, 1), 1)   # 现在唯一的 1 环来自创造的位
        spend_slot(actor, 1)
        self.assertEqual(self.pools(actor)["engine.slot.created.1"], (0, 1))

    def test_created_slots_vanish_on_long_rest(self):
        """原文 "vanishes when you finish a Long Rest"：整池蒸发，不是回满。"""
        from dnd5r.session import LongRest, Session
        session = Session(self.bundle, seed=3)
        session.create_character(SORCERER, 5, SORC_SCORES)
        session.dispatch(api.UsePower(CREATE_SLOT, {"slot_level": 1}))
        self.assertIn("engine.slot.created.1", self.pools(session.character))
        session.dispatch(LongRest())
        self.assertNotIn("engine.slot.created.1",
                         {row["id"] for row in
                          api.character_sheet(session.character, self.bundle)["pools"]})
        self.assertEqual(self.pools(session.character)[SORCERY], (5, 5))

    def test_minimum_level_gate(self):
        """3 环位要术士 5 级起：3 级术士造 3 环直接拒绝，点不扣。"""
        actor = self.sorcerer(3)
        out = api.use_power(actor, self.bundle, CREATE_SLOT, seed=1,
                            choice={"slot_level": 3})
        self.assertFalse(out["ok"])
        self.assertIn("术士等级 5 起", out["message"])
        self.assertEqual(self.pools(actor)[SORCERY], (3, 3))   # 一点没扣

    def test_insufficient_points_refuses(self):
        """5 级只剩 1 点时造 2 环位（要 3 点）：拒绝且不扣。"""
        actor = self.sorcerer(5)
        actor.root().resources.get(SORCERY).spend(4)
        out = api.use_power(actor, self.bundle, CREATE_SLOT, seed=1,
                            choice={"slot_level": 2})
        self.assertFalse(out["ok"])
        self.assertIn("术法点剩 1", out["message"])
        self.assertEqual(self.pools(actor)[SORCERY], (1, 5))

    def test_slot_to_points(self):
        """烧一个 2 环位得 2 点：等量、上限不破。"""
        actor = self.sorcerer(5)
        out = api.use_power(actor, self.bundle, CONVERT_SLOT, seed=1,
                            choice={"slot_level": 2})
        self.assertTrue(out["ok"], out["message"])
        pools = self.pools(actor)
        self.assertEqual(pools[SORCERY], (5, 5))             # 3 + 2 = 5（正好顶满）
        self.assertEqual(pools["engine.slot.sorcerer.2"], (2, 3))   # 3 − 1

    def test_slot_to_points_needs_that_level(self):
        actor = self.sorcerer(5)
        out = api.use_power(actor, self.bundle, CONVERT_SLOT, seed=1,
                            choice={"slot_level": 5})        # 5 级没有 5 环位
        self.assertFalse(out["ok"])

    def test_missing_choice_is_an_error(self):
        out = api.use_power(self.sorcerer(5), self.bundle, CONVERT_SLOT, seed=1)
        self.assertFalse(out["ok"])
        self.assertIn("选一个环级", out["message"])


class SummonTest(Base):
    """施法 → 生物入場。AC/HP 与法术详情（summon.card）同一套数。"""

    def wizard_encounter(self):
        wizard = api.new_character(
            self.bundle, WIZARD, 9,
            {"str": 10, "dex": 14, "con": 14, "int": 18, "wis": 10, "cha": 8},
            name_zh="法师", name_en="Wizard")
        foe = api.spawn_monster(self.bundle, "dnd2024.monster.wolf")
        encounter = api.new_encounter([wizard, foe], rng=ScriptedRng([10, 15]))
        guard = 0
        while encounter.current().actor is not wizard and guard < 4:
            api.advance_turn(encounter)
            guard += 1
        return wizard, foe, encounter

    def test_casting_joins_the_summon(self):
        wizard, foe, encounter = self.wizard_encounter()
        before = len(encounter.combatants)
        result = api.roll_spell(wizard, self.bundle, SUMMON_DRAGON,
                                targets=[foe], rng=ScriptedRng([11, 6, 6]),
                                apply=True, encounter=encounter)
        self.assertEqual(len(encounter.combatants), before + 1)
        body = result["summon"]
        # 5 环的龙之精魂：AC 14+5=19，HP 50（与 P8b 的英文原文明细同源）
        self.assertEqual(body["ac"], 19)
        self.assertEqual(body["hp"], 50)
        self.assertEqual(body["side"], "party")              # 替施法者打仗
        row = next(item for item in api.encounter_view(encounter, self.bundle)["order"]
                   if item["id"] == body["id"])
        self.assertEqual(row["hp"]["current"], 50)

    def test_preview_does_not_join(self):
        wizard, foe, encounter = self.wizard_encounter()
        before = len(encounter.combatants)
        api.roll_spell(wizard, self.bundle, SUMMON_DRAGON, targets=[foe],
                       rng=ScriptedRng([11]), apply=False, encounter=encounter)
        self.assertEqual(len(encounter.combatants), before)

    def test_no_encounter_says_so(self):
        wizard, foe, _ = self.wizard_encounter()
        result = api.roll_spell(wizard, self.bundle, SUMMON_DRAGON,
                                targets=[foe], rng=ScriptedRng([11]),
                                apply=True, encounter=None)
        self.assertTrue(any("召唤未结算" in note for note in result["notes"]))
        self.assertNotIn("summon", result)

    def test_summon_acts_with_its_own_table(self):
        """入場的召唤物用它自己的动作打人 —— 与怪物同一条结算（attack: spell
        = 施法者的法术攻击加值，入場时算好挂在身上）。"""
        wizard, foe, encounter = self.wizard_encounter()
        result = api.roll_spell(wizard, self.bundle, SUMMON_DRAGON,
                                targets=[foe], rng=ScriptedRng([11, 6, 6]),
                                apply=True, encounter=encounter)
        body = next(item.actor for item in encounter.combatants
                    if item.id == result["summon"]["id"])
        guard = 0
        while encounter.current().actor is not body and guard < 6:
            api.advance_turn(encounter)
            guard += 1
        # 动作表：0 多重攻击（说明）1 撕裂（近战）2 吐息（豁免）—— 打的是 1
        hit = api.monster_attack(encounter, self.bundle, body, "action:1", foe,
                                 rng=ScriptedRng([12, 3, 3]), apply=True)
        # 法师 9 级（熟练 +4、智力 +4）→ 法术攻击 +8；动作表带得对就能掷
        self.assertEqual(hit["attack"]["bonus"], 8)
        self.assertEqual(hit["outcome"], "hit")
        self.assertLess(foe.hp.current, foe.hp.maximum)

    def test_variants_are_selectable(self):
        """巨虫三选一（德鲁伊法术）：缺省取第一只，summon_id 能换，报告里写明可选项。"""
        druid = api.new_character(
            self.bundle, "dnd2024.class.druid", 9,
            {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 18, "cha": 8},
            name_zh="德鲁伊", name_en="Druid")
        foe = api.spawn_monster(self.bundle, "dnd2024.monster.wolf")
        encounter = api.new_encounter([druid, foe], rng=ScriptedRng([10, 15]))
        guard = 0
        while encounter.current().actor is not druid and guard < 4:
            api.advance_turn(encounter)
            guard += 1
        result = api.roll_spell(druid, self.bundle, "dnd2024.spell.giant_insect",
                                slot=4, targets=[foe], rng=ScriptedRng([11, 6, 6]),
                                apply=True, encounter=encounter,
                                summon_id="dnd2024.summon.giant_insect_spider")
        self.assertEqual(result["summon"]["id"], "dnd2024.summon.giant_insect_spider")
        self.assertIn("dnd2024.summon.giant_insect_centipede",
                      result["summon"]["options"])


if __name__ == "__main__":
    unittest.main()
