# -*- coding: utf-8 -*-
"""文件路径: 包内代码统一从这里取数据/存档位置。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "dnd55e_core_data.json")
SPELL_FILE = os.path.join(BASE_DIR, "dnd55e_spells.json")
DETAIL_FILE = os.path.join(BASE_DIR, "dnd55e_classes_detail.json")
CHAR_DIR = os.path.join(BASE_DIR, "characters")     # 角色卡固定目录
LAST_PTR = os.path.join(CHAR_DIR, "_last.json")


