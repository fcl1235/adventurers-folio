# -*- coding: utf-8 -*-
"""会话：命令只发意图，剧本端到端。

P11（§14.32）之后 Session 是「CLI 剧本壳」：**没有自己的投影**（原先那套
Card 与 `api.character_sheet` 各算一遍 AC / 攻击，已删，G24 的正解）。
要看角色就读 sheet，同一个数只有一个算法。

这里同时是一条端到端剧本：建 1 级战士 → 回气 → 短休 → 再回气 → 长休。
全程没有一行 UI 代码，能跑通就说明后端真的独立。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.session import (
    LongRest,
    NewTurn,
    Regain,
    Session,
    ShortRest,
    TakeDamage,
    UsePower,
)

ROOT = Path(__file__).resolve().parents[2]
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
FIGHTER = "dnd2024.class.fighter"
SECOND_WIND = "dnd2024.class.fighter.second_wind"
SECOND_WIND_POOL = "dnd2024.resource.fighter.second_wind"


def make_session(level=1, seed=5) -> Session:
    session = Session.open(str(ROOT / "plugins"), seed=seed)
    session.create_character(FIGHTER, level, SCORES, "测试战士", "Test Fighter")
    return session


def sheet(session: Session) -> dict:
    """角色卡只有一份：api.character_sheet。这里只是顺手包装。"""
    return api.character_sheet(session.character, session.bundle, session.locale)


def pool_of(session: Session, pool_id: str) -> dict:
    return next(row for row in sheet(session)["pools"] if row["id"] == pool_id)


def power_of(session: Session, power_id: str) -> dict:
    return next(row for row in sheet(session)["powers"] if row["id"] == power_id)


class SessionSheetTest(unittest.TestCase):
    """投影只有一份：Session 的角色卡就是 api.character_sheet。"""

    def test_header_numbers(self):
        data = sheet(make_session())
        self.assertEqual(data["name"], "测试战士")
        self.assertEqual(data["total_level"], 1)
        self.assertEqual(data["hp"]["maximum"], 12)
        self.assertEqual(data["ac"]["total"], 12)
        self.assertEqual(data["proficiency_bonus"], 2)
        self.assertEqual([(row["name"], row["class_level"]) for row in data["classes"]],
                         [("战士", 1)])

    def test_powers_and_pools_present(self):
        data = sheet(make_session())
        ids = {row["id"] for row in data["powers"]}
        self.assertIn(SECOND_WIND, ids)
        pool_ids = {row["id"] for row in data["pools"]}
        self.assertIn(SECOND_WIND_POOL, pool_ids)
        # 生命骰单独放在 hp 块里（pools 只列非骰池）
        self.assertEqual([row["id"] for row in data["hp"]["hit_dice"]],
                         ["hit_dice.%s" % FIGHTER])

    def test_locale_affects_sheet(self):
        session = Session.open(str(ROOT / "plugins"), locale="en", seed=5)
        session.create_character(FIGHTER, 1, SCORES, "测试战士", "Test Fighter")
        data = sheet(session)
        self.assertEqual(data["name"], "Test Fighter")
        self.assertIn("Second Wind", {row["name"] for row in data["powers"]})

    def test_attack_numbers(self):
        data = sheet(make_session(level=20))
        self.assertEqual(data["attacks_per_action"], 4)      # 20 级战士四打
        self.assertEqual(data["attack"]["total"], 9)          # 力量 +3 + 熟练 +6

    def test_sheet_is_plain_dict(self):
        """前端拿到的是可 JSON 化的 dict —— 这就是契约本身。"""
        import json

        data = sheet(make_session())
        json.dumps(data, ensure_ascii=False)   # 不抛就行


class EndToEndTest(unittest.TestCase):
    def test_fighter_second_wind_then_short_rest(self):
        session = make_session()
        actor = session.character

        # 先掉血，否则回气看不出效果
        report = session.dispatch(TakeDamage(9))
        self.assertTrue(report.ok)
        self.assertEqual(actor.hp.current, 3)

        # 回气：1d10 + 战士等级（1）→ 至少 2 点；附赠动作花掉、次数 2→1
        report = session.dispatch(UsePower(SECOND_WIND))
        self.assertTrue(report.ok)
        self.assertGreater(actor.hp.current, 3)
        self.assertEqual(session.economy.bonus, 0)
        self.assertEqual(pool_of(session, SECOND_WIND_POOL)["left"], 1)

        # 短休恢复 1 次
        report = session.dispatch(ShortRest())
        self.assertTrue(report.ok)
        self.assertIn("second_wind", report.message)
        self.assertEqual(pool_of(session, SECOND_WIND_POOL)["left"], 2)

        # 新回合恢复附赠动作，能力又能用
        report = session.dispatch(NewTurn())
        self.assertTrue(report.ok)
        self.assertEqual(session.economy.bonus, 1)

    def test_short_rest_spends_hit_dice(self):
        session = make_session()
        actor = session.character
        session.dispatch(TakeDamage(10))
        report = session.dispatch(ShortRest(dice=1))
        self.assertGreater(actor.hp.current, 2)
        self.assertIn("生命骰", report.message)

    def test_long_rest_resets_everything(self):
        session = make_session(level=9)
        actor = session.character
        session.dispatch(TakeDamage(50))
        session.dispatch(UsePower(SECOND_WIND))
        report = session.dispatch(LongRest())
        self.assertEqual(actor.hp.current, actor.hp.maximum)
        self.assertIn("资源回满", report.message)
        self.assertEqual(pool_of(session, "dnd2024.resource.fighter.indomitable")["left"], 1)

    def test_unknown_command(self):
        session = make_session()
        report = session.dispatch("做个三明治")
        self.assertFalse(report.ok)
        self.assertIn("不认识的命令", report.message)

    def test_unknown_power(self):
        session = make_session()
        report = session.dispatch(UsePower("dnd2024.class.fighter.nope"))
        self.assertFalse(report.ok)

    def test_exhausted_power_is_blocked(self):
        """两次用完 2 次回气后再点，应报资源不足；每回合都要先恢复附赠动作。"""
        session = make_session()
        for _ in range(2):
            session.dispatch(NewTurn())
            report = session.dispatch(UsePower(SECOND_WIND))
            self.assertTrue(report.ok, report.message)
        session.dispatch(NewTurn())
        report = session.dispatch(UsePower(SECOND_WIND))
        self.assertFalse(report.ok)
        self.assertIn("不足", report.message)

    def test_regain(self):
        session = make_session()
        actor = session.character
        session.dispatch(TakeDamage(5))
        report = session.dispatch(Regain(3))
        self.assertTrue(report.ok)
        self.assertEqual(actor.hp.current, 10)

    def test_log_keeps_recent(self):
        session = make_session()
        for _ in range(20):
            session.dispatch(NewTurn())
        self.assertLessEqual(len(session.log), 12)


if __name__ == "__main__":
    unittest.main()
