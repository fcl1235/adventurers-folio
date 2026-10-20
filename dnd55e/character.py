# -*- coding: utf-8 -*-
"""角色数据模型: 派生数值 (AC/HP/命中/DC/资源…) 与存档序列化。纯逻辑, 不依赖 tkinter。"""
import random

from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)

# 拆分后需要的内部依赖
from .consts import ABILITIES, ABILITY_CN
from .rules import Rules
from .util import ability_mod, mod_str, proficiency_bonus


class Character:
    """角色数据模型"""

    def __init__(self, rules):
        self.r = rules
        self.name = "无名冒险者"
        self.level = 1
        self.xp = 0
        self.class_id = None
        self.subclass = None
        self.background_id = None
        self.species_id = None
        self.base_scores = {a: 10 for a in ABILITIES}
        self.bg_bonus = None          # {"mode":"2+1","plus2":ab,"plus1":ab} / {"mode":"111","ones":[..]}
        self.asi_history = []         # 每次ASI: {"type":"asi",...} 或 {"type":"feat","name":..}
        self.skill_prof = set()
        self.bonus_skills = set()     # 种族/专长给的额外技能 (不占职业配额)
        self.expertise = set()
        self.weapon_mastery = []      # 武器名列表
        self.armor_index = 0          # consts.ARMORS 下标
        self.shield = False
        self.tough_feat = False       # Tough 专长
        self.hp_current = 1
        self.hp_temp = 0
        self.spell_slots_used = {}    # {环级: 已用}
        self.feats = []               # 其他专长名
        self.languages = "通用语, "
        self.equipment = ""
        self.notes = ""
        self.exhaustion = 0
        self.conditions = set()
        # ---- 2024 扩展: 法术 / 装备与加成来源 ----
        self.spells = {"cantrips": [], "prepared": []}
        self.spellbook = []           # 法师法术书 (sid 列表)
        self.book_pending = 0         # 待用的免费抄录次数
        self.weapon = ""              # 当前武器装备 (consts.WEAPONS[0] 名称)
        self.two_handed_grip = False  # 两用(versatile)武器是否双手持用
        self.weapon_magic = 0         # 武器魔法加值 +0..+3
        self.shield_magic = 0         # 盾牌魔法加值
        self.items = []               # consts.MAGIC_ITEMS 的 id 列表
        self.fighting_style = None    # consts.FIGHTING_STYLES key
        self.order = None             # 1级职阶: cleric protector/thaumaturge, druid warden/magician
        self.land = "temperate"       # 大地结社: 长休时选的地形 arid/polar/temperate/tropical
        self.wild_shape_id = None     # 荒野变形当前形态 (monsters.json 的 id)
        self.metamagic = []           # 术士已知超魔法 id (2级2个, 10/17级各+2)
        self.innate_active = False    # 先天魔法生效中 (20级时让 1 个超魔法免费)
        self.innate_used = 0          # 先天魔法已用次数 (2 次/长休)
        self.sorcerous_rest_used = False   # 术士 5 级「魔法恢复」本长休是否用过
        self.mastery_spells = []      # 法师 18 级「法术精通」: 1 个 1 环 + 1 个 2 环
        self.signature_spells = []    # 法师 20 级「招牌法术」: 2 个 3 环
        self.signature_used = []      # 招牌法术的免费施放已用 (短休恢复)
        self.offhand_weapon = ""      # 副手武器 (双武器战斗)
        self.concentration = None     # 当前专注的法术 id
        self.lineage = None           # 精灵/侏儒/提夫林 血脉分支
        self.race_free_used = []      # 种族法术的「每长休免费一次」已用
        self.res_used = {}            # 职业资源已用点数 {资源 id: 已用}
        self.font_slots = {}          # 术法源泉兑换出的临时法术位 {环级: 个数}
        # ---- 2024 休息 / 濒死 / 战斗状态 ----
        self.hit_dice_used = 0        # 已消耗的生命骰 (总数 = 等级)
        self.death_success = 0        # 死亡豁免成功数 (3 即稳定)
        self.death_fail = 0           # 死亡豁免失败数 (3 即死亡)
        self.raging = False           # 野蛮人是否处于狂暴

    # ---- 派生数值 ----

    def ability_cap(self, ab):
        """属性上限: 常规 20; 野蛮人 20 级(力/体) / 武僧 20 级(敏/感) 为 25"""
        if self.class_id == "barbarian" and self.level >= 20 \
                and ab in ("STR", "CON"):
            return 25
        if self.class_id == "monk" and self.level >= 20 \
                and ab in ("DEX", "WIS"):
            return 25
        return 20

    def capstone_bonus(self, ab):
        """20 级职业压轴: 原始冠军 / 身心合一 —— 两项属性各 +4"""
        if self.class_id == "barbarian" and self.level >= 20 \
                and ab in ("STR", "CON"):
            return 4
        if self.class_id == "monk" and self.level >= 20 \
                and ab in ("DEX", "WIS"):
            return 4
        return 0

    def score(self, ab):
        s = self.base_scores[ab]
        b = self.bg_bonus
        if b:
            if b["mode"] == "2+1":
                if b["plus2"] == ab:
                    s += 2
                elif b["plus1"] == ab:
                    s += 1
            else:
                if ab in b["ones"]:
                    s += 1
        for c in self.asi_history:
            if c.get("type") == "asi":
                if c.get("plus2") == ab:
                    s += 2
                if c.get("plus1") == ab:
                    s += 1
                if ab in c.get("ones", []):
                    s += 1
        # 基础值 + 背景 + ASI 的阶段上限恒为 20
        s = min(20, s)
        # 20 级职业特性 (原始冠军 / 身心合一) 再 +4, 上限 25
        s = min(self.ability_cap(ab), s + self.capstone_bonus(ab))
        # 魔法物品的属性设定值 (如力量腰带 21) 可突破 20 上限
        for iid in self.items:
            v = consts.ITEMS_BY_ID.get(iid, {}).get("set_" + ab.lower())
            if v and v > s:
                s = v
        # 通用专长的属性设定值 (如 食人魔力量手套式专长)
        for ab2, v in (self.feat_effects().get("set_ability") or {}).items():
            if ab2 == ab and int(v) > s:
                s = int(v)
        return s

    # ---- 种族自带法术 / 自动熟练 ----

    def species_spells(self, level=None):
        """[(解锁等级, 法术 id)] —— 按血脉分支与当前等级过滤"""
        lv = self.level if level is None else level
        ent = consts.SPECIES_SPELLS.get(self.species_id or "")
        if not ent:
            return []
        if isinstance(ent, dict):                 # 有血脉分支
            ent = ent.get(self.lineage or "") or []
        return [(u, sid) for (u, sid) in ent
                if u <= lv and self.r.spell(sid)]

    def race_spell_ids(self):
        return [sid for _, sid in self.species_spells()]

    def auto_skills(self):
        return list(consts.SPECIES_AUTO_SKILLS.get(self.species_id or "", []))

    # ---- 建卡/升级期的固定配额 (用于锁定「定死的东西」) ----

    def skill_quota(self):
        """职业允许自选的技能数"""
        return int(self.cls().get("skill_count") or 0)

    def class_skill_pool(self):
        return set(self.cls().get("skill_options") or [])

    def bg_skills(self):
        if not self.background_id:
            return set()
        return set(self.r.bg(self.background_id).get("skills") or [])

    def class_skill_picks(self):
        """已选的「职业技能」数量 (不含背景/种族/专长给的熟练)"""
        picked = (self.skill_prof & self.class_skill_pool()) \
            - self.bg_skills() - set(self.bonus_skills)
        return len(picked)

    def extra_skill_allowance(self):
        """起源专长「多面手 Skilled」额外给的技能熟练数 (3)"""
        return 3 if self.has_feat("Skilled", "多面手") else 0

    def expertise_allowance(self):
        """专精 (Expertise) 允许项数 —— 只有游荡者/吟游诗人/游侠拥有"""
        lv, n = self.level, 0
        if self.class_id == "rogue":
            n = 2 + (2 if lv >= 6 else 0)
        elif self.class_id == "bard":
            n = (2 if lv >= 2 else 0) + (2 if lv >= 9 else 0)
        elif self.class_id == "ranger":
            n = (1 if lv >= 2 else 0) + (2 if lv >= 9 else 0)
        return n

    def weapon_mastery_pool(self):
        return {w[0] for w in Rules.class_mastery_pool(self.cls())}
    def class_dice_text(self):
        """职业关键数值 (骰子/次数), 让没有资源池的职业也有信息可看"""
        parts = []
        d = self.class_stat("martial_arts_die", 0)
        if d:
            parts.append(f"武艺伤害骰 1d{d}")
        sa = self.class_stat("sneak_attack", None)
        if isinstance(sa, dict) and sa.get("dice_count"):
            parts.append(f"偷袭 {sa['dice_count']}d{sa.get('dice_value', 6)}")
        rd = self.class_stat("rage_damage_bonus", 0)
        if rd:
            parts.append(f"狂暴伤害 +{rd}")
        mv = self.class_stat("unarmored_movement_bonus", 0)
        if mv:
            parts.append(f"无甲移动 +{mv} 尺")
        bi = self.class_stat("bardic_inspiration_die", 0)
        if bi:
            parts.append(f"灵感骰 d{bi}")
        mc = self.mastery_count()
        if mc:
            parts.append(f"武器专精 {mc} 件")
        inv = self.class_stat("eldritch_invocations", 0)
        if inv:
            parts.append(f"魔能祈唤 {inv} 个")
        return "　·　".join(parts)

    def attunement_cap(self):
        """同调上限: 3 件 (2024 通用规则; 盗贼的「使用魔法装置」只放宽
        使用物品的条件, 并不增加同调数)"""
        return 3

    def attuned_items(self):
        """当前需要同调的物品 (精灵斗篷/精灵靴等不需要同调)"""
        return [i for i in self.items
                if consts.ITEMS_BY_ID.get(i, {}).get("attune", True)]

    # ---- 法术配额 ----

    def max_spell_level(self):
        """当前能施放的最高环级 (由普通法术位决定; 秘契法术不算普通法术位)"""
        slots = self.spell_slots()
        arc = set(self.arcanum_levels())
        normal = [lv for lv in slots if lv not in arc]
        return max(normal) if normal else 0

    def learnable_max_level(self):
        """可以「学会/写入」的最高环级 —— 含邪术师秘契 6–9 环"""
        slots = self.spell_slots()
        return max(slots) if slots else 0

    def prepared_count(self):
        """已准备法术数 (秘契法术不占普通准备配额; 固定准备的法术也不占)"""
        lim = self.max_spell_level()
        fixed = set(self.fixed_spells())
        return sum(1 for sid in (self.spells or {}).get("prepared", [])
                   if sid not in fixed
                   and (self.r.spell(sid) or {}).get("level", 0) <= lim)

    # ---- 始终准备的法术 (职业特性 / 子职) ----

    def land_options(self):
        """大地结社的四种地形"""
        return [("arid", "干旱 Arid"), ("polar", "极地 Polar"),
                ("temperate", "温带 Temperate"), ("tropical", "热带 Tropical")]

    def land_label(self):
        if not self.land:
            return ""
        return dict(self.land_options()).get(self.land, self.land)

    def fixed_spells(self):
        """始终准备、不占配额、不可移除的法术 id 列表 (按等级门槛累加)"""
        out = []
        lv = max(int(self.level or 1), 1)
        tbl = consts.FIXED_SPELLS or {}
        for gate, ids in sorted((tbl.get("class") or {}).get(self.class_id or "",
                                                          {}).items()):
            if lv >= gate:
                out.extend(ids)
        sub = (tbl.get("subclass") or {}).get(self.subclass or "")
        if sub:
            rows = (sub.get("land") or {}).get(self.land or "temperate") \
                if sub.get("land") else sub.get("table")
            for gate, ids in sorted((rows or {}).items()):
                if lv >= gate:
                    out.extend(ids)
        # 法师 18/20 级自选的法术也是「始终准备」
        out.extend(self.mastery_spells or [])
        out.extend(self.signature_spells or [])
        return list(dict.fromkeys(out))

    def fixed_source(self, sid):
        """这个法术是「职业固定」还是「子职固定」, 不是则 None"""
        lv = max(int(self.level or 1), 1)
        if sid in (self.mastery_spells or []) or \
                sid in (self.signature_spells or []):
            return "法师"
        tbl = consts.FIXED_SPELLS or {}
        for gate, ids in (tbl.get("class") or {}).get(self.class_id or "", {}).items():
            if lv >= gate and sid in ids:
                return "职业"
        sub = (tbl.get("subclass") or {}).get(self.subclass or "")
        if sub:
            rows = (sub.get("land") or {}).get(self.land or "temperate") \
                if sub.get("land") else sub.get("table")
            for gate, ids in (rows or {}).items():
                if lv >= gate and sid in ids:
                    return "子职"
        return None

    def prune_fixed(self):
        """把已经由特性授予的法术从手动列表里剔掉, 避免重复显示/重复计数"""
        fixed = set(self.fixed_spells())
        for key in ("cantrips", "prepared"):
            mine = (self.spells or {}).get(key) or []
            self.spells[key] = [s for s in mine if s not in fixed]

    # ---- 2024 超魔法 (Metamagic) ----

    def metamagic_cap(self):
        """已知超魔法上限: 2 级 2 个, 10 级 +2, 17 级 +2"""
        if self.class_id != "sorcerer" or self.level < 2:
            return 0
        return 2 + (2 if self.level >= 10 else 0) + (2 if self.level >= 17 else 0)

    def metamagic_known(self):
        return [m for m in self.metamagic if m in consts.METAMAGIC][
            :self.metamagic_cap()]

    def metamagic_per_spell(self):
        """一道法术能叠几个: 默认 1; 7 级「魔法化身」先天魔法期间 2"""
        if self.level >= 7 and self.innate_active:
            return 2
        return 1

    def mm_free(self):
        """20 级「奥术神化」: 先天魔法期间, 每回合 1 个超魔法不花术法点"""
        return (self.class_id == "sorcerer" and self.level >= 20
                and self.innate_active)

    def mm_cost(self, ids):
        return sum(consts.METAMAGIC[m][1] for m in dict.fromkeys(ids)
                   if m in consts.METAMAGIC)

    def mm_validate(self, ids):
        """返回 (是否可行, 原因, 实际花费)"""
        ids = [m for m in dict.fromkeys(ids) if m in consts.METAMAGIC]
        if not ids:
            return True, "", 0
        known = set(self.metamagic_known())
        for m in ids:
            if m not in known:
                return False, f"未学会「{consts.METAMAGIC[m][0]}」", 0
        main = [m for m in ids if not consts.METAMAGIC[m][3]]
        if len(main) > self.metamagic_per_spell():
            return False, ("一道法术最多只能应用 "
                           f"{self.metamagic_per_spell()} 个超魔法"
                           "（强化/探秘可与其他叠加）"), 0
        cost = self.mm_cost(ids)
        if self.mm_free():          # 免费的那一个按最贵的一项抵扣
            cost -= max(consts.METAMAGIC[m][1] for m in ids)
        cost = max(0, cost)
        if cost > self.sorcery_left():
            return False, (f"术法点不够：这套组合要 {cost} 点，"
                           f"只剩 {self.sorcery_left()} 点"), 0
        return True, "", cost

    def mm_apply(self, ids):
        """扣术法点, 返回 (成功, 日志文案)"""
        ids = [m for m in dict.fromkeys(ids) if m in consts.METAMAGIC]
        ok, why, cost = self.mm_validate(ids)
        if not ok:
            return False, why
        if not ids:
            return True, ""
        raw = self.mm_cost(ids)
        if cost:
            self.res_spend("sorcery", cost)
        names = "＋".join(consts.METAMAGIC[m][0].split(" ")[0] for m in ids)
        saved = f"（奥术神化省下 {raw - cost} 点）" if raw > cost else ""
        spent = f"花 {cost} 点术法点" if cost else "未花术法点"
        return True, f"超魔法 {names}{saved} · {spent}"

    # ---- 先天魔法 (1 级) / 奥术神化 (20 级) ----

    def innate_cap(self):
        return 2 if self.class_id == "sorcerer" else 0

    def innate_left(self):
        return max(0, self.innate_cap() - int(self.innate_used))

    def innate_on(self):
        """开启先天魔法; 次数用完时 7 级起可花 2 点术法点顶上"""
        if self.innate_cap() == 0:
            return False, "只有术士有先天魔法。"
        if self.innate_active:
            return True, ""
        if self.innate_left() > 0:
            self.innate_used += 1
        elif self.level >= 7 and self.sorcery_left() >= 2:
            self.res_spend("sorcery", 2)
        else:
            return False, "先天魔法的次数用完了（长休恢复 2 次）。"
        self.innate_active = True
        return True, ""

    def innate_off(self):
        self.innate_active = False

    def sorcerous_rest(self):
        """术士 5 级「魔法恢复」: 短休回一半术法点 (向下取整), 1 次/长休"""
        if self.class_id != "sorcerer" or self.level < 5:
            return False, ""
        if self.sorcerous_rest_used:
            return False, "「魔法恢复」本次长休已用过"
        spent = int(self.res_used.get("sorcery", 0))
        if spent <= 0:
            return False, ""
        gain = min(spent, self.level // 2)
        self.res_used["sorcery"] = spent - gain
        self.sorcerous_rest_used = True
        return True, f"魔法恢复：术法点 +{gain}"

    # ---- 法师 18 级 法术精通 / 20 级 招牌法术 ----

    def mastery_cap(self):
        """18 级法术精通的法术总数: 1 环 1 个 + 2 环 1 个"""
        return 2 if (self.class_id == "wizard" and self.level >= 18) else 0

    def signature_cap(self):
        return 2 if (self.class_id == "wizard" and self.level >= 20) else 0

    # ---- 法师法术书 (2024 PHB): 书内 → 准备 两层 ----

    def _wizard_spell_ids(self):
        """法师法术表的 id 集合 (惰性缓存)"""
        ids = getattr(self, "_wiz_ids", None)
        if ids is None:
            ids = {s["id"] for s in self.r.class_spells("wizard")}
            self._wiz_ids = ids
        return ids

    def book_max_level(self):
        """能抄进书的最高环级 = 当前能准备的最高环级"""
        if self.class_id != "wizard":
            return 0
        return max(self.max_spell_level(), 1)

    def in_book(self, sid):
        """这个法术是否已经抄在法术书里"""
        return bool(sid) and sid in (self.spellbook or [])

    def book_spells(self, lv=None):
        """法术书里的法术 (可只取某一环)"""
        out = []
        for sid in (self.spellbook or []):
            s = self.r.spell(sid)
            if s and (lv is None or s["level"] == lv):
                out.append(s)
        return sorted(out, key=lambda s: (s["level"], s["name"]))

    def can_prepare(self, sid):
        """能否准备: 必须是法师法术, 且已在法术书中"""
        if self.class_id != "wizard":
            return False
        return self.in_book(sid) and sid in self._wizard_spell_ids()

    def ritual_castable(self, sid):
        """书里的仪式法术可以不准备就直接施放 (额外 10 分钟, 不耗环位)"""
        s = self.r.spell(sid)
        return bool(s) and self.in_book(sid) and bool(s.get("ritual"))

    def copy_cost(self, sid):
        """抄录花费: 50 gp × 环级"""
        s = self.r.spell(sid)
        return 50 * (s["level"] if s else 0)

    def copy_hours(self, sid):
        """抄录耗时: 2 小时 × 环级"""
        s = self.r.spell(sid)
        return 2 * (s["level"] if s else 0)

    def book_add(self, sid, free=False):
        """把法术抄进书 → (ok, msg)。free=True 消耗 1 次免费抄录"""
        s = self.r.spell(sid)
        if not s:
            return False, "法术库里没有这个法术"
        if self.class_id != "wizard":
            return False, "只有法师拥有法术书"
        if sid not in self._wizard_spell_ids():
            return False, f"{s['name']} 不是法师法术，不能抄进法术书"
        if self.in_book(sid):
            return False, f"{s['name']} 已经在法术书里了"
        if s["level"] < 1:
            return False, "戏法不进法术书，直接会就可以"
        top = self.book_max_level()
        if s["level"] > top:
            return False, f"你目前最高只能把 {top} 环法术抄进书里"
        if free:
            if self.book_pending <= 0:
                return False, "没有可用的免费抄录次数了"
            self.book_pending -= 1
        self.spellbook.append(sid)
        tag = "免费抄录" if free else \
            f"花费 {self.copy_cost(sid)} gp · {self.copy_hours(sid)} 小时抄录"
        return True, f"{s['name']}（{s['level']} 环）已写入法术书 · {tag}"

    def book_remove(self, sid):
        """把法术从书里划掉 → (ok, msg)。正准备中的不能移除"""
        s = self.r.spell(sid)
        name = s["name"] if s else "该法术"
        if not self.in_book(sid):
            return False, f"{name} 不在法术书里"
        if sid in ((self.spells or {}).get("prepared") or []):
            return False, f"{name} 正在准备中，请先在法术页取消准备"
        if sid in self.fixed_spells():
            return False, f"{name} 由职业特性始终准备，不能从书里移除"
        self.spellbook.remove(sid)
        return True, f"{name} 已从法术书移除"

    def book_auto_fill(self):
        """兼容旧存档: 没有 spellbook 字段时, 用已准备的法师法术灌满"""
        if self.class_id != "wizard":
            self.spellbook = []
            return
        if self.spellbook:
            return
        wiz = self._wizard_spell_ids()
        for sid in ((self.spells or {}).get("prepared") or []):
            if sid in wiz and sid not in self.spellbook:
                self.spellbook.append(sid)

    def _choice_spells(self, raw, min_level, levels, cap, one_per_level=False):
        """校验「自选法术」: 必须是本职业法术、指定环级、数量受限"""
        if self.class_id != "wizard" or self.level < min_level:
            return []
        wiz = {s["id"] for s in self.r.class_spells("wizard")}
        out, used_lv = [], set()
        for sid in (raw or []):
            if sid in out or sid not in wiz:
                continue
            s = self.r.spell(sid)
            if not s or s["level"] not in levels:
                continue
            if one_per_level and s["level"] in used_lv:
                continue
            out.append(sid)
            used_lv.add(s["level"])
            if len(out) >= cap:
                break
        return out

    def is_mastery_spell(self, sid):
        return sid in (self.mastery_spells or [])

    def is_signature_spell(self, sid):
        return sid in (self.signature_spells or [])

    def signature_left(self, sid):
        """招牌法术本短休还剩几次免费施放"""
        if not self.is_signature_spell(sid):
            return 0
        return 0 if sid in (self.signature_used or []) else 1

    def cantrip_cap(self):
        """戏法数量: 用 2024 职业逐级表 (4 级 / 10 级各 +1)"""
        if self.third_caster():
            row = self._third_row()
            cap = int(row[0]) if row else 0
            return cap + (1 if self.order in ("thaumaturge", "magician") else 0)
        tbl = consts.CANTRIPS_KNOWN.get(self.class_id or "")
        if tbl:
            cap = int(tbl.get(self.level, 0))
        else:
            base = consts.SPELL_COUNTS.get(self.class_id, (0, 0))[0]
            if base <= 0:
                return 0
            cap = base + (1 if self.level >= 4 else 0) \
                + (1 if self.level >= 10 else 0)
        # 神圣职阶·施法者 / 原始职阶·魔术师: 额外 1 个戏法
        if self.order in ("thaumaturge", "magician"):
            cap += 1
        return cap

    def prepared_hint(self):
        """准备/已知法术的数量上限 —— 2024 各职业表逐级固定值"""
        if not self.casting():
            return 0
        if self.third_caster():
            row = self._third_row()
            return int(row[1]) if row else 0
        tbl = consts.PREPARED_SPELLS.get(self.class_id or "")
        if tbl:
            return int(tbl.get(self.level, 0))
        return max(1, self.level + ability_mod(self.score(
            self.casting()["ability"])))

    def lineage_cn(self):
        return consts.LINEAGE_CN.get(self.lineage or "", "")

    # ---- 职业特性 / 资源池 ----

    def class_features(self):
        """[(等级, 名称, 效果, 是否已解锁)] —— 只列本职业, 不含子职"""
        return [(f["level"], f["name"], f["desc"], f["level"] <= self.level)
                for f in self.r.class_features(self.class_id)]

    def subclass_summary(self):
        info = self.r.sub_info(self.subclass) if self.subclass else None
        return info["summary"] if info else ""

    def subclass_features(self):
        """[(等级, 名称, 效果, 是否已解锁)] —— 未选子职时为空"""
        info = self.r.sub_info(self.subclass) if self.subclass else None
        if not info:
            return []
        return [(f["level"], f["name"], f["desc"], f["level"] <= self.level)
                for f in info["features"]]

    def class_stat(self, key, default=0):
        """取 SRD 职业表中的数值 (如 martial_arts_die / sneak_attack)"""
        tbl = self.r.class_detail(self.class_id).get("class_specific") or {}
        row = tbl.get(str(self.level)) or tbl.get(self.level) or {}
        v = row.get(key, default)
        return v if v is not None else default

    def mastery_count(self):
        """武器专精件数: 优先用 SRD 逐级表, 否则退回核心数据"""
        v = self.class_stat("weapon_mastery", None)
        if v is not None and int(v) >= 0:
            return int(v)
        return int(self.cls().get("weapon_mastery_count") or 0)

    def pact_level(self):
        """契约法术位的环级 (邪术师: 全部法术位都是这个环级)"""
        c = self.casting()
        if not c or c["type"] != "pact":
            return 0
        slots = self.spell_slots()
        normal = [lv for lv in slots if lv not in self.arcanum_levels()]
        return max(normal) if normal else 0

    def resource_max(self, res):
        """资源上限: 表驱动或公式驱动"""
        tbl = res.get("table")
        if tbl:
            v = tbl.get(str(self.level), tbl.get(self.level))
            return max(0, int(v or 0))
        f = res.get("formula")
        if f == "level":
            return self.level
        if f == "cha_mod_min1":
            return max(1, ability_mod(self.score("CHA")))
        if f == "wis_mod_min1":
            return max(1, ability_mod(self.score("WIS")))
        if f == "5*level":
            return 5 * self.level
        if f == "half_level_ceil":
            return (self.level + 1) // 2
        if f == "pact_slots":
            slots = self.spell_slots()
            return max(slots.values()) if slots else 0
        return 0

    def _res_die(self, res):
        die = res.get("die")
        if not die:
            return None
        best = None
        for k, v in die.items():
            if self.level >= int(k):
                best = v if best is None else max(best, v)
        return best

    def resources(self):
        """当前职业可用的资源池 (按等级过滤, 已含消耗状态)"""
        out = []
        for res in self.r.class_resources(self.class_id):
            if self.level < int(res.get("from_level", 1)):
                continue
            mx = self.resource_max(res)
            if mx <= 0 and not res.get("die"):
                continue
            if res.get("formula") == "pact_slots":
                # 契约法术位与「法术」页共用同一份已用记录, 避免两处计数打架
                used = int(self.spell_slots_used.get(self.pact_level(), 0))
            else:
                used = int(self.res_used.get(res["id"], 0))
            used = max(0, min(mx, used))
            out.append({
                "id": res["id"], "name": res["name"], "icon": res.get("icon", ""),
                "max": mx, "used": used, "left": mx - used,
                "die": self._res_die(res), "note": res.get("note", ""),
                "short": res.get("short", 0), "long": res.get("long", "all"),
                "short_after_level": res.get("short_after_level"),
                "short_after": res.get("short_after"),
            })
        return out

    def res_spend(self, rid, n=1):
        for res in self.r.class_resources(self.class_id):
            if res["id"] != rid:
                continue
            mx = self.resource_max(res)
            if res.get("formula") == "pact_slots":
                lv = self.pact_level()
                cur = int(self.spell_slots_used.get(lv, 0))
                self.spell_slots_used[lv] = max(0, min(mx, cur + n))
                return self.spell_slots_used[lv]
            used = int(self.res_used.get(rid, 0))
            self.res_used[rid] = max(0, min(mx, used + n))
            return self.res_used[rid]
        return 0

    def res_restore(self, rid, n=1):
        return self.res_spend(rid, -n)

    def res_reset(self, rest="long"):
        """短休: 按每条资源的规则恢复; 长休: 清空"""
        if rest == "long":
            self.res_used = {}
            return
        for res in self.r.class_resources(self.class_id):
            rid = res["id"]
            if res.get("formula") == "pact_slots" and res.get("short") == "all":
                self.spell_slots_used.pop(self.pact_level(), None)
                continue
            if rid not in self.res_used:
                continue
            mx = self.resource_max(res)
            if res.get("short") == "all":
                self.res_used[rid] = 0
            elif res.get("short") == 1:
                self.res_used[rid] = max(0, int(self.res_used.get(rid, 0)) - 1)
            # 达到特定等级后短休也全恢复 (如诗人 5 级灵感泉源)
            lvl = res.get("short_after_level")
            if lvl and self.level >= int(lvl) and res.get("short_after") == "all":
                self.res_used[rid] = 0
            self.res_used[rid] = min(mx, self.res_used.get(rid, 0))

    # ---- 术士·术法源泉 Font of Magic (2 级) ----

    def font_can_use(self):
        return self.class_id == "sorcerer" and self.level >= 2

    def _sorcery_res(self):
        for res in self.r.class_resources(self.class_id):
            if res["id"] == "sorcery":
                return res

    def sorcery_max(self):
        res = self._sorcery_res()
        return self.resource_max(res) if res else 0

    def sorcery_left(self):
        return max(0, self.sorcery_max() - int(self.res_used.get("sorcery", 0)))

    def font_create_slot(self, level):
        """术法点 → 临时法术位 (长休消失)。返回 (是否成功, 提示)"""
        if not self.font_can_use():
            return False, "只有 2 级以上的术士能用术法源泉。"
        conf = consts.FONT_OF_MAGIC
        level = int(level)
        cost = conf["cost"].get(level)
        if not cost or level > conf["max_slot_level"]:
            return False, f"只能兑换 1–{conf['max_slot_level']} 环的法术位。"
        left = self.sorcery_left()
        if left < cost:
            return False, f"术法点不够：需要 {cost} 点，只剩 {left} 点。"
        self.res_spend("sorcery", cost)
        self.font_slots[level] = self.font_slots.get(level, 0) + 1
        return True, (f"花 {cost} 点术法点，兑换 1 个 {level} 环临时法术位"
                      "（长休消失）。")

    def font_burn_slot(self, level):
        """法术位 → 等量术法点。返回 (是否成功, 提示)"""
        if not self.font_can_use():
            return False, "只有 2 级以上的术士能用术法源泉。"
        level = int(level)
        total = self.spell_slots().get(level, 0)
        if total <= 0:
            return False, f"没有 {level} 环法术位可烧。"
        used = int(self.spell_slots_used.get(level, 0))
        if used >= total:
            return False, f"{level} 环法术位已经用完了。"
        room = int(self.res_used.get("sorcery", 0))     # 最多能补回这么多
        if room <= 0:
            return False, "术法点已满，先花掉一些再来烧法术位。"
        gain = min(level, room)
        # 优先烧普通法术位; 普通位都烧光了才动术法源泉换出来的临时位
        base_n = self._base_slots().get(level, 0)
        if (self.font_slots or {}).get(level) and used >= base_n:
            self.font_slots[level] -= 1
            if self.font_slots[level] <= 0:
                self.font_slots.pop(level, None)
        else:
            self.spell_slots_used[level] = used + 1
        self.res_spend("sorcery", -gain)
        return True, f"烧掉 1 个 {level} 环法术位，回复 {gain} 点术法点。"

    def scores(self):
        return {a: self.score(a) for a in ABILITIES}

    def mods(self):
        return {a: ability_mod(self.score(a)) for a in ABILITIES}

    def pb(self):
        return proficiency_bonus(self.level)

    def cls(self):
        return self.r.cls(self.class_id)

    def casting(self):
        """施法配置。1/3 施法者子职 (奥法骑士/诡术师) 也算施法, 只是表不同。"""
        c = self.cls().get("casting")
        if c:
            return c
        third = self.third_caster()
        if third:
            return {"type": "third", "ability": third["ability"],
                    "mode": "prepared", "subclass": True,
                    "spell_list": third["spell_list"],
                    "note": third.get("note", "")}
        return None

    def third_caster(self):
        """若本职业无施法但子职是 1/3 施法者, 返回其配置 (含逐级表)"""
        if not self.subclass or self.level < 3:
            return None
        ent = consts.THIRD_CASTER.get(self.subclass)
        if not ent or ent.get("class") != self.class_id:
            return None
        return ent

    def spell_list_class(self):
        """可选法术列表的来源职业 (奥法骑士/诡术师借用法师列表)"""
        c = self.casting()
        if c and c.get("spell_list"):
            return c["spell_list"]
        return self.class_id

    def _third_row(self):
        t = self.third_caster()
        if not t:
            return None
        return t["table"].get(self.level)

    def can_fighting_style(self):
        """战斗风格只有战士/圣武士/游侠拥有, 且需达到对应等级"""
        need = consts.STYLE_MIN_LEVEL.get(self.class_id)
        return need is not None and self.level >= need

    def style_level_need(self):
        return consts.STYLE_MIN_LEVEL.get(self.class_id)

    # ---- 1 级职阶 (牧师 神圣职阶 / 德鲁伊 原始职阶) ----

    def order_options(self):
        """{key: (名称, 说明)} —— 只有牧师/德鲁伊有"""
        return consts.ORDERS.get(self.class_id or "", {})

    def order_label(self):
        ent = self.order_options().get(self.order or "")
        return ent[0] if ent else ""

    def order_note(self):
        ent = self.order_options().get(self.order or "")
        return ent[1] if ent else ""

    def order_skill_bonus(self, sid):
        """施法者/魔术师: 奥秘（及宗教/自然）检定加感知调整值"""
        if self.order == "thaumaturge" and sid in ("arcana", "religion"):
            return max(1, ability_mod(self.score("WIS")))
        if self.order == "magician" and sid in ("arcana", "nature"):
            return max(1, ability_mod(self.score("WIS")))
        return 0

    def hp_max(self):
        c = self.cls()
        hd = c["hit_die"]
        con = ability_mod(self.score("CON"))
        hp = hd + con + (self.level - 1) * max(1, hd // 2 + 1 + con)
        if self.species_id == "dwarf":       # 矮人韧性 Dwarven Toughness
            hp += self.level
        # Tough 专长: 可能来自 4 级专长, 也可能来自背景的起源专长
        if self.has_tough():
            hp += 2 * self.level
        # 通用专长: 每级额外 HP
        hp += int(self.feat_effects().get("hp_per_level", 0) or 0) * self.level
        # 物品 HP 上限加值
        hp += sum(int(consts.ITEMS_BY_ID.get(i, {}).get("hp_bonus") or 0)
                  for i in self.items)
        return max(1, hp)

    def has_tough(self):
        """Tough(坚忍) 是否生效 —— 手动勾选或专长栏/背景里有都算"""
        return bool(self.tough_feat) or self.has_feat("Tough", "坚忍")

    def spell_slots(self):
        """返回 {环级: 最大次数} —— 含术法源泉兑换出的临时法术位"""
        slots = self._base_slots()
        if not slots:
            return slots
        for lv, n in (self.font_slots or {}).items():
            if n > 0:
                slots[lv] = slots.get(lv, 0) + n
        return slots

    def _base_slots(self):
        """职业表给的法术位 (不含术法源泉兑换)"""
        c = self.casting()
        if not c:
            return {}
        lv = self.level
        if c["type"] == "full":
            return self.r.full_slots(lv)
        if c["type"] == "half":
            return dict(consts.HALF_SLOTS[lv])
        if c["type"] == "third":          # 奥法骑士 / 诡术师
            row = self._third_row()
            return dict(row[2]) if row else {}
        # pact magic (2024: 1级 1 个; 2–10级 2 个; 11–16级 3 个; 17+ 4 个)
        if lv == 1:
            n = 1
        elif lv >= 17:
            n = 4
        elif lv >= 11:
            n = 3
        else:
            n = 2
        sl = min(5, (lv + 1) // 2)
        slots = {sl: n}
        if lv >= 11:
            slots[6] = 1   # 秘契法术 Mystic Arcanum
        if lv >= 13:
            slots[7] = 1
        if lv >= 15:
            slots[8] = 1
        if lv >= 17:
            slots[9] = 1
        return slots

    def slots_recharge_short_rest(self):
        return bool(self.casting() and self.casting()["type"] == "pact")

    def arcanum_levels(self):
        """秘契法术 (Mystic Arcanum, 邪术师 11/13/15/17 级) —— 1 次/长休,
        不属于契约法术位, 短休不恢复。"""
        c = self.casting()
        if not c or c["type"] != "pact":
            return []
        return [lv for lv in (6, 7, 8, 9) if lv in self.spell_slots()]

    def ac(self):
        return self.ac_breakdown()[0]

    def all_feat_names(self):
        """所有专长名 (手动 + 背景起源专长), 去重保序"""
        names = [str(f) for f in getattr(self, "feats", [])]
        bid = getattr(self, "background_id", None)
        if bid:
            bg = next((b for b in self.r.d["backgrounds"]
                       if b["id"] == bid), None)
            if bg and bg.get("origin_feat"):
                names.append(bg["origin_feat"])
        return list(dict.fromkeys(names))

    def feat_effects(self):
        """已持有专长的机械效果汇总 —— 只读 feats_general.json 的 effects 字段"""
        out = {}
        for name in self.all_feat_names():
            info = consts.FEATS_BY_NAME.get(name)
            if not info:
                continue
            for k, v in (info.get("effects") or {}).items():
                if k in ("note_only",):
                    continue
                if isinstance(v, bool):
                    out[k] = bool(out.get(k)) or v
                elif isinstance(v, (int, float)):
                    out[k] = out.get(k, 0) + v
                else:
                    out.setdefault(k, v)
        return out

    def has_feat(self, *keys):
        """专长是否持有 (英文原名或中文关键字命中任一即可)"""
        for f in self.all_feat_names():
            low = f.lower()
            if any(k.lower() in low for k in keys):
                return True
        return False

    def initiative(self):
        m = ability_mod(self.score("DEX")) + self.check_bonus()
        if self.has_feat("Alert", "警觉") \
                or self.feat_effects().get("initiative_pb"):
            m += self.pb()      # 2024 Alert / 同类专长: 先攻 + 熟练加值
        elif self.class_id == "bard" and self.level >= 2:
            # 万事通: 未含熟练加值的属性检定 + 半熟练 (先攻是敏捷检定)
            m += self.pb() // 2
        return m - self.exh_penalty()      # 先攻是敏捷检定, 受力竭影响

    def exh_penalty(self):
        """2024 力竭: 每级所有 d20 检定 -2"""
        return 2 * self.exhaustion

    def check_bonus(self):
        """物品对「属性检定」的加值 (幸运石 +1, 同时加豁免)"""
        return (sum(consts.ITEMS_BY_ID.get(i, {}).get("check", 0) for i in self.items)
                + int(self.feat_effects().get("check", 0) or 0))

    def ability_check_mod(self, ab):
        """纯属性检定修正 (力竭已计入; 诗人万事通给半熟练)"""
        m = ability_mod(self.score(ab)) + self.check_bonus()
        if self.class_id == "bard" and self.level >= 2:
            m += self.pb() // 2
        return m - self.exh_penalty()

    def save_profs(self):
        """豁免熟练集合 —— 职业 + 后期特性 (武僧14 全豁免 / 游荡者15 感魅)"""
        out = set(self.cls().get("saves") or [])
        if self.class_id == "monk" and self.level >= 14:     # 自律生还者
            out |= set(ABILITIES)
        if self.class_id == "rogue" and self.level >= 15:    # 滑溜心智
            out |= {"WIS", "CHA"}
        return out

    def resistances(self):
        """伤害抗性 (来自物品, 并集去重)"""
        out = []
        for iid in self.items:
            for r in (consts.ITEMS_BY_ID.get(iid, {}).get("resist") or []):
                if r not in out:
                    out.append(r)
        return out

    def immunities(self):
        """伤害免疫 (来自物品)"""
        out = []
        for iid in self.items:
            for r in (consts.ITEMS_BY_ID.get(iid, {}).get("immune") or []):
                if r not in out:
                    out.append(r)
        return out

    def condition_immunities(self):
        """状态免疫 (来自物品)"""
        out = []
        for iid in self.items:
            for r in (consts.ITEMS_BY_ID.get(iid, {}).get("condition_immune") or []):
                if r not in out:
                    out.append(r)
        return out

    def save_mod(self, ab):
        m = ability_mod(self.score(ab))
        if ab in self.save_profs():
            m += self.pb()
        for iid in self.items:                       # 防护戒指/斗篷/幸运石
            m += consts.ITEMS_BY_ID.get(iid, {}).get("save", 0)
        sv = self.feat_effects().get("save", 0)      # 通用专长: 豁免加值
        if isinstance(sv, dict):
            m += int(sv.get("all", 0) or 0) + int(sv.get(ab, 0) or 0)
        else:
            m += int(sv or 0)
        # 守护灵光 (圣武士 6 级): 魅力调整值, 最低 +1
        if self.class_id == "paladin" and self.level >= 6:
            m += max(1, ability_mod(self.score("CHA")))
        return m - self.exh_penalty()

    def skill_mod(self, sid):
        sk = self.r.skill_by_id[sid]
        m = ability_mod(self.score(sk["ability"])) + self.check_bonus()
        if sid in self.expertise:
            m += 2 * self.pb()
        elif sid in self.skill_prof:
            m += self.pb()
        elif self.class_id == "bard" and self.level >= 2:    # 万事通: 半熟练
            m += self.pb() // 2
        m += self.order_skill_bonus(sid)      # 职阶给的奥秘/宗教/自然加值
        return m - self.exh_penalty()

    def reliable_talent(self, sid):
        """游荡者 7 级: 熟练技能的属性检定, d20 掷出 9 或以下按 10 计"""
        return (self.class_id == "rogue" and self.level >= 7
                and sid in self.skill_prof)

    def indomitable_might(self, ab):
        """野蛮人 18 级: 力量检定/豁免的总值低于力量值 → 直接用力量值"""
        return (self.class_id == "barbarian" and self.level >= 18
                and ab == "STR")

    # ---- 装备/攻击 ----

    def weapon_entry(self):
        for w in consts.WEAPONS:
            if w[0] == self.weapon:
                return w
        return None

    def weapon_ability(self):
        """武器用哪个属性: 远程用敏捷; 灵巧武器取高者; 其余力量"""
        w = self.weapon_entry()
        if not w:
            return "STR"
        name = w[0]
        props = self.weapon_props(name)
        if "ranged" in props:
            return "DEX"
        if "finesse" in props or name in consts.FINESSSE_SET:
            return "STR" if self.score("STR") >= self.score("DEX") else "DEX"
        # 2024 武艺: 武僧武器 (熟练的近战武器) 也可用敏捷
        if (self.class_id == "monk" and self.level >= 1
                and self.has_weapon_prof(name)):
            return "DEX" if self.score("DEX") >= self.score("STR") else "STR"
        return "STR"

    def is_ranged_weapon(self):
        return "ranged" in self.weapon_props()

    def is_two_handed_weapon(self):
        """必须双手持用 (versatile 两用武器算单手, 可吃决斗风格)"""
        return "two_handed" in self.weapon_props()

    def is_versatile_weapon(self):
        return "versatile" in self.weapon_props()

    def is_heavy_weapon(self):
        return "heavy" in self.weapon_props()

    def heavy_penalty(self):
        """2024 Heavy: 力量<13 的近战重武器 / 敏捷<13 的远程重武器 → 攻击劣势"""
        if not self.is_heavy_weapon():
            return False
        if self.is_ranged_weapon():
            return self.score("DEX") < 13
        return self.score("STR") < 13

    def is_thrown_weapon(self):
        return "thrown" in self.weapon_props()

    # ---- 熟练判定 (武器/护甲/盾牌/工具) ----

    def weapon_prof_rules(self):
        try:
            rules = list(self.cls().get("weapons", []))
        except Exception:
            return []
        # 神圣职阶·保护者 / 原始职阶·守护者: 追加军用武器熟练
        if self.order in ("protector", "warden") and "martial" not in rules:
            rules.append("martial")
        return rules

    def has_weapon_prof(self, name=None):
        name = name or self.weapon
        return Rules.prof_with({"weapons": self.weapon_prof_rules()}, name)

    def armor_cat(self):
        return consts.ARMOR_CAT[self.armor_index]

    def armor_profs(self):
        """护甲熟练 —— 含 1 级职阶给的额外训练"""
        out = list(self.cls().get("armor") or [])
        if self.order == "protector" and "heavy" not in out:
            out.append("heavy")          # 牧师·保护者
        if self.order == "warden" and "medium" not in out:
            out.append("medium")         # 德鲁伊·守护者
        return out

    def has_armor_prof_at(self, idx):
        cat = consts.ARMOR_CAT[idx]
        if cat is None:
            return True
        return cat in self.armor_profs()

    def has_armor_prof(self):
        return self.has_armor_prof_at(self.armor_index)

    def has_shield_prof(self):
        return "shields" in self.armor_profs()

    def armor_penalty(self):
        """未熟练护甲/盾牌、重甲力量不足、隐匿劣势等 (2024 规则)"""
        out = []
        if not self.has_armor_prof():
            out.append(f"⚠ 未熟练{consts.ARMOR_CAT_CN.get(self.armor_cat(), '护甲')}："
                       "力量/敏捷 检定与豁免、攻击检定劣势，且无法施法")
        if self.shield and not self.has_shield_prof():
            out.append("⚠ 未熟练盾牌：力量/敏捷 检定与豁免、攻击检定劣势，且无法施法")
        req = consts.ARMOR_STR_REQ[self.armor_index]
        if req and self.score("STR") < req:
            out.append(f"⚠ {consts.ARMORS[self.armor_index][0]} 需要力量 {req}："
                       f"当前力量 {self.score('STR')} 不足，速度 -10 尺")
        if consts.ARMOR_STEALTH[self.armor_index]:
            out.append(f"⚠ {consts.ARMORS[self.armor_index][0]}：隐匿检定带劣势")
        return out

    def tool_profs(self):
        out = []
        if self.background_id:
            bg = next((b for b in self.r.d["backgrounds"]
                       if b["id"] == self.background_id), None)
            if bg:
                out.append(tool_cn(bg["tool"]))
        for t in (self.cls().get("tools") or []):
            out.append(tool_cn(t))
        return out

    def proficiency_report(self):
        """熟练项汇总 (角色卡展示)"""
        out = []
        rules = self.weapon_prof_rules()
        if "martial" in rules:
            wtxt = "简单武器 + 全部军用武器"
        elif "simple" in rules:
            extra = ""
            if "martial-light-property" in rules:
                extra = " + 带 Light 的军用武器"
            elif "martial-finesse-or-light" in rules:
                extra = " + 带 Finesse/Light 的军用武器"
            wtxt = "简单武器" + extra
        else:
            wtxt = "无"
        cur = f"当前：{self.weapon}" if self.weapon else "当前未装备"
        if self.weapon:
            cur += " ✓" if self.has_weapon_prof() else " ✗未熟练"
        out.append(f"武器：{wtxt}　｜　{cur}")
        arm = self.armor_profs()
        atxt = "、".join(consts.ARMOR_CAT_CN[a] for a in arm) or "无"
        acur = consts.ARMORS[self.armor_index][0] + (" ✓" if self.has_armor_prof()
                                              else " ✗未熟练")
        if self.shield:
            acur += "　｜　盾牌" + ("✓" if self.has_shield_prof() else "✗未熟练")
        out.append(f"护甲：{atxt}　｜　{acur}")
        tools = self.tool_profs()
        out.append("工具：" + ("、".join(f"{t} (+{self.pb()})" for t in tools)
                               if tools else "无"))
        out.append("语言：" + (self.languages.strip(" ,，") or "通用语"))
        out.append("豁免熟练：" + "、".join(ABILITY_CN[a]
                                           for a in self.save_profs()))
        if self.order_note():
            out.append(f"1级职阶：{self.order_label()} —— {self.order_note()}")
        out.extend(self.armor_penalty())
        return out

    def _weapon_item_bonus(self):
        """已勾选魔法武器/弹药提供的 (攻击, 伤害) 加值 —— 取最大, 不叠加"""
        atk = dmg = 0
        for iid in self.items:
            it = consts.ITEMS_BY_ID.get(iid, {})
            if it.get("kind") in ("weapon", "ammunition"):
                atk = max(atk, int(it.get("attack") or 0))
                dmg = max(dmg, int(it.get("damage") or 0))
        return atk, dmg

    def attack_bonus(self):
        w = self.weapon_entry()
        if not w:                       # 徒手打击: 力量 (武僧可用敏捷) + 熟练
            ab = "STR"
            if self.class_id == "monk" and self.level >= 1:
                ab = "DEX" if self.score("DEX") > self.score("STR") else "STR"
            return (ability_mod(self.score(ab)) + self.pb()
                    - self.exh_penalty())
        pb = self.pb() if self.has_weapon_prof(w[0]) else 0   # 未熟练不加熟练加值
        atk_item, _ = self._weapon_item_bonus()               # 魔法武器/弹药
        m = (ability_mod(self.score(self.weapon_ability())) + pb
             + max(self.weapon_magic, atk_item))
        if self.fighting_style == "archery" and self.is_ranged_weapon():
            m += 2
        eff = self.feat_effects()
        m += int(eff.get("attack_bonus", 0) or 0)          # 通用专长: 攻击加值
        if self.is_ranged_weapon():
            m += int(eff.get("attack_bonus_ranged", 0) or 0)
        return m - self.exh_penalty()      # 力竭: 攻击检定 -2/级

    def weapon_props(self, name=None):
        """武器的规则属性 (light/finesse/two_handed/versatile/ranged/thrown)"""
        name = name or self.weapon
        return consts.WEAPON_PROPS.get(name, [])

    def damage_dice(self):
        w = self.weapon_entry()
        if not w:
            # 2024 徒手打击: 1 + 力量调整值; 武僧用武艺骰, 酒馆斗殴者为 1d4
            die = 0
            if self.class_id == "monk":
                die = self.class_stat("martial_arts_die", 0) or 4
            if self.fighting_style == "unarmed":
                # 徒手战斗: 1d6; 另一手完全空着(无副手武器/无盾)则 1d8
                die = max(die, 6)
                if not self.offhand_weapon and not self.shield:
                    die = max(die, 8)
            ud = self.feat_effects().get("unarmed_die")   # 专长给的徒手骰
            if isinstance(ud, str) and "d" in ud:
                try:
                    die = max(die, int(ud.split("d")[1]))
                except ValueError:
                    pass
            if die:
                return f"1d{die}"
            if self.has_feat("Tavern Brawler", "酒馆斗殴"):
                return "1d4"
            return "1"
        if self.two_handed_grip and self.is_versatile_weapon():
            alt = consts.WEAPON_VERSATILE.get(w[0])
            if alt:
                return alt
        return w[2].split(" ")[0]

    def damage_type(self):
        w = self.weapon_entry()
        if not w:
            return "钝击"               # 徒手打击是钝击伤害
        return w[2].split(" ")[1] if len(w[2].split(" ")) > 1 else ""

    def damage_bonus(self):
        w = self.weapon_entry()
        if not w:                       # 徒手: 伤害加值按攻击属性
            ab = "STR"
            if self.class_id == "monk" and self.level >= 1:
                ab = "DEX" if self.score("DEX") > self.score("STR") else "STR"
            m = ability_mod(self.score(ab))
            if self.class_id == "barbarian" and self.raging:
                m += self.rage_damage()
            return m
        _, dmg_item = self._weapon_item_bonus()
        m = (ability_mod(self.score(self.weapon_ability()))
             + max(self.weapon_magic, dmg_item))
        # 决斗: 单手近战武器且另一手没有武器（盾牌不算武器, 可以同时用）
        # 两用武器双手持用时不享受决斗加值; 副手持武器也不行
        if self.fighting_style == "dueling" and not self.is_two_handed_weapon() \
                and not self.is_ranged_weapon() and not self.two_handed_grip \
                and not self.offhand_weapon:
            m += 2
        # 投掷武器战斗: 投掷武器伤害 +2
        if self.fighting_style == "thrown_weapon" \
                and "thrown" in self.weapon_props():
            m += 2
        eff = self.feat_effects()
        m += int(eff.get("damage_bonus", 0) or 0)
        # 巨武器掌握: 重型武器命中时额外 +熟练加值 (每回合 1 次)
        if eff.get("heavy_damage_pb") and self.is_heavy_weapon():
            m += self.pb()
        # 狂暴伤害只加在「用力量」的攻击上 (2024 Rage)
        if self.class_id == "barbarian" and self.raging \
                and self.weapon_ability() == "STR":
            m += self.rage_damage()
        return m

    # ---- 双武器战斗 (附属动作: 副手轻武器再打一下) ----

    def offhand_entry(self):
        return next((w for w in consts.WEAPONS if w[0] == self.offhand_weapon),
                    None)

    def has_dual_wielder(self):
        return self.has_feat("Dual Wielder", "双武器大师")

    def offhand_can_dual(self):
        """2024 Light: 两把都是轻型武器。
        「双武器大师」放宽为「两把都不是双手/两用武器」"""
        main, off = self.weapon, self.offhand_weapon
        if not main or not off:
            return False
        light = set(consts.LIGHT_WEAPONS)
        if main in light and off in light:
            return True
        if not self.has_dual_wielder():
            return False
        bad = {"two_handed", "versatile"}
        return not (set(self.weapon_props(main)) & bad
                    or set(self.weapon_props(off)) & bad)

    def offhand_ability(self):
        w = self.offhand_entry()
        if not w:
            return "STR"
        props = self.weapon_props(w[0])
        if "finesse" in props or w[0] in consts.FINESSSE_SET:
            return "DEX" if self.score("DEX") > self.score("STR") else "STR"
        return "STR"

    def offhand_attack_bonus(self):
        w = self.offhand_entry()
        if not w or not self.offhand_can_dual():
            return 0
        pb = self.pb() if self.has_weapon_prof(w[0]) else 0
        return (ability_mod(self.score(self.offhand_ability())) + pb
                - self.exh_penalty())

    def offhand_damage_dice(self):
        w = self.offhand_entry()
        return w[2].split(" ")[0] if w else ""

    def offhand_damage_type(self):
        w = self.offhand_entry()
        if not w:
            return ""
        parts = w[2].split(" ")
        return parts[1] if len(parts) > 1 else ""

    def offhand_damage_bonus(self):
        """2024: 副手攻击伤害不加属性调整值 (负值照加);
        有「双武器战斗」战斗风格才加"""
        w = self.offhand_entry()
        if not w or not self.offhand_can_dual():
            return 0
        m = ability_mod(self.score(self.offhand_ability()))
        extra = m if self.fighting_style == "two_weapon" else min(0, m)
        if self.class_id == "barbarian" and self.raging \
                and self.offhand_ability() == "STR":
            extra += self.rage_damage()
        return extra

    def offhand_note(self):
        """副手不可用时的原因, 可用则返回空串"""
        if not self.offhand_weapon:
            return ""
        if not self.offhand_can_dual():
            if self.has_dual_wielder():
                return "双武器大师也要求两把都不是双手/两用武器"
            return "副手必须与主手同为轻型武器（或选「双武器大师」专长）"
        return ""

    def speed(self):
        """速度 = 种族基础 + 职业/物品加值 - 力竭(5×级) ；束缚类状态归零"""
        sp = 30
        if self.species_id:
            sp = self.r.sp(self.species_id).get("speed", 30)
        no_armor = self.armor_cat() is None
        # 野蛮人·快速移动 (5级, 非重甲)
        if self.class_id == "barbarian" and self.level >= 5 \
                and self.armor_cat() != "heavy":
            sp += 10
        # 游侠·游荡 Roving (6级, 非重甲): 速度 +10, 并获得等值攀爬/游泳速度
        if self.class_id == "ranger" and self.level >= 6 \
                and self.armor_cat() != "heavy":
            sp += 10
        # 武僧·无甲移动 (2/6/10/14/18 级 → +10/+15/+20/+25/+30, 需无甲无盾)
        if self.class_id == "monk" and self.level >= 2 and no_armor \
                and not self.shield:
            sp += (30 if self.level >= 18 else 25 if self.level >= 14
                   else 20 if self.level >= 10 else 15 if self.level >= 6
                   else 10)
        sp += int(self.feat_effects().get("speed", 0) or 0)   # 通用专长: 速度
        for iid in self.items:
            it = consts.ITEMS_BY_ID.get(iid, {})
            sp += it.get("speed", 0) + it.get("speed_bonus", 0)
            # 速度之靴: 步行速度翻倍
            if it.get("speed_mult"):
                sp *= it["speed_mult"]
        # 重甲力量需求不满足 → 速度 -10 尺 (2024)
        if self.armor_cat() == "heavy":
            req = consts.ARMOR_STR_REQ[self.armor_index]
            if req and self.score("STR") < req:
                sp -= 10
        sp -= 5 * self.exhaustion
        for cond in ("擒抱", "束缚", "麻痹", "震慑", "昏迷", "石化"):
            if cond in self.conditions:
                return 0
        return max(0, sp)

    def carry_capacity(self):
        """负重上限 = 力量 × 15 磅；推/拉/举 = 力量 × 30 磅"""
        s = self.score("STR")
        return s * 15, s * 30

    # ---- 2024 休息 / 濒死 / 专注 ----

    def hit_die(self):
        return self.cls()["hit_die"]

    def hit_dice_max(self):
        return max(1, self.level)          # 单职业: 生命骰数 = 等级

    def hit_dice_left(self):
        return max(0, self.hit_dice_max() - self.hit_dice_used)

    def spend_hit_dice(self, n=1, rolls=None):
        """短休花生命骰回血: 每颗 = d{生命骰} + 体质调整值
        rolls 可传入预先掷好的点数(测试用), 返回 (实际消耗, 回复量, 明细)"""
        n = max(0, min(n, self.hit_dice_left()))
        if n <= 0:
            return 0, 0, []
        con = ability_mod(self.score("CON"))
        die = self.hit_die()
        detail, total = [], 0
        for i in range(n):
            raw = rolls[i] if rolls and i < len(rolls) else random.randint(1, die)
            heal = max(1, raw + con)
            total += heal
            detail.append(f"d{die}={raw}{mod_str(con)}→{heal}")
        self.hit_dice_used += n
        self.hp_current = min(self.hp_max(), self.hp_current + total)
        return n, total, detail

    @property
    def is_dying(self):
        return self.hp_current <= 0

    def concentration_dc(self, damage):
        """受伤专注豁免 DC = max(10, 伤害 // 2)"""
        return max(10, int(damage) // 2)

    def condition_blocks_action(self):
        """这些状态下不能执行动作/施法"""
        return bool(self.conditions & {"失能", "麻痹", "震慑", "昏迷", "石化"})

    def attacks_per_action(self):
        """攻击动作的挥击次数 (含职业与子职的额外攻击)"""
        n = 1
        for lv, name, _d, unlocked in self.class_features():
            if not unlocked:
                continue
            if "三重额外攻击" in name:
                n = max(n, 4)
            elif "双重额外攻击" in name:
                n = max(n, 3)
            elif "额外攻击" in name:
                n = max(n, 2)
        for lv, name, _d, unlocked in self.subclass_features():
            if unlocked and "额外攻击" in name:
                n = max(n, 2)
        return n

    def martial_arts_die(self):
        """武僧武艺骰 (1/5/11/17 级 → d6/d8/d10/d12); 非武僧返回 0"""
        return int(self.class_stat("martial_arts_die", 0) or 0)

    def sneak_dice(self):
        """偷袭骰数 (游荡者): 优先取 SRD 逐级表, 否则 1 级起每 2 级 +1d6"""
        if self.class_id != "rogue":
            return 0
        sa = self.class_stat("sneak_attack", None)
        if isinstance(sa, dict) and sa.get("dice_count"):
            return int(sa["dice_count"])
        return (self.level + 1) // 2

    def mastery_dc(self, wname):
        """武器专精的豁免 DC (撂倒/推撞等) = 8 + 攻击属性调整值 + 熟练加值"""
        if wname == self.weapon:
            ab = self.weapon_ability()
        else:
            props = self.weapon_props(wname)
            if "ranged" in props:
                ab = "DEX"
            elif "finesse" in props:
                ab = "STR" if self.score("STR") >= self.score("DEX") else "DEX"
            else:
                ab = "STR"
        pb = self.pb() if self.has_weapon_prof(wname) else 0
        return 8 + ability_mod(self.score(ab)) + pb

    def rage_damage(self):
        return self.class_stat("rage_damage_bonus", 0) or 0


    def _shield_item_bonus(self):
        """已勾选「盾牌 +N」物品的 AC 增强 (与手工 shield_magic 取大, 不叠加)"""
        out = 0
        for iid in self.items:
            it = consts.ITEMS_BY_ID.get(iid, {})
            if it.get("kind") != "armor":
                continue
            nm = it.get("name", "")
            if "盾" in nm or "Shield" in nm:
                out = max(out, int(it.get("ac_bonus_armor") or 0))
        return out

    def _armor_item_bonus(self):
        """已勾选「护甲 +N」物品的 AC 增强 (盾牌不算, 走 _shield_item_bonus)"""
        out = 0
        for iid in self.items:
            it = consts.ITEMS_BY_ID.get(iid, {})
            if it.get("kind") != "armor":
                continue
            nm = it.get("name", "")
            if "盾" in nm or "Shield" in nm:
                continue
            out = max(out, int(it.get("ac_bonus_armor") or 0))
        return out

    def ac_breakdown(self):
        """返回 (AC, [来源说明...])"""
        name, base, cap = consts.ARMORS[self.armor_index]
        dex = ability_mod(self.score("DEX"))
        notes = []
        # 大法师长袍等: 无甲无盾时以固定基础 AC 替代 10 (不是叠加)
        base_ac_item = 0
        if not self.shield:
            for iid in self.items:
                it0 = consts.ITEMS_BY_ID.get(iid, {})
                if it0.get("base_ac") and it0.get("no_armor"):
                    base_ac_item = max(base_ac_item, int(it0["base_ac"]))
        if base is None:
            if base_ac_item:
                ac = base_ac_item + dex
                notes.append(f"物品·基础 AC {base_ac_item}+敏捷({mod_str(dex)})")
            elif self.class_id == "barbarian":
                ac = 10 + dex + ability_mod(self.score("CON"))
                notes.append("无甲防御(野蛮人) 10+敏捷+体质")
            elif self.class_id == "monk" and not self.shield:
                ac = 10 + dex + ability_mod(self.score("WIS"))
                notes.append("无甲防御(武僧) 10+敏捷+感知")
            else:
                ac = 10 + dex
                notes.append(f"无甲 10+敏捷({mod_str(dex)})")
        else:
            used = dex if cap is None else min(dex, cap)
            ac = base + used
            notes.append(f"{name} {base}{mod_str(used)}")
            ab = self._armor_item_bonus()          # 魔法护甲的增强加值
            if ab:
                ac += ab
                notes.append(f"物品·护甲增强 +{ab}")
        if self.shield:
            sh = max(self.shield_magic, self._shield_item_bonus())
            ac += 2 + sh
            notes.append(f"盾牌 +{2 + sh}")
        feat_ac = int(self.feat_effects().get("ac", 0) or 0)
        if feat_ac:
            ac += feat_ac
            notes.append(f"专长·AC +{feat_ac}")
        if self.fighting_style == "defense" and base is not None:
            ac += 1
            notes.append("战斗风格·防御 +1")
        for iid in self.items:
            it = consts.ITEMS_BY_ID.get(iid, {})
            if it.get("no_armor") and (base is not None or self.shield):
                continue          # 防御护腕: 需无甲且无盾
            if it.get("ac"):
                ac += it["ac"]
                notes.append(f"{it['name'].split(' ')[0]} +{it['ac']}")
        return ac, notes

    def wild_shapes(self):
        """荒野变形可选形态 (德鲁伊, 按等级/子职筛 CR)"""
        from . import wildshape
        if self.class_id != "druid":
            return []
        return wildshape.shapes(self.level, self.subclass)

    def wild_shape(self):
        """当前变身形态的野兽数据 (由 monsters.json 提供)"""
        return consts.MONSTERS_BY_ID.get(self.wild_shape_id or "")

    def senses(self):
        """特殊感官 {'blindsight': 10, 'darkvision': 60} —— 来源: 盲斗风格 / 物品"""
        out = {}
        if self.fighting_style == "blind_fighting":
            out["blindsight"] = 10
        for iid in self.items:
            it = consts.ITEMS_BY_ID.get(iid, {})
            for key in ("blindsight", "darkvision"):
                v = int(it.get(key) or 0)
                if v > out.get(key, 0):
                    out[key] = v
        return out

    def passive_perception(self):
        return 10 + self.skill_mod("perception")

    def spell_dc(self):
        c = self.casting()
        if not c:
            return None
        m = 8 + ability_mod(self.score(c["ability"])) + self.pb()
        for iid in self.items:          # 大法师长袍等: 法术豁免 DC 加值
            m += int(consts.ITEMS_BY_ID.get(iid, {}).get("spell_dc") or 0)
        return m

    def spell_attack(self):
        c = self.casting()
        if not c:
            return None
        # 法术攻击是 d20 攻击检定, 受力竭影响
        m = (ability_mod(self.score(c["ability"])) + self.pb()
             - self.exh_penalty())
        for iid in self.items:
            m += int(consts.ITEMS_BY_ID.get(iid, {}).get("spell_attack") or 0)
        return m

    def bonus_breakdown(self):
        """列出所有自动生效的加值来源, 便于核对"""
        out = []
        if self.exhaustion:
            out.append(f"⚠ 力竭 {self.exhaustion} 级: 攻击/豁免/属性检定/技能 "
                       f"已全部 -{self.exh_penalty()}，速度 -{5 * self.exhaustion} 尺")
        if self.species_id:
            sp = self.r.sp(self.species_id)
            if self.species_id == "dwarf":
                out.append(f"种族·矮人韧性: HP 上限 +{self.level}")
            if self.species_id in ("human", "elf"):
                out.append(f"种族·{sp['name']}: 额外 1 项技能熟练")
        if self.has_tough():
            out.append(f"专长·Tough: HP 上限 +{2 * self.level}")
        if self.has_feat("Alert", "警觉"):
            out.append(f"专长·Alert: 先攻 +{self.pb()} (熟练加值)")
        if self.class_id in ("barbarian", "monk") and consts.ARMORS[self.armor_index][1] is None:
            out.append("职业·无甲防御: AC 计入第二属性")
        if self.class_id == "barbarian" and self.level >= 5:
            out.append("职业·快速移动: 速度 +10 尺")
        if self.class_id == "ranger" and self.level >= 6 \
                and self.armor_cat() != "heavy":
            out.append(f"职业·游荡: 速度 +10 尺，攀爬/游泳速度 = {self.speed()} 尺")
        if self.class_id == "monk" and self.level >= 2:
            out.append("职业·无甲移动: 速度提升")
        if self.class_id == "paladin" and self.level >= 6:
            out.append(f"职业·守护灵光(10尺): 豁免 "
                       f"+{max(1, ability_mod(self.score('CHA')))} (魅力, 最低 +1)")
        if self.class_id == "monk" and self.level >= 14:
            out.append("职业·自律生还者: 全部豁免熟练；失败可花 1 气点重掷")
        if self.class_id == "rogue" and self.level >= 15:
            out.append("职业·滑溜心智: 感知与魅力豁免熟练")
        if self.class_id == "rogue" and self.level >= 7:
            out.append("职业·可靠天赋: 熟练技能的检定，d20 掷出 9 或以下按 10 计")
        if self.class_id == "barbarian" and self.level >= 18:
            out.append(f"职业·不屈之力: 力量检定/豁免总值不低于力量值 "
                       f"{self.score('STR')}")
        if self.level >= 20 and self.class_id in ("barbarian", "monk"):
            out.append("职业·20级压轴: 力量与体质 / 敏捷与感知 各 +4（上限 25）")
        if self.class_id == "bard" and self.level >= 2:
            out.append(f"职业·万事通: 非熟练检定 +{self.pb() // 2}")
        if self.fighting_style:
            nm, desc, _ = consts.FIGHTING_STYLES[self.fighting_style]
            out.append(f"战斗风格·{nm}: {desc}")
        # 守护 / 拦截 是反应, 涉及同伴与时机, 只提示不自动结算
        if self.fighting_style == "protection" and self.shield:
            out.append("战斗风格·守护: 持盾时用反应, 使 5 尺内对同伴的一次攻击带劣势")
        elif self.fighting_style == "interception" \
                and (self.shield or self.weapon):
            out.append(f"战斗风格·拦截: 反应使同伴受到的伤害减 1d10+{self.pb()}"
                       f"（需持盾或武器）")
        for iid in self.items:
            it = consts.ITEMS_BY_ID.get(iid, {})
            txt = it.get("note") or it.get("desc", "")
            if len(txt) > 40:
                txt = txt[:39] + "…"
            out.append(f"物品·{it.get('name')}: {txt}")
        if self.weapon_magic:
            out.append(f"武器魔法加值: 命中/伤害 +{self.weapon_magic}")
        if self.shield_magic:
            out.append(f"盾牌魔法加值: AC +{self.shield_magic}")
        # 熟练项提醒
        if self.weapon and not self.has_weapon_prof(self.weapon):
            out.append(f"⚠ 未熟练武器「{self.weapon}」：攻击检定不加熟练加值"
                       f"（当前命中 {mod_str(self.attack_bonus())}）")
        if self.weapon and self.heavy_penalty():
            abn = "敏捷" if self.is_ranged_weapon() else "力量"
            out.append(f"⚠ 重型武器「{self.weapon}」：{abn}不足 13，攻击检定带劣势")
        if self.is_ranged_weapon():
            out.append("⚠ 远程武器：5 尺内有敌人时攻击带劣势；"
                       "超过常规射程（远射程内）也带劣势")
        if self.weapon and "light" in self.weapon_props():
            out.append("轻型武器：攻击动作后可附赠动作，用另一把轻型武器再攻一次"
                       "（该次伤害不加属性调整值；Nick 专精可并入攻击动作）")
        if self.weapon and "loading" in self.weapon_props():
            out.append("装填武器：每回合只能射击 1 次（忽略装填属性的特性除外）")
        if self.two_handed_grip and self.is_versatile_weapon():
            out.append(f"当前双手持用「{self.weapon}」：伤害骰 "
                       f"{self.damage_dice()}（不适用决斗风格）")
        out.extend(self.armor_penalty())
        # 职业里程碑 (信息提示, 数值需按情境判定)
        lv = self.level
        n_atk = self.attacks_per_action()
        if n_atk > 1:
            out.append(f"职业·额外攻击: 攻击动作可攻击 {n_atk} 次 "
                       f"（掷攻击会一次投 {n_atk} 个 d20）")
        if self.class_id == "barbarian" and lv >= 1:
            rd = self.rage_damage()
            if self.raging:
                out.append(f"职业·狂暴(进行中): 伤害 +{rd} 已计入 · "
                           "物理伤害抗性 · 力量检定/豁免优势 · 不能专注")
            else:
                out.append(f"职业·狂暴: 伤害 +{rd}，物理伤害抗性 "
                           "（在「职业」页点开狂暴后再算）")
        if self.class_id == "rogue":
            n = self.sneak_dice()
            out.append(f"职业·偷袭: 额外 {n}d6 (优势或同伴相邻时，"
                       "勾选「含偷袭」后掷伤害会加上)")
        if self.class_id == "monk":
            d = self.class_stat("martial_arts_die", 0)
            out.append(f"职业·武艺: 徒手/武僧武器伤害骰 "
                       f"{('1d%d' % d) if d else '1d4'}（附赠动作可再攻击 1 次）")
        if self.class_id == "paladin" and lv >= 2:
            out.append("职业·至圣斩: 命中后可用法术位追加 2d8 光耀 (每击一次)")
        # 其余专长: 明确提示需手动应用, 避免误以为已计入
        auto = ("tough", "alert", "坚忍", "坚韧", "警觉")
        manual = [f for f in list(self.feats)
                  if not any(k in f.lower() for k in auto)]
        if manual:
            out.append("其余专长 (需手动应用): " + "、".join(feat_cn(f) for f in manual))
        return out

    # ---- 检定 ----

    def d20_mod_total(self, mod):
        """d20 检定的最终修正。

        力竭惩罚 (-2/级) 已经计入 save_mod / skill_mod / attack_bonus /
        initiative / ability_check_mod, 所以这里不再重复扣, 只保留这个
        函数作为统一出口。"""
        return mod

    def roll_d20(self, label, mod):
        raw = random.randint(1, 20)
        total = raw + self.d20_mod_total(mod)
        ex = f" (力竭-{2 * self.exhaustion})" if self.exhaustion else ""
        return f"{label}\nd20: {raw} {mod_str(mod)}{ex} = {total}"

    # ---- 序列化 ----

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
