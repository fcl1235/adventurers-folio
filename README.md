# 5rcard — D&D 2024（5.5e）角色卡

一个纯 Python + tkinter 的桌面角色卡工具，只做 **D&D 2024 / 5R** 规则，
数据全部内置于本地 JSON（不联网、不依赖第三方库）。

## 启动

双击 `启动人物卡.bat`，或直接命令行：

```
python dnd55e_character_builder.py
python dnd55e_character_builder.py --selftest    # 无人值守自检
```

需要 Python 3.10+（含 tkinter）。角色档存在 `characters/` 下。

## 功能

- **建卡向导**：职业 / 背景 / 种族 / 属性（标准数组·点数购买·4d6k3）/ 技能 / 专精 / 法术 / 摘要
- **主界面六个标签页**：技能、法术、装备·加成、职业、专长·特性、笔记
- 12 个职业 × 1–20 级、48 个子职、347 个法术、140 件魔法物品、91 只野兽形态
- 法术位分层（职业表 / 术法源泉临时位 / 秘契位）、超魔法、法师法术书与精通/招牌法术、
  荒野变形、游侠野兽伙伴、传奇恩惠、双武器、同调上限、力竭与状态

## 代码结构（四层）

```
dnd55e/
├── core/           领域内核：Character 本体（不 import 任何 UI）
│   ├── base.py       状态字段 / 属性上限 / score()
│   ├── derived.py    AC / HP / 速度 / 先攻
│   ├── checks.py     豁免 / 技能 / 加值来源说明
│   ├── combat/       武器攻击与双武器
│   ├── features.py   专长 effects / 传奇恩惠 / 伙伴
│   ├── resources.py  职业资源池
│   └── serialize.py  存档读写
├── classes/        职业模块：一职业一个文件，@register 注册
│   ├── base.py       ClassModule 的 hook（默认空实现）
│   ├── registry.py   注册表（未知职业回退空实现）
│   └── barbarian.py … warlock.py
├── spellcasting/   施法：按施法类型与环级分模块
│   ├── types.py      full / half / third / pact
│   ├── slots.py      法术位
│   └── levels/       cantrip + level1…level9
├── ui/             表现层：tabs / panels / actions / refresh / classtab
├── dialogs/        弹窗：升级、法术书、专长、变形、召唤物、物品卡
├── wizard_steps/   建卡向导的七个步骤
├── rules.py        规则表查询（只读 JSON）
├── data.py         JSON 加载器（lru_cache）
├── consts.py       懒加载常量 + 中文文案
└── wildshape.py    野兽形态纯函数
```

新增职业只需在 `dnd55e/classes/` 加一个文件并在类上加 `@register("class_id")`，
主程序零改动。

## 数据文件

| 文件 | 内容 |
|---|---|
| `dnd55e_core_data.json` | 职业 / 种族 / 背景 / 技能 / 法术位表 |
| `dnd55e_classes_detail.json` | 职业与子职特性、资源池 |
| `dnd55e_spells.json` | 法术（含 `summon` 召唤物映射） |
| `dnd55e/data/feats_general.json` | 67 条专长：43 通用 + 12 战斗风格 + 12 传奇恩惠 |
| `dnd55e/data/monsters.json` | 91 只野兽（含 3 只游侠伙伴） |
| `dnd55e/data/summons.json` | 32 条召唤物 stat block |
| `dnd55e/data/items.json` | 140 件魔法物品 |

## 自检

```
运行自检.bat
```

9 步：数据体检 → 应用自检 → 建卡流程 → 逐级数值对账（约 2200 项）→ 布局 →
中英文案 → 提示裁切 → 召唤物校验 → 模块依赖。全绿时应以 `ALL CHECKS PASSED` 结束。

数据文件改完后还要单独跑对应的校验器：`_featcheck.py` / `_itemcheck.py` /
`_moncheck.py` / `_summoncheck.py`。

## 文档

- `dnd55e_rules_reference.md` — 规则基准与实现口径
- `_dataspec.md` — 数据字段规范
- `重构方案.md` — P1–P5 模块化改造（已完成）
- `P6方案.md` — P6 五项功能补齐（已完成）
