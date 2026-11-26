"""Turn a saved hex-ladder run into geogrid-companion/v1 honeycomb studies.

Reads saved results only. It never searches and never makes a paid call.

usage:
    python scripts/hex_to_companion.py runs/<run> [--location "City, ST area"]
        [--rivals 9] [--no-current] [--detail-views]

Input: <run_dir>/grid/grid_points.json with
    center   {lat, lng, name, cid}                 the business (layer 0)
    settings {zoom, depth, device}
    s0       main honeycomb spacing in miles (optional; else the coarsest spacing)
    radius   {phrase: miles}                       how far each phrase was measured
    study_radius  R in miles (optional; else the largest radius). The circle contract:
             every base-lattice point within R is measured for every phrase and
             nothing outside R is ever searched. Points beyond R that an older run
             already paid for stay in the raw grid file but are dropped from the study.
    phrases  {phrase: [point, ...]} where each point has
             id, lat, lng, east, north (miles from the business),
             unit_q, unit_r (lattice coordinates in finest units), spacing, role,
             status ("ok" or other), rank (int or null), top [[pos, name, cid,
             rating, reviews, lat, lng], ...], instrument_limited (optional bool:
             not found while the business lies outside the search screen)
    Roles: coarse, expand, fill sit on the s0 lattice; "refine_<miles>" points are
    nested rungs inside it.

Output: the main view merges every rung into one study, each point tagged with its
rung (hex.rung_miles), so refinement reads inside the circle, not as islands:
    <run_dir>/companion/view-<s0>/companion-study.json
    runs/current-study.json pointing at the main view (unless --no-current)
A not-found point flagged instrument_limited exports as status "instrument_limited"
(drawn as "can't see from here", never a loss). Edge signal: when the business is top 3
at >= 50% of the scored points on the outermost s0 ring inside R (distance > R - s0),
study.edge_signal[lane].extends is true and the companion summary says the territory
likely extends past R and offers growing the circle as a new, explicit paid study.
--detail-views also writes the older one-spacing detail views (view-<miles> per refine
rung), listed in study_views for the "Study footprint" picker.
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from study import _safe_local_path

EDGE_SHARE = 0.5     # top-3 share of the outermost ring that signals "extends past R"
EDGE_MIN_SCORED = 3  # fewer scored ring points: the edge is unread, no signal

KM_PER_MI = 1.609344


def lattice_unit(points):
    """Miles per finest lattice unit, fitted from east = (q + r/2) u, north = r (sqrt3/2) u."""
    num = den = 0.0
    for p in points:
        x, y = p["unit_q"] + p["unit_r"] / 2, p["unit_r"] * math.sqrt(3) / 2
        num += x * p["east"] + y * p["north"]
        den += x * x + y * y
    if not den:
        raise SystemExit("cannot fit the lattice unit: every point sits at the origin")
    unit = num / den
    for p in points:
        err = math.hypot((p["unit_q"] + p["unit_r"] / 2) * unit - p["east"], p["unit_r"] * math.sqrt(3) / 2 * unit - p["north"])
        if err > 0.02 * unit + 1e-6:
            raise SystemExit(f"point {p['id']} is off the hex lattice by {err:.4f} mi")
    return unit


def miles_label(miles):
    label = f"{miles:g}"
    return label if "." in label else label + ".0"


def km_label(miles):
    return f"{miles * KM_PER_MI:.6f}".rstrip("0").rstrip(".")


def build_views(grid, all_points, detail=False):
    main_roles = sorted({p["role"] for p in all_points if not p["role"].startswith("refine_")})
    main_spacing = grid.get("s0") or max(p["spacing"] for p in all_points if p["role"] in main_roles)
    views = [{"id": miles_label(main_spacing), "spacing": float(main_spacing), "label": "Full circle {km} km honeycomb, all rungs", "merged": True}]
    if not detail:
        return views
    refine = {}
    for p in all_points:
        if p["role"].startswith("refine_"):
            refine.setdefault(p["role"], float(p["spacing"]))
    for role, spacing in sorted(refine.items(), key=lambda kv: -kv[1]):
        views.append({"id": miles_label(spacing), "spacing": spacing, "label": "Detail {km} km honeycomb", "refine": role})
    return views


def view_nodes(points, view, unit):
    """Main view: the main-role points on its lattice. Detail view: every on-lattice
    point within two spacings of a refinement seed (the phase-1 node choice)."""
    if view.get("merged"):
        return list(points)
    step = round(view["spacing"] / unit)
    on = [p for p in points if p["unit_q"] % step == 0 and p["unit_r"] % step == 0]
    seeds = [p for p in points if p["role"] == view["refine"]]
    reach = 2 * view["spacing"] * 1.05
    return [p for p in on if any(math.hypot(s["east"] - p["east"], s["north"] - p["north"]) <= reach for s in seeds)]


def rung_of(p, s0, unit):
    """Coarsest ladder rung (s0, s0/2, s0/4, ...) whose lattice holds the point."""
    spacing = float(s0)
    while spacing / unit > 1 + 1e-9:
        step = round(spacing / unit)
        if step and abs(spacing / unit - step) < 1e-6 and p["unit_q"] % step == 0 and p["unit_r"] % step == 0:
            return spacing
        spacing /= 2
    return unit


def edge_signal(merged, s0, radius_mi, lane_ids):
    """Per lane: top-3 share on the outermost s0 ring inside R. Instrument-limited points are
    not scored (never a loss, never a win). Replaces expansion: nothing beyond R is searched."""
    ring = [p for p in merged.values() if p["hex"]["rung_miles"] == round(s0, 6)
            and p["distance_from_target_km"] / KM_PER_MI > radius_mi - s0 + 1e-3]
    out = {}
    for lid in lane_ids:
        obs = [p["by_lane"][lid] for p in ring if lid in p["by_lane"]]
        scored = [o for o in obs if o["status"] in ("ok", "not_returned_depth_reached")]
        top3 = sum(1 for o in scored if o["target_rank"] and o["target_rank"] <= 3)
        share = top3 / len(scored) if scored else None
        out[lid] = {"ring_points": len(obs), "scored": len(scored), "top3": top3,
                    "share": None if share is None else round(share, 4), "radius_miles": radius_mi,
                    "extends": bool(len(scored) >= EDGE_MIN_SCORED and share >= EDGE_SHARE)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--location", default=None, help="area label shown in the companion header")
    ap.add_argument("--rivals", type=int, default=9, help="most visible rivals to keep as factions")
    ap.add_argument("--no-current", action="store_true", help="do not repoint runs/current-study.json")
    ap.add_argument("--detail-views", action="store_true", help="also write one-spacing detail views per refine rung")
    args = ap.parse_args()

    run = _safe_local_path(args.run_dir)
    runs_root = run.parent
    run_name = run.name
    grid_path = _safe_local_path(run / "grid" / "grid_points.json")
    grid = json.loads(grid_path.read_text(encoding="utf-8"))
    center, settings, phrases = grid["center"], grid["settings"], grid["phrases"]
    depth = settings["depth"]
    target_cid = str(center["cid"])
    lanes = [{"lane_id": f"q{i + 1}", "query": q} for i, q in enumerate(phrases)]
    lane_of = {lane["query"]: lane["lane_id"] for lane in lanes}
    radius_mi = float(grid.get("study_radius") or max(grid["radius"].values()))
    # Strict circle: points beyond R (paid for by an older expansion) never enter the study.
    inside_r = lambda p: math.hypot(p["east"], p["north"]) <= radius_mi + 1e-6
    dropped = {k: sum(not inside_r(p) for p in pts) for k, pts in phrases.items()}
    phrases = {k: [p for p in pts if inside_r(p)] for k, pts in phrases.items()}
    all_points = [p for pts in phrases.values() for p in pts]
    unit = lattice_unit(all_points)
    views = build_views(grid, all_points, args.detail_views)
    s0 = views[0]["spacing"]
    location = args.location if args.location is not None else (center.get("location") or grid.get("location") or "")

    # Roster: the target plus the most visible rivals across every saved result (21 - rank).
    visibility, profile = {}, {}
    for p in all_points:
        for pos, name, cid, rating, reviews, lat, lng in p.get("top") or []:
            cid = str(cid)
            profile.setdefault(cid, (name, rating, reviews, lat, lng))
            if cid != target_cid and pos and pos <= depth:
                visibility[cid] = visibility.get(cid, 0) + 21 - pos
    rivals = sorted(visibility, key=lambda c: -visibility[c])[: args.rivals]

    def faction(cid, is_target, position=None):
        name, rating, reviews, lat, lng = profile.get(cid, (center["name"], None, None, center["lat"], center["lng"]))
        if is_target:
            lat, lng, name = center["lat"], center["lng"], center["name"]
        out = {"faction_id": f"cid:{cid}", "name": name, "is_target": is_target, "cid": cid, "place_id": None,
               "domain": None, "lat": lat, "lng": lng, "location_estimated": lat is None or lng is None,
               "discovered": not is_target, "rating": rating, "votes_count": reviews, "address": None}
        if position:
            out["selection"] = {"position": position, "visibility_score": visibility[cid]}
        return out

    factions = [faction(target_cid, True)] + [faction(c, False, i) for i, c in enumerate(rivals, 1)]

    def lane_result(p):
        if p.get("status") != "ok":
            return {"target_rank": None, "status": "error", "sampled_at": None, "top_items": []}
        items = [{"title": name, "rank": pos, "cid": str(cid), "rating": rating, "votes_count": reviews,
                  "latitude": lat, "longitude": lng} for pos, name, cid, rating, reviews, lat, lng in p.get("top") or []]
        rank = p.get("rank")
        status = "ok" if rank else "instrument_limited" if p.get("instrument_limited") else "not_returned_depth_reached"
        return {"target_rank": rank, "status": status, "sampled_at": None, "top_items": items}

    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    url_of = {v["id"]: f"/runs/{run_name}/companion/view-{v['id']}/companion-study.json" for v in views}
    study_views = [{"label": v["label"].format(km=km_label(v["spacing"])), "url": url_of[v["id"]]} for v in views]
    edge_main = None  # the edge signal belongs to the full circle (views[0]); detail views reuse it
    for view in views:
        merged = {}
        for phrase, points in phrases.items():
            for p in view_nodes(points, view, unit):
                key = (p["unit_q"], p["unit_r"])
                point = merged.setdefault(key, {
                    "tag": p["id"], "lat": p["lat"], "lng": p["lng"],
                    "distance_from_target_km": round(math.hypot(p["east"], p["north"]) * KM_PER_MI, 4),
                    "roles": [], "phase": p["role"], "anchor_factions": [], "by_lane": {},
                    "hex": {"unit_q": p["unit_q"], "unit_r": p["unit_r"], "first_rung_miles": round(unit, 6),
                            "rung_miles": round(rung_of(p, s0, unit), 6)},
                })
                if p["role"] not in point["roles"]:
                    point["roles"].append(p["role"])
                point["by_lane"][lane_of[phrase]] = lane_result(p)
        study = {
            "schema": "geogrid-companion/v1", "generated_at": generated,
            "business": {"name": center["name"], "cid": target_cid},
            "target": {"name": center["name"], "cid": target_cid, "lat": center["lat"], "lng": center["lng"]},
            "location": location,
            "factions": factions, "lanes": lanes, "points": list(merged.values()),
            "study": {
                "geometry": "hex_radius", "depth": depth, "total_points": len(merged),
                "sampling": {"geometry": "hex_radius", "radius_km": radius_mi * KM_PER_MI, "spacing_km": view["spacing"] * KM_PER_MI,
                             "center": {"lat": center["lat"], "lng": center["lng"]},
                             "description": f"{km_label(radius_mi)} km radius · {km_label(view['spacing'])} km honeycomb",
                             "study_radius_miles": radius_mi,
                             "hex": {"unit_miles": round(unit, 6), "step": round(view["spacing"] / unit)}},
                "controls": {"zoom": settings.get("zoom"), "device": settings.get("device"), "depth": depth},
                "edge_signal": edge_main or edge_signal(merged, s0, radius_mi, [lane["lane_id"] for lane in lanes]),
            },
            "study_views": study_views,
            "evidence": {"source_run": run_name, "note": "Exported from saved run results; no new searches."},
        }
        edge_main = study["study"]["edge_signal"]
        out = _safe_local_path(run / "companion" / f"view-{view['id']}" / "companion-study.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(study, separators=(",", ":")), encoding="utf-8")
        print(f"view {view['id']} mi: {len(merged)} points -> {out.relative_to(runs_root.parent)}")
        for lane in lanes:
            lid = lane["lane_id"]
            inside = [p["by_lane"][lid] for p in merged.values() if lid in p["by_lane"]]
            ranks = [o["target_rank"] for o in inside if o["target_rank"]]
            edge = study["study"]["edge_signal"][lid]
            print(f"  {lid} {lane['query']}: inside R {len(inside)}, found {len(ranks)}, top3 {sum(r <= 3 for r in ranks)}, "
                  f"#1 {sum(r == 1 for r in ranks)}, limited {sum(o['status'] == 'instrument_limited' for o in inside)}, "
                  f"absent {sum(o['status'] == 'not_returned_depth_reached' for o in inside)}, "
                  f"dropped beyond R {dropped[lane['query']]}, edge top3 {edge['top3']}/{edge['scored']} "
                  f"(ring {edge['ring_points']}){' EXTENDS PAST R' if edge['extends'] else ''}")

    if not args.no_current:
        current_path = _safe_local_path(runs_root / "current-study.json")
        current_path.write_text(json.dumps({"study": url_of[views[0]["id"]]}), encoding="utf-8")
        print(f"runs/current-study.json -> {url_of[views[0]['id']]}")
    print(f"lattice unit {unit:g} mi; rivals: {[profile[c][0] for c in rivals]}")


if __name__ == "__main__":
    main()
