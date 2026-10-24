# -*- coding: utf-8 -*-
"""P10a 生成器：从 `monsters.yaml` 生成荒野变形可选的 `bestiary/beasts.yaml`。

**为什么改成生成**：形态卡原本是 P4 手抄的 2014 版数据，与 SRD 5.2 已经漂了
（巨鳄 HP 19 vs 13、狼力量 12 vs 14、黑熊敏捷 10 vs 12、豹 AC 12 vs 13），
而形态的整张卡本来**就是**那只野兽的卡 —— 两处各存一份，迟早各说各话。
现在 16 只形态全部由怪物条目派生，`--check` 进 CI，漂不动。

**为什么动作也一起抄过来**：G22 修的就是「变成熊以后只能按徒手 1 + 力量算」。
动作的形状与怪物完全一样（`MonsterAttack`），结算走同一条
`resolve_monster_attack`，所以这里原样搬运 `attack_bonus` —— 绝不按
「属性调整值 + 熟练」重算（实测 91 只里 95 条攻击有 85 条推不出来）。

**为什么要一张手写表**：形态 id 与怪物 id 不总是同名（`rat` 对应巨鼠
`giant_rat`、`poisonous_snake` 在 2024 叫 `venomous_snake`），而且「哪些野兽
算野兽」是选材决定，不该由机器猜。改选材就改 `FORMS`。

用法：
  python tools/gen_beasts.py            # 写出 plugins/dnd2024-core/bestiary/beasts.yaml
  python tools/gen_beasts.py --check    # 只比对，不写文件（CI 用）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.gen_monsters import bilingual_text, inline, quote  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plugins" / "dnd2024-core" / "monsters.yaml"
OUT = ROOT / "plugins" / "dnd2024-core" / "bestiary" / "beasts.yaml"

# (形态 id 尾段, 怪物 id 尾段)。顺序照原文件，大致按 CR 递增。
FORMS: tuple[tuple[str, str], ...] = (
    ("bat", "bat"),
    ("cat", "cat"),
    ("frog", "frog"),
    ("owl", "owl"),
    ("rat", "giant_rat"),                  # 形态名「巨鼠」，id 沿用 P4 的短名
    ("weasel", "weasel"),
    ("poisonous_snake", "venomous_snake"),  # 2024 把毒蛇改名叫 venomous snake
    ("boar", "boar"),
    ("panther", "panther"),
    ("wolf", "wolf"),
    ("black_bear", "black_bear"),
    ("crocodile", "crocodile"),
    ("reef_shark", "reef_shark"),
    ("brown_bear", "brown_bear"),
    ("giant_spider", "giant_spider"),
    ("giant_eagle", "giant_eagle"),
)

SPEED_KEYS = ("walk", "climb", "fly", "swim", "burrow")
SENSE_KEYS = ("blindsight", "darkvision", "tremorsense", "truesight")
ABILITY_KEYS = ("str", "dex", "con", "int", "wis", "cha")


def number_inline(mapping: dict) -> str:
    """数值映射写成 flow mapping，**不加引号**。

    `gen_monsters.inline()` 会把 `"12"` 这种字符串数字加引号（旧数据是字符串），
    形态表里的值本来就是整数，不该跟着写成一堆 `"12"`。
    """
    return "{ %s }" % ", ".join("%s: %s" % (key, value)
                                for key, value in mapping.items())


def render_attack(row: dict, indent: str = "    ") -> list[str]:
    """一条动作。字段顺序与 `monsters.yaml` 保持一致，diff 才看得懂。"""
    lines = ["%s- name: %s" % (indent, inline(row["name"])),
             "%s  kind: %s" % (indent, row.get("kind", "melee"))]
    for key in ("attack_bonus", "reach", "range", "long_range", "save", "save_dc"):
        value = row.get(key)
        if value in (None, 0, ""):
            continue
        lines.append("%s  %s: %s" % (indent, key,
                                     int(value) if isinstance(value, int)
                                     else quote(value)))
    damage = row.get("damage") or []
    if damage:
        lines.append("%s  damage:" % indent)
        lines.extend("%s    - %s" % (indent, inline(item)) for item in damage)
    text = row.get("text") or {}
    if text:
        lines.extend(bilingual_text("text", text.get("zh", ""), text.get("en", ""),
                                    indent + "  "))
    return lines


def render_trait(row: dict, indent: str = "    ") -> list[str]:
    text = row.get("text") or {}
    lines = ["%s- name: %s" % (indent, inline(row["name"]))]
    lines.extend(bilingual_text("text", text.get("zh", ""), text.get("en", ""),
                                indent + "  "))
    # 掷骰形状（G23 / P10b）原样带过去：变狼的德鲁伊，群体战术判的是
    # 「变形这一层」的阵营与位置（root 是 pc，阵营默认我方）。
    mode = row.get("attack_mode") or {}
    if isinstance(mode, dict) and mode.get("mode"):
        lines.append("%s  attack_mode: %s"
                     % (indent, inline({"mode": mode.get("mode", ""),
                                        "when": mode.get("when", "")})))
    return lines


def render_form(slug: str, monster: dict) -> str:
    abilities = {key: int(monster["abilities"][key]) for key in ABILITY_KEYS}
    speeds = {key: int(value) for key, value in (monster.get("speeds") or {}).items()
              if key in SPEED_KEYS and int(value)}
    senses = {key: int(value) for key, value in (monster.get("senses") or {}).items()
              if key in SENSE_KEYS and int(value)}
    lines = [
        "- id: dnd2024.form.beast.%s" % slug,
        "  name: %s" % inline(monster["name"]),
        "  size: %s" % monster.get("size", "medium"),
        "  ac: %d" % int(monster["ac"]),
        "  hp: %d" % int(monster["hp"]),
        "  cr: %s" % ("%g" % float(monster.get("cr") or 0)),
        "  abilities: %s" % number_inline(abilities),
        "  speeds: %s" % number_inline(speeds or {"walk": 30}),
    ]
    if senses:
        lines.append("  senses: %s" % number_inline(senses))
    saves = {key: int(value) for key, value in (monster.get("saves") or {}).items()
             if key in ABILITY_KEYS}
    if saves:
        # 印着的豁免加值：猫的敏捷豁免 +4 而敏捷只有 +2，推不出来
        lines.append("  saves: %s" % number_inline(saves))
    for key, render in (("traits", render_trait), ("actions", render_attack),
                        ("bonus_actions", render_attack), ("reactions", render_attack)):
        rows = monster.get(key) or []
        if not rows:
            continue
        lines.append("  %s:" % key)
        for row in rows:
            lines.extend(render(row))
    return "\n".join(lines)


HEADER = """\
# 由 tools/gen_beasts.py 从 monsters.yaml 生成，别手改（改了就重跑生成器）。
#
# 荒野变形能变成的 16 种野兽（CR 0–1，够覆盖 CR 轴三档与游泳/飞行解禁）。
#
# 每条形态**就是那只野兽的整张卡**：ac / hp / cr / 六项属性 / 速度 / 感官 /
# 印着的豁免加值 / 特性 / 三个槽位的动作，全部原样搬自怪物条目。
# 所以变形后不用按「徒手 1 + 力量调整值」凑 —— 熊有熊的啃咬 1d8+3、命中 +5，
# 结算与怪物走同一条 `resolve_monster_attack`（G22）。
#
# 变形时仍按规则保留本体的 int/wis/cha（`build_form` 的 keep 名单），
# 这里存的是形态原值，不是混合后的结果。
"""


def build() -> str:
    rows = yaml.safe_load(SOURCE.read_text(encoding="utf-8")) or []
    by_id = {row["id"]: row for row in rows}
    body: list[str] = []
    for slug, monster_slug in FORMS:
        monster = by_id.get("dnd2024.monster.%s" % monster_slug)
        if monster is None:
            raise SystemExit("monsters.yaml 里没有 %s（形态 %s 需要它）"
                             % (monster_slug, slug))
        body.append(render_form(slug, monster))
    return HEADER + "\n" + "\n\n".join(body) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_beasts", description="生成兽形表")
    parser.add_argument("--check", action="store_true", help="只比对，不写文件")
    args = parser.parse_args(argv)

    if not SOURCE.exists():
        print("缺少数据源：%s" % SOURCE)
        return 2
    text = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("beasts.yaml 与生成结果不一致，请重跑 python tools/gen_beasts.py")
            return 1
        print("beasts.yaml 与生成结果一致")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("写出 %s（%d 种形态）" % (OUT.relative_to(ROOT), text.count("\n- id: ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
