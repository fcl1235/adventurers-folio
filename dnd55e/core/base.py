# -*- coding: utf-8 -*-
"""角色模型分片: core/base.py (由 character.py 物理拆分, P1 纯搬运)。"""
from .. import consts, classes
from ..consts import (ABILITIES)
from ..util import (ability_mod, proficiency_bonus)
from ..rules import Rules


class BaseMixin:
    """BaseMixin"""

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
        # ---- 传奇恩惠 (19 级起) 的选择结果 ----
        self.boon_ability = {}        # {"Enemy name": "CON"} 传奇恩惠领到的 +1 属性
        self.boon_resist = []         # 恩惠「能量抗性」选定的伤害类型 (如 ["fire","cold"])
        self.boon_expertise = []      # 恩惠「技艺」选定的专精技能 id

    def cls_module(self):
        """当前职业的规则模块 (未选职业时返回空实现)。"""
        return classes.get(self.class_id)

    def ability_cap(self, ab):
        """属性上限: 常规 20, 由职业模块决定是否放宽"""
        return self.cls_module().ability_cap(self, ab)

    def capstone_bonus(self, ab):
        """20 级职业压轴: 原始冠军 / 身心合一 —— 两项属性各 +4"""
        return self.cls_module().capstone_bonus(self, ab)

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
        # 传奇恩惠: 单项 +1 且上限抬到 30 (19 级起)
        if self.boon_names():
            s += self.boon_ability_bonus(ab)
            s = min(max(self.ability_cap(ab), self.boon_ability_cap(ab)), s)
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
        """专精 (Expertise) 允许项数 —— 由职业模块决定"""
        return self.cls_module().expertise_allowance(self, self.level)

    def weapon_mastery_pool(self):
        return {w[0] for w in Rules.class_mastery_pool(self.cls())}

    def lineage_cn(self):
        return consts.LINEAGE_CN.get(self.lineage or "", "")

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
