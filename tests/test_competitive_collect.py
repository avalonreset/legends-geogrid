"""Tests for lean safe collector (competitive_collect.py).

Verifies offline preflight estimation, spending budget barriers,
idempotent runs without repurchasing, ambiguous failure stoppage,
plan mismatch detection, source study plan lineage validation,
and battlefield.py compatibility.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import battlefield
from competitive_export import export_study
from competitive_collect import adapt_plan, collect, make_task_payload, fingerprint_task, compute_cost
from study_contract import digest


def make_sample_plan(root: Path) -> tuple[Path, dict]:
    plan = {
        "schema": "legends-geogrid-competitive-plan/v1",
        "collection_policy": {"intent": "viewport", "rationale": "Explicit restricted-window transport fixture."},
        "target_business": {
            "faction_id": "TARGET", "location_status": "verified",
            "name": "Apex Climate Control",
            "cid": "999000111",
            "domain": "apexclimate.example.com",
            "lat": 38.6442,
            "lng": -121.2678,
            "location_label": "Austin, TX",
        },
        "rival_factions_roster": [{
            "faction_id": "F01", "name": "Rival Fortress Inc", "cid": "888000222",
            "lat": 38.6492, "lng": -121.2628, "location_status": "verified",
        }],
        "query_selection": [
            {"query": "hvac contractor", "query_id": "q1", "label": "HVAC Contractor", "narrative": "Primary core"},
            {"query": "ac repair", "query_id": "q2", "label": "AC Repair", "narrative": "Secondary service"},
        ],
        "measurement_settings": {
            "depth": 20,
            "zoom": 14,
            "device": "desktop",
            "language_code": "en",
            "se_domain": "google.com",
            "search_this_area": True,
            "method": "live",
        },
        "origins": [
            {"tag": "csp_001", "origin_id": "csp_001", "lat": 38.6442, "lng": -121.2678, "phase": 1, "roles": ["target_citadel"]},
            {"tag": "csp_002", "origin_id": "csp_002", "lat": 38.6500, "lng": -121.2600, "phase": 1, "roles": ["corridor_midpoint"]},
            {"tag": "csp_003", "origin_id": "csp_003", "lat": 38.6600, "lng": -121.2500, "phase": 2, "roles": ["outward_sentinel"]},
        ],
    }
    path = root / "competitive-plan.json"
    path.write_text(json.dumps(plan, indent=2))
    return path, plan


def make_mock_serp_response(keyword: str, tag: str, center_lat: float, center_lng: float) -> dict:
    return {
        "status_code": 20000,
        "status_message": "Ok.",
        "cost": 0.002,
        "tasks_count": 1,
        "tasks": [
            {
                "status_code": 20000,
                "status_message": "Ok.",
                "cost": 0.002,
                "data": {"tag": tag, "keyword": keyword},
                "result": [
                    {
                        "datetime": "2026-10-18 12:00:00 +00:00",
                        "items": [
                            {
                                "type": "maps_search",
                                "rank_group": 1,
                                "rank_absolute": 1,
                                "title": "Apex Climate Control",
                                "category": "HVAC contractor",
                                "domain": "apexclimate.example.com",
                                "cid": "999000111",
                                "latitude": center_lat,
                                "longitude": center_lng,
                                "rating": {"value": 4.9, "votes_count": 220},
                            },
                            {
                                "type": "maps_search",
                                "rank_group": 2,
                                "rank_absolute": 2,
                                "title": "Rival Fortress Inc",
                                "category": "HVAC contractor",
                                "domain": "rivalfortress.example.com",
                                "cid": "888000222",
                                "latitude": center_lat + 0.005,
                                "longitude": center_lng + 0.005,
                                "rating": {"value": 4.7, "votes_count": 190},
                            },
                        ],
                    }
                ],
            }
        ],
    }


class CompetitiveCollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan_path, self.plan = make_sample_plan(self.root)
        self.out_dir = self.root / "study_run"
        self.lineage_path = self.root / "source-study.json"
        self.lineage_path.write_text("{}")
        self.plan["source_study_plan"] = str(self.lineage_path)
        self.plan_path.write_text(json.dumps(self.plan, indent=2))
        self.validation = patch("competitive_collect.validate_study_plan", return_value=(
            {"business": self.plan["target_business"],
             "queries": [dict(q, selected=True) for q in self.plan["query_selection"]]},
            {"plan_sha256": digest(self.lineage_path)},
        ))
        self.validation.start()
        self.addCleanup(self.validation.stop)

    def test_offline_estimate_preflight_zero_calls(self):
        fake_api = MagicMock()
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = fake_api

        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            res = collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=False)

        self.assertEqual(res["status"], "estimate_only")
        self.assertEqual(res["total_origins"], 3)
        self.assertEqual(res["lanes_count"], 2)
        self.assertEqual(res["total_tasks"], 6)
        self.assertEqual(res["new_tasks"], 6)
        self.assertEqual(res["reused_tasks"], 0)
        self.assertAlmostEqual(res["estimated_cost_usd"], 0.012, places=4)
        self.assertFalse(self.out_dir.exists())
        fake_api.assert_not_called()

    def test_strict_preflight_budget_ceiling(self):
        fake_api = MagicMock()
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = fake_api

        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            with self.assertRaisesRegex(ValueError, "exceeds confirmed budget"):
                collect(allow_live=True, 
                    plan_path=self.plan_path,
                    output_dir=self.out_dir,
                    execute=True,
                    confirm_cost_usd=0.005,  # Below needed $0.012
                )
        fake_api.assert_not_called()
        self.assertFalse(self.out_dir.exists())

    def test_successful_execute_and_battlefield_compatibility(self):
        def fake_request(endpoint, payload, **kwargs):
            task = payload[0]
            return make_mock_serp_response(
                task["keyword"], task["tag"], self.plan["target_business"]["lat"], self.plan["target_business"]["lng"]
            )

        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=fake_request)

        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            res = collect(allow_live=True, 
                plan_path=self.plan_path,
                output_dir=self.out_dir,
                execute=True,
                confirm_cost_usd=0.50,
            )

        self.assertEqual(res["status"], "collected")
        self.assertEqual(res["total_tasks"], 6)
        self.assertEqual(res["new_tasks"], 6)
        self.assertEqual(fake_mod.api_request.call_count, 6)

        # Output artifacts
        report_cfg_file = self.out_dir / "report-config.json"
        self.assertTrue(report_cfg_file.is_file())
        lane1_parsed = self.out_dir / "lane-1" / "parsed-grid.json"
        lane1_raw = self.out_dir / "lane-1" / "dataforseo-response.raw.json"
        self.assertTrue(lane1_parsed.is_file())
        self.assertTrue(lane1_raw.is_file())

        parsed_data = json.loads(lane1_parsed.read_text(encoding="utf-8"))
        self.assertEqual(parsed_data["target"], "Apex Climate Control")
        self.assertEqual(len(parsed_data["results"]), 3)
        self.assertEqual(parsed_data["results"][0]["rank"], 1)
        exported = export_study(self.out_dir)
        self.assertEqual(exported["schema"], "geogrid-companion/v1")
        self.assertEqual(len(exported["points"]), 3)
        self.assertEqual(exported["evidence"]["observations_with_timestamp"], 6)
        observed = exported["points"][0]["by_lane"]["q1"]
        self.assertEqual(observed["top_items"][1]["faction_id"], "F01")
        self.assertEqual(observed["top_items"][1]["votes_count"], 190)
        self.assertIsInstance(observed["top_items"][1]["latitude"], float)
        self.assertIsInstance(observed["top_items"][1]["longitude"], float)
        self.assertEqual(observed["sampled_at"], "2026-10-18T12:00:00+00:00")

        # Battlefield compatibility verification
        bundle = battlefield.load_study_lanes(self.out_dir)
        self.assertEqual(len(bundle.lanes), 2)
        self.assertEqual(bundle.business["name"], "Apex Climate Control")
        self.assertEqual(bundle.business["cid"], "999000111")

        model = battlefield.build_battlefield_model(self.out_dir)
        self.assertIn("Apex Climate Control", model["target"]["name"])
        self.assertTrue(len(model["factions"]) >= 2)

    def test_regular_grid_survives_collection_export_and_free_resume(self):
        from lattice_sampling import lattice_plan
        self.plan = lattice_plan(self.plan, size=3, spacing_km=1, method="live")
        self.plan_path.write_text(json.dumps(self.plan))
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=lambda endpoint, payload, **kw:
            make_mock_serp_response(payload[0]["keyword"], payload[0]["tag"], 38.6442, -121.2678))
        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=.1)
            fake_mod.api_request.reset_mock()
            receipt = collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=0)
            fake_mod.api_request.assert_not_called()
        self.assertEqual(receipt["reused_tasks"], 18)
        parsed = json.loads((self.out_dir / "lane-1" / "parsed-grid.json").read_text())
        self.assertEqual(parsed["measurement_settings"]["grid_size"], 3)
        self.assertEqual(parsed["measurement_settings"]["geometry"], "square_grid")
        self.assertEqual({(r["point"]["row"], r["point"]["col"]) for r in parsed["results"]},
                         {(r, c) for r in range(3) for c in range(3)})
        exported = export_study(self.out_dir)
        self.assertEqual(exported["study"]["geometry"], "square_grid")
        self.assertEqual(exported["study"]["sampling"]["spacing_km"], 1)
        self.assertEqual(len(exported["points"]), 9)

    def test_repeated_run_no_repurchase(self):
        def fake_request(endpoint, payload, **kwargs):
            task = payload[0]
            return make_mock_serp_response(
                task["keyword"], task["tag"], self.plan["target_business"]["lat"], self.plan["target_business"]["lng"]
            )

        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=fake_request)

        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            # First execution
            res1 = collect(allow_live=True, 
                plan_path=self.plan_path,
                output_dir=self.out_dir,
                execute=True,
                confirm_cost_usd=0.50,
            )
            self.assertEqual(res1["new_tasks"], 6)
            self.assertEqual(fake_mod.api_request.call_count, 6)

            # Reset call count
            fake_mod.api_request.reset_mock()

            # Second execution on same completed directory: zero new calls, $0 budget needed
            res2 = collect(allow_live=True, 
                plan_path=self.plan_path,
                output_dir=self.out_dir,
                execute=True,
                confirm_cost_usd=0.0,
            )
            self.assertEqual(res2["new_tasks"], 0)
            self.assertEqual(res2["reused_tasks"], 6)
            self.assertEqual(res2["actual_cost_usd"], 0.0)
            fake_mod.api_request.assert_not_called()

    def test_ambiguous_stop_never_retried(self):
        # Create output dir with a dangling reservation (reserve event without response event)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        ledger = self.out_dir / "collection-ledger.jsonl"
        fake_task = make_task_payload("hvac contractor", self.plan["origins"][0], self.plan["measurement_settings"])
        fp = fingerprint_task(fake_task)

        # Write reserve event ONLY
        ledger.write_text(json.dumps({
            "event": "reserve",
            "request_sha256": fp,
            "tag": "csp_001",
            "reserved_usd": 0.002,
            "observed_at": "2026-10-18T12:00:00+00:00",
        }) + "\n", encoding="utf-8")

        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock()

        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            with self.assertRaisesRegex(ValueError, "Ambiguous uncompleted reservation detected"):
                collect(allow_live=True, 
                    plan_path=self.plan_path,
                    output_dir=self.out_dir,
                    execute=True,
                    confirm_cost_usd=0.50,
                )
        fake_mod.api_request.assert_not_called()

    def test_plan_mismatch_fails(self):
        # First execution
        def fake_request(endpoint, payload, **kwargs):
            task = payload[0]
            return make_mock_serp_response(
                task["keyword"], task["tag"], self.plan["target_business"]["lat"], self.plan["target_business"]["lng"]
            )

        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=fake_request)

        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            collect(allow_live=True, 
                plan_path=self.plan_path,
                output_dir=self.out_dir,
                execute=True,
                confirm_cost_usd=0.50,
            )

            # Modify plan file
            self.plan["target_business"]["name"] = "Tampered Business Name"
            self.plan_path.write_text(json.dumps(self.plan, indent=2))

            with self.assertRaisesRegex(ValueError, "Plan content mismatch"):
                collect(allow_live=True, 
                    plan_path=self.plan_path,
                    output_dir=self.out_dir,
                    execute=True,
                    confirm_cost_usd=0.50,
                )

    def test_flexible_adapter_supports_both_schemas(self):
        # 1. competitive_sampling format
        adapted1 = adapt_plan(self.plan)
        self.assertEqual(adapted1["business"]["name"], "Apex Climate Control")
        self.assertEqual(len(adapted1["queries"]), 2)
        self.assertEqual(len(adapted1["origins"]), 3)

        # 2. explicit contract format
        contract_doc = {
            "business": {
                "name": "Apex Climate Control",
                "cid": "999000111",
                "domain": "apexclimate.example.com",
                "lat": 38.6442,
                "lng": -121.2678,
            },
            "queries": [
                {"query_id": "lane_1", "query": "hvac contractor"},
                {"query_id": "lane_2", "query": "ac repair"},
            ],
            "settings": {
                "depth": 20,
                "zoom": 14,
                "device": "desktop",
                "language_code": "en",
                "se_domain": "google.com",
                "search_this_area": True,
            },
            "origins": [
                {"tag": "pt_1", "lat": 38.6442, "lng": -121.2678},
                {"tag": "pt_2", "lat": 38.6500, "lng": -121.2600},
            ],
        }
        adapted2 = adapt_plan(contract_doc)
        self.assertEqual(adapted2["business"]["name"], "Apex Climate Control")
        self.assertEqual(len(adapted2["queries"]), 2)
        self.assertEqual(len(adapted2["origins"]), 2)
        self.assertEqual(adapted2["origins"][0]["tag"], "pt_1")

    def test_phase_filter(self):
        adapted_p1 = adapt_plan(self.plan, phase_filter=1)
        self.assertEqual(len(adapted_p1["origins"]), 2)

        adapted_p2 = adapt_plan(self.plan, phase_filter=2)
        self.assertEqual(len(adapted_p2["origins"]), 1)

        with self.assertRaisesRegex(ValueError, "No origins matching phase"):
            adapt_plan(self.plan, phase_filter=99)

    def test_source_study_plan_lineage_validation(self):
        self.validation.stop()
        # Build valid study plan fixture
        ev_dir = self.root / "evidence"
        ev_dir.mkdir(parents=True, exist_ok=True)
        sources = []
        def src(sid, kind, val):
            p = ev_dir / f"{sid}.json"
            p.write_text(json.dumps(val))
            sources.append({
                "id": sid, "kind": kind, "file": f"{sid}.json",
                "sha256": digest(p),
                "observed_at": "2026-10-18T10:00:00+00:00",
                "url": f"https://example.org/{sid}",
            })
        def env(data, item):
            return {"status_code": 20000, "tasks": [{"status_code": 20000, "data": data, "result": [{"items": [item]}]}]}

        src("site", "website", {"text": "Apex Climate Control, 100 Main St, Austin, TX. HVAC contractor and ac repair."})
        src("gbp", "gbp", env({}, {
            "cid": "999000111", "latitude": 38.6442, "longitude": -121.2678,
            "url": "https://apexclimate.example.com/", "title": "Apex Climate Control", "category": "HVAC contractor",
        }))
        src("demand", "demand", env({"keywords": ["hvac contractor", "ac repair"]}, {"keyword": "hvac contractor"}))
        for i, lat in enumerate([38.6442, 38.6500, 38.6600]):
            src(f"pilot_hvac_{i}", "maps_probe", env(
                {"keyword": "hvac contractor", "location_coordinate": f"{lat},-121.2678,14z", "language_code": "en", "device": "desktop", "search_this_area": True, "depth": 20},
                {"title": "Apex Climate Control", "category": "HVAC contractor"}
            ))
            src(f"pilot_ac_{i}", "maps_probe", env(
                {"keyword": "ac repair", "location_coordinate": f"{lat},-121.2678,14z", "language_code": "en", "device": "desktop", "search_this_area": True, "depth": 20},
                {"title": "Apex Climate Control", "category": "HVAC contractor"}
            ))

        ref = lambda sid, p, q: {"source_id": sid, "pointer": p, "quote": q}
        sp_doc = {
            "schema": "geogrid-study/v1",
            "business": {
                "name": "Apex Climate Control", "cid": "999000111", "domain": "apexclimate.example.com",
                "location_label": "Austin, TX", "lat": 38.6442, "lng": -121.2678,
            },
            "sources": sources,
            "identity": {
                "source_id": "gbp", "pointer": "/tasks/0/result/0/items/0",
                "website_reference": ref("site", "/text", "100 Main St"),
                "reconciliation": "Business name and address agree.",
            },
            "settings": {
                "method": "standard", "grid_size": 3, "radius_km": 2.0, "depth": 20, "zoom": 14,
                "device": "desktop", "search_this_area": True, "language_code": "en", "se_domain": "google.com",
                "geography_reason": "Local service area.", "decision": "Study HVAC contractor visibility.",
            },
            "queries": [
                {
                    "query": "hvac contractor", "selected": True, "role": "category",
                    "reason": "Core category search.", "offering_evidence": [ref("site", "/text", "HVAC contractor")],
                    "demand_source": "demand", "demand_scope": "Metro demand.", "intent_assessment": "Returns HVAC competitors.",
                    "limitations": "Advisory demand.", "pilot_sources": ["pilot_hvac_0", "pilot_hvac_1", "pilot_hvac_2"],
                    "intent_evidence": [ref("pilot_hvac_0", "/tasks/0/result/0/items/0/category", "HVAC contractor")],
                    "theme": {"id": "category", "label": "HVAC Category", "customer_need": "Find HVAC contractor", "distinct_value": "Primary category"},
                },
                {
                    "query": "ac repair", "selected": True, "role": "service",
                    "reason": "Core service search.", "offering_evidence": [ref("site", "/text", "ac repair")],
                    "demand_source": "demand", "demand_scope": "Metro demand.", "intent_assessment": "Returns AC repair.",
                    "limitations": "Advisory demand.", "pilot_sources": ["pilot_ac_0", "pilot_ac_1", "pilot_ac_2"],
                    "intent_evidence": [ref("pilot_ac_0", "/tasks/0/result/0/items/0/category", "HVAC contractor")],
                    "theme": {"id": "service", "label": "AC Repair", "customer_need": "Emergency AC repair", "distinct_value": "Seasonal service"},
                },
            ],
            "selection": {
                "coverage_summary": "Focused category and service lanes.",
                "evidence": [ref("site", "/text", "HVAC contractor"), ref("gbp", "/tasks/0/result/0/items/0/category", "HVAC contractor")],
                "fewer_themes": {"reason": "Two high-demand customer themes.", "evidence": [ref("site", "/text", "HVAC contractor")]},
            },
        }
        sp_file = ev_dir / "study-plan.json"
        sp_file.write_text(json.dumps(sp_doc, indent=2))

        # 1. Successful validation when linked
        res = collect(allow_live=True, 
            plan_path=self.plan_path,
            output_dir=self.out_dir,
            execute=False,
            study_plan_path=sp_file,
        )
        self.assertTrue(res["study_plan_validated"])

        # 2. Mismatched query rejected
        bad_plan = dict(self.plan)
        bad_plan["query_selection"] = [{"query": "unresearched keyword", "query_id": "q1"}]
        bad_path = self.root / "bad-plan.json"
        bad_path.write_text(json.dumps(bad_plan))

        with self.assertRaisesRegex(ValueError, "not found among selected queries"):
            collect(allow_live=True, 
                plan_path=bad_path,
                output_dir=self.out_dir,
                execute=False,
                study_plan_path=sp_file,
            )

        # 3. Mismatched business name rejected
        bad_plan2 = dict(self.plan)
        bad_plan2["target_business"] = dict(bad_plan2["target_business"], name="Different Business Name")
        bad_path2 = self.root / "bad-plan2.json"
        bad_path2.write_text(json.dumps(bad_plan2))

        with self.assertRaisesRegex(ValueError, "Business mismatch"):
            collect(allow_live=True, 
                plan_path=bad_path2,
                output_dir=self.out_dir,
                execute=False,
                study_plan_path=sp_file,
            )

    def test_cli_main_estimate_and_execute(self):
        from competitive_collect import main
        # Estimate mode via CLI
        out_buf = []
        with patch("sys.stdout.write", side_effect=out_buf.append):
            code = main(["--plan", str(self.plan_path), "--output-dir", str(self.out_dir)])
        self.assertEqual(code, 0)
        output_json = json.loads("".join(out_buf))
        self.assertEqual(output_json["status"], "estimate_only")

        # Execute mode via CLI
        def fake_request(endpoint, payload, **kwargs):
            task = payload[0]
            return make_mock_serp_response(
                task["keyword"], task["tag"], self.plan["target_business"]["lat"], self.plan["target_business"]["lng"]
            )
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=fake_request)

        out_buf_exec = []
        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            with patch("sys.stdout.write", side_effect=out_buf_exec.append):
                code2 = main([
                    "--plan", str(self.plan_path),
                    "--output-dir", str(self.out_dir),
                    "--execute", "--allow-live",
                    "--confirm-cost-usd", "0.50",
                ])
        self.assertEqual(code2, 0)
        output_json2 = json.loads("".join(out_buf_exec))
        self.assertEqual(output_json2["status"], "collected")

    def test_nonfinite_budget_and_coordinates_never_dispatch(self):
        for value in (float("nan"), float("inf"), -1):
            with self.assertRaisesRegex(ValueError, "Budget"):
                collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=value)
        self.plan["origins"][0]["lat"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Coordinates"):
            adapt_plan(self.plan)

    def test_execute_requires_lineage(self):
        self.plan.pop("source_study_plan")
        self.plan_path.write_text(json.dumps(self.plan))
        with self.assertRaisesRegex(ValueError, "validated source"):
            collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=1)

    def test_failure_drains_batch_and_resume_does_not_repurchase(self):
        def fail_one(endpoint, payload, **kwargs):
            task = payload[0]
            if task["tag"] == "csp_001":
                raise TimeoutError("ambiguous provider timeout")
            return make_mock_serp_response(task["keyword"], task["tag"], 38.6442, -121.2678)
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=fail_one)
        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            with self.assertRaisesRegex(ValueError, "response incomplete"):
                collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=1)
            self.assertEqual(fake_mod.api_request.call_count, 3)
            events = [json.loads(line) for line in (self.out_dir / "collection-ledger.jsonl").read_text().splitlines()]
            self.assertEqual(sum(e["event"] == "response" for e in events), 2)
            with self.assertRaisesRegex(ValueError, "Ambiguous"):
                collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=1)
            self.assertEqual(fake_mod.api_request.call_count, 3)

    def test_provider_cost_overrun_stops_before_next_batch(self):
        def expensive(endpoint, payload, **kwargs):
            task = payload[0]
            response = make_mock_serp_response(task["keyword"], task["tag"], 38.6442, -121.2678)
            response["cost"] = 0.02
            return response
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=expensive)
        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            with self.assertRaisesRegex(ValueError, "exceeded estimate"):
                collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=.012, max_workers=1)
            self.assertEqual(fake_mod.api_request.call_count, 1)

    def test_provider_failure_saved_and_not_retried(self):
        def denied(endpoint, payload, **kwargs):
            task = payload[0]
            response = make_mock_serp_response(task["keyword"], task["tag"], 38.6442, -121.2678)
            response["tasks"][0]["status_code"] = 40200
            return response
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=denied)
        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            with self.assertRaisesRegex(ValueError, "Provider status"):
                collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=1, max_workers=1)
            with self.assertRaisesRegex(ValueError, "Saved provider failure"):
                collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=1)
            self.assertEqual(fake_mod.api_request.call_count, 1)

    def test_all_requested_organic_results_survive_export(self):
        def full_results(endpoint, payload, **kwargs):
            task = payload[0]
            response = make_mock_serp_response(task["keyword"], task["tag"], 38.6442, -121.2678)
            response["tasks"][0]["result"][0]["items"].extend(
                {"type": "maps_search", "rank_group": n, "rank_absolute": n + 2,
                 "title": f"Business {n}", "cid": str(n)} for n in range(3, 21)
            )
            return response
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=full_results)
        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=1)
        model = export_study(self.out_dir)
        self.assertEqual(len(model["points"][0]["by_lane"]["q1"]["top_items"]), 20)
        emerging = [f for f in model["factions"] if f.get("discovered")]
        self.assertEqual([f["cid"] for f in emerging], [str(n) for n in range(3, 11)])
        self.assertEqual(len(model["factions"]), 10)
        self.assertEqual(model["evidence"]["emerging_rivals"], 8)
        self.assertTrue(model["evidence"]["shortlist_complete"])
        self.assertEqual(model["factions"][1]["selection"]["visibility_score"], 6 * 19)
        self.assertEqual(model["points"][0]["by_lane"]["q1"]["top_items"][2]["faction_id"], "cid:3")
        self.assertIsNone(model["points"][0]["by_lane"]["q1"]["top_items"][10]["faction_id"])

    def test_shortlist_filters_categories_without_discarding_results(self):
        self.plan["competitor_policy"] = {"eligible_category_pattern": "(?i)hvac|heating"}
        self.plan_path.write_text(json.dumps(self.plan))
        def results(endpoint, payload, **kwargs):
            task = payload[0]
            response = make_mock_serp_response(task["keyword"], task["tag"], 38.6442, -121.2678)
            response["tasks"][0]["result"][0]["items"].extend([
                {"type": "maps_search", "rank_group": 3, "title": "Retail Store", "cid": "3", "category": "Hardware store"},
                {"type": "maps_search", "rank_group": 4, "title": "Heating Rival", "cid": "4", "category": "Heating contractor"},
            ])
            return response
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=results)
        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=1)
        model = export_study(self.out_dir)
        self.assertEqual([f["cid"] for f in model["factions"]], ["999000111", "888000222", "4"])
        self.assertFalse(model["evidence"]["shortlist_complete"])
        self.assertEqual(len(model["points"][0]["by_lane"]["q1"]["top_items"]), 4)

    def test_same_name_and_domain_at_distinct_profiles_keep_separate_slots(self):
        def results(endpoint, payload, **kwargs):
            task = payload[0]
            response = make_mock_serp_response(task["keyword"], task["tag"], 38.6442, -121.2678)
            items = response["tasks"][0]["result"][0]["items"]
            branch = dict(items[1], cid="333", rank_group=3, rank_absolute=3)
            items.append(branch)
            return response
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=results)
        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            collect(allow_live=True, plan_path=self.plan_path, output_dir=self.out_dir, execute=True, confirm_cost_usd=1)
        model = export_study(self.out_dir)
        self.assertEqual(len(model["factions"]), 3)
        rival = model["factions"][1]
        self.assertEqual(rival["cid"], "888000222")
        self.assertEqual(rival["selection"]["visibility_score"], 6 * 19)
        self.assertEqual(rival["selection"]["appearances"], 6)
        self.assertEqual(model["factions"][2]["cid"], "333")
        self.assertEqual(model["factions"][2]["selection"]["visibility_score"], 6 * 18)
        self.assertEqual(model["points"][0]["by_lane"]["q1"]["top_items"][2]["faction_id"], "cid:333")

    def test_concurrent_workers_reservation_before_dispatch(self):
        # Verify bounded chunk of 6 workers writes all reservations prior to responses
        def fake_request(endpoint, payload, **kwargs):
            task = payload[0]
            return make_mock_serp_response(
                task["keyword"], task["tag"], self.plan["target_business"]["lat"], self.plan["target_business"]["lng"]
            )
        fake_mod = types.ModuleType("legends_dataforseo")
        fake_mod.api_request = MagicMock(side_effect=fake_request)

        with patch.dict(sys.modules, legends_dataforseo=fake_mod):
            res = collect(allow_live=True, 
                plan_path=self.plan_path,
                output_dir=self.out_dir,
                execute=True,
                confirm_cost_usd=0.50,
                max_workers=6,
            )

        self.assertEqual(res["status"], "collected")
        ledger_file = self.out_dir / "collection-ledger.jsonl"
        lines = [json.loads(line) for line in ledger_file.read_text(encoding="utf-8").splitlines() if line.strip()]

        # For lane 1 (3 tasks): chunk of 3 has all 3 reserve events before any response events
        lane1_events = lines[:6]
        self.assertEqual([e["event"] for e in lane1_events[:3]], ["reserve", "reserve", "reserve"])
        self.assertEqual([e["event"] for e in lane1_events[3:]], ["response", "response", "response"])


if __name__ == "__main__":
    unittest.main()

