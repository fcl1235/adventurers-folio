# -*- coding: utf-8 -*-
"""布局审计（桌面前端）—— 只用 reqsize，不显示窗口。

为什么不用「打开窗口看一眼」：那会抢焦点、打断正在用电脑的人（零弹窗铁律）。
`winfo_req*` 不需要映射就能拿到真实需求尺寸，剩下的用分配算术补：

    可用宽 = 窗口最小宽 − 左右 padding
    可用高 = 窗口最小高 − 头部 − 状态栏 − 笔记本标签

审计两件事：每页需求不超过可用区；单元格宽度之和不超出所在栏的预算。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnd5r.api as api                      # noqa: E402
from apps.desktop.app import DesktopApp, WINDOW_MIN   # noqa: E402
from apps.desktop.pages import OverviewPage  # noqa: E402
from apps.desktop.widgets import COL_MID, COL_RIGHT  # noqa: E402

SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
INT_SCORES = {"str": 8, "dex": 14, "con": 14, "int": 17, "wis": 12, "cha": 10}
CASES = [
    ("战士 5", "dnd2024.class.fighter", 5, None, SCORES),
    ("法师 5", "dnd2024.class.wizard", 5, None, INT_SCORES),
    ("德鲁伊 8 · 大地", "dnd2024.class.druid", 8, "dnd2024.subclass.druid.circle_of_the_land", SCORES),
    ("游荡者 3", "dnd2024.class.rogue", 3, None, {"str": 10, "dex": 17, "con": 14,
                                                  "int": 12, "wis": 12, "cha": 10}),
]


def _check_skills(label: str, page: OverviewPage, sheet: dict) -> list[str]:
    """技能表里的数值必须与 sheet 一致 —— 界面不许自己算第二遍。"""
    problems = []
    rows = sheet.get("skills") or []
    if page.skills.row_count != len(rows):
        return ["%s：技能表 %d 行，sheet 是 %d 行"
                % (label, page.skills.row_count, len(rows))]
    for index, row in enumerate(rows):
        shown = page.skills.text(index, 2)
        want = "%+d" % row["total"]
        if shown != want:
            problems.append("%s：技能 %s 显示 %s，sheet 是 %s"
                            % (label, row["name"], shown, want))
    return problems


def main() -> int:
    bundle = api.load_content(ROOT / "plugins")
    if bundle.errors:
        for issue in bundle.errors:
            print("[FAIL] 内容：%s" % issue)
        return 1

    problems: list[str] = []
    for label, class_id, level, subclass, scores in CASES:
        actor = api.new_character(bundle, class_id, level, scores, subclass=subclass)
        app = DesktopApp(bundle, actor, selftest=True)   # withdrawn，永不显示
        try:
            report = app.layout_report()
            avail_w = WINDOW_MIN[0] - 16                   # 左右各 8 的 padding
            avail_h = WINDOW_MIN[1] - app.status.winfo_reqheight() - 40  # 40 = 头部 + 标签条
            for row in report["pages"]:
                width, height = row["req"]
                print("%-14s 页面 %4dx%-4d 可用 %4dx%-4d"
                      % (label, width, height, avail_w, avail_h))
                if width > avail_w:
                    problems.append("%s：宽 %d > 可用 %d（横向溢出，按钮/列会被裁）"
                                    % (label, width, avail_w))
                if height > avail_h:
                    problems.append("%s：高 %d > 可用 %d（纵向溢出）"
                                    % (label, height, avail_h))
            # 列宽预算：**现量**控件的 reqwidth，不按字符数手算（字体一变手算就废）
            page = app.pages[0]
            if isinstance(page, OverviewPage):
                need = page.skills.winfo_reqwidth()
                if need > COL_MID:
                    problems.append("技能表需要 %d px，超过中栏预算 %d" % (need, COL_MID))
                need = page.attacks.winfo_reqwidth()
                if need > COL_RIGHT:
                    problems.append("攻击表需要 %d px，超过右栏预算 %d" % (need, COL_RIGHT))
            if isinstance(page, OverviewPage):
                problems.extend(_check_skills(label, page, app.sheet))
            if app.winfo_ismapped():
                problems.append("%s：窗口被映射了（零弹窗铁律）" % label)
        finally:
            app.destroy()

    if problems:
        for item in problems:
            print("[FAIL] %s" % item)
        return 1
    print("LAYOUT OK —— %d 个角色 × 1 页全部在预算内" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
