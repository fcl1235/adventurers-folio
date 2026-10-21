# -*- coding: utf-8 -*-
"""架构设计文档体检：确保「12 职业探针」不是嘴上说说。

检查项：
  1. data 里 12 个职业在 §11.2 表格里各有一行，不多不少
  2. §11.3 的缺口编号 G1..Gn 连续、不重复，且 §11.2 引用到的都存在
  3. §1 的硬约束 C1..Cn 连续；C7=双语、C8=双等级 必须在
  4. §12（兼职）与 §13（内容模型）的小节编号连续
  5. 双语示例至少 3 处 `zh:` + `en:` 同时出现
  6. 每个职业在 §11.2 至少给出 3 条真实机制（探针不能糊弄）

退出码 0 = 通过。不弹窗、不依赖第三方库。
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(ROOT, "架构设计v3-插件化.md")
DATA = os.path.join(ROOT, "dnd55e_classes_detail.json")

CN = {
    "barbarian": "野蛮人", "bard": "吟游诗人", "cleric": "牧师", "druid": "德鲁伊",
    "fighter": "战士", "monk": "武僧", "paladin": "圣武士", "ranger": "游侠",
    "rogue": "游荡者", "sorcerer": "术士", "warlock": "邪术师", "wizard": "法师",
}


def read():
    with io.open(DOC, encoding="utf-8") as f:
        return f.read()


def section(text, start_pat, end_pat):
    m = re.search(start_pat, text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    m2 = re.search(end_pat, rest, re.M)
    return rest[:m2.start()] if m2 else rest


def table_rows(body):
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return rows


def main():
    errs, warns = [], []
    text = read()
    data = json.load(io.open(DATA, encoding="utf-8"))["classes"]

    # 1. 12 职业覆盖
    probe = section(text, r"^### 11\.2 逐职业结论.*$", r"^### 11\.3")
    prows = table_rows(probe)[1:]              # 去掉表头
    seen = {}
    for cells in prows:
        if len(cells) < 3:
            continue
        name = cells[0]
        for cid, zh in CN.items():
            if name.startswith(zh):
                seen[cid] = cells
    for cid, zh in CN.items():
        if cid not in data:
            errs.append("数据缺职业: %s" % cid)
        if cid not in seen:
            errs.append("§11.2 缺探针行: %s(%s)" % (zh, cid))
    extra = set(seen) - set(data)
    if extra:
        errs.append("§11.2 有数据里不存在的职业: %s" % ", ".join(sorted(extra)))

    # 6. 每个职业至少 3 条真实机制
    for cid, cells in seen.items():
        feats = cells[1]
        n = feats.count("）") + feats.count(")")
        if n < 3:
            warns.append("§11.2 %s 只列了 %d 条机制" % (CN[cid], n))

    # 2. 缺口编号
    gaps = section(text, r"^### 11\.3.*$", r"^### 11\.4")
    gids = []
    for cells in table_rows(gaps)[1:]:
        if cells and re.fullmatch(r"G\d+", cells[0]):
            gids.append(int(cells[0][1:]))
    if not gids:
        errs.append("§11.3 没解析到缺口表")
    else:
        if gids != list(range(1, len(gids) + 1)):
            errs.append("§11.3 缺口编号不连续/重复: %s" % gids)
        cited = {int(x) for x in re.findall(r"G(\d+)", probe)}
        missing = sorted(cited - set(gids))
        if missing:
            errs.append("§11.2 引用了不存在的缺口: %s" % missing)
        for g in gids:
            if not re.search(r"\bG%d\b" % g, probe + text[text.find("### 11.2"):text.find("### 11.4")]):
                warns.append("缺口 G%d 没有被任何职业逼出来" % g)

    # 3. 硬约束
    cons = []
    for cells in table_rows(section(text, r"^## 1\. .*$", r"^## 2\.")):
        if cells and re.fullmatch(r"C\d+", cells[0]):
            cons.append(int(cells[0][1:]))
    if cons != list(range(1, len(cons) + 1)):
        errs.append("§1 约束编号不连续: %s" % cons)
    if len(cons) < 8:
        errs.append("§1 约束少于 8 条（C7 双语 / C8 双等级 必须存在）")
    if "双语齐全" not in text:
        errs.append("C7 双语约束缺失")
    if "等级不可互换" not in text:
        errs.append("C8 双等级约束缺失")

    # 4. 兼职与内容模型小节编号
    for sec, want in (("12", 6), ("13", 9)):
        got = sorted({int(n) for n in re.findall(r"^### %s\.(\d+) " % sec, text, re.M)})
        if got != list(range(1, want + 1)):
            errs.append("§%s 小节编号异常: %s（期望 1..%d）" % (sec, got, want))

    # 5. 双语示例
    n_zh = len(re.findall(r"zh:\s*\S", text))
    n_en = len(re.findall(r"en:\s*\S", text))
    if min(n_zh, n_en) < 3:
        errs.append("双语示例不足（zh=%d, en=%d）" % (n_zh, n_en))

    print("=== 设计文档体检 ===")
    print("文档行数      : %d" % len(text.splitlines()))
    print("职业覆盖      : %d / 12" % len(seen))
    print("缺口条数      : %d" % len(gids))
    print("硬约束        : %d 条" % len(cons))
    print("双语示例      : zh %d 处 / en %d 处" % (n_zh, n_en))
    for cid in CN:
        if cid in seen:
            print("  %-9s %s" % (CN[cid], seen[cid][1][:60]))
    for w in warns:
        print("[WARN] %s" % w)
    for e in errs:
        print("[FAIL] %s" % e)
    print("DESIGNCHECK %s" % ("OK" if not errs else "FAILED"))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
