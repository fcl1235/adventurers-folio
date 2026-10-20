# -*- coding: utf-8 -*-
"""纯函数工具: 属性调整值、熟练加值、掷骰解析、法术文本。"""
import random

from . import consts
from . import summoning
from .consts import (feat_cn, feat_desc, mastery_cn, size_cn,
                        subclass_cn, tool_cn)

# 拆分后需要的内部依赖
from .consts import ABILITIES, ABILITY_CN


def ability_mod(score):
    return (score - 10) // 2


def mod_str(m):
    return ("+" if m >= 0 else "") + str(m)


def proficiency_bonus(level):
    return 2 + (level - 1) // 4


def roll_dice_reroll(expr, threshold=2):
    """NdM+K, 每个骰子掷出 <= threshold 时重掷一次(采用新结果)。
    2024 巨武器战斗: 双手/双手持用武器伤害骰出 1 或 2 可重掷。"""
    expr0 = expr.replace(" ", "")
    expr, sign, k = expr0, 0, 0
    if "+" in expr:
        expr, ks = expr.split("+")
        sign, k = 1, int(ks)
    elif "-" in expr:
        expr, ks = expr.split("-")
        sign, k = -1, int(ks)
    if "d" not in expr.lower():
        base = int(expr)
        return base + sign * k, f"{expr0} = {base + sign * k}"
    n, m = expr.lower().split("d")
    n, m = int(n), int(m)
    rolls, fixes = [], []
    for _ in range(n):
        r = random.randint(1, m)
        if r <= threshold:
            old = r
            r = random.randint(1, m)
            fixes.append(f"{old}→{r}")
        rolls.append(r)
    total = sum(rolls) + sign * k
    detail = "+".join(map(str, rolls))
    if n > 1:
        detail = f"({detail})"
    if sign:
        detail += ("+" if sign > 0 else "-") + str(k)
    tag = f"  [巨武器重掷 {' '.join(fixes)}]" if fixes else ""
    return total, f"{expr}: [{detail}] = {total}{tag}"



def roll_dice(expr):
    """解析 'NdM' / 'NdM+K' / 'NdM-K' / 固定值 '1' / '1+3'，返回 (总数, 明细)"""
    expr = expr.replace(" ", "")
    sign, k = 0, 0
    if "+" in expr:
        expr, ks = expr.split("+")
        sign, k = 1, int(ks)
    elif "-" in expr:
        expr, ks = expr.split("-")
        sign, k = -1, int(ks)
    if "d" not in expr.lower():          # 固定伤害 (徒手 1 点 / 吹箭 1 点)
        base = int(expr)
        total = base + sign * k
        detail = str(base) + (("+" if sign > 0 else "-") + str(k) if sign else "")
        return total, f"{expr}: {detail} = {total}"
    n, m = expr.lower().split("d")
    n, m = int(n), int(m)
    rolls = [random.randint(1, m) for _ in range(n)]
    total = sum(rolls) + sign * k
    detail = "+".join(map(str, rolls))
    if n > 1:
        detail = f"({detail})"
    if sign:
        detail += ("+" if sign > 0 else "-") + str(k)
    return total, f"{expr}: [{detail}] = {total}"


def roll_4d6kh3():
    d = [random.randint(1, 6) for _ in range(4)]
    return sum(sorted(d, reverse=True)[:3])


def spell_detail(s):
    """法术详情文本 (向导与角色卡共用)"""
    if not s:
        return "选择法术查看详情。"
    lines = [f"{s['name']}  {s['name_en']}",
             f"{s['level']} 环 · {s['school']}    {s['cast']}    {s['range']}",
             f"成分: {s['comp']}    持续: {s['duration']}"
             + ("    【专注】" if s["concentration"] else "")
             + ("    【仪式】" if s["ritual"] else "")]
    extra = []
    if s["save"]:
        extra.append(f"{s['save']}豁免")
    if s["damage"]:
        extra.append(f"伤害 {s['damage']} {s['damage_type']}")
    if s["attack"]:
        extra.append("法术攻击")
    if s["area"]:
        extra.append(f"范围 {s['area']}")
    if extra:
        lines.append(" ｜ ".join(extra))
    lines.append("")
    lines.append(s["desc"] or "（效果见 SRD 原文）")
    block = summoning.summon_block(s)
    if block:
        lines.append("")
        lines.append(block)
    sc = s.get("scaling") or {}
    if len(sc) > 1:
        up = "、".join(f"{k}环:{v}" for k, v in list(sc.items())[1:4])
        lines.append(f"升环: {up}")
    return "\n".join(lines)

def ab_from_display(display_name):
    for ab in ABILITIES:
        if display_name == f"{ABILITY_CN[ab]}({ab})":
            return ab
    return ABILITIES[0]
