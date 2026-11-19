#!/usr/bin/env python3
"""Generate examples/viewer-companion-depth100-fixture.json.

A synthetic geogrid-companion/v1 study for the embedded report viewer: a 7 by 7 grid, one search,
up to 100 ranked listings per point, opaque competitor keys and no provider identifiers. Everything
is invented (fictional names, fixed seed), so the output is byte for byte reproducible.

    python scripts/make_viewer_depth_fixture.py            # write the fixture
    python scripts/make_viewer_depth_fixture.py --check    # exit 1 if the file on disk differs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "viewer-companion-depth100-fixture.json"

CENTER = (30.2672, -97.7431)
GRID = 7
SPACING_KM = 1.0
DEPTH = 100
SCORE_WINDOW = 20
TARGET_KEY = "biz-0"
POOL = 180

FIRST = ["Harbor", "Lone Star", "Capital", "Oak Hill", "Riverbend", "Blue Heron", "Summit", "Copper", "Cedar", "Mesa",
         "Bluebonnet", "Prairie", "Granite", "Willow", "Sterling", "Pioneer", "Lakeside", "Ironwood", "Maple", "Falcon"]
SECOND = ["Pipe & Drain", "Plumbing", "Rooter", "Water Works", "Plumbing Pros", "Drain Care", "Pipe Masters",
          "Mechanical", "Leak Busters", "Flow Services", "Plumbing & Heating", "Sewer & Drain"]
CATEGORIES = ["Plumber", "Emergency plumber", "Drainage service", "Water heater installer", "Plumbing supply store"]


def key_for(index: int) -> str:
    return "k-" + hashlib.sha1(f"viewer-fixture-{index}".encode()).hexdigest()[:8]


def build() -> dict:
    rng = random.Random(29)
    names, seen = [], set()
    while len(names) < POOL:
        name = f"{rng.choice(FIRST)} {rng.choice(SECOND)}"
        if name not in seen:
            seen.add(name)
            names.append(name)
    keys = [key_for(i) for i in range(POOL)]
    weights = [1.0 / (i + 4) ** 0.85 for i in range(POOL)]
    profiles = {
        keys[i]: {
            "title": names[i],
            "rating": round(rng.uniform(3.6, 5.0), 1),
            "votes_count": rng.randint(8, 950),
            "category": rng.choice(CATEGORIES),
        }
        for i in range(POOL)
    }

    km_lat = 110.574
    km_lng = 111.320 * math.cos(math.radians(CENTER[0]))
    half = (GRID - 1) / 2
    points = []
    found_ranks = []
    for row in range(GRID):
        for col in range(GRID):
            dy, dx = (row - half) * SPACING_KM, (col - half) * SPACING_KM
            lat, lng = CENTER[0] + dy / km_lat, CENTER[1] + dx / km_lng
            dist = math.hypot(dx, dy)
            tag = f"p_{row:02d}_{col:02d}"
            captured = DEPTH
            # The business ranks well near its base and falls away with distance.
            wanted = round(1 + dist * 5.2 + rng.gauss(0, 2.6))
            target_rank = max(1, wanted)
            if tag == "p_00_00":
                target_rank = None            # not in the captured 100
            elif tag == "p_00_03":
                target_rank = 37              # beyond the default top 20
            elif tag == "p_06_06":
                target_rank, captured = 14, 20  # a shallow capture: top 20 only, no expander
            elif target_rank > 62:
                target_rank = None
            # Competitor order: popularity plus noise (Gumbel), best first.
            order = sorted(range(POOL), key=lambda i: -(math.log(weights[i]) - math.log(-math.log(max(rng.random(), 1e-12)))))
            picked = order[: captured - (1 if target_rank and target_rank <= captured else 0)]
            slots = [r for r in range(1, captured + 1) if r != target_rank]
            items = [{"faction_id": keys[i], "rank": slots[n]} for n, i in enumerate(picked)]
            if target_rank and target_rank <= captured:
                items.append({"faction_id": TARGET_KEY, "rank": target_rank})
            items.sort(key=lambda it: it["rank"])
            status = "found" if target_rank else ("not_returned_depth_reached" if captured == DEPTH else "not_returned_sample")
            if target_rank:
                found_ranks.append(target_rank)
            points.append({
                "tag": tag, "lat": round(lat, 6), "lng": round(lng, 6),
                "distance_from_target_km": round(dist, 3), "roles": ["square_grid"], "phase": 1, "anchor_factions": [],
                "by_lane": {"q1": {"target_rank": target_rank, "status": status, "sampled_at": "2026-11-19T15:00:00Z", "top_items": items}},
            })

    total = len(points)
    within = [r for r in found_ranks if r <= SCORE_WINDOW]
    scores = {
        "found_share": round(len(within) / total, 4),
        "top3_share": round(len([r for r in within if r <= 3]) / total, 4),
        "avg_rank": round(sum(within) / len(within), 2) if within else None,
    }
    return {
        "schema": "geogrid-companion/v1",
        "generated_at": "2026-11-19T15:00:00Z",
        "business": {"name": "Example Plumbing Co"},
        "location": "Austin, TX",
        "factions": [{
            "faction_id": TARGET_KEY, "name": "Example Plumbing Co", "is_target": True,
            "lat": CENTER[0], "lng": CENTER[1], "location_estimated": False,
            "rating": 4.8, "votes_count": 412, "category": "Plumber", "address": "100 Example Street, Austin, TX",
        }],
        "profiles": profiles,
        "lanes": [{"lane_id": "q1", "query": "emergency plumber", "scores": scores}],
        "points": points,
        "study": {
            "geometry": "square_grid", "depth": DEPTH, "score_window": SCORE_WINDOW,
            "sampling": {"geometry": "square_grid", "spacing_km": SPACING_KM, "center": {"lat": CENTER[0], "lng": CENTER[1]},
                         "description": f"{GRID} by {GRID} grid, {SPACING_KM:g} km spacing"},
            "controls": {"method": "standard", "depth": DEPTH, "device": "mobile"},
        },
        "evidence": {"observed_from": "2026-11-19T15:00:00Z", "observed_to": "2026-11-19T15:30:00Z"},
    }


def render() -> str:
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the file on disk is not what this script produces")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8").replace("\r\n", "\n") if OUT.exists() else None
        if current != text:
            print(f"{OUT.name} is out of date; run this script to regenerate it", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
