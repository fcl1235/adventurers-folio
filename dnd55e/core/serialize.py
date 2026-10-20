# -*- coding: utf-8 -*-
"""角色模型分片: core/serialize.py (由 character.py 物理拆分, P1 纯搬运)。"""
from .. import consts
from ..consts import (ABILITIES, subclass_cn)


class SerializeMixin:
    """SerializeMixin"""

    def to_dict(self):
        return {
            "system": "dnd55e-character v1",
            "name": self.name, "level": self.level, "xp": self.xp,
            "class_id": self.class_id, "subclass": self.subclass,
            "order": self.order,
            "land": self.land,
            "wild_shape_id": self.wild_shape_id,
            "metamagic": list(self.metamagic),
            "innate_active": self.innate_active,
            "innate_used": self.innate_used,
            "sorcerous_rest_used": self.sorcerous_rest_used,
            "mastery_spells": list(self.mastery_spells),
            "signature_spells": list(self.signature_spells),
            "signature_used": list(self.signature_used),
            "offhand_weapon": self.offhand_weapon,
            "background_id": self.background_id, "species_id": self.species_id,
            "base_scores": self.base_scores, "bg_bonus": self.bg_bonus,
            "asi_history": self.asi_history,
            "skill_prof": sorted(self.skill_prof),
            "bonus_skills": sorted(self.bonus_skills),
            "expertise": sorted(self.expertise),
            "weapon_mastery": self.weapon_mastery,
            "armor_index": self.armor_index, "shield": self.shield,
            "tough_feat": self.tough_feat,
            "hp_current": self.hp_current, "hp_temp": self.hp_temp,
            "spell_slots_used": self.spell_slots_used,
            "feats": self.feats, "languages": self.languages,
            "equipment": self.equipment, "notes": self.notes,
            "exhaustion": self.exhaustion,
            "conditions": sorted(self.conditions),
            "spells": self.spells,
            "spellbook": list(self.spellbook),
            "book_pending": self.book_pending,
            "weapon": self.weapon, "weapon_magic": self.weapon_magic,
            "two_handed_grip": self.two_handed_grip,
            "shield_magic": self.shield_magic,
            "items": self.items, "fighting_style": self.fighting_style,
            "concentration": self.concentration,
            "lineage": self.lineage,
            "race_free_used": self.race_free_used,
            "res_used": self.res_used,
            "font_slots": self.font_slots,
            "hit_dice_used": self.hit_dice_used,
            "death_success": self.death_success,
            "death_fail": self.death_fail,
            "raging": self.raging,
        }

    def load_dict(self, d):
        """从存档字典恢复, 所有字段做边界钳制/白名单校验, 坏数据不崩。"""
        def _int(v, default, lo, hi):
            try:
                return max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                return default

        known_cls = {c["id"] for c in self.r.d["classes"]}
        known_bg = {b["id"] for b in self.r.d["backgrounds"]}
        known_sp = {s["id"] for s in self.r.d["species"]}
        known_sk = {s["id"] for s in self.r.d["skills"]}
        known_wp = {w[0] for w in consts.WEAPONS}

        self.name = str(d.get("name") or self.name)[:40]
        self.level = _int(d.get("level"), 1, 1, 20)
        self.xp = _int(d.get("xp"), 0, 0, 10 ** 9)
        cid = d.get("class_id")
        self.class_id = cid if cid in known_cls else self.r.d["classes"][0]["id"]
        sub = d.get("subclass")
        valid_subs = self.cls()["subclasses"] + [subclass_cn(s) for s in
                                                 self.cls()["subclasses"]]
        self.subclass = sub if sub in valid_subs else None
        # 1 级职阶: 只接受本职业的合法选项, 其它职业一律清空
        ordv = d.get("order")
        self.order = ordv if ordv in (consts.ORDERS.get(self.class_id) or {}) else None
        # 大地结社地形: 只对 circle-of-the-land 有效
        landv = d.get("land")
        ok_lands = {k for k, _ in self.land_options()}
        self.land = landv if landv in ok_lands else "temperate"
        # 荒野变形形态: 必须是当前等级允许的野兽, 否则清空
        ws = d.get("wild_shape_id")
        self.wild_shape_id = ws if ws in {m["id"] for m in self.wild_shapes()} else None
        bid = d.get("background_id")
        self.background_id = bid if bid in known_bg else self.r.d["backgrounds"][0]["id"]
        sid = d.get("species_id")
        legacy_sp = consts.LEGACY_SPECIES.get(sid)
        if legacy_sp:                # 旧存档里的 5e 传承种族 → 2024 对应种族
            sid = legacy_sp
        self.species_id = sid if sid in known_sp else self.r.d["species"][0]["id"]

        bs = d.get("base_scores") or {}
        self.base_scores = {a: _int(bs.get(a), 10, 1, 20) for a in ABILITIES}

        bg = d.get("bg_bonus")
        if isinstance(bg, dict) and bg.get("mode") in ("2+1", "111"):
            if bg["mode"] == "2+1":
                p2, p1 = bg.get("plus2"), bg.get("plus1")
                if p2 in ABILITIES and p1 in ABILITIES and p2 != p1:
                    self.bg_bonus = {"mode": "2+1", "plus2": p2, "plus1": p1}
            else:
                ones = [a for a in (bg.get("ones") or []) if a in ABILITIES]
                if len(ones) == 3 and len(set(ones)) == 3:
                    self.bg_bonus = {"mode": "111", "ones": ones}

        self.asi_history = [x for x in (d.get("asi_history") or [])
                            if isinstance(x, dict)]
        self.skill_prof = {s for s in (d.get("skill_prof") or [])
                           if s in known_sk}
        # 种族/专长给的额外熟练: 必须同时也是熟练项, 最多 6 项
        self.bonus_skills = {s for s in (d.get("bonus_skills") or [])
                             if s in self.skill_prof}
        if len(self.bonus_skills) > 6:
            self.bonus_skills = set(sorted(self.bonus_skills)[:6])
        self.expertise = {s for s in (d.get("expertise") or [])
                          if s in self.skill_prof}
        # 专精数量不得超过职业/等级的允许值
        exp_allow = self.expertise_allowance()
        if len(self.expertise) > exp_allow:
            ordered = [s["id"] for s in self.r.d["skills"]
                       if s["id"] in self.expertise]
            self.expertise = set(ordered[:exp_allow])
        # 武器专精: 数量按等级, 且只能取本职业熟练范围内的武器
        mc = self.mastery_count()
        pool = self.weapon_mastery_pool()
        self.weapon_mastery = [w for w in (d.get("weapon_mastery") or [])
                               if w in known_wp and (not pool or w in pool)][:mc]
        self.armor_index = _int(d.get("armor_index"), 0, 0, len(consts.ARMORS) - 1)
        self.shield = bool(d.get("shield", False))
        self.tough_feat = bool(d.get("tough_feat", False))
        # 术法源泉换出的临时法术位: 必须在 spell_slots_used 之前读入,
        # 否则会被当成超出职业表的非法值丢掉
        self.font_slots = {}
        if self.class_id == "sorcerer" and self.level >= 2:
            for k, v in (d.get("font_slots") or {}).items():
                kk = _int(k, 0, 1, 5)
                vv = _int(v, 0, 0, 9)
                if kk and vv:
                    self.font_slots[kk] = vv
        self.spell_slots_used = {}
        max_slots = self.spell_slots()
        for k, v in (d.get("spell_slots_used") or {}).items():
            kk = _int(k, 0, 1, 9)
            if kk in max_slots:
                self.spell_slots_used[kk] = _int(v, 0, 0, max_slots[kk])
        self.feats = [str(x)[:40] for x in (d.get("feats") or [])][:20]
        self.languages = str(d.get("languages") or "通用语")[:120]
        self.equipment = str(d.get("equipment") or "")[:4000]
        self.notes = str(d.get("notes") or "")[:20000]
        if legacy_sp:                # 迁移说明写进备注, 不静默改动
            tip = (f"※ 旧存档中的「{consts.LEGACY_SPECIES_CN.get(d.get('species_id'), '')}」"
                   f"已按 2024 规则改为「{self.r.sp(self.species_id)['name']}」"
                   f"（5.5e 种族不加属性），请复核种族与属性。")
            if tip not in self.notes:
                self.notes = (tip + "\n" + self.notes)[:20000]
        self.exhaustion = _int(d.get("exhaustion"), 0, 0, 6)
        self.conditions = {c for c in (d.get("conditions") or [])
                           if c in consts.CONDITIONS}
        # ---- 2024 扩展字段 (全部白名单校验) ----
        known_sp_ids = set(self.r.spells)
        sp = d.get("spells") or {}
        def _sp_list(key, lv_filter=None):
            out = []
            for sid in (sp.get(key) or []):
                rec = self.r.spell(sid)
                if not rec:
                    continue
                if lv_filter is not None and rec["level"] != lv_filter:
                    continue
                if rec["level"] == 0 and lv_filter is None and key == "prepared":
                    continue
                out.append(sid)
            return out[:40]
        self.spells = {"cantrips": _sp_list("cantrips", 0),
                       "prepared": _sp_list("prepared")}
        # 法术书: 只收法师法术表里的 id, 去重后限长
        wiz_ids = {s["id"] for s in self.r.class_spells("wizard")}
        self.spellbook = []
        for sid in (d.get("spellbook") or []):
            if sid in wiz_ids and sid not in self.spellbook:
                self.spellbook.append(sid)
        self.spellbook = self.spellbook[:220]
        # 法师 1→20 级最多可攒 2+2*19=40 次免费抄录
        self.book_pending = _int(d.get("book_pending"), 0, 0, 40)
        # 超魔法 / 先天魔法 / 法师精通与招牌法术 / 副手武器
        self.metamagic = [m for m in (d.get("metamagic") or [])
                          if m in consts.METAMAGIC][:self.metamagic_cap()]
        self.innate_used = _int(d.get("innate_used"), 0, 0, 2)
        self.sorcerous_rest_used = bool(d.get("sorcerous_rest_used", False))
        self.innate_active = bool(d.get("innate_active", False)) \
            and self.innate_cap() > 0
        self.mastery_spells = self._choice_spells(d.get("mastery_spells"),
                                                  18, {1, 2}, 2, True)
        self.signature_spells = self._choice_spells(d.get("signature_spells"),
                                                    20, {3}, 2, False)
        self.signature_used = [s for s in (d.get("signature_used") or [])
                               if s in self.signature_spells][:2]
        off = d.get("offhand_weapon")
        self.offhand_weapon = off if off in known_wp else ""
        self.weapon = d.get("weapon") if d.get("weapon") in known_wp else ""
        self.two_handed_grip = bool(d.get("two_handed_grip", False)) and \
            bool(self.weapon) and self.is_versatile_weapon()
        self.weapon_magic = _int(d.get("weapon_magic"), 0, 0, 3)
        self.shield_magic = _int(d.get("shield_magic"), 0, 0, 3)
        self.items = [i for i in (d.get("items") or []) if i in consts.ITEMS_BY_ID][:20]
        fs = d.get("fighting_style")
        self.fighting_style = fs if fs in consts.FIGHTING_STYLES else None
        if self.fighting_style and not self.can_fighting_style():
            self.fighting_style = None       # 该职业/等级没有战斗风格特性
        conc = d.get("concentration")
        self.concentration = conc if conc in known_sp_ids else None
        lin = d.get("lineage")
        ent = consts.SPECIES_SPELLS.get(self.species_id or "")
        self.lineage = lin if (isinstance(ent, dict) and lin in ent) else None
        self.race_free_used = [s for s in (d.get("race_free_used") or [])
                               if s in known_sp_ids][:10]
        # 职业资源: 只接受本职业真实存在的资源 id, 并钳制到上限
        self.res_used = {}
        raw_res = d.get("res_used")
        if isinstance(raw_res, dict):
            for res in self.r.class_resources(self.class_id):
                rid = res["id"]
                if rid in raw_res:
                    mx = self.resource_max(res)
                    self.res_used[rid] = _int(raw_res.get(rid), 0, 0, mx)
        self.skill_prof |= set(self.auto_skills())
        # 休息 / 濒死 / 姿态
        self.hit_dice_used = _int(d.get("hit_dice_used"), 0,
                                  0, self.hit_dice_max())
        self.death_success = _int(d.get("death_success"), 0, 0, 3)
        self.death_fail = _int(d.get("death_fail"), 0, 0, 3)
        self.raging = bool(d.get("raging", False)) and self.class_id == "barbarian"
        # 最后钳制 HP (依赖上面的 level/scores/species/tough)
        self.hp_temp = _int(d.get("hp_temp"), 0, 0, 999)
        self.hp_current = _int(d.get("hp_current"), self.hp_max(),
                               0, self.hp_max())
        # 特性授予的法术不再占用手动列表 (旧存档里可能存过)
        self.prune_fixed()
        # 旧存档没有法术书 → 用已准备的法师法术补齐
        self.book_auto_fill()
