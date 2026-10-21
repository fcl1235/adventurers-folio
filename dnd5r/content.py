# -*- coding: utf-8 -*-
"""内容加载：把插件里的 YAML 变成 ClassDef / Power / ResourceDef。

三条原则：
  1. **内容不进代码**：这里是唯一读 YAML 的地方，规则层只吃解析好的对象。
  2. **坏内容只坏自己**：单个文件解析失败记进 errors，其余内容照常可用。
  3. **解析期就校验**：双语（C7）、id 规范、引用存在、效果可解析，
     全部在加载时炸掉，而不是等到玩家点了按钮才崩。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from .kernel.errors import DndError, PluginError, RuleError
from .kernel.ids import is_valid
from .kernel.text import Text
from .plugin import Manifest, load_manifest
from .rules.amount import Amount, parse_amount
from .rules.effects import parse_effects
from .rules.powers import Power, PowerBook, parse_power
from .rules.progression import CasterKind, attacks_per_action
from .model.levels import ClassLevel, as_class_level
from .model.resources import Pool, PoolKind, Refresh

RESOURCE_KINDS = {item.value: item for item in PoolKind}
REFRESH_KINDS = {item.value: item for item in Refresh}


# --- 资源 -------------------------------------------------------------
@dataclass(frozen=True)
class ResourceDef:
    """一个资源池的定义。次数表放数据里，代码只负责查表。"""

    id: str
    kind: PoolKind
    refresh: Refresh = Refresh.LONG_REST
    capacity: Amount | None = None
    by_level: Mapping[int, int] | None = None
    recover_on_short_rest: int = 0
    label: Text | None = None
    owner_class: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("资源 id 不合规范：%r" % (self.id,))
        if self.capacity is None and not self.by_level:
            raise PluginError("资源 %s 必须给 capacity 或 by_level" % self.id)
        if self.by_level:
            for key, value in self.by_level.items():
                if int(key) < 1 or int(value) < 0:
                    raise PluginError("资源 %s 的等级表不合法：%r=%r" % (self.id, key, value))

    def capacity_at(self, level: ClassLevel, ref_map: Mapping[str, Any] | None = None) -> int:
        """按「本职业等级」查表。兼职时次数按职业等级，不按总等级（G15）。"""
        if self.by_level:
            usable = [int(key) for key in self.by_level if int(key) <= int(level)]
            if not usable:
                return 0
            return int(self.by_level[max(usable)])
        assert self.capacity is not None
        if ref_map is None:
            if self.capacity.times is not None or self.capacity.plus is not None:
                raise PluginError(
                    "资源 %s 的容量依赖等级引用，必须提供 ref_map" % self.id
                )
            return self.capacity.flat
        return self.capacity.evaluate(ref_map)

    def build(self, level: ClassLevel, ref_map: Mapping[str, Any] | None = None) -> Pool:
        return Pool(
            id=self.id,
            kind=self.kind,
            capacity=self.capacity_at(level, ref_map),
            label=self.label,
            owner_class=self.owner_class or None,
            refresh=self.refresh,
            recover_on_short_rest=self.recover_on_short_rest,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind.value, "refresh": self.refresh.value,
            "by_level": dict(self.by_level or {}),
            "recover_on_short_rest": self.recover_on_short_rest,
        }


def parse_resource(data: Any, owner_class: str = "") -> ResourceDef:
    if not isinstance(data, Mapping):
        raise PluginError("资源条目必须是映射：%r" % (data,))
    ident = data.get("id")
    if not ident:
        raise PluginError("资源缺少 id")
    kind_key = str(data.get("kind", "charge")).lower()
    if kind_key not in RESOURCE_KINDS:
        raise PluginError("%s 的资源类型必须是 %s" % (ident, "/".join(sorted(RESOURCE_KINDS))))
    refresh_key = str(data.get("refresh", "long_rest")).lower()
    if refresh_key not in REFRESH_KINDS:
        raise PluginError("%s 的恢复方式必须是 %s" % (ident, "/".join(sorted(REFRESH_KINDS))))

    by_level = None
    if data.get("by_level"):
        try:
            by_level = {int(key): int(value) for key, value in data["by_level"].items()}
        except (TypeError, ValueError):
            raise PluginError("%s 的 by_level 必须是 等级→次数 的映射" % ident)

    capacity = None
    if data.get("capacity") is not None:
        capacity = parse_amount(data["capacity"], where="%s capacity" % ident)

    label = None
    if data.get("label") is not None:
        label = Text.from_dict(data["label"], where="%s label" % ident)

    return ResourceDef(
        id=str(ident),
        kind=RESOURCE_KINDS[kind_key],
        refresh=REFRESH_KINDS[refresh_key],
        capacity=capacity,
        by_level=by_level,
        recover_on_short_rest=int(data.get("recover_on_short_rest", 0)),
        label=label,
        owner_class=str(data.get("owner", owner_class)),
    )


# --- 职业 -------------------------------------------------------------
@dataclass(frozen=True)
class ClassDef:
    id: str
    name: Text
    hit_die: int
    primary: tuple[str, ...] = ()
    saves: tuple[str, ...] = ()
    caster: CasterKind = CasterKind.NONE
    subclass_level: ClassLevel = ClassLevel(3)
    skill_choices: int = 2
    skill_list: tuple[str, ...] = ()
    resources: tuple[ResourceDef, ...] = ()
    powers: tuple[Power, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("职业 id 不合规范：%r" % (self.id,))
        if self.hit_die < 2:
            raise PluginError("%s 的生命骰面不合法：%r" % (self.id, self.hit_die))
        for key in self.saves:
            if key not in ("str", "dex", "con", "int", "wis", "cha"):
                raise PluginError("%s 的豁免熟练含未知属性：%r" % (self.id, key))
        seen = set()
        for resource in self.resources:
            if resource.id in seen:
                raise PluginError("%s 的资源 id 重复：%s" % (self.id, resource.id))
            seen.add(resource.id)

    def resource(self, resource_id: str) -> ResourceDef:
        for item in self.resources:
            if item.id == resource_id:
                return item
        raise PluginError("%s 没有资源 %s" % (self.id, resource_id))

    def powers_at(self, class_level: ClassLevel) -> tuple[Power, ...]:
        picked = [power for power in self.powers if int(power.level) <= int(class_level)]
        return tuple(sorted(picked, key=lambda item: (int(item.level), item.id)))

    def total_attacks(self, class_level: ClassLevel) -> int:
        """额外攻击取最大不叠加（Extra Attack 的 Stack.MAX 语义）。

        数据里写成 `grant_modifier: {target: attack.count, value: 2, stack: max}`，
        所以「5 级战士兼 5 级圣武士变成四打」这种错误结构上不可能发生。
        """
        pairs = []
        for power in self.powers_at(class_level):
            for effect in power.effects:
                for mod in getattr(effect, "modifiers", ()):
                    if mod.target == "attack.count" and isinstance(mod.value, int):
                        pairs.append((power.id, mod.value))
        return attacks_per_action(pairs)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name.to_dict(), "hit_die": self.hit_die,
            "primary": list(self.primary), "saves": list(self.saves),
            "caster": self.caster.value, "subclass_level": int(self.subclass_level),
            "resources": [item.to_dict() for item in self.resources],
            "powers": len(self.powers),
        }


def parse_class(data: Any, source: str = "") -> ClassDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的职业定义必须是映射" % source)
    for key in ("id", "name", "hit_die"):
        if key not in data:
            raise PluginError("%s 的职业定义缺少 %s" % (source, key))

    ident = str(data["id"])
    caster_key = str(data.get("caster", "none")).lower()
    try:
        caster = CasterKind(caster_key)
    except ValueError:
        raise PluginError("%s 的 caster 必须是 %s"
                          % (ident, "/".join(item.value for item in CasterKind)))
    try:
        subclass_level = as_class_level(int(data.get("subclass_level", 3)))
    except RuleError as exc:
        raise PluginError("%s 的子职等级不合法：%s" % (ident, exc))

    resources = tuple(
        parse_resource(item, owner_class=ident) for item in (data.get("resources") or ())
    )
    powers = tuple(
        parse_power(item, owner=ident, source=source) for item in (data.get("powers") or ())
    )

    return ClassDef(
        id=ident,
        name=Text.from_dict(data["name"], where="%s name" % ident),
        hit_die=int(data["hit_die"]),
        primary=tuple(str(item).lower() for item in (data.get("primary") or ())),
        saves=tuple(str(item).lower() for item in (data.get("saves") or ())),
        caster=caster,
        subclass_level=subclass_level,
        skill_choices=int(data.get("skill_choices", 2)),
        skill_list=tuple(str(item) for item in (data.get("skill_list") or ())),
        resources=resources,
        powers=powers,
        source=source,
    )


# --- 插件与汇总 -------------------------------------------------------
@dataclass
class PluginContent:
    manifest: Manifest | None = None
    classes: dict[str, ClassDef] = field(default_factory=dict)
    book: PowerBook = field(default_factory=PowerBook)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ContentBundle:
    classes: dict[str, ClassDef] = field(default_factory=dict)
    book: PowerBook = field(default_factory=PowerBook)
    manifests: list[Manifest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def class_def(self, class_id: str) -> ClassDef:
        if class_id not in self.classes:
            raise PluginError("没有这个职业：%s（已加载：%s）"
                              % (class_id, ", ".join(sorted(self.classes)) or "无"))
        return self.classes[class_id]

    def stats(self) -> dict[str, Any]:
        return {
            "classes": len(self.classes),
            "powers": len(self.book.ids()),
            "by_kind": self.book.stats(),
            "errors": len(self.errors),
        }


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PluginError("%s 不是合法 YAML：%s" % (path, exc))


def load_plugin(folder: str | Path) -> PluginContent:
    base = Path(folder)
    result = PluginContent()
    try:
        result.manifest = load_manifest(base / "plugin.yaml")
    except PluginError as exc:
        result.errors.append(str(exc))
        return result

    for path in sorted((base / "classes").glob("*.yaml")) if (base / "classes").exists() else []:
        rel = "%s/classes/%s" % (base.name, path.name)
        try:
            class_def = parse_class(_read_yaml(path), source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if class_def.id in result.classes:
            result.errors.append("%s 的职业 id 重复：%s" % (rel, class_def.id))
            continue
        result.classes[class_def.id] = class_def
        for power in class_def.powers:
            try:
                result.book.add(power)
            except PluginError as exc:
                result.errors.append(str(exc))

    result.book = result.book.apply_augments()
    return result


def load_all(root: str | Path = "plugins") -> ContentBundle:
    """加载目录下所有插件。冲突报错但不清空已加载内容。"""
    bundle = ContentBundle()
    base = Path(root)
    if not base.exists():
        return bundle

    for folder in sorted(base.iterdir()):
        if not folder.is_dir() or not (folder / "plugin.yaml").exists():
            continue
        content = load_plugin(folder)
        bundle.errors.extend(content.errors)
        if content.manifest is None:
            continue
        bundle.manifests.append(content.manifest)
        for class_id, class_def in content.classes.items():
            if class_id in bundle.classes:
                bundle.errors.append(
                    "职业 %s 同时由 %s 与 %s 提供"
                    % (class_id, bundle.classes[class_id].source, class_def.source)
                )
                continue
            bundle.classes[class_id] = class_def
        for power in content.book.all():
            if bundle.book.has(power.id):
                bundle.errors.append("能力 %s 重复提供" % power.id)
                continue
            bundle.book.add(power)
    bundle.book = bundle.book.apply_augments()
    return bundle


__all__ = [
    "ResourceDef", "ClassDef", "PluginContent", "ContentBundle",
    "parse_resource", "parse_class", "load_plugin", "load_all",
]
