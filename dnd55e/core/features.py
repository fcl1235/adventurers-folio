# -*- coding: utf-8 -*-
"""角色模型分片: core/features.py (由 character.py 物理拆分, P1 纯搬运)。"""
from .. import consts
from ..util import (ability_mod)


class FeaturesMixin:
    """FeaturesMixin"""

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
            if info.get("_sec") == "epic_boon":
                continue    # 传奇恩惠另走 boon_effects (属性上限 30, 不能混算)
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

    def boon_names(self):
        """已领取的传奇恩惠名 (英文原名), 按领取顺序去重"""
        out = []
        for name in self.all_feat_names():
            info = consts.FEATS_BY_NAME.get(name)
            if not info or info.get("_sec") != "epic_boon":
                continue
            if name not in out:
                out.append(name)
        return out

    def boon_effects(self):
        """传奇恩惠的机械效果汇总 —— 与 feat_effects 分开,
        因为传奇恩惠的属性加值上限是 30 (普通专长仍是 20)。"""
        out = {}
        for name in self.boon_names():
            info = consts.FEATS_BY_NAME.get(name) or {}
            for k, v in (info.get("effects") or {}).items():
                if k in ("note_only", "ability_boost"):
                    continue
                if k == "resist_choice":        # 已选的两项抗性
                    for r in self.boon_resist:
                        if r not in out.setdefault("resist", []):
                            out["resist"].append(r)
                    continue
                if isinstance(v, bool):
                    out[k] = bool(out.get(k)) or v
                elif isinstance(v, (int, float)):
                    out[k] = out.get(k, 0) + v
                else:
                    out.setdefault(k, v)
        return out

    def boon_has(self, key):
        """是否持有带某个 effects 键的传奇恩惠 (如 resist_choice)"""
        for name in self.boon_names():
            info = consts.FEATS_BY_NAME.get(name) or {}
            if key in (info.get("effects") or {}):
                return True
        return False

    def boon_resist_pool(self):
        """恩惠允许选择的伤害类型 (resist_choice.from 的并集)"""
        pool = []
        for name in self.boon_names():
            info = consts.FEATS_BY_NAME.get(name) or {}
            rc = (info.get("effects") or {}).get("resist_choice") or {}
            for r in (rc.get("from") or []):
                if r not in pool:
                    pool.append(r)
        return pool

    def boon_resist_limit(self):
        """可选的抗性条数上限 (resist_choice.count 之和)"""
        n = 0
        for name in self.boon_names():
            info = consts.FEATS_BY_NAME.get(name) or {}
            rc = (info.get("effects") or {}).get("resist_choice") or {}
            n += int(rc.get("count") or 0)
        return n

    def boon_ability_cap(self, ab):
        """传奇恩惠把单项属性上限抬到 30 (只针对它加值属性的那一项)"""
        best = 20
        for name in self.boon_names():
            info = consts.FEATS_BY_NAME.get(name) or {}
            boost = (info.get("effects") or {}).get("ability_boost") or {}
            cap = int(boost.get("max") or 0)
            if not cap or ab not in (boost.get("from") or []):
                continue
            # 只有真正把 +1 记在这一项上, 才享受上限提升
            if self.boon_ability.get(name) == ab:
                best = max(best, cap)
        return best

    def boon_ability_bonus(self, ab):
        """传奇恩惠给出的 +1 (每项恩惠各 +1)"""
        n = 0
        for name in self.boon_names():
            if self.boon_ability.get(name) == ab:
                n += 1
        return n

    def skill_all_proficient(self):
        """是否获得全部技能熟练 (传奇恩惠「技艺」)"""
        return bool(self.boon_effects().get("skill_all_prof"))

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

    def can_fighting_style(self):
        """战斗风格只有战士/圣武士/游侠拥有, 且需达到对应等级"""
        need = consts.STYLE_MIN_LEVEL.get(self.class_id)
        return need is not None and self.level >= need

    def style_level_need(self):
        return consts.STYLE_MIN_LEVEL.get(self.class_id)

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

    def martial_arts_die(self):
        """武僧武艺骰 (1/5/11/17 级 → d6/d8/d10/d12); 非武僧返回 0"""
        return self.cls_module().martial_arts_die(self)

    def sneak_dice(self):
        """偷袭骰数 (游荡者): 优先取 SRD 逐级表, 否则 1 级起每 2 级 +1d6"""
        return self.cls_module().sneak_dice(self)

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
