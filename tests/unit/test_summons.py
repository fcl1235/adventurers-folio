# -*- coding: utf-8 -*-
"""P8b 验收：召唤物 stat block 是内容（G9）。

在此之前，四个召唤法术的详情只能把整段英文 stat block 当 `upcast` 文本贴出来 ——
AC / HP 写的是「11 + 法术环级」这种字符串，升环换个环位就不知道该显示什么，
施法结算（G6）也就无从下手：那只生物没有 AC，没有 HP，没有动作。

这一组盯住四件事：

  1. AC / HP 是**可算的**结构（`Scaling`），任何环级都能现算，且算出来跟英文原文对得上
  2. 「按体型分叉」的活化物件不被硬塞进环级公式
  3. 伤害是 `骰式 + 固定值 + 每环 +N + 施法调整值`，不是一整句话
  4. 法术详情真的带出卡片，且**没有召唤物的法术**不受影响

断言挑的是「本来会算错」的样本：
  - 龙之精魂 5 环 = AC 19 / HP 50，6 环 = AC 20 / HP 60（升环两样都涨）
  - 异界坐骑 2 环 = AC 12 / HP 25（和「10 + 环级」「5 + 10×环级」两处都对得上）
  - 活化物件 5 环与 9 环 HP 都是 10（巨型才 40）—— 如果错误地按环级加，这里必红
  - 巨虫的毒刺 4 环是 1d6+7（3 + 4 环），9 环是 1d6+12
  - 飞行：坐骑 2 环没有飞行，4 环才有
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import PluginError, SummonDef, load_all, parse_summon
from dnd5r.kernel.errors import RuleError
from dnd5r.rules.summon import DamagePart, Scaling, resolve, slot_curve

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

DRAGON = "dnd2024.summon.draconic_spirit"
OBJECT = "dnd2024.summon.animated_object"
CENTIPEDE = "dnd2024.summon.giant_insect_centipede"
SPIDER = "dnd2024.summon.giant_insect_spider"
WASP = "dnd2024.summon.giant_insect_wasp"
STEED = "dnd2024.summon.otherworldly_steed_celestial"
STEED_FEY = "dnd2024.summon.otherworldly_steed_fey"
STEED_FIEND = "dnd2024.summon.otherworldly_steed_fiend"
SUMMON_DRAGON = "dnd2024.spell.summon_dragon"
ANIMATE = "dnd2024.spell.animate_objects"
GIANT_INSECT = "dnd2024.spell.giant_insect"
FIND_STEED = "dnd2024.spell.find_steed"


def _bundle():
    return load_all(PLUGINS)


class ScalingTest(unittest.TestCase):
    """`Scaling` 是唯一的「随环级变化」的表达方式，先把它钉住。"""

    def test_每环都加(self):
        scale = Scaling(base=11, per_slot=1)
        self.assertEqual(scale.at(1), 12)
        self.assertEqual(scale.at(4), 15)
        self.assertEqual(scale.at(9), 20)

    def test_从某一环才开始加(self):
        scale = Scaling(base=30, per_slot=5, from_level=2)
        # 低于起点不能倒扣 —— 「超出 2 级的环级」在 2 环时就是 0 级超出。
        self.assertEqual(scale.at(1), 30)
        self.assertEqual(scale.at(2), 30)
        self.assertEqual(scale.at(5), 45)

    def test_不随环级变(self):
        self.assertEqual(Scaling(base=15).at(1), 15)
        self.assertEqual(Scaling(base=15).at(9), 15)
        self.assertEqual(Scaling(base=15).describe(), "15")

    def test_说明文字能读(self):
        self.assertEqual(Scaling(11, 1).describe(), "11 + 1 × 法术环级")
        self.assertEqual(Scaling(30, 5, 2).describe(), "30 + 5 × 超出 2 级的环级")

    def test_0环与负数环级要报错(self):
        # 0 环是戏法，「用 0 环召」不存在。静默返回 base 会给出一个假数。
        with self.assertRaises(RuleError):
            Scaling(11, 1).at(0)
        with self.assertRaises(RuleError):
            Scaling(11, 1).at(-1)

    def test_负数配置要报错(self):
        with self.assertRaises(PluginError):
            Scaling(base=-1)
        with self.assertRaises(PluginError):
            Scaling(base=10, per_slot=-1)
        with self.assertRaises(PluginError):
            Scaling(base=10, from_level=10)


class DamagePartTest(unittest.TestCase):
    """伤害构成：骰式、固定值、每环 +N、施法调整值、升环加骰。"""

    def test_每环加点值(self):
        part = DamagePart(dice="1d6", flat=4, per_slot=1, damage_type="piercing")
        self.assertEqual(part.at(5), "1d6+9")
        self.assertEqual(part.at(9), "1d6+13")

    def test_只有骰子(self):
        self.assertEqual(DamagePart(dice="2d6", damage_type="fire").at(3), "2d6")

    def test_每环加骰(self):
        # 活化物件：5 环 1d4+3，每升一环多一颗 1d4。
        part = DamagePart(dice="1d4", flat=3, per_slot_dice="1d4",
                          per_slot_dice_above=5, damage_type="force")
        self.assertEqual(part.at(5), "1d4+3")
        self.assertEqual(part.at(6), "2d4+3")
        self.assertEqual(part.at(8), "4d4+3")

    def test_加施法属性调整值(self):
        part = DamagePart(dice="2d6", flat=3, caster_mod=True, damage_type="force")
        self.assertEqual(part.at(5, caster_mod=4), "2d6+7")
        # 不给调整值时不能悄悄当成 0 之后又声称「已含调整值」——
        # 数字与 `caster_mod` 标记是两回事，界面靠标记补文案。
        self.assertEqual(part.at(5, caster_mod=0), "2d6+3")

    def test_同面骰要合并(self):
        # 「1d6 + 1d6」这种写法不该出现两个骰子项，否则摇起来像两次独立掷骰。
        part = DamagePart(dice="1d6", per_slot_dice="1d6", per_slot_dice_above=1,
                          damage_type="fire")
        self.assertEqual(part.at(3), "3d6")

    def test_坏骰式与坏类型要报错(self):
        with self.assertRaises(PluginError):
            DamagePart(dice="1d")          # 解析不了
        with self.assertRaises(PluginError):
            DamagePart()                   # 一项数值都没有
        with self.assertRaises(PluginError):
            DamagePart(per_slot_dice="1d4")  # 没写从哪一环起


class SummonContentTest(unittest.TestCase):
    """8 条召唤物进内容了，而且抄的是英文原文的数。"""

    def setUp(self):
        self.bundle = _bundle()

    def test_加载无错且有八条(self):
        self.assertEqual(list(self.bundle.errors), [])
        self.assertEqual(len(self.bundle.summons), 8)

    def test_每条都指向存在的法术(self):
        for summon in self.bundle.summons.values():
            self.assertIn(summon.spell, self.bundle.spells, summon.id)

    def test_四个法术各自召出谁(self):
        self.assertEqual([s.id for s in self.bundle.summons_for_spell(ANIMATE)], [OBJECT])
        self.assertEqual([s.id for s in self.bundle.summons_for_spell(SUMMON_DRAGON)],
                         [DRAGON])
        self.assertEqual(len(self.bundle.summons_for_spell(GIANT_INSECT)), 3)
        self.assertEqual(len(self.bundle.summons_for_spell(FIND_STEED)), 3)

    def test_没有召唤物的法术返回空(self):
        self.assertEqual(self.bundle.summons_for_spell("dnd2024.spell.fireball"), ())

    def test_基础环数值对得上原文(self):
        cases = {
            DRAGON: (5, 19, 50),        # AC 14 + 5 / HP 50
            OBJECT: (5, 15, 10),        # AC 15 / HP 10（中型）
            CENTIPEDE: (4, 15, 30),     # AC 11 + 4 / HP 30
            SPIDER: (4, 15, 30),
            WASP: (4, 15, 30),
            STEED: (2, 12, 25),         # AC 10 + 2 / HP 5 + 10×2
            STEED_FEY: (2, 12, 25),
            STEED_FIEND: (2, 12, 25),
        }
        for ident, (slot, ac, hp) in cases.items():
            summon = self.bundle.summons[ident]
            self.assertEqual(summon.ac_at(slot), ac, ident)
            self.assertEqual(summon.hp_at(slot, "medium"), hp, ident)

    def test_升环两样都涨(self):
        dragon = self.bundle.summons[DRAGON]
        self.assertEqual((dragon.ac_at(6), dragon.hp_at(6)), (20, 60))
        self.assertEqual((dragon.ac_at(9), dragon.hp_at(9)), (23, 90))

    def test_活化物件不按环级涨(self):
        # 活化物件的 HP 只看体型。如果错误地当环级公式算，9 环这条必红。
        obj = self.bundle.summons[OBJECT]
        self.assertEqual(obj.hp_at(5, "medium"), 10)
        self.assertEqual(obj.hp_at(9, "medium"), 10)
        self.assertEqual(obj.hp_at(9, "large"), 20)
        self.assertEqual(obj.hp_at(9, "huge"), 40)
        # 不指定体型必须报错 —— 猜一个体型等于凭空给出一个数
        with self.assertRaises(PluginError):
            obj.hp_at(5)
        with self.assertRaises(PluginError):
            obj.hp_at(5, "gargantuan")

    def test_被动察觉与感知调整值一致(self):
        # 8 条原文都没给察觉熟练，所以 PP 必然 = 10 + 感知调整值。
        # 旧程序把龙之精魂写成 10、活化物件写成 10，都是这一条能抓到的错。
        for summon in self.bundle.summons.values():
            wisdom = summon.abilities.score("wis")
            expect = 10 + (wisdom - 10) // 2
            self.assertEqual(summon.passive_perception, expect, summon.id)

    def test_体型缺省必须给说明(self):
        obj = self.bundle.summons[OBJECT]
        self.assertEqual(obj.size, "")
        self.assertIsNotNone(obj.size_note)

    def test_显示名带变体(self):
        self.assertEqual(self.bundle.summons[SPIDER].label, "巨型昆虫（蜘蛛）")
        self.assertEqual(self.bundle.summons[DRAGON].label, "龙之精魂")

    def test_巨虫三形态只差三处(self):
        centipede = self.bundle.summons[CENTIPEDE]
        spider = self.bundle.summons[SPIDER]
        wasp = self.bundle.summons[WASP]
        # 飞行只有黄蜂有
        self.assertIn("fly", wasp.speeds_at(4))
        self.assertNotIn("fly", centipede.speeds_at(4))
        self.assertNotIn("fly", spider.speeds_at(4))
        # 蛛网弹只有蜘蛛有，毒液喷吐只有蜈蚣有
        names = lambda s: {row.name.zh for row in s.actions + s.bonus_actions}
        self.assertIn("蛛网弹", names(spider))
        self.assertNotIn("蛛网弹", names(centipede))
        self.assertIn("毒液喷吐", names(centipede))
        self.assertNotIn("毒液喷吐", names(wasp))


class SummonResolveTest(unittest.TestCase):
    """结算出来的卡：属性、速度解禁、动作伤害。"""

    def setUp(self):
        self.bundle = _bundle()

    def test_飞行要四环(self):
        steed = self.bundle.summons[STEED]
        self.assertNotIn("fly", steed.speeds_at(2))
        self.assertIn("fly", steed.speeds_at(4))
        card = resolve(steed, 2)
        # 没解禁也不能凭空消失 —— 界面要能说「4 环起」
        self.assertEqual(card["speeds_locked"]["fly"], {"value": 60, "slot": 4})

    def test_动作伤害按环级现算(self):
        centipede = self.bundle.summons[CENTIPEDE]
        card = resolve(centipede, 4)
        jab = [row for row in card["actions"] if row["name"] == "毒刺"][0]
        self.assertEqual([part["at_slot"] for part in jab["damage"]], ["1d6+7", "1d4"])
        card9 = resolve(centipede, 9)
        jab9 = [row for row in card9["actions"] if row["name"] == "毒刺"][0]
        self.assertEqual(jab9["damage"][0]["at_slot"], "1d6+12")

    def test_活化物件三段伤害各带体型标签(self):
        card = resolve(self.bundle.summons[OBJECT], 5, size="medium")
        slam = card["actions"][0]
        self.assertEqual([part["label"]["zh"] for part in slam["damage"]],
                         ["中型或更小", "大型", "巨型"])
        self.assertEqual([part["at_slot"] for part in slam["damage"]],
                         ["1d4+3", "2d6+3", "2d12+3"])
        # 升环加骰：9 环时中型的 1d4 变 5d4
        card9 = resolve(self.bundle.summons[OBJECT], 9, size="medium")
        self.assertEqual(card9["actions"][0]["damage"][0]["at_slot"], "5d4+3")

    def test_豁免与区域是字段不是句子(self):
        card = resolve(self.bundle.summons[DRAGON], 5)
        breath = [row for row in card["actions"] if row["name"] == "吐息武器"][0]
        self.assertEqual(breath["save"], "dex")
        self.assertEqual(breath["save_dc"], "spell")
        self.assertEqual(breath["area"], ["cone", 30])

    def test_曲线只在有变化的环级上不同(self):
        dragon = slot_curve(self.bundle.summons[DRAGON], 5)
        self.assertEqual([row["slot"] for row in dragon], [5, 6, 7, 8, 9])
        obj = slot_curve(self.bundle.summons[OBJECT], 5, size="medium")
        self.assertEqual({(row["ac"], row["hp"]) for row in obj}, {(15, 10)})


class SummonGuardTest(unittest.TestCase):
    """坏内容要在解析期就炸，且只炸自己。"""

    def _raw(self, **patch):
        data = {
            "id": "dnd2024.summon.t",
            "name": {"zh": "测试", "en": "Test"},
            "spell": SUMMON_DRAGON,
            "creature_type": "beast",
            "ac": {"base": 11, "per_slot": 1},
            "hp": {"base": 10},
            "languages": {"zh": "无", "en": "None"},
            "abilities": {"str": 10, "dex": 10, "con": 10,
                          "int": 10, "wis": 10, "cha": 10},
            "actions": [{"name": {"zh": "击", "en": "Hit"}, "kind": "melee",
                         "attack": "spell", "reach": 5,
                         "damage": [{"dice": "1d4", "type": "piercing"}]}],
        }
        data.update(patch)
        return data

    def test_最小可用条目能过(self):
        summon = parse_summon(self._raw(), "t")
        self.assertEqual(summon.ac_at(2), 13)

    def test_hp与hp_by_size必须二选一(self):
        with self.assertRaises(PluginError):
            parse_summon(self._raw(hp=None), "t")
        raw = self._raw(hp=None, hp_by_size={"medium": 10})
        self.assertEqual(parse_summon(raw, "t").hp_at(1, "medium"), 10)
        with self.assertRaises(PluginError):
            parse_summon(self._raw(hp={"base": 10}, hp_by_size={"medium": 5}), "t")

    def test_生物类型要在白名单里(self):
        with self.assertRaises(PluginError):
            parse_summon(self._raw(creature_type="slime"), "t")

    def test_近战动作必须有触及(self):
        with self.assertRaises(PluginError):
            parse_summon(self._raw(actions=[
                {"name": {"zh": "击", "en": "Hit"}, "kind": "melee",
                 "damage": [{"dice": "1d4"}]}]), "t")

    def test_要豁免就必须给DC(self):
        with self.assertRaises(PluginError):
            parse_summon(self._raw(actions=[
                {"name": {"zh": "喷", "en": "Spray"}, "kind": "save",
                 "save": "con", "damage": [{"dice": "1d4"}]}]), "t")

    def test_没有动作等于召出来站着(self):
        with self.assertRaises(PluginError):
            parse_summon(self._raw(actions=[]), "t")

    def test_指向不存在的法术会被合并期抓到(self):
        bundle = _bundle()
        bundle.summons["dnd2024.summon.bad"] = parse_summon(
            self._raw(id="dnd2024.summon.bad", spell="dnd2024.spell.nope"), "t")
        from dnd5r.content import _check_summon_spells
        bundle.errors.clear()
        _check_summon_spells(bundle)
        self.assertTrue(any("nope" in item for item in bundle.errors), bundle.errors)


class SummonApiTest(unittest.TestCase):
    """法术详情真的带出卡片；没有召唤物的法术不受影响。"""

    def setUp(self):
        self.bundle = _bundle()

    def test_召唤法术详情带卡片(self):
        info = api.spell_info(self.bundle, SUMMON_DRAGON)
        self.assertEqual(len(info["summons"]), 1)
        card = info["summons"][0]["card"]
        self.assertEqual((card["ac"], card["hp"]), (19, 50))
        self.assertEqual(card["creature_type"], "dragon")
        self.assertTrue(info["summons"][0]["by_slot"])

    def test_普通法术没有这个键或为空(self):
        info = api.spell_info(self.bundle, "dnd2024.spell.fireball")
        self.assertEqual(info["summons"], [])

    def test_按环级问某一只(self):
        card = api.summon_info(self.bundle, STEED, 7)
        self.assertEqual((card["ac"], card["hp"]), (17, 75))
        self.assertIn("fly", card["speeds"])

    def test_不传环级就用法术自己的环级(self):
        card = api.summon_info(self.bundle, DRAGON)
        self.assertEqual(card["slot_level"], 5)

    def test_未知召唤物要报错(self):
        with self.assertRaises(api.PluginError):
            api.summon_info(self.bundle, "dnd2024.summon.nope")

    def test_界面文案带出关键数字(self):
        from apps.desktop.pages_spells import spell_text, summon_text
        info = api.spell_info(self.bundle, SUMMON_DRAGON)
        text = summon_text(info["summons"][0])
        self.assertIn("AC 19", text)
        self.assertIn("生命值 50", text)
        self.assertIn("1d6+9 穿刺", text)
        self.assertIn("盲视 30 尺", text)
        # 英文原始 stat block 不该再当「升环」整段贴一遍
        row = {"name": info["name"], "level": info["level"], "school": info["school"],
               "text": info["text"], "upcast": info["upcast"]}
        body = spell_text(row, info)
        self.assertNotIn("Melee Attack Roll", body)


if __name__ == "__main__":
    unittest.main()
