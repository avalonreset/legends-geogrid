#!/usr/bin/env python3
"""Export measured competitive observations for the companion, without tactical scores."""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import math
from pathlib import Path
import re

from competitive_sampling import haversine_km
from study_contract import digest


def export_study(run_dir: Path, radius_miles: float | None = None) -> dict:
    if radius_miles is not None and (not math.isfinite(radius_miles) or radius_miles <= 0):
        raise ValueError("Radius must be finite and positive")
    plan_path = run_dir / "competitive-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    config = json.loads((run_dir / "report-config.json").read_text(encoding="utf-8"))
    receipt = json.loads((run_dir / "collection-summary.json").read_text(encoding="utf-8"))
    if receipt["plan_sha256"] != digest(plan_path):
        raise ValueError("Plan changed after collection")
    source_roster = [plan["target_business"], *plan["rival_factions_roster"]]
    factions = [{
        "faction_id": f["faction_id"], "name": f["name"],
        "is_target": f["faction_id"] == "TARGET",
        "cid": f.get("cid"), "place_id": f.get("place_id"), "domain": f.get("domain"),
        "lat": f.get("lat"), "lng": f.get("lng"),
        "location_estimated": f.get("location_status") != "verified",
        # Old review counts are intentionally not presented as fresh measurements.
    } for f in source_roster]
    target = factions[0]
    sampling = dict(plan.get("sampling_parameters", {}))
    geometry = sampling.get("geometry", "competitive_irregular")
    selected_tags = None
    if radius_miles is not None:
        from radius_sampling import radial_origins, MILE_KM
        if geometry != "square_grid" or not sampling.get("spacing_km"):
            raise ValueError("Radius export requires a measured regular grid with recorded spacing")
        expected = radial_origins(target["lat"], target["lng"], radius_miles, sampling["spacing_km"] / MILE_KM)
        available = {(o["lat"], o["lng"]): o["origin_id"] for o in plan["origins"]}
        missing = [o for o in expected if (o["lat"], o["lng"]) not in available]
        if missing:
            raise ValueError(f"Radius has {len(missing)} unmeasured locations; collect them before export")
        selected_tags = {available[(o["lat"], o["lng"])] for o in expected}
        geometry = "radius_grid"
        sampling = {"geometry": geometry, "radius_km": radius_miles * MILE_KM,
            "spacing_km": sampling["spacing_km"], "center": {"lat": target["lat"], "lng": target["lng"]},
            "description": f"{radius_miles * MILE_KM:g} km radius · {sampling['spacing_km']:g} km spacing",
            "rationale": "Regular lattice clipped by geodesic distance from the primary profile. Every selected origin measured for every query; no square corners outside the requested radius."}

    def identity(item):
        matches = []
        for f in factions:
            if item.get("cid") and f.get("cid") and str(item["cid"]) != str(f["cid"]):
                continue
            if item.get("place_id") and f.get("place_id") and item["place_id"] != f["place_id"]:
                continue
            if ((item.get("cid") and str(item["cid"]) == str(f.get("cid")))
                    or (item.get("place_id") and item["place_id"] == f.get("place_id"))):
                matches.append(f["faction_id"])
        return matches[0] if len(matches) == 1 else None

    origins = {o["origin_id"]: o for o in plan["origins"]}
    points, lanes, timestamps, controls = {}, [], [], []
    top3_counts, profiles, visibility_scores, appearances = Counter(), {}, Counter(), Counter()
    categories, query_scores, examples = {}, {}, {}
    for lane in config["lanes"]:
        parsed = json.loads((run_dir / lane["records_path"]).read_text(encoding="utf-8"))
        controls.append(parsed["measurement_settings"])
        qid = lane["query_id"]
        lanes.append({"lane_id": qid, "query": lane["query"]})
        for result in parsed["results"]:
            raw_point = result["point"]
            tag = raw_point["tag"]
            if selected_tags is not None and tag not in selected_tags:
                continue
            source = origins[tag]
            point = points.setdefault(tag, {
                "tag": tag, "lat": raw_point["lat"], "lng": raw_point["lng"],
                "distance_from_target_km": haversine_km(target["lat"], target["lng"], raw_point["lat"], raw_point["lng"]),
                "roles": source.get("roles", []), "phase": source.get("phase"),
                "anchor_factions": source.get("anchor_factions", []), "by_lane": {},
            })
            items, seen = [], set()
            for item in result["top_items"]:
                rank = item.get("rank_group")
                if not isinstance(rank, int) or rank < 1:
                    continue
                cid = str(item.get("cid") or "")
                if cid and rank <= 20 and cid not in seen:
                    seen.add(cid)
                    profiles[cid] = item
                    visibility_scores[cid] += 21 - rank
                    appearances[cid] += 1
                    query_scores.setdefault(cid, Counter())[qid] += 21 - rank
                    if item.get("category"):
                        categories.setdefault(cid, set()).add(item["category"])
                    if len(examples.setdefault(cid, [])) < 4:
                        examples[cid].append({"records_path": lane["records_path"], "origin": tag, "query_id": qid, "rank": rank})
                    if rank <= 3:
                        top3_counts[cid] += 1
                rating = item.get("rating") or {}
                items.append({
                    "title": item.get("title"), "rank": rank,
                    "address": item.get("address"),
                    "latitude": item.get("latitude"), "longitude": item.get("longitude"),
                    "cid": item.get("cid"), "place_id": item.get("place_id"),
                    "faction_id": identity(item), "rating": rating.get("value") if isinstance(rating, dict) else rating,
                    "votes_count": rating.get("votes_count") if isinstance(rating, dict) else item.get("votes_count"),
                })
            stamp = result.get("sampled_at")
            if stamp:
                timestamps.append(stamp)
            point["by_lane"][qid] = {
                "target_rank": result["rank"], "status": result["status"],
                "sampled_at": stamp, "top_items": items,
                "observed_ranks": result["observed_ranks"],
                **({"provenance": result["provenance"]} if result.get("provenance") else {}),
            }
    if (selected_tags is not None and set(points) != selected_tags) or any(len(p["by_lane"]) != len(lanes) for p in points.values()):
        raise ValueError("Lanes do not cover the same origins")
    known_by_cid = {str(f.get("cid")): f for f in factions}
    category_pattern = plan.get("competitor_policy", {}).get("eligible_category_pattern")
    eligible = [cid for cid in visibility_scores if cid != str(target.get("cid"))
                and (not category_pattern or any(re.search(category_pattern, category) for category in categories.get(cid, [])))]
    leaders = sorted(eligible, key=lambda cid: (-visibility_scores[cid], -top3_counts[cid], -appearances[cid], cid))[:9]
    factions = [target]
    for number, cid in enumerate(leaders, 1):
        profile = profiles[cid]
        faction = dict(known_by_cid.get(cid) or {
            "faction_id": f"cid:{cid}",
            "name": profile["title"], "is_target": False, "cid": cid,
            "place_id": profile.get("place_id"), "domain": profile.get("domain"),
            "lat": profile.get("latitude"), "lng": profile.get("longitude"),
            "location_estimated": profile.get("latitude") is None or profile.get("longitude") is None,
            "discovered": True,
        })
        faction["selection"] = {
            "position": number, "visibility_score": visibility_scores[cid],
            "top3_appearances": top3_counts[cid], "appearances": appearances[cid],
            "score_by_query": dict(query_scores[cid]), "categories": sorted(categories.get(cid, [])),
            "evidence_examples": examples[cid],
        }
        factions.append(faction)
    # Shortlisting changes display identities only. Preserve all returned listings.
    for point in points.values():
        for observation in point["by_lane"].values():
            for item in observation["top_items"]:
                item["faction_id"] = identity(item)
    for faction in factions:
        profile = profiles.get(str(faction.get("cid")))
        if profile:
            faction.update(rating=profile.get("rating"), votes_count=profile.get("votes_count"), address=profile.get("address"))
    return {
        "schema": "geogrid-companion/v1", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "business": config["business"], "target": target,
        "location": config["business"].get("location"),
        "factions": factions, "lanes": lanes, "points": list(points.values()),
        "study": {"geometry": geometry,
                  "sampling": sampling,
                  "depth": plan["measurement_settings"]["depth"],
                  "total_points": len(points), "controls": plan["measurement_settings"]},
        "collection_policy": plan.get("collection_policy"),
        "evidence": {
            "observed_from": min(timestamps) if timestamps else None,
            "observed_to": max(timestamps) if timestamps else None,
            "observations_with_timestamp": len(timestamps), "total_observations": len(points) * len(lanes),
            "run_total_cost_usd": receipt.get("run_total_cost_usd"),
            "source_total_observations": receipt.get("composition", {}).get("source_total_observations", receipt["total_tasks"]),
            "view_equivalent_scan_cost_usd": None if receipt.get("composition") else round((receipt.get("run_total_cost_usd") or 0) * len(points) * len(lanes) / receipt["total_tasks"], 6),
            "export_is_subset": radius_miles is not None,
            "plan_sha256": receipt["plan_sha256"], "source_query_plan": plan["source_study_plan"],
            "roster_policy": "Primary Google Business Profile plus nine competing profiles. Separate locations remain separate competitors even when names and websites match. Rank-weighted visibility sums 21 minus organic rank (ranks 1–20) over all origins and queries equally. Ties: top-three appearances, then appearances, then CID. The roster stays fixed across queries. " + (
                "Eligibility follows the service-category filter recorded in the study plan. " if category_pattern else ""
            ) + "All returned listings through the requested depth remain available in location evidence. This measures visibility on this footprint, not revenue or market share.",
            "roster_limit": 9,
            "eligible_rivals": len(eligible),
            "shortlist_complete": len(leaders) == 9,
            "initial_rivals": len(source_roster) - 1,
            "emerging_rivals": sum(bool(f.get("discovered")) for f in factions),
            "boundary_policy": "Discrete measured locations. No continuous market boundary or customer-demand estimate.",
            **({"composition": receipt["composition"]} if receipt.get("composition") else {}),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--radius-miles", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.radius_miles is not None and args.output is None:
        parser.error("--radius-miles requires a separate --output to preserve the source archive")
    model = export_study(args.run_dir, args.radius_miles)
    output = args.output or args.run_dir / "companion-study.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "points": len(model["points"]), "queries": len(model["lanes"]), "evidence": model["evidence"]}, indent=2))


if __name__ == "__main__":
    main()
