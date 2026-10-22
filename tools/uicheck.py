# -*- coding: utf-8 -*-
"""布局审计（桌面前端）—— 只用 reqsize，不显示窗口。

为什么不用「打开窗口看一眼」：那会抢焦点、打断正在用电脑的人（零弹窗铁律）。
`winfo_req*` 不需要映射就能拿到真实需求尺寸，剩下的用分配算术补：

    可用宽 = 窗口最小宽 − 左右 padding
    可用高 = 窗口最小高 − 头部 − 状态栏 − 笔记本标签

审计三件事：每页需求不超过可用区；单元格宽度不超出所在栏预算；
**页面上显示的数字与 `character_sheet()` 一致**（界面不许自己算第二遍）。
最后一项比尺寸重要：布局塞得下但数字错了，比塞不下更糟。
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
from apps.desktop.pages_feats import FeatPage  # noqa: E402
from apps.desktop.pages_powers import PowersPage  # noqa: E402
from apps.desktop.pages_spells import SpellPage, _chosen_ids  # noqa: E402
from apps.desktop.widgets import COL_MID, COL_RIGHT  # noqa: E402

SCORES = {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}
INT_SCORES = {"str": 8, "dex": 14, "con": 14, "int": 17, "wis": 12, "cha": 10}
# (标签, 职业, 等级, 子职, 属性, 专长)
CASES = [
    ("战士 5", "dnd2024.class.fighter", 5, None, SCORES, ()),
    ("法师 5", "dnd2024.class.wizard", 5, None, INT_SCORES, ()),
    ("德鲁伊 8 · 大地", "dnd2024.class.druid", 8,
     "dnd2024.subclass.druid.circle_of_the_land", SCORES, ()),
    ("游荡者 3", "dnd2024.class.rogue", 3, None,
     {"str": 10, "dex": 17, "con": 14, "int": 12, "wis": 12, "cha": 10}, ()),
    # 专长必须单独跑一档：没有专长的角色会让「专长页」看起来永远是对的
    ("战士 8 · 专长", "dnd2024.class.fighter", 8, None, SCORES,
     ("dnd2024.feat.ability_score_improvement", "dnd2024.feat.skill_expert",
      "dnd2024.feat.alert")),
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


def _check_spells(label: str, page: SpellPage, stats: dict) -> list[str]:
    """法术页：清单行数与候选一致，且**准备/取消真的写得进去**。"""
    problems: list[str] = []
    block = page._block()
    if not block:
        if str(page.pick_button.cget("state")) != "disabled":
            problems.append("%s：不施法却让按钮可点" % label)
        return problems
    for kind, pane in (("cantrips", page.cantrips), ("prepared", page.prepared)):
        options = page._spell_options(kind)
        if pane.row_count != len(options):
            problems.append("%s：%s 清单 %d 行，候选 %d 个"
                            % (label, kind, pane.row_count, len(options)))
        if pane.row_count and not pane.text_at(0).strip():
            problems.append("%s：%s 清单首行是空的（没填数据）" % (label, kind))

    bucket = block.get("prepared") or {}
    if int(bucket.get("remaining") or 0) <= 0:
        return problems                       # 名额已满，来回切换会被规则拒绝
    chosen = _chosen_ids(bucket)
    target = next((row["id"] for row in page._spell_options("prepared")
                   if row["id"] not in chosen), "")
    if not target:
        return problems
    page.prepared.select_id(target)
    if not page.toggle_prepared():
        problems.append("%s：准备法术失败（%s）" % (label, page.status_var.get()))
        return problems
    stats["toggles"] = stats.get("toggles", 0) + 1
    if target not in _chosen_ids(page._block()["prepared"]):
        problems.append("%s：点了准备但档案没变（%s）" % (label, target))
    page.prepared.select_id(target)
    if not page.toggle_prepared():
        problems.append("%s：取消准备失败（%s）" % (label, page.status_var.get()))
    elif target in _chosen_ids(page._block()["prepared"]):
        problems.append("%s：点了取消但档案还留着（%s）" % (label, target))
    return problems


def _check_feats(label: str, page: FeatPage, stats: dict) -> list[str]:
    """专长页：清单与 sheet 一致；选择项真能写进去；诚实标记必须说得清。"""
    problems: list[str] = []
    feats = page._feats
    if page.feats.row_count != len(feats):
        problems.append("%s：专长清单 %d 行，sheet 是 %d 条"
                        % (label, page.feats.row_count, len(feats)))
    for row in feats:
        index = page.feats.index_of(row["id"])
        if index < 0:
            problems.append("%s：清单里找不到专长 %s" % (label, row["id"]))
            continue
        if row["name"] not in page.feats.text_at(index):
            problems.append("%s：专长行没有名字（%s）" % (label, row["id"]))

    choice = page._choice()
    if not choice:
        return problems
    if str(page.add_button.cget("state")) == "disabled" and int(choice["remaining"]) > 0:
        problems.append("%s：还差 %d 项却不让选" % (label, choice["remaining"]))
        return problems
    if int(choice["remaining"]) <= 0:
        return problems

    value = str((choice.get("options") or [""])[0])
    page.options.select_id(value)
    before = list(choice.get("picked") or [])
    if not page.add_pick():
        problems.append("%s：加选择项失败（%s）" % (label, page.status_var.get()))
        return problems
    stats["feat_picks"] = stats.get("feat_picks", 0) + 1
    after = list(page._choice().get("picked") or [])
    if len(after) != len(before) + 1:
        problems.append("%s：点了加上但选择没变（%s → %s）" % (label, before, after))
    if not page.clear_picks():
        problems.append("%s：清空选择项失败（%s）" % (label, page.status_var.get()))
    elif page._choice().get("picked"):
        problems.append("%s：清空后还留着 %s" % (label, page._choice()["picked"]))
    # 诚实标记：四条里必须有一条对得上（不能是空字符串）
    if not page.honesty.text.get("1.0", "end").strip():
        problems.append("%s：专长页没有说明「算没算进数值」" % label)
    return problems


def _check_overview_defense(label: str, page: OverviewPage, sheet: dict) -> list[str]:
    """概览页的抗性/感官/暴击行必须与 sheet 一致（这几行以前根本没显示过）。"""
    problems = []
    rows = {page.fight.label_at(index): page.fight.value_at(index) for index in range(8)}
    want_resist = "、".join(sheet.get("resistances") or []) or "—"
    if rows.get("抗性") != want_resist:
        problems.append("%s：概览抗性 %r，sheet 是 %r" % (label, rows.get("抗性"), want_resist))
    if rows.get("暴击") != "≥ %d" % int((sheet.get("crit") or {}).get("min", 20)):
        problems.append("%s：概览暴击 %r 与 sheet 不一致" % (label, rows.get("暴击")))
    return problems


def _check_pools(label: str, page: PowersPage) -> list[str]:
    """资源池的显示值必须等于 sheet 的「剩余 / 上限」。

    必须在**用掉一次之后**比对才有意义：满的时候 `left == max`，
    写成 `max / max` 也能通过 —— 那种检查等于没检查。
    """
    problems = []
    for index, pool in enumerate(page._pools[:9]):
        shown = page.pools.value_at(index)
        want = "%d / %d" % (pool["left"], pool["max"])
        if shown != want:
            problems.append("%s：资源池「%s」显示 %r，sheet 是 %r"
                            % (label, pool.get("label") or pool["id"], shown, want))
    return problems


def _check_powers(label: str, page: PowersPage, stats: dict) -> list[str]:
    """能力页：资源池/能力清单与 sheet 一致；能用的能力真能点一次。"""
    problems: list[str] = []
    if page.powers.row_count != len(page._powers):
        problems.append("%s：能力清单 %d 行，sheet 是 %d 条"
                        % (label, page.powers.row_count, len(page._powers)))

    usable = [row for row in page._powers if row.get("button") and not row.get("blocked")]
    if not usable:
        if str(page.use_button.cget("state")) == "normal" and page._selected().get("button"):
            problems.append("%s：不可用的能力却让按钮亮着" % label)
        return problems

    row = usable[0]
    page.powers.select_id(row["id"])
    page._power_id = row["id"]
    page._fill_detail()
    before = _pool_left(page, row)
    if not page.use_selected():
        problems.append("%s：使用「%s」失败（%s）" % (label, row["name"], page.status_var.get()))
        return problems
    stats["power_uses"] = stats.get("power_uses", 0) + 1
    after = _pool_left(page, row)
    if before is not None and after is not None and after != before - 1:
        problems.append("%s：用了「%s」但资源没扣（%d → %d）"
                        % (label, row["name"], before, after))
    if not page.report.text.get("1.0", "end").strip():
        problems.append("%s：使用「%s」后没有报告" % (label, row["name"]))
    problems.extend(_check_pools(label, page))
    return problems


def _pool_left(page: PowersPage, row: dict):
    """这次使用该扣哪个池：按能力的 owner 找同前缀的资源池。"""
    owner = str(row.get("owner") or "")
    for pool in page._pools:
        if owner and pool["id"].startswith(owner.rsplit(".", 1)[0]):
            return pool["left"]
    return None


def main() -> int:
    bundle = api.load_content(ROOT / "plugins")
    if bundle.errors:
        for issue in bundle.errors:
            print("[FAIL] 内容：%s" % issue)
        return 1

    problems: list[str] = []
    page_count = 0
    stats: dict = {}
    for label, class_id, level, subclass, scores, feats in CASES:
        actor = api.new_character(bundle, class_id, level, scores,
                                  subclass=subclass, feats=feats)
        app = DesktopApp(bundle, actor, selftest=True)   # withdrawn，永不显示
        try:
            page_count = len(app.pages)
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
            for page in app.pages:
                if isinstance(page, OverviewPage):
                    need = page.skills.winfo_reqwidth()
                    if need > COL_MID:
                        problems.append("技能表需要 %d px，超过中栏预算 %d" % (need, COL_MID))
                    need = page.attacks.winfo_reqwidth()
                    if need > COL_RIGHT:
                        problems.append("攻击表需要 %d px，超过右栏预算 %d" % (need, COL_RIGHT))
                    problems.extend(_check_skills(label, page, app.sheet))
                    problems.extend(_check_overview_defense(label, page, app.sheet))
                elif isinstance(page, SpellPage):
                    problems.extend(_check_spells(label, page, stats))
                elif isinstance(page, FeatPage):
                    problems.extend(_check_feats(label, page, stats))
                elif isinstance(page, PowersPage):
                    problems.extend(_check_powers(label, page, stats))
            if app.winfo_ismapped():
                problems.append("%s：窗口被映射了（零弹窗铁律）" % label)
        finally:
            app.destroy()

    if problems:
        for item in problems:
            print("[FAIL] %s" % item)
        return 1
    print("LAYOUT OK —— %d 个角色 × %d 页全部在预算内；"
          "法术 %d / 专长 %d / 能力 %d 次写库"
          % (len(CASES), page_count, stats.get("toggles", 0),
             stats.get("feat_picks", 0), stats.get("power_uses", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
