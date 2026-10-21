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
        subclass=getattr(args, "subclass", None),
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
    choice = {"form_id": args.form} if getattr(args, "form", None) else {}
    result = api.use_power(actor, bundle, args.power, seed=args.seed, locale=args.lang,
                           choice=choice)
    rows: list[str] = [result["message"]] if result["message"] else []
    for roll in result["rolls"]:
        rows.append("  %s：%d（%s）" % (roll["label"], roll["total"], roll["detail"]))
    print("\n".join(rows) if rows else "（无输出）")
    print("HP %(current)s/%(maximum)s（临时 %(temp)s）" % result["sheet"]["hp"])
    pools = "、".join("%s %d/%d" % (item["id"].split(".")[-1], item["left"], item["max"])
                      for item in result["sheet"]["pools"])
    print("资源 %s" % (pools or "无"))
    return 0 if result["ok"] else 1


def _cr(value: float) -> str:
    """CR 显示成 1/8 而不是 0.125 —— 桌面上没人说「零点一二五」。"""
    for fraction, label in ((0.125, "1/8"), (0.25, "1/4"), (0.5, "1/2")):
        if abs(float(value) - fraction) < 1e-9:
            return label
    return "%g" % float(value)


def cmd_forms(args) -> int:
    """列出当前等级可选的形态（含被过滤掉的原因）。"""
    bundle, actor = _character(args)
    options = api.form_options(actor, bundle, locale=args.lang)
    if options["class"] is None:
        print("这个职业没有形态轴（不是德鲁伊类的变形职业）")
        return 0
    print("%s 等级 %d：可选 %d 种"
          % (options["class"], options["class_level"], len(options["usable"])))
    for form in options["usable"]:
        print("  %-42s CR %-5s AC %-3d HP %-3d %s"
              % (form["id"], _cr(form["cr"]), form["ac"], form["hp"],
                 " ".join("%s %d" % item for item in form["speeds"].items())))
    if options["blocked"]:
        print("--- 当前不可选 ---")
        for form in options["blocked"]:
            print("  %-42s %s" % (form["id"], "；".join(form["reasons"])))
    return 0


def cmd_subclasses(args) -> int:
    """按职业分组列出子职 —— 建角色时先看这张表。"""
    bundle = api.load_content(args.root)
    options = api.subclass_options(bundle, args.cls or None, locale=args.lang)
    current = None
    for row in options["options"]:
        if row["class"] != current:
            current = row["class"]
            class_def = bundle.classes.get(current)
            label = class_def.name.get(args.lang) if class_def else current
            print("%s（%s）" % (label, current))
        print("  %-48s L%-2d %2d 条  %s"
              % (row["id"], row["unlock_level"], row["powers"], row["name"]))
    if not options["options"]:
        print("这个职业没有子职")
    return 0


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


def _print_view(view) -> None:
    header = view.header
    print("%s  %s  等级 %d" % (header.name, "、".join(header.classes), header.level))
    print("HP %d/%d%s  AC %d  熟练 +%d"
          % (header.hp, header.hp_max,
             "（临时 %d）" % header.temp_hp if header.temp_hp else "",
             header.ac, header.proficiency_bonus))
    if header.conditions:
        print("状态：%s" % "、".join(header.conditions))
    print("--- 卡片 ---")
    for card in view.cards:
        mark = "▶" if card.actions else "·"
        value = (" [%s]" % card.value) if card.value else ""
        print(" %s %-14s %-22s%s  %s" % (mark, card.title, card.subtitle, value, card.tone))
        for line in card.detail:
            print("      %s" % line)
    for card in view.attacks:
        print(" · %-14s %-22s [%s]" % (card.title, card.subtitle, card.value))


def cmd_play(args) -> int:
    """无头剧本：掉血 → 用能力 → 短休 → 长休。每一步都真的跑一遍。"""
    session = api.Session.open(args.root, locale=args.lang, seed=args.seed)
    actor = session.create_character(args.cls, args.level, _scores(args),
                                     name_zh=args.zh, name_en=args.en,
                                     subclass=getattr(args, "subclass", None))
    print("=== 初始 ===")
    _print_view(session.view())

    hit = max(1, actor.hp.maximum // 2)
    print("\n=== 受伤 %d ===" % hit)
    _, report = session.dispatch(api.TakeDamage(hit))
    print(report.message, "→ HP %d/%d" % (actor.hp.current, actor.hp.maximum))

    print("\n=== 使用 %s ===" % args.power)
    choice = {"form_id": args.form} if getattr(args, "form", None) else {}
    view, report = session.dispatch(api.UsePower(args.power, choice))
    print(report.message or "（无输出）")
    print("→ HP %d/%d" % (actor.hp.current, actor.hp.maximum))

    print("\n=== 短休 ===")
    _, report = session.dispatch(api.ShortRest(dice=0))
    print(report.message)

    print("\n=== 新回合后再次使用 ===")
    session.dispatch(api.NewTurn())
    _, report = session.dispatch(api.UsePower(args.power, choice))
    print(("成功：" if report.ok else "被拒绝：") + (report.message or "（无输出）"))

    print("\n=== 长休 ===")
    _, report = session.dispatch(api.LongRest())
    print(report.message)
    print("\n=== 结束 ===")
    _print_view(session.view())
    return 0


def _add_character_args(parser) -> None:
    parser.add_argument("--class", dest="cls", default="dnd2024.class.fighter")
    parser.add_argument("--subclass", default=None, help="子职 id（如 dnd2024.subclass.fighter.champion）")
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
    use.add_argument("--form", default=None, help="变形类能力要选的形态 id")
    use.add_argument("--seed", type=int, default=None)
    use.set_defaults(func=cmd_use)

    subs = sub.add_parser("subclasses", help="列出子职（可按职业过滤）")
    subs.add_argument("--class", dest="cls", default=None)
    subs.add_argument("--root", default="plugins")
    subs.add_argument("--lang", default="zh", choices=["zh", "en"])
    subs.set_defaults(func=cmd_subclasses)

    forms = sub.add_parser("forms", help="列出当前可选形态（德鲁伊）")
    _add_character_args(forms)
    forms.add_argument("--seed", type=int, default=None)
    forms.set_defaults(func=cmd_forms)

    play = sub.add_parser("play", help="无头剧本：掉血 → 用能力 → 短休 → 长休")
    _add_character_args(play)
    play.add_argument("--power", default="dnd2024.class.fighter.second_wind")
    play.add_argument("--form", default=None, help="变形类能力要选的形态 id")
    play.add_argument("--seed", type=int, default=7)
    play.set_defaults(func=cmd_play)

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
