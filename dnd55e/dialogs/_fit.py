# -*- coding: utf-8 -*-
"""弹窗尺寸统一处理。

写死 `geometry("WxH")` 的坏处: 内容一多 (比如 88 种野兽形态、九个环位)
请求高度就会超过窗口, pack 到最后的按钮栏被挤到可视区外 —— 用户点不到按钮。
这里统一按 reqsize 给尺寸: 不少于设计下限, 不超出屏幕。
"""
import tkinter as tk


def fit(dlg, min_w=0, min_h=0, max_h=None):
    """把窗口调到「装得下内容」的尺寸, 并记下结果供测试断言。"""
    try:
        dlg.update_idletasks()
        w = max(int(min_w), dlg.winfo_reqwidth() + 4)
        h = max(int(min_h), dlg.winfo_reqheight() + 4)
        w = min(w, dlg.winfo_screenwidth() - 80)
        h = min(h, dlg.winfo_screenheight() - 120)
        if max_h:
            h = min(h, int(max_h))
        dlg._fit_size = (w, h)
        dlg.geometry(f"{w}x{h}")
        return w, h
    except tk.TclError:
        return None


def center_on(dlg, master):
    """在父窗口中央显示 (父窗口不可见时不动, 免得算出负数坐标)。"""
    try:
        master.update_idletasks()
        w, h = getattr(dlg, "_fit_size",
                       (dlg.winfo_reqwidth(), dlg.winfo_reqheight()))
        mw, mh = master.winfo_width(), master.winfo_height()
        if mw <= 1 or mh <= 1:
            return
        x = master.winfo_rootx() + max(0, (mw - w) // 2)
        y = master.winfo_rooty() + max(0, (mh - h) // 2)
        dlg.geometry("+%d+%d" % (x, y))
    except tk.TclError:
        pass
