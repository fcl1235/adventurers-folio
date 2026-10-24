# -*- coding: utf-8 -*-
"""插件发现：目录扫描。

单个插件坏了只禁用自己，不拖垮启动 —— 所以 errors 与 manifests 一起返回。
（2026-10 / P14：entry_points 发现已删 —— 零调用方，协议无真实用例不编造；
将来有 pip 发行的真插件时再按那时的需求定协议。）
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
