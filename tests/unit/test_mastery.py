# -*- coding: utf-8 -*-
"""G32 验收：武器精通真的结算了。

在这之前「精通」只是武器数据上的一个 slug：`mastery: topple` 印在装备页，
攻击掷骰完全不看它，界面上还写着「效果未结算」。这组测试盯四件事：

  1. **资格**：只有建卡时选过的武器才算「你有这件武器的精通」。
     名字对得上 ≠ 你有 —— 这是以前最容易骗过人的地方（法师拿巨剑也有 topple）。
  2. **真结算的四种**：擦伤补伤害（走抗性）、击倒掷体质豁免并把倒地写进状态、
     扰乱给下一次攻击优势、削弱给目标下一次攻击劣势。后两者挂的是**真标记**。
  3. **不假算的四种**：劈砍/快手/推撞/迟缓缺战场信息，只交参数；
     报告里必须说清「还没结算、缺什么」，不能让人以为算过了。
  4. **关得掉**：`mastery=False` 时一次效果都不触发（DM 想在桌上自己判的时候用）。

第 2 条里有两个顺序陷阱，都写过：
  * 扰乱挂的正是「下一次攻击优势」，而本次攻击同时要**消耗**标记 ——
    先挂就会被这次攻击自己吃掉；
  * 擦伤是唯一一条「没命中也有伤害」的规则，不能因为 `outcome == "miss"`
    就直接跳过伤害管线。

另加一条 `MarkSet.end_turn` 的 `next` 作用域：原文写「直到你的下回合结束」，
用 `turn` 会在挂上的那一刻（就是自己回合末）被清掉，等于白挂。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.model.inventory import EquipSlot
from dnd5r.model.marks import Mark, MarkSet
from dnd5r.rules.combat import Target

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
FIGHTER = "dnd2024.class.fighter"
W = "dnd2024.item.weapon."

STR16 = {"str": 16, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10}
STR8 = {"str": 8, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10}

GREATSWORD = W + "greatsword"   # 擦伤 graze
MAUL = W + "maul"               # 击倒 topple
RAPIER = W + "rapier"           # 扰乱 vex
LONGSWORD = W + "longsword"     # 削弱 sap
GREATAXE = W + "greataxe"       # 劈砍 cleave
DAGGER = W + "dagger"           # 快手 nick
GREATCLUB = W + "greatclub"     # 推撞 push
CLUB = W + "club"               # 迟缓 slow


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def fighter(self, weapon: str, masteries=(), scores=None, actor_id=None,
                level: int = 5):
        """5 级战士（熟练 +3），装备指定武器。默认**不选精通**。"""
        kwargs = {"actor_id": actor_id} if actor_id else {}
        actor = api.new_character(
            self.bundle, FIGHTER, level, scores or STR16,
            name_zh="战士", name_en="Fighter",
            masteries=tuple(masteries), **kwargs)
        if weapon:
            actor.inventory.equip(EquipSlot.MAIN_HAND, weapon)
        return actor

    def foe(self, actor_id: str = "foe"):
        """有角色卡的对手：倒地、标记才有地方落。"""
        return api.new_character(
            self.bundle, FIGHTER, 5, STR16,
            name_zh="对手", name_en="Foe", actor_id=actor_id)


class CatalogTest(Base):
    def test_eight_masteries_all_bilingual(self):
        rows = api.mastery_catalog("zh")["masteries"]
        self.assertEqual(len(rows), 8)
        self.assertEqual({row["key"] for row in rows},
                         {"cleave", "graze", "nick", "push",
                          "sap", "slow", "topple", "vex"})
        english = {row["key"]: row for row in api.mastery_catalog("en")["masteries"]}
        for row in rows:
            self.assertTrue(row["name"])
            self.assertTrue(row["summary"])
            self.assertNotEqual(english[row["key"]]["name"], row["name"],
                                "%s 的英文名没翻" % row["key"])
            self.assertNotEqual(english[row["key"]]["summary"], row["summary"],
                                "%s 的英文效果没翻" % row["key"])

    def test_resolved_flags_are_honest(self):
        """四种真算、四种给参数 —— 这个旗标是界面的依据，不能全都写 True。"""
        rows = {row["key"]: row for row in api.mastery_catalog("zh")["masteries"]}
        for key in ("graze", "topple", "vex", "sap"):
            self.assertTrue(rows[key]["resolved"], key)
        for key in ("cleave", "nick", "push", "slow"):
            self.assertFalse(rows[key]["resolved"], key)
            self.assertTrue(rows[key]["needs"], "%s 要说明缺什么" % key)


class QualifiedTest(Base):
    def test_weapon_catalog_carries_names(self):
        rows = {row["id"]: row for row in api.weapon_catalog(self.bundle, "zh")["weapons"]}
        self.assertEqual(rows[MAUL]["mastery"], "topple")
        self.assertEqual(rows[MAUL]["mastery_name"], "击倒")
        self.assertIn("体质豁免", rows[MAUL]["mastery_summary"])

    def test_usable_only_when_picked(self):
        """数据上有精通属性 ≠ 你能用出来。"""
        picked = api.character_sheet(
            self.fighter(GREATSWORD, [GREATSWORD]), self.bundle, "zh")
        plain = api.character_sheet(
            self.fighter(GREATSWORD), self.bundle, "zh")
        self.assertTrue(picked["attacks"][0]["mastery_usable"])
        self.assertFalse(plain["attacks"][0]["mastery_usable"])
        # 两种情况都还能读到「这件武器是擦伤」—— 属性是数据，资格才是玩家的事实
        self.assertEqual(plain["attacks"][0]["mastery_name"], "擦伤")

    def test_unpicked_weapon_says_why(self):
        actor = self.fighter(GREATSWORD)
        result = api.attack_roll(actor, self.bundle, Target(ac=25),
                                 rng=ScriptedRng([2]), apply=False)
        self.assertFalse(result["mastery"]["usable"])
        self.assertIn("没有这件武器的精通", result["mastery"]["reason"])
        self.assertEqual(result["damage"]["total"], 0)


class GrazeTest(Base):
    def test_miss_still_deals_ability_modifier(self):
        actor = self.fighter(GREATSWORD, [GREATSWORD])
        result = api.attack_roll(actor, self.bundle, Target(ac=25),
                                 rng=ScriptedRng([2]), apply=False)
        self.assertEqual(result["outcome"], "miss")
        self.assertTrue(result["mastery"]["applied"])
        self.assertEqual(result["mastery"]["damage"], 3)     # 力量 16 → +3
        self.assertEqual(result["damage"]["total"], 3)
        # 伤害类型跟武器走，不是「无类型」
        self.assertEqual(result["damage"]["breakdown"][0]["damage_type"], "slashing")
        self.assertIn("擦伤", "".join(result["notes"]))

    def test_graze_goes_through_resistance(self):
        """未命中也有伤害，但它仍是一段挥砍伤害 —— 抗性照常减半（向下取整）。"""
        actor = self.fighter(GREATSWORD, [GREATSWORD])
        result = api.attack_roll(
            actor, self.bundle,
            Target(ac=25, resistances=frozenset({"slashing"})),
            rng=ScriptedRng([2]), apply=False)
        self.assertEqual(result["damage"]["total"], 1)
        self.assertIn("抗性", "".join(result["notes"]))

    def test_negative_modifier_never_heals(self):
        """力量 8（-1）：擦伤补的是 max(0, 调整值)，不能把目标「治」回来。

        力量不足 13 拿重型武器本身有劣势 → 掷两次 d20，脚本要给两个值。
        """
        actor = self.fighter(GREATSWORD, [GREATSWORD], scores=STR8)
        result = api.attack_roll(actor, self.bundle, Target(ac=25),
                                 rng=ScriptedRng([2, 3]), apply=False)
        self.assertEqual(result["mastery"]["damage"], 0)
        self.assertEqual(result["damage"]["total"], 0)
        self.assertEqual(result["damage"]["breakdown"], [])

    def test_mastery_can_be_turned_off(self):
        actor = self.fighter(GREATSWORD, [GREATSWORD])
        result = api.attack_roll(actor, self.bundle, Target(ac=25),
                                 rng=ScriptedRng([2]), apply=False, mastery=False)
        self.assertEqual(result["damage"]["total"], 0)
        self.assertFalse(result["mastery"]["applied"])
        self.assertIn("没有使用", "".join(result["notes"]))


class ToppleTest(Base):
    def test_failed_save_applies_prone(self):
        actor = self.fighter(MAUL, [MAUL])
        foe = self.foe()
        # d20 15 → 命中；2d6 → 4、5；豁免 d20 1 + 5 = 6 < DC 14 → 倒地
        result = api.attack_roll(actor, self.bundle, foe,
                                 rng=ScriptedRng([15, 4, 5, 1]), apply=True)
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["mastery"]["dc"], 14)        # 8 + 3 + 3
        self.assertEqual(result["mastery"]["save"], "con")
        self.assertFalse(result["mastery"]["save_roll"]["saved"])
        self.assertTrue(result["mastery"]["applied"])
        self.assertIn("prone", foe.conditions.ids())

    def test_successful_save_stays_up(self):
        actor = self.fighter(MAUL, [MAUL])
        foe = self.foe()
        # 豁免 d20 15 + 5 = 20 ≥ 14
        result = api.attack_roll(actor, self.bundle, foe,
                                 rng=ScriptedRng([15, 4, 5, 15]), apply=True)
        self.assertTrue(result["mastery"]["save_roll"]["saved"])
        self.assertFalse(result["mastery"]["applied"])
        self.assertNotIn("prone", foe.conditions.ids())

    def test_preview_does_not_apply_prone(self):
        actor = self.fighter(MAUL, [MAUL])
        foe = self.foe()
        result = api.attack_roll(actor, self.bundle, foe,
                                 rng=ScriptedRng([15, 4, 5, 1]), apply=False)
        self.assertFalse(result["mastery"]["applied"])
        self.assertNotIn("prone", foe.conditions.ids())
        self.assertIn("预览", "".join(result["notes"]))

    def test_target_without_sheet_says_so(self):
        """手填「AC 15 的木桩」没有状态集合：说清倒地没落地，别让玩家以为挂了。"""
        actor = self.fighter(MAUL, [MAUL])
        result = api.attack_roll(actor, self.bundle, Target(ac=15),
                                 rng=ScriptedRng([15, 4, 5, 1]), apply=True)
        self.assertFalse(result["mastery"]["applied"])
        self.assertIn("没有角色卡", "".join(result["notes"]))


class AdvMarkTest(Base):
    def test_vex_mark_survives_its_own_attack(self):
        """扰乱挂给的是「下一次攻击优势」—— 本次攻击消耗标记时不能顺手吃掉它。"""
        actor = self.fighter(RAPIER, [RAPIER])
        foe = self.foe()
        api.attack_roll(actor, self.bundle, foe,
                        rng=ScriptedRng([15, 5]), apply=True)
        marks = api.marks_of(actor)
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["label"], "扰乱")

        nxt = api.attack_roll(actor, self.bundle, foe,
                              rng=ScriptedRng([10, 15, 5]), apply=False)
        self.assertEqual(nxt["attack"]["mode"], "adv")
        self.assertIn("扰乱", nxt["attack"]["mode_sources"])

    def test_vex_mark_expires_next_turn(self):
        actor = self.fighter(RAPIER, [RAPIER])
        foe = self.foe()
        api.attack_roll(actor, self.bundle, foe,
                        rng=ScriptedRng([15, 5]), apply=True)
        actor.root().marks.end_turn()          # 自己的回合末：只降级，不清
        self.assertEqual(len(api.marks_of(actor)), 1)
        actor.root().marks.end_turn()          # 下个回合末：真的清掉
        self.assertEqual(api.marks_of(actor), [])

    def test_sap_marks_the_target(self):
        actor = self.fighter(LONGSWORD, [LONGSWORD])
        foe = self.foe()
        result = api.attack_roll(actor, self.bundle, foe,
                                 rng=ScriptedRng([15, 5]), apply=True)
        self.assertEqual(result["mastery"]["mark"]["mode"], "dis")
        marks = api.marks_of(foe)
        self.assertEqual(len(marks), 1)
        self.assertEqual(marks[0]["mode"], "dis")

    def test_preview_does_not_hang_marks(self):
        actor = self.fighter(RAPIER, [RAPIER])
        foe = self.foe()
        api.attack_roll(actor, self.bundle, foe,
                        rng=ScriptedRng([15, 5]), apply=False)
        self.assertEqual(api.marks_of(actor), [])


class ParametersOnlyTest(Base):
    def test_cleave_gives_second_attack_numbers(self):
        actor = self.fighter(GREATAXE, [GREATAXE])
        result = api.attack_roll(actor, self.bundle, Target(ac=15),
                                 rng=ScriptedRng([15, 7]), apply=False)
        block = result["mastery"]
        self.assertFalse(block["resolved"])
        self.assertEqual(block["kind"], "extra_attack")
        self.assertEqual(block["attack"], 6)          # 力量 +3、熟练 +3
        self.assertEqual(block["damage_dice"], "1d12")  # 不加属性调整值
        self.assertIn("第二个生物", "".join(result["notes"]))

    def test_push_and_slow_give_distance(self):
        pushed = api.attack_roll(self.fighter(GREATCLUB, [GREATCLUB]), self.bundle,
                                 Target(ac=15), rng=ScriptedRng([15, 3]), apply=False)
        self.assertEqual(pushed["mastery"]["distance"], 10)
        self.assertIn("推离 10 尺", "".join(pushed["notes"]))

        slowed = api.attack_roll(self.fighter(CLUB, [CLUB]), self.bundle,
                                 Target(ac=15), rng=ScriptedRng([15, 3]), apply=False)
        self.assertEqual(slowed["mastery"]["speed"], 10)
        self.assertIn("速度减 10 尺", "".join(slowed["notes"]))

    def test_nick_points_at_bonus_action(self):
        actor = self.fighter(DAGGER, [DAGGER])
        result = api.attack_roll(actor, self.bundle, Target(ac=15),
                                 rng=ScriptedRng([15, 3]), apply=False)
        self.assertEqual(result["mastery"]["kind"], "extra_attack")
        self.assertIn("附赠动作", "".join(result["notes"]))

    def test_english_report_is_english(self):
        """算出来的句子必须在规则层翻 —— 界面拿到的已经是整句，翻不了。"""
        actor = self.fighter(GREATSWORD, [GREATSWORD])
        result = api.attack_roll(actor, self.bundle, Target(ac=25),
                                 rng=ScriptedRng([2]), apply=False, locale="en")
        text = "".join(result["notes"])
        self.assertIn("Graze", text)
        self.assertNotIn("擦伤", text)


class MarkScopeTest(unittest.TestCase):
    def test_next_downgrades_then_clears(self):
        marks = MarkSet()
        marks.add(Mark(id="m", kind="advantage", mode="adv", expires="next"))
        marks.end_turn()
        self.assertEqual(len(marks.items), 1)
        self.assertEqual(marks.items[0].expires, "turn")
        marks.end_turn()
        self.assertEqual(marks.items, [])

    def test_turn_scope_still_clears_immediately(self):
        marks = MarkSet()
        marks.add(Mark(id="t", kind="advantage", mode="adv", expires="turn"))
        marks.end_turn()
        self.assertEqual(marks.items, [])


if __name__ == "__main__":
    unittest.main()
