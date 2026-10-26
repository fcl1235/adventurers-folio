# -*- coding: utf-8 -*-
"""插件加载：读 YAML、坏内容只坏自己、跨插件交叉校验。

三条原则见包注释（内容不进代码 / 坏内容只坏自己 / 解析期就校验）。
拆自 P11 之前的 content.py。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..kernel.errors import DndError, PluginError, RuleError
from ..kernel.ids import is_valid
from ..plugin import Manifest, load_manifest
from ..rules.powers import Power, PowerBook, parse_power
from .bestiary import (
    FormSpec, SummonDef, parse_cr_axis, parse_form, parse_monster,
    parse_summon,
)
from .classes import (
    ClassDef, MulticlassDef, SubclassDef, parse_class,
    parse_multiclass_entry, parse_subclass,
)
from .feats import FeatDef, SPELL_LIST_ANY, parse_feat
from .items import ArmorDef, WeaponDef, parse_armor, parse_weapon
from .skills import SkillDef, ToolDef, parse_skill, parse_tool
from .spells import SpellDef, parse_spell, parse_spell_list
from .bestiary import MonsterDef  # noqa: F401  （类型注解用，见下方 PluginContent）

# --- 插件与汇总 -------------------------------------------------------
@dataclass
class PluginContent:
    manifest: Manifest | None = None
    classes: dict[str, ClassDef] = field(default_factory=dict)
    subclasses: dict[str, SubclassDef] = field(default_factory=dict)
    book: PowerBook = field(default_factory=PowerBook)
    forms: dict[str, FormSpec] = field(default_factory=dict)
    armors: dict[str, ArmorDef] = field(default_factory=dict)
    weapons: dict[str, WeaponDef] = field(default_factory=dict)
    spells: dict[str, SpellDef] = field(default_factory=dict)
    spell_lists: dict[str, tuple[str, ...]] = field(default_factory=dict)
    feats: dict[str, FeatDef] = field(default_factory=dict)
    skills: dict[str, SkillDef] = field(default_factory=dict)
    tools: dict[str, ToolDef] = field(default_factory=dict)
    summons: dict[str, "SummonDef"] = field(default_factory=dict)
    monsters: dict[str, "MonsterDef"] = field(default_factory=dict)
    multiclass: dict[str, MulticlassDef] = field(default_factory=dict)
    caster_progression: dict[int, dict[int, int]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ContentBundle:
    classes: dict[str, ClassDef] = field(default_factory=dict)
    subclasses: dict[str, SubclassDef] = field(default_factory=dict)
    book: PowerBook = field(default_factory=PowerBook)
    forms: dict[str, FormSpec] = field(default_factory=dict)
    armors: dict[str, ArmorDef] = field(default_factory=dict)
    weapons: dict[str, WeaponDef] = field(default_factory=dict)
    spells: dict[str, SpellDef] = field(default_factory=dict)
    spell_lists: dict[str, tuple[str, ...]] = field(default_factory=dict)
    feats: dict[str, FeatDef] = field(default_factory=dict)
    skills: dict[str, SkillDef] = field(default_factory=dict)
    tools: dict[str, ToolDef] = field(default_factory=dict)
    summons: dict[str, "SummonDef"] = field(default_factory=dict)
    monsters: dict[str, "MonsterDef"] = field(default_factory=dict)
    multiclass: dict[str, MulticlassDef] = field(default_factory=dict)
    caster_progression: dict[int, dict[int, int]] = field(default_factory=dict)
    manifests: list[Manifest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # overlay 账本：谁替换了谁（P14）。存的是人话行，供自检与排查打印。
    replaced: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def class_def(self, class_id: str) -> ClassDef:
        if class_id not in self.classes:
            raise PluginError("没有这个职业：%s（已加载：%s）"
                              % (class_id, ", ".join(sorted(self.classes)) or "无"))
        return self.classes[class_id]

    def class_by_short(self, short: str) -> str:
        """短名（`wizard`）→ 完整职业 id（`dnd2024.class.wizard`）。

        不写死前缀：专长的 `spell_list: wizard` 写的是短名，职业来自哪个插件
        就从加载结果里查哪个（F36）。多个插件都提供 `.class.<短名>` 时报
        歧义，不猜 —— 猜一个等于让另一个插件的专长选到错职业的法术表。
        """
        hits = sorted(item_id for item_id in self.classes
                      if item_id.split(".")[-2:] == ["class", short])
        if not hits:
            raise PluginError("没有短名为 %s 的职业（已加载：%s）"
                              % (short, ", ".join(sorted(self.classes)) or "无"))
        if len(hits) > 1:
            raise PluginError("短名 %s 匹配到多个职业：%s" % (short, "、".join(hits)))
        return hits[0]

    def armor(self, armor_id: str) -> ArmorDef:
        if armor_id not in self.armors:
            raise PluginError("没有这件护甲：%s" % armor_id)
        return self.armors[armor_id]

    def weapon(self, weapon_id: str) -> WeaponDef:
        if weapon_id not in self.weapons:
            raise PluginError("没有这件武器：%s" % weapon_id)
        return self.weapons[weapon_id]

    def spell(self, spell_id: str) -> SpellDef:
        if spell_id not in self.spells:
            raise PluginError("没有这个法术：%s" % spell_id)
        return self.spells[spell_id]

    def spell_list(self, class_id: str) -> tuple[str, ...]:
        return self.spell_lists.get(class_id, ())

    def classes_for_spell(self, spell_id: str) -> tuple[str, ...]:
        """哪些职业能施放这个法术 —— 从法术表反查，法术本身不存这份信息。

        存两份必然漂移：法术表是**权威**（第三方插件加一行就能给某个职业补法术），
        法术条目只描述法术自己。
        """
        return tuple(sorted(class_id for class_id, spells in self.spell_lists.items()
                            if spell_id in spells))

    def spells_of_level(self, level: int, class_id: str | None = None) -> tuple[SpellDef, ...]:
        """某一环的法术（可按职业过滤），按 id 排序保证界面稳定。"""
        allowed = set(self.spell_list(class_id)) if class_id else None
        return tuple(sorted(
            (spell for spell in self.spells.values()
             if int(spell.level) == int(level)
             and (allowed is None or spell.id in allowed)),
            key=lambda item: item.id,
        ))

    def summons_for_spell(self, spell_id: str) -> tuple[SummonDef, ...]:
        """这个法术能召出哪几只生物 —— 从召唤物反查，法术自己不存这份名单。

        与 `classes_for_spell` 同一个道理：召唤物条目里写 `spell`，法术条目只描述
        法术自己。存两份就会出现「法术说能召三只、召唤物表里只有两只」的漂移。
        """
        return tuple(sorted(
            (item for item in self.summons.values() if item.spell == spell_id),
            key=lambda item: (item.variant.zh if item.variant else "", item.id),
        ))

    def subclass(self, subclass_id: str) -> SubclassDef:
        if subclass_id not in self.subclasses:
            raise PluginError("没有这个子职：%s（已加载：%s）"
                              % (subclass_id, ", ".join(sorted(self.subclasses)) or "无"))
        return self.subclasses[subclass_id]

    def subclasses_for(self, class_id: str) -> tuple[SubclassDef, ...]:
        """某个职业可选的全部子职（按 id 排序，保证界面顺序稳定）。"""
        return tuple(sorted(
            (item for item in self.subclasses.values() if item.class_id == class_id),
            key=lambda item: item.id,
        ))

    def feat(self, feat_id: str) -> FeatDef:
        if feat_id not in self.feats:
            raise PluginError("没有这个专长：%s（已加载：%s）"
                              % (feat_id, ", ".join(sorted(self.feats)) or "无"))
        return self.feats[feat_id]

    def feats_of_kind(self, kind: str) -> tuple[FeatDef, ...]:
        return tuple(sorted(
            (item for item in self.feats.values() if item.kind == kind),
            key=lambda item: item.id,
        ))

    def stats(self) -> dict[str, Any]:
        return {
            "classes": len(self.classes),
            "feats": len(self.feats),
            "subclasses": len(self.subclasses),
            "powers": len(self.book.ids()),
            "forms": len(self.forms),
            "armors": len(self.armors),
            "weapons": len(self.weapons),
            "spells": len(self.spells),
            "spell_lists": len(self.spell_lists),
            "skills": len(self.skills),
            "tools": len(self.tools),
            "summons": len(self.summons),
            "monsters": len(self.monsters),
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

    for path in sorted((base / "subclasses").glob("*.yaml")) \
            if (base / "subclasses").exists() else []:
        rel = "%s/subclasses/%s" % (base.name, path.name)
        try:
            subclass = parse_subclass(_read_yaml(path), source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if subclass.id in result.subclasses:
            result.errors.append("%s 的子职 id 重复：%s" % (rel, subclass.id))
            continue
        result.subclasses[subclass.id] = subclass
        for power in subclass.powers:
            try:
                result.book.add(power)
            except PluginError as exc:
                result.errors.append(str(exc))

    bestiary = base / "bestiary"
    if bestiary.exists():
        for path in sorted(bestiary.glob("*.yaml")):
            rel = "%s/bestiary/%s" % (base.name, path.name)
            try:
                rows = _read_yaml(path) or []
            except PluginError as exc:
                result.errors.append(str(exc))
                continue
            if isinstance(rows, Mapping):
                rows = [rows]
            for row in rows:
                try:
                    form = parse_form(row, source=rel)
                except (PluginError, DndError) as exc:
                    result.errors.append(str(exc))
                    continue
                if form.id in result.forms:
                    result.errors.append("%s 的形态 id 重复：%s" % (rel, form.id))
                    continue
                result.forms[form.id] = form

    _load_items(base, result)
    _load_multiclass(base, result)
    _load_caster_progression(base, result)
    _load_spells(base, result)
    _load_feats(base, result)
    _load_skills(base, result)
    _load_tools(base, result)
    _load_summons(base, result)
    _load_monsters(base, result)
    result.book.validate_augments()
    return result


def _load_summons(base: Path, result: PluginContent) -> None:
    """召唤物：一个插件一份 `summons.yaml`。

    与 `tools.yaml` 同一个位置：几十条、条目之间没有互相引用、按 id 取用 ——
    没有理由拆成「一条一文件」（那是专长/子职为了 git diff 好读才做的）。
    """
    path = base / "summons.yaml"
    if not path.exists():
        return
    rel = "%s/summons.yaml" % base.name
    try:
        rows = _read_yaml(path) or []
    except PluginError as exc:
        result.errors.append(str(exc))
        return
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows:
        try:
            summon = parse_summon(row, source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if summon.id in result.summons:
            result.errors.append("%s 的召唤物 id 重复：%s" % (rel, summon.id))
            continue
        result.summons[summon.id] = summon


def _load_monsters(base: Path, result: PluginContent) -> None:
    """怪物：一个插件一份 `monsters.yaml`（与 `summons.yaml` 同一个位置）。

    为什么整表一个文件：怪物之间没有互相引用，按 id 取用，几十到上百条 ——
    一条一文件只在「git diff 要人能读」时才值得（专长/子职），怪物看的是排序。
    """
    path = base / "monsters.yaml"
    if not path.exists():
        return
    rel = "%s/monsters.yaml" % base.name
    try:
        rows = _read_yaml(path) or []
    except PluginError as exc:
        result.errors.append(str(exc))
        return
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows:
        try:
            monster = parse_monster(row, source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if monster.id in result.monsters:
            result.errors.append("%s 的怪物 id 重复：%s" % (rel, monster.id))
            continue
        result.monsters[monster.id] = monster


def _load_tools(base: Path, result: PluginContent) -> None:
    """工具表：一个插件一份 `tools.yaml`（37 行，名称+类别+建议属性）。

    与技能同样的位置、同样的写法 —— 工具只是「另一种可以练熟的物品」，
    不该因为「只有 37 件」就塞进代码里。
    """
    path = base / "tools.yaml"
    if not path.exists():
        return
    rel = "%s/tools.yaml" % base.name
    try:
        rows = _read_yaml(path) or []
    except PluginError as exc:
        result.errors.append(str(exc))
        return
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows:
        try:
            tool = parse_tool(row, source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if tool.id in result.tools:
            result.errors.append("%s 的工具 id 重复：%s" % (rel, tool.id))
            continue
        result.tools[tool.id] = tool


def _load_feats(base: Path, result: PluginContent) -> None:
    """专长：一专长一文件（`feats/defense.yaml`）。

    与职业/子职同一套原语，所以装载时只多一步「把 powers 塞进 PowerBook」——
    专长的静态效果之后走的是完全相同的 modifier / effect 管道。
    """
    folder = base / "feats"
    if not folder.exists():
        return
    for path in sorted(folder.glob("*.yaml")):
        rel = "%s/feats/%s" % (base.name, path.name)
        try:
            feat = parse_feat(_read_yaml(path), source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if feat.id in result.feats:
            result.errors.append("%s 的专长 id 重复：%s" % (rel, feat.id))
            continue
        result.feats[feat.id] = feat
        for power in feat.powers:
            try:
                result.book.add(power)
            except PluginError as exc:
                result.errors.append(str(exc))


def _load_skills(base: Path, result: PluginContent) -> None:
    """技能表：一个插件一份 `skills.yaml`（18 行，名称+属性）。"""
    path = base / "skills.yaml"
    if not path.exists():
        return
    rel = "%s/skills.yaml" % base.name
    try:
        rows = _read_yaml(path) or []
    except PluginError as exc:
        result.errors.append(str(exc))
        return
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows:
        try:
            skill = parse_skill(row, source=rel)
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))
            continue
        if skill.id in result.skills:
            result.errors.append("%s 的技能 id 重复：%s" % (rel, skill.id))
            continue
        result.skills[skill.id] = skill


def _load_spells(base: Path, result: PluginContent) -> None:
    """法术与职业法术表。法术按环一文件（`spells/level-3.yaml`）。"""
    folder = base / "spells"
    if folder.exists():
        for path in sorted(folder.glob("*.yaml")):
            rel = "%s/spells/%s" % (base.name, path.name)
            try:
                rows = _read_yaml(path) or []
            except PluginError as exc:
                result.errors.append(str(exc))
                continue
            if isinstance(rows, Mapping):
                rows = [rows]
            for row in rows:
                try:
                    spell = parse_spell(row, source=rel)
                except (PluginError, DndError) as exc:
                    result.errors.append(str(exc))
                    continue
                if spell.id in result.spells:
                    result.errors.append("%s 的法术 id 重复：%s" % (rel, spell.id))
                    continue
                result.spells[spell.id] = spell

    lists = base / "spell-lists"
    if lists.exists():
        for path in sorted(lists.glob("*.yaml")):
            rel = "%s/spell-lists/%s" % (base.name, path.name)
            try:
                class_id, spells = parse_spell_list(_read_yaml(path), source=rel)
            except (PluginError, DndError) as exc:
                result.errors.append(str(exc))
                continue
            if class_id in result.spell_lists:
                result.errors.append("%s 的法术表职业重复：%s" % (rel, class_id))
                continue
            result.spell_lists[class_id] = spells


def _load_multiclass(base: Path, result: PluginContent) -> None:
    """兼职表：前置属性 + 多职业熟练。文件可选（没有就当这个插件不支持兼职）。"""
    path = base / "multiclass.yaml"
    if not path.exists():
        return
    rel = "%s/multiclass.yaml" % base.name
    try:
        rows = _read_yaml(path) or []
    except PluginError as exc:
        result.errors.append(str(exc))
        return
    if isinstance(rows, Mapping):
        rows = [rows]
    for row in rows:
        try:
            entry = parse_multiclass_entry(row, rel)
            if entry.class_id in result.multiclass:
                raise PluginError("%s 的兼职条目重复：%s" % (rel, entry.class_id))
            result.multiclass[entry.class_id] = entry
        except (PluginError, DndError) as exc:
            result.errors.append(str(exc))


def _load_caster_progression(base: Path, result: PluginContent) -> None:
    """兼职合并法术位表。1–20 级必须一档不缺 —— 缺一档，那一档的兼职角色就
    查不到位，静默少一整页法术位。"""
    path = base / "caster-progression.yaml"
    if not path.exists():
        return
    rel = "%s/caster-progression.yaml" % base.name
    try:
        data = _read_yaml(path) or {}
        table_raw = data.get("slots") if isinstance(data, Mapping) else data
        if not isinstance(table_raw, Mapping):
            raise PluginError("%s 的 slots 必须是映射" % rel)
        table: dict[int, dict[int, int]] = {}
        for level, row in table_raw.items():
            if not isinstance(row, Mapping):
                raise PluginError("%s 的第 %s 级必须是映射" % (rel, level))
            table[int(level)] = {int(k): int(v) for k, v in row.items()}
    except (PluginError, DndError) as exc:
        result.errors.append(str(exc))
        return
    missing = [level for level in range(1, 21) if level not in table]
    if missing:
        result.errors.append("%s 的合并位表缺 %s 级" % (rel, "、".join(map(str, missing))))
        return
    result.caster_progression.update(table)


def _load_items(base: Path, result: PluginContent) -> None:
    """物品目录：按条目的 `kind` 分派。现在只有护甲，武器随 P5c 接入。"""
    folder = base / "items"
    if not folder.exists():
        return
    for path in sorted(folder.glob("*.yaml")):
        rel = "%s/items/%s" % (base.name, path.name)
        try:
            rows = _read_yaml(path) or []
        except PluginError as exc:
            result.errors.append(str(exc))
            continue
        if isinstance(rows, Mapping):
            rows = [rows]
        for row in rows:
            kind = str(row.get("kind", "armor")).lower() if isinstance(row, Mapping) else ""
            try:
                if kind == "armor":
                    armor = parse_armor(row, where=rel)
                    if armor.id in result.armors:
                        raise PluginError("%s 的护甲 id 重复：%s" % (rel, armor.id))
                    result.armors[armor.id] = armor
                elif kind == "weapon":
                    weapon = parse_weapon(row, where=rel)
                    if weapon.id in result.weapons:
                        raise PluginError("%s 的武器 id 重复：%s" % (rel, weapon.id))
                    result.weapons[weapon.id] = weapon
                else:
                    raise PluginError("%s 未知物品类型 %r（支持 armor / weapon）" % (rel, kind))
            except (PluginError, DndError) as exc:
                result.errors.append(str(exc))


def _absorb(bundle: "ContentBundle", content: PluginContent,
            kind: str, target: dict, source: dict) -> None:
    """合并一类内容。撞 id 的两种下场（§13.4，P14 收敛为两语义）：

    * 新插件的清单**声明过 replaces** → 整条替换，记进 `bundle.replaced`；
    * 没声明 → 报错。「后加载的赢」是静默覆盖，不给。
    字段级 patch 不做 —— `Effect.to_dict` 非无损往返（§14.7 第 5 条），
    合并必丢字段，要改哪条就把哪条写全。
    """
    declared = content.manifest.replaces if content.manifest is not None else ()
    for key, value in source.items():
        if key in target:
            if key in declared:
                target[key] = value
                bundle.replaced.append(
                    "%s %s 由 %s 替换" % (kind, key, manifest_id_hint(content)))
            else:
                bundle.errors.append(
                    "%s %s 重复提供（要覆盖请在清单里声明 replaces）" % (kind, key))
            continue
        target[key] = value


def manifest_id_hint(content: PluginContent) -> str:
    return content.manifest.id if content.manifest is not None else "?"


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
        _absorb(bundle, content, "职业", bundle.classes, content.classes)
        _absorb(bundle, content, "形态", bundle.forms, content.forms)
        _absorb(bundle, content, "护甲", bundle.armors, content.armors)
        _absorb(bundle, content, "武器", bundle.weapons, content.weapons)
        _absorb(bundle, content, "技能", bundle.skills, content.skills)
        _absorb(bundle, content, "工具", bundle.tools, content.tools)
        _absorb(bundle, content, "召唤物", bundle.summons, content.summons)
        _absorb(bundle, content, "怪物", bundle.monsters, content.monsters)
        _absorb(bundle, content, "兼职条目", bundle.multiclass, content.multiclass)
        _absorb(bundle, content, "子职", bundle.subclasses, content.subclasses)
        _absorb(bundle, content, "专长", bundle.feats, content.feats)
        _absorb(bundle, content, "法术", bundle.spells, content.spells)
        _absorb(bundle, content, "法术表", bundle.spell_lists, content.spell_lists)
        # 能力注册表自带来源追溯，替换走它自己的 replace_existing
        declared = content.manifest.replaces if content.manifest is not None else ()
        for power in content.book.all():
            if bundle.book.has(power.id):
                if power.id in declared:
                    bundle.book.add(power, replace_existing=True)
                    bundle.replaced.append(
                        "能力 %s 由 %s 替换" % (power.id, manifest_id_hint(content)))
                else:
                    bundle.errors.append(
                        "能力 %s 重复提供（要覆盖请在清单里声明 replaces）" % power.id)
                continue
            bundle.book.add(power)
        if content.caster_progression:
            if bundle.caster_progression:
                bundle.errors.append("合并位表 %s 重复提供" % manifest_id_hint(content))
                continue
            bundle.caster_progression.update(content.caster_progression)
    _check_subclass_classes(bundle)
    _check_spell_lists(bundle)
    _check_feat_spell_refs(bundle)
    _check_summon_spells(bundle)
    bundle.book.validate_augments()
    return bundle


def _check_summon_spells(bundle: ContentBundle) -> None:
    """召唤物指向的法术必须存在。

    只能合并之后查：召唤物与法术可以来自不同插件（一个插件提供法术、另一个补
    stat block 是合法用法）。查不到就是「召出来但界面找不到入口」，报错而不是静默丢。
    """
    for summon in bundle.summons.values():
        if summon.spell not in bundle.spells:
            bundle.errors.append(
                "召唤物 %s 指向不存在的法术 %s" % (summon.id, summon.spell))


def _check_spell_lists(bundle: ContentBundle) -> None:
    """法术表里引用的 id 必须存在；表里也不能把不同环级的法术混在一起。

    同样只能在合并之后查：法术与法术表可以来自不同插件。
    """
    for class_id, spells in bundle.spell_lists.items():
        if class_id not in bundle.classes:
            bundle.errors.append("法术表挂在未知职业上：%s" % class_id)
        missing = [ident for ident in spells if ident not in bundle.spells]
        if missing:
            bundle.errors.append("法术表 %s 引用了不存在的法术：%s"
                                 % (class_id, ", ".join(missing[:5])))


def _check_feat_spell_refs(bundle: ContentBundle) -> None:
    """专长引用的法术/法术表必须存在。

    与法术表同样的理由只能在合并后查：专长可以来自别的插件，法术也是。
    `choice.spell_list` 指向的职业必须**有法术表** —— 否则玩家在界面上会看到
    一个空下拉框，而不是一条能被看见的错误。
    """
    for feat in bundle.feats.values():
        missing = [ident for ident in feat.spells if ident not in bundle.spells]
        if missing:
            bundle.errors.append("专长 %s 给了不存在的法术：%s"
                                 % (feat.id, ", ".join(missing[:5])))
        for choice in feat.choices:
            if choice.kind != "spell":
                continue
            if choice.spell_list == SPELL_LIST_ANY:
                continue
            try:
                class_id = bundle.class_by_short(choice.spell_list)
            except PluginError as exc:
                bundle.errors.append("专长 %s 的选择项 %s：%s"
                                     % (feat.id, choice.id, exc))
                continue
            if not bundle.spell_list(class_id):
                bundle.errors.append(
                    "专长 %s 的选择项 %s 指向的职业 %s 没有法术表"
                    % (feat.id, choice.id, choice.spell_list))


def _check_subclass_classes(bundle: ContentBundle) -> None:
    """子职必须挂在已加载的职业上。

    只能放在合并之后做：职业与子职可以来自不同插件（第三方给核心职业补子职）。
    解析期查不到别的插件有没有这个职业，所以这一步晚于解析是必然的。
    """
    for subclass in bundle.subclasses.values():
        if subclass.class_id not in bundle.classes:
            bundle.errors.append(
                "子职 %s 挂在未知职业 %s 上（来自 %s）"
                % (subclass.id, subclass.class_id, subclass.source or "?")
            )


__all__ = [
    "ResourceDef", "ClassDef", "SubclassDef", "ArmorDef", "WeaponDef",
    "PluginContent", "ContentBundle",
    "parse_resource", "parse_class", "parse_subclass", "parse_cr_axis", "parse_form",
    "parse_armor", "parse_weapon", "powers_at_level",
    "SpellDef", "parse_spell", "parse_spell_list", "lookup_dice",
    "FeatDef", "FeatChoice", "parse_feat", "parse_feat_choice",
    "FEAT_KINDS", "CHOICE_KINDS", "CHOICE_UNIVERSE", "DAMAGE_TYPES", "SKILL_KEYS",
    "SkillDef", "parse_skill",
    "load_plugin", "load_all",
]
