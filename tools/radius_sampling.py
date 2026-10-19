"""Regular latitude/longitude lattice clipped to a geodesic radius."""
from __future__ import annotations
import argparse
import json
import math
from competitive_sampling import haversine_km

MILE_KM = 1.609344


def radial_origins(lat: float, lng: float, radius_miles: float, spacing_miles: float) -> list[dict]:
    values = (lat, lng, radius_miles, spacing_miles)
    if not all(math.isfinite(v) for v in values) or not -85 < lat < 85 or not -180 <= lng <= 180:
        raise ValueError("Finite coordinates below polar latitudes required")
    if not 0 < radius_miles <= 100 or not 0 < spacing_miles <= radius_miles:
        raise ValueError("Require 0 < spacing <= radius <= 100 miles")
    n = math.ceil(radius_miles / spacing_miles)
    if (2 * n + 1) ** 2 > 100000:
        raise ValueError("Requested lattice exceeds 100,000 candidate locations")
    step = spacing_miles * MILE_KM / 111.195
    origins = []
    for y in range(-n, n + 1):
        for x in range(-n, n + 1):
            p_lat = round(lat + y * step, 7)
            p_lng = round(lng + x * step / math.cos(math.radians(lat)), 7)
            distance = haversine_km(lat, lng, p_lat, p_lng)
            if distance <= radius_miles * MILE_KM:
                origins.append({"origin_id": f"r_{y+n:03}_{x+n:03}", "lat": p_lat, "lng": p_lng,
                    "grid_x": x, "grid_y": y, "distance_from_target_km": distance,
                    "phase": 1, "roles": ["radius_grid"]})
    return origins


def estimate(lat, lng, radius_miles, spacing_miles, queries=4, rate_usd=.0006):
    if not isinstance(queries, int) or queries < 1 or not math.isfinite(rate_usd) or rate_usd <= 0:
        raise ValueError("Positive integer query count and finite positive task rate required")
    points = radial_origins(lat, lng, radius_miles, spacing_miles)
    return {"radius_miles": radius_miles, "spacing_miles": spacing_miles,
        "locations": len(points), "queries": queries, "requests": len(points) * queries,
        "task_rate_usd": rate_usd, "estimated_scan_cost_usd": round(len(points) * queries * rate_usd, 6),
        "business_multiplier": 1, "basis": "One shared Maps request per coordinate and query; up to 30 organic listings. Research excluded. Radius tests measured origins, not polygon edges."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lng", type=float, required=True)
    parser.add_argument("--radius-miles", type=float, required=True)
    parser.add_argument("--spacing-miles", type=float, default=.5)
    parser.add_argument("--queries", type=int, default=4)
    parser.add_argument("--task-rate-usd", type=float, default=.0006, help="Standard queue default; Live explicitly uses 0.002")
    args = parser.parse_args()
    print(json.dumps(estimate(args.lat, args.lng, args.radius_miles, args.spacing_miles, args.queries, args.task_rate_usd), indent=2))
