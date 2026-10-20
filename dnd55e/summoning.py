# -*- coding: utf-8 -*-
"""法术召唤物 / 变形形态的查询与文本化。

2024 版把召唤法术统一成「用一个 Stat Block」，而变形类法术（变形术、完全变形术、
动物形态）则是「按条件筛选任意野兽」。两者在 dnd55e_spells.json 里都用同一个
可选字段 `summon` 描述：

  {"kind": "statblock", "options": [{"name": "陆行", "statblock": "bestial-spirit-land"}],
   "note": "…"}
  {"kind": "filter", "type": "beast", "cr": "target", "size": "任意",
   "exclude": ["swarm"], "note": "…"}

本模块只负责「读 + 拼文案」，不做界面，也不改角色数值 —— 召唤物的 AC/HP 是随
施法环级变化的公式，交给人按实际环级读，程序不代算。
"""
from . import consts

# 体型中文（summons.json 里 size 直接存中文，个别是 "微型/小型/中型/大型/巨型"）
CR_CN = {"target": "不超过目标原本的 CR（无 CR 时用其等级）",
         "any": "不超过目标原本的 CR 或等级"}

TYPE_CN = {"beast": "野兽", "any": "任意生物", "celestial": "天界生物",
           "fiend": "邪魔", "fey": "妖精", "undead": "亡灵",
           "construct": "构装", "elemental": "元素", "dragon": "龙",
           "aberration": "异怪"}


def summon_of(spell):
    """取法术的 summon 描述；没有则返回 None"""
    return (spell or {}).get("summon") or None


def statblocks(spell):
    """statblock 型法术对应的召唤物条目列表（按 options 顺序）"""
    sm = summon_of(spell)
    if not sm or sm.get("kind") != "statblock":
        return []
    table = consts.SUMMONS_BY_ID
    out = []
    for opt in sm.get("options") or []:
        sb = table.get(opt.get("statblock") or "")
        if sb:
            item = dict(sb)
            item["_option"] = opt.get("name") or sb.get("variant") or ""
            out.append(item)
    return out


def _speed_text(sp):
    parts = []
    for key, cn in (("walk", "步行"), ("climb", "攀爬"), ("fly", "飞行"),
                    ("swim", "游泳"), ("burrow", "掘地")):
        v = sp.get(key) or 0
        if v:
            parts.append(f"{cn} {v} 尺")
    if sp.get("hover"):
        parts.append("（可悬浮）")
    return "、".join(parts) if parts else "—"


def _senses_text(sns):
    parts = []
    for key, cn in (("darkvision", "黑暗视觉"), ("blindsight", "盲视"),
                    ("tremorsense", "震颤感知"), ("truesight", "真实视觉")):
        v = sns.get(key) or 0
        if v:
            parts.append(f"{cn} {v} 尺")
    p = sns.get("passive_perception") or 0
    if p:
        parts.append(f"被动察觉 {p}")
    return "、".join(parts) if parts else "—"


def _action_lines(actions, label):
    out = []
    for a in actions or []:
        out.append(f"  · [{label}] {a['name']}")
        out.append(f"    {a['desc']}")
    return out


def card_text(sb):
    """把一个召唤物条目渲染成 stat block 文本（供详情卡显示）"""
    if not sb:
        return "（没有可显示的 stat block）"
    ab = sb.get("abilities") or {}
    lines = [sb.get("name") or "（未命名）",
             f"{sb.get('size') or '—'} · {TYPE_CN.get(sb.get('type'), sb.get('type') or '—')}"
             + (f"    （{sb['_option']}）" if sb.get("_option") else ""),
             f"AC {sb.get('ac')}    HP {sb.get('hp')}"
             + (f"    生命骰 {sb['hp_dice']}" if sb.get("hp_dice") not in (None, "", "—") else ""),
             f"速度 {_speed_text(sb.get('speed') or {})}",
             "属性  " + "  ".join(f"{k} {ab.get(k, '—')}" for k in
                                  ("STR", "DEX", "CON", "INT", "WIS", "CHA")),
             f"感官 {_senses_text(sb.get('senses') or {})}",
             f"语言 {sb.get('languages') or '—'}"]
    traits = sb.get("traits") or []
    if traits:
        lines.append("")
        for t in traits:
            lines.append(f"· {t['name']}")
            lines.append(f"  {t['desc']}")
    acts = sb.get("actions") or []
    if acts:
        lines.append("")
        lines.append("动作")
        lines.extend(_action_lines(acts, "动作"))
    bonus = sb.get("bonus_actions") or []
    if bonus:
        lines.append("")
        lines.append("附赠动作")
        lines.extend(_action_lines(bonus, "附赠"))
    rea = sb.get("reactions") or []
    if rea:
        lines.append("")
        lines.append("反应")
        lines.extend(_action_lines(rea, "反应"))
    return "\n".join(lines)


def summon_block(spell):
    """法术详情里的「召唤物」段落（空字符串表示该法术没有召唤信息）"""
    sm = summon_of(spell)
    if not sm:
        return ""
    kind = sm.get("kind")
    if kind == "statblock":
        sbs = statblocks(spell)
        if not sbs:
            return ""
        head = "召唤物（用下列 Stat Block）"
        lines = [head]
        for sb in sbs:
            opt = sb.get("_option") or sb.get("name", "")
            lines.append(f"  · {opt}：{sb.get('name')}    AC {sb.get('ac')}    HP {sb.get('hp')}"
                         f"    速度 {_speed_text(sb.get('speed') or {})}")
        if sm.get("note"):
            lines.append(f"  {sm['note']}")
        return "\n".join(lines)
    if kind == "filter":
        t = TYPE_CN.get(sm.get("type"), sm.get("type") or "任意生物")
        cr = sm.get("cr")
        cr_txt = CR_CN.get(cr) or f"CR ≤ {cr}"
        size = sm.get("size") or "任意"
        excl = sm.get("exclude") or []
        line = f"可变形态：{t}    体型 {size}    {cr_txt}"
        if excl:
            names = {"swarm": "虫群"}
            line += "    排除：" + "、".join(names.get(e, e) for e in excl)
        out = ["变形 / 召唤范围", "  " + line]
        if sm.get("note"):
            out.append(f"  {sm['note']}")
        return "\n".join(out)
    return ""
