# -*- coding: utf-8 -*-
"""内容加载：把插件里的 YAML 变成 ClassDef / Power / ResourceDef。

三条原则：
  1. **内容不进代码**：这里是唯一读 YAML 的地方，规则层只吃解析好的对象。
  2. **坏内容只坏自己**：单个文件解析失败记进 errors，其余内容照常可用。
  3. **解析期就校验**：双语（C7）、id 规范、引用存在、效果可解析，
     全部在加载时炸掉，而不是等到玩家点了按钮才崩。

P11（§14.32）起按条目类型分文件，本文件只做转发 —— 想改哪类内容去对应模块：

  resources  池定义          classes   职业与子职
  items      护甲与武器      skills    技能与工具
  feats      专长            bestiary  怪物 / 召唤物 / 形态
  spells     法术与法术表    loader    插件加载与交叉校验

（下方那批「顺手转发」的名字是旧 content.py 顶层 import 的历史遗产，
别的模块一直在用 —— 保留，别让既有 import 断。）
"""

from .resources import REFRESH_KINDS, RESOURCE_KINDS, ResourceDef, parse_resource
from .items import (
    ARMOR_CATEGORIES, WEAPON_CATEGORIES, WEAPON_DAMAGE_TYPES, WEAPON_PROPERTIES,
    ArmorDef, WeaponDef, parse_armor, parse_weapon,
)
from .classes import (
    ClassDef, MulticlassDef, SubclassDef, parse_class,
    parse_multiclass_entry, parse_slots, parse_subclass, powers_at_level,
)
from .skills import (
    CHOICE_UNIVERSE, SKILL_KEYS, TOOL_KINDS, SkillDef, ToolDef, parse_skill,
    parse_tool,
)
from .feats import (
    CHOICE_KINDS, FEAT_KINDS, SPELL_LIST_ANY, FeatChoice, FeatDef, parse_feat,
    parse_feat_choice,
)
from .bestiary import (
    CONDITION_IMMUNITIES, CREATURE_TYPES, DAMAGE_TYPES, MonsterDef, SummonDef,
    parse_cr_axis, parse_form, parse_monster, parse_summon,
)
from .spells import (
    AREA_SHAPES, CAST_KINDS, DURATION_KINDS, SAVE_EFFECTS, SCALING_KINDS,
    SPELL_SCHOOLS, SpellDef, lookup_dice, parse_spell, parse_spell_list,
)
from .loader import (
    ContentBundle, PluginContent, load_all, load_plugin,
    _check_subclass_classes, _check_summon_spells,
)

# --- 历史转发的名字（原 content.py 顶层 import 的副产物，保持兼容） ---
from ..kernel.dice import parse as parse_dice  # noqa: F401
from ..kernel.dice import stack as stack_dice  # noqa: F401
from ..kernel.errors import (  # noqa: F401
    DiceError, DndError, PluginError, RuleError,
)
from ..kernel.ids import is_valid  # noqa: F401
from ..kernel.text import Text  # noqa: F401
from ..model.inventory import EquipSlot  # noqa: F401
from ..model.levels import ClassLevel, as_class_level  # noqa: F401
from ..model.resources import Pool, PoolKind, Refresh  # noqa: F401
from ..model.statblock import ABILITY_KEYS, Abilities  # noqa: F401
from ..plugin import Manifest, load_manifest  # noqa: F401
from ..rules.amount import Amount, parse_amount  # noqa: F401
from ..rules.effects import parse_effects  # noqa: F401
from ..rules.morph import CrAxis, FormSpec  # noqa: F401
from ..rules.monsters import ACTION_KINDS as MONSTER_ACTION_KINDS  # noqa: F401
from ..rules.monsters import (  # noqa: F401
    MonsterAttack,
    MonsterTrait,
    parse_attack as parse_monster_attack,
    parse_trait as parse_monster_trait,
)
from ..rules.powers import Power, PowerBook, apply_patch, parse_power  # noqa: F401
from ..rules.progression import CasterKind, attacks_per_action  # noqa: F401
from ..rules.summon import (  # noqa: F401
    SENSE_KINDS,
    SIZES,
    SPEED_KINDS,
    SummonAction,
    parse_action,
    parse_scaling,
    resolve as resolve_summon,
)

__all__ = [
    "ResourceDef", "ClassDef", "SubclassDef", "ArmorDef", "WeaponDef",
    "MonsterDef", "SummonDef",
    "PluginContent", "ContentBundle",
    "parse_resource", "parse_class", "parse_subclass", "parse_cr_axis", "parse_form",
    "MulticlassDef", "parse_multiclass_entry",
    "parse_armor", "parse_weapon", "parse_monster", "parse_summon",
    "parse_skill", "parse_tool", "parse_feat", "parse_feat_choice",
    "parse_spell", "parse_spell_list", "powers_at_level", "lookup_dice",
    "load_plugin", "load_all",
    "FEAT_KINDS", "CHOICE_KINDS", "CHOICE_UNIVERSE", "DAMAGE_TYPES", "SKILL_KEYS",
    "SkillDef", "TOOL_KINDS", "SCALING_KINDS", "SPELL_LIST_ANY",
    "WEAPON_DAMAGE_TYPES", "TOOL_KINDS",
]
