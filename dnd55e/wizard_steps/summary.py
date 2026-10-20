"""步骤 7: 汇总确认。"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from .. import consts, util
from ..character import Character
from ..consts import (ABILITIES, ABILITY_CN, ARMOR_PROF_CN, CAST_MODE_CN,
                      CAST_TYPE_CN, WEAPON_PROF_CN, feat_cn, feat_desc,
                      mastery_cn, size_cn, subclass_cn, tool_cn)
from ..rules import Rules
from ..theme import (BG, DIM, GOLD2, LISTBOX_STYLE, PURPLE, TEXT, TXT_BG,
                     HintText)
from ..util import (ab_from_display, ability_mod, mod_str,
                    proficiency_bonus, roll_4d6kh3, spell_detail)


class SummaryMixin():
    def _step_summary(self):
        f = ttk.Frame(self.container)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="摘要确认", font=("", 13, "bold")).pack(anchor="w")
        txt = tk.Text(f, height=22, wrap="word", state="disabled", background=TXT_BG, foreground=TEXT, insertbackground=TEXT, relief="flat", width=1)
        txt.pack(fill="both", expand=True, pady=6)

        cls = self.r.cls(self.data["class_id"])
        bg = self.r.bg(self.data["background_id"])
        sp = self.r.sp(self.data["species_id"])
        tmp = self._build_char()
        scores = tmp.scores()
        mods = tmp.mods()
        skills = "、".join(
            self.r.skill_by_id[s]["name"]
            for s in sorted(self.data["skill_prof"],
                            key=lambda x: self.r.skill_by_id[x]["name"]))
        sp_note = "（背景加值, 种族不加属性）"
        spells = self.data.get("spells") or {}
        spell_lines = []
        if spells.get("cantrips"):
            spell_lines.append("戏法: " + "、".join(
                self.r.spell(s)["name"] for s in spells["cantrips"] if self.r.spell(s)))
        if spells.get("prepared"):
            spell_lines.append("1 环: " + "、".join(
                self.r.spell(s)["name"] for s in spells["prepared"] if self.r.spell(s)))
        lines = [
            f"姓名: {self.data['name']}    等级: 1",
            f"职业: {cls['name']}    子职: (3级解锁)",
            f"背景: {bg['name']} [专长 {feat_cn(bg['origin_feat'])}]    "
            f"种族: {sp['name']}",
            "",
            f"属性{sp_note}: " + "   ".join(
                f"{ABILITY_CN[a]} {scores[a]}({mod_str(mods[a])})"
                for a in ABILITIES),
            f"生命值: {tmp.hp_max()}    AC: {tmp.ac()}    "
            f"先攻: {mod_str(tmp.initiative())}",
            f"熟练加值: +2    被动察觉: {tmp.passive_perception()}",
            f"豁免熟练: {'、'.join(ABILITY_CN[a] for a in cls['saves'])}",
            f"技能熟练 ({len(self.data['skill_prof'])} 项): {skills}",
            f"工具熟练: {tool_cn(bg['tool'])}",
            f"武器专精: {', '.join(self.data['weapon_mastery']) or '— (该职业无)'}",
            f"种族额外专长: {feat_cn(self.data['human_feat'])}"
            if self.data.get("human_feat") else "",
            ("法术 —— " + " ｜ ".join(spell_lines)) if spell_lines else "",
            "",
            "说明: 装备、魔法物品与加成明细请在角色卡「装备·武器」页设置;",
            "      法术可在角色卡「法 术」页随时增删与施放。",
        ]
        txt.config(state="normal")
        txt.insert("1.0", "\n".join(lines))
        txt.config(state="disabled")
