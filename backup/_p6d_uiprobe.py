# -*- coding: utf-8 -*-
"""P6d 界面探针: 驯兽师原始伙伴面板 / 形态切换 / 掷野兽打击。

用 selftest 模式起一个隐藏窗口, 造一个 5 级 Beast Master, 逐项断言。
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dnd55e_character_builder as cb   # noqa: E402


def check(ok, msg):
    print(("  ✓ " if ok else "  ✗ ") + msg)
    if not ok:
        raise SystemExit("UIPROBE FAILED: " + msg)


def texts(widget):
    out = []
    for w in widget.winfo_children():
        try:
            t = w.cget("text")
            if t:
                out.append(str(t))
        except Exception:
            pass
        out.extend(texts(w))
    return out


def main():
    app = cb.App(selftest=True)
    r = app.rules
    c = cb.Character(r)
    c.class_id, c.background_id, c.species_id = "ranger", "sage", "human"
    c.base_scores = {"STR": 12, "DEX": 16, "CON": 14, "INT": 10, "WIS": 16,
                     "CHA": 8}
    c.bg_bonus = {"mode": "2+1", "plus2": "WIS", "plus1": "DEX"}
    c.skill_prof = {"stealth", "survival", "perception"}
    c.feats = ["Alert"]
    c.level, c.subclass = 5, "Beast Master"
    c.companion_id = "beast-of-the-land"
    c.hp_current = c.hp_max()
    app.set_character(c)
    app.update_idletasks()

    body = app.class_body
    blob = "\n".join(texts(body))
    check("原始伙伴" in blob, "职业页出现原始伙伴面板")
    check("陆行兽" in blob, "面板显示当前形态")
    check("AC 17" in blob or "AC 18" in blob, "面板显示 AC")
    check("野兽打击" in blob, "面板显示野兽打击")

    # 面板不该把职业页撑宽 (滚动区 560)
    check(body.winfo_reqwidth() <= 560,
          f"职业页宽度 {body.winfo_reqwidth()} <= 560")

    # 切换形态
    app._companion_set("飞行兽 Beast of the Sky")
    check(app.char.companion_id == "beast-of-the-sky", "下拉切换形态生效")
    app.update_idletasks()
    check("飞行兽" in "\n".join(texts(app.class_body)), "面板跟随刷新")

    # 掷野兽打击
    app._companion_strike()
    line = app.roll_log.get(0)
    check("野兽打击" in line, "掷骰日志记录野兽打击")
    check("d20=" in line, "日志含攻击骰")
    check("挥砍" in line, "日志含伤害类型")

    # 非驯兽师不显示面板
    c.subclass = "Hunter"
    app.refresh()
    app.update_idletasks()
    check("原始伙伴" not in "\n".join(texts(app.class_body)),
          "非驯兽师不显示伙伴面板")

    print("\nUIPROBE OK — 野兽伙伴面板正常")


if __name__ == "__main__":
    main()
