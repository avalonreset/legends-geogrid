"""Create a regular, primary-centered lattice using an existing researched plan."""
import argparse
import copy
import json
import math
from pathlib import Path

from competitive_collect import adapt_plan, compute_cost


def lattice_plan(source, size=21, spacing_km=1.0, method="standard"):
    if not isinstance(size, int) or size < 3 or size > 51 or size % 2 != 1:
        raise ValueError("Size must be odd, from 3 to 51")
    if not math.isfinite(spacing_km) or not 0.1 <= spacing_km <= 5:
        raise ValueError("Spacing must be 0.1 to 5 km")
    plan = copy.deepcopy(source)
    if method not in ("standard", "live"):
        raise ValueError("Choose standard or explicitly request live")
    plan["measurement_settings"]["method"] = method
    target = plan["target_business"]
    lat, lng = target["lat"], target["lng"]
    if abs(lat) >= 85:
        raise ValueError("This local lattice requires a center below 85 degrees latitude")
    half = size // 2
    # Constant latitude and longitude increments preserve aligned rows and columns.
    lat_step = spacing_km / 111.195
    lng_step = lat_step / math.cos(math.radians(lat))
    plan["origins"] = [
        {"origin_id": f"grid_r{row:02}_c{col:02}",
         "lat": round(lat + (half - row) * lat_step, 7),
         "lng": round(lng + (col - half) * lng_step, 7),
         "phase": 1, "roles": ["regular_grid"], "anchor_factions": ["TARGET"]}
        for row in range(size) for col in range(size)
    ]
    tasks = size * size * len(plan["query_selection"])
    cost = compute_cost(tasks, plan["measurement_settings"]["depth"], method)
    plan["sampling_parameters"] = {
        "geometry": "square_grid", "grid_size": size, "spacing_km": spacing_km,
        "half_width_km": half * spacing_km,
        "description": f"{size} × {size} grid · {spacing_km:g} km spacing",
        "rationale": "A common regular lattice centered on the primary business, covering the competitor comparison area. Extent is a measurement window, not a market boundary.",
    }
    plan["phases"] = [{"phase": 1, "name": "Shared regular grid", "origins_count": size * size,
                       "total_tasks": tasks, "estimated_cost_usd": cost}]
    plan["summary"] = {"total_deduplicated_origins": size * size, "total_queries": len(plan["query_selection"]),
                       "total_tasks": tasks, "total_estimated_cost_usd": cost}
    # Irregular-plan analysis does not describe this independent lattice.
    for key in ("truncation_analysis", "execution_adapter"):
        plan.pop(key, None)
    adapt_plan(plan)
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=21)
    parser.add_argument("--spacing-km", type=float, default=1.0)
    parser.add_argument("--method", choices=("standard", "live"), default="standard")
    args = parser.parse_args()
    plan = lattice_plan(json.loads(args.source_plan.read_text(encoding="utf-8-sig")), args.size, args.spacing_km, args.method)
    args.output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan["summary"], indent=2))
