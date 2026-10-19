#!/usr/bin/env python3
"""Radial Multi-Ring Trail-Off GeoGrid Runner for legends-geogrid.

Replaces rigid boxy square grids with a Concentric Radial Ring architecture:
- High-density zoomed-in inner rings (0.55 km, 1.20 km, 2.10 km) around the Target Citadel
  to capture sharp street-by-street rank transitions.
- Mid-corridor rings (3.30 km, 4.80 km, 6.80 km) to map neighborhood & commercial corridors.
- Outer trail-off frontier rings (9.50 km, 13.00 km) to map the full organic range and shape
  of both the Target Business and the Top 10 Competitors until ranking gravity trails off.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

import local_heatmap_poc as runner


# Default 9-ring radial trail-off geometry (173 coordinates total, 26 km diameter)
DEFAULT_RADIAL_RINGS: tuple[tuple[int, float, int], ...] = (
    # (ring_index, radius_km, point_count)
    (0, 0.00, 1),    # Center HQ Citadel
    (1, 0.55, 8),    # Street-Level Micro Core (every 45 deg)
    (2, 1.20, 12),   # Neighborhood Core (every 30 deg)
    (3, 2.10, 16),   # Immediate Contested Perimeter (every 22.5 deg)
    (4, 3.30, 20),   # Inner Suburban Ring (every 18 deg)
    (5, 4.80, 24),   # Mid-Corridor Ring (every 15 deg)
    (6, 6.80, 24),   # Regional Corridor Ring (every 15 deg)
    (7, 9.50, 24),   # Competitor Citadel Outer Ring (every 15 deg)
    (8, 13.00, 24),  # Metro Trail-Off Horizon Ring (every 15 deg)
)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


def generate_radial_points(
    center_lat: float,
    center_lng: float,
    rings: tuple[tuple[int, float, int], ...] = DEFAULT_RADIAL_RINGS,
) -> tuple[list[runner.GridPoint], dict[str, dict[str, Any]]]:
    """Generate concentric radial GridPoints and per-tag radial metadata."""
    lat_factor = 111.32
    lng_factor = 111.32 * math.cos(math.radians(center_lat))
    points: list[runner.GridPoint] = []
    radial_meta: dict[str, dict[str, Any]] = {}

    for ring_idx, radius_km, count in rings:
        if count == 1 or radius_km == 0.0:
            tag = "r0c0"
            pt = runner.GridPoint(row=0, col=0, lat=round(center_lat, 7), lng=round(center_lng, 7), tag=tag)
            points.append(pt)
            radial_meta[tag] = {
                "ring": 0,
                "spoke": 0,
                "spoke_count": 1,
                "ring_radius_km": 0.0,
                "bearing_deg": 0.0,
            }
            continue

        # Offset odd rings by half-step for hexagonal/staggered radial packing!
        step_deg = 360.0 / count
        phase_deg = (step_deg / 2.0) if (ring_idx % 2 == 1) else 0.0
        for spoke_idx in range(count):
            bearing_deg = (spoke_idx * step_deg + phase_deg) % 360.0
            # Bearing: 0 deg = North (+lat), 90 deg = East (+lng)
            rad = math.radians(bearing_deg)
            dy_km = radius_km * math.cos(rad)
            dx_km = radius_km * math.sin(rad)
            lat = round(center_lat + (dy_km / lat_factor), 7)
            lng = round(center_lng + (dx_km / lng_factor), 7)
            tag = f"r{ring_idx}c{spoke_idx}"
            pt = runner.GridPoint(row=ring_idx, col=spoke_idx, lat=lat, lng=lng, tag=tag)
            points.append(pt)
            radial_meta[tag] = {
                "ring": ring_idx,
                "spoke": spoke_idx,
                "spoke_count": count,
                "ring_radius_km": radius_km,
                "bearing_deg": round(bearing_deg, 2),
            }

    return points, radial_meta


def load_banked_tasks_by_keyword(bank_dirs: list[Path]) -> dict[str, list[tuple[float, float, dict[str, Any]]]]:
    """Load previously captured raw DataForSEO tasks keyed by normalized keyword."""
    bank: dict[str, list[tuple[float, float, dict[str, Any]]]] = {}
    for bdir in bank_dirs:
        if not bdir.exists():
            continue
        for raw_path in bdir.rglob("dataforseo-response.raw.json"):
            try:
                raw_data = json.loads(raw_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            for task in raw_data.get("tasks") or []:
                if int(task.get("status_code") or 0) >= 40000 and int(task.get("status_code") or 0) != runner.NO_SEARCH_RESULTS_STATUS:
                    continue
                tdata = task.get("data") or {}
                kw = str(tdata.get("keyword") or "").strip().lower()
                loc = str(tdata.get("location_coordinate") or "")
                parts = loc.split(",")
                if len(parts) >= 2 and kw:
                    try:
                        t_lat = float(parts[0])
                        t_lng = float(parts[1])
                        bank.setdefault(kw, []).append((t_lat, t_lng, task))
                    except ValueError:
                        pass
    return bank


def find_banked_task(
    bank_for_kw: list[tuple[float, float, dict[str, Any]]],
    lat: float,
    lng: float,
    tolerance_km: float = 0.22,
) -> dict[str, Any] | None:
    best_task = None
    best_dist = tolerance_km
    for b_lat, b_lng, task in bank_for_kw:
        d = haversine_km(lat, lng, b_lat, b_lng)
        if d <= best_dist:
            best_dist = d
            best_task = task
    return best_task


def fetch_live_tasks_parallel(
    tasks_to_fetch: list[dict[str, Any]],
    timeout: int = 45,
    max_workers: int = 28,
) -> dict[str, dict[str, Any]]:
    """Fetch DataForSEO live tasks in parallel using a thread pool."""
    results_by_tag: dict[str, dict[str, Any]] = {}
    if not tasks_to_fetch:
        return results_by_tag

    total = len(tasks_to_fetch)
    completed = 0
    t0 = time.time()

    def _worker(task: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        tag = str(task.get("tag") or "")
        for attempt in range(3):
            try:
                payload = runner.call_dataforseo_live_task(task, timeout=timeout)
                task_items = payload.get("tasks") or []
                if task_items:
                    returned_task = dict(task_items[0])
                    returned_task.setdefault("data", task)
                    returned_task["_api_cost"] = float(payload.get("cost") or returned_task.get("cost") or 0.0)
                    return tag, returned_task
            except Exception as exc:
                if attempt == 2:
                    return tag, {
                        "status_code": 50000,
                        "status_message": str(exc),
                        "data": task,
                        "result": [],
                        "cost": 0.0,
                        "_api_cost": 0.0,
                    }
                time.sleep(0.8 * (attempt + 1))
        return tag, {
            "status_code": 50000,
            "status_message": "No task returned",
            "data": task,
            "result": [],
            "cost": 0.0,
            "_api_cost": 0.0,
        }

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(_worker, t): t for t in tasks_to_fetch}
        for fut in as_completed(future_map):
            tag, returned_task = fut.result()
            results_by_tag[tag] = returned_task
            completed += 1
            if completed % 25 == 0 or completed == total:
                elapsed = time.time() - t0
                print(f"    [radial-live] {completed}/{total} tasks completed ({elapsed:.1f}s)", file=sys.stderr)

    return results_by_tag


def run_radial_study(
    *,
    business: dict[str, Any],
    lanes_spec: list[dict[str, Any]],
    output_dir: Path,
    bank_dirs: list[Path] | None = None,
    max_workers: int = 28,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    center_lat = float(business["lat"])
    center_lng = float(business["lng"])
    points, radial_meta = generate_radial_points(center_lat, center_lng, DEFAULT_RADIAL_RINGS)
    max_radius_km = max(r[1] for r in DEFAULT_RADIAL_RINGS)

    bank = load_banked_tasks_by_keyword((bank_dirs or []) + [output_dir])
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")

    report_lanes_cfg: list[dict[str, Any]] = []
    total_new_calls = 0
    total_reused_calls = 0
    total_cost_usd = 0.0

    for idx, lspec in enumerate(lanes_spec, start=1):
        query_id = str(lspec.get("query_id") or f"q{idx}")
        keyword = str(lspec["query"])
        label = str(lspec.get("label") or keyword)
        narrative = str(lspec.get("narrative") or "")

        lane_parent = output_dir / f"lane-{idx}"
        if lane_parent.exists():
            import shutil
            shutil.rmtree(lane_parent, ignore_errors=True)
        lane_dir = lane_parent / f"{stamp}-radial-{query_id}"
        lane_dir.mkdir(parents=True, exist_ok=True)

        args = runner.parse_args([
            "--keyword", keyword,
            "--target-name", str(business["name"]),
            "--target-domain", str(business.get("website") or business.get("domain") or ""),
            "--target-cid", str(business.get("cid") or ""),
            "--center-lat", str(center_lat),
            "--center-lng", str(center_lng),
            "--radius-km", str(max_radius_km),
            "--grid-size", "15",
            "--depth", "20",
            "--zoom", "14",
            "--method", "live",
        ])

        all_tasks = runner.build_tasks(args, points)
        kw_bank = bank.get(keyword.strip().lower(), [])

        reused_by_tag: dict[str, dict[str, Any]] = {}
        tasks_to_fetch: list[dict[str, Any]] = []

        for pt, task in zip(points, all_tasks):
            banked = find_banked_task(kw_bank, pt.lat, pt.lng, tolerance_km=0.22)
            if banked is not None:
                cloned = json.loads(json.dumps(banked))
                cloned["data"] = dict(task)
                cloned["tag"] = pt.tag
                reused_by_tag[pt.tag] = cloned
                total_reused_calls += 1
            else:
                tasks_to_fetch.append(task)
                total_new_calls += 1

        print(
            f"[Lane {idx}: '{keyword}'] {len(points)} radial points "
            f"({len(reused_by_tag)} banked, {len(tasks_to_fetch)} live calls)...",
            file=sys.stderr,
        )
        fetched_by_tag = fetch_live_tasks_parallel(tasks_to_fetch, timeout=45, max_workers=max_workers)

        ordered_tasks: list[dict[str, Any]] = []
        lane_cost = 0.0
        lane_errors = 0
        for pt in points:
            if pt.tag in reused_by_tag:
                t_obj = reused_by_tag[pt.tag]
            else:
                t_obj = fetched_by_tag[pt.tag]
                lane_cost += float(t_obj.pop("_api_cost", 0.0) or t_obj.get("cost") or 0.0)
            status_code = int(t_obj.get("status_code") or 0)
            if status_code >= 40000 and status_code != runner.NO_SEARCH_RESULTS_STATUS:
                lane_errors += 1
            ordered_tasks.append(t_obj)

        total_cost_usd += lane_cost
        raw_payload = {
            "version": "radial-trail-off-v1",
            "status_code": 20000,
            "status_message": "Ok.",
            "time": dt.datetime.now(dt.timezone.utc).isoformat(),
            "cost": round(lane_cost, 4),
            "tasks_count": len(ordered_tasks),
            "tasks_error": lane_errors,
            "tasks": ordered_tasks,
        }

        (lane_dir / "dataforseo-request-tasks.json").write_text(
            json.dumps(all_tasks, indent=2), encoding="utf-8"
        )
        (lane_dir / "dataforseo-response.raw.json").write_text(
            json.dumps(raw_payload, indent=2), encoding="utf-8"
        )

        parsed_results = runner.parse_results(raw_payload, points, args)
        m_settings = runner.measurement_settings(args)
        m_settings["geometry"] = "radial_concentric"
        m_settings["radial_rings"] = [
            {"ring": r_idx, "radius_km": r_km, "points": r_cnt}
            for r_idx, r_km, r_cnt in DEFAULT_RADIAL_RINGS
        ]

        results_serialized = []
        for r in parsed_results:
            rmeta = radial_meta.get(r.point.tag, {})
            pt_dict = {
                "row": r.point.row,
                "col": r.point.col,
                "lat": r.point.lat,
                "lng": r.point.lng,
                "tag": r.point.tag,
                "ring": rmeta.get("ring", r.point.row),
                "spoke": rmeta.get("spoke", r.point.col),
                "ring_radius_km": rmeta.get("ring_radius_km"),
                "bearing_deg": rmeta.get("bearing_deg"),
            }
            results_serialized.append({
                "point": pt_dict,
                "rank": r.rank,
                "status": r.status,
                "error": r.error,
                "returned_items_count": r.returned_items_count,
                "organic_items_count": r.organic_items_count,
                "observed_ranks": list(r.observed_ranks),
                "sampled_at": r.sampled_at,
                "matched_item": r.matched_item,
                "top_items": r.top_items,
            })

        parsed_grid_payload = {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "keyword": keyword,
            "target": business["name"],
            "measurement_settings": m_settings,
            "metrics": runner.calculate_metrics(parsed_results),
            "results": results_serialized,
        }
        parsed_grid_path = lane_dir / "parsed-grid.json"
        parsed_grid_path.write_text(json.dumps(parsed_grid_payload, indent=2), encoding="utf-8")

        report_lanes_cfg.append({
            "query_id": query_id,
            "query": keyword,
            "label": label,
            "narrative": narrative,
            "records_path": str(parsed_grid_path.relative_to(output_dir)),
        })

    report_cfg = {
        "schema": "legends-geogrid-report/v1",
        "business": business,
        "geometry": "radial_concentric",
        "lanes": report_lanes_cfg,
    }
    (output_dir / "report-config.json").write_text(json.dumps(report_cfg, indent=2), encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "points_per_lane": len(points),
        "lanes_count": len(lanes_spec),
        "total_serps": len(points) * len(lanes_spec),
        "new_live_calls": total_new_calls,
        "reused_banked_calls": total_reused_calls,
        "total_cost_usd": round(total_cost_usd, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a concentric radial trail-off study.")
    parser.add_argument("--source-study", required=True, help="Existing study dir with business & lane metadata")
    parser.add_argument("--output-dir", required=True, help="Output directory for radial study")
    parser.add_argument("--bank-dir", action="append", default=[], help="Directories to reuse banked raw tasks from")
    parser.add_argument("--workers", type=int, default=28, help="Concurrent live worker threads")
    args = parser.parse_args()

    src = Path(args.source_study).resolve()
    cfg = json.loads((src / "report-config.json").read_text(encoding="utf-8-sig"))
    business = cfg["business"]
    lanes_spec = cfg["lanes"]

    # Copy evidence directory if present so GBP metadata and profile review carry over
    src_ev = src / "evidence"
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if src_ev.is_dir():
        import shutil
        shutil.copytree(src_ev, out_dir / "evidence", dirs_exist_ok=True)

    bank_dirs = [src] + [Path(p).resolve() for p in args.bank_dir]
    receipt = run_radial_study(
        business=business,
        lanes_spec=lanes_spec,
        output_dir=out_dir,
        bank_dirs=bank_dirs,
        max_workers=args.workers,
    )
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
