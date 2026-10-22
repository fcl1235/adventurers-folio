# -*- coding: utf-8 -*-
"""内容加载：真实插件必须读得进来；坏内容必须只坏自己。"""

import shutil
import tempfile
import unittest
from pathlib import Path

from dnd5r.content import load_all, load_plugin, parse_class, parse_resource
from dnd5r.kernel.errors import PluginError
from dnd5r.model.levels import ClassLevel

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"

FIGHTER = "dnd2024.class.fighter"


class RealPluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_all(PLUGINS)

    def test_no_errors(self):
        self.assertEqual(self.bundle.errors, [])

    def test_has_fighter(self):
        self.assertIn(FIGHTER, self.bundle.classes)
        fighter = self.bundle.classes[FIGHTER]
        self.assertEqual(fighter.hit_die, 10)
        self.assertEqual(fighter.saves, ("str", "con"))
        self.assertEqual(int(fighter.subclass_level), 3)

    def test_all_texts_bilingual(self):
        for class_def in self.bundle.classes.values():
            self.assertTrue(class_def.name.zh and class_def.name.en)
            for power in class_def.powers:
                self.assertTrue(power.name.zh and power.name.en, power.id)
                self.assertTrue(power.text.zh and power.text.en, power.id)

    def test_power_counts_by_level(self):
        fighter = self.bundle.classes[FIGHTER]
        self.assertEqual(len(fighter.powers_at(ClassLevel(1))), 3)
        self.assertEqual(len(fighter.powers_at(ClassLevel(2))), 5)
        self.assertEqual(len(fighter.powers_at(ClassLevel(20))), 12)

    def test_buttons(self):
        fighter = self.bundle.classes[FIGHTER]
        names = [power.name.zh for power in fighter.powers_at(ClassLevel(2)) if power.is_button]
        self.assertEqual(names, ["回气", "行动激增"])

    def test_resource_capacity_table(self):
        fighter = self.bundle.classes[FIGHTER]
        second_wind = fighter.resource("dnd2024.resource.fighter.second_wind")
        self.assertEqual(second_wind.capacity_at(ClassLevel(1)), 2)
        self.assertEqual(second_wind.capacity_at(ClassLevel(4)), 3)
        self.assertEqual(second_wind.capacity_at(ClassLevel(10)), 4)
        self.assertEqual(second_wind.capacity_at(ClassLevel(20)), 4)
        self.assertEqual(second_wind.recover_on_short_rest, 1)

    def test_action_surge_threshold_table(self):
        fighter = self.bundle.classes[FIGHTER]
        surge = fighter.resource("dnd2024.resource.fighter.action_surge")
        self.assertEqual(surge.capacity_at(ClassLevel(2)), 1)
        self.assertEqual(surge.capacity_at(ClassLevel(16)), 1)
        self.assertEqual(surge.capacity_at(ClassLevel(17)), 2)

    def test_extra_attack_takes_max(self):
        fighter = self.bundle.classes[FIGHTER]
        self.assertEqual(fighter.total_attacks(ClassLevel(4)), 1)
        self.assertEqual(fighter.total_attacks(ClassLevel(5)), 2)
        self.assertEqual(fighter.total_attacks(ClassLevel(11)), 3)
        self.assertEqual(fighter.total_attacks(ClassLevel(20)), 4)

    def test_power_ids_registered(self):
        self.assertIn("dnd2024.class.fighter.second_wind", self.bundle.book.ids())
        self.assertIn("dnd2024.class.fighter.indomitable", self.bundle.book.ids())

    def test_triggered_powers_have_phase(self):
        for power in self.bundle.book.all():
            if power.kind.value == "triggered":
                self.assertIsNotNone(power.phase, power.id)


class ParseUnitTest(unittest.TestCase):
    def test_resource_needs_capacity(self):
        with self.assertRaises(PluginError):
            parse_resource({"id": "demo.pool.x", "kind": "charge"})

    def test_resource_bad_id(self):
        with self.assertRaises(PluginError):
            parse_resource({"id": "pool", "kind": "charge", "capacity": 1})

    def test_class_needs_hit_die(self):
        with self.assertRaises(PluginError):
            parse_class({"id": "demo.class.x", "name": {"zh": "x", "en": "x"}})

    def test_class_bad_save(self):
        with self.assertRaises(PluginError):
            parse_class({
                "id": "demo.class.x", "name": {"zh": "x", "en": "x"},
                "hit_die": 8, "saves": ["luck"],
            })

    def test_capacity_from_amount(self):
        resource = parse_resource({
            "id": "demo.pool.y", "kind": "point", "capacity": {"flat": 5, "times": "class_level"},
        })
        ref = {"prof_bonus": 2, "total_level": 3, "class_level": 3}
        self.assertEqual(resource.capacity_at(ClassLevel(3), ref), 15)
        with self.assertRaises(PluginError):
            resource.capacity_at(ClassLevel(3))


class ErrorIsolationTest(unittest.TestCase):
    """一个文件坏掉不能拖垮同插件的其它职业。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dnd5r_plugin_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, text: str) -> None:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _manifest(self, plugin_id="demo-plugin"):
        self._write("plugin.yaml", "id: %s\nkind: content\napi: 1\nname:\n  zh: 演示\n  en: Demo\n" % plugin_id)

    def test_broken_class_does_not_kill_plugin(self):
        self._manifest()
        self._write("classes/good.yaml", """
id: demo.class.good
name: {zh: 好职业, en: Good}
hit_die: 8
saves: [dex]
powers:
  - id: demo.class.good.power
    name: {zh: 能力, en: Power}
    text: {zh: 说明, en: Text}
    level: 1
    kind: passive
    effects:
      - note: {zh: 仅提示, en: Note only}
""")
        self._write("classes/bad.yaml", """
id: demo.class.bad
name: {zh: 坏职业, en: Bad}
hit_die: 0
""")
        content = load_plugin(self.tmp)
        self.assertIn("demo.class.good", content.classes)
        self.assertNotIn("demo.class.bad", content.classes)
        self.assertTrue(content.errors)
        self.assertTrue(any("hit_die" in item or "生命骰" in item for item in content.errors))

    def test_broken_yaml_is_reported(self):
        self._manifest()
        self._write("classes/broken.yaml", "id: demo.class.x\n  name: [unclosed\n")
        content = load_plugin(self.tmp)
        self.assertTrue(content.errors)

    def test_duplicate_class_across_plugins(self):
        root = self.tmp / "plugins"
        for name in ("a", "b"):
            folder = root / name
            folder.mkdir(parents=True)
            (folder / "plugin.yaml").write_text(
                "id: %s-plugin\nkind: content\napi: 1\nname:\n  zh: 演示\n  en: Demo\n" % name,
                encoding="utf-8")
            (folder / "classes").mkdir()
            (folder / "classes" / "same.yaml").write_text(
                "id: demo.class.same\nname: {zh: 同名, en: Same}\nhit_die: 8\n",
                encoding="utf-8")
        bundle = load_all(root)
        self.assertEqual(len(bundle.classes), 1)
        self.assertTrue(any("同时由" in item for item in bundle.errors))

    def test_missing_plugins_dir_is_empty(self):
        bundle = load_all(self.tmp / "nope")
        self.assertEqual(bundle.classes, {})
        self.assertEqual(bundle.errors, [])


if __name__ == "__main__":
    unittest.main()
