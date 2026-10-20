# -*- coding: utf-8 -*-
"""游荡者：专精、可靠天赋、滑溜心智、偷袭。"""
from . import registry
from .base import ClassModule


@registry.register("rogue")
class Rogue(ClassModule):
    name_cn = "游荡者"

    def expertise_allowance(self, ch, level):
        return 2 + (2 if level >= 6 else 0)

    def save_profs_extra(self, ch):
        """滑溜心智 (15 级): 感知与魅力豁免熟练"""
        return {"WIS", "CHA"} if ch.level >= 15 else set()

    def reliable_talent(self, ch, skill_id):
        return ch.level >= 7 and skill_id in ch.skill_prof

    def sneak_dice(self, ch):
        """偷袭骰数: 优先取 SRD 逐级表, 否则 1 级起每 2 级 +1d6"""
        sa = ch.class_stat("sneak_attack", None)
        if isinstance(sa, dict) and sa.get("dice_count"):
            return int(sa["dice_count"])
        return (ch.level + 1) // 2

    def explain(self, ch, phase):
        out = []
        if phase == "early":
            if ch.level >= 15:
                out.append((162, "职业·滑溜心智: 感知与魅力豁免熟练"))
            if ch.level >= 7:
                out.append((164, "职业·可靠天赋: 熟练技能的检定，d20 掷出 9 或以下按 10 计"))
        else:
            n = ch.sneak_dice()
            out.append((226, f"职业·偷袭: 额外 {n}d6 (优势或同伴相邻时，"
                             "勾选「含偷袭」后掷伤害会加上)"))
        return out
