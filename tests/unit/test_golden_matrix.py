# -*- coding: utf-8 -*-
"""P7a 验收：三层对账矩阵本身的护栏。

矩阵是一张「覆盖面 × 差异登记」的网，网自己得有洞才不会漏鱼：

  1. 三层快照都在，条目数与层定义一致（少一层等于少测一半，但输出仍然全绿）
  2. 层 1 覆盖**全部 48 个子职**，且每个 id 都是内容里真存在的
  3. 层 2 的专长**一个都不能带属性加值** —— 带了就撞 G12（旧程序漏算属性），
     差异会来自 oracle 而不是内核，这一层就白测了
  4. `KNOWN_DELTAS` 每条原因都写清了（不许用「已知差异」四个字糊过去）
  5. 矩阵里出现的职业/变体都能在新内核里建出来（防止快照比内容旧）

第 3 条是这次真踩到的：最先挑的「哨兵 / 巫师杀手」看着像纯战斗专长，
2024 版其实都带「力量或敏捷 +1」，而且不选就只是 `pending`、不报错 ——
矩阵会显示零差异，等于什么都没测。
"""

import json
import unittest
from pathlib import Path

import dnd5r.api as api
from tools import golden

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"


class GoldenMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = api.load_content(PLUGINS)
        cls.class_rows = json.loads(golden.SNAPSHOT_CLASS.read_text(encoding="utf-8"))
        cls.layers = json.loads(golden.SNAPSHOT_LAYERS.read_text(encoding="utf-8"))

    def test_snapshots_exist(self):
        self.assertEqual(self.bundle.errors, [])
        self.assertTrue(self.class_rows, "层 0 快照是空的")
        self.assertIn("subclass", self.layers)
        self.assertIn("feat", self.layers)

    def test_class_layer_size(self):
        # 12 职业 × 20 级
        self.assertEqual(len(self.class_rows), 12 * 20)

    def test_subclass_layer_covers_every_subclass(self):
        covered = {key.partition("|")[2].rpartition(":")[0]
                   for key in self.layers["subclass"]}
        self.assertEqual(covered, set(self.bundle.subclasses))
        self.assertEqual(len(covered), 48)
        self.assertEqual(len(self.layers["subclass"]), 48 * 20)

    def test_feat_layer_has_no_ability_boost(self):
        """带属性加值的专长不能进层 2 —— 也说明它必须被选完才算测过。"""
        for feat_id, _legacy, _classes in golden.FEAT_CASES:
            with self.subTest(feat=feat_id):
                feat = self.bundle.feats[feat_id]
                boost = [choice.id for choice in feat.choices
                         if choice.kind == "ability_boost"]
                self.assertEqual(boost, [], "%s 带属性加值，不该进专长层" % feat_id)

    def test_feat_layer_keys_are_buildable(self):
        """每个专长变体都得能真的建成角色，否则区别只在于「跳过」而不是「测过」。"""
        for feat_id, _legacy, classes in golden.FEAT_CASES:
            self.assertIn(feat_id, self.bundle.feats)
            for class_id in (classes or ("fighter",)):
                actor = api.new_character(
                    self.bundle, golden.CLASS_MAP[class_id], 4, golden.SCORES,
                    name_zh="矩阵", name_en="Matrix", feats=(feat_id,))
                self.assertTrue(actor.profile.feats)

    def test_known_deltas_are_explained(self):
        self.assertTrue(golden.KNOWN_DELTAS, "白名单空了就把这段测试删掉，别留假护栏")
        for key, reason in golden.KNOWN_DELTAS.items():
            with self.subTest(key=key):
                self.assertEqual(len(key), 4)
                self.assertIn(key[0], golden.LAYERS)
                self.assertGreater(len(reason), 15, "原因写得太短，等于没写")
                self.assertNotEqual(reason.strip(), "已知差异")

    def test_known_delta_keys_point_at_real_content(self):
        for layer, class_id, variant, field in golden.KNOWN_DELTAS:
            with self.subTest(key=(layer, class_id, variant, field)):
                self.assertIn(field, golden.FIELDS)
                if layer == "subclass":
                    self.assertIn(variant, self.bundle.subclasses)
                elif layer == "feat":
                    self.assertIn(variant, self.bundle.feats)
                else:
                    self.assertEqual(variant, "")

    def test_subclass_snapshot_uses_kernel_ids(self):
        """层 1 的 key 必须两边同源：旧程序存英文名、内核存 id 时，比对会「0 组全绿」。"""
        for key in list(self.layers["subclass"])[:5]:
            _class_id, _, rest = key.partition("|")
            variant = rest.rpartition(":")[0]
            self.assertTrue(variant.startswith("dnd2024.subclass."), key)


if __name__ == "__main__":
    unittest.main()
