#!/usr/bin/env python3
"""Bounded, resumable multi-query geo-grid acquisition. Offline planning by default.

See examples/adaptive/README.md for configuration, replay and spend semantics.
Only the explicit LiveAdapter accesses the network; no credentials are read while
planning or replaying. Each output directory is one immutable acquisition identity.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from typing import Any

import local_heatmap_poc as runner

REVISION = "adaptive-geogrid-v2"
SECTORS = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")
DIRECTIONS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
DEFAULTS = {
    "strategy": "adaptive8sectors", "spacing_km": 1.0, "starting_grid": 3,
    "max_shell": 5, "depth": 20, "negative_depth": 20, "provider_zoom": 13,
    "display_zoom": 11, "language_code": "en", "device": "desktop",
    "se_domain": "google.com", "search_this_area": True, "max_calls": 1000,
    "timeout_seconds": 90,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be finite and between {minimum} and {maximum}")
    return float(value)


def integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    number(value, name, minimum, maximum)
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def coordinates(config: dict, x: int, y: int) -> tuple[float, float]:
    lat = config["center"]["lat"] + y * config["spacing_km"] / 111.32
    lng = config["center"]["lng"] + x * config["spacing_km"] / (
        111.32 * math.cos(math.radians(config["center"]["lat"])))
    if not -90 < lat < 90 or not -180 <= lng <= 180:
        raise ValueError("grid crosses a pole or the antimeridian; choose smaller bounds")
    return round(lat, 7), round(lng, 7)


def validate_config(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("configuration must be a JSON object")
    unknown = set(raw) - set(DEFAULTS) - {"center", "queries", "targets"}
    if unknown:
        raise ValueError(f"unknown configuration fields: {sorted(unknown)}")
    config = copy.deepcopy(DEFAULTS)
    config.update(copy.deepcopy(raw))
    center = config.get("center")
    if not isinstance(center, dict) or set(center) != {"lat", "lng"}:
        raise ValueError("center requires exactly lat and lng")
    number(center["lat"], "center.lat", -89.999999, 89.999999)
    number(center["lng"], "center.lng", -180, 180)
    number(config["spacing_km"], "spacing_km", 0.01, 100)
    integer(config["starting_grid"], "starting_grid", 1, 101)
    if config["starting_grid"] % 2 != 1:
        raise ValueError("starting_grid must be odd")
    integer(config["max_shell"], "max_shell", (config["starting_grid"] - 1) // 2, 50)
    integer(config["depth"], "depth", 1, 700)
    integer(config["negative_depth"], "negative_depth", 1, config["depth"])
    integer(config["provider_zoom"], "provider_zoom", 3, 21)
    integer(config["display_zoom"], "display_zoom", 0, 22)
    integer(config["max_calls"], "max_calls", 1, 1_000_000)
    integer(config["timeout_seconds"], "timeout_seconds", 1, 600)
    if not isinstance(config["strategy"], str) or config["strategy"] not in {"dense", "sparse", "adaptive8sectors"}:
        raise ValueError("strategy must be dense, sparse or adaptive8sectors")
    if type(config["search_this_area"]) is not bool:
        raise ValueError("search_this_area must be a boolean")
    if not isinstance(config["device"], str) or config["device"] not in {"desktop", "mobile"}:
        raise ValueError("device must be desktop or mobile")
    for field in ("language_code", "se_domain"):
        if not isinstance(config[field], str) or not config[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    queries = config.get("queries")
    if not isinstance(queries, list) or not 1 <= len(queries) <= 50:
        raise ValueError("queries requires between 1 and 50 lanes")
    ids = set()
    for query in queries:
        if not isinstance(query, dict) or set(query) != {"id", "keyword"}:
            raise ValueError("each query requires exactly id and keyword")
        if not isinstance(query["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", query["id"]):
            raise ValueError("query id must be 1-64 ASCII letters, digits, underscores or hyphens")
        if query["id"] in ids:
            raise ValueError("query ids must be unique")
        ids.add(query["id"])
        if not isinstance(query["keyword"], str) or not query["keyword"].strip():
            raise ValueError("query keyword must be nonempty")
    targets = config.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 50:
        raise ValueError("targets requires between 1 and 50 exact identity records")
    for target in targets:
        if not isinstance(target, dict) or not target or set(target) - {"cid", "place_id", "domain"}:
            raise ValueError("target requires cid, place_id and/or domain; name matching is not supported")
        for key, value in target.items():
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"target {key} must be a nonempty trimmed string")
        if "cid" in target and not target["cid"].isdigit():
            raise ValueError("target cid must be a decimal string")
        if "domain" in target:
            host = runner.canonical_domain(target["domain"])
            if not host or not re.fullmatch(r"[a-z0-9.-]+", host) or "." not in host:
                raise ValueError("target domain must identify a hostname")
    # Validate the complete bounding square before any request can be issued.
    limit = config["max_shell"]
    for x, y in ((-limit, -limit), (-limit, limit), (limit, -limit), (limit, limit)):
        coordinates(config, x, y)
    return config


def sector(x: int, y: int) -> str:
    return SECTORS[int(((math.degrees(math.atan2(y, x)) + 22.5) % 360) // 45)]


def square(shell: int) -> list[tuple[int, int]]:
    return [(x, y) for y in range(shell, -shell - 1, -1) for x in range(-shell, shell + 1)]


def shell_points(shell: int, direction: str | None = None) -> list[tuple[int, int]]:
    return [(x, y) for x, y in square(shell) if max(abs(x), abs(y)) == shell
            and (direction is None or sector(x, y) == direction)]


def sentinel(shell: int, direction: str) -> tuple[int, int]:
    dx, dy = DIRECTIONS[SECTORS.index(direction)]
    return dx * shell, dy * shell


def observation_key(query_id: str, x: int, y: int) -> str:
    return f"{query_id}:{x}:{y}"


def request_task(config: dict, query: dict, x: int, y: int) -> dict:
    lat, lng = coordinates(config, x, y)
    return {
        "keyword": query["keyword"], "location_coordinate": f"{lat:.7f},{lng:.7f},{config['provider_zoom']}z",
        "language_code": config["language_code"], "device": config["device"],
        "depth": config["depth"], "search_places": False,
        "search_this_area": config["search_this_area"], "se_domain": config["se_domain"],
        "tag": observation_key(query["id"], x, y),
    }


def exact_match(item: dict, targets: list[dict]) -> bool:
    for target in targets:
        args = SimpleNamespace(target_name="", target_cid=target.get("cid", ""),
                               target_place_id=target.get("place_id", ""), target_domain="")
        if (args.target_cid or args.target_place_id) and runner.match_score(item, args) != 1.0:
            continue
        if "domain" in target and runner.canonical_domain(runner.item_domain(item)) != runner.canonical_domain(target["domain"]):
            continue
        return True
    return False


def blank_observation(config: dict, query: dict, x: int, y: int) -> dict:
    lat, lng = coordinates(config, x, y)
    return {"query_id": query["id"], "lat": lat, "lng": lng, "x": x, "y": y,
            "rank": None, "state": "unmeasured", "returned_count": 0, "depth": 0,
            "requested_depth": config["depth"], "observed_ranks": [], "sampled_at": None,
            "source": "unmeasured", "clean_negative": False}


def normalize_response(config: dict, query: dict, x: int, y: int,
                       payload: dict, source: str, sampled_at: str) -> dict:
    row = blank_observation(config, query, x, y)
    row.update(source=source, sampled_at=sampled_at, state="error")
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if (not isinstance(payload, dict) or payload.get("status_code") != 20000 or not isinstance(tasks, list)
            or len(tasks) != 1 or not isinstance(tasks[0], dict)):
        row["error_code"] = "invalid_provider_response"
        return row
    task = tasks[0]
    if task.get("status_code") == 40102:
        row["state"] = "empty"
        return row
    if task.get("status_code") != 20000:
        row["error_code"] = "provider_task_error"
        return row
    results = task.get("result")
    if not results:
        row["state"] = "empty"
        return row
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        row["error_code"] = "invalid_result"
        return row
    raw_items = results[0].get("items")
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list) or any(not isinstance(item, dict) for item in raw_items):
        row["error_code"] = "invalid_items"
        return row
    items = runner.organic_maps_items(raw_items)
    ranks = sorted({runner.organic_rank(item) for item in items} - {None})
    rank_set = set(ranks)
    reached = 0
    while reached + 1 in rank_set:
        reached += 1
    row.update(returned_count=len(items), observed_ranks=ranks, depth=reached)
    matches = [item for item in items if exact_match(item, config["targets"])]
    match_ranks = [runner.organic_rank(item) for item in matches]
    valid_ranks = [rank for rank in match_ranks if rank is not None]
    if valid_ranks:
        row.update(state="found", rank=min(valid_ranks))
    elif matches:
        row["error_code"] = "target_rank_missing"
    else:
        row["state"] = "not_returned" if items else "empty"
        row["clean_negative"] = (row["state"] == "not_returned"
                                 and reached >= config["negative_depth"]
                                 and len(items) >= config["negative_depth"])
    return row


def reported_cost(payload: dict) -> Decimal:
    """Provider wrapper cost is total; nested costs are a fallback, never added twice."""
    if not isinstance(payload, dict):
        raise ValueError("invalid provider cost envelope")
    values = [payload.get("cost")] if "cost" in payload else [
        task.get("cost", 0) for task in payload.get("tasks", []) if isinstance(task, dict)]
    total = Decimal(0)
    for value in values:
        if value is None:
            continue
        try:
            charge = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("invalid provider cost") from exc
        if not charge.is_finite() or charge < 0:
            raise ValueError("invalid provider cost")
        total += charge
    return total


class LiveAdapter:
    source = "dataforseo-live"
    identity = {"source": source, "endpoint": "/serp/google/maps/live/advanced"}

    def preflight(self) -> None:
        runner.dataforseo_auth_header()  # Validate presence only; never store or print it.

    def fetch(self, config: dict, query: dict, x: int, y: int) -> tuple[dict, str]:
        return runner.call_dataforseo_live_task(request_task(config, query, x, y),
                                               config["timeout_seconds"]), utc_now()


class ReplayAdapter:
    source = "synthetic-replay"

    def __init__(self, fixture: dict):
        if not isinstance(fixture, dict) or set(fixture) - {"default", "observations"}:
            raise ValueError("replay requires default and/or observations")
        if not isinstance(fixture.get("observations", {}), dict):
            raise ValueError("replay observations must be an object")
        self.fixture = copy.deepcopy(fixture)
        self.identity = {"source": self.source, "fixture_sha256": digest(fixture)}

    def preflight(self) -> None:
        pass

    def fetch(self, config: dict, query: dict, x: int, y: int) -> tuple[dict, str]:
        spec = self.fixture.get("observations", {}).get(observation_key(query["id"], x, y),
                                                       self.fixture.get("default", {"state": "error"}))
        if not isinstance(spec, dict):
            raise ValueError("replay outcome must be an object")
        timestamp = spec.get("sampled_at", "2000-01-01T00:00:00+00:00")
        if "response" in spec:
            return copy.deepcopy(spec["response"]), timestamp
        state = spec.get("state", "error")
        if state not in {"found", "not_returned", "empty", "error"}:
            raise ValueError("invalid replay state")
        count = spec.get("returned_count", config["depth"] if state in {"found", "not_returned"} else 0)
        integer(count, "replay returned_count", 0, 700)
        items = [{"type": "maps_search", "cid": "0", "place_id": "synthetic-other",
                  "domain": "unrelated.invalid", "rank_group": rank}
                 for rank in range(1, count + 1)]
        if state == "found":
            rank = spec.get("rank", 1)
            integer(rank, "replay rank", 1, count)
            items[rank - 1].update(config["targets"][0])
        task = {"status_code": 20000 if state != "error" else 50000,
                "result": [{"items": [] if state == "empty" else items}]}
        return {"status_code": 20000, "tasks": [task], "cost": spec.get("cost_usd", 0)}, timestamp


def fingerprint(config: dict, adapter_identity: dict) -> str:
    return digest({"revision": REVISION, "config": config, "adapter": adapter_identity})


def plan_summary(config: dict) -> dict:
    base_shell = (config["starting_grid"] - 1) // 2
    origin_count = ((2 * config["max_shell"] + 1) ** 2 if config["strategy"] != "sparse"
                    else config["starting_grid"] ** 2 + 8 * (config["max_shell"] - base_shell))
    per_call = runner.estimate_scan_cost(1, config["depth"], "live")
    return {"schema_version": 1, "status": "offline-plan", "config": config,
            "config_fingerprint": fingerprint(config, {"source": "plan"}),
            "base_origins": [{"x": x, "y": y, "lat": coordinates(config, x, y)[0],
                              "lng": coordinates(config, x, y)[1]} for x, y in square(base_shell)],
            "base_tasks": config["starting_grid"] ** 2 * len(config["queries"]),
            "maximum_origins": origin_count, "maximum_tasks": origin_count * len(config["queries"]),
            "max_calls": config["max_calls"], "estimated_per_call_usd": per_call,
            "maximum_estimated_cost_usd": round(origin_count * len(config["queries"]) * per_call, 9),
            "half_width_km": config["max_shell"] * config["spacing_km"],
            "corner_distance_km": math.sqrt(2) * config["max_shell"] * config["spacing_km"],
            "bounds_kind": "square", "adaptive_selection": "depends on returned observations",
            "cost_note": "Base Live estimate from existing runner; actual provider charges may differ."}


def atomic_json(path: Path, payload: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


class RunLock:
    """Fail closed on concurrent runs; stale locks need deliberate operator removal."""
    def __init__(self, directory: Path):
        self.path = directory / ".collector.lock"

    def __enter__(self):
        try:
            with self.path.open("x", encoding="utf-8") as stream:
                stream.write(str(os.getpid()))
        except FileExistsError as exc:
            raise ValueError("output directory is locked; verify no collector is running before removing .collector.lock") from exc
        return self

    def __exit__(self, *args):
        self.path.unlink()


class BudgetStop(Exception):
    pass


class Collector:
    """Single-writer state machine. Rebuilds frontier deterministically from ledger."""
    def __init__(self, config: dict, adapter: LiveAdapter | ReplayAdapter,
                 directory: Path, ceiling: float):
        self.config = validate_config(config)
        number(ceiling, "confirm-cost-usd", 0, 1_000_000)
        self.ceiling = Decimal(str(ceiling))
        self.adapter = adapter
        self.directory = Path(directory)
        self.identity = fingerprint(self.config, adapter.identity)
        self.unit_cost = Decimal(str(runner.estimate_scan_cost(1, self.config["depth"], "live")))
        self.state: dict = {}
        self.rows: dict[str, dict] = {}
        self.selected: set[tuple[int, int]] = set()
        self.sectors: dict[str, dict] = {}
        self.events: list[dict] = []
        self.base_complete = False
        self.new_calls = 0
        self.resumed_calls = 0

    def accounting(self) -> dict:
        ledger = self.state["ledger"]
        reserved = sum((Decimal(entry["reserved_usd"]) for entry in ledger.values()), Decimal(0))
        accounted = sum((max(Decimal(entry["reserved_usd"]), Decimal(entry.get("reported_usd", "0")))
                         for entry in ledger.values()), Decimal(0))
        reported = sum((Decimal(entry.get("reported_usd", "0")) for entry in ledger.values()), Decimal(0))
        return {"attempted_calls": len(ledger), "new_calls": self.new_calls,
                "resumed_calls": self.resumed_calls, "reserved_usd": float(reserved),
                "reported_usd": float(reported), "accounted_usd": float(accounted),
                "ceiling_usd": float(self.ceiling), "synthetic": self.adapter.source == "synthetic-replay"}

    def save(self) -> None:
        self.state["integrity"] = digest({k: v for k, v in self.state.items() if k != "integrity"})
        atomic_json(self.directory / "state.json", self.state)

    def load(self) -> None:
        path = self.directory / "state.json"
        if path.exists():
            self.state = json.loads(path.read_text(encoding="utf-8"))
            if self.state.get("fingerprint") != self.identity:
                raise ValueError("cache fingerprint mismatch; choose a new output directory")
            if self.state.get("integrity") != digest({k: v for k, v in self.state.items() if k != "integrity"}):
                raise ValueError("cache integrity mismatch; ledger must not be manually edited")
            if not isinstance(self.state.get("ledger"), dict):
                raise ValueError("invalid cache ledger")
            self.resumed_calls = len(self.state["ledger"])
            # An interrupted request may already have billed. Keep its full reservation.
            for entry in self.state["ledger"].values():
                if entry["status"] == "reserved":
                    entry["row"].update(state="error", error_code="interrupted_request_unknown_outcome",
                                        source=self.adapter.source)
                    entry["status"] = "uncertain"
                self.rows[entry["key"]] = entry["row"]
            selected = self.state.get("selected_origins", [[row["x"], row["y"]] for row in self.rows.values()])
            self.select([tuple(point) for point in selected])
        else:
            if any((self.directory / name).exists() for name in
                   ("manifest.json", "observations.json", "observations.jsonl")):
                raise ValueError("acquisition artifacts exist without a ledger; use a new output directory")
            self.state = {"schema_version": 1, "fingerprint": self.identity,
                          "config": self.config, "adapter": self.adapter.identity, "ledger": {}}
        self.save()

    def select(self, points: list[tuple[int, int]]) -> None:
        previous = len(self.selected)
        for x, y in points:
            self.selected.add((x, y))
            for query in self.config["queries"]:
                self.rows.setdefault(observation_key(query["id"], x, y),
                                     blank_observation(self.config, query, x, y))
        if len(self.selected) != previous:
            self.state["selected_origins"] = [list(point) for point in sorted(self.selected)]
            self.save()

    def acquire(self, points: list[tuple[int, int]], stage: str) -> None:
        self.select(points)
        for x, y in points:
            missing = [q for q in self.config["queries"]
                       if observation_key(q["id"], x, y) not in self.state["ledger"]]
            if not missing:
                continue
            accounting = self.accounting()
            if (accounting["attempted_calls"] + len(missing) > self.config["max_calls"]
                    or Decimal(str(accounting["accounted_usd"])) + self.unit_cost * len(missing) > self.ceiling):
                raise BudgetStop("whole_origin_budget_exhausted")
            for query in missing:
                # Recheck after each response: unexpectedly high actual charges halt immediately.
                if Decimal(str(self.accounting()["accounted_usd"])) + self.unit_cost > self.ceiling:
                    raise BudgetStop("reported_charge_budget_exhausted")
                key = observation_key(query["id"], x, y)
                entry = {"key": key, "request_fingerprint": digest({"run": self.identity,
                         "task": request_task(self.config, query, x, y)}), "stage": stage,
                         "reserved_usd": str(self.unit_cost), "reported_usd": "0",
                         "status": "reserved", "row": self.rows[key]}
                provenance = {"request_fingerprint": entry["request_fingerprint"],
                              "response_sha256": None, "response_retained": False,
                              "canonicalization": "json-sort-keys-compact-ascii-v1"}
                entry["row"]["provenance"] = provenance
                self.state["ledger"][key] = entry
                self.new_calls += 1
                self.save()  # Durable reservation MUST precede the billable side effect.
                cost_unknown = False
                try:
                    payload, sampled_at = self.adapter.fetch(self.config, query, x, y)
                    # Hash the complete original response without retaining arbitrary
                    # provider fields, callback URLs, tags, or possible secrets.
                    provenance["response_sha256"] = digest(payload)
                    entry["response_sha256"] = provenance["response_sha256"]
                    self.save()
                    try:
                        entry["reported_usd"] = str(reported_cost(payload))
                    except (ValueError, TypeError):
                        cost_unknown = True
                        entry["cost_unknown"] = True
                        raise ValueError("invalid reported charge")
                    row = normalize_response(self.config, query, x, y, payload, self.adapter.source, sampled_at)
                except Exception as exc:
                    # Never persist provider exception text (may contain request/auth details).
                    row = blank_observation(self.config, query, x, y)
                    row.update(state="error", sampled_at=utc_now(), source=self.adapter.source,
                               error_code=type(exc).__name__)
                row["provenance"] = provenance
                entry.update(status="complete", row=row)
                self.rows[key] = row
                self.save()
                if cost_unknown:
                    raise BudgetStop("unknown_reported_charge")
                if Decimal(str(self.accounting()["accounted_usd"])) > self.ceiling:
                    raise BudgetStop("reported_charge_exceeds_ceiling")

    def evaluate(self, points: list[tuple[int, int]]) -> dict:
        rows = [self.rows.get(observation_key(q["id"], x, y))
                for x, y in points for q in self.config["queries"]]
        complete = bool(rows) and all(row and row["state"] != "unmeasured" for row in rows)
        positive = any(row and row["state"] == "found" for row in rows)
        clean = complete and all(row["clean_negative"] for row in rows)
        return {"complete": complete, "positive": positive, "clean_negative": clean,
                "inconclusive": any(not row or row["state"] in {"empty", "error", "unmeasured"}
                                     or (row["state"] == "not_returned" and not row["clean_negative"])
                                     for row in rows)}

    def update_layer(self, direction: str, shell: int) -> None:
        evaluation = self.evaluate(shell_points(shell, direction))
        state = self.sectors[direction]
        state["last_full_shell"] = shell
        if evaluation["inconclusive"]:
            state.update(state="unresolved", clean_layers=0)
        elif evaluation["positive"]:
            state.update(state="active", clean_layers=0)
        elif evaluation["clean_negative"]:
            state["clean_layers"] += 1
            state["state"] = "pending_sentinel" if state["clean_layers"] >= 2 else "active"
        else:
            state.update(state="unresolved", clean_layers=0)

    def frontier(self) -> str:
        config = self.config
        base_shell = (config["starting_grid"] - 1) // 2
        self.acquire(square(base_shell), "common_base")
        self.base_complete = self.evaluate(square(base_shell))["complete"]
        self.sectors = {direction: {"state": "active", "clean_layers": 0,
                                    "last_full_shell": None, "sentinel_shell": None}
                        for direction in SECTORS}
        if config["strategy"] == "adaptive8sectors" and base_shell > 0:
            for direction in SECTORS:
                self.update_layer(direction, base_shell)
        for shell in range(base_shell + 1, config["max_shell"] + 1):
            if config["strategy"] == "dense":
                self.acquire(shell_points(shell), "dense_layer")
                continue
            if config["strategy"] == "sparse":
                self.acquire([sentinel(shell, direction) for direction in SECTORS], "sparse_rays")
                continue
            for direction in SECTORS:
                state = self.sectors[direction]
                if state["state"] == "active":
                    self.acquire(shell_points(shell, direction), "sector_layer")
                    self.update_layer(direction, shell)
                elif state["state"] == "pending_sentinel":
                    probe = [sentinel(shell, direction)]
                    self.acquire(probe, "sentinel")
                    state["sentinel_shell"] = shell
                    evaluation = self.evaluate(probe)
                    if evaluation["positive"]:
                        self.events.append({"event": "positive_sentinel_reactivation",
                                            "sector": direction, "shell": shell})
                        state.update(state="active", clean_layers=0)
                        self.acquire(shell_points(shell, direction), "sentinel_backfill")
                        self.update_layer(direction, shell)
                    elif evaluation["clean_negative"]:
                        state["state"] = "sampled_stop"
                    else:
                        state["state"] = "unresolved_sentinel"
        for state in self.sectors.values():
            if config["strategy"] != "adaptive8sectors":
                state["state"] = "sampled_bounds" if config["strategy"] == "sparse" else "bounds_reached"
            elif state["state"] in {"active", "pending_sentinel"}:
                state["state"] = "bounds_reached"
        if any(row["state"] in {"error", "empty", "unmeasured"} or
               (row["state"] == "not_returned" and not row["clean_negative"]) for row in self.rows.values()):
            return "unresolved"
        if all(state["state"] == "sampled_stop" for state in self.sectors.values()):
            return "sampled_stop"
        return "sampled_bounds" if config["strategy"] == "sparse" else "bounds_reached"

    def write_outputs(self, status: str, reason: str | None) -> dict:
        rows = sorted(self.rows.values(), key=lambda row: (-row["y"], row["x"], row["query_id"]))
        manifest = {"schema_version": 1, "fingerprint": self.identity, "status": status,
                    "reason": reason, "config": self.config, "source": self.adapter.source,
                    "complete_common_base": self.base_complete,
                    "selected_origins": len(self.selected), "observations": len(rows),
                    "complete_selected_origins": sum(all(self.rows[observation_key(q["id"], x, y)]["state"]
                                                          != "unmeasured" for q in self.config["queries"])
                                                     for x, y in self.selected),
                    "state_counts": {state: sum(row["state"] == state for row in rows)
                                     for state in ("found", "not_returned", "error", "empty", "unmeasured")},
                    "accounting": self.accounting(), "sectors": self.sectors, "events": self.events,
                    "coverage_claim": "Sampled observations only; no assertion of absence between or beyond origins.",
                    "provenance_policy": "Per-task SHA-256 of canonical complete provider response; raw responses not retained.",
                    "rank_basis": runner.RANK_BASIS}
        atomic_json(self.directory / "observations.json", rows)
        jsonl = self.directory / "observations.jsonl"
        temp = jsonl.with_suffix(".jsonl.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, jsonl)
        atomic_json(self.directory / "manifest.json", manifest)
        return manifest

    def run(self) -> dict:
        self.directory.mkdir(parents=True, exist_ok=True)
        with RunLock(self.directory):
            self.load()
            atomic_json(self.directory / "plan.json", plan_summary(self.config))
            self.adapter.preflight()
            status, reason = "interrupted", None
            try:
                if Decimal(str(self.accounting()["accounted_usd"])) > self.ceiling:
                    raise BudgetStop("prior_spend_exceeds_ceiling")
                if any(entry.get("cost_unknown") for entry in self.state["ledger"].values()):
                    raise BudgetStop("unknown_reported_charge")
                status = self.frontier()
            except BudgetStop as exc:
                status, reason = "budget_stop", str(exc)
            finally:
                manifest = self.write_outputs(status, reason)
            return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="offline plan (default)")
    mode.add_argument("--replay", type=Path, help="offline synthetic provider fixture")
    mode.add_argument("--execute", action="store_true", help="explicit paid Live acquisition")
    parser.add_argument("--confirm-cost-usd", type=float, help="cumulative run ceiling; required for Live")
    parser.add_argument("--output-dir", type=Path, default=Path("runs/adaptive"))
    parser.add_argument("--diagnostic", action="store_true", help="Explicit expert-directed adaptive experiment, not an automatically researched study")
    args = parser.parse_args(argv)
    try:
        if args.execute and not args.diagnostic:
            raise ValueError("Adaptive expert execution requires --diagnostic; default researched baselines use tools/study.py")
        config = validate_config(json.loads(args.config.read_text(encoding="utf-8-sig")))
        if args.confirm_cost_usd is not None:
            number(args.confirm_cost_usd, "confirm-cost-usd", 0, 1_000_000)
        if args.execute and args.confirm_cost_usd is None:
            raise ValueError("--execute requires --confirm-cost-usd")
        if not args.execute and args.replay is None:
            plan = plan_summary(config)
            args.output_dir.mkdir(parents=True, exist_ok=True)
            with RunLock(args.output_dir):
                atomic_json(args.output_dir / "plan.json", plan)
            print(json.dumps(plan, indent=2))
            return 0
        adapter = (ReplayAdapter(json.loads(args.replay.read_text(encoding="utf-8-sig")))
                   if args.replay else LiveAdapter())
        ceiling = args.confirm_cost_usd
        if ceiling is None:  # Synthetic-only convenience; still exercises accounting.
            ceiling = plan_summary(config)["maximum_estimated_cost_usd"]
        manifest = Collector(config, adapter, args.output_dir, ceiling).run()
        print(json.dumps(manifest, indent=2))
        return 2 if manifest["status"] in {"budget_stop", "unresolved", "interrupted"} else 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Collector refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
