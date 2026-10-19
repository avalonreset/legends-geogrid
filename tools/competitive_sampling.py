#!/usr/bin/env python3
"""Bounded Competitor-Aware Sampling Planner for legends-geogrid.

Generates a deterministic multi-faction sampling plan derived from target business
evidence and top 10 rival factions (from battlefield-model.json or study runs),
adhering to STUDY_CONTRACT.md, QUERY_SELECTION_POLICY.md, and SAMPLING_POLICY.md.

Topology:
1. Shared Faction Citadels: Target HQ + verified rival citadels.
2. Neighborhood Core Clusters: Micro-grids (0.65 km spacing) around each citadel.
3. Contested Corridor Midpoints: Transition probes between Target and rival bases.
4. Directional Sentinels: Discrete exploratory probes of ranking reach.
5. Spatial Deduplication: Merges proposed probes within 50m, retaining one actual coordinate.
6. Target-Centric Truncation Detection: Identifies where target-only grids truncate coverage.
7. Phased Execution & Cost Estimation: All tasks require fresh collection (no unsafe reuse).
8. Modern Settings Alignment: Strict zoom 14, depth 30, desktop, en, google.com, search_this_area True.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from local_heatmap_poc import (
        COST_PER_TASK_USD,
        LIVE_COST_PER_TASK_USD,
        canonical_domain,
        estimate_scan_cost,
        normalize,
    )
except ImportError:
    COST_PER_TASK_USD = {"standard": 0.0006, "priority": 0.0012, "live": 0.002}
    LIVE_COST_PER_TASK_USD = 0.002

    def estimate_scan_cost(task_count: int, depth: int, method: str) -> float:
        rate = COST_PER_TASK_USD.get(method, LIVE_COST_PER_TASK_USD)
        depth_units = max(1, math.ceil(depth / 100))
        return task_count * rate * depth_units

    def normalize(val: str | None) -> str:
        return re.sub(r"[^a-z0-9]+", "", (val or "").lower())

    def canonical_domain(url: str | None) -> str | None:
        if not url:
            return None
        m = re.search(r"^(?:https?://)?(?:www\.)?([^/?#:]+)", str(url).strip().lower())
        return m.group(1) if m else None

# Uncertainty & Observation Status Constants (SAMPLING_POLICY.md & ENHANCE.md)
STATUS_FOUND = "found"
STATUS_CONFIRMED_NR = "not_returned_depth_reached"
STATUS_UNKNOWN_SHORT = "unknown_short"
STATUS_UNKNOWN_EMPTY = "unknown_empty"
STATUS_UNKNOWN_ERROR = "unknown_error"
STATUS_UNKNOWN_UNSAMPLED = "unknown_unsampled"

# Sampling Heuristics (SAMPLING_POLICY.md)
DEFAULT_NEIGHBOR_SPACING_KM = 0.65  # <= 0.75 km neighborhood heuristic
DEFAULT_SNAP_TOLERANCE_KM = 0.05    # planned-origin merging only; never cached-result reuse
DEFAULT_SENTINEL_RADII_KM = (2, 5, 10)
EARTH_RADIUS_KM = 6371.0088


def parse_radii(val: Any) -> list[int | float]:
    """Parse comma-separated or sequence radii into list of ints or floats."""
    if not val:
        return [2, 5, 10]
    if isinstance(val, (list, tuple)):
        raw = list(val)
    else:
        raw = [p.strip() for p in str(val).split(",") if p.strip()]
    res: list[int | float] = []
    for x in raw:
        fx = float(x)
        res.append(int(fx) if fx.is_integer() else fx)
    return res


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute exact Haversine distance in kilometers between two coordinates."""
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    a = min(1.0, max(0.0, a))
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute initial compass bearing from (lat1, lng1) to (lat2, lng2) in degrees (0..360)."""
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dl = math.radians(float(lng2) - float(lng1))
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def project_point(lat: float, lng: float, distance_km: float, bearing: float) -> tuple[float, float]:
    """Project a point from (lat, lng) along a bearing by distance_km using spherical geodesy."""
    r = EARTH_RADIUS_KM
    d_div_r = distance_km / r
    rad_b = math.radians(bearing)
    lat_r = math.radians(lat)
    lng_r = math.radians(lng)

    new_lat = math.asin(
        math.sin(lat_r) * math.cos(d_div_r) + math.cos(lat_r) * math.sin(d_div_r) * math.cos(rad_b)
    )
    new_lng = lng_r + math.atan2(
        math.sin(rad_b) * math.sin(d_div_r) * math.cos(lat_r),
        math.cos(d_div_r) - math.sin(lat_r) * math.sin(new_lat),
    )
    return round(math.degrees(new_lat), 7), round(math.degrees(new_lng), 7)


def classify_serp_observation_status(
    *,
    rank: int | None,
    returned_items_count: int,
    depth: int,
    has_error: bool = False,
    is_sampled: bool = True,
) -> str:
    """Deterministically classify SERP observation status under soundness policy."""
    if not is_sampled:
        return STATUS_UNKNOWN_UNSAMPLED
    if has_error:
        return STATUS_UNKNOWN_ERROR
    if rank is not None and 1 <= rank <= depth:
        return STATUS_FOUND
    if returned_items_count >= depth:
        return STATUS_CONFIRMED_NR
    if returned_items_count == 0:
        return STATUS_UNKNOWN_EMPTY
    return STATUS_UNKNOWN_SHORT


def snap_and_deduplicate_origins(
    probes: list[dict[str, Any]],
    tolerance_km: float = DEFAULT_SNAP_TOLERANCE_KM,
    zoom: int = 14,
) -> list[dict[str, Any]]:
    """Cluster and deduplicate proposed probe coordinates within spatial tolerance."""
    role_priority = {
        "target_citadel": 1,
        "rival_citadel": 2,
        "target_baseline": 3,
        "neighborhood_core": 4,
        "corridor_midpoint": 5,
        "corridor_extension": 6,
        "outward_sentinel": 7,
    }

    def _probe_sort_key(p: dict[str, Any]) -> tuple[int, int, float, float, float]:
        primary_role = str(p.get("role_category") or "other")
        prio = role_priority.get(primary_role, 9)
        phase = int(p.get("phase") or 1)
        dist = float(p.get("distance_from_target_km") or 0.0)
        return (phase, prio, round(dist, 3), -float(p["lat"]), float(p["lng"]))

    sorted_probes = sorted(probes, key=_probe_sort_key)
    clusters: list[dict[str, Any]] = []

    for probe in sorted_probes:
        p_lat = float(probe["lat"])
        p_lng = float(probe["lng"])
        matched_cluster = None
        min_d = tolerance_km

        for cluster in clusters:
            d = haversine_km(p_lat, p_lng, cluster["lat"], cluster["lng"])
            if d <= min_d:
                min_d = d
                matched_cluster = cluster

        if matched_cluster is not None:
            for role in probe.get("roles") or [probe.get("role")]:
                if role and role not in matched_cluster["roles"]:
                    matched_cluster["roles"].append(role)
            for fid in probe.get("anchor_factions") or []:
                if fid and fid not in matched_cluster["anchor_factions"]:
                    matched_cluster["anchor_factions"].append(fid)
            matched_cluster["phase"] = min(matched_cluster["phase"], int(probe.get("phase", 3)))
            matched_cluster["merged_count"] += 1
        else:
            new_cluster = {
                "lat": round(p_lat, 7),
                "lng": round(p_lng, 7),
                "phase": int(probe.get("phase", 1)),
                "roles": list(probe.get("roles") or [probe.get("role")]),
                "anchor_factions": list(probe.get("anchor_factions") or []),
                "distance_from_target_km": round(float(probe.get("distance_from_target_km", 0.0)), 3),
                "bearing_from_target_deg": round(float(probe.get("bearing_from_target_deg", 0.0)), 1),
                "merged_count": 1,
                "notes": probe.get("notes") or "",
            }
            clusters.append(new_cluster)

    clusters.sort(key=lambda c: (c["phase"], c["distance_from_target_km"], -c["lat"], c["lng"]))

    origins: list[dict[str, Any]] = []
    for idx, cluster in enumerate(clusters, start=1):
        origin_id = f"csp_{idx:03d}"
        cluster["origin_id"] = origin_id
        cluster["location_coordinate"] = f"{cluster['lat']:.7f},{cluster['lng']:.7f},{zoom}z"
        origins.append(cluster)

    return origins


def extract_factions_roster(
    battlefield_model: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Extract Target and Rival Factions with geo-validation and status classification."""
    target_data = dict(battlefield_model.get("target") or battlefield_model.get("target_faction") or {})
    business_data = dict(battlefield_model.get("business") or {})

    t_lat = target_data.get("lat") or business_data.get("lat")
    t_lng = target_data.get("lng") or business_data.get("lng")
    has_valid_target_geo = (
        t_lat is not None
        and t_lng is not None
        and math.isfinite(float(t_lat))
        and math.isfinite(float(t_lng))
        and (float(t_lat) != 0.0 or float(t_lng) != 0.0)
    )

    target_geo: dict[str, Any] = {
        "faction_id": "TARGET",
        "name": target_data.get("name") or business_data.get("name") or "Target Business",
        "cid": target_data.get("cid") or business_data.get("cid"),
        "place_id": target_data.get("place_id") or business_data.get("place_id"),
        "domain": target_data.get("domain") or business_data.get("domain"),
        "address": target_data.get("address") or business_data.get("address"),
        "lat": round(float(t_lat), 7) if has_valid_target_geo else None,
        "lng": round(float(t_lng), 7) if has_valid_target_geo else None,
        "location_status": "verified" if has_valid_target_geo else "missing_geo",
        "solv_pct": float(target_data.get("solv_pct") or 0.0),
        "top3_count": int(target_data.get("top3_count") or 0),
        "rating": target_data.get("rating"),
        "votes_count": target_data.get("votes_count"),
        "max_top3_reach_km": float(target_data.get("max_top3_reach_km") or 0.0),
        "trail_off_radius_km": float(target_data.get("trail_off_radius_km") or 0.0),
    }

    factions_list = battlefield_model.get("factions") or []
    rival_geos: list[dict[str, Any]] = []

    for f in factions_list:
        fid = str(f.get("faction_id") or "")
        if fid == "TARGET" or not fid:
            continue

        r_lat = f.get("lat")
        r_lng = f.get("lng")
        has_geo = (
            r_lat is not None
            and r_lng is not None
            and math.isfinite(float(r_lat))
            and math.isfinite(float(r_lng))
            and (float(r_lat) != 0.0 or float(r_lng) != 0.0)
        )

        is_est = bool(f.get("location_estimated", False))
        if not has_geo:
            loc_status = "missing_geo"
        elif is_est:
            loc_status = "estimated"
        else:
            loc_status = "verified"

        d_from_target = None
        b_from_target = None
        if has_geo and has_valid_target_geo:
            d_from_target = round(haversine_km(target_geo["lat"], target_geo["lng"], float(r_lat), float(r_lng)), 2)
            b_from_target = round(bearing_deg(target_geo["lat"], target_geo["lng"], float(r_lat), float(r_lng)), 1)

        rival_geos.append({
            "faction_id": fid,
            "name": str(f.get("name") or f"Rival {fid}"),
            "cid": f.get("cid"),
            "place_id": f.get("place_id"),
            "domain": f.get("domain"),
            "address": f.get("address"),
            "lat": round(float(r_lat), 7) if has_geo else None,
            "lng": round(float(r_lng), 7) if has_geo else None,
            "location_status": loc_status,
            "distance_from_target_km": d_from_target,
            "bearing_from_target_deg": b_from_target,
            "solv_pct": float(f.get("solv_pct") or 0.0),
            "top3_count": int(f.get("top3_count") or 0),
            "rating": f.get("rating"),
            "votes_count": f.get("votes_count"),
            "max_top3_reach_km": float(f.get("max_top3_reach_km") or 0.0),
            "trail_off_radius_km": float(f.get("trail_off_radius_km") or 0.0),
            "archetype": f.get("archetype") or "LOCAL_OUTPOST",
        })

    rival_geos.sort(key=lambda r: (-r["solv_pct"], -r["top3_count"], r["faction_id"]))
    return target_geo, rival_geos


def detect_target_centric_truncation(
    target_geo: dict[str, Any],
    rival_geos: list[dict[str, Any]],
    grid_meta: dict[str, Any],
    study_plan: dict[str, Any] | None = None,
    neighbor_spacing_km: float = DEFAULT_NEIGHBOR_SPACING_KM,
) -> dict[str, Any]:
    """Detect where target-centric sampling creates asymmetric or truncated coverage."""
    study_radius_km = float(grid_meta.get("radius_km") or 0.0)
    grid_size = int(grid_meta.get("grid_size") or 5)
    geometry_type = str(grid_meta.get("geometry") or "square_grid")

    plan_settings = (study_plan.get("settings") or {}) if isinstance(study_plan, dict) else {}
    baseline_radius_km = float(plan_settings.get("radius_km") or 0.0)

    findings: list[dict[str, Any]] = []
    truncated_citadels_count = 0
    baseline_omitted_count = 0
    coarse_resolution_count = 0
    asymmetric_outward_count = 0
    boundary_contested_count = 0
    missing_geo_count = 0

    t_lat = target_geo.get("lat")
    t_lng = target_geo.get("lng")
    has_target_geo = t_lat is not None and t_lng is not None

    for rival in rival_geos:
        fid = rival["faction_id"]
        fname = rival["name"]
        loc_status = rival["location_status"]

        if loc_status == "missing_geo" or rival["lat"] is None or rival["lng"] is None:
            missing_geo_count += 1
            findings.append({
                "faction_id": fid,
                "faction_name": fname,
                "severity": "WARNING",
                "finding_type": "missing_geocoding",
                "message": (
                    f"{fid} ({fname}) lacks verified physical coordinates on GBP. "
                    "Address reconciliation or service-area business centroid required."
                ),
            })
            continue

        if not has_target_geo:
            continue

        dist_km = haversine_km(t_lat, t_lng, rival["lat"], rival["lng"])

        # 1. Truncated from baseline study plan extent (e.g. 1.2 km core)
        if baseline_radius_km > 0.0 and dist_km > baseline_radius_km:
            baseline_omitted_count += 1
            findings.append({
                "faction_id": fid,
                "faction_name": fname,
                "severity": "CRITICAL",
                "finding_type": "baseline_plan_omission",
                "distance_km": round(dist_km, 2),
                "baseline_radius_km": round(baseline_radius_km, 2),
                "message": (
                    f"{fid} ({fname}) citadel at {dist_km:.2f} km lies completely outside the "
                    f"validated baseline study plan radius ({baseline_radius_km:.2f} km). "
                    "Its home doorstep was omitted from the original baseline."
                ),
            })

        # 2. Citadel outside active grid radius
        if study_radius_km > 0.0 and dist_km > study_radius_km:
            truncated_citadels_count += 1
            findings.append({
                "faction_id": fid,
                "faction_name": fname,
                "severity": "CRITICAL",
                "finding_type": "citadel_outside_boundary",
                "distance_km": round(dist_km, 2),
                "study_radius_km": round(study_radius_km, 2),
                "message": (
                    f"{fid} ({fname}) citadel at {dist_km:.2f} km is outside the active "
                    f"study radius of {study_radius_km:.2f} km."
                ),
            })

        # 3. Coarse sampling resolution at rival citadel
        est_spacing_km = None
        if "radial" in geometry_type:
            spokes = 24 if dist_km >= 4.8 else (16 if dist_km >= 2.0 else 8)
            est_spacing_km = round((2.0 * math.pi * dist_km) / max(1, spokes), 2)
        elif study_radius_km > 0.0 and grid_size > 1:
            est_spacing_km = round((2.0 * study_radius_km) / (grid_size - 1), 2)

        if est_spacing_km is not None and est_spacing_km > 0.75:
            coarse_resolution_count += 1
            findings.append({
                "faction_id": fid,
                "faction_name": fname,
                "severity": "WARNING",
                "finding_type": "coarse_sampling_resolution",
                "distance_km": round(dist_km, 2),
                "estimated_spacing_km": est_spacing_km,
                "threshold_km": 0.75,
                "message": (
                    f"Target-centric sampling resolution at {fid} ({fname}, {dist_km:.2f} km) is "
                    f"coarse (~{est_spacing_km:.2f} km point spacing), exceeding the 0.75 km "
                    "neighborhood resolution heuristic."
                ),
            })

        # 4. Asymmetric outward territory
        if study_radius_km > 0.0 and dist_km >= 0.40 * study_radius_km:
            asymmetric_outward_count += 1
            findings.append({
                "faction_id": fid,
                "faction_name": fname,
                "severity": "INFO",
                "finding_type": "asymmetric_outward_territory",
                "distance_km": round(dist_km, 2),
                "study_radius_km": round(study_radius_km, 2),
                "message": (
                    f"{fid} ({fname}) is located {dist_km:.2f} km from Target center. "
                    "The outward territory behind this rival away from Target is unsampled or sparse."
                ),
            })

        # 5. Frontier reach / trail-off near or beyond study boundary
        reach_km = rival.get("max_top3_reach_km") or 0.0
        if study_radius_km > 0.0 and (dist_km + reach_km > study_radius_km * 0.90):
            boundary_contested_count += 1
            findings.append({
                "faction_id": fid,
                "faction_name": fname,
                "severity": "WARNING",
                "finding_type": "frontier_reach_truncation",
                "projected_reach_km": round(dist_km + reach_km, 2),
                "study_radius_km": round(study_radius_km, 2),
                "message": (
                    f"{fid} ({fname}) projects Top 3 reach up to {reach_km:.2f} km from its base, "
                    f"reaching {dist_km + reach_km:.2f} km from Target. True frontier is truncated."
                ),
            })

    return {
        "target_study_radius_km": round(study_radius_km, 2),
        "target_study_grid_size": grid_size,
        "target_study_geometry": geometry_type,
        "baseline_plan_radius_km": round(baseline_radius_km, 2) if baseline_radius_km > 0 else None,
        "total_rivals_analyzed": len(rival_geos),
        "truncated_citadels_count": truncated_citadels_count,
        "baseline_omitted_count": baseline_omitted_count,
        "coarse_resolution_count": coarse_resolution_count,
        "asymmetric_outward_count": asymmetric_outward_count,
        "boundary_contested_count": boundary_contested_count,
        "missing_geo_count": missing_geo_count,
        "findings": findings,
    }


def generate_candidate_sampling_probes(
    target_geo: dict[str, Any],
    rival_geos: list[dict[str, Any]],
    *,
    neighbor_spacing_km: float = DEFAULT_NEIGHBOR_SPACING_KM,
    sentinel_radii_km: Any = DEFAULT_SENTINEL_RADII_KM,
    baseline_points: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Generate candidate probes across target baseline, 3x3 neighborhood cores, and 8 compass sentinels."""
    candidate_probes: list[dict[str, Any]] = []

    has_target_geo = target_geo.get("location_status") != "missing_geo" and target_geo.get("lat") is not None
    t_lat = float(target_geo["lat"]) if has_target_geo else 0.0
    t_lng = float(target_geo["lng"]) if has_target_geo else 0.0
    t_fid = target_geo.get("faction_id", "TARGET")

    # 1. Refresh baseline origins in Phase 2.
    if baseline_points:
        for point in baseline_points:
            p_lat = point.get("lat")
            p_lng = point.get("lng")
            if p_lat is None or p_lng is None:
                continue
            lat_f = round(float(p_lat), 7)
            lng_f = round(float(p_lng), 7)
            ring = point.get("ring", 0)
            spoke = point.get("spoke", 0)
            tag_str = str(point.get("tag") or "")
            role = tag_str if tag_str else f"target_radial_r{ring}_s{spoke}"
            dist_km = round(
                float(point.get("distance_from_target_km") or (haversine_km(t_lat, t_lng, lat_f, lng_f) if has_target_geo else 0.0)),
                3,
            )
            bearing_d = round(
                float(point.get("bearing_deg") or (bearing_deg(t_lat, t_lng, lat_f, lng_f) if has_target_geo else 0.0)),
                1,
            )
            candidate_probes.append({
                "lat": lat_f,
                "lng": lng_f,
                "phase": 2,
                "role": role,
                "role_category": "target_baseline",
                "anchor_factions": [t_fid],
                "distance_from_target_km": dist_km,
                "bearing_from_target_deg": bearing_d,
                "notes": f"Target radial baseline origin at prior origin {tag_str}",
            })

    centers = [target_geo] + rival_geos

    # 2. Anchors in Phase 1; 3x3 neighborhood cores in Phase 2.
    for faction in centers:
        if faction.get("location_status") == "missing_geo" or faction.get("lat") is None or faction.get("lng") is None:
            continue
        f_lat = float(faction["lat"])
        f_lng = float(faction["lng"])
        fid = faction.get("faction_id", "UNKNOWN")
        fname = faction.get("name", "Unknown")
        is_target = (fid == t_fid)

        # Citadel anchor (center)
        candidate_probes.append({
            "lat": f_lat,
            "lng": f_lng,
            "phase": 1,
            "role": "target_citadel" if is_target else f"{fid.lower()}_citadel",
            "role_category": "target_citadel" if is_target else "rival_citadel",
            "anchor_factions": [fid],
            "distance_from_target_km": round(haversine_km(t_lat, t_lng, f_lat, f_lng), 3) if has_target_geo else 0.0,
            "bearing_from_target_deg": round(bearing_deg(t_lat, t_lng, f_lat, f_lng), 1) if has_target_geo else 0.0,
            "notes": f"Center citadel anchor for {fid} ({fname})",
        })
        if has_target_geo and not is_target:
            distance = haversine_km(t_lat, t_lng, f_lat, f_lng)
            direction = bearing_deg(t_lat, t_lng, f_lat, f_lng)
            for fraction in ((1 / 3, 1 / 2, 2 / 3) if distance > 6 else (1 / 2,)):
                lat, lng = project_point(t_lat, t_lng, distance * fraction, direction)
                candidate_probes.append({
                    "lat": lat, "lng": lng, "phase": 1 if fraction == 1 / 2 else 2,
                    "role": f"corridor_{fid}_{fraction:.3f}", "role_category": "corridor_midpoint",
                    "anchor_factions": [t_fid, fid], "distance_from_target_km": distance * fraction,
                    "notes": "Straight-line comparison origin between supplied bases; no claim about roads or travel",
                })

        # Cardinal surrounding core probes (4 points at neighbor_spacing_km)
        for bearing in (0, 90, 180, 270):
            lat, lng = project_point(f_lat, f_lng, neighbor_spacing_km, float(bearing))
            candidate_probes.append({
                "lat": lat,
                "lng": lng,
                "phase": 2,
                "role": f"{fid}_core_{bearing}",
                "role_category": "neighborhood_core",
                "anchor_factions": [fid],
                "distance_from_target_km": round(haversine_km(t_lat, t_lng, lat, lng), 3) if has_target_geo else 0.0,
                "bearing_from_target_deg": round(bearing_deg(t_lat, t_lng, lat, lng), 1) if has_target_geo else float(bearing),
                "notes": f"Neighborhood cardinal core probe for {fid} bearing {bearing}",
            })

        # Diagonal surrounding core probes (4 points at neighbor_spacing_km * sqrt(2))
        for bearing in (45, 135, 225, 315):
            lat, lng = project_point(f_lat, f_lng, neighbor_spacing_km * math.sqrt(2), float(bearing))
            candidate_probes.append({
                "lat": lat,
                "lng": lng,
                "phase": 2,
                "role": f"{fid}_core_{bearing}",
                "role_category": "neighborhood_core",
                "anchor_factions": [fid],
                "distance_from_target_km": round(haversine_km(t_lat, t_lng, lat, lng), 3) if has_target_geo else 0.0,
                "bearing_from_target_deg": round(bearing_deg(t_lat, t_lng, lat, lng), 1) if has_target_geo else float(bearing),
                "notes": f"Neighborhood diagonal core probe for {fid} bearing {bearing}",
            })

    # 3. Eight compass probes per center at configurable radii (Phase 3).
    parsed_radii = parse_radii(sentinel_radii_km)
    for faction in centers:
        if faction.get("location_status") == "missing_geo" or faction.get("lat") is None or faction.get("lng") is None:
            continue
        f_lat = float(faction["lat"])
        f_lng = float(faction["lng"])
        fid = faction.get("faction_id", "UNKNOWN")

        for radius in parsed_radii:
            for bearing in range(0, 360, 45):
                lat, lng = project_point(f_lat, f_lng, float(radius), float(bearing))
                candidate_probes.append({
                    "lat": lat,
                    "lng": lng,
                    "phase": 3,
                    "role": f"{fid}_reach_{radius:g}km_{bearing}",
                    "role_category": "outward_sentinel",
                    "anchor_factions": [fid],
                    "distance_from_target_km": round(haversine_km(t_lat, t_lng, lat, lng), 3) if has_target_geo else 0.0,
                    "bearing_from_target_deg": round(bearing_deg(t_lat, t_lng, lat, lng), 1) if has_target_geo else float(bearing),
                    "notes": f"Exploratory reach probe {radius:g} km from supplied base, bearing {bearing}; intervening ground unmeasured",
                })

    return candidate_probes


def extract_queries_and_settings(
    study_plan: dict[str, Any] | None,
    battlefield_model: dict[str, Any],
    raw_task_sample: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract explicit selected queries and measurement settings from study plan or modern raw requests."""
    selected_queries: list[dict[str, Any]] = []
    settings: dict[str, Any] = {}

    if isinstance(study_plan, dict):
        settings.update(study_plan.get("settings") or {})
        for q in study_plan.get("queries") or []:
            if isinstance(q, dict) and q.get("selected"):
                selected_queries.append({
                    "query": str(q["query"]),
                    "role": q.get("role", "service"),
                    "reason": q.get("reason", ""),
                    "theme": dict(q.get("theme") or {}),
                    "demand_scope": q.get("demand_scope", ""),
                    "intent_assessment": q.get("intent_assessment", ""),
                    "limitations": q.get("limitations", ""),
                })

    if not selected_queries:
        for idx, lane in enumerate(battlefield_model.get("lanes") or [], start=1):
            q_str = str(lane.get("keyword") or lane.get("query") or f"query_{idx}")
            selected_queries.append({
                "query": q_str,
                "role": "service",
                "reason": str(lane.get("narrative") or "Preserved study lane query"),
                "theme": {
                    "id": f"lane_{idx}",
                    "label": str(lane.get("label") or q_str),
                    "customer_need": "Preserved commercial inquiry",
                    "distinct_value": "Measures competitive discoverability",
                },
                "demand_scope": "Preserved from active study",
                "intent_assessment": "Derived from observed SERP items",
                "limitations": "",
            })

    grid_meta = battlefield_model.get("grid") or battlefield_model.get("study") or {}
    modern_zoom = None

    if raw_task_sample and isinstance(raw_task_sample, dict):
        if raw_task_sample.get("zoom") is not None:
            modern_zoom = int(raw_task_sample["zoom"])
        elif "location_coordinate" in raw_task_sample:
            m = re.search(r",(\d+)z$", str(raw_task_sample["location_coordinate"]))
            if m:
                modern_zoom = int(m.group(1))
        for key in ("depth", "device", "language_code", "se_domain", "search_this_area"):
            if key in raw_task_sample and raw_task_sample[key] is not None:
                settings[key] = raw_task_sample[key]

    if modern_zoom is None and grid_meta.get("zoom") is not None:
        modern_zoom = int(grid_meta["zoom"])

    # Radial and modern runs default to zoom 14 rather than old 5x5 core grid zoom 15
    if modern_zoom is not None:
        settings["zoom"] = modern_zoom
    else:
        settings.setdefault("zoom", 14)

    settings.setdefault("depth", 30)
    settings.setdefault("device", "desktop")
    settings.setdefault("language_code", "en")
    settings.setdefault("se_domain", "google.com")
    settings.setdefault("search_this_area", True)
    settings.setdefault("method", "standard")
    settings["settings_provenance"] = (
        f"Modern execution controls (zoom {settings['zoom']}, depth {settings['depth']}, "
        f"{settings['device']}) aligned with raw provider requests and validated study queries"
    )

    return selected_queries, settings


def build_phased_plan(
    origins: list[dict[str, Any]],
    selected_queries: list[dict[str, Any]],
    settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Organize deduplicated origins into progressive Phases 1..3 with task and cost estimates."""
    phase_meta = {
        1: {
            "name": "Phase 1: Business locations and connecting origins",
            "description": (
                "Compare all selected businesses near their bases and connecting midpoints."
            ),
        },
        2: {
            "name": "Phase 2: Baseline refresh and neighborhood cores",
            "description": "Refresh prior origins and measure 3x3 neighborhoods at 0.65 km spacing.",
        },
        3: {
            "name": "Phase 3: Directional reach probes",
            "description": (
                "Probes unresolved outward reach along 8 compass bearings per center at 2, 5, and 10 km. "
                "Candidate probes, not complete boundary claims; after initial results active outward fronts require review."
            ),
        },
    }

    depth = int(settings.get("depth", 30))
    method = str(settings.get("method", "standard"))
    queries_count = len(selected_queries)

    phases: list[dict[str, Any]] = []
    cum_tasks = 0
    cum_cost = 0.0

    for p_num in (1, 2, 3):
        p_origins = [o for o in origins if o["phase"] == p_num]
        o_count = len(p_origins)
        total_tasks = o_count * queries_count
        cost_usd = round(estimate_scan_cost(total_tasks, depth, method), 4)

        cum_tasks += total_tasks
        cum_cost = round(cum_cost + cost_usd, 4)

        phases.append({
            "phase": p_num,
            "name": phase_meta[p_num]["name"],
            "description": phase_meta[p_num]["description"],
            "origins_count": o_count,
            "queries_count": queries_count,
            "total_tasks": total_tasks,
            "new_tasks": total_tasks,
            "estimated_cost_usd": cost_usd,
            "cumulative_tasks": cum_tasks,
            "cumulative_new_tasks": cum_tasks,
            "cumulative_cost_usd": cum_cost,
            "origin_ids": [o["origin_id"] for o in p_origins],
        })

    summary = {
        "total_deduplicated_origins": len(origins),
        "total_queries": queries_count,
        "total_tasks": cum_tasks,
        "total_reused_tasks": 0,
        "total_new_tasks": cum_tasks,
        "total_estimated_cost_usd": cum_cost,
        "method": method,
        "depth": depth,
        "zoom": settings.get("zoom", 14),
        "cost_per_task_usd": COST_PER_TASK_USD.get(method, LIVE_COST_PER_TASK_USD),
        "readiness_status": "planned_requires_review",
    }

    return phases, summary


class CompetitiveExecutionAdapter:
    """Execution adapter connecting competitive sampling plans to collector transport."""

    def __init__(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.settings = plan.get("measurement_settings") or {}
        self.queries = plan.get("query_selection") or []
        self.origins = plan.get("origins") or []

    def build_tasks(self, phase: int | None = None) -> list[dict[str, Any]]:
        return generate_execution_tasks(self.plan, phase=phase)

    def estimate_cost_usd(self, phase: int | None = None) -> float:
        phases = self.plan.get("phases") or []
        if phase is not None:
            for p in phases:
                if p.get("phase") == phase:
                    return float(p.get("estimated_cost_usd") or 0.0)
            return 0.0
        return float((self.plan.get("summary") or {}).get("total_estimated_cost_usd") or 0.0)

    def get_execution_recipe(self, output_dir: str | Path, phase: int | None = None) -> dict[str, Any]:
        cost = self.estimate_cost_usd(phase)
        tasks = self.build_tasks(phase)
        return {
            "phase": phase or "all_phases",
            "output_dir": str(output_dir),
            "task_count": len(tasks),
            "estimated_cost_usd": cost,
            "suggested_cli_command": (
                f'python tools/competitive_collect.py --plan competitive-plan.json '
                f'--output-dir "{output_dir}" --execute --confirm-cost-usd {cost:.4f}'
                + (f" --phase {phase}" if phase is not None else "")
            ),
            "safety_gate": "Requires explicit --execute and --confirm-cost-usd flags",
        }


def generate_execution_tasks(
    plan: dict[str, Any],
    phase: int | None = None,
) -> list[dict[str, Any]]:
    """Generate DataForSEO task payloads compatible with collector execution."""
    settings = plan.get("measurement_settings") or {}
    queries = plan.get("query_selection") or []
    all_origins = plan.get("origins") or []

    if phase is not None:
        target_origins = [o for o in all_origins if o.get("phase") == phase]
    else:
        target_origins = all_origins

    tasks: list[dict[str, Any]] = []
    depth = int(settings.get("depth", 30))
    zoom = int(settings.get("zoom", 14))
    device = str(settings.get("device", "desktop"))
    language_code = str(settings.get("language_code", "en"))
    se_domain = str(settings.get("se_domain", "google.com"))
    search_this_area = bool(settings.get("search_this_area", True))

    for q_idx, q_item in enumerate(queries, start=1):
        keyword = str(q_item["query"])
        for orig in target_origins:
            orig_id = orig["origin_id"]
            tag = orig_id
            coord = orig.get("location_coordinate") or f"{orig['lat']:.7f},{orig['lng']:.7f},{zoom}z"
            tasks.append({
                "keyword": keyword,
                "location_coordinate": coord,
                "depth": depth,
                "device": device,
                "language_code": language_code,
                "se_domain": se_domain,
                "search_this_area": search_this_area,
                "search_places": False,
                "tag": tag,
            })

    return tasks


def plan_competitive_sampling(
    *,
    battlefield_model: dict[str, Any],
    study_plan: dict[str, Any] | None = None,
    raw_task_sample: dict[str, Any] | None = None,
    neighbor_spacing_km: float = DEFAULT_NEIGHBOR_SPACING_KM,
    snap_tolerance_km: float = DEFAULT_SNAP_TOLERANCE_KM,
    source_battlefield_path: str | None = None,
    source_study_plan_path: str | None = None,
    sentinel_radii_km: Any = DEFAULT_SENTINEL_RADII_KM,
) -> dict[str, Any]:
    """Build a bounded, competitor-aware sampling plan from battlefield and study inputs."""
    parsed_radii = parse_radii(sentinel_radii_km)
    if (not math.isfinite(neighbor_spacing_km) or not 0 < neighbor_spacing_km <= 5
            or not math.isfinite(snap_tolerance_km) or not 0 <= snap_tolerance_km <= 0.25
            or not parsed_radii or any(not math.isfinite(r) or not 0 < r <= 50 for r in parsed_radii)):
        raise ValueError("Finite, bounded sampling distances required")
    target_geo, rival_geos = extract_factions_roster(battlefield_model)
    grid_meta = dict(battlefield_model.get("grid") or battlefield_model.get("study") or {})

    truncation_analysis = detect_target_centric_truncation(
        target_geo,
        rival_geos,
        grid_meta,
        study_plan=study_plan,
        neighbor_spacing_km=neighbor_spacing_km,
    )
    selected_queries, settings = extract_queries_and_settings(study_plan, battlefield_model, raw_task_sample)
    settings.update(method="standard", zoom=14, depth=30, device="desktop",
                    language_code="en", se_domain="google.com", search_this_area=True, search_places=False)
    settings["settings_provenance"] = "Fresh comparative experiment: selected researched queries; Standard queue with common Maps controls"

    baseline_pts = (
        battlefield_model.get("points")
        or (study_plan.get("points") if isinstance(study_plan, dict) else None)
        or (study_plan.get("grid", {}).get("points") if isinstance(study_plan, dict) else None)
        or []
    )
    raw_probes = generate_candidate_sampling_probes(
        target_geo,
        rival_geos,
        neighbor_spacing_km=neighbor_spacing_km,
        sentinel_radii_km=parsed_radii,
        baseline_points=baseline_pts,
    )

    deduped_origins = snap_and_deduplicate_origins(
        raw_probes,
        tolerance_km=snap_tolerance_km,
        zoom=int(settings.get("zoom", 14)),
    )

    phases, summary = build_phased_plan(deduped_origins, selected_queries, settings)

    adapter = CompetitiveExecutionAdapter({
        "measurement_settings": settings,
        "query_selection": selected_queries,
        "origins": deduped_origins,
        "phases": phases,
        "summary": summary,
        "source_study_plan": source_study_plan_path,
    })

    execution_adapter_info = {
        "target_runner": "tools/competitive_collect.py",
        "task_format": "DataForSEO Google Maps Live format with modern zoom 14 coordinate encoding",
        "spending_authorization_gate": "--execute and --confirm-cost-usd required for execution",
        "task_generation_api": "generate_execution_tasks(plan, phase=None)",
        "offline_safety": "Planner is deterministic offline; no paid calls or credentials used",
        "execution_recipe": adapter.get_execution_recipe(output_dir="runs/competitive_study"),
    }

    soundness_policy = {
        "policy_reference": "docs/SAMPLING_POLICY.md and docs/ENHANCE.md",
        "core_doctrine": "Unknown observations are distinctly separate from confirmed absence (full-depth NR).",
        "spatial_reuse_policy": "Naive spatial reuse (<= 220m) without fresh timestamp verification is rejected as unsafe.",
        "status_mappings": {
            STATUS_FOUND: "Rank 1..depth returned and verified in SERP items.",
            STATUS_CONFIRMED_NR: "Full requested depth returned; business verified absent from all positions.",
            STATUS_UNKNOWN_SHORT: "Fewer than requested depth items returned; deeper positions unmeasured.",
            STATUS_UNKNOWN_EMPTY: "Zero items returned by provider; search results unmeasured.",
            STATUS_UNKNOWN_ERROR: "Provider error or network exception encountered; status unmeasured.",
            STATUS_UNKNOWN_UNSAMPLED: "Coordinate not yet probed; status unmeasured.",
        },
        "non_fabrication_rule": (
            "Never fabricate opportunity scores or claim proven lack of demand/presence "
            "based on short, empty, error, or unsampled observations."
        ),
        "boundary_limitation": (
            "Directional sentinels are discrete exploratory probes along sampled radials, not a completed or certified "
            "territorial boundary; unsampled corridors between or beyond sentinels remain unknown."
        ),
        "readiness_gate": (
            "Status 'planned_requires_review' indicates provider connectivity, original source freshness, "
            "and business geographic relevance must be reviewed before live execution."
        ),
    }

    plan_doc: dict[str, Any] = {
        "schema": "legends-geogrid-competitive-plan/v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_battlefield": source_battlefield_path,
        "source_study_plan": source_study_plan_path,
        "target_business": target_geo,
        "rival_factions_roster": rival_geos,
        "truncation_analysis": truncation_analysis,
        "query_selection": selected_queries,
        "measurement_settings": settings,
        "sampling_parameters": {
            "neighbor_spacing_km": neighbor_spacing_km,
            "snap_tolerance_km": snap_tolerance_km,
            "sentinel_radii_km": parsed_radii,
            "total_candidate_probes": len(raw_probes),
            "deduplicated_origins_count": len(deduped_origins),
        },
        "soundness_policy": soundness_policy,
        "phases": phases,
        "summary": summary,
        "origins": deduped_origins,
        "execution_adapter": execution_adapter_info,
    }

    return plan_doc


def load_inputs(
    battlefield_input: str | Path,
    study_plan_input: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, str, str | None]:
    """Load battlefield model, study plan, and sample raw task settings from file paths or directories."""
    bf_path = Path(battlefield_input).resolve()
    sp_path = Path(study_plan_input).resolve() if study_plan_input else None

    raw_task_sample: dict[str, Any] | None = None
    study_plan_data: dict[str, Any] | None = None

    if bf_path.is_dir():
        candidate_bf = bf_path / "battlefield" / "battlefield-model.json"
        if not candidate_bf.is_file():
            candidate_bf = bf_path / "battlefield-model.json"

        if candidate_bf.is_file():
            bf_data = json.loads(candidate_bf.read_text(encoding="utf-8-sig"))
            bf_source_str = str(candidate_bf)
        else:
            from battlefield import build_battlefield_model
            bf_data = build_battlefield_model(bf_path)
            bf_source_str = str(bf_path)

        if sp_path is None:
            candidate_sp = bf_path / "evidence" / "study-plan.json"
            if candidate_sp.is_file():
                sp_path = candidate_sp

        for tasks_cand in sorted(bf_path.rglob("dataforseo-request-tasks.json")):
            try:
                tasks_list = json.loads(tasks_cand.read_text(encoding="utf-8-sig"))
                if isinstance(tasks_list, list) and tasks_list and isinstance(tasks_list[0], dict):
                    raw_task_sample = tasks_list[0]
                    break
            except (OSError, ValueError):
                pass
    else:
        bf_data = json.loads(bf_path.read_text(encoding="utf-8-sig"))
        bf_source_str = str(bf_path)
        if sp_path is None:
            cand_sp = bf_path.parent.parent / "evidence" / "study-plan.json"
            if cand_sp.is_file():
                sp_path = cand_sp
            else:
                cand_sp2 = bf_path.parent / "evidence" / "study-plan.json"
                if cand_sp2.is_file():
                    sp_path = cand_sp2

        cand_tasks = bf_path.parent / "dataforseo-request-tasks.json"
        if cand_tasks.is_file():
            try:
                tasks_list = json.loads(cand_tasks.read_text(encoding="utf-8-sig"))
                if isinstance(tasks_list, list) and tasks_list and isinstance(tasks_list[0], dict):
                    raw_task_sample = tasks_list[0]
            except (OSError, ValueError):
                pass

    if sp_path and sp_path.is_file():
        study_plan_data = json.loads(sp_path.read_text(encoding="utf-8-sig"))
        sp_source_str = str(sp_path)
    else:
        sp_source_str = None

    return bf_data, study_plan_data, raw_task_sample, bf_source_str, sp_source_str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded Competitor-Aware Sampling Planner for legends-geogrid."
    )
    parser.add_argument(
        "--battlefield",
        "--battlefield-model",
        dest="battlefield",
        required=True,
        help="Path to battlefield-model.json or study directory containing battlefield model",
    )
    parser.add_argument(
        "--study-plan",
        "--plan",
        dest="study_plan",
        default=None,
        help="Path to validated study-plan.json (auto-detected if inside study dir)",
    )
    parser.add_argument(
        "--output",
        default=".codex-tmp/competitive-plan.json",
        help="Path to output competitive sampling plan JSON (default: .codex-tmp/competitive-plan.json)",
    )
    parser.add_argument(
        "--neighbor-spacing-km",
        type=float,
        default=DEFAULT_NEIGHBOR_SPACING_KM,
        help=f"Target spacing for neighborhood clusters (default: {DEFAULT_NEIGHBOR_SPACING_KM} km)",
    )
    parser.add_argument(
        "--snap-km",
        type=float,
        default=DEFAULT_SNAP_TOLERANCE_KM,
        help=f"Deduplication snap clustering tolerance in km (default: {DEFAULT_SNAP_TOLERANCE_KM} km)",
    )
    parser.add_argument(
        "--sentinel-radii-km",
        dest="sentinel_radii_km",
        default="2,5,10",
        help="Explicit outward sentinel probe radii in km per center, comma-separated (default: 2,5,10)",
    )
    parser.add_argument(
        "--tasks-output",
        default=None,
        help="Optional path to output execution DataForSEO task payloads JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan summary receipt to stdout",
    )
    args = parser.parse_args(argv)

    bf_data, study_plan_data, raw_task_sample, bf_src, sp_src = load_inputs(
        args.battlefield,
        args.study_plan,
    )

    plan = plan_competitive_sampling(
        battlefield_model=bf_data,
        study_plan=study_plan_data,
        raw_task_sample=raw_task_sample,
        neighbor_spacing_km=args.neighbor_spacing_km,
        snap_tolerance_km=args.snap_km,
        sentinel_radii_km=args.sentinel_radii_km,
        source_battlefield_path=bf_src,
        source_study_plan_path=sp_src,
    )

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.tasks_output:
        tasks = generate_execution_tasks(plan)
        t_path = Path(args.tasks_output).resolve()
        t_path.parent.mkdir(parents=True, exist_ok=True)
        t_path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    receipt = {
        "status": "ok",
        "plan_file": str(out_path),
        "target": plan["target_business"]["name"],
        "rival_factions_count": len(plan["rival_factions_roster"]),
        "truncated_citadels": plan["truncation_analysis"]["truncated_citadels_count"],
        "baseline_omitted_citadels": plan["truncation_analysis"]["baseline_omitted_count"],
        "coarse_resolution_citadels": plan["truncation_analysis"]["coarse_resolution_count"],
        "total_deduplicated_origins": plan["summary"]["total_deduplicated_origins"],
        "queries_count": plan["summary"]["total_queries"],
        "total_tasks": plan["summary"]["total_tasks"],
        "total_estimated_cost_usd": plan["summary"]["total_estimated_cost_usd"],
        "zoom": plan["measurement_settings"]["zoom"],
        "depth": plan["measurement_settings"]["depth"],
        "phases_breakdown": [
            {
                "phase": p["phase"],
                "origins": p["origins_count"],
                "tasks": p["total_tasks"],
                "cost_usd": p["estimated_cost_usd"],
            }
            for p in plan["phases"]
        ],
    }
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
