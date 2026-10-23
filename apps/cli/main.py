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
        feats=tuple(getattr(args, "feat", None) or ()),
        choices=_choices(getattr(args, "pick", None)),
    )


def _choices(pairs) -> dict[str, list[str]]:
    """`--pick <key>=a,b` → {key: [a, b]}。重复的键按出现顺序拼起来。"""
    found: dict[str, list[str]] = {}
    for raw in pairs or ():
        key, _, value = raw.partition("=")
        if not key or not value:
            raise SystemExit("--pick 的写法是 <key>=<a,b,...>，实际：%r" % raw)
        found.setdefault(key.strip(), []).extend(
            [item.strip() for item in value.split(",") if item.strip()])
    return found


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


def cmd_spells(args) -> int:
    """法术目录：默认只列一个职业一档环，免得刷屏。"""
    bundle = api.load_content(args.root)
    catalog = api.spell_catalog(bundle, args.cls or None, args.level, locale=args.lang)
    print("%s 共 %d 条" % (
        "%s 第 %s 环" % (args.cls or "全部职业", "全部" if args.level is None else args.level),
        catalog["count"]))
    for row in catalog["spells"]:
        marks = "".join(["C" if row["concentration"] else "", "R" if row["ritual"] else ""])
        print("  %d %-12s %-42s %-28s %s"
              % (row["level"], row["school"], row["id"], row["name"], marks))
    return 0


def cmd_spell(args) -> int:
    bundle = api.load_content(args.root)
    data = api.spell_info(bundle, args.spell, locale=args.lang)
    print("%s（%s）" % (data["name"], data["id"]))
    print("环级 %d · %s · %s" % (data["level"], data["school"],
                                "专注" if data["concentration"] else "非专注"))
    print("施法 %s · 距离 %s · 持续 %s · 成分 %s"
          % (data["cast"]["text"], data["range"]["text"], data["duration"]["text"],
             "/".join(item.upper() for item in data["components"])))
    if data["save"]:
        print("豁免 %s" % data["save"].upper())
    if data["attack"]:
        print("法术攻击：%s" % data["attack"])
    if data["area"]:
        print("范围 %s %d 尺" % (data["area"]["shape"], data["area"]["feet"]))
    if data["damage"]:
        print("伤害 %s（%s）" % (data["damage_at_base"], data["damage_type"]))
    print(data["text"])
    return 0


def cmd_cast(args) -> int:
    """掷一次施法结算。目标由命令行给（AC / 豁免加值 / 抗性），不需要建怪物。

    这是「没有战斗面板时也真的能用」的那条路：DM 手上有哥布林的 AC 与豁免，
    敲进来就能算出这一发打掉多少 —— 而不是看着法术页自己心算。
    """
    bundle, actor = _character(args)
    saves = {}
    for raw in args.save or ():
        key, _, value = raw.partition("=")
        key = key.strip().lower()
        if not key or not value.strip():
            raise SystemExit("--save 的写法是 <属性>=<加值>，实际：%r" % raw)
        saves[key] = int(value)
    target = api.Target(
        label=args.target,
        ac=args.ac,
        saves=saves,
        resistances=frozenset(item.strip().lower()
                             for item in (args.resist or "").split(",") if item.strip()),
        immunities=frozenset(item.strip().lower()
                             for item in (args.immune or "").split(",") if item.strip()),
    )
    report = api.roll_spell(
        actor, bundle, args.spell, args.slot, [target],
        locale=args.lang, class_id=args.cast_as or "", apply=args.apply,
        seed=args.seed, free=args.free,
    )
    casting = report["casting"]
    if not args.free:
        # 有免费次数却不知道是这类最好查的浪费 —— 直接把提示打在结算前面
        spare = [row for row in api.free_casts(actor, bundle, args.lang)
                 if row["spell"] == args.spell and row["left"] > 0]
        if spare:
            print("提示：《%s》还有 %d 次免法术位施放（加 --free 用它）"
                  % (spare[0]["name"], spare[0]["left"]))
    holder = (casting["class"] or casting["source"] or "?").rsplit(".", 1)[-1]
    kind_note = "免费施放" if report["free"] else ""
    print("%s（%d 环，用 %s 施放%s）"
          % (report["spell"]["name"], report["slot"], holder,
             "，" + kind_note if kind_note else ""))
    free = report["free"]
    if free:
        print("免费施放次数 %d/%d%s"
              % (free["left"], free["capacity"],
                 "" if free["spent"] else "（预览：未扣除，加 --apply 才记账）"))
    print("法术 DC %d%s · 法术攻击 +%d%s"
          % (casting["dc"], _detail(casting["dc_detail"], casting["dc"]),
             casting["attack"], _detail(casting["attack_detail"], casting["attack"])))
    print("骰式 %s%s" % (report["dice"] or "—",
                        "（%s）" % report["damage_type"] if report["damage_type"] else ""))
    print()
    for row in report["rows"]:
        if row["kind"] == "none":
            print("%s：%s" % (row["target"], row["note"]))
            continue
        shot = "第 %d 道 " % row["shot"] if report["shots"] > 1 else ""
        print("%s%s：d20 %d + %d = %d vs %s %d → %s"
              % (shot, row["target"], row["die"], row["bonus"],
                 row["die"] + row["bonus"], row["against"], row["target_number"],
                 _OUTCOME_ZH.get(row["outcome"], row["outcome"])))
        if row["damage_dice"]:
            print("    伤害 %s = %d%s → %d%s"
                  % (row["damage_dice"], row["raw"],
                     "（%s）" % _DEFENSE_ZH[row["defense"]] if row["defense"] else "",
                     row["damage"],
                     "（已扣血：%d → %d）" % (row["hp_before"], row["hp_after"])
                     if row["applied"] is not None else ""))
        if row["note"]:
            print("    %s" % row["note"])
    if report["notes"]:
        print()
        for line in report["notes"]:
            print("注：%s" % line)
    if report["total_damage"]:
        print("\n合计伤害 %d" % report["total_damage"])
    return 0


def _detail(text: str, total: int) -> str:
    """明细与合计一样就不重复印（法术 DC 没有加值可拆时 `describe()` 只回一个数）。"""
    return "" if not text or text.strip() == str(total) else "（%s）" % text


_OUTCOME_ZH = {"critical": "重击", "hit": "命中", "miss": "未命中",
               "failed": "豁免失败", "succeeded": "豁免成功",
               "auto": "必中", "none": "不结算"}
_DEFENSE_ZH = {"resistance": "抗性减半", "immunity": "免疫"}


def cmd_feats(args) -> int:
    """专长目录：按类别分组，标出 19 级恩惠这类等级门槛。"""
    bundle = api.load_content(args.root)
    options = api.feat_options(bundle, kind=args.kind or None, locale=args.lang)
    current = None
    labels = {"origin": "起源", "general": "通用",
              "fighting_style": "战斗风格", "epic_boon": "传奇恩惠"}
    for row in options["feats"]:
        if row["kind"] != current:
            current = row["kind"]
            print("%s（%d 条）" % (labels.get(current, current),
                                 len([item for item in options["feats"]
                                      if item["kind"] == current])))
        level = ("L%-2d" % row["level"]) if row["level"] else "  - "
        print("  %-46s %s %s" % (row["id"], level, row["name"]))
    print("共 %d 条" % options["count"])
    return 0


def cmd_feat(args) -> int:
    """看一个专长的完整定义：前提、选择项、静态原语。"""
    bundle = api.load_content(args.root)
    feat = bundle.feat(args.feat)
    data = feat.to_dict(args.lang)
    print("%s（%s）" % (data["name"], data["id"]))
    print("类别 %s · 前提等级 %s · 可重复 %s"
          % (data["kind"], data["level"] or "无", "是" if data["repeatable"] else "否"))
    if data["classes"]:
        print("限定职业 %s" % "、".join(data["classes"]))
    print(data["text"])
    for choice in data["choices"]:
        print("  选择项 %-10s %-14s 选 %d 项  候选 %s"
              % (choice["id"], choice["kind"], choice["count"],
                 "/".join(choice["options"]) or "见规则"))
    for row in data["resources"]:
        print("  资源   %-40s %s/%s%s"
              % (row["id"], row["kind"], row["refresh"],
                 "（按法术各一次）" if row["per_spell"] else ""))
    if data["casting_ability"]:
        print("施法属性 %s（boost = 本专长提升的那项，choose = 玩家选）"
              % data["casting_ability"])
    print("静态能力 %d 条" % data["powers"])
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
    parser.add_argument("--feat", action="append", default=None,
                        help="专长 id，可重复（如 --feat dnd2024.feat.tough）")
    parser.add_argument("--pick", action="append", default=None,
                        help="专长选择项的值：<专长 id>.<选择项>=a,b（可重复）")
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

    feats = sub.add_parser("feats", help="列出专长（可按类别过滤）")
    feats.add_argument("--kind", default=None,
                       choices=["origin", "general", "fighting_style", "epic_boon"])
    feats.add_argument("--root", default="plugins")
    feats.add_argument("--lang", default="zh", choices=["zh", "en"])
    feats.set_defaults(func=cmd_feats)

    feat = sub.add_parser("feat", help="看一个专长的定义")
    feat.add_argument("--feat", required=True)
    feat.add_argument("--root", default="plugins")
    feat.add_argument("--lang", default="zh", choices=["zh", "en"])
    feat.set_defaults(func=cmd_feat)

    spells = sub.add_parser("spells", help="列出法术（可按职业与环级过滤）")
    spells.add_argument("--class", dest="cls", default=None)
    spells.add_argument("--level", type=int, default=None)
    spells.add_argument("--root", default="plugins")
    spells.add_argument("--lang", default="zh", choices=["zh", "en"])
    spells.set_defaults(func=cmd_spells)

    spell = sub.add_parser("spell", help="看一个法术的细节")
    spell.add_argument("--spell", required=True)
    spell.add_argument("--root", default="plugins")
    spell.add_argument("--lang", default="zh", choices=["zh", "en"])
    spell.set_defaults(func=cmd_spell)

    cast = sub.add_parser("cast", help="掷一次施法结算（目标由命令行给）")
    cast.add_argument("--spell", required=True)
    cast.add_argument("--slot", type=int, default=None, help="用几环位施放（缺省按法术自身环级）")
    cast.add_argument("--cast-as", dest="cast_as", default=None,
                      help="兼职时指定用哪个职业施放（决定 DC 与攻击加值）")
    cast.add_argument("--target", default="目标")
    cast.add_argument("--ac", type=int, default=13)
    cast.add_argument("--save", action="append", default=None,
                      help="目标的豁免加值：<属性>=<加值>，可重复（如 --save dex=2）")
    cast.add_argument("--resist", default="", help="伤害抗性，逗号分隔（如 fire,cold）")
    cast.add_argument("--immune", default="", help="伤害免疫，逗号分隔")
    cast.add_argument("--apply", action="store_true", help="真的扣血（缺省只算不落库）")
    cast.add_argument("--free", action="store_true",
                      help="用专长给的那一次免费施放（不消耗法术位，按自身环级结算）")
    cast.add_argument("--seed", type=int, default=None)
    _add_character_args(cast)
    cast.set_defaults(func=cmd_cast)

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
