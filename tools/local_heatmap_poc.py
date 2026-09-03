#!/usr/bin/env python
"""
DataForSEO-powered local SEO geo-grid runner for legends-geogrid.

This script creates a grid around a target coordinate, calls the DataForSEO
Google Maps SERP live endpoint, matches a target business in each result set,
and writes raw JSON plus Markdown/HTML heatmap reports.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


DATAFORSEO_MAPS_LIVE_URL = "https://api.dataforseo.com/v3/serp/google/maps/live/advanced"
DATAFORSEO_MAPS_TASK_POST_URL = "https://api.dataforseo.com/v3/serp/google/maps/task_post"
DATAFORSEO_MAPS_TASK_GET_ADVANCED_URL = "https://api.dataforseo.com/v3/serp/google/maps/task_get/advanced/{task_id}"
LIVE_COST_PER_TASK_USD = 0.002
PRIORITY_COST_PER_TASK_USD = 0.0012
STANDARD_COST_PER_TASK_USD = 0.0006
QUEUE_TASK_BATCH_SIZE = 100
COST_PER_TASK_USD = {
    "standard": STANDARD_COST_PER_TASK_USD,
    "priority": PRIORITY_COST_PER_TASK_USD,
    "live": LIVE_COST_PER_TASK_USD,
}


@dataclass(frozen=True)
class GridPoint:
    row: int
    col: int
    lat: float
    lng: float
    tag: str


@dataclass
class PointResult:
    point: GridPoint
    rank: int | None
    matched_item: dict[str, Any] | None
    top_items: list[dict[str, Any]]
    error: str | None = None


def normalize(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def estimate_scan_cost(task_count: int, depth: int, method: str) -> float:
    """Return the documented base estimate, including depth billing units."""
    if task_count < 0:
        raise ValueError("task_count cannot be negative")
    if depth < 1:
        raise ValueError("depth must be positive")
    if method not in COST_PER_TASK_USD:
        raise ValueError(f"unsupported method: {method}")
    depth_units = math.ceil(depth / 100)
    return task_count * COST_PER_TASK_USD[method] * depth_units


def validate_run_args(args: argparse.Namespace) -> None:
    if not -90 < args.center_lat < 90:
        raise ValueError("center_lat must be greater than -90 and less than 90")
    if not -180 <= args.center_lng <= 180:
        raise ValueError("center_lng must be between -180 and 180")
    if args.grid_size > 51:
        raise ValueError("grid_size cannot exceed 51")
    if args.depth < 1:
        raise ValueError("depth must be positive")
    if not 0 <= args.zoom <= 23:
        raise ValueError("zoom must be between 0 and 23")
    if not 0 < args.match_threshold <= 1:
        raise ValueError("match_threshold must be greater than 0 and at most 1")
    if not math.isfinite(args.confirm_cost_usd) or args.confirm_cost_usd < 0:
        raise ValueError("confirm-cost-usd must be a finite, non-negative number")


def generate_grid(center_lat: float, center_lng: float, grid_size: int, radius_km: float) -> list[GridPoint]:
    if grid_size < 1 or grid_size % 2 == 0:
        raise ValueError("grid_size must be an odd positive integer, for example 3, 5, or 7")
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")

    center_index = (grid_size - 1) / 2
    step_km = 0 if grid_size == 1 else (2 * radius_km) / (grid_size - 1)
    points: list[GridPoint] = []
    lat_factor = 111.32
    lng_factor = 111.32 * math.cos(math.radians(center_lat))

    for row in range(grid_size):
        for col in range(grid_size):
            dy = (center_index - row) * step_km
            dx = (col - center_index) * step_km
            lat = center_lat + (dy / lat_factor)
            lng = center_lng + (dx / lng_factor)
            points.append(GridPoint(row=row, col=col, lat=lat, lng=lng, tag=f"r{row}c{col}"))
    return points


def build_tasks(args: argparse.Namespace, points: list[GridPoint]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for point in points:
        task: dict[str, Any] = {
            "keyword": args.keyword,
            "location_coordinate": f"{point.lat:.7f},{point.lng:.7f},{args.zoom}z",
            "language_code": args.language_code,
            "device": args.device,
            "depth": args.depth,
            "tag": point.tag,
            "search_places": args.search_places,
        }
        if args.se_domain:
            task["se_domain"] = args.se_domain
        if args.method == "standard":
            task["priority"] = 1
        elif args.method == "priority":
            task["priority"] = 2
        tasks.append(task)
    return tasks


def dataforseo_auth_header() -> str:
    username = os.environ.get("DATAFORSEO_USERNAME")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not username or not password:
        raise RuntimeError("DATAFORSEO_USERNAME and DATAFORSEO_PASSWORD must be set in the environment")
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def call_dataforseo_live_task(task: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        DATAFORSEO_MAPS_LIVE_URL,
        data=json.dumps([task]).encode("utf-8"),
        headers={
            "Authorization": dataforseo_auth_header(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DataForSEO HTTP {exc.code}: {body}") from exc
    return json.loads(body)


def call_dataforseo_live(tasks: list[dict[str, Any]], timeout: int) -> dict[str, Any]:
    """Call the live endpoint once per task and combine the results.

    DataForSEO queue endpoints support larger task arrays, but the Google Maps
    live endpoint currently rejects multi-task payloads with "You can set only
    one task at a time." The fan-out is intentional for this POC.
    """
    combined: dict[str, Any] = {
        "version": "fanout",
        "status_code": 20000,
        "status_message": "Ok.",
        "time": None,
        "cost": 0,
        "tasks_count": len(tasks),
        "tasks_error": 0,
        "tasks": [],
    }
    for index, task in enumerate(tasks, start=1):
        print(f"  point {index}/{len(tasks)} {task.get('tag')}", file=sys.stderr)
        payload = call_dataforseo_live_task(task, timeout)
        combined["cost"] += float(payload.get("cost") or 0)
        task_items = payload.get("tasks") or []
        if not task_items:
            combined["tasks_error"] += 1
            combined["tasks"].append(
                {
                    "status_code": payload.get("status_code") or 50000,
                    "status_message": payload.get("status_message") or "No task returned",
                    "data": task,
                    "result": [],
                    "cost": 0,
                }
            )
            continue
        returned_task = task_items[0]
        returned_task.setdefault("data", task)
        if int(returned_task.get("status_code") or 0) >= 40000:
            combined["tasks_error"] += 1
        combined["tasks"].append(returned_task)
    return combined


def http_json(url: str, timeout: int, payload: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": dataforseo_auth_header(),
            "Content-Type": "application/json",
        },
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DataForSEO HTTP {exc.code}: {body}") from exc
    return json.loads(body)


def call_dataforseo_standard(tasks: list[dict[str, Any]], timeout: int, poll_seconds: int, poll_interval: int) -> dict[str, Any]:
    task_ids: list[str] = []
    post_cost = 0.0
    post_errors = 0
    post_tasks: list[dict[str, Any]] = []
    post_responses: list[dict[str, Any]] = []

    for start in range(0, len(tasks), QUEUE_TASK_BATCH_SIZE):
        batch = tasks[start : start + QUEUE_TASK_BATCH_SIZE]
        print(f"  post batch {start + 1}-{start + len(batch)}", file=sys.stderr)
        post_payload = http_json(DATAFORSEO_MAPS_TASK_POST_URL, timeout=timeout, payload=batch)
        post_responses.append(post_payload)
        for task in post_payload.get("tasks") or []:
            post_tasks.append(task)
            post_cost += float(task.get("cost") or 0)
            if int(task.get("status_code") or 0) >= 40000:
                post_errors += 1
                continue
            task_id = task.get("id")
            if task_id:
                task_ids.append(str(task_id))

    combined: dict[str, Any] = {
        "version": "standard-queue",
        "status_code": 20000 if post_errors == 0 else 20100,
        "status_message": "Ok." if post_errors == 0 else "Task post completed with errors.",
        "time": None,
        "cost": post_cost,
        "tasks_count": len(tasks),
        "tasks_error": post_errors,
        "post_response": {
            "status_code": 20000 if post_errors == 0 else 20100,
            "status_message": "Aggregated queue task_post responses.",
            "tasks_count": len(tasks),
            "tasks_error": post_errors,
            "tasks": post_tasks,
        },
        "post_responses": post_responses,
        "tasks": [],
    }

    deadline = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=poll_seconds)
    pending = set(task_ids)
    last_payloads: dict[str, dict[str, Any]] = {}

    while pending and dt.datetime.now(dt.timezone.utc) < deadline:
        for task_id in list(pending):
            print(f"  poll {task_id}", file=sys.stderr)
            get_url = DATAFORSEO_MAPS_TASK_GET_ADVANCED_URL.format(task_id=task_id)
            get_payload = http_json(get_url, timeout=timeout)
            last_payloads[task_id] = get_payload
            get_tasks = get_payload.get("tasks") or []
            if not get_tasks:
                continue
            get_task = get_tasks[0]
            status_code = int(get_task.get("status_code") or 0)
            if status_code == 20000:
                combined["tasks"].append(get_task)
                pending.remove(task_id)
            elif status_code >= 40000 and status_code not in {40601, 40602}:
                combined["tasks_error"] += 1
                combined["tasks"].append(get_task)
                pending.remove(task_id)
        if pending:
            import time

            time.sleep(poll_interval)

    for task_id in sorted(pending):
        combined["tasks_error"] += 1
        fallback = (last_payloads.get(task_id, {}).get("tasks") or [{}])[0]
        fallback.setdefault("id", task_id)
        fallback.setdefault("status_code", 40602)
        fallback.setdefault("status_message", "Task was not ready before poll timeout")
        fallback.setdefault("result", [])
        combined["tasks"].append(fallback)

    return combined


def item_domain(item: dict[str, Any]) -> str:
    return str(item.get("domain") or item.get("url") or "")


def canonical_domain(value: str | None) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"//{text}")
    host = (parsed.hostname or "").rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def domain_matches(candidate: str | None, target: str | None) -> bool:
    candidate_host = canonical_domain(candidate)
    target_host = canonical_domain(target)
    return bool(
        candidate_host
        and target_host
        and (candidate_host == target_host or candidate_host.endswith(f".{target_host}"))
    )


def match_score(item: dict[str, Any], args: argparse.Namespace) -> float:
    title_norm = normalize(str(item.get("title") or ""))
    target_norm = normalize(args.target_name)
    cid = str(item.get("cid") or "")
    place_id = str(item.get("place_id") or "")

    if args.target_cid and cid == str(args.target_cid):
        return 1.0
    if args.target_place_id and place_id == str(args.target_place_id):
        return 1.0
    if domain_matches(item_domain(item), args.target_domain):
        return 0.95
    if target_norm and title_norm == target_norm:
        return 0.92
    if target_norm and (target_norm in title_norm or title_norm in target_norm):
        return 0.86
    if target_norm and title_norm:
        return SequenceMatcher(None, title_norm, target_norm).ratio()
    return 0.0


def summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    rating = item.get("rating") or {}
    return {
        "rank": item.get("rank_absolute") or item.get("rank_group"),
        "title": item.get("title"),
        "category": item.get("category"),
        "domain": item.get("domain"),
        "address": item.get("address"),
        "rating": rating.get("value") if isinstance(rating, dict) else None,
        "votes_count": rating.get("votes_count") if isinstance(rating, dict) else None,
        "cid": item.get("cid"),
        "place_id": item.get("place_id"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
    }


def extract_items(task: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    if task.get("status_code") and int(task["status_code"]) >= 40000:
        return [], str(task.get("status_message") or "DataForSEO task error")
    results = task.get("result") or []
    if not results:
        return [], "No result array returned"
    items = results[0].get("items") or []
    return [item for item in items if isinstance(item, dict)], None


def parse_results(payload: dict[str, Any], points: list[GridPoint], args: argparse.Namespace) -> list[PointResult]:
    point_by_tag = {point.tag: point for point in points}
    results_by_tag: dict[str, PointResult] = {}

    for index, task in enumerate(payload.get("tasks") or []):
        fallback = points[index] if index < len(points) else None
        tag = (task.get("data") or {}).get("tag") or task.get("tag") or (fallback.tag if fallback else "")
        point = point_by_tag.get(str(tag)) or fallback
        if point is None or point.tag in results_by_tag:
            continue
        items, error = extract_items(task)

        best_item = None
        best_score = 0.0
        for item in items:
            score = match_score(item, args)
            if score > best_score:
                best_score = score
                best_item = item

        if best_score < args.match_threshold:
            best_item = None

        rank = None
        if best_item:
            rank = int(best_item.get("rank_absolute") or best_item.get("rank_group") or 0) or None

        results_by_tag[point.tag] = PointResult(
            point=point,
            rank=rank,
            matched_item=summarize_item(best_item) if best_item else None,
            top_items=[summarize_item(item) for item in items[: args.top_competitors]],
            error=error,
        )

    return [
        results_by_tag.get(
            point.tag,
            PointResult(
                point=point,
                rank=None,
                matched_item=None,
                top_items=[],
                error="No API result returned for this coordinate",
            ),
        )
        for point in points
    ]


def rank_symbol(rank: int | None, is_center: bool = False) -> str:
    if rank is None:
        value = "-"
    elif rank <= 9:
        value = str(rank)
    elif rank <= 20:
        value = "+"
    else:
        value = "-"
    return f"[{value}]" if is_center else f" {value} "


def rank_class(rank: int | None) -> str:
    if rank is None:
        return "rank-none"
    if rank == 1:
        return "rank-one"
    if rank <= 3:
        return "rank-top3"
    if rank <= 10:
        return "rank-visible"
    if rank <= 20:
        return "rank-buried"
    return "rank-none"


def calculate_metrics(results: list[PointResult]) -> dict[str, Any]:
    ranks = [result.rank for result in results if result.rank is not None]
    top3 = [rank for rank in ranks if rank <= 3]
    visible = [rank for rank in ranks if rank <= 10]
    total = len(results)
    error_points = sum(1 for result in results if result.error)
    return {
        "points": total,
        "found_points": len(ranks),
        "top3_points": len(top3),
        "visible_points": len(visible),
        "solv": round((len(top3) / total) * 100, 1) if total else 0,
        "visible_share": round((len(visible) / total) * 100, 1) if total else 0,
        "average_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
        "not_found_points": total - len(ranks),
        "error_points": error_points,
    }


def prospecting_verdict(metrics: dict[str, Any]) -> tuple[str, str]:
    if int(metrics.get("error_points") or 0):
        return (
            "Incomplete scan",
            "One or more coordinates did not return a usable API result. Retry those points before interpreting coverage.",
        )
    solv = float(metrics["solv"])
    visible = float(metrics["visible_share"])
    if solv < 20 and visible < 35:
        return (
            "High outreach opportunity",
            "The business is not consistently present in the local top 3 and has a clear visibility gap outside its immediate strongest point.",
        )
    if solv < 50:
        return (
            "Moderate outreach opportunity",
            "The business has a foothold, but the map shows enough weak coverage to justify a targeted local SEO conversation.",
        )
    return (
        "Retention / defense opportunity",
        "The business already has meaningful coverage; the angle is competitor defense, review velocity, and protecting strong zones.",
    )


def weak_zone_summary(results: list[PointResult], grid_size: int) -> str:
    labels = {
        (0, 0): "northwest",
        (0, grid_size // 2): "north",
        (0, grid_size - 1): "northeast",
        (grid_size // 2, 0): "west",
        (grid_size // 2, grid_size // 2): "center",
        (grid_size // 2, grid_size - 1): "east",
        (grid_size - 1, 0): "southwest",
        (grid_size - 1, grid_size // 2): "south",
        (grid_size - 1, grid_size - 1): "southeast",
    }
    weak = []
    for result in results:
        if result.rank is None or result.rank > 3:
            label = labels.get((result.point.row, result.point.col), result.point.tag)
            weak.append(label)
    if not weak:
        return "No weak zones in this grid."
    return "Weakest coverage appears around: " + ", ".join(weak[:6]) + ("." if len(weak) <= 6 else ", and more.")


def competitor_counts(results: list[PointResult]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for result in results:
        for item in result.top_items[:3]:
            title = item.get("title")
            if not title:
                continue
            counts[title] = counts.get(title, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:10]


def render_ascii_grid(results: list[PointResult], grid_size: int) -> str:
    by_cell = {(result.point.row, result.point.col): result for result in results}
    center = grid_size // 2
    lines = ["     W -------- E"]
    for row in range(grid_size):
        prefix = "  N " if row == 0 else ("  S " if row == grid_size - 1 else "  | ")
        cells = []
        for col in range(grid_size):
            result = by_cell.get((row, col))
            cells.append(rank_symbol(result.rank, is_center=(row == center and col == center)) if result else "?")
        lines.append(prefix + " ".join(cells))
    return "\n".join(lines)


def render_markdown(args: argparse.Namespace, results: list[PointResult], payload: dict[str, Any], started_at: str) -> str:
    metrics = calculate_metrics(results)
    verdict, verdict_reason = prospecting_verdict(metrics)
    weak_summary = weak_zone_summary(results, args.grid_size)
    grid = render_ascii_grid(results, args.grid_size)
    competitors = competitor_counts(results)
    actual_cost = sum(float(task.get("cost") or 0) for task in payload.get("tasks") or [])
    if payload.get("cost"):
        actual_cost = float(payload.get("cost") or actual_cost)
    estimated_live = len(results) * LIVE_COST_PER_TASK_USD
    estimated_priority = len(results) * PRIORITY_COST_PER_TASK_USD
    estimated_standard = len(results) * STANDARD_COST_PER_TASK_USD

    lines = [
        f"# Local SEO Geo-Grid Proof: {args.target_name}",
        "",
        f"- Generated: {started_at}",
        f"- Keyword: `{args.keyword}`",
        f"- Location: {args.location_label}",
        f"- Center: `{args.center_lat:.7f},{args.center_lng:.7f}`",
        f"- Grid: {args.grid_size}x{args.grid_size} ({len(results)} points), radius {args.radius_km:g} km",
        f"- Data source: DataForSEO Google Maps SERP {args.method}",
        f"- Estimated cost: ${estimated_live:.4f} live, ${estimated_priority:.4f} priority, or ${estimated_standard:.4f} standard",
        f"- Reported API cost: ${actual_cost:.4f}" if actual_cost else "- Reported API cost: not returned in payload",
        "",
        "## Heatmap",
        "",
        "```text",
        grid,
        "```",
        "",
        "Legend: `1` is rank 1, `2-3` is top 3, `4-9` is visible, `+` is rank 10-20, `-` is not found in returned depth.",
        "",
        "## Prospecting Verdict",
        "",
        f"- Verdict: {verdict}",
        f"- Why: {verdict_reason}",
        f"- Weak-zone narrative: {weak_summary}",
        f"- Sales angle: show the prospect that nearby competitors are winning map-pack visibility in the red cells, then propose a focused GBP/category/review/local-page sprint instead of a vague SEO retainer.",
        f"- Trust receipt: raw DataForSEO request, response, and parsed grid are saved in this run folder.",
        "",
        "## Metrics",
        "",
        f"- Map Pack Visibility Share: {metrics['solv']}% ({metrics['top3_points']}/{metrics['points']} points in top 3)",
        f"- Visible share: {metrics['visible_share']}% ({metrics['visible_points']}/{metrics['points']} points in top 10)",
        f"- Average rank where found: {metrics['average_rank'] if metrics['average_rank'] is not None else 'no data'}",
        f"- Not found: {metrics['not_found_points']} points",
        f"- API/result errors: {metrics['error_points']} points",
        "",
        "## Grid Details",
        "",
        "| Point | Coordinate | Rank | Matched title | Top result |",
        "|---|---:|---:|---|---|",
    ]

    for result in results:
        matched = result.matched_item or {}
        top = result.top_items[0] if result.top_items else {}
        lines.append(
            "| "
            + result.point.tag
            + " | "
            + f"{result.point.lat:.6f},{result.point.lng:.6f}"
            + " | "
            + (str(result.rank) if result.rank is not None else "-")
            + " | "
            + str(matched.get("title") or "-").replace("|", "\\|")
            + " | "
            + str(top.get("title") or "-").replace("|", "\\|")
            + " |"
        )

    lines.extend(["", "## Repeated Top Competitors", ""])
    if competitors:
        for title, count in competitors:
            lines.append(f"- {title}: top-3 at {count}/{len(results)} points")
    else:
        lines.append("- no data")

    lines.extend(
        [
            "",
            "## Why This Beats A Commodity Heatmap",
            "",
            "- It uses source receipts, not screenshots only.",
            "- It distinguishes not-found, visible, and top-3 coverage.",
            "- It names repeated competitor pressure by grid point.",
            "- It supports affordability mode (`standard` queue) for bulk prospecting and live mode for demos.",
            "- It can be plugged into Local SEO Brain so recommendations cite GBP, website, review, citation, and map-grid evidence together.",
            "",
            "## Notes",
            "",
            "- If the target is not found but a human can see it on Google Maps, tighten matching with `--target-cid`, `--target-place-id`, or `--target-domain`.",
            "- For prospecting, run 3x3 first, then escalate weak/high-value prospects to 5x5 or 7x7.",
            "- Do not use Google Places as the rank-tracking backbone; it returns place data, not a search-rank grid.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(args: argparse.Namespace, results: list[PointResult], markdown_path: Path) -> str:
    metrics = calculate_metrics(results)
    verdict, verdict_reason = prospecting_verdict(metrics)
    weak_summary = weak_zone_summary(results, args.grid_size)
    title = f"Local SEO Heatmap - {args.target_name}"

    lats = [result.point.lat for result in results] or [args.center_lat]
    lngs = [result.point.lng for result in results] or [args.center_lng]
    lat_span = max(max(lats) - min(lats), 0.001)
    lng_span = max(max(lngs) - min(lngs), 0.001)
    min_lat = min(lats) - (lat_span * 0.18)
    max_lat = max(lats) + (lat_span * 0.18)
    min_lng = min(lngs) - (lng_span * 0.18)
    max_lng = max(lngs) + (lng_span * 0.18)
    lat_range = max(max_lat - min_lat, 0.001)
    lng_range = max(max_lng - min_lng, 0.001)

    cells = []
    pins = []
    center_index = args.grid_size // 2
    for result in results:
        label = "-" if result.rank is None else str(result.rank)
        matched_title = (result.matched_item or {}).get("title") or "Not found"
        tooltip = f"{result.point.tag} | {result.point.lat:.6f},{result.point.lng:.6f} | {matched_title}"
        left = ((result.point.lng - min_lng) / lng_range) * 100
        top = ((max_lat - result.point.lat) / lat_range) * 100
        center_class = " center-pin" if result.point.row == center_index and result.point.col == center_index else ""
        cells.append(
            f'<div class="cell {rank_class(result.rank)}" title="{html.escape(tooltip)}">'
            f'<span>{html.escape(label)}</span><small>{html.escape(result.point.tag)}</small></div>'
        )
        pins.append(
            f'<div class="rank-pin {rank_class(result.rank)}{center_class}" '
            f'style="left:{left:.3f}%;top:{top:.3f}%;" title="{html.escape(tooltip)}">'
            f'<span>{html.escape(label)}</span><small>{html.escape(result.point.tag)}</small></div>'
        )
    competitors = competitor_counts(results)[:6]
    max_count = max([count for _, count in competitors] or [1])
    competitor_rows = "".join(
        f'<div class="bar-row"><span>{html.escape(title)}</span><b style="width:{(count / max_count) * 100:.1f}%"></b><em>{count}</em></div>'
        for title, count in competitors
    )
    map_zoom = min(max(int(args.zoom), 11), 16)
    google_map_url = (
        f"https://www.google.com/maps?ll={args.center_lat:.7f},{args.center_lng:.7f}"
        f"&z={map_zoom}&t=m&output=embed"
    )
    map_image = getattr(args, "map_image", "")
    if map_image:
        image_path = Path(map_image)
        image_src = image_path.name if image_path.is_absolute() else map_image
        map_surface = f'<img class="map-frame" src="{html.escape(image_src, quote=True)}" alt="Google Static Maps background">'
        map_layer_note = "Map layer: saved Google Static Maps image."
    else:
        map_surface = (
            f'<iframe class="map-frame" src="{html.escape(google_map_url, quote=True)}" '
            'loading="eager" referrerpolicy="no-referrer-when-downgrade"></iframe>'
        )
        map_layer_note = "Map layer: Google Maps embed."
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; color: #17202a; background: #f6f7f9; }}
    main {{ max-width: 980px; margin: 0 auto; }}
    header {{ padding: 32px 32px 20px; background: #ffffff; border-bottom: 1px solid #d7dde5; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; }}
    .meta {{ color: #52606d; margin-bottom: 24px; }}
    .layout {{ display: grid; grid-template-columns: 1.45fr .55fr; gap: 20px; padding: 24px 32px 16px; }}
    .supporting {{ padding: 0 32px 32px; }}
    .map-shell {{ position: relative; height: min(62vw, 620px); min-height: 460px; overflow: hidden; border-radius: 8px; border: 1px solid #c9d3df; background: #dfe7ef; }}
    .map-frame {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; object-fit: cover; filter: saturate(.96) contrast(.98); }}
    .pin-layer {{ position: absolute; inset: 0; z-index: 2; pointer-events: none; }}
    .rank-pin {{ position: absolute; width: 48px; height: 48px; transform: translate(-50%, -50%); border-radius: 999px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 3px solid #fff; box-shadow: 0 5px 16px rgba(15, 23, 42, .45); font-weight: 800; }}
    .rank-pin span {{ font-size: 20px; line-height: 1; }}
    .rank-pin small {{ font-size: 9px; margin-top: 2px; opacity: .84; }}
    .center-pin {{ outline: 4px solid rgba(15, 94, 238, .65); outline-offset: 3px; }}
    .map-legend {{ display: flex; flex-wrap: wrap; gap: 8px 14px; margin-top: 12px; color: #52606d; font-size: 13px; }}
    .legend-dot {{ display: inline-block; width: 11px; height: 11px; border-radius: 999px; margin-right: 5px; vertical-align: -1px; }}
    .grid {{ display: grid; grid-template-columns: repeat({args.grid_size}, minmax(64px, 1fr)); gap: 8px; }}
    .cell {{ aspect-ratio: 1; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 1px solid rgba(0,0,0,.08); }}
    .cell span {{ font-size: 26px; font-weight: 700; line-height: 1; }}
    .cell small {{ margin-top: 6px; color: rgba(0,0,0,.55); }}
    .rank-one {{ background: #0f9f6e; color: white; }}
    .rank-top3 {{ background: #8bd450; color: #102a12; }}
    .rank-visible {{ background: #ffd166; color: #3b2f00; }}
    .rank-buried {{ background: #f79d65; color: #3a1600; }}
    .rank-none {{ background: #e55b5b; color: white; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; padding: 0 32px 8px; }}
    .metric {{ background: white; border: 1px solid #d7dde5; border-radius: 8px; padding: 14px; }}
    .metric strong {{ display: block; font-size: 22px; }}
    .panel {{ background: #fff; border: 1px solid #d7dde5; border-radius: 8px; padding: 16px; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .bar-row {{ position: relative; display: grid; grid-template-columns: 1fr 32px; gap: 8px; align-items: center; margin: 10px 0; min-height: 28px; }}
    .bar-row b {{ position: absolute; left: 0; top: 0; bottom: 0; background: #dbeafe; border-radius: 6px; z-index: 0; }}
    .bar-row span, .bar-row em {{ position: relative; z-index: 1; padding: 0 8px; font-style: normal; }}
    .notes {{ margin-top: 16px; color: #52606d; font-size: 14px; line-height: 1.4; }}
    a {{ color: #155eef; }}
    @media (max-width: 760px) {{ .layout, .metrics {{ grid-template-columns: 1fr; }} .map-shell {{ min-height: 420px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{html.escape(title)}</h1>
      <div class="meta">Keyword: {html.escape(args.keyword)} | {html.escape(args.location_label)} | {args.grid_size}x{args.grid_size}, {args.radius_km:g} km radius | DataForSEO {html.escape(args.method)}</div>
    </header>
    <section class="metrics">
      <div class="metric"><strong>{metrics['solv']}%</strong>Map Pack Visibility</div>
      <div class="metric"><strong>{metrics['visible_share']}%</strong>Top 10 visibility</div>
      <div class="metric"><strong>{metrics['average_rank'] if metrics['average_rank'] is not None else 'no data'}</strong>Avg rank</div>
      <div class="metric"><strong>{metrics['not_found_points']}</strong>Not found</div>
    </section>
    <section class="layout">
      <div class="panel">
        <h2>Google Maps Geo-Grid</h2>
        <div class="map-shell">
          {map_surface}
          <div class="pin-layer">{''.join(pins)}</div>
        </div>
        <div class="map-legend">
          <span><i class="legend-dot rank-top3"></i>top 3</span>
          <span><i class="legend-dot rank-visible"></i>rank 4-10</span>
          <span><i class="legend-dot rank-none"></i>not found</span>
          <span>Blue ring = business center</span>
        </div>
      </div>
      <aside class="panel">
        <h2>Competitor Pressure</h2>
        {competitor_rows or '<p>no data</p>'}
        <h2>Prospecting Verdict</h2>
        <p><strong>{html.escape(verdict)}</strong></p>
        <p>{html.escape(verdict_reason)}</p>
        <p>{html.escape(weak_summary)}</p>
        <div class="notes">{html.escape(map_layer_note)} Rank pins: DataForSEO Google Maps SERP results from each GPS coordinate. Red pins are not guesses; they mean the target was not found in the returned Maps depth at that coordinate.</div>
        <p><a href="{html.escape(markdown_path.name)}">Open Markdown report</a></p>
      </aside>
    </section>
    <section class="supporting">
      <div class="panel"><h2>Rank Grid Data</h2><div class="grid">{''.join(cells)}</div></div>
    </section>
  </main>
</body>
</html>
"""


def write_outputs(args: argparse.Namespace, tasks: list[dict[str, Any]], payload: dict[str, Any], results: list[PointResult]) -> dict[str, str]:
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    run_slug = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{normalize(args.target_name)[:32] or 'target'}"
    output_dir = Path(args.output_dir).resolve() / run_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_payload = output_dir / "dataforseo-response.raw.json"
    raw_tasks = output_dir / "dataforseo-request-tasks.json"
    parsed_json = output_dir / "parsed-grid.json"
    markdown_path = output_dir / "heatmap-report.md"
    html_path = output_dir / "heatmap-report.html"

    raw_tasks.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    raw_payload.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    parsed_json.write_text(
        json.dumps(
            {
                "target": args.target_name,
                "keyword": args.keyword,
                "location": args.location_label,
                "metrics": calculate_metrics(results),
                "results": [
                    {
                        "point": result.point.__dict__,
                        "rank": result.rank,
                        "matched_item": result.matched_item,
                        "top_items": result.top_items,
                        "error": result.error,
                    }
                    for result in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(args, results, payload, started_at), encoding="utf-8")
    html_path.write_text(render_html(args, results, markdown_path), encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "raw_payload": str(raw_payload),
        "raw_tasks": str(raw_tasks),
        "parsed_json": str(parsed_json),
        "markdown": str(markdown_path),
        "html": str(html_path),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate or run a DataForSEO Google Maps geo-grid scan")
    parser.add_argument("--method", choices=["live", "priority", "standard"], default="standard")
    parser.add_argument("--keyword", required=True, help="Local-intent keyword, for example 'pizza' or 'emergency dentist'")
    parser.add_argument("--target-name", required=True, help="Business name to match in Maps SERP items")
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lng", type=float, required=True)
    parser.add_argument("--location-label", default="Unspecified location")
    parser.add_argument("--radius-km", type=float, default=2.0)
    parser.add_argument("--grid-size", type=int, default=3)
    parser.add_argument("--depth", type=int, default=100)
    parser.add_argument("--zoom", type=int, default=15)
    parser.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    parser.add_argument("--language-code", default="en")
    parser.add_argument("--se-domain", default="google.com")
    parser.add_argument("--search-places", action="store_true", help="Enable DataForSEO search_places mode")
    parser.add_argument("--target-domain", default="")
    parser.add_argument("--target-cid", default="")
    parser.add_argument("--target-place-id", default="")
    parser.add_argument("--match-threshold", type=float, default=0.82)
    parser.add_argument("--top-competitors", type=int, default=5)
    parser.add_argument("--output-dir", default="runs")
    parser.add_argument("--map-image", default="", help="Optional saved Google Static Maps image to use as the report background")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--poll-seconds", type=int, default=360)
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--execute", action="store_true", help="Spend DataForSEO credits; omitted means estimate only")
    parser.add_argument("--confirm-cost-usd", type=float, default=0.0, help="Required maximum estimated spend when --execute is used")
    parser.add_argument("--estimate-only", action="store_true", help="Deprecated compatibility flag; estimates are already the default")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    validate_run_args(args)
    points = generate_grid(args.center_lat, args.center_lng, args.grid_size, args.radius_km)
    tasks = build_tasks(args, points)
    live_estimate = estimate_scan_cost(len(tasks), args.depth, "live")
    priority_estimate = estimate_scan_cost(len(tasks), args.depth, "priority")
    standard_estimate = estimate_scan_cost(len(tasks), args.depth, "standard")

    if args.estimate_only or not args.execute:
        print(
            json.dumps(
                {
                    "status": "estimate-only",
                    "execute": False,
                    "tasks": len(tasks),
                    "live_estimate_usd": round(live_estimate, 4),
                    "priority_estimate_usd": round(priority_estimate, 4),
                    "standard_estimate_usd": round(standard_estimate, 4),
                    "grid": [point.__dict__ for point in points],
                },
                indent=2,
            )
        )
        return 0

    expected = {
        "live": live_estimate,
        "priority": priority_estimate,
        "standard": standard_estimate,
    }[args.method]
    if expected > args.confirm_cost_usd:
        raise RuntimeError(
            f"Refusing to execute: estimated cost ${expected:.4f} exceeds "
            f"--confirm-cost-usd ${args.confirm_cost_usd:.4f}"
        )

    if args.method == "live":
        print(f"Running {len(tasks)} DataForSEO Maps live tasks (~${live_estimate:.4f})", file=sys.stderr)
        payload = call_dataforseo_live(tasks, timeout=args.timeout)
    else:
        print(f"Posting {len(tasks)} DataForSEO Maps {args.method} queue tasks (~${expected:.4f})", file=sys.stderr)
        payload = call_dataforseo_standard(tasks, timeout=args.timeout, poll_seconds=args.poll_seconds, poll_interval=args.poll_interval)
    results = parse_results(payload, points, args)
    outputs = write_outputs(args, tasks, payload, results)
    metrics = calculate_metrics(results)
    print(json.dumps({"metrics": metrics, "outputs": outputs}, indent=2))
    return 2 if metrics["error_points"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
