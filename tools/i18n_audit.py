# -*- coding: utf-8 -*-
"""界面文案审计：找出没接进 `T()` 的中文字符串。

为什么要有这个工具：界面上几百处中文散在 17 个文件里，靠肉眼过一遍必然漏。
`grep` 也不行 —— 它分不清「字符串」与注释、文档串，而后两者**不需要**
翻译（注释是给我们自己看的）。所以用 `ast` 只取真正的字符串字面量，
并把模块/类/函数的首条 docstring 排除掉。

判定规则：
  * 字符串里含 CJK（U+4E00–U+9FFF）才算「文案」；
  * 已经被 `T(...)` 包住的算「已接入」—— `T` 的调用参数会被登记；
  * `i18n` 的目录本身（`apps/desktop/i18n.py`）与内容包不走这里。

**接口层另有一套**（`--api`）：`dnd5r/api` 与 `dnd5r/rules` 算出来的句子
（「要选 3 项技能，现在选了 2 项」）界面拿到手时已经填好数，`T()` 按整句
查表永远查不到 —— 所以那边必须在**格式化之前**用 `tr()` 翻模板。两边的
漏网都要查：界面漏了是某块字不翻，接口层漏了是某条报错不翻。

用法：
    python tools/i18n_audit.py             # 界面：报告（退出码非 0 = 有漏网）
    python tools/i18n_audit.py --json      # 给下游脚本用
    python tools/i18n_audit.py --keys      # 列出所有需要译文的键（按文件分组）
    python tools/i18n_audit.py --missing   # 界面译文缺口
    python tools/i18n_audit.py --api       # 接口层：报告没接 tr() 的中文
    python tools/i18n_audit.py --api-missing   # 接口层译文缺口
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CJK = re.compile(r"[\u4e00-\u9fff]")
UI_DIR = PROJECT_ROOT / "apps" / "desktop"
# 接口层两个目录：`api` 负责组装给界面的数据，`rules` 负责校验报错。
API_DIRS = (PROJECT_ROOT / "dnd5r" / "api", PROJECT_ROOT / "dnd5r" / "rules")
# 已经**承诺翻译**的模块（玩家走主流程必然会看到的那几条路：建卡向导、
# 属性生成、背景加值、法术选点、起始装备、升级/改卡）。审计只对这批报错 ——
# 否则工具永远红着，红久了就没人看。
# 剩下的（`rules/attack`、`rules/combat`、`rules/summon` 里的引擎诊断）还是中文：
# 那些是「这一个动作为什么不能做」的技术说明，数量近 400 条，且大量嵌在
# 骰式明细里。它们**不影响界面自身的语言**，只是说明文字还没翻 —— 要加就把
# 模块名写进这里，然后跑 `--api` 看还缺哪些。
API_ADOPTED = {
    "dnd5r/api/wizard.py", "dnd5r/api/origin.py", "dnd5r/api/progress.py",
    "dnd5r/api/languages.py",
    "dnd5r/rules/abilities.py", "dnd5r/rules/spellcasting.py",
    "dnd5r/rules/starting.py",
}
# 这两个文件的「中文」是**数据**不是文案：
#   i18n.py       —— 译文表本身就是中英对照
#   i18n_en.py    —— 英文表
SKIP = {"i18n.py", "i18n_en.py"}
# 接口层的译文表本身
API_SKIP = {"text.py"}

# 显示用映射表：存中文原文，取值时翻译。这些**必须**是「数据」而不是普通文案，
# 因为界面不直接写这些字（写的是 `ABILITY_ZH[key]`）。静态审计放过它们，
# 但运行时有没有译到由 `i18n.MISSING` 兜底（那条才是权威）。
DATA_TABLES = {
    "conditions.py": {"CONDITIONS", "_ZH"},
    # 下面这几张是**表头 / 槽位 / 模式的显示名**：存中文原文，在使用处过 T()
    # （`text=T(title)`、`label = T(label)`）。不能在模块级翻 —— 那会在 import 时
    # 定死成启动语言，切语言后这一批就不动了（踩过）。
    "pages.py": {"SKILL_COLUMNS", "ATTACK_COLUMNS"},
    "pages_gear.py": {"SLOT_ROWS"},
    "pages_encounter.py": {"MODES"},
}

# 接口层同样的「数据表」：存中文原文，由 `tr()` 在**取值时**翻译
# （`tr(item["title"], locale)` / `tr(label, locale)` 里是变量，静态看不见字面量）。
# 它们译没译到由 `probe_en` 的运行时检查兜底。
API_DATA_TABLES = {
    "wizard.py": {"WIZARD_STEPS"},
    "origin.py": {"SCORE_MODE_ZH"},
    # 槽位显示名（起始装备的 `slot_zh`）。**还没翻** —— 与 `api/loadout.py` 的
    # `SLOT_ZH` 是同一批，换装模块整体没纳入，两边要一起改。登记成「数据表」
    # 只是让审计不把它算成漏网；真正译没译由 `probe_en` 的运行时检查说话。
    "starting.py": {"SLOT_ZH"},
}

# 这两个是**名字**不是文案：`name_zh` / `name_en` 各存一份，界面按语言取。
NAME_DEFAULTS = {"无名冒险者", "无名角色"}

# 「暂留中文」标记：字面量所在的源码行带这个注释，审计就跳过它。
# 用它而不是全局白名单，是因为**理由必须写在那一行旁边** —— 白名单会慢慢
# 变成长名单，长到没人再读，最后连「为什么没翻」都不知道。
KEEP_MARK = "i18n-keep"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """所有 docstring 字面量的 id（模块 / 类 / 函数 / 嵌套函数）。"""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            found.add(id(first.value))
    return found


def _wrapped_nodes(tree: ast.AST, names: tuple[str, ...] = ("T", "_T", "t")) -> set[int]:
    """已经在 `T(...)`（或接口层的 `tr(...)`）里的字符串字面量。"""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in names:
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.add(id(arg))
    return found


def _data_nodes(tree: ast.AST, names: set[str]) -> set[int]:
    """`Catalog({...})` 的字典值，以及 `DATA_TABLES` 里点名的变量内容。"""
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if func == "Catalog":
                for arg in node.args:
                    if isinstance(arg, ast.Dict):
                        found |= {id(item) for item in ast.walk(arg)
                                  if isinstance(item, ast.Constant)}
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            hit = False
            for target in targets:
                name = getattr(target, "id", None)
                if name is None and isinstance(target, ast.Subscript):
                    name = getattr(target.value, "id", None)
                if name in names:
                    hit = True
            if hit and node.value is not None:
                found |= {id(item) for item in ast.walk(node.value)
                          if isinstance(item, ast.Constant)}
    return found


def _kept(lines: list[str], lineno: int, end_lineno: int | None = None) -> bool:
    """这条字面量是否标了 `i18n-keep`（标记写在自己这行，或紧邻的上一段注释里）。

    往上扫到**空行为止**：标记总是写在那一段代码的头顶，中间隔一行空行就说明
    那是另一段了。数字窗口不行 —— dict 的第四个别名离标记有五行远。
    """
    stop = max(end_lineno or lineno, lineno)
    if any(KEEP_MARK in text for text in lines[lineno - 1:stop]):
        return True
    index = lineno - 2
    while index >= 0 and lines[index].strip():
        if KEEP_MARK in lines[index]:
            return True
        index -= 1
    return False


def audit_file(path: Path, *, api: bool = False) -> list[dict]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    names = ("tr",) if api else ("T", "_T", "t")
    tables = API_DATA_TABLES if api else DATA_TABLES
    skip = (_docstring_nodes(tree) | _wrapped_nodes(tree, names)
            | _data_nodes(tree, tables.get(path.name, set())))
    lines = source.splitlines()
    rows: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in skip or not CJK.search(node.value):
            continue
        line = node.lineno
        if node.value.strip() in NAME_DEFAULTS:
            continue
        if _kept(lines, node.lineno, getattr(node, "end_lineno", line)):
            continue
        rows.append({
            "file": "%s/%s" % (path.parent.name, path.name) if api else path.name,
            "line": line,
            "text": node.value,
            "context": lines[line - 1].strip() if line <= len(lines) else "",
        })
    rows.sort(key=lambda row: row["line"])
    return rows


def collect() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(UI_DIR.glob("*.py")):
        if path.name in SKIP:
            continue
        rows.extend(audit_file(path))
    return rows


def collect_api() -> list[dict]:
    rows: list[dict] = []
    for folder in API_DIRS:
        for path in sorted(folder.glob("*.py")):
            if path.name in API_SKIP:
                continue
            rows.extend(audit_file(path, api=True))
    return rows


def collect_api_adopted() -> tuple[list[dict], dict[str, int]]:
    """已承诺翻译的模块里的漏网，以及**其余**模块的中文条数（按文件）。"""
    rows: list[dict] = []
    rest: dict[str, int] = {}
    for folder in API_DIRS:
        for path in sorted(folder.glob("*.py")):
            if path.name in API_SKIP:
                continue
            found = audit_file(path, api=True)
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            if rel in API_ADOPTED:
                rows.extend(found)
            elif found:
                rest[rel] = len(found)
    return rows, rest


def collect_keys() -> list[tuple[str, str]]:
    """所有**需要译文的中文串**（已接入 T()/Catalog/数据表的那些），以及所在文件。

    译文表的键就是从这儿来的 —— 手工照界面抄一遍必然会漏，而且抄错了
    运行时只会静默回退成中文。
    """
    found: dict[str, str] = {}
    for path in sorted(UI_DIR.glob("*.py")):
        if path.name in SKIP:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        registered = (_wrapped_nodes(tree) | _data_nodes(tree, DATA_TABLES.get(path.name, set())))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) not in registered or not CJK.search(node.value):
                continue
            found.setdefault(node.value, path.name)
    return sorted(found.items(), key=lambda item: (item[1], item[0]))


def collect_api_keys() -> list[tuple[str, str]]:
    """接口层 `tr()` 里出现过的中文模板（= `rules/text.EN` 该有的键）。"""
    found: dict[str, str] = {}
    for folder in API_DIRS:
        for path in sorted(folder.glob("*.py")):
            if path.name in API_SKIP:
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            registered = (_wrapped_nodes(tree, ("tr",))
                          | _data_nodes(tree, API_DATA_TABLES.get(path.name, set())))
            lines = source.splitlines()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if id(node) not in registered or not CJK.search(node.value):
                    continue
                # 带 i18n-keep 的还没翻（理由写在源码里），不算缺口
                if _kept(lines, node.lineno, getattr(node, "end_lineno", node.lineno)):
                    continue
                found.setdefault(node.value, "%s/%s" % (folder.name, path.name))
    return sorted(found.items(), key=lambda item: (item[1], item[0]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="界面与接口层文案审计")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--keys", action="store_true",
                        help="列出所有需要译文的中文串（按文件分组）")
    parser.add_argument("--missing", action="store_true",
                        help="列出还没有英文译文的条目")
    parser.add_argument("--api", action="store_true",
                        help="查接口层（dnd5r/api、dnd5r/rules）没接 tr() 的中文")
    parser.add_argument("--api-all", action="store_true",
                        help="连未纳入翻译的引擎模块一起列（默认只看已承诺的那几个）")
    parser.add_argument("--api-missing", action="store_true",
                        help="查接口层译文表（rules/text.EN）的缺口")
    args = parser.parse_args(argv)

    if args.keys:
        current = None
        for text, source_file in collect_keys():
            if source_file != current:
                current = source_file
                print("--- %s" % current)
            print(text)
        return 0

    if args.missing:
        sys.path.insert(0, str(PROJECT_ROOT))
        from apps.desktop.i18n_en import EN
        rows = [(text, source) for text, source in collect_keys() if text not in EN]
        for text, source in rows:
            print("%-20s %s" % (source, text.replace("\n", "⏎")[:80]))
        print("缺 %d 条译文" % len(rows))
        return 0 if not rows else 1

    if args.api_missing:
        sys.path.insert(0, str(PROJECT_ROOT))
        from dnd5r.rules.text import EN
        rows = [(text, source) for text, source in collect_api_keys() if text not in EN]
        for text, source in rows:
            print("%-20s %s" % (source, text.replace("\n", "⏎")[:80]))
        print("接口层缺 %d 条译文" % len(rows))
        return 0 if not rows else 1

    if args.api or args.api_all:
        if args.api_all:
            rows, rest = collect_api(), {}
        else:
            rows, rest = collect_api_adopted()
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
            return 0 if not rows else 1
        if rest:
            total = sum(rest.values())
            print("另有 %d 处引擎文案（%d 个模块）暂留中文：%s"
                  % (total, len(rest), "、".join(sorted(rest)[:6])
                     + ("…" if len(rest) > 6 else "")))
        if not rows:
            print("I18N OK　已纳入翻译的接口层文案全部接进 tr()")
            return 0
        print("还有 %d 处接口层中文没接进 tr()：" % len(rows))
        for row in rows:
            print("  %-22s %4d  %s" % (row["file"], row["line"],
                                       row["text"].replace("\n", "⏎")[:70]))
        return 1

    rows = collect()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0 if not rows else 1

    if not rows:
        print("I18N OK　界面文案全部接进 T()")
        return 0

    by_file: dict[str, list[dict]] = {}
    for row in rows:
        by_file.setdefault(row["file"], []).append(row)
    print("还有 %d 处中文没接进 T()：" % len(rows))
    for name in sorted(by_file, key=lambda key: -len(by_file[key])):
        items = by_file[name]
        print("  %-22s %3d" % (name, len(items)))
        for row in items:
            print("      %4d  %s" % (row["line"], row["text"].replace("\n", "⏎")[:70]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
