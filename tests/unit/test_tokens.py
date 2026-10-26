# -*- coding: utf-8 -*-
"""P13b 验收：GrantToken（目标通道）+ 诗人灵感（G30 结清）。

期望值全部从 SRD 5.2 原文推导（bard.yaml 里存了英文原文，与本组断言同源）。

盯八件事：

  1. 附赠动作、花一次灵感次数（次数 = 魅力调整值，至少 1）；
  2. 只能给别人（原文 another creature），给自己当场拒绝；
  3. 骰面按诗人等级 d6/d8/d10/d12（5/10/15 级跳档），授予那一刻定死；
  4. 同时只能持有一颗：再授一颗 = 替换，不是两颗；
  5. 受益者掷 d20 检定时可加骰（玩家显式要求才加），骰值进合计，用完即消；
  6. 没骰却要求加 = 报错；预览（不加）时骰保留；
  7. 距离：双方都摆位才判 60 尺，没摆位放过（宁可放过不误拦）；
  8. rest 作用域：一次休息（短/长）后骰消失（「一小时」的引擎近似）。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import DndError
from dnd5r.kernel.rng import ScriptedRng

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

BARD = "dnd2024.class.bard"
INSPIRATION = "dnd2024.class.bard.bardic_inspiration"
FONT = "dnd2024.class.bard.font_of_inspiration"
INSPIRATION_POOL = "dnd2024.resource.bard.inspiration"

BARD_SCORES = {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 14}
HERO_SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 10, "cha": 8}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def pair(self, bard_level=1):
        bard = api.new_character(self.bundle, BARD, bard_level, BARD_SCORES,
                                 name_zh="诗人", name_en="Bard", actor_id="pc.bard")
        hero = api.new_character(self.bundle, "dnd2024.class.fighter", 3,
                                 HERO_SCORES, name_zh="战士", name_en="Fighter")
        encounter = api.new_encounter([bard, hero], rng=ScriptedRng([10, 15]))
        guard = 0
        while encounter.current().actor is not bard and guard < 4:
            api.advance_turn(encounter)
            guard += 1
        return bard, hero, encounter

    def inspire(self, bard, encounter, target_id="pc.hero", rng=None):
        return api.use_power(bard, self.bundle, INSPIRATION,
                             rng=rng or ScriptedRng([7]),
                             choice={"target_id": target_id},
                             encounter=encounter)

    def pool_row(self, actor, pool_id):
        return next(row for row in api.character_sheet(actor, self.bundle)["pools"]
                    if row["id"] == pool_id)


class GrantTest(Base):
    def test_grant_costs_a_use_and_gives_the_die(self):
        bard, hero, encounter = self.pair()
        before = self.pool_row(bard, INSPIRATION_POOL)["left"]
        out = self.inspire(bard, encounter)
        self.assertTrue(out["ok"], out["message"])
        self.assertEqual(self.pool_row(bard, INSPIRATION_POOL)["left"], before - 1)
        tokens = api.tokens_of(hero)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0]["dice"], "1d6")        # 1 级 = d6

    def test_uses_equal_charisma_mod_minimum_one(self):
        bard, hero, _ = self.pair()
        self.assertEqual(self.pool_row(bard, INSPIRATION_POOL)["max"], 2)  # 魅力 14
        meek = api.new_character(
            self.bundle, BARD, 1,
            {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 8},
            name_zh="怯诗人", name_en="Meek Bard")
        self.assertEqual(self.pool_row(meek, INSPIRATION_POOL)["max"], 1)  # 至少 1

    def test_cannot_grant_to_self(self):
        bard, _hero, encounter = self.pair()
        out = self.inspire(bard, encounter, target_id="pc.bard")
        self.assertFalse(out["ok"])
        self.assertIn("不能给自己", out["message"])

    def test_die_scales_with_bard_level(self):
        for level, dice in ((5, "1d8"), (10, "1d10"), (15, "1d12")):
            bard, hero, encounter = self.pair(bard_level=level)
            out = self.inspire(bard, encounter)
            self.assertTrue(out["ok"], out["message"])
            self.assertEqual(api.tokens_of(hero)[0]["dice"], dice)

    def test_one_die_at_a_time_replaces(self):
        """原文 A creature can have only one Bardic Inspiration die at a time。"""
        from dnd5r.rules.actioneconomy import ActionEconomy
        bard, hero, encounter = self.pair()
        self.inspire(bard, encounter)                       # 第一次
        out = api.use_power(bard, self.bundle, INSPIRATION,
                            rng=ScriptedRng([7]), choice={"target_id": "pc.hero"},
                            encounter=encounter, economy=ActionEconomy())
        # 第二次（独立额度，只验「替换不叠加」）
        self.assertTrue(out["ok"], out["message"])
        self.assertEqual(len(api.tokens_of(hero)), 1)
        self.assertEqual(self.pool_row(bard, INSPIRATION_POOL)["left"], 0)  # 两次都花

    def test_range_checked_only_when_both_placed(self):
        bard, hero, encounter = self.pair()
        api.place_combatant(encounter, bard, 0, 0)
        api.place_combatant(encounter, hero, 9, 9)          # 切比雪夫 9 格 = 45 尺
        out = self.inspire(bard, encounter)
        self.assertTrue(out["ok"], out["message"])          # 45 尺 ≤ 60 尺
        api.place_combat(encounter if False else encounter, hero, 0, 0) if False else api.place_combatant(encounter, hero, 12, 0)
        # 地图只有 10 格，直接挪出界：用 9,9 vs 0,0 是 45 尺；再造一个更远的对照
        bard2, hero2, enc2 = self.pair()
        api.place_combatant(enc2, bard2, 0, 0)
        hero2_row = enc2.get(hero2)
        hero2_row.x, hero2_row.y, hero2_row.placed = 20, 0, True   # 100 尺外
        out2 = self.inspire(bard2, enc2)
        self.assertFalse(out2["ok"])
        self.assertIn("超出 60 尺", out2["message"])

    def test_no_encounter_says_so(self):
        bard = api.new_character(self.bundle, BARD, 1, BARD_SCORES,
                                 name_zh="诗人", name_en="Bard", actor_id="pc.bard")
        out = api.use_power(bard, self.bundle, INSPIRATION,
                            rng=ScriptedRng([7]),
                            choice={"target_id": "pc.hero"}, encounter=None)
        self.assertTrue(out["ok"], out["message"])
        self.assertIn("未结算", out["message"])


class ConsumeTest(Base):
    def test_die_adds_to_total_and_is_spent(self):
        bard, hero, encounter = self.pair()
        self.inspire(bard, encounter)
        # 战士运动检定：d20=5 + 修正 +3 + 灵感骰 4 → 报告能对上账
        result = api.roll_check(hero, self.bundle, "skill", "athletics",
                                rng=ScriptedRng([5, 4]), use_inspiration=True)
        self.assertEqual(result["die"], 5)
        self.assertEqual(result["inspiration"]["roll"], 4)
        self.assertEqual(result["total"], 5 + 3 + 4)
        self.assertEqual(api.tokens_of(hero), [])           # 用完即消

    def test_preview_keeps_the_die(self):
        bard, hero, encounter = self.pair()
        self.inspire(bard, encounter)
        result = api.roll_check(hero, self.bundle, "skill", "athletics",
                                rng=ScriptedRng([5]))
        self.assertIsNone(result["inspiration"])
        self.assertEqual(len(api.tokens_of(hero)), 1)       # 只列不扣
        self.assertEqual(result["tokens_pending"][0]["dice"], "1d6")

    def test_no_die_is_an_error(self):
        bard, hero, encounter = self.pair()
        with self.assertRaises(api.RuleError):
            api.roll_check(hero, self.bundle, "skill", "athletics",
                           rng=ScriptedRng([5]), use_inspiration=True)

    def test_die_survives_turn_but_not_a_rest(self):
        """「一小时内」的引擎近似：回合推进不清，休息清。"""
        from dnd5r.session import Session
        session = Session(self.bundle, seed=9)
        bard = session.create_character(BARD, 1, BARD_SCORES, actor_id="pc.bard")
        hero = api.new_character(self.bundle, "dnd2024.class.fighter", 3,
                                 HERO_SCORES, name_zh="战士", name_en="Fighter")
        session.start_encounter([hero], rng=ScriptedRng([10, 15]))
        # 推到诗人回合再授予
        guard = 0
        while session.encounter.current().actor is not bard and guard < 4:
            session.dispatch(api.NewTurn())
            guard += 1
        session._use_power(INSPIRATION, {"target_id": hero.id})
        self.assertEqual(len(api.tokens_of(hero)), 1)
        session.dispatch(api.NewTurn())                     # 回合推进
        session.dispatch(api.NewTurn())
        self.assertEqual(len(api.tokens_of(hero)), 1)       # 还在
        # 休息清的是**持骰人**的 rest 作用域：战士自己长休，骰就没了
        from dnd5r.rules.rest import long_rest
        long_rest(hero)
        self.assertEqual(api.tokens_of(hero), [])           # 休息即消


class FontOfInspirationTest(Base):
    """5 级灵感泉源：花任意一个法术位回一次灵感（2024 原文 no action required）。"""

    def test_slot_buys_back_one_use(self):
        bard = api.new_character(self.bundle, BARD, 5, BARD_SCORES,
                                 name_zh="诗人", name_en="Bard")
        pool = bard.root().resources.get(INSPIRATION_POOL)
        pool.spend(2)                                       # 2/2 → 0/2
        out = api.use_power(bard, self.bundle, FONT,
                            rng=ScriptedRng([3]), choice={"slot_level": 2})
        self.assertTrue(out["ok"], out["message"])
        self.assertEqual(pool.available, 1)                 # 回 1，不是回 2
        self.assertEqual(bard.root().resources.get("engine.slot.bard.2").available,
                         2)                                 # 3 − 1

    def test_short_rest_recharge_not_modeled(self):
        """池的 refresh 建池时定死（长休）；短休恢复的升级记 note 未建模 —— 测试钉住
        这条边界，将来谁建了 refresh 补丁通道，把这条改成短休也回满。"""
        from dnd5r.session import ShortRest
        bard, _hero, _enc = self.pair(bard_level=5)
        bard.root().resources.get(INSPIRATION_POOL).spend(1)
        from dnd5r.session import Session
        session = Session(self.bundle, seed=4)
        session.actor = bard
        session.dispatch(ShortRest())
        self.assertEqual(bard.root().resources.get(INSPIRATION_POOL).available, 1)


if __name__ == "__main__":
    unittest.main()
