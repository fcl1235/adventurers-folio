# 许可与权利声明 / Licenses & Notices

本项目是**非官方的、免费的**粉丝作品（unofficial fan content），不与 Wizards of the Coast LLC
（威世智）存在任何隶属、赞助或背书关系。

This is unofficial, non-commercial Fan Content. Not approved or endorsed by Wizards of the Coast.

---

## 1. 程序代码

`dnd55e/`、`dnd5r/`、`apps/`、`tools/`、`tests/` 及各校验脚本（`*.py`、`*.bat`）的著作权归本项目作者，
以 **MIT License** 授权，全文见 `LICENSE`。

**MIT 许可仅覆盖源代码**，不覆盖 `plugins/` 下的规则内容与 Markdown 文档；那些内容适用第 2、3 节的条件。
（`LICENSE` 保持标准 MIT 原文不加补充条款，是为了让 GitHub 能正确识别许可类型；适用范围写在这里。）

## 2. SRD 5.2 内容（CC-BY-4.0）

本项目部分规则内容来自《System Reference Document 5.2》（SRD 5.2，对应 D&D 2024 版核心规则），
由 Wizards of the Coast LLC 依 **Creative Commons Attribution 4.0 International（CC-BY-4.0）** 发布。

> This work includes material from the System Reference Document 5.2 ("SRD 5.2") by
> Wizards of the Coast LLC, available at https://www.dndbeyond.com/srd.
> The SRD 5.2 is licensed under the Creative Commons Attribution 4.0 International License,
> available at https://creativecommons.org/licenses/by/4.0/legalcode.

**已作修改（Indication of changes）**：本项目将 SRD 5.2 的英文规则内容翻译为简体中文，
并将规则文本重构为便于程序读取的 JSON 数据结构，同时在界面上以表单、数值计算与 Stat Block
等形式重新呈现。这些改动不改变原规则的机制含义。

## 3. 非 SRD 内容（Fan Content Policy）

本项目同时收录了部分**不在 SRD 5.2 范围内**的 2024 版核心规则内容（例如部分子职、背景、
专长、魔法物品与 Summon 系列召唤法术），以及少量 WotC 拥有的产品标识名词。
这些内容的依据是 Wizards of the Coast 的
[Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy)，即：

- 本项目**完全免费**，不设付费墙、订阅、注册墙或任何形式的付费门槛；
- 本项目**不包含、不使用** WotC 的商标、标识（logo）、美术作品或字体资源；
- 本项目为**非官方**作品，已在上方作出明确声明；
- WotC 保留随时要求调整或撤下相关内容的权利，本项目作者将遵从。

> Portions of the materials used are property of Wizards of the Coast LLC.
> ©Wizards of the Coast LLC. This is unofficial Fan Content permitted under the
> Fan Content Policy. Not approved/endorsed by Wizards.

## 4. 商标

"Dungeons & Dragons"、"D&D"、Dragon Ampersand 及相关标识是 Wizards of the Coast LLC 的注册商标。
本项目名称 `adventurers-folio`（中文名「冒险者手帖」）不使用上述商标；正文中对规则版本的指代仅用于说明兼容性（"compatible with
fifth edition" / "5E compatible"），不构成商标使用授权。

## 5. 不收录的内容

为降低权利风险，本仓库**不包含**上游原始抓取快照（`data/raw/`），该目录已在 `.gitignore` 中排除。
需要原始数据请自行运行 `_fetch_srd.py` / `_fetch_class_detail.py` 从公开的 SRD 5.2 数据源获取。

## 6. 免责

规则内容按"现状"提供，作者不对其完整性与准确性作任何担保，亦不承担因使用本程序产生的任何责任。
若权利人认为本项目某处内容不当，请通过 Issue 联系，作者会及时处理。
