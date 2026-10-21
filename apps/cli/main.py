# -*- coding: utf-8 -*-
"""无头前端：只通过 dnd5r.api 使用后端（约束 C3）。

用法：
  python -m apps.cli.main version
  python -m apps.cli.main new --classes fighter:5,wizard:3 --str 16 --dex 14
  python -m apps.cli.main plugins
  python -m apps.cli.main lint
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import dnd5r.api as api

DEFAULT_SCORES = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}


def parse_classes(text: str) -> list[tuple[str, int]]:
    pairs = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise SystemExit("职业写法应为 class:level，例如 fighter:5,wizard:3")
        class_id, _, level = chunk.partition(":")
        pairs.append((class_id.strip(), int(level)))
    if not pairs:
        raise SystemExit("至少要给一个职业")
    return pairs


def cmd_version(_args) -> int:
    print("dnd5r %s" % api.VERSION)
    return 0


def cmd_new(args) -> int:
    scores = dict(DEFAULT_SCORES)
    for key in scores:
        value = getattr(args, key)
        if value is not None:
            scores[key] = value
    actor = api.create_actor(
        name_zh=args.zh,
        name_en=args.en,
        scores=scores,
        classes=parse_classes(args.classes),
        hp_max=args.hp,
    )
    print(json.dumps(api.actor_view(actor, locale=args.lang), ensure_ascii=False, indent=2))
    return 0


def cmd_plugins(args) -> int:
    for row in api.plugin_summary(args.root):
        print("%-18s %-8s %-8s %s" % (row["id"], row["kind"], row["version"], row["name"]))
    return 0


def cmd_lint(_args) -> int:
    from tools.lint_layers import main as lint_main
    return lint_main([])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dnd5r", description="D&D 5R 规则引擎命令行")
    sub = parser.add_subparsers(dest="command")

    version = sub.add_parser("version", help="版本号")
    version.set_defaults(func=cmd_version)

    new = sub.add_parser("new", help="建角色并输出视图")
    new.add_argument("--classes", default="fighter:1")
    new.add_argument("--zh", default="无名冒险者")
    new.add_argument("--en", default="Unnamed Adventurer")
    new.add_argument("--hp", type=int, default=10)
    new.add_argument("--lang", default="zh", choices=["zh", "en"])
    for key in DEFAULT_SCORES:
        new.add_argument("--" + key, type=int, default=None)
    new.set_defaults(func=cmd_new)

    plugins = sub.add_parser("plugins", help="列出插件")
    plugins.add_argument("--root", default="plugins")
    plugins.set_defaults(func=cmd_plugins)

    lint = sub.add_parser("lint", help="跑分层检查")
    lint.set_defaults(func=cmd_lint)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
