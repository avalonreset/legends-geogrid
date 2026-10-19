"""Compose a complete radial study from verified saved scans, without paid requests."""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import datetime as dt
import json
from pathlib import Path

from competitive_collect import adapt_plan, fingerprint_task, load_ledger, make_task_payload
from competitive_export import export_study
from competitive_queue import POST_ENDPOINT
import local_heatmap_poc as runner
from radius_sampling import MILE_KM, radial_origins
from study_contract import digest


def require_same_search(base, other):
    """Delivery method may differ; the business, query text and search controls may not."""
    for key in ("lat", "lng", "cid", "place_id", "domain"):
        if base["business"][key] != other["business"][key]:
            raise ValueError(f"Source business differs: {key}")
    for key in set(base["settings"]) - {"method"}:
        if base["settings"][key] != other["settings"][key]:
            raise ValueError(f"Source search control differs: {key}")
    queries = {q["query_id"]: q["query"] for q in base["queries"]}
    if any(queries.get(q["query_id"]) != q["query"] for q in other["queries"]):
        raise ValueError("Source query differs")


def require_complete(origins, queries, observations):
    expected = {(q["query_id"], o["lat"], o["lng"]) for q in queries for o in origins}
    missing = expected - observations.keys()
    if missing:
        raise ValueError(f"Radial study has {len(missing)} unmeasured query/location pairs")
    return expected


def read_archive(path):
    """Verify receipts, raw hashes and exact request identity, then reparse the raw results."""
    path = Path(path).resolve()
    plan_path = path / "competitive-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    receipt = json.loads((path / "collection-summary.json").read_text())
    if receipt["status"] != "collected" or receipt["plan_sha256"] != digest(plan_path):
        raise ValueError(f"Archive is not a completed immutable scan: {path}")
    adapted = adapt_plan(plan)
    completed, ambiguous = load_ledger(path / "collection-ledger.jsonl")
    if ambiguous or len(completed) != receipt["total_tasks"]:
        raise ValueError(f"Archive has ambiguous or incomplete requests: {path}")
    settings, business = adapted["settings"], adapted["business"]
    endpoint = POST_ENDPOINT if settings["method"] == "standard" else "/serp/google/maps/live/advanced"
    observations = {}
    for query in adapted["queries"]:
        tasks, evidence, points = [], [], []
        for index, origin in enumerate(adapted["origins"]):
            request = make_task_payload(query["query"], origin, settings)
            fp = fingerprint_task(request, endpoint)
            saved = json.loads((path / "requests" / f"{fp}.json").read_text())
            if saved["endpoint"] != endpoint or saved["tasks"] != [request]:
                raise ValueError("Archived request differs from source plan")
            if fp not in completed:
                raise ValueError("Missing exact request response")
            # Read the hash-verified raw envelope, not editable normalized lane files.
            raw_path = path / "responses" / f"{fp}.json"
            raw = json.loads(raw_path.read_text())
            task = raw["tasks"][0]
            if task["status_code"] not in (20000, 40102):
                raise ValueError("Archive includes failed provider tasks")
            task["tag"] = origin["tag"]
            tasks.append(task)
            points.append(runner.GridPoint(index, 0, origin["lat"], origin["lng"], origin["tag"]))
            evidence.append({
                "source_run": str(path), "request_sha256": fp,
                "response_sha256": digest(raw_path), "provider_task_id": task["id"],
                "method": settings["method"], "source_tag": origin["tag"],
            })
        args = argparse.Namespace(
            target_name=business["name"], target_cid=business["cid"],
            target_place_id=business["place_id"], target_domain=business["domain"],
            match_threshold=.72, depth=settings["depth"], top_competitors=settings["depth"],
        )
        parsed = runner.parse_results({"tasks": tasks}, points, args)
        for result, provenance in zip(parsed, evidence):
            record = asdict(result)
            record["provenance"] = provenance
            key = (query["query_id"], result.point.lat, result.point.lng)
            if key in observations:
                raise ValueError("Duplicate coordinate/query in source")
            observations[key] = record
    ledger = path / "collection-ledger.jsonl"
    actual = round(sum(json.loads(line).get("actual_usd", 0)
                       for line in ledger.read_text().splitlines()), 6)
    if abs(actual - receipt["run_total_cost_usd"]) > 1e-8:
        raise ValueError("Archive charge differs from ledger")
    audit = {"path": str(path), "plan_sha256": digest(plan_path),
             "ledger_sha256": digest(ledger), "observations": len(observations),
             "actual_cost_usd": actual, "method": settings["method"]}
    return plan, adapted, observations, audit


def compose(sources, output, radius_miles, spacing_miles):
    if not sources:
        raise ValueError("At least one source archive required")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Composition output must be new; preserve prior evidence")
    all_observations, audits = {}, []
    for index, source in enumerate(sources):
        plan, adapted, observations, audit = read_archive(source)
        if index == 0:
            base_plan, base = copy.deepcopy(plan), adapted
        else:
            require_same_search(base, adapted)
            if adapted["settings"]["method"] != "standard":
                raise ValueError("Enrichment archives must use Standard queue")
        # Caller supplies archives chronologically. Refreshes replace a saved observation,
        # never fabricate a better rank; superseded responses remain in the source archive.
        for key, record in observations.items():
            previous = all_observations.get(key)
            if previous and previous.get("sampled_at") and record.get("sampled_at"):
                if record["sampled_at"] < previous["sampled_at"]:
                    raise ValueError("Refresh predates the observation it would replace")
            all_observations[key] = record
        audits.append(audit)
    business = base["business"]
    origins = radial_origins(business["lat"], business["lng"], radius_miles, spacing_miles)
    expected = require_complete(origins, base["queries"], all_observations)
    selected = {key: all_observations[key] for key in expected}
    sampling = {
        "geometry": "radius_grid", "radius_km": radius_miles * MILE_KM,
        "spacing_km": spacing_miles * MILE_KM,
        "center": {"lat": business["lat"], "lng": business["lng"]},
        "description": f"{radius_miles * MILE_KM:g} km radius · {spacing_miles * MILE_KM:g} km spacing",
        "rationale": "Complete regular lattice clipped by distance from the primary profile. Every included origin was searched for every query.",
    }
    methods = sorted({r["provenance"]["method"] for r in selected.values()})
    base_plan.update(origins=origins, sampling_parameters=sampling)
    base_plan.pop("summary", None)
    base_plan.pop("phases", None)
    base_plan["measurement_settings"]["method"] = methods[0] if len(methods) == 1 else "mixed_archive"
    base_plan["composition"] = {"source_archives": audits, "default_future_method": "standard"}
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    base_plan["generated_at"] = timestamp
    output.mkdir(parents=True)
    def save(path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save(output / "competitive-plan.json", base_plan)
    lanes = []
    for index, query in enumerate(base["queries"], 1):
        results = []
        for origin in origins:
            result = copy.deepcopy(selected[(query["query_id"], origin["lat"], origin["lng"])])
            result["point"].update(tag=origin["origin_id"], row=origin["grid_y"], col=origin["grid_x"],
                                   roles=origin["roles"], phase=1)
            results.append(result)
        lane = output / f"lane-{index}"
        lane.mkdir()
        save(lane / "parsed-grid.json", {
            "target": business["name"], "generated_at": timestamp,
            "keyword": query["query"], "measurement_settings": base_plan["measurement_settings"],
            "results": results,
        })
        lanes.append(dict(query_id=query["query_id"], query=query["query"],
                          label=query["label"], records_path=f"lane-{index}/parsed-grid.json"))
    save(output / "report-config.json", {"business": business, "lanes": lanes, "synthetic": False,
                                        "geometry": "radius_grid"})
    new_cost = round(sum(a["actual_cost_usd"] for a in audits[1:]), 6)
    base_source = audits[0]["path"]
    reused = sum(r["provenance"]["source_run"] == base_source for r in selected.values())
    costs = {
        "new_collection_cost_usd": new_cost,
        "historical_source_cost_usd": audits[0]["actual_cost_usd"],
        "fresh_standard_cost_usd": round(len(selected) * .0006, 6),
        "reused_observations": reused, "new_observations": len(selected) - reused,
        "source_total_observations": sum(a["observations"] for a in audits),
        "delivery_methods": methods,
    }
    receipt = {
        "status": "composed", "plan_sha256": digest(output / "competitive-plan.json"),
        "total_tasks": len(selected), "run_total_cost_usd": round(sum(a["actual_cost_usd"] for a in audits), 6),
        "composition": costs, "sources": audits,
        "short_result_sets_by_query": {
            q["query_id"]: sum(not set(range(1, 21)).issubset(r["observed_ranks"])
                               for (qid, _, _), r in selected.items() if qid == q["query_id"])
            for q in base["queries"]
        },
    }
    save(output / "collection-summary.json", receipt)
    save(output / "companion-study.json", export_study(output))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True,
                        help="Completed archives in chronological order; first is historical reuse")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--radius-miles", type=float, required=True)
    parser.add_argument("--spacing-miles", type=float, default=.5)
    args = parser.parse_args()
    print(json.dumps(compose(args.source, args.output, args.radius_miles, args.spacing_miles), indent=2))
