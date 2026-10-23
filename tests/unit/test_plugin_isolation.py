# -*- coding: utf-8 -*-
"""P8 出口验收：**删掉任一插件，程序仍然启动**。

这条不是「健壮性加分项」，而是分层架构的**唯一实证**：
如果内容缺席就崩，说明规则代码里还藏着对某份内容的硬依赖 ——
那些依赖就是 C1（内核零内容）漏网的地方，只是平时被插件遮着看不见。

三种缺法各测一次：

  1. 整个插件目录不存在（刚 clone 下来还没放内容）
  2. 插件缺 `spells/`（生成器没跑过）
  3. 插件缺 `feats/` 与 `tools.yaml`

每种都要求：`load_content` 不抛异常、`character_sheet` 能算、桌面端能建起来
（`selftest=True`，窗口全程 withdrawn）。

另外把 `errors` 的语义钉住：**错误是警告不是异常** ——
内容有问题时程序要能启动并把问题列出来，而不是让玩家对着一个堆栈发呆。
"""

import shutil
import tempfile
import unittest
from pathlib import Path

import dnd5r.api as api
from apps.desktop.app import DesktopApp

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
CORE = "dnd2024-core"
FIGHTER = "dnd2024.class.fighter"
WIZARD = "dnd2024.class.wizard"
SCORES = {"str": 16, "dex": 14, "con": 14, "int": 18, "wis": 12, "cha": 8}


class PluginIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dnd5r-plugins-"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _copy(self, name: str, drop: tuple[str, ...] = ()) -> Path:
        """拷一份插件目录，按 `drop` 删掉里面的相对路径。"""
        target = self.tmp / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(PLUGINS, target)
        for rel in drop:
            path = target / CORE / rel
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        return target

    def _app(self, bundle, actor):
        app = DesktopApp(bundle, actor, selftest=True)
        self.addCleanup(app.destroy)
        return app

    # --- 1. 一份内容都没有 ---------------------------------------------
    def test_no_plugin_dir_at_all(self):
        empty = self.tmp / "nothing-here"
        empty.mkdir(exist_ok=True)
        bundle = api.load_content(empty)
        self.assertEqual(bundle.errors, [])
        self.assertEqual(bundle.classes, {})

        actor = api.create_actor("甲", "A", SCORES, [(FIGHTER, 5)])
        sheet = api.character_sheet(actor, bundle)
        self.assertEqual(sheet["total_level"], 5)
        self.assertEqual(sheet.get("spells") or [], [])

        app = self._app(bundle, actor)
        self.assertFalse(app.winfo_ismapped(), "selftest 模式不许把窗口弹出来")
        # 页数写成「等于标签页数」而不是写死 4/5：以后加页面不该改这条测试，
        # 真正要盯的是「每个标签都有页面、且都建出来了」
        self.assertEqual(len(app.pages), len(app.book.tabs()))
        # 战斗页在空内容下也得建得出来：怪物名单是空的，但不许崩
        self.assertEqual(app.encounter_page.roster_pane.row_count, 0)

    # --- 2. 缺法术 ------------------------------------------------------
    def test_missing_spells_still_starts(self):
        bundle = api.load_content(self._copy("no-spells", ("spells",)))
        # 法术表还在，于是它会报「引用了不存在的法术」—— 这是警告，不是异常
        self.assertTrue(bundle.errors)
        self.assertTrue(any("法术表" in issue for issue in bundle.errors))
        self.assertEqual(bundle.spells, {})
        self.assertEqual(len(bundle.classes), 12)

        actor = api.new_character(bundle, WIZARD, 5, SCORES)
        app = self._app(bundle, actor)
        self.assertEqual(app.sheet.get("spells") or [], [])
        # 法术页在空内容下也要能重画（不是「有内容才不崩」）
        app.spells.refresh(app.sheet)

    # --- 3. 缺专长与工具 ------------------------------------------------
    def test_missing_feats_and_tools_still_starts(self):
        bundle = api.load_content(
            self._copy("no-feats", ("feats", "tools.yaml")))
        self.assertEqual(bundle.feats, {})
        self.assertEqual(bundle.tools, {})
        self.assertEqual(len(bundle.classes), 12)

        actor = api.new_character(bundle, FIGHTER, 5, SCORES)
        app = self._app(bundle, actor)
        self.assertEqual(app.sheet.get("feats") or [], [])
        self.assertIsNotNone(app.feats)

    # --- 4. 错误是清单不是异常 ------------------------------------------
    def test_errors_do_not_block_loading(self):
        """一份内容有问题，不该连累其它插件 —— 能用的部分照常可用。"""
        bundle = api.load_content(self._copy("half-broken", ("spells",)))
        self.assertTrue(bundle.errors)
        self.assertGreater(len(bundle.classes), 0)
        self.assertGreater(len(bundle.subclasses), 0)
        # 召唤物指向的法术没了，也要能被收进 errors 而不是炸掉
        actor = api.new_character(bundle, FIGHTER, 5, SCORES)
        self.assertIsNotNone(api.character_sheet(actor, bundle))


if __name__ == "__main__":
    unittest.main()
