# -*- coding: utf-8 -*-
"""P10a 验收：兽形天然武器（G22）。

在这之前，荒野变形只换属性/AC/HP：德鲁伊变成熊以后「攻击」仍是徒手
1 + 力量调整值 —— 熊的啃咬 1d8+3、命中 +5 就白写在数据里了。
现在形态的整张卡来自怪物条目（`tools/gen_beasts.py`），动作形状与怪物
完全一样，结算走同一条 `resolve_monster_attack`。

这组测试盯五件事：

  1. **16 只形态与对应怪物条目逐字段相等** —— 防的是「两边各存一份、
     迟早各说各话」。原本手抄的 2014 数据已经漂了（巨鳄 HP 19 vs 13、
     狼力量 12 vs 14、豹 AC 12 vs 13），这条测试就是为了让它漂不动。
  2. `gen_beasts.py --check` 与产物一致（改了生成器没重跑会红）。
  3. **变形后能列出形态自己的攻击**，且 `form_view` 没变形时说没变形。
  4. **真结算**：命中加值取卡上的数、伤害照骰、按槽位付额度、
     预览不扣血；「多重攻击」不占额度。
  5. **形态印着的豁免加值也生效**：变猫以后敏捷豁免是 +4（卡上印的），
     不是 +2（敏捷 15 推出来的）。这一条与命中加值是同一个坑。

第 4 条的反向验证在 `tools/inject_forms.py`：把命中加值改成
「力量调整值 + 熟练」，本文件必须变红。
"""

import subprocess
import sys
import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import IllegalAction, RuleError
from dnd5r.kernel.rng import ScriptedRng
from dnd5r.rules.combat import target_from_actor

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
BEASTS = PLUGINS / "dnd2024-core" / "bestiary" / "beasts.yaml"
DRUID = "dnd2024.class.druid"
MOON = "dnd2024.subclass.druid.circle_of_the_moon"
WILD_SHAPE = "dnd2024.class.druid.wild_shape"

# 形态 id 尾段 → 怪物 id 尾段。与 tools/gen_beasts.py 的 FORMS 同一张表，
# 故意各写一遍：生成器改了表而测试没跟上，就会红（这是好事）。
FORMS = (
    ("bat", "bat"), ("cat", "cat"), ("frog", "frog"), ("owl", "owl"),
    ("rat", "giant_rat"), ("weasel", "weasel"),
    ("poisonous_snake", "venomous_snake"), ("boar", "boar"),
    ("panther", "panther"), ("wolf", "wolf"), ("black_bear", "black_bear"),
    ("crocodile", "crocodile"), ("reef_shark", "reef_shark"),
    ("brown_bear", "brown_bear"), ("giant_spider", "giant_spider"),
    ("giant_eagle", "giant_eagle"),
)

CAT = "dnd2024.form.beast.cat"              # AC 12 / 敏捷豁免印着 +4
WOLF_FORM = "dnd2024.form.beast.wolf"       # 咬 +4 / 1d6+2 / 力量 14
BEAR = "dnd2024.form.beast.brown_bear"      # 多重攻击 + 咬 1d8+3 + 爪 1d4+3
WOLF_MONSTER = "dnd2024.monster.wolf"       # 打它来验扣血

SCORES = {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 16, "cha": 12}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def druid(self, level=3):
        # 带月亮结社：CR 上限是「等级 ÷ 3」（3 级就到 CR 1），
        # 不带的话棕熊（CR 1）要 8 级才解锁 —— 这里要验的是攻击，不是 CR 轴。
        return api.new_character(self.bundle, DRUID, level, SCORES,
                                 name_zh="德鲁伊", name_en="Druid", subclass=MOON)

    def morph(self, actor, form_id):
        report = api.use_power(actor, self.bundle, WILD_SHAPE,
                               choice={"form_id": form_id})
        self.assertTrue(report["ok"], report.get("message"))
        return actor

    def duel(self, form_id=BEAR, level=3, rolls=(20, 1)):
        """德鲁伊变成 `form_id`，与一只狼开战，并推进到**德鲁伊**的回合。"""
        hero = self.morph(self.druid(level), form_id)
        foe = api.spawn_monster(self.bundle, WOLF_MONSTER)
        encounter = api.new_encounter([hero, foe], rng=ScriptedRng(list(rolls)))
        guard = 0
        while api.encounter_view(encounter)["current"] != hero.id:
            api.advance_turn(encounter)
            guard += 1
            assert guard < 10, "遭遇战里没轮到德鲁伊"
        return hero, foe, encounter


class DataFidelityTest(Base):
    """第 1、2 条：形态卡与怪物条目不许分叉。"""

    def test_every_form_matches_its_monster(self):
        for slug, monster_slug in FORMS:
            form = self.bundle.forms["dnd2024.form.beast." + slug]
            monster = self.bundle.monsters["dnd2024.monster." + monster_slug]
            where = "形态 %s 与怪物 %s" % (slug, monster_slug)
            self.assertEqual(form.ac, monster.ac, where + " 的 AC")
            self.assertEqual(form.hp, monster.hp, where + " 的 HP")
            self.assertAlmostEqual(form.cr, monster.cr, msg=where + " 的 CR")
            self.assertEqual(form.size, monster.size, where + " 的体型")
            self.assertEqual(dict(form.abilities.scores),
                             dict(monster.abilities.scores), where + " 的属性")
            self.assertEqual(dict(form.speeds), dict(monster.speeds), where + " 的速度")
            self.assertEqual(dict(form.saves), dict(monster.saves), where + " 的豁免")
            self.assertEqual([row.name.zh for row in form.actions],
                             [row.name.zh for row in monster.actions],
                             where + " 的动作")
            self.assertEqual([row.attack_bonus for row in form.actions],
                             [row.attack_bonus for row in monster.actions],
                             where + " 的命中加值")

    def test_generator_matches_the_file(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "gen_beasts.py"), "--check"],
            cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0,
                         "beasts.yaml 与生成器不一致：%s%s"
                         % (result.stdout, result.stderr))


class FormViewTest(Base):
    """第 3 条：界面拿得到形态的攻击清单。"""

    def test_not_morphed_says_so(self):
        view = api.form_view(self.druid(3), self.bundle)
        self.assertFalse(view["morphed"])
        self.assertNotIn("actions", view)

    def test_morphed_lists_the_beasts_own_attacks(self):
        actor = self.morph(self.druid(3), WOLF_FORM)
        view = api.form_view(actor, self.bundle)
        self.assertTrue(view["morphed"])
        self.assertEqual(view["name"], "狼")
        self.assertEqual([row["key"] for row in view["actions"]], ["action:0"])
        bite = view["actions"][0]
        self.assertEqual(bite["attack_bonus"], 4)          # 卡上的数
        self.assertEqual([row["dice"] for row in bite["damage"]], ["1d6+2"])

    def test_multiattack_is_listed_but_not_rollable(self):
        actor = self.morph(self.druid(3), BEAR)
        rows = api.form_view(actor, self.bundle)["actions"]
        self.assertEqual([row["key"] for row in rows],
                         ["action:0", "action:1", "action:2"])
        self.assertEqual(rows[0]["kind"], "multiattack")
        self.assertFalse(rows[0]["rollable"])
        self.assertTrue(rows[1]["rollable"])

    def test_sheet_carries_the_form(self):
        actor = self.morph(self.druid(3), BEAR)
        sheet = api.character_sheet(actor, self.bundle)
        self.assertTrue(sheet["morphed"])
        self.assertEqual(sheet["form"]["name"], "棕熊")
        self.assertEqual(len(sheet["form"]["actions"]), 3)


class FormAttackTest(Base):
    """第 4 条：变形后真能按形态的卡打人。"""

    def test_bear_bite_hits_and_damages(self):
        hero, foe, encounter = self.duel()
        before = foe.hp.current
        result = api.monster_attack(
            encounter, self.bundle, hero, "action:1", foe,   # action:0 是多重攻击
            rng=ScriptedRng([15, 4]), apply=True)
        self.assertEqual(result["outcome"], "hit")
        self.assertEqual(result["attack"]["bonus"], 5)       # 棕熊咬 +5
        self.assertEqual(result["damage"]["total"], 7)        # 1d8[4] + 3
        self.assertEqual(foe.hp.current, before - 7)

    def test_bonus_is_not_derived_from_abilities(self):
        """猫的抓挠印着 +4，而它的力量只有 3（-4）—— 按公式推会得到 -2。"""
        hero, foe, encounter = self.duel(CAT)
        result = api.monster_attack(
            encounter, self.bundle, hero, "action:0", foe,
            rng=ScriptedRng([2]), apply=False)
        self.assertEqual(result["attack"]["bonus"], 4)                   # 卡上的数
        self.assertEqual(hero.top().statblock.abilities.mod("str"), -4)   # 猫力量 3
        self.assertNotEqual(result["attack"]["bonus"],
                            hero.top().statblock.abilities.mod("str") + 2)  # 那会算出 -2

    def test_pays_the_action_once(self):
        hero, foe, encounter = self.duel()
        api.monster_attack(encounter, self.bundle, hero, "action:1", foe,
                           rng=ScriptedRng([15, 4]), apply=True)
        with self.assertRaises(IllegalAction):
            api.monster_attack(encounter, self.bundle, hero, "action:1", foe,
                               rng=ScriptedRng([15, 4]), apply=True)

    def test_preview_changes_nothing(self):
        hero, foe, encounter = self.duel()
        before = foe.hp.current
        result = api.monster_attack(
            encounter, self.bundle, hero, "action:1", foe,
            rng=ScriptedRng([15, 4]), apply=False)
        self.assertEqual(foe.hp.current, before)
        self.assertTrue(result["economy"]["preview"])
        self.assertEqual(result["economy"]["after"]["action"], 1)

    def test_multiattack_pays_nothing(self):
        hero, foe, encounter = self.duel()
        result = api.monster_attack(
            encounter, self.bundle, hero, "action:0", foe,
            rng=ScriptedRng([]), apply=True)
        self.assertFalse(result["rolled"])
        self.assertEqual(result["economy"]["kind"], "")
        self.assertEqual(result["economy"]["after"]["action"], 1)

    def test_unmorphed_player_has_no_natural_weapons(self):
        hero = self.druid(3)                       # 没变形
        foe = api.spawn_monster(self.bundle, WOLF_MONSTER)
        encounter = api.new_encounter([hero, foe], rng=ScriptedRng([20, 1]))
        with self.assertRaises(RuleError):
            api.monster_attack(encounter, self.bundle, hero, "action:0", foe,
                               rng=ScriptedRng([15, 4]), apply=False)


class PrintedSavesOfFormTest(Base):
    """第 5 条：形态卡上印着的豁免加值也要生效。"""

    def test_cat_keeps_its_printed_dex_save(self):
        actor = self.morph(self.druid(3), CAT)     # 猫：敏捷 15（+2）、豁免印着 +4
        target = target_from_actor(self.bundle, actor)
        self.assertEqual(target.saves["dex"], 4)
        self.assertNotEqual(target.saves["dex"],
                            actor.top().statblock.abilities.mod("dex"))

    def test_body_saves_are_not_mixed_in(self):
        """保留本体的 int/wis/cha，但不能顺手把本体的豁免也带进形态卡。"""
        actor = self.morph(self.druid(3), CAT)
        target = target_from_actor(self.bundle, actor)
        # 猫只印了敏捷豁免；智力豁免仍是「属性 + 熟练」推出来的（德鲁伊熟练智力）
        self.assertEqual(target.saves["int"],
                         actor.top().statblock.abilities.mod("int") + 2)


class EncounterPageTest(Base):
    """界面上也要真的换成形态的天然武器 —— 只修 api、界面还按武器列，等于没修。"""

    def _app(self, form_id=BEAR):
        from apps.desktop.app import DesktopApp

        actor = self.druid(3)
        app = DesktopApp(self.bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        self.morph(actor, form_id)          # 变形不经过界面也能生效（同一个 actor）
        app.refresh()
        return app

    def test_action_list_comes_from_the_form(self):
        page = self._app().encounter_page
        page.roster_pane.select_id(WOLF_MONSTER)
        self.assertTrue(page.add_monster(rng=ScriptedRng([10])))
        self.assertTrue(page.start(rng=ScriptedRng([20, 5])))
        names = [row["name"] for row in page._action_rows]
        self.assertIn("啃咬 +5", names)              # 棕熊的咬，不是长剑
        self.assertNotIn("长剑", " ".join(names))
        self.assertEqual([row["key"] for row in page._action_rows],
                         ["action:0", "action:1", "action:2"])
        self.assertIn("形态 棕熊", page.attacker_var.get())

    def test_roll_through_the_page_damages_the_monster(self):
        page = self._app().encounter_page
        page.roster_pane.select_id(WOLF_MONSTER)
        page.add_monster(rng=ScriptedRng([10]))
        page.start(rng=ScriptedRng([20, 5]))
        page._action_key = "action:1"
        foe = next(row for row in page.encounter.combatants
                   if str(row.actor.id).startswith(WOLF_MONSTER))
        before = foe.actor.hp.current
        self.assertTrue(page.roll(True, rng=ScriptedRng([15, 4])))
        self.assertEqual(foe.actor.hp.current, before - 7)   # 1d8[4] + 3


if __name__ == "__main__":
    unittest.main()
