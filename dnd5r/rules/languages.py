# -*- coding: utf-8 -*-
"""语言（G36）：2024 的「通用语 + 2 门标准自选」，以及职业/特性给的语言。

2024 与 2014 最大的差别在这里：**语言不是物种的字段**。规则原文是
「你的角色至少会三门语言：通用语，加上两门你掷骰或从标准语言表里挑的语言。
你的职业与其他特性也可能给你语言。」所以：

- 通用语：建卡自动，不占名额；
- 2 门标准语言：玩家自选（标准表 8 项，通用语已经在手上）；
- 职业：德鲁伊固定知德鲁伊语；盗贼固定知盗贼黑话 + 1 门自选；游侠 2 级 2 门自选。

规则层只做三件事，不认任何一种语言的名字（C1）：
1. 把 `language.*` token 从混合 token 里拆出来；
2. 校验玩家选的那几门（重复 / 已会 / 不在可选范围 / 数量）；
3. 拼一句给人看的摘要。

「哪些算标准」「这门语言叫什么」全部来自内容，规则层只拿集合与名字。
"""

from __future__ import annotations

from typing import Iterable, Sequence

from ..kernel.text import Text
from .text import join_list, tr

# 熟练 token 里语言的前缀。`grant_proficiency: language.elvish` →
# `Profile.languages` 里的 `elvish`。
LANGUAGE_PREFIX = "language."


def split_tokens(tokens: Iterable[str]) -> tuple[set[str], set[str]]:
    """混合 token → (语言 key 集合, 其余 token 集合)。"""
    languages: set[str] = set()
    others: set[str] = set()
    for token in tokens:
        if token.startswith(LANGUAGE_PREFIX) and "." in token:
            languages.add(token.split(".", 1)[1])
        else:
            others.add(token)
    return languages, others


def granted(bundle, actor) -> set[str]:
    """角色**已解锁的能力**被动给的语言 key。

    与熟练同一条管道（`grant_proficiency`），只是落在另一个集合里。建卡时
    这些能力的效果不「执行」，所以必须在这里现算，不能指望 `Profile` 里存着。
    """
    from .contributions import available_powers  # 局部 import：避免模块级环

    found: set[str] = set()
    for power in available_powers(bundle, actor):
        for effect in power.effects:
            for token in getattr(effect, "tokens", ()) or ():
                if token.startswith(LANGUAGE_PREFIX) and "." in token:
                    found.add(token.split(".", 1)[1])
    return found


def known(bundle, actor) -> set[str]:
    """这个角色会说的全部语言 key（档案里的 + 能力给的）。"""
    profile = getattr(actor, "profile", None)
    stored = set(profile.languages) if profile is not None else set()
    return stored | granted(bundle, actor)


def name_of(bundle, key: str, locale: str = "zh") -> str:
    """语言显示名。查不到就退回 key —— 编一个名字比露出 key 更难排查。"""
    for item in getattr(bundle, "languages", {}).values():
        if item.key == key:
            return item.name.get(locale)
    return key


def names(bundle, keys: Iterable[str], locale: str = "zh") -> list[str]:
    return [name_of(bundle, key, locale) for key in keys]


def describe(bundle, keys: Iterable[str], locale: str = "zh") -> str:
    """「通用语、精灵语」—— 空集合返回空串。"""
    return join_list(names(bundle, keys, locale), locale)


def check_picks(bundle, picks: Sequence[str], *, known_keys: Iterable[str],
                allowed: Iterable[str], need: int,
                locale: str = "zh") -> list[str]:
    """校验玩家选的这几门语言，返回问题清单（空 = 合法）。

    `allowed` 由调用方算好（建卡自选只能标准语言，职业给的门数可以到稀有）——
    规则层不认「标准/稀有」，那是内容的 `rare` 字段，不是规则词汇。
    """
    problems: list[str] = []
    picked = [str(item) for item in picks]
    already = set(known_keys)
    book = set(allowed)

    seen: list[str] = []
    for key in picked:
        if key in seen:
            problems.append(tr("同一门语言选了两次：%s", locale) % name_of(bundle, key, locale))
        seen.append(key)
    # 已经会的再选一次 = 白占一个名额。注意「重复」与「已会」是两件事：
    # 前者的错在草案里，后者的错在草案与角色之间。
    known_twice = sorted({key for key in picked if key in already})
    if known_twice:
        problems.append(tr("这些语言你已经会了：%s", locale)
                        % join_list(names(bundle, known_twice, locale), locale))
    outside = [key for key in picked if key not in book]
    if outside:
        problems.append(tr("这些语言不在可选范围内：%s", locale)
                        % join_list(names(bundle, outside, locale), locale))
    if len(picked) != int(need):
        problems.append(tr("要选 %d 门语言，现在选了 %d 门", locale)
                        % (int(need), len(picked)))
    return problems


def summary(bundle, keys: Iterable[str]) -> Text:
    """语言一栏的双语文案（规则层输出的句子用 `Text`，不在这里选语言）。"""
    ordered = sorted(set(keys))
    if not ordered:
        return Text.of("无", "None")
    return Text.of(describe(bundle, ordered, "zh"), describe(bundle, ordered, "en"))


__all__ = [
    "LANGUAGE_PREFIX", "split_tokens", "granted", "known", "name_of", "names",
    "describe", "check_picks", "summary",
]
