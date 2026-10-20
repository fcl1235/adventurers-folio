# -*- coding: utf-8 -*-
"""职业模块基类。

一个职业的全部规则集中在一个模块里：数值加值、说明文案、存档字段、UI 板块。
新增职业 = 新建一个文件 + 一行 @register，主程序零改动。

约定：
* 所有 hook 都接收 `ch`（角色对象），模块只读取它，不保存自己的状态。
* 模块**不得** import `core` / `spellcasting`，避免循环导入。
* 默认实现都是"无效果"，职业模块只覆盖自己需要的 hook。
"""


class ClassModule:
    """职业规则的空实现。"""

    class_id = ""
    name_cn = ""

    # ---- 属性与加值 ----
    def ability_cap(self, ch, ab):
        """该属性的上限（默认 20）。"""
        return 20

    def capstone_bonus(self, ch, ab):
        """20 级压轴给该属性的固定加值（默认 0）。"""
        return 0

    def expertise_allowance(self, ch, level):
        """专精可选数量。"""
        return 0

    # ---- AC / 速度 ----
    def unarmored_ac(self, ch, dex_mod):
        """无甲防御：返回 (AC, 说明) 或 None。"""
        return None

    def speed_bonus(self, ch):
        """职业给的速度加值（尺）。"""
        return 0

    # ---- 检定 ----
    def half_proficiency(self, ch):
        """非熟练项的"半熟练"加值（诗人万事通）。"""
        return 0

    def save_profs_extra(self, ch):
        """后期特性追加的豁免熟练集合。"""
        return set()

    def save_bonus(self, ch, ab):
        """豁免上的职业加值（圣武士守护灵光）。"""
        return 0

    def reliable_talent(self, ch, skill_id):
        """可靠天赋：熟练技能的 d20 低于 10 按 10 计。"""
        return False

    def indomitable_might(self, ch, ab):
        """不屈之力：检定总值不低于属性值。"""
        return False

    # ---- 攻击 / 伤害 ----
    def weapon_ability_override(self, ch, name, props):
        """武器可用哪个属性攻击（武僧武艺）。返回 "STR"/"DEX" 或 None。"""
        return None

    def unarmed_ability(self, ch):
        """徒手打击的攻击属性。返回 "STR"/"DEX" 或 None。"""
        return None

    def unarmed_die(self, ch):
        """徒手伤害骰面数（武僧武艺）。0 表示无特殊。"""
        return 0

    def damage_bonus_extra(self, ch, ability, two_handed):
        """武器/徒手伤害上的职业加值（野蛮人狂暴）。"""
        return 0

    def sneak_dice(self, ch):
        """偷袭骰数（游荡者）。"""
        return 0

    def martial_arts_die(self, ch):
        """武艺骰面数（武僧）。"""
        return 0

    # ---- 说明文案：返回 [(优先级, 文案)] ----
    def explain(self, ch, phase):
        """phase="early" 在战斗风格之前；phase="late" 在装备提示之后。

        优先级决定输出顺序，与模块注册顺序无关；同优先级按注册顺序。
        优先级取值沿用拆分前 bonus_breakdown 里的书写次序，保证输出逐字一致。
        """
        return []

    # ---- 施法相关 ----
    def owns_spellbook(self, ch):
        """是否拥有"法术书"这一机制（法师）。"""
        return False

    def mastery_cap(self, ch):
        """法术精通可选数量。"""
        return 0

    def signature_cap(self, ch):
        """招牌法术可选数量。"""
        return 0

    def font_can_use(self, ch):
        """能否使用术法源泉。"""
        return False

    def metamagic_cap(self, ch):
        """已知超魔法上限。"""
        return 0

    def innate_cap(self, ch):
        """先天魔法次数上限。"""
        return 0

    def mm_free(self, ch):
        """超魔法是否有一次免费。"""
        return False

    def sorcerous_rest_ok(self, ch):
        """能否使用「魔法恢复」。"""
        return False

    def wild_shape_allowed(self, ch):
        """能否荒野变形（德鲁伊）。"""
        return False

    def companion(self, ch):
        """野兽伙伴面板数据（游侠·驯兽师）。默认没有。"""
        return None

    def can_rage(self, ch):
        """能否进入狂暴（野蛮人）。"""
        return False

    # ---- 存档 ----
    def pre_slots_state(self, ch, d, to_int):
        """在读取 spell_slots_used 之前恢复职业状态（顺序敏感）。"""
        return None

    def post_state(self, ch, d):
        """在 HP 钳制之后恢复职业状态。"""
        return None

    # ---- UI ----
    def render_panel(self, app, parent, ch):
        """在「职业」页里渲染本职业专属的板块。"""
        return None
