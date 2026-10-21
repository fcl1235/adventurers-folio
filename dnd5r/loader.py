# -*- coding: utf-8 -*-
"""插件发现：目录扫描 + entry points。

单个插件坏了只禁用自己，不拖垮启动 —— 所以 errors 与 manifests 一起返回。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .kernel.errors import PluginError
from .plugin import Manifest, check_requires, load_manifest


@dataclass
class Discovery:
    manifests: list[Manifest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.manifests)


def iter_plugin_dirs(root: str | Path) -> Iterable[Path]:
    base = Path(root)
    if not base.exists():
        return
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "plugin.yaml").exists():
            yield child


def discover(root: str | Path) -> Discovery:
    result = Discovery()
    for folder in iter_plugin_dirs(root):
        try:
            result.manifests.append(load_manifest(folder / "plugin.yaml"))
        except PluginError as exc:
            result.errors.append(str(exc))

    available = {item.id: item.version for item in result.manifests}
    kept = []
    for item in result.manifests:
        problems = check_requires(item, available)
        if problems:
            result.errors.extend("%s: %s" % (item.id, text) for text in problems)
        else:
            kept.append(item)
    result.manifests = kept
    return result


def discover_entry_points(group: str = "dnd5r.plugins") -> Discovery:
    """第三方 pip 安装的插件。没有装任何插件时静默返回空。"""
    result = Discovery()
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return result

    for entry in entry_points(group=group):
        try:
            factory = entry.load()
            manifest = factory() if callable(factory) else factory
            if not isinstance(manifest, Manifest):
                raise PluginError("entry point %s 没有返回 Manifest" % entry.name)
            result.manifests.append(manifest)
        except Exception as exc:  # 第三方代码不可信，坏掉只报告
            result.errors.append("entry point %s: %s" % (entry.name, exc))
    return result
