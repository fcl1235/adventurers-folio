# -*- coding: utf-8 -*-
"""插件协议：清单解析与校验。插件是内容与变体的唯一入口。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import yaml

from .kernel.errors import PluginError, TextError
from .kernel.ids import is_plugin_id
from .kernel.text import Text

API_VERSION = 1
PLUGIN_KINDS = ("content", "ruleset", "adapter")


@dataclass(frozen=True, slots=True)
class Manifest:
    id: str
    kind: str
    api: int
    name: Text
    version: str = "0.1.0"
    requires: tuple[str, ...] = ()
    # 本插件要**整条替换**哪些内容 id（overlay 的显式声明，§13.4）。
    # 没声明而在别的插件里撞了 id：报错，不搞「后加载的赢」。
    replaces: tuple[str, ...] = ()
    provides: Mapping[str, Sequence[str]] = field(default_factory=dict)
    path: str = ""

    @property
    def root(self) -> Path:
        return Path(self.path).parent

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "api": self.api,
            "name": self.name.to_dict(),
            "version": self.version,
            "requires": list(self.requires),
            "provides": {key: list(value) for key, value in self.provides.items()},
        }


def parse_manifest(data: Any, where: str = "plugin.yaml") -> Manifest:
    if not isinstance(data, Mapping):
        raise PluginError("%s 必须是映射" % where)
    missing = [key for key in ("id", "kind", "api", "name") if key not in data]
    if missing:
        raise PluginError("%s 缺少字段：%s" % (where, ", ".join(missing)))

    plugin_id = str(data["id"])
    if not is_plugin_id(plugin_id):
        raise PluginError("%s 的 id 不合规范：%r（允许小写字母、数字、下划线、连字符）" % (where, plugin_id))

    kind = str(data["kind"])
    if kind not in PLUGIN_KINDS:
        raise PluginError("%s 的 kind 必须是 %s，实际 %r" % (where, "/".join(PLUGIN_KINDS), kind))

    try:
        api = int(data["api"])
    except (TypeError, ValueError):
        raise PluginError("%s 的 api 必须是整数：%r" % (where, data["api"]))
    if api != API_VERSION:
        raise PluginError("%s 需要 api %d，本程序只支持 %d" % (where, api, API_VERSION))

    try:
        name = Text.from_dict(data["name"], where="%s name" % where)
    except TextError as exc:
        raise PluginError(str(exc))

    requires = data.get("requires") or ()
    if isinstance(requires, str):
        requires = (requires,)
    provides = data.get("provides") or {}
    if not isinstance(provides, Mapping):
        raise PluginError("%s 的 provides 必须是映射" % where)

    return Manifest(
        id=plugin_id,
        kind=kind,
        api=api,
        name=name,
        version=str(data.get("version", "0.1.0")),
        requires=tuple(str(item) for item in requires),
        replaces=tuple(str(item) for item in (data.get("replaces") or ())),
        provides=MappingProxyType({str(k): tuple(str(x) for x in v) for k, v in provides.items()}),
        path=str(where),
    )


def load_manifest(path: str | Path) -> Manifest:
    file_path = Path(path)
    if not file_path.exists():
        raise PluginError("找不到插件清单：%s" % file_path)
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PluginError("%s 不是合法 YAML：%s" % (file_path, exc))
    return parse_manifest(raw, where=str(file_path))


def _version_tuple(text: str) -> tuple[int, ...]:
    """`1.2.3` → (1, 2, 3)。数字段之外的内容按 0 计（`1.0a` ≈ 1.0）。"""
    parts = []
    for chunk in str(text).split("."):
        digits = ""
        for ch in chunk.strip():
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def check_requires(manifest: Manifest, available: Mapping[str, str]) -> list[str]:
    """检查依赖：名字要在、版本要够（`pkg >= 1.2` 按数字段逐段比）。

    版本只有两位数字时补零比较（1.2 == 1.2.0），不做 semver 全集 ——
    插件版本本来就只有我们自己发。
    """
    problems = []
    for item in manifest.requires:
        if ">=" in item:
            name, _, wanted = item.partition(">=")
            name, wanted = name.strip(), wanted.strip()
            have = available.get(name)
            if have is None:
                problems.append("缺少依赖插件 %s" % name)
            elif _version_tuple(have) < _version_tuple(wanted):
                problems.append("依赖 %s 需要 >= %s，实际 %s" % (name, wanted, have))
        else:
            name = item.strip()
            if name and name not in available:
                problems.append("缺少依赖插件 %s" % name)
    return problems
