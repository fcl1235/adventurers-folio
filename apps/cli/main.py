# -*- coding: utf-8 -*-
"""无头前端：只通过 dnd5r.api 使用后端（约束 C3）。

用法：
  python -m apps.cli.main version
  python -m apps.cli.main content
  python -m apps.cli.main sheet --class dnd2024.class.fighter --level 5
  python -m apps.cli.main use   --class dnd2024.class.fighter --power dnd2024.class.fighter.second_wind
  python -m apps.cli.main plugins
  python -m apps.cli.main lint
  python -m apps.cli.main golden

`use` 能跑通就说明后端真的独立：整个过程没有一行 UI 代码参与。
"""

from __future__ import annotations

import argparse
import json
import sys

import dnd5r.api as api

DEFAULT_SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


def _scores(args) -> dict[str, int]:
    scores = dict(DEFAULT_SCORES)
    for key in scores:
        value = getattr(args, key, None)
        if value is not None:
            scores[key] = value
    return scores


def _character(args):
    bundle = api.load_content(args.root)
    if bundle.errors:
        for issue in bundle.errors:
            print("[FAIL] 内容：%s" % issue, file=sys.stderr)
    return bundle, api.new_character(
        bundle, args.cls, args.level, _scores(args),
        name_zh=args.zh, name_en=args.en,
    )


def cmd_version(_args) -> int:
    print("dnd5r %s" % api.VERSION)
    return 0


def cmd_content(args) -> int:
    bundle = api.load_content(args.root)
    summary = api.content_summary(bundle, locale=args.lang)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_sheet(args) -> int:
    bundle, actor = _character(args)
    print(json.dumps(api.character_sheet(actor, bundle, locale=args.lang),
                     ensure_ascii=False, indent=2))
    return 0


def cmd_use(args) -> int:
    bundle, actor = _character(args)
    result = api.use_power(actor, bundle, args.power, seed=args.seed, locale=args.lang)
    rows: list[str] = [result["message"]] if result["message"] else []
    for roll in result["rolls"]:
        rows.append("  %s：%d（%s）" % (roll["label"], roll["total"], roll["detail"]))
    print("\n".join(rows) if rows else "（无输出）")
    print("HP %(current)s/%(maximum)s（临时 %(temp)s）" % result["sheet"]["hp"])
    pools = "、".join("%s %d/%d" % (item["id"].split(".")[-1], item["left"], item["max"])
                      for item in result["sheet"]["pools"])
    print("资源 %s" % (pools or "无"))
    return 0 if result["ok"] else 1


def cmd_plugins(args) -> int:
    for row in api.plugin_summary(args.root):
        print("%-18s %-8s %-8s %s" % (row["id"], row["kind"], row["version"], row["name"]))
    return 0


def cmd_lint(_args) -> int:
    from tools.lint_layers import main as lint_main

    return lint_main([])


def cmd_golden(args) -> int:
    from tools.golden import main as golden_main

    argv = ["--root", args.root]
    if args.live:
        argv.append("--live")
    return golden_main(argv)


def _add_character_args(parser) -> None:
    parser.add_argument("--class", dest="cls", default="dnd2024.class.fighter")
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--zh", default="无名冒险者")
    parser.add_argument("--en", default="Unnamed Adventurer")
    parser.add_argument("--lang", default="zh", choices=["zh", "en"])
    parser.add_argument("--root", default="plugins")
    for key in DEFAULT_SCORES:
        parser.add_argument("--" + key, type=int, default=None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dnd5r", description="D&D 5R 规则引擎命令行")
    sub = parser.add_subparsers(dest="command")

    version = sub.add_parser("version", help="版本号")
    version.set_defaults(func=cmd_version)

    content = sub.add_parser("content", help="内容统计")
    content.add_argument("--root", default="plugins")
    content.add_argument("--lang", default="zh", choices=["zh", "en"])
    content.set_defaults(func=cmd_content)

    for name, tip in (("sheet", "输出角色卡（派生值现算）"), ("new", "sheet 的别名")):
        sheet = sub.add_parser(name, help=tip)
        _add_character_args(sheet)
        sheet.set_defaults(func=cmd_sheet)

    use = sub.add_parser("use", help="执行一个主动能力")
    _add_character_args(use)
    use.add_argument("--power", required=True)
    use.add_argument("--seed", type=int, default=None)
    use.set_defaults(func=cmd_use)

    plugins = sub.add_parser("plugins", help="列出插件")
    plugins.add_argument("--root", default="plugins")
    plugins.set_defaults(func=cmd_plugins)

    lint = sub.add_parser("lint", help="跑分层检查")
    lint.set_defaults(func=cmd_lint)

    golden = sub.add_parser("golden", help="新旧内核数值对账")
    golden.add_argument("--root", default="plugins")
    golden.add_argument("--live", action="store_true")
    golden.set_defaults(func=cmd_golden)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
