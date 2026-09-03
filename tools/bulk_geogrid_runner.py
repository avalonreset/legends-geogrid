#!/usr/bin/env python
"""
Cache-aware bulk runner for legends-geogrid prospect scans.

Default behavior is a dry run. It normalizes the prospect list, estimates the
DataForSEO task count and cost, fingerprints each paid scan, and writes a
manifest plus a vault-facing run note. It only spends credits when --execute
and --confirm-cost-usd are both supplied.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from local_heatmap_poc import estimate_scan_cost, generate_grid, normalize

DUPLICATE_STATUSES = {"duplicate", "reused-in-run", "duplicate-error"}


@dataclass(frozen=True)
class ProspectScan:
    row_number: int
    prospect_id: str
    business_name: str
    keyword: str
    center_lat: float
    center_lng: float
    location_label: str
    target_domain: str
    target_cid: str
    target_place_id: str
    radius_km: float
    grid_size: int
    depth: int
    zoom: int
    device: str
    language_code: str
    se_domain: str
    search_places: bool


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def cell(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and value.strip():
            return value.strip()
    return ""


def number_cell(row: dict[str, str], default: float, *names: str) -> float:
    value = cell(row, *names)
    return default if not value else float(value)


def int_cell(row: dict[str, str], default: int, *names: str) -> int:
    value = cell(row, *names)
    return default if not value else int(float(value))


def load_prospects(args: argparse.Namespace) -> list[ProspectScan]:
    path = Path(args.prospects).resolve()
    scans: list[ProspectScan] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Prospect CSV has no header row")

        for index, row in enumerate(reader, start=1):
            business_name = cell(row, "business_name", "target_name", "name")
            keyword = cell(row, "keyword", "query")
            center_lat = number_cell(row, args.center_lat, "center_lat", "lat", "latitude")
            center_lng = number_cell(row, args.center_lng, "center_lng", "lng", "longitude")
            if not business_name or not keyword:
                raise ValueError(f"Row {index} requires business_name and keyword")
            if center_lat == 0 or center_lng == 0:
                raise ValueError(f"Row {index} requires center_lat and center_lng")

            fallback_id = f"{normalize(business_name)[:28] or 'prospect'}-{index:04d}"
            scans.append(
                ProspectScan(
                    row_number=index,
                    prospect_id=cell(row, "prospect_id", "id") or fallback_id,
                    business_name=business_name,
                    keyword=keyword,
                    center_lat=center_lat,
                    center_lng=center_lng,
                    location_label=cell(row, "location_label", "location", "city") or args.location_label,
                    target_domain=cell(row, "target_domain", "domain"),
                    target_cid=cell(row, "target_cid", "cid"),
                    target_place_id=cell(row, "target_place_id", "place_id"),
                    radius_km=number_cell(row, args.radius_km, "radius_km", "radius"),
                    grid_size=int_cell(row, args.grid_size, "grid_size", "grid"),
                    depth=int_cell(row, args.depth, "depth"),
                    zoom=int_cell(row, args.zoom, "zoom"),
                    device=cell(row, "device") or args.device,
                    language_code=cell(row, "language_code", "language") or args.language_code,
                    se_domain=cell(row, "se_domain") or args.se_domain,
                    search_places=parse_bool(cell(row, "search_places")) or args.search_places,
                )
            )
            if args.max_prospects and len(scans) >= args.max_prospects:
                break
    return scans


def validate_scan(scan: ProspectScan) -> None:
    if scan.grid_size < 1 or scan.grid_size % 2 == 0:
        raise ValueError(f"{scan.prospect_id}: grid_size must be an odd positive integer")
    if scan.radius_km <= 0:
        raise ValueError(f"{scan.prospect_id}: radius_km must be positive")
    if scan.depth <= 0:
        raise ValueError(f"{scan.prospect_id}: depth must be positive")
    if not -90 < scan.center_lat < 90:
        raise ValueError(f"{scan.prospect_id}: center_lat must be greater than -90 and less than 90")
    if not -180 <= scan.center_lng <= 180:
        raise ValueError(f"{scan.prospect_id}: center_lng must be between -180 and 180")
    if scan.grid_size > 51:
        raise ValueError(f"{scan.prospect_id}: grid_size cannot exceed 51")
    if not 0 <= scan.zoom <= 23:
        raise ValueError(f"{scan.prospect_id}: zoom must be between 0 and 23")
    for label, value in (("center_lat", scan.center_lat), ("center_lng", scan.center_lng), ("radius_km", scan.radius_km)):
        if not math.isfinite(value):
            raise ValueError(f"{scan.prospect_id}: {label} must be finite")


def validate_run_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", run_id):
        raise ValueError("run-id must be 1-100 characters using letters, numbers, dots, dashes, or underscores")
    if ".." in run_id:
        raise ValueError("run-id cannot contain '..'")
    return run_id


def validate_cost_ceiling(value: float) -> float:
    if not math.isfinite(value) or value < 0:
        raise ValueError("confirm-cost-usd must be a finite, non-negative number")
    return value


def scan_identity(scan: ProspectScan, method: str) -> dict[str, Any]:
    identity_key = (
        scan.target_place_id
        or scan.target_cid
        or normalize(scan.target_domain)
        or normalize(scan.business_name)
    )
    return {
        "source": "dataforseo-google-maps-serp",
        "method": method,
        "target": identity_key,
        "business_name": normalize(scan.business_name),
        "keyword": scan.keyword.strip().lower(),
        "center_lat": round(scan.center_lat, 7),
        "center_lng": round(scan.center_lng, 7),
        "radius_km": scan.radius_km,
        "grid_size": scan.grid_size,
        "depth": scan.depth,
        "zoom": scan.zoom,
        "device": scan.device,
        "language_code": scan.language_code,
        "se_domain": scan.se_domain,
        "search_places": scan.search_places,
    }


def fingerprint_scan(scan: ProspectScan, method: str) -> str:
    payload = json.dumps(scan_identity(scan, method), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def load_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {"version": 1, "entries": {}}
    return json.loads(cache_path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_cache_fresh(entry: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.allow_stale_cache:
        return True
    generated_at = entry.get("generated_at")
    if not generated_at:
        return False
    try:
        generated = dt.datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    age = dt.datetime.now(dt.timezone.utc) - generated
    return age <= dt.timedelta(days=args.freshness_days)


def normalized_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "row_number",
        "prospect_id",
        "business_name",
        "keyword",
        "center_lat",
        "center_lng",
        "location_label",
        "target_domain",
        "target_cid",
        "target_place_id",
        "radius_km",
        "grid_size",
        "depth",
        "zoom",
        "device",
        "language_code",
        "se_domain",
        "search_places",
        "fingerprint",
        "cache_status",
        "task_count",
        "estimated_cost_usd",
        "duplicate_of",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render_vault_note(manifest: dict[str, Any]) -> str:
    totals = manifest["totals"]
    lines = [
        "---",
        "type: local-seo-geogrid-bulk-run",
        f"status: {manifest['status']}",
        f"created: {manifest['generated_at'][:10]}",
        "tags:",
        "  - local-seo",
        "  - geogrid",
        "  - dataforseo",
        "  - cache",
        "---",
        "",
        f"# GeoGrid Bulk Run: {manifest['run_id']}",
        "",
        "## Summary",
        "",
        f"- Generated: {manifest['generated_at']}",
        f"- Source CSV: `{manifest['source_csv']}`",
        f"- Method: `{manifest['method']}`",
        f"- Prospects loaded: {totals['prospects_loaded']}",
        f"- Cached prospects skipped: {totals['cached_scans']}",
        f"- Pending paid prospects: {totals['pending_scans']}",
        f"- Pending coordinate tasks: {totals['pending_tasks']}",
        f"- Estimated pending cost: ${totals['pending_cost_usd']:.4f}",
        f"- Manifest: `{manifest['manifest_path']}`",
        f"- Normalized CSV: `{manifest['normalized_csv_path']}`",
        f"- Evidence folder: `{manifest['run_dir']}`",
        "",
        "## Cache Rule",
        "",
        "Each paid scan is fingerprinted by target identity, keyword, center coordinate, radius, grid size, depth, zoom, device, language, search domain, search places flag, and DataForSEO queue mode. Fresh cached scans are skipped before any paid call is made.",
        "",
        "## Next Action",
        "",
    ]
    if manifest["execute"]:
        lines.append("Review completed scan folders and promote the strongest opportunities into the demo/report layer.")
    else:
        lines.append("Dry run only. Re-run with `--execute --confirm-cost-usd <amount>` after confirming the prospect list is real and worth paying for.")
    lines.append("")
    return "\n".join(lines)


def local_runner_command(scan: ProspectScan, method: str, output_dir: Path, args: argparse.Namespace) -> list[str]:
    script = Path(__file__).with_name("local_heatmap_poc.py")
    command = [
        sys.executable,
        str(script),
        "--method",
        method,
        "--keyword",
        scan.keyword,
        "--target-name",
        scan.business_name,
        "--center-lat",
        str(scan.center_lat),
        "--center-lng",
        str(scan.center_lng),
        "--location-label",
        scan.location_label,
        "--radius-km",
        str(scan.radius_km),
        "--grid-size",
        str(scan.grid_size),
        "--depth",
        str(scan.depth),
        "--zoom",
        str(scan.zoom),
        "--device",
        scan.device,
        "--language-code",
        scan.language_code,
        "--se-domain",
        scan.se_domain,
        "--output-dir",
        str(output_dir),
        "--execute",
        "--confirm-cost-usd",
        str(estimate_scan_cost(scan.grid_size * scan.grid_size, scan.depth, method)),
        "--timeout",
        str(args.timeout),
        "--poll-seconds",
        str(args.poll_seconds),
        "--poll-interval",
        str(args.poll_interval),
    ]
    if scan.search_places:
        command.append("--search-places")
    if scan.target_domain:
        command.extend(["--target-domain", scan.target_domain])
    if scan.target_cid:
        command.extend(["--target-cid", scan.target_cid])
    if scan.target_place_id:
        command.extend(["--target-place-id", scan.target_place_id])
    return command


def extract_stdout_json(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        raise RuntimeError("Runner stdout did not contain a JSON payload")
    return json.loads(stdout[start:])


def execute_pending(
    pending_rows: list[dict[str, Any]],
    scans_by_fingerprint: dict[str, ProspectScan],
    cache: dict[str, Any],
    run_dir: Path,
    method: str,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    scans_dir = run_dir / "scans"
    jsonl_path = run_dir / "parsed-results.jsonl"

    for row in pending_rows:
        fingerprint = row["fingerprint"]
        scan = scans_by_fingerprint[fingerprint]
        command = local_runner_command(scan, method, scans_dir, args)
        started_at = utc_now()
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        runner_result: dict[str, Any] = {}
        try:
            runner_result = extract_stdout_json(process.stdout)
        except (RuntimeError, json.JSONDecodeError):
            pass
        if process.returncode != 0:
            row["cache_status"] = "error"
            row["error"] = process.stderr[-4000:]
            if runner_result.get("outputs"):
                row["outputs"] = runner_result["outputs"]
            completed.append(row)
            continue

        outputs = runner_result.get("outputs") or {}
        parsed_path = outputs.get("parsed_json")
        if not parsed_path or not Path(parsed_path).exists():
            row["cache_status"] = "error"
            row["error"] = "Runner reported success without a readable parsed_json artifact"
            completed.append(row)
            continue

        try:
            parsed_payload = json.loads(Path(parsed_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            row["cache_status"] = "error"
            row["error"] = f"Runner parsed_json could not be read: {exc}"
            completed.append(row)
            continue

        metrics = parsed_payload.get("metrics")
        if not isinstance(metrics, dict):
            row["cache_status"] = "error"
            row["error"] = "Runner parsed_json is missing a metrics object"
            completed.append(row)
            continue

        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "fingerprint": fingerprint,
                        "prospect": asdict(scan),
                        "outputs": outputs,
                        "parsed": parsed_payload,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )

        entry = {
            "fingerprint": fingerprint,
            "generated_at": started_at,
            "method": method,
            "prospect_id": scan.prospect_id,
            "business_name": scan.business_name,
            "keyword": scan.keyword,
            "identity": scan_identity(scan, method),
            "outputs": outputs,
            "metrics": metrics,
        }
        cache.setdefault("entries", {})[fingerprint] = entry
        row["cache_status"] = "executed"
        row["outputs"] = outputs
        completed.append(row)
        write_json(run_dir.parent / "cache-index.json", cache)

    return completed


def parse_args(argv: list[str]) -> argparse.Namespace:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Estimate, cache, and optionally run bulk local SEO geo-grid scans")
    parser.add_argument("--prospects", required=True, help="CSV with business_name, keyword, center_lat, and center_lng columns")
    parser.add_argument("--run-id", default=dt.datetime.now().strftime("%Y%m%d-%H%M%S-bulk-geogrid"))
    parser.add_argument("--method", choices=["standard", "priority", "live"], default="standard")
    parser.add_argument("--output-root", default=str(default_root / "bulk-runs"))
    parser.add_argument("--vault-data-dir", default="", help="Optional directory for an Obsidian-style Markdown run note")
    parser.add_argument("--execute", action="store_true", help="Spend DataForSEO credits for uncached scans")
    parser.add_argument("--confirm-cost-usd", type=float, default=0.0, help="Required spending ceiling when --execute is used")
    parser.add_argument("--max-prospects", type=int, default=0, help="Optional row cap for tests")
    parser.add_argument("--freshness-days", type=int, default=30)
    parser.add_argument("--allow-stale-cache", action="store_true")
    parser.add_argument("--center-lat", type=float, default=0.0, help="Fallback center latitude if CSV omits it")
    parser.add_argument("--center-lng", type=float, default=0.0, help="Fallback center longitude if CSV omits it")
    parser.add_argument("--location-label", default="Unspecified location")
    parser.add_argument("--radius-km", type=float, default=2.0)
    parser.add_argument("--grid-size", type=int, default=5)
    parser.add_argument("--depth", type=int, default=20)
    parser.add_argument("--zoom", type=int, default=15)
    parser.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    parser.add_argument("--language-code", default="en")
    parser.add_argument("--se-domain", default="google.com")
    parser.add_argument("--search-places", action="store_true")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--poll-seconds", type=int, default=420)
    parser.add_argument("--poll-interval", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    validate_run_id(args.run_id)
    validate_cost_ceiling(args.confirm_cost_usd)
    output_root = Path(args.output_root).resolve()
    run_dir = output_root / args.run_id
    cache_path = output_root / "cache-index.json"
    manifest_path = run_dir / "manifest.json"
    normalized_path = run_dir / "prospects.normalized.csv"
    vault_note_path = Path(args.vault_data_dir).resolve() / f"{args.run_id}.md" if args.vault_data_dir else None

    scans = load_prospects(args)
    if not scans:
        raise ValueError("No prospects loaded")

    cache = load_cache(cache_path)
    rows: list[dict[str, Any]] = []
    pending_rows: list[dict[str, Any]] = []
    scans_by_fingerprint: dict[str, ProspectScan] = {}

    for scan in scans:
        validate_scan(scan)
        fingerprint = fingerprint_scan(scan, args.method)
        task_count = len(generate_grid(scan.center_lat, scan.center_lng, scan.grid_size, scan.radius_km))
        estimated_cost = estimate_scan_cost(task_count, scan.depth, args.method)
        duplicate_of = ""
        if fingerprint in scans_by_fingerprint:
            cache_status = "duplicate"
            duplicate_of = scans_by_fingerprint[fingerprint].prospect_id
        else:
            entry = cache.get("entries", {}).get(fingerprint)
            cache_status = "cached" if entry and is_cache_fresh(entry, args) else "pending"
        row = {
            **asdict(scan),
            "fingerprint": fingerprint,
            "cache_status": cache_status,
            "task_count": task_count,
            "estimated_cost_usd": round(estimated_cost, 6),
            "duplicate_of": duplicate_of,
        }
        rows.append(row)
        scans_by_fingerprint.setdefault(fingerprint, scan)
        if cache_status == "pending":
            pending_rows.append(row)

    pending_cost = sum(float(row["estimated_cost_usd"]) for row in pending_rows)
    if args.execute and pending_cost > args.confirm_cost_usd:
        raise RuntimeError(
            f"Refusing to execute: pending cost ${pending_cost:.4f} exceeds --confirm-cost-usd ${args.confirm_cost_usd:.4f}"
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    normalized_csv(normalized_path, rows)

    executed_rows: list[dict[str, Any]] = []
    if args.execute:
        executed_rows = execute_pending(pending_rows, scans_by_fingerprint, cache, run_dir, args.method, args)
        by_fingerprint = {row["fingerprint"]: row for row in executed_rows}
        updated_rows: list[dict[str, Any]] = []
        for row in rows:
            executed = by_fingerprint.get(row["fingerprint"])
            if row["cache_status"] == "duplicate" and executed:
                row["cache_status"] = "reused-in-run" if executed["cache_status"] == "executed" else "duplicate-error"
                for key in ("outputs", "metrics", "error"):
                    if key in executed:
                        row[key] = executed[key]
                updated_rows.append(row)
            else:
                updated_rows.append(executed or row)
        rows = updated_rows
        normalized_csv(normalized_path, rows)
        cache = load_cache(cache_path)

    manifest = {
        "version": 1,
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "status": "executed" if args.execute else "dry-run",
        "execute": args.execute,
        "method": args.method,
        "source_csv": str(Path(args.prospects).resolve()),
        "run_dir": str(run_dir),
        "manifest_path": str(manifest_path),
        "normalized_csv_path": str(normalized_path),
        "vault_note_path": str(vault_note_path) if vault_note_path else None,
        "cache_index_path": str(cache_path),
        "defaults": {
            "radius_km": args.radius_km,
            "grid_size": args.grid_size,
            "depth": args.depth,
            "zoom": args.zoom,
            "device": args.device,
            "language_code": args.language_code,
            "se_domain": args.se_domain,
            "search_places": args.search_places,
            "freshness_days": args.freshness_days,
        },
        "totals": {
            "prospects_loaded": len(rows),
            "cached_scans": sum(1 for row in rows if row["cache_status"] == "cached"),
            "pending_scans": sum(1 for row in rows if row["cache_status"] == "pending"),
            "executed_scans": sum(1 for row in rows if row["cache_status"] == "executed"),
            "duplicate_scans": sum(1 for row in rows if row["cache_status"] in DUPLICATE_STATUSES),
            "error_scans": sum(1 for row in rows if row["cache_status"] == "error"),
            "total_tasks": sum(
                int(row["task_count"])
                for row in rows
                if row["cache_status"] not in DUPLICATE_STATUSES
            ),
            "pending_tasks": sum(int(row["task_count"]) for row in rows if row["cache_status"] == "pending"),
            "pending_cost_usd": round(sum(float(row["estimated_cost_usd"]) for row in rows if row["cache_status"] == "pending"), 4),
            "total_cost_if_uncached_usd": round(
                sum(
                    float(row["estimated_cost_usd"])
                    for row in rows
                    if row["cache_status"] not in DUPLICATE_STATUSES
                ),
                4,
            ),
        },
        "rows": rows,
    }
    write_json(manifest_path, manifest)
    if vault_note_path:
        vault_note_path.parent.mkdir(parents=True, exist_ok=True)
        vault_note_path.write_text(render_vault_note(manifest), encoding="utf-8")

    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "status": manifest["status"],
                "prospects_loaded": manifest["totals"]["prospects_loaded"],
                "pending_scans": manifest["totals"]["pending_scans"],
                "pending_tasks": manifest["totals"]["pending_tasks"],
                "pending_cost_usd": manifest["totals"]["pending_cost_usd"],
                "manifest": str(manifest_path),
                "vault_note": str(vault_note_path) if vault_note_path else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
