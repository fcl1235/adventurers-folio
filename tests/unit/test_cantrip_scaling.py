# -*- coding: utf-8 -*-
"""P7c 验收：戏法伤害随**角色等级**成长（G10）。

以前 27 条戏法只存了 1 级那一档骰式，5/11/17 级的「Cantrip Upgrade」
只在英文正文里躺着。一个 11 级法师的火矢在卡上永远写着 1d10。

这一组测试盯三件事：

  1. 成长档按**角色等级**查（不是环位）—— 两条轴混了就会给 5 级角色 1 级骰
  2. 五种成长语义分开：伤害骰 / 额外伤害 / 光束数 / 射程 / 武器骰
     （把光束数当成伤害骰，会让「Eldritch Blast 11 级打 3d10」成立 —— 它是 3 道 1d10）
  3. 生成器的解析结果与内容文件逐条一致 —— 手工补的数据和生成器不能各说各话

数据里有 12 条戏法**没有**成长：那不是漏，是原文里就没有（幻影术、传讯术…）。
"""

import json
import unittest
from pathlib import Path

import dnd5r.api as api
from dnd5r.content import SCALING_KINDS, SpellDef, parse_spell
from dnd5r.kernel.errors import PluginError

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
RAW = ROOT / "data" / "raw" / "spells.json"

# 「有成长」的 15 条，按 kind 分组。数字是权威：改动内容就要改这里，是故意的。
EXPECTED = {
    "damage": {
        "fire_bolt": ("1d10", {5: "2d10", 11: "3d10", 17: "4d10"}),
        "ray_of_frost": ("1d8", {5: "2d8", 11: "3d8", 17: "4d8"}),
        "vicious_mockery": ("1d6", {5: "2d6", 11: "3d6", 17: "4d6"}),
        "acid_splash": ("1d6", {5: "2d6", 11: "3d6", 17: "4d6"}),
    },
    "extra_damage": {"true_strike": ("", {5: "1d6", 11: "2d6", 17: "3d6"})},
    "beams": {"eldritch_blast": ("1d10", {5: "2", 11: "3", 17: "4"})},
    "range": {"spare_the_dying": ("", {5: "30", 11: "60", 17: "120"})},
    "weapon_die": {"shillelagh": ("", {5: "d10", 11: "d12", 17: "2d6"})},
}


class CantripScalingDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)

    def test_count(self):
        rows = [spell for spell in self.bundle.spells.values() if spell.scaling]
        self.assertEqual(len(rows), 15)
        plain = [spell for spell in self.bundle.spells.values()
                 if spell.is_cantrip and not spell.scaling]
        # 12 条原文里没有成长（幻影术、传讯术、神导术…）
        self.assertEqual(len(plain), 12)
        self.assertEqual(len(rows) + len(plain), 27)

    def test_every_kind_present(self):
        kinds = {spell.scaling_kind for spell in self.bundle.spells.values() if spell.scaling}
        self.assertEqual(kinds, set(SCALING_KINDS))

    def test_values_match_table(self):
        for kind, spells in EXPECTED.items():
            for key, (base, levels) in spells.items():
                with self.subTest(spell=key):
                    spell = self.bundle.spell("dnd2024.spell.%s" % key)
                    self.assertEqual(spell.scaling_kind, kind)
                    self.assertEqual({int(k): str(v) for k, v in spell.scaling.items()}, levels)
                    if base:
                        self.assertEqual(spell.damage_at(0), base)

    def test_lookup_uses_character_level(self):
        spell = self.bundle.spell("dnd2024.spell.fire_bolt")
        self.assertEqual(spell.scaling_at(1), "")          # 1–4 级没有成长档
        self.assertEqual(spell.scaling_at(4), "")
        self.assertEqual(spell.scaling_at(5), "2d10")
        self.assertEqual(spell.scaling_at(10), "2d10")
        self.assertEqual(spell.scaling_at(11), "3d10")
        self.assertEqual(spell.scaling_at(17), "4d10")
        self.assertEqual(spell.scaling_at(20), "4d10")

    def test_ray_of_frost_is_not_beams(self):
        """Ray of Frost 的正文里有 'beam of blue-white light' —— 关键词判 kind 会误伤。"""
        spell = self.bundle.spell("dnd2024.spell.ray_of_frost")
        self.assertEqual(spell.scaling_kind, "damage")

    def test_beams_do_not_rewrite_damage(self):
        info = api.spell_info(self.bundle, "dnd2024.spell.eldritch_blast", character_level=11)
        self.assertEqual(info["scaling_now"], "3")
        # 11 级是 3 道 1d10，不是一次 3d10
        self.assertEqual(info["damage_now"], "1d10")

    def test_damage_kind_rewrites_damage(self):
        info = api.spell_info(self.bundle, "dnd2024.spell.fire_bolt", character_level=11)
        self.assertEqual(info["damage_now"], "3d10")
        low = api.spell_info(self.bundle, "dnd2024.spell.fire_bolt", character_level=3)
        self.assertEqual(low["damage_now"], "1d10")
        self.assertEqual(low["scaling_now"], "")

    def test_no_level_means_no_guess(self):
        """不传角色等级时不许按「1 级角色」给一个假骰式。"""
        info = api.spell_info(self.bundle, "dnd2024.spell.fire_bolt")
        self.assertNotIn("scaling_now", info)
        self.assertNotIn("damage_now", info)

    def test_non_cantrip_has_no_scaling(self):
        for spell in self.bundle.spells.values():
            if not spell.is_cantrip:
                self.assertEqual(spell.scaling, {}, spell.id)


class CantripScalingGuardTest(unittest.TestCase):
    """坏数据要在加载期炸，不要等到 5 级才发现骰子不对。"""

    def _spell(self, **overrides):
        data = {
            "id": "dnd2024.spell.test_cantrip",
            "name": {"zh": "测试", "en": "Test"},
            "level": 0,
            "school": "evocation",
            "text": {"zh": "测试", "en": "Test"},
            "scaling": {"kind": "damage", 5: "2d6", 11: "3d6", 17: "4d6"},
        }
        data.update(overrides)
        return data

    def test_accepts_valid(self):
        spell = parse_spell(self._spell())
        self.assertEqual(spell.scaling_kind, "damage")
        self.assertEqual(spell.scaling_at(5), "2d6")

    def test_rejects_unknown_kind(self):
        with self.assertRaises(PluginError):
            parse_spell(self._spell(scaling={"kind": "sparkles", 5: "2d6"}))

    def test_rejects_missing_kind(self):
        with self.assertRaises(PluginError):
            parse_spell(self._spell(scaling={5: "2d6"}))

    def test_rejects_wrong_levels(self):
        # 6 / 12 / 18 不是 2024 的成长档，写错了要当场报
        with self.assertRaises(PluginError):
            parse_spell(self._spell(scaling={"kind": "damage", 6: "2d6"}))

    def test_rejects_bad_dice(self):
        with self.assertRaises(PluginError):
            parse_spell(self._spell(scaling={"kind": "damage", 5: "2d"}))

    def test_rejects_negative_count(self):
        with self.assertRaises(PluginError):
            parse_spell(self._spell(scaling={"kind": "beams", 5: "0"}))

    def test_rejects_scaling_on_leveled_spell(self):
        """有环法术的长进走升环（damage 表），再写一条成长轴就有两个真相。"""
        with self.assertRaises(PluginError):
            parse_spell(self._spell(level=1,
                                    damage={1: "2d6"},
                                    scaling={"kind": "damage", 5: "3d6"}))

    def test_scaling_kind_without_table(self):
        with self.assertRaises(PluginError):
            parse_spell(self._spell(scaling={"kind": "damage"}))


class GeneratorAgreementTest(unittest.TestCase):
    """生成器的解析结果必须与内容文件逐条一致。

    这次的教训：内容是我用一次性脚本补的，生成器另写了一份逻辑。
    两份只要有一处不同（比如 Ray of Frost 的 beam 关键词），
    下次 `--force` 重跑就会把数据改掉，而没人会注意到。
    """

    def test_generator_matches_content(self):
        from tools.gen_spells import parse_scaling

        bundle = api.load_content(PLUGINS)
        rows = json.loads(RAW.read_text(encoding="utf-8"))["items"]
        checked = 0
        for row in rows:
            if int(row.get("level", 1)) != 0:
                continue
            kind, table = parse_scaling(row)
            slug = row["index"].lower().replace("-", "_")
            spell = bundle.spells.get("dnd2024.spell.%s" % slug)
            if spell is None:                     # 8 个 summon-* 不在内容里
                continue
            checked += 1
            self.assertEqual(spell.scaling_kind, kind, row["index"])
            self.assertEqual({int(k): str(v) for k, v in spell.scaling.items()}, table,
                             row["index"])
        self.assertEqual(checked, 27)


if __name__ == "__main__":
    unittest.main()
