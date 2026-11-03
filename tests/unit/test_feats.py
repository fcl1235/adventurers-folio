# -*- coding: utf-8 -*-
"""P5g 验收：79 个专长。

专长之前只有 `Profile.feats` 一个空元组，谁也不读。这一组把
「专长是内容、静态效果走原语、玩家选择走 choices」变成可验的：

  1. 79 条全部加载（12 起源 + 43 通用 + 12 战斗风格 + 12 传奇恩惠），双语齐全
  2. 静态原语：坚韧（HP 每级 +2）、防御（穿甲才有 AC）、箭术（只给远程）
  3. 玩家选择：属性提升的两种模式、坚毅的「豁免与属性同选」、技艺专家的专精
  4. 传奇恩惠：+1 上限 30（不是 20）、坚毅 +40 HP、速行 +30、真实视觉、抗性
  5. 前提：等级 / 职业限制要拒绝，属性前提只提示不拦
  6. 选择没选完不是错误（留在 choices_needed 里），选错了要报错
"""

import json
import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.kernel.errors import PluginError, RuleError
from dnd5r.model.inventory import EquipSlot

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}

ASI = "dnd2024.feat.ability_score_improvement"
ALERT = "dnd2024.feat.alert"
DEFENSE = "dnd2024.feat.defense"
ARCHERY = "dnd2024.feat.archery"
TOUGH = "dnd2024.feat.tough"
SPEEDY = "dnd2024.feat.speedy"
RESILIENT = "dnd2024.feat.resilient"
SKILL_EXPERT = "dnd2024.feat.skill_expert"
BOON_STRENGTH = "dnd2024.feat.boon_of_fortitude"
BOON_SPEED = "dnd2024.feat.boon_of_speed"
BOON_TRUESIGHT = "dnd2024.feat.boon_of_truesight"
BOON_RESIST = "dnd2024.feat.boon_of_energy_resistance"


class FeatDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_table_loaded(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertEqual(len(self.bundle.feats), 79)

    def test_kinds(self):
        counts = {kind: len(self.bundle.feats_of_kind(kind))
                  for kind in ("origin", "general", "fighting_style", "epic_boon")}
        self.assertEqual(counts, {"origin": 12, "general": 43,
                                  "fighting_style": 12, "epic_boon": 12})

    def test_ids_wellformed(self):
        for feat in self.bundle.feats.values():
            self.assertTrue(feat.id.startswith("dnd2024.feat."), feat.id)
            self.assertNotIn(" ", feat.id)
            for power in feat.powers:
                self.assertEqual(power.owner, feat.id, power.id)
                self.assertTrue(power.id.startswith(feat.id + "."), power.id)

    def test_all_texts_bilingual(self):
        for feat in self.bundle.feats.values():
            self.assertTrue(feat.name.zh, feat.id)
            self.assertTrue(feat.name.en, feat.id)
            self.assertTrue(feat.text.zh, feat.id)
            self.assertTrue(feat.text.en, feat.id)
            # en 里出现汉字说明「英文」其实是硬塞的中文，比缺英文更糟
            self.assertIsNone(_first_cjk(feat.text.en), "%s 的英文里混了中文" % feat.id)
            for power in feat.powers:
                self.assertTrue(power.name.zh and power.name.en, power.id)
                self.assertTrue(power.text.zh and power.text.en, power.id)
                self.assertTrue(power.effects, power.id)

    def test_fighting_style_needs_no_level(self):
        for feat in self.bundle.feats_of_kind("fighting_style"):
            self.assertEqual(int(feat.level), 0, feat.id)

    def test_boons_need_level_19(self):
        for feat in self.bundle.feats_of_kind("epic_boon"):
            self.assertEqual(int(feat.level), 19, feat.id)
            caps = [choice.cap for choice in feat.choices if choice.kind == "ability_boost"]
            self.assertEqual(caps, [30], "%s 的恩惠加值上限应是 30" % feat.id)


def _first_cjk(text: str) -> str | None:
    for char in text or "":
        if "\u4e00" <= char <= "\u9fff":
            return char
    return None


class FeatMechanicsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _fighter(self, level=5, feats=(), choices=None, scores=None):
        return api.new_character(
            self.bundle, "dnd2024.class.fighter", level, scores or SCORES,
            name_zh="测试", name_en="Test", feats=feats, choices=choices or {},
        )

    def _sheet(self, actor):
        return api.character_sheet(actor, self.bundle)

    # --- 静态原语 ---------------------------------------------------
    def test_tough_adds_two_hp_per_level(self):
        plain = self._sheet(self._fighter(5))
        tough = self._sheet(self._fighter(5, feats=[TOUGH]))
        self.assertEqual(tough["hp"]["maximum"] - plain["hp"]["maximum"], 10)

    def test_defense_requires_armor(self):
        actor = self._fighter(5, feats=[DEFENSE])
        unarmored = self._sheet(actor)["ac"]["total"]
        actor.inventory.equip(EquipSlot.ARMOR, "dnd2024.item.armor.chain_mail")
        armored = self._sheet(actor)["ac"]["total"]
        plain = self._fighter(5)
        plain.inventory.equip(EquipSlot.ARMOR, "dnd2024.item.armor.chain_mail")
        self.assertEqual(armored, self._sheet(plain)["ac"]["total"] + 1)
        self.assertEqual(unarmored, self._sheet(self._fighter(5))["ac"]["total"])

    def test_archery_only_boosts_ranged(self):
        actor = self._fighter(5, feats=[ARCHERY])
        plain = self._fighter(5)
        for item, slot in (("dnd2024.item.weapon.longbow", EquipSlot.MAIN_HAND),
                           ("dnd2024.item.weapon.longsword", EquipSlot.MAIN_HAND)):
            actor.inventory.equip(slot, item)
            plain.inventory.equip(slot, item)
            bonus = self._sheet(actor)["attacks"][0]["attack"] - self._sheet(plain)["attacks"][0]["attack"]
            expected = 2 if "longbow" in item else 0
            self.assertEqual(bonus, expected, item)

    def test_speedy_adds_ten_feet(self):
        plain = self._sheet(self._fighter(5))["speed"]["walk"]
        fast = self._sheet(self._fighter(5, feats=[SPEEDY],
                                         choices={SPEEDY + ".boost": ["dex"]}))["speed"]["walk"]
        self.assertEqual(fast - plain, 10)

    # --- 玩家选择 ---------------------------------------------------
    def test_ability_score_improvement_two_in_one(self):
        actor = self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str", "str"]})
        self.assertEqual(actor.top().statblock.abilities.score("str"), 18)
        sheet = self._sheet(actor)
        self.assertEqual(sheet["abilities"]["str"]["bonus"], 2)

    def test_ability_score_improvement_two_abilities(self):
        actor = self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str", "dex"]})
        self.assertEqual(actor.top().statblock.abilities.score("str"), 17)
        self.assertEqual(actor.top().statblock.abilities.score("dex"), 15)

    def test_ability_score_improvement_caps_at_20(self):
        actor = self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str", "str"]},
                              scores=dict(SCORES, str=19))
        self.assertEqual(actor.top().statblock.abilities.score("str"), 20)

    def test_ability_score_improvement_needs_two_picks(self):
        actor = self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str"]})
        self.assertEqual(actor.top().statblock.abilities.score("str"), 16)
        self.assertIn(ASI + ".boost", self._sheet(actor)["choices_needed"])

    def test_too_many_picks_rejected(self):
        with self.assertRaises(RuleError):
            self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["str", "dex", "con"]})

    def test_unknown_pick_rejected(self):
        with self.assertRaises(RuleError):
            self._fighter(8, feats=[ASI], choices={ASI + ".boost": ["luck", "luck"]})

    def test_resilient_pins_boost_to_chosen_save(self):
        # 战士本来熟练力量与体质豁免，所以选魅力才看得出「新熟练」
        actor = self._fighter(8, feats=[RESILIENT], choices={RESILIENT + ".save": ["cha"]})
        self.assertEqual(actor.top().statblock.abilities.score("cha"), 9)
        self.assertEqual(actor.top().statblock.abilities.score("wis"), 12)
        sheet = self._sheet(actor)
        self.assertTrue(sheet["saves"]["cha"]["proficient"])
        self.assertFalse(sheet["saves"]["dex"]["proficient"])

    def test_skill_expert_gives_skill_and_expertise(self):
        actor = self._fighter(8, feats=[SKILL_EXPERT], choices={
            SKILL_EXPERT + ".skill": ["stealth"],
            SKILL_EXPERT + ".expertise": ["stealth"],
            SKILL_EXPERT + ".boost": ["dex"],
        })
        self.assertIn("skill.stealth", actor.profile.proficiencies)
        self.assertIn("skill.stealth", actor.profile.expertise)

    def test_expertise_requires_proficiency(self):
        # 选了不熟练的技能做专精 → Profile 的集合约束拒绝（不是静默忽略）
        with self.assertRaises(RuleError):
            self._fighter(8, feats=[SKILL_EXPERT], choices={
                SKILL_EXPERT + ".skill": ["stealth"],
                SKILL_EXPERT + ".expertise": ["arcana"],
                SKILL_EXPERT + ".boost": ["dex"],
            })

    # --- 传奇恩惠 ---------------------------------------------------
    def test_boon_ability_cap_is_thirty(self):
        scores = dict(SCORES, str=20)
        actor = self._fighter(19, feats=[BOON_STRENGTH],
                              choices={BOON_STRENGTH + ".boost": ["str"]}, scores=scores)
        self.assertEqual(actor.top().statblock.abilities.score("str"), 21)

    def test_boon_fortitude_flat_hp(self):
        plain = self._sheet(self._fighter(19))["hp"]["maximum"]
        tough = self._sheet(self._fighter(19, feats=[BOON_STRENGTH],
                                          choices={BOON_STRENGTH + ".boost": ["str"]}))
        # +40 HP 与 +1 力量（体质没动）—— 差值就是 40
        self.assertEqual(tough["hp"]["maximum"] - plain, 40)

    def test_boon_speed(self):
        plain = self._sheet(self._fighter(19))["speed"]["walk"]
        fast = self._sheet(self._fighter(19, feats=[BOON_SPEED],
                                         choices={BOON_SPEED + ".boost": ["dex"]}))
        self.assertEqual(fast["speed"]["walk"] - plain, 30)

    def test_boon_truesight(self):
        sheet = self._sheet(self._fighter(19, feats=[BOON_TRUESIGHT],
                                          choices={BOON_TRUESIGHT + ".boost": ["wis"]}))
        self.assertEqual(sheet["senses"].get("truesight"), 60)

    def test_boon_energy_resistance(self):
        picks = {BOON_RESIST + ".boost": ["con"], BOON_RESIST + ".resist": ["fire", "cold"]}
        sheet = self._sheet(self._fighter(19, feats=[BOON_RESIST], choices=picks))
        self.assertEqual(sheet["resistances"], ["cold", "fire"])

    # --- 前提与登记 -------------------------------------------------
    def test_level_prereq_rejected(self):
        with self.assertRaises(RuleError):
            self._fighter(3, feats=[BOON_STRENGTH])

    def test_class_prereq_rejected(self):
        # 受祝福的勇士只给圣武士
        with self.assertRaises(RuleError):
            self._fighter(5, feats=["dnd2024.feat.blessed_warrior"])

    def test_unknown_feat_rejected(self):
        with self.assertRaises(PluginError):
            self._fighter(5, feats=["dnd2024.feat.does_not_exist"])

    def test_duplicate_feat_rejected_unless_repeatable(self):
        with self.assertRaises(RuleError):
            self._fighter(8, feats=[TOUGH, TOUGH])
        # 属性提升可重复选取
        actor = self._fighter(8, feats=[ASI, ASI],
                              choices={ASI + ".boost": ["str", "str"]})
        self.assertEqual(actor.profile.feats.count(ASI), 2)

    def test_feat_powers_are_available(self):
        actor = self._fighter(5, feats=[TOUGH])
        ids = {power.id for power in api.available_powers(self.bundle, actor)}
        self.assertIn("dnd2024.feat.tough.hp", ids)

    # --- 选单 -------------------------------------------------------
    def test_feat_options_filter_by_prereq(self):
        actor = self._fighter(5)
        options = api.feat_options(self.bundle, actor)
        self.assertEqual(options["count"], 79)
        rows = {row["id"]: row for row in options["feats"]}
        self.assertFalse(rows[BOON_STRENGTH]["selectable"], "19 级恩惠不该在 5 级可选")
        self.assertFalse(rows["dnd2024.feat.blessed_warrior"]["selectable"])
        self.assertTrue(rows[TOUGH]["selectable"])
        # 属性前提只提示不拦：力量 16 的战士能看到「演员」但标注 CHA 不足
        self.assertFalse(rows["dnd2024.feat.actor"]["selectable"])
        self.assertTrue(any("CHA" in item for item in rows["dnd2024.feat.actor"]["blocked"]))

    def test_taken_feat_not_selectable_again(self):
        actor = self._fighter(8, feats=[TOUGH])
        rows = {row["id"]: row for row in api.feat_options(self.bundle, actor)["feats"]}
        self.assertTrue(rows[TOUGH]["taken"])
        self.assertFalse(rows[TOUGH]["selectable"])

    def test_sheet_lists_feats_and_pending_choices(self):
        # 只选了技能：专精的候选就该只剩这一个已熟练的技能
        actor = self._fighter(8, feats=[SKILL_EXPERT],
                             choices={SKILL_EXPERT + ".skill": ["stealth"]})
        sheet = self._sheet(actor)
        self.assertEqual([row["id"] for row in sheet["feats"]], [SKILL_EXPERT])
        self.assertTrue(sheet["feats"][0]["pending"])
        self.assertEqual(len(sheet["choices_needed"]), 2)   # 专精 + 属性
        row = sheet["feats"][0]
        self.assertEqual(len(row["choices"]), 3)
        expertise = [item for item in row["choices"] if item["id"] == "expertise"][0]
        self.assertEqual(expertise["options"], ["stealth"])
        self.assertEqual(expertise["remaining"], 1)


ABIL = ("str", "dex", "con", "int", "wis", "cha")


def _xphb_ability_specs():
    """`data/raw/_5e_feats.json` 里 XPHB 条目的 ability 字段（权威原文）。"""
    path = ROOT / "data" / "raw" / "_5e_feats.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8")).get("feat") or []
    rows = raw if isinstance(raw, list) else list(raw.values())
    out = {}
    for item in rows:
        if isinstance(item, dict) and item.get("source") == "XPHB":
            out[item["name"]] = item
    return out


def _expected_from_spec(spec):
    """把 XPHB 的 ability 写法折成 (允许的属性集, 总点数)。"""
    pools, total = set(), 0
    for entry in spec or ():
        if not isinstance(entry, dict) or entry.get("hidden"):
            continue
        if "choose" in entry:
            chosen = entry["choose"] or {}
            froms = [str(item).lower() for item in (chosen.get("from") or ())]
            pools |= set(froms) if froms else set(ABIL)
            total = max(total, int(chosen.get("amount") or 1) * int(chosen.get("count") or 1))
        else:
            keys = {key for key in entry if key in ABIL}
            if keys:
                pools |= keys
                total = max(total, sum(int(entry[key]) for key in keys))
    return pools, total


class FeatAuthorityTest(unittest.TestCase):
    """属性加值必须与 XPHB 原文一致 —— 中文说明只是兜底，不是权威。

    这条测试是 P5g 那个「重要发现」的永久护栏：旧数据的 `effects` 只记了恩惠的
    ability_boost，40 多个通用专长的 +1 全在中文说明里；而中文说明本身也有错
    （骑乘战斗者写「智力或感知」，原文是 力量/敏捷/感知）。生成器现在先读原文，
    这个测试保证以后重新生成时不会悄悄退回按中文猜。
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        cls.raw = _xphb_ability_specs()

    def test_every_ability_bonus_matches_source(self):
        checked = 0
        for feat in self.bundle.feats.values():
            en = feat.name.en
            item = self.raw.get(en) or self.raw.get(en.split(" (")[0])
            if not item or not item.get("ability"):
                continue
            pools, total = _expected_from_spec(item["ability"])
            if not pools:
                continue
            boost = [c for c in feat.choices if c.kind == "ability_boost"]
            if not boost:
                # 坚毅把加值绑在「选哪项豁免」上，等价但走 save 通道
                save = [c for c in feat.choices if c.kind == "save"]
                self.assertTrue(save and save[0].boost == 1, "%s 丢了属性加值" % en)
                continue
            self.assertEqual(len(boost), 1, en)
            choice = boost[0]
            self.assertEqual(set(choice.pool or ABIL), pools, "%s 的可选属性与原文不符" % en)
            self.assertEqual(choice.count * choice.amount, total, "%s 的加值点数与原文不符" % en)
            self.assertEqual(choice.cap, 30 if feat.kind == "epic_boon" else 20, en)
            checked += 1
        self.assertGreaterEqual(checked, 50, "只对上了 %d 条，数据源可能读错" % checked)


class RepeatFeatTest(unittest.TestCase):
    """G11：同一个专长登记两次时，两组选择各存各的。

    属性提升 4 级一次、8 级一次。键只写专长 id 的话，第二次的 +2 会把第一次覆盖 ——
    结果是「拿了两次属性提升只加了 2 点」，还查不出原因。
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _fighter(self, level, feats, choices):
        return api.new_character(
            self.bundle, "dnd2024.class.fighter", level, dict(SCORES),
            feats=feats, choices=choices)

    def test_two_instances_do_not_overwrite(self):
        actor = self._fighter(8, [ASI, ASI], {
            ASI + ".boost": ("str", "str"),
            ASI + "#1.boost": ("con", "con"),
        })
        self.assertEqual(actor.statblock.abilities.score("str"), SCORES["str"] + 2)
        self.assertEqual(actor.statblock.abilities.score("con"), SCORES["con"] + 2)

    def test_second_instance_pending_reported_by_index(self):
        actor = self._fighter(8, [ASI, ASI], {ASI + ".boost": ("str", "str")})
        needed = api.character_sheet(actor, self.bundle)["choices_needed"]
        self.assertEqual(needed, [ASI + "#1.boost"])


class HonestyMarkTest(unittest.TestCase):
    """「这条专长到底算没算进数值」必须能在数据里读出来。

    没有这个标记，界面只能把 79 条专长画得一样 —— 玩家会以为「警觉」的
    +5 先攻已经算进去了。这一组盯三件事：词汇封闭、有 choices 的一定算数、
    「只有文字」的那一档真的存在（不是空集合）。
    """

    STATUSES = {"counted", "active", "onhit", "dice", "manual", "text"}

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        cls.sheet = api.character_sheet(
            api.new_character(cls.bundle, "dnd2024.class.fighter", 20, dict(SCORES)), cls.bundle)

    def test_every_feat_has_a_known_status(self):
        for feat in self.bundle.feats.values():
            status = api._feat_status(feat)
            self.assertIn(status, self.STATUSES, feat.id)

    def test_feats_with_choices_are_counted(self):
        for feat in self.bundle.feats.values():
            if feat.choices:
                self.assertEqual(api._feat_status(feat), "counted", feat.id)

    def test_text_only_feats_exist_and_are_labelled(self):
        text_only = [feat.id for feat in self.bundle.feats.values()
                     if api._feat_status(feat) == "text"]
        self.assertGreater(len(text_only), 0,
                           "一条「只有文字」的都没有 —— 标记大概率是假的")

    def test_power_status_distinguishes_buttons(self):
        """有按钮的能力在使用时结算，不能和「只有文字」混为一谈。"""
        from dnd5r.rules.build import available_powers
        from dnd5r.rules.contributions import power_status

        actor = api.new_character(self.bundle, "dnd2024.class.fighter", 5, dict(SCORES))
        statuses = {power.name.zh: power_status(power) for power in available_powers(self.bundle, actor)}
        self.assertEqual(statuses.get("回气"), "active")
        self.assertEqual(statuses.get("额外攻击"), "counted")

    def test_sheet_rows_carry_status(self):
        actor = api.new_character(self.bundle, "dnd2024.class.fighter", 8, dict(SCORES),
                                  feats=[ALERT])
        sheet = api.character_sheet(actor, self.bundle)
        self.assertEqual(sheet["feats"][0]["status"], "text")
        for power in sheet["powers"]:
            self.assertIn(power["status"], self.STATUSES)


class AbilityScoreImprovementTest(unittest.TestCase):
    """G35：4 级起的属性提升 / 自选专长必须真的拿得到。

    修之前：只有 `new_character(feats=...)` 能登记专长，升到 4 级什么也不会发生，
    职业 YAML 里那条特性只是规则文字。这一组盯五件事：

      1. 「几级给名额」是**数据**（`asi_levels`），战士 6/14、盗贼 10 不能少；
      2. 名额账：给了几次 / 用了几次 / 还剩几次；
      3. `add_feat` 一步把专长和选择项都写进去（不留「有名额但没加属性」的中间态）；
      4. 重复选取分格（第二次的 +2 不覆盖第一次）；改第二次不动第一次；
      5. 去掉一条能真的退回去（选择项一起清掉，不然下次加同一条会吃上旧选择）。
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def _fighter(self, level):
        return api.new_character(self.bundle, "dnd2024.class.fighter", level, dict(SCORES))

    # --- 1. 数据 -------------------------------------------------------
    def test_asi_levels_are_data(self):
        expected = {
            "barbarian": [4, 8, 12, 16], "bard": [4, 8, 12, 16],
            "cleric": [4, 8, 12, 16], "druid": [4, 8, 12, 16],
            "fighter": [4, 6, 8, 12, 14, 16], "monk": [4, 8, 12, 16],
            "paladin": [4, 8, 12, 16], "ranger": [4, 8, 12, 16],
            "rogue": [4, 8, 10, 12, 16], "sorcerer": [4, 8, 12, 16],
            "warlock": [4, 8, 12, 16], "wizard": [4, 8, 12, 16],
        }
        for slug, levels in expected.items():
            class_def = self.bundle.classes["dnd2024.class.%s" % slug]
            self.assertEqual([int(item) for item in class_def.asi_levels], levels, slug)

    def test_asi_levels_must_be_strictly_increasing(self):
        """乱序或重复只会在某个随机等级多给/少给一次，界面上看不出来 —— 加载期就炸。"""
        from dnd5r.content.classes import _parse_asi_levels
        with self.assertRaises(PluginError):
            _parse_asi_levels([8, 4], "test")
        with self.assertRaises(PluginError):
            _parse_asi_levels([4, 4], "test")
        with self.assertRaises(PluginError):
            _parse_asi_levels([0], "test")

    # --- 2. 名额账 -----------------------------------------------------
    def test_ledger_counts_by_class_level(self):
        cases = [(1, 0), (3, 0), (4, 1), (5, 1), (6, 2), (8, 3), (16, 6)]
        for level, granted in cases:
            ledger = api.feat_ledger(self.bundle, self._fighter(level).profile)
            self.assertEqual(ledger["granted"], granted, level)
            self.assertEqual(ledger["pending"], granted, level)

    def test_ledger_is_per_class_not_total_level(self):
        """战士 4 兼法师 4 = 两次，不是按总等级 8 级算出的三次。"""
        actor = api.new_character(
            self.bundle, "dnd2024.class.fighter", 4,
            {"str": 13, "dex": 14, "con": 14, "int": 14, "wis": 10, "cha": 8},
            extra_classes=(("dnd2024.class.wizard", 4),))
        self.assertEqual(api.feat_ledger(self.bundle, actor.profile)["granted"], 2)

    def test_ledger_counts_repeats_and_origin_feat_separately(self):
        """起源专长来自背景，不占名额；属性提升登记两次就用了两次。"""
        actor = api.new_character(
            self.bundle, "dnd2024.class.fighter", 8, dict(SCORES),
            feats=[ASI, ASI], choices={ASI + ".boost": ("str", "str"),
                                      ASI + "#1.boost": ("con", "con")},
            background="dnd2024.background.soldier")
        ledger = api.feat_ledger(self.bundle, actor.profile)
        self.assertEqual(ledger["used"], 2)
        self.assertEqual(ledger["pending"], 1)
        self.assertEqual(ledger["over"], 0)

    def test_sheet_carries_feat_slots(self):
        sheet = api.character_sheet(self._fighter(4), self.bundle)
        self.assertEqual(sheet["feat_slots"]["pending"], 1)
        self.assertEqual(sheet["feat_slots"]["levels"], "4/6/8/12/14/16")

    # --- 3. 加专长 -----------------------------------------------------
    def test_add_feat_applies_bonus_in_one_step(self):
        actor = self._fighter(4)
        before = actor.statblock.abilities.score("str")
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("str", "str")})
        self.assertEqual(actor.statblock.abilities.score("str"), before + 2)
        self.assertEqual(api.feat_ledger(self.bundle, actor.profile)["pending"], 0)

    def test_add_feat_requires_a_spare_slot(self):
        """4 级只有一次：用掉以后再加就该拒绝，而且话说清楚是「没名额」而不是「等级不够」。"""
        actor = api.add_feat(self._fighter(4), self.bundle, ASI,
                             picks={"boost": ("str", "str")})
        with self.assertRaises(RuleError) as caught:
            api.add_feat(actor, self.bundle, ASI, picks={"boost": ("dex", "dex")})
        self.assertIn("属性提升名额", str(caught.exception))

    def test_add_feat_below_level_four_is_refused_by_prereq(self):
        with self.assertRaises(RuleError) as caught:
            api.add_feat(self._fighter(3), self.bundle, ASI,
                         picks={"boost": ("str", "str")})
        self.assertIn("4 级", str(caught.exception))

    def test_add_feat_rejects_origin_feats(self):
        """起源专长由背景给。从这里加会造出「1 级手上有三个起源专长」。"""
        with self.assertRaises(RuleError) as caught:
            api.add_feat(self._fighter(8), self.bundle, ALERT)
        self.assertIn("背景或职业特性", str(caught.exception))

    def test_add_feat_keeps_runtime_state(self):
        """加专长要重建，但当前 HP / 状态不能跟着回满。"""
        actor = self._fighter(4)
        actor.hp.current = 3
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("con", "con")})
        self.assertEqual(actor.hp.current, 3)

    def test_add_feat_without_picks_leaves_it_pending(self):
        """先加专长、稍后再选也可以 —— 「还没选」不是错误，但要能在界面里看见。"""
        actor = api.add_feat(self._fighter(4), self.bundle, ASI)
        sheet = api.character_sheet(actor, self.bundle)
        self.assertTrue(sheet["feats"][-1]["pending"])
        self.assertEqual(sheet["choices_needed"], [ASI + ".boost"])

    # --- 4. 重复选取 ---------------------------------------------------
    def test_second_instance_gets_its_own_slot(self):
        actor = self._fighter(8)
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("str", "str")})
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("con", "con")})
        self.assertEqual(actor.profile.feats.count(ASI), 2)
        self.assertEqual(actor.statblock.abilities.score("str"), SCORES["str"] + 2)
        self.assertEqual(actor.statblock.abilities.score("con"), SCORES["con"] + 2)

    def test_sheet_rows_carry_index(self):
        actor = self._fighter(8)
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("str", "str")})
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("con", "con")})
        rows = [row for row in api.character_sheet(actor, self.bundle)["feats"]
                if row["id"] == ASI]
        self.assertEqual([row["index"] for row in rows], [0, 1])
        self.assertEqual(rows[1]["choices"][0]["key"], ASI + "#1.boost")

    def test_editing_second_instance_leaves_first_alone(self):
        actor = self._fighter(8)
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("str", "str")})
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("con", "con")})
        actor = api.set_feat_choice(actor, self.bundle, ASI, "boost", ("wis", "wis"),
                                    index=1)
        self.assertEqual(actor.statblock.abilities.score("str"), SCORES["str"] + 2)
        self.assertEqual(actor.statblock.abilities.score("con"), SCORES["con"])
        self.assertEqual(actor.statblock.abilities.score("wis"), SCORES["wis"] + 2)

    # --- 5. 去掉 -------------------------------------------------------
    def test_remove_feat_reverts_and_clears_choices(self):
        actor = self._fighter(4)
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("str", "str")})
        actor = api.remove_feat(actor, self.bundle, ASI)
        self.assertEqual(actor.statblock.abilities.score("str"), SCORES["str"])
        self.assertNotIn(ASI + ".boost", actor.profile.choices)
        self.assertEqual(api.feat_ledger(self.bundle, actor.profile)["pending"], 1)

    def test_remove_feat_drops_the_last_instance(self):
        actor = self._fighter(8)
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("str", "str")})
        actor = api.add_feat(actor, self.bundle, ASI, picks={"boost": ("con", "con")})
        actor = api.remove_feat(actor, self.bundle, ASI)
        self.assertEqual(actor.profile.feats.count(ASI), 1)
        self.assertEqual(actor.statblock.abilities.score("str"), SCORES["str"] + 2)
        self.assertEqual(actor.statblock.abilities.score("con"), SCORES["con"])
        self.assertNotIn(ASI + "#1.boost", actor.profile.choices)

    def test_remove_feat_refuses_class_granted_feats(self):
        actor = api.new_character(self.bundle, "dnd2024.class.fighter", 4, dict(SCORES),
                                  background="dnd2024.background.soldier")
        with self.assertRaises(RuleError):
            api.remove_feat(actor, self.bundle, "dnd2024.feat.savage_attacker")

    # --- 6. 升级视图 ---------------------------------------------------
    def test_level_up_view_mentions_the_new_slot(self):
        """升到 4 级就该提示「还有一次属性提升没用」，否则玩家永远不知道这事。"""
        from dnd5r.api.progress import level_up_view
        view = level_up_view(self.bundle, self._fighter(3))
        steps = [row["step"] for row in view["needs"]]
        self.assertIn("feats", steps)


if __name__ == "__main__":
    unittest.main()
