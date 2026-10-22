# 5rcard — D&D **5R**（5.5e / 2024）角色卡

> 项目名 `5rcard` = **5R** + card。这里的 5R 就是 D&D 2024 修订版，
> 国外社区也叫 **5.5e**（2014 版才叫 5e）。本项目**只做 5R**，不是 5e 的兼容实现。

纯 Python + tkinter 的桌面角色卡工具。规则数据全部内置为本地 JSON：
不联网、不装第三方库、不需要数据库。

- 12 个职业 × 1–20 级、48 个子职
- 347 个法术（含 8 个 2024 Summon 系列的召唤物映射）
- 140 件魔法物品、91 条野兽数据（88 只可变形 + 3 只游侠伙伴）、32 条召唤物 Stat Block
- 67 条专长（43 通用 + 12 战斗风格 + 12 传奇恩惠）
- 建卡向导 + 六标签页角色卡 + 升级/休息/掷骰

## 规则版本：只做 5R

本项目的判定标准是 **D&D 2024 修订版**，凡是 5R 与 5e 有出入的地方一律按 5R：

| 领域 | 5e（2014） | **5R（本项目采用）** |
|---|---|---|
| 属性加值来源 | 种族 | **背景**（+2/+1 或 +1/+1/+1） |
| 建卡顺序 | 种族 → 职业 | **职业 → 背景 → 种族** |
| 战斗风格 | 职业特性 | **专长**（战士 1 级、圣武士/游侠 2 级） |
| 力竭 | 分级惩罚（劣势 / 速度减半 / HP 上限减半…） | **每级统一 d20 −2、速度 −5 尺** |
| 武器专精 | 无 | **Weapon Mastery**（每把武器带一个专精词条） |
| 法术准备数 | 属性调整值 + 等级 | **按职业表**（戏法数、准备数、契约位都查表） |
| 召唤法术 | 一条法术配一张怪物表 | **Summon 系列用独立 Stat Block，随环级缩放** |
| 荒野变形 | CR 随等级/子职跳档 | **已知形态数 4/6/8、游泳 4 级与飞行 8 级解禁、月环 CR = 等级÷3** |

5R 与 2014 内容**向后兼容**，但本程序不带 2014 数据，也不提供版本切换开关。
（代码里 `dnd55e`、`5.5e` 这类命名是历史遗留，指的都是同一个 5R。）

## 快速开始

需要 Python 3.10+（含 tkinter，Windows 官方安装包自带）。

```
启动人物卡.bat                      # 双击也可
python dnd55e_character_builder.py            # 直接启动
python dnd55e_character_builder.py --selftest # 无人值守自检(不开窗口)
```

角色档存在 `characters/` 下（`_last.json` 记住上次打开的档）。

## 界面导览

**顶部工具栏**：新建角色 · 保存 · 打开 · 导出 JSON ｜ 升级 · 长休 · 短休 ｜ 骰子工具
**菜单**：`文件`（新建/保存/另存为/打开存档文件夹/载入/导出 JSON）、`角色`（升级/长休/短休）、`工具`（骰子工具）
**快捷键**：`Ctrl+S` 保存、`Ctrl+O` 打开

**六个标签页**

| 标签页 | 内容 |
|---|---|
| 技能 | 18 项技能的调整值，熟练/专精可勾选；鼠标悬停看说明与当前加值 |
| 法术 | 法术位、已学/已准备列表、法术详情（含召唤物段）、施放/专注/召唤物按钮、法师法术书 |
| 装备·加成 | 武器/护甲/战斗风格/武器专精、魔法物品格、AC 与加值来源、抗性/免疫/真实视觉 |
| 职业 | 资源池、生命骰、术法源泉、超魔法、传奇恩惠、阶职、荒野变形、野兽伙伴、子职、职业特性 |
| 专长·特性 | 专长列表与说明、种族特性、背景、熟练项 |
| 笔记 | 语言、装备清单、自由笔记 |

**常用交互**

- 法术页选中法术 → 详情显示召唤物段；有召唤物的法术会出现「召唤物」按钮，点开是完整 Stat Block 卡
- 物品格**左键**装卸、**右键**打开完整效果卡（稀有度、同调、全文、已计入的数值、卡内一键装备）
- 职业页的资源点「用 1 / 回 1」、生命骰「花 1 颗回血」、传奇恩惠的属性/抗性/专精选择都在原地面板里
- 驯兽师 3 级起职业页有「原始伙伴」，可切三形态并掷「野兽打击」

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
├── classes/        职业模块：一职业一个文件
│   ├── base.py       ClassModule 的 hook（默认全空实现）
│   ├── registry.py   @register 注册表（未知职业回退空实现）
│   └── barbarian.py … warlock.py
├── spellcasting/   施法：按施法类型与环级分模块
│   ├── types.py      full / half / third / pact
│   ├── slots.py      法术位
│   └── levels/       cantrip + level1…level9
├── ui/             表现层：tabs / panels / actions / refresh / classtab
├── dialogs/        弹窗：升级、法术书、专长、变形、召唤物、物品卡、骰子
├── wizard_steps/   建卡向导的七个步骤
├── rules.py        规则表查询（只读 JSON）
├── data.py         JSON 加载器（lru_cache）
├── consts.py       懒加载常量 + 中文文案
├── summoning.py    召唤物段渲染
└── wildshape.py    野兽形态纯函数
```

职业规则不再散落在主程序里：`core/` 与 `spellcasting/` 中已无任何 `class_id == "..."` 分支，
全部走 `classes.get(class_id)` 的 hook。**新增职业 = 在 `dnd55e/classes/` 加一个文件 + 类上一行
`@register("class_id")`**，主程序零改动。

## 数据文件

| 文件 | 内容 |
|---|---|
| `dnd55e_core_data.json` | 职业 / 种族 / 背景 / 技能 / 法术位表 |
| `dnd55e_classes_detail.json` | 职业与子职特性、资源池 |
| `dnd55e_spells.json` | 法术；带 `summon` 字段的法术会渲染召唤物段 |
| `dnd55e/data/feats_general.json` | 67 条专长：43 通用 + 12 战斗风格 + 12 传奇恩惠 |
| `dnd55e/data/monsters.json` | 91 条野兽数据（88 只可变形 + 3 只游侠伙伴） |
| `dnd55e/data/summons.json` | 32 条召唤物 Stat Block（覆盖 12 个法术） |
| `dnd55e/data/items.json` | 140 件魔法物品 |
| `dnd55e/data/fixed_spells.json` | 「始终准备」法术（领域/结社/精通/招牌） |
| `dnd55e/data/metamagic.json` | 超魔法选项 |

数据来自 SRD 5.2（dnd5eapi.co 的 2024 端点）与 5etools 镜像的 PHB 2024 条目；
原始抓取快照留在 `data/raw/`。

## 自检

```
运行自检.bat
```

9 步：数据体检 → 应用自检 → 建卡流程 → 逐级数值对账（约 2200 项）→
布局审计 → 中英文案 → 提示裁切 → 召唤物校验 → 模块依赖。
全绿时以 `ALL CHECKS PASSED` 结束。

改数据文件后还要单独跑对应校验器（它们不在批处理里）：

```
python _featcheck.py      # feats_general.json
python _itemcheck.py      # items.json
python _moncheck.py       # monsters.json
python _summoncheck.py    # summons.json
```

另有可选的深度验证脚本，在 `backup/` 下：
`_p2_snapshot.py` + `_p2_diff.py`（12 职业 × 1–20 级 = 248 组数值快照比对，需
`PYTHONHASHSEED=0`）、`_p5_tagcheck.py`（逐个 tag 检出到独立 worktree 跑全套自检）、
`_p6a_probe.py` … `_p6f_uiprobe.py`（五项功能的界面与数值探针）。

## 已知取舍

- **变形与召唤不替换角色本体的数值**：程序给出形态/伙伴的 Stat Block 与掷骰，
  角色属性、HP 仍按本体记录，避免一次变形把存档写坏。
- 63 件「无法机械计算」的魔法物品（如「寒冷伤害减免 2d8」）只展示完整文字效果，
  不参与数值计算；它们的 `note_only: true` 表示「除已填数值外还有算不了的效果」。
- 传奇恩惠里一部分效果（能量转移、复原池等）按说明记录，不自动结算。
- 只有简体中文界面。

## 许可与声明

本项目是**非官方、免费**的粉丝作品（unofficial fan content），与 Wizards of the Coast 无隶属关系。

- **程序代码**（`dnd55e/`、`dnd5r/`、`apps/`、`tools/` 等）：MIT License，见 `LICENSE`
- **SRD 5.2 规则内容**：依 CC-BY-4.0 使用，已翻译并重构为中文 JSON
- **非 SRD 的 2024 核心内容**：依 WotC [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy) 使用

完整署名、修改说明与免责声明见 **[`NOTICE.md`](NOTICE.md)**。

本仓库**不包含** `data/raw/` 上游原始快照（已在 `.gitignore` 排除），需要时自行运行
`_fetch_srd.py` 获取。

> 本作品部分材料版权归 Wizards of the Coast LLC 所有。
> Portions of the materials used are property of Wizards of the Coast LLC. ©Wizards of the Coast LLC.
> This is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards.

## 文档

- `dnd55e_rules_reference.md` — 规则基准与实现口径（2024 vs 2014 差异、逐条实现的判定）
- `_dataspec.md` — 数据字段规范（给改数据的人看）
- `重构方案.md` — P1–P5 模块化改造记录（已完成）
- `P6方案.md` — P6 五项功能补齐与执行结果（已完成）
