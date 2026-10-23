# -*- coding: utf-8 -*-
"""P8g 验收：子职自己的资源池（G19）。

规则里有一类次数长在**子职特性**上，不在职业表里 ——
月亮结社 10 级的月光步：「使用次数等于你的感知调整值（至少 1 次），
完成长休后全部恢复」。在子职能声明资源之前，这句话只能写在 note 里让人手记。

这组测试盯四件事：
  1. 容量是**属性调整值**，不是等级 —— 所以 `floor` 必须在（感知 8 也有 1 次）；
  2. 池**属于子职**：换子职就没有，别把月环的次数送给大地结社；
  3. 池**有等级门槛**：3 级德鲁伊的卡上不该出现 10 级才有的池
     （`by_level` 那套「低等级算 0」表达不了「常数容量 + 等级门槛」）；
  4. 花掉一次就是花掉一次：余量 -1、长休回满、重建不回血也不吐次数。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import ResourceDef, SubclassDef, parse_resource
from dnd5r.kernel.errors import PluginError
from dnd5r.kernel.text import Text
from dnd5r.model.levels import ClassLevel
from dnd5r.model.resources import PoolKind
from dnd5r.rules.amount import parse_amount
from dnd5r.rules.rest import long_rest

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
DRUID = "dnd2024.class.druid"
MOON = "dnd2024.subclass.druid.circle_of_the_moon"
LAND = "dnd2024.subclass.druid.circle_of_the_land"
STEP = MOON + ".moonlight_step"
STEP_POOL = "dnd2024.resource.druid.circle_of_the_moon.moonlight_step"

# 感知 16（+3）：池就是 3 次
SCORES = {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 16, "cha": 12}
# 感知 8（-1）：原文写 "minimum of once"，所以是 1 次而不是 0
LOW_WIS = dict(SCORES, wis=8)
# 感知 20（+5）：上不封顶，跟着属性走
HIGH_WIS = dict(SCORES, wis=20)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        assert not cls.bundle.errors, cls.bundle.errors

    def druid(self, level, subclass=MOON, scores=None):
        return api.new_character(self.bundle, DRUID, level, scores or SCORES,
                                 name_zh="德鲁伊", name_en="Druid",
                                 subclass=subclass)


class MoonlightPoolTest(Base):
    """月光步的次数池：容量、门槛、归属、消耗。"""

    def test_pool_exists_at_ten(self):
        actor = self.druid(10)
        self.assertTrue(actor.resources.has(STEP_POOL))
        pool = actor.resources.get(STEP_POOL)
        self.assertEqual(pool.capacity, 3)          # 感知 16 → +3
        self.assertEqual(pool.available, 3)
        self.assertIs(pool.kind, PoolKind.CHARGE)

    def test_capacity_follows_wisdom_not_level(self):
        """10 级与 12 级的池一样大 —— 涨的是属性，不是等级。"""
        ten = self.druid(10).resources.get(STEP_POOL).capacity
        twelve = self.druid(12).resources.get(STEP_POOL).capacity
        self.assertEqual((ten, twelve), (3, 3))

    def test_low_wisdom_still_has_one_use(self):
        pool = self.druid(10, scores=LOW_WIS).resources.get(STEP_POOL)
        self.assertEqual(pool.capacity, 1)

    def test_high_wisdom_counts_every_point(self):
        pool = self.druid(10, scores=HIGH_WIS).resources.get(STEP_POOL)
        self.assertEqual(pool.capacity, 5)

    def test_no_pool_before_ten(self):
        """3 级、9 级都没有 —— 池的等级门槛是内容里写的 `level: 10`。"""
        for level in (3, 9):
            self.assertFalse(self.druid(level).resources.has(STEP_POOL), level)

    def test_pool_belongs_to_the_subclass(self):
        """换成大地结社就没有这个池：次数是月环给的，不是德鲁伊给的。"""
        actor = self.druid(12, subclass=LAND)
        self.assertFalse(actor.resources.has(STEP_POOL))
        # 职业自己的池照旧
        self.assertTrue(actor.resources.has("dnd2024.resource.druid.wild_shape"))

    def test_use_spends_one_charge(self):
        actor = self.druid(10)
        report = api.use_power(actor, self.bundle, STEP)
        self.assertTrue(report["ok"], report["message"])
        pool = actor.resources.get(STEP_POOL)
        self.assertEqual((pool.available, pool.capacity), (2, 3))

    def test_empty_pool_blocks_the_fourth_use(self):
        actor = self.druid(10)
        for _ in range(3):
            self.assertTrue(api.use_power(actor, self.bundle, STEP)["ok"])
        spent = api.use_power(actor, self.bundle, STEP)
        self.assertFalse(spent["ok"])
        self.assertIn("月光步", spent["message"])
        # 拒绝时不能悄悄把余量压成负数
        self.assertEqual(actor.resources.get(STEP_POOL).available, 0)

    def test_sheet_shows_the_pool_and_blocks_when_empty(self):
        """界面不判断规则：余量与「为什么点不了」都要由 api 算好放进卡里。"""
        actor = self.druid(10)
        sheet = api.character_sheet(actor, self.bundle)
        row = next(item for item in sheet["pools"] if item["id"] == STEP_POOL)
        self.assertEqual((row["left"], row["max"]), (3, 3))
        self.assertEqual(row["label"], "月光步使用次数")
        power = next(item for item in sheet["powers"] if item["id"] == STEP)
        self.assertEqual(power["blocked"], [])
        for _ in range(3):
            api.use_power(actor, self.bundle, STEP)
        sheet = api.character_sheet(actor, self.bundle)
        power = next(item for item in sheet["powers"] if item["id"] == STEP)
        self.assertTrue(power["blocked"], "次数用光后按钮必须说明原因")

    def test_long_rest_refills(self):
        actor = self.druid(10)
        for _ in range(3):
            api.use_power(actor, self.bundle, STEP)
        self.assertEqual(actor.resources.get(STEP_POOL).available, 0)
        long_rest(actor)
        self.assertEqual(actor.resources.get(STEP_POOL).available, 3)

    def test_rebuild_keeps_used_charges(self):
        """改专长会重建角色，但用掉的次数不该吐回来（与 HP 同一条规矩）。"""
        actor = self.druid(10)
        api.use_power(actor, self.bundle, STEP)
        fresh = api.rebuild_actor(self.bundle, actor)
        self.assertEqual(fresh.resources.get(STEP_POOL).available, 2)


class SubclassResourceParseTest(unittest.TestCase):
    """内容层：子职声明资源、字段校验、命名空间。"""

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_yaml_resource_registered(self):
        sub = self.bundle.subclasses[MOON]
        self.assertEqual(len(sub.resources), 1)
        resource = sub.resources[0]
        self.assertEqual(resource.id, STEP_POOL)
        # 资源与特性用不同命名空间：同名条目在 plugins_cli 的全局 id 校验里会撞
        self.assertTrue(resource.id.startswith("dnd2024.resource."))
        self.assertEqual(resource.owner_class, MOON)     # 池的主人记子职，不记职业
        self.assertEqual(int(resource.level), 10)

    def test_level_defaults_to_zero(self):
        """不写 level 就是「与所属内容同时解锁」，不能因为 0 < 1 就报错。"""
        resource = parse_resource({"id": "demo.res.demo", "capacity": 2})
        self.assertEqual(int(resource.level), 0)

    def test_negative_level_rejected(self):
        with self.assertRaises(PluginError):
            parse_resource({"id": "demo.res.demo", "capacity": 2, "level": -1})

    def test_level_must_be_int(self):
        with self.assertRaises(PluginError):
            parse_resource({"id": "demo.res.demo", "capacity": 2, "level": "10"})

    def test_resource_id_cannot_shadow_power(self):
        """同一个子职里资源与特性重名，界面上两个「月光步」分不清谁是谁。"""
        resource = ResourceDef(
            id="demo.sub.demo.step", kind=PoolKind.CHARGE,
            capacity=parse_amount(1), level=ClassLevel(3))
        power_id = "demo.sub.demo.step"
        with self.assertRaises(PluginError):
            SubclassDef(
                id="demo.sub.demo", class_id="demo.class.demo",
                name=Text.of("演示", "Demo"), summary=Text.of("演示", "Demo"),
                powers=(_power(power_id),), resources=(resource,))

    def test_locked_pool_is_not_built(self):
        """等级门槛在 `capacity_at` 里落成 0 —— 调用方见到 0 就不建池。"""
        resource = self.bundle.subclasses[MOON].resources[0]
        self.assertEqual(resource.capacity_at(
            ClassLevel(9), {"abilities": self._abilities()}), 0)
        self.assertEqual(resource.capacity_at(
            ClassLevel(10), {"abilities": self._abilities()}), 3)

    def _abilities(self):
        from dnd5r.model.statblock import Abilities
        return Abilities.of(**SCORES)


def _power(ident):
    from dnd5r.rules.powers import parse_power
    return parse_power({
        "id": ident,
        "name": {"zh": "演示", "en": "Demo"},
        "text": {"zh": "演示", "en": "Demo"},
        "kind": "passive",
        "effects": [{"note": {"zh": "演示", "en": "Demo"}}],
    }, owner="demo.sub.demo")


if __name__ == "__main__":
    unittest.main()
