"""Offline regressions for legacy runner acquisition, cache and presentation fixes."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import local_heatmap_poc as local
import bulk_geogrid_runner as bulk


def args(**overrides):
    result = local.parse_args(["--keyword", "bicycle repair", "--target-name", "Example Workshop",
                               "--center-lat", "38", "--center-lng", "-100", "--grid-size", "3"])
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


class RunnerFixTests(unittest.TestCase):
    def test_output_allocation_preserves_identical_and_different_query_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = args(output_dir=directory)
            first = local.write_outputs(settings, [], {"first": True}, [])
            second = local.write_outputs(settings, [], {"second": True}, [])
            settings.keyword = "wheel repair"
            third = local.write_outputs(settings, [], {"third": True}, [])
            self.assertEqual(3, len({result["output_dir"] for result in (first, second, third)}))
            self.assertEqual({"first": True}, json.loads(Path(first["raw_payload"]).read_text()))
            self.assertEqual("bicycle repair", json.loads(Path(second["parsed_json"]).read_text())["keyword"])

    def test_ambiguous_branches_are_unknown_but_exact_identifier_resolves(self):
        settings = args(target_domain="workshop.example", target_name="Workshop")
        point = local.generate_grid(38, -100, 1, 1)[0]
        items = [{"type": "maps_search", "title": "Workshop North", "domain": "workshop.example", "cid": "1", "rank_group": 1},
                 {"type": "maps_search", "title": "Workshop South", "domain": "workshop.example", "cid": "2", "rank_group": 8}]
        payload = {"tasks": [{"status_code": 20000, "result": [{"items": items}]}]}
        ambiguous = local.parse_results(payload, [point], settings)[0]
        self.assertEqual("ambiguous_target", ambiguous.status)
        self.assertIsNone(ambiguous.rank)
        self.assertIsNone(ambiguous.matched_item)
        self.assertEqual(0, local.calculate_metrics([ambiguous])["top3_eligible_points"])
        settings.target_cid = "2"
        exact = local.parse_results(payload, [point], settings)[0]
        self.assertEqual(8, exact.rank)
        self.assertIsNone(exact.error)

    def test_duplicate_branch_records_do_not_create_false_ambiguity(self):
        settings = args(target_domain="workshop.example")
        point = local.generate_grid(38, -100, 1, 1)[0]
        item = {"type": "maps_search", "title": "Example Workshop", "domain": "workshop.example", "cid": "1", "rank_group": 2}
        result = local.parse_results({"tasks": [{"status_code": 20000, "result": [{"items": [item, dict(item)]}]}]}, [point], settings)[0]
        self.assertEqual(2, result.rank)
        self.assertIsNone(result.error)

    def test_schematic_has_physical_offsets_and_no_unregistered_street_map(self):
        pin_positions = []
        for radius in (1, 4):
            settings = args(radius_km=radius, map_image="unregistered-background.png")
            results = [local.PointResult(point, 1, None, []) for point in local.generate_grid(38, -100, 3, radius)]
            document = local.render_html(settings, results, Path("report.md"))
            self.assertIn("schematic", document)
            self.assertIn("approximate kilometres", document)
            self.assertNotIn("<iframe", document)
            self.assertNotIn("<img", document)
            self.assertNotIn("unregistered-background.png", document)
            self.assertIn("aspect-ratio: 1", document)
            positions = re.findall(r'style="left:([\d.]+)%;top:([\d.]+)%;"', document)
            self.assertEqual(9, len(positions))
            self.assertEqual(("50.000", "50.000"), positions[4])
            pin_positions.append(positions)
        self.assertNotEqual(*pin_positions)

    def test_dateline_grid_wraps_and_schematic_keeps_east_to_the_right(self):
        settings = args(center_lat=72, center_lng=179.99, radius_km=2)
        points = local.generate_grid(72, 179.99, 3, 2)
        self.assertTrue(all(-180 <= point.lng <= 180 for point in points))
        self.assertLess(points[5].lng, 0)
        document = local.render_html(settings, [local.PointResult(p, 1, None, []) for p in points], Path("report.md"))
        positions = re.findall(r'style="left:([\d.]+)%;top:([\d.]+)%;"', document)
        self.assertGreater(float(positions[5][0]), 50)

    def test_invalid_geometry_never_reaches_requests(self):
        for lat, lng, radius in ((90, 0, 1), (89.999, 0, 2), (0, 181, 1),
                                 (0, 0, float("nan")), (0, 0, float("inf")), (float("nan"), 0, 1)):
            with self.subTest(lat=lat, lng=lng, radius=radius), self.assertRaises(ValueError):
                local.generate_grid(lat, lng, 3, radius)
        with self.assertRaises(ValueError):
            local.build_tasks(args(), [local.GridPoint(0, 0, 0, float("nan"), "bad")])

    def test_competitor_counts_filter_ranks_deduplicate_and_skip_errors(self):
        point = local.generate_grid(38, -100, 1, 1)[0]
        result = local.PointResult(point, None, None, [
            {"title": "Eighth", "rank": 8}, {"title": "First", "rank": 1},
            {"title": "First", "rank": 2}, {"title": "Third", "rank": 3},
            {"title": "Bad", "rank": True}, {"title": "Missing"}])
        self.assertEqual([("First", 1), ("Third", 1)], local.competitor_counts([result]))
        result.error = "Provider error"
        self.assertEqual([], local.competitor_counts([result]))

    def test_human_cost_receipt_uses_depth_units_for_all_methods(self):
        settings = args(depth=201)
        point = local.generate_grid(38, -100, 1, 1)[0]
        report = local.render_markdown(settings, [local.PointResult(point, 1, None, [])], {}, "synthetic")
        self.assertIn("$0.0060 live, $0.0036 priority, or $0.0018 standard", report)


class CacheFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        csv = self.root / "prospects.csv"
        csv.write_text("business_name,keyword,lat,lng,target_cid\nExample Workshop,bicycle repair,38,-100,123\n")
        self.argv = ["--prospects", str(csv), "--output-root", str(self.root / "bulk"), "--run-id", "proof", "--grid-size", "1"]
        self.bulk_args = bulk.parse_args(self.argv)
        self.scan = bulk.load_prospects(self.bulk_args)[0]
        command = bulk.local_runner_command(self.scan, "standard", self.root / "scans", self.bulk_args)
        self.settings = local.parse_args(command[2:])
        points = local.generate_grid(38, -100, 1, self.scan.radius_km)
        tasks = local.build_tasks(self.settings, points)
        payload = {"tasks": [{"status_code": 20000, "data": {"tag": points[0].tag},
                              "result": [{"items": [{"cid": "123", "rank_group": 1, "title": "Example Workshop"}]}]}]}
        self.outputs = local.write_outputs(self.settings, tasks, payload, local.parse_results(payload, points, self.settings))
        parsed, hashes = bulk.inspect_artifacts(self.outputs, bulk.scan_identity(self.scan, "standard"))
        self.entry = {"fingerprint": bulk.fingerprint_scan(self.scan, "standard"),
                      "identity": bulk.scan_identity(self.scan, "standard"), "outputs": self.outputs,
                      "artifact_sha256": hashes, "generated_at": parsed["generated_at"], "metrics": parsed["metrics"]}

    def fresh(self, entry=None):
        return bulk.is_cache_fresh(entry or self.entry, self.bulk_args, self.scan, "standard")

    def test_valid_cache_reuse_carries_reviewable_lineage(self):
        self.assertTrue(self.fresh())
        bulk.write_json(self.root / "bulk/cache-index.json", {"entries": {self.entry["fingerprint"]: self.entry}})
        with patch("builtins.print"):
            self.assertEqual(0, bulk.main(self.argv))
        row = json.loads((self.root / "bulk/proof/manifest.json").read_text())["rows"][0]
        self.assertEqual("cached", row["cache_status"])
        for field in ("outputs", "metrics", "generated_at", "artifact_sha256"):
            self.assertEqual(self.entry[field], row[field])
        self.assertEqual(self.entry["generated_at"], row["cache_reuse"]["acquired_at"])

    def test_missing_or_mutated_artifacts_cannot_be_allowed_stale(self):
        self.bulk_args.allow_stale_cache = True
        for key in ("raw_tasks", "raw_payload", "parsed_json", "markdown", "html"):
            path = Path(self.outputs[key])
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            self.assertFalse(self.fresh(), key)
            path.write_bytes(original)
        broken = copy.deepcopy(self.entry)
        broken["outputs"]["parsed_json"] = str(self.root / "missing.json")
        self.assertFalse(self.fresh(broken))

    def test_self_consistent_hashes_do_not_hide_wrong_measurement_identity(self):
        path = Path(self.outputs["parsed_json"])
        parsed = json.loads(path.read_text())
        parsed["measurement_settings"]["target_cid"] = "different-target"
        path.write_text(json.dumps(parsed))
        self.entry["artifact_sha256"]["parsed_json"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertFalse(self.fresh())

    def test_wrong_request_lineage_is_rejected_even_with_new_hash(self):
        path = Path(self.outputs["raw_tasks"])
        tasks = json.loads(path.read_text())
        tasks[0]["depth"] = 101
        path.write_text(json.dumps(tasks))
        self.entry["artifact_sha256"]["raw_tasks"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertFalse(self.fresh())

    def test_unverified_old_index_and_wrong_metrics_are_rejected(self):
        old = copy.deepcopy(self.entry)
        del old["artifact_sha256"]
        self.assertFalse(self.fresh(old))
        wrong = copy.deepcopy(self.entry)
        wrong["metrics"]["found_points"] = 100
        self.assertFalse(self.fresh(wrong))

    def test_response_with_updated_hash_must_still_reproduce_parsed_results(self):
        path = Path(self.outputs["raw_payload"])
        payload = json.loads(path.read_text())
        payload["tasks"][0]["result"][0]["items"][0]["cid"] = "another-business"
        path.write_text(json.dumps(payload))
        self.entry["artifact_sha256"]["raw_payload"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertFalse(self.fresh())

    def test_successful_child_is_cached_only_with_valid_evidence(self):
        run = self.root / "executed"
        run.mkdir()
        cache = {"entries": {}}
        row = {"fingerprint": self.entry["fingerprint"], "cache_status": "pending"}
        child = SimpleNamespace(returncode=0, stdout=json.dumps({"outputs": self.outputs}), stderr="")
        with patch.object(bulk.subprocess, "run", return_value=child):
            result = bulk.execute_pending([row], {row["fingerprint"]: self.scan}, cache, run, "standard", self.bulk_args)
        self.assertEqual("executed", result[0]["cache_status"])
        self.assertTrue(self.fresh(cache["entries"][row["fingerprint"]]))


if __name__ == "__main__":
    unittest.main()
