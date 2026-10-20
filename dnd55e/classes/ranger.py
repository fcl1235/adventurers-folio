# -*- coding: utf-8 -*-
"""游侠：游荡（速度 +10）、专精。"""
from . import registry
from .base import ClassModule


@registry.register("ranger")
class Ranger(ClassModule):
    name_cn = "游侠"

    def expertise_allowance(self, ch, level):
        return (1 if level >= 2 else 0) + (2 if level >= 9 else 0)

    def speed_bonus(self, ch):
        """游荡 Roving (6 级, 非重甲): 速度 +10"""
        if ch.level >= 6 and ch.armor_cat() != "heavy":
            return 10
        return 0

    def explain(self, ch, phase):
        if phase == "early" and ch.level >= 6 and ch.armor_cat() != "heavy":
            return [(152, f"职业·游荡: 速度 +10 尺，攀爬/游泳速度 = {ch.speed()} 尺")]
        return []

    # ---- 驯兽师 Beast Master: 原始伙伴 (3 级) ----
    COMPANIONS = ("beast-of-the-land", "beast-of-the-sea", "beast-of-the-sky")

    def companion(self, ch):
        """驯兽师 3 级起获得原始伙伴; 返回按等级算好的面板数据"""
        if ch.subclass != "Beast Master" or ch.level < 3:
            return None
        from .. import consts
        from ..util import ability_mod, mod_str
        options = [m for m in (consts.MONSTERS_BY_ID.get(i) for i in
                               self.COMPANIONS) if m]
        if not options:
            return None
        cid = ch.companion_id
        cur = consts.MONSTERS_BY_ID.get(cid or "") or options[0]
        if not cur.get("companion"):
            cur = options[0]
        table = cur.get("scaling") or {}
        wis = ability_mod(ch.score("WIS"))
        ac = 13 + wis
        per = int(table.get("per_level") or 0)
        hp = int(cur.get("hp") or 0) + per * ch.level
        hp_txt = (table.get("hp") or "").replace("游侠等级", str(ch.level))
        st = cur.get("strike") or {}
        flat = int(st.get("flat") or 0) + wis
        dmg = f"{st.get('damage', '')}+{flat}"
        return {
            "id": cur["id"], "name": cur["name"],
            "ac": ac, "ac_note": f"13 + 感知 {mod_str(wis)}",
            "hp": hp, "hp_formula": hp_txt,
            "strike": f"野兽打击：命中 {mod_str(ch.spell_attack())}"
                      f"（你的法术攻击）· 伤害 {dmg} {st.get('damage_type', '')}"
                      f"（{st.get('damage')} + 固定 {st.get('flat')}"
                      f" + 感知 {wis}）"
                      + (f" · {st['extra']}" if st.get("extra") else ""),
            "strike_parts": st, "wis_mod": wis,
            "note": "附赠动作指挥它疾行/撤离/闪避/协助；"
                    "也可牺牲你攻击动作中的一次攻击，让它用野兽打击。"
                    "每次长休可换一种形态，死亡 1 小时内可耗一个法术位复活。",
            "options": [{"id": m["id"], "name": m["name"]} for m in options],
        }
