# -*- coding: utf-8 -*-
"""静态数据入口 (兼容旧名字)。

真正的内容放在 data/*.json, 这里只做「首次访问才加载」的懒代理,
所以 `consts.WEAPONS` 第一次用到时才会读盘。
"""
from . import data

ABILITIES = data.abilities()
ABILITY_CN = data.ability_cn()

_LOADERS = {
    "ABILITY_DESC": data.ability_desc,
    "SKILL_DESC": data.skill_desc,
    "CONDITIONS": data.conditions,
    "CONDITION_DESC": data.condition_desc,
    "TOOL_CN": data.tool_cn,
    "SIZE_CN": data.size_cn,
    "WEAPON_PROF_CN": data.weapon_prof_cn,
    "ARMOR_PROF_CN": data.armor_prof_cn,
    "CAST_TYPE_CN": data.cast_type_cn,
    "CAST_MODE_CN": data.cast_mode_cn,
    "WEAPONS": data.weapons,
    "WEAPON_PROPS": data.weapon_props,
    "WEAPON_VERSATILE": data.versatile_dice,
    "LIGHT_WEAPONS": data.light_weapons,
    "FINESSSE_SET": data.finesse_weapons,
    "MASTERY_DESC": data.mastery_desc,
    "MASTERY_CN": data.mastery_cn_map,
    "ARMORS": data.armors,
    "ARMOR_CAT": data.armor_cats,
    "ARMOR_CAT_CN": data.armor_cats_cn,
    "ARMOR_STR_REQ": data.armor_str_req,
    "ARMOR_STEALTH": data.armor_stealth,
    "MAGIC_ITEMS": data.magic_items,
    "ITEMS_BY_ID": data.items_by_id,
    "FEAT_INFO": data.feat_info,
    "GENERAL_FEATS": data.general_feats,
    "FEATS_BY_NAME": data.feats_by_name,
    "MONSTERS": data.monsters,
    "MONSTERS_BY_ID": data.monsters_by_id,
    "SUMMONS": data.summons,
    "SUMMONS_BY_ID": data.summons_by_id,
    "SUBCLASS_CN": data.subclass_cn,
    "FIGHTING_STYLES": data.fighting_styles,
    "STYLE_MIN_LEVEL": data.style_min_level,
    "ORDERS": data.orders,
    "FIXED_SPELLS": data.fixed_spells,
    "METAMAGIC": data.metamagic_options,
    "FONT_OF_MAGIC": data.font_of_magic,
    "SPELL_COUNTS": data.spell_counts,
    "HALF_SLOTS": data.half_slots,
    "PREPARED_SPELLS": data.prepared_spells,
    "CANTRIPS_KNOWN": data.cantrips_known,
    "THIRD_CASTER": data.third_caster,
    "POINT_COST": data.point_cost,
    "STANDARD_ARRAY": data.standard_array,
    "SPECIES_SKILL_BONUS": data.species_skill_bonus,
    "SPECIES_AUTO_SKILLS": data.species_auto_skills,
    "LEGACY_SPECIES": data.legacy_species,
    "LEGACY_SPECIES_CN": data.legacy_species_cn,
    "SPECIES_SPELLS": data.species_spells,
    "LINEAGE_CN": data.lineage_cn,
}

__all__ = ["ABILITIES", "ABILITY_CN"] + sorted(_LOADERS)


def __getattr__(name):
    """模块级懒加载: 首次访问才读对应 JSON, 之后留在 globals 里。"""
    loader = _LOADERS.get(name)
    if loader is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    val = loader()
    globals()[name] = val
    return val


# ---- 文案小工具 (都走懒加载, 不在这里存文本) ----
# 伤害类型英文 → 中文 (抗性/免疫展示用; 与 items.json 的英文小写键一致)
DAMAGE_TYPES_CN = {
    "acid": "强酸", "bludgeoning": "钝击", "cold": "寒冷", "fire": "火焰",
    "force": "力场", "lightning": "闪电", "necrotic": "黯蚀",
    "piercing": "穿刺", "poison": "毒素", "psychic": "心灵",
    "radiant": "光耀", "slashing": "挥砍", "thunder": "雷鸣",
}

# 状态英文 id → 中文 (condition_immune 展示用)
CONDITIONS_CN = {
    "blinded": "目盲", "charmed": "魅惑", "deafened": "耳聋",
    "exhaustion": "力竭", "frightened": "恐惧", "grappled": "擒抱",
    "incapacitated": "失能", "invisible": "隐形", "paralyzed": "麻痹",
    "petrified": "石化", "poisoned": "中毒", "prone": "倒地",
    "restrained": "束缚", "stunned": "震慑", "unconscious": "昏迷",
}


def damage_cn(key):
    return DAMAGE_TYPES_CN.get(key, key)


def mastery_cn(key):
    cn = data.mastery_cn_map()
    return f"{cn[key]} {key}" if key in cn else key


def feat_cn(name):
    info = data.feat_info().get(name)
    if info:
        return f"{info[0]} {name}"
    g = data.feats_by_name().get(name)      # 通用专长 / 战斗风格 / 传奇恩惠
    if g:
        return f"{g.get('cn', '')} {name}".strip()
    return name


def feat_desc(name):
    info = data.feat_info().get(name)
    if info:
        return f"{info[0]} {name}: {info[1]}"
    g = data.feats_by_name().get(name)
    if g:
        return f"{g.get('cn', '')} {name}: {g.get('desc', '')}".strip()
    return name


def tool_cn(name):
    cn = data.tool_cn().get(name)
    return f"{cn} {name}" if cn else name


def subclass_cn(name):
    cn = data.subclass_cn().get(name)
    return f"{cn} {name}" if cn else name


def size_cn(sizes):
    m = data.size_cn()
    return "/".join(m.get(s, s) for s in sizes)


