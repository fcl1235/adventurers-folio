# -*- coding: utf-8 -*-
"""施法：法术豁免 DC、法术攻击加值、可选法术、法位与准备上限。

这一层**不做目标结算** —— 引擎现在只有一个角色，没有战斗目标模型
（敌人、区域、占据都还没进内核）。所以这里只做「算得出来的那部分」：

  DC = 8 + 熟练 + 施法属性调整值        ← 纯规则，与目标无关
  攻击加值 = 熟练 + 施法属性调整值
  可选法术 = 职业表 ∩ 当前环位 ≤ 最高可施环
  准备上限 / 戏法数 = 职业表查等级

伤害骰、豁免结果、区域影响留给出「施法结算」时再接 —— 那需要一个目标模型，
不是这一层能凭空造出来的。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

from ..kernel.errors import IllegalAction, RuleError
from ..model.actor import Actor
from ..model.levels import ClassLevel
from ..rules.resolver import Resolver
from .summon import slot_curve

if TYPE_CHECKING:               # 只在注解里用到，见下方说明
    from ..content import ClassDef, ContentBundle, SpellDef

# 这里**不能**在运行期 import `content`：`content` 为了解析能力要 import
# `rules.powers`，而 `powers` 要用本模块的法位函数（`lowest_slot` / `spend_slot`）。
# 三者一成环，`import dnd5r.api` 就直接炸。本文件只用到这三个类型做注解，
# 而 `from __future__ import annotations` 已经把注解变成字符串，运行期不需要它们。

# 法术位池的 id 前缀。位是建角色时统一建的（`build_actor`），
# 这里只读不建 —— 否则「算一次 DC」会顺手改角色状态。
SLOT_PREFIX = "dnd2024.slot."


def casting_ability(class_def: ClassDef) -> str:
    """这个职业用哪个属性施法。数据里没写就是内容错误，不猜 int。"""
    if not class_def.casting_ability:
        raise RuleError("职业 %s 没有声明 casting_ability" % class_def.id)
    return class_def.casting_ability


def spell_dc(resolver: Resolver, actor: Actor, ability: str):
    """法术豁免 DC：8 + 熟练 + 属性调整值。"""
    return resolver.spell_dc(actor, ability)


def free_cast_pool(actor: Actor, spell_id: str):
    """这道法术还能不能「不消耗法术位」放一次 —— 能就返回付账的那个池。

    池是**按法术绑的**（妖精触碰的「两道法术各一次」），所以这里只认
    `pool.spell == spell_id`。「还有几次」由池的余量回答，不另存一个计数器。
    多个池都能付时按 id 排序取第一个：同一份角色状态必须算出同一个结果。
    """
    pools = [pool for pool in actor.root().resources.pools.values()
             if pool.pays_for(spell_id) and pool.available > 0]
    return sorted(pools, key=lambda item: item.id)[0] if pools else None


def spell_attack_bonus(resolver: Resolver, actor: Actor, ability: str):
    return resolver.spell_attack(actor, ability)


def max_cantrips(class_def: ClassDef, class_level: ClassLevel) -> int:
    """已知戏法数（查表，取不超过等级的最大档）。"""
    return _at(class_def.cantrips, int(class_level))


def max_prepared(class_def: ClassDef, class_level: ClassLevel) -> int:
    """可准备法术数（2024 的「准备法术」表，不是「等级 + 属性」估算）。"""
    return _at(class_def.prepared, int(class_level))


def _at(table, class_level: int) -> int:
    """查表：取不超过该职业等级的最大档（与资源表同一条规则）。

    参数刻意叫 `class_level` 且只收整数 —— 这里查的是**职业**等级表，
    传进总等级就是错；C8 只拦 `level` 这个名字，名字写清才是真防线。
    """
    usable = [int(key) for key in table or () if int(key) <= int(class_level)]
    return 0 if not usable else int(table[max(usable)])


def highest_slot(actor: Actor, class_id: str) -> int:
    """这个职业当前能用的最高环位（从资源池里读，不从等级推）。"""
    top = 0
    for pool in actor.root().resources.pools.values():
        if pool.owner_class and pool.owner_class != class_id:
            continue
        if not pool.id.startswith(SLOT_PREFIX):
            continue
        level = int(pool.id.rsplit(".", 1)[-1])
        if pool.capacity > 0:
            top = max(top, level)
    return top


def spell_options(
    bundle: ContentBundle,
    actor: Actor,
    class_id: str,
    class_level: ClassLevel,
) -> tuple[SpellDef, ...]:
    """这个角色在这一职业下可选的施法法术（戏法另算）。

    过滤条件只有两条：在职业表里，且环级不超过当前最高施法位。
    准备与否属于玩家的选择，不在这里筛。
    """
    top = highest_slot(actor, class_id)
    allowed = set(bundle.spell_list(class_id))
    return tuple(sorted(
        (spell for spell in bundle.spells.values()
         if spell.id in allowed and 0 < int(spell.level) <= top),
        key=lambda item: (int(item.level), item.id),
    ))


def cantrip_options(bundle: ContentBundle, class_id: str) -> tuple[SpellDef, ...]:
    allowed = set(bundle.spell_list(class_id))
    return tuple(sorted(
        (spell for spell in bundle.spells.values()
         if spell.id in allowed and int(spell.level) == 0),
        key=lambda item: item.id,
    ))


def slot_rows(actor: Actor, class_id: str, locale: str = "zh") -> list[dict]:
    """法位余量表：[(环级, 剩余, 上限)]，按环级升序。"""
    rows = []
    for pool in actor.root().resources.pools.values():
        if not pool.id.startswith(SLOT_PREFIX):
            continue
        if pool.owner_class and pool.owner_class != class_id:
            continue
        level = int(pool.id.rsplit(".", 1)[-1])
        rows.append({"level": level, "left": pool.available, "max": pool.capacity,
                     "label": pool.label.get(locale) if pool.label else ""})
    return sorted(rows, key=lambda item: item["level"])


def slot_pools(actor: Actor, class_id: str = "") -> list[tuple[int, object]]:
    """[(环级, 池)]，按环级升序。

    `class_id` 为空时收**全部职业**的位（兼职的位是分开记的，但花的时候
    哪个环级有余量就花哪个 —— 环级本身已经决定了该扣谁）。
    """
    found = []
    for pool in actor.root().resources.pools.values():
        if not pool.id.startswith(SLOT_PREFIX):
            continue
        if class_id and pool.owner_class and pool.owner_class != class_id:
            continue
        found.append((int(pool.id.rsplit(".", 1)[-1]), pool))
    return sorted(found, key=lambda item: item[0])


def lowest_slot(actor: Actor, min_level: int, class_id: str = "") -> int | None:
    """最低的、有余量的、且不低于 `min_level` 的环级。没有就返回 None。

    这条是给「消耗一个 2 环或更高的法术位」这类原文用的：原文说「或更高」，
    所以不能挑最高的那个把人坑了。
    """
    for level, pool in slot_pools(actor, class_id):
        if level >= int(min_level) and pool.available > 0:
            return level
    return None


def spend_slot(actor: Actor, slot_level: int, class_id: str = ""):
    """扣掉**指定环级**的一个法术位，返回被扣的池。

    `slot_level` 是「用几环放」这件事的答案：升环施法时玩家选了 3 环，
    就扣 3 环。想表达「2 环或更高」先用 `lowest_slot()` 挑出环级。

    **没有任何位池的角色不拦**：怪物、召唤物、只能随意施法的存在本来就没有
    法术位账本，拦下来只会让「掷一次施法结算」对他们失效。有账本但没有这个
    环级才是错 —— 那说明界面让人选了一个没有的环位。
    """
    pools = slot_pools(actor, class_id)
    if not pools:
        return None
    index = int(slot_level)
    # 同一环级可能有多个池（职业位 + 创造的位）：按顺序找**有余额**的那个，
    # 第一个池空了直接报错会让人花不出去创造的位（P13 抓到）。
    same_level = [pool for level, pool in pools if level == index]
    if not same_level:
        raise IllegalAction("没有 %d 环法术位" % index)
    for pool in same_level:
        if pool.can_spend(1):
            pool.spend(1)
            return pool
    raise IllegalAction("没有可用的 %d 环法术位（已用光）" % index)


def highest_slot_table(class_def: ClassDef, class_level: ClassLevel) -> int:
    """按**职业表**算最高环位。建角色时资源池还没建，不能读池子。"""
    row = class_def.slots_at(class_level)
    top = 0
    for index, capacity in enumerate(row, start=1):
        if int(capacity) > 0:
            top = index
    return top


def _spell_of(bundle: ContentBundle, spell_id: str):
    spell = bundle.spells.get(spell_id)
    return spell


def check_spell_picks(
    bundle: ContentBundle,
    classes: Mapping[str, ClassLevel],
    cantrips: Mapping[str, Sequence[str]] | None = None,
    prepared: Mapping[str, Sequence[str]] | None = None,
    locale: str = "zh",
) -> list[str]:
    """校验「已知戏法 / 准备法术」，返回问题清单（空 = 通过）。

    为什么不在 `Profile` 里校验：配额（`max_cantrips` / `max_prepared` / 最高环位）
    全都来自 `ClassDef` 的表，模型层看不到内容。放在这里，界面与建角色共用一份规则，
    也就不会出现「界面允许选、结算时爆掉」。
    """
    problems: list[str] = []
    tables = (
        ("戏法", cantrips or {}, True),
        ("准备法术", prepared or {}, False),
    )
    for label, picks, is_cantrip in tables:
        for class_id, spell_ids in picks.items():
            class_level = classes.get(class_id)
            if class_level is None:
                problems.append("%s 里的职业 %s 不在角色档案中" % (label, class_id))
                continue
            class_def = bundle.classes.get(class_id)
            if class_def is None:
                problems.append("内容里没有职业 %s" % class_id)
                continue
            if not class_def.casting_ability:
                problems.append("%s（%s）不是施法职业，不该有%s"
                                % (class_def.name.get(locale), class_id, label))
                continue
            items = list(spell_ids)
            if len(set(items)) != len(items):
                duplicates = sorted({item for item in items if items.count(item) > 1})
                problems.append("%s里有重复法术：%s" % (label, "、".join(duplicates)))
                continue
            quota = (max_cantrips(class_def, class_level) if is_cantrip
                     else max_prepared(class_def, class_level))
            if len(items) > quota:
                problems.append("%s超出上限：选了 %d 个，上限 %d"
                                % (label, len(items), quota))
            allowed = set(bundle.spell_list(class_id))
            top = highest_slot_table(class_def, class_level)
            for spell_id in items:
                spell = _spell_of(bundle, spell_id)
                if spell is None:
                    problems.append("%s里的 %s 不存在" % (label, spell_id))
                    continue
                if spell.id not in allowed:
                    problems.append("%s不在 %s 的法术表里" % (spell.name.get(locale),
                                                         class_def.name.get(locale)))
                    continue
                if is_cantrip and int(spell.level) != 0:
                    problems.append("%s 不是戏法（%d 环），不能放进已知戏法"
                                    % (spell.name.get(locale), int(spell.level)))
                elif not is_cantrip:
                    if int(spell.level) == 0:
                        problems.append("%s 是戏法，不能准备" % spell.name.get(locale))
                    elif int(spell.level) > top:
                        problems.append("%s 是 %d 环，当前最高只有 %d 环"
                                        % (spell.name.get(locale), int(spell.level), top))
    return problems


def casting_summary(
    bundle: ContentBundle,
    actor: Actor,
    class_id: str,
    class_level: ClassLevel,
    resolver: Resolver,
    locale: str = "zh",
) -> dict:
    """给界面用的一块数据：DC、攻击加值、法位、上限、可选法术、已选了什么。"""
    class_def = bundle.class_def(class_id)
    ability = casting_ability(class_def)
    dc = spell_dc(resolver, actor, ability)
    attack = spell_attack_bonus(resolver, actor, ability)
    spells = spell_options(bundle, actor, class_id, class_level)
    cantrips = cantrip_options(bundle, class_id)
    profile = actor.profile
    chosen_cantrips = profile.cantrips_of(class_id) if profile else ()
    chosen_spells = profile.spells_of(class_id) if profile else ()
    cap_cantrip = max_cantrips(class_def, class_level)
    cap_prepared = max_prepared(class_def, class_level)

    def _row(spell_id: str) -> dict:
        spell = bundle.spells.get(spell_id)
        return {"id": spell_id, "level": int(spell.level) if spell else 0,
                "name": spell.name.get(locale) if spell else spell_id}

    return {
        "class": class_id,
        "ability": ability,
        "dc": {"total": dc.total, "detail": dc.describe()},
        "attack": {"total": attack.total, "detail": attack.describe()},
        "slots": slot_rows(actor, class_id, locale),
        "highest_slot": highest_slot(actor, class_id),
        "cantrips": {"max": cap_cantrip,
                     "chosen": [_row(item) for item in chosen_cantrips],
                     "remaining": max(0, cap_cantrip - len(chosen_cantrips)),
                     "options": [item.to_dict(locale) for item in cantrips]},
        "prepared": {"max": cap_prepared,
                     "chosen": [_row(item) for item in chosen_spells],
                     "remaining": max(0, cap_prepared - len(chosen_spells)),
                     "options": [item.to_dict(locale) for item in spells]},
    }


def spell_detail(bundle: ContentBundle, spell_id: str,
                 locale: str = "zh", character_level: int | None = None) -> dict:
    """单条法术的展示数据（含该环位的伤害骰式）。

    给了 `character_level` 才有戏法成长 —— 5 / 11 / 17 级的档位看的是**角色等级**，
    不是环位。没给的场合（法术目录、未经角色上下文的查询）宁可返回空，
    也不要按「1 级角色」给一个会骗人的骰式。
    """
    spell = bundle.spell(spell_id)
    data = spell.to_dict(locale)
    data["damage_at_base"] = spell.damage_at(int(spell.level))
    data["summons"] = _summon_rows(bundle, spell, locale)
    if character_level is None:
        return data
    now = spell.scaling_at(int(character_level))
    data["character_level"] = int(character_level)
    data["scaling_now"] = now
    # 只有「伤害骰被替换」这一类才改基础伤害；光束数 / 射程 / 武器骰是别的东西，
    # 硬塞进 damage 会让「多道光束的法术 = 一颗更大的骰子」这种错读法成立。
    data["damage_now"] = now if (now and spell.scaling_kind == "damage") \
        else data["damage_at_base"]
    return data


def _summon_rows(bundle: ContentBundle, spell: SpellDef, locale: str) -> list[dict]:
    """这个法术召出的生物，各在**基础环**下的样子 + 升环曲线。

    基础环取法术自己的环级。曲线从基础环到 9 环，界面据此说明「升环会变多强」；
    有一格算不出来（比如按体型分叉却没指定体型）就跳过那一格 —— 不能因为界面上
    想画一条曲线，就让整条法术详情炸掉。

    `caster_mod` 传 0：这里是**没有角色上下文**的查询，法术属性调整值是多少取决于
    谁在施法。需要真数的场合（战斗结算）走 `api.summon_info(...)`，那里能拿到角色。
    """
    base = max(1, int(spell.level))
    rows = []
    for summon in bundle.summons_for_spell(spell.id):
        # 按体型分叉的那只（活化物件）拿「中型」当默认行；真正的用法是让玩家按物件
        # 体型选，`hp_by_size` 与 `by_slot` 都一并带出去，界面列出全部选项。
        size = "medium" if summon.hp_by_size else ""
        card = summon.card(base, locale, 0, size)
        rows.append({
            "card": card,
            "size_note": summon.size_note.get(locale) if summon.size_note else "",
            "hp_by_size": dict(summon.hp_by_size) if summon.hp_by_size else {},
            "by_slot": slot_curve(summon, base, locale, 0, size),
        })
    return rows


__all__ = [
    "casting_ability", "spell_dc", "spell_attack_bonus", "max_cantrips",
    "max_prepared", "highest_slot", "highest_slot_table", "check_spell_picks",
    "spell_options", "cantrip_options", "free_cast_pool",
    "slot_rows", "casting_summary", "spell_detail",
]
