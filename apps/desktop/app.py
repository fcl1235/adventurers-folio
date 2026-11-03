# -*- coding: utf-8 -*-
"""桌面外壳：一个窗口、一个角色、若干页面。

前端只用 `dnd5r.api`（约束 C3）：这里没有一处规则计算，全部数字来自
`api.character_sheet()`。所以「界面上显示的值」与「CLI / 测试算出的值」
不可能不一致 —— 它们是同一个函数。

零弹窗铁律：`selftest=True` 时窗口 **只 withdraw，永不 deiconify**。
探针要尺寸就用 reqsize，不靠把窗口亮出来量。

骨架对齐旧程序：hero 条（身份 / HP / 数值胶囊）+ 左属性卡 + 中标签页 + 右状态。
以前新界面只有一个三行文字的 header，于是「人物卡」看起来像一张表单。
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import dnd5r.api as api

from . import theme
from .cards import Chip
from .conditions import name_of
from .dice import format_roll
from .i18n import LOCALE_SHORT, T, get_locale, join, set_locale, system_locale
from .pages import OverviewPage
from .pages_encounter import EncounterPage
from .pages_feats import FeatPage
from .pages_gear import GearPage
from .pages_powers import PowersPage
from .pages_spells import SpellPage
from .pages_status import StatusPage
from .wizard import WizardView
from .widgets import COL_MID, hit_dice_text, hint_bar

# 设计尺寸：与旧程序一致，左 320 属性卡 + 中 610 标签页 + 右 300 状态正好放下。
WINDOW_SIZE = (1340, 860)
# **布局保证能塞下的最小窗口**：uicheck 与 test_desktop 都按它算预算。
WINDOW_MIN = (1180, 820)
# 真正的硬下限（小屏才用得上）。低于 WINDOW_MIN 时页面会被裁，这是已知限制。
WINDOW_FLOOR = (1024, 600)

SAVE_DIR = Path("saves")
# 界面的两种形态：`sheet` 是角色卡（默认），`wizard` 是建卡向导。
# 用**同一个窗口**换内容，不开 Toplevel —— 弹窗要么写死 geometry
# （内容一变按钮就消失），要么得复制一套 _fit 逻辑。
MODE_SHEET = "sheet"
MODE_WIZARD = "wizard"
# 界面偏好（目前只有语言）。和角色档放一起，跟着存档目录走。
SETTINGS_NAME = "_settings.json"


def _read_settings(save_dir: Path) -> dict:
    try:
        return json.loads((Path(save_dir) / SETTINGS_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class DesktopApp(tk.Tk):
    def __init__(self, bundle, actor, *, locale: str | None = None, selftest: bool = False,
                 save_dir=None) -> None:
        super().__init__()
        self.bundle = bundle
        self.actor = actor
        self.selftest = selftest
        self.sheet: dict = {}
        self.save_dir = Path(save_dir) if save_dir else SAVE_DIR
        # 语言优先级：显式传参 → 上次选过的 → 系统界面语言。
        # **selftest 一律中文**：探针不许因为「这台机器上次点过 English」而变绿变红。
        if locale is None:
            if not selftest:
                locale = _read_settings(self.save_dir).get("locale")
            locale = locale or ("zh" if selftest else system_locale())
        set_locale(locale)
        self.locale = get_locale()
        self.current_path: Path | None = None
        # 遭遇战是 app 级状态（P15）：战斗页创建/销毁它，能力页（授予目标）
        # 与法术页（召唤入場）都要读同一份 —— 挂在页私有属性上别的页够不着。
        self.encounter = None
        # 当前形态与建卡向导实例（`MODE_WIZARD` 时才有）
        self.mode = MODE_SHEET
        self.wizard = None

        self.title(T("冒险者手帖 · 5R 角色卡"))
        # 主题必须在建控件**之前**套上：ttk 样式是「建的时候就查」的，
        # 先建再改样式，已经建好的控件有一部分不会跟着变（Text/Listbox 更不会）。
        theme.apply_theme(self)
        self.minsize(*WINDOW_FLOOR)
        if selftest:
            self.withdraw()          # 永不 deiconify：探针不许抢焦点
        else:
            self._fit()

        self._build()
        self.refresh()
        # 快捷键走 bind_all：窗口内的任何控件拿到焦点都能用
        self.bind_all("<Control-s>", lambda _event: self.save_dialog())
        self.bind_all("<Control-o>", lambda _event: self.open_dialog())
        self.bind_all("<Control-n>", lambda _event: self.new_character())

    # --- 窗口尺寸 ---------------------------------------------------------
    def _fit(self) -> None:
        """按屏幕收缩：设计尺寸 → 屏宽-40 / 屏高-100 → 不低于硬下限。"""
        try:
            screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        except tk.TclError:                  # 无显示环境（极少），用设计尺寸
            screen_w, screen_h = WINDOW_SIZE
        width = min(WINDOW_SIZE[0], max(WINDOW_FLOOR[0], screen_w - 40))
        height = min(WINDOW_SIZE[1], max(WINDOW_FLOOR[1], screen_h - 100))
        self.geometry("%dx%d" % (width, height))

    # --- 骨架 -------------------------------------------------------------
    def _build(self) -> None:
        # 顺序有讲究：状态栏先占底部，再给会伸展的笔记本，否则窄屏时整条被裁掉
        self.status = hint_bar(self)
        self.status.pack(side="bottom", fill="x", padx=8, pady=(2, 6))

        self.hero = self._build_hero()
        self.hero.pack(side="top", fill="x", padx=8, pady=(6, 2))

        self.book = ttk.Notebook(self)
        self.book.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))

        self.overview = OverviewPage(self.book, on_roll=self.roll_check,
                                     on_action=self.on_state_action)
        self.book.add(self.overview, text=T("概览"))
        self.gear = GearPage(self.book, self)
        self.book.add(self.gear, text=T("装备"))
        self.spells = SpellPage(self.book, self)
        self.book.add(self.spells, text=T("法术"))
        self.feats = FeatPage(self.book, self)
        self.book.add(self.feats, text=T("专长"))
        self.powers_page = PowersPage(self.book, self)
        self.book.add(self.powers_page, text=T("能力"))
        self.encounter_page = EncounterPage(self.book, self)
        self.book.add(self.encounter_page, text=T("战斗"))
        # 状态（条件 / 力竭 / 濒死 / 专注）单独一页：塞在概览右栏那个 300×400
        # 的滚动区里时，死亡豁免默认在视野外，滚动还会重影（见 pages_status 说明）。
        self.status_page = StatusPage(self.book, on_action=self.on_state_action)
        self.book.add(self.status_page, text=T("状态"))
        self.pages = [self.overview, self.gear, self.spells, self.feats,
                      self.powers_page, self.encounter_page, self.status_page]

    def _build_hero(self) -> ttk.Frame:
        """身份 + 生命值 + 5 个数值胶囊。

        `name_var` / `sub_var` / `state_var` 三个变量名保留 —— 测试直接摸它们。
        """
        hero = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        # 左：身份
        ident = ttk.Frame(hero, style="Panel.TFrame")
        ident.pack(side="left", anchor="n")
        self.name_var = tk.StringVar()
        ttk.Label(ident, textvariable=self.name_var, style="Panel.TLabel",
                  font=(theme.UI_FONT, 17, "bold"),
                  foreground=theme.GOLD2).pack(anchor="w")
        self.sub_var = tk.StringVar()
        ttk.Label(ident, textvariable=self.sub_var, style="DimPanel.TLabel",
                  wraplength=360, justify="left").pack(anchor="w")
        self.state_var = tk.StringVar()
        ttk.Label(ident, textvariable=self.state_var, style="DimPanel.TLabel",
                  foreground=theme.WARN).pack(anchor="w", pady=(2, 0))

        # 中：生命值。数字用大号且按比例变色，进度条只做辅助。
        hp_box = ttk.Frame(hero, style="Panel.TFrame")
        hp_box.pack(side="left", anchor="n", padx=(28, 0))
        hp_head = ttk.Frame(hp_box, style="Panel.TFrame")
        hp_head.pack(anchor="w")
        ttk.Label(hp_head, text=T("❤ 生命值"), style="DimPanel.TLabel").pack(side="left")
        self.hp_var = tk.StringVar()
        self.hp_value = ttk.Label(hp_head, textvariable=self.hp_var, style="Panel.TLabel",
                                  font=(theme.UI_FONT, 20, "bold"))
        self.hp_value.pack(side="left", padx=(8, 0))
        self.hp_bar = ttk.Progressbar(hp_box, style="HP.Horizontal.TProgressbar",
                                      length=235, maximum=100, value=0)
        self.hp_bar.pack(anchor="w", pady=(3, 0))
        self.hp_detail = ttk.Label(hp_box, text="", style="DimPanel.TLabel")
        self.hp_detail.pack(anchor="w")

        # 右：5 个数值胶囊（AC / 先攻 / 速度 / 熟练 / 察觉）
        chips = ttk.Frame(hero, style="Panel.TFrame")
        chips.pack(side="right", anchor="n")
        self.chips: dict[str, Chip] = {}
        for key, title in (("ac", T("护甲 AC")), ("initiative", T("先攻")),
                           ("speed", T("速度")), ("prof", T("熟练")), ("perception", T("察觉"))):
            chip = Chip(chips, title)
            chip.pack(side="left", padx=(6, 0))
            self.chips[key] = chip

        # 文件按钮。放在 hero 里而不是加一条菜单栏：Tk 的菜单栏是窗口框的一部分，
        # **不计入 `winfo_reqheight`**，一加就等于凭空少掉 ~20px 可用高度，
        # 而 chrome_height() 量不到它 —— 那种超出最难发现。hero 里加按钮只占宽度。
        files = ttk.Frame(hero, style="Panel.TFrame")
        files.pack(side="right", anchor="n", padx=(0, 10))
        self.file_buttons: dict[str, ttk.Button] = {}
        for key, text, action in (("new", T("新建"), self.new_character),
                                  ("open", T("打开"), self.open_dialog),
                                  ("save", T("保存"), self.save_dialog),
                                  ("edit", T("改卡"), self.edit_character),
                                  ("level", T("升级"), self.level_up)):
            button = ttk.Button(files, text=text, style="Mini.TButton",
                                command=action, width=5)
            button.pack(side="left", padx=(0, 4))
            self.file_buttons[key] = button

        # 语言：按钮上写**要切过去的那个语言**（中文界面显示 "EN"），
        # 比写当前语言直观 —— 点它就是要变成它。
        self.lang_button = ttk.Button(
            files, text=self._other_locale_label(), style="Mini.TButton",
            command=self.toggle_locale, width=4)
        self.lang_button.pack(side="left", padx=(0, 4))
        return hero

    # --- 语言 -------------------------------------------------------------
    def _other_locale_label(self) -> str:
        return LOCALE_SHORT["en" if self.locale == "zh" else "zh"]

    def toggle_locale(self) -> None:
        self.switch_locale("en" if self.locale == "zh" else "zh")

    def switch_locale(self, code: str) -> None:
        """切语言 = **整窗重建**。

        控件是在创建时取文案的（`text=T("...")` 当场求值），改不了已经建好的
        几百个标签。重建比逐个改便宜，也不会漏掉哪一处。
        代价：正在建的卡（向导里那半张）会丢 —— 所以建卡中不让切。
        """
        if code == self.locale:
            return
        if self.mode == MODE_WIZARD:
            self.status.configure(text=T("建卡过程中不能切换语言，先建完或点「取消」"),
                                  foreground=theme.WARN)
            return
        set_locale(code)
        self.locale = code
        self._write_settings()
        index = 0
        try:
            index = self.book.index(self.book.select())
        except tk.TclError:
            pass
        for child in self.winfo_children():
            child.destroy()
        self.mode = MODE_SHEET
        self.wizard = None
        self.title(T("冒险者手帖 · 5R 角色卡"))
        self._build()
        self.refresh()
        try:
            self.book.select(index)
        except (tk.TclError, IndexError):
            pass

    def _write_settings(self) -> None:
        """记住语言。写不进去不影响使用（下次退回系统语言），所以失败就忽略。"""
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            data = _read_settings(self.save_dir)
            data["locale"] = self.locale
            (self.save_dir / SETTINGS_NAME).write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    # --- 刷新 -------------------------------------------------------------
    def refresh(self) -> None:
        """整个界面按最新的 sheet 重画。改完数据就调它，别做局部补丁。"""
        self.sheet = api.character_sheet(self.actor, self.bundle, self.locale)
        for page in self.pages:
            page.refresh(self.sheet)
        self._refresh_header()

    def apply_actor(self, actor) -> None:
        """换掉角色并重画。改档案（专长选择项）后必须整只换 —— 派生值全变了。"""
        self.actor = actor
        self.refresh()

    # --- 掷骰 -------------------------------------------------------------
    def roll_check(self, kind: str, key: str = "", rng=None, note: str = "") -> dict | None:
        """掷一次并写进记录。**加值与优势全由 `api.roll_check` 决定**。

        `rng` 只为测试注入：界面上掷的是真骰子，探针里可以塞一条固定序列。
        `note` 是掷完才知道的那句话（「DC 12 保持专注」）—— 记录里必须有，
        否则过一会儿回看，看见的只是一次没头没尾的体质豁免。
        失败只改状态行、返回 None —— 让异常冒到 Tk 回调里会打一堆调用栈，
        界面上却一点反馈都没有。
        """
        try:
            result = api.roll_check(self.actor, self.bundle, kind, key, rng=rng)
        except api.DndError as exc:
            self.status.configure(text=T("掷骰失败：%s") % exc,
                                  foreground=theme.WARN)
            return None
        line = format_roll(result)
        if note:
            line = "%s → %s" % (line, note)
        self.overview.dice_log.add(line)
        self.status.configure(text=T("掷骰　") + line, foreground=theme.TEXT)
        return result

    # --- 状态：条件 / 力竭 / 濒死 / 专注 -----------------------------------
    def on_state_action(self, name: str, value=None, rng=None) -> dict | None:
        """把状态面板的四种操作落成事实，然后整页重画。

        `rng` 只为测试注入。失败照旧只改状态行 —— 让 RuleError 冒到 Tk 回调里，
        玩家看到的是「点了没反应 + 控制台一堆栈」。
        """
        try:
            if name == "condition":
                ident, on = value
                changed = api.set_condition(self.actor, ident, on)
                note = T("已记上") if on else T("已取下")
                if not changed:
                    note = T("本来就是") + (T("记上的") if on else T("取下的"))
                self.status.configure(text=T("状态　%s %s（已记录，未计入数值）")
                                            % (name_of(ident), note),
                                      foreground=theme.TEXT)
            elif name == "exhaustion":
                level = api.set_exhaustion(self.actor, int(value))
                self.status.configure(text=T("力竭 %d 级（已计入：全部 d20 %+d）")
                                            % (level, -2 * level),
                                      foreground=theme.TEXT)
            elif name == "death_save":
                result = api.roll_death_save(self.actor, rng)
                line = T("死亡豁免：%d → %s（成功 %d/%d · 失败 %d/%d）") % (
                    result["roll"], result["label"], result["succeeded"],
                    result["succeeded_of"], result["failed"], result["failed_of"])
                self.overview.dice_log.add(line)
                self.status.configure(text=line, foreground=theme.TEXT)
                self.refresh()
                return result
            elif name == "death_reset":
                api.reset_death_saves(self.actor)
                self.status.configure(text=T("死亡豁免已重置"), foreground=theme.TEXT)
            elif name == "scores":
                actor = api.set_base_scores(self.actor, self.bundle, dict(value))
                # 换的是整只 actor：属性牵动 HP 上限/熟练/攻击/豁免一整套派生值
                self.apply_actor(actor)
                self.status.configure(text=T("属性已更新（HP 上限、熟练与攻击已重算）"),
                                      foreground=theme.TEXT)
                return actor
            elif name == "concentration":
                dc = api.concentration_dc(int(value))
                roll = self.roll_check(
                    "save", "con", rng=rng,
                    note=T("DC %d 专注") % dc)
                if roll is None:
                    return None
                ok = roll["total"] >= dc
                self.status_page.state_panel.set_concentration_dc(
                    dc, T("成功") if ok else T("失败"))
                self.status.configure(
                    text=T("专注检定　DC %d → %d，%s") % (dc, roll["total"],
                                                    T("保持专注") if ok else T("专注中断")),
                    foreground=theme.TEXT if ok else theme.WARN)
                return roll
            else:
                raise api.RuleError(T("不认识的状态操作：%r") % (name,))
        except api.DndError as exc:
            self.status.configure(text=T("状态操作失败：%s") % exc,
                                  foreground=theme.WARN)
            if name == "scores":
                self.overview.set_edit_error(str(exc))
            return None
        self.refresh()
        return None

    # --- 存读档 -----------------------------------------------------------
    def default_save_path(self) -> Path:
        name = (self.sheet.get("name") or "character").strip() or "character"
        return self.save_dir / ("%s.json" % name)

    def save_to(self, path) -> str | None:
        """写盘。返回实际路径，失败返回 None（原因进状态行，不抛）。"""
        target = Path(path)
        try:
            payload = api.save_character(self.actor)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                              encoding="utf-8")
        except (OSError, api.DndError) as exc:
            self.status.configure(text=T("存档失败：%s") % exc, foreground=theme.WARN)
            return None
        self._remember(target)
        self.current_path = target
        self.status.configure(text=T("已保存：%s") % target.name, foreground=theme.TEXT)
        return str(target)

    def load_from(self, path) -> bool:
        target = Path(path)
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            actor = api.load_character(self.bundle, payload)
        except (OSError, ValueError, api.DndError) as exc:
            self.status.configure(text=T("读档失败：%s") % exc, foreground=theme.WARN)
            return False
        self.apply_actor(actor)
        self._remember(target)
        self.current_path = target
        # 换了角色，上一个人的掷骰记录留着只会误导
        self.overview.dice_log.clear()
        self.status.configure(text=T("已读取：%s") % target.name, foreground=theme.TEXT)
        return True

    def new_character(self) -> None:
        """新建 → 打开建卡向导。默认档案只在向导被取消时兜底。"""
        self.open_wizard()

    # --- 建卡向导 ---------------------------------------------------------
    def open_wizard(self, draft: dict | None = None, editing: bool = False,
                    step: int = 0) -> None:
        """在主窗口内切到建卡向导。

        `editing=True` 是「改现有角色」（升级后发现还差选择）：完成时走
        `apply_draft`（重建并保住背包/HP/资源），不走造新角色那条路。
        """
        if self.mode == MODE_WIZARD:
            return
        self.mode = MODE_WIZARD
        # hero 与标签页**同时**让位：向导走完全程，中途看见旧角色的血条
        # 会让人以为「已经在改这个角色了」。
        self.hero.pack_forget()
        self.book.pack_forget()
        self.wizard = WizardView(self, self, draft=draft, editing=editing, step=step)
        self.wizard.pack(side="top", fill="both", expand=True, padx=8, pady=(6, 0))
        self.status.configure(
            text=T("%s · 第 %d 步：%s") % (T("改卡中") if editing else T("建卡中"),
                                      self.wizard.index + 1,
                                      self.wizard.current["title"]),
            foreground=theme.DIM)

    def close_wizard(self) -> None:
        """回到角色卡。**顺序要紧**：hero 先 pack，标签页后 pack ——
        反过来的话标签页会占满整条，hero 被挤到最后一行。"""
        if self.mode != MODE_WIZARD:
            return
        self.mode = MODE_SHEET
        if self.wizard is not None:
            self.wizard.destroy()
            self.wizard = None
        self.hero.pack(side="top", fill="x", padx=8, pady=(6, 2))
        self.book.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 4))

    def finish_wizard(self, actor, editing: bool = False) -> None:
        """向导点了「建卡 / 完成」：换角色、回角色卡、清记录。

        **先退出向导再 apply_actor**：`apply_actor` 会调 `_fit_window`，
        而它在向导模式下量的是一个还没还原的布局（chrome 里算的是向导高度），
        算出来的窗口尺寸会偏小。顺序反了窗口会莫名缩一下。

        `editing=True` 时**不清**当前文件与掷骰记录 —— 改的还是同一个角色，
        记录留着才对得上。
        """
        self.close_wizard()
        self.apply_actor(actor)
        if editing:
            self.status.configure(text=T("已改卡：%s") % (self.sheet.get("name") or ""),
                                  foreground=theme.TEXT)
            return
        self.current_path = None
        self.overview.dice_log.clear()
        self.status.configure(text=T("已建卡：%s（还没保存，Ctrl+S 或点「保存」）")
                                    % (self.sheet.get("name") or T("无名冒险者")),
                              foreground=theme.TEXT)

    # --- 升级 -------------------------------------------------------------
    def edit_character(self) -> None:
        """改现有角色：把向导整程打开，完成时走 `apply_draft`。

        没有这个入口时，专长修好也没人能用上 —— 建完卡之后物种、背景、技能、
        精通就全锁死了，只有「升级」碰巧遇到「还差选择」时才顺带进得去。
        人物卡软件的核心是**卡要能改**，所以这里给一个直白的按钮。
        """
        try:
            draft = api.draft_from_actor(self.bundle, self.actor)
        except api.DndError as exc:
            self.status.configure(text=T("这张卡改不了：%s") % exc, foreground=theme.WARN)
            return
        self.open_wizard(draft=draft, editing=True)

    def level_up(self) -> None:
        """升一级主职业。保留背包/装备/HP；还差选择就把向导开到那一步。

        **不弹确认框**：零弹窗铁律。升级是可逆的（降级就是改回去），
        而且 `rebuild_actor` 保住了运行时状态，不存在「升错了角色废了」。
        """
        try:
            view = api.level_up_view(self.bundle, self.actor, self.locale)
            actor = api.level_up(self.bundle, self.actor, self.locale)
        except api.DndError as exc:
            self.status.configure(text=T("升不了级：%s") % exc, foreground=theme.WARN)
            return
        self.apply_actor(actor)
        parts = [T("升到 %d 级 %s（生命上限 %d → %d）")
                 % (view["to_level"], view["class_name"],
                    view["hp_before"], view["hp_after"])]
        if view["prof_before"] != view["prof_after"]:
            parts.append(T("熟练加值 +%d") % (view["prof_after"] - view["prof_before"]))
        if view["unlocks"]:
            parts.append(T("新解锁：") + join(row["name"] for row in view["unlocks"]))
        if view["needs"]:
            parts.append(T("还差：") + "；".join(row["text"] for row in view["needs"]))
            # 把向导直接开到第一个「要补选择」的那一步，玩家不用自己找。
            # **状态行要在 open_wizard 之后再写**：它会先把自己的「第 N 步」写进去。
            message = " · ".join(parts)
            self.open_wizard(draft=api.draft_from_actor(self.bundle, self.actor),
                             editing=True,
                             step=api.STEP_INDEX.get(view["needs"][0]["step"], 0))
            self.status.configure(text=message, foreground=theme.WARN)
            return
        self.status.configure(text=" · ".join(parts), foreground=theme.TEXT)

    def save_dialog(self):
        """另存为/保存。selftest 下**必须直接返回** —— 弹文件对话框会挂住探针。"""
        if self.mode == MODE_WIZARD:
            # 建卡中「保存」会存下**上一个**角色的卡，然后界面说「已保存」。
            # 那是最坏的一种谎话：玩家以为存了新角色。
            self.status.configure(text=T("建卡过程中不能保存，先把卡建完（或点「取消」）"),
                                  foreground=theme.WARN)
            return None
        if self.selftest:
            return None
        from tkinter import filedialog
        initial = self.current_path or self.default_save_path()
        path = filedialog.asksaveasfilename(
            parent=self, title=T("保存角色"), initialdir=str(self.save_dir),
            initialfile=initial.name, defaultextension=".json",
            filetypes=[(T("冒险者手帖 角色档"), "*.json"), (T("所有文件"), "*.*")])
        return self.save_to(path) if path else None

    def open_dialog(self):
        if self.mode == MODE_WIZARD:
            # 同理：读进来会换掉角色，而界面上还停在第 N 步的草案里
            self.status.configure(text=T("建卡过程中不能打开别的角色，先建完或点「取消」"),
                                  foreground=theme.WARN)
            return False
        if self.selftest:
            return False
        from tkinter import filedialog
        self.save_dir.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            parent=self, title=T("打开角色"), initialdir=str(self.save_dir),
            filetypes=[(T("冒险者手帖 角色档"), "*.json"), (T("所有文件"), "*.*")])
        return self.load_from(path) if path else False

    def _remember(self, target: Path) -> None:
        """记下「上次用的文件」。记不住不影响存盘本身，所以失败就忽略。"""
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            (self.save_dir / "_last.json").write_text(
                json.dumps({"path": str(target)}, ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            pass

    def _refresh_header(self) -> None:
        sheet = self.sheet
        self.name_var.set(sheet.get("name", ""))
        classes = join("%s %d" % (row["name"], row["class_level"])
                            for row in sheet.get("classes", []))
        subs = join(row["name"] for row in sheet.get("subclasses", []) if row.get("unlocked"))
        # **出身也是身份**：物种与背景以前只在建卡向导里出现过，建完卡在界面上
        # 彻底消失 —— 「我是矮人/士兵」是人物卡的一等信息，不能只体现在派生数值里。
        origin = sheet.get("origin") or {}
        species = (origin.get("species") or {}).get("name") or ""
        background = (origin.get("background") or {}).get("name") or ""
        born = " · ".join(item for item in (species, background) if item)
        total = sheet.get("total_level", 0)
        self.sub_var.set(" · ".join(item for item in
                                    [classes, subs, born, T("总等级 %d") % total] if item))
        marks = []
        if sheet.get("morphed"):
            marks.append(T("变形中"))
        if sheet.get("conditions"):
            marks.append(T("状态：") + join(sheet["conditions"]))
        self.state_var.set("  ".join(marks))
        self._refresh_hp(sheet)
        self._refresh_chips(sheet)
        self.status.configure(
            text=T("内容：%d 职业 / %d 子职 / %d 法术 / %d 专长 · 错误 %d")
                 % (len(self.bundle.classes), len(self.bundle.subclasses),
                    len(self.bundle.spells), len(self.bundle.feats),
                    len(self.bundle.errors)))

    def _refresh_hp(self, sheet: dict) -> None:
        hp = sheet.get("hp", {})
        current, maximum = int(hp.get("current", 0)), int(hp.get("maximum", 0))
        self.hp_var.set("%d / %d" % (current, maximum))
        self.hp_value.configure(foreground=theme.hp_color(current, maximum))
        self.hp_bar.configure(maximum=max(1, maximum), value=current)
        extras = []
        if hp.get("temp"):
            extras.append(T("临时 %d") % hp["temp"])
        dice = hit_dice_text(hp.get("hit_dice"), sheet.get("classes"))
        if dice:
            extras.append(T("生命骰 ") + dice)
        self.hp_detail.configure(text=" · ".join(extras))

    def _refresh_chips(self, sheet: dict) -> None:
        perception = next((row["total"] for row in sheet.get("skills", ())
                           if row.get("key") == "perception"), None)
        self.chips["ac"].set_value(str(sheet.get("ac", {}).get("total", "—")))
        self.chips["initiative"].set_value(
            "%+d" % sheet.get("initiative", {}).get("total", 0))
        self.chips["speed"].set_value("%d" % sheet.get("speed", {}).get("walk", 0))
        self.chips["prof"].set_value("%+d" % sheet.get("proficiency_bonus", 0))
        self.chips["perception"].set_value(
            "%+d" % perception if perception is not None else "—")

    # --- 给探针用 ---------------------------------------------------------
    def page_size(self, page: ttk.Frame) -> tuple[int, int]:
        """页面自身需要的尺寸（不依赖窗口是否可见）。"""
        return page.winfo_reqwidth(), page.winfo_reqheight()

    def chrome_height(self) -> int:
        """窗口中**不归页面用**的那部分高度：状态栏 + hero + 标签条 + 外边距。

        **现量，不许写死。** 这里原来在测试里被写死成 40（"header + 标签条"），
        一旦顶栏长高（比如加一条 hero），那个 40 就假了 —— 会出现
        「报 LAYOUT OK 但实际已经超预算」这种最难查的错。实测 old header 时是 99。
        """
        self.update_idletasks()
        if self.mode == MODE_WIZARD and self.wizard is not None:
            # 向导模式下 hero 与标签页都让位了，窗口里只剩向导 + 状态栏
            return self.winfo_reqheight() - self.wizard.winfo_reqheight()
        tallest = max(self.page_size(page)[1] for page in self.pages)
        return self.winfo_reqheight() - tallest

    def hero_height(self) -> int:
        """hero 条占的高度（预算里最该盯住的一块）。"""
        self.update_idletasks()
        return self.hero.winfo_reqheight()

    def layout_report(self) -> dict:
        """布局审计用的纯数据：每页 reqsize + 中栏预算。

        `update_idletasks()` 只做几何计算，**不映射窗口**（此时窗口是 withdrawn）。
        """
        self.update_idletasks()
        return {
            "window": WINDOW_SIZE,
            "window_min": WINDOW_MIN,
            "chrome": self.chrome_height(),
            "hero": self.hero_height(),
            "mid_budget": COL_MID,
            "pages": [{"name": str(page), "req": self.page_size(page)}
                      for page in self.pages],
        }
