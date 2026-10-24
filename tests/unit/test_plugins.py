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
        self.assertEqual(len(result.manifests), 2)      # demo + homebrew（P14）
        self.assertGreaterEqual(len(result.ids), 2)
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


class OverlayTest(unittest.TestCase):
    """P14：overlay 两语义 —— add 直接进；replace 必须在清单里声明。"""

    def test_declared_replace_wins(self):
        from dnd5r.content import load_all

        bundle = load_all(FIXTURES / "plugins_ok")
        self.assertFalse(bundle.errors, bundle.errors)
        self.assertIn("demo.weapon.stick", bundle.weapons)          # add
        self.assertEqual(bundle.weapons["demo.weapon.club"].name.zh, "木棒（自制）")
        self.assertTrue(any("demo.weapon.club" in row for row in bundle.replaced))

    def test_undeclared_duplicate_is_an_error(self):
        import shutil
        import tempfile

        from dnd5r.content import load_all

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURES / "plugins_ok" / "demo", root / "demo")
            shutil.copytree(FIXTURES / "plugins_ok" / "homebrew", root / "homebrew")
            manifest = (root / "homebrew" / "plugin.yaml").read_text(encoding="utf-8")
            (root / "homebrew" / "plugin.yaml").write_text(
                manifest.replace("replaces: [demo.weapon.club]", "replaces: []"),
                encoding="utf-8")
            bundle = load_all(root)
            self.assertFalse(bundle.ok)
            self.assertTrue(any("replaces" in row for row in bundle.errors),
                            bundle.errors)

    def test_requires_version_math(self):
        from dnd5r.plugin import check_requires, load_manifest

        manifest = load_manifest(FIXTURES / "plugins_ok" / "homebrew" / "plugin.yaml")
        self.assertEqual(check_requires(manifest, {"demo-core": "0.1.0"}), [])
        self.assertEqual(check_requires(manifest, {"demo-core": "0.1"}), [])   # 0.1 == 0.1.0
        # 要求 >= 0.1：对方 9.9.9 也满足（>= 是下限，不是精确匹配）
        self.assertEqual(check_requires(manifest, {"demo-core": "9.9.9"}), [])
        from dnd5r.plugin import parse_manifest
        wanting = parse_manifest({
            "id": "picky", "kind": "content", "api": 1,
            "name": {"zh": "挑版本", "en": "Picky"},
            "requires": ["demo-core >= 2.0"],
        })
        problems = check_requires(wanting, {"demo-core": "0.1.0"})
        self.assertTrue(any(">= 2.0" in row and "0.1.0" in row for row in problems))
        self.assertTrue(check_requires(manifest, {}))                           # 缺依赖
