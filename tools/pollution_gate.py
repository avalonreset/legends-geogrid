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
import argparse, base64, json, os, re, sys, urllib.error, urllib.request
from local_heatmap_poc import extract_items, organic_maps_items

ENDPOINT = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
LIVE_COST_PER_POINT_USD = 0.002


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"Redirects not allowed ({msg})", headers, fp)


def post(payload, login, password):
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Basic " + token, "Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    with opener.open(req, timeout=110) as r:
        raw = r.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("DataForSEO response exceeds 5 MB safety limit")
    return json.loads(raw.decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--points", required=True, help="lat,lng;lat,lng;...")
    ap.add_argument("--category", required=True, help="regex: must-match titles")
    ap.add_argument("--banned", default="", help="regex: instant-fail titles")
    ap.add_argument("--depth", type=int, default=20)
    ap.add_argument("--execute", action="store_true", help="Execute live paid DataForSEO calls")
    ap.add_argument("--confirm-cost-usd", type=float, default=None, help="Maximum approved USD spend")
    a = ap.parse_args()
    cat = re.compile(a.category, re.I)
    ban = re.compile(a.banned, re.I) if a.banned else None
    pts = [p.split(",") for p in a.points.split(";") if p.strip()]
    estimated_usd = round(len(pts) * LIVE_COST_PER_POINT_USD, 4)
    if not a.execute:
        print(json.dumps({
            "status": "dry_run_preview",
            "keyword": a.keyword,
            "points": len(pts),
            "estimated_cost_usd": estimated_usd,
            "note": f"Pass --execute --confirm-cost-usd {estimated_usd:.4f} to run live probes.",
        }, indent=2))
        return 2
    if a.confirm_cost_usd is None or a.confirm_cost_usd < estimated_usd:
        sys.exit(f"--execute requires --confirm-cost-usd >= {estimated_usd:.4f}")
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        sys.exit("DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD must be set in the environment")
    fails = []
    for lat, lng in pts:
        d = post([{"keyword": a.keyword, "location_coordinate": f"{lat},{lng}",
                   "language_code": "en", "device": "desktop", "depth": a.depth}],
                 login, password)
        task = (d.get("tasks") or [{}])[0]
        items, error = extract_items(task)
        if d.get("status_code") != 20000 or error:
            fails.append((f"{lat},{lng}", "Provider failure or missing successful response"))
            continue
        items = organic_maps_items(items)
        if not items:
            fails.append((f"{lat},{lng}", "No organic results; query relevance is unverified"))
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
