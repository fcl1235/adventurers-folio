"""把整个窗口的控件树 dump 出来, 用于比对两次构建是否完全一致。

用法: python backup/_p4_widgetdump.py 输出文件.json
"""
import json
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dnd55e_character_builder as cb   # noqa: E402


def attrs(w):
    out = {}
    for k in ("text", "style", "height", "width", "wraplength", "state",
              "padding", "values", "justify", "anchor", "wrap"):
        try:
            v = str(w.cget(k))
        except tk.TclError:
            continue
        if v:
            out[k] = v
    return out


def binds(w):
    out = []
    for seq in w.bind():
        try:
            out.append([seq, w.bind(seq)])
        except tk.TclError:
            pass
    return out


def walk(w, path, acc):
    try:
        cls = w.winfo_class()
    except tk.TclError:
        return
    acc.append({
        "path": path,
        "class": cls,
        "req": [w.winfo_reqwidth(), w.winfo_reqheight()],
        "attrs": attrs(w),
        "binds": binds(w),
    })
    try:
        kids = w.winfo_children()
    except tk.TclError:
        return
    for i, k in enumerate(kids):
        walk(k, "%s/%d:%s" % (path, i, k.winfo_class()), acc)


def main():
    out = sys.argv[1]
    app = cb.App(selftest=True)
    r = app.rules

    c = cb.Character(r)
    c.class_id, c.background_id, c.species_id = "wizard", "sage", "human"
    c.base_scores = {"STR": 8, "DEX": 14, "CON": 13, "INT": 15,
                     "WIS": 12, "CHA": 10}
    c.bg_bonus = {"mode": "2+1", "plus2": "INT", "plus1": "CON"}
    c.skill_prof = {"arcana", "history", "insight"}
    c.feats = ["Alert"]
    c.level = 3
    c.subclass = "Evoker"
    c.hp_current = c.hp_max()
    app.set_character(c)
    app.update_idletasks()

    acc = []
    walk(app, "root", acc)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(acc, f, ensure_ascii=False, indent=1)
    print("dump %d 个控件 -> %s" % (len(acc), out))
    app.destroy()


if __name__ == "__main__":
    main()
