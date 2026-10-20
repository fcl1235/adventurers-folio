# -*- coding: utf-8 -*-
"""角色模型分片: core/combat/weapons.py (由 character.py 物理拆分, P1 纯搬运)。"""
from ... import consts
from ...consts import (ABILITY_CN, tool_cn)
from ...util import (ability_mod)
from ...rules import Rules


class WeaponsMixin:
    """WeaponsMixin"""

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
