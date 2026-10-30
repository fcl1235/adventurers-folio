# -*- coding: utf-8 -*-
"""职业与子职定义：等级表、特性、资源、施法属性。拆自 P11 之前的 content.py。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..kernel.errors import PluginError, RuleError
from ..kernel.ids import is_valid
from ..kernel.text import Text
from ..model.levels import ClassLevel, as_class_level
from ..model.resources import Refresh
from ..model.statblock import ABILITY_KEYS
from ..rules.morph import CrAxis
from ..rules.powers import Power, apply_patch, parse_power
from ..rules.progression import CasterKind, attacks_per_action
from .bestiary import parse_cr_axis
from .resources import REFRESH_KINDS, ResourceDef, parse_resource

# --- 职业 -------------------------------------------------------------
def powers_at_level(powers: tuple[Power, ...], class_level: ClassLevel) -> tuple[Power, ...]:
    """当前等级解锁的能力，**并且把已解锁的 patch 应用进去**。

    叠层必须在这里做而不是加载时做：18 级的「野兽施法」要解除变形期间
    的施法禁令，如果在加载时全局套用，2 级德鲁伊也能施法了。

    职业与子职共用这一份实现：子职特性的等级也按**父职业等级**算，
    「3 级才拿子职」这条规则由等级门槛自然表达，不需要额外的开关。
    """
    picked = [power for power in powers if int(power.level) <= int(class_level)]
    picked.sort(key=lambda item: (int(item.level), item.id))
    index = {power.id: power for power in picked}
    for power in picked:
        if not power.augments:
            continue
        for target_id in power.augments:
            if target_id in index:      # 目标也解锁了才叠，跨职业的交由校验期报错
                index[target_id] = apply_patch(index[target_id], power)
    return tuple(index[power.id] for power in picked)


@dataclass(frozen=True)
class ClassDef:
    id: str
    name: Text
    hit_die: int
    primary: tuple[str, ...] = ()
    saves: tuple[str, ...] = ()
    caster: CasterKind = CasterKind.NONE
    # 施法属性（cha/wis/int）：。caster 只说是全/半/契约施法者，不说用哪个属性
    casting_ability: str = ""
    subclass_level: ClassLevel = ClassLevel(3)
    skill_choices: int = 2
    skill_list: tuple[str, ...] = ()
    resources: tuple[ResourceDef, ...] = ()
    powers: tuple[Power, ...] = ()
    # 武器/护甲熟练，统一写带前缀的 token：weapon.simple / armor.light
    proficiencies: tuple[str, ...] = ()
    morph: CrAxis | None = None
    # 法术位表：等级 → (1 环, 2 环, …, 9 环)。内核只查表，不写公式
    slots: Mapping[int, tuple[int, ...]] = field(default_factory=dict)
    cantrips: Mapping[int, int] = field(default_factory=dict)
    prepared: Mapping[int, int] = field(default_factory=dict)
    # 武器精通件数：等级 → 可精通的武器种类数。没有这个键 = 该职业没有武器精通
    # （2024 只有野蛮人/战士/圣武士/游侠/盗贼有）。0 与「没有」是两件事：
    # 空表 = 完全不给这项特性；写了表但某级缺 = 沿用最近的下界。
    mastery_counts: Mapping[int, int] = field(default_factory=dict)
    slot_refresh: Refresh = Refresh.LONG_REST   # 邪术师契约位是短休恢复
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("职业 id 不合规范：%r" % (self.id,))
        if self.hit_die < 2:
            raise PluginError("%s 的生命骰面不合法：%r" % (self.id, self.hit_die))
        for key in self.saves:
            if key not in ("str", "dex", "con", "int", "wis", "cha"):
                raise PluginError("%s 的豁免熟练含未知属性：%r" % (self.id, key))
        if self.casting_ability and self.casting_ability not in (
                "str", "dex", "con", "int", "wis", "cha"):
            raise PluginError("%s 的施法属性不合法：%r" % (self.id, self.casting_ability))
        if self.caster is not CasterKind.NONE and not self.casting_ability:
            raise PluginError("%s 是施法职业，必须声明 casting_ability" % self.id)
        if self.caster is CasterKind.NONE and self.casting_ability:
            raise PluginError("%s 不是施法职业，却声明了 casting_ability" % self.id)
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
        """当前等级解锁的能力（含叠层）。规则见 `powers_at_level()`。"""
        return powers_at_level(self.powers, class_level)

    def slots_at(self, class_level: ClassLevel) -> tuple[int, ...]:
        """这一级的 9 个环位容量。没有该级条目时按最近的下界（与资源表同规则）。"""
        if not self.slots:
            return (0,) * 9
        usable = [int(key) for key in self.slots if int(key) <= int(class_level)]
        if not usable:
            return (0,) * 9
        row = tuple(self.slots[max(usable)])
        return row + (0,) * (9 - len(row))

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

    def mastery_count_at(self, class_level: ClassLevel) -> int:
        """这一级可以精通几件武器。空表返回 0 —— 「没有武器精通」与「写了个 0」
        在界面上要做的事一样（不显示这一步），所以不必区分。"""
        if not self.mastery_counts:
            return 0
        usable = [int(key) for key in self.mastery_counts if int(key) <= int(class_level)]
        if not usable:
            return 0
        return max(0, int(self.mastery_counts[max(usable)]))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name.to_dict(), "hit_die": self.hit_die,
            "primary": list(self.primary), "saves": list(self.saves),
            "caster": self.caster.value, "casting_ability": self.casting_ability,
            "subclass_level": int(self.subclass_level),
            "resources": [item.to_dict() for item in self.resources],
            "powers": len(self.powers),
        }


# --- 子职 -------------------------------------------------------------
@dataclass(frozen=True)
class SubclassDef:
    """一个子职：挂在某个职业上的一组特性。

    子职**不是**职业的字段，而是独立内容：它自带 id、自带特性表，
    通过 `class_id` 挂回去。这样「一个职业有四个子职」不需要职业文件知道
    任何子职的事，第三方插件也能给已有职业补子职。
    """

    id: str
    class_id: str
    name: Text
    summary: Text
    unlock_level: ClassLevel = ClassLevel(3)
    powers: tuple[Power, ...] = ()
    # 子职自己的资源池。规则里「使用次数等于你的感知调整值（至少 1 次）」
    # 这类次数长在**子职特性**上，不属于职业 —— 借职业的资源表表达会让人
    # 一换子职就莫名其妙多出/少掉池，而且同一职业的四个子职会互相串味。
    resources: tuple[ResourceDef, ...] = ()
    source: str = ""

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("子职 id 不合规范：%r" % (self.id,))
        if not is_valid(self.class_id):
            raise PluginError("子职 %s 的 class_id 不合规范：%r" % (self.id, self.class_id))
        seen = set()
        for power in self.powers:
            if power.id in seen:
                raise PluginError("子职 %s 的特性 id 重复：%s" % (self.id, power.id))
            seen.add(power.id)
        for resource in self.resources:
            if resource.id in seen:
                raise PluginError("子职 %s 的资源 id 与特性重名：%s" % (self.id, resource.id))
            seen.add(resource.id)

    def powers_at(self, class_level: ClassLevel) -> tuple[Power, ...]:
        """按**父职业等级**解锁的特性（含叠层）。"""
        if int(class_level) < int(self.unlock_level):
            return ()
        return powers_at_level(self.powers, class_level)

    def resources_at(self, class_level: ClassLevel) -> tuple[ResourceDef, ...]:
        """按**父职业等级**解锁的资源池：3 级之前选了子职也不该有池。"""
        if int(class_level) < int(self.unlock_level):
            return ()
        return self.resources

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "class": self.class_id,
            "name": self.name.to_dict(),
            "summary": self.summary.to_dict(),
            "unlock_level": int(self.unlock_level),
            "powers": len(self.powers),
            "resources": [item.to_dict() for item in self.resources],
        }


def parse_subclass(data: Any, source: str = "", unlock_level: int = 3) -> SubclassDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的子职定义必须是映射" % source)
    for key in ("id", "class", "name", "powers"):
        if key not in data:
            raise PluginError("%s 的子职定义缺少 %s" % (source, key))

    ident = str(data["id"])
    powers = tuple(
        parse_power(row, owner=ident, source=source)
        for row in (data.get("powers") or ())
    )
    try:
        level = as_class_level(int(data.get("unlock_level", unlock_level)))
    except RuleError as exc:
        raise PluginError("%s 的子职解锁等级不合法：%s" % (ident, exc))
    resources = tuple(
        parse_resource(row, owner_class=ident)
        for row in (data.get("resources") or ())
    )
    return SubclassDef(
        id=ident,
        class_id=str(data["class"]),
        name=Text.from_dict(data["name"], where="%s name" % ident),
        # summary 可以省：没有就退回名字，免得界面上出现空行
        summary=Text.from_dict(data["summary"], where="%s summary" % ident)
        if data.get("summary") else Text.from_dict(data["name"], where="%s name" % ident),
        unlock_level=level,
        powers=powers,
        resources=resources,
        source=source,
    )


def _parse_refresh(data: Any, where: str) -> Refresh:
    if data is None:
        return Refresh.LONG_REST
    key = str(data).strip().lower()
    if key not in REFRESH_KINDS:
        raise PluginError("%s 的 slot_refresh 必须是 %s"
                          % (where, "/".join(sorted(REFRESH_KINDS))))
    return REFRESH_KINDS[key]


def _parse_level_table(data: Any, where: str) -> dict[int, int]:
    if not data:
        return {}
    if not isinstance(data, Mapping):
        raise PluginError("%s 必须是 等级→数值 的映射" % where)
    try:
        return {int(key): int(value) for key, value in data.items()}
    except (TypeError, ValueError):
        raise PluginError("%s 必须是 等级→数值 的映射" % where)


def _parse_mastery_counts(data: Any, ident: str) -> dict[int, int]:
    """武器精通件数表。**写错了必须报错** —— 静默吞掉一个非法等级，
    界面上就变成「战士 5 级选不了精通」，查起来要翻三层。"""
    table = _parse_level_table(data, "%s mastery_counts" % ident)
    for level, count in table.items():
        if not 1 <= level <= 20:
            raise PluginError("%s 的 mastery_counts 等级越界：%r" % (ident, level))
        if not 0 <= count <= 10:
            raise PluginError("%s 的 mastery_counts 件数不合理：%d 级 %r"
                              % (ident, level, count))
    return table


def parse_slots(data: Any) -> dict[int, tuple[int, ...]]:
    """法术位表：`{5: [4,3,2,0,0,0,0,0,0]}`。多写或写错环数都要当场报错。"""
    if not data:
        return {}
    if not isinstance(data, Mapping):
        raise PluginError("slots 必须是 等级→9 个环位 的映射")
    rows: dict[int, tuple[int, ...]] = {}
    for key, value in data.items():
        if not isinstance(value, (list, tuple)):
            raise PluginError("slots 的 %r 必须是 9 个整数的列表" % (key,))
        if len(value) > 9:
            raise PluginError("slots 的 %r 超过 9 环：%r" % (key, value))
        try:
            row = tuple(int(item) for item in value)
        except (TypeError, ValueError):
            raise PluginError("slots 的 %r 必须是整数：%r" % (key, value))
        if any(item < 0 for item in row):
            raise PluginError("slots 的 %r 出现负环位：%r" % (key, value))
        rows[int(key)] = row
    return rows


def _parse_class_proficiencies(data: Any, where: str) -> tuple[str, ...]:
    """职业给的武器/护甲熟练。

    写成 `{weapons: [simple, martial], armor: [light, medium, shield]}`，
    解析成 `weapon.simple` / `armor.light` 这种 token —— 与 `grant_proficiency`
    同一套命名，这样装备判定只需要看一份集合。
    """
    if not data:
        return ()
    if not isinstance(data, Mapping):
        raise PluginError("%s 的 proficiencies 必须是映射" % where)
    tokens: list[str] = []
    for kind, values in data.items():
        if kind not in ("weapons", "armor"):
            raise PluginError("%s 的 proficiencies 只认 weapons / armor，实际 %r" % (where, kind))
        prefix = "weapon" if kind == "weapons" else "armor"
        for value in (values or ()):
            token = "%s.%s" % (prefix, str(value).lower().replace("-", "_"))
            if token not in tokens:
                tokens.append(token)
    return tuple(tokens)


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
        casting_ability=str(data.get("casting_ability", "")).lower(),
        subclass_level=subclass_level,
        skill_choices=int(data.get("skill_choices", 2)),
        skill_list=tuple(str(item) for item in (data.get("skill_list") or ())),
        resources=resources,
        powers=powers,
        proficiencies=_parse_class_proficiencies(data.get("proficiencies"), ident),
        morph=parse_cr_axis(data.get("morph")),
        slots=parse_slots(data.get("slots")),
        cantrips=_parse_level_table(data.get("cantrips"), "%s cantrips" % ident),
        prepared=_parse_level_table(data.get("prepared"), "%s prepared" % ident),
        mastery_counts=_parse_mastery_counts(data.get("mastery_counts"), ident),
        slot_refresh=_parse_refresh(data.get("slot_refresh"), ident),
        source=source,
    )


@dataclass(frozen=True)
class MulticlassDef:
    """兼职条目（PHB「Multiclassing」表）：前置属性与多职业熟练。

    `prereq` 外层是「或」、内层映射是「且」：战士 `[{str:13},{dex:13}]`
    = 力量 13 **或** 敏捷 13；武僧 `[{dex:13, wis:13}]` = 两项都要。
    `grants` 与职业熟练同一套 token（weapon.* / armor.*），豁免熟练
    永远不在这里 —— 起始职业才有（§12.3）。
    """

    class_id: str
    prereq: tuple[tuple[tuple[str, int], ...], ...] = ()
    grants: tuple[str, ...] = ()

    def prereq_ok(self, abilities) -> list[str]:
        """返回不满足的原因（空 = 可进入）。任一「且」组全满足即可。"""
        problems: list[str] = []
        for alternative in self.prereq:
            missing = []
            for key, need in alternative:
                try:
                    score = abilities.score(key)
                except RuleError:
                    missing.append("未知属性 %s" % key)
                    continue
                if score < int(need):
                    missing.append("%s %d < %d" % (key.upper(), score, int(need)))
            if not missing:
                return []              # 有一组满足就行
            problems.extend(missing)
        return ["；".join(dict.fromkeys(problems))] if problems else []


def parse_multiclass_entry(data: Any, source: str = "") -> MulticlassDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的兼职条目必须是映射" % source)
    class_id = str(data.get("class") or "")
    if not class_id:
        raise PluginError("%s 的兼职条目缺少 class" % source)
    raw_prereq = data.get("prereq") or ()
    if isinstance(raw_prereq, Mapping):
        raw_prereq = (raw_prereq,)
    alternatives: list[tuple[tuple[str, int], ...]] = []
    for alternative in raw_prereq:
        if not isinstance(alternative, Mapping):
            raise PluginError("%s 的 %s prereq 每一组都必须是映射" % (source, class_id))
        group = tuple((str(key).lower(), int(need))
                      for key, need in alternative.items())
        for key, _need in group:
            if key not in ABILITY_KEYS:
                raise PluginError("%s 的 %s prereq 用了未知属性 %r"
                                  % (source, class_id, key))
        alternatives.append(group)
    return MulticlassDef(
        class_id=class_id,
        prereq=tuple(alternatives),
        grants=tuple(str(item) for item in (data.get("grants") or ())),
    )
