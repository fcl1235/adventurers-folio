# -*- coding: utf-8 -*-
"""角色模型分片: core/checks.py (由 character.py 物理拆分, P1 纯搬运)。"""
import random
from .. import consts
from ..consts import (ABILITIES, feat_cn)
from ..util import (ability_mod, mod_str)


class ChecksMixin:
    """ChecksMixin"""

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
