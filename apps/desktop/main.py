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

DEFAULT_SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}


def _scores(args) -> dict[str, int]:
    scores = dict(DEFAULT_SCORES)
    for key in scores:
        value = getattr(args, key, None)
        if value is not None:
            scores[key] = value
    return scores


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apps.desktop", description="D&D 2024 角色卡（桌面）")
    parser.add_argument("--root", default="plugins", help="插件目录")
    parser.add_argument("--class", dest="cls", default="dnd2024.class.fighter", help="职业 id")
    parser.add_argument("--level", type=int, default=5, help="职业等级")
    parser.add_argument("--subclass", default=None, help="子职 id")
    parser.add_argument("--feat", action="append", default=[], help="专长 id（可多次）")
    parser.add_argument("--multiclass", action="append", default=[],
                        help="兼职：class_id=level（可多次，如 --multiclass dnd2024.class.wizard=3）")
    parser.add_argument("--name", dest="zh", default="无名冒险者", help="角色名")
    for key in DEFAULT_SCORES:
        parser.add_argument("--%s" % key, type=int, default=None, help="%s 值" % key.upper())
    parser.add_argument("--selftest", action="store_true", help="构建界面后立即退出（不显示窗口）")
    return parser




def _multiclass(pairs):
    """--multiclass class_id=level（可重复）→ [(class_id, level)]。"""
    out = []
    for item in pairs or ():
        ident, _, level = str(item).partition("=")
        if not ident or not level:
            raise SystemExit("--multiclass 要写 class_id=level：%r" % item)
        out.append((ident.strip(), int(level)))
    return tuple(out)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    bundle = api.load_content(args.root)
    for issue in bundle.errors:
        print("[FAIL] 内容：%s" % issue, file=sys.stderr)

    actor = api.new_character(bundle, args.cls, args.level, _scores(args),
                              name_zh=args.zh, subclass=args.subclass,
                              feats=tuple(args.feat),
                              extra_classes=_multiclass(args.multiclass))
    from .app import DesktopApp
    app = DesktopApp(bundle, actor, selftest=args.selftest)
    if args.selftest:
        report = app.layout_report()
        for row in report["pages"]:
            print("页面需要 %dx%d" % row["req"])
        app.destroy()
        return 0
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
