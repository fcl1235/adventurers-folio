# -*- coding: utf-8 -*-
"""遭遇战页：谁在场、轮到谁、离多远、这一下打没打中。

引擎在 P9a/P9b/P9c 就齐了（先攻序、5 尺格距离、武器与怪物攻击都真结算），
但桌上一直没入口 —— 这一页是入口，它自己**不算任何规则**：
先攻序、距离、命中、伤害全部来自 `dnd5r.api`，界面只负责把参数收齐、
把报告原样摆出来（约束 C3）。

四个刻意的取舍：

1. **战斗不进存档**。关掉程序就忘掉这一场 —— 与 `Encounter` / `ActionEconomy`
   同一条理由。所以这页没有「保存战斗」按钮，也不假装有。
2. **地图是 10×8 格（50×40 尺），不做寻路**。点哪格走哪格，斜着走不算远。
   绕柱子请分段点 —— 程序确实不知道墙在哪，画一堆墙只会骗人。
3. **「预览」与「真结算」分成两个按钮**。误点一下就改别人的血条，
   比多点一次麻烦得多。预览不扣血、不扣动作额度。
4. **出手的人取自先攻条**，不是另设一个「当前操作者」。这样「谁在打谁」
   与「现在轮到谁」永远指同一个东西，不会出现两边不一致。

零弹窗铁律：`selftest=True` 时窗口只 withdraw。这页的所有断言走方法调用，
不 deiconify、不 grab_set。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import dnd5r.api as api

from . import theme
from .widgets import COL_LEFT, COL_MID, COL_RIGHT, ListPane, ScrollText, section

# 一格 5 尺。10 × 8 格 = 50 × 40 尺，够放一场小型遭遇战，也不会把页面顶出预算。
CELL = 40
COLS = 10
ROWS = 8
FOOT = 5

MODES = (("place", "摆位（不花移动力）"), ("move", "移动（花移动力）"),
         ("teleport", "传送（30 尺内）"))
TELEPORT_FEET = 30

KIND_ZH = {"pc": "玩家", "npc": "NPC", "monster": "怪物",
           "form": "形态", "summon": "召唤物"}


class EncounterPage(ttk.Frame):
    """遭遇战页。`app` 只用 actor / bundle / locale / refresh。"""

    def __init__(self, master, app) -> None:
        super().__init__(master, padding=(6, 4))
        self.app = app
        # 遭遇战本体挂在 app 上（别的页要指认目标 / 召唤入場）；这里只留代理
        self.roster: list[dict] = []     # 怪物清单（来自 api.monster_catalog）
        self._attendees: list = []       # 已经点过「加入」的怪物 Actor
        self._attacker_id = ""
        self._target_id = ""
        self._action_key = ""
        self._action_rows: list[dict] = []
        self._form_noted: tuple[str, str] | None = None
        self._mode = tk.StringVar(value="place")
        self._log: list[str] = []
        self._build()

    # 遭遇战代理：读写都落到 app（唯一一份，战斗页只是它的驾驶舱）
    @property
    def encounter(self):
        return self.app.encounter

    @encounter.setter
    def encounter(self, value) -> None:
        self.app.encounter = value

    # --- 骨架 -------------------------------------------------------------
    def _build(self) -> None:
        left = ttk.Frame(self, width=COL_LEFT)
        mid = ttk.Frame(self, width=COL_MID)
        right = ttk.Frame(self, width=COL_RIGHT)
        left.grid(row=0, column=0, sticky="nsw")
        mid.grid(row=0, column=1, sticky="nsew", padx=8)
        right.grid(row=0, column=2, sticky="nsew")
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_roster(left)
        self._build_order(mid)
        self._build_map(mid)
        self._build_attack(right)

        self.status_var = tk.StringVar(value="先点左边把怪物加进来，再「掷先攻」。")
        self.status = ttk.Label(self, textvariable=self.status_var, anchor="w")
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

    def _build_roster(self, left) -> None:
        box = section(left, "怪物名单")
        box.pack(fill="both", expand=True)
        self.roster_pane = ListPane(box, height=12, width=26)
        self.roster_pane.pack(fill="both", expand=True, pady=(2, 0))

        row = ttk.Frame(left)
        row.pack(fill="x", pady=(6, 0))
        self.add_button = ttk.Button(row, text="加入战斗", command=self.add_monster)
        self.add_button.pack(side="left")
        ttk.Button(row, text="清空", command=self.clear_all).pack(side="left", padx=(4, 0))

        self.hint_var = tk.StringVar(
            value="清单按 CR 排序。同一只加两次会是「狼」与「狼 2」，各有各的血条。")
        ttk.Label(left, textvariable=self.hint_var, foreground=theme.DIM,
                  wraplength=COL_LEFT - 20, justify="left").pack(anchor="w", pady=(6, 0))

    def _build_order(self, mid) -> None:
        box = section(mid, "先攻条")
        box.pack(fill="x")
        self.order_pane = ListPane(box, height=6, width=50)
        self.order_pane.pack(fill="x", pady=(2, 0))
        self.order_pane.list.bind("<<ListboxSelect>>", lambda _e: self._select_attacker())

        row = ttk.Frame(box)
        row.pack(fill="x", pady=(4, 0))
        self.start_button = ttk.Button(row, text="掷先攻并开始", command=self.start)
        self.start_button.pack(side="left")
        self.next_button = ttk.Button(row, text="下一回合", command=self.next_turn)
        self.next_button.pack(side="left", padx=(4, 0))
        # 阵营是输入不是判断：程序不猜谁是狼的同伴，DM 说了算（G23）
        self.side_button = ttk.Button(row, text="改阵营", command=self.toggle_side)
        self.side_button.pack(side="left", padx=(4, 0))
        self.round_var = tk.StringVar(value="还没开战")
        ttk.Label(row, textvariable=self.round_var).pack(side="left", padx=(10, 0))

    def _build_map(self, mid) -> None:
        box = section(mid, "战场（一格 5 尺 · 10 × 8）",
                      "点格子 = 把先攻条里选中的人移过去；绕柱子请分段点。")
        box.pack(fill="both", expand=True, pady=(6, 0))

        modes = ttk.Frame(box)
        modes.pack(fill="x")
        for value, text in MODES:
            ttk.Radiobutton(modes, text=text, value=value, variable=self._mode).pack(
                side="left", padx=(0, 8))

        self.canvas = tk.Canvas(box, width=COLS * CELL, height=ROWS * CELL,
                                background=theme.MAP_BG, highlightthickness=1,
                                highlightbackground=theme.MAP_BORDER)
        self.canvas.pack(anchor="w", pady=(4, 0))
        self.canvas.bind("<Button-1>", self._on_canvas_click)

    def _build_attack(self, right) -> None:
        box = section(right, "这一次出手")
        box.pack(fill="x")
        self.attacker_var = tk.StringVar(value="出手的人：（先攻条里选）")
        ttk.Label(box, textvariable=self.attacker_var, wraplength=COL_RIGHT - 20,
                  foreground=theme.DIM).pack(anchor="w")

        ttk.Label(box, text="目标：", foreground=theme.DIM).pack(anchor="w", pady=(4, 0))
        self.target_pane = ListPane(box, height=4, width=30)
        self.target_pane.pack(fill="x")
        self.target_pane.list.bind("<<ListboxSelect>>", lambda _e: self._select_target())

        ttk.Label(box, text="动作用哪一条：", foreground=theme.DIM).pack(anchor="w", pady=(4, 0))
        self.action_pane = ListPane(box, height=4, width=30)
        self.action_pane.pack(fill="x")
        self.action_pane.list.bind("<<ListboxSelect>>", lambda _e: self._select_action())

        # 掷骰模式：默认「自动」—— 按特性事实判定（群体战术）；判不了时
        # 报告会明说，这时 DM 在这里手动指定。只对怪物/形态攻击生效，
        # 玩家武器攻击按角色自己的状态判定（选了也会提示没生效）。
        mode_row = ttk.Frame(box)
        mode_row.pack(fill="x", pady=(4, 0))
        ttk.Label(mode_row, text="掷骰模式：", foreground=theme.DIM).pack(side="left")
        self.mode_var = tk.StringVar(value="自动")
        ttk.Combobox(mode_row, textvariable=self.mode_var, state="readonly",
                     values=("自动", "优势", "劣势", "平掷"),
                     width=6).pack(side="left")

        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 0))
        self.roll_button = ttk.Button(row, text="掷一次", command=lambda: self.roll(True))
        self.roll_button.pack(side="left")
        ttk.Button(row, text="预览", command=lambda: self.roll(False)).pack(
            side="left", padx=(4, 0))

        log = section(right, "战斗记录")
        log.pack(fill="both", expand=True, pady=(6, 0))
        self.log = ScrollText(log, height=10, width=30)
        self.log.pack(fill="both", expand=True)

    # --- 数据 -------------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        """`sheet` 变了（玩家掉血、变形、换装备）就重画一遍 —— 不缓存派生值。"""
        if not self.roster:
            self._fill_roster()
        self._fill_order()
        self._fill_targets()
        self._fill_actions()
        self._draw_map()
        self._check_buttons()

    def _fill_roster(self) -> None:
        self.roster = api.monster_catalog(self.app.bundle, self.app.locale)
        rows = []
        for row in self.roster:
            rows.append((row["id"], "CR %-4s %s（AC %d · HP %d）"
                         % (row["cr_text"], row["name"], row["ac"], row["hp"])))
        self.roster_pane.fill(rows)
        if self.roster and not self.roster_pane.selected_id():
            self.roster_pane.select_id(self.roster[0]["id"])

    def _fill_order(self) -> None:
        view = self._view()
        rows = []
        for row in (view.get("order") or []):
            mark = "▶" if row.get("active") else "　"
            side = {"party": "我", "foes": "敌"}.get(row.get("side"), "？")
            rows.append((row["id"], "%s [%s] %s　先攻 %d　HP %d/%d　(%d,%d)%s"
                         % (mark, side, row["label"], int(row["initiative"]),
                            int(row["hp"]["current"]), int(row["hp"]["maximum"]),
                            int(row["x"]), int(row["y"]),
                            "　已倒地" if row.get("down") else "")))
        self.order_pane.fill(rows)
        keep = self._attacker_id or view.get("current") or ""
        if keep:
            self.order_pane.select_id(keep)
        self._attacker_id = self.order_pane.selected_id()
        self.round_var.set("第 %d 轮 · 轮到 %s" % (view.get("round") or 0,
                                               self._current_label(view))
                           if view.get("started") else "还没开战")
        hint = view.get("distance_hint") or ""
        if hint:
            self.hint_var.set(hint)
        elif self.hint_var.get().startswith("位置还没摆"):
            self.hint_var.set("清单按 CR 排序。同一只加两次会是「狼」与「狼 2」，各有各的血条。")

    @staticmethod
    def _current_label(view: dict) -> str:
        for row in view.get("order") or []:
            if row.get("active"):
                return row["label"]
        return "（无人）"

    def _fill_targets(self) -> None:
        view = self._view()
        rows = [(row["id"], "%s（AC %d · HP %d）"
                 % (row["label"], int(row["ac"]), int(row["hp"]["current"])))
                for row in (view.get("order") or []) if row["id"] != self._attacker_id]
        self.target_pane.fill(rows)
        if self._target_id not in {row[0] for row in rows}:
            self._target_id = rows[0][0] if rows else ""
        if self._target_id:
            self.target_pane.select_id(self._target_id)

    def _fill_actions(self) -> None:
        """出手的人能做什么：玩家给武器，变形中的玩家给形态的天然武器，怪物给动作。

        三条来源都是 api 算好的，界面只拼标签 —— 命中加值、伤害骰一个都不自己算。
        """
        combatant = self._combatant(self._attacker_id)
        rows: list[dict] = []
        form: dict = {"morphed": False}
        if combatant is not None:
            actor = combatant["actor"]
            kind = api.actor_view(actor, self.app.locale).get("kind")
            form = api.form_view(actor, self.app.bundle, self.app.locale)
            if kind == "pc" and not form.get("morphed"):
                for row in (self.app.sheet.get("attacks") or []):
                    rows.append({
                        "key": row["weapon"],
                        "name": "%s %+d（%s%+d %s）"
                                % (row["name"], int(row["attack"]), row["damage"],
                                   int(row["damage_bonus"]), row["damage_type"]),
                    })
            elif form.get("morphed"):
                # 变形中：天然武器照形态卡上的数走（与怪物同一条结算）
                rows = _attack_rows(form.get("actions") or [])
                self._note_form(actor, form)
            else:
                sheet = api.monster_sheet(self.app.bundle, actor, locale=self.app.locale)
                rows = _attack_rows(sheet.get("actions") or [])
        self._action_rows = rows
        self.action_pane.fill([(row["key"], row["name"]) for row in rows])
        if self._action_key not in {row["key"] for row in rows}:
            self._action_key = rows[0]["key"] if rows else ""
        if self._action_key:
            self.action_pane.select_id(self._action_key)
        label = combatant["label"] if combatant else "（先攻条里选）"
        if form.get("morphed"):
            label = "%s（形态 %s · AC %d · HP %d）" % (
                label, form.get("name") or form.get("id"),
                int(form.get("ac") or 0), int(form.get("hp") or 0))
        self.attacker_var.set("出手的人：%s" % label)

    def _note_form(self, actor, form: dict) -> None:
        """换了个形态就说一句：这是它的卡，哪些特性算得出来、哪些只有文字。

        放在状态行而不是新控件里 —— 右栏高度是预算内的，多一行 Label
        会把下面的按钮挤出窗口（布局铁律）。同一个人同一个形态只说一次。
        """
        key = (self._attacker_id, form.get("id"))
        if self._form_noted == key:
            return
        self._form_noted = key
        traits = list(form.get("traits") or ())
        modeled = "、".join(row["name"] for row in traits if row.get("attack_mode"))
        texts = "、".join(row["name"] for row in traits if not row.get("attack_mode"))
        bits = []
        if modeled:
            bits.append("%s 按场上位置自动判定优势" % modeled)
        if texts:
            bits.append("%s 只有文字（未建模）" % texts)
        self._say("形态 %s：天然武器按卡上的数算%s"
                  % (form.get("name") or form.get("id"),
                     "；" + "；".join(bits) if bits else "；这个形态没有特性"))

    def _combatant(self, ident: str):
        if not self.encounter or not ident:
            return None
        for row in (self._view().get("order") or []):
            if row["id"] != ident:
                continue
            for combatant in self.encounter.combatants:
                if combatant.id == ident:
                    return {"label": row["label"], "actor": combatant.actor,
                            "row": row, "combatant": combatant}
        return None

    def _view(self) -> dict:
        if not self.encounter:
            return {}
        return api.encounter_view(self.encounter, self.app.bundle, self.app.locale)

    # --- 开战 -------------------------------------------------------------
    def add_monster(self, rng=None) -> bool:
        picked = self.roster_pane.selected_id()
        if not picked:
            self._say("先在左边挑一只怪物。", error=True)
            return False
        index = 1 + sum(1 for actor in self._attendees
                        if str(actor.id).split("#", 1)[0] == picked)
        actor = api.spawn_monster(self.app.bundle, picked, index)
        self._attendees.append(actor)
        if self.encounter is not None:
            api.join_encounter(self.encounter, self.app.bundle, actor, rng=rng)
        self._append("%s 加入。" % actor.display_name)
        self._say("已加入 %s。" % actor.display_name)
        self.app.refresh()
        return True

    def clear_all(self) -> None:
        """清空这一场。**只有这里会丢状态** —— 战斗本来就不进存档。"""
        self.encounter = None
        self._attendees = []
        self._attacker_id = ""
        self._target_id = ""
        self._action_key = ""
        self._form_noted = None
        self._log = []
        self.log.set_text("")
        self._say("已清空。")
        self.app.refresh()

    def start(self, rng=None) -> bool:
        if self.encounter is not None and self.encounter.round:
            self._say("这一场已经开始了；要重开请先「清空」。", error=True)
            return False
        actors = [self.app.actor] + list(self._attendees)
        if len(actors) < 2:
            self._say("至少要有一个人和一只怪物。", error=True)
            return False
        self.encounter = api.new_encounter(actors, rng=rng)
        view = self._view()
        self._append("=== 第 1 轮 ===")
        self._say("先攻序：%s" % " → ".join(row["label"] for row in view["order"]))
        self._attacker_id = view.get("current") or ""
        self.app.refresh()
        return True

    def next_turn(self) -> bool:
        if not self.encounter:
            self._say("还没开战。", error=True)
            return False
        info = api.advance_turn(self.encounter)
        self._append("=== 第 %d 轮 · 轮到 %s ===" % (info["round"], info["label"]))
        self._attacker_id = info["current"]
        self._say("轮到 %s。" % info["label"])
        self.app.refresh()
        return True

    def toggle_side(self) -> bool:
        """把先攻条里选中的人换到另一边（我方 ↔ 敌方）。

        群体战术只认阵营 —— 魅惑倒戈的狼、临时倒戈的盟友都靠这个按钮表达，
        程序不猜，只记账。
        """
        if not self.encounter:
            self._say("还没开战。", error=True)
            return False
        picked = self.order_pane.selected_id()
        if not picked:
            self._say("先在先攻条里点一个人。", error=True)
            return False
        row = next((item for item in (self._view().get("order") or [])
                    if item["id"] == picked), None)
        new_side = "foes" if row and row.get("side") == "party" else "party"
        word = "我方" if new_side == "party" else "敌方"
        try:
            info = api.set_combatant_side(self.encounter, picked, new_side)
        except api.DndError as exc:
            self._say(str(exc), error=True)
            return False
        self._append("%s 改为%s。" % (info["label"], word))
        self._say("%s 现在算%s。" % (info["label"], word))
        self.app.refresh()
        return True

    # --- 选择 -------------------------------------------------------------
    def _select_attacker(self) -> None:
        picked = self.order_pane.selected_id()
        if not picked or picked == self._attacker_id:
            return
        self._attacker_id = picked
        self._action_key = ""
        self._fill_targets()
        self._fill_actions()
        self._check_buttons()

    def _select_target(self) -> None:
        picked = self.target_pane.selected_id()
        if picked:
            self._target_id = picked
        self._check_buttons()

    def _select_action(self) -> None:
        picked = self.action_pane.selected_id()
        if picked:
            self._action_key = picked
        self._check_buttons()

    def _check_buttons(self) -> None:
        ready = bool(self.encounter and self._attacker_id
                     and self._target_id and self._action_key)
        self.roll_button.configure(state="normal" if ready else "disabled")
        self.next_button.configure(state="normal" if self.encounter else "disabled")
        self.side_button.configure(state="normal" if self.encounter else "disabled")
        self.start_button.configure(
            state="disabled" if (self.encounter and self.encounter.round) else "normal")

    # --- 地图 -------------------------------------------------------------
    def _on_canvas_click(self, event) -> None:
        if not self.encounter:
            return
        x, y = int(event.x) // CELL, int(event.y) // CELL
        if not (0 <= x < COLS and 0 <= y < ROWS):
            return
        picked = self.order_pane.selected_id()
        if not picked:
            self._say("先在先攻条里点一个人，再点格子。", error=True)
            return
        mode = self._mode.get()
        try:
            if mode == "place":
                info = api.place_combatant(self.encounter, picked, x, y)
                self._append("%s 摆到 (%d,%d)。" % (info["label"], x, y))
            elif mode == "teleport":
                info = api.teleport_combatant(self.encounter, picked, x, y,
                                              TELEPORT_FEET)
                self._append("%s 传送到 (%d,%d)，%d 尺。"
                             % (info["label"], x, y, info["feet"]))
            else:
                info = api.move_combatant(self.encounter, picked, x, y)
                self._append("%s 走到 (%d,%d)，花了 %d 尺，剩 %d 尺。"
                             % (info["label"], x, y, info["feet"], info["left"]))
                for row in info.get("left_reach") or []:
                    self._append("  ↳ %s 可以对他借机攻击%s"
                                 % (row["label"], "" if row["reaction"]
                                    else "（但这一轮的反应已用掉）"))
        except api.DndError as exc:
            self._say(str(exc), error=True)
            return
        self._say("已移动 %s。" % self._combatant(picked)["label"]
                  if self._combatant(picked) else "已移动。")
        self.app.refresh()

    def _draw_map(self) -> None:
        self.canvas.delete("all")
        for col in range(COLS + 1):
            self.canvas.create_line(col * CELL, 0, col * CELL, ROWS * CELL,
                                    fill=theme.MAP_GRID)
        for row in range(ROWS + 1):
            self.canvas.create_line(0, row * CELL, COLS * CELL, row * CELL,
                                    fill=theme.MAP_GRID)
        view = self._view()
        for index, row in enumerate(view.get("order") or []):
            cx = int(row["x"]) * CELL + CELL // 2
            cy = int(row["y"]) * CELL + CELL // 2
            if not (0 <= cx < COLS * CELL and 0 <= cy < ROWS * CELL):
                continue
            if row["id"] == self._attacker_id:
                fill, outline = theme.MAP_PC_FILL, theme.MAP_PC_EDGE
            elif row.get("active"):
                fill, outline = theme.MAP_FOE_FILL, theme.MAP_FOE_EDGE
            else:
                fill, outline = theme.MAP_NEUTRAL_FILL, theme.MAP_NEUTRAL_EDGE
            if row.get("down"):
                fill, outline = theme.MAP_EMPTY_FILL, theme.MAP_EMPTY_EDGE
            self.canvas.create_oval(cx - 15, cy - 15, cx + 15, cy + 15,
                                    fill=fill, outline=outline, width=2)
            # 同格的人叠在一起时错开 2px，至少看得出「不止一个人」
            self.canvas.create_text(cx, cy + index % 3, text=row["label"][:2],
                                    fill=theme.MAP_TEXT, font=(theme.UI_FONT, 8))

    # --- 出手 -------------------------------------------------------------
    def roll(self, apply: bool, rng=None) -> bool:
        """掷一次。`apply=False` 是预览：掷骰、算数，但不改任何人的血与额度。"""
        if not (self.encounter and self._attacker_id and self._target_id
                and self._action_key):
            self._say("先把出手的人、目标、动作都选好。", error=True)
            return False
        attacker = self._combatant(self._attacker_id)
        target = self._combatant(self._target_id)
        if attacker is None or target is None:
            self._say("这两个人不在场上了。", error=True)
            return False
        actor = attacker["actor"]
        kind = api.actor_view(actor, self.app.locale).get("kind")
        morphed = bool(api.form_view(actor, self.app.bundle,
                                     self.app.locale).get("morphed"))
        manual = {"优势": "adv", "劣势": "dis", "平掷": "flat"}.get(
            self.mode_var.get(), "")
        try:
            if kind == "pc" and not morphed:
                if manual:
                    self._append("  · 玩家武器攻击暂不支持手动指定掷骰模式"
                                 "（按角色自己的优势/劣势判定）")
                result = api.attack_roll(
                    actor, self.app.bundle, target["actor"],
                    weapon=self._action_key, apply=apply, rng=rng,
                    encounter=self.encounter)
            else:
                # 怪物与变形中的角色走同一条：命中加值取卡上的数、按槽位付额度；
                # 掷骰模式默认按特性事实判定（群体战术），手动指定优先
                result = api.monster_attack(
                    self.encounter, self.app.bundle, actor, self._action_key,
                    target["actor"], rng=rng, apply=apply, mode=manual)
        except api.DndError as exc:
            self._say(str(exc), error=True)
            return False
        self._append(_describe(result, attacker["label"], target["label"], apply))
        self._say("预览：没有改任何人的血。" if not apply
                  else "%s → %s：%s" % (attacker["label"], target["label"],
                                        _outcome_zh(result)))
        self.app.refresh()
        return True

    # --- 输出 -------------------------------------------------------------
    def _append(self, text: str) -> None:
        self._log.append(text)
        self._log = self._log[-40:]
        self.log.set_text("\n".join(self._log))

    def _say(self, text: str, error: bool = False) -> None:
        self.status_var.set(text)
        self.status.configure(foreground=theme.WARN if error else theme.DIM)


def _attack_rows(actions: list[dict]) -> list[dict]:
    """把 `attack_options` 的行拼成「名字 +命中（豁免 DC）」。

    怪物与形态给的是同一个形状（`slot:index` 键 + `attack_bonus` / `save`），
    所以这里只管标字，不管它来自哪张卡。
    """
    rows: list[dict] = []
    for row in actions:
        label = row["name"]
        if row.get("attack_bonus") is not None:
            label += " %+d" % int(row["attack_bonus"])
        if row.get("save"):
            label += "（%s 豁免 DC %d）" % (row["save"].upper(), int(row["save_dc"]))
        rows.append({"key": row["key"], "name": label, "kind": row.get("kind")})
    return rows


def _outcome_zh(result: dict) -> str:
    if result.get("outcome") == "save_required":
        return "要目标掷豁免（见记录）"
    if not result.get("rolled", True):
        return "没有可掷的数值（见记录）"
    if result.get("outcome") == "critical":
        return "重击，%d 点伤害" % result["damage"]["total"]
    if result.get("outcome") == "hit":
        return "命中，%d 点伤害" % result["damage"]["total"]
    return "未命中"


def _describe(result: dict, attacker: str, target: str, apply: bool) -> str:
    """把报告摊成几行字。数字全部来自 api，这里只排版。"""
    lines = ["[%s] %s → %s（AC %d）"
             % ("结算" if apply else "预览", attacker, target,
                int(result["target"]["ac"]))]
    attack = result.get("attack")
    if attack:
        mode = {"adv": "（优势）", "dis": "（劣势）"}.get(attack.get("mode"), "")
        sources = attack.get("mode_sources") or []
        if mode and sources:
            mode = "%s · %s" % (mode.strip("（）"), "、".join(sources))
            mode = "（%s）" % mode
        lines.append("  d20 %d %+d = %d%s" % (int(attack["die"]), int(attack["bonus"]),
                                              int(attack["total"]), mode))
    for row in result["damage"].get("breakdown") or []:
        lines.append("  %s：%s = %d（%s）" % (row["label"], row["roll"],
                                            int(row["damage"]),
                                            row["damage_type_zh"] or "—"))
    lines.append("  结果：%s" % _outcome_zh(result))
    for note in result.get("notes") or []:
        lines.append("  · %s" % note)
    return "\n".join(lines)
