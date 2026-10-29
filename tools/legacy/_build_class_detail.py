#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 SRD 5.2 抓取的职业/子职数据与中文释义合并成运行时文件
dnd55e_classes_detail.json。

输入: data/raw/class-levels-2024.json, data/raw/features-2024.json,
      detail_features_cn.py, detail_subclasses_cn.py, dnd55e_core_data.json
用法: python _build_class_detail.py
"""
import json
import os
import sys

from _path import PROJECT_ROOT as HERE           # 项目根（本脚本在 tools/legacy/）

from detail_features_cn import FEATURE_CN, RESOURCES, DICE_NOTES   # noqa: E402
from detail_subclasses_cn import SUBCLASS_INFO                     # noqa: E402

RAW = os.path.join(HERE, "data", "raw")
OUT = os.path.join(HERE, "dnd55e_classes_detail.json")


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def level_table(spec):
    """把 {等级阈值: 值} 展开成 1..20 的完整表（向下沿用）"""
    out, cur = {}, None
    for lv in range(1, 21):
        if lv in spec:
            cur = spec[lv]
        out[lv] = cur
    return out


def main():
    core = load("dnd55e_core_data.json")
    levels = load(os.path.join("data", "raw", "class-levels-2024.json"))
    feats = load(os.path.join("data", "raw", "features-2024.json"))
    srd_subs = load(os.path.join("data", "raw", "subclasses-srd.json"))

    problems = []
    out = {"meta": {
        "name": "dnd55e 职业/子职明细",
        "rules": "D&D 2024 (5.5e / 5R), SRD 5.2 (CC-BY-4.0)",
        "note": "职业特性与资源数值取自 SRD 5.2；非 SRD 子职为 PHB 2024 要点摘要。",
    }, "classes": {}, "subclasses": {}}

    # ---------------- 职业特性 + 资源 ---------------- #
    for cls in core["classes"]:
        cid = cls["id"]
        rows = levels.get(cid, [])
        feats_out, seen = [], set()
        for row in rows:
            for f in row.get("features", []):
                idx = f["index"]
                if idx in seen:
                    continue
                seen.add(idx)
                rec = feats.get(idx, {})
                cn = FEATURE_CN.get(idx)
                if not cn:
                    problems.append(f"缺少中文: {idx} ({rec.get('name')})")
                    cn = (rec.get("name") or idx, "")
                feats_out.append({
                    "index": idx,
                    "level": row["level"],
                    "name_en": rec.get("name") or idx,
                    "name": cn[0],
                    "desc": cn[1],
                })
        # 资源池
        res = []
        for r in RESOURCES.get(cid, []):
            item = {k: v for k, v in r.items() if k in
                    ("id", "name", "from_level", "short", "long", "note",
                     "icon", "die", "short_after_level", "short_after")}
            if isinstance(r["max"], dict):
                item["table"] = level_table(r["max"])
                item["formula"] = None
            else:
                item["table"] = None
                item["formula"] = r["max"]
            res.append(item)
        out["classes"][cid] = {
            "features": feats_out,
            "resources": res,
            "dice_note": DICE_NOTES.get(cid, ""),
            "class_specific": {},   # 运行时另算（武艺骰/偷袭骰等）
        }
        # 附带 SRD 的 class_specific 表，供武器专精/武艺骰/偷袭取数
        cs_tables = {}
        for row in rows:
            cs = row.get("class_specific") or {}
            cs_tables[row["level"]] = cs
        out["classes"][cid]["class_specific"] = cs_tables

    # ---------------- 子职 ---------------- #
    uniq_en = []
    for cls in core["classes"]:
        for s in cls["subclasses"]:
            uniq_en.append((cls["id"], s))
    for cid, name in uniq_en:
        info = SUBCLASS_INFO.get(name)
        if not info:
            problems.append(f"缺少子职说明: {name}")
            continue
        lv = sorted({f[0] for f in info["features"]})
        # 与 SRD 对照（仅 SRD 子职）
        srd_key = None
        for k, v in srd_subs.items():
            if v["name"] == name:
                srd_key = k
                break
        if srd_key:
            srd_lv = sorted({f["level"] for f in srd_subs[srd_key]["features"]})
            if srd_lv != lv:
                problems.append(f"{name} 等级与 SRD 不一致: {lv} vs {srd_lv}")
        out["subclasses"][name] = {
            "class": cid,
            "srd": bool(info.get("srd")),
            "summary": info["summary"],
            "levels": lv,
            "features": [{"level": a, "name": b, "desc": c}
                         for a, b, c in info["features"]],
        }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    n_feat = sum(len(v["features"]) for v in out["classes"].values())
    print(f"✓ {OUT}")
    print(f"  职业 {len(out['classes'])} 个 / 特性 {n_feat} 条 / "
          f"子职 {len(out['subclasses'])} 个")
    if problems:
        print("\n⚠ 需要处理:")
        for p in problems:
            print("  -", p)
        return 1
    print("  校验通过（无缺漏，SRD 子职等级一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
