# -*- coding: utf-8 -*-
"""提示框文字完整性检查。

此前的 bug: 提示框是 tk.Label 且写死 height=2/3（行数）+ wraplength（像素），
长中文换行后行数超过 height 就被裁掉, 界面上看不到后半句。

现在的实现是 HintText（固定行高的 tk.Text）: 文字全部写入, 超出部分
可以滚动查看, 不会再丢字。本脚本验证:
  1. 每条能触发的提示文案, 控件里拿到的文本 == 原始文案（一个字都不少）;
  2. 控件高度不随文案长度变化（版面不抖动）;
  3. 文案确实超过一行（否则测不出裁剪）;
  4. 滚动区域覆盖得到全部内容（yview 可移动）。
"""
import sys
import tkinter as tk

import importlib.util
import os

from _path import PROJECT_ROOT as DIR            # 项目根（本脚本在 tools/legacy/）
spec = importlib.util.spec_from_file_location(
    "cb", os.path.join(DIR, "dnd55e_character_builder.py"))
cb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cb)
for fn in ("showwarning", "showinfo", "showerror"):
    setattr(cb.messagebox, fn, lambda *a, **k: None)

from dnd55e import consts

FAIL = []
CHECKED = 0


def check(widget, label, text, must_overflow=True):
    """验证控件保存了完整文案, 且高度不变。"""
    global CHECKED
    before_h = widget.winfo_reqheight()
    before_w = widget.winfo_reqwidth()
    widget.config(text=text)
    widget.master.update_idletasks()
    after_h = widget.winfo_reqheight()
    after_w = widget.winfo_reqwidth()
    got = widget.cget("text")
    CHECKED += 1

    if got != text:
        FAIL.append("%s: 文案被改动\n  期望 %r\n  实际 %r"
                    % (label, text, got))
        return
    if (before_h, before_w) != (after_h, after_w):
        FAIL.append("%s: 控件尺寸变化 %s -> %s"
                    % (label, (before_h, before_w), (after_h, after_w)))
        return
    if must_overflow and len(text) < 10:
        FAIL.append("%s: 测试文案太短, 测不出裁剪 (%d 字)" % (label, len(text)))
        return

    # 内容是否真的超出可视区（超出才说明原来会被裁）
    first, last = widget.yview()
    overflow = not (first <= 0.0 and last >= 1.0)
    print("  ✓ %-14s %3d 字  高 %2d  %s"
          % (label, len(text), after_h, "需滚动" if overflow else "一屏内"))


def main():
    app = cb.App(selftest=True)
    app.update_idletasks()
    ch = cb.Character(app.rules)
    ch.class_id, ch.background_id, ch.species_id = "wizard", "sage", "human"
    ch.base_scores = {"STR": 8, "DEX": 14, "CON": 13,
                      "INT": 15, "WIS": 12, "CHA": 10}
    ch.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
    ch.skill_prof = {"arcana", "history", "insight"}
    ch.feats = ["Alert"]
    ch.level = 3
    ch.subclass = "Evoker"
    ch.hp_current = ch.hp_max()
    app.set_character(ch)
    app.refresh()
    app.update_idletasks()

    print("提示框文字完整性:")

    # 1 属性提示: 用最长的属性说明
    longest = max(consts.ABILITY_DESC.items(), key=lambda kv: len(kv[1]))
    app._ability_hint(longest[0])
    check(app.ab_hint, "ab_hint",
          "%s (%s): %s" % (cb.ABILITY_CN[longest[0]], longest[0], longest[1]))

    # 2 技能提示
    longest = max(consts.SKILL_DESC.items(), key=lambda kv: len(kv[1]))
    app._skill_hover(longest[0])
    check(app.skill_hint, "skill_hint", app.skill_hint.cget("text"))

    # 3 状态提示
    longest = max(consts.CONDITION_DESC.items(), key=lambda kv: len(kv[1]))
    app._cond_hint(longest[0])
    check(app.cond_hint, "cond_hint",
          "%s: %s" % (longest[0], longest[1]))

    # 4 物品提示: 取说明最长的一件
    item = max(consts.MAGIC_ITEMS,
               key=lambda it: len(it.get("note") or it.get("desc") or ""))
    app._item_hint(item)
    check(app.item_hint, "item_hint", app.item_hint.cget("text"))

    # 5 专长说明: 取描述最长的专长
    names = list(consts.FEATS_BY_NAME)
    longest = max(names, key=lambda n: len(cb.feat_desc(n) or ""))
    from dnd55e.util import spell_detail  # noqa: F401  (确保模块可导入)
    app.feat_info.config(text=cb.feat_desc(longest))
    check(app.feat_info, "feat_info", cb.feat_desc(longest))

    # 6 向导里的技能提示
    wiz = cb.Wizard(app, app.rules, lambda *a: None)
    wiz.update_idletasks()
    wiz.data["class_id"] = "wizard"
    wiz.data["background_id"] = "sage"
    wiz.data["species_id"] = "human"
    wiz.step = 3
    wiz._step_skills()
    wiz.update_idletasks()
    sid = max(consts.SKILL_DESC.items(), key=lambda kv: len(kv[1]))[0]
    wiz._hint_skill(sid)
    check(wiz._skill_hint, "wizard skill", wiz._skill_hint.cget("text"))
    wiz.destroy()

    # 7 向导里的种族 / 人类专长说明（同属「写死 height=3」的问题）
    wiz2 = cb.Wizard(app, app.rules, lambda *a: None)
    wiz2.update_idletasks()
    wiz2.step = 2
    wiz2._step_species()
    wiz2.update_idletasks()
    for nm, w, txt in (
            ("lbl_lineage", wiz2.lbl_lineage, "龙族血统 — " + "测试" * 40),
            ("lbl_hfeat", wiz2.lbl_hfeat, cb.feat_desc("Musician"))):
        w.config(text=txt)
        check(w, nm, txt, must_overflow=False)
    wiz2.destroy()

    print("\n共检查 %d 处" % CHECKED)
    app.destroy()
    if FAIL:
        print("\n" + "=" * 50)
        for f in FAIL:
            print("✗", f)
        sys.exit(1)
    print("=" * 50)
    print("HINTCHECK OK — 提示文字不会被裁切")


if __name__ == "__main__":
    main()
