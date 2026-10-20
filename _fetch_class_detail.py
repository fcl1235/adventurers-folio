#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 SRD 5.2 (2024) 的职业等级表 / 职业特性 / 子职，落盘到 data/raw/。

只用于补全「职业特性 + 资源池 + 子职介绍」，不参与运行时联网。
缓存优先：目标文件已存在则跳过（--force 重抓）。
"""
import json
import os
import sys
import time
import urllib.request

BASE = "https://www.dnd5eapi.co"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw")
UA = {"User-Agent": "Mozilla/5.0 (dnd55e-character-builder data sync)"}


def get(path, retries=3):
    url = path if path.startswith("http") else BASE + path
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:          # 网络抖动重试
            last = e
            time.sleep(1.2 * (i + 1))
    raise last


def save(name, obj, force=False):
    p = os.path.join(RAW, name)
    if os.path.exists(p) and not force:
        print(f"  = {name} 已存在, 跳过")
        return False
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    print(f"  ✓ {name}  {os.path.getsize(p) // 1024} KB")
    return True


def main():
    force = "--force" in sys.argv
    os.makedirs(RAW, exist_ok=True)

    print("1) 职业等级表 (含 class_specific 资源数值)")
    classes = json.load(open(os.path.join(RAW, "classes.json"),
                             encoding="utf-8"))["items"]
    levels = {}
    for c in classes:
        cid = c["index"]
        try:
            lv = get(f"/api/2024/classes/{cid}/levels")
            levels[cid] = lv
            print(f"  ✓ {cid:9s} {len(lv)} 级")
        except Exception as e:
            print(f"  ✗ {cid}: {e}")
    save("class-levels-2024.json", levels, force)

    print("2) 职业特性说明")
    feats = {}
    for cid, lv in levels.items():
        for row in lv:
            for f in row.get("features", []):
                idx = f["index"]
                if idx in feats:
                    continue
                try:
                    feats[idx] = get(f["url"])
                except Exception as e:
                    print(f"  ✗ {idx}: {e}")
    save("features-2024.json", feats, force)
    print(f"  共 {len(feats)} 条特性")

    print("3) SRD 子职 (每职业 1 个, 含各级特性与说明)")
    subs = {}
    for c in classes:
        for s in c.get("subclasses", []):
            try:
                subs[s["index"]] = get(s["url"])
                print(f"  ✓ {s['index']:22s} "
                      f"{len(subs[s['index']].get('features', []))} 条特性")
            except Exception as e:
                print(f"  ✗ {s['index']}: {e}")
    save("subclasses-srd.json", subs, force)
    print("完成。")


if __name__ == "__main__":
    main()
