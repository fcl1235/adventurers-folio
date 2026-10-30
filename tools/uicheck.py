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

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dnd5r.api as api                      # noqa: E402
from apps.desktop import theme                    # noqa: E402
from apps.desktop.app import DesktopApp, WINDOW_MIN   # noqa: E402
from apps.desktop.pages import OverviewPage  # noqa: E402
from apps.desktop.pages_encounter import EncounterPage  # noqa: E402
from apps.desktop.pages_feats import FeatPage  # noqa: E402
from apps.desktop.pages_powers import PowersPage  # noqa: E402
from apps.desktop.pages_spells import SpellPage, _chosen_ids  # noqa: E402
from apps.desktop.widgets import COL_MID, COL_RIGHT  # noqa: E402
from dnd5r.kernel.rng import ScriptedRng            # noqa: E402
from dnd5r.model.inventory import EquipSlot         # noqa: E402

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


def _check_appearance(label: str, app, page: OverviewPage, sheet: dict) -> list[str]:
    """外观不是靠肉眼看的：颜色、属性卡、胶囊都要能被断言卡住。

    这几条盯的是「人物卡回归」这件事本身 —— 主题没套上、属性卡没建、
    或者哪个原生控件还留着浅底色，都会在这里红。
    """
    problems: list[str] = []
    if str(app.cget("bg")) != theme.BG:
        problems.append("%s：根窗口底色 %r，不是主题的 %r"
                        % (label, app.cget("bg"), theme.BG))

    # 六张属性卡：数量、调整值、分数、豁免都要与 sheet 一致
    abilities = sheet.get("abilities") or {}
    saves = sheet.get("saves") or {}
    if len(page.ability_cards) != 6:
        problems.append("%s：属性卡 %d 张，应为 6 张"
                        % (label, len(page.ability_cards)))
    for key, card in page.ability_cards.items():
        row = abilities.get(key) or {}
        want_mod = "%+d" % int(row.get("mod", 0))
        if card.mod_text() != want_mod:
            problems.append("%s：%s 调整值显示 %r，应为 %r"
                            % (label, key, card.mod_text(), want_mod))
        want_score = "数值 %d" % int(row.get("score", 0))
        if card.score_text() != want_score:
            problems.append("%s：%s 分数显示 %r，应为 %r"
                            % (label, key, card.score_text(), want_score))
        save = saves.get(key) or {}
        if card.save_text() != "豁免 %+d" % int(save.get("total", 0)):
            problems.append("%s：%s 豁免显示 %r 与 sheet 不一致"
                            % (label, key, card.save_text()))
        if card.save_proficient() != bool(save.get("proficient")):
            problems.append("%s：%s 豁免熟练标记与 sheet 不一致" % (label, key))

    # 5 个胶囊
    perception = next((row["total"] for row in sheet.get("skills", ())
                       if row.get("key") == "perception"), None)
    expect = {
        "ac": str((sheet.get("ac") or {}).get("total", "—")),
        "initiative": "%+d" % (sheet.get("initiative") or {}).get("total", 0),
        "speed": "%d" % (sheet.get("speed") or {}).get("walk", 0),
        "prof": "%+d" % sheet.get("proficiency_bonus", 0),
        "perception": "%+d" % perception if perception is not None else "—",
    }
    for key, want in expect.items():
        chip = app.chips.get(key)
        if chip is None:
            problems.append("%s：缺少 %s 胶囊" % (label, key))
        elif chip.value() != want:
            problems.append("%s：%s 胶囊显示 %r，应为 %r"
                            % (label, key, chip.value(), want))

    # 残留浅底色检查：tk 原生控件不受 ttk 样式管，必须自己配
    dark = {theme.BG, theme.PANEL, theme.CARD, theme.CARD2, theme.TXT_BG,
            theme.MAP_BG}
    for widget in _walk(app):
        if widget.winfo_class() not in ("Canvas", "Text", "Listbox"):
            continue
        try:
            background = str(widget.cget("background")).lower()
        except Exception:
            continue
        if background not in {value.lower() for value in dark}:
            problems.append("%s：%s 用的是浅底色 %s（暗色主题下会很刺眼）"
                            % (label, widget.winfo_class(), background))
    return problems


def _walk(widget):
    """递归遍历控件树（含 ttk 的容器）。"""
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _check_dice(label: str, app, page: OverviewPage, sheet: dict) -> list[str]:
    """掷骰必须真的接到引擎：结果 = d20 + 卡上那个加值，记录也要落地。

    用 `ScriptedRng` 固定骰面，所以这条检查是确定的 —— 不依赖运气。
    """
    problems: list[str] = []
    skill = next((row for row in sheet.get("skills") or () if row.get("key") == "stealth"),
                 (sheet.get("skills") or [None])[0])
    if skill is None:
        return problems
    before = page.dice_log.row_count
    result = app.roll_check("skill", skill["key"], rng=ScriptedRng([10]))
    if result is None:
        problems.append("%s：掷骰失败（状态行：%s）" % (label, app.status.cget("text")))
        return problems
    want = 10 + int(skill["total"])
    if int(result.get("total", 0)) != want:
        problems.append("%s：%s 掷出 %s，应为 d20 10 + 卡面 %d = %d"
                        % (label, skill["name"], result.get("total"),
                           skill["total"], want))
    if page.dice_log.row_count != min(before + 1, 60):
        problems.append("%s：掷骰记录没有新增（%d → %d）"
                        % (label, before, page.dice_log.row_count))
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


def _check_encounter(label: str, page: EncounterPage, stats: dict) -> list[str]:
    """战斗页：清单与候选一致、先攻条与 api 一致、**算的数真落到血上**。

    最后一条是这一页的全部意义。前几页的错只是显示错，这一页的错会让
    玩家把血记错 —— 所以断言「报告里说打了多少，血就少了多少」，
    并且预览与结算分开验（预览动了血比不显示更糟）。
    """
    problems: list[str] = []
    bundle = page.app.bundle
    catalog = api.monster_catalog(bundle)
    if page.roster_pane.row_count != len(catalog):
        problems.append("%s：怪物名单 %d 行，候选 %d 只"
                        % (label, page.roster_pane.row_count, len(catalog)))
        return problems

    # 先给角色一把真武器：法师默认是徒手（1-1 → 0 点），
    # 用徒手来验「血有没有动」等于验了个寂寞。
    page.app.actor.inventory.equip(EquipSlot.MAIN_HAND,
                                   "dnd2024.item.weapon.longsword")
    page.app.refresh()

    page.roster_pane.select_id("dnd2024.monster.wolf")
    if not page.add_monster(rng=ScriptedRng([10])):
        problems.append("%s：加不了怪物（%s）" % (label, page.status_var.get()))
        return problems
    if not page.start(rng=ScriptedRng([20, 5])):
        problems.append("%s：开不了战（%s）" % (label, page.status_var.get()))
        return problems
    stats["encounters"] = stats.get("encounters", 0) + 1

    encounter = page.encounter
    view = api.encounter_view(encounter, bundle)

    def check_bars(stage: str) -> None:
        """先攻条与目标栏的每个数都要等于 api 的当前值。

        必须在**打完一次之后**再跑一遍：满血时 `current == maximum`，
        把 current 写成 maximum 也能通过 —— 那种检查等于没检查（F10 的老坑）。
        """
        fresh = api.encounter_view(encounter, bundle)
        if page.order_pane.row_count != len(fresh["order"]):
            problems.append("%s（%s）：先攻条 %d 行，场上有 %d 人"
                            % (label, stage, page.order_pane.row_count,
                               len(fresh["order"])))
            return
        for index, row in enumerate(fresh["order"]):
            shown = page.order_pane.text_at(index)
            if row["label"] not in shown:
                problems.append("%s（%s）：先攻条第 %d 行没有名字（%r）"
                                % (label, stage, index, shown))
            if "HP %d/%d" % (row["hp"]["current"], row["hp"]["maximum"]) not in shown:
                problems.append("%s（%s）：先攻条第 %d 行血量与 api 不一致（%r，应为 %d/%d）"
                                % (label, stage, index, shown,
                                   row["hp"]["current"], row["hp"]["maximum"]))
            slot = page.target_pane.index_of(row["id"])
            if slot >= 0 and "AC %d" % row["ac"] not in page.target_pane.text_at(slot):
                problems.append("%s（%s）：目标行第 %d 条的 AC 与 api 不一致"
                                % (label, stage, index))

    check_bars("开战")

    page.order_pane.select_id(view["current"])
    page._select_attacker()
    page._attacker_id = view["current"]
    page._fill_targets()
    page._fill_actions()
    if not page.action_pane.row_count:
        problems.append("%s：出手的人没有任何可用动作" % label)
        return problems
    page.action_pane.select_id(page.action_pane.selected_id() or
                               page._action_rows[0]["key"])
    page._select_action()
    if not page.target_pane.row_count:
        problems.append("%s：没有可选目标" % label)
        return problems
    target_id = page._target_id

    def hp_of(ident: str) -> int:
        for row in api.encounter_view(encounter, bundle)["order"]:
            if row["id"] == ident:
                return int(row["hp"]["current"])
        return -1

    # 掷 20 = 必中，且**重击**（伤害骰翻倍）—— 这样「血没动」一定是程序的问题，
    # 不是「刚好掷了个空的」。值给多一点：3d10 翻倍要 6 颗。
    rolls = [20, 2, 2, 2, 2, 2, 2, 2]
    before = hp_of(target_id)
    if not page.roll(False, rng=ScriptedRng(list(rolls))):
        problems.append("%s：预览失败（%s）" % (label, page.status_var.get()))
        return problems
    if hp_of(target_id) != before:
        problems.append("%s：预览就改了血（%d → %d）"
                        % (label, before, hp_of(target_id)))
    if encounter.get(page._attacker_id).economy.action != 1:
        problems.append("%s：预览就把动作额度用掉了" % label)

    if not page.roll(True, rng=ScriptedRng(list(rolls))):
        problems.append("%s：结算失败（%s）" % (label, page.status_var.get()))
        return problems
    stats["attacks"] = stats.get("attacks", 0) + 1
    after = hp_of(target_id)
    reported = page.log.text.get("1.0", "end")
    said = re.findall(r"结果：.*?(\d+) 点伤害", reported)
    if not said:
        problems.append("%s：结算后没有把「结果」写进战斗记录" % label)
    else:
        # 报告说打了多少，血就得少多少 —— 这一页的全部意义就在这一条
        if int(said[-1]) != before - after:
            problems.append("%s：报告说 %s 点伤害，血只少了 %d（%d → %d）"
                            % (label, said[-1], before - after, before, after))
    if not reported.strip():
        problems.append("%s：战斗记录是空的" % label)
    check_bars("打完")

    # 地图：摆位一次，位置要进 api 的视图
    page._mode.set("place")
    page.order_pane.select_id(page._attacker_id)
    page._on_canvas_click(type("E", (), {"x": 80, "y": 120})())
    placed = {row["id"]: (row["x"], row["y"])
              for row in api.encounter_view(encounter, bundle)["order"]}
    if placed.get(page._attacker_id) != (2, 3):
        problems.append("%s：点了 (2,3) 但位置是 %r"
                        % (label, placed.get(page._attacker_id)))

    # 下一回合：当前指针必须换人
    current = api.encounter_view(encounter)["current"]
    if not page.next_turn():
        problems.append("%s：推进回合失败（%s）" % (label, page.status_var.get()))
    elif api.encounter_view(encounter)["current"] == current and len(view["order"]) > 1:
        problems.append("%s：点了下一回合但指针没动" % label)
    return problems


def _check_live_wiring(bundle) -> list[str]:
    """P15 活接线：能力页的选择行、法术页的施放、遭遇战的跨页存活。

    与布局审计分开：这里不量尺寸，只验「界面上点的按钮真的动了引擎的状态」。
    三个断言各盯一条链：
      1. 诗人在遭遇战里用灵感 → 狼身上有骰（选择行 target_id 生效）；
      2. 德鲁伊从法术页施放巨虫术 → 场上多一只（施放行 encounter 生效）；
      3. 换页刷新之后 app.encounter 还在（状态上移没有被打断）。
    """
    problems: list[str] = []
    from dnd5r.kernel.rng import ScriptedRng

    bard = api.new_character(
        bundle, "dnd2024.class.bard", 2,
        {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 14},
        name_zh="诗人", name_en="Bard", actor_id="pc.bard")
    app = DesktopApp(bundle, bard, selftest=True)
    try:
        wolf = api.spawn_monster(bundle, "dnd2024.monster.wolf")
        app.encounter = api.new_encounter([bard, wolf], rng=ScriptedRng([10, 15]))
        guard = 0
        while app.encounter.current().actor is not bard and guard < 4:
            api.advance_turn(app.encounter)
            guard += 1
        app.refresh()
        page = app.powers_page
        page.powers.select_id("dnd2024.class.bard.bardic_inspiration")
        page._select_power()
        if page._choice_kind != "target_id":
            problems.append("活接线：灵感的选择行没有出现（channels 未进 sheet？）")
        elif not page.use_selected():
            problems.append("活接线：灵感使用失败（%s）" % page.status_var.get())
        elif not api.tokens_of(wolf):
            problems.append("活接线：用了灵感，狼身上却没有骰")
        # 换页刷新：遭遇战必须还活着
        app.refresh()
        if app.encounter is None or len(app.encounter.combatants) != 2:
            problems.append("活接线：刷新后遭遇战丢了（状态没有真的挂在 app 上）")
    finally:
        app.destroy()

    druid = api.new_character(
        bundle, "dnd2024.class.druid", 9,
        {"str": 10, "dex": 12, "con": 14, "int": 10, "wis": 18, "cha": 8},
        name_zh="德鲁伊", name_en="Druid")
    app = DesktopApp(bundle, druid, selftest=True)
    try:
        api.plan_spells(druid, bundle, "dnd2024.class.druid",
                        prepared=["dnd2024.spell.giant_insect"])
        app.refresh()
        wolf = api.spawn_monster(bundle, "dnd2024.monster.wolf")
        app.encounter = api.new_encounter([druid, wolf], rng=ScriptedRng([10, 15]))
        page = app.spells
        page.show("prepared", "dnd2024.spell.giant_insect")
        before = len(app.encounter.combatants)
        if not page.cast(True):
            problems.append("活接线：法术页施放失败（%s）" % page.status_var.get())
        elif len(app.encounter.combatants) != before + 1:
            problems.append("活接线：施放了召唤法术，场上却没有多出生物")
        slot4 = next((row for row in app.sheet["spellcasting"][0]["slots"]
                      if row["level"] == 4), None)
        if slot4 and slot4["left"] != slot4["max"] - 1:
            problems.append("活接线：结算施放没有扣法术位（4 环 %d/%d）"
                            % (slot4["left"], slot4["max"]))
    finally:
        app.destroy()
    return problems


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
            # 高度：status 是已 pack 的底部条，其余（顶栏 / 标签条 / 外边距）现量。
            # 以前这里写死 `- 40`，实测 chrome 是 99 —— 预算多算了 59px，
            # 加了 hero 之后还会更假。改量的，就不会再出现「绿着但超了」。
            avail_h = WINDOW_MIN[1] - app.chrome_height()
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
                    problems.extend(_check_appearance(label, app, page, app.sheet))
                    problems.extend(_check_dice(label, app, page, app.sheet))
                elif isinstance(page, SpellPage):
                    problems.extend(_check_spells(label, page, stats))
                elif isinstance(page, FeatPage):
                    problems.extend(_check_feats(label, page, stats))
                elif isinstance(page, PowersPage):
                    problems.extend(_check_powers(label, page, stats))
                elif isinstance(page, EncounterPage):
                    problems.extend(_check_encounter(label, page, stats))
            if app.winfo_ismapped():
                problems.append("%s：窗口被映射了（零弹窗铁律）" % label)
        finally:
            app.destroy()

    problems.extend(_check_live_wiring(bundle))
    print("活接线：能力选择行 / 法术施放 / 遭遇战跨页 —— %s"
          % ("OK" if not problems else "见上"))

    if problems:
        for item in problems:
            print("[FAIL] %s" % item)
        return 1
    print("LAYOUT OK —— %d 个角色 × %d 页全部在预算内；"
          "法术 %d / 专长 %d / 能力 %d 次写库；遭遇战 %d 场 / 攻击 %d 次"
          % (len(CASES), page_count, stats.get("toggles", 0),
             stats.get("feat_picks", 0), stats.get("power_uses", 0),
             stats.get("encounters", 0), stats.get("attacks", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
