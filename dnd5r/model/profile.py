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
from .statblock import ABILITY_KEYS, SCORE_MAX, SCORE_MIN

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
    # **建角色时输入的原始属性**（属性加值之前）。没有它，档案就还原不出角色：
    # 显示值里混着专长/子职给的加值，倒推回去是减不掉的（有上限通道）。
    # 存档、读档、以及界面里改一个专长都要靠它重建。
    base_scores: Mapping[str, int] = field(default_factory=dict)
    # 物种与背景都是**内容 id**（"dnd2024.species.dwarf"）。空串 = 没选
    # （怪物、旧档、只关心战斗的临时角色都能是空的）。
    species: str = ""
    background: str = ""
    # 背景加值的**分配结果**（属性 → +2/+1）。形态合法性（+2 与 +1，或三项各 +1）
    # 由 `rules/abilities.background_bonus()` 判 —— 模型层只存事实，不判规则细节。
    # 单独存而不是塞进 `choices`：它没有「选择项 id」，塞进去必然要拆字符串。
    background_bonus: Mapping[str, int] = field(default_factory=dict)
    # **武器精通**（2024 规则）：存武器的**内容 id**（"dnd2024.item.weapon.longsword"），
    # 与专长、子职同一个口径。精通效果本身**不结算** —— 它依赖命中后的战术选择，
    # 没有目标模型就算不出来。这里只记录玩家选了哪几件，界面标注「已记录，未结算」。
    masteries: frozenset[str] = frozenset()

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
        # 物种 / 背景：要么没选，要么是合规内容 id
        for label, value in (("物种", self.species), ("背景", self.background)):
            if value and not is_valid(value):
                raise RuleError("%s id 不合规范：%r" % (label, value))
        bad = [key for key in self.background_bonus if key not in ABILITY_KEYS]
        if bad:
            raise RuleError("背景加值只能加在 %s 上：%r"
                            % ("/".join(ABILITY_KEYS), bad))
        if not isinstance(self.masteries, frozenset):
            object.__setattr__(self, "masteries", frozenset(str(item)
                                                             for item in self.masteries))
        # 原始属性：要么整块不给（旧档、怪物），要么六项齐全。给一半视为数据错误 ——
        # 「少写了 con」会被当成 0 去算 HP，错得悄无声息。
        if self.base_scores:
            missing = [key for key in ABILITY_KEYS if key not in self.base_scores]
            if missing:
                raise RuleError("原始属性缺项：%s" % ", ".join(missing))
            for key in ABILITY_KEYS:
                value = self.base_scores[key]
                if not isinstance(value, int) or isinstance(value, bool):
                    raise RuleError("原始属性 %s 必须是整数：%r" % (key.upper(), value))
                if not (SCORE_MIN <= value <= SCORE_MAX):
                    raise RuleError("原始属性 %s 超出 %d..%d：%r"
                                    % (key.upper(), SCORE_MIN, SCORE_MAX, value))

    # --- 构造 ---------------------------------------------------------
    @classmethod
    def single(cls, class_id: str, class_level: int) -> "Profile":
        return cls(classes=(ClassEntry.make(class_id, class_level),))

    def add_class(self, class_id: str, class_level: int) -> "Profile":
        return replace(self, classes=self.classes + (ClassEntry.make(class_id, class_level),))

    def with_class_level(self, class_id: str, class_level: int) -> "Profile":
        """改某个职业的等级（升级 / 降级只用这一处）。

        **不在这一层拦总等级上限**：`MAX_TOTAL_LEVEL` 是 build 时的事，
        在这里再判一次只会出现两套口径。但「没有这个职业」要当场报错 ——
        悄悄追加一个新职业条目是最难查的那种静默。
        """
        if not self.has_class(class_id):
            raise RuleError("档案里没有这个职业：%s" % class_id)
        updated = tuple(
            ClassEntry.make(entry.class_id, int(class_level))
            if entry.class_id == class_id else entry
            for entry in self.classes
        )
        return replace(self, classes=updated)

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

    # --- 原始属性 -----------------------------------------------------
    def with_base_scores(self, scores: Mapping[str, int]) -> "Profile":
        """记录建角色时输入的属性（**加值之前**）。界面改属性、存档、重建都靠它。"""
        return replace(self, base_scores={key: int(scores[key]) for key in ABILITY_KEYS})

    def base_score(self, key: str) -> int:
        """没有记录原始属性时抛错 —— 悄悄返回 0 会让重建出一个废角色。"""
        if not self.base_scores:
            raise RuleError("档案没有记录原始属性，无法重建角色（旧档需重新建角色）")
        return int(self.base_scores[key])

    # --- 物种 / 背景 / 精通 -------------------------------------------
    def with_origin(self, species: str = "", background: str = "",
                    bonus: Mapping[str, int] | None = None) -> "Profile":
        """设定物种、背景与背景加值的分配（各自传空表示清掉）。建卡第一屏之后就该定下来。"""
        return replace(
            self,
            species=str(species),
            background=str(background),
            background_bonus={str(key): int(value) for key, value in (bonus or {}).items()},
        )

    def with_masteries(self, weapons: Iterable[str]) -> "Profile":
        """记录武器精通（武器的内容 id）。集合语义，重复给同一件只算一次。"""
        return replace(self, masteries=frozenset(str(item) for item in weapons))

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
            # 原始属性必须进档：没有它，读回来的角色只剩一堆派生值，改不了也重建不了
            "base_scores": {key: self.base_scores[key] for key in ABILITY_KEYS
                            if key in self.base_scores},
            "species": self.species,
            "background": self.background,
            "background_bonus": {key: int(value)
                                 for key, value in self.background_bonus.items()},
            "masteries": sorted(self.masteries),
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
            base_scores={str(key): int(value)
                         for key, value in (data.get("base_scores") or {}).items()},
            # v1/v2 旧档没有这四项 —— 取默认，不报错（出身是 2024 的可选项）
            species=str(data.get("species") or ""),
            background=str(data.get("background") or ""),
            background_bonus={str(key): int(value)
                              for key, value in (data.get("background_bonus") or {}).items()},
            masteries=frozenset(str(item) for item in (data.get("masteries") or ())),
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
