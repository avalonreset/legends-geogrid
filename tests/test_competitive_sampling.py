from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import competitive_sampling as cs  # noqa: E402

EM_DASH = chr(8212)


def _assert_no_em_dash(test_case: unittest.TestCase, obj: Any, path: str = "root") -> None:
    if isinstance(obj, str):
        test_case.assertNotIn(EM_DASH, obj, f"Forbidden em dash found at {path}: {obj!r}")
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _assert_no_em_dash(test_case, item, f"{path}[{idx}]")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _assert_no_em_dash(test_case, k, f"{path}.key({k})")
            _assert_no_em_dash(test_case, v, f"{path}.{k}")


class CompetitiveSamplingPlannerTests(unittest.TestCase):
    """Unit and integration tests for bounded competitor-aware sampling planner."""

    def setUp(self) -> None:
        self.center_lat = 38.6442
        self.center_lng = -121.2678

        # Synthetic minimal battlefield model with 1 Target and 3 Rivals
        self.synthetic_battlefield = {
            "schema": "legends-geogrid-battlefield/v1",
            "business": {
                "name": "Apex Mechanical",
                "lat": self.center_lat,
                "lng": self.center_lng,
                "domain": "apexmechanical.example",
                "cid": "1000000000000000001",
            },
            "target": {
                "faction_id": "TARGET",
                "name": "Apex Mechanical",
                "lat": self.center_lat,
                "lng": self.center_lng,
                "solv_pct": 25.0,
                "top3_count": 15,
                "max_top3_reach_km": 2.5,
                "trail_off_radius_km": 4.0,
            },
            "grid": {
                "total_points": 25,
                "total_lanes": 2,
                "radius_km": 1.5,
                "grid_size": 5,
                "geometry": "square_grid",
                "depth": 20,
                "zoom": 14,
            },
            "factions": [
                {
                    "faction_id": "TARGET",
                    "name": "Apex Mechanical",
                    "lat": self.center_lat,
                    "lng": self.center_lng,
                    "solv_pct": 25.0,
                    "top3_count": 15,
                },
                {
                    "faction_id": "F01",
                    "name": "Nearby Rival Air",
                    "lat": self.center_lat + 0.005,  # ~0.55 km North
                    "lng": self.center_lng,
                    "solv_pct": 20.0,
                    "top3_count": 12,
                    "location_estimated": False,
                    "max_top3_reach_km": 1.8,
                    "trail_off_radius_km": 3.0,
                },
                {
                    "faction_id": "F02",
                    "name": "Distant Fortress Heating",
                    "lat": self.center_lat + 0.05,  # ~5.5 km North (outside 1.5 km grid)
                    "lng": self.center_lng,
                    "solv_pct": 30.0,
                    "top3_count": 18,
                    "location_estimated": False,
                    "max_top3_reach_km": 3.5,
                    "trail_off_radius_km": 6.0,
                },
                {
                    "faction_id": "F03",
                    "name": "Service Area Rival Without Address",
                    "lat": None,
                    "lng": None,
                    "solv_pct": 8.0,
                    "top3_count": 5,
                    "location_estimated": True,
                    "address": None,
                },
            ],
            "lanes": [
                {
                    "lane_id": "q1",
                    "keyword": "hvac contractor",
                    "label": "hvac contractor",
                    "narrative": "Verified category discovery lane",
                },
                {
                    "lane_id": "q2",
                    "keyword": "ac repair",
                    "label": "ac repair",
                    "narrative": "Emergency cooling repair lane",
                },
            ],
        }

        self.synthetic_study_plan = {
            "schema": "geogrid-study/v1",
            "business": {
                "name": "Apex Mechanical",
                "lat": self.center_lat,
                "lng": self.center_lng,
                "domain": "apexmechanical.example",
                "cid": "1000000000000000001",
            },
            "settings": {
                "method": "live",
                "grid_size": 5,
                "radius_km": 1.2,
                "depth": 20,
                "zoom": 15,
                "device": "desktop",
                "language_code": "en",
                "se_domain": "google.com",
                "search_this_area": True,
            },
            "queries": [
                {
                    "query": "hvac contractor",
                    "selected": True,
                    "role": "category",
                    "reason": "Primary verified category",
                    "theme": {
                        "id": "category",
                        "label": "HVAC contractor category",
                        "customer_need": "Commercial and residential contractor discovery",
                        "distinct_value": "Measures general brandless discoverability",
                    },
                },
                {
                    "query": "ac repair",
                    "selected": True,
                    "role": "service",
                    "reason": "Core summer emergency offering",
                    "theme": {
                        "id": "ac_repair",
                        "label": "Air conditioning repair",
                        "customer_need": "Emergency cooling restoration",
                        "distinct_value": "Measures urgent repair responsiveness",
                    },
                },
                {
                    "query": "heating repair",
                    "selected": False,
                    "role": "service",
                    "reason": "Unselected winter candidate",
                },
            ],
        }

    def test_missing_geo_handling(self) -> None:
        """Verify competitors with missing/None geo coordinates are handled gracefully."""
        target_geo, rival_geos = cs.extract_factions_roster(self.synthetic_battlefield)
        self.assertEqual(target_geo["location_status"], "verified")
        self.assertEqual(len(rival_geos), 3)

        # F03 has lat=None, lng=None
        f03 = next(r for r in rival_geos if r["faction_id"] == "F03")
        self.assertEqual(f03["location_status"], "missing_geo")
        self.assertIsNone(f03["lat"])
        self.assertIsNone(f03["lng"])

        # Candidate probe generation must safely skip F03 without raising an error
        probes = cs.generate_candidate_sampling_probes(target_geo, rival_geos)
        for p in probes:
            self.assertNotIn("F03", p.get("anchor_factions") or [])
            self.assertIsNotNone(p["lat"])
            self.assertIsNotNone(p["lng"])

        # Truncation analysis must report missing geocoding finding for F03
        grid_meta = self.synthetic_battlefield["grid"]
        analysis = cs.detect_target_centric_truncation(target_geo, rival_geos, grid_meta)
        self.assertEqual(analysis["missing_geo_count"], 1)
        f03_finding = next(f for f in analysis["findings"] if f["faction_id"] == "F03")
        self.assertEqual(f03_finding["finding_type"], "missing_geocoding")

    def test_spatial_deduplication_and_snapping(self) -> None:
        """Verify proximate probes within snap tolerance merge into a single shared origin."""
        p1 = {
            "lat": 38.6500000,
            "lng": -121.2600000,
            "phase": 1,
            "role": "f01_citadel",
            "role_category": "rival_citadel",
            "anchor_factions": ["F01"],
            "distance_from_target_km": 1.0,
        }
        # 30 meters north
        p2 = {
            "lat": 38.6502700,
            "lng": -121.2600000,
            "phase": 2,
            "role": "f02_citadel",
            "role_category": "rival_citadel",
            "anchor_factions": ["F02"],
            "distance_from_target_km": 1.03,
        }
        # Distant point 2 km away
        p3 = {
            "lat": 38.6700000,
            "lng": -121.2600000,
            "phase": 1,
            "role": "f03_citadel",
            "role_category": "rival_citadel",
            "anchor_factions": ["F03"],
            "distance_from_target_km": 3.0,
        }

        merged = cs.snap_and_deduplicate_origins([p1, p2, p3], tolerance_km=0.20, zoom=14)
        self.assertEqual(len(merged), 2, "Probes within 30m must snap into one origin")

        # First cluster must contain merged roles and anchor factions
        first = merged[0]
        self.assertIn("f01_citadel", first["roles"])
        self.assertIn("f02_citadel", first["roles"])
        self.assertIn("F01", first["anchor_factions"])
        self.assertIn("F02", first["anchor_factions"])
        self.assertEqual(first["phase"], 1)
        self.assertTrue(first["location_coordinate"].endswith(",14z"))

    def test_query_and_settings_inheritance(self) -> None:
        """Verify planner inherits explicit selected queries and modern settings."""
        raw_task = {
            "zoom": 14,
            "depth": 20,
            "device": "desktop",
            "language_code": "en",
            "se_domain": "google.com",
            "search_this_area": True,
        }
        plan = cs.plan_competitive_sampling(
            battlefield_model=self.synthetic_battlefield,
            study_plan=self.synthetic_study_plan,
            raw_task_sample=raw_task,
        )

        queries = plan["query_selection"]
        self.assertEqual(len(queries), 2)
        q_texts = [q["query"] for q in queries]
        self.assertIn("hvac contractor", q_texts)
        self.assertIn("ac repair", q_texts)
        self.assertNotIn("heating repair", q_texts)

        settings = plan["measurement_settings"]
        self.assertEqual(settings["method"], "standard")
        # Fresh companion studies use top 30 even when the source archive used 20.
        self.assertEqual(settings["depth"], 30)
        # Modern zoom 14 preferred over old 5x5 baseline zoom 15
        self.assertEqual(settings["zoom"], 14)
        self.assertEqual(settings["device"], "desktop")
        self.assertTrue(settings["search_this_area"])

    def test_unknown_not_equal_to_absence(self) -> None:
        """Verify strict adherence to soundness policy: unknown != absence."""
        # 1. Rank 3 returned -> Found
        s1 = cs.classify_serp_observation_status(
            rank=3,
            returned_items_count=20,
            depth=20,
            has_error=False,
            is_sampled=True,
        )
        self.assertEqual(s1, cs.STATUS_FOUND)

        # 2. Rank None, full 20 items returned -> Confirmed NR
        s2 = cs.classify_serp_observation_status(
            rank=None,
            returned_items_count=20,
            depth=20,
            has_error=False,
            is_sampled=True,
        )
        self.assertEqual(s2, cs.STATUS_CONFIRMED_NR)

        # 3. Rank None, only 4 items returned (short) -> Unknown Short (NOT NR!)
        s3 = cs.classify_serp_observation_status(
            rank=None,
            returned_items_count=4,
            depth=20,
            has_error=False,
            is_sampled=True,
        )
        self.assertEqual(s3, cs.STATUS_UNKNOWN_SHORT)
        self.assertNotEqual(s3, cs.STATUS_CONFIRMED_NR, "Truncated short list must never be treated as confirmed NR")

        # 4. Rank None, 0 items returned (empty) -> Unknown Empty (NOT NR!)
        s4 = cs.classify_serp_observation_status(
            rank=None,
            returned_items_count=0,
            depth=20,
            has_error=False,
            is_sampled=True,
        )
        self.assertEqual(s4, cs.STATUS_UNKNOWN_EMPTY)
        self.assertNotEqual(s4, cs.STATUS_CONFIRMED_NR, "Empty SERP must never be treated as confirmed absence")

        # 5. Provider error -> Unknown Error
        s5 = cs.classify_serp_observation_status(
            rank=None,
            returned_items_count=0,
            depth=20,
            has_error=True,
            is_sampled=True,
        )
        self.assertEqual(s5, cs.STATUS_UNKNOWN_ERROR)

        # 6. Unsampled coordinate -> Unknown Unsampled
        s6 = cs.classify_serp_observation_status(
            rank=None,
            returned_items_count=0,
            depth=20,
            has_error=False,
            is_sampled=False,
        )
        self.assertEqual(s6, cs.STATUS_UNKNOWN_UNSAMPLED)

    def test_truncation_detection(self) -> None:
        """Verify accurate detection of target-centric grid truncations."""
        target_geo, rival_geos = cs.extract_factions_roster(self.synthetic_battlefield)
        grid_meta = self.synthetic_battlefield["grid"]

        analysis = cs.detect_target_centric_truncation(
            target_geo,
            rival_geos,
            grid_meta,
            study_plan=self.synthetic_study_plan,
        )

        # F02 is ~5.5 km North, while grid radius is 1.5 km and baseline plan is 1.2 km
        f02_findings = [f for f in analysis["findings"] if f["faction_id"] == "F02"]
        self.assertTrue(any(f["finding_type"] == "citadel_outside_boundary" for f in f02_findings))
        self.assertTrue(any(f["finding_type"] == "baseline_plan_omission" for f in f02_findings))
        self.assertGreaterEqual(analysis["truncated_citadels_count"], 1)
        self.assertGreaterEqual(analysis["baseline_omitted_count"], 1)

    def test_deterministic_phasing_and_cost_estimation(self) -> None:
        """Verify phases are deterministically structured and priced without unsafe spatial reuse."""
        plan = cs.plan_competitive_sampling(
            battlefield_model=self.synthetic_battlefield,
            study_plan=self.synthetic_study_plan,
        )

        phases = plan["phases"]
        self.assertEqual(len(phases), 3)
        self.assertEqual(phases[0]["phase"], 1)
        self.assertEqual(phases[1]["phase"], 2)

        # In safe offline planning mode, naive spatial reuse is rejected (all new tasks)
        summary = plan["summary"]
        self.assertEqual(summary["total_reused_tasks"], 0)
        self.assertEqual(summary["total_new_tasks"], summary["total_tasks"])

        # Verify math: total_tasks == origins_count * queries_count
        queries_count = summary["total_queries"]
        for p in phases:
            self.assertEqual(p["total_tasks"], p["origins_count"] * queries_count)
            self.assertEqual(p["new_tasks"], p["total_tasks"])
            expected_cost = round(p["new_tasks"] * 0.0006, 4)
            self.assertEqual(p["estimated_cost_usd"], expected_cost)

        self.assertEqual(summary["total_tasks"], sum(p["total_tasks"] for p in phases))
        self.assertEqual(summary["total_estimated_cost_usd"], round(sum(p["estimated_cost_usd"] for p in phases), 4))
        self.assertEqual(summary["readiness_status"], "planned_requires_review")

        soundness = plan["soundness_policy"]
        self.assertIn("boundary_limitation", soundness)
        self.assertIn("readiness_gate", soundness)

    def test_execution_adapter_and_task_generation(self) -> None:
        """Verify execution adapter builds valid DataForSEO task payloads with zoom encoding."""
        plan = cs.plan_competitive_sampling(
            battlefield_model=self.synthetic_battlefield,
            study_plan=self.synthetic_study_plan,
        )

        adapter = cs.CompetitiveExecutionAdapter(plan)
        tasks_p1 = adapter.build_tasks(phase=1)
        all_tasks = adapter.build_tasks()

        self.assertGreater(len(tasks_p1), 0)
        self.assertGreater(len(all_tasks), len(tasks_p1))

        first_task = all_tasks[0]
        self.assertIn("keyword", first_task)
        self.assertIn("location_coordinate", first_task)
        self.assertIn("depth", first_task)
        self.assertNotIn("zoom", first_task)
        self.assertIn("device", first_task)
        self.assertIn("language_code", first_task)
        self.assertIn("se_domain", first_task)
        self.assertIn("tag", first_task)

        # Coordinate format must include zoom encoding, e.g. "lat,lng,14z"
        self.assertTrue(first_task["location_coordinate"].endswith(",14z"))
        self.assertFalse(first_task["search_places"])
        self.assertFalse(any(key.startswith("_") for key in first_task))

        # Recipe structure
        recipe = adapter.get_execution_recipe(output_dir="runs/test_run", phase=1)
        self.assertEqual(recipe["phase"], 1)
        self.assertEqual(recipe["task_count"], len(tasks_p1))
        self.assertIn("--execute", recipe["suggested_cli_command"])

    def test_ten_rival_radial_example_and_output(self) -> None:
        """Test the planner against a 10-rival radial battlefield fixture with co-located bases."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            radial_dir = Path(tmp_dir) / "radial-theater" / "battlefield"
            radial_dir.mkdir(parents=True)
            factions = [
                {
                    "faction_id": "TARGET",
                    "name": "Apex Mechanical",
                    "is_target": True,
                    "lat": self.center_lat,
                    "lng": self.center_lng,
                    "solv_pct": 25.0,
                    "top3_count": 15,
                    "location_estimated": False,
                }
            ]
            for idx in range(1, 11):
                lat_offset = 0.02 if idx in (4, 7) else 0.008 * idx
                lng_offset = 0.02 + (0.00005 if idx == 7 else 0.0) if idx in (4, 7) else -0.006 * idx
                factions.append(
                    {
                        "faction_id": f"F{idx:02}",
                        "name": f"Synthetic Rival {idx}",
                        "is_target": False,
                        "lat": self.center_lat + lat_offset,
                        "lng": self.center_lng + lng_offset,
                        "solv_pct": 15.0,
                        "top3_count": 10,
                        "location_estimated": False,
                        "cid": f"9000000000000000{idx:02}",
                    }
                )
            fixture = {
                **self.synthetic_battlefield,
                "factions": factions,
                "lanes": [
                    *self.synthetic_battlefield["lanes"],
                    {
                        "lane_id": "q3",
                        "keyword": "furnace repair",
                        "label": "furnace repair",
                        "narrative": "Heating repair lane",
                    },
                ],
            }
            (radial_dir / "battlefield-model.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")

            out_json = Path(tmp_dir) / "competitive-plan.json"
            ret = cs.main([
                "--battlefield", str(radial_dir.parent),
                "--output", str(out_json),
            ])
            self.assertEqual(ret, 0)
            self.assertTrue(out_json.is_file())

            plan_data = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(plan_data["schema"], "legends-geogrid-competitive-plan/v1")
            self.assertEqual(plan_data["target_business"]["name"], "Apex Mechanical")
            self.assertEqual(len(plan_data["rival_factions_roster"]), 10)
            self.assertEqual(len(plan_data["query_selection"]), 3)

            # Modern settings alignment: zoom must be 14 (read from modern radial run)
            self.assertEqual(plan_data["measurement_settings"]["zoom"], 14)

            # Co-located rivals F04 and F07 (~5m apart) must snap together
            origins = plan_data["origins"]
            shared_origin = next(
                (o for o in origins if "F04" in o["anchor_factions"] and "F07" in o["anchor_factions"]),
                None,
            )
            self.assertIsNotNone(
                shared_origin,
                "Co-located rivals F04 and F07 must snap into a shared origin",
            )
            self.assertTrue(shared_origin["location_coordinate"].endswith(",14z"))

            # Preserve the original footprint and probe the full competitor field.
            summary = plan_data["summary"]
            self.assertEqual(summary["total_deduplicated_origins"], 340)
            self.assertEqual(summary["total_queries"], 3)
            self.assertEqual(summary["total_tasks"], len(origins) * 3)
            self.assertEqual(plan_data["sampling_parameters"]["sentinel_radii_km"], [2, 5, 10])
            for fid in ["TARGET", *[f"F{i:02}" for i in range(1, 11)]]:
                for bearing in range(0, 360, 45):
                    self.assertTrue(any(f"{fid}_reach_10km_{bearing}" in o["roles"] for o in origins))

            # Every point is collected fresh.
            self.assertEqual(summary["total_reused_tasks"], 0)
            self.assertEqual(summary["total_new_tasks"], summary["total_tasks"])
            self.assertAlmostEqual(summary["total_estimated_cost_usd"], summary["total_tasks"] * .0006)
            self.assertEqual(summary["readiness_status"], "planned_requires_review")

            self.assertIn("boundary_limitation", plan_data["soundness_policy"])
            self.assertIn("readiness_gate", plan_data["soundness_policy"])

            # Assert no forbidden em dashes anywhere in generated plan
            _assert_no_em_dash(self, plan_data)


if __name__ == "__main__":
    unittest.main()
