# 数据规范（给数据子代理专用，非交付文档）

项目：D&D 2024（5.5e）人物卡程序，Python + tkinter。
包根：`dnd55e/`，数据在 `dnd55e/data/*.json`，原始抓取在 `data/raw/*.json`。
原始数据来自 dnd5eapi.co 的 2024 端点（SRD 5.2），**只覆盖 SRD 内容**，PHB 独有内容需要另外查证。

## 通用铁律

1. **不许编造**。查不到就标 `"source": "unverified"` 并在最终报告里列出，不要凭印象填数值。
2. 所有面向玩家的文案用**简体中文**，专有名词格式 `中文名 English`（例：`巨武器大师 Great Weapon Master`）。
3. JSON 一律 `ensure_ascii=False`、`indent=1`、末尾换行，用 Python `json.dump` 写出，不要手写大括号。
4. id 只用小写字母、数字、下划线或短横线，与已有风格一致。
5. 只写**你被指定**的文件。绝对不要改 `dnd55e/character.py`、`dnd55e/ui_*.py`、`dnd55e/consts.py`、`dnd55e/data.py`、`dnd55e/wizard.py`、`_flowtest.py`——这些由主代理统一集成。
6. 不要运行 `运行自检.bat`（会和其他并行任务抢资源）。只跑你自己的校验脚本。
7. 完成后用一句话报告：文件路径、条目数、字段完整率、未核实条目清单。

---

## A. 通用专长 → `dnd55e/data/feats_general.json`

2024 PHB 的 **General feats（41 个）**，`data/raw/feats.json` 里只有 Grappler 和 ASI 两条，其余需要查证（可用 WebSearch / WebFetch，建议 dnd5e.wikidot、dndbeyond 免费规则、5e.tools 2024 数据）。

结构：

```json
{
  "_note": "2024 PHB 通用专长。effects 只放能机械计算的部分，其余写 desc。",
  "general": {
    "Great Weapon Master": {
      "cn": "巨武器大师",
      "prereq": {"level": 4, "abilities": [["STR", 13]], "feature": null},
      "desc": "……中文效果全文，含所有数值……",
      "repeatable": false,
      "effects": {
        "heavy_damage_pb": true,
        "bonus_attack_on_crit_or_kill": true
      }
    }
  },
  "fighting_style": { "Archery": {"cn": "箭术", "desc": "...", "effects": {"attack_bonus_ranged": 2}} },
  "epic_boon": { "Boon of Combat Prowess": {"cn": "战斗神勇恩惠", "prereq": {"level": 19}, "desc": "...", "effects": {}} }
}
```

`effects` 的 key **只能**从下表选，值为数字/布尔/字符串，不要自创字段：

| key | 类型 | 含义 | 集成时会怎么用 |
|---|---|---|---|
| `initiative_pb` | bool | 先攻加熟练加值 | 加到先攻 |
| `hp_per_level` | int | 每级额外 HP | HP 上限 |
| `ac` | int | AC 加值 | AC |
| `save` | int / `{"all":1}` / `{"DEX":2}` | 豁免加值 | 豁免 |
| `check` | int | 属性检定加值 | 检定 |
| `speed` | int | 速度加值（尺） | 速度 |
| `unarmed_die` | str | 徒手伤害骰，如 `"1d6"` | 徒手伤害 |
| `set_ability` | `{"STR":19}` | 属性设为固定值 | 属性上限/设定 |
| `skills` | int | 额外技能熟练数 | 建卡配额 |
| `expertise` | int | 额外专精数 | 建卡配额 |
| `save_prof_choice` | int | 可选几项豁免熟练 | 建卡 |
| `armor_prof` | `["medium"]` | 护甲熟练（light/medium/heavy/shields） | 熟练判定 |
| `weapon_prof` | `["martial"]` | 武器熟练（simple/martial） | 熟练判定 |
| `tool_prof` | int | 工具熟练数 | 建卡 |
| `attack_bonus` | int | 攻击加值（通用） | 攻击 |
| `attack_bonus_ranged` | int | 仅远程攻击加值 | 攻击 |
| `damage_bonus` | int | 伤害加值（通用） | 伤害 |
| `heavy_damage_pb` | bool | 用重型武器命中时 +熟练加值伤害（每回合 1 次） | 伤害 |
| `concentration_adv` | bool | 专注豁免优势 | 提示 |
| `spell_grants` | `{"class":"wizard","cantrips":2,"level1":1}` | 授予法术 | 法术页 |
| `note_only` | bool | 纯叙事、无常量数值 | 不参与计算 |

`desc` 必须包含 2024 版原文的全部数值与触发条件（2024 改了很多旧版，例如 GWM 不再是 -5/+10、Sharpshooter 不再有 -5/+10）。**每条都要核对 2024 版，不要抄 2014 版**。

---

## B. 魔法物品 → `dnd55e/data/items.json`（扩充，保留已有 12 条的 id 与字段）

现有字段：`id`、`name`（`中文 English`）、`note`、`attune`(bool)，以及可算字段 `ac`、`save`、`check`、`no_armor`、`speed_mult`、`set_str/int/dex/con/wis/cha`。**这 12 条的 id 和语义不能改**，只允许补字段。

从 `data/raw/magic-items.json`（262 条，含 `variants`）里扩充，目标 **≥ 80 条**，优先覆盖：防御类、属性设定类、武器/护甲增强、法术 DC/攻击、抗性、位移、充能类。

新增字段（只允许这些）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `rarity` | str | `common/uncommon/rare/very_rare/legendary/artifact/varies` |
| `kind` | str | `ring/cloak/armor/weapon/wand/staff/wondrous/potion/scroll/ammunition` |
| `desc` | str | 原文效果的中文简述（1–3 句） |
| `ac_bonus_armor` | int | 护甲/盾牌本身的增强加值（不是佩戴者 AC） |
| `attack` | int | 武器魔法攻击加值 |
| `damage` | int | 武器魔法伤害加值 |
| `spell_dc` | int | 法术豁免 DC 加值 |
| `spell_attack` | int | 法术攻击加值 |
| `hp_bonus` | int | HP 上限加值 |
| `resist` | `["fire"]` | 伤害抗性（英文小写） |
| `immune` | `["poison"]` | 伤害免疫 |
| `condition_immune` | `["charmed"]` | 状态免疫 |
| `charges` | int | 充能数（有则写，恢复规则写 `charge_note`） |
| `charge_note` | str | 充能恢复说明 |
| `speed_bonus` | int | 速度加值（尺） |
| `note_only` | bool | 无法机械计算 |

物品的 `attune` 严格按原文（2024 里很多物品改成免同调）。变体（+1/+2/+3）拆成独立条目，id 加后缀如 `weapon_plus1`。

---

## C. 怪物（野兽）→ `dnd55e/data/monsters.json`

用途：德鲁伊荒野变形、游侠野兽伙伴、法师变形术。**只需要 Beast 类型，CR 0–6**。

数据源建议：`https://www.dnd5eapi.co/api/2024/monsters?type=beast`（或 `/api/2014/monsters`，2024 缺的用 2014 补并标 `"edition":"2014"`）。2024 版把一些野兽的数值改了，优先 2024。

结构：

```json
{
  "_note": "野兽形态数据, 供荒野变形/野兽伙伴/变形术使用。CR 0-6。",
  "monsters": [
    {
      "id": "wolf",
      "name": "狼 Wolf",
      "cr": "1/4",
      "cr_num": 0.25,
      "xp": 50,
      "size": "中型",
      "ac": 13,
      "ac_note": "天生护甲",
      "hp": 11,
      "hp_dice": "2d8+2",
      "speed": {"walk": 40, "climb": 0, "fly": 0, "swim": 0, "hover": false},
      "abilities": {"STR": 12, "DEX": 15, "CON": 12, "INT": 3, "WIS": 12, "CHA": 6},
      "saves": {},
      "skills": {"察觉": 3, "隐匿": 4},
      "senses": {"darkvision": 0, "blindsight": 0, "passive_perception": 13},
      "languages": "—",
      "traits": [{"name": "群体战术 Pack Tactics", "desc": "……"}],
      "actions": [
        {"name": "啃咬 Bite", "kind": "melee",
         "attack_bonus": 4, "reach": 5, "range": null,
         "damage": "2d4+2", "damage_type": "穿刺", "desc": "……"}
      ],
      "bonus_actions": [],
      "reactions": [],
      "edition": "2024",
      "source": "srd"
    }
  ]
}
```

要求：
- 覆盖 CR 0、1/8、1/4、1/2、1、2、3、4、5、6 各档，目标 **≥ 45 只**，每档至少 3 只（CR 6 可少）。
- `cr_num` 用数字（1/8 → 0.125，1/4 → 0.25，1/2 → 0.5）。
- `abilities` 必须是 6 项完整值。
- `actions` 里把 `attack_bonus`、`damage`、`reach`/`range` 拆成独立字段（荒野变形要直接掷骰），不要只写成一串文本。
- 中文 `size`：微型/小型/中型/大型/巨型。
- 有飞行/游泳速度的必须填，荒野变形要判断「2 级不能选飞行或游泳形态」。
- 2024 版没有的（例如某些 2014 才有的野兽），`"edition": "2014"`。

校验脚本要求（三个数据任务各自写一个）：
- 断言 JSON 可解析、id 唯一、必填字段齐全、枚举值合法。
- 交叉校验 id 引用（例如专长的 `spell_grants` 职业、物品的 `resist` 伤害类型、怪物的 `damage_type`）。
- 打印「条目数 / 字段完整率 / 未核实条数」。
