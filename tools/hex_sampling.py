"""Hexagonal (honeycomb) lattice clipped to a circular border, with a nested ladder.

Companion to radius_sampling.py (the square "radius_grid"). Points are the
centers of a honeycomb: a triangular lattice whose nearest-neighbor spacing
is s miles. Point 0 is exactly the business coordinate.

Geometry and geodesic notes
---------------------------
Lattice placement uses a local tangent plane (equirectangular offsets, the
same convention as radius_sampling.py): latitude steps use 111.195 km per
degree and longitude steps divide by cos(center latitude). The circular
clip itself uses the exact haversine distance from the center, so no point
outside radius R is ever emitted. Within R <= 25 miles and below about 60
degrees latitude, tangent-plane placement error stays under roughly 0.1
percent of the spacing; it grows toward the poles, so centers at or above
85 degrees latitude are rejected, matching radius_sampling.py.

Nested ladder and stable IDs
----------------------------
Spacing is continuous. A study picks any positive base spacing s0 (for
example 2.7 miles); each refinement halves it: s0, s0/2, s0/4, and so on,
with a hard floor of 0.5 miles. No rung below 0.5 miles is ever generated,
and a base below the floor is clamped to 0.5. Every point is identified by
integer coordinates (I, J) in the basis of the finest rung reachable from
s0, so the same physical point has the same origin_id at every rung:
origin_id = "hex_<I>_<J>". A coarse point (i, j) at spacing s reappears at
spacing s/2 as (2i, 2j), so halving s keeps every existing point exactly.
Rung membership of a point is every reachable spacing whose step divides
both I and J; first_rung_miles is the coarsest such spacing. The classic
4/2/1/0.5 ladder is the special case s0 = 4.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math

from competitive_sampling import haversine_km

MILE_KM = 1.609344
KM_PER_DEGREE = 111.195
FLOOR_MILES = 0.5
FINEST_MILES = FLOOR_MILES
EXAMPLE_SPACINGS = (4.0, 2.7, 2.0, 1.0, 0.5)
RUNGS = (4.0, 2.0, 1.0, 0.5)  # Backwards-compatible alias: the s0 = 4 ladder.
MAX_RADIUS_MILES = 25.0
STALE_AFTER_DAYS = 14
STANDARD_RATE_USD = 0.0006
_SQRT3 = math.sqrt(3.0)
# Axial neighbor steps in (I, J) unit coordinates, scaled by the rung step.
AXIAL_DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))
SETTINGS_KEYS = ("zoom", "depth", "language", "device")


def ladder_spacings(base_spacing: float) -> list[float]:
    """Reachable rungs from s0 by halving, never below the 0.5 mile floor."""
    if not math.isfinite(base_spacing) or base_spacing <= 0:
        raise ValueError("Base spacing s0 must be a positive finite number of miles")
    base = max(float(base_spacing), FLOOR_MILES)
    spacings = [base]
    while spacings[-1] / 2.0 >= FLOOR_MILES - 1e-12:
        spacings.append(spacings[-1] / 2.0)
    return spacings


def rank_class(rank) -> str:
    """Coarse rank classes used to spot cells where the picture changes."""
    if rank is None:
        return "not_found"
    if rank <= 3:
        return "top3"
    if rank <= 10:
        return "top10"
    if rank <= 20:
        return "top20"
    return "deep"


def point_id(unit_q: int, unit_r: int) -> str:
    """Stable ID encoding finest-rung lattice coordinates."""
    return f"hex_{int(unit_q)}_{int(unit_r)}"


def parse_point_id(origin_id: str) -> tuple[int, int]:
    parts = str(origin_id).split("_")
    if len(parts) != 3 or parts[0] != "hex":
        raise ValueError(f"Not a hex_radius point id: {origin_id!r}")
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        raise ValueError(f"Not a hex_radius point id: {origin_id!r}") from None


def rung_membership(unit_q: int, unit_r: int, base_spacing: float) -> list[float]:
    """Every reachable spacing at which this physical point exists, coarse first."""
    spacings = ladder_spacings(base_spacing)
    finest = spacings[-1]
    members = []
    for spacing in spacings:
        step = int(round(spacing / finest))
        if unit_q % step == 0 and unit_r % step == 0:
            members.append(spacing)
    return members


def _validate_center(lat: float, lng: float) -> None:
    if not (math.isfinite(lat) and math.isfinite(lng)) or not -85 < lat < 85 or not -180 <= lng <= 180:
        raise ValueError("Finite coordinates below polar latitudes required")


def _rung_index(base_spacing: float, spacing_miles: float) -> int:
    """Index of spacing_miles in the ladder from base_spacing, or raise."""
    spacings = ladder_spacings(base_spacing)
    for index, spacing in enumerate(spacings):
        if math.isclose(spacing, spacing_miles, rel_tol=0, abs_tol=1e-9):
            return index
    raise ValueError(f"Spacing {spacing_miles:g} is not on the ladder from s0={base_spacing:g}: {spacings}")


def hex_origins(lat: float, lng: float, radius_miles: float, spacing_miles: float,
                base_spacing: float | None = None) -> list[dict]:
    """Honeycomb lattice points inside the circle, centered exactly on (lat, lng).

    base_spacing is the study s0; it defaults to spacing_miles, which makes
    this point set its own finest basis. When a base is given, spacing must
    be one of its halved rungs so point IDs stay stable across the ladder.
    """
    _validate_center(lat, lng)
    if not (math.isfinite(radius_miles) and math.isfinite(spacing_miles)):
        raise ValueError("Radius and spacing must be finite")
    if not 0 < radius_miles <= MAX_RADIUS_MILES:
        raise ValueError(f"Require 0 < radius <= {MAX_RADIUS_MILES:g} miles (tangent-plane limit)")
    base = float(base_spacing) if base_spacing is not None else float(spacing_miles)
    _rung_index(base, spacing_miles)
    ladder = ladder_spacings(base)
    finest = ladder[-1]
    unit_step = int(round(spacing_miles / finest))
    # Bound axial candidates: axial rows reach R / (s * sqrt(3)/2), past R / s.
    bound = int(math.ceil(radius_miles / spacing_miles * 1.3)) + 2
    if (2 * bound + 1) ** 2 > 400_000:
        raise ValueError("Requested lattice exceeds candidate limit")
    cos_lat = math.cos(math.radians(lat))
    origins = []
    for r in range(-bound, bound + 1):
        for q in range(-bound, bound + 1):
            east_mi = spacing_miles * (q + r / 2.0)
            north_mi = spacing_miles * (_SQRT3 / 2.0 * r)
            if math.hypot(east_mi, north_mi) > radius_miles + spacing_miles:
                continue
            p_lat = round(lat + north_mi * MILE_KM / KM_PER_DEGREE, 7)
            p_lng = round(lng + east_mi * MILE_KM / (KM_PER_DEGREE * cos_lat), 7)
            distance = haversine_km(lat, lng, p_lat, p_lng)
            if distance > radius_miles * MILE_KM:
                continue
            unit_q, unit_r = q * unit_step, r * unit_step
            members = rung_membership(unit_q, unit_r, base)
            origins.append({
                "origin_id": point_id(unit_q, unit_r),
                "lat": p_lat, "lng": p_lng,
                "axial_q": q, "axial_r": r,
                "unit_q": unit_q, "unit_r": unit_r,
                "grid_x": q, "grid_y": r,
                "east_miles": round(east_mi, 6), "north_miles": round(north_mi, 6),
                "distance_from_target_km": distance,
                "base_spacing_miles": base, "spacing_miles": spacing_miles,
                "first_rung_miles": members[0] if members else spacing_miles,
                "rung_membership": members,
                "sampled_at": None, "scan_age_days": None, "stale": False,
                "phase": 1, "roles": ["hex_radius"],
            })
    origins.sort(key=lambda p: (p["unit_r"], p["unit_q"]))
    if point_id(0, 0) not in {p["origin_id"] for p in origins}:
        raise ValueError("Hex lattice lost its exact center point")
    return origins


def ladder_origins(lat: float, lng: float, radius_miles: float,
                   base_spacing: float) -> dict[float, list[dict]]:
    """Points at each rung from s0. Coarser rungs are exact ID subsets of finer rungs."""
    return {s: hex_origins(lat, lng, radius_miles, s, base_spacing=base_spacing)
            for s in ladder_spacings(base_spacing)}


def merged_ladder(lat: float, lng: float, radius_miles: float,
                  base_spacing: float) -> list[dict]:
    """Finest-rung points, each annotated with full rung membership."""
    ladder = ladder_origins(lat, lng, radius_miles, base_spacing)
    return ladder[ladder_spacings(base_spacing)[-1]]


def _point_in_polygon(lat: float, lng: float, polygon: list) -> bool:
    """Ray casting on the local (lng, lat) plane; fine at study scale."""
    inside = False
    count = len(polygon)
    for i in range(count):
        lat1, lng1 = polygon[i]
        lat2, lng2 = polygon[(i + 1) % count]
        if (lng1 > lng) != (lng2 > lng):
            cross_lat = lat1 + (lng - lng1) * (lat2 - lat1) / (lng2 - lng1)
            if lat < cross_lat:
                inside = not inside
    return inside


def changed_cells(coarse_points: list[dict], leaders=None, rank_classes=None) -> set[str]:
    """Coarse point IDs where the picture changes between neighbors.

    A point is changed when any of its six axial neighbors (that was also
    collected) carries a different leader or a different rank class.
    leaders and rank_classes map origin_id to the observed value.
    """
    if leaders is None and rank_classes is None:
        raise ValueError("changed_cells needs leaders and/or rank_classes")
    by_id = {p["origin_id"]: p for p in coarse_points}
    changed = set()
    for point in coarse_points:
        for dq, dr in AXIAL_DIRECTIONS:
            neighbor_id = point_id(point["unit_q"] + dq * _neighbor_step(point),
                                   point["unit_r"] + dr * _neighbor_step(point))
            if neighbor_id not in by_id:
                continue
            if leaders is not None and leaders.get(point["origin_id"]) != leaders.get(neighbor_id):
                if point["origin_id"] in leaders and neighbor_id in leaders:
                    changed.add(point["origin_id"])
            if rank_classes is not None and rank_classes.get(point["origin_id"]) != rank_classes.get(neighbor_id):
                if point["origin_id"] in rank_classes and neighbor_id in rank_classes:
                    changed.add(point["origin_id"])
    return changed


def _neighbor_step(point: dict) -> int:
    """Unit-coordinate step to the next point at this point's own spacing."""
    base = point["base_spacing_miles"]
    finest = ladder_spacings(base)[-1]
    return int(round(point["spacing_miles"] / finest))


def refinement_delta(lat: float, lng: float, radius_miles: float,
                     coarse_spacing: float, fine_spacing: float,
                     observed_ids, base_spacing: float | None = None,
                     region_polygon=None, leaders=None, rank_classes=None,
                     border_points=None) -> list[dict]:
    """Only the new points for the next rung. Observed IDs are never returned.

    Region limits (combinable):
    - region_polygon: list of (lat, lng) vertices; only new points inside.
    - leaders and/or rank_classes: observations on the coarse points. Only
      new points within one coarse spacing of a changed cell are returned,
      where a changed cell has a neighbor with a different leader or a
      different rank class (see changed_cells and rank_class).
    - border_points: (east_miles, north_miles) tangent-plane locations,
      for example a sibling branch; new points within one coarse spacing
      of any of them are also returned.
    """
    base = float(base_spacing) if base_spacing is not None else float(coarse_spacing)
    coarse_index = _rung_index(base, coarse_spacing)
    fine_index = _rung_index(base, fine_spacing)
    if not fine_index > coarse_index:
        raise ValueError("Refinement needs a finer rung below the coarse rung on the same ladder")
    observed = set(observed_ids)
    for origin_id in observed:
        parse_point_id(origin_id)
    fine = hex_origins(lat, lng, radius_miles, fine_spacing, base_spacing=base)
    new_points = [p for p in fine if p["origin_id"] not in observed]
    if region_polygon is not None:
        polygon = [(float(a), float(b)) for a, b in region_polygon]
        if len(polygon) < 3:
            raise ValueError("Region polygon needs at least three (lat, lng) vertices")
        new_points = [p for p in new_points if _point_in_polygon(p["lat"], p["lng"], polygon)]
    if leaders is not None or rank_classes is not None or border_points:
        coarse = hex_origins(lat, lng, radius_miles, coarse_spacing, base_spacing=base)
        coarse_by_id = {p["origin_id"]: p for p in coarse}
        anchors: list[tuple[float, float]] = []
        if leaders is not None or rank_classes is not None:
            changed = changed_cells(coarse, leaders=leaders, rank_classes=rank_classes)
            if not changed:
                return []
            anchors.extend((coarse_by_id[oid]["east_miles"], coarse_by_id[oid]["north_miles"])
                           for oid in changed)
        if border_points:
            anchors.extend((float(e), float(n)) for e, n in border_points)
        reach = coarse_spacing * 1.05
        new_points = [p for p in new_points
                      if any(math.hypot(p["east_miles"] - e, p["north_miles"] - n) <= reach
                             for e, n in anchors)]
    return new_points


def _as_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        return dt.date.fromisoformat(text[:10])


def stamp_scan_dates(points: list[dict], sampled_at, coarse_sampled_at=None) -> list[dict]:
    """Attach per-point scan date metadata; flag refinements older than 14 days.

    coarse_sampled_at is the coarse pass date. A point scanned more than
    STALE_AFTER_DAYS after it gets stale=True and scan_age_days set.
    """
    scan_date = _as_date(sampled_at)
    coarse_date = _as_date(coarse_sampled_at) if coarse_sampled_at is not None else None
    stamped = []
    for point in points:
        row = dict(point)
        row["sampled_at"] = scan_date.isoformat()
        if coarse_date is not None:
            age = (scan_date - coarse_date).days
            row["scan_age_days"] = age
            row["stale"] = age > STALE_AFTER_DAYS
        stamped.append(row)
    return stamped


def refinement_staleness(coarse_sampled_at, refinement_sampled_at) -> dict:
    age = (_as_date(refinement_sampled_at) - _as_date(coarse_sampled_at)).days
    return {"age_days": age, "stale": age > STALE_AFTER_DAYS, "threshold_days": STALE_AFTER_DAYS}


def normalize_settings(settings: dict) -> dict:
    """Canonical lock keys: zoom, depth, language, device.

    Accepts the repo spellings (zoom / provider_zoom, language_code /
    language) so study plans and adaptive configs compare equal.
    """
    if not isinstance(settings, dict):
        raise ValueError("Settings must be an object")
    normalized = {
        "zoom": settings.get("zoom", settings.get("provider_zoom")),
        "depth": settings.get("depth"),
        "language": settings.get("language_code", settings.get("language")),
        "device": settings.get("device"),
    }
    missing = [k for k, v in normalized.items() if v is None]
    if missing:
        raise ValueError(f"Settings lock needs: {', '.join(missing)}")
    return normalized


def settings_fingerprint(settings: dict) -> str:
    canonical = json.dumps(normalize_settings(settings), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_settings_lock(coarse_settings: dict, refinement_settings: dict) -> dict:
    """Reject a refinement whose zoom, depth, language or device differs."""
    coarse = normalize_settings(coarse_settings)
    refined = normalize_settings(refinement_settings)
    differing = [k for k in SETTINGS_KEYS if coarse[k] != refined[k]]
    if differing:
        raise ValueError("Refinement settings differ from coarse pass: " + ", ".join(differing))
    return coarse


def estimate(lat, lng, radius_miles, spacing_miles, queries=4, rate_usd=STANDARD_RATE_USD):
    """Point count and cost preview at the standard queue price."""
    if not isinstance(queries, int) or queries < 1 or not math.isfinite(rate_usd) or rate_usd <= 0:
        raise ValueError("Positive integer query count and finite positive task rate required")
    points = hex_origins(lat, lng, radius_miles, spacing_miles)
    return {"geometry": "hex_radius", "radius_miles": radius_miles, "spacing_miles": spacing_miles,
        "base_spacing_miles": points[0]["base_spacing_miles"] if points else spacing_miles,
        "locations": len(points), "queries": queries, "requests": len(points) * queries,
        "task_rate_usd": rate_usd, "estimated_scan_cost_usd": round(len(points) * queries * rate_usd, 6),
        "business_multiplier": 1,
        "basis": "One shared Maps request per coordinate and query at the standard queue price. Hex points are honeycomb centers clipped by exact haversine distance from the business."}


def _square_origins_count(lat, lng, radius_miles, spacing_miles) -> int:
    """Square lattice clipped to the circle; same math as radius_sampling."""
    _validate_center(lat, lng)
    n = math.ceil(radius_miles / spacing_miles)
    step = spacing_miles * MILE_KM / KM_PER_DEGREE
    count = 0
    for y in range(-n, n + 1):
        for x in range(-n, n + 1):
            p_lat = round(lat + y * step, 7)
            p_lng = round(lng + x * step / math.cos(math.radians(lat)), 7)
            if haversine_km(lat, lng, p_lat, p_lng) <= radius_miles * MILE_KM:
                count += 1
    return count


def _hexagon_count(lat, lng, radius_miles, spacing_miles) -> int:
    """Points inside a containing hexagon (apothem = radius) at this spacing."""
    bound = int(math.ceil(radius_miles / spacing_miles * 1.3)) + 2
    count = 0
    for r in range(-bound, bound + 1):
        for q in range(-bound, bound + 1):
            hex_distance = max(abs(q), abs(r), abs(q + r))
            if hex_distance * spacing_miles * _SQRT3 / 2.0 <= radius_miles + 1e-9:
                count += 1
    return count


def footprint_comparison(lat: float, lng: float, radius_miles: float, spacing_miles: float, queries: int = 1) -> dict:
    """Hex circle vs square and radius_grid at the same worst-case gap.

    Worst-case gap (distance to the nearest point) is s/sqrt(3) for the
    honeycomb and d/sqrt(2) for a square lattice, so the matched square
    spacing is d = s * sqrt(2/3). radius_grid is that same square lattice
    clipped to the circle, so its count equals the square count. The
    containing hexagon has apothem = radius.
    """
    hex_count = len(hex_origins(lat, lng, radius_miles, spacing_miles))
    matched_square_spacing = spacing_miles * math.sqrt(2.0 / 3.0)
    square_count = _square_origins_count(lat, lng, radius_miles, matched_square_spacing)
    hexagon_count = _hexagon_count(lat, lng, radius_miles, spacing_miles)
    def pct_fewer(part, whole):
        return round(100.0 * (whole - part) / whole, 2) if whole else 0.0
    return {
        "radius_miles": radius_miles, "spacing_miles": spacing_miles,
        "hex_circle_points": hex_count,
        "square_spacing_miles": round(matched_square_spacing, 6),
        "square_circle_points": square_count, "radius_grid_points": square_count,
        "hexagon_points": hexagon_count,
        "hex_vs_square_pct_fewer": pct_fewer(hex_count, square_count),
        "circle_vs_hexagon_pct_fewer": pct_fewer(hex_count, hexagon_count),
        "queries": queries,
        "hex_cost_usd": round(hex_count * queries * STANDARD_RATE_USD, 6),
        "square_cost_usd": round(square_count * queries * STANDARD_RATE_USD, 6),
    }


def cost_table(lat: float, lng: float, queries: int = 1,
               radii=(3, 5, 10, 15, 20, 25), spacings=EXAMPLE_SPACINGS) -> list[dict]:
    """Published count and cost table at the $0.0006 standard queue price.

    spacings are example base spacings s0 (the classic 4/2/1/0.5 plus the
    odd 2.7); each row counts a single pass at that spacing.
    """
    rows = []
    for radius in radii:
        for spacing in spacings:
            result = estimate(lat, lng, radius, spacing, queries=queries)
            rows.append({"radius_miles": radius, "spacing_miles": spacing,
                         "locations": result["locations"], "queries": queries,
                         "requests": result["requests"],
                         "estimated_scan_cost_usd": result["estimated_scan_cost_usd"]})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--radius-miles", type=float, default=15.0)
    parser.add_argument("--spacing-miles", type=float, default=2.0)
    parser.add_argument("--base-spacing", type=float, default=None,
                        help="Study s0; the spacing must be one of its halved rungs")
    parser.add_argument("--queries", type=int, default=1)
    parser.add_argument("--table", action="store_true", help="Print the full R by s count and cost table")
    parser.add_argument("--ladder", action="store_true", help="Print reachable rungs from the base spacing")
    parser.add_argument("--compare", action="store_true", help="Print hex vs square, radius_grid and hexagon counts")
    args = parser.parse_args()
    if args.table:
        print(json.dumps(cost_table(args.lat, args.lng, args.queries), indent=2))
    elif args.ladder:
        base = args.base_spacing if args.base_spacing is not None else args.spacing_miles
        print(json.dumps({"base_spacing_miles": base, "rungs_miles": ladder_spacings(base),
                          "counts": {str(s): len(hex_origins(args.lat, args.lng, args.radius_miles, s, base_spacing=base))
                                     for s in ladder_spacings(base)}}, indent=2))
    elif args.compare:
        print(json.dumps(footprint_comparison(args.lat, args.lng, args.radius_miles, args.spacing_miles, args.queries), indent=2))
    else:
        print(json.dumps(estimate(args.lat, args.lng, args.radius_miles, args.spacing_miles, args.queries), indent=2))

