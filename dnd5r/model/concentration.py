# -*- coding: utf-8 -*-
"""专注（concentration）：此刻正在专注哪一道法术。

为什么不用 `MarkSet` 里的一条标记：标记是**匿名的一次性加减项**（「下一次攻击
优势」），只需要 kind 与 mode；专注要回答三个标记答不出的问题 ——

  * 在专注**哪一道**法术（名字要能印在卡上）
  * 用**几环**放的（升环的火球与 3 环的火球不是同一件事）
  * 被顶掉的**是哪一个**（开始新专注时必须说出来，不能静默清掉）

而且两者的生命周期不一样：`purge_rest` 清 `rest` 作用域时会把标记一起清掉，
可专注只被**长休**与**受伤豁免失败**打断，短休不断。混在一个集合里，迟早
会有人顺手 `purge("rest")` 把专注也清了。

**名字存在这里**（`name_zh` / `name_en`）：规则层不查内容（与 C1 同一口径），
由上层把 `SpellDef.name` 填进来。存档也只存这份快照 —— 内容将来改了法术名，
读旧档不该因此报错。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..kernel.errors import RuleError

__all__ = ["Concentration", "MAX_SPELL_LEVEL"]

MAX_SPELL_LEVEL = 9


@dataclass
class Concentration:
    """一条专注记录。`slot` 是实际用的环位（升环时大于 `level`），戏法为 0。"""

    spell_id: str
    name_zh: str = ""
    name_en: str = ""
    level: int = 0
    slot: int = 0

    def __post_init__(self) -> None:
        if not str(self.spell_id or "").strip():
            raise RuleError("专注记录必须有法术 id")
        for field_name in ("level", "slot"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise RuleError("%s 必须是整数：%r" % (field_name, value))
            if not 0 <= value <= MAX_SPELL_LEVEL:
                raise RuleError("%s 必须在 0–%d：%r" % (field_name, MAX_SPELL_LEVEL, value))

    def name(self, locale: str = "zh") -> str:
        """显示名。英文缺了就回退中文，再缺回退 id —— 不印一个空引号。"""
        if str(locale or "zh").lower().startswith("en"):
            return self.name_en or self.name_zh or self.spell_id
        return self.name_zh or self.name_en or self.spell_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "spell_id": self.spell_id,
            "name": {"zh": self.name_zh, "en": self.name_en},
            "level": int(self.level),
            "slot": int(self.slot),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Concentration | None":
        """读档用。**坏数据返回 None 而不是抛错**：一条专注记录不值得让整个
        角色打不开 —— 宁可变回「没在专注」，玩家重新放一次就对了。"""
        if not isinstance(data, Mapping):
            return None
        spell_id = str(data.get("spell_id") or "").strip()
        if not spell_id:
            return None
        names = data.get("name") or {}
        if not isinstance(names, Mapping):
            names = {}

        def _int(key: str) -> int:
            try:
                return max(0, min(int(data.get(key) or 0), MAX_SPELL_LEVEL))
            except (TypeError, ValueError):
                return 0

        try:
            return cls(
                spell_id=spell_id,
                name_zh=str(names.get("zh") or ""),
                name_en=str(names.get("en") or ""),
                level=_int("level"), slot=_int("slot"),
            )
        except RuleError:
            return None
