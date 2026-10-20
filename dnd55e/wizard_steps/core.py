"""向导骨架: 初始化 / 步骤导航 / 校验派发 / 最终组装角色。"""
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


class WizardCore():
    def __init__(self, master, rules, on_finish):
        super().__init__(master)
        if not master.winfo_viewable():   # 后台测试: 父窗口不可见时不弹出
            self.withdraw()
        self.r = rules
        self.on_finish = on_finish
        self.title("新建角色 · D&D 5.5e 建卡向导")
        self.geometry("740x720")
        self.minsize(700, 560)
        self.transient(master)
        self.configure(bg=BG)
        try:
            self.grab_set()
        except tk.TclError:
            pass

        self.data = {
            "name": "", "class_id": None, "background_id": None,
            "species_id": None, "base_scores": {}, "bg_bonus": None,
            "skill_prof": set(), "bonus_skills": set(),
            "weapon_mastery": [], "human_feat": None, "order": None,
        }
        self.step = 0
        self.steps = [self._step_class, self._step_background, self._step_species,
                      self._step_abilities, self._step_skills]
        if True:  # 武器专精步骤按职业条件插入
            self.steps.append(self._step_mastery)
        self.steps.append(self._step_spells)      # 仅施法职业显示
        self.steps.append(self._step_summary)

        # 底部导航必须先 pack (side=bottom): pack 按顺序分配空间,
        # 后 pack 的侧栏永远先拿到空间, 内容再高也不会把导航挤出窗口
        self.progress = ttk.Label(self, text="", anchor="center",
                                  padding=(0, 4))
        self.progress.pack(fill="x", side="bottom")
        nav = ttk.Frame(self, padding=(10, 4))
        nav.pack(fill="x", side="bottom")
        self.btn_prev = ttk.Button(nav, text="← 上一步", command=self.prev,
                                   state="disabled")
        self.btn_prev.pack(side="left", padx=4)
        self.btn_next = ttk.Button(nav, text="下一步 →", command=self.next)
        self.btn_next.pack(side="right", padx=4)

        self.container = ttk.Frame(self, padding=10)
        self.container.pack(fill="both", expand=True)
        self.render_step()

    def render_step(self):
        for w in self.container.winfo_children():
            w.destroy()
        vis = [i for i in range(len(self.steps)) if not self._skip(i)]
        pos = vis.index(self.step) + 1 if self.step in vis else 1
        self.progress.config(text=f"第 {pos} / {len(vis)} 步")
        self.btn_prev.config(state="normal" if vis[0] != self.step else "disabled")
        self.btn_next.config(
            text="完成 ✓" if self.step == vis[-1] else "下一步 →")
        self.steps[self.step]()

    def _skip(self, idx):
        """某些步骤按职业条件跳过 (如无法术职业跳过选法术)"""
        fn = self.steps[idx]
        if fn == self._step_spells:
            cid = self.data.get("class_id")
            if not (cid and self.r.cls(cid).get("casting")):
                return True
            # 本地法术库缺失时不卡住建卡, 直接跳过
            return not self.r.class_spells(cid)
        return False

    def prev(self):
        prv = self.step - 1
        while prv > 0 and self._skip(prv):
            prv -= 1
        if prv >= 0:
            self.step = prv
            self.render_step()

    def next(self):
        if not self.validate_step():
            return
        vis = [i for i in range(len(self.steps)) if not self._skip(i)]
        if self.step == vis[-1]:
            self.finish()
            return
        nxt = self.step + 1
        while nxt < len(self.steps) - 1 and self._skip(nxt):
            nxt += 1
        self.step = nxt
        self.render_step()

    def validate_step(self):
        fn = getattr(self, f"_validate_{self.step}", None)
        return fn() if fn else True

    def _build_char(self):
        """按向导当前数据构造角色 —— 摘要页与 finish 共用同一份逻辑,
        避免两处字段不同步 (曾因漏设字段导致摘要页崩)。"""
        char = Character(self.r)
        char.name = self.data.get("name") or "无名冒险者"
        char.class_id = self.data.get("class_id") or char.class_id
        char.background_id = self.data.get("background_id") or char.background_id
        char.species_id = self.data.get("species_id") or char.species_id
        char.base_scores = dict(self.data.get("base_scores") or char.base_scores)
        char.bg_bonus = self.data.get("bg_bonus")
        char.skill_prof = set(self.data.get("skill_prof") or set())
        char.bonus_skills = set(self.data.get("bonus_skills") or set())
        char.weapon_mastery = list(self.data.get("weapon_mastery") or [])
        char.order = self.data.get("order") or None
        char.spells = dict(self.data.get("spells") or
                           {"cantrips": [], "prepared": []})
        # 法师: 1 级法术书应有 6 个法术, 向导只挑了 4 个「已准备」的法术,
        # 差额记成免费抄录次数, 让玩家自己在「法术书」里补齐
        if char.class_id == "wizard":
            char.spellbook = [sid for sid in (char.spells.get("prepared") or [])
                              if (self.r.spell(sid) or {}).get("level", 0) >= 1]
            char.book_pending = max(0, 6 - len(char.spellbook))
        char.lineage = self.data.get("lineage")
        char.skill_prof |= set(char.auto_skills())
        # 默认装备: 该职业熟练的第一件武器
        pool = Rules.class_mastery_pool(char.cls()) or consts.WEAPONS
        char.weapon = pool[0][0]
        char.fighting_style = None      # 由角色卡「装备」页选择
        if self.data.get("human_feat"):
            char.feats.append(self.data["human_feat"])
        char.hp_current = char.hp_max()
        return char

    def finish(self):
        char = self._build_char()
        self.destroy()
        self.on_finish(char)
