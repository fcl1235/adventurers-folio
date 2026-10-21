# -*- coding: utf-8 -*-
"""角色档案：多职业等级、熟练集合、专长与选择。

这里只存「玩家的选择」，不存任何派生数值（约束 C5）。
总等级是派生值，永远由 classes 求和得出，不单独存。
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    proficiencies: frozenset[str] = frozenset()
    expertise: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset()
    feats: tuple[str, ...] = ()
    choices: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.classes:
            raise RuleError("角色至少要有一个职业等级")
        seen = set()
        for entry in self.classes:
            if entry.class_id in seen:
                raise RuleError("职业重复：%s" % entry.class_id)
            seen.add(entry.class_id)
        # 熟练与专精必须是熟练的子集
        unknown = set(self.expertise) - set(self.proficiencies)
        if unknown:
            raise RuleError("专精项不在熟练集合里：%s" % ", ".join(sorted(unknown)))

    # --- 构造 ---------------------------------------------------------
    @classmethod
    def single(cls, class_id: str, class_level: int) -> "Profile":
        return cls(classes=(ClassEntry.make(class_id, class_level),))

    def add_class(self, class_id: str, class_level: int) -> "Profile":
        return Profile(
            classes=self.classes + (ClassEntry.make(class_id, class_level),),
            proficiencies=self.proficiencies,
            expertise=self.expertise,
            languages=self.languages,
            feats=self.feats,
            choices=self.choices,
        )

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
    def with_proficiencies(self, add: Iterable[str] = (), remove: Iterable[str] = ()) -> "Profile":
        new = (set(self.proficiencies) | set(add)) - set(remove)
        return Profile(
            classes=self.classes,
            proficiencies=frozenset(new),
            expertise=frozenset(set(self.expertise) - set(remove)),
            languages=self.languages,
            feats=self.feats,
            choices=self.choices,
        )

    def to_dict(self) -> dict:
        """只写事实，总等级不写（C5）。"""
        return {
            "classes": [entry.to_dict() for entry in self.classes],
            "proficiencies": sorted(self.proficiencies),
            "expertise": sorted(self.expertise),
            "languages": sorted(self.languages),
            "feats": list(self.feats),
            "choices": {key: list(value) for key, value in self.choices.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "Profile":
        entries = tuple(
            ClassEntry.make(str(item["id"]), int(item["class_level"]))
            for item in data.get("classes", ())
        )
        return cls(
            classes=entries,
            proficiencies=frozenset(data.get("proficiencies", ())),
            expertise=frozenset(data.get("expertise", ())),
            languages=frozenset(data.get("languages", ())),
            feats=tuple(data.get("feats", ())),
            choices={key: tuple(value) for key, value in (data.get("choices") or {}).items()},
        )


def class_levels_of(profile: Profile) -> Mapping[str, ClassLevel]:
    return {entry.class_id: entry.class_level for entry in profile.classes}
