# -*- coding: utf-8 -*-
"""一次性重构脚本: 单文件 → dnd55e/ 包 + data/*.json

执行后不再需要, 保留作为重构记录/可重复生成。
"""
import importlib.util
import json
import os
import re

DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(DIR, "backup", "dnd55e_character_builder_monolith.py")
PKG = os.path.join(DIR, "dnd55e")
DATADIR = os.path.join(PKG, "data")
os.makedirs(DATADIR, exist_ok=True)

# --------------------------------------------------------------------------
# 1. 加载单文件模块, 把数据表导出成 JSON
# --------------------------------------------------------------------------
spec = importlib.util.spec_from_file_location("mono", SRC)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def dump(name, obj):
    with open(os.path.join(DATADIR, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    print(f"  data/{name}.json  {os.path.getsize(os.path.join(DATADIR, name + '.json')) // 1024} KB")


dump("abilities", {
    "abilities": m.ABILITIES,
    "ability_cn": m.ABILITY_CN,
    "ability_desc": m.ABILITY_DESC,
    "point_cost": {str(k): v for k, v in m.POINT_COST.items()},
    "standard_array": m.STANDARD_ARRAY,
})
dump("skills", {
    "skill_desc": m.SKILL_DESC,
    "conditions": m.CONDITIONS,
    "condition_desc": m.CONDITION_DESC,
    "tool_cn": m.TOOL_CN,
    "size_cn": m.SIZE_CN,
})
dump("weapons", {
    "weapons": [list(w) for w in m.WEAPONS],
    "light": sorted(m.LIGHT_WEAPONS),
    "finesse": sorted(m.FINESSSE_SET),
    "mastery_desc": m.MASTERY_DESC,
    "mastery_cn": m.MASTERY_CN,
})
dump("armors", {
    "armors": [list(a) for a in m.ARMORS],
    "cats": m.ARMOR_CAT,
    "cats_cn": m.ARMOR_CAT_CN,
})
dump("items", {"items": m.MAGIC_ITEMS})
dump("feats", {"origin": {k: list(v) for k, v in m.FEAT_INFO.items()}})
dump("classes_ui", {
    "subclass_cn": m.SUBCLASS_CN,
    "fighting_styles": {k: list(v) for k, v in m.FIGHTING_STYLES.items()},
    "style_min_level": m.STYLE_MIN_LEVEL,
    "spell_counts": {k: list(v) for k, v in m.SPELL_COUNTS.items()},
    "half_slots": {str(k): {str(a): b for a, b in v.items()}
                   for k, v in m.HALF_SLOTS.items()},
})
dump("species", {
    "skill_bonus": m.SPECIES_SKILL_BONUS,
    "auto_skills": m.SPECIES_AUTO_SKILLS,
    "legacy": m.LEGACY_SPECIES,
    "legacy_cn": m.LEGACY_SPECIES_CN,
    "spells": m.SPECIES_SPELLS,
    "lineage_cn": m.LINEAGE_CN,
})

# --------------------------------------------------------------------------
# 2. 切分源码
# --------------------------------------------------------------------------
LINES = open(SRC, encoding="utf-8").read().split("\n")


def sl(a, b):
    """取 1-based 闭区间行"""
    return "\n".join(LINES[a - 1:b]).rstrip() + "\n"


DATA_NAMES = [
    "ABILITY_DESC", "SKILL_DESC", "CONDITION_DESC", "CONDITIONS",
    "MASTERY_DESC", "MASTERY_CN", "TOOL_CN", "SIZE_CN", "SUBCLASS_CN",
    "LINEAGE_CN", "SPECIES_SPELLS", "SPECIES_SKILL_BONUS",
    "SPECIES_AUTO_SKILLS", "LEGACY_SPECIES", "LEGACY_SPECIES_CN",
    "FEAT_INFO", "WEAPONS", "LIGHT_WEAPONS", "FINESSSE_SET", "ARMORS",
    "ARMOR_CAT_CN", "ARMOR_CAT", "MAGIC_ITEMS", "ITEMS_BY_ID",
    "FIGHTING_STYLES", "STYLE_MIN_LEVEL", "SPELL_COUNTS", "HALF_SLOTS",
    "POINT_COST", "STANDARD_ARRAY",
]
# 长的先替换, 避免前缀误伤 (虽然 \b 已能区分)
DATA_NAMES.sort(key=len, reverse=True)
PAT = re.compile(r"\b(" + "|".join(DATA_NAMES) + r")\b")


def qualify(code):
    """把数据表名改成 consts.XXX (跳过已经是 consts. 前缀的)"""
    out = []
    pos = 0
    for mt in PAT.finditer(code):
        s, e = mt.span()
        prev = code[max(0, s - 7):s]
        out.append(code[pos:s])
        if prev.endswith("consts."):
            out.append(mt.group(1))
        else:
            out.append("consts." + mt.group(1))
        pos = e
    out.append(code[pos:])
    return "".join(out)


TK = ("import tkinter as tk\n"
      "from tkinter import ttk, messagebox, filedialog\n"
      "from tkinter.simpledialog import askinteger\n")


def write(name, head, body, do_qualify=True):
    code = body if not do_qualify else qualify(body)
    with open(os.path.join(PKG, name), "w", encoding="utf-8") as f:
        f.write(head.rstrip() + "\n\n\n" + code)
    print(f"  {name:16s} {len(code.splitlines()):5d} 行")


# ---- paths.py ----
write("paths.py", '''# -*- coding: utf-8 -*-
"""文件路径: 包内代码统一从这里取数据/存档位置。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "dnd55e_core_data.json")
SPELL_FILE = os.path.join(BASE_DIR, "dnd55e_spells.json")
DETAIL_FILE = os.path.join(BASE_DIR, "dnd55e_classes_detail.json")
CHAR_DIR = os.path.join(BASE_DIR, "characters")     # 角色卡固定目录
LAST_PTR = os.path.join(CHAR_DIR, "_last.json")
''', "", do_qualify=False)

# ---- data.py ----
write("data.py", '''# -*- coding: utf-8 -*-
"""按需加载 data/*.json 的规则数据 (lru_cache, 首次使用时才读盘)。"""
import json
import os
from functools import lru_cache

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@lru_cache(maxsize=None)
def _load(name):
    with open(os.path.join(DATA_DIR, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


# ---- 属性 / 点数 ----
def abilities():
    return list(_load("abilities")["abilities"])


def ability_cn():
    return dict(_load("abilities")["ability_cn"])


def ability_desc():
    return dict(_load("abilities")["ability_desc"])


def point_cost():
    return {int(k): v for k, v in _load("abilities")["point_cost"].items()}


def standard_array():
    return list(_load("abilities")["standard_array"])


# ---- 技能 / 状态 / 术语 ----
def skill_desc():
    return dict(_load("skills")["skill_desc"])


def conditions():
    return list(_load("skills")["conditions"])


def condition_desc():
    return dict(_load("skills")["condition_desc"])


def tool_cn():
    return dict(_load("skills")["tool_cn"])


def size_cn():
    return dict(_load("skills")["size_cn"])


# ---- 武器 / 护甲 / 物品 ----
def weapons():
    return [tuple(w) for w in _load("weapons")["weapons"]]


def light_weapons():
    return set(_load("weapons")["light"])


def finesse_weapons():
    return set(_load("weapons")["finesse"])


def mastery_desc():
    return dict(_load("weapons")["mastery_desc"])


def mastery_cn_map():
    return dict(_load("weapons")["mastery_cn"])


def armors():
    return [tuple(a) for a in _load("armors")["armors"]]


def armor_cats():
    return list(_load("armors")["cats"])


def armor_cats_cn():
    return dict(_load("armors")["cats_cn"])


def magic_items():
    return [dict(i) for i in _load("items")["items"]]


def items_by_id():
    return {i["id"]: i for i in magic_items()}


# ---- 专长 ----
def feat_info():
    return {k: tuple(v) for k, v in _load("feats")["origin"].items()}


# ---- 职业相关文案 ----
def subclass_cn():
    return dict(_load("classes_ui")["subclass_cn"])


def fighting_styles():
    return {k: (v[0], v[1], v[2])
            for k, v in _load("classes_ui")["fighting_styles"].items()}


def style_min_level():
    return dict(_load("classes_ui")["style_min_level"])


def spell_counts():
    return {k: tuple(v) for k, v in _load("classes_ui")["spell_counts"].items()}


def half_slots():
    return {int(lv): {int(a): b for a, b in row.items()}
            for lv, row in _load("classes_ui")["half_slots"].items()}


# ---- 种族 ----
def _species():
    return _load("species")


def species_skill_bonus():
    return dict(_species()["skill_bonus"])


def species_auto_skills():
    return dict(_species()["auto_skills"])


def legacy_species():
    return dict(_species()["legacy"])


def legacy_species_cn():
    return dict(_species()["legacy_cn"])


def species_spells():
    return _species()["spells"]


def lineage_cn():
    return dict(_species()["lineage_cn"])
''', "", do_qualify=False)

# ---- consts.py ----
write("consts.py", '''# -*- coding: utf-8 -*-
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
    "WEAPONS": data.weapons,
    "LIGHT_WEAPONS": data.light_weapons,
    "FINESSSE_SET": data.finesse_weapons,
    "MASTERY_DESC": data.mastery_desc,
    "MASTERY_CN": data.mastery_cn_map,
    "ARMORS": data.armors,
    "ARMOR_CAT": data.armor_cats,
    "ARMOR_CAT_CN": data.armor_cats_cn,
    "MAGIC_ITEMS": data.magic_items,
    "ITEMS_BY_ID": data.items_by_id,
    "FEAT_INFO": data.feat_info,
    "SUBCLASS_CN": data.subclass_cn,
    "FIGHTING_STYLES": data.fighting_styles,
    "STYLE_MIN_LEVEL": data.style_min_level,
    "SPELL_COUNTS": data.spell_counts,
    "HALF_SLOTS": data.half_slots,
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
def mastery_cn(key):
    cn = data.mastery_cn_map()
    return f"{cn[key]} {key}" if key in cn else key


def feat_cn(name):
    info = data.feat_info().get(name)
    return f"{info[0]} {name}" if info else name


def feat_desc(name):
    info = data.feat_info().get(name)
    return f"{info[0]} {name}: {info[1]}" if info else name


def tool_cn(name):
    cn = data.tool_cn().get(name)
    return f"{cn} {name}" if cn else name


def subclass_cn(name):
    cn = data.subclass_cn().get(name)
    return f"{cn} {name}" if cn else name


def size_cn(sizes):
    m = data.size_cn()
    return "/".join(m.get(s, s) for s in sizes)
''', "", do_qualify=False)

# ---- theme.py (颜色 + 样式函数 + ScrollFrame) ----
THEME_HEAD = '''# -*- coding: utf-8 -*-
"""暗色主题: 颜色常量、ttk 样式、滚动容器。"""
import tkinter as tk
from tkinter import ttk
'''
write("theme.py", THEME_HEAD, sl(398, 426) + "\n" + sl(427, 468), do_qualify=False)

# 追加 apply_theme (由 App._setup_style 提出来)
style_body = sl(3102, 3186).replace("self", "root")
style_body = "\n".join(ln[4:] if ln.startswith("    ") else ln
                       for ln in style_body.split("\n"))
with open(os.path.join(PKG, "theme.py"), "a", encoding="utf-8") as f:
    f.write("\n\ndef apply_theme(root):\n"
            '    """把暗色主题套到 root 上 (ttk 样式 + 下拉列表配色)。"""\n'
            + style_body)
print("  theme.py(+apply_theme)")

# ---- util.py ----
write("util.py", '''# -*- coding: utf-8 -*-
"""纯函数工具: 属性调整值、熟练加值、掷骰解析、法术文本。"""
import random

from . import consts
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\n''', sl(474, 541) + "\n" + sl(3011, 3016))

# ---- rules.py ----
write("rules.py", '''# -*- coding: utf-8 -*-
"""规则引擎: 读取核心 JSON, 提供职业/种族/背景/法术查询。"""
import json

from . import consts
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\nfrom .paths import DATA_FILE, DETAIL_FILE
''', sl(542, 631))

# ---- character.py ----
write("character.py", '''# -*- coding: utf-8 -*-
"""角色数据模型: 派生数值 (AC/HP/命中/DC/资源…) 与存档序列化。纯逻辑, 不依赖 tkinter。"""
import random

from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\n''', sl(632, 1632))

# ---- wizard.py ----
write("wizard.py", TK + '''
from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\nfrom .util import ability_mod, mod_str, proficiency_bonus, spell_detail
''', sl(1637, 2770))

# ---- dialogs.py ----
write("dialogs.py", TK + '''
from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\nfrom .util import ability_mod, mod_str, proficiency_bonus
''', sl(2776, 3009) + "\n\n" + sl(3018, 3062))

# ---- ui_shell.py (布局) ----
shell = "class AppShell:\n" + sl(3070, 3100) + '''
    def _setup_style(self):
        from .theme import apply_theme
        apply_theme(self)
''' + sl(3188, 3730)
write("ui_shell.py", TK + '''
from . import consts, theme, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\nfrom .theme import ScrollFrame
from .dialogs import DiceDialog
from .util import ability_mod, mod_str, spell_detail
''', shell)

# ---- ui_sheet.py (角色卡渲染) ----
write("ui_sheet.py", TK + '''
from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\nfrom .util import ability_mod, mod_str
''', "class AppSheet:\n" + sl(3731, 4172))

# ---- ui_actions.py (交互动作) ----
write("ui_actions.py", TK + '''
from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\nfrom .util import ability_mod, mod_str
''', "class AppActions:\n" + sl(4173, 4910))

# ---- ui_io.py (存档 / 升级 / 休息) ----
write("ui_io.py", TK + '''
from . import consts, util
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\nfrom .dialogs import LevelUpDialog
from .util import mod_str
from .wizard import Wizard
from .paths import CHAR_DIR, LAST_PTR
''', "class AppIO:\n" + sl(4914, 5156))

# ---- selftest.py ----
write("selftest.py", '''# -*- coding: utf-8 -*-
"""无 GUI 自检: 规则数值 + 建卡向导 + 升级 + 存档往返。"""
import json
import os
import random
import tempfile

from . import consts
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,\n                        subclass_cn, tool_cn)\nfrom .character import Character
from .dialogs import LevelUpDialog
from .rules import Rules
from .wizard import Wizard
''', sl(5161, 5364))

# ---- app.py (组合) ----
write("app.py", '''# -*- coding: utf-8 -*-
"""主窗口: 由四块 mixin 组合, 各自负责布局/渲染/交互/存档。"""
import tkinter as tk

from .ui_actions import AppActions
from .ui_io import AppIO
from .ui_sheet import AppSheet
from .ui_shell import AppShell


class App(AppShell, AppSheet, AppActions, AppIO, tk.Tk):
    """D&D 5.5e 人物卡主窗口"""
''', "")

# ---- __init__.py ----
write("__init__.py", '''# -*- coding: utf-8 -*-
"""D&D 5.5e (2024) 人物卡 —— 包入口。

模块划分:
  paths     文件路径
  data      按需加载 data/*.json
  consts    静态数据懒代理 + 文案小工具
  rules     规则数据查询
  character 角色模型 (纯逻辑)
  util      纯函数工具
  theme     暗色主题 / 滚动容器
  wizard    建卡向导
  dialogs   升级弹窗 / 骰子工具
  ui_*      主窗口的布局 / 渲染 / 交互 / 存档
  app       主窗口组合
  selftest  自检
"""
from .app import App
from .character import Character
from .dialogs import DiceDialog, LevelUpDialog
from .rules import Rules
from .wizard import Wizard

__all__ = ["App", "Character", "DiceDialog", "LevelUpDialog", "Rules",
           "Wizard"]
''', "", do_qualify=False)

print("\n完成。")
