from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import battlefield  # noqa: E402

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


def _build_synthetic_multi_lane_study(base_dir: Path) -> Path:
    """Create a 2-lane, 3x3 study run directory with raw 20-item DataForSEO payloads."""
    run_dir = base_dir / "synthetic_study" / "baseline"
    center_lat = 38.6442
    center_lng = -121.2678
    radius_km = 3.0
    grid_size = 3

    from local_heatmap_poc import generate_grid

    grid_points = generate_grid(center_lat, center_lng, grid_size, radius_km)

    for lane_idx, query in enumerate(("hvac contractor", "ac repair"), start=1):
        lane_dir = run_dir / f"lane-{lane_idx}" / f"20261015-lane{lane_idx}"
        lane_dir.mkdir(parents=True, exist_ok=True)

        parsed_results = []
        raw_tasks = []

        for pt_idx, pt in enumerate(grid_points):
            is_core = pt.row == 1 and pt.col == 1
            is_west_edge = pt.col == 0
            is_east_fortress = pt.col == 2 and pt.row == 0

            if is_core:
                target_rank = 1 if lane_idx == 1 else 2
            elif is_west_edge:
                target_rank = 5 if lane_idx == 1 else None
            elif is_east_fortress:
                target_rank = 8
            else:
                target_rank = 4 if lane_idx == 1 else 12

            raw_items: list[dict[str, Any]] = [
                {
                    "type": "maps_paid_item",
                    "is_paid": True,
                    "rank_group": 1,
                    "rank_absolute": 1,
                    "title": "Sponsored Ad Ignored",
                }
            ]

            for rk in range(1, 21):
                if target_rank == rk:
                    raw_items.append(
                        {
                            "type": "maps_search",
                            "rank_group": rk,
                            "rank_absolute": rk + 1,
                            "title": "Apex Climate Control",
                            "category": "HVAC contractor",
                            "additional_categories": ["Air conditioning repair service"],
                            "domain": "apexclimate.example.com",
                            "url": "https://apexclimate.example.com/",
                            "address": "100 Main St, Austin, TX",
                            "rating": {"value": 4.9, "votes_count": 220},
                            "cid": "999000111",
                            "place_id": "ChIJ_APEX_TARGET",
                            "latitude": center_lat,
                            "longitude": center_lng,
                            "is_claimed": True,
                            "price_level": "$$",
                            "work_hours": {"current_status": "open"},
                        }
                    )
                    continue

                if is_east_fortress and rk in (1, 2, 3):
                    # Entrenched high-review fortress incumbents right on their Citadel
                    raw_items.append(
                        {
                            "type": "maps_search",
                            "rank_group": rk,
                            "rank_absolute": rk + 1,
                            "title": f"Fortress Rival {rk}",
                            "category": "HVAC contractor",
                            "additional_categories": [
                                "Heating contractor",
                                "Furnace repair service",
                                "Air duct cleaning service",
                            ],
                            "domain": f"fortress{rk}.example.com",
                            "url": f"https://fortress{rk}.example.com/",
                            "address": f"{rk}00 East Fortress Way",
                            "rating": {"value": 4.9, "votes_count": 650 + rk * 20},
                            "cid": f"888000{rk:02d}",
                            "place_id": f"ChIJ_FORTRESS_{rk}",
                            "latitude": pt.lat + 0.001,
                            "longitude": pt.lng + 0.001,
                            "is_claimed": True,
                            "price_level": "$$",
                            "work_hours": {"current_status": "open"},
                        }
                    )
                elif is_west_edge and rk in (1, 2, 3):
                    # Overextended weak incumbents > 3.5 km from their own base with low reviews and rating
                    raw_items.append(
                        {
                            "type": "maps_search",
                            "rank_group": rk,
                            "rank_absolute": rk + 1,
                            "title": f"Paper Tiger HVAC {rk}",
                            "category": "General contractor" if rk == 3 else "HVAC contractor",
                            "additional_categories": ["Sheet metal contractor"],
                            "domain": None if rk == 3 else f"tiger{rk}.example.com",
                            "url": None if rk == 3 else f"https://tiger{rk}.example.com/",
                            "address": f"{rk}0 Distant Industrial Rd",
                            "rating": {"value": 4.2 if rk == 3 else 4.4, "votes_count": 18 + rk * 5},
                            "cid": f"777000{rk:02d}",
                            "place_id": f"ChIJ_TIGER_{rk}",
                            "latitude": center_lat + 0.032,
                            "longitude": center_lng + 0.035,
                            "is_claimed": False if rk == 3 else True,
                            "price_level": "$",
                            "work_hours": None,
                        }
                    )
                else:
                    comp_num = ((rk + pt_idx) % 12) + 1
                    raw_items.append(
                        {
                            "type": "maps_search",
                            "rank_group": rk,
                            "rank_absolute": rk + 1,
                            "title": f"Regional Competitor {comp_num:02d}" + (f" {EM_DASH} North" if comp_num == 1 else ""),
                            "category": "HVAC contractor",
                            "additional_categories": ["Heating contractor", "Boiler supplier"],
                            "domain": f"rival{comp_num:02d}.example.com",
                            "url": f"https://rival{comp_num:02d}.example.com/",
                            "address": f"{comp_num}00 Service Blvd",
                            "rating": {"value": 4.6, "votes_count": 90 + comp_num * 10},
                            "cid": f"555000{comp_num:02d}",
                            "place_id": f"ChIJ_RIVAL_{comp_num:02d}",
                            "latitude": center_lat + (comp_num - 6) * 0.004,
                            "longitude": center_lng + (comp_num - 6) * 0.004,
                            "is_claimed": True,
                            "price_level": "$$",
                            "work_hours": {"current_status": "open"},
                        }
                    )

            raw_tasks.append(
                {
                    "status_code": 20000,
                    "status_message": "Ok.",
                    "data": {"tag": pt.tag, "keyword": query},
                    "result": [{"datetime": "2026-10-15 12:00:00 +00:00", "items": raw_items}],
                }
            )

            # Truncated top_items (only 5 items) in parsed-grid.json to test 20-item raw enrichment
            truncated_top = [
                {
                    "rank": it["rank_group"],
                    "title": it["title"],
                    "cid": it.get("cid"),
                }
                for it in raw_items
                if not it.get("is_paid")
            ][:5]

            parsed_results.append(
                {
                    "point": {
                        "row": pt.row,
                        "col": pt.col,
                        "lat": pt.lat,
                        "lng": pt.lng,
                        "tag": pt.tag,
                    },
                    "rank": target_rank,
                    "status": "found" if target_rank is not None else "not_returned_depth_reached",
                    "error": None,
                    "matched_item": (
                        {"rank": target_rank, "title": "Apex Climate Control", "cid": "999000111"}
                        if target_rank is not None
                        else None
                    ),
                    "top_items": truncated_top,
                    "returned_items_count": 20,
                    "organic_items_count": 20,
                    "observed_ranks": list(range(1, 21)),
                }
            )

        parsed_payload = {
            "target": "Apex Climate Control",
            "keyword": query,
            "location": "Austin, TX",
            "measurement_settings": {
                "schema_version": 4,
                "method": "standard",
                "keyword": query,
                "center_lat": center_lat,
                "center_lng": center_lng,
                "radius_km": radius_km,
                "grid_size": grid_size,
                "depth": 20,
                "zoom": 15,
                "target_name": "Apex Climate Control",
                "target_cid": "999000111",
                "target_domain": "apexclimate.example.com",
            },
            "metrics": {"points": len(grid_points)},
            "results": parsed_results,
        }
        raw_payload = {
            "version": "fanout",
            "status_code": 20000,
            "tasks_count": len(raw_tasks),
            "tasks": raw_tasks,
        }

        (lane_dir / "parsed-grid.json").write_text(json.dumps(parsed_payload, indent=2), encoding="utf-8")
        (lane_dir / "dataforseo-response.raw.json").write_text(
            json.dumps(raw_payload, indent=2),
            encoding="utf-8",
        )

    report_config = {
        "schema_version": 1,
        "synthetic": False,
        "business": {
            "name": "Apex Climate Control",
            "lat": center_lat,
            "lng": center_lng,
            "location": "Austin, TX",
            "website": "apexclimate.example.com",
        },
        "lanes": [
            {
                "query_id": "q1",
                "label": "hvac contractor",
                "query": "hvac contractor",
                "records_path": str(run_dir / "lane-1" / "parsed-grid.json"),
                "narrative": "Primary contractor category discovery.",
            },
            {
                "query_id": "q2",
                "label": "ac repair",
                "query": "ac repair",
                "records_path": str(run_dir / "lane-2" / "parsed-grid.json"),
                "narrative": "Urgent air conditioning repair discovery.",
            },
        ],
    }
    (run_dir / "report-config.json").write_text(json.dumps(report_config, indent=2), encoding="utf-8")
    return run_dir


class BattlefieldEngineTests(unittest.TestCase):
    def test_geodesic_haversine_and_compass_sectors(self) -> None:
        self.assertAlmostEqual(0.0, battlefield.haversine_km(30.0, -97.0, 30.0, -97.0), places=6)
        one_deg_lat = battlefield.haversine_km(30.0, -97.0, 31.0, -97.0)
        self.assertTrue(110.5 <= one_deg_lat <= 112.0)

        c_lat, c_lng = 38.6442, -121.2678
        self.assertEqual("CORE", battlefield.compass_sector(c_lat, c_lng, c_lat, c_lng, radius_km=2.0))
        self.assertEqual("CORE", battlefield.compass_sector(c_lat, c_lng, c_lat + 0.001, c_lng, radius_km=2.0))
        self.assertEqual("N", battlefield.compass_sector(c_lat, c_lng, c_lat + 0.02, c_lng, radius_km=2.0))
        self.assertEqual("S", battlefield.compass_sector(c_lat, c_lng, c_lat - 0.02, c_lng, radius_km=2.0))
        self.assertEqual("E", battlefield.compass_sector(c_lat, c_lng, c_lat, c_lng + 0.025, radius_km=2.0))
        self.assertEqual("W", battlefield.compass_sector(c_lat, c_lng, c_lat, c_lng - 0.025, radius_km=2.0))
        self.assertEqual("NE", battlefield.compass_sector(c_lat, c_lng, c_lat + 0.02, c_lng + 0.025, radius_km=2.0))
        self.assertEqual("NW", battlefield.compass_sector(c_lat, c_lng, c_lat + 0.02, c_lng - 0.025, radius_km=2.0))
        self.assertEqual("SE", battlefield.compass_sector(c_lat, c_lng, c_lat - 0.02, c_lng + 0.025, radius_km=2.0))
        self.assertEqual("SW", battlefield.compass_sector(c_lat, c_lng, c_lat - 0.02, c_lng - 0.025, radius_km=2.0))

    def test_multi_lane_raw_20_item_enrichment_and_tactical_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _build_synthetic_multi_lane_study(Path(tmp))
            lanes = battlefield.load_study_lanes(run_dir)
            self.assertEqual(2, len(lanes))

            for lane in lanes:
                self.assertTrue(lane["enriched_from_raw"])
                for pt_res in lane["results"]:
                    self.assertEqual(20, len(pt_res["top_items"]))
                    first_item = pt_res["top_items"][0]
                    for required_field in (
                        "rank",
                        "rank_group",
                        "rank_absolute",
                        "title",
                        "category",
                        "additional_categories",
                        "domain",
                        "url",
                        "address",
                        "rating",
                        "votes_count",
                        "cid",
                        "place_id",
                        "latitude",
                        "longitude",
                        "is_claimed",
                        "price_level",
                        "work_hours",
                    ):
                        self.assertIn(required_field, first_item)

            model = battlefield.build_battlefield_model(run_dir)
            _assert_no_em_dash(self, model)

            # 11-Faction Roster (TARGET + 10 Rivals)
            self.assertEqual(11, len(model["factions"]))
            target = model["factions"][0]
            self.assertEqual("TARGET", target["faction_id"])
            self.assertTrue(target["is_target"])
            self.assertEqual(0, target["rank_order"])
            self.assertEqual("#10b981", target["color"])
            self.assertEqual("YOU", target["short_code"])
            self.assertEqual("COMMANDER", target["archetype"])
            self.assertEqual("SELF", target["threat_level"])

            for idx, rival in enumerate(model["factions"][1:], start=1):
                self.assertEqual(f"F{idx:02d}", rival["faction_id"])
                self.assertEqual(f"R{idx:02d}", rival["short_code"])
                self.assertFalse(rival["is_target"])
                self.assertEqual(idx, rival["rank_order"])
                self.assertIn(
                    rival["archetype"],
                    {
                        "REGIONAL_HEGEMON",
                        "CITADEL_FORTRESS",
                        "OVEREXTENDED_TIGER",
                        "CORRIDOR_BLOCKER",
                        "LOCAL_OUTPOST",
                    },
                )
                self.assertIn(rival["threat_level"], {"CRITICAL", "HIGH", "MODERATE", "LOW"})
                self.assertTrue(bool(rival["primary_vulnerability"]))
                self.assertIn("q1", rival["lane_stats"])
                self.assertIn("q2", rival["lane_stats"])

            # Verify points tactical states, opportunity scores, and gravity anomalies
            points_by_tag = {p["tag"]: p for p in model["points"]}
            self.assertEqual(9, len(points_by_tag))

            core_pt = points_by_tag["r1c1"]
            self.assertEqual("CLEARED_CITADEL", core_pt["aggregate"]["fog_state"])
            self.assertEqual("TARGET_OWNED", core_pt["aggregate"]["turf_state"])
            self.assertEqual("OWNED_STRONGHOLD", core_pt["aggregate"]["tactical_class"])
            self.assertTrue(15 <= core_pt["aggregate"]["opportunity_score"] <= 45)

            west_pt = points_by_tag["r1c0"]
            q1_west = west_pt["by_lane"]["q1"]
            q2_west = west_pt["by_lane"]["q2"]
            self.assertEqual("CONTESTED_VISION", q1_west["fog_state"])
            self.assertEqual("PRIME_STRIKE_ZONE", q1_west["tactical_class"])
            self.assertGreaterEqual(q1_west["opportunity_score"], 65)
            self.assertTrue(q1_west["gravity_anomaly"]["has_anomaly"])
            self.assertGreaterEqual(q1_west["gravity_anomaly"]["distance_from_pin_km"], 2.5)

            self.assertEqual("DARK_ZONE", q2_west["fog_state"])
            self.assertIn(q2_west["tactical_class"], {"FLANKING_MINE", "PRIME_STRIKE_ZONE"})
            self.assertGreaterEqual(q2_west["opportunity_score"], 52)

            east_fortress_pt = points_by_tag["r0c2"]
            q1_fort = east_fortress_pt["by_lane"]["q1"]
            self.assertEqual("ENEMY_FORTRESS", q1_fort["tactical_class"])
            self.assertLess(q1_fort["opportunity_score"], 38)

            # Verify Campaign Orders
            orders = model["campaign_orders"]
            self.assertTrue(bool(orders["headline_summary"]))
            fow = orders["fog_of_war_summary"]
            self.assertEqual(
                9,
                fow["cleared_citadel_tiles"]
                + fow["contested_vision_tiles"]
                + fow["suppressed_tiles"]
                + fow["dark_zone_tiles"],
            )
            self.assertTrue(len(orders["strike_corridors"]) >= 1)
            self.assertTrue(len(orders["tech_tree_unlocks"]) >= 3)
            unlock_types = {u["unlock_type"] for u in orders["tech_tree_unlocks"]}
            self.assertIn("GBP_CATEGORY", unlock_types)
            self.assertIn("SERVICE_CORRIDOR_PAGE", unlock_types)
            self.assertIn("REVIEW_TROOP_SURGE", unlock_types)
            self.assertIn("BLIND_SPOT_THEME", unlock_types)
            self.assertTrue(len(orders["fortress_warnings"]) >= 1)
            self.assertTrue(1 <= len(orders["next_turn_recon_probes"]) <= 5)

    def test_home_slice_starter_study_model(self) -> None:
        home_slice_path = ROOT / "src" / "data" / "home-slice-study.json"
        self.assertTrue(home_slice_path.is_file())

        model = battlefield.build_battlefield_model(home_slice_path)
        _assert_no_em_dash(self, model)

        self.assertEqual(4, len(model["lanes"]))
        self.assertEqual(1249, len(model["points"]))
        self.assertEqual(11, len(model["factions"]))

        target = model["target_faction"]
        self.assertEqual("Home Slice Pizza", target["name"])
        self.assertGreater(target["solv_pct"], 5.0)

        fow = model["campaign_orders"]["fog_of_war_summary"]
        self.assertEqual(
            1249,
            fow["cleared_citadel_tiles"]
            + fow["contested_vision_tiles"]
            + fow["suppressed_tiles"]
            + fow["dark_zone_tiles"],
        )

        for rival in model["rival_factions"]:
            self.assertIsNotNone(rival["lat"])
            self.assertIsNotNone(rival["lng"])
            self.assertTrue(30.10 <= rival["lat"] <= 30.45)
            self.assertTrue(-97.95 <= rival["lng"] <= -97.55)

    def test_bundled_proof_cli_execution(self) -> None:
        source = ROOT / "src" / "data" / "home-slice-study.json"

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = battlefield.main(
                    [
                        "--input",
                        str(source),
                        "--output-dir",
                        str(out_dir),
                        "--no-pdf",
                        "--no-console",
                    ]
                )
            self.assertEqual(0, rc)
            receipt = json.loads(buf.getvalue())
            self.assertEqual("ok", receipt["status"])
            model_file = Path(receipt["outputs"]["battlefield_model_json"])
            self.assertTrue(model_file.is_file())
            saved_model = json.loads(model_file.read_text(encoding="utf-8"))
            _assert_no_em_dash(self, saved_model)
            self.assertEqual(4, saved_model["grid"]["total_lanes"])
            self.assertEqual(1249, saved_model["grid"]["total_points"])


if __name__ == "__main__":
    unittest.main()
