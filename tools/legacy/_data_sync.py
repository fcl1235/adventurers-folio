# -*- coding: utf-8 -*-
"""
数据同步 (本地优先, 缺什么补什么)
=================================
1. 检查本地数据完整性
2. 缺文件才联网抓取 (已有的不重复下载)
3. 打印本地资料清单

用法:
  python _data_sync.py           # 缺什么补什么
  python _data_sync.py --check   # 只体检, 不联网
  python _data_sync.py --force   # 强制重新下载全部
"""
import json
import os
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(DIR, "data", "raw")
PY = sys.executable

CORE = ["dnd55e_core_data.json", "dnd55e_spells.json",
        "dnd55e_classes_detail.json"]
RAW_CATS = ["spells", "classes", "subclasses", "backgrounds", "feats",
            "equipment", "magic-items", "conditions", "skills",
            "ability-scores", "languages", "damage-types",
            "weapon-properties", "equipment-categories", "magic-schools",
            "proficiencies", "class-levels",
            "class-levels-2024", "features-2024", "subclasses-srd"]


def stat(path):
    if not os.path.exists(path):
        return None
    try:
        if path.endswith(".json"):
            d = json.load(open(path, encoding="utf-8"))
            if isinstance(d, dict):
                if "spells" in d:
                    return f"{len(d['spells'])} 条法术"
                if "classes" in d and "subclasses" in d:
                    return (f"{len(d['classes'])} 职业 / "
                            f"{len(d['subclasses'])} 子职")
                if "items" in d:
                    return f"{len(d['items'])} 条"
                return f"{len(d)} 个字段"
    except Exception:
        pass
    return f"{os.path.getsize(path) // 1024} KB"


def main():
    check_only = "--check" in sys.argv
    force = "--force" in sys.argv
    missing = []

    for f in CORE:
        if not os.path.exists(os.path.join(DIR, f)):
            missing.append(f)

    raw_dir = RAW
    for c in RAW_CATS:
        p = os.path.join(raw_dir, c + ".json")
        if not os.path.exists(p) or os.path.getsize(p) < 200:
            missing.append(f"data/raw/{c}.json")

    print("本地资料:")
    for f in CORE:
        p = os.path.join(DIR, f)
        print(f"  {'✓' if os.path.exists(p) else '✗'} {f:24s} {stat(p) or '缺失'}")
    ok_raw = sum(1 for c in RAW_CATS
                 if os.path.exists(os.path.join(raw_dir, c + ".json")))
    print(f"  {'✓' if ok_raw == len(RAW_CATS) else '!'} data/raw/ "
          f"{ok_raw}/{len(RAW_CATS)} 个分类")

    if not missing:
        print("\n全部数据已在本地，无需联网。")
        return 0

    print(f"\n缺失 {len(missing)} 项: {', '.join(missing)}")
    if check_only:
        print("(--check 模式: 不联网)")
        return 1

    print("开始补齐 (只抓缺失项) ...")
    args = [PY, os.path.join(DIR, "_build_spells.py")]
    if force:
        args.append("--force")
    if "dnd55e_spells.json" in missing or force:
        subprocess.run(args, cwd=DIR)
    if any(m.startswith("data/raw/") for m in missing) or force:
        a2 = [PY, os.path.join(DIR, "_fetch_srd.py")]
        if force:
            a2.append("--force")
        subprocess.run(a2, cwd=DIR)

    detail_raw = ("class-levels-2024", "features-2024", "subclasses-srd")
    need_detail_raw = any(f"data/raw/{c}.json" in missing for c in detail_raw)
    need_detail = "dnd55e_classes_detail.json" in missing
    if need_detail_raw or force:
        a3 = [PY, os.path.join(DIR, "_fetch_class_detail.py")]
        if force:
            a3.append("--force")
        subprocess.run(a3, cwd=DIR)
        need_detail = True
    if need_detail or force:
        subprocess.run([PY, os.path.join(DIR, "_build_class_detail.py")], cwd=DIR)

    still = [m for m in missing
             if not os.path.exists(os.path.join(DIR, m if m.startswith("data/")
                                                else m))]
    if still:
        print("\n仍未补齐 (可能无网络):", ", ".join(still))
        print("程序在缺法术库时会自动跳过选法术步骤，其余功能不受影响。")
        return 1
    print("\n补齐完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
