# -*- coding: utf-8 -*-
"""休息门面：把 `rules/rest.py` 的短休 / 长休端到桌面上。

**为什么这一层必须存在**：`rules/rest.py` 在 P15 之后只剩 CLI 壳（`session.py`）
在调，桌面端一次都休息不了。而法术位、职业资源池、生命骰、力竭、`rest` 作用域
标记（诗人灵感）、`dies_at_rest` 效果**全都靠休息刷新** —— 玩家打完一场遭遇战
就永远停在 0 位上，只能重建角色。这不是「少个按钮」，是没有恢复入口。

两件事留在这一层，不下沉到规则：
  * `hit_dies` 映射（class_id → 骰面）从内容里查 —— 规则层只收算好的表；
  * 长休「会发生什么」提前算出来给界面预览（回多少血、几颗骰、几个池），
    按钮旁边就能写清楚，不用点完才知道。
"""

from __future__ import annotations

from ..content import ContentBundle
from ..kernel.rng import Rng
from ..model.actor import Actor
from ..model.resources import Refresh
from ..rules.rest import RestResult, long_rest, short_rest
from ..rules.text import tr

__all__ = ["hit_dies_for", "rest_options", "take_short_rest", "take_long_rest"]


def hit_dies_for(actor: Actor, content: ContentBundle) -> dict[str, int]:
    """class_id → 生命骰面。兼职按各自骰面，顺序跟 `profile.classes` 一致。"""
    profile = actor.root().profile
    found: dict[str, int] = {}
    if profile is None:
        return found
    for entry in profile.classes:
        class_def = content.classes.get(entry.class_id)
        if class_def is not None:
            found[entry.class_id] = class_def.hit_die
    return found


def _dice_rows(actor: Actor, content: ContentBundle, locale: str) -> list[dict]:
    """每个职业一条：骰面、还剩几颗、共有几颗。

    生命骰池的 id 是 `hit_dice.<class_id>`，由 `rules/build.py` 建。
    池可能不存在（旧档 / 手搓的 Actor），那就报 0 而不是崩 —— 界面上写
    「0 / 0」比一个异常好懂。
    """
    root = actor.root()
    profile = root.profile
    if profile is None:
        return []
    rows: list[dict] = []
    for entry in profile.classes:
        class_def = content.classes.get(entry.class_id)
        pool_id = "hit_dice.%s" % entry.class_id
        pool = root.resources.get(pool_id) if root.resources.has(pool_id) else None
        rows.append({
            "id": entry.class_id,
            "name": (class_def.name.get(locale) if class_def is not None
                     else entry.class_id),
            "sides": int(class_def.hit_die) if class_def is not None else 0,
            "left": int(pool.available) if pool is not None else 0,
            "max": int(pool.capacity) if pool is not None else 0,
        })
    return rows


def rest_options(actor: Actor, content: ContentBundle, locale: str = "zh") -> dict:
    """休息区要用的数字：剩几颗生命骰、长休会恢复什么、短休有没有意义。

    界面**不自己判规则**：短休「还能不能恢复」在引擎里是两件事 —— 有生命骰，
    或者有短休池 / `recover_on_short_rest` 的池没满（战士回气不需要花骰）。
    写在这里，界面照抄。
    """
    root = actor.root()
    rows = _dice_rows(actor, content, locale)
    hp = root.hp
    pools_dry = 0
    short_useful = False
    for pool in root.resources.pools.values():
        if pool.refresh is Refresh.NONE:
            continue
        if pool.used:
            pools_dry += 1
            # 短休「有意义」= 有短休池（回气）或写着 `recover_on_short_rest` 的池
            if pool.refresh is Refresh.SHORT_REST or pool.recover_on_short_rest:
                short_useful = True
    dice_left = sum(row["left"] for row in rows)
    return {
        "dice_left": dice_left,
        "dice_max": sum(row["max"] for row in rows),
        "classes": rows,
        "hp": {"current": int(hp.current), "maximum": int(hp.maximum),
               "temp": int(hp.temp)},
        "long_rest": {
            "heal": max(0, int(hp.maximum) - int(hp.current)),
            "dice": sum(row["max"] - row["left"] for row in rows),
            "pools": pools_dry,
        },
        "can_short": bool(dice_left) or short_useful,
    }


def _display_names(actor: Actor, content: ContentBundle, locale: str) -> dict[str, str]:
    """职业 id / 资源池 id → 显示名。

    规则层不查内容（`rules/rest.py::_display` 只认传进来的表），所以「战士」
    与「回气」这两个名字必须在这一层拼好 —— 否则中文界面上休息记录会写着
    `fighter 生命骰 ×2`、`second_wind +1`，玩家看不懂那是什么。
    """
    root = actor.root()
    names: dict[str, str] = {}
    profile = root.profile
    if profile is not None:
        for entry in profile.classes:
            class_def = content.classes.get(entry.class_id)
            if class_def is not None:
                name = class_def.name.get(locale)
                names[entry.class_id] = name
                # 生命骰池的 id 是 `hit_dice.<class_id>`，长休的「生命骰全回」
                # 报的是池 id —— 不补这一条就会显示 `fighter` 而不是「战士」。
                names["hit_dice.%s" % entry.class_id] = name
    for pool in root.resources.pools.values():
        if pool.label:
            names[pool.id] = pool.label.get(locale)
    return names


def _report(result: RestResult, actor: Actor, locale: str) -> dict:
    """统一形状：界面只读这个，不去摸 `RestResult`（C3：页面不 import 规则对象）。"""
    root = actor.root()
    return {
        "ok": True,
        "kind": result.kind,
        "kind_name": tr("长休" if result.kind == "long_rest" else "短休", locale),
        "hp": {"before": int(result.hp_before), "after": int(result.hp_after),
               "maximum": int(root.hp.maximum)},
        "dice_spent": int(result.dice_spent),
        "healed": int(result.healed),
        "pools": list(result.pools),
        "expired": list(result.expired),
        "lines": list(result.lines),
        "summary": result.summary,
    }


def take_short_rest(
    actor: Actor,
    content: ContentBundle,
    spend: int = 0,
    rng: Rng | None = None,
    locale: str = "zh",
) -> dict:
    """短休。`spend` 超过剩余骰数时按剩余算（规则层截断，这里不重复判）。"""
    result = short_rest(actor, hit_dies_for(actor, content), spend=spend,
                        rng=rng, locale=locale,
                        names=_display_names(actor, content, locale))
    return _report(result, actor, locale)


def take_long_rest(actor: Actor, content: ContentBundle | None = None,
                   locale: str = "zh") -> dict:
    """长休：HP 与临时 HP 归位、生命骰全回、非 NONE 池回满、`rest` 标记清空。

    `content` 只用来把职业 / 资源池显示名翻成当前语言；给 `None` 也能跑
    （退回 id 尾段），这样只关心数值的调用方不必装一份内容包。
    """
    names = _display_names(actor, content, locale) if content is not None else None
    return _report(long_rest(actor, locale=locale, names=names), actor, locale)
