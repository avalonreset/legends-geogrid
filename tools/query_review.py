"""Evidence freshness and query-review validator for researched GeoGrid studies.

Inspects a study plan and its cited sources (or a competitive sampling plan plus
its source study plan) without making network or paid provider calls. Works
standalone without AI Marketing Hub Home while optionally validating declared
Library or Home evidence-adapter links by source contract and hash.

Never fabricates numerical opportunity scores, demand figures, expiry certainty,
or automatic historical query substitutions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse

from study_contract import SCHEMA, digest, inside, nonempty, number, pointer, require

REVIEW_SCHEMA = "geogrid-query-review/v1"
COMPETITIVE_PLAN_SCHEMA = "legends-geogrid-competitive-plan/v1"
EXTERNAL_SOURCE_KINDS = ("library_note", "home_record")

# Canonical synonyms / near-duplicate token normalizations for overlap review.
# Flagging overlap is an advisory review signal for the operator, never an
# automatic rejection when distinct intent is documented or owner-requested.
SYNONYM_MAP = {
    "ac": "air_conditioning",
    "a/c": "air_conditioning",
    "aircon": "air_conditioning",
    "heating": "furnace_heating",
    "heater": "furnace_heating",
    "furnace": "furnace_heating",
    "company": "contractor_company",
    "contractor": "contractor_company",
    "contractors": "contractor_company",
    "companies": "contractor_company",
    "service": "service_repair",
    "services": "service_repair",
    "repair": "service_repair",
    "repairs": "service_repair",
    "fixing": "service_repair",
    "installation": "install_replace",
    "install": "install_replace",
    "replacement": "install_replace",
    "replace": "install_replace",
}

STOPWORDS = {
    "a", "an", "and", "the", "in", "near", "me", "my", "for", "of", "to", "by", "local", "best",
}

KNOWN_BUSINESS_INPUTS = (
    ("gsc_query_performance", "Search Console query and landing-page impressions/clicks"),
    ("gbp_owner_performance", "Private GBP owner call, direction, and website-click metrics"),
    ("crm_job_history", "Verified CRM completed jobs, service mix, and neighborhood distribution"),
    ("service_economics", "Service-line margins, average ticket, and technician dispatch capacity"),
    ("travel_constraints", "Practical technician travel boundaries and weekday/weekend availability"),
)


def _parse_iso(ts: str) -> datetime:
    stamp = datetime.fromisoformat(nonempty(ts, "timestamp").replace("Z", "+00:00"))
    require(stamp.tzinfo is not None, "timestamp requires timezone")
    return stamp


def _tokenize_query(text: str) -> tuple[list[str], set[str]]:
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    cleaned = re.sub(r"\bair\s+conditioning\b", "air_conditioning", cleaned)
    cleaned = re.sub(r"\bheat\s+pump\b", "heat_pump", cleaned)
    cleaned = re.sub(r"\bmini\s+split\b", "mini_split", cleaned)
    raw_tokens = [t for t in re.split(r"[^a-z0-9_/-]+", cleaned) if t and t not in STOPWORDS]
    canonical = {SYNONYM_MAP.get(t, t) for t in raw_tokens}
    return raw_tokens, canonical


GENERIC_ROLE_TOKENS = {"contractor_company", "service_repair", "install_replace"}
GENERIC_RAW_TOKENS = {
    "contractor", "contractors", "company", "companies",
    "service", "services", "repair", "repairs",
    "installation", "install", "replacement", "replace",
}


def detect_synonym_overlaps(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect wording or concept overlaps among selected queries without auto-rejecting."""
    selected = [q for q in queries if isinstance(q, dict) and q.get("selected")]
    overlaps: list[dict[str, Any]] = []
    for i, q1 in enumerate(selected):
        term1 = str(q1.get("query") or "").strip()
        _, can1 = _tokenize_query(term1)
        for q2 in selected[i + 1 :]:
            term2 = str(q2.get("query") or "").strip()
            _, can2 = _tokenize_query(term2)
            shared = sorted(can1 & can2)
            if not shared:
                continue
            union = can1 | can2
            jaccard = len(shared) / len(union) if union else 0.0
            shared_domain = sorted(set(shared) - GENERIC_ROLE_TOKENS)
            if jaccard >= 0.5 or shared_domain:
                user_preserved = (
                    q1.get("role") == "user_requested" and q2.get("role") == "user_requested"
                )
                overlaps.append({
                    "queries": [term1, term2],
                    "shared_concepts": shared,
                    "role_pair": [q1.get("role"), q2.get("role")],
                    "theme_ids": [
                        (q1.get("theme") or {}).get("id"),
                        (q2.get("theme") or {}).get("id"),
                    ],
                    "status": "documented_comparison" if user_preserved else "review_distinct_intent",
                    "note": (
                        "Queries share normalized service concepts ("
                        + ", ".join(shared)
                        + "). Preserved as explicit user-requested comparison; verify separate decision value."
                        if user_preserved
                        else "Queries share normalized service concepts ("
                        + ", ".join(shared)
                        + "). Confirm observed Maps result intent and business decision differ before scanning."
                    ),
                })
    return overlaps


def extract_service_theme_coverage(
    plan: dict[str, Any],
    docs: dict[str, Any],
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compare evidenced GBP categories and website offerings against candidate queries."""
    identity = plan.get("identity") or {}
    gbp_sid = identity.get("source_id")
    gbp_categories: list[str] = []
    if gbp_sid and gbp_sid in docs:
        try:
            item = pointer(docs[gbp_sid], identity.get("pointer", ""))
            if isinstance(item, dict):
                primary = item.get("category")
                if isinstance(primary, str) and primary.strip():
                    gbp_categories.append(primary.strip())
                for extra in item.get("additional_categories") or []:
                    if isinstance(extra, str) and extra.strip() and extra.strip() not in gbp_categories:
                        gbp_categories.append(extra.strip())
        except ValueError:
            pass

    queries = [q for q in (plan.get("queries") or []) if isinstance(q, dict)]
    selected = [q for q in queries if q.get("selected")]
    rejected_or_deferred = [q for q in queries if not q.get("selected")]

    roles_covered = sorted({str(q.get("role")) for q in selected if q.get("role")})
    themes = []
    for idx, q in enumerate(selected, start=1):
        t = q.get("theme") or {}
        themes.append({
            "query_id": q.get("query_id") or f"q{idx}",
            "query": q.get("query"),
            "role": q.get("role"),
            "theme_id": t.get("id"),
            "theme_label": t.get("label"),
            "customer_need": t.get("customer_need"),
            "distinct_value": t.get("distinct_value"),
            "offering_citations_count": len(q.get("offering_evidence") or []),
            "pilot_origins_count": len(set(q.get("pilot_sources") or [])),
        })

    per_query_tokens = []
    for q in selected:
        raw_t, can_t = _tokenize_query(str(q.get("query") or ""))
        per_query_tokens.append((set(raw_t), can_t))

    directly_matched_gbp: list[str] = []
    indirect_gbp: list[str] = []
    uncovered_gbp_categories: list[str] = []

    for cat in gbp_categories:
        cat_raw, cat_can = _tokenize_query(cat)
        cat_raw_set = set(cat_raw)
        cat_domain_raw = cat_raw_set - GENERIC_RAW_TOKENS
        cat_domain_can = cat_can - GENERIC_ROLE_TOKENS
        if not cat_domain_can:
            cat_domain_can = cat_can
        if not cat_domain_raw:
            cat_domain_raw = cat_raw_set

        # Direct match: a single selected query contains all raw domain tokens and all canonical tokens of the category
        if any(cat_domain_raw <= q_raw and cat_can <= q_can for q_raw, q_can in per_query_tokens):
            directly_matched_gbp.append(cat)
        # Indirect/partial match: at least one selected query shares the canonical domain concept
        elif any(bool(cat_domain_can & (q_can - GENERIC_ROLE_TOKENS)) for _, q_can in per_query_tokens):
            indirect_gbp.append(cat)
        else:
            uncovered_gbp_categories.append(cat)

    return {
        "selected_count": len(selected),
        "non_selected_count": len(rejected_or_deferred),
        "roles_covered": roles_covered,
        "has_category_control": "category" in roles_covered or bool(directly_matched_gbp),
        "has_service_lane": any(r in roles_covered for r in ("service", "product")),
        "observed_gbp_categories": gbp_categories,
        "directly_matched_gbp_categories": directly_matched_gbp,
        "indirect_or_partial_gbp_categories": indirect_gbp,
        "unselected_gbp_categories": uncovered_gbp_categories,
        "selected_themes": themes,
        "non_selected_candidates_documented": len(rejected_or_deferred) > 0,
    }


def classify_query_decisions(
    plan: dict[str, Any],
    docs: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Summarize accepted, rejected, and deferred query candidates with source-backed reasons."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    for idx, q in enumerate(plan.get("queries") or [], start=1):
        if not isinstance(q, dict):
            continue
        term = str(q.get("query") or "").strip()
        reason = str(q.get("reason") or "").strip()
        disposition = str(q.get("disposition") or "").strip().lower()
        if q.get("selected"):
            demand_id = q.get("demand_source")
            demand_updated = None
            demand_location = None
            if demand_id and demand_id in docs:
                tasks = (docs[demand_id] or {}).get("tasks") or []
                if tasks and isinstance(tasks[0], dict):
                    data = tasks[0].get("data") or {}
                    demand_location = data.get("location_code")
                    results = tasks[0].get("result") or []
                    if results and isinstance(results[0], dict):
                        for item in results[0].get("items") or []:
                            if isinstance(item, dict) and item.get("keyword") == term:
                                kw_info = item.get("keyword_info") or {}
                                demand_updated = kw_info.get("last_updated_time")
                                break
            accepted.append({
                "query_id": q.get("query_id") or f"q{idx}",
                "query": term,
                "status": "accepted",
                "role": q.get("role"),
                "theme_id": (q.get("theme") or {}).get("id"),
                "theme_label": (q.get("theme") or {}).get("label"),
                "reason": reason,
                "user_instruction": q.get("user_instruction"),
                "demand_source": demand_id,
                "demand_location_code": demand_location,
                "demand_provider_updated_at": demand_updated,
                "demand_scope": q.get("demand_scope"),
                "intent_assessment": q.get("intent_assessment"),
                "limitations": q.get("limitations"),
                "offering_quotes": [
                    {"source_id": ref.get("source_id"), "quote": ref.get("quote")}
                    for ref in (q.get("offering_evidence") or [])
                    if isinstance(ref, dict)
                ],
            })
        else:
            is_deferred = (
                disposition == "deferred"
                or any(
                    word in reason.lower()
                    for word in ("defer", "later", "future", "phase 2", "next study", "seasonal")
                )
            )
            entry = {
                "query": term,
                "status": "deferred" if is_deferred else "rejected",
                "role": q.get("role"),
                "reason": reason or "No reason supplied",
            }
            if is_deferred:
                deferred.append(entry)
            else:
                rejected.append(entry)

    return {
        "accepted": accepted,
        "rejected": rejected,
        "deferred": deferred,
    }


def evaluate_business_inputs(
    plan: dict[str, Any],
    docs: dict[str, Any],
    sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Identify observed public sources and mark unprovided private inputs as unknown without blocking first use."""
    kinds_present = sorted({s.get("kind", "") for s in sources.values()})
    declared_inputs = plan.get("business_inputs") or {}
    missing_inputs: list[dict[str, Any]] = []
    provided_inputs: list[dict[str, str]] = []

    for key, description in KNOWN_BUSINESS_INPUTS:
        entry = declared_inputs.get(key) if isinstance(declared_inputs, dict) else None
        if isinstance(entry, dict) and entry.get("status") == "observed" and entry.get("source_id") in sources:
            provided_inputs.append({
                "input": key,
                "description": description,
                "source_id": str(entry["source_id"]),
            })
        else:
            missing_inputs.append({
                "input": key,
                "description": description,
                "status": "unknown",
                "required_for_first_use": False,
                "impact": (
                    "Marked unknown; not required for first use. An explicitly exploratory public study "
                    "is allowed, while conversion rates, revenue, and profitable dispatch territory remain unmeasured."
                ),
            })

    website_pages_captured = 0
    for s in sources.values():
        if s.get("kind") == "website":
            website_pages_captured += 1

    return {
        "evidence_mode": plan.get("evidence_mode", "website_and_profile"),
        "study_posture": "private_inputs_augmented" if provided_inputs else "explicitly_exploratory_public_study",
        "public_study_allowed_without_private_inputs": True,
        "first_use_policy": (
            "Private accounts, profitability data, and owner interview answers are never required for first use; "
            "unprovided private inputs are marked unknown and an explicitly exploratory public study is permitted."
        ),
        "observed_source_kinds": kinds_present,
        "website_captures_count": website_pages_captured,
        "single_homepage_capture_only": website_pages_captured == 1,
        "provided_private_inputs": provided_inputs,
        "missing_business_inputs": missing_inputs,
    }


def _validate_request_payload(req_path: Path, expected_sha: str, sid: str) -> dict[str, Any]:
    """Verify request payload hash and ensure request body is non-empty JSON."""
    actual_sha = digest(req_path)
    require(actual_sha == expected_sha, f"request payload hash mismatch: {sid}")
    doc = json.loads(req_path.read_text(encoding="utf-8-sig"))
    require(isinstance(doc, dict), f"request payload must be a JSON object: {sid}")
    body = doc.get("body")
    if body is None and isinstance(doc.get("request"), dict):
        body = doc["request"].get("body")
    require(
        isinstance(body, (list, dict)) and len(body) > 0,
        f"request payload has empty or missing body: {sid}",
    )
    return doc


def _validate_provider_envelope(
    doc: dict[str, Any],
    sid: str,
    *,
    expected_result_count: int | None = None,
) -> dict[str, Any]:
    """Reject pending, failed, or empty provider envelopes as invalid evidence."""
    require(isinstance(doc, dict), f"provider evidence must be a JSON object: {sid}")
    envelope = (
        doc["response"]
        if isinstance(doc.get("response"), dict) and "tasks" in doc.get("response", {})
        else doc
    )
    require(envelope.get("status_code") == 20000, f"provider envelope failed or pending: {sid}")
    tasks = envelope.get("tasks")
    require(isinstance(tasks, list) and len(tasks) > 0, f"missing provider tasks: {sid}")
    for t in tasks:
        require(isinstance(t, dict), f"invalid provider task entry: {sid}")
        t_status = t.get("status_code")
        require(t_status == 20000, f"pending or failed provider task ({t_status}) is not valid evidence: {sid}")
        res = t.get("result")
        require(isinstance(res, list) and len(res) > 0, f"empty provider result is not valid evidence: {sid}")
        first = res[0]
        if isinstance(first, dict) and "items" in first:
            items = first.get("items")
            require(
                isinstance(items, list) and len(items) > 0,
                f"empty provider result items is not valid evidence: {sid}",
            )
        if expected_result_count is not None:
            require(
                t.get("result_count") == expected_result_count and expected_result_count > 0,
                f"provider result_count mismatch or zero: {sid}",
            )
    return envelope


def inspect_external_adapters(
    plan: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    """Validate optional Study Library or AI Marketing Hub Home source contracts without runtime coupling."""
    external = plan.get("external_evidence") or []
    require(isinstance(external, list), "external_evidence must be a list when present")
    records: list[dict[str, Any]] = []
    for item in external:
        require(isinstance(item, dict), "external_evidence item must be an object")
        adapter = nonempty(item.get("adapter"), "external_evidence.adapter")
        require(
            adapter in ("study_library", "aimh_home", "local_evidence"),
            "external_evidence.adapter must be study_library, aimh_home, or local_evidence",
        )
        sid = nonempty(item.get("id"), "external_evidence.id")
        rel_file = nonempty(item.get("file"), "external_evidence.file")
        path = inside(root, rel_file)
        expected_sha = nonempty(item.get("sha256"), "external_evidence.sha256")
        require(digest(path) == expected_sha, f"external evidence hash mismatch: {sid}")
        stamp = _parse_iso(item.get("observed_at", ""))
        records.append({
            "id": sid,
            "adapter": adapter,
            "file": rel_file,
            "sha256": expected_sha,
            "observed_at": stamp.isoformat(),
            "contract": item.get("contract") or "source_link_only",
        })
    return {
        "standalone_mode": True,
        "home_runtime_required": False,
        "attached_external_records": records,
        "boundary_policy": (
            "legends-geogrid runs standalone without AI Marketing Hub Home or MCP servers. "
            "Optional Library or Home evidence is consumed only via local hash-verified source files and citations."
        ),
    }


def review_refresh_dir(
    refresh_dir: str | Path,
    *,
    now: datetime | None = None,
    warn_age_days: float = 14.0,
    max_age_days: float = 30.0,
) -> dict[str, Any]:
    """Inspect a research refresh directory (provider-evidence-manifest.json, website manifest, and optional analysis/query-review.json)."""
    now = now or datetime.now(timezone.utc)
    rpath = Path(refresh_dir).resolve()
    if rpath.is_file():
        rpath = rpath.parent
    require(rpath.is_dir(), f"refresh directory not found: {refresh_dir}")

    manifest_path = rpath / "provider-evidence-manifest.json"
    require(manifest_path.is_file(), "provider-evidence-manifest.json missing in refresh directory")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    require(isinstance(manifest, dict), "refresh manifest must be a JSON object")
    nonempty(manifest.get("schema"), "refresh manifest schema")

    entries = manifest.get("entries") or []
    require(isinstance(entries, list) and len(entries) > 0, "refresh manifest entries required")
    expected_tasks = manifest.get("tasks")
    if isinstance(expected_tasks, int):
        require(len(entries) == expected_tasks, "refresh manifest entry count differs from declared tasks")

    by_endpoint_family: dict[str, int] = {}
    maps_pilot_queries: dict[str, int] = {}
    organic_pilot_queries: list[str] = []
    refreshed_gbp: dict[str, Any] | None = None
    oldest_days = 0.0
    newest_days = math.inf
    expired_task_ids: list[str] = []
    aging_task_ids: list[str] = []
    task_sources: list[dict[str, Any]] = []

    for entry in entries:
        require(isinstance(entry, dict), "refresh manifest entry must be an object")
        tid = nonempty(entry.get("task_id"), "entry.task_id")
        req_rel = nonempty(entry.get("request_file"), f"request_file for {tid}")
        req_sha = nonempty(entry.get("request_sha256"), f"request_sha256 for {tid}")
        resp_rel = nonempty(entry.get("response_file"), f"response_file for {tid}")
        resp_sha = nonempty(entry.get("response_sha256"), f"response_sha256 for {tid}")

        req_file = inside(rpath, req_rel)
        _validate_request_payload(req_file, req_sha, tid)

        resp_file = inside(rpath, resp_rel)
        require(digest(resp_file) == resp_sha, f"response hash mismatch: {tid}")
        resp_doc = json.loads(resp_file.read_text(encoding="utf-8-sig"))
        require(entry.get("status_code") == 20000, f"manifest status_code not 20000: {tid}")
        res_count = entry.get("result_count")
        require(isinstance(res_count, int) and res_count > 0, f"manifest result_count must be > 0: {tid}")
        envelope = _validate_provider_envelope(resp_doc, tid, expected_result_count=res_count)

        obs_iso = str(entry.get("retrieved_at") or resp_doc.get("retrieved_at") or "")
        stamp = _parse_iso(obs_iso)
        age_sec = (now - stamp).total_seconds()
        require(age_sec >= -300, f"refresh response is future dated: {tid}")
        age_d = round(max(0.0, age_sec) / 86400.0, 2)
        oldest_days = max(oldest_days, age_d)
        newest_days = min(newest_days, age_d)

        if age_d > max_age_days:
            f_state = "expired_for_new_paid_scan"
            expired_task_ids.append(tid)
        elif age_d >= warn_age_days:
            f_state = "aging_review_recommended"
            aging_task_ids.append(tid)
        else:
            f_state = "fresh"

        ep = str(entry.get("endpoint") or "")
        task0 = envelope["tasks"][0]
        tdata = task0.get("data") or {}
        if "/keywords_for_keywords/" in ep:
            fam = "keywords_for_keywords"
        elif "/keywords_for_site/" in ep:
            fam = "keywords_for_site"
        elif "/search_volume/" in ep:
            fam = "search_volume"
        elif "/serp/google/maps/" in ep:
            fam = "maps_pilot"
            kw = str(tdata.get("keyword") or "").strip()
            if kw:
                maps_pilot_queries[kw] = maps_pilot_queries.get(kw, 0) + 1
        elif "/serp/google/organic/" in ep:
            fam = "organic_pilot"
            kw = str(tdata.get("keyword") or "").strip()
            if kw and kw not in organic_pilot_queries:
                organic_pilot_queries.append(kw)
        elif "/my_business_info/" in ep:
            fam = "gbp_profile"
            items = ((task0.get("result") or [{}])[0]).get("items") or []
            if items and isinstance(items[0], dict):
                gitem = items[0]
                refreshed_gbp = {
                    "cid": str(gitem.get("cid") or ""),
                    "title": gitem.get("title"),
                    "primary_category": gitem.get("category"),
                    "additional_categories": list(gitem.get("additional_categories") or []),
                    "address": gitem.get("address"),
                    "domain": gitem.get("domain"),
                }
        else:
            fam = "other"
        by_endpoint_family[fam] = by_endpoint_family.get(fam, 0) + 1
        task_sources.append({
            "id": tid,
            "kind": fam,
            "file": resp_rel,
            "observed_at": obs_iso,
            "age_days": age_d,
            "freshness_state": f_state,
            "url": ep,
        })

    if math.isinf(newest_days):
        newest_days = 0.0

    # Website manifest inspection if present (generic field handling; reports unavailable when absent)
    website_dir = rpath / "website"
    ws_manifest_path = website_dir / "source-manifest.json"
    if ws_manifest_path.is_file():
        ws_manifest = json.loads(ws_manifest_path.read_text(encoding="utf-8-sig"))
        require(isinstance(ws_manifest, dict), "website/source-manifest.json must be a JSON object")
        summary_obj = (
            ws_manifest.get("summary")
            if isinstance(ws_manifest.get("summary"), dict)
            else (ws_manifest.get("counts") if isinstance(ws_manifest.get("counts"), dict) else {})
        )
        ep_list = (
            ws_manifest.get("entries")
            if isinstance(ws_manifest.get("entries"), list)
            else (ws_manifest.get("endpoints") if isinstance(ws_manifest.get("endpoints"), list) else None)
        )
        sitemap_sub = summary_obj.get("sitemap_declared_urls") if isinstance(summary_obj.get("sitemap_declared_urls"), dict) else {}
        sitemap_brk = ws_manifest.get("sitemap_breakdown") if isinstance(ws_manifest.get("sitemap_breakdown"), dict) else {}

        declared_sitemap_urls = (
            summary_obj.get("distinct_sitemap_urls_total")
            if "distinct_sitemap_urls_total" in summary_obj
            else (
                sitemap_sub.get("total_unique_sitemap_urls")
                if "total_unique_sitemap_urls" in sitemap_sub
                else (
                    sitemap_brk.get("total_distinct_sitemap_urls")
                    if "total_distinct_sitemap_urls" in sitemap_brk
                    else summary_obj.get("declared_unique_sitemap_urls", ws_manifest.get("declared_unique_sitemap_urls"))
                )
            )
        )
        captured_sitemap_urls = summary_obj.get("distinct_sitemap_urls_captured")
        substantive_pages = summary_obj.get("substantive_html_pages_inspected")
        total_endpoints = (
            summary_obj.get("total_endpoints_captured")
            if "total_endpoints_captured" in summary_obj
            else (
                summary_obj.get("total_endpoints_fetched")
                if "total_endpoints_fetched" in summary_obj
                else (len(ep_list) if ep_list is not None else None)
            )
        )

        verified_raw_files: int | None = 0 if ep_list is not None else None
        mismatched_or_inflight_raw_files: list[str] = []
        http_200_pages: int | None = 0 if ep_list is not None else None
        if ep_list is not None:
            for ep_entry in ep_list:
                if not isinstance(ep_entry, dict):
                    continue
                raw_rel = ep_entry.get("raw_file")
                ep_sha = ep_entry.get("sha256")
                key = str(ep_entry.get("key") or raw_rel or "")
                if raw_rel and ep_sha:
                    raw_path = inside(website_dir, str(raw_rel))
                    if digest(raw_path) == ep_sha:
                        verified_raw_files = (verified_raw_files or 0) + 1
                    else:
                        mismatched_or_inflight_raw_files.append(key)
                    if ep_entry.get("status") == 200:
                        require(raw_path.stat().st_size > 0, f"empty HTTP 200 website capture: {key}")
                        if ep_entry.get("category") not in ("meta", "sitemap"):
                            http_200_pages = (http_200_pages or 0) + 1

        raw_dir = website_dir / "raw"
        raw_files_on_disk = len(list(raw_dir.glob("*"))) if raw_dir.is_dir() else None
        captured_for_coverage = (
            captured_sitemap_urls
            if isinstance(captured_sitemap_urls, int)
            else http_200_pages
        )
        if isinstance(declared_sitemap_urls, int) and declared_sitemap_urls > 0 and isinstance(captured_for_coverage, int):
            sitemap_coverage_status = (
                "complete"
                if (captured_for_coverage >= declared_sitemap_urls and not mismatched_or_inflight_raw_files)
                else "in_progress_partial"
            )
        else:
            sitemap_coverage_status = "unavailable"

        website_summary: dict[str, Any] = {
            "status": "available",
            "manifest_file": str(ws_manifest_path),
            "generated_at": ws_manifest.get("generated_at") or ws_manifest.get("generated_at_utc"),
            "domain": ws_manifest.get("domain"),
            "total_endpoints_captured": total_endpoints,
            "distinct_sitemap_urls_total": declared_sitemap_urls,
            "distinct_sitemap_urls_captured": captured_sitemap_urls if captured_sitemap_urls is not None else http_200_pages,
            "substantive_html_pages_inspected": substantive_pages,
            "raw_files_on_disk": raw_files_on_disk,
            "verified_raw_files_sha256": verified_raw_files,
            "inflight_or_mismatched_raw_files": mismatched_or_inflight_raw_files,
            "http_200_content_pages_fetched": http_200_pages,
            "declared_unique_sitemap_urls": declared_sitemap_urls,
            "sitemap_coverage_status": sitemap_coverage_status,
        }
    else:
        website_summary = {
            "status": "unavailable",
            "manifest_file": None,
            "sitemap_coverage_status": "unavailable",
        }

    # Check optional analyst review file at analysis/query-review.json
    analyst_review_path = rpath / "analysis" / "query-review.json"
    analyst_review_summary: dict[str, Any] = {
        "expected_path": str(analyst_review_path),
        "present": analyst_review_path.is_file(),
    }
    if analyst_review_path.is_file():
        ar_doc = json.loads(analyst_review_path.read_text(encoding="utf-8-sig"))
        require(isinstance(ar_doc, dict), "analysis/query-review.json must be a JSON object")
        serialized_lower = json.dumps(ar_doc).lower()
        require(
            "opportunity_score" not in serialized_lower,
            "analysis/query-review.json must not fabricate numerical opportunity_score values",
        )
        analyst_review_summary["schema"] = ar_doc.get("schema")
        analyst_review_summary["sha256"] = digest(analyst_review_path)

    return {
        "refresh_dir": str(rpath),
        "manifest_sha256": digest(manifest_path),
        "business_cid": manifest.get("business_cid"),
        "method": manifest.get("method"),
        "tasks_verified": len(entries),
        "all_request_and_response_hashes_valid": True,
        "all_tasks_completed_non_empty": True,
        "submission_cost_usd": manifest.get("submission_cost_usd"),
        "newest_age_days": newest_days,
        "oldest_age_days": oldest_days,
        "expired_task_ids": expired_task_ids,
        "aging_task_ids": aging_task_ids,
        "task_sources": task_sources,
        "endpoint_breakdown": by_endpoint_family,
        "maps_pilot_queries": maps_pilot_queries,
        "organic_pilot_queries": organic_pilot_queries,
        "refreshed_gbp_profile": refreshed_gbp,
        "website_inventory": website_summary,
        "analyst_query_review": analyst_review_summary,
        "limitations": manifest.get("limitations") or [],
    }


def _resolve_plan_ref(ref_str: str, base_dir: Path) -> Path:
    candidate = Path(ref_str)
    if candidate.is_absolute() and candidate.is_file():
        return candidate.resolve()
    repo_root = Path(__file__).resolve().parent.parent
    for root in (base_dir, repo_root, Path.cwd()):
        resolved = (root / candidate).resolve()
        if resolved.is_file():
            return resolved
    return (base_dir / candidate).resolve()


ADVISORY_SCOPE = "review_not_collection_authorization"
COLLECTION_READINESS = "not_assessed"
COLLECTION_READINESS_NOTE = (
    "Advisory review only (review_not_collection_authorization); collection_readiness is not_assessed here. "
    "Full study_contract.validate() and visibility_policy checks run separately before paid collection. "
    "Private analytics are never required."
)


def review_plan(
    plan_path: str | Path | None = None,
    *,
    competitive_plan_path: str | Path | None = None,
    refresh_dir: str | Path | None = None,
    now: datetime | None = None,
    warn_age_days: float = 14.0,
    max_age_days: float = 30.0,
) -> dict[str, Any]:
    """Run evidence freshness and query-selection review on a study plan, competitive plan, and/or refresh directory."""
    now = now or datetime.now(timezone.utc)
    require(math.isfinite(warn_age_days) and 0 < warn_age_days <= max_age_days, "invalid warn_age_days")
    require(math.isfinite(max_age_days) and 0 < max_age_days <= 365, "invalid max_age_days")
    require(plan_path is not None or refresh_dir is not None, "either --plan or --refresh-dir is required")

    # If plan_path points directly to a refresh directory or provider-evidence-manifest.json
    if plan_path is not None and refresh_dir is None:
        candidate_path = Path(plan_path).resolve()
        if candidate_path.is_dir() and (candidate_path / "provider-evidence-manifest.json").is_file():
            refresh_dir = candidate_path
            plan_path = None
        elif candidate_path.is_file() and candidate_path.name == "provider-evidence-manifest.json":
            refresh_dir = candidate_path.parent
            plan_path = None

    refresh_summary = (
        review_refresh_dir(refresh_dir, now=now, warn_age_days=warn_age_days, max_age_days=max_age_days)
        if refresh_dir is not None
        else None
    )

    if plan_path is None:
        assert refresh_summary is not None
        ws = refresh_summary.get("website_inventory") or {}
        ref_expired = list(refresh_summary.get("expired_task_ids") or [])
        ref_aging = list(refresh_summary.get("aging_task_ids") or [])
        ref_oldest = float(refresh_summary["oldest_age_days"])
        ref_newest = float(refresh_summary["newest_age_days"])
        ref_spread = round(max(0.0, ref_oldest - ref_newest), 2)
        ref_mixed = ref_spread >= 7.0
        flags: list[str] = [
            "No study-plan.json was supplied; refresh directory inspection is advisory and cannot authorize paid collection."
        ]
        if ref_expired:
            flags.append(
                f"Refresh tasks exceed the {max_age_days:g}-day new-collection window ({', '.join(ref_expired)}). "
                "Historical reports remain valid and frozen; capture current evidence before buying a new scan."
            )
        elif ref_aging:
            flags.append(
                f"Refresh tasks are {ref_oldest:.1f} days old ({', '.join(ref_aging)}). "
                f"Within the {max_age_days:g}-day contract window, but older than the {warn_age_days:g}-day freshness warning threshold; "
                "Note: observation age does not prove content changed, but verify current offers/categories if refreshing."
            )
        if ref_mixed:
            flags.append(
                f"Refresh task timestamps span {ref_spread:.1f} days (newest {ref_newest:.1f}d, oldest {ref_oldest:.1f}d)."
            )
        if ws.get("status") == "unavailable":
            flags.append("Website source-manifest.json is unavailable in refresh directory.")
        elif ws.get("sitemap_coverage_status") == "in_progress_partial":
            flags.append(
                f"Website refresh has verified {ws.get('distinct_sitemap_urls_captured')} captured sitemap pages "
                f"of {ws.get('distinct_sitemap_urls_total')} declared unique sitemap URLs "
                f"(status: {ws.get('sitemap_coverage_status')})."
            )
        if not refresh_summary["analyst_query_review"]["present"]:
            flags.append(
                f"Analyst query review artifact (analysis/query-review.json) is not yet present; "
                f"{refresh_summary['tasks_verified']} provider tasks and request/response hashes are verified."
            )
        age_within_window = bool(refresh_summary["tasks_verified"] > 0 and len(ref_expired) == 0)
        return {
            "schema": REVIEW_SCHEMA,
            "reviewed_at": now.isoformat(),
            "plan_file": None,
            "plan_sha256": refresh_summary["manifest_sha256"],
            "business": {
                "cid": refresh_summary.get("business_cid"),
                "name": (refresh_summary.get("refreshed_gbp_profile") or {}).get("title") or "Refreshed Business",
                "domain": (refresh_summary.get("refreshed_gbp_profile") or {}).get("domain"),
            },
            "status": "historical_frozen" if ref_expired else "review_recommended",
            "measurement_posture": {
                "mode": "historical_frozen_evidence" if ref_expired else "fresh_collection_candidate",
                "active_settings": {"method": refresh_summary.get("method")},
                "advisory_scope": ADVISORY_SCOPE,
                "review_not_collection_authorization": True,
                "source_age_within_window": age_within_window,
                "collection_readiness": COLLECTION_READINESS,
                "collection_readiness_note": COLLECTION_READINESS_NOTE,
                "historical_study_frozen": True,
                "flags": flags,
            },
            "source_freshness": {
                "warn_age_days": warn_age_days,
                "max_age_days": max_age_days,
                "oldest_age_days": ref_oldest,
                "newest_age_days": ref_newest,
                "age_spread_days": ref_spread,
                "mixed_vintage": ref_mixed,
                "expired_source_ids": ref_expired,
                "aging_source_ids": ref_aging,
                "sources": list(refresh_summary.get("task_sources") or []),
                "certainty_note": (
                    "Observation age measures time elapsed since capture, not proof that external website or GBP facts changed."
                ),
            },
            "service_theme_coverage": {
                "selected_count": 0,
                "non_selected_count": 0,
                "roles_covered": [],
                "observed_gbp_categories": (
                    ([refresh_summary["refreshed_gbp_profile"]["primary_category"]] if (refresh_summary.get("refreshed_gbp_profile") or {}).get("primary_category") else [])
                    + list((refresh_summary.get("refreshed_gbp_profile") or {}).get("additional_categories") or [])
                ),
                "directly_matched_gbp_categories": [],
                "indirect_or_partial_gbp_categories": [],
                "unselected_gbp_categories": [],
                "selected_themes": [],
                "non_selected_candidates_documented": False,
            },
            "synonym_overlaps": [],
            "query_decisions": {"accepted": [], "rejected": [], "deferred": []},
            "business_inputs": evaluate_business_inputs({}, {}, {}),
            "adapter_boundary": inspect_external_adapters({}, Path(refresh_dir).resolve()),
            "competitive_alignment": None,
            "refresh_evidence": refresh_summary,
            "non_fabrication_policy": (
                "No numerical opportunity scores, local demand estimates, or expiry certainties are invented. "
                "Existing queries are not automatically wrong and historical query IDs are never auto-substituted."
            ),
        }

    path = Path(plan_path).resolve()
    raw = json.loads(path.read_text(encoding="utf-8-sig"))

    comp_plan: dict[str, Any] | None = None
    comp_path: Path | None = None
    if raw.get("schema") == COMPETITIVE_PLAN_SCHEMA and competitive_plan_path is None:
        comp_plan = raw
        comp_path = path
        sp_ref = comp_plan.get("source_study_plan")
        require(bool(sp_ref), "competitive plan requires source_study_plan for query review")
        path = _resolve_plan_ref(str(sp_ref), comp_path.parent)
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    elif competitive_plan_path is not None:
        comp_path = Path(competitive_plan_path).resolve()
        comp_plan = json.loads(comp_path.read_text(encoding="utf-8-sig"))

    require(raw.get("schema") == SCHEMA, "unsupported study schema")
    root = path.parent

    sources: dict[str, dict[str, Any]] = {}
    docs: dict[str, Any] = {}
    source_ages: list[dict[str, Any]] = []
    oldest_days = 0.0
    newest_days = math.inf
    expired_sources: list[str] = []
    aging_sources: list[str] = []

    for src in raw.get("sources") or []:
        sid = nonempty(src.get("id"), "source id")
        kind = nonempty(src.get("kind"), "source kind")
        file_path = inside(root, src.get("file", ""))
        actual_sha = digest(file_path)
        require(actual_sha == src.get("sha256"), f"source hash mismatch: {sid}")
        if src.get("request_file") is not None or src.get("request_sha256") is not None:
            req_rel = nonempty(src.get("request_file"), f"request_file for {sid}")
            req_sha = nonempty(src.get("request_sha256"), f"request_sha256 for {sid}")
            req_path = inside(root, req_rel)
            _validate_request_payload(req_path, req_sha, sid)
        stamp = _parse_iso(src.get("observed_at", ""))
        age_seconds = (now - stamp).total_seconds()
        require(age_seconds >= -300, f"source is future dated: {sid}")
        age_days = round(max(0.0, age_seconds) / 86400.0, 2)
        oldest_days = max(oldest_days, age_days)
        newest_days = min(newest_days, age_days)

        if age_days > max_age_days:
            freshness_state = "expired_for_new_paid_scan"
            expired_sources.append(sid)
        elif age_days >= warn_age_days:
            freshness_state = "aging_review_recommended"
            aging_sources.append(sid)
        else:
            freshness_state = "fresh"

        sources[sid] = src
        docs[sid] = json.loads(file_path.read_text(encoding="utf-8-sig"))
        if kind == "website":
            require(
                isinstance(docs[sid], dict) and bool(str(docs[sid].get("text") or "").strip()),
                f"empty website text is not valid evidence: {sid}",
            )
        elif kind in ("gbp", "demand", "maps_probe", "organic_probe"):
            _validate_provider_envelope(docs[sid], sid)

        source_ages.append({
            "id": sid,
            "kind": kind,
            "file": src.get("file"),
            "observed_at": src.get("observed_at"),
            "age_days": age_days,
            "freshness_state": freshness_state,
            "url": src.get("url"),
        })

    if math.isinf(newest_days):
        newest_days = 0.0

    age_spread_days = round(max(0.0, oldest_days - newest_days), 2)
    mixed_vintage = age_spread_days >= 7.0

    # Measurement posture: distinguish historical/reused vs fresh planned scan, and check settings
    settings = dict(raw.get("settings") or {})
    comp_settings = dict((comp_plan or {}).get("measurement_settings") or {})
    active_settings = comp_settings if comp_settings else settings

    has_composition = isinstance((comp_plan or {}).get("composition"), dict)
    if expired_sources or not source_ages:
        measurement_mode = "historical_frozen_evidence" if expired_sources else "incomplete_evidence"
    elif has_composition:
        measurement_mode = "composed_archive_reuse"
    else:
        measurement_mode = "fresh_collection_candidate"

    posture_flags: list[str] = []
    if not source_ages:
        posture_flags.append(
            "No sources are listed in the study plan; evidence sources are required before collection."
        )
    if expired_sources:
        posture_flags.append(
            f"Sources exceed the {max_age_days:g}-day new-collection window ({', '.join(expired_sources)}). "
            "Historical reports remain valid and frozen; capture current evidence before buying a new scan."
        )
    elif aging_sources:
        posture_flags.append(
            f"Sources are {oldest_days:.1f} days old ({', '.join(aging_sources)}). "
            f"Within the {max_age_days:g}-day contract window, but older than the {warn_age_days:g}-day freshness warning threshold; "
            "Note: observation age does not prove content changed, but verify current offers/categories if refreshing."
        )
    if mixed_vintage:
        posture_flags.append(
            f"Source timestamps span {age_spread_days:.1f} days (newest {newest_days:.1f}d, oldest {oldest_days:.1f}d). "
            "Website/GBP evidence and SERP/demand probes were collected on different dates."
        )
    if active_settings.get("method") == "live":
        posture_flags.append(
            "Plan specifies method='live' ($0.002/task). Default for Maps ranking studies is Standard queue "
            "($0.0006/task) unless Live is explicitly requested by the user with --allow-live."
        )
    if active_settings.get("search_this_area") is True:
        posture_flags.append(
            "Plan specifies search_this_area=true. Regional origin-based visibility studies default to "
            "search_this_area=false to avoid rectangular viewport cutoffs unless an explicit viewport experiment is intended."
        )

    coverage = extract_service_theme_coverage(raw, docs, sources)
    decisions = classify_query_decisions(raw, docs)
    overlaps = detect_synonym_overlaps(raw.get("queries") or [])
    inputs = evaluate_business_inputs(raw, docs, sources)
    adapters = inspect_external_adapters(raw, root)

    if not decisions["rejected"] and not decisions["deferred"]:
        posture_flags.append(
            "No rejected or deferred candidate queries are recorded in the study plan. "
            "Record considered alternatives and why they were omitted so future reviews do not repeat pilot spend."
        )
    if inputs["single_homepage_capture_only"]:
        posture_flags.append(
            "Only one website source capture is attached. When dedicated service or city landing pages exist, "
            "capture and cite them alongside the homepage."
        )
    if coverage["unselected_gbp_categories"]:
        posture_flags.append(
            "Observed GBP categories not represented in selected query concepts: "
            + ", ".join(coverage["unselected_gbp_categories"])
            + ". Confirm whether these are intentionally omitted or deferred."
        )
    if coverage["indirect_or_partial_gbp_categories"]:
        posture_flags.append(
            "Observed GBP categories covered only indirectly via synonym or related service query: "
            + ", ".join(coverage["indirect_or_partial_gbp_categories"])
            + "."
        )
    if refresh_summary is not None:
        ref_gbp = refresh_summary.get("refreshed_gbp_profile") or {}
        if ref_gbp.get("primary_category") and coverage["observed_gbp_categories"]:
            old_primary = coverage["observed_gbp_categories"][0]
            if ref_gbp["primary_category"] != old_primary:
                posture_flags.append(
                    f"Refreshed GBP primary category ('{ref_gbp['primary_category']}') differs from the study plan's "
                    f"earlier GBP primary category ('{old_primary}'); reconcile before buying a new scan."
                )
        ws = refresh_summary.get("website_inventory") or {}
        if ws.get("sitemap_coverage_status") == "in_progress_partial":
            posture_flags.append(
                f"Website refresh has verified {ws.get('distinct_sitemap_urls_captured')} captured sitemap pages "
                f"of {ws.get('distinct_sitemap_urls_total')} declared unique sitemap URLs "
                f"(status: {ws.get('sitemap_coverage_status')})."
            )
        if not refresh_summary["analyst_query_review"]["present"]:
            posture_flags.append(
                f"Analyst query review artifact (analysis/query-review.json) is not yet present; "
                f"{refresh_summary['tasks_verified']} provider tasks and request/response hashes are verified."
            )

    # Verify competitive plan query ID and text alignment if supplied
    competitive_alignment = None
    if comp_plan is not None:
        comp_queries = [
            {
                "query_id": str(q.get("query_id") or f"q{idx}").strip(),
                "query": str(q.get("query") or q.get("keyword") or "").strip(),
            }
            for idx, q in enumerate(comp_plan.get("query_selection") or comp_plan.get("queries") or [], start=1)
            if isinstance(q, dict)
        ]
        study_queries = [
            {
                "query_id": str(q["query_id"]).strip(),
                "query": str(q["query"]).strip(),
            }
            for q in decisions["accepted"]
        ]
        ids_match = [q["query_id"] for q in comp_queries] == [q["query_id"] for q in study_queries]
        texts_match = [q["query"].lower() for q in comp_queries] == [q["query"].lower() for q in study_queries]
        exact_match = ids_match and texts_match
        if not exact_match:
            posture_flags.append(
                "Competitive plan query IDs or query strings differ from the source study plan; "
                "do not silently substitute historical query IDs."
            )
        competitive_alignment = {
            "competitive_plan_file": str(comp_path),
            "competitive_queries": comp_queries,
            "matches_study_plan_ids": ids_match,
            "matches_study_plan_order_and_text": texts_match,
            "matches_study_plan_ids_and_text": exact_match,
            "historical_query_ids_preserved": ids_match,
            "note": (
                "Competitive plan query IDs and exact query strings match the source study plan; "
                "historical query IDs are preserved."
                if exact_match
                else (
                    "Competitive plan query strings match, but query_id values differ from the source study plan."
                    if texts_match
                    else "Competitive plan queries differ in ID, text, or order from the source study plan; "
                    "do not silently substitute historical query IDs."
                )
            ),
        }

    age_within_window = bool(source_ages) and len(expired_sources) == 0
    overall_status = (
        "historical_frozen"
        if expired_sources
        else (
            "review_recommended"
            if (not age_within_window or aging_sources or overlaps or posture_flags)
            else "advisory_reviewed"
        )
    )

    return {
        "schema": REVIEW_SCHEMA,
        "reviewed_at": now.isoformat(),
        "plan_file": str(path),
        "plan_sha256": digest(path),
        "business": raw.get("business"),
        "status": overall_status,
        "measurement_posture": {
            "mode": measurement_mode,
            "active_settings": {
                k: active_settings.get(k)
                for k in ("method", "depth", "zoom", "device", "search_this_area", "language_code", "se_domain")
            },
            "advisory_scope": ADVISORY_SCOPE,
            "review_not_collection_authorization": True,
            "source_age_within_window": age_within_window,
            "collection_readiness": COLLECTION_READINESS,
            "collection_readiness_note": COLLECTION_READINESS_NOTE,
            "historical_study_frozen": True,
            "flags": posture_flags,
        },
        "source_freshness": {
            "warn_age_days": warn_age_days,
            "max_age_days": max_age_days,
            "oldest_age_days": oldest_days,
            "newest_age_days": newest_days,
            "age_spread_days": age_spread_days,
            "mixed_vintage": mixed_vintage,
            "expired_source_ids": expired_sources,
            "aging_source_ids": aging_sources,
            "sources": source_ages,
            "certainty_note": (
                "Observation age measures time elapsed since capture, not proof that external website or GBP facts changed."
            ),
        },
        "service_theme_coverage": coverage,
        "synonym_overlaps": overlaps,
        "query_decisions": decisions,
        "business_inputs": inputs,
        "adapter_boundary": adapters,
        "competitive_alignment": competitive_alignment,
        "refresh_evidence": refresh_summary,
        "non_fabrication_policy": (
            "No numerical opportunity scores, local demand estimates, or expiry certainties are invented. "
            "Existing queries are not automatically wrong and historical query IDs are never auto-substituted."
        ),
    }


def format_markdown(review: dict[str, Any]) -> str:
    """Render a concise, owner-actionable Markdown summary of the query & freshness review."""
    b = review.get("business") or {}
    freshness = review["source_freshness"]
    posture = review["measurement_posture"]
    coverage = review["service_theme_coverage"]
    decisions = review["query_decisions"]

    lines = [
        f"# Query & Evidence Review: {b.get('name', 'Business')}",
        "",
        f"- **Status:** `{review['status']}`",
        f"- **Measurement mode:** `{posture['mode']}` (advisory scope: `{posture['advisory_scope']}`, source age within window: `{posture['source_age_within_window']}`, collection readiness: `{posture['collection_readiness']}`)",
        f"- **Plan SHA-256:** `{review['plan_sha256']}`",
        f"- **Source age range:** `{freshness['newest_age_days']:.2f}d` to `{freshness['oldest_age_days']:.2f}d` (spread `{freshness['age_spread_days']:.2f}d`)",
        "",
        "## Actionable review flags",
        "",
    ]
    if posture["flags"]:
        for flag in posture["flags"]:
            lines.append(f"- {flag}")
    else:
        lines.append("- No freshness, control, or coverage warnings triggered.")

    if review.get("refresh_evidence"):
        ref = review["refresh_evidence"]
        ws = ref.get("website_inventory") or {}
        rgbp = ref.get("refreshed_gbp_profile") or {}
        lines += [
            "",
            "## Refresh evidence verification",
            "",
            f"- **Refresh directory:** `{ref['refresh_dir']}`",
            f"- **Provider tasks verified:** `{ref['tasks_verified']}` (request and response SHA-256 valid: `{ref['all_request_and_response_hashes_valid']}`, all completed 20000 non-empty: `{ref['all_tasks_completed_non_empty']}`)",
            f"- **Endpoint breakdown:** `{json.dumps(ref['endpoint_breakdown'], sort_keys=True)}`",
            f"- **Piloted Maps candidate queries ({len(ref['maps_pilot_queries'])}):** {', '.join(f'`{k}` ({v} origins)' for k, v in ref['maps_pilot_queries'].items())}",
            f"- **Piloted Organic queries ({len(ref['organic_pilot_queries'])}):** {', '.join(f'`{k}`' for k in ref['organic_pilot_queries'])}",
        ]
        if rgbp:
            lines.append(
                f"- **Refreshed GBP categories:** primary `{rgbp.get('primary_category')}`; additional: {', '.join(rgbp.get('additional_categories') or [])}"
            )
        if ws:
            lines.append(
                f"- **Website refresh inventory:** `{ws.get('http_200_content_pages_fetched')}` HTTP 200 content pages / `{ws.get('declared_unique_sitemap_urls')}` sitemap URLs (`{ws.get('sitemap_coverage_status')}`, `{ws.get('verified_raw_files_sha256')}` raw file hashes verified)"
            )

    if freshness["sources"]:
        lines += ["", "## Source observation ages", ""]
        for src in freshness["sources"]:
            lines.append(
                f"- `[{src['id']}]` **{src['kind']}**: `{src['age_days']:.2f}d` old (`{src['observed_at']}`) -> `{src['freshness_state']}`"
            )

    lines += [
        "",
        "## Service-theme coverage",
        "",
        f"- **Selected themes:** {coverage['selected_count']} | **Non-selected documented:** {coverage['non_selected_count']}",
        f"- **Roles covered:** {', '.join(coverage['roles_covered']) or 'none'}",
        f"- **Observed GBP categories:** {', '.join(coverage['observed_gbp_categories']) or 'none'}",
    ]
    if coverage.get("indirect_or_partial_gbp_categories"):
        lines.append(
            f"- **GBP categories covered indirectly via synonym/related service:** {', '.join(coverage['indirect_or_partial_gbp_categories'])}"
        )
    if coverage["unselected_gbp_categories"]:
        lines.append(f"- **GBP categories without direct token match:** {', '.join(coverage['unselected_gbp_categories'])}")

    if review["synonym_overlaps"]:
        lines += ["", "## Synonym and concept overlap review", ""]
        for ov in review["synonym_overlaps"]:
            q_pair = " vs. ".join(f"`{q}`" for q in ov["queries"])
            lines.append(f"- {q_pair} (`{ov['status']}`): {ov['note']}")

    if decisions["accepted"]:
        lines += ["", "## Query portfolio decisions", "", "### Accepted queries", ""]
        for q in decisions["accepted"]:
            lines.append(
                f"- **`{q['query']}`** (`{q['role']}`, theme `{q['theme_id']}`): {q['reason']} "
                f"[Demand scope: {q['demand_scope']}]"
            )

    if decisions["rejected"]:
        lines += ["", "### Rejected candidates", ""]
        for q in decisions["rejected"]:
            lines.append(f"- **`{q['query']}`**: {q['reason']}")

    if decisions["deferred"]:
        lines += ["", "### Deferred candidates", ""]
        for q in decisions["deferred"]:
            lines.append(f"- **`{q['query']}`**: {q['reason']}")

    lines += [
        "",
        "## Private business inputs & exploratory public study posture",
        "",
        f"- **Study posture:** `{review['business_inputs']['study_posture']}` (public study allowed without private inputs: `{review['business_inputs']['public_study_allowed_without_private_inputs']}`)",
    ]
    for item in review["business_inputs"]["missing_business_inputs"]:
        lines.append(f"- **`{item['input']}`** ({item['description']}): `{item['status']}` (required for first use: `{item['required_for_first_use']}`)")

    lines += [
        "",
        "## Adapter boundary & non-fabrication note",
        "",
        f"- {review['adapter_boundary']['boundary_policy']}",
        f"- {review['non_fabrication_policy']}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=None, help="Path to study-plan.json, competitive-plan.json, or refresh manifest/folder")
    parser.add_argument("--competitive-plan", default=None, help="Optional path to competitive-plan.json to verify query alignment")
    parser.add_argument("--refresh-dir", default=None, help="Optional path to intelligence-refresh directory with provider-evidence-manifest.json")
    parser.add_argument("--output", default=None, help="Optional path to write JSON review output (refuses to overwrite)")
    parser.add_argument("--markdown", default=None, help="Optional path to write Markdown review report (refuses to overwrite)")
    parser.add_argument("--warn-age-days", type=float, default=14.0, help="Advisory freshness warning threshold in days (default: 14)")
    parser.add_argument("--max-age-days", type=float, default=30.0, help="Contract maximum source age in days (default: 30)")
    args = parser.parse_args(argv)

    try:
        res = review_plan(
            args.plan,
            competitive_plan_path=args.competitive_plan,
            refresh_dir=args.refresh_dir,
            warn_age_days=args.warn_age_days,
            max_age_days=args.max_age_days,
        )
        if args.output:
            out_path = Path(args.output).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("x", encoding="utf-8") as f:
                json.dump(res, f, indent=2, ensure_ascii=False, allow_nan=False)
        if args.markdown:
            md_path = Path(args.markdown).resolve()
            md_path.parent.mkdir(parents=True, exist_ok=True)
            with md_path.open("x", encoding="utf-8") as f:
                f.write(format_markdown(res))
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, FileNotFoundError) as exc:
        print(f"Query review stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
