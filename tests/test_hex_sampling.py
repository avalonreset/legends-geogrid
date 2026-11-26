import json
import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from hex_sampling import (EXAMPLE_SPACINGS, STANDARD_RATE_USD, changed_cells,
                          cost_table, estimate, footprint_comparison,
                          hex_origins, ladder_origins, ladder_spacings,
                          parse_point_id, point_id, rank_class,
                          refinement_delta, refinement_staleness,
                          rung_membership, settings_fingerprint,
                          stamp_scan_dates, validate_settings_lock)
import hex_demo
import hex_plan as hex_plan_mod
from hex_plan import hex_plan
from study_contract import validate_hex_sampling

LAT, LNG = 30.09, -97.55  # approximate, Del Valle TX


class HexSamplingTests(unittest.TestCase):
    def test_center_is_exactly_the_business(self):
        points = hex_origins(LAT, LNG, 15, 2)
        center = {p["origin_id"]: p for p in points}["hex_0_0"]
        self.assertEqual((center["lat"], center["lng"]), (round(LAT, 7), round(LNG, 7)))
        self.assertEqual(center["distance_from_target_km"], 0.0)

    def test_ladder_halves_from_any_base_with_floor(self):
        self.assertEqual(ladder_spacings(4.0), [4.0, 2.0, 1.0, 0.5])
        self.assertEqual(ladder_spacings(2.7), [2.7, 1.35, 0.675])
        self.assertEqual(ladder_spacings(1.0), [1.0, 0.5])
        self.assertEqual(ladder_spacings(0.9), [0.9])
        self.assertEqual(ladder_spacings(0.3), [0.5])
        for base in (4.0, 2.7, 1.3, 0.9):
            self.assertTrue(all(s >= 0.5 for s in ladder_spacings(base)))

    def test_ids_encode_finest_rung_coordinates(self):
        points = hex_origins(LAT, LNG, 5, 2.7, base_spacing=2.7)
        for point in points:
            self.assertEqual(parse_point_id(point["origin_id"]),
                             (point["unit_q"], point["unit_r"]))
            self.assertEqual(point["origin_id"], point_id(point["unit_q"], point["unit_r"]))
            self.assertEqual(point["base_spacing_miles"], 2.7)
        self.assertEqual(rung_membership(0, 0, 4.0), [4.0, 2.0, 1.0, 0.5])
        self.assertEqual(rung_membership(2, 0, 4.0), [1.0, 0.5])
        self.assertEqual(rung_membership(0, 0, 2.7), [2.7, 1.35, 0.675])

    def test_ladder_nesting_keeps_every_coarse_point(self):
        for base in (4.0, 2.7):
            ladder = ladder_origins(LAT, LNG, 15, base)
            rungs = ladder_spacings(base)
            self.assertEqual(list(ladder), rungs)
            coarse_ids = None
            for spacing in rungs:
                ids = {p["origin_id"] for p in ladder[spacing]}
                if coarse_ids is not None:
                    self.assertTrue(coarse_ids <= ids, f"s0={base} rung {spacing} lost coarse points")
                coarse_ids = ids
            coarse = {p["origin_id"]: (p["lat"], p["lng"]) for p in ladder[rungs[0]]}
            fine = {p["origin_id"]: (p["lat"], p["lng"]) for p in ladder[rungs[-1]]}
            for origin_id, coord in coarse.items():
                self.assertEqual(fine[origin_id], coord)

    def test_off_ladder_spacing_rejected(self):
        with self.assertRaises(ValueError):
            hex_origins(LAT, LNG, 15, 1.0, base_spacing=2.7)
        with self.assertRaises(ValueError):
            hex_origins(LAT, LNG, 15, -1)
        with self.assertRaises(ValueError):
            ladder_spacings(0)
        with self.assertRaises(ValueError):
            ladder_spacings(float("nan"))

    def test_refinement_delta_returns_only_new_points(self):
        coarse = hex_origins(LAT, LNG, 15, 4)
        observed = {p["origin_id"] for p in coarse}
        delta = refinement_delta(LAT, LNG, 15, 4, 2, observed)
        fine_ids = {p["origin_id"] for p in hex_origins(LAT, LNG, 15, 2)}
        self.assertEqual({p["origin_id"] for p in delta}, fine_ids - observed)
        self.assertFalse({p["origin_id"] for p in delta} & observed)
        odd = refinement_delta(LAT, LNG, 15, 2.7, 1.35,
                               {p["origin_id"] for p in hex_origins(LAT, LNG, 15, 2.7, base_spacing=2.7)},
                               base_spacing=2.7)
        self.assertTrue(odd)
        self.assertTrue(all(p["spacing_miles"] == 1.35 for p in odd))

    def test_refinement_delta_polygon_region(self):
        coarse = hex_origins(LAT, LNG, 15, 4)
        observed = {p["origin_id"] for p in coarse}
        north = [(LAT + 0.05, LNG - 0.3), (LAT + 0.05, LNG + 0.3),
                 (LAT + 0.3, LNG + 0.3), (LAT + 0.3, LNG - 0.3)]
        delta = refinement_delta(LAT, LNG, 15, 4, 2, observed, region_polygon=north)
        self.assertTrue(delta)
        self.assertTrue(all(p["lat"] > LAT + 0.05 for p in delta))

    def test_refinement_delta_leader_change_cells_only(self):
        coarse = hex_origins(LAT, LNG, 10, 4)
        observed = {p["origin_id"] for p in coarse}
        leaders = {p["origin_id"]: ("east" if p["east_miles"] >= 0 else "west") for p in coarse}
        changed = changed_cells(coarse, leaders=leaders)
        self.assertTrue(changed)
        self.assertTrue(all(abs({p["origin_id"]: p for p in coarse}[oid]["east_miles"]) <= 4
                            for oid in changed))
        full = refinement_delta(LAT, LNG, 10, 4, 2, observed)
        delta = refinement_delta(LAT, LNG, 10, 4, 2, observed, leaders=leaders)
        self.assertTrue(0 < len(delta) < len(full))

    def test_refinement_delta_rank_class_change_cells_only(self):
        self.assertEqual([rank_class(r) for r in (None, 1, 3, 4, 10, 11, 20, 21)],
                         ["not_found", "top3", "top3", "top10", "top10", "top20", "top20", "deep"])
        coarse = hex_origins(LAT, LNG, 10, 2.7, base_spacing=2.7)
        observed = {p["origin_id"] for p in coarse}
        classes = {p["origin_id"]: rank_class(2 if abs(p["east_miles"]) < 3 else 8) for p in coarse}
        full = refinement_delta(LAT, LNG, 10, 2.7, 1.35, observed, base_spacing=2.7)
        delta = refinement_delta(LAT, LNG, 10, 2.7, 1.35, observed,
                                 base_spacing=2.7, rank_classes=classes)
        self.assertTrue(0 < len(delta) < len(full))
        uniform = refinement_delta(LAT, LNG, 10, 2.7, 1.35, observed, base_spacing=2.7,
                                   rank_classes={oid: "top3" for oid in observed})
        self.assertEqual(uniform, [])

    def test_scan_dates_flag_stale_after_14_days(self):
        points = stamp_scan_dates(hex_origins(LAT, LNG, 5, 2), "2026-11-20", "2026-11-01")
        self.assertTrue(all(p["sampled_at"] == "2026-11-20" for p in points))
        self.assertTrue(all(p["stale"] and p["scan_age_days"] == 19 for p in points))
        fresh = stamp_scan_dates(hex_origins(LAT, LNG, 5, 2), "2026-11-10", "2026-11-01")
        self.assertTrue(all(not p["stale"] for p in fresh))
        self.assertEqual(refinement_staleness("2026-11-01", "2026-11-15"),
                         {"age_days": 14, "stale": False, "threshold_days": 14})
        self.assertTrue(refinement_staleness("2026-11-01", "2026-11-16")["stale"])

    def test_settings_lock_rejects_any_difference(self):
        base = {"zoom": 15, "depth": 20, "language_code": "en", "device": "desktop"}
        self.assertEqual(validate_settings_lock(base, dict(base))["language"], "en")
        self.assertEqual(settings_fingerprint(base),
                         settings_fingerprint({"provider_zoom": 15, "depth": 20, "language": "en", "device": "desktop"}))
        for key, value in (("zoom", 14), ("depth", 30), ("language_code", "es"), ("device", "mobile")):
            changed = dict(base, **{key: value})
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    validate_settings_lock(base, changed)

    def test_counts_and_cost_at_standard_price(self):
        result = estimate(LAT, LNG, 15, 2, queries=3)
        points = hex_origins(LAT, LNG, 15, 2)
        self.assertEqual(result["locations"], len(points))
        self.assertEqual(result["requests"], len(points) * 3)
        self.assertAlmostEqual(result["estimated_scan_cost_usd"], len(points) * 3 * STANDARD_RATE_USD)
        table = cost_table(LAT, LNG, queries=1)
        self.assertEqual(len(table), 6 * len(EXAMPLE_SPACINGS))
        self.assertIn(2.7, {r["spacing_miles"] for r in table})
        self.assertEqual({(r["radius_miles"], r["spacing_miles"]) for r in table},
                         {(r, s) for r in (3, 5, 10, 15, 20, 25) for s in EXAMPLE_SPACINGS})
        by_key = {(r["radius_miles"], r["spacing_miles"]): r for r in table}
        self.assertEqual(by_key[(15, 2.0)]["locations"], len(points))
        self.assertEqual(by_key[(15, 2.7)]["locations"],
                         len(hex_origins(LAT, LNG, 15, 2.7, base_spacing=2.7)))

    def test_comparison_matches_expected_savings(self):
        row = footprint_comparison(LAT, LNG, 15, 1)
        self.assertEqual(row["radius_grid_points"], row["square_circle_points"])
        self.assertTrue(18 < row["hex_vs_square_pct_fewer"] < 28, row)
        self.assertTrue(4 < row["circle_vs_hexagon_pct_fewer"] < 16, row)

    def test_invalid_geometry_rejected(self):
        for radius, spacing in ((0, 1), (26, 1), (15, 0.25), (15, 0.3)):
            with self.subTest(radius=radius, spacing=spacing):
                with self.assertRaises(ValueError):
                    hex_origins(LAT, LNG, radius, spacing)

    def test_hex_plan_and_contract_validator(self):
        source = {
            "target_business": {"name": "Example", "lat": LAT, "lng": LNG},
            "query_selection": [{"query": "example service"}],
            "measurement_settings": {"depth": 20, "zoom": 15},
            "origins": [{"origin_id": "old", "lat": LAT, "lng": LNG}],
        }
        settings = {"zoom": 15, "depth": 20, "language_code": "en", "device": "desktop"}
        plan = hex_plan(source, radius_miles=10, base_spacing_miles=2.7, settings=settings)
        self.assertEqual(plan["sampling_parameters"]["geometry"], "hex_radius")
        self.assertEqual(plan["sampling_parameters"]["base_spacing_miles"], 2.7)
        self.assertEqual(plan["origins"][0]["roles"], ["hex_radius"])
        self.assertEqual([p["spacing_miles"] for p in plan["phases"]], [2.7, 1.35, 0.675])
        self.assertEqual(validate_hex_sampling(plan)["geometry"], "hex_radius")
        broken = dict(plan, origins=plan["origins"][:-1])
        with self.assertRaises(ValueError):
            validate_hex_sampling(broken)

    def test_hex_plan_and_hex_demo_refuse_symlink_or_junction_paths(self):
        def _link_dir(link_path: Path, target: Path) -> None:
            if sys.platform == "win32":
                import _winapi
                _winapi.CreateJunction(str(target), str(link_path))
            else:
                link_path.symlink_to(target, target_is_directory=True)

        source = {
            "target_business": {"name": "Example", "lat": LAT, "lng": LNG},
            "query_selection": [{"query": "example service"}],
            "measurement_settings": {"depth": 20, "zoom": 15},
            "origins": [{"origin_id": "old", "lat": LAT, "lng": LNG}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_in = root / "real_in"
            real_out = root / "real_out"
            real_in.mkdir()
            real_out.mkdir()
            src_file = real_in / "source.json"
            src_file.write_text(json.dumps(source), encoding="utf-8")

            linked_in = root / "linked_in"
            linked_out = root / "linked_out"
            _link_dir(linked_in, real_in)
            _link_dir(linked_out, real_out)

            # hex_plan refuses symlink/junction input path.
            with self.assertRaises(ValueError):
                hex_plan_mod.main([
                    "--source-plan", str(linked_in / "source.json"),
                    "--output", str(real_out / "plan.json"),
                ])

            # hex_plan refuses symlink/junction output path.
            with self.assertRaises(ValueError):
                hex_plan_mod.main([
                    "--source-plan", str(src_file),
                    "--output", str(linked_out / "plan.json"),
                ])
            self.assertFalse((real_out / "plan.json").exists())

            # hex_demo refuses symlink/junction output directory.
            with self.assertRaises(ValueError):
                hex_demo.build_demo(linked_out)
            self.assertEqual(list(real_out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
