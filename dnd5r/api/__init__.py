# -*- coding: utf-8 -*-
"""唯一门面：前端只能用这里的东西（约束 C3）。

P11（§14.32）起这里只是**转发层**：实现按职责拆在子模块里，本文件一个
定义都没有 —— 想看某件事的实现去对应子模块：

  catalog      查内容（法术 / 召唤物 / 怪物 / 插件清单）与「照内容造一只」
  character    建卡、专长与法术选择、执行能力（use_power 是唯一入口）
  sheet        投影：角色卡 / 最小视图 / 形态视图（派生值单点计算）
  combat       掷骰与出手：检定 / 施法 / 武器攻击 / 借机 / 怪物攻击
  encounter    遭遇战操作：建场 / 视图 / 回合推进 / 摆位移动传送 / 阵营
  persistence  存档（只写事实，C5）
  _support     共用底座：派生值求解、检定模式、执行上下文

C3 检查的是 `dnd5r.api` 前缀，前端 import 的名字不变 —— 拆分对约束零影响。

`locale` 的语义（写死，见架构文档 §13.9）：只切换**内容双语**（条目的
name / text）；界面骨架文案一律中文。`locale="en"` 出现中文按钮不是 bug。

`Session` 与命令对象放在**最后**导入：它已降位为「CLI 剧本壳」（§14.30 P11），
并且要在方法里反向调用本包的函数，放在头部会在初始化时成环。
"""

from ._support import ABILITY_KEYS, FEAT_KIND_ORDER, VERSION, resolver_for
from .catalog import (
    content_summary, load_content, monster_actions, monster_catalog,
    monster_sheet, plugin_summary, spell_catalog, spell_info, spawn_monster,
    summon_info,
)
from .persistence import SAVE_VERSION, load_character, save_character
from .character import (
    create_actor, feat_options, find_power, free_casts, new_character,
    plan_spells, set_feat_choice, spell_plan, subclass_options, use_power,
)
from .sheet import (
    _feat_status, actor_view, character_sheet, form_options, form_view,
)
from .combat import (
    CHECK_KINDS, attack_options, attack_roll, marks_of, monster_attack,
    opportunity_attack, roll_check, roll_spell, tokens_of,
)
from .encounter import (
    advance_turn, encounter_distance, encounter_view, join_encounter,
    move_combatant, nearby, new_encounter, place_combatant,
    set_combatant_side, teleport_combatant,
)
from .state import (
    clear_conditions, concentration_dc, death_save_view, reset_death_saves,
    roll_death_save, set_condition, set_exhaustion,
)
# 前端要构造 / 捕获的类型与异常是 api 契约的一部分（P6 的教训：
# 不让 apps 去 import kernel.errors，C3 才守得住）
from ..kernel.errors import DndError, PluginError, RuleError
from ..rules.actioneconomy import ActionEconomy, ActionType
from ..rules.build import (
    available_powers, build_from_profile, eligible_forms_for, feat_picks,
    morph_class_of, rebuild_actor,
)
from ..rules.combat import (
    RESOLUTION_KINDS, Casting, Target, casting_for, target_from_actor,
)
from ..rules.encounter import FOOT, Combatant, Encounter
from ..session import (
    LongRest, NewTurn, Regain, Session, ShortRest, TakeDamage, UsePower,
)

__all__ = [
    "VERSION", "load_content", "content_summary",
    "create_actor", "new_character", "resolver_for", "build_from_profile",
    "available_powers", "feat_picks", "rebuild_actor",
    "set_feat_choice", "save_character", "load_character", "SAVE_VERSION",
    "character_sheet", "actor_view", "roll_check", "CHECK_KINDS",
    "roll_spell", "Target", "Casting", "target_from_actor", "casting_for",
    "RESOLUTION_KINDS", "free_casts",
    "find_power", "use_power", "plugin_summary",
    "spell_info", "summon_info", "monster_catalog", "monster_sheet",
    "monster_actions", "spawn_monster",
    # 运行时状态：状态勾选 / 力竭 / 濒死 / 专注 DC（P4）
    "set_condition", "clear_conditions", "set_exhaustion",
    "roll_death_save", "reset_death_saves", "death_save_view", "concentration_dc",
    "attack_roll", "opportunity_attack", "monster_attack", "attack_options",
    "marks_of", "tokens_of",
    "eligible_forms_for", "morph_class_of", "form_options", "form_view",
    # 遭遇战（P9a）：回合容器、先攻、距离。对象进出，不落档。
    "Encounter", "Combatant", "FOOT",
    "new_encounter", "encounter_view", "advance_turn", "place_combatant",
    "move_combatant", "teleport_combatant", "encounter_distance", "nearby",
    "set_combatant_side", "join_encounter",
    # 前端要 catch 的是「调用失败」这件事，所以异常类型属于 api 的契约 ——
    # 不让 apps 去 import kernel.errors（C3），否则拦错误都得越界。
    "DndError", "RuleError", "PluginError",
    "ActionEconomy", "ActionType",
    "Session", "UsePower", "ShortRest", "LongRest", "NewTurn", "TakeDamage", "Regain",
]
