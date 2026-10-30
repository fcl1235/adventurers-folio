# -*- coding: utf-8 -*-
"""存档：只写事实，读档只重建（C5）。拆自 P11 之前的巨型 __init__。"""
from __future__ import annotations

from typing import Any, Mapping

from ..content import ContentBundle
from ..kernel.errors import RuleError
from ..model.actor import MAX_EXHAUSTION, Actor
from ..model.death import DeathSaves
from ..model.inventory import Inventory
from ..model.profile import Profile
from ..rules.build import build_from_profile
from ..rules.spellcasting import SLOT_PREFIX

# 2：加了 conditions / exhaustion / death_saves 三段。**读 v1 不迁移**——
# 缺的段一律取默认（没有状态、不力竭、没开始掷死亡豁免），旧档照旧能打开。
SAVE_VERSION = 2

# 旧档的位池 id 前缀（F36 之前位池挂在插件命名空间下）。存档按池 id 记余量，
# 前缀变了不迁移，读档时旧 id 匹配不上池，已用位会静默丢 —— 所以在这里改写。
LEGACY_SLOT_PREFIX = "dnd2024.slot."


def _migrate_pool_id(pool_id: str) -> str:
    if pool_id.startswith(LEGACY_SLOT_PREFIX):
        return SLOT_PREFIX + pool_id[len(LEGACY_SLOT_PREFIX):]
    return pool_id


def save_character(actor: Actor, locale: str = "zh") -> dict:
    """把角色写成可存盘的字典。**只写事实**，派生值一律不写（C5）。

    派生值进档看着省事，读回来就是一包会过期的数字：内容一升级（比如某条
    专长补了 +1），存档里的旧 AC 还在，界面到底信谁？
    """
    profile = actor.profile
    if profile is None:
        raise RuleError("角色没有职业档案，无法存档")
    name = actor.statblock.name
    root = actor.root()
    return {
        "version": SAVE_VERSION,
        "id": actor.id,
        "kind": actor.kind.value,
        "name": {"zh": name.zh, "en": name.en},
        "locale": locale,
        "profile": profile.to_dict(),
        "hp": {"current": int(root.hp.current), "temp": int(root.hp.temp)},
        # 已用数按池 id 记：内容改了池容量也不会读到负数（读档时夹一次）
        "resources": {pool_id: int(pool.used)
                      for pool_id, pool in root.resources.pools.items()},
        # 以下三段是 v2 新增。条件与力竭是**玩家点出来的事实**，不是派生值，
        # 所以必须进档：不存的话「关掉程序回来，状态全没了」比不显示更糟。
        "conditions": list(actor.conditions.ids()),
        "exhaustion": int(root.exhaustion),
        "death_saves": root.death_saves.to_dict(),
        # 背包与装备槽。**v1 漏了这个** —— 穿上锁甲存盘、读回来变回 10 AC，
        # 而且没有任何报错：派生值是现算的，所以「装备没了」只表现为数字变小。
        "inventory": root.inventory.to_dict(),
    }


def load_character(
    content: ContentBundle,
    data: Mapping[str, Any],
    locale: str = "zh",
) -> Actor:
    """从存档重建角色。存档里缺原始属性（旧档）时明确报错，不猜。"""
    version = int(data.get("version") or 0)
    if version > SAVE_VERSION:
        raise RuleError("存档版本 %d 比程序新（支持到 %d），请升级程序"
                        % (version, SAVE_VERSION))
    raw = data.get("profile")
    if not isinstance(raw, Mapping):
        raise RuleError("存档缺少 profile")
    profile = Profile.from_dict(raw)
    name = data.get("name") or {}
    actor = build_from_profile(
        content, profile,
        str(name.get("zh") or "无名角色"),
        str(name.get("en") or "Unnamed"),
        actor_id=str(data.get("id") or "pc.hero"),
    )
    hp = data.get("hp") or {}
    if "current" in hp:
        actor.hp.current = max(0, min(int(hp["current"]), actor.hp.maximum))
    actor.hp.temp = max(0, int(hp.get("temp") or 0))
    for pool_id, used in (data.get("resources") or {}).items():
        pool_id = _migrate_pool_id(str(pool_id))
        if not actor.resources.has(pool_id):
            continue                      # 内容升级后池没了：忽略，别让读档失败
        pool = actor.resources.pools[pool_id]
        amount = min(int(used), pool.capacity)
        if amount > 0:
            pool.spend(amount)
    # v2 段：缺了就是默认值（v1 旧档没有这三段，不该因此读不开）
    for ident in (data.get("conditions") or ()):
        ident = str(ident).strip()
        if ident:
            actor.conditions.add(ident)
    level = data.get("exhaustion") or 0
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 0
    actor.exhaustion = max(0, min(level, MAX_EXHAUSTION))
    actor.death_saves = DeathSaves.from_dict(data.get("death_saves"))
    # v1 存档没有 inventory：读成空背包（那时候也存不下装备，没有可丢的东西）
    raw_gear = data.get("inventory")
    if isinstance(raw_gear, dict):
        actor.inventory = Inventory.from_dict(raw_gear)
    return actor
