import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.simpledialog import askinteger

from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)
from .dialogs import LevelUpDialog
from .util import mod_str
from .wizard import Wizard
from . import paths

# 拆分后需要的内部依赖
import json
import os
from .character import Character
from .util import ability_mod


class AppIO:
    def new_character(self):
        Wizard(self, self.rules, self.set_character)

    # ---- 存档 (固定目录 + 自动载入) ----

    @staticmethod
    def _safe_name(name):
        bad = '\\/:*?"<>|'
        out = "".join(("_" if ch in bad else ch) for ch in (name or "角色"))
        return out.strip() or "角色"

    def _char_path(self, name=None):
        return os.path.join(paths.CHAR_DIR, self._safe_name(name or self.char.name)
                            + ".json")

    def _remember_last(self, path):
        try:
            os.makedirs(paths.CHAR_DIR, exist_ok=True)
            with open(paths.LAST_PTR, "w", encoding="utf-8") as f:
                json.dump({"file": os.path.basename(path)}, f,
                          ensure_ascii=False)
        except OSError:
            pass

    def _write_char(self, path):
        self._notes_changed()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.char.to_dict(), f, ensure_ascii=False, indent=2)

    def save_character(self):
        """保存到固定目录 characters/ (不弹窗)"""
        if not self.char:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        path = self._char_path()
        try:
            self._write_char(path)
        except OSError as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return
        self._remember_last(path)
        self._log_roll(f"💾 已保存: {os.path.basename(path)}")
        self.status.config(text=f"💾 已保存到 {path}")

    def save_character_as(self):
        """另存为任意路径"""
        if not self.char:
            return
        os.makedirs(paths.CHAR_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".json", initialdir=paths.CHAR_DIR,
            initialfile=f"{self._safe_name(self.char.name)}.json",
            filetypes=[("D&D 5.5e 角色档", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self._write_char(path)
        except OSError as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return
        self._remember_last(path)
        self._log_roll(f"💾 已另存: {path}")

    def _load_path(self, path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        char = Character(self.rules)
        char.load_dict(d)
        self.set_character(char)
        self._remember_last(path)
        self._log_roll(f"📂 已载入: {char.name} ({os.path.basename(path)})")

    def load_character(self):
        os.makedirs(paths.CHAR_DIR, exist_ok=True)
        path = filedialog.askopenfilename(
            parent=self, initialdir=paths.CHAR_DIR,
            filetypes=[("D&D 5.5e 角色档", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self._load_path(path)
        except Exception as e:
            messagebox.showerror("错误", f"载入失败: {e}", parent=self)

    def _auto_start(self):
        """启动时优先读取上次的角色卡, 没有才打开建卡向导"""
        path = None
        try:
            with open(paths.LAST_PTR, encoding="utf-8") as f:
                cand = os.path.join(paths.CHAR_DIR, json.load(f).get("file", ""))
            if os.path.exists(cand):
                path = cand
        except (OSError, ValueError):
            path = None
        if not path and os.path.isdir(paths.CHAR_DIR):
            files = [os.path.join(paths.CHAR_DIR, f) for f in os.listdir(paths.CHAR_DIR)
                     if f.endswith(".json") and not f.startswith("_")]
            if files:
                path = max(files, key=os.path.getmtime)
        if path:
            try:
                self._load_path(path)
                return
            except Exception as e:
                print("自动载入失败:", e)
        self.new_character()

    def open_char_folder(self):
        try:
            os.makedirs(paths.CHAR_DIR, exist_ok=True)
            os.startfile(paths.CHAR_DIR)
        except OSError as e:
            messagebox.showerror("错误", str(e), parent=self)

    def export_character(self):
        if not self.char:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".json",
            initialfile=f"{self.char.name}_export.json")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.char.to_dict(), f, ensure_ascii=False, indent=2)
        self._log_roll(f"⬇ 已导出: {path}")

    def level_up(self):
        c = self.char
        if not c:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        if c.level >= 20:
            messagebox.showinfo("提示", "已到 20 级上限", parent=self)
            return
        dlg = LevelUpDialog(self, c)
        self.wait_window(dlg)
        rec = dlg.result
        if not rec:
            return
        c.level = rec["level"]
        if rec["subclass"]:
            c.subclass = rec["subclass"]
        c.prune_fixed()          # 新得到的「始终准备」法术不再占手动列表
        if rec["asi"]:
            c.asi_history.append(rec["asi"])
        # 传奇恩惠: 必须进 c.feats, 否则 all_feat_names() 看不到, effects 不生效
        boon = rec.get("boon")
        if boon and boon not in c.feats:
            c.feats.append(boon)
        ab = rec.get("boon_ability")
        if boon and ab:
            c.boon_ability[boon] = ab
        gain = max(1, c.cls()["hit_die"] // 2 + 1 +
                   ability_mod(c.score("CON")))
        c.hp_current += gain
        self.refresh()
        msg = [f"升至 {c.level} 级!",
               f"HP +{gain} (当前 {c.hp_current}/{c.hp_max()})"]
        if rec["subclass"]:
            msg.append(f"子职: {subclass_cn(rec['subclass'])}")
        if rec["boon"]:
            msg.append(f"传奇恩惠: {rec['boon']}")
        # 法师: 每升 1 级免费抄入 2 个法术 (2024 PHB)
        if c.class_id == "wizard":
            c.book_pending = min(40, c.book_pending + 2)
            msg.append(f"法术书：可免费抄录 2 个法术（待抄 {c.book_pending} 次）")
        self._log_roll(f"⬆ 升级! 现在是 {c.level} 级, HP +{gain}")
        messagebox.showinfo("升级完成", "\n".join(msg), parent=self)

    def long_rest(self):
        c = self.char
        if not c:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        c.spell_slots_used = {}
        c.font_slots = {}              # 术法源泉换出的临时位随长休消失
        c.race_free_used = []          # 种族法术的免费次数随长休恢复
        c.signature_used = []          # 招牌法术的免费施放 (短休也恢复)
        c.innate_used = 0              # 先天魔法 2 次/长休
        c.innate_active = False
        c.sorcerous_rest_used = False   # 魔法恢复 1 次/长休
        c.res_reset("long")            # 职业资源全部回满 (狂暴/气/术法点/圣疗池…)
        c.hp_current = c.hp_max()
        c.hp_temp = 0                  # 2024: 长休后临时生命消失
        c.hit_dice_used = 0            # 2024: 长休恢复全部生命骰
        c.death_success = c.death_fail = 0
        c.raging = False
        if c.exhaustion > 0:
            c.exhaustion -= 1
        self.refresh()
        self._log_roll("🌙 长休: HP 全满 · 法术位/秘契/职业资源全恢复 · "
                       "生命骰全回 · 力竭 -1")
        messagebox.showinfo(
            "长休", "长休结束:\n• HP 全满\n"
                    "• 法术位与秘契法术全部恢复\n"
                    "• 职业资源全部回满 (狂暴/气/术法点/圣疗池…)\n"
                    f"• 生命骰全部恢复 (d{c.hit_die()} ×{c.hit_dice_max()})\n"
                    "• 死亡豁免清零 · 结束狂暴\n• 力竭 -1 级",
            parent=self)

    def short_rest(self):
        c = self.char
        if not c:
            messagebox.showinfo("提示", "还没有角色 —— 先「✦ 新建角色」",
                                parent=self)
            return
        c.res_reset("short")           # 按各资源规则恢复 (恢复 1 次 / 全部)
        c.raging = False
        c.signature_used = []          # 2024: 招牌法术短休也恢复免费施放
        msg = []
        _ok_sr, _msg_sr = c.sorcerous_rest()   # 术士 5 级「魔法恢复」
        if _ok_sr:
            msg.append(_msg_sr)
        # 游侠 10 级「不倦」: 每次短休力竭 -1
        if c.class_id == "ranger" and c.level >= 10 and c.exhaustion > 0:
            c.exhaustion -= 1
            msg.append("不倦：力竭 -1 级")
        if c.slots_recharge_short_rest():
            # 契约法术位短休回满；秘契法术 (6–9 环) 只随长休恢复
            arc = set(c.arcanum_levels())
            for lv in list(c.spell_slots_used):
                if lv not in arc:
                    c.spell_slots_used.pop(lv, None)
            msg.append("契约法术位已恢复（秘契法术仍需长休）")
        for r in c.resources():
            if r["short"] == "all":
                msg.append(f"{r['name']} 已全部恢复")
            elif r["short"] == 1:
                msg.append(f"{r['name']} 恢复 1 次")
        # 花生命骰回血 (2024 短休核心)
        left = c.hit_dice_left()
        if left > 0:
            n = self._ask_hd(left)
            if n:
                used, heal, detail = c.spend_hit_dice(n)
                msg.append(f"花 {used} 颗生命骰回复 {heal} HP（"
                           + "、".join(detail) + "）")
        else:
            msg.append("生命骰已用尽（长休恢复）")
        self.refresh()
        self._log_roll("☕ 短休: " + ("; ".join(msg) if msg else "无自动恢复项"))
        messagebox.showinfo("短休", "短休结束:\n" +
                            ("\n".join("• " + m for m in msg) if msg
                             else "该职业短休无自动恢复的资源；法术位需长休恢复。"),
                            parent=self)

    def _ask_hd(self, left):
        """询问短休要花几颗生命骰 (自检/无头模式不弹窗, 直接返回 0)"""
        if getattr(self, "_selftest", False):
            return 0
        c = self.char
        n = askinteger(
            "短休 · 花生命骰",
            f"你有 {left} 颗 d{c.hit_die()} 生命骰（共 {c.hit_dice_max()} 颗）。\n"
            f"每颗恢复 d{c.hit_die()}+体质调整值，花几颗？\n（输入 0 表示不花）",
            parent=self, minvalue=0, maxvalue=left, initialvalue=0)
        return n or 0

    def _on_close(self):
        self._notes_changed()
        if self.char is not None and not getattr(self, "_selftest", False):
            try:
                path = self._char_path()
                self._write_char(path)
                self._remember_last(path)
            except OSError:
                pass
        self.destroy()
