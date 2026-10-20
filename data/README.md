# 本地资料库 (data/)

本目录保存从 **D&D SRD 5.2（2024 规则，CC-BY 4.0）** 抓取的原始快照。
程序运行**只读本地文件**，不联网；只有本地缺文件时，才用 `_data_sync.py` 补抓。

## 文件清单

| 文件 | 内容 | 条数 |
|---|---|---|
| `raw/spells.json` | 全部法术（含职业、伤害、豁免、升环） | 339 |
| `raw/classes.json` | 12 职业（生命骰/豁免/熟练/施法/子职列表） | 12 |
| `raw/class-levels.json` | 每职业 1–20 级表 + 全部职业特性文本 | 12 职业 |
| `raw/subclasses.json` | 子职 | 12 |
| `raw/backgrounds.json` | 背景（SRD 仅 4 个） | 4 |
| `raw/feats.json` | 专长 | 17 |
| `raw/equipment.json` | 武器/护甲/工具/装备 | 182 |
| `raw/magic-items.json` | 魔法物品 | 262 |
| `raw/conditions.json` | 状态 | 15 |
| `raw/skills.json` | 技能 | 18 |
| `raw/ability-scores.json` | 六属性 | 6 |
| `raw/languages.json` | 语言 | 19 |
| `raw/damage-types.json` | 伤害类型 | 13 |
| `raw/weapon-properties.json` | 武器属性（含专精） | 10 |
| `raw/equipment-categories.json` | 装备分类 | 30 |
| `raw/magic-schools.json` | 法术学派 | 8 |
| `raw/proficiencies.json` | 熟练项 | 74 |

上层加工文件（程序直接使用）：

- `dnd55e_core_data.json` — 建卡核心数据（职业/种族/背景/技能/护甲/法术位表，已中文化）
- `dnd55e_spells.json` — 法术库（339 条，中文名 + 中文一句话效果 + 结构化字段）

## 数据流

```
数据源 API ──(_fetch_srd.py, 缓存优先)──> data/raw/*.json
                                          │
        dnd55e_spells.json <──(_build_spells.py, 中文名/说明)──┘
                                          │
                          dnd55e_character_builder.py (只读本地)
```

## 命令

```bat
python _data_sync.py          :: 体检 + 只补缺失项（有网才抓）
python _data_sync.py --check  :: 只体检，不联网
python _data_sync.py --force  :: 全部重新抓取
python _build_spells.py       :: 单独重建法术库（已有则跳过）
python _fetch_srd.py          :: 单独补抓原始快照（已有则跳过）
```

## 注意

- SRD 5.2 是 CC-BY 4.0，可合法内置与分发；完整 PHB 2024 的独占内容（部分子职特性文本、专长等）未收录。
- 法术的中文名为通用译名，一句话效果为人工整理，用于快速查阅；判定细节以 SRD 原文为准（`desc_en` 字段保留英文原文）。
- 修改规则数据时优先改 `dnd55e_core_data.json` / `dnd55e_spells.json`，不要改 `data/raw/`（那是快照）。
