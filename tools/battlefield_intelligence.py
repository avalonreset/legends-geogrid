"""Offline, auditable geographic investigation clusters from a companion study.

These are measured ranking bands, never a demand, difficulty, or revenue score.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import html
import json
import math
from pathlib import Path
import statistics
from urllib.parse import urlencode

from radius_sampling import MILE_KM, radial_origins

BANDS = ("top3", "near_top3", "development", "not_top30", "unknown")
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def profile_key(item):
    if item.get("cid"):
        return "cid:" + str(item["cid"])
    if item.get("place_id"):
        return "place:" + str(item["place_id"])
    return None


def components(keys):
    remaining = set(keys)
    result = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        stack, group = [seed], []
        while stack:
            point = stack.pop()
            group.append(point)
            for dx, dy in STEPS:
                nxt = (point[0] + dx, point[1] + dy)
                if nxt in remaining:
                    remaining.remove(nxt)
                    stack.append(nxt)
        result.append(sorted(group))
    return sorted(result, key=lambda group: (-len(group), group[0]))


def classify(observation, target_key):
    """Require full identity-bearing ranks 1-30 before classifying a cell."""
    if not observation or observation.get("status") not in ("found", "not_returned_depth_reached"):
        return "unknown", None, []
    items = observation.get("top_items") or []
    ranked = [item for item in items if isinstance(item.get("rank"), int)
              and not isinstance(item["rank"], bool) and 1 <= item["rank"] <= 30]
    keys = [profile_key(item) for item in ranked]
    complete = (sorted(item["rank"] for item in ranked) == list(range(1, 31))
                and None not in keys and len(set(keys)) == 30)
    if not complete:
        return "unknown", None, []
    ranks = [item["rank"] for item in ranked if profile_key(item) == target_key]
    rank = ranks[0] if ranks else None
    # A contradictory exported target rank is a data-quality fault, not absence.
    if observation.get("target_rank") != rank:
        return "unknown", None, []
    if rank is None:
        return "not_top30", None, ranked
    return ("top3" if rank <= 3 else "near_top3" if rank <= 10 else "development"), rank, ranked


def analyze(study, source_study=None):
    sampling = study.get("study", {}).get("sampling", {})
    if sampling.get("geometry") != "radius_grid":
        raise ValueError("Geographic analysis requires a declared regular radius_grid")
    center = sampling["center"]
    spacing = sampling["spacing_km"]
    expected = radial_origins(center["lat"], center["lng"], sampling["radius_km"] / MILE_KM, spacing / MILE_KM)
    grid = {(p["grid_x"], p["grid_y"]): p for p in expected}
    actual = {}
    step = spacing / 111.195
    for point in study["points"]:
        key = (round((point["lng"] - center["lng"]) * math.cos(math.radians(center["lat"])) / step),
               round((point["lat"] - center["lat"]) / step))
        if key not in grid or abs(point["lat"] - grid[key]["lat"]) > 0.000001 or abs(point["lng"] - grid[key]["lng"]) > 0.000001:
            raise ValueError("Observation does not match the declared circular lattice")
        if key in actual:
            raise ValueError("Duplicate observation coordinate")
        actual[key] = point
    target_key = profile_key(study["target"])
    if not target_key:
        raise ValueError("Primary profile requires CID or place ID")
    query_ids = [lane["lane_id"] for lane in study["lanes"]]
    if len(query_ids) != len(set(query_ids)) or not query_ids:
        raise ValueError("Distinct nonempty query identifiers required")
    classified = {q: {k: classify(actual.get(k, {}).get("by_lane", {}).get(q), target_key) for k in grid} for q in query_ids}
    metadata = {}
    for points in classified.values():
        for _, _, items in points.values():
            for item in items:
                metadata.setdefault(profile_key(item), item)
    def rivals(counts):
        return [{"profile_key": key, "name": metadata[key].get("title"), "address": metadata[key].get("address"), "count": count}
                for key, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]
    def summary(keys, q):
        ranks, leaders, ahead = [], Counter(), Counter()
        for key in keys:
            _, rank, items = classified[q][key]
            if rank is not None:
                ranks.append(rank)
            for item in items:
                identity = profile_key(item)
                if item["rank"] == 1:
                    leaders[identity] += 1
                if rank is not None and item["rank"] < rank:
                    ahead[identity] += 1
        lat = statistics.mean(grid[k]["lat"] for k in keys)
        lng = statistics.mean(grid[k]["lng"] for k in keys)
        representative = min(keys, key=lambda k: ((grid[k]["lat"]-lat)**2 + ((grid[k]["lng"]-lng)*math.cos(math.radians(lat)))**2, k))
        source = actual.get(representative, grid[representative])
        tag = source.get("tag", source.get("origin_id"))
        members = set(keys)
        adjacent = {(x+dx, y+dy) for x,y in keys for dx,dy in STEPS
                    if (x+dx,y+dy) in grid and (x+dx,y+dy) not in members
                    and classified[q][(x+dx,y+dy)][0] == "top3"}
        link_args = {"query": q, "point": tag, "business": "TARGET", "view": "visibility"}
        if source_study:
            normalized = source_study.replace("\\", "/")
            if "/runs/" in normalized:
                normalized = "/runs/" + normalized.split("/runs/", 1)[1]
            elif normalized.startswith("runs/"):
                normalized = "/" + normalized
            link_args["study"] = normalized
        return {"origin_count": len(keys), "median_observed_rank": statistics.median(ranks) if ranks else None,
                "centroid": {"lat": lat, "lng": lng},
                "offset_miles": {"east": statistics.mean(k[0] for k in keys)*spacing/MILE_KM,
                                 "north": statistics.mean(k[1] for k in keys)*spacing/MILE_KM},
                "distance_miles": {"min": min(grid[k]["distance_from_target_km"] for k in keys)/MILE_KM,
                                   "max": max(grid[k]["distance_from_target_km"] for k in keys)/MILE_KM},
                "representative": {"tag": tag, "lat": source["lat"], "lng": source["lng"]},
                "coordinate_link": "https://www.openstreetmap.org/?" + urlencode({"mlat": source["lat"], "mlon": source["lng"]}),
                "viewer_link": "/?" + urlencode(link_args),
                "adjacent_top3_origins": len(adjacent), "leaders": rivals(leaders), "profiles_ahead": rivals(ahead),
                "cross_query_top3_counts": {other: sum(classified[other][k][0]=="top3" for k in keys) for other in query_ids},
                "origin_tags": [actual.get(k, {}).get("tag", grid[k]["origin_id"]) for k in keys]}
    queries = []
    aggregate_ahead, aggregate_winners = Counter(), Counter()
    for lane in study["lanes"]:
        q = lane["lane_id"]
        counts = Counter(value[0] for value in classified[q].values())
        groups = {band: [summary(group, q) for group in components(k for k, value in classified[q].items() if value[0] == band)]
                  for band in BANDS[:-1]}
        for key, (band, rank, items) in classified[q].items():
            if band == "near_top3":
                for item in items:
                    if item["rank"] < rank:
                        aggregate_ahead[profile_key(item)] += 1
                    if item["rank"] == 1:
                        aggregate_winners[profile_key(item)] += 1
        queries.append({"query_id": q, "query": lane["query"], "expected_origins": len(grid),
                        "complete_origins": len(grid)-counts["unknown"], "counts": {band: counts[band] for band in BANDS},
                        "components": groups})
    threshold = min(3, len(query_ids))
    shared = [k for k in grid if sum(classified[q][k][0] == "near_top3" for q in query_ids) >= threshold]
    return {"schema": "geogrid-battlefield-intelligence/v1", "primary": study["target"],
            "source": {"study": source_study, "generated_at": study.get("generated_at"), "evidence": study.get("evidence"),
                       "controls": study.get("study", {}).get("controls")},
            "method": {"adjacency": "Four orthogonal lattice neighbors; no diagonal joins, interpolation, or filled territory",
                       "bands": {"top3": "1-3", "near_top3": "4-10", "development": "11-30", "not_top30": "Absent in complete top30; exact rank unknown", "unknown": "Missing, incomplete, contradictory, or pending evidence"},
                       "component_order": "Origin count descending, then lattice coordinate; not commercial priority",
                       "limitations": "Single snapshot. No demand, revenue, ease, ranking cause, or commercial service area inferred. Profiles retain distinct IDs. Counts are origins, not customers."},
            "expected_origins": len(grid), "missing_origins": len(grid)-len(actual), "queries": queries,
            "near_top3_pairs": sum(q["counts"]["near_top3"] for q in queries),
            "near_top3_rivals": [{**r, "first_place_count": aggregate_winners[r["profile_key"]]} for r in rivals(aggregate_ahead)],
            "cross_query_focus": {"minimum_near_top3_queries": threshold, "origin_count": len(shared),
                                  "components": [[{"tag": actual[k]["tag"], "lat": actual[k]["lat"], "lng": actual[k]["lng"],
                                                   "ranks": {q: classified[q][k][1] for q in query_ids},
                                                   "bands": {q: classified[q][k][0] for q in query_ids}} for k in group] for group in components(shared)]}}


def escape(value):
    text = html.escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    for character in ("\\", "|", "[", "]", "*", "_", "`", "#"):
        text = text.replace(character, "\\" + character)
    return text


def markdown(report):
    lines = ["# Measured geographic investigation areas", "", escape(report["primary"]["name"]), "",
             report["method"]["limitations"], "", "Components connect orthogonal neighboring samples only. Their order is size, not commercial priority.", "",
             "| Query | Top 3 | Ranks 4-10 | Ranks 11-30 | Outside top 30 | Unknown |", "|---|---:|---:|---:|---:|---:|"]
    for query in report["queries"]:
        lines.append("| " + escape(query["query"]) + " | " + " | ".join(str(query["counts"][band]) for band in BANDS) + " |")
    for query in report["queries"]:
        lines.extend(["", "## " + escape(query["query"]), ""])
        for component in query["components"]["near_top3"]:
            p = component["representative"]
            lines.append(f"- {component['origin_count']} contiguous ranks 4-10; median rank {component['median_observed_rank']}; "
                         f"{component['distance_miles']['min']:.2f}-{component['distance_miles']['max']:.2f} miles from primary. "
                         f"Representative [{escape(p['tag'])}]({component['coordinate_link']}) "
                         f"({p['lat']:.6f}, {p['lng']:.6f}); [open in viewer]({component['viewer_link']}).")
            lines.append("  First-place profiles: " + "; ".join(f"{escape(r['name'])} ({escape(r['address'] or 'address not supplied')}): {r['count']}" for r in component["leaders"][:5]) + ".")
    focus = report["cross_query_focus"]
    points = [point for group in focus["components"] for point in group]
    query_ids = [query["query_id"] for query in report["queries"]]
    all_queries = sum(all(point["bands"][q] == "near_top3" for q in query_ids) for point in points)
    lines.extend(["", "## Shared investigation locations", "",
                  f"{focus['origin_count']} origins rank 4-10 on at least {focus['minimum_near_top3_queries']} queries "
                  f"(threshold: min(3, number of studied queries)); {all_queries} rank 4-10 on every studied query. "
                  "This is a descriptive cross-query filter, not an opportunity score.", "",
                  "Existing top-three coverage within these locations: " +
                  "; ".join(f"{escape(query['query'])}: {sum(point['bands'][query['query_id']]=='top3' for point in points)}"
                            for query in report["queries"]) + ".", "",
                  "| Origin | Coordinates | " + " | ".join(escape(query["query"]) for query in report["queries"]) + " |",
                  "|---|---|" + "---:|"*len(query_ids)])
    for point in points:
        link = "https://www.openstreetmap.org/?" + urlencode({"mlat": point["lat"], "mlon": point["lng"]})
        ranks = [str(point["ranks"][q]) if point["ranks"][q] is not None else
                 ("Outside top 30" if point["bands"][q] == "not_top30" else "Unknown") for q in query_ids]
        lines.append(f"| [{escape(point['tag'])}]({link}) | {point['lat']:.6f}, {point['lng']:.6f} | " + " | ".join(ranks) + " |")
    lines.extend(["", "## Rivals across near-top-three observations", "", f"Denominator: {report['near_top3_pairs']} location/query pairs. Queries are counted separately, not independent customers.", ""])
    for rival in report["near_top3_rivals"][:15]:
        lines.append(f"- {escape(rival['name'])} ({escape(rival['address'] or 'address not supplied')}): ahead in {rival['count']}; first in {rival['first_place_count']}.")
    lines.extend(["", "Next decisions require service relevance, operating reach and demand evidence. Repeat measurements before interpreting stability or change.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = args.study.read_bytes()
    report = analyze(json.loads(payload), str(args.study))
    report["source"]["sha256"] = hashlib.sha256(payload).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "battlefield-intelligence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.output_dir / "battlefield-intelligence.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"expected_origins": report["expected_origins"], "missing_origins": report["missing_origins"], "near_top3_pairs": report["near_top3_pairs"], "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
