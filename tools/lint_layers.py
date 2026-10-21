# -*- coding: utf-8 -*-
"""分层守护：把设计文档里的硬约束变成可执行检查。

C1 内核零内容    C2 内核零 UI     C3 前端零规则    C4 随机可注入
C6 插件只用公开原语                C8 等级不可互换

用法：python tools/lint_layers.py [--root .]
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

FORBIDDEN = [
    # 职业
    "barbarian", "bard", "cleric", "druid", "fighter", "monk",
    "paladin", "ranger", "rogue", "sorcerer", "warlock", "wizard",
    # 常见法术与怪物
    "fireball", "magic_missile", "wild_shape", "rage", "sneak_attack",
    "eldritch", "metamagic", "goblin", "dragon", "beholder",
]

CORE_DIRS = ("kernel", "rules", "model")
PLUGIN_ALLOWED = ("dnd5r.plugin", "dnd5r.api")


def py_files(root: Path):
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        print("[FAIL] 语法错误 %s: %s" % (path, exc))
        return None


def imported_modules(tree: ast.Module) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                prefix = "." * (node.level or 0)
                found.append(prefix + node.module)
    return found


def check_c1(pkg: Path) -> list[str]:
    hits = []
    for folder in CORE_DIRS:
        for path in py_files(pkg / folder):
            text = path.read_text(encoding="utf-8").lower()
            for word in FORBIDDEN:
                if re.search(r"\b%s\b" % re.escape(word), text):
                    hits.append("%s 出现内容名词 %r（C1）" % (path.relative_to(pkg.parent), word))
    return hits


def check_c2(pkg: Path) -> list[str]:
    hits = []
    for path in py_files(pkg):
        tree = parse(path)
        if tree is None:
            continue
        if any(mod.split(".")[0] == "tkinter" for mod in imported_modules(tree)):
            hits.append("%s 让后端依赖了 tkinter（C2）" % path.relative_to(pkg.parent))
    return hits


def check_c3(root: Path) -> list[str]:
    hits = []
    for path in py_files(root / "apps"):
        tree = parse(path)
        if tree is None:
            continue
        for module in imported_modules(tree):
            if not module.startswith("dnd5r"):
                continue
            if not (module == "dnd5r.api" or module.startswith("dnd5r.api.")):
                hits.append("%s 越过 api 直接引用 %s（C3）" % (path.relative_to(root), module))
    return hits


def check_c4(pkg: Path) -> list[str]:
    hits = []
    for path in py_files(pkg):
        if path.name == "rng.py" and path.parent.name == "kernel":
            continue
        tree = parse(path)
        if tree is None:
            continue
        for module in imported_modules(tree):
            if module == "random":
                hits.append("%s 私自引入 random，应走 kernel.rng（C4）" % path.relative_to(pkg.parent))
    return hits


def check_c6(root: Path) -> list[str]:
    hits = []
    for path in py_files(root / "plugins"):
        tree = parse(path)
        if tree is None:
            continue
        for module in imported_modules(tree):
            if not module.startswith("dnd5r"):
                continue
            if not any(module == ok or module.startswith(ok + ".") for ok in PLUGIN_ALLOWED):
                hits.append("%s 引用了内部模块 %s（C6）" % (path.relative_to(root), module))
    return hits


def _annotation_name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp):  # X | None
        left = _annotation_name(node.left)
        right = _annotation_name(node.right)
        return left if "Level" in left else right
    return ""


def check_c8(pkg: Path) -> list[str]:
    hits = []
    for folder in CORE_DIRS:
        for path in py_files(pkg / folder):
            tree = parse(path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                args = list(node.args.args) + list(node.args.kwonlyargs)
                for arg in args:
                    if arg.arg != "level":
                        continue
                    ann = _annotation_name(arg.annotation)
                    if ann not in ("TotalLevel", "ClassLevel"):
                        hits.append(
                            "%s:%d 的参数 level 必须标注 TotalLevel 或 ClassLevel，实际 %r（C8）"
                            % (path.relative_to(pkg.parent), node.lineno, ann or None)
                        )
    return hits


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="分层与硬约束检查")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    pkg = root / "dnd5r"
    if not pkg.exists():
        print("[FAIL] 找不到 dnd5r 包：%s" % pkg)
        return 1

    checks = [
        ("C1 内核零内容", check_c1(pkg)),
        ("C2 内核零 UI", check_c2(pkg)),
        ("C3 前端零规则", check_c3(root)),
        ("C4 随机可注入", check_c4(pkg)),
        ("C6 插件只用公开原语", check_c6(root)),
        ("C8 等级不可互换", check_c8(pkg)),
    ]

    failures = 0
    print("=== 分层检查 (%s) ===" % pkg.name)
    for label, issues in checks:
        if issues:
            failures += len(issues)
            print("[FAIL] %s：%d 项" % (label, len(issues)))
            for issue in issues[:12]:
                print("       %s" % issue)
            if len(issues) > 12:
                print("       ... 另有 %d 项" % (len(issues) - 12))
        else:
            print("[PASS] %s" % label)

    print("LINT %s（%d 处违规）" % ("OK" if not failures else "FAILED", failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
