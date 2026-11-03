# -*- coding: utf-8 -*-
"""界面语言：中文原文当键，英文挂在 `i18n_en` 里。

**为什么用中文原文当键**，而不是 `nav.back` 这种符号键：

  1. 界面文件里已经有六百多处中文，一处一个符号键，键名表本身就成了一门新语言，
     没人记得住 `sheet.fight.resist` 是「抗性」还是「抗性/免疫」；
  2. 漏译时 `T("属性")` 原样返回「属性」—— 界面不会崩、不会出现空白或 `!key!`；
  3. 改文案只要动中文那一处，译文表按中文去对，翻不到就是没译，一查便知；
  4. 译文表可以按页面分组读，审校的时候像看对照表，不像看代码。

代价是「同一句话在不同页面要不同译法」做不到 —— 出现那种情况就在中文里把话说全
（「攻击次数」而不是「次数」），这本来就是好文案该做的事。

三种用法：
    T("上一步")                    原样取译文
    T("%d 级") % level              带格式的短句（英文模板的占位符顺序必须与中文一致）
    Catalog({"str": "力量", ...})   显示用映射表：**取值时**才翻译，改语言立刻生效
"""
from __future__ import annotations

from typing import Any, Iterable

from .i18n_en import EN

LOCALES = ("zh", "en")
# 语言选择器上显示的名字用**各自的语言**写：英文用户找 "English"，
# 中文用户找「中文」，不指望谁会去认 "Chinese" 这个词。
LOCALE_LABEL = {"zh": "中文", "en": "English"}
# 按钮上用**短名**：写目标语言自己的写法（中文用户看到 "EN"，英文用户看到「中文」）。
# 用 LOCALE_LABEL 里的全名不行 —— 「English」七个字符在 4 字符宽的按钮里会被截掉，
# 截成 "Engl…" 比直接写 "EN" 更难认。
LOCALE_SHORT = {"zh": "中文", "en": "EN"}

_LOCALE = "zh"
# 运行时没查到译文的键。测试与 `tools/i18n_audit.py --runtime` 都靠它判定覆盖度：
# **静态能查出来的只是「有没有包 T()」，真正会不会漏译只有跑一遍才知道**
# （动态拼出来的句子、内容包里的名字，静态一个都看不见）。
MISSING: set[str] = set()


def get_locale() -> str:
    return _LOCALE


def system_locale() -> str:
    """系统界面语言 → "zh" / "en"。认不出来就按中文（内容以中文为主）。

    不用 `locale.getlocale()`：Windows 上它经常返回 `(None, None)`，
    宁可问一次 Win32 的 UI 语言。
    """
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "zh" if (lang_id & 0x3FF) == 0x04 else "en"
    except Exception:                 # 非 Windows / 取值失败
        return "zh"


def set_locale(code: str) -> None:
    """切语言。**只改状态**：已经建好的控件不会自己变，界面要整窗重建。"""
    global _LOCALE
    code = str(code or "").lower()
    if code not in LOCALES:
        raise ValueError("不认识的语言：%r" % (code,))
    _LOCALE = code
    MISSING.clear()


def is_zh() -> bool:
    return _LOCALE == "zh"


def T(text: str, *args: Any) -> str:
    """取当前语言的文案。`args` 给了就按 `%` 格式化（占位符顺序与中文一致）。"""
    if not isinstance(text, str):
        return text
    if not text:                  # 空串是「这一格先不写」，不是待译文案
        return text
    if _LOCALE == "zh":
        value = text
    else:
        value = EN.get(text)
        if value is None:
            # 回退中文 + 记账。宁可露出一句中文（用户至少能猜），
            # 也不要露出 "weapon.mastery.topple" 这种内部 id。
            MISSING.add(text)
            value = text
    if args:
        try:
            return value % args
        except (TypeError, ValueError):
            return value          # 译文占位符写错了：给原文，别在界面上抛异常
    return value


def join(items: Iterable[str], sep: str = "、") -> str:
    """连接列表。中文用顿号，英文用 `", "` —— 直接把「、」写进译文表更糟，
    那会让「抗性：火焰、冷冻」在英文里变成 "Fire、Cold"。"""
    return (", " if _LOCALE != "zh" else sep).join(str(item) for item in items)


def sep() -> str:
    return "、" if _LOCALE == "zh" else ", "


def unit(value, zh: str, en: str) -> str:
    """带单位的数字：「60 尺」/ "60 ft."。

    单位不能塞进译文表 —— 「%s 尺」这种模板会让数字也变成待译文本的一部分，
    而尺/磅/金币在很多地方都要拼，漏一处就是中文里夹一个 "ft."。
    """
    return "%s %s" % (value, zh if _LOCALE == "zh" else en)


def ft(value) -> str:
    return unit(value, "尺", "ft.")


def colon() -> str:
    """标签与值的分隔（「抗性：火」对 "Resist: fire"）。"""
    return "：" if _LOCALE == "zh" else ": "


class Catalog(dict):
    """显示用的映射表：**存储中文原文，取值时翻译**。

    这样 `ABILITY_ZH[key]` 这类几十处现有写法一行都不用改，切语言也立刻生效 ——
    如果改成在模块加载时翻译，语言一换表里就全冻在旧语言上了。
    """

    def __getitem__(self, key):
        return T(dict.__getitem__(self, key))

    def get(self, key, default=None):
        try:
            raw = dict.__getitem__(self, key)
        except KeyError:
            return default
        return T(raw)

    def values(self):                       # 只在显示「全部选项」的地方用得到
        return [T(raw) for raw in dict.values(self)]
