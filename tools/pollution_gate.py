#!/usr/bin/env python3
"""Pollution gate (formula gate 2): probe a keyword at spread points before grid spend.

Usage:
  python3 tools/pollution_gate.py --keyword "furnace repair sacramento" \
      --points "38.8046,-121.4658;38.7246,-121.3658;38.6446,-121.2658;38.4846,-121.0658" \
      --category "hvac|heating|cooling|furnace|air cond|mechanical|comfort|climate" \
      --banned "auto|collision|smog|tire|oil change" \
      --depth 20

Exit 0 with PASS when every probe point returns only in-category results.
Exit 1 with FAIL naming the offending business and point otherwise.
Credentials: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD in the environment.
Costs ~$0.002 per probe on the Live endpoint (or use the repo bulk runner's
standard queue for ~$0.0006 per probe on large batches).
"""
import argparse, base64, json, re, sys, urllib.request

ENDPOINT = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"


def post(payload, login, password):
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Basic " + token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=110) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--points", required=True, help="lat,lng;lat,lng;...")
    ap.add_argument("--category", required=True, help="regex: must-match titles")
    ap.add_argument("--banned", default="", help="regex: instant-fail titles")
    ap.add_argument("--depth", type=int, default=20)
    a = ap.parse_args()
    import os
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        sys.exit("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set in the environment")
    cat = re.compile(a.category, re.I)
    ban = re.compile(a.banned, re.I) if a.banned else None
    pts = [p.split(",") for p in a.points.split(";")]
    fails = []
    for lat, lng in pts:
        d = post([{"keyword": a.keyword, "location_coordinate": f"{lat},{lng}",
                   "language_code": "en", "device": "desktop", "depth": a.depth}],
                 login, password)
        task = (d.get("tasks") or [{}])[0]
        status = task.get("status_code")
        items = ((task.get("result") or [{}])[0].get("items")) or []
        if status == 40102 or not items:
            print(f"point {lat},{lng}: no pack (dead geography candidate)")
            continue
        for it in items:
            t = it.get("title") or ""
            if (ban and ban.search(t)) or not cat.search(t):
                fails.append((f"{lat},{lng}", t))
        print(f"point {lat},{lng}: {len(items)} results checked")
    if fails:
        print("FAIL:")
        for pt, t in fails:
            print(f"  {pt}: {t}")
        return 1
    print(f"PASS: {a.keyword}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
