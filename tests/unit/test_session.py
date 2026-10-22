# -*- coding: utf-8 -*-
"""会话：前端只拿 Card，命令只发意图。

这里同时是一条端到端剧本：建 1 级战士 → 回气 → 短休 → 再回气 →
长休。全程没有一行 UI 代码，能跑通就说明后端真的独立。
"""

import unittest
from pathlib import Path

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


def make_session(level=1, seed=5) -> Session:
    session = Session.open(str(ROOT / "plugins"), seed=seed)
    session.create_character(FIGHTER, level, SCORES, "测试战士", "Test Fighter")
    return session


class SessionBasicsTest(unittest.TestCase):
    def test_header(self):
        view = make_session().view()
        self.assertEqual(view.header.name, "测试战士")
        self.assertEqual(view.header.level, 1)
        self.assertEqual(view.header.hp_max, 12)
        self.assertEqual(view.header.ac, 12)
        self.assertEqual(view.header.proficiency_bonus, 2)
        self.assertEqual(view.header.classes, ("战士 1",))

    def test_cards_are_made_by_backend(self):
        view = make_session().view()
        ids = [card.id for card in view.cards]
        self.assertIn("power:%s" % SECOND_WIND, ids)
        self.assertIn("pool:hit_dice.%s" % FIGHTER, ids)

    def test_pool_card_hidden_when_power_shows_it(self):
        """按钮卡已经显示 2/2，再出一张同名资源卡只会看花眼。"""
        view = make_session().view()
        ids = [card.id for card in view.cards]
        self.assertNotIn("pool:dnd2024.resource.fighter.second_wind", ids)

    def test_button_payload_is_the_command(self):
        view = make_session().view()
        action = next(item for item in view.actions() if item.payload["power_id"] == SECOND_WIND)
        self.assertEqual(action.command, "use_power")
        self.assertEqual(action.label, "回气")

    def test_passive_cards_have_no_button(self):
        view = make_session().view()
        for card in view.cards:
            if card.subtitle == "被动":
                self.assertEqual(card.actions, ())

    def test_attack_card(self):
        session = make_session(level=20)
        card = session.view().attacks[0]
        self.assertEqual(card.value, "4 次/动作")
        self.assertIn("9", card.subtitle)  # 力量 +3 + 熟练 +6

    def test_locale(self):
        session = Session.open(str(ROOT / "plugins"), locale="en", seed=5)
        session.create_character(FIGHTER, 1, SCORES, "测试战士", "Test Fighter")
        view = session.view()
        self.assertEqual(view.header.name, "Test Fighter")
        titles = [card.title for card in view.cards]
        self.assertIn("Second Wind", titles)


class EndToEndTest(unittest.TestCase):
    def test_fighter_second_wind_then_short_rest(self):
        session = make_session()
        actor = session.character

        # 先掉血，否则回气看不出效果
        view, report = session.dispatch(TakeDamage(9))
        self.assertTrue(report.ok)
        self.assertEqual(view.header.hp, 3)

        # 回气：1d10 + 战士等级（1）→ 至少 2 点
        view, report = session.dispatch(UsePower(SECOND_WIND))
        self.assertTrue(report.ok)
        self.assertGreater(view.header.hp, 3)
        self.assertEqual(view.header.hp, actor.hp.current)

        # 附赠动作已用完，卡片变成不可点
        card = view.card("power:%s" % SECOND_WIND)
        self.assertEqual(card.actions, ())
        self.assertIn("blocked", card.badges)

        # 次数从 2 变 1（显示在按钮卡上）
        self.assertEqual(view.card("power:%s" % SECOND_WIND).value, "1/2")

        # 短休恢复 1 次
        view, report = session.dispatch(ShortRest())
        self.assertTrue(report.ok)
        self.assertIn("second_wind", report.message)
        self.assertEqual(view.card("power:%s" % SECOND_WIND).value, "2/2")

        # 新回合恢复附赠动作，卡片重新可点
        view, _ = session.dispatch(NewTurn())
        self.assertTrue(view.card("power:%s" % SECOND_WIND).actions)

    def test_short_rest_spends_hit_dice(self):
        session = make_session()
        actor = session.character
        session.dispatch(TakeDamage(10))
        view, report = session.dispatch(ShortRest(dice=1))
        self.assertGreater(actor.hp.current, 2)
        self.assertIn("生命骰", report.message)

    def test_long_rest_resets_everything(self):
        session = make_session(level=9)
        actor = session.character
        session.dispatch(TakeDamage(50))
        session.dispatch(UsePower(SECOND_WIND))
        view, report = session.dispatch(LongRest())
        self.assertEqual(actor.hp.current, actor.hp.maximum)
        self.assertIn("资源回满", report.message)
        self.assertEqual(view.card("power:dnd2024.class.fighter.indomitable").value, "1/1")

    def test_unknown_command(self):
        session = make_session()
        _, report = session.dispatch("做个三明治")
        self.assertFalse(report.ok)
        self.assertIn("不认识的命令", report.message)

    def test_unknown_power(self):
        session = make_session()
        _, report = session.dispatch(UsePower("dnd2024.class.fighter.nope"))
        self.assertFalse(report.ok)

    def test_exhausted_power_is_blocked(self):
        """两次用完 2 次回气后再点，应报资源不足；每回合都要先恢复附赠动作。"""
        session = make_session()
        for _ in range(2):
            session.dispatch(NewTurn())
            _, report = session.dispatch(UsePower(SECOND_WIND))
            self.assertTrue(report.ok, report.message)
        session.dispatch(NewTurn())
        _, report = session.dispatch(UsePower(SECOND_WIND))
        self.assertFalse(report.ok)
        self.assertIn("不足", report.message)

    def test_regain(self):
        session = make_session()
        actor = session.character
        session.dispatch(TakeDamage(5))
        _, report = session.dispatch(Regain(3))
        self.assertEqual(actor.hp.current, 10)

    def test_log_keeps_recent(self):
        session = make_session()
        for _ in range(20):
            session.dispatch(NewTurn())
        view = session.view()
        self.assertLessEqual(len(view.log), 12)

    def test_view_is_serializable(self):
        data = make_session().view().to_dict()
        self.assertIn("header", data)
        self.assertIn("cards", data)
        self.assertTrue(all("actions" in card for card in data["cards"]))


if __name__ == "__main__":
    unittest.main()
