# -*- coding: utf-8 -*-
"""把 SRD 5.2 (2024) 全量资料快照到本地 data/raw/ , 之后离线可用"""
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://www.dnd5eapi.co/api/2024/"
FORCE = "--force" in sys.argv      # 默认命中本地缓存就不联网
OUT = r"E:\workbuddycache\test1\data\raw"

# 分类 -> 是否需要逐条抓详情
CATS = {
    "spells": True, "classes": True, "subclasses": True, "races": True,
    "backgrounds": True, "feats": True, "equipment": True,
    "magic-items": True, "conditions": False, "skills": False,
    "ability-scores": False, "languages": False, "damage-types": False,
    "weapon-properties": False, "equipment-categories": False,
    "magic-schools": False, "proficiencies": False,
}


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def snapshot(cat, details):
    path = os.path.join(OUT, cat + ".json")
    if not FORCE and os.path.exists(path) and os.path.getsize(path) > 500:
        try:
            n = len(json.load(open(path, encoding="utf-8"))["items"])
            return cat, n, "cached"
        except Exception:
            pass
    try:
        lst = get(BASE + cat + "/?limit=2000")
    except urllib.error.HTTPError as e:
        return cat, 0, f"HTTP {e.code}"
    items = lst.get("results", [])
    data = {"count": len(items), "items": []}
    if not details:
        for it in items:
            try:
                data["items"].append(get(BASE + cat + "/" + it["index"]))
            except Exception:
                data["items"].append(it)
    else:
        def one(it):
            try:
                return get(BASE + cat + "/" + it["index"])
            except Exception:
                return it
        with ThreadPoolExecutor(max_workers=8) as ex:
            data["items"] = list(ex.map(one, items))
    json.dump(data, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return cat, len(data["items"]), "ok"


def main():
    os.makedirs(OUT, exist_ok=True)
    for cat, det in CATS.items():
        try:
            c, n, st = snapshot(cat, det)
            print(f"{c:22s} {n:4d}  {st}")
        except Exception as e:
            print(f"{cat:22s} ERR {type(e).__name__}: {str(e)[:80]}")
    # 职业逐级数据 (等级表/特性)
    lv_path = os.path.join(OUT, "class-levels.json")
    if not FORCE and os.path.exists(lv_path) and os.path.getsize(lv_path) > 500:
        print("class-levels.json cached")
        return
    try:
        cls = json.load(open(os.path.join(OUT, "classes.json"),
                             encoding="utf-8"))["items"]
        levels = {}
        for c in cls:
            idx = c.get("index")
            if not idx:
                continue
            try:
                levels[idx] = {
                    "levels": get(f"{BASE}classes/{idx}/levels"),
                    "features": get(f"{BASE}classes/{idx}/features"),
                }
            except Exception as e:
                levels[idx] = {"error": str(e)[:80]}
        json.dump(levels, open(os.path.join(OUT, "class-levels.json"), "w",
                               encoding="utf-8"), ensure_ascii=False, indent=1)
        print("class-levels.json", len(levels), "classes")
    except Exception as e:
        print("class-levels ERR", e)


if __name__ == "__main__":
    main()
