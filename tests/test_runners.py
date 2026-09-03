from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from bulk_geogrid_runner import (  # noqa: E402
    ProspectScan,
    fingerprint_scan,
    execute_pending,
    local_runner_command,
    main as bulk_main,
    validate_cost_ceiling,
    validate_run_id,
)
from local_heatmap_poc import (  # noqa: E402
    calculate_metrics,
    domain_matches,
    estimate_scan_cost,
    generate_grid,
    parse_results,
    prospecting_verdict,
    validate_run_args,
)


class GridTests(unittest.TestCase):
    def test_17_by_17_grid_has_289_points_and_center(self) -> None:
        points = generate_grid(30.249711, -97.749132, 17, 2)
        self.assertEqual(289, len(points))
        center = points[144]
        self.assertEqual("r8c8", center.tag)
        self.assertAlmostEqual(30.249711, center.lat)
        self.assertAlmostEqual(-97.749132, center.lng)

    def test_grid_rejects_even_size(self) -> None:
        with self.assertRaises(ValueError):
            generate_grid(30, -97, 4, 2)


class CostTests(unittest.TestCase):
    def test_documented_17_by_17_standard_cost(self) -> None:
        self.assertAlmostEqual(0.1734, estimate_scan_cost(289, 20, "standard"))

    def test_depth_multiplier_is_included(self) -> None:
        self.assertAlmostEqual(0.3468, estimate_scan_cost(289, 101, "standard"))


class SafetyTests(unittest.TestCase):
    def test_single_runner_is_estimate_only_by_default(self) -> None:
        process = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "local_heatmap_poc.py"),
                "--keyword",
                "pizza",
                "--target-name",
                "Example Pizza",
                "--center-lat",
                "30.249711",
                "--center-lng",
                "-97.749132",
                "--grid-size",
                "17",
                "--depth",
                "20",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(process.stdout)
        self.assertEqual("estimate-only", payload["status"])
        self.assertFalse(payload["execute"])
        self.assertEqual(289, payload["tasks"])
        self.assertEqual(0.1734, payload["standard_estimate_usd"])

    def test_bulk_child_command_carries_a_cost_ceiling(self) -> None:
        scan = ProspectScan(
            row_number=1,
            prospect_id="example",
            business_name="Example Pizza",
            keyword="pizza",
            center_lat=30.249711,
            center_lng=-97.749132,
            location_label="Austin, TX",
            target_domain="example.com",
            target_cid="",
            target_place_id="",
            radius_km=2,
            grid_size=17,
            depth=20,
            zoom=15,
            device="desktop",
            language_code="en",
            se_domain="google.com",
            search_places=False,
        )
        args = argparse.Namespace(timeout=90, poll_seconds=420, poll_interval=15)
        with tempfile.TemporaryDirectory() as temp_dir:
            command = local_runner_command(scan, "standard", Path(temp_dir), args)
        self.assertIn("--execute", command)
        ceiling_index = command.index("--confirm-cost-usd") + 1
        self.assertAlmostEqual(0.1734, float(command[ceiling_index]))

    def test_invalid_latitude_is_rejected(self) -> None:
        args = argparse.Namespace(
            center_lat=90,
            center_lng=0,
            grid_size=3,
            depth=20,
            zoom=15,
            match_threshold=0.82,
        )
        with self.assertRaises(ValueError):
            validate_run_args(args)

    def test_nan_cost_ceiling_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_cost_ceiling(float("nan"))

    def test_partial_api_response_keeps_full_grid_shape(self) -> None:
        points = generate_grid(30.249711, -97.749132, 3, 2)
        args = argparse.Namespace(
            target_name="Example Pizza",
            target_domain="",
            target_cid="",
            target_place_id="",
            match_threshold=0.82,
            top_competitors=3,
        )
        payload = {
            "tasks": [
                {
                    "status_code": 20000,
                    "data": {"tag": "r0c0"},
                    "result": [{"items": []}],
                }
            ]
        }
        results = parse_results(payload, points, args)
        self.assertEqual(9, len(results))
        self.assertEqual("r0c0", results[0].point.tag)
        self.assertEqual("No API result returned for this coordinate", results[-1].error)
        metrics = calculate_metrics(results)
        self.assertEqual(8, metrics["error_points"])
        self.assertEqual("Incomplete scan", prospecting_verdict(metrics)[0])

    def test_domain_matching_uses_hostname_boundaries(self) -> None:
        self.assertTrue(domain_matches("https://www.acme.com/service", "acme.com"))
        self.assertTrue(domain_matches("maps.acme.com", "acme.com"))
        self.assertFalse(domain_matches("notacme.com", "acme.com"))

    def test_bulk_dry_run_deduplicates_identical_scans(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "prospects.csv"
            csv_path.write_text(
                "prospect_id,business_name,keyword,center_lat,center_lng,target_domain\n"
                "one,Example Pizza,pizza,30.249711,-97.749132,example.com\n"
                "two,Example Pizza,pizza,30.249711,-97.749132,example.com\n",
                encoding="utf-8",
            )
            exit_code = bulk_main(
                [
                    "--prospects",
                    str(csv_path),
                    "--run-id",
                    "dedupe-test",
                    "--output-root",
                    str(root / "out"),
                    "--grid-size",
                    "17",
                    "--depth",
                    "20",
                ]
            )
            self.assertEqual(0, exit_code)
            manifest = json.loads((root / "out" / "dedupe-test" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["totals"]["pending_scans"])
            self.assertEqual(1, manifest["totals"]["duplicate_scans"])
            self.assertEqual(289, manifest["totals"]["pending_tasks"])
            self.assertEqual(0.1734, manifest["totals"]["pending_cost_usd"])

    def test_success_exit_without_parsed_artifact_is_not_cached(self) -> None:
        scan = ProspectScan(
            row_number=1,
            prospect_id="example",
            business_name="Example Pizza",
            keyword="pizza",
            center_lat=30.249711,
            center_lng=-97.749132,
            location_label="Austin, TX",
            target_domain="example.com",
            target_cid="",
            target_place_id="",
            radius_km=2,
            grid_size=3,
            depth=20,
            zoom=15,
            device="desktop",
            language_code="en",
            se_domain="google.com",
            search_places=False,
        )
        fingerprint = fingerprint_scan(scan, "standard")
        row = {"fingerprint": fingerprint, "cache_status": "pending"}
        cache = {"version": 1, "entries": {}}
        args = argparse.Namespace(timeout=1, poll_seconds=1, poll_interval=1)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "bulk_geogrid_runner.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout="not-json", stderr=""),
            ):
                completed = execute_pending(
                    [row],
                    {fingerprint: scan},
                    cache,
                    Path(temp_dir),
                    "standard",
                    args,
                )
        self.assertEqual("error", completed[0]["cache_status"])
        self.assertNotIn(fingerprint, cache["entries"])

    def test_bulk_run_id_cannot_escape_output_root(self) -> None:
        with self.assertRaises(ValueError):
            validate_run_id("../../outside")
        self.assertEqual("demo-run_01", validate_run_id("demo-run_01"))


class CacheTests(unittest.TestCase):
    def test_fingerprint_changes_with_depth(self) -> None:
        base = dict(
            row_number=1,
            prospect_id="example",
            business_name="Example Pizza",
            keyword="pizza",
            center_lat=30.249711,
            center_lng=-97.749132,
            location_label="Austin, TX",
            target_domain="example.com",
            target_cid="",
            target_place_id="",
            radius_km=2,
            grid_size=17,
            zoom=15,
            device="desktop",
            language_code="en",
            se_domain="google.com",
            search_places=False,
        )
        shallow = ProspectScan(depth=20, **base)
        deep = ProspectScan(depth=200, **base)
        self.assertNotEqual(fingerprint_scan(shallow, "standard"), fingerprint_scan(deep, "standard"))


if __name__ == "__main__":
    unittest.main()
