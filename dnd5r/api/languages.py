# -*- coding: utf-8 -*-
"""语言（G36）的 api 投影：建卡一步的选项 + 卡面一栏。

规则层（`rules/languages`）只认集合与 key；「哪门是通用语」「哪门稀有」
「哪门是职业白给的」全部在这里从内容读出来再拼给人看。

2024 的账目是这么算的（SRD 5.2「Choose Languages」）：

    通用语（自动） + 2 门标准语言（自选） + 职业/特性给的门数

职业给的门数分两种，**不能合并**：

- 固定会的：德鲁伊语、盗贼黑话 —— 走特性的 `grant_proficiency`，建卡后由
  `rules/languages.granted()` 现算；
- 选几门：盗贼 1 门、游侠 2 级 2 门 —— 走 `ClassDef.language_choices`，
  玩家在这一步里挑。

固定会的在建卡前也要显示出来（否则玩家以为漏了），所以 `fixed` 是从
「职业 + 物种到这一级解锁的特性」里预览出来的；建卡后以能力管道为准。
"""

from __future__ import annotations

from typing import Sequence

from ..kernel.text import Text
from ..rules.languages import (
    LANGUAGE_PREFIX, describe, granted, name_of, split_tokens,
)
from ..rules.text import join_list, tr

# 2024：通用语之外还要选两门标准语言
BASIC_LANGUAGE_SLOTS = 2


def _keys_from_powers(powers) -> list[str]:
    """一组特性里 `grant_proficiency: language.*` 的语言 key（保持出现顺序、去重）。"""
    found: list[str] = []
    for power in powers:
        for effect in power.effects:
            for token in getattr(effect, "tokens", ()) or ():
                if token.startswith(LANGUAGE_PREFIX) and "." in token:
                    key = token.split(".", 1)[1]
                    if key not in found:
                        found.append(key)
    return found


def common_key(content) -> str:
    """内容里标记为「每个角色都会」的那门语言（通用语）。没有就返回空串。"""
    for item in getattr(content, "languages", {}).values():
        if item.common:
            return item.key
    return ""


def class_fixed_keys(content, class_id: str, level: int) -> list[str]:
    """该职业到这一级**固定给**的语言 key（不含自选门数）。"""
    class_def = content.classes.get(class_id) if class_id else None
    if class_def is None:
        return []
    return _keys_from_powers(class_def.powers_at(max(1, int(level))))


def species_fixed_keys(content, species_id: str) -> list[str]:
    """物种固定给的语言（2024 的物种都不给，自制内容可能有）。"""
    item = content.species.get(species_id) if species_id else None
    return _keys_from_powers(item.powers) if item is not None else []


def granted_slots(content, class_id: str, level: int) -> int:
    """该职业到这一级给几门**自选**语言。"""
    class_def = content.classes.get(class_id) if class_id else None
    if class_def is None:
        return 0
    return int(class_def.language_choices_at(max(1, int(level))))


def need_of(content, class_id: str, level: int) -> int:
    """这一级一共要选几门（2 门标准 + 职业自选）。"""
    return BASIC_LANGUAGE_SLOTS + granted_slots(content, class_id, level)


def _row(content, key: str, locale: str, extra: dict | None = None) -> dict:
    item = next((row for row in getattr(content, "languages", {}).values()
                 if row.key == key), None)
    row = {"key": key, "name": name_of(content, key, locale),
           "rare": bool(item.rare) if item is not None else False,
           "note": item.note.get(locale) if item is not None and item.note else ""}
    row.update(extra or {})
    return row


def language_options(content, draft, locale: str = "zh") -> dict:
    """建卡「语言」一步的全部数据。界面只负责画，不再自己查内容（C2）。"""
    class_id = str(draft.get("class_id") or "")
    level = int(draft.get("class_level") or 1)
    species_id = str(draft.get("species") or "")

    common = common_key(content)
    fixed = class_fixed_keys(content, class_id, level) + species_fixed_keys(content, species_id)
    taken = {common, *fixed} - {""}
    granted_need = granted_slots(content, class_id, level)
    need = BASIC_LANGUAGE_SLOTS + granted_need

    standard, rare = [], []
    for item in getattr(content, "languages", {}).values():
        if item.key in taken:
            continue
        row = item.to_dict(locale)
        # 标准表保持内容文件里的顺序（= SRD 表的顺序）；稀有表按名称排，方便找
        (rare if item.rare else standard).append(
            {"key": row["key"], "name": row["name"], "rare": row["rare"],
             "note": row["note"]})
    rare.sort(key=lambda row: row["key"])

    picked = [str(item) for item in (draft.get("languages") or ())
              if str(item) not in taken]
    if granted_need:
        hint = tr("通用语自动会；再从标准语言里选 %d 门"
                  "（职业额外给 %d 门，可以选稀有语言）", locale) \
            % (BASIC_LANGUAGE_SLOTS, granted_need)
    else:
        hint = tr("通用语自动会；再从标准语言里选 %d 门", locale) % BASIC_LANGUAGE_SLOTS
    return {
        "common": _row(content, common, locale) if common else None,
        "fixed": [_row(content, key, locale, {"source": "class"}) for key in fixed],
        "need": need,
        "basic_need": BASIC_LANGUAGE_SLOTS,
        "granted_need": granted_need,
        "standard": standard,
        "rare": rare,
        "picked": picked,
        "hint": hint,
    }


def check_draft(content, draft, locale: str = "zh",
                editing: bool = False) -> list[str]:
    """校验草案里的语言选择，返回问题清单。

    `editing=True`（改卡）不查数量：老存档的语言可能一条都没有（G36 之前建的卡），
    拿建卡的额度去卡它，等于「开一次卡就得先把语言补齐」，而那不是改卡要做的事。
    """
    class_id = str(draft.get("class_id") or "")
    level = int(draft.get("class_level") or 1)
    known_keys = {common_key(content)} | set(class_fixed_keys(content, class_id, level)) \
        | set(species_fixed_keys(content, str(draft.get("species") or "")))
    known_keys.discard("")
    # 「已经会」的那些不算玩家选的：通用语由建卡自动补进档案，改卡时
    # `draft_from_actor` 又会把它原样带回来 —— 把它算进名额会让计数永远多 1。
    picked = [str(item) for item in (draft.get("languages") or ())
              if str(item) not in known_keys]
    if not picked:
        return [] if editing else _short(content, draft, 0, locale)
    problems: list[str] = []
    seen: list[str] = []
    for key in picked:
        if key in seen:
            problems.append(tr("同一门语言选了两次：%s", locale) % name_of(content, key, locale))
        seen.append(key)
    unknown = [key for key in picked if not _has(content, key)]
    if unknown:
        problems.append(tr("没有这些语言：%s", locale) % join_list(unknown, locale))
    if editing:
        return problems
    standard_count = sum(1 for key in set(picked)
                         if _has(content, key) and not _is_rare(content, key))
    if standard_count < BASIC_LANGUAGE_SLOTS:
        problems.append(tr("标准语言至少要选 %d 门（现在 %d 门）", locale)
                        % (BASIC_LANGUAGE_SLOTS, standard_count))
    problems.extend(_short(content, draft, len(set(picked)), locale))
    return problems


def _short(content, draft, count: int, locale: str) -> list[str]:
    need = need_of(content, str(draft.get("class_id") or ""),
                   int(draft.get("class_level") or 1))
    if count == need:
        return []
    return [tr("要选 %d 门语言，现在选了 %d 门", locale) % (need, count)]


def _has(content, key: str) -> bool:
    return any(item.key == key for item in getattr(content, "languages", {}).values())


def _is_rare(content, key: str) -> bool:
    return any(item.key == key and item.rare
               for item in getattr(content, "languages", {}).values())


def sheet_languages(content, actor, locale: str = "zh") -> list[dict]:
    """卡面「语言」一栏：排序后带来源（自动 / 职业 / 自选）。"""
    profile = getattr(actor, "profile", None)
    stored = set(profile.languages) if profile is not None else set()
    from_class = granted(content, actor) if actor is not None else set()
    common = common_key(content)
    rows: list[dict] = []
    for key in sorted(stored | from_class):
        if key == common:
            source = "common"
        elif key in from_class:
            source = "class"
        else:
            source = "chosen"
        rows.append({"key": key, "name": name_of(content, key, locale),
                     "source": source})
    # 通用语排最前（卡上一直这么写），其余按来源再按名字
    order = {"common": 0, "class": 1, "chosen": 2}
    rows.sort(key=lambda row: (order.get(row["source"], 9), row["name"]))
    return rows


def languages_text(content, actor, locale: str = "zh") -> str:
    """一行摘要（状态页用）。"""
    rows = sheet_languages(content, actor, locale)
    return describe(content, [row["key"] for row in rows], locale)


def summary_text(content, keys: Sequence[str]) -> Text:
    """双语文案：给规则层/存档这类不选语言的地方用。"""
    return Text.of(describe(content, keys, "zh"), describe(content, keys, "en"))


__all__ = [
    "BASIC_LANGUAGE_SLOTS", "common_key", "class_fixed_keys", "species_fixed_keys",
    "granted_slots", "need_of", "language_options", "check_draft",
    "sheet_languages", "languages_text", "summary_text",
    "LANGUAGE_PREFIX", "split_tokens",
]
