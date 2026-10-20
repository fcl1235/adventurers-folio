# -*- coding: utf-8 -*-
"""规则引擎: 读取核心 JSON, 提供职业/种族/背景/法术查询。"""
import json

from . import consts
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)
from .paths import DATA_FILE, DETAIL_FILE, SPELL_FILE


class Rules:
    """封装 dnd55e_core_data.json"""

    def __init__(self, path=DATA_FILE):
        with open(path, encoding="utf-8") as f:
            self.d = json.load(f)
        self.classes_by_id = {c["id"]: c for c in self.d["classes"]}
        self.bg_by_id = {b["id"]: b for b in self.d["backgrounds"]}
        self.sp_by_id = {s["id"]: s for s in self.d["species"]}
        self.skill_by_id = {s["id"]: s for s in self.d["skills"]}
        self.armor_by_id = {a["id"]: a for a in self.d["armor"]}
        # 法术库 (SRD 5.2 快照; 文件缺失时降级为空库, 程序仍可用)
        self.spells = {}
        self.spells_by_class = {}
        self.spells_by_level = {}
        try:
            with open(SPELL_FILE, encoding="utf-8") as f:
                for s in json.load(f)["spells"]:
                    self.spells[s["id"]] = s
                    self.spells_by_level.setdefault(s["level"], []).append(s)
                    for c in s["classes"]:
                        self.spells_by_class.setdefault(c, []).append(s)
        except (OSError, ValueError, KeyError) as e:
            print("法术库载入失败:", e)
        # 职业特性 / 资源池 / 子职介绍 (SRD 5.2 抓取 + 中文整理)
        self.detail = {"classes": {}, "subclasses": {}}
        try:
            with open(DETAIL_FILE, encoding="utf-8") as f:
                self.detail = json.load(f)
        except (OSError, ValueError) as e:
            print("职业明细载入失败:", e)

    # ---- 职业明细 ----

    def class_detail(self, cid):
        return self.detail["classes"].get(cid) or {"features": [],
                                                   "resources": []}

    def class_features(self, cid):
        return self.class_detail(cid)["features"]

    def class_resources(self, cid):
        return self.class_detail(cid)["resources"]

    def sub_info(self, name):
        return self.detail["subclasses"].get(name)

    def sub_options(self, cid):
        """[(英文字职名, 中文名, 一句话定位)]"""
        out = []
        for s in self.cls(cid)["subclasses"]:
            info = self.sub_info(s)
            out.append((s, subclass_cn(s),
                        info["summary"] if info else ""))
        return out

    def spell(self, sid):
        return self.spells.get(sid)

    def class_spells(self, cid, level=None):
        out = self.spells_by_class.get(cid, [])
        if level is not None:
            out = [s for s in out if s["level"] == level]
        return sorted(out, key=lambda s: (s["level"], s["name"]))

    def cls(self, cid):
        return self.classes_by_id[cid]

    def bg(self, bid):
        return self.bg_by_id[bid]

    def sp(self, sid):
        return self.sp_by_id[sid]

    def full_slots(self, level):
        return {int(k): v for k, v in
                self.d["spell_slots"]["full_caster"][str(level)].items()}

    @staticmethod
    def prof_with(cls, name):
        """某职业是否熟练某武器 (2024: 用武器的 light/finesse 属性判定)"""
        w = next((x for x in consts.WEAPONS if x[0] == name), None)
        if not w:
            return False
        rules = cls.get("weapons") or []
        if "martial" in rules:
            return True
        props = w[4] if len(w) > 4 else []
        if w[1] == "简单":
            return "simple" in rules
        if w[1] == "军用":
            if "martial-light-property" in rules and "light" in props:
                return True
            if "martial-finesse-or-light" in rules and \
                    ("light" in props or "finesse" in props):
                return True
        return False

    @staticmethod
    def class_mastery_pool(cls):
        """该职业可选武器专精的武器名单 —— 前提是熟练该武器 (2024)"""
        return [w for w in consts.WEAPONS if Rules.prof_with(cls, w[0])]
