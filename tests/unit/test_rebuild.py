# -*- coding: utf-8 -*-
"""P6d 验收：角色重建与存档往返。

这一组盯的不是「能不能存」，而是**存了以后还是不是同一个角色**：

  1. 档案必须记下建角色时输入的原始属性 —— 否则读档后重建不出来
  2. 重建要保住运行时状态（当前 HP、临时 HP、已用资源），不能顺手回满
  3. 改一个专长选择项就要重算全部派生值（属性提升改了体质，HP 上限得跟着变）
  4. 改失败时原角色一个字段都不能动（界面要能继续用）

最容易出的错是「重建成功但少了点什么」：熟练丢了、专精没了、抗性消失。
所以下面每一条都做**整档往返比对**，而不是只断言某几个数字。
"""

import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import RuleError
from dnd5r.model.inventory import EquipSlot
from dnd5r.model.profile import Profile
from dnd5r.rules.build import build_from_profile, rebuild_actor

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"
WIZARD = "dnd2024.class.wizard"
ROGUE = "dnd2024.class.rogue"
ASI = "dnd2024.feat.ability_score_improvement"
SKILL_EXPERT = "dnd2024.feat.skill_expert"
CHAIN_MAIL = "dnd2024.item.armor.chain_mail"
SHIELD = "dnd2024.item.armor.shield"

STR_SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
INT_SCORES = {"str": 8, "dex": 14, "con": 14, "int": 17, "wis": 12, "cha": 10}
DEX_SCORES = {"str": 10, "dex": 17, "con": 14, "int": 12, "wis": 12, "cha": 10}


class RebuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _fighter(self, level=5, feats=()):
        return api.new_character(self.bundle, FIGHTER, level, STR_SCORES, feats=feats)

    # --- 原始属性 -------------------------------------------------------
    def test_actor_records_base_scores(self):
        actor = self._fighter()
        self.assertEqual(dict(actor.profile.base_scores), STR_SCORES)

    def test_rebuild_reproduces_same_character(self):
        actor = self._fighter(feats=[ASI])
        actor = api.set_feat_choice(actor, self.bundle, ASI, "boost", ["str", "str"])
        fresh = rebuild_actor(self.bundle, actor)
        self.assertEqual(fresh.profile, actor.profile)
        self.assertEqual(fresh.hp.maximum, actor.hp.maximum)
        self.assertEqual(fresh.top().statblock.abilities, actor.top().statblock.abilities)
        self.assertEqual(set(fresh.resources.pools), set(actor.resources.pools))

    def test_rebuild_keeps_runtime_state(self):
        """重建不是「长休」：血、临时血、用掉的次数都得留着。"""
        actor = self._fighter(level=5)
        actor.hp.current = 12
        actor.hp.temp = 4
        pool_id = sorted(actor.resources.pools)[0]
        actor.resources.spend(pool_id, 1)

        fresh = rebuild_actor(self.bundle, actor)
        self.assertEqual(fresh.hp.current, 12)
        self.assertEqual(fresh.hp.temp, 4)
        self.assertEqual(fresh.resources.pools[pool_id].used, 1)

    def test_rebuild_keeps_equipment(self):
        """重建要保住装备。

        AC 是取卡时从 `inventory.equipped` 现读的（`rules/armor.loadout_for`），
        所以不搬背包就等于「界面里改一次力量，护甲自己脱了」——
        实测过：穿锁甲 + 盾 AC 18，改完 str 掉回 12。
        """
        actor = self._fighter(level=5)
        actor.inventory.equip(EquipSlot.ARMOR, CHAIN_MAIL)
        actor.inventory.equip(EquipSlot.SHIELD, SHIELD)
        before = api.character_sheet(actor, self.bundle)["ac"]["total"]

        scores = dict(STR_SCORES, str=18)
        fresh = rebuild_actor(self.bundle, actor,
                              actor.profile.with_base_scores(scores))
        after = api.character_sheet(fresh, self.bundle)["ac"]["total"]
        self.assertEqual(after, before, "重建后 AC 变了 —— 装备没搬过去")
        self.assertEqual(fresh.inventory.equipped, actor.inventory.equipped)
        self.assertIsNot(fresh.inventory, actor.inventory, "背包被共享了，改一份会两份都变")

    def test_rebuild_keeps_hand_added_choices(self):
        """玩家单独挑的熟练（不由内容决定）不能在重建时丢掉。"""
        actor = self._fighter()
        actor.profile = actor.profile.with_proficiencies(["skill.arcana"])
        fresh = rebuild_actor(self.bundle, actor)
        self.assertIn("skill.arcana", fresh.profile.proficiencies)
        self.assertEqual(fresh.profile.proficiencies, actor.profile.proficiencies)

    def test_multiclass_rebuild_works(self):
        """P12 之后兼职真的能重建（此前是明确拒绝）。两段职业都要回来。"""
        actor = self._fighter()
        scores = dict(STR_SCORES, int=14)   # 法师兼职前置：INT 13
        actor.profile = actor.profile.add_class(WIZARD, 3).with_base_scores(scores)
        fresh = rebuild_actor(self.bundle, actor)
        self.assertEqual([item.class_id for item in fresh.profile.classes],
                         [item.class_id for item in actor.profile.classes])
        self.assertEqual(fresh.profile.total, actor.profile.total)

    def test_profile_without_base_scores_refuses(self):
        """旧档没有原始属性：明确报错。返回 0 会建出一个废角色。"""
        actor = self._fighter()
        actor.profile = Profile(classes=actor.profile.classes)
        with self.assertRaises(RuleError) as ctx:
            build_from_profile(self.bundle, actor.profile, "测试", "Test")
        self.assertIn("原始属性", str(ctx.exception))

    # --- 改选择项 -------------------------------------------------------
    def test_boost_changes_derived_values(self):
        actor = self._fighter(level=4, feats=[ASI])
        before_hp = actor.hp.maximum
        boosted = api.set_feat_choice(actor, self.bundle, ASI, "boost", ["con", "con"])
        self.assertEqual(boosted.top().statblock.abilities.score("con"), 16)
        self.assertGreater(boosted.hp.maximum, before_hp, "体质 +2 之后 HP 上限没变")
        # 原角色不受影响（返回的是新角色）
        self.assertEqual(actor.top().statblock.abilities.score("con"), 14)

    def test_boost_skill_follows_ability(self):
        actor = self._fighter(level=4, feats=[ASI])
        before = [row for row in api.character_sheet(actor, self.bundle)["skills"]
                  if row["key"] == "athletics"][0]["total"]
        boosted = api.set_feat_choice(actor, self.bundle, ASI, "boost", ["str", "str"])
        after = [row for row in api.character_sheet(boosted, self.bundle)["skills"]
                 if row["key"] == "athletics"][0]["total"]
        self.assertEqual(after, before + 1, "力量 +2 之后运动检定应 +1")

    def test_invalid_pick_leaves_actor_untouched(self):
        actor = self._fighter(level=4, feats=[ASI])
        snapshot = (actor.hp.maximum, dict(actor.profile.choices),
                    actor.top().statblock.abilities.score("str"))
        with self.assertRaises(RuleError):
            api.set_feat_choice(actor, self.bundle, ASI, "boost", ["str", "luck"])
        self.assertEqual(
            (actor.hp.maximum, dict(actor.profile.choices),
             actor.top().statblock.abilities.score("str")),
            snapshot)

    def test_partial_pick_is_pending_not_error(self):
        """只选了 1 项不算错 —— 界面要能显示「还差一项」。"""
        actor = self._fighter(level=4, feats=[ASI])
        half = api.set_feat_choice(actor, self.bundle, ASI, "boost", ["str"])
        sheet = api.character_sheet(half, self.bundle)
        self.assertTrue(sheet["choices_needed"])
        self.assertEqual(half.top().statblock.abilities.score("str"), 16)

    def test_unknown_feat_and_choice_rejected(self):
        actor = self._fighter(level=4, feats=[ASI])
        with self.assertRaises(RuleError):
            api.set_feat_choice(actor, self.bundle, "dnd2024.feat.nope", "boost", ["str"])
        with self.assertRaises(RuleError):
            api.set_feat_choice(actor, self.bundle, ASI, "nope", ["str"])

    def test_feat_not_taken_rejected(self):
        actor = self._fighter(level=4)
        with self.assertRaises(RuleError):
            api.set_feat_choice(actor, self.bundle, ASI, "boost", ["str", "str"])

    def test_expertise_choice_needs_proficiency(self):
        """专精只能落在已熟练的技能上 —— 没熟练就选它必须报错，而不是静默生效。"""
        actor = api.new_character(self.bundle, ROGUE, 8, DEX_SCORES, feats=[SKILL_EXPERT])
        actor = api.set_feat_choice(actor, self.bundle, SKILL_EXPERT, "skill", ["stealth"])
        self.assertIn("skill.stealth", actor.profile.proficiencies)
        # 选一个没熟练的专精项
        with self.assertRaises(RuleError):
            api.set_feat_choice(actor, self.bundle, SKILL_EXPERT, "expertise", ["history"])

    def test_repeat_feat_index(self):
        """同一专长选两次：第二次的键带 `#1`，两次加值各算各的。"""
        actor = api.new_character(self.bundle, FIGHTER, 8, STR_SCORES, feats=[ASI, ASI])
        actor = api.set_feat_choice(actor, self.bundle, ASI, "boost", ["str", "str"])
        actor = api.set_feat_choice(actor, self.bundle, ASI, "boost", ["str", "str"], index=1)
        self.assertEqual(actor.top().statblock.abilities.score("str"), 20)
        self.assertIn("%s#1.boost" % ASI, actor.profile.choices)


class SaveLoadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _actor(self):
        actor = api.new_character(self.bundle, FIGHTER, 5, STR_SCORES, feats=[ASI])
        return api.set_feat_choice(actor, self.bundle, ASI, "boost", ["str", "str"])

    def test_round_trip_keeps_profile(self):
        actor = self._actor()
        data = api.save_character(actor)
        back = api.load_character(self.bundle, data)
        self.assertEqual(back.profile, actor.profile)
        self.assertEqual(back.id, actor.id)
        self.assertEqual(back.statblock.name.zh, actor.statblock.name.zh)

    def test_round_trip_keeps_runtime(self):
        actor = self._actor()
        actor.hp.current = 7
        actor.hp.temp = 3
        pool_id = sorted(actor.resources.pools)[0]
        actor.resources.spend(pool_id, 1)
        back = api.load_character(self.bundle, api.save_character(actor))
        self.assertEqual(back.hp.current, 7)
        self.assertEqual(back.hp.temp, 3)
        self.assertEqual(back.resources.pools[pool_id].used, 1)

    def test_save_writes_no_derived_values(self):
        """派生值进档就是会过期的数字。存档里不许出现 ac / hp.maximum。"""
        data = api.save_character(self._actor())
        self.assertNotIn("ac", data)
        self.assertNotIn("maximum", data["hp"])
        self.assertIn("base_scores", data["profile"])

    def test_double_round_trip_is_stable(self):
        once = api.load_character(self.bundle, api.save_character(self._actor()))
        twice = api.load_character(self.bundle, api.save_character(once))
        self.assertEqual(once.profile, twice.profile)
        self.assertEqual(once.hp.maximum, twice.hp.maximum)

    def test_hp_clamped_to_new_maximum(self):
        """内容改了 HP 算法（上限变小）时，读档不能带出 current > maximum。"""
        actor = self._actor()
        data = api.save_character(actor)
        data["hp"]["current"] = 999
        back = api.load_character(self.bundle, data)
        self.assertEqual(back.hp.current, back.hp.maximum)

    def test_legacy_slot_ids_migrated(self):
        """F36 之前的旧档：位池 id 挂在插件命名空间下，读档必须改写成引擎前缀。

        不迁移的话旧 id 匹配不上池，已用的法术位会静默回满 —— 那是白送位的 bug。
        """
        actor = api.new_character(self.bundle, WIZARD, 5, STR_SCORES)
        data = api.save_character(actor)
        data["resources"] = {"dnd2024.slot.wizard.1": 2}
        back = api.load_character(self.bundle, data)
        self.assertEqual(back.resources.pools["engine.slot.wizard.1"].used, 2)

    def test_future_version_rejected(self):
        data = api.save_character(self._actor())
        data["version"] = api.SAVE_VERSION + 1
        with self.assertRaises(RuleError):
            api.load_character(self.bundle, data)

    def test_missing_profile_rejected(self):
        with self.assertRaises(RuleError):
            api.load_character(self.bundle, {"version": 1})

    def test_unknown_resource_pool_ignored(self):
        """内容升级后某个资源池没了：忽略那一格，别让整份存档读不出来。"""
        data = api.save_character(self._actor())
        data["resources"]["dnd2024.resource.ghost"] = 2
        back = api.load_character(self.bundle, data)
        self.assertFalse(back.resources.has("dnd2024.resource.ghost"))


if __name__ == "__main__":
    unittest.main()
