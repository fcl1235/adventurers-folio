# -*- coding: utf-8 -*-
"""角色模型分片: core/derived.py (由 character.py 物理拆分, P1 纯搬运)。"""
import random
from .. import consts
from ..util import (ability_mod, mod_str)


class DerivedMixin:
    """DerivedMixin"""

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

    def ac(self):
        return self.ac_breakdown()[0]

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

    def wild_shapes(self):
        """荒野变形可选形态 (德鲁伊, 按等级/子职筛 CR)"""
        from .. import wildshape
        if self.class_id != "druid":
            return []
        return wildshape.shapes(self.level, self.subclass)

    def wild_shape(self):
        """当前变身形态的野兽数据 (由 monsters.json 提供)"""
        return consts.MONSTERS_BY_ID.get(self.wild_shape_id or "")
