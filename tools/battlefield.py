#!/usr/bin/env python3
"""Multi-competitor Fog of War and Tactical Battlefield engine for legends-geogrid.

Builds an 11-faction geospatial intelligence model (Target + Top 10 Rivals),
computes per-coordinate Fog of War states, Sovereign Turf ownership, Incumbent
Vulnerability and Opportunity Scores (0..100), Gravity Anomalies, and Campaign
Orders from multi-lane study directories, single-lane run directories, or
standalone parsed-grid JSON files.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from local_heatmap_poc import (  # noqa: E402
    canonical_domain,
    domain_matches,
    extract_items,
    normalize,
    organic_maps_items,
    organic_rank,
)


FACTION_PALETTE: dict[str, dict[str, str]] = {
    "TARGET": {"color": "#10b981", "short_code": "YOU"},
    "F01": {"color": "#3b82f6", "short_code": "R01"},
    "F02": {"color": "#8b5cf6", "short_code": "R02"},
    "F03": {"color": "#ec4899", "short_code": "R03"},
    "F04": {"color": "#f97316", "short_code": "R04"},
    "F05": {"color": "#06b6d4", "short_code": "R05"},
    "F06": {"color": "#eab308", "short_code": "R06"},
    "F07": {"color": "#14b8a6", "short_code": "R07"},
    "F08": {"color": "#f43f5e", "short_code": "R08"},
    "F09": {"color": "#a855f7", "short_code": "R09"},
    "F10": {"color": "#64748b", "short_code": "R10"},
}

COMPASS_SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
SECTOR_NAMES = {
    "CORE": "Core Citadel",
    "N": "Northern",
    "NE": "Northeastern",
    "E": "Eastern",
    "SE": "Southeastern",
    "S": "Southern",
    "SW": "Southwestern",
    "W": "Western",
    "NW": "Northwestern",
}

_EM_DASH_CHAR = chr(8212)
_EN_DASH_CHAR = chr(8211)


def _clean_text(value: Any) -> str:
    """Sanitize text and replace dash characters with standard ASCII punctuation."""
    if value is None:
        return ""
    text = str(value).replace(_EM_DASH_CHAR, " - ").replace(_EN_DASH_CHAR, "-")
    text = re.sub(r"\s+-\s+-\s+", " - ", text)
    return text.strip()


def _sanitize_tree(obj: Any) -> Any:
    """Recursively ensure no forbidden dash characters remain in any output string."""
    if isinstance(obj, str):
        return obj.replace(_EM_DASH_CHAR, " - ")
    if isinstance(obj, list):
        return [_sanitize_tree(item) for item in obj]
    if isinstance(obj, tuple):
        return [_sanitize_tree(item) for item in obj]
    if isinstance(obj, dict):
        return {_sanitize_tree(k): _sanitize_tree(v) for k, v in obj.items()}
    return obj


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = float(value)
        return num if math.isfinite(num) else None
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = int(round(float(value)))
        return num
    except (TypeError, ValueError):
        return None


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute exact Haversine distance in kilometers between two WGS84 coordinates."""
    r_earth = 6371.0088
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lng2) - float(lng1))
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    a = min(1.0, max(0.0, a))
    return 2.0 * r_earth * math.asin(math.sqrt(a))


def compass_sector(
    center_lat: float,
    center_lng: float,
    lat: float,
    lng: float,
    radius_km: float = 0.0,
) -> str:
    """Compute 8-way compass sector (N, NE, E, SE, S, SW, W, NW) or CORE."""
    dist_km = haversine_km(center_lat, center_lng, lat, lng)
    core_threshold = min(0.45, 0.15 * float(radius_km)) if (radius_km and radius_km > 0) else 0.05
    if dist_km < core_threshold:
        return "CORE"

    dy = (float(lat) - float(center_lat)) * 111.32
    mean_lat_rad = math.radians((float(center_lat) + float(lat)) / 2.0)
    dlon = (float(lng) - float(center_lng) + 180.0) % 360.0 - 180.0
    dx = dlon * 111.32 * math.cos(mean_lat_rad)

    bearing = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
    index = int(((bearing + 22.5) % 360.0) // 45.0) % 8
    return COMPASS_SECTORS[index]


class StudyLanesBundle(list):
    """List of loaded study lanes that also exposes study-level metadata attributes."""

    def __init__(
        self,
        lanes: list[dict[str, Any]],
        *,
        source_path: Path,
        business: dict[str, Any] | None = None,
        profile_review: dict[str, Any] | None = None,
        report_config: dict[str, Any] | None = None,
        study_plan: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(lanes)
        self.lanes = lanes
        self.source_path = source_path
        self.business = business or {}
        self.profile_review = profile_review or {}
        self.report_config = report_config or {}
        self.study_plan = study_plan or {}

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return default


def _normalize_fs_path(raw_path: str | Path, base_dir: Path | None = None) -> Path:
    """Resolve Windows, POSIX, or MSYS (/E/...) paths gracefully."""
    if isinstance(raw_path, Path):
        text = str(raw_path)
    else:
        text = str(raw_path).strip()

    msys_match = re.match(r"^/([a-zA-Z])/(.*)$", text)
    if msys_match:
        drive = msys_match.group(1).upper()
        rest = msys_match.group(2)
        candidate = Path(f"{drive}:/{rest}")
        if candidate.exists():
            return candidate.resolve()

    candidate = Path(text)
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()
    if base_dir is not None:
        rel_candidate = (base_dir / text).resolve()
        if rel_candidate.exists():
            return rel_candidate
    return candidate


def _find_parsed_grid_in_lane_dir(lane_dir: Path) -> Path | None:
    """Locate parsed-grid.json within a lane directory."""
    if not lane_dir.is_dir():
        return None
    direct = lane_dir / "parsed-grid.json"
    if direct.is_file():
        return direct.resolve()

    collector = lane_dir / "collector-output.json"
    if collector.is_file():
        try:
            payload = json.loads(collector.read_text(encoding="utf-8-sig"))
            raw_parsed = (payload.get("outputs") or {}).get("parsed_json")
            if raw_parsed:
                resolved = _normalize_fs_path(raw_parsed, lane_dir)
                if resolved.is_file():
                    return resolved
        except (OSError, ValueError, KeyError):
            pass

    candidates = sorted(lane_dir.rglob("parsed-grid.json"))
    if candidates:
        return candidates[0].resolve()
    return None


def _resolve_lane_parsed_path(
    raw_records_path: str | Path | None,
    base_dir: Path,
    lane_number: int | None = None,
) -> Path:
    """Resolve a lane's parsed-grid.json path with fallback to lane-N directory search."""
    if raw_records_path:
        candidate = _normalize_fs_path(raw_records_path, base_dir)
        if candidate.is_file():
            return candidate
        if candidate.parent.is_dir():
            found = _find_parsed_grid_in_lane_dir(candidate.parent)
            if found is not None:
                return found

    if lane_number is not None:
        lane_dir = base_dir / f"lane-{lane_number}"
        found = _find_parsed_grid_in_lane_dir(lane_dir)
        if found is not None:
            return found

    raise FileNotFoundError(
        f"Unable to locate parsed-grid.json for lane {lane_number or raw_records_path} in {base_dir}"
    )


def _enrich_item_dict(raw_item: dict[str, Any], fallback_rank: int) -> dict[str, Any]:
    """Normalize a raw or parsed SERP item into a rich 18-field dictionary."""
    rk = organic_rank(raw_item)
    if rk is None:
        raw_rk = raw_item.get("rank")
        if isinstance(raw_rk, int) and not isinstance(raw_rk, bool) and raw_rk > 0:
            rk = raw_rk
        else:
            rk = fallback_rank

    rating_field = raw_item.get("rating")
    if isinstance(rating_field, dict):
        rating_val = _to_float(rating_field.get("value"))
        votes_val = _to_int(rating_field.get("votes_count"))
    else:
        rating_val = _to_float(rating_field)
        votes_val = _to_int(raw_item.get("votes_count"))

    raw_add_cats = raw_item.get("additional_categories")
    if isinstance(raw_add_cats, list):
        additional_categories = [_clean_text(c) for c in raw_add_cats if c and _clean_text(c)]
    else:
        additional_categories = []

    raw_domain = raw_item.get("domain")
    raw_url = raw_item.get("url")
    domain_str = _clean_text(raw_domain) if raw_domain else None
    if not domain_str and raw_url:
        domain_str = canonical_domain(str(raw_url)) or None

    cid_val = raw_item.get("cid")
    place_id_val = raw_item.get("place_id")
    is_claimed_val = raw_item.get("is_claimed")

    return {
        "rank": rk,
        "rank_group": raw_item.get("rank_group") if raw_item.get("rank_group") is not None else rk,
        "rank_absolute": raw_item.get("rank_absolute") if raw_item.get("rank_absolute") is not None else rk,
        "title": _clean_text(raw_item.get("title") or ""),
        "category": _clean_text(raw_item.get("category")) if raw_item.get("category") else None,
        "additional_categories": additional_categories,
        "domain": domain_str,
        "url": _clean_text(raw_url) if raw_url else None,
        "address": _clean_text(raw_item.get("address")) if raw_item.get("address") else None,
        "rating": rating_val,
        "votes_count": votes_val,
        "cid": str(cid_val).strip() if cid_val not in (None, "") else None,
        "place_id": str(place_id_val).strip() if place_id_val not in (None, "") else None,
        "latitude": _to_float(raw_item.get("latitude")),
        "longitude": _to_float(raw_item.get("longitude")),
        "is_claimed": bool(is_claimed_val) if is_claimed_val is not None else None,
        "price_level": _clean_text(raw_item.get("price_level")) if raw_item.get("price_level") is not None else None,
        "work_hours": raw_item.get("work_hours"),
    }


def _enrich_lane_from_files(
    parsed_path: Path,
    *,
    lane_id: str,
    lane_number: int,
    query_override: str | None = None,
    label_override: str | None = None,
    narrative: str | None = None,
) -> dict[str, Any]:
    """Load a lane's parsed-grid.json and enrich with dataforseo-response.raw.json if present."""
    parsed_data = json.loads(parsed_path.read_text(encoding="utf-8-sig"))
    raw_path = parsed_path.parent / "dataforseo-response.raw.json"
    enriched_from_raw = False
    raw_tasks_by_tag: dict[str, dict[str, Any]] = {}
    raw_tasks_list: list[dict[str, Any]] = []

    if raw_path.is_file():
        try:
            raw_payload = json.loads(raw_path.read_text(encoding="utf-8-sig"))
            raw_tasks_list = [t for t in (raw_payload.get("tasks") or []) if isinstance(t, dict)]
            for idx, task in enumerate(raw_tasks_list):
                tag = (task.get("data") or {}).get("tag") or task.get("tag")
                if tag and str(tag) not in raw_tasks_by_tag:
                    raw_tasks_by_tag[str(tag)] = task
            enriched_from_raw = bool(raw_tasks_list)
        except (OSError, ValueError):
            enriched_from_raw = False

    raw_results = parsed_data.get("results") or []
    target_name = _clean_text(
        parsed_data.get("target")
        or (parsed_data.get("measurement_settings") or {}).get("target_name")
        or "Target Business"
    )
    keyword = _clean_text(
        query_override
        or parsed_data.get("keyword")
        or (parsed_data.get("measurement_settings") or {}).get("keyword")
        or label_override
        or lane_id
    )
    label = _clean_text(label_override or keyword)

    enriched_results: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_results):
        point = dict(row.get("point") or {})
        tag = str(point.get("tag") or f"p{idx}")
        point["tag"] = tag
        point["row"] = int(point.get("row", 0))
        point["col"] = int(point.get("col", 0))
        point["lat"] = float(point.get("lat", 0.0))
        point["lng"] = float(point.get("lng", 0.0))

        point_rank = _to_int(row.get("rank"))
        if point_rank is not None and point_rank <= 0:
            point_rank = None

        serp_items: list[dict[str, Any]] = []
        task = raw_tasks_by_tag.get(tag)
        if task is None and enriched_from_raw and idx < len(raw_tasks_list):
            task = raw_tasks_list[idx]

        if task is not None:
            extracted_raw, _ = extract_items(task)
            org_raw = organic_maps_items(extracted_raw)
            sorted_org = sorted(
                org_raw,
                key=lambda it: (
                    organic_rank(it) if organic_rank(it) is not None else math.inf,
                    it.get("rank_absolute") if isinstance(it.get("rank_absolute"), int) else math.inf,
                ),
            )
            for item_idx, raw_item in enumerate(sorted_org, start=1):
                rich_item = _enrich_item_dict(raw_item, fallback_rank=item_idx)
                if rich_item["title"]:
                    serp_items.append(rich_item)
        else:
            existing_top = row.get("top_items") or []
            for item_idx, item in enumerate(existing_top, start=1):
                if isinstance(item, dict):
                    rich_item = _enrich_item_dict(item, fallback_rank=item_idx)
                    if rich_item["title"]:
                        serp_items.append(rich_item)

            if point_rank is not None:
                already_has_target = any(
                    it["rank"] == point_rank
                    or (normalize(it["title"]) == normalize(target_name) and normalize(target_name))
                    for it in serp_items
                )
                if not already_has_target:
                    matched_raw = row.get("matched_item")
                    if isinstance(matched_raw, dict) and matched_raw.get("title"):
                        synth_source = dict(matched_raw, rank=point_rank)
                    else:
                        synth_source = {"title": target_name, "rank": point_rank}
                    serp_items.append(_enrich_item_dict(synth_source, fallback_rank=point_rank))
                    serp_items.sort(key=lambda it: it["rank"] or math.inf)

        matched_enriched: dict[str, Any] | None = None
        if isinstance(row.get("matched_item"), dict):
            matched_enriched = _enrich_item_dict(
                row["matched_item"],
                fallback_rank=point_rank or 1,
            )
        if point_rank is not None:
            for it in serp_items:
                if it["rank"] == point_rank:
                    matched_enriched = it
                    break

        status = row.get("status")
        if not status:
            if row.get("error"):
                status = "provider_error"
            elif point_rank is not None:
                status = "found"
            elif serp_items:
                status = "not_returned_depth_reached"
            else:
                status = "empty_results"

        enriched_results.append(
            {
                "point": point,
                "rank": point_rank,
                "status": str(status),
                "error": _clean_text(row.get("error")) if row.get("error") else None,
                "matched_item": matched_enriched,
                "top_items": serp_items,
                "serp_items": serp_items,
                "returned_items_count": int(row.get("returned_items_count") or len(serp_items)),
                "organic_items_count": int(row.get("organic_items_count") or len(serp_items)),
                "observed_ranks": list(
                    row.get("observed_ranks")
                    or sorted({it["rank"] for it in serp_items if isinstance(it.get("rank"), int)})
                ),
            }
        )

    settings = dict(parsed_data.get("measurement_settings") or {})
    if not settings.get("grid_size") and enriched_results:
        max_rc = max(max(r["point"]["row"], r["point"]["col"]) for r in enriched_results)
        settings["grid_size"] = max_rc + 1

    grid_size = int(settings.get("grid_size") or max(1, int(round(math.sqrt(len(enriched_results))))))
    if settings.get("center_lat") is None or settings.get("center_lng") is None:
        center_rc = grid_size // 2
        center_pt = next(
            (
                r["point"]
                for r in enriched_results
                if r["point"]["row"] == center_rc and r["point"]["col"] == center_rc
            ),
            None,
        )
        if center_pt is not None:
            settings["center_lat"] = center_pt["lat"]
            settings["center_lng"] = center_pt["lng"]
        elif enriched_results:
            settings["center_lat"] = sum(r["point"]["lat"] for r in enriched_results) / len(enriched_results)
            settings["center_lng"] = sum(r["point"]["lng"] for r in enriched_results) / len(enriched_results)
        else:
            settings["center_lat"] = 0.0
            settings["center_lng"] = 0.0

    if not settings.get("radius_km") and enriched_results:
        c_lat = float(settings["center_lat"])
        c_lng = float(settings["center_lng"])
        center_rc = grid_size // 2
        edge_pts = [
            r["point"]
            for r in enriched_results
            if (r["point"]["row"] == 0 and r["point"]["col"] == center_rc)
            or (r["point"]["row"] == center_rc and r["point"]["col"] == 0)
        ]
        if edge_pts:
            settings["radius_km"] = round(
                max(haversine_km(c_lat, c_lng, p["lat"], p["lng"]) for p in edge_pts),
                2,
            )
        else:
            max_d = max(
                (haversine_km(c_lat, c_lng, r["point"]["lat"], r["point"]["lng"]) for r in enriched_results),
                default=1.0,
            )
            settings["radius_km"] = round(max(0.5, max_d / math.sqrt(2.0)), 2)

    settings.setdefault("target_name", target_name)
    settings.setdefault("keyword", keyword)
    settings.setdefault("depth", 20)
    settings.setdefault("zoom", 15)

    return {
        "lane_id": lane_id,
        "query_id": lane_id,
        "lane_number": lane_number,
        "query": keyword,
        "keyword": keyword,
        "label": label,
        "narrative": _clean_text(narrative) if narrative else "",
        "parsed_path": str(parsed_path.resolve()),
        "raw_path": str(raw_path.resolve()) if enriched_from_raw else None,
        "enriched_from_raw": enriched_from_raw,
        "target": target_name,
        "location": _clean_text(parsed_data.get("location") or ""),
        "measurement_settings": settings,
        "metrics": dict(parsed_data.get("metrics") or {}),
        "results": enriched_results,
    }


def _extract_gbp_evidence(base_dir: Path, study_plan: dict[str, Any]) -> dict[str, Any]:
    """Extract target business details from saved GBP evidence files if available."""
    info: dict[str, Any] = {}
    evidence_dir = base_dir / "evidence"
    if not evidence_dir.is_dir():
        return info

    for source in study_plan.get("sources") or []:
        if not isinstance(source, dict) or source.get("kind") != "gbp":
            continue
        fname = source.get("file")
        if not fname:
            continue
        fpath = evidence_dir / fname
        if not fpath.is_file():
            continue
        try:
            payload = json.loads(fpath.read_text(encoding="utf-8-sig"))
            tasks = payload.get("tasks") or []
            if not tasks:
                continue
            results = tasks[0].get("result") or []
            if not results:
                continue
            items = results[0].get("items") or []
            if not items or not isinstance(items[0], dict):
                continue
            rich = _enrich_item_dict(items[0], fallback_rank=1)
            info.update({k: v for k, v in rich.items() if v not in (None, "", [])})
            break
        except (OSError, ValueError, KeyError, IndexError):
            continue
    return info


def _extract_profile_review_facts(profile_review: dict[str, Any] | None) -> dict[str, Any]:
    """Extract target business metadata from report-config or study-receipt profile_review."""
    info: dict[str, Any] = {}
    if not isinstance(profile_review, dict):
        return info
    if profile_review.get("cid"):
        info["cid"] = str(profile_review["cid"]).strip()

    for fact in profile_review.get("facts") or []:
        if not isinstance(fact, dict) or fact.get("status") != "observed":
            continue
        field = fact.get("field")
        val = fact.get("value")
        if field == "title" and val:
            info["title"] = _clean_text(val)
        elif field == "category" and val:
            info["category"] = _clean_text(val)
        elif field == "address" and val:
            info["address"] = _clean_text(val)
        elif field == "url" and val:
            info["url"] = _clean_text(val)
            dom = canonical_domain(str(val))
            if dom:
                info["domain"] = dom
        elif field == "additional_categories" and isinstance(val, list):
            info["additional_categories"] = [_clean_text(c) for c in val if c and _clean_text(c)]
        elif field == "rating" and isinstance(val, dict):
            r_val = _to_float(val.get("value"))
            v_val = _to_int(val.get("votes_count"))
            if r_val is not None:
                info["rating"] = r_val
            if v_val is not None:
                info["votes_count"] = v_val
    return info


def load_study_lanes(source_path: str | Path) -> StudyLanesBundle:
    """Resolve study lanes from a study directory, lane folder, report-config.json, or parsed-grid.json."""
    resolved_input = _normalize_fs_path(source_path)
    if not resolved_input.exists():
        raise FileNotFoundError(f"Input path does not exist: {source_path}")

    report_config: dict[str, Any] = {}
    study_plan: dict[str, Any] = {}
    profile_review: dict[str, Any] = {}
    business_meta: dict[str, Any] = {}
    lanes: list[dict[str, Any]] = []

    if resolved_input.is_file():
        payload = json.loads(resolved_input.read_text(encoding="utf-8-sig"))
        base_dir = resolved_input.parent
        if isinstance(payload, dict) and isinstance(payload.get("lanes"), list):
            report_config = payload
            business_meta.update(payload.get("business") or {})
            profile_review = payload.get("profile_review") or {}
            plan_path = base_dir / "evidence" / "study-plan.json"
            if plan_path.is_file():
                study_plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
                for k, v in (study_plan.get("business") or {}).items():
                    business_meta.setdefault(k, v)
            for idx, lane_cfg in enumerate(payload["lanes"], start=1):
                lane_id = str(lane_cfg.get("query_id") or f"q{idx}")
                parsed_path = _resolve_lane_parsed_path(
                    lane_cfg.get("records_path"),
                    base_dir,
                    lane_number=idx,
                )
                lanes.append(
                    _enrich_lane_from_files(
                        parsed_path,
                        lane_id=lane_id,
                        lane_number=idx,
                        query_override=lane_cfg.get("query"),
                        label_override=lane_cfg.get("label"),
                        narrative=lane_cfg.get("narrative"),
                    )
                )
        elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
            lanes.append(
                _enrich_lane_from_files(
                    resolved_input,
                    lane_id="q1",
                    lane_number=1,
                )
            )
        elif isinstance(payload, dict) and isinstance(payload.get("queries"), list):
            study_plan = payload
            business_meta.update(payload.get("business") or {})
            run_root = base_dir.parent if base_dir.name == "evidence" else base_dir
            return load_study_lanes(run_root)
        else:
            raise ValueError(f"Unsupported JSON file format at {resolved_input}")
    else:
        base_dir = resolved_input
        if (
            (base_dir / "baseline").is_dir()
            and not (base_dir / "report-config.json").is_file()
            and not any(c.is_dir() and c.name.startswith("lane-") for c in base_dir.iterdir())
        ):
            base_dir = base_dir / "baseline"
        for cfg_name in ("recovered-report-config.json", "report-config.py", "report-config.json"):
            if cfg_name.endswith(".py"):
                continue
            cfg_path = base_dir / cfg_name
            if cfg_path.is_file():
                try:
                    report_config = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
                    break
                except (OSError, ValueError):
                    pass

        plan_path = base_dir / "evidence" / "study-plan.json"
        if plan_path.is_file():
            try:
                study_plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                study_plan = {}

        receipt_path = base_dir / "study-receipt.json"
        if receipt_path.is_file():
            try:
                receipt_data = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
                if not profile_review and isinstance(receipt_data.get("profile_review"), dict):
                    profile_review = receipt_data["profile_review"]
            except (OSError, ValueError):
                pass

        if isinstance(report_config.get("business"), dict):
            business_meta.update(report_config["business"])
        if isinstance(study_plan.get("business"), dict):
            for k, v in study_plan["business"].items():
                business_meta.setdefault(k, v)
        if not profile_review and isinstance(report_config.get("profile_review"), dict):
            profile_review = report_config["profile_review"]

        lane_dirs: list[tuple[int, Path]] = []
        for child in base_dir.iterdir():
            if child.is_dir():
                m = re.match(r"^lane-(\d+)$", child.name)
                if m:
                    lane_dirs.append((int(m.group(1)), child))
        lane_dirs.sort(key=lambda pair: pair[0])

        cfg_lanes = report_config.get("lanes") if isinstance(report_config.get("lanes"), list) else []
        selected_queries = [
            q for q in (study_plan.get("queries") or []) if isinstance(q, dict) and q.get("selected")
        ]

        if lane_dirs:
            for idx, (lane_num, lane_dir) in enumerate(lane_dirs, start=1):
                parsed_path = _find_parsed_grid_in_lane_dir(lane_dir)
                if parsed_path is None:
                    continue
                cfg_lane = cfg_lanes[idx - 1] if idx - 1 < len(cfg_lanes) else {}
                plan_q = selected_queries[idx - 1] if idx - 1 < len(selected_queries) else {}
                lane_id = str(cfg_lane.get("query_id") or f"q{lane_num}")
                query_str = cfg_lane.get("query") or plan_q.get("query")
                label_str = cfg_lane.get("label") or query_str
                narrative_str = cfg_lane.get("narrative")
                lanes.append(
                    _enrich_lane_from_files(
                        parsed_path,
                        lane_id=lane_id,
                        lane_number=lane_num,
                        query_override=query_str,
                        label_override=label_str,
                        narrative=narrative_str,
                    )
                )
        elif cfg_lanes:
            for idx, cfg_lane in enumerate(cfg_lanes, start=1):
                lane_id = str(cfg_lane.get("query_id") or f"q{idx}")
                parsed_path = _resolve_lane_parsed_path(
                    cfg_lane.get("records_path"),
                    base_dir,
                    lane_number=idx,
                )
                lanes.append(
                    _enrich_lane_from_files(
                        parsed_path,
                        lane_id=lane_id,
                        lane_number=idx,
                        query_override=cfg_lane.get("query"),
                        label_override=cfg_lane.get("label"),
                        narrative=cfg_lane.get("narrative"),
                    )
                )
        else:
            single_parsed = _find_parsed_grid_in_lane_dir(base_dir)
            if single_parsed is None:
                raise FileNotFoundError(f"No study lanes or parsed-grid.json found in {base_dir}")
            lanes.append(
                _enrich_lane_from_files(
                    single_parsed,
                    lane_id="q1",
                    lane_number=1,
                )
            )

    if not lanes:
        raise ValueError(f"No valid lanes loaded from {source_path}")

    base_for_evidence = resolved_input if resolved_input.is_dir() else resolved_input.parent
    gbp_info = _extract_gbp_evidence(base_for_evidence, study_plan)
    prof_info = _extract_profile_review_facts(profile_review)

    first_lane = lanes[0]
    first_settings = first_lane.get("measurement_settings") or {}
    merged_business: dict[str, Any] = {
        "name": _clean_text(
            business_meta.get("name")
            or prof_info.get("title")
            or gbp_info.get("title")
            or first_lane.get("target")
            or first_settings.get("target_name")
            or "Target Business"
        ),
        "cid": (
            str(
                business_meta.get("cid")
                or prof_info.get("cid")
                or gbp_info.get("cid")
                or first_settings.get("target_cid")
                or ""
            ).strip()
            or None
        ),
        "place_id": (
            str(
                business_meta.get("place_id")
                or gbp_info.get("place_id")
                or first_settings.get("target_place_id")
                or ""
            ).strip()
            or None
        ),
        "domain": (
            canonical_domain(
                business_meta.get("domain")
                or business_meta.get("website")
                or prof_info.get("domain")
                or gbp_info.get("domain")
                or first_settings.get("target_domain")
            )
            or None
        ),
        "website": _clean_text(
            business_meta.get("website")
            or business_meta.get("domain")
            or prof_info.get("url")
            or gbp_info.get("url")
            or first_settings.get("target_domain")
            or ""
        )
        or None,
        "category": _clean_text(prof_info.get("category") or gbp_info.get("category") or "") or None,
        "additional_categories": list(
            prof_info.get("additional_categories") or gbp_info.get("additional_categories") or []
        ),
        "address": _clean_text(prof_info.get("address") or gbp_info.get("address") or "") or None,
        "location": _clean_text(
            business_meta.get("location")
            or business_meta.get("location_label")
            or first_lane.get("location")
            or ""
        ),
        "lat": _to_float(business_meta.get("lat"))
        or _to_float(gbp_info.get("latitude"))
        or _to_float(first_settings.get("center_lat"))
        or 0.0,
        "lng": _to_float(business_meta.get("lng"))
        or _to_float(gbp_info.get("longitude"))
        or _to_float(first_settings.get("center_lng"))
        or 0.0,
        "rating": _to_float(prof_info.get("rating")) or _to_float(gbp_info.get("rating")),
        "votes_count": _to_int(prof_info.get("votes_count")) or _to_int(gbp_info.get("votes_count")),
    }

    return StudyLanesBundle(
        lanes,
        source_path=resolved_input,
        business=merged_business,
        profile_review=profile_review,
        report_config=report_config,
        study_plan=study_plan,
    )


def _is_target_item(item: dict[str, Any], target_meta: dict[str, Any]) -> bool:
    """Determine if a SERP item represents the Target Business."""
    target_cid = str(target_meta.get("cid") or "").strip()
    item_cid = str(item.get("cid") or "").strip()
    if target_cid and item_cid:
        return target_cid == item_cid

    target_place_id = str(target_meta.get("place_id") or "").strip()
    item_place_id = str(item.get("place_id") or "").strip()
    if target_place_id and item_place_id:
        return target_place_id == item_place_id

    target_domain = canonical_domain(target_meta.get("domain") or target_meta.get("website"))
    item_dom = canonical_domain(item.get("domain") or item.get("url"))
    if target_domain and item_dom and domain_matches(item_dom, target_domain):
        if not target_cid or not item_cid:
            return True

    target_norm = normalize(target_meta.get("name"))
    item_norm = normalize(item.get("title"))
    if target_norm and item_norm and target_norm == item_norm:
        if not target_cid or not item_cid:
            return True

    return False


def _competitor_identity_key(item: dict[str, Any]) -> str:
    """Build a canonical aggregation key for a competitor item."""
    cid = str(item.get("cid") or "").strip()
    if cid:
        return f"cid:{cid}"
    place_id = str(item.get("place_id") or "").strip()
    if place_id:
        return f"place:{place_id}"
    dom = canonical_domain(item.get("domain") or item.get("url"))
    if dom:
        return f"dom:{dom}"
    title_norm = normalize(item.get("title"))
    return f"title:{title_norm or 'unknown'}"


def _percentile(sorted_values: list[float], q: float) -> float:
    """Compute linear-interpolated percentile (0.0 <= q <= 1.0) on a sorted list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return float(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)


def _classify_rival_archetype(
    *,
    solv_pct: float,
    top3_count: int,
    votes_count: int | None,
    target_votes: int | None,
    gravity_radius_km: float,
    max_top3_distance_km: float,
    radius_km: float,
    sector_top3_counts: Counter[str],
    lane_stats: dict[str, dict[str, Any]],
) -> str:
    """Classify a rival faction into a tactical battlefield archetype."""
    if solv_pct >= 50.0:
        return "REGIONAL_HEGEMON"

    t_votes = target_votes or 0
    r_votes = votes_count or 0
    if top3_count > 0 and (
        (r_votes >= max(350, int(t_votes * 1.4)))
        or (
            ((t_votes > 0 and r_votes >= t_votes) or r_votes >= 180)
            and gravity_radius_km <= max(1.8, 0.9 * radius_km)
            and max_top3_distance_km <= max(2.5, 0.45 * radius_km)
        )
    ):
        return "CITADEL_FORTRESS"

    if top3_count > 0 and (
        (t_votes > 0 and 0 < r_votes < t_votes)
        or (max_top3_distance_km > 2.5 and (t_votes == 0 or r_votes <= t_votes * 1.25))
    ):
        return "OVEREXTENDED_TIGER"

    max_sector_share = (
        (max(sector_top3_counts.values()) / top3_count)
        if top3_count > 0 and sector_top3_counts
        else 0.0
    )
    max_lane_solv = max((st.get("solv_pct", 0.0) for st in lane_stats.values()), default=0.0)
    if (top3_count >= 3 and max_sector_share >= 0.5) or max_lane_solv >= 25.0:
        return "CORRIDOR_BLOCKER"

    if top3_count > 0 and t_votes > 0 and r_votes < t_votes:
        return "OVEREXTENDED_TIGER"

    return "LOCAL_OUTPOST"


def _classify_threat_level(
    *,
    is_target: bool,
    solv_pct: float,
    visible_pct: float,
    top1_count: int,
    top3_count: int,
    total_slots: int,
) -> str:
    if is_target:
        return "SELF"
    if solv_pct >= 35.0 or top1_count >= max(5, int(total_slots * 0.20)):
        return "CRITICAL"
    if solv_pct >= 15.0 or top3_count >= max(3, int(total_slots * 0.10)):
        return "HIGH"
    if solv_pct >= 5.0 or visible_pct >= 20.0 or top3_count >= 1:
        return "MODERATE"
    return "LOW"


def _describe_primary_vulnerability(
    *,
    is_target: bool,
    name: str,
    solv_pct: float,
    top3_count: int,
    votes_count: int | None,
    target_votes: int | None,
    rating: float | None,
    target_rating: float | None,
    domain: str | None,
    categories_count: int,
    max_top3_distance_km: float,
    lane_stats: dict[str, dict[str, Any]],
) -> str:
    if is_target:
        weak_lanes = [lid for lid, st in lane_stats.items() if st.get("solv_pct", 0.0) < 50.0]
        if solv_pct >= 75.0:
            return (
                f"Core citadel secured ({solv_pct:.1f}% SoLV); primary exposure is along outer "
                f"perimeter tiles and secondary service themes."
            )
        if weak_lanes:
            return (
                f"Visibility suppressed in {len(weak_lanes)} of {len(lane_stats)} query lane(s) "
                f"({', '.join(weak_lanes)}); requires targeted corridor and category expansion."
            )
        return f"Current Top 3 footprint covers {solv_pct:.1f}% of measured slots; perimeter remains contested."

    t_votes = target_votes or 0
    r_votes = votes_count
    if max_top3_distance_km > 2.5 and t_votes > 0 and r_votes is not None and r_votes < t_votes:
        deficit = t_votes - r_votes
        return (
            f"Overextended: holds Top 3 at {max_top3_distance_km:.1f} km from base with "
            f"{deficit} fewer reviews than target ({r_votes} vs {t_votes})"
        )
    if t_votes > 0 and r_votes is not None and r_votes < t_votes:
        deficit = t_votes - r_votes
        return (
            f"Review troop deficit: {r_votes} reviews vs target's {t_votes} "
            f"({deficit} fewer reviews)"
        )
    if r_votes is not None and r_votes >= max(350, int(t_votes * 1.4)) and lane_stats:
        weakest_lid, weakest_st = min(
            lane_stats.items(),
            key=lambda kv: kv[1].get("solv_pct", 0.0),
        )
        w_solv = weakest_st.get("solv_pct", 0.0)
        if w_solv <= 15.0:
            return (
                f"Heavy fortress ({r_votes} reviews), but vulnerable in lane {weakest_lid} "
                f"({w_solv:.1f}% SoLV) and outside its home sector"
            )
        if rating is not None and target_rating and rating < target_rating - 0.1:
            return (
                f"Heavy review volume ({r_votes} reviews) but lower {rating:.1f} star rating "
                f"vs target's {target_rating:.1f} stars"
            )
    if max_top3_distance_km > 2.5:
        return (
            f"Extended reach: projects Top 3 up to {max_top3_distance_km:.1f} km from its Citadel "
            f"across outer grid coordinates"
        )
    if not domain:
        return "Missing website domain on GBP"
    if rating is not None and (rating < 4.6 or (target_rating and rating < target_rating - 0.1)):
        return f"Rating gap: {rating:.1f} star average leaves opening for higher-rated challenger"
    if categories_count <= 1:
        return "Narrow category footprint (only 1 category observed)"

    weak_lanes = [lid for lid, st in lane_stats.items() if st.get("top3_count", 0) == 0]
    if weak_lanes:
        return f"Absent from Top 3 in query lane(s) {', '.join(weak_lanes)}; flankable on multi-theme intent"
    return f"Localized footprint ({top3_count} Top 3 slots, {solv_pct:.1f}% SoLV); vulnerable outside core base"


def _fog_state_for_rank(rank: int | None) -> str:
    if rank is not None and 1 <= rank <= 3:
        return "CLEARED_CITADEL"
    if rank is not None and 4 <= rank <= 10:
        return "CONTESTED_VISION"
    if rank is not None and 11 <= rank <= 20:
        return "SUPPRESSED_SECTOR"
    return "DARK_ZONE"


def build_battlefield_model(source_path: str | Path | StudyLanesBundle) -> dict[str, Any]:
    """Build the complete Fog of War and Tactical Battlefield model."""
    bundle = (
        source_path
        if isinstance(source_path, StudyLanesBundle)
        else load_study_lanes(source_path)
    )
    lanes = list(bundle)
    if not lanes:
        raise ValueError("Cannot build battlefield model from empty lanes")

    first_settings = lanes[0].get("measurement_settings") or {}
    center_lat = float(bundle.business.get("lat") or first_settings.get("center_lat") or 0.0)
    center_lng = float(bundle.business.get("lng") or first_settings.get("center_lng") or 0.0)
    radius_km = float(first_settings.get("radius_km") or 2.0)
    grid_size = int(first_settings.get("grid_size") or 5)
    zoom = int(first_settings.get("zoom") or 15)
    depth = int(first_settings.get("depth") or 20)

    target_meta = dict(bundle.business)
    target_meta.setdefault("name", lanes[0].get("target") or "Target Business")
    target_meta["lat"] = center_lat
    target_meta["lng"] = center_lng

    # Step 1: Scan all SERP items across all lanes and coordinates to enrich Target
    # and aggregate every unique competitor.
    competitor_records: dict[str, dict[str, Any]] = {}
    target_record: dict[str, Any] = {
        "name": target_meta["name"],
        "cid": target_meta.get("cid"),
        "place_id": target_meta.get("place_id"),
        "domain": target_meta.get("domain"),
        "url": target_meta.get("website"),
        "category": target_meta.get("category"),
        "additional_categories": list(target_meta.get("additional_categories") or []),
        "address": target_meta.get("address"),
        "rating": target_meta.get("rating"),
        "votes_count": target_meta.get("votes_count"),
        "lats": [center_lat] if center_lat else [],
        "lngs": [center_lng] if center_lng else [],
        "weighted_points": [],
        "appearances": [],
    }

    lane_ids = [lane["lane_id"] for lane in lanes]
    points_by_tag: dict[str, dict[str, Any]] = {}
    lane_dominant_categories: dict[str, str | None] = {}

    for lane in lanes:
        lid = lane["lane_id"]
        cat_counter: Counter[str] = Counter()
        for res in lane["results"]:
            pt = res["point"]
            tag = pt["tag"]
            if tag not in points_by_tag:
                points_by_tag[tag] = {
                    "tag": tag,
                    "row": int(pt["row"]),
                    "col": int(pt["col"]),
                    "lat": float(pt["lat"]),
                    "lng": float(pt["lng"]),
                    "ring": pt.get("ring"),
                    "spoke": pt.get("spoke"),
                    "ring_radius_km": pt.get("ring_radius_km"),
                    "bearing_deg": pt.get("bearing_deg"),
                }
            point_rank = res.get("rank")
            matched_item = res.get("matched_item")
            if isinstance(matched_item, dict):
                if matched_item.get("cid") and not target_meta.get("cid"):
                    target_meta["cid"] = matched_item["cid"]
                    target_record["cid"] = matched_item["cid"]
                if matched_item.get("place_id") and not target_meta.get("place_id"):
                    target_meta["place_id"] = matched_item["place_id"]
                    target_record["place_id"] = matched_item["place_id"]
                if matched_item.get("domain") and not target_meta.get("domain"):
                    dom = canonical_domain(matched_item["domain"])
                    if dom:
                        target_meta["domain"] = dom
                        target_record["domain"] = dom
                if matched_item.get("category") and not target_record.get("category"):
                    target_record["category"] = matched_item["category"]
                for ac in matched_item.get("additional_categories") or []:
                    if ac not in target_record["additional_categories"]:
                        target_record["additional_categories"].append(ac)
                if matched_item.get("address") and not target_record.get("address"):
                    target_record["address"] = matched_item["address"]
                if matched_item.get("rating") is not None and target_record.get("rating") is None:
                    target_record["rating"] = matched_item["rating"]
                if matched_item.get("votes_count") is not None:
                    target_record["votes_count"] = max(
                        target_record.get("votes_count") or 0,
                        int(matched_item["votes_count"]),
                    )
                if matched_item.get("latitude") is not None and matched_item.get("longitude") is not None:
                    target_record["lats"].append(float(matched_item["latitude"]))
                    target_record["lngs"].append(float(matched_item["longitude"]))

            seen_in_slot: set[str] = set()
            target_recorded_in_slot = False

            for item in res.get("serp_items") or []:
                cat = item.get("category")
                if cat:
                    cat_counter[cat] += 1

                is_tgt = _is_target_item(item, target_meta) or (
                    point_rank is not None and item.get("rank") == point_rank
                )
                rk = item.get("rank")
                if not isinstance(rk, int) or rk <= 0:
                    continue

                if is_tgt:
                    item["is_target"] = True
                    item["competitor_key"] = "TARGET"
                    if not target_recorded_in_slot:
                        target_recorded_in_slot = True
                        target_record["appearances"].append(
                            {
                                "lane_id": lid,
                                "tag": tag,
                                "lat": float(pt["lat"]),
                                "lng": float(pt["lng"]),
                                "rank": rk,
                            }
                        )
                        if item.get("category") and not target_record.get("category"):
                            target_record["category"] = item["category"]
                        for ac in item.get("additional_categories") or []:
                            if ac not in target_record["additional_categories"]:
                                target_record["additional_categories"].append(ac)
                        if item.get("rating") is not None and target_record.get("rating") is None:
                            target_record["rating"] = item["rating"]
                        if item.get("votes_count") is not None:
                            target_record["votes_count"] = max(
                                target_record.get("votes_count") or 0,
                                int(item["votes_count"]),
                            )
                    continue

                item["is_target"] = False
                comp_key = _competitor_identity_key(item)
                item["competitor_key"] = comp_key
                if comp_key in seen_in_slot:
                    continue
                seen_in_slot.add(comp_key)

                rec = competitor_records.get(comp_key)
                if rec is None:
                    rec = {
                        "key": comp_key,
                        "name": item.get("title") or "Unknown Competitor",
                        "cid": item.get("cid"),
                        "place_id": item.get("place_id"),
                        "domain": canonical_domain(item.get("domain") or item.get("url")) or item.get("domain"),
                        "url": item.get("url"),
                        "category": item.get("category"),
                        "additional_categories": list(item.get("additional_categories") or []),
                        "address": item.get("address"),
                        "rating": item.get("rating"),
                        "votes_count": item.get("votes_count"),
                        "is_claimed": item.get("is_claimed"),
                        "lats": [],
                        "lngs": [],
                        "weighted_points": [],
                        "appearances": [],
                    }
                    competitor_records[comp_key] = rec
                else:
                    if not rec.get("cid") and item.get("cid"):
                        rec["cid"] = item["cid"]
                    if not rec.get("place_id") and item.get("place_id"):
                        rec["place_id"] = item["place_id"]
                    if not rec.get("domain") and (item.get("domain") or item.get("url")):
                        rec["domain"] = canonical_domain(item.get("domain") or item.get("url")) or item.get("domain")
                    if not rec.get("category") and item.get("category"):
                        rec["category"] = item["category"]
                    for ac in item.get("additional_categories") or []:
                        if ac not in rec["additional_categories"]:
                            rec["additional_categories"].append(ac)
                    if not rec.get("address") and item.get("address"):
                        rec["address"] = item["address"]
                    if rec.get("rating") is None and item.get("rating") is not None:
                        rec["rating"] = item["rating"]
                    if item.get("votes_count") is not None:
                        rec["votes_count"] = max(rec.get("votes_count") or 0, int(item["votes_count"]))

                if item.get("latitude") is not None and item.get("longitude") is not None:
                    rec["lats"].append(float(item["latitude"]))
                    rec["lngs"].append(float(item["longitude"]))

                weight = 3.0 if rk == 1 else (2.0 if rk == 2 else (1.5 if rk == 3 else (1.0 / rk)))
                rec["weighted_points"].append((float(pt["lat"]), float(pt["lng"]), weight, rk))
                rec["appearances"].append(
                    {
                        "lane_id": lid,
                        "tag": tag,
                        "lat": float(pt["lat"]),
                        "lng": float(pt["lng"]),
                        "rank": rk,
                    }
                )

            if point_rank is not None and not target_recorded_in_slot:
                target_record["appearances"].append(
                    {
                        "lane_id": lid,
                        "tag": tag,
                        "lat": float(pt["lat"]),
                        "lng": float(pt["lng"]),
                        "rank": int(point_rank),
                    }
                )

        lane_dominant_categories[lid] = cat_counter.most_common(1)[0][0] if cat_counter else None

    total_points = len(points_by_tag)
    total_lanes = len(lanes)
    total_slots = max(1, total_points * total_lanes)
    lane_slot_counts = {lane["lane_id"]: max(1, len(lane["results"])) for lane in lanes}

    # Resolve Target coordinates and update target_meta
    if target_record["lats"] and target_record["lngs"]:
        target_lat = float(target_record["lats"][0])
        target_lng = float(target_record["lngs"][0])
    else:
        target_lat = center_lat
        target_lng = center_lng
    target_meta["lat"] = target_lat
    target_meta["lng"] = target_lng
    target_meta["category"] = target_record.get("category")
    target_meta["additional_categories"] = target_record.get("additional_categories") or []
    target_meta["address"] = target_record.get("address")
    target_meta["rating"] = target_record.get("rating")
    target_meta["votes_count"] = target_record.get("votes_count")
    if target_record.get("domain") and not target_meta.get("domain"):
        target_meta["domain"] = target_record["domain"]

    # Helper to compute coordinates and dominance stats for any record
    def _compute_record_location(rec: dict[str, Any]) -> tuple[float, float, bool]:
        if rec["lats"] and rec["lngs"]:
            raw_lat = sum(rec["lats"]) / len(rec["lats"])
            raw_lng = sum(rec["lngs"]) / len(rec["lngs"])
            is_sab = (not rec.get("address")) or (
                "Service establishment" in (rec.get("additional_categories") or [])
            )
            raw_dist = haversine_km(center_lat, center_lng, raw_lat, raw_lng)
            if not (is_sab and raw_dist > max(10.0, radius_km * 1.6)):
                return raw_lat, raw_lng, False
        top3_pts = [wp for wp in rec["weighted_points"] if wp[3] <= 3]
        pts_to_use = top3_pts if top3_pts else rec["weighted_points"]
        if pts_to_use:
            w_sum = sum(wp[2] for wp in pts_to_use) or 1.0
            est_lat = sum(wp[0] * wp[2] for wp in pts_to_use) / w_sum
            est_lng = sum(wp[1] * wp[2] for wp in pts_to_use) / w_sum
            return est_lat, est_lng, True
        return center_lat, center_lng, True

    comp_locations: dict[str, tuple[float, float]] = {"TARGET": (target_lat, target_lng)}
    scored_competitors: list[dict[str, Any]] = []

    for comp_key, rec in competitor_records.items():
        c_lat, c_lng, is_estimated = _compute_record_location(rec)
        comp_locations[comp_key] = (c_lat, c_lng)
        if (
            rec.get("domain")
            and rec.get("category")
            and normalize(rec.get("name") or "") == normalize(rec.get("category") or "")
            and rec["domain"] not in (rec.get("name") or "")
        ):
            rec["name"] = f"{rec['name']} ({rec['domain']})"
        apps = rec["appearances"]
        ranks = [a["rank"] for a in apps]
        top1_count = sum(1 for r in ranks if r == 1)
        top3_count = sum(1 for r in ranks if 1 <= r <= 3)
        top10_count = sum(1 for r in ranks if 1 <= r <= 10)
        found_count = len(ranks)
        avg_rank = round(sum(ranks) / len(ranks), 2) if ranks else None
        dom_score = round(
            top1_count * 5.0 + top3_count * 3.0 + top10_count * 1.0 + found_count * 0.25,
            2,
        )
        rec.update(
            {
                "lat": round(c_lat, 7),
                "lng": round(c_lng, 7),
                "location_estimated": is_estimated,
                "top1_count": top1_count,
                "top3_count": top3_count,
                "top10_count": top10_count,
                "found_count": found_count,
                "average_rank": avg_rank,
                "dominance_score": dom_score,
                "solv_pct": round((top3_count / total_slots) * 100.0, 1),
                "visible_pct": round((top10_count / total_slots) * 100.0, 1),
            }
        )
        scored_competitors.append(rec)

    scored_competitors.sort(
        key=lambda r: (
            -r["dominance_score"],
            -r["top3_count"],
            -r["top1_count"],
            -r["top10_count"],
            r["average_rank"] if r["average_rank"] is not None else 999.0,
            normalize(r["name"]),
        )
    )

    top_rivals = scored_competitors[:10]
    comp_key_to_faction_id: dict[str, str] = {"TARGET": "TARGET"}
    for idx, rival in enumerate(top_rivals, start=1):
        fid = f"F{idx:02d}"
        comp_key_to_faction_id[rival["key"]] = fid

    # Build the 11-Faction Roster (TARGET + F01..F10)
    def _build_faction_entry(
        rec: dict[str, Any],
        *,
        faction_id: str,
        is_target: bool,
        rank_order: int,
    ) -> dict[str, Any]:
        palette = FACTION_PALETTE[faction_id]
        f_lat = float(rec.get("lat", target_lat if is_target else center_lat))
        f_lng = float(rec.get("lng", target_lng if is_target else center_lng))
        apps = rec["appearances"]
        ranks = [a["rank"] for a in apps]
        top1_count = sum(1 for r in ranks if r == 1)
        top3_count = sum(1 for r in ranks if 1 <= r <= 3)
        top10_count = sum(1 for r in ranks if 1 <= r <= 10)
        found_count = len(ranks)
        avg_rank = round(sum(ranks) / len(ranks), 2) if ranks else None
        solv_pct = round((top3_count / total_slots) * 100.0, 1)
        visible_pct = round((top10_count / total_slots) * 100.0, 1)
        dom_score = round(
            top1_count * 5.0 + top3_count * 3.0 + top10_count * 1.0 + found_count * 0.25,
            2,
        )

        top3_dists = sorted(
            haversine_km(f_lat, f_lng, a["lat"], a["lng"])
            for a in apps
            if 1 <= a["rank"] <= 3
        )
        gravity_radius_km = round(_percentile(top3_dists, 0.75), 2) if top3_dists else 0.0
        max_top3_dist_km = round(max(top3_dists), 2) if top3_dists else 0.0
        dist_from_center = round(haversine_km(center_lat, center_lng, f_lat, f_lng), 2)

        sector_top3_counts: Counter[str] = Counter()
        for a in apps:
            if 1 <= a["rank"] <= 3:
                sec = compass_sector(center_lat, center_lng, a["lat"], a["lng"], radius_km)
                sector_top3_counts[sec] += 1

        lane_stats: dict[str, dict[str, Any]] = {}
        for lid in lane_ids:
            l_slots = lane_slot_counts[lid]
            l_ranks = [a["rank"] for a in apps if a["lane_id"] == lid]
            l_top1 = sum(1 for r in l_ranks if r == 1)
            l_top3 = sum(1 for r in l_ranks if 1 <= r <= 3)
            l_top10 = sum(1 for r in l_ranks if 1 <= r <= 10)
            l_found = len(l_ranks)
            lane_stats[lid] = {
                "solv_pct": round((l_top3 / l_slots) * 100.0, 1),
                "visible_pct": round((l_top10 / l_slots) * 100.0, 1),
                "top1_count": l_top1,
                "top3_count": l_top3,
                "top10_count": l_top10,
                "found_count": l_found,
                "average_rank": round(sum(l_ranks) / len(l_ranks), 2) if l_ranks else None,
            }

        all_cats = [c for c in ([rec.get("category")] + list(rec.get("additional_categories") or [])) if c]
        unique_cats = list(dict.fromkeys(all_cats))

        if is_target:
            archetype = "COMMANDER"
        else:
            archetype = _classify_rival_archetype(
                solv_pct=solv_pct,
                top3_count=top3_count,
                votes_count=rec.get("votes_count"),
                target_votes=target_meta.get("votes_count"),
                gravity_radius_km=gravity_radius_km,
                max_top3_distance_km=max_top3_dist_km,
                radius_km=radius_km,
                sector_top3_counts=sector_top3_counts,
                lane_stats=lane_stats,
            )

        threat_level = _classify_threat_level(
            is_target=is_target,
            solv_pct=solv_pct,
            visible_pct=visible_pct,
            top1_count=top1_count,
            top3_count=top3_count,
            total_slots=total_slots,
        )

        primary_vulnerability = _describe_primary_vulnerability(
            is_target=is_target,
            name=rec["name"],
            solv_pct=solv_pct,
            top3_count=top3_count,
            votes_count=rec.get("votes_count"),
            target_votes=target_meta.get("votes_count"),
            rating=rec.get("rating"),
            target_rating=target_meta.get("rating"),
            domain=rec.get("domain"),
            categories_count=len(unique_cats),
            max_top3_distance_km=max_top3_dist_km,
            lane_stats=lane_stats,
        )

        return {
            "faction_id": faction_id,
            "is_target": is_target,
            "rank_order": rank_order,
            "name": _clean_text(rec["name"]),
            "cid": rec.get("cid"),
            "place_id": rec.get("place_id"),
            "domain": rec.get("domain"),
            "category": rec.get("category"),
            "additional_categories": list(rec.get("additional_categories") or []),
            "address": rec.get("address"),
            "lat": round(f_lat, 7),
            "lng": round(f_lng, 7),
            "location_estimated": bool(rec.get("location_estimated", False)),
            "distance_from_center_km": dist_from_center,
            "rating": rec.get("rating"),
            "votes_count": rec.get("votes_count"),
            "color": palette["color"],
            "short_code": palette["short_code"],
            "dominance_score": dom_score,
            "solv_pct": solv_pct,
            "visible_pct": visible_pct,
            "top1_count": top1_count,
            "top3_count": top3_count,
            "top10_count": top10_count,
            "found_count": found_count,
            "total_slots": total_slots,
            "average_rank": avg_rank,
            "gravity_radius_km": gravity_radius_km,
            "max_top3_distance_km": max_top3_dist_km,
            "archetype": archetype,
            "threat_level": threat_level,
            "primary_vulnerability": _clean_text(primary_vulnerability),
            "lane_stats": lane_stats,
        }

    target_record["lat"] = target_lat
    target_record["lng"] = target_lng
    target_record["location_estimated"] = False

    factions: list[dict[str, Any]] = [
        _build_faction_entry(target_record, faction_id="TARGET", is_target=True, rank_order=0)
    ]
    for idx, rival_rec in enumerate(top_rivals, start=1):
        factions.append(
            _build_faction_entry(
                rival_rec,
                faction_id=f"F{idx:02d}",
                is_target=False,
                rank_order=idx,
            )
        )

    factions_by_id: dict[str, dict[str, Any]] = {f["faction_id"]: f for f in factions}
    target_faction = factions[0]
    rival_factions = factions[1:]

    # Build lookup by lane_id and point tag
    lane_results_by_tag: dict[str, dict[str, dict[str, Any]]] = {}
    for lane in lanes:
        lid = lane["lane_id"]
        lane_results_by_tag[lid] = {r["point"]["tag"]: r for r in lane["results"]}

    # Step 4: Per-Coordinate & Per-Lane Tactical Analysis
    sorted_tags = sorted(
        points_by_tag.keys(),
        key=lambda t: (points_by_tag[t]["row"], points_by_tag[t]["col"]),
    )

    all_gravity_anomalies: list[dict[str, Any]] = []
    analyzed_points: list[dict[str, Any]] = []

    target_votes = target_faction.get("votes_count")
    target_rating = target_faction.get("rating")

    for tag in sorted_tags:
        pt_base = points_by_tag[tag]
        p_lat = pt_base["lat"]
        p_lng = pt_base["lng"]
        dist_from_target = round(haversine_km(target_lat, target_lng, p_lat, p_lng), 2)
        sector = compass_sector(center_lat, center_lng, p_lat, p_lng, radius_km)

        by_lane: dict[str, dict[str, Any]] = {}

        for lane in lanes:
            lid = lane["lane_id"]
            l_query = lane["query"]
            dom_cat = lane_dominant_categories.get(lid)
            res = lane_results_by_tag[lid].get(tag) or {
                "point": pt_base,
                "rank": None,
                "status": "missing_result",
                "serp_items": [],
                "top_items": [],
            }
            t_rank = res.get("rank")
            serp_items = res.get("serp_items") or res.get("top_items") or []
            fog_state = _fog_state_for_rank(t_rank)

            # Annotate each SERP item with faction_id and distance from its Citadel to this pin
            annotated_items: list[dict[str, Any]] = []
            for it in serp_items:
                comp_key = it.get("competitor_key") or (
                    "TARGET" if _is_target_item(it, target_meta) else _competitor_identity_key(it)
                )
                fid = comp_key_to_faction_id.get(comp_key)
                if comp_key in comp_locations:
                    c_lat_i, c_lng_i = comp_locations[comp_key]
                elif it.get("latitude") is not None and it.get("longitude") is not None:
                    c_lat_i, c_lng_i = float(it["latitude"]), float(it["longitude"])
                else:
                    c_lat_i, c_lng_i = p_lat, p_lng
                item_dist_km = round(haversine_km(c_lat_i, c_lng_i, p_lat, p_lng), 2)
                annotated = dict(
                    it,
                    faction_id=fid,
                    faction_color=factions_by_id[fid]["color"] if fid in factions_by_id else "#94a3b8",
                    faction_short_code=factions_by_id[fid]["short_code"] if fid in factions_by_id else "OTH",
                    distance_from_pin_km=item_dist_km,
                )
                annotated_items.append(annotated)

            top3_items = [it for it in annotated_items if isinstance(it.get("rank"), int) and 1 <= it["rank"] <= 3]
            top3_rivals = [it for it in top3_items if it.get("faction_id") != "TARGET"]

            # Sovereign Turf in this lane
            rank1_item = next((it for it in top3_items if it["rank"] == 1), None)
            tracked_top3 = [it for it in top3_items if it.get("faction_id") in factions_by_id]

            if t_rank == 1 or (
                t_rank in (2, 3)
                and (rank1_item is None or rank1_item.get("faction_id") not in factions_by_id)
            ):
                ctrl_faction = target_faction
                turf_state = "TARGET_OWNED"
            elif rank1_item is not None and rank1_item.get("faction_id") in factions_by_id:
                ctrl_faction = factions_by_id[rank1_item["faction_id"]]
                turf_state = "TARGET_OWNED" if ctrl_faction["is_target"] else "RIVAL_CONTROLLED"
            elif tracked_top3:
                best_tracked = min(tracked_top3, key=lambda x: x["rank"])
                ctrl_faction = factions_by_id[best_tracked["faction_id"]]
                turf_state = "TARGET_OWNED" if ctrl_faction["is_target"] else "RIVAL_CONTROLLED"
            elif rank1_item is not None:
                ctrl_faction = {
                    "faction_id": "UNALIGNED",
                    "name": rank1_item.get("title") or "Unaligned Local Competitor",
                    "color": "#64748b",
                }
                turf_state = "CONTESTED_NO_MANS_LAND"
            else:
                ctrl_faction = {
                    "faction_id": "UNALIGNED",
                    "name": "Unclaimed Sector",
                    "color": "#475569",
                }
                turf_state = "CONTESTED_NO_MANS_LAND"

            # Gravity Anomaly detection at this coordinate in this lane
            gravity_anomaly: dict[str, Any] = {
                "has_anomaly": False,
                "faction_id": None,
                "faction_name": None,
                "rank": None,
                "distance_from_pin_km": None,
                "reason": "No gravity anomaly detected; Top 3 rankings align with local proximity.",
            }
            for inc in sorted(
                top3_items,
                key=lambda x: (x.get("faction_id") not in factions_by_id, int(x.get("rank") or 99)),
            ):
                inc_dist = float(inc.get("distance_from_pin_km") or 0.0)
                if inc_dist < 2.5:
                    continue
                inc_rank = int(inc["rank"])
                closer_candidates: list[tuple[float, str, int | None]] = []
                if (t_rank is None or t_rank > inc_rank) and (dist_from_target + 0.75 < inc_dist):
                    closer_candidates.append((dist_from_target, target_faction["name"], t_rank))
                for lower in annotated_items:
                    l_rank = lower.get("rank")
                    if isinstance(l_rank, int) and l_rank > inc_rank:
                        l_dist = float(lower.get("distance_from_pin_km") or 0.0)
                        if l_dist + 0.75 < inc_dist:
                            closer_candidates.append((l_dist, lower.get("title") or "Local business", l_rank))
                if closer_candidates:
                    closer_candidates.sort(key=lambda c: (c[2] is None, c[0]))
                    c_dist, c_name, c_rank = closer_candidates[0]
                    c_rank_str = f"Rank #{c_rank}" if c_rank is not None else "unranked in top 20"
                    inc_fid = inc.get("faction_id") or "UNALIGNED"
                    inc_name = _clean_text(inc.get("title") or "Incumbent")
                    gravity_anomaly = {
                        "has_anomaly": True,
                        "tag": tag,
                        "lane_id": lid,
                        "faction_id": inc_fid,
                        "faction_name": inc_name,
                        "rank": inc_rank,
                        "distance_from_pin_km": round(inc_dist, 2),
                        "closer_business_name": _clean_text(c_name),
                        "closer_business_rank": c_rank,
                        "closer_distance_km": round(c_dist, 2),
                        "reason": _clean_text(
                            f"{inc_name} holds Rank #{inc_rank} at {inc_dist:.2f} km from its Citadel, "
                            f"outranking {c_name} ({c_rank_str}) located {c_dist:.2f} km from this pin."
                        ),
                    }
                    break

            # Deterministic Opportunity Score (0..100), Tactical Class, Vulnerability Reasons & Counter Move
            reasons: list[str] = []
            if t_rank == 1:
                runner_up = next((it for it in top3_rivals if it["rank"] == 2), None)
                if runner_up is not None:
                    ru_votes = runner_up.get("votes_count")
                    ru_dist = float(runner_up.get("distance_from_pin_km") or 0.0)
                    opp_score = 22 if (ru_votes and target_votes and ru_votes >= target_votes) else 18
                    reasons.append(
                        f"Target commands Rank #1 at {dist_from_target:.2f} km from base in '{l_query}'."
                    )
                    reasons.append(
                        f"Closest challenger at Rank #2 is {runner_up['title']} "
                        f"({ru_dist:.2f} km from its base"
                        + (f", {ru_votes} reviews)." if ru_votes is not None else ").")
                    )
                else:
                    opp_score = 16
                    reasons.append(
                        f"Target holds uncontested Rank #1 at {dist_from_target:.2f} km from base in '{l_query}'."
                    )
                    reasons.append("No tracked rival holds a Top 3 slot at this coordinate.")
                tactical_class = "OWNED_STRONGHOLD"
                counter_move = (
                    f"Defend Rank #1 stronghold at {tag} ({sector} sector): maintain review velocity "
                    f"and GBP activity for '{l_query}'."
                )
            elif t_rank in (2, 3):
                lead_inc = next((it for it in top3_rivals if it["rank"] == 1), top3_rivals[0] if top3_rivals else None)
                opp_score = 35
                reasons.append(
                    f"Target already holds Rank #{t_rank} in Top 3 at {dist_from_target:.2f} km from base."
                )
                if lead_inc is not None:
                    l_dist = float(lead_inc.get("distance_from_pin_km") or 0.0)
                    l_votes = lead_inc.get("votes_count")
                    if l_dist > 2.0:
                        opp_score += 5
                    if l_votes is not None and target_votes is not None and l_votes <= target_votes:
                        opp_score += 5
                    reasons.append(
                        f"Rank #1 incumbent {lead_inc['title']} operates {l_dist:.2f} km from its base"
                        + (f" with {l_votes} reviews vs your {target_votes}." if l_votes is not None and target_votes is not None else ".")
                    )
                else:
                    reasons.append(f"Upgrade path from Rank #{t_rank} to #1 is open in '{l_query}'.")
                opp_score = max(30, min(45, opp_score))
                tactical_class = "OWNED_STRONGHOLD"
                counter_move = (
                    f"Consolidate Top 3 foothold at {tag} ({sector} sector) and push from Rank #{t_rank} to #1 "
                    f"for '{l_query}'."
                )
            else:
                if t_rank is not None and 4 <= t_rank <= 6:
                    base_score = 55
                    reasons.append(
                        f"Strike distance position: Target ranks #{t_rank} in '{l_query}' ({dist_from_target:.2f} km from base)."
                    )
                elif t_rank is not None and 7 <= t_rank <= 10:
                    base_score = 45
                    reasons.append(
                        f"Contested Page-1 visibility: Target ranks #{t_rank} in '{l_query}' ({dist_from_target:.2f} km from base)."
                    )
                elif t_rank is not None and 11 <= t_rank <= 20:
                    base_score = 32
                    reasons.append(
                        f"Suppressed visibility: Target ranks #{t_rank} in '{l_query}' ({dist_from_target:.2f} km from base)."
                    )
                else:
                    base_score = 25
                    reasons.append(
                        f"Dark Zone coordinate: Target is unranked in top 20 for '{l_query}' at {dist_from_target:.2f} km from base."
                    )

                inc_dists = [float(it.get("distance_from_pin_km") or 0.0) for it in top3_rivals]
                avg_inc_dist = (sum(inc_dists) / len(inc_dists)) if inc_dists else 0.0
                max_inc_dist = max(inc_dists) if inc_dists else 0.0

                dist_bonus = 0
                if avg_inc_dist > 2.0:
                    dist_bonus = min(
                        22,
                        int(
                            round(
                                8.0
                                + (avg_inc_dist - 2.0) * 7.0
                                + (4.0 if dist_from_target <= avg_inc_dist else 0.0)
                            )
                        ),
                    )
                    reasons.append(
                        f"Top 3 incumbents overextended (avg {avg_inc_dist:.1f} km from base vs your {dist_from_target:.1f} km)."
                    )
                elif max_inc_dist >= 2.3:
                    far_inc = max(top3_rivals, key=lambda x: float(x.get("distance_from_pin_km") or 0.0))
                    dist_bonus = min(14, int(round(6.0 + (max_inc_dist - 2.0) * 5.0)))
                    reasons.append(
                        f"Top 3 incumbent {far_inc['title']} (#{far_inc['rank']}) is overextended at {max_inc_dist:.1f} km from base."
                    )

                # Review Troop Deficit Bonus (+0 to +18) or Fortress Penalty (-20)
                rev_modifier = 0
                inc_votes_list = [it["votes_count"] for it in top3_rivals if it.get("votes_count") is not None]
                gatekeeper = next((it for it in top3_rivals if it["rank"] == 3), top3_rivals[-1] if top3_rivals else None)

                if (
                    len(inc_votes_list) == 3
                    and all(v > 300 and v > 2 * max(target_votes or 1, 1) for v in inc_votes_list)
                ):
                    rev_modifier = -20
                    reasons.append(
                        f"Enemy fortress wall: all Top 3 incumbents hold >300 reviews (min {min(inc_votes_list)} vs your {target_votes or 0})."
                    )
                elif gatekeeper is not None and gatekeeper.get("votes_count") is not None and target_votes is not None:
                    gk_votes = int(gatekeeper["votes_count"])
                    if gk_votes <= target_votes:
                        ratio = min(1.0, (target_votes - gk_votes) / max(target_votes, 1))
                        rev_modifier = min(18, int(round(10.0 + 8.0 * ratio)))
                        reasons.append(
                            f"Rank #{gatekeeper['rank']} gatekeeper ({gatekeeper['title']}) has {gk_votes} reviews vs your {target_votes}."
                        )
                    elif gk_votes <= int(target_votes * 1.2):
                        rev_modifier = 8
                        reasons.append(
                            f"Rank #{gatekeeper['rank']} gatekeeper ({gatekeeper['title']}) has comparable review count ({gk_votes} vs your {target_votes})."
                        )
                    else:
                        weakest_rev_inc = min(
                            (it for it in top3_rivals if it.get("votes_count") is not None),
                            key=lambda x: x["votes_count"],
                            default=None,
                        )
                        if weakest_rev_inc is not None and weakest_rev_inc["votes_count"] <= target_votes:
                            w_votes = int(weakest_rev_inc["votes_count"])
                            rev_modifier = 12
                            reasons.append(
                                f"Rank #{weakest_rev_inc['rank']} incumbent ({weakest_rev_inc['title']}) has {w_votes} reviews vs your {target_votes}."
                            )
                elif gatekeeper is not None and gatekeeper.get("votes_count") is None:
                    gk_fid = gatekeeper.get("faction_id")
                    gk_solv = factions_by_id[gk_fid]["solv_pct"] if gk_fid in factions_by_id else 5.0
                    if gk_solv < 25.0:
                        rev_modifier = 12
                        reasons.append(
                            f"Rank #{gatekeeper['rank']} gatekeeper ({gatekeeper['title']}) holds limited regional share ({gk_solv:.1f}% SoLV)."
                        )

                # Rating Vulnerability (+0 to +8)
                rating_bonus = 0
                rated_rivals = [it for it in top3_rivals if it.get("rating") is not None]
                if rated_rivals:
                    low_rated = min(rated_rivals, key=lambda x: float(x["rating"]))
                    low_r = float(low_rated["rating"])
                    if low_r < 4.5 or (target_rating is not None and low_r < float(target_rating) - 0.1):
                        rating_bonus = 8 if low_r < 4.5 else 5
                        reasons.append(
                            f"Rank #{low_rated['rank']} incumbent ({low_rated['title']}) carries a {low_r:.1f} star rating"
                            + (f" vs your {target_rating:.1f}." if target_rating is not None else " (< 4.5).")
                        )

                # Domain / Category / Unclaimed Vulnerability (+0 to +10)
                profile_bonus = 0
                has_any_domain_data = any(it.get("domain") for it in annotated_items)
                has_any_cat_data = any(it.get("category") for it in annotated_items)
                missing_dom_inc = (
                    next((it for it in top3_rivals if not it.get("domain")), None)
                    if has_any_domain_data
                    else None
                )
                off_cat_inc = (
                    next(
                        (
                            it
                            for it in top3_rivals
                            if dom_cat and it.get("category") and normalize(it["category"]) != normalize(dom_cat)
                        ),
                        None,
                    )
                    if has_any_cat_data
                    else None
                )
                unclaimed_inc = next((it for it in top3_rivals if it.get("is_claimed") is False), None)

                if missing_dom_inc is not None:
                    profile_bonus += 8
                    reasons.append(
                        f"Rank #{missing_dom_inc['rank']} incumbent ({missing_dom_inc['title']}) has no website domain on GBP."
                    )
                if off_cat_inc is not None:
                    profile_bonus = min(10, profile_bonus + 8)
                    reasons.append(
                        f"Rank #{off_cat_inc['rank']} incumbent ({off_cat_inc['title']}) uses primary category '{off_cat_inc['category']}' vs dominant '{dom_cat}'."
                    )
                if unclaimed_inc is not None:
                    profile_bonus = min(10, profile_bonus + 8)
                    reasons.append(
                        f"Rank #{unclaimed_inc['rank']} incumbent ({unclaimed_inc['title']}) has an unclaimed GBP listing."
                    )

                if len(reasons) < 2 and top3_rivals:
                    lead = top3_rivals[0]
                    reasons.append(
                        f"Current Rank #1 holder is {lead['title']} ({lead.get('distance_from_pin_km', 0.0):.2f} km from its Citadel)."
                    )

                opp_score = int(
                    round(min(100, max(0, base_score + dist_bonus + rev_modifier + rating_bonus + profile_bonus)))
                )

                if (t_rank is None or t_rank > 10) and 52 <= opp_score < 68:
                    tactical_class = "FLANKING_MINE"
                elif opp_score >= 65:
                    tactical_class = "PRIME_STRIKE_ZONE"
                elif (t_rank is None or t_rank > 10) and opp_score >= 52:
                    tactical_class = "FLANKING_MINE"
                elif opp_score < 38:
                    tactical_class = "ENEMY_FORTRESS"
                else:
                    tactical_class = "CONTESTED_FRONT"

                weak_target_inc = gatekeeper or (top3_rivals[0] if top3_rivals else None)
                weak_inc_name = weak_target_inc["title"] if weak_target_inc else "incumbent pack"
                if tactical_class == "PRIME_STRIKE_ZONE":
                    counter_move = (
                        f"Execute direct corridor strike at {tag} ({sector} sector) on '{l_query}' "
                        f"to displace Rank #3 gatekeeper {weak_inc_name}."
                    )
                elif tactical_class == "FLANKING_MINE":
                    counter_move = (
                        f"Deploy flanking service page and localized GBP signals for '{l_query}' in {sector} sector "
                        f"({tag}) where {weak_inc_name} holds lightly defended turf."
                    )
                elif tactical_class == "ENEMY_FORTRESS":
                    counter_move = (
                        f"Do not attack {tag} ({sector} sector) head-on for '{l_query}'; flank via adjacent "
                        f"corridors before challenging {weak_inc_name}."
                    )
                else:
                    counter_move = (
                        f"Build review and category relevance along {sector} sector ({tag}) for '{l_query}' "
                        f"to pressure {weak_inc_name}."
                    )

            reasons = [_clean_text(r) for r in reasons[:4]]
            while len(reasons) < 2:
                reasons.append(
                    f"Coordinate {tag} sits {dist_from_target:.2f} km from Target Citadel in {sector} sector."
                )

            by_lane[lid] = {
                "lane_id": lid,
                "query": l_query,
                "target_rank": t_rank,
                "status": res.get("status"),
                "fog_state": fog_state,
                "controlling_faction_id": ctrl_faction["faction_id"],
                "controlling_faction_name": _clean_text(ctrl_faction["name"]),
                "controlling_faction_color": ctrl_faction["color"],
                "turf_state": turf_state,
                "opportunity_score": opp_score,
                "tactical_class": tactical_class,
                "vulnerability_reasons": reasons,
                "counter_move": _clean_text(counter_move),
                "gravity_anomaly": gravity_anomaly,
                "top_items": annotated_items[:20],
            }
            if gravity_anomaly["has_anomaly"]:
                all_gravity_anomalies.append(gravity_anomaly)

        # Aggregate across all lanes for this coordinate point
        lane_entries = [by_lane[lid] for lid in lane_ids]
        lane_ranks = [le["target_rank"] for le in lane_entries]
        valid_ranks = [r for r in lane_ranks if r is not None]
        top1_lanes = sum(1 for r in valid_ranks if r == 1)
        top3_lanes = sum(1 for r in valid_ranks if 1 <= r <= 3)
        top10_lanes = sum(1 for r in valid_ranks if 1 <= r <= 10)
        found_lanes = len(valid_ranks)
        avg_target_rank = round(sum(valid_ranks) / len(valid_ranks), 2) if valid_ranks else None
        best_target_rank = min(valid_ranks) if valid_ranks else None

        # Aggregate Fog of War State
        if top3_lanes >= math.ceil(total_lanes * 0.5):
            agg_fog_state = "CLEARED_CITADEL"
        elif top10_lanes > 0:
            agg_fog_state = "CONTESTED_VISION"
        elif found_lanes > 0:
            agg_fog_state = "SUPPRESSED_SECTOR"
        else:
            agg_fog_state = "DARK_ZONE"

        # Aggregate Sovereign Turf
        ctrl_counts: Counter[str] = Counter(le["controlling_faction_id"] for le in lane_entries)
        top_ctrl_id, top_ctrl_count = ctrl_counts.most_common(1)[0]

        if top1_lanes == total_lanes or (
            top3_lanes >= math.ceil(total_lanes * 0.6) and ctrl_counts.get("TARGET", 0) >= top_ctrl_count
        ):
            agg_ctrl_id = "TARGET"
            agg_ctrl_name = target_faction["name"]
            agg_ctrl_color = target_faction["color"]
            agg_turf_state = "TARGET_OWNED"
        elif total_lanes == 1:
            single = lane_entries[0]
            agg_ctrl_id = single["controlling_faction_id"]
            agg_ctrl_name = single["controlling_faction_name"]
            agg_ctrl_color = single["controlling_faction_color"]
            agg_turf_state = single["turf_state"]
        elif top_ctrl_id != "UNALIGNED" and top_ctrl_count > total_lanes / 2.0:
            f_obj = factions_by_id.get(top_ctrl_id, target_faction)
            agg_ctrl_id = f_obj["faction_id"]
            agg_ctrl_name = f_obj["name"]
            agg_ctrl_color = f_obj["color"]
            agg_turf_state = "TARGET_OWNED" if f_obj["is_target"] else "RIVAL_CONTROLLED"
        else:
            # Contested across different factions across lanes; pick highest weighted faction at this coordinate
            faction_pin_scores: Counter[str] = Counter()
            for le in lane_entries:
                for it in le["top_items"][:3]:
                    fid = it.get("faction_id")
                    if fid and fid in factions_by_id:
                        rk = it.get("rank") or 3
                        faction_pin_scores[fid] += 4 - min(3, rk)
            if faction_pin_scores:
                best_fid = faction_pin_scores.most_common(1)[0][0]
                f_obj = factions_by_id[best_fid]
                agg_ctrl_id = f_obj["faction_id"]
                agg_ctrl_name = f_obj["name"]
                agg_ctrl_color = f_obj["color"]
            else:
                agg_ctrl_id = lane_entries[0]["controlling_faction_id"]
                agg_ctrl_name = lane_entries[0]["controlling_faction_name"]
                agg_ctrl_color = lane_entries[0]["controlling_faction_color"]
            agg_turf_state = "CONTESTED_NO_MANS_LAND"

        # Aggregate Opportunity Score & Tactical Class
        is_agg_stronghold = (top3_lanes / total_lanes) >= 0.6
        if is_agg_stronghold:
            agg_tactical_class = "OWNED_STRONGHOLD"
            mean_lane_opp = sum(le["opportunity_score"] for le in lane_entries) / total_lanes
            if top1_lanes == total_lanes:
                agg_opp_score = int(round(min(25, max(15, mean_lane_opp))))
            else:
                non_top3_lanes = [le for le in lane_entries if le["target_rank"] is None or le["target_rank"] > 3]
                if non_top3_lanes:
                    agg_opp_score = int(round(min(45, max(35, (mean_lane_opp + max(le["opportunity_score"] for le in non_top3_lanes)) / 2.0))))
                else:
                    agg_opp_score = int(round(min(45, max(30, mean_lane_opp))))
        else:
            strike_lanes = [le for le in lane_entries if le["target_rank"] is None or le["target_rank"] > 3]
            if strike_lanes:
                max_strike = max(le["opportunity_score"] for le in strike_lanes)
                mean_strike = sum(le["opportunity_score"] for le in strike_lanes) / len(strike_lanes)
                agg_opp_score = int(round(min(100, max(0, 0.6 * max_strike + 0.4 * mean_strike))))
            else:
                agg_opp_score = int(round(sum(le["opportunity_score"] for le in lane_entries) / total_lanes))

            if agg_fog_state in ("DARK_ZONE", "SUPPRESSED_SECTOR") and 52 <= agg_opp_score < 68:
                agg_tactical_class = "FLANKING_MINE"
            elif agg_opp_score >= 65:
                agg_tactical_class = "PRIME_STRIKE_ZONE"
            elif agg_fog_state in ("DARK_ZONE", "SUPPRESSED_SECTOR") and agg_opp_score >= 52:
                agg_tactical_class = "FLANKING_MINE"
            elif agg_opp_score < 38:
                agg_tactical_class = "ENEMY_FORTRESS"
            else:
                agg_tactical_class = "CONTESTED_FRONT"

        # Aggregate reasons & counter_move from the highest-opportunity lane at this coordinate
        best_lane_entry = max(lane_entries, key=lambda le: le["opportunity_score"])
        agg_reasons: list[str] = []
        for le in sorted(lane_entries, key=lambda x: -x["opportunity_score"]):
            for r_text in le["vulnerability_reasons"]:
                if r_text not in agg_reasons:
                    agg_reasons.append(r_text)
                if len(agg_reasons) >= 4:
                    break
            if len(agg_reasons) >= 4:
                break
        while len(agg_reasons) < 2:
            agg_reasons.append(f"Coordinate {tag} sits {dist_from_target:.2f} km from Target base in {sector} sector.")

        agg_anomalies = [le["gravity_anomaly"] for le in lane_entries if le["gravity_anomaly"]["has_anomaly"]]
        if agg_anomalies:
            agg_gravity_anomaly = max(
                agg_anomalies,
                key=lambda a: (
                    1 if a.get("faction_id") in factions_by_id else 0,
                    float(a.get("distance_from_pin_km") or 0.0),
                    -(a.get("rank") or 99),
                ),
            )
        else:
            agg_gravity_anomaly = lane_entries[0]["gravity_anomaly"]

        aggregate_block = {
            "target_rank": best_target_rank if total_lanes == 1 else avg_target_rank,
            "best_target_rank": best_target_rank,
            "avg_target_rank": avg_target_rank,
            "top1_lanes": top1_lanes,
            "top3_lanes": top3_lanes,
            "top10_lanes": top10_lanes,
            "found_lanes": found_lanes,
            "total_lanes": total_lanes,
            "fog_state": agg_fog_state,
            "controlling_faction_id": agg_ctrl_id,
            "controlling_faction_name": _clean_text(agg_ctrl_name),
            "controlling_faction_color": agg_ctrl_color,
            "turf_state": agg_turf_state,
            "opportunity_score": agg_opp_score,
            "tactical_class": agg_tactical_class,
            "vulnerability_reasons": agg_reasons[:4],
            "counter_move": best_lane_entry["counter_move"],
            "gravity_anomaly": agg_gravity_anomaly,
            "top_items": best_lane_entry["top_items"],
        }

        dy_lat = (p_lat - center_lat) * 111.32
        dx_lng = (p_lng - center_lng) * 111.32 * math.cos(math.radians(center_lat))
        computed_bearing = round((math.degrees(math.atan2(dx_lng, dy_lat)) + 360.0) % 360.0, 2)

        analyzed_points.append(
            {
                "tag": tag,
                "row": pt_base["row"],
                "col": pt_base["col"],
                "ring": pt_base.get("ring"),
                "spoke": pt_base.get("spoke"),
                "ring_radius_km": pt_base.get("ring_radius_km"),
                "bearing_deg": pt_base.get("bearing_deg") if pt_base.get("bearing_deg") is not None else computed_bearing,
                "lat": p_lat,
                "lng": p_lng,
                "distance_from_target_km": dist_from_target,
                "sector": sector,
                "by_lane": by_lane,
                "aggregate": aggregate_block,
                # Convenience top-level mirrors of aggregate fields
                "target_rank": aggregate_block["target_rank"],
                "best_target_rank": best_target_rank,
                "avg_target_rank": avg_target_rank,
                "fog_state": agg_fog_state,
                "controlling_faction_id": agg_ctrl_id,
                "controlling_faction_name": _clean_text(agg_ctrl_name),
                "controlling_faction_color": agg_ctrl_color,
                "turf_state": agg_turf_state,
                "opportunity_score": agg_opp_score,
                "tactical_class": agg_tactical_class,
                "vulnerability_reasons": agg_reasons[:4],
                "counter_move": best_lane_entry["counter_move"],
                "gravity_anomaly": agg_gravity_anomaly,
                "top_items": best_lane_entry["top_items"],
            }
        )

    # Step 5: Campaign Orders Synthesis
    cleared_tiles = sum(1 for p in analyzed_points if p["aggregate"]["fog_state"] == "CLEARED_CITADEL")
    contested_tiles = sum(1 for p in analyzed_points if p["aggregate"]["fog_state"] == "CONTESTED_VISION")
    suppressed_tiles = sum(1 for p in analyzed_points if p["aggregate"]["fog_state"] == "SUPPRESSED_SECTOR")
    dark_tiles = sum(1 for p in analyzed_points if p["aggregate"]["fog_state"] == "DARK_ZONE")
    vis_cov_pct = round(((cleared_tiles + contested_tiles) / max(1, total_points)) * 100.0, 1)

    fog_of_war_summary = {
        "total_tiles": total_points,
        "cleared_citadel_tiles": cleared_tiles,
        "contested_vision_tiles": contested_tiles,
        "suppressed_tiles": suppressed_tiles,
        "suppressed_sector_tiles": suppressed_tiles,
        "dark_zone_tiles": dark_tiles,
        "visibility_coverage_pct": vis_cov_pct,
        "cleared_coverage_pct": round((cleared_tiles / max(1, total_points)) * 100.0, 1),
        "blind_spot_pct": round((dark_tiles / max(1, total_points)) * 100.0, 1),
    }

    # Group points by compass sector to build Strike Corridors
    points_by_sector: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in analyzed_points:
        points_by_sector[p["sector"]].append(p)

    sector_summary: dict[str, dict[str, Any]] = {}
    corridor_candidates: list[dict[str, Any]] = []

    for sec, sec_pts in points_by_sector.items():
        sec_scores = [p["aggregate"]["opportunity_score"] for p in sec_pts]
        avg_sec_score = round(sum(sec_scores) / len(sec_scores), 1) if sec_scores else 0.0
        ctrl_counter = Counter(p["aggregate"]["controlling_faction_id"] for p in sec_pts)
        lead_fid = ctrl_counter.most_common(1)[0][0] if ctrl_counter else "UNALIGNED"
        sector_summary[sec] = {
            "sector": sec,
            "sector_name": SECTOR_NAMES.get(sec, sec),
            "tile_count": len(sec_pts),
            "avg_opportunity_score": avg_sec_score,
            "controlling_faction_id": lead_fid,
            "cleared_tiles": sum(1 for p in sec_pts if p["aggregate"]["fog_state"] == "CLEARED_CITADEL"),
            "contested_tiles": sum(1 for p in sec_pts if p["aggregate"]["fog_state"] == "CONTESTED_VISION"),
            "suppressed_tiles": sum(1 for p in sec_pts if p["aggregate"]["fog_state"] == "SUPPRESSED_SECTOR"),
            "dark_tiles": sum(1 for p in sec_pts if p["aggregate"]["fog_state"] == "DARK_ZONE"),
        }

        # Identify strikeable tiles in this sector (either non-stronghold in aggregate or non-#1 in at least one lane)
        strike_pts = [
            p
            for p in sec_pts
            if p["aggregate"]["tactical_class"] != "OWNED_STRONGHOLD"
            or any(le["target_rank"] is None or le["target_rank"] > 3 for le in p["by_lane"].values())
        ]
        candidate_pts = strike_pts if strike_pts else sec_pts

        # Compute corridor opportunity score from the strikeable lane slots in this sector
        slot_scores: list[int] = []
        affected_lanes: set[str] = set()
        incumbent_hits: Counter[str] = Counter()
        incumbent_vuln_map: dict[str, str] = {}
        rank_samples: list[int] = []
        unranked_count = 0

        for p in candidate_pts:
            for lid, le in p["by_lane"].items():
                rk = le["target_rank"]
                if strike_pts and rk is not None and rk <= 3:
                    continue
                slot_scores.append(le["opportunity_score"])
                affected_lanes.add(lid)
                if rk is not None:
                    rank_samples.append(rk)
                else:
                    unranked_count += 1
                for it in le["top_items"][:3]:
                    if it.get("faction_id") != "TARGET" and it.get("title"):
                        inc_name = it["title"]
                        incumbent_hits[inc_name] += 1
                        if inc_name not in incumbent_vuln_map:
                            fid = it.get("faction_id")
                            if fid and fid in factions_by_id:
                                incumbent_vuln_map[inc_name] = factions_by_id[fid]["primary_vulnerability"]
                            else:
                                incumbent_vuln_map[inc_name] = le["vulnerability_reasons"][0]

        if not slot_scores:
            slot_scores = [p["aggregate"]["opportunity_score"] for p in candidate_pts]
            affected_lanes = set(lane_ids)
            for p in candidate_pts:
                for lid, le in p["by_lane"].items():
                    if le["target_rank"] is not None:
                        rank_samples.append(le["target_rank"])
                    for it in le["top_items"][:3]:
                        if it.get("faction_id") != "TARGET" and it.get("title"):
                            inc_name = it["title"]
                            incumbent_hits[inc_name] += 1
                            if inc_name not in incumbent_vuln_map:
                                fid = it.get("faction_id")
                                incumbent_vuln_map[inc_name] = (
                                    factions_by_id[fid]["primary_vulnerability"]
                                    if fid and fid in factions_by_id
                                    else le["vulnerability_reasons"][0]
                                )

        corridor_avg_opp = round(sum(slot_scores) / max(1, len(slot_scores)), 1)
        if rank_samples and unranked_count:
            ranks_label = f"Ranks #{min(rank_samples)}-#{max(rank_samples)} ({unranked_count} dark slot(s))"
        elif rank_samples:
            if min(rank_samples) == max(rank_samples):
                ranks_label = f"Rank #{min(rank_samples)}"
            else:
                ranks_label = f"Ranks #{min(rank_samples)}-#{max(rank_samples)}"
        else:
            ranks_label = f"Unranked ({unranked_count} dark slot(s))"

        if incumbent_hits:
            # Prefer a non-fortress (Paper Tiger / lower-review) incumbent when naming the primary strike target
            factions_by_name = {f["name"]: f for f in rival_factions}
            sorted_incs = sorted(
                incumbent_hits.items(),
                key=lambda kv: (
                    0
                    if (
                        kv[0] in factions_by_name
                        and factions_by_name[kv[0]]["archetype"] == "CITADEL_FORTRESS"
                    )
                    else 1,
                    kv[1],
                ),
                reverse=True,
            )
            weak_inc_name = sorted_incs[0][0]
            weak_inc_vuln = incumbent_vuln_map.get(weak_inc_name, "Contested perimeter incumbent")
        elif rival_factions:
            weak_inc_name = rival_factions[0]["name"]
            weak_inc_vuln = rival_factions[0]["primary_vulnerability"]
        else:
            weak_inc_name = "Local Competitors"
            weak_inc_vuln = "Fragmented local pack"

        affected_lane_list = sorted(affected_lanes)
        affected_queries = [
            next((l["query"] for l in lanes if l["lane_id"] == lid), lid)
            for lid in affected_lane_list
        ]

        corridor_candidates.append(
            {
                "has_non_stronghold": bool(strike_pts),
                "sector": sec,
                "title": f"{SECTOR_NAMES.get(sec, sec)} Corridor ({sec} Sector)",
                "tiles": [p["tag"] for p in candidate_pts],
                "tile_count": len(candidate_pts),
                "avg_opportunity_score": corridor_avg_opp,
                "max_opportunity_score": max(slot_scores) if slot_scores else 0,
                "target_current_ranks": ranks_label,
                "weak_incumbent_name": _clean_text(weak_inc_name),
                "weak_incumbent_vulnerability": _clean_text(weak_inc_vuln),
                "lanes_affected": affected_lane_list,
                "queries_affected": affected_queries,
                "recommended_order": _clean_text(
                    f"Concentrate local landing page signals, internal links, and review velocity in the "
                    f"{SECTOR_NAMES.get(sec, sec)} ({sec}) corridor across {', '.join(affected_queries)} "
                    f"to overtake {weak_inc_name} across {len(candidate_pts)} tile(s)."
                ),
            }
        )

    corridor_candidates.sort(
        key=lambda c: (
            c["has_non_stronghold"],
            c["avg_opportunity_score"],
            c["max_opportunity_score"],
            c["tile_count"],
        ),
        reverse=True,
    )

    strike_corridors: list[dict[str, Any]] = []
    for idx, cand in enumerate(corridor_candidates[:5], start=1):
        entry = dict(cand)
        entry.pop("has_non_stronghold", None)
        entry["corridor_id"] = f"SC-{idx:02d}"
        strike_corridors.append(entry)

    # Tech Tree Unlocks (GBP_CATEGORY, SERVICE_CORRIDOR_PAGE, REVIEW_TROOP_SURGE, BLIND_SPOT_THEME)
    tech_tree_unlocks: list[dict[str, Any]] = []
    target_primary_cat = target_faction.get("category") or ""
    target_primary_norm = normalize(target_primary_cat)
    target_cats_norm = {
        normalize(c)
        for c in ([target_faction.get("category")] + list(target_faction.get("additional_categories") or []))
        if c
    }

    # Check if Top-10 Rivals overwhelmingly use a different PRIMARY category than Target
    rival_primary_users: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rival_primary_display: dict[str, str] = {}
    for rf in rival_factions:
        rcat = rf.get("category")
        if rcat:
            rn = normalize(rcat)
            if rn and rn != target_primary_norm:
                rival_primary_users[rn].append(rf)
                rival_primary_display.setdefault(rn, rcat)

    if rival_primary_users:
        top_prim_norm, top_prim_list = max(
            rival_primary_users.items(),
            key=lambda kv: (len(kv[1]), sum(u["solv_pct"] for u in kv[1])),
        )
        if len(top_prim_list) >= 3:
            p_disp = rival_primary_display[top_prim_norm]
            p_avg_solv = round(sum(u["solv_pct"] for u in top_prim_list) / len(top_prim_list), 1)
            in_secondary = top_prim_norm in target_cats_norm
            action_verb = "Promote to Primary GBP Category" if in_secondary else "Set Primary GBP Category"
            sec_note = (
                f"Target currently lists '{target_primary_cat}' as Primary and relegates '{p_disp}' to Secondary."
                if in_secondary
                else f"Target currently lists '{target_primary_cat}' as Primary."
            )
            tech_tree_unlocks.append(
                {
                    "unlock_type": "GBP_CATEGORY",
                    "name": _clean_text(f"{action_verb}: {p_disp}"),
                    "category_name": _clean_text(p_disp),
                    "used_by_rivals": [u["name"] for u in top_prim_list[:5]],
                    "rivals_solv_avg": p_avg_solv,
                    "impact_rationale": _clean_text(
                        f"{len(top_prim_list)} of {len(rival_factions)} Top-10 rivals (averaging {p_avg_solv:.1f}% SoLV) "
                        f"use '{p_disp}' as their Primary GBP category. {sec_note}"
                    ),
                }
            )

    rival_cat_users: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rival_cat_display: dict[str, str] = {}
    for rf in rival_factions:
        rf_cats = [c for c in ([rf.get("category")] + list(rf.get("additional_categories") or [])) if c]
        seen_rf_cat: set[str] = set()
        for c in rf_cats:
            cn = normalize(c)
            if not cn or cn in seen_rf_cat:
                continue
            seen_rf_cat.add(cn)
            rival_cat_users[cn].append(rf)
            rival_cat_display.setdefault(cn, c)

    missing_cat_candidates = [
        (cn, users) for cn, users in rival_cat_users.items() if cn not in target_cats_norm
    ]
    missing_cat_candidates.sort(
        key=lambda pair: (
            len(pair[1]),
            sum(u["solv_pct"] for u in pair[1]) / max(1, len(pair[1])),
        ),
        reverse=True,
    )

    if missing_cat_candidates:
        max_missing = 1 if tech_tree_unlocks else 2
        for cn, users in missing_cat_candidates[:max_missing]:
            c_name = rival_cat_display[cn]
            avg_solv = round(sum(u["solv_pct"] for u in users) / len(users), 1)
            tech_tree_unlocks.append(
                {
                    "unlock_type": "GBP_CATEGORY",
                    "name": _clean_text(f"Add GBP Category: {c_name}"),
                    "category_name": _clean_text(c_name),
                    "used_by_rivals": [u["name"] for u in users[:5]],
                    "rivals_solv_avg": avg_solv,
                    "impact_rationale": _clean_text(
                        f"Used by {len(users)} Top-10 rival(s) averaging {avg_solv:.1f}% SoLV, "
                        f"but currently absent from Target's observed GBP categories."
                    ),
                }
            )
    elif not tech_tree_unlocks:
        primary_cat = target_faction.get("category") or lanes[0]["query"].title()
        cat_users = rival_factions[:3]
        avg_solv = (
            round(sum(u["solv_pct"] for u in cat_users) / len(cat_users), 1)
            if cat_users
            else target_faction["solv_pct"]
        )
        tech_tree_unlocks.append(
            {
                "unlock_type": "GBP_CATEGORY",
                "name": _clean_text(f"Primary & Secondary Category Alignment ({primary_cat})"),
                "category_name": _clean_text(primary_cat),
                "used_by_rivals": [u["name"] for u in cat_users] if cat_users else [target_faction["name"]],
                "rivals_solv_avg": avg_solv,
                "impact_rationale": _clean_text(
                    f"Ensure GBP primary and secondary service categories explicitly cover all measured "
                    f"query themes ({', '.join(l['query'] for l in lanes)})."
                ),
            }
        )

    # SERVICE_CORRIDOR_PAGE unlock
    top_corridor = strike_corridors[0] if strike_corridors else None
    domain_rivals = [rf for rf in rival_factions if rf.get("domain")] or rival_factions[:3]
    dom_avg_solv = (
        round(sum(u["solv_pct"] for u in domain_rivals) / len(domain_rivals), 1)
        if domain_rivals
        else 0.0
    )
    corridor_sec = top_corridor["sector"] if top_corridor else "W"
    corridor_q = (top_corridor.get("queries_affected") or [lanes[0]["query"]])[0] if top_corridor else lanes[0]["query"]
    tech_tree_unlocks.append(
        {
            "unlock_type": "SERVICE_CORRIDOR_PAGE",
            "name": _clean_text(
                f"{SECTOR_NAMES.get(corridor_sec, corridor_sec)} ({corridor_sec}) '{corridor_q}' Service Corridor Page"
            ),
            "used_by_rivals": [u["name"] for u in domain_rivals[:4]],
            "rivals_solv_avg": dom_avg_solv,
            "impact_rationale": _clean_text(
                f"Target the {SECTOR_NAMES.get(corridor_sec, corridor_sec)} ({corridor_sec}) strike corridor "
                f"({top_corridor['avg_opportunity_score'] if top_corridor else 50.0:.1f} avg opportunity score) "
                f"with dedicated neighborhood and service proof for '{corridor_q}'."
            ),
        }
    )

    # REVIEW_TROOP_SURGE unlock
    rivals_with_votes = [rf for rf in rival_factions if rf.get("votes_count") is not None]
    if rivals_with_votes:
        t_votes_num = int(target_votes or 0)
        higher_rivals = sorted(
            [rf for rf in rivals_with_votes if int(rf["votes_count"]) > t_votes_num],
            key=lambda r: int(r["votes_count"]),
        )
        lower_rivals = [rf for rf in rivals_with_votes if int(rf["votes_count"]) <= t_votes_num]
        if higher_rivals:
            next_tier_f = higher_rivals[0]
            next_votes = int(next_tier_f["votes_count"])
            delta_votes = next_votes - t_votes_num
            rev_name = f"Review Troop Surge (+{delta_votes} reviews to overtake {next_tier_f['name']})"
            outgun_note = (
                f"Target ({t_votes_num} reviews) already outguns {len(lower_rivals)} of {len(rivals_with_votes)} Top-10 rivals. "
                if lower_rivals
                else ""
            )
            rev_rationale = (
                f"{outgun_note}Adding +{delta_votes} reviews overtakes next-tier rival "
                f"{next_tier_f['name']} ({next_votes} reviews) across contested corridors."
            )
        else:
            max_rival_votes_f = max(rivals_with_votes, key=lambda r: int(r["votes_count"]))
            max_r_votes = int(max_rival_votes_f["votes_count"])
            rev_name = f"Review Velocity Defense (Maintain lead over {max_rival_votes_f['name']}'s {max_r_votes} reviews)"
            rev_rationale = (
                f"Target leads all Top-10 rivals with {t_votes_num} reviews vs {max_rival_votes_f['name']} ({max_r_votes}). "
                f"Prompt customers in outer {corridor_sec} sector jobs to mention specific services."
            )
        rev_users = [u["name"] for u in rivals_with_votes[:4]]
        rev_solv = round(sum(u["solv_pct"] for u in rivals_with_votes[:4]) / min(4, len(rivals_with_votes)), 1)
    else:
        rev_users = [rf["name"] for rf in rival_factions[:3]]
        rev_solv = round(sum(rf["solv_pct"] for rf in rival_factions[:3]) / max(1, len(rival_factions[:3])), 1)
        rev_name = f"Corridor Review Velocity Campaign ({corridor_sec} Sector)"
        rev_rationale = (
            f"Acquire service-specific reviews mentioning '{corridor_q}' to displace top incumbents "
            f"({', '.join(rev_users[:2]) or 'local rivals'}) in contested tiles."
        )

    tech_tree_unlocks.append(
        {
            "unlock_type": "REVIEW_TROOP_SURGE",
            "name": _clean_text(rev_name),
            "used_by_rivals": rev_users,
            "rivals_solv_avg": rev_solv,
            "impact_rationale": _clean_text(rev_rationale),
        }
    )

    # BLIND_SPOT_THEME unlock
    weakest_lane = min(
        lanes,
        key=lambda l: target_faction["lane_stats"].get(l["lane_id"], {}).get("solv_pct", 0.0),
    )
    w_lid = weakest_lane["lane_id"]
    w_query = weakest_lane["query"]
    w_solv = target_faction["lane_stats"].get(w_lid, {}).get("solv_pct", 0.0)
    lane_leaders = sorted(
        rival_factions,
        key=lambda rf: rf["lane_stats"].get(w_lid, {}).get("solv_pct", 0.0),
        reverse=True,
    )[:3]
    leader_solv = (
        round(
            sum(rf["lane_stats"].get(w_lid, {}).get("solv_pct", 0.0) for rf in lane_leaders)
            / max(1, len(lane_leaders)),
            1,
        )
        if lane_leaders
        else 0.0
    )
    tech_tree_unlocks.append(
        {
            "unlock_type": "BLIND_SPOT_THEME",
            "name": _clean_text(f"Theme Expansion: '{w_query}' ({w_lid})"),
            "used_by_rivals": [rf["name"] for rf in lane_leaders],
            "rivals_solv_avg": leader_solv,
            "impact_rationale": _clean_text(
                f"Target achieves {w_solv:.1f}% SoLV on '{w_query}' ({w_lid}), whereas top lane rivals "
                f"average {leader_solv:.1f}% SoLV. Dedicated theme content and GBP service items unlock this lane."
            ),
        }
    )

    # Fortress Warnings
    fortress_warnings: list[dict[str, Any]] = []
    fortress_pts = [p for p in analyzed_points if p["aggregate"]["tactical_class"] == "ENEMY_FORTRESS"]
    if fortress_pts:
        by_f_sec: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for p in fortress_pts:
            by_f_sec[(p["sector"], p["aggregate"]["controlling_faction_id"])].append(p)
        sorted_f_groups = sorted(
            by_f_sec.items(),
            key=lambda item: (len(item[1]), -sum(x["aggregate"]["opportunity_score"] for x in item[1]) / len(item[1])),
            reverse=True,
        )
        for idx, ((sec, fid), pts_group) in enumerate(sorted_f_groups[:4], start=1):
            f_obj = factions_by_id.get(fid)
            f_name = f_obj["name"] if f_obj else pts_group[0]["aggregate"]["controlling_faction_name"]
            avg_opp = round(sum(x["aggregate"]["opportunity_score"] for x in pts_group) / len(pts_group), 1)
            v_cnt = f_obj.get("votes_count") if f_obj else None
            r_val = f_obj.get("rating") if f_obj else None
            reason_str = _clean_text(
                f"{f_name} controls {len(pts_group)} fortified tile(s) in {sec} sector "
                f"(avg opportunity score {avg_opp:.1f})"
                + (
                    f" backed by {v_cnt} reviews near its Citadel."
                    if v_cnt
                    else " near its core base."
                )
            )
            advice_str = _clean_text(
                f"Avoid direct spend on {sec} sector fortress tiles ({', '.join(x['tag'] for x in pts_group[:4])}); "
                f"capture higher-opportunity flanking corridors first."
            )
            fortress_warnings.append(
                {
                    "warning_id": f"FW-{idx:02d}",
                    "sector": sec,
                    "faction_id": fid,
                    "fortress_faction_id": fid,
                    "faction_name": _clean_text(f_name),
                    "fortress_name": _clean_text(f_name),
                    "tiles": [x["tag"] for x in pts_group],
                    "avg_opportunity_score": avg_opp,
                    "rival_votes_count": v_cnt,
                    "votes_count": v_cnt,
                    "rival_rating": r_val,
                    "rating": r_val,
                    "reason": reason_str,
                    "warning": f"{reason_str} {advice_str}",
                    "tactical_advice": advice_str,
                }
            )
    elif rival_factions:
        # Even when no coordinate has opportunity_score < 38, warn on the strongest rival Citadel
        top_rival = rival_factions[0]
        tr_sec = compass_sector(center_lat, center_lng, top_rival["lat"], top_rival["lng"], radius_km)
        tr_tiles = [
            p["tag"]
            for p in analyzed_points
            if p["aggregate"]["controlling_faction_id"] == top_rival["faction_id"]
        ]
        if not tr_tiles:
            tr_tiles = [
                p["tag"]
                for p in sorted(
                    analyzed_points,
                    key=lambda p: haversine_km(top_rival["lat"], top_rival["lng"], p["lat"], p["lng"]),
                )[:2]
            ]
        reason_str = _clean_text(
            f"Primary rival Citadel for {top_rival['name']} sits in {tr_sec} sector "
            f"({top_rival['distance_from_center_km']:.2f} km from grid center, {top_rival['solv_pct']:.1f}% SoLV)."
        )
        advice_str = _clean_text(
            f"Monitor {top_rival['name']} near its {tr_sec} base and prioritize outer perimeter "
            f"strike corridors before contesting its doorstep."
        )
        fortress_warnings.append(
            {
                "warning_id": "FW-01",
                "sector": tr_sec,
                "faction_id": top_rival["faction_id"],
                "fortress_faction_id": top_rival["faction_id"],
                "faction_name": top_rival["name"],
                "fortress_name": top_rival["name"],
                "tiles": tr_tiles[:5],
                "avg_opportunity_score": 35.0,
                "rival_votes_count": top_rival.get("votes_count"),
                "votes_count": top_rival.get("votes_count"),
                "rival_rating": top_rival.get("rating"),
                "rating": top_rival.get("rating"),
                "reason": reason_str,
                "warning": f"{reason_str} {advice_str}",
                "tactical_advice": advice_str,
            }
        )

    # Next-Turn Recon Probes (up to 5 concrete CLI commands)
    next_turn_recon_probes: list[dict[str, Any]] = []
    primary_query = lanes[0]["query"]
    for idx, rf in enumerate(rival_factions[:3], start=1):
        probe_radius = round(max(1.0, min(3.0, radius_km)), 2)
        cid_flag = f' --target-cid "{rf["cid"]}"' if rf.get("cid") else ""
        cli_cmd = (
            f'python tools/local_heatmap_poc.py --keyword "{primary_query}" '
            f'--target-name "{rf["name"]}"{cid_flag} '
            f"--center-lat {rf['lat']:.7f} --center-lng {rf['lng']:.7f} "
            f"--radius-km {probe_radius:g} --grid-size 5 --method standard"
        )
        next_turn_recon_probes.append(
            {
                "probe_id": f"RP-{idx:02d}",
                "probe_type": "RIVAL_CITADEL_SCAN",
                "title": _clean_text(f"Rival Citadel Recon: {rf['name']} ({rf['short_code']})"),
                "target_faction_id": rf["faction_id"],
                "target_short_code": rf["short_code"],
                "target_name": rf["name"],
                "center_lat": rf["lat"],
                "center_lng": rf["lng"],
                "radius_km": probe_radius,
                "grid_size": 5,
                "keyword": primary_query,
                "rationale": _clean_text(
                    f"Map {rf['name']}'s home Citadel ({rf['solv_pct']:.1f}% SoLV, archetype {rf['archetype']}) "
                    f"to measure its true gravity decay boundary."
                ),
                "cli_command": _clean_text(cli_cmd),
            }
        )

    # Add Frontier Expansion Scans
    if strike_corridors:
        sc = strike_corridors[0]
        sc_pts = [points_by_tag[t] for t in sc["tiles"] if t in points_by_tag]
        f_lat = round(sum(p["lat"] for p in sc_pts) / len(sc_pts), 7) if sc_pts else center_lat
        f_lng = round(sum(p["lng"] for p in sc_pts) / len(sc_pts), 7) if sc_pts else center_lng
        sc_query = (sc.get("queries_affected") or [primary_query])[0]
        t_cid_flag = f' --target-cid "{target_faction["cid"]}"' if target_faction.get("cid") else ""
        probe_idx = len(next_turn_recon_probes) + 1
        next_turn_recon_probes.append(
            {
                "probe_id": f"RP-{probe_idx:02d}",
                "probe_type": "FRONTIER_EXPANSION_SCAN",
                "title": _clean_text(f"Frontier Corridor Probe: {sc['sector']} Sector ({sc_query})"),
                "target_faction_id": "TARGET",
                "target_short_code": "YOU",
                "target_name": target_faction["name"],
                "center_lat": f_lat,
                "center_lng": f_lng,
                "radius_km": round(max(1.0, radius_km * 0.75), 2),
                "grid_size": 5,
                "keyword": sc_query,
                "rationale": _clean_text(
                    f"High-density sub-grid across {sc['sector']} strike corridor "
                    f"(avg opportunity {sc['avg_opportunity_score']:.1f}) to track rank lift after intervention."
                ),
                "cli_command": _clean_text(
                    f'python tools/local_heatmap_poc.py --keyword "{sc_query}" '
                    f'--target-name "{target_faction["name"]}"{t_cid_flag} '
                    f"--center-lat {f_lat:.7f} --center-lng {f_lng:.7f} "
                    f"--radius-km {round(max(1.0, radius_km * 0.75), 2):g} --grid-size 5 --method standard"
                ),
            }
        )

    if len(next_turn_recon_probes) < 5:
        wide_radius = round(radius_km * 2.5, 2)
        t_cid_flag = f' --target-cid "{target_faction["cid"]}"' if target_faction.get("cid") else ""
        probe_idx = len(next_turn_recon_probes) + 1
        next_turn_recon_probes.append(
            {
                "probe_id": f"RP-{probe_idx:02d}",
                "probe_type": "FRONTIER_EXPANSION_SCAN",
                "title": _clean_text(f"Regional Theater Zoom-Out ({wide_radius:g} km Radius)"),
                "target_faction_id": "TARGET",
                "target_short_code": "YOU",
                "target_name": target_faction["name"],
                "center_lat": center_lat,
                "center_lng": center_lng,
                "radius_km": wide_radius,
                "grid_size": 7,
                "keyword": weakest_lane["query"],
                "rationale": _clean_text(
                    f"Expand sampling radius from {radius_km:g} km to {wide_radius:g} km on '{weakest_lane['query']}' "
                    f"to map the outer regional rank decay boundary."
                ),
                "cli_command": _clean_text(
                    f'python tools/local_heatmap_poc.py --keyword "{weakest_lane["query"]}" '
                    f'--target-name "{target_faction["name"]}"{t_cid_flag} '
                    f"--center-lat {center_lat:.7f} --center-lng {center_lng:.7f} "
                    f"--radius-km {wide_radius:g} --grid-size 7 --method standard"
                ),
            }
        )

    # Headline Summary (2-3 crisp sentences, zero em dashes)
    top_rival_summary = (
        f"Top rival {rival_factions[0]['name']} ({rival_factions[0]['short_code']}) holds "
        f"{rival_factions[0]['solv_pct']:.1f}% SoLV ({rival_factions[0]['top3_count']} Top-3 slots) "
        f"with archetype {rival_factions[0]['archetype']}."
        if rival_factions
        else "No recurring Top-3 rivals were observed across the grid."
    )
    top_corridor_summary = (
        f"Primary strike order targets the {strike_corridors[0]['title']} "
        f"(avg opportunity score {strike_corridors[0]['avg_opportunity_score']:.1f} across {len(strike_corridors[0]['tiles'])} tile(s)) "
        f"against {strike_corridors[0]['weak_incumbent_name']}."
        if strike_corridors
        else "Maintain core defensive posture across all measured sectors."
    )
    headline_summary = _clean_text(
        f"{target_faction['name']} commands {target_faction['solv_pct']:.1f}% Share of Local Voice "
        f"({cleared_tiles} Cleared Citadel, {contested_tiles} Contested Vision, {suppressed_tiles} Suppressed, "
        f"and {dark_tiles} Dark Zone tile(s) across {total_points} coordinates and {total_lanes} query lane(s)). "
        f"{top_rival_summary} {top_corridor_summary}"
    )

    campaign_orders = {
        "headline_summary": headline_summary,
        "fog_of_war_summary": fog_of_war_summary,
        "strike_corridors": strike_corridors,
        "tech_tree_unlocks": tech_tree_unlocks,
        "fortress_warnings": fortress_warnings,
        "next_turn_recon_probes": next_turn_recon_probes[:5],
    }

    # Build lane summaries for top-level `lanes` array
    lane_summaries: list[dict[str, Any]] = []
    for lane in lanes:
        lid = lane["lane_id"]
        t_lstats = target_faction["lane_stats"].get(lid, {})
        l_cleared = sum(1 for p in analyzed_points if p["by_lane"][lid]["fog_state"] == "CLEARED_CITADEL")
        l_contested = sum(1 for p in analyzed_points if p["by_lane"][lid]["fog_state"] == "CONTESTED_VISION")
        l_suppressed = sum(1 for p in analyzed_points if p["by_lane"][lid]["fog_state"] == "SUPPRESSED_SECTOR")
        l_dark = sum(1 for p in analyzed_points if p["by_lane"][lid]["fog_state"] == "DARK_ZONE")
        best_lane_rival = max(
            rival_factions,
            key=lambda rf: rf["lane_stats"].get(lid, {}).get("solv_pct", 0.0),
            default=None,
        )
        dom_rival_name = (
            f"{best_lane_rival['short_code']} {best_lane_rival['name']} "
            f"({best_lane_rival['lane_stats'].get(lid, {}).get('solv_pct', 0.0):.1f}%)"
            if best_lane_rival is not None
            else "None detected"
        )
        lane_summaries.append(
            {
                "lane_id": lid,
                "query_id": lid,
                "lane_number": lane["lane_number"],
                "query": lane["query"],
                "keyword": lane["keyword"],
                "label": lane["label"],
                "narrative": lane["narrative"],
                "parsed_path": lane["parsed_path"],
                "raw_path": lane["raw_path"],
                "enriched_from_raw": lane["enriched_from_raw"],
                "points_count": len(lane["results"]),
                "dominant_category": lane_dominant_categories.get(lid),
                "dominant_faction_id": best_lane_rival["faction_id"] if best_lane_rival else "TARGET",
                "dominant_faction_name": best_lane_rival["name"] if best_lane_rival else target_faction["name"],
                "dominant_rival_name": dom_rival_name,
                "solv_pct": t_lstats.get("solv_pct", 0.0),
                "top3_count": t_lstats.get("top3_count", 0),
                "average_rank": t_lstats.get("average_rank"),
                "target_solv_pct": t_lstats.get("solv_pct", 0.0),
                "target_visible_pct": t_lstats.get("visible_pct", 0.0),
                "target_top1_count": t_lstats.get("top1_count", 0),
                "target_top3_count": t_lstats.get("top3_count", 0),
                "target_top10_count": t_lstats.get("top10_count", 0),
                "target_found_count": t_lstats.get("found_count", 0),
                "target_average_rank": t_lstats.get("average_rank"),
                "fog_of_war_summary": {
                    "total_tiles": total_points,
                    "cleared_citadel_tiles": l_cleared,
                    "contested_vision_tiles": l_contested,
                    "suppressed_tiles": l_suppressed,
                    "dark_zone_tiles": l_dark,
                    "visibility_coverage_pct": round(((l_cleared + l_contested) / max(1, total_points)) * 100.0, 1),
                },
            }
        )

    all_lats = [p["lat"] for p in analyzed_points] + [f["lat"] for f in factions]
    all_lngs = [p["lng"] for p in analyzed_points] + [f["lng"] for f in factions]
    dx = max((max(all_lngs) - min(all_lngs)) * 0.08, 0.002) if all_lngs else 0.01
    dy = max((max(all_lats) - min(all_lats)) * 0.08, 0.002) if all_lats else 0.01
    grid_bounds = [
        round(min(all_lngs) - dx, 7),
        round(min(all_lats) - dy, 7),
        round(max(all_lngs) + dx, 7),
        round(max(all_lats) + dy, 7),
    ]

    is_radial_geometry = (
        first_settings.get("geometry") == "radial_concentric"
        or any(p.get("ring") is not None for p in analyzed_points)
    )
    max_observed_dist_km = round(max((p["distance_from_target_km"] for p in analyzed_points), default=radius_km), 2)
    effective_radius_km = max(radius_km, max_observed_dist_km)

    # Synthesize Concentric Ring Trail-Off Curve
    ring_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for p in analyzed_points:
        r_idx = p.get("ring")
        if r_idx is None:
            # Bucket into 6 distance shells for standard grids
            d_ratio = p["distance_from_target_km"] / max(0.1, effective_radius_km)
            r_idx = min(6, int(round(d_ratio * 5)))
        ring_groups[int(r_idx)].append(p)

    radial_rings_summary: list[dict[str, Any]] = []
    for r_idx in sorted(ring_groups.keys()):
        r_pts = ring_groups[r_idx]
        r_rad = r_pts[0].get("ring_radius_km")
        if r_rad is None:
            r_rad = round(sum(x["distance_from_target_km"] for x in r_pts) / len(r_pts), 2)
        r_slots = len(r_pts) * total_lanes
        r_top3 = sum(x["aggregate"]["top3_lanes"] for x in r_pts)
        r_top10 = sum(x["aggregate"]["top10_lanes"] for x in r_pts)
        r_found = sum(x["aggregate"]["found_lanes"] for x in r_pts)
        r_solv = round((r_top3 / max(1, r_slots)) * 100.0, 1)
        r_vis = round((r_top10 / max(1, r_slots)) * 100.0, 1)
        r_fnd = round((r_found / max(1, r_slots)) * 100.0, 1)
        ctrl_c = Counter(
            x["aggregate"]["controlling_faction_id"]
            for x in r_pts
            if x["aggregate"]["controlling_faction_id"] != "UNALIGNED"
        )
        if not ctrl_c:
            ctrl_c = Counter(x["aggregate"]["controlling_faction_id"] for x in r_pts)
        dom_fid = ctrl_c.most_common(1)[0][0] if ctrl_c else "UNALIGNED"
        dom_f = factions_by_id.get(dom_fid)
        if r_solv >= 40.0:
            t_state = "CORE_DOMINANCE"
        elif r_vis >= 25.0:
            t_state = "ACTIVE_CONTEST"
        elif r_fnd > 0.0:
            t_state = "OUTER_DROP_OFF"
        else:
            t_state = "TRAIL_OFF_HORIZON"
        radial_rings_summary.append({
            "ring": r_idx,
            "radius_km": round(float(r_rad), 2),
            "point_count": len(r_pts),
            "target_solv_pct": r_solv,
            "target_visible_pct": r_vis,
            "target_found_pct": r_fnd,
            "dominant_faction_id": dom_fid,
            "dominant_faction_name": dom_f["name"] if dom_f else "Regional Pack",
            "dominant_faction_color": dom_f["color"] if dom_f else "#64748b",
            "trail_off_state": t_state,
        })

    # Synthesize 8-Sector Trail-Off Frontier Reach
    sector_reach_summary: dict[str, dict[str, Any]] = {}
    for sec_code in ("N", "NE", "E", "SE", "S", "SW", "W", "NW"):
        s_pts = [p for p in analyzed_points if p["sector"] == sec_code or (p["sector"] == "CORE" and p["distance_from_target_km"] == 0)]
        top3_dists = [p["distance_from_target_km"] for p in s_pts if p["aggregate"]["top3_lanes"] > 0]
        top10_dists = [p["distance_from_target_km"] for p in s_pts if p["aggregate"]["top10_lanes"] > 0]
        found_dists = [p["distance_from_target_km"] for p in s_pts if p["aggregate"]["found_lanes"] > 0]
        max_sec_dist = max((p["distance_from_target_km"] for p in s_pts), default=0.0)
        rival_c = Counter(
            p["aggregate"]["controlling_faction_id"]
            for p in s_pts
            if p["aggregate"]["controlling_faction_id"] not in ("TARGET", "UNALIGNED")
        )
        top_sec_rival_id = rival_c.most_common(1)[0][0] if rival_c else (rival_factions[0]["faction_id"] if rival_factions else "UNALIGNED")
        top_sec_rival = factions_by_id.get(top_sec_rival_id)
        sector_reach_summary[sec_code] = {
            "sector": sec_code,
            "sector_name": SECTOR_NAMES.get(sec_code, sec_code),
            "max_sampled_km": round(max_sec_dist, 2),
            "target_top3_reach_km": round(max(top3_dists), 2) if top3_dists else 0.0,
            "target_top10_reach_km": round(max(top10_dists), 2) if top10_dists else 0.0,
            "target_trail_off_km": round(max(found_dists), 2) if found_dists else 0.0,
            "dominant_rival_id": top_sec_rival_id,
            "dominant_rival_name": top_sec_rival["name"] if top_sec_rival else "Unaligned",
            "dominant_rival_color": top_sec_rival["color"] if top_sec_rival else "#64748b",
        }

    # Synthesize Faction Territory Envelopes
    faction_envelopes: dict[str, dict[str, Any]] = {}
    for f_obj in factions:
        fid = f_obj["faction_id"]
        f_lat, f_lng = f_obj["lat"], f_obj["lng"]
        controlled_pts = [p for p in analyzed_points if p["aggregate"]["controlling_faction_id"] == fid]
        top3_pts = []
        found_pts = []
        for p in analyzed_points:
            has_t3 = False
            has_fnd = False
            for le in p["by_lane"].values():
                for it in le["top_items"]:
                    if it.get("faction_id") == fid:
                        has_fnd = True
                        if isinstance(it.get("rank"), int) and it["rank"] <= 3:
                            has_t3 = True
            if has_t3:
                top3_pts.append(p)
            if has_fnd:
                found_pts.append(p)
        t3_dists = [haversine_km(f_lat, f_lng, p["lat"], p["lng"]) for p in top3_pts]
        fnd_dists = [haversine_km(f_lat, f_lng, p["lat"], p["lng"]) for p in found_pts]
        faction_envelopes[fid] = {
            "faction_id": fid,
            "short_code": f_obj["short_code"],
            "name": f_obj["name"],
            "color": f_obj["color"],
            "citadel_lat": f_lat,
            "citadel_lng": f_lng,
            "controlled_tiles_count": len(controlled_pts),
            "top3_tiles_count": len(top3_pts),
            "found_tiles_count": len(found_pts),
            "max_top3_reach_km": round(max(t3_dists), 2) if t3_dists else 0.0,
            "trail_off_radius_km": round(max(fnd_dists), 2) if fnd_dists else 0.0,
            "top3_tags": [p["tag"] for p in top3_pts],
            "controlled_tags": [p["tag"] for p in controlled_pts],
        }

    radial_policy = {
        "geometry": "radial_concentric" if is_radial_geometry else "grid_square",
        "max_radius_km": effective_radius_km,
        "rings": radial_rings_summary,
        "sector_reach": sector_reach_summary,
        "faction_envelopes": faction_envelopes,
    }

    if is_radial_geometry:
        grid_dims_str = f"9-Ring Radial ({total_points} origins, {effective_radius_km:g} km radius)"
    else:
        grid_dims_str = f"{grid_size}x{grid_size} ({total_points} origins)"
    location_label = _clean_text(
        target_meta.get("location") or target_meta.get("address") or "Local Service Area"
    )
    grid_meta = {
        "target_name": target_faction["name"],
        "location": location_label,
        "center_lat": center_lat,
        "center_lng": center_lng,
        "radius_km": effective_radius_km,
        "grid_size": grid_size,
        "rows": len(ring_groups) if is_radial_geometry else grid_size,
        "cols": 24 if is_radial_geometry else grid_size,
        "geometry": radial_policy["geometry"],
        "grid_dimensions": grid_dims_str,
        "total_points": total_points,
        "total_lanes": total_lanes,
        "total_slots": total_slots,
        "total_competitors_analyzed": len(scored_competitors),
        "zoom": zoom,
        "depth": depth,
        "bounds": grid_bounds,
    }

    model = {
        "schema": "geogrid-battlefield/v1",
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_path": str(bundle.source_path),
        "location": location_label,
        "grid_dimensions": grid_dims_str,
        "total_competitors_analyzed": len(scored_competitors),
        "business": target_meta,
        "target": target_faction,
        "study": grid_meta,
        "grid": grid_meta,
        "radial_policy": radial_policy,
        "lanes": lane_summaries,
        "factions": factions,
        "target_faction": target_faction,
        "rival_factions": rival_factions,
        "factions_by_id": factions_by_id,
        "points": analyzed_points,
        "sector_summary": sector_summary,
        "gravity_anomalies": all_gravity_anomalies,
        "campaign_orders": campaign_orders,
    }

    return _sanitize_tree(model)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Fog of War & Tactical Battlefield intelligence model and reports."
    )
    parser.add_argument(
        "--input",
        "--run-dir",
        dest="input",
        required=True,
        help="Path to study run directory, single-lane directory, report-config.json, or parsed-grid.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write battlefield-model.json and optional console/PDF outputs",
    )
    parser.add_argument(
        "--theme",
        choices=("geogrid", "light"),
        default="geogrid",
        help="Visual theme for PDF report rendering (default: geogrid)",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip rendering battlefield-report.pdf",
    )
    parser.add_argument(
        "--no-console",
        action="store_true",
        help="Skip rendering battlefield-console.html",
    )
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    model = build_battlefield_model(args.input)
    model_path = output_dir / "battlefield-model.json"
    model_path.write_text(
        json.dumps(model, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    outputs: dict[str, str | None] = {
        "battlefield_model_json": str(model_path),
        "battlefield_console_html": None,
        "battlefield_report_pdf": None,
    }

    if not args.no_console:
        try:
            import battlefield_console  # type: ignore

            console_path = output_dir / "battlefield-console.html"
            battlefield_console.render_console(model, console_path)
            outputs["battlefield_console_html"] = str(console_path)
        except ImportError:
            pass

    if not args.no_pdf:
        try:
            import battlefield_report  # type: ignore

            pdf_path = output_dir / "battlefield-report.pdf"
            battlefield_report.render_battlefield_pdf(model, pdf_path, theme=args.theme)
            outputs["battlefield_report_pdf"] = str(pdf_path)
        except ImportError:
            pass

    fog = model["campaign_orders"]["fog_of_war_summary"]
    receipt = {
        "status": "ok",
        "target": model["target_faction"]["name"],
        "lanes_count": model["grid"]["total_lanes"],
        "points_count": model["grid"]["total_points"],
        "factions_count": len(model["factions"]),
        "target_solv_pct": model["target_faction"]["solv_pct"],
        "fog_of_war_summary": fog,
        "strike_corridors_count": len(model["campaign_orders"]["strike_corridors"]),
        "gravity_anomalies_count": len(model["gravity_anomalies"]),
        "outputs": outputs,
    }
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
