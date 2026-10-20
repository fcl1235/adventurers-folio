# -*- coding: utf-8 -*-
"""P1 物理拆分: 把 character.py 按方法边界切到 core/* 与 spellcasting/*。

纯机器搬运: 按 AST 取方法的原始源码行, 逐字节复制, 不改一个字符逻辑。
生成后 character.py 变成 mixin 组装门面。
"""
import ast
import builtins
import os
import sys

SRC = "dnd55e/character.py"

# ---- 方法 -> 目标模块 ----
GROUPS = {
    "core/base.py": [
        "__init__", "ability_cap", "capstone_bonus", "score",
        "species_spells", "race_spell_ids", "auto_skills", "skill_quota",
        "class_skill_pool", "bg_skills", "class_skill_picks",
        "extra_skill_allowance", "expertise_allowance",
        "weapon_mastery_pool", "lineage_cn", "scores", "mods", "pb",
        "cls", "casting", "third_caster", "spell_list_class", "_third_row",
    ],
    "core/derived.py": [
        "hp_max", "has_tough", "ac", "speed", "carry_capacity",
        "hit_die", "hit_dice_max", "hit_dice_left", "spend_hit_dice",
        "is_dying", "concentration_dc", "condition_blocks_action",
        "attacks_per_action", "_shield_item_bonus", "_armor_item_bonus",
        "ac_breakdown", "senses", "passive_perception",
        "wild_shapes", "wild_shape",
    ],
    "core/checks.py": [
        "initiative", "exh_penalty", "check_bonus", "ability_check_mod",
        "save_profs", "resistances", "immunities", "condition_immunities",
        "save_mod", "skill_mod", "reliable_talent", "indomitable_might",
        "spell_dc", "spell_attack", "bonus_breakdown",
        "d20_mod_total", "roll_d20",
    ],
    "core/combat/weapons.py": [
        "weapon_entry", "weapon_ability", "is_ranged_weapon",
        "is_two_handed_weapon", "is_versatile_weapon", "is_heavy_weapon",
        "heavy_penalty", "is_thrown_weapon", "weapon_prof_rules",
        "has_weapon_prof", "armor_cat", "armor_profs", "has_armor_prof_at",
        "has_armor_prof", "has_shield_prof", "armor_penalty", "tool_profs",
        "proficiency_report", "_weapon_item_bonus", "attack_bonus",
        "weapon_props", "damage_dice", "damage_type", "damage_bonus",
    ],
    "core/combat/offhand.py": [
        "offhand_entry", "has_dual_wielder", "offhand_can_dual",
        "offhand_ability", "offhand_attack_bonus", "offhand_damage_dice",
        "offhand_damage_type", "offhand_damage_bonus", "offhand_note",
    ],
    "core/items.py": ["attunement_cap", "attuned_items"],
    "core/features.py": [
        "all_feat_names", "feat_effects", "has_feat", "class_dice_text",
        "class_features", "subclass_summary", "subclass_features",
        "class_stat", "mastery_count", "can_fighting_style",
        "style_level_need", "order_options", "order_label", "order_note",
        "order_skill_bonus", "martial_arts_die", "sneak_dice",
        "mastery_dc", "rage_damage",
    ],
    "core/resources.py": [
        "resource_max", "_res_die", "resources", "res_spend",
        "res_restore", "res_reset",
    ],
    "core/serialize.py": ["to_dict", "load_dict"],
    "spellcasting/slots.py": [
        "spell_slots", "_base_slots", "slots_recharge_short_rest",
        "arcanum_levels", "pact_level",
    ],
    "spellcasting/prepare.py": [
        "max_spell_level", "learnable_max_level", "prepared_count",
        "cantrip_cap", "prepared_hint",
    ],
    "spellcasting/fixed.py": [
        "fixed_spells", "fixed_source", "prune_fixed",
        "land_options", "land_label",
    ],
    "spellcasting/metamagic.py": [
        "metamagic_cap", "metamagic_known", "metamagic_per_spell",
        "mm_free", "mm_cost", "mm_validate", "mm_apply",
        "innate_cap", "innate_left", "innate_on", "innate_off",
        "sorcerous_rest",
    ],
    "spellcasting/font.py": [
        "font_can_use", "_sorcery_res", "sorcery_max", "sorcery_left",
        "font_create_slot", "font_burn_slot",
    ],
    "spellcasting/spellbook.py": [
        "mastery_cap", "signature_cap", "_wizard_spell_ids",
        "book_max_level", "in_book", "book_spells", "can_prepare",
        "ritual_castable", "copy_cost", "copy_hours", "book_add",
        "book_remove", "book_auto_fill", "_choice_spells",
        "is_mastery_spell", "is_signature_spell", "signature_left",
    ],
}

# 内部依赖名 -> 生成 import 的模板 ({} 换成相对点数)
IMPORT_MAP = {
    "consts": "from {d} import consts",
    "util": "from {d} import util",
    "Rules": "from {d}rules import Rules",
    "random": "import random",
}
CONSTS_NAMES = ["ABILITIES", "ABILITY_CN", "feat_cn", "feat_desc",
                "mastery_cn", "size_cn", "subclass_cn", "tool_cn"]
UTIL_NAMES = ["ability_mod", "mod_str", "proficiency_bonus",
              "spell_detail", "roll_dice"]


def cls_name_for(relpath):
    """core/combat/weapons.py -> WeaponsMixin"""
    stem = os.path.splitext(os.path.basename(relpath))[0]
    parts = stem.split("_")
    return "".join(p.capitalize() for p in parts) + "Mixin"


def collect_globals(node):
    """方法体内所有裸引用的全局名 (排除 self / 参数 / 局部赋值)。"""
    local = set()
    for a in ast.walk(node):
        if isinstance(a, ast.arg):
            local.add(a.arg)
        elif isinstance(a, ast.Name) and isinstance(a.ctx, ast.Store):
            local.add(a.id)
        elif isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            local.add(a.name)
        elif isinstance(a, ast.Import):
            for al in a.names:
                local.add(al.asname or al.name.split(".")[0])
        elif isinstance(a, ast.ImportFrom):
            for al in a.names:
                local.add(al.asname or al.name)
    used = set()
    for a in ast.walk(node):
        if isinstance(a, ast.Name) and isinstance(a.ctx, ast.Load):
            if a.id not in local and a.id != "self":
                used.add(a.id)
    return used


def main():
    src = open(SRC, encoding="utf-8").read()
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    methods = {}
    for n in cls.body:
        if isinstance(n, ast.FunctionDef):
            methods[n.name] = n

    assigned = set()
    for names in GROUPS.values():
        assigned |= set(names)
    missing = set(methods) - assigned
    extra = assigned - set(methods)
    if missing:
        print("!! 未分配的方法:", sorted(missing))
        sys.exit(1)
    if extra:
        print("!! 不存在的方法:", sorted(extra))
        sys.exit(1)

    # 每个方法 -> 引用的全局名
    used_by = {name: collect_globals(node) for name, node in methods.items()}

    for relpath, names in GROUPS.items():
        depth = relpath.count("/")
        dots = "." * (depth + 1)
        need = set()
        for nm in names:
            need |= used_by[nm]
        need -= {nm for nm in need if nm in methods}
        need -= set(dir(builtins))

        imps = []
        if "random" in need:
            imps.append("import random")
        for k in ("consts", "util"):
            if k in need:
                imps.append(IMPORT_MAP[k].format(d=dots))
        cn = [n for n in CONSTS_NAMES if n in need]
        if cn:
            imps.append("from %sconsts import (%s)" % (dots, ", ".join(sorted(cn))))
        un = [n for n in UTIL_NAMES if n in need]
        if un:
            imps.append("from %sutil import (%s)" % (dots, ", ".join(sorted(un))))
        if "Rules" in need:
            imps.append("from %srules import Rules" % dots)

        unknown = need - set(IMPORT_MAP) - set(CONSTS_NAMES) - set(UTIL_NAMES)
        if unknown:
            print("!! %s 有未映射的全局名: %s" % (relpath, sorted(unknown)))
            sys.exit(1)

        body_parts = []
        for nm in names:
            node = methods[nm]
            chunk = lines[node.lineno - 1:node.end_lineno]
            body_parts.append("".join(chunk).rstrip("\n"))

        cname = cls_name_for(relpath)
        head = [
            "# -*- coding: utf-8 -*-",
            '"""角色模型分片: %s (由 character.py 物理拆分, P1 纯搬运)。"""' % relpath,
        ]
        head += imps
        head.append("")
        head.append("")
        head.append("class %s:" % cname)
        head.append('    """%s"""' % cname)
        head.append("")
        out = "\n".join(head) + "\n" + "\n\n".join(body_parts) + "\n"

        os.makedirs(os.path.dirname(relpath), exist_ok=True)
        with open(relpath, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        print("%-32s %4d 行  %2d 方法  (类 %s)" %
              (relpath, out.count("\n"), len(names), cname))

    # ---- 生成 character.py 门面 ----
    order = list(GROUPS)
    imports = []
    parents = []
    for relpath in order:
        base_mod = "core" if relpath.startswith("core/") else "spellcasting"
        modpath = relpath[:-3].replace("/", ".")
        cname = cls_name_for(relpath)
        imports.append("from .%s import %s" % (modpath, cname))
        parents.append(cname)

    facade = ['# -*- coding: utf-8 -*-',
              '"""角色数据模型门面。真正的实现分散在 core/ 与 spellcasting/ 的 mixin 里。',
              '',
              '直接 import Character 使用即可, 方法名与拆分前完全一致。',
              '"""']
    facade += sorted(imports)
    facade.append("")
    facade.append("")
    facade.append("class Character(%s):" % ", ".join(parents))
    facade.append('    """角色数据模型 (mixin 组装)。"""')
    facade.append("")
    with open(SRC, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(facade))
    print("%-32s 门面 %d 个 mixin" % (SRC, len(parents)))


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
