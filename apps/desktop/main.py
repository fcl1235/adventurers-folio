# -*- coding: utf-8 -*-
"""桌面入口。

  python -m apps.desktop.main
  python -m apps.desktop.main --class dnd2024.class.druid --level 8 --subclass dnd2024.subclass.druid.land
  python -m apps.desktop.main --selftest        # 建界面、量尺寸、退出（窗口不显示）

`--selftest` 是给 `tools/uicheck.py` 与回归脚本用的：它构建真实控件树并跑一次
`refresh()`，但窗口全程 withdraw —— 不会抢焦点，也不会在主循环里挂着。
"""

from __future__ import annotations

import argparse
import sys

import dnd5r.api as api
from .i18n import LOCALES, T, set_locale, system_locale

DEFAULT_SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


def _preset_locale(argv) -> None:
    """先扫一遍 `--lang`，把语言定下来 —— 帮助文本是 build_parser 时求值的，
    等 argparse 解析完再切就晚了。认不出来就用系统语言。"""
    items = list(argv if argv is not None else sys.argv[1:])
    code = None
    for index, item in enumerate(items):
        if item == "--lang" and index + 1 < len(items):
            code = items[index + 1]
        elif item.startswith("--lang="):
            code = item.split("=", 1)[1]
    set_locale(code if code in LOCALES else system_locale())


def _scores(args) -> dict[str, int]:
    scores = dict(DEFAULT_SCORES)
    for key in scores:
        value = getattr(args, key, None)
        if value is not None:
            scores[key] = value
    return scores


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apps.desktop", description=T("冒险者手帖 · 5R 角色卡（桌面）"))
    parser.add_argument("--root", default="plugins", help=T("插件目录"))
    parser.add_argument("--class", dest="cls", default="dnd2024.class.fighter", help=T("职业 id"))
    parser.add_argument("--level", type=int, default=5, help=T("职业等级"))
    parser.add_argument("--subclass", default=None, help=T("子职 id"))
    parser.add_argument("--feat", action="append", default=[], help=T("专长 id（可多次）"))
    parser.add_argument("--multiclass", action="append", default=[],
                        help=T("兼职：class_id=level（可多次，如 --multiclass dnd2024.class.wizard=3）"))
    parser.add_argument("--name", dest="zh", default=T("无名冒险者"), help=T("角色名"))
    for key in DEFAULT_SCORES:
        parser.add_argument("--%s" % key, type=int, default=None, help=T("%s 值") % key.upper())
    parser.add_argument("--selftest", action="store_true", help=T("构建界面后立即退出（不显示窗口）"))
    parser.add_argument("--lang", choices=list(LOCALES), default=None,
                        help=T("界面语言（默认跟随系统，也可以点界面上的语言按钮切）"))
    return parser




def _multiclass(pairs):
    """--multiclass class_id=level（可重复）→ [(class_id, level)]。"""
    out = []
    for item in pairs or ():
        ident, _, level = str(item).partition("=")
        if not ident or not level:
            raise SystemExit(T("--multiclass 要写 class_id=level：%r") % item)
        out.append((ident.strip(), int(level)))
    return tuple(out)


def main(argv=None) -> int:
    _preset_locale(argv)
    args = build_parser().parse_args(argv)
    if args.lang:
        set_locale(args.lang)
    bundle = api.load_content(args.root)
    for issue in bundle.errors:
        print(T("[FAIL] 内容：%s") % issue, file=sys.stderr)

    actor = api.new_character(bundle, args.cls, args.level, _scores(args),
                              name_zh=args.zh, subclass=args.subclass,
                              feats=tuple(args.feat),
                              extra_classes=_multiclass(args.multiclass))
    from .app import DesktopApp
    app = DesktopApp(bundle, actor, locale=args.lang, selftest=args.selftest)
    if args.selftest:
        report = app.layout_report()
        for row in report["pages"]:
            print(T("页面需要 %dx%d") % row["req"])
        app.destroy()
        return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
