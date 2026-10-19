#!/usr/bin/env python3
"""Lean safe collector for multi-competitor irregular GeoGrid study.

Enforces preflight spend gates, immutable request/response persistence,
append-only reservation ledgers, and exact request resumption without repurchasing.
Produces battlefield.py-compatible lane outputs and report configs with bounded concurrency.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import local_heatmap_poc as runner
from study_contract import digest, validate as validate_study_plan
from competitive_queue import POST_ENDPOINT, load_submissions, process_queue
from visibility_policy import validate_visibility_policy

ENDPOINT = "/serp/google/maps/live/advanced"
LIVE_TASK_RATE_USD = 0.002
DEFAULT_WORKERS = 6


def adapt_plan(raw_plan: dict[str, Any], phase_filter: int | None = None) -> dict[str, Any]:
    """Adapt competitive_sampling.py output or flexible contract dictionary into normalized schema."""
    b_raw = raw_plan.get("target_business") or raw_plan.get("business") or {}
    if not isinstance(b_raw, dict) or not str(b_raw.get("name") or "").strip():
        raise ValueError("Plan missing valid business.name")
    business = {
        "name": str(b_raw["name"]).strip(), "lat": float(b_raw["lat"]), "lng": float(b_raw["lng"]),
        "cid": str(b_raw["cid"]).strip() if b_raw.get("cid") else None,
        "place_id": str(b_raw["place_id"]).strip() if b_raw.get("place_id") else None,
        "domain": str(b_raw["domain"]).strip() if b_raw.get("domain") else None,
        "location": str(b_raw.get("location_label") or b_raw.get("location") or b_raw.get("address") or "").strip(),
        "website": b_raw.get("website") or b_raw.get("domain"),
    }

    q_list = raw_plan.get("query_selection") or raw_plan.get("queries") or []
    if not isinstance(q_list, list) or not q_list:
        raise ValueError("Plan queries list cannot be empty")
    queries = []
    for idx, item in enumerate(q_list, start=1):
        if isinstance(item, str):
            q_str, q_id, label, narrative = item.strip(), f"q{idx}", item.strip(), ""
        elif isinstance(item, dict):
            q_str = str(item.get("query") or item.get("keyword") or "").strip()
            q_id = str(item.get("query_id") or item.get("id") or f"q{idx}").strip()
            label = str(item.get("label") or q_str).strip()
            narrative = str(item.get("narrative") or item.get("reason") or "").strip()
        else:
            raise ValueError(f"Invalid query entry: {item}")
        if not q_str:
            raise ValueError(f"Query text required for query item {idx}")
        queries.append({"query_id": q_id, "query": q_str, "label": label, "narrative": narrative})

    s_raw = raw_plan.get("measurement_settings") or raw_plan.get("collection_settings") or raw_plan.get("settings") or {}
    settings = {
        "depth": int(s_raw.get("depth", 30)), "zoom": int(s_raw.get("zoom", 14)),
        "device": str(s_raw.get("device", "desktop")), "language_code": str(s_raw.get("language_code", "en")),
        "se_domain": str(s_raw.get("se_domain", "google.com")),
        "search_this_area": bool(s_raw.get("search_this_area", False)), "search_places": False,
        "method": str(s_raw.get("method", "standard")),
    }

    orig_list = raw_plan.get("origins") or []
    if not isinstance(orig_list, list) or not orig_list:
        raise ValueError("Plan origins list cannot be empty")
    origins = []
    for idx, orig in enumerate(orig_list, start=1):
        phase = int(orig.get("phase", 1))
        if phase_filter is not None and phase != phase_filter:
            continue
        origins.append({
            "tag": str(orig.get("origin_id") or orig.get("tag") or f"csp_{idx:03d}").strip(),
            "lat": float(orig["lat"]), "lng": float(orig["lng"]), "phase": phase,
            "roles": list(orig.get("roles") or ([orig["role"]] if orig.get("role") else [])),
        })
    if not origins:
        raise ValueError(f"No origins matching phase {phase_filter}")
    for entry in [business, *origins]:
        if not (math.isfinite(entry["lat"]) and -90 < entry["lat"] < 90
                and math.isfinite(entry["lng"]) and -180 <= entry["lng"] <= 180):
            raise ValueError("Coordinates must be finite and in geographic range")
    for entries, key in ((queries, "query_id"), (origins, "tag")):
        values = [entry[key] for entry in entries]
        if len(values) != len(set(values)) or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", v) for v in values):
            raise ValueError(f"Unique safe {key} values required")
    if len({q["query"].casefold() for q in queries}) != len(queries):
        raise ValueError("Duplicate queries are not allowed")
    if not 1 <= settings["depth"] <= 100 or not 3 <= settings["zoom"] <= 21:
        raise ValueError("Depth must be 1..100 and zoom 3..21")
    if settings["method"] not in ("standard", "live") or settings["device"] not in ("desktop", "mobile"):
        raise ValueError("Collector supports standard/live desktop/mobile requests only")
    if not isinstance(s_raw.get("search_this_area", False), bool) or s_raw.get("search_places", False) is not False:
        raise ValueError("Explicit boolean Maps search controls required")

    return {
        "business": business, "queries": queries, "settings": settings, "origins": origins,
        "source_study_plan": raw_plan.get("source_study_plan"), "raw_plan": raw_plan,
    }


def validate_lineage(
    adapted: dict[str, Any],
    study_plan_path: str | Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate researched study plan source lineage via study_contract / tools/study.py."""
    target_sp = study_plan_path or adapted.get("source_study_plan")
    if not target_sp:
        return None, None
    sp_file = Path(target_sp).resolve()
    if not sp_file.is_file():
        raise FileNotFoundError(f"Study plan not found at {sp_file}")

    sp_data, receipt = validate_study_plan(sp_file)
    adapted["source_study_plan"] = str(sp_file)
    b_plan, b_sp = adapted["business"], sp_data.get("business") or {}
    if runner.normalize(b_plan["name"]) != runner.normalize(b_sp.get("name")):
        raise ValueError(f"Business mismatch with study plan: {b_plan['name']} != {b_sp.get('name')}")
    for key in ("cid", "place_id", "domain"):
        if key == "place_id" and not b_sp.get(key):
            continue
        if str(b_plan.get(key) or "").strip() != str(b_sp.get(key) or "").strip():
            raise ValueError(f"{key} mismatch with study plan")
    for key in ("lat", "lng"):
        if abs(float(b_plan[key]) - float(b_sp[key])) > 0.000001:
            raise ValueError(f"{key} mismatch with study plan")

    sp_queries = {q["query"].strip().lower() for q in (sp_data.get("queries") or []) if q.get("selected")}
    for q in adapted["queries"]:
        if q["query"].strip().lower() not in sp_queries:
            raise ValueError(f"Query '{q['query']}' not found among selected queries in study plan")

    return sp_data, receipt


def make_task_payload(keyword: str, orig: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    task = {
        "keyword": keyword, "location_coordinate": f"{orig['lat']:.7f},{orig['lng']:.7f},{settings['zoom']}z",
        "depth": settings["depth"], "device": settings["device"],
        "language_code": settings["language_code"], "se_domain": settings["se_domain"],
        "search_this_area": settings["search_this_area"], "search_places": False, "tag": orig["tag"],
    }
    if settings["method"] == "standard":
        task["priority"] = 1
    return task


def fingerprint_task(task: dict[str, Any], endpoint: str = ENDPOINT) -> str:
    return hashlib.sha256(json.dumps([endpoint, task], sort_keys=True).encode("utf-8")).hexdigest()


def load_ledger(ledger_path: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Parse immutable ledger: returns (completed_responses_by_fp, uncompleted_reserved_fps)."""
    if not ledger_path.is_file():
        return {}, set()
    completed: dict[str, dict[str, Any]] = {}
    reserved: set[str] = set()
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        fp = entry["request_sha256"]
        if entry["event"] == "reserve":
            reserved.add(fp)
        elif entry["event"] == "response":
            envelope_path = ledger_path.parent / "responses" / f"{fp}.json"
            if not envelope_path.is_file() or digest(envelope_path) != entry.get("envelope_sha256"):
                raise ValueError("Saved response missing or changed; inspect run before resuming")
            completed[fp] = entry["response"]
    return completed, reserved - set(completed.keys()) - set(load_submissions(ledger_path))


def compute_cost(task_count: int, depth: int, method: str = "standard") -> float:
    return round(task_count * {"standard": .0006, "live": LIVE_TASK_RATE_USD}[method] * max(1, math.ceil(depth / 100)), 4)


def collect(
    *,
    plan_path: str | Path,
    output_dir: str | Path,
    execute: bool = False,
    confirm_cost_usd: float = 0.0,
    phase: int | None = None,
    study_plan_path: str | Path | None = None,
    max_workers: int = DEFAULT_WORKERS,
    allow_live: bool = False,
) -> dict[str, Any]:
    if not math.isfinite(confirm_cost_usd) or confirm_cost_usd < 0:
        raise ValueError("Budget must be finite and nonnegative")
    if not 1 <= max_workers <= 12:
        raise ValueError("Workers must be in 1..12")
    plan_file = Path(plan_path).resolve()
    raw_plan = json.loads(plan_file.read_text(encoding="utf-8-sig"))
    adapted = adapt_plan(raw_plan, phase_filter=phase)
    b, s, queries, origins = adapted["business"], adapted["settings"], adapted["queries"], adapted["origins"]
    if execute and s["method"] == "live" and not allow_live:
        raise ValueError("Live requires explicit user choice and --allow-live; use Standard queue by default")
    endpoint = POST_ENDPOINT if s["method"] == "standard" else ENDPOINT
    sp_data, sp_receipt = validate_lineage(adapted, study_plan_path)

    out_path = Path(output_dir).resolve()
    ledger_file = out_path / "collection-ledger.jsonl"
    completed_fps, ambiguous_fps = load_ledger(ledger_file)
    submissions = load_submissions(ledger_file)
    if ambiguous_fps:
        raise ValueError(
            f"Ambiguous uncompleted reservation detected for request {next(iter(ambiguous_fps))}; "
            "inspect saved state, do not resubmit"
        )

    saved_plan_file = out_path / "competitive-plan.json"
    current_plan_hash = digest(plan_file)
    if saved_plan_file.is_file() and digest(saved_plan_file) != current_plan_hash:
        raise ValueError("Plan content mismatch with existing run in output directory")

    lane_tasks: list[tuple[dict[str, Any], list[tuple[dict[str, Any], str]]]] = []
    total_tasks, new_tasks = 0, 0
    for q in queries:
        tasks_in_lane: list[tuple[dict[str, Any], str]] = []
        for orig in origins:
            t = make_task_payload(q["query"], orig, s)
            fp = fingerprint_task(t, endpoint)
            total_tasks += 1
            if fp not in completed_fps and fp not in submissions:
                new_tasks += 1
            tasks_in_lane.append((t, fp))
        lane_tasks.append((q, tasks_in_lane))

    est_cost = compute_cost(new_tasks, s["depth"], s["method"])
    receipt: dict[str, Any] = {
        "status": "estimate_only" if not execute else "collected",
        "output_dir": str(out_path), "target": b["name"],
        "total_origins": len(origins), "lanes_count": len(queries),
        "total_tasks": total_tasks, "reused_tasks": total_tasks - new_tasks,
        "new_tasks": new_tasks, "estimated_cost_usd": est_cost,
        "plan_sha256": current_plan_hash, "study_plan_validated": bool(sp_receipt),
        "method": s["method"], "unit_cost_usd": compute_cost(1, s["depth"], s["method"]),
        "pending_tasks": len(set(submissions) - set(completed_fps)),
    }

    if new_tasks:
        validate_visibility_policy(s, raw_plan.get("collection_policy"), raw_plan.get("diagnostic"))
    if not execute:
        return receipt

    if not sp_receipt:
        raise ValueError("Execution requires a validated source study plan")
    if est_cost > confirm_cost_usd:
        raise ValueError(f"Estimated cost ${est_cost:.4f} exceeds confirmed budget ${confirm_cost_usd:.4f}")

    out_path.mkdir(parents=True, exist_ok=True)
    if not saved_plan_file.is_file():
        saved_plan_file.write_bytes(plan_file.read_bytes())

    lock_file = out_path / ".collector-lock"
    try:
        with lock_file.open("x") as f:
            f.write(current_plan_hash)
    except FileExistsError:
        raise ValueError("Collection folder busy; inspect lock before recovery") from None

    actual_total_cost = 0.0
    report_lanes: list[dict[str, Any]] = []
    effective_workers = max(1, min(max_workers, 12))

    try:
        from legends_dataforseo import api_request
        # Re-read state under the exclusive lock; another process may have finished
        # between preflight and acquisition.
        if load_ledger(ledger_file) != (completed_fps, ambiguous_fps):
            raise ValueError("Ledger changed during preflight; rerun to resume safely")
        if load_submissions(ledger_file) != submissions:
            raise ValueError("Queue ledger changed during preflight; rerun safely")
        response_dir = out_path / "responses"
        request_dir = out_path / "requests"
        response_dir.mkdir(exist_ok=True)
        request_dir.mkdir(exist_ok=True)

        def append_event(entry: dict[str, Any]) -> None:
            with ledger_file.open("a", encoding="utf-8") as lf:
                lf.write(json.dumps(entry, allow_nan=False) + "\n")
                lf.flush()
                os.fsync(lf.fileno())

        def _fetch_task(task_fp_pair: tuple[dict[str, Any], str]) -> tuple[str, dict[str, Any], dict[str, Any]]:
            t_item, t_fp = task_fp_pair
            try:
                resp = api_request(ENDPOINT, [t_item], timeout=90, confirm=True, consumer="legends-geogrid",
                                   estimated_cost_usd=compute_cost(1, s["depth"], s["method"]),
                                   max_cost_usd=compute_cost(1, s["depth"], s["method"]))
            except Exception as exc:
                if isinstance(getattr(exc, "response", None), dict):
                    return t_fp, exc.response, t_item
                raise
            return t_fp, resp, t_item

        def normalize_response(resp: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
            resp_tasks = resp.get("tasks") or []
            if len(resp_tasks) != 1:
                raise ValueError(f"Provider returned unexpected task envelope for tag {request['tag']}")
            t_res = dict(resp_tasks[0])
            t_res.setdefault("data", request)
            t_res["tag"] = request["tag"]
            t_res["_actual_cost"] = float(resp.get("cost") or t_res.get("cost") or 0.0)
            if not math.isfinite(t_res["_actual_cost"]) or t_res["_actual_cost"] < 0:
                raise ValueError("Invalid provider cost")
            return t_res

        def successful(response: dict[str, Any]) -> bool:
            return response.get("status_code") in (20000, runner.NO_SEARCH_RESULTS_STATUS)

        if any(not successful(t) for t in completed_fps.values()):
            raise ValueError("Saved provider failure requires inspection; no automatic repurchase")

        def check_plan():
            if digest(plan_file) != current_plan_hash or digest(Path(adapted["source_study_plan"])) != sp_receipt["plan_sha256"]:
                raise ValueError("Source plan changed during collection")

        if s["method"] == "standard":
            actual_total_cost = process_queue(
                tasks=[pair for _, pairs in lane_tasks for pair in pairs],
                completed=completed_fps, submissions=submissions, output=out_path,
                append_event=append_event, api_request=api_request, check_plan=check_plan,
                budget=confirm_cost_usd, task_cost=compute_cost(1, s["depth"], "standard"),
                workers=effective_workers, normalize=normalize_response,
            )
            receipt["pending_tasks"] = total_tasks - len(completed_fps)
            if receipt["pending_tasks"]:
                receipt.update(status="queued", completed_tasks=len(completed_fps),
                               actual_cost_usd=actual_total_cost,
                               run_total_cost_usd=round(sum(e["actual_usd"] for e in submissions.values()), 6))
                (out_path / "collection-summary.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                return receipt

        for lane_idx, (q, tasks_in_lane) in enumerate(lane_tasks, start=1):
            if sp_receipt and digest(Path(adapted["source_study_plan"]).resolve()) != sp_receipt["plan_sha256"]:
                raise ValueError("Source study plan changed during collection")

            lane_dir = out_path / f"lane-{lane_idx}"
            lane_dir.mkdir(parents=True, exist_ok=True)

            pending_items = [(t, fp) for t, fp in tasks_in_lane if fp not in completed_fps]

            # Process pending tasks in safe bounded groups of effective_workers
            for chunk_idx in range(0, len(pending_items), effective_workers):
                chunk = pending_items[chunk_idx : chunk_idx + effective_workers]
                check_plan()
                if (out_path / "STOP").exists():
                    raise ValueError("STOP requested; no further Live requests")
                if actual_total_cost + compute_cost(len(chunk), s["depth"], s["method"]) > confirm_cost_usd + 1e-9:
                    raise ValueError("Actual cost plus next reservations exceeds confirmed budget")
                # Main thread records reservations for the entire chunk before dispatch
                for task, fp in chunk:
                    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
                    with (request_dir / f"{fp}.json").open("x", encoding="utf-8") as req:
                        req.write(json.dumps({"endpoint": ENDPOINT, "tasks": [task]}, indent=2))
                    append_event({
                        "event": "reserve", "request_sha256": fp, "tag": task["tag"],
                        "reserved_usd": compute_cost(1, s["depth"], s["method"]), "observed_at": stamp,
                    })

                # Concurrently execute bounded chunk without auto-retry
                failures = []
                with ThreadPoolExecutor(max_workers=len(chunk)) as pool:
                    future_map = {pool.submit(_fetch_task, item): item for item in chunk}
                    for fut in as_completed(future_map):
                        try:
                            fp, envelope, request = fut.result()
                            response_path = response_dir / f"{fp}.json"
                            with response_path.open("x", encoding="utf-8") as raw:
                                raw.write(json.dumps(envelope, ensure_ascii=False, allow_nan=False))
                            task_result = normalize_response(envelope, request)
                        except Exception as exc:
                            failures.append(f"{type(exc).__name__}: response incomplete; inspect reserved request")
                            continue
                        actual_total_cost += task_result["_actual_cost"]
                        stamp_resp = dt.datetime.now(dt.timezone.utc).isoformat()
                        append_event({
                            "event": "response", "request_sha256": fp, "tag": task_result["tag"],
                            "reserved_usd": compute_cost(1, s["depth"], s["method"]), "actual_usd": task_result["_actual_cost"],
                            "observed_at": stamp_resp, "envelope_sha256": digest(response_path),
                            "response": task_result,
                        })
                        completed_fps[fp] = task_result
                        if envelope.get("status_code") != 20000 or not successful(task_result):
                            failures.append(f"Provider status {task_result.get('status_code')}; inspect saved response")
                if failures:
                    raise ValueError("; ".join(failures))
                if actual_total_cost > confirm_cost_usd + 1e-9:
                    raise ValueError("Provider cost exceeded estimate; stopped before further requests")

            lane_results = [completed_fps[fp] for _, fp in tasks_in_lane]
            now_utc = dt.datetime.now(dt.timezone.utc).isoformat()
            raw_payload = {
                "version": f"competitive-{s['method']}-v1", "status_code": 20000, "status_message": "Ok.", "time": now_utc,
                "cost": round(sum(float(t.get("_actual_cost", 0.0) or t.get("cost", 0.0)) for t in lane_results), 4),
                "tasks_count": len(lane_results),
                "tasks_error": sum(1 for t in lane_results if not successful(t)),
                "tasks": lane_results,
            }
            (lane_dir / "dataforseo-request-tasks.json").write_text(
                json.dumps([t for t, _ in tasks_in_lane], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            (lane_dir / "dataforseo-response.raw.json").write_text(
                json.dumps(raw_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

            # Runner normalization helper for battlefield compatibility
            sampling = raw_plan.get("sampling_parameters", {})
            geometry = sampling.get("geometry", "competitive_irregular")
            grid_size = int(sampling.get("grid_size", len(origins)))
            regular = geometry == "square_grid" and grid_size * grid_size == len(origins)
            points = [runner.GridPoint(row=idx // grid_size if regular else idx,
                                       col=idx % grid_size if regular else 0,
                                       lat=orig["lat"], lng=orig["lng"], tag=orig["tag"])
                      for idx, orig in enumerate(origins)]
            runner_args = argparse.Namespace(
                keyword=q["query"], target_name=b["name"], target_cid=b.get("cid"),
                target_place_id=b.get("place_id"), target_domain=b.get("domain"),
                center_lat=b["lat"], center_lng=b["lng"],
                radius_km=sampling.get("half_width_km", 0.0), grid_size=grid_size,
                depth=s["depth"], zoom=s["zoom"], device=s["device"], language_code=s["language_code"],
                se_domain=s["se_domain"], search_this_area=s["search_this_area"], search_places=False,
                match_threshold=0.72, top_competitors=s["depth"], method=s["method"], location_label=b.get("location") or "",
            )
            parsed_pts = runner.parse_results(raw_payload, points, runner_args)
            m_settings = runner.measurement_settings(runner_args)
            m_settings["geometry"] = geometry
            if regular:
                m_settings["spacing_km"] = sampling["spacing_km"]

            parsed_grid_payload = {
                "target": b["name"], "generated_at": now_utc, "keyword": q["query"],
                "location": b.get("location") or "", "measurement_settings": m_settings,
                "metrics": runner.calculate_metrics(parsed_pts),
                "results": [
                    {
                        "point": {
                            "row": r.point.row, "col": r.point.col, "lat": r.point.lat, "lng": r.point.lng, "tag": r.point.tag,
                            "phase": origins[idx]["phase"], "roles": origins[idx]["roles"],
                        },
                        "rank": r.rank, "matched_item": r.matched_item, "top_items": r.top_items,
                        "error": r.error, "status": r.status, "returned_items_count": r.returned_items_count,
                        "organic_items_count": r.organic_items_count, "observed_ranks": list(r.observed_ranks),
                        "sampled_at": r.sampled_at,
                    }
                    for idx, r in enumerate(parsed_pts)
                ],
            }
            (lane_dir / "parsed-grid.json").write_text(
                json.dumps(parsed_grid_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            report_lanes.append({
                "query_id": q["query_id"], "query": q["query"], "label": q["label"],
                "narrative": q["narrative"] or f"Irregular competitive probe for {q['query']}",
                "records_path": f"lane-{lane_idx}/parsed-grid.json",
            })

        report_cfg = {
            "schema_version": 1, "synthetic": False,
            "business": {
                "name": b["name"], "cid": b.get("cid"), "place_id": b.get("place_id"), "domain": b.get("domain"),
                "website": b.get("website") or b.get("domain"), "lat": b["lat"], "lng": b["lng"],
                "location": b.get("location") or "",
            },
            "thesis": "Shared-location competitive ranking study.",
            "geometry": raw_plan.get("sampling_parameters", {}).get("geometry", "competitive_irregular"),
            "lanes": report_lanes,
        }
        (out_path / "report-config.json").write_text(
            json.dumps(report_cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        receipt["actual_cost_usd"] = round(actual_total_cost, 4)
        receipt["run_total_cost_usd"] = round(sum(t["_actual_cost"] for t in completed_fps.values()), 4)
        receipt["report_config"] = str(out_path / "report-config.json")
        (out_path / "collection-summary.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return receipt
    finally:
        if lock_file.exists():
            lock_file.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collector for multi-competitor irregular GeoGrid study.")
    parser.add_argument("--plan", required=True, help="Path to competitive plan JSON")
    parser.add_argument("--output-dir", required=True, help="Path to study run directory")
    parser.add_argument("--execute", action="store_true", help="Execute collection (default is estimate only)")
    parser.add_argument("--confirm-cost-usd", type=float, default=0.0, help="Confirmed spending ceiling")
    parser.add_argument("--phase", type=int, default=None, help="Optional phase filter (default all)")
    parser.add_argument("--study-plan", default=None, help="Optional path to source study-plan.json")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Worker concurrency limit (default 6)")
    parser.add_argument("--allow-live", action="store_true", help="Explicit user opt-in to higher-cost Live execution")
    args = parser.parse_args(argv)

    try:
        res = collect(
            plan_path=args.plan, output_dir=args.output_dir, execute=args.execute,
            confirm_cost_usd=args.confirm_cost_usd, phase=args.phase, study_plan_path=args.study_plan,
            max_workers=args.workers, allow_live=args.allow_live,
        )
        print(json.dumps(res, indent=2))
        return 0
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"Collection stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
