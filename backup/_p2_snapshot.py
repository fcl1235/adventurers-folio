# -*- coding: utf-8 -*-
"""P2/P3 回归快照: 对 12 职业 × 1-20 级枚举全部纯计算方法的输出, 存 JSON。

改代码前跑一次 -> baseline.json, 改完再跑 -> current.json, 逐键 diff。
任何一处 class_id 分支迁移出错都会立刻暴露, 不需要靠 _flowtest 的人肉断言覆盖。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dnd55e.character import Character          # noqa: E402
from dnd55e.rules import Rules                  # noqa: E402

ABIL = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
SKILLS = ["acrobatics", "arcana", "athletics", "perception",
          "persuasion", "stealth", "survival"]

# 每个职业一个「像样」的子职, 覆盖 third-caster / 灵光 / 大地结社 等特殊路径
SUBCLASS = {
    "barbarian": "Path of the Berserker",
    "bard": "College of Lore",
    "cleric": "Life Domain",
    "druid": "Circle of the Land",
    "fighter": "Battle Master",
    "monk": "Warrior of the Open Hand",
    "paladin": "Oath of Devotion",
    "ranger": "Hunter",
    "rogue": "Thief",
    "sorcerer": "Draconic Sorcery",
    "warlock": "Fiend Patron",
    "wizard": "Evoker",
}


def build(cls_id, level, sub=None):
    r = Rules()
    c = Character(r)
    c.class_id = cls_id
    c.level = level
    c.subclass = sub or SUBCLASS.get(cls_id)
    c.species_id = "human"
    c.background_id = "sage"
    c.base_scores = {"STR": 14, "DEX": 14, "CON": 14,
                     "INT": 15, "WIS": 12, "CHA": 13}
    c.skill_prof = {"arcana", "perception", "stealth", "athletics"}
    c.expertise = {"stealth"} if cls_id in ("rogue", "bard", "ranger") else set()
    c.weapon = "Longsword"
    c.armor_index = 0
    c.fighting_style = "defense" if cls_id in ("fighter", "paladin",
                                               "ranger") else None
    if cls_id == "druid":
        c.land = "temperate"
    return c


def snap(c):
    """单个角色的全量数值快照 (只用纯函数, 不碰 UI)。"""
    d = {}
    for ab in ABIL:
        d["ability_cap:" + ab] = c.ability_cap(ab)
        d["capstone_bonus:" + ab] = c.capstone_bonus(ab)
        d["score:" + ab] = c.score(ab)
        d["save_mod:" + ab] = c.save_mod(ab)
        d["ability_check_mod:" + ab] = c.ability_check_mod(ab)
    d["expertise_allowance"] = c.expertise_allowance()
    d["initiative"] = c.initiative()
    d["save_profs"] = sorted(c.save_profs())
    for sk in SKILLS:
        d["skill_mod:" + sk] = c.skill_mod(sk)
    for sk in SKILLS:
        d["reliable_talent:" + sk] = c.reliable_talent(sk)
    for ab in ABIL:
        d["indomitable_might:" + ab] = c.indomitable_might(ab)
    d["bonus_breakdown"] = c.bonus_breakdown()
    d["speed"] = c.speed()
    d["ac"] = c.ac()
    d["ac_breakdown"] = c.ac_breakdown()
    d["hp_max"] = c.hp_max()
    d["carry_capacity"] = list(c.carry_capacity())
    d["hit_die"] = c.hit_die()
    d["hit_dice_max"] = c.hit_dice_max()
    d["attacks_per_action"] = c.attacks_per_action()
    d["sneak_dice"] = c.sneak_dice()
    d["rage_damage"] = c.rage_damage()
    d["martial_arts_die"] = c.martial_arts_die()
    d["mastery_count"] = c.mastery_count()
    d["mastery_dc"] = c.mastery_dc("Longsword")
    d["attack_bonus"] = c.attack_bonus()
    d["damage_bonus"] = c.damage_bonus()
    d["damage_dice"] = c.damage_dice()
    d["damage_type"] = c.damage_type()
    d["offhand_can_dual"] = c.offhand_can_dual()
    d["weapon_ability"] = c.weapon_ability()
    d["proficiency_report"] = c.proficiency_report()
    d["passive_perception"] = c.passive_perception()
    d["spell_dc"] = c.spell_dc()
    d["spell_attack"] = c.spell_attack()
    d["casting"] = c.casting()
    d["spell_slots"] = {str(k): v for k, v in c.spell_slots().items()}
    d["pact_level"] = c.pact_level()
    d["arcanum_levels"] = c.arcanum_levels()
    d["slots_recharge_short_rest"] = c.slots_recharge_short_rest()
    d["max_spell_level"] = c.max_spell_level()
    d["learnable_max_level"] = c.learnable_max_level()
    d["prepared_count"] = c.prepared_count()
    d["cantrip_cap"] = c.cantrip_cap()
    d["mastery_cap"] = c.mastery_cap()
    d["signature_cap"] = c.signature_cap()
    d["font_can_use"] = c.font_can_use()
    d["sorcery_max"] = c.sorcery_max()
    d["metamagic_cap"] = c.metamagic_cap()
    d["mm_free"] = c.mm_free()
    d["fixed_spells"] = c.fixed_spells()
    d["can_fighting_style"] = c.can_fighting_style()
    d["style_level_need"] = c.style_level_need()
    d["order_options"] = sorted(c.order_options())
    d["can_prepare"] = True
    d["wild_shapes"] = [m["id"] for m in c.wild_shapes()]
    d["resources"] = [(x["id"], x["max"]) for x in c.resources()]
    return d


def main():
    out = {}
    for cls_id in sorted(SUBCLASS):
        for level in range(1, 21):
            key = "%s@%d" % (cls_id, level)
            try:
                c = build(cls_id, level)
                out[key] = snap(c)
            except Exception as e:                    # noqa: BLE001
                out[key] = {"__error__": "%s: %s" % (type(e).__name__, e)}
    # 额外: 1/3 施法者子职
    for sub in ("Eldritch Knight", "Arcane Trickster"):
        cid = "fighter" if sub == "Eldritch Knight" else "rogue"
        for level in (3, 7, 13, 20):
            key = "%s/%s@%d" % (cid, sub, level)
            try:
                out[key] = snap(build(cid, level, sub))
            except Exception as e:                    # noqa: BLE001
                out[key] = {"__error__": "%s: %s" % (type(e).__name__, e)}
    dst = sys.argv[1] if len(sys.argv) > 1 else "backup/snap.json"
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    n = sum(1 for v in out.values() if "__error__" in v)
    print("写出 %s: %d 组, %d 组出错" % (dst, len(out), n))
    for k, v in out.items():
        if "__error__" in v:
            print("  !!", k, v["__error__"][:90])


if __name__ == "__main__":
    main()
