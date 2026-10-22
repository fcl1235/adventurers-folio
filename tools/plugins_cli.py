# -*- coding: utf-8 -*-
"""插件校验：清单、id 唯一性、双语齐全（C7）、术语一致性。

用法：
  python -m tools.plugins_cli check --root plugins
  python -m tools.plugins_cli check --root plugins --terms
  python -m tools.plugins_cli list  --root plugins
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from dnd5r.kernel.errors import PluginError, TextError
from dnd5r.kernel.glossary import Glossary
from dnd5r.kernel.ids import is_valid
from dnd5r.kernel.text import Text
from dnd5r.loader import iter_plugin_dirs
from dnd5r.plugin import Manifest, load_manifest


@dataclass
class CheckResult:
    manifests: list[Manifest] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    texts: list[tuple[Text, str]] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.issues


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PluginError("%s 不是合法 YAML：%s" % (path, exc))


def walk_entries(node: Any, where: str, result: CheckResult, rel: str,
                 local: bool = False) -> None:
    """递归扫描内容条目：校验 id、收集双语文案。

    `local=True` 表示这一段里的 id 只是**条目内部**的编号（专长的 choices），
    不参与全局唯一性与格式校验 —— 否则 `id: boost` 会被当成内容 id 报错。
    """
    if isinstance(node, list):
        for index, item in enumerate(node):
            walk_entries(item, "%s[%d]" % (where, index), result, rel, local)
        return
    if not isinstance(node, Mapping):
        return

    if "id" in node and not local:
        ident = str(node["id"])
        if not is_valid(ident):
            result.issues.append("%s: id 不合规范 %r" % (rel, ident))
        elif ident in result.ids:
            result.issues.append("%s: id 重复 %r（另见 %s）" % (rel, ident, result.ids[ident]))
        else:
            result.ids[ident] = rel

    for key in ("name", "text"):
        if key in node:
            try:
                text = Text.from_dict(node[key], where="%s.%s" % (rel, key))
                result.texts.append((text, "%s.%s" % (rel, key)))
            except TextError as exc:
                result.issues.append(str(exc))

    for key, value in node.items():
        if isinstance(value, (Mapping, list)):
            walk_entries(value, "%s.%s" % (where, key), result, rel,
                         local or key == "choices")


def check_root(root: str | Path, with_terms: bool = False) -> CheckResult:
    result = CheckResult()
    base = Path(root)
    glossary = Glossary()

    for folder in iter_plugin_dirs(base):
        manifest_path = folder / "plugin.yaml"
        try:
            manifest = load_manifest(manifest_path)
            result.manifests.append(manifest)
        except PluginError as exc:
            result.issues.append(str(exc))
            continue

        for path in sorted(folder.rglob("*.yaml")):
            if path.name == "plugin.yaml":
                continue
            rel = str(path.relative_to(base))
            if path.name == "glossary.yaml":
                try:
                    glossary = Glossary.from_mapping(load_yaml(path) or {})
                except PluginError as exc:
                    result.issues.append(str(exc))
                continue
            try:
                walk_entries(load_yaml(path), "", result, rel)
            except PluginError as exc:
                result.issues.append(str(exc))

    if with_terms:
        result.issues.extend(glossary.lint_many(result.texts))
    return result


def cmd_check(args) -> int:
    result = check_root(args.root, with_terms=args.terms)
    print("=== 插件校验 (%s) ===" % args.root)
    for manifest in result.manifests:
        print("  %-18s %-8s api %s  %s / %s"
              % (manifest.id, manifest.kind, manifest.api, manifest.name.zh, manifest.name.en))
    print("条目 id      : %d" % len(result.ids))
    print("双语文案     : %d" % len(result.texts))
    for issue in result.issues:
        print("[FAIL] %s" % issue)
    print("PLUGINS %s（%d 个问题）" % ("OK" if result.ok else "FAILED", len(result.issues)))
    return 0 if result.ok else 1


def cmd_list(args) -> int:
    result = check_root(args.root)
    for manifest in result.manifests:
        provides = ", ".join("%s %d" % (k, len(v)) for k, v in manifest.provides.items()) or "-"
        print("%-18s %-8s %-8s %s" % (manifest.id, manifest.kind, manifest.version, provides))
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plugins_cli", description="插件与内容校验")
    parser.add_argument("--root", default="plugins")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="校验清单、id、双语、术语")
    check.add_argument("--root", default="plugins")
    check.add_argument("--terms", action="store_true", help="同时检查术语一致性")
    check.set_defaults(func=cmd_check)

    listing = sub.add_parser("list", help="列出插件")
    listing.add_argument("--root", default="plugins")
    listing.set_defaults(func=cmd_list)

    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
