"""法术页: 列表 / 详情 / 法术书 / 增删 / 施放 / 专注。"""
import random
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from ... import consts, util
from ... import summoning
from ...consts import (ABILITIES, ABILITY_CN, feat_cn, feat_desc, mastery_cn,
                       size_cn, subclass_cn, tool_cn)
from ...dialogs import (FeatPickerDialog, MetamagicDialog, SpellbookDialog,
                        SummonCardDialog, WildShapeDialog)
from ...rules import Rules
from ...theme import BG, GOLD2
from ...util import (ability_mod, mod_str, roll_dice, roll_dice_reroll,
                     spell_detail)


class SpellActionsMixin:
    def _spell_rows(self):
        c = self.char
        rows = []
        if not c:
            return rows
        fixed = set(c.fixed_spells())
        for key in ("cantrips", "prepared"):
            for sid in (c.spells or {}).get(key, []):
                if sid in fixed:             # 已由特性授予, 不重复列出
                    continue
                s = c.r.spell(sid)
                if s:
                    rows.append(dict(s, _src="职业"))
        for sid in c.fixed_spells():         # 职业特性 / 子职「始终准备」
            s = c.r.spell(sid)
            if s:
                rows.append(dict(s, _src=f"{c.fixed_source(sid)}固定"))
        for unlock, sid in c.species_spells():       # 种族自带, 不占职业位
            s = c.r.spell(sid)
            if s:
                rows.append(dict(s, _src="种族"))
        # 法师: 书里的仪式法术不用准备也能施放 (仪式施法, 不耗环位)
        if c.class_id == "wizard":
            shown = {r["id"] for r in rows}
            for sid in (c.spellbook or []):
                if sid in shown:
                    continue
                s = c.r.spell(sid)
                if s and s.get("ritual"):
                    rows.append(dict(s, _src="仪式"))
        rows.sort(key=lambda s: (s["level"], s["name"]))
        self._spell_cache = rows
        return rows

    def _spell_refresh(self):
        c = self.char
        if not c or not hasattr(self, "spell_list"):
            return
        prev = self._selected_spell()
        prev_id = prev["id"] if prev else None
        rows = self._spell_rows()
        self.spell_list.delete(0, "end")
        keep = None
        for i, s in enumerate(rows):
            tag = "戏法" if s["level"] == 0 else f"{s['level']}环"
            src = "[种族] " if s.get("_src") == "种族" else ""
            if str(s.get("_src", "")).endswith("固定"):
                src = f"✦{s['_src']} "
            elif s.get("_src") == "仪式":
                src = "[仪式] "
            mark = "  ◉专注中" if c.concentration == s["id"] else ""
            self.spell_list.insert("end", f"[{tag}] {src}{s['name']}{mark}")
            if s["id"] == prev_id:
                keep = i
        if keep is not None:          # 刷新后保持原选中项, 便于连续施法
            self.spell_list.selection_set(keep)
            self.spell_list.see(keep)
        learned = {s["id"] for s in rows}
        prepared = set(c.spells.get("prepared") or [])
        fixed = set(c.fixed_spells())
        maxlv = c.learnable_max_level()
        if c.class_id == "wizard":
            # 法师: 下拉框只列「法术书里、还没准备」的法术; 戏法仍从职业表学
            top = max(c.book_max_level(), 1)
            opts = [s for s in c.book_spells()
                    if s["level"] >= 1 and s["id"] not in prepared
                    and s["level"] <= top]
            opts += [s for s in c.r.class_spells("wizard", 0)
                     if s["id"] not in learned]
            opts.sort(key=lambda s: (s["level"], s["name"]))
        else:
            opts = [s for s in c.r.class_spells(c.spell_list_class() or "")
                    if s["id"] not in learned and s["id"] not in fixed
                    and (s["level"] == 0 or s["level"] <= max(maxlv, 1))]
        self._spell_opts = opts
        self.spell_add_cb["values"] = [f"{s['name']} {s['name_en']}"
                                       for s in opts]
        # 法师才显示法术书按钮 / 把「学习」改成「准备」
        if hasattr(self, "spellbook_btn"):
            if c.class_id == "wizard":
                self.spellbook_btn.config(
                    text=f"📖 法术书 ({len(c.spellbook or [])})")
                if not self.spellbook_btn.winfo_manager():
                    self.spellbook_btn.pack(side="right")
            elif self.spellbook_btn.winfo_manager():
                self.spellbook_btn.pack_forget()
        if hasattr(self, "spell_add_btn"):
            self.spell_add_btn.config(
                text="＋ 准备" if c.class_id == "wizard" else "＋ 学习")
        # 配额提示: 戏法硬上限 / 准备法术上限 (2024 职业表)
        if hasattr(self, "spell_quota_lbl"):
            if not c.casting():
                self.spell_quota_lbl.config(
                    text="该职业没有施法能力（若子职给法术，选子职后这里会自动出现）")
            else:
                n_c = len(c.spells.get("cantrips") or [])
                n_p = c.prepared_count()
                arc = c.arcanum_levels()
                extra = (f"　秘契 {max(arc)} 环（不占准备数）" if arc else "")
                n_fx = len(c.fixed_spells())
                fx = (f"　✦固定 {n_fx} 个（不占格）" if n_fx else "")
                n_mm = len(c.metamagic_known())
                mm = (f"　⚙超魔法 {n_mm} 个（施法时选）" if n_mm else "")
                bk = (f"　📖书内 {len(c.spellbook or [])} 个"
                      if c.class_id == "wizard" else "")
                self.spell_quota_lbl.config(
                    text=f"戏法 {n_c}/{c.cantrip_cap()}　"
                         f"法术 {n_p}/{c.prepared_hint()}（职业表）　"
                         f"最高可用 {c.max_spell_level()} 环{extra}{fx}{mm}{bk}")
        if not rows:
            tip = ("法术书里还没有能用的法术。点右上角「📖 法术书」抄录，"
                   "再从下拉框里「＋ 准备」。"
                   if c.class_id == "wizard" else
                   "本角色尚无法术。用上方下拉框选择本职业法术，点「＋ 学习」加入。"
                   "（法师/牧师等准备施法者也可按 DM 允许随时调整）")
            self._spell_detail_set(tip)

    def _spell_detail_set(self, text):
        self.spell_detail.config(state="normal")
        self.spell_detail.delete("1.0", "end")
        self.spell_detail.insert("1.0", text)
        self.spell_detail.config(state="disabled")

    def _selected_spell(self):
        sel = self.spell_list.curselection()
        rows = getattr(self, "_spell_cache", [])
        if sel and sel[0] < len(rows):
            return rows[sel[0]]
        return None

    def _spell_show(self, _e=None):
        s = self._selected_spell()
        txt = spell_detail(s)
        c = self.char
        if s and c and c.spell_dc() is not None:
            txt += f"\n\n你的法术豁免 DC {c.spell_dc()} · 法术攻击 {mod_str(c.spell_attack())}"
        self._spell_detail_set(txt)
        # 「查看召唤物」按钮只在当前法术有召唤/变形数据时出现
        btn = getattr(self, "summon_btn", None)
        if btn is not None:
            if s and summoning.summon_of(s):
                btn.pack(side="right", padx=3)
            else:
                btn.pack_forget()

    def _spell_summon(self):
        """弹出当前法术的召唤物 stat block 卡"""
        s = self._selected_spell()
        if not s or not summoning.summon_of(s):
            return
        dlg = SummonCardDialog(self, spell=s,
                               selftest=getattr(self, "_selftest", False))
        if not getattr(self, "_selftest", False):
            self.wait_window(dlg)

    def _spellbook_open(self):
        """打开法师法术书 (抄录 / 移出)"""
        c = self.char
        if not c or c.class_id != "wizard":
            return
        dlg = SpellbookDialog(self, c, selftest=getattr(self, "_selftest", False))
        self.wait_window(dlg)
        self.refresh()

    def _spell_add(self):
        c = self.char
        if not c:
            return
        idx = self.spell_add_cb.current()
        if idx < 0 or idx >= len(getattr(self, "_spell_opts", [])):
            return
        s = self._spell_opts[idx]
        if s["id"] in set(c.fixed_spells()):
            messagebox.showinfo(
                "提示", f"{s['name']} 已由职业/子职特性「始终准备」，"
                        f"不需要再学，也不占准备数。", parent=self)
            return
        key = "cantrips" if s["level"] == 0 else "prepared"
        cur = list(c.spells.get(key) or [])
        # 法师: 只能准备法术书里的法术
        if key == "prepared" and c.class_id == "wizard" \
                and not c.can_prepare(s["id"]):
            messagebox.showwarning(
                "不在法术书里",
                f"{s['name']} 不在你的法术书里，不能准备。\n"
                "请先点「📖 法术书」把它抄进书里。", parent=self)
            return
        # 戏法: 数量由职业固定, 不能超
        if key == "cantrips" and len(cur) >= c.cantrip_cap():
            messagebox.showwarning(
                "戏法已满",
                f"{c.cls()['name']} 目前只能掌握 {c.cantrip_cap()} 个戏法"
                f"（已学 {len(cur)} 个）。\n4 级与 10 级各会再 +1。", parent=self)
            return
        # 法术环级不能超过你能施放的最高环 (含秘契 6–9 环)
        if s["level"] > max(c.learnable_max_level(), 1):
            messagebox.showwarning(
                "环级不足",
                f"你目前最高只能施放 {c.learnable_max_level()} 环法术，"
                f"还不能学习 {s['name']}（{s['level']} 环）。", parent=self)
            return
        # 准备法术: 数量由职业表定死, 不能超; 秘契法术不占这份额度
        arcanum = s["level"] > c.max_spell_level()
        if key == "prepared" and not arcanum \
                and c.prepared_count() >= c.prepared_hint():
            messagebox.showwarning(
                "已到准备上限",
                f"{c.cls()['name']} {c.level} 级最多准备 "
                f"{c.prepared_hint()} 个法术（2024 职业表，已准备 "
                f"{c.prepared_count()} 个）。\n"
                "想换法术请先移除一个；长休时可以重新准备。", parent=self)
            return
        if s["id"] not in cur:
            c.spells.setdefault(key, []).append(s["id"])
        self.refresh()
        self._spell_detail_set(spell_detail(s))

    def _spell_del(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        if s.get("_src") == "种族":
            messagebox.showinfo(
                "提示", f"{s['name']} 是种族自带法术，不能移除。\n"
                        f"（{self.char.lineage_cn() or '种族'}特性，始终备好）",
                parent=self)
            return
        if str(s.get("_src", "")).endswith("固定"):
            src = s["_src"][:-2]           # "职业固定" -> "职业"
            messagebox.showinfo(
                "提示", f"{s['name']} 由{src}特性「始终准备」，不能移除。\n"
                        "它也不占用准备法术的数量。", parent=self)
            return
        if s.get("_src") == "仪式":
            messagebox.showinfo(
                "提示", f"{s['name']} 还在法术书里（未准备），可以直接仪式施放。\n"
                        "要删掉请点「📖 法术书」把书里的这个法术移出。",
                parent=self)
            return
        for key in ("cantrips", "prepared"):
            if s["id"] in c.spells.get(key, []):
                c.spells[key].remove(s["id"])
        if c.concentration == s["id"]:
            c.concentration = None
        self.refresh()

    def _spell_cast(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        # 2024: 穿着未熟练的护甲/盾牌时无法施法
        if not c.has_armor_prof() or (c.shield and not c.has_shield_prof()):
            messagebox.showwarning(
                "提示", "穿着未熟练的护甲或盾牌时无法施法（2024 规则）。\n"
                        "请在「装备·加成」页更换护甲或卸下盾牌。", parent=self)
            return
        if c.condition_blocks_action():
            messagebox.showwarning(
                "提示", "当前状态（失能/麻痹/震慑/昏迷/石化）无法执行动作，"
                        "因此不能施法。", parent=self)
            return
        if c.raging:
            messagebox.showwarning(
                "提示", "狂暴期间不能施放任何法术（2024 Rage）。\n"
                        "要施法请先结束狂暴。", parent=self)
            return
        # 仪式施法: 书里的仪式法术不用准备, 也不耗环位 (额外 10 分钟)
        if s.get("_src") == "仪式":
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ 仪式施放 {s['name']}（10 分钟，不耗环位）")
            return
        # 超魔法: 施法前选 (取消则整个施法取消)
        mm = self._mm_pick(s)
        if mm is None:
            return
        ok, why, _cost = c.mm_validate(mm)
        if not ok:
            messagebox.showwarning("超魔法不可用", why, parent=self)
            return
        mm_msg = ""
        if mm:
            _ok2, mm_msg = c.mm_apply(mm)
        tail = f" · {mm_msg}" if mm_msg else ""
        if s["level"] == 0:
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            tag = "（种族）" if s.get("_src") == "种族" else ""
            self._log_roll(f"✨ 施放戏法{tag} {s['name']}{tail}")
            return
        # 法师 18 级「法术精通」: 最低环随意施放, 不耗环位
        if c.is_mastery_spell(s["id"]):
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ {s['name']}（法术精通：随意施放，不耗环位）{tail}")
            return
        # 法师 20 级「招牌法术」: 每个短休免费施放 1 次 (3 环)
        if c.signature_left(s["id"]):
            c.signature_used.append(s["id"])
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ {s['name']}（招牌法术：3 环免费，短休恢复）{tail}")
            return
        # 种族法术: 每项每长休可免费施放 1 次
        if s.get("_src") == "种族" and s["id"] not in c.race_free_used:
            c.race_free_used.append(s["id"])
            if s["concentration"]:
                c.concentration = s["id"]
            self.refresh()
            self._log_roll(f"✨ 种族法术 {s['name']}（免费，1/长休）{tail}")
            return
        slots = c.spell_slots()
        avail = [x for x in sorted(slots)
                 if x >= s["level"] and slots[x] - c.spell_slots_used.get(x, 0) > 0]
        if not avail:
            messagebox.showwarning(
                "提示", f"{s['level']} 环及以上已无剩余法术位（长休恢复）",
                parent=self)
            return
        use = avail[0]
        c.spell_slots_used[use] = c.spell_slots_used.get(use, 0) + 1
        if s["concentration"]:
            c.concentration = s["id"]
        self.refresh()
        extra = ""
        sc = s.get("scaling") or {}
        if s["damage"] and str(use) in sc:
            extra = f" · {sc[str(use)]} {s['damage_type']}"
        self._log_roll(f"✨ 施放 {s['name']}（{use} 环位）{extra}{tail}")

    def _mm_pick(self, spell):
        """选超魔法: None=取消施法, []=不应用"""
        c = self.char
        if not c or not c.metamagic_known() or c.sorcery_left() <= 0:
            return []
        if getattr(self, "_selftest", False):
            return []                       # 后台测试不弹窗
        dlg = MetamagicDialog(self, c, spell)
        self.wait_window(dlg)
        return dlg.result

    def _spell_focus(self):
        c = self.char
        s = self._selected_spell()
        if not c or not s:
            return
        if c.concentration == s["id"]:
            c.concentration = None
            self._log_roll(f"◯ 结束专注: {s['name']}")
        else:
            c.concentration = s["id"]
            self._log_roll(f"◉ 开始专注: {s['name']}")
        self.refresh()
