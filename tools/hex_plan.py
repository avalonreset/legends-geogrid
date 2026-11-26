"""Create a hex_radius study plan from an existing researched plan.

Mirrors lattice_sampling.lattice_plan (square_grid) and the radius_grid
path in radius_compose.py: the plan carries origins plus
sampling_parameters with a geometry tag, per-rung phases, and a summary
costed at the standard queue price. No network or paid calls here.

The ladder is continuous: base_spacing_miles is the study s0 (any positive
value, for example 2.7 miles). The coarse pass collects at s0; each later
refinement halves the spacing down to the 0.5 mile floor, reusing the same
point IDs, so a refinement never rescans a collected point.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from competitive_collect import adapt_plan, compute_cost
from hex_sampling import MILE_KM, hex_origins, ladder_spacings, validate_settings_lock
from study import _safe_local_path


def hex_plan(source, radius_miles=15.0, base_spacing_miles=2.7, method="standard",
             settings=None):
    """Return a new plan whose origins form a hex_radius ladder footprint.

    Origins are the coarse pass at s0. Phases list every reachable rung
    (s0, s0/2, s0/4, down to the 0.5 mile floor) with cumulative origin
    counts, so the full ladder cost is visible before any collection.
    settings, when given, is the locked scan settings record (zoom, depth,
    language, device) stored on the plan for refinement checks.
    """
    if method not in ("standard", "live"):
        raise ValueError("Choose standard or explicitly request live")
    plan = copy.deepcopy(source)
    plan["measurement_settings"]["method"] = method
    target = plan["target_business"]
    lat, lng = target["lat"], target["lng"]
    rungs = ladder_spacings(base_spacing_miles)
    base = rungs[0]
    origins = hex_origins(lat, lng, radius_miles, base, base_spacing=base)
    plan["origins"] = origins
    phases = []
    seen: set[str] = set()
    for index, rung in enumerate(rungs, 1):
        rung_points = hex_origins(lat, lng, radius_miles, rung, base_spacing=base)
        new_points = [p for p in rung_points if p["origin_id"] not in seen]
        seen.update(p["origin_id"] for p in rung_points)
        tasks = len(rung_points) * len(plan["query_selection"])
        phases.append({"phase": index, "name": f"Hex ladder rung {rung:g} mi",
                       "spacing_miles": rung, "origins_count": len(rung_points),
                       "new_origins_count": len(new_points), "total_tasks": tasks,
                       "estimated_cost_usd": compute_cost(tasks, plan["measurement_settings"]["depth"], method)})
    plan["phases"] = phases
    tasks = len(origins) * len(plan["query_selection"])
    plan["sampling_parameters"] = {
        "geometry": "hex_radius", "radius_km": radius_miles * MILE_KM,
        "radius_miles": radius_miles, "spacing_km": base * MILE_KM,
        "spacing_miles": base, "base_spacing_miles": base,
        "ladder_rungs_miles": rungs,
        "center": {"lat": lat, "lng": lng},
        "description": f"{radius_miles:g} mi radius, honeycomb base spacing {base:g} mi, ladder {', '.join(f'{s:g}' for s in rungs)} mi",
        "rationale": "Honeycomb lattice centered exactly on the primary business, clipped by geodesic distance. The ladder halves from s0 down to the 0.5 mile floor and coarse rungs are exact subsets of finer rungs, so refinement never rescans an observed point.",
    }
    if settings is not None:
        plan["sampling_parameters"]["settings_lock"] = validate_settings_lock(settings, settings)
        plan["sampling_parameters"]["settings_fingerprint_source"] = "hex_plan"
    plan["summary"] = {"total_deduplicated_origins": len(origins),
                       "total_queries": len(plan["query_selection"]),
                       "total_tasks": tasks,
                       "total_estimated_cost_usd": compute_cost(tasks, plan["measurement_settings"]["depth"], method)}
    for key in ("truncation_analysis", "execution_adapter"):
        plan.pop(key, None)
    adapt_plan(plan)
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--radius-miles", type=float, default=15.0)
    parser.add_argument("--base-spacing", type=float, default=2.7)
    parser.add_argument("--method", choices=("standard", "live"), default="standard")
    args = parser.parse_args(argv)
    source_path = _safe_local_path(args.source_plan)
    output_path = _safe_local_path(args.output)
    source = json.loads(source_path.read_text(encoding="utf-8-sig"))
    plan = hex_plan(source, args.radius_miles, args.base_spacing, args.method)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
