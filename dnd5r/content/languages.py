# -*- coding: utf-8 -*-
"""语言定义（P17 / G36）。

2024 规则里语言**不再是物种的字段**：建卡时「通用语 + 2 门标准语言自选」，
另有职业与特性给的语言（德鲁伊语、盗贼黑话、游侠的 2 门）。所以这里只有
名称与稀有分类，没有「哪个物种会说什么」——那是 2014 的模型。

id 的最后一段就是 `Profile.languages` 用的 key：`dnd2024.language.elvish`
↔ `language.elvish` ↔ `Profile.languages` 里的 `elvish`。三者对不上就等于
「会这门语言但查不到名字」，所以 `key` 是算出来的，不单独存。

**标准 / 稀有不写在内核常量里**：表是内容，`rare` 是数据。规则层要「只能选
标准语言」时由 api 层把候选集合算好传下去（C1：规则层不认语言名）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..kernel.errors import PluginError
from ..kernel.ids import is_valid
from ..kernel.text import Text


@dataclass(frozen=True)
class LanguageDef:
    """一门语言：名称 + 是否稀有 + 可选的补充说明。

    `note` 目前只有原初语用到（四种方言互通），但它不是装饰 —— 玩家在界面上
    看到「原初语」时必须知道它包含方言，否则会以为要分别学四种。
    """

    id: str
    name: Text
    rare: bool = False
    note: Text | None = None
    # 「每个角色都会这门语言」——2024 只有通用语是。规则层不知道哪个 key 是
    # 通用语（C1），所以这件事只能由内容标记，api 层读它再传给规则层。
    common: bool = False

    def __post_init__(self) -> None:
        if not is_valid(self.id):
            raise PluginError("语言 id 不合规范：%r" % (self.id,))
        if self.common and self.rare:
            raise PluginError("语言 %s 不能既是通用语又是稀有语言" % self.id)

    @property
    def key(self) -> str:
        return self.id.rsplit(".", 1)[-1]

    def to_dict(self, locale: str = "zh") -> dict:
        return {"id": self.id, "key": self.key, "rare": self.rare,
                "common": self.common,
                "name": self.name.get(locale),
                "note": self.note.get(locale) if self.note is not None else ""}


def parse_language(data: Any, source: str = "") -> LanguageDef:
    if not isinstance(data, Mapping):
        raise PluginError("%s 的语言定义必须是映射" % source)
    for key in ("id", "name"):
        if key not in data:
            raise PluginError("%s 的语言定义缺少 %s（%s）"
                              % (source, key, data.get("id", "?")))
    note = data.get("note")
    return LanguageDef(
        id=str(data["id"]),
        name=Text.from_dict(data["name"], where="%s name" % data["id"]),
        rare=bool(data.get("rare", False)),
        common=bool(data.get("common", False)),
        note=Text.from_dict(note, where="%s note" % data["id"]) if note else None,
    )
