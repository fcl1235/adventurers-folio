# -*- coding: utf-8 -*-
"""插件与内容校验测试：清单、双语、id 唯一。"""

import unittest
from pathlib import Path

from dnd5r.kernel.errors import PluginError
from dnd5r.plugin import API_VERSION, parse_manifest
from tools.plugins_cli import check_root

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class ManifestTest(unittest.TestCase):
    def good(self, **changes):
        data = {
            "id": "demo-core",
            "kind": "content",
            "api": API_VERSION,
            "name": {"zh": "示例核心", "en": "Demo Core"},
        }
        data.update(changes)
        return data

    def test_minimal_manifest(self):
        manifest = parse_manifest(self.good())
        self.assertEqual(manifest.id, "demo-core")
        self.assertEqual(manifest.name.en, "Demo Core")

    def test_bilingual_name_required(self):
        with self.assertRaises(PluginError):
            parse_manifest(self.good(name={"zh": "示例核心"}))

    def test_bad_kind_rejected(self):
        with self.assertRaises(PluginError):
            parse_manifest(self.good(kind="theme"))

    def test_api_must_match(self):
        with self.assertRaises(PluginError):
            parse_manifest(self.good(api=99))

    def test_bad_id_rejected(self):
        with self.assertRaises(PluginError):
            parse_manifest(self.good(id="Demo Core"))

    def test_missing_field_reported(self):
        data = self.good()
        del data["kind"]
        with self.assertRaises(PluginError):
            parse_manifest(data)


class CheckRootTest(unittest.TestCase):
    def test_good_fixture_passes(self):
        result = check_root(FIXTURES / "plugins_ok", with_terms=True)
        self.assertTrue(result.ok, result.issues)
        self.assertEqual(len(result.manifests), 1)
        self.assertEqual(len(result.ids), 1)
        self.assertGreaterEqual(len(result.texts), 2)

    def test_bad_fixture_reports_all_problems(self):
        result = check_root(FIXTURES / "plugins_bad")
        self.assertFalse(result.ok)
        joined = " | ".join(result.issues)
        self.assertIn("缺少语言", joined)        # 缺 en
        self.assertIn("id 重复", joined)
        self.assertIn("缺少字段", joined)        # 坏清单

    def test_plugin_exists_in_repo(self):
        result = check_root(Path(__file__).resolve().parents[2] / "plugins")
        self.assertTrue(result.ok, result.issues)
        self.assertEqual([m.id for m in result.manifests], ["dnd2024-core"])


if __name__ == "__main__":
    unittest.main()
