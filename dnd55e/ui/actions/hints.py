"""悬停提示文案 (写进 HintText, 固定行高不撑版面)。"""
import random
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from ... import consts, util
from ...consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                       size_cn, subclass_cn, tool_cn)
from ...dialogs import (FeatPickerDialog, MetamagicDialog, SpellbookDialog,
                        WildShapeDialog)
from ...rules import Rules
from ...theme import BG, GOLD2
from ...util import (ability_mod, mod_str, roll_dice, roll_dice_reroll,
                     spell_detail)


class HintsMixin:
    def _ability_hint(self, ab):
        self.ab_hint.config(
            text=f"{ABILITY_CN[ab]} ({ab}): {consts.ABILITY_DESC.get(ab, '')}",
            foreground=GOLD2)

    def _skill_hover(self, sid):
        sk = self.rules.skill_by_id[sid]
        c = self.char
        extra = ""
        if c:
            extra = f" · 当前 {mod_str(c.skill_mod(sid))}"
            if sid in c.expertise:
                extra += " (专精 ×2)"
            elif sid in c.skill_prof:
                extra += " (熟练)"
        self.skill_hint.config(
            text=f"{sk['name']} ({ABILITY_CN[sk['ability']]}) —— "
                 f"{consts.SKILL_DESC.get(sid, '')}{extra}",
            foreground=GOLD2)

    def _cond_hint(self, cond):
        self.cond_hint.config(
            text=f"{cond}: {consts.CONDITION_DESC.get(cond, '')}", foreground=GOLD2)

    def _item_hint(self, it):
        # 新物品只有 desc、没有 note (note 是旧 12 条的短摘要), 两者取其一
        note = it.get("note") or it.get("desc", "")
        if len(note) > 76:                # 提示行固定 2 行高, 超长截断防止撑开
            note = note[:75] + "…"
        self.item_hint.config(text=f"{it['name']} —— {note}",
                              foreground=GOLD2)
