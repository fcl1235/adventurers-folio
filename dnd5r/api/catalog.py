# -*- coding: utf-8 -*-
"""内容目录：查内容包（法术 / 召唤物 / 怪物 / 插件清单）与「照内容造一只」。
只读查询，不改角色状态。拆自 P11 之前的巨型 __init__。"""
from __future__ import annotations

from typing import Any

from ..content import ContentBundle, load_all
from ..kernel.errors import PluginError, RuleError
from ..model.actor import Actor, ActorKind
from ..rules.morph import form_id
from ..rules.spellcasting import spell_detail

def load_content(root: str = "plugins") -> ContentBundle:
    """加载插件目录。坏的插件只进 errors，不抛出。"""
    return load_all(root)


def content_summary(bundle: ContentBundle, locale: str = "zh") -> dict:
    stats = bundle.stats()
    stats["class_names"] = sorted(item.name.get(locale) for item in bundle.classes.values())
    stats["plugins"] = [manifest.id for manifest in bundle.manifests]
    return stats


def spell_catalog(
    bundle: ContentBundle,
    class_id: str | None = None,
    level: int | None = None,
    locale: str = "zh",
) -> dict:
    """法术目录（可按职业与环级过滤）。给界面出选择列表用。"""
    allowed = set(bundle.spell_list(class_id)) if class_id else None
    rows = [
        spell for spell in bundle.spells.values()
        if (level is None or int(spell.level) == int(level))
        and (allowed is None or spell.id in allowed)
    ]
    rows.sort(key=lambda item: (int(item.level), item.id))
    return {
        "class": class_id,
        "level": level,
        "count": len(rows),
        "spells": [
            {"id": spell.id, "name": spell.name.get(locale), "level": int(spell.level),
             "school": spell.school, "ritual": spell.ritual,
             "concentration": spell.concentration,
             "classes": list(bundle.classes_for_spell(spell.id))}
            for spell in rows
        ],
    }


def spell_info(bundle: ContentBundle, spell_id: str, locale: str = "zh",
               character_level: int | None = None) -> dict:
    """单条法术的完整展示数据（含基础环的伤害骰式）。

    传 `character_level` 才会按 5 / 11 / 17 级给出戏法成长后的骰式 ——
    成长看**角色等级**，不是环位。
    """
    return spell_detail(bundle, spell_id, locale, character_level)


def summon_info(bundle: ContentBundle, summon_id: str, slot_level: int = 0,
                size: str = "", locale: str = "zh") -> dict:
    """一只召唤物在某个环级下的 stat block 卡。

    `caster_mod` 一律按 0 算：法术攻击加值 / 豁免 DC / 施法属性调整值**取决于谁在施法**，
    卡片上写「＝你的法术攻击加值」比写一个假数字诚实。真要在战斗里结算，调用方再把
    角色的调整值传进 `rules.summon.resolve`。
    """
    summon = bundle.summons.get(str(summon_id))
    if summon is None:
        raise PluginError("没有这个召唤物：%s（已加载：%s）"
                          % (summon_id, ", ".join(sorted(bundle.summons)) or "无"))
    slot = int(slot_level) or int(bundle.spell(summon.spell).level)
    return summon.card(slot, locale, 0, size)


def monster_catalog(
    content: ContentBundle,
    locale: str = "zh",
    max_cr: float | None = None,
) -> list[dict]:
    """可选怪物清单（按 CR、再按 id 排序）。

    `max_cr` 只用来筛「这一队打得动什么」，不替 DM 决定放几只 ——
    遭遇难度不是这只程序算得出来的东西。
    """
    from ..rules.monsters import cr_text

    rows = []
    for ident, monster in content.monsters.items():
        if max_cr is not None and float(monster.cr) > float(max_cr) + 1e-9:
            continue
        rows.append({
            "id": ident,
            "name": monster.name.get(locale),
            "size": monster.size,
            "ac": int(monster.ac),
            "hp": int(monster.hp),
            "cr": float(monster.cr),
            "cr_text": cr_text(monster.cr),
            "has_actions": bool(monster.actions),
        })
    return sorted(rows, key=lambda row: (row["cr"], row["id"]))


def spawn_monster(
    content: ContentBundle,
    monster_id: str,
    index: int = 1,
) -> Actor:
    """照内容造一只怪物，交给 `new_encounter` 或 `Encounter.add`。

    `index` 是同种第几只：三只哥布林要有三个不同的 id，否则 `add` 会以
    「参与者重复」拒绝（而且三段血会记到同一只身上）。
    """
    from ..rules.monsters import build_monster

    if monster_id not in content.monsters:
        raise PluginError("没有这只怪物：%s（已加载 %d 只，例如 %s）"
                          % (monster_id, len(content.monsters),
                             "、".join(sorted(content.monsters)[:3]) or "无"))
    return build_monster(content.monsters[monster_id], index)


def _monster_def(content: ContentBundle, actor: Actor):
    """从 Actor 找回它的怪物条目。`#2` 这类序号后缀不属于内容 id。"""
    base = str(actor.id).split("#", 1)[0]
    if base not in content.monsters:
        raise RuleError("%s 不是内容里的怪物（找不到 %s）" % (actor.id, base))
    return content.monsters[base]


def _action_table(content: ContentBundle, actor: Actor):
    """这个 Actor 从哪里拿「它自己的攻击」：怪物卡，或变形后的形态卡。

    变形中的角色是**玩家**（`kind` 还是 pc），动作却在形态层上。按 `kind`
    分支会漏掉这一支 —— 德鲁伊变熊以后被当成「还在挥长剑」。
    所以这里看的是**最上层**（`top()`），不是本体的 kind。
    """
    top = actor.top()
    if top.kind is ActorKind.SUMMON:
        from ..rules.summon import build_summon_actor
        # 召唤物入場时把动作表记在 scratch……不 —— 它没有 scratch。动作表随
        # 施法参数变（环级/施法者攻加），所以这里按 id 现造一遍：
        # actor.display 没存环级，改为在 build 时把 table 挂在 actor 上。
        table = getattr(top, "summon_table", None)
        if table is None:
            base = str(actor.id).split("#", 1)[0]
            raise RuleError("%s 没带动作表（召唤物要用 api.roll_spell 召出来）" % base)
        return table
    if top.kind is ActorKind.FORM:
        ident = form_id(actor)
        if ident not in content.forms:
            raise RuleError("当前形态 %s 不在内容里" % ident)
        return content.forms[ident]
    if top.kind is ActorKind.MONSTER:
        return _monster_def(content, top)
    raise RuleError("%s 没有天然武器清单；只有怪物与变形中的角色才有"
                    % actor.display_name)


def monster_sheet(
    content: ContentBundle,
    monster_or_actor: Any,
    index: int = 1,
    locale: str = "zh",
) -> dict:
    """一张怪物卡：ac / hp / 属性 / 特性 / 动作。缺省按内容现造一只来读。"""
    from ..rules.monsters import monster_stats

    if isinstance(monster_or_actor, str):
        actor = spawn_monster(content, monster_or_actor, index)
    elif isinstance(monster_or_actor, Actor):
        actor = monster_or_actor
    else:
        raise RuleError("monster_sheet 要怪物 id 或 Actor：%r" % (monster_or_actor,))
    return monster_stats(_monster_def(content, actor), actor, locale)


def monster_actions(
    content: ContentBundle,
    monster_id: str,
    locale: str = "zh",
) -> list[dict]:
    """这只怪物能做什么（给界面列按钮）。"""
    from ..rules.monsters import attack_options

    if monster_id not in content.monsters:
        raise PluginError("没有这只怪物：%s" % monster_id)
    return attack_options(content.monsters[monster_id], locale)


def plugin_summary(root: str = "plugins", locale: str = "zh") -> list[dict]:
    """给前端看的插件列表；坏掉的插件只记录不抛出。"""
    from ..loader import discover

    found = discover(root)
    return [
        {
            "id": manifest.id,
            "kind": manifest.kind,
            "version": manifest.version,
            "name": manifest.name.get(locale),
            "provides": {key: len(value) for key, value in manifest.provides.items()},
        }
        for manifest in found.manifests
    ]
