# -*- coding: utf-8 -*-
"""法术页：施法数值 + 戏法/准备法术的挑选。

这一页是第一个**会写数据**的页面，所以有三条硬规矩：

  1. 校验全在 `api.plan_spells` 里（配额、环级上限、是否在本职业表），
     界面只负责「点了就提交」，不自己判断能不能选 —— 判断写在两处必然分叉。
  2. 提交失败时显示错误、**不改档案**，清单回到服务端的状态（不留下假勾选）。
  3. 不弹窗。错误显示在页面底部一行红字里 —— 弹窗会挡住角色卡，
     而且自检里一弹就挂（铁律）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import dnd5r.api as api

from .widgets import COL_LEFT, COL_MID, COL_RIGHT, KeyValue, ListPane, ScrollText, section

MARK_CHOSEN = "✓ "
MARK_EMPTY = "　"
ABILITY_ZH = {"str": "力量", "dex": "敏捷", "con": "体质",
              "int": "智力", "wis": "感知", "cha": "魅力"}
SCHOOL_ZH = {
    "abjuration": "防护", "conjuration": "咒法", "divination": "预言",
    "enchantment": "附魔", "evocation": "塑能", "illusion": "幻术",
    "necromancy": "死灵", "transmutation": "变化",
}
CAST_ZH = {"action": "1 动作", "bonus": "1 附赠动作", "reaction": "1 反应",
           "time": "长时", "special": "特殊"}


def _spell_line(row: dict, chosen: bool) -> str:
    """一行清单：勾选标记 + 环级 + 名称 + 学派。环级写在左边对齐才好扫。"""
    level = int(row.get("level") or 0)
    head = "戏法" if level == 0 else "%d 环" % level
    school = SCHOOL_ZH.get(str(row.get("school") or ""), "")
    return "%s%s  %s  %s" % (MARK_CHOSEN if chosen else MARK_EMPTY,
                             head, row["name"], school)


def _chosen_ids(bucket: dict) -> list[str]:
    """`chosen` 是带名字的小行（id/level/name），这里只要 id —— 界面按 id 比对。"""
    return [str(row["id"]) if isinstance(row, dict) else str(row)
            for row in (bucket.get("chosen") or [])]


SCALING_ZH = {"damage": "伤害骰", "extra_damage": "额外伤害",
              "beams": "光束数", "range": "射程（尺）", "weapon_die": "武器骰"}
# 豁免成功后的伤害。「未判定」那一档必须写成一句人话，
# 留空会让人以为是「豁免成功也没事」——那是另一条规则。
SAVE_EFFECT_ZH = {"half": "豁免成功半伤", "none": "豁免成功无伤",
                  "": "豁免成功的伤害见原文"}

# --- 召唤物 stat block 的词汇表 ---------------------------------------
# 放前端而不是内核：这是**显示**用的对照表，内核只认英文键（约束 C1/C3）。
CREATURE_ZH = {
    "aberration": "异怪", "beast": "野兽", "celestial": "天界生物",
    "construct": "构装", "dragon": "龙", "elemental": "元素",
    "fey": "妖精", "fiend": "邪魔", "giant": "巨人", "humanoid": "类人",
    "monstrosity": "怪诞生物", "ooze": "泥怪", "plant": "植物", "undead": "亡灵",
}
SIZE_ZH = {"tiny": "微型", "small": "小型", "medium": "中型",
           "large": "大型", "huge": "巨型", "gargantuan": "超巨型"}
SPEED_ZH = {"walk": "步行", "climb": "攀爬", "swim": "游泳",
            "fly": "飞行", "burrow": "掘道"}
SENSE_ZH = {"blindsight": "盲视", "darkvision": "黑暗视觉",
            "tremorsense": "震颤感知", "truesight": "真实视觉"}
DAMAGE_ZH = {
    "acid": "强酸", "bludgeoning": "钝击", "cold": "冷冻", "fire": "火焰",
    "force": "力场", "lightning": "闪电", "necrotic": "黯蚀", "piercing": "穿刺",
    "poison": "毒素", "psychic": "心灵", "radiant": "光耀", "slashing": "挥砍",
    "thunder": "雷鸣",
}
CONDITION_ZH = {
    "blinded": "目盲", "charmed": "魅惑", "deafened": "耳聋", "exhaustion": "力竭",
    "frightened": "恐惧", "grappled": "受擒", "incapacitated": "失能",
    "invisible": "隐形", "paralyzed": "麻痹", "petrified": "石化",
    "poisoned": "中毒", "prone": "倒地", "restrained": "束缚",
    "stunned": "震慑", "unconscious": "昏迷",
}
AREA_ZH = {"cone": "锥形", "line": "线形", "sphere": "球形",
           "cube": "立方", "cylinder": "柱形"}


def _signed(value: int) -> str:
    return "%+d" % int(value)


def _damage_text(part: dict, word: str = "伤害") -> str:
    """一段伤害：`1d6+9 穿刺` / `2d6+3+施法调整值 力场`。"""
    bits = [str(part.get("at_slot") or "?")]
    if part.get("caster_mod"):
        bits.append("施法调整值")
    kind = DAMAGE_ZH.get(str(part.get("type") or ""), str(part.get("type") or ""))
    if kind:
        bits.append(kind)
    label = part.get("label") or {}
    text = " ".join(bits)
    if label.get("zh"):
        text += "（%s）" % label["zh"]
    return "%s %s" % (word, text)


def _action_line(action: dict) -> str:
    """一条动作 / 特性：名称 + 命中/豁免 + 伤害 + 说明。"""
    kind = str(action.get("kind") or "other")
    head = str(action.get("name") or "")
    bits = []
    if kind == "melee":
        bits.append("近战，触及 %d 尺" % int(action.get("reach") or 0))
    elif kind == "ranged":
        bits.append("远程，射程 %d 尺" % int(action.get("range") or 0))
    if action.get("attack") == "spell":
        bits.append("命中＝你的法术攻击加值")
    if action.get("save"):
        where = ""
        area = action.get("area")
        if area:
            where = "，%d 尺%s" % (int(area[1]), AREA_ZH.get(str(area[0]), str(area[0])))
        elif action.get("range"):
            where = "，%d 尺内" % int(action["range"])
        bits.append("%s豁免（DC＝你的法术豁免 DC%s）"
                    % (ABILITY_ZH.get(str(action["save"]), str(action["save"])), where))
    word = "回复" if kind == "heal" else "伤害"
    damage = [_damage_text(part, "").strip() for part in (action.get("damage") or [])]
    if damage:
        # 按体型分叉的（活化物件）用「／」并排，加一次词头就够，别每条都写「伤害」。
        bits.append("%s %s" % (word, "／".join(damage)))
    line = "%s：%s" % (head, "；".join(bits)) if bits else head
    text = str(action.get("text") or "")
    if text:
        line += "\n    " + text
    return line


def summon_text(row: dict, slot: int = 0) -> str:
    """一张召唤物 stat block。`row` 是 `spell_info(...)["summons"]` 的一项。"""
    card = row.get("card") or {}
    name = str(card.get("name") or "")
    if card.get("variant"):
        name = "%s（%s）" % (name, card["variant"])
    size = str(row.get("size_note") or SIZE_ZH.get(str(card.get("size") or ""), ""))
    kind = CREATURE_ZH.get(str(card.get("creature_type") or ""),
                           str(card.get("creature_type") or ""))
    parts = ["【%s】%s %s" % (name, size, kind)]
    slot = int(slot or card.get("slot_level") or 0)
    options = card.get("hp_options") or {}
    if slot:
        if options:
            parts.append("%d 环时：AC %d" % (slot, int(card.get("ac") or 0)))
        else:
            parts.append("%d 环时：AC %d，生命值 %d（%s）"
                         % (slot, int(card.get("ac") or 0), int(card.get("hp") or 0),
                            str(card.get("ac_text") or "")))
    if options:
        parts.append("生命值按体型：%s"
                     % "／".join("%s %d" % (SIZE_ZH.get(key, key), value)
                                 for key, value in options.items()))
    if card.get("hp_dice"):
        parts.append("生命骰：%s" % card["hp_dice"])
    speeds = card.get("speeds") or {}
    if speeds:
        parts.append("速度：" + "，".join("%s %d 尺" % (SPEED_ZH.get(key, key), value)
                                        for key, value in speeds.items()))
    locked = card.get("speeds_locked") or {}
    if locked:
        parts.append("尚未解禁：" + "，".join(
            "%s %d 尺要 %d 环起" % (SPEED_ZH.get(key, key), int(item["value"]),
                                   int(item["slot"]))
            for key, item in locked.items()))
    scores = card.get("abilities") or {}
    if scores:
        row_bits = []
        for key in ("str", "dex", "con", "int", "wis", "cha"):
            score = int(scores.get(key) or 0)
            row_bits.append("%s %d（%s）" % (ABILITY_ZH[key], score,
                                            _signed((score - 10) // 2)))
        parts.append("　".join(row_bits))
    senses = card.get("senses") or {}
    sensory = ["%s %d 尺" % (SENSE_ZH.get(key, key), value)
               for key, value in senses.items()]
    sensory.append("被动察觉 %d" % int(card.get("passive_perception") or 0))
    parts.append("感官：" + "，".join(sensory))
    if card.get("languages"):
        parts.append("语言：" + str(card["languages"]))
    for tag, key, table in (("抗性", "resistances", DAMAGE_ZH),
                            ("伤害免疫", "immunities", DAMAGE_ZH),
                            ("状态免疫", "condition_immunities", CONDITION_ZH)):
        values = card.get(key) or []
        if values:
            parts.append("%s：%s" % (tag, "，".join(table.get(item, item)
                                                    for item in values)))
    for group, title in (("traits", "特性"), ("actions", "动作"),
                         ("bonus_actions", "附赠动作"), ("reactions", "反应")):
        rows = card.get(group) or []
        if not rows:
            continue
        parts.append("")
        parts.append(title + "：")
        parts.extend(_action_line(item) for item in rows)
    curve = row.get("by_slot") or []
    # 曲线全平时不画：活化物件的 AC/HP 跟环级无关，列 5 行一模一样的数字只会误导。
    if len({(int(item["ac"]), int(item["hp"])) for item in curve}) > 1:
        parts.append("")
        parts.append("升环：" + "　".join("%d 环 AC %d／HP %d"
                                         % (int(item["slot"]), int(item["ac"]),
                                            int(item["hp"])) for item in curve[:5])
                     + ("……" if len(curve) > 5 else ""))
    if card.get("note"):
        parts.append("")
        parts.append("注：" + str(card["note"]))
    return "\n".join(parts)


def spell_text(row: dict, info: dict | None = None) -> str:
    """一条法术的完整说明（右栏）。用选项行里现成的字段拼，不查第二遍表。"""
    level = int(row.get("level") or 0)
    parts = ["%s（%s）" % (row["name"], "戏法" if level == 0 else "%d 环" % level)]
    cast = row.get("cast") or {}
    bits = []
    if cast.get("text"):
        bits.append("施法 " + str(cast["text"]))
    if (row.get("range") or {}).get("text"):
        bits.append("距离 " + str(row["range"]["text"]))
    if row.get("components"):
        bits.append("成分 " + "".join(str(item).upper() for item in row["components"]))
    if (row.get("duration") or {}).get("text"):
        bits.append("持续 " + str(row["duration"]["text"]))
    if bits:
        parts.append("　".join(bits))
    extra = []
    if row.get("concentration"):
        extra.append("专注")
    if row.get("ritual"):
        extra.append("仪式")
    if row.get("save"):
        extra.append("%s 豁免" % ABILITY_ZH.get(str(row["save"]), str(row["save"])))
        # 「豁免成功吃多少」是能算出来的，就别让玩家再去英文原文里找。
        # 控制类法术（没有伤害表）不写这一句：那里根本没有「伤害多少」这回事。
        effect = str(row.get("save_effect") or "")
        if effect:
            extra.append(SAVE_EFFECT_ZH[effect])
        elif row.get("damage"):
            extra.append(SAVE_EFFECT_ZH[""])
    if row.get("attack"):
        extra.append("法术攻击")
    if extra:
        parts.append(" / ".join(item for item in extra if item))
    if row.get("text"):
        parts.append("")
        parts.append(str(row["text"]))
    damage = row.get("damage") or {}
    if damage:
        parts.append("")
        parts.append("伤害：" + "；".join("%s 环 %s" % (slot, dice)
                                         for slot, dice in sorted(damage.items())))
        if row.get("damage_type"):
            parts.append("伤害类型：%s" % row["damage_type"])
    summons = (info or {}).get("summons") or []
    if row.get("upcast") and not summons:
        # 召唤类法术的 `upcast` 是整段英文 stat block 原文，下方已经有结构化卡片，
        # 再贴一遍是两套文案、两处会漂移。
        parts.append("升环：" + str(row["upcast"]))
    # 戏法成长：**不是**环位伤害表的一部分，5/11/17 看的是角色等级
    scaling = row.get("scaling") or {}
    levels = scaling.get("levels") or {}
    if levels:
        tag = SCALING_ZH.get(str(scaling.get("kind")), str(scaling.get("kind")))
        parts.append("戏法成长（%s）：%s"
                     % (tag, " / ".join("%s 级 %s" % (level, value)
                                        for level, value in sorted(levels.items()))))
        if info and info.get("scaling_now"):
            parts.append("你现在 %s 级，按 %s 算"
                         % (info.get("character_level"), info["scaling_now"]))
    for summon in summons:
        parts.append("")
        parts.append(summon_text(summon))
    return "\n".join(parts)


class SpellPage(ttk.Frame):
    """法术页。`app` 只用三样东西：actor / bundle / refresh()。"""

    def __init__(self, master, app) -> None:
        super().__init__(master, padding=(6, 4))
        self.app = app
        self._blocks: list[dict] = []
        self._index = 0
        self._busy = False
        self._build()

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

        # 状态行先 pack 到底部：内容撑高时不许把它挤没（布局铁律）
        self.status_var = tk.StringVar(value="")
        self.status = ttk.Label(self, textvariable=self.status_var, anchor="w")
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        # --- 左：施法数值 + 法术位 -------------------------------------
        head = section(left, "施法")
        head.pack(fill="x")
        self.class_var = tk.StringVar(value="")
        self.class_row = ttk.Frame(head)
        self.class_row.pack(fill="x")
        ttk.Label(self.class_row, textvariable=self.class_var,
                  font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        # 兼职会有多块施法（各算各的 DC 与法位），给一对切换按钮；
        # 只有一个施法职业时不显示 —— 没得切还摆个按钮只是噪声。
        self.switch_row = ttk.Frame(head)
        ttk.Button(self.switch_row, text="‹", width=3,
                   command=lambda: self._switch(-1)).pack(side="left")
        ttk.Button(self.switch_row, text="›", width=3,
                   command=lambda: self._switch(1)).pack(side="left", padx=(2, 0))
        self.head = KeyValue(head, rows=4)
        self.head.pack(fill="x", pady=(2, 0))

        slots = section(left, "法术位")
        slots.pack(fill="x", pady=(8, 0))
        self.slots = KeyValue(slots, rows=9)
        self.slots.pack(fill="x")

        # --- 中：戏法 / 准备法术 ---------------------------------------
        # ttk.LabelFrame 没有 textvariable（只有 tk.LabelFrame 有），标题只能 refresh 时改
        canti = ttk.LabelFrame(mid, text="戏法", padding=(8, 4))
        self.cantrip_frame = canti
        canti.pack(fill="both", expand=True)
        self.cantrips = ListPane(canti, height=8, width=44)
        self.cantrips.pack(fill="both", expand=True)
        self.cantrips.list.bind("<<ListboxSelect>>",
                                lambda _event: self._show_detail("cantrips"))

        prep = ttk.LabelFrame(mid, text="准备法术", padding=(8, 4))
        self.prep_frame = prep
        prep.pack(fill="both", expand=True, pady=(6, 0))
        self.prepared = ListPane(prep, height=13, width=44)
        self.prepared.pack(fill="both", expand=True)
        self.prepared.list.bind("<<ListboxSelect>>",
                                lambda _event: self._show_detail("prepared"))

        # --- 右：详情 + 操作 -------------------------------------------
        detail = section(right, "法术详情")
        detail.pack(fill="both", expand=True)
        self.detail = ScrollText(detail, height=18, width=30)
        self.detail.pack(fill="both", expand=True)

        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(6, 0))
        self.pick_button = ttk.Button(buttons, text="准备 / 取消",
                                      command=self.toggle_prepared)
        self.pick_button.pack(side="left")
        self.cantrip_button = ttk.Button(buttons, text="设为戏法 / 取消",
                                         command=self.toggle_cantrip)
        self.cantrip_button.pack(side="left", padx=(6, 0))

    # --- 数据 -------------------------------------------------------------
    def refresh(self, sheet: dict) -> None:
        self._busy = True
        try:
            self._blocks = list(sheet.get("spellcasting") or [])
            self._index = min(self._index, max(0, len(self._blocks) - 1))
            self._fill(sheet)
        finally:
            self._busy = False

    def _block(self) -> dict:
        return self._blocks[self._index] if self._blocks else {}

    def _switch(self, step: int) -> None:
        if len(self._blocks) < 2:
            return
        self._index = (self._index + step) % len(self._blocks)
        self.app.refresh()

    def _show_switch(self, visible: bool) -> None:
        if visible and not self.switch_row.winfo_manager():
            self.switch_row.pack(fill="x", pady=(2, 0))
        elif not visible and self.switch_row.winfo_manager():
            self.switch_row.pack_forget()

    def _class_name(self, class_id: str) -> str:
        class_def = self.app.bundle.classes.get(class_id)
        return class_def.name.get(self.app.locale) if class_def else class_id

    def _fill(self, sheet: dict) -> None:
        block = self._block()
        self._show_switch(len(self._blocks) > 1)
        if not block:
            self.class_var.set("这个角色不施法")
            self.head.clear()
            self.slots.clear()
            self.cantrips.fill([])
            self.prepared.fill([])
            self.cantrip_frame.configure(text="戏法")
            self.prep_frame.configure(text="准备法术")
            self.detail.set_text("")
            self._status("没有施法职业：本页只对施法者生效。")
            self._enable(False)
            return
        self._enable(True)

        name = self._class_name(block["class"])
        suffix = "" if len(self._blocks) == 1 else "（%d/%d）" % (self._index + 1,
                                                                len(self._blocks))
        self.class_var.set(name + suffix)
        self.head.clear()
        self.head.set_row(0, "施法属性", ABILITY_ZH.get(block["ability"], block["ability"]))
        self.head.set_row(1, "豁免 DC", str((block.get("dc") or {}).get("total", 0)))
        self.head.set_row(2, "法术攻击", "%+d" % (block.get("attack") or {}).get("total", 0))
        self.head.set_row(3, "最高环位", "%d 环" % int(block.get("highest_slot") or 0))

        self.slots.clear()
        for index, row in enumerate(block.get("slots") or []):
            self.slots.set_row(index, "%d 环" % row["level"],
                               "%d / %d" % (row["left"], row["max"]))

        self._fill_lists(block)

    def _fill_lists(self, block: dict) -> None:
        cantrips = block.get("cantrips") or {}
        chosen_cantrips = _chosen_ids(cantrips)
        rows = [(row["id"], _spell_line(row, row["id"] in chosen_cantrips))
                for row in cantrips.get("options") or []]
        self.cantrips.fill(rows)
        self.cantrip_frame.configure(
            text="戏法 %d / %d" % (len(chosen_cantrips), int(cantrips.get("max") or 0)))

        prepared = block.get("prepared") or {}
        chosen_prepared = _chosen_ids(prepared)
        rows = [(row["id"], _spell_line(row, row["id"] in chosen_prepared))
                for row in prepared.get("options") or []]
        self.prepared.fill(rows)
        self.prep_frame.configure(
            text="准备法术 %d / %d" % (len(chosen_prepared),
                                     int(prepared.get("max") or 0)))

        if not self._blocks or not self._block().get("prepared"):
            return
        remaining = (int(prepared.get("max") or 0) - len(chosen_prepared))
        if remaining > 0:
            self._status("还能准备 %d 个法术。" % remaining)
        else:
            self._status("准备名额已满；要换法术先取消一个。")

    def _enable(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.pick_button.configure(state=state)
        self.cantrip_button.configure(state=state)

    def _status(self, text: str, error: bool = False) -> None:
        self.status_var.set(text)
        self.status.configure(foreground="#a33" if error else "#666666")

    # --- 显示详情 ---------------------------------------------------------
    def _spell_options(self, kind: str) -> list[dict]:
        block = self._block()
        bucket = block.get(kind) or {}
        return list(bucket.get("options") or [])

    def _row(self, kind: str, spell_id: str) -> dict:
        for row in self._spell_options(kind):
            if row["id"] == spell_id:
                return row
        return {}

    def _show_detail(self, kind: str) -> None:
        pane = self.cantrips if kind == "cantrips" else self.prepared
        spell_id = pane.selected_id()
        row = self._row(kind, spell_id) if spell_id else {}
        if not row:
            self.detail.set_text("")
            return
        # 「当前等级对应哪一档」是规则，问 api；页面只负责把答案排成文本
        info = api.spell_info(self.app.bundle, spell_id,
                              character_level=int((self.app.sheet or {}).get("total_level") or 0))
        self.detail.set_text(spell_text(row, info))

    def show(self, kind: str, spell_id: str) -> str:
        """自检入口：选中某个法术并返回右栏文字（不依赖真实点击）。"""
        pane = self.cantrips if kind == "cantrips" else self.prepared
        pane.select_id(spell_id)
        self._show_detail(kind)
        return self.detail.text.get("1.0", "end").strip()

    # --- 写数据 -----------------------------------------------------------
    def toggle_prepared(self) -> bool:
        return self._toggle("prepared")

    def toggle_cantrip(self) -> bool:
        return self._toggle("cantrips")

    def _toggle(self, kind: str) -> bool:
        """把清单里选中的那条加进/移出选择。返回是否成功（自检要看这个）。"""
        if self._busy or not self._blocks:
            return False
        block = self._block()
        pane = self.cantrips if kind == "cantrips" else self.prepared
        spell_id = pane.selected_id()
        if not spell_id:
            self._status("先在清单里选一个法术。", error=True)
            return False

        chosen = _chosen_ids(block.get(kind) or {})
        if spell_id in chosen:
            chosen.remove(spell_id)
            action = "取消"
        else:
            chosen.append(spell_id)
            action = "选定"

        actor = self.app.actor
        try:
            if kind == "cantrips":
                api.plan_spells(actor, self.app.bundle, block["class"],
                                cantrips=chosen, locale=self.app.locale)
            else:
                api.plan_spells(actor, self.app.bundle, block["class"],
                                prepared=chosen, locale=self.app.locale)
        except api.DndError as error:
            # 校验失败：档案没动，清单回到服务端状态。
            # 顺序不能反 —— 先 refresh（它会写「还能准备 N 个」），再写错误，
            # 否则错误立刻被那句友好提示盖掉，玩家看不到为什么没生效。
            self.app.refresh()
            self._restore_selection(kind, spell_id)
            self._status(str(error), error=True)
            return False

        self.app.refresh()
        self._restore_selection(kind, spell_id)
        self._show_detail(kind)
        self._status("已%s「%s」。" % (action, self._row(kind, spell_id).get("name", spell_id)))
        return True

    def _restore_selection(self, kind: str, spell_id: str) -> None:
        pane = self.cantrips if kind == "cantrips" else self.prepared
        pane.select_id(spell_id)
