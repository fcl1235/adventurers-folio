# -*- coding: utf-8 -*-
"""角色档案：多职业等级、熟练集合、专长与选择。

这里只存「玩家的选择」，不存任何派生数值（约束 C5）。
总等级是派生值，永远由 classes 求和得出，不单独存。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

from ..kernel.errors import RuleError
from ..kernel.ids import is_valid
from .levels import ClassLevel, TotalLevel, as_class_level

# 语言清单属于内容，不属于模型 —— 这里只保留 lazy 的自由字符串集合。


@dataclass(frozen=True, slots=True)
class ClassEntry:
    class_id: str
    class_level: ClassLevel

    def __post_init__(self) -> None:
        if not is_valid(self.class_id):
            raise RuleError("职业 id 不合规范：%r" % (self.class_id,))
        as_class_level(int(self.class_level))

    @classmethod
    def make(cls, class_id: str, class_level: int) -> "ClassEntry":
        return cls(class_id=class_id, class_level=as_class_level(class_level))

    def to_dict(self) -> dict:
        return {"id": self.class_id, "class_level": int(self.class_level)}


@dataclass(frozen=True, slots=True)
class Profile:
    classes: tuple[ClassEntry, ...]
    # 子职是**内容 id**（"dnd2024.subclass.<class>.<subclass>"），不是显示名。
    # 兼职可以有两个子职，所以这里是元组 —— 每个职业各挂各的那一个。
    subclasses: tuple[str, ...] = ()
    proficiencies: frozenset[str] = frozenset()
    expertise: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset()
    feats: tuple[str, ...] = ()
    choices: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    # 伤害抗性（传奇恩惠「能量抗性」这类）。这里存**伤害类型**（fire / cold），
    # 不存内容 id —— 它是规则词汇，不是某本书里的条目。
    resistances: frozenset[str] = frozenset()
    # 已知戏法与准备法术：**按职业分开**（兼职时两个职业各有各的配额）。
    # 值是法术内容 id；数量与环级上限由 `rules/spellcasting.check_spell_picks` 校验，
    # 因为配额来自 ClassDef 的表，模型层看不到内容。
    cantrips: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    prepared: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.classes:
            raise RuleError("角色至少要有一个职业等级")
        seen = set()
        for entry in self.classes:
            if entry.class_id in seen:
                raise RuleError("职业重复：%s" % entry.class_id)
            seen.add(entry.class_id)
        for subclass_id in self.subclasses:
            if not is_valid(subclass_id):
                raise RuleError("子职 id 不合规范：%r" % (subclass_id,))
        if len(set(self.subclasses)) != len(self.subclasses):
            raise RuleError("子职重复：%s" % ", ".join(self.subclasses))
        # 熟练与专精必须是熟练的子集
        unknown = set(self.expertise) - set(self.proficiencies)
        if unknown:
            raise RuleError("专精项不在熟练集合里：%s" % ", ".join(sorted(unknown)))

    # --- 构造 ---------------------------------------------------------
    @classmethod
    def single(cls, class_id: str, class_level: int) -> "Profile":
        return cls(classes=(ClassEntry.make(class_id, class_level),))

    def add_class(self, class_id: str, class_level: int) -> "Profile":
        return replace(self, classes=self.classes + (ClassEntry.make(class_id, class_level),))

    # --- 等级 ---------------------------------------------------------
    @property
    def total(self) -> TotalLevel:
        return TotalLevel(sum(int(entry.class_level) for entry in self.classes))

    def class_level(self, class_id: str) -> ClassLevel:
        """没有这个职业时返回 0 —— 兼职角色问「某职业几级」是常态。"""
        for entry in self.classes:
            if entry.class_id == class_id:
                return entry.class_level
        return ClassLevel(0)

    def has_class(self, class_id: str) -> bool:
        return int(self.class_level(class_id)) > 0

    @property
    def class_ids(self) -> tuple[str, ...]:
        return tuple(entry.class_id for entry in self.classes)

    @property
    def is_multiclass(self) -> bool:
        return len(self.classes) > 1

    # --- 集合型贡献 ---------------------------------------------------
    def with_subclass(self, subclass_id: str) -> "Profile":
        """挂上子职（幂等）。「同一职业只能有一个子职」由内容层校验。"""
        if subclass_id in self.subclasses:
            return self
        return replace(self, subclasses=self.subclasses + (subclass_id,))

    def without_subclass(self, subclass_id: str | None = None) -> "Profile":
        """摘掉一个子职；不给 id 就全摘（改职业时用）。"""
        keep = () if subclass_id is None else tuple(
            item for item in self.subclasses if item != subclass_id
        )
        if keep == self.subclasses:
            return self
        return replace(self, subclasses=keep)

    def has_subclass(self, subclass_id: str) -> bool:
        return subclass_id in self.subclasses

    def with_proficiencies(self, add: Iterable[str] = (), remove: Iterable[str] = ()) -> "Profile":
        new = (set(self.proficiencies) | set(add)) - set(remove)
        return replace(
            self,
            proficiencies=frozenset(new),
            expertise=frozenset(set(self.expertise) - set(remove)),
        )

    def with_feats(self, feats: Iterable[str]) -> "Profile":
        return replace(self, feats=tuple(feats))

    def with_choices(self, choices: Mapping[str, tuple[str, ...]]) -> "Profile":
        return replace(self, choices=dict(choices))

    def with_resistances(self, add: Iterable[str] = ()) -> "Profile":
        return replace(self, resistances=self.resistances | frozenset(add))

    # --- 法术选择 -----------------------------------------------------
    def with_cantrips(self, class_id: str, spells: Iterable[str]) -> "Profile":
        """设定某个职业的已知戏法。空列表 = 清掉这一职业的记录。"""
        return replace(self, cantrips=_with_map(self.cantrips, class_id, spells))

    def with_prepared(self, class_id: str, spells: Iterable[str]) -> "Profile":
        return replace(self, prepared=_with_map(self.prepared, class_id, spells))

    def spells_of(self, class_id: str) -> tuple[str, ...]:
        return tuple(self.prepared.get(class_id, ()))

    def cantrips_of(self, class_id: str) -> tuple[str, ...]:
        return tuple(self.cantrips.get(class_id, ()))

    def to_dict(self) -> dict:
        """只写事实，总等级不写（C5）。"""
        return {
            "classes": [entry.to_dict() for entry in self.classes],
            "subclasses": list(self.subclasses),
            "proficiencies": sorted(self.proficiencies),
            "expertise": sorted(self.expertise),
            "languages": sorted(self.languages),
            "feats": list(self.feats),
            "choices": {key: list(value) for key, value in self.choices.items()},
            "resistances": sorted(self.resistances),
            "cantrips": {key: list(value) for key, value in self.cantrips.items()},
            "prepared": {key: list(value) for key, value in self.prepared.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "Profile":
        entries = tuple(
            ClassEntry.make(str(item["id"]), int(item["class_level"]))
            for item in data.get("classes", ())
        )
        raw = data.get("subclasses")
        if raw is None:                       # 旧档写的是单个 subclass
            single = data.get("subclass")
            raw = [single] if single else []
        return cls(
            classes=entries,
            subclasses=tuple(str(item) for item in raw),
            proficiencies=frozenset(data.get("proficiencies", ())),
            expertise=frozenset(data.get("expertise", ())),
            languages=frozenset(data.get("languages", ())),
            feats=tuple(data.get("feats", ())),
            choices={key: tuple(value) for key, value in (data.get("choices") or {}).items()},
            resistances=frozenset(data.get("resistances", ())),
            cantrips={key: tuple(value) for key, value in (data.get("cantrips") or {}).items()},
            prepared={key: tuple(value) for key, value in (data.get("prepared") or {}).items()},
        )


def _with_map(source: Mapping[str, tuple[str, ...]], class_id: str,
              spells: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """按职业改写一张 法术表。**去重并保序**：顺序就是界面上的顺序。"""
    updated = dict(source)
    items = tuple(dict.fromkeys(str(item) for item in spells))
    if items:
        updated[class_id] = items
    else:
        updated.pop(class_id, None)
    return updated


def class_levels_of(profile: Profile) -> Mapping[str, ClassLevel]:
    return {entry.class_id: entry.class_level for entry in profile.classes}
