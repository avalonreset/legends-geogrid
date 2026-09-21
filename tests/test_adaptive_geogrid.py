from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import adaptive_geogrid as ag


def config(**changes):
    raw = {
        "center": {"lat": 40.0, "lng": -100.0},
        "targets": [{"cid": "123", "place_id": "test-place"}],
        "queries": [{"id": "primary", "keyword": "pizza"},
                    {"id": "secondary", "keyword": "pizza delivery"}],
        "starting_grid": 3, "max_shell": 3, "depth": 3, "negative_depth": 3,
    }
    raw.update(changes)
    return ag.validate_config(raw)


def response(items, **changes):
    payload = {"status_code": 20000, "cost": 0.002,
               "tasks": [{"status_code": 20000, "result": [{"items": items}]}]}
    payload.update(changes)
    return payload


def items(count=3):
    return [{"type": "maps_search", "cid": "999", "place_id": "unrelated",
             "domain": "other.invalid", "rank_group": rank} for rank in range(1, count + 1)]


class ConfigTests(unittest.TestCase):
    def test_invalid_coordinates_and_bounds(self):
        for center in ({"lat": 90, "lng": 0}, {"lat": 0, "lng": 181},
                       {"lat": float("nan"), "lng": 0}, {"lat": 0, "lng": float("inf")},
                       {"lat": True, "lng": 0}, {"lat": 89.9999, "lng": 0},
                       {"lat": 0, "lng": 179.9999}):
            with self.subTest(center=center), self.assertRaises(ValueError):
                config(center=center)

    def test_invalid_settings_fail_closed(self):
        invalid = ({"starting_grid": 2}, {"max_shell": 0}, {"max_shell": 51},
                   {"depth": 0}, {"negative_depth": 4}, {"provider_zoom": 2},
                   {"display_zoom": float("nan")}, {"spacing_km": -1},
                   {"search_this_area": "false"}, {"max_calls": True},
                   {"depth": 3.0}, {"strategy": "guess"}, {"unknown": True},
                   {"strategy": []}, {"device": []},
                   {"targets": [{"name": "Example"}]}, {"targets": [{"cid": 123}]},
                   {"targets": [{"domain": ""}]}, {"queries": []},
                   {"queries": [{"id": "a:b", "keyword": "pizza"}]},
                   {"queries": [{"id": "a", "keyword": "pizza"}, {"id": "a", "keyword": "food"}]})
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                config(**values)

    def test_all_config_settings_and_adapter_participate_in_fingerprint(self):
        original = config()
        identity = ag.ReplayAdapter({"default": {"state": "empty"}}).identity
        expected = ag.fingerprint(original, identity)
        for key in original:
            altered = copy.deepcopy(original)
            altered[key] = {"changed": True}
            with self.subTest(key=key):
                self.assertNotEqual(expected, ag.fingerprint(altered, identity))
        self.assertNotEqual(expected, ag.fingerprint(original, ag.LiveAdapter.identity))
        other = ag.ReplayAdapter({"default": {"state": "error"}}).identity
        self.assertNotEqual(expected, ag.fingerprint(original, other))

    def test_display_zoom_does_not_change_provider_task(self):
        first = config()
        second = config(display_zoom=5)
        self.assertEqual(ag.request_task(first, first["queries"][0], 0, 0),
                         ag.request_task(second, second["queries"][0], 0, 0))
        third = config(provider_zoom=5)
        self.assertTrue(ag.request_task(third, third["queries"][0], 0, 0)["location_coordinate"].endswith(",5z"))

    def test_deterministic_geometry_and_partition(self):
        for shell in range(1, 9):
            expected = set(ag.shell_points(shell))
            partition = [point for direction in ag.SECTORS for point in ag.shell_points(shell, direction)]
            self.assertEqual(8 * shell, len(partition))
            self.assertEqual(expected, set(partition))
            for direction in ag.SECTORS:
                self.assertIn(ag.sentinel(shell, direction), ag.shell_points(shell, direction))
        self.assertEqual(ag.plan_summary(config()), ag.plan_summary(config()))


class NormalizationTests(unittest.TestCase):
    def normalize(self, payload, cfg=None):
        cfg = cfg or config()
        return ag.normalize_response(cfg, cfg["queries"][0], 0, 0, payload,
                                     "synthetic-replay", "2000-01-01T00:00:00+00:00")

    def test_clean_negative_requires_contiguous_organic_depth(self):
        row = self.normalize(response(items()))
        self.assertEqual(("not_returned", 3, True), (row["state"], row["depth"], row["clean_negative"]))
        for values in (items(2), [items()[0], items()[2], dict(items()[2])],
                       [{**item, "rank_group": 10 + i} for i, item in enumerate(items())]):
            row = self.normalize(response(values))
            self.assertFalse(row["clean_negative"])

    def test_ads_do_not_complete_depth_or_match(self):
        values = items(2) + [{**items()[2], "cid": "123", "place_id": "test-place", "is_paid": True}]
        row = self.normalize(response(values))
        self.assertEqual("not_returned", row["state"])
        self.assertEqual(2, row["returned_count"])
        self.assertFalse(row["clean_negative"])

    def test_every_supplied_identity_field_must_match(self):
        cfg = config(targets=[{"cid": "123", "place_id": "test-place", "domain": "example.com"}])
        good = {"type": "maps_search", "rank_group": 2, "cid": "123", "place_id": "test-place",
                "url": "https://www.example.com/locations"}
        self.assertEqual("found", self.normalize(response([good]), cfg)["state"])
        for key in ("cid", "place_id", "url"):
            bad = {**good, key: "different"}
            self.assertEqual("not_returned", self.normalize(response([bad]), cfg)["state"])

    def test_multiple_identity_alternatives_choose_best_organic_rank(self):
        cfg = config(targets=[{"cid": "123"}, {"place_id": "other-place"}, {"domain": "example.com"}])
        values = [{**items()[0], "cid": "123", "rank_group": 12},
                  {**items()[0], "place_id": "other-place", "rank_group": 4},
                  {**items()[0], "domain": "EXAMPLE.com", "rank_group": 2}]
        self.assertEqual(2, self.normalize(response(values), cfg)["rank"])

    def test_domain_matching_is_exact_normalized_host(self):
        cfg = config(targets=[{"domain": "https://www.example.com/"}])
        for domain, expected in (("www.example.com", "found"), ("example.com", "found"),
                                 ("branch.example.com", "not_returned"), ("notexample.com", "not_returned")):
            row = self.normalize(response([{**items()[0], "domain": domain}]), cfg)
            self.assertEqual(expected, row["state"])

    def test_bad_rank_on_matching_target_cannot_certify_negative(self):
        for rank in (None, True, 0, -2, "3"):
            row = self.normalize(response([{**items()[0], "cid": "123", "place_id": "test-place",
                                            "rank_group": rank}]))
            self.assertEqual("error", row["state"])
            self.assertIsNone(row["rank"])
            self.assertFalse(row["clean_negative"])

    def test_empty_errors_malformed_response_are_not_negatives(self):
        payloads = [None, [], response([]), {"status_code": 20000, "tasks": []},
                    response(items(), status_code=50000),
                    {"status_code": 20000, "tasks": [{"status_code": 40102}]},
                    {"status_code": 20000, "tasks": [{"status_code": 50000}]},
                    response([] , tasks=[{"status_code": 20000, "result": {"items": []}}]),
                    response([] , tasks=[{"status_code": 20000, "result": [{"items": [None]}]}])]
        for payload in payloads:
            with self.subTest(payload=payload):
                row = self.normalize(payload)
                self.assertIn(row["state"], {"empty", "error"})
                self.assertFalse(row["clean_negative"])

    def test_cost_wrapper_not_double_counted(self):
        self.assertEqual("0.02", str(ag.reported_cost({"cost": 0.02, "tasks": [{"cost": 0.02}]})))
        self.assertEqual("0.02", str(ag.reported_cost({"tasks": [{"cost": 0.02}]})))
        with self.assertRaises(ValueError):
            ag.reported_cost({"cost": -1})


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.fixture = {"default": {"state": "not_returned", "returned_count": 3}}

    def run_scan(self, cfg=None, fixture=None, ceiling=10, directory=None, adapter=None):
        return ag.Collector(cfg or config(), adapter or ag.ReplayAdapter(fixture or self.fixture),
                            directory or self.directory, ceiling).run()

    def rows(self, directory=None):
        return json.loads(((directory or self.directory) / "observations.json").read_text())

    def test_two_complete_layers_and_all_query_sentinels(self):
        manifest = self.run_scan()
        self.assertEqual("sampled_stop", manifest["status"])
        self.assertTrue(manifest["complete_common_base"])
        self.assertEqual(66, manifest["accounting"]["attempted_calls"])
        self.assertEqual(33, manifest["selected_origins"])
        for state in manifest["sectors"].values():
            self.assertEqual((2, 2, 3, "sampled_stop"),
                             (state["clean_layers"], state["last_full_shell"], state["sentinel_shell"], state["state"]))
        by_origin = {}
        for row in self.rows():
            by_origin.setdefault((row["x"], row["y"]), set()).add(row["query_id"])
        self.assertTrue(all(queries == {"primary", "secondary"} for queries in by_origin.values()))

    def test_positive_sentinel_reactivates_and_completes_shell(self):
        fixture = {**self.fixture, "observations": {"secondary:3:0": {"state": "found", "rank": 2}}}
        manifest = self.run_scan(config(max_shell=6), fixture)
        self.assertIn({"event": "positive_sentinel_reactivation", "sector": "E", "shell": 3}, manifest["events"])
        state = manifest["sectors"]["E"]
        self.assertEqual(("sampled_stop", 5, 6), (state["state"], state["last_full_shell"], state["sentinel_shell"]))
        actual = {(row["x"], row["y"], row["query_id"]) for row in self.rows()}
        for x, y in ag.shell_points(3, "E"):
            for query_id in ("primary", "secondary"):
                self.assertIn((x, y, query_id), actual)
        self.assertEqual(len(actual), manifest["accounting"]["attempted_calls"])
        state_data = json.loads((self.directory / "state.json").read_text())
        self.assertEqual("sentinel", state_data["ledger"]["secondary:3:0"]["stage"])

    def test_one_point_base_is_not_a_negative_sector_layer(self):
        manifest = self.run_scan(config(starting_grid=1))
        self.assertEqual("sampled_stop", manifest["status"])
        self.assertTrue(all(state["last_full_shell"] == 2 for state in manifest["sectors"].values()))

    def test_short_empty_and_errors_never_produce_sampled_stop(self):
        for index, outcome in enumerate(({"state": "not_returned", "returned_count": 2},
                                         {"state": "empty"}, {"state": "error"})):
            manifest = self.run_scan(fixture={"default": outcome}, directory=self.directory / str(index))
            self.assertEqual("unresolved", manifest["status"])
            self.assertEqual(18, manifest["accounting"]["attempted_calls"])
            self.assertTrue(all(state["state"] == "unresolved" for state in manifest["sectors"].values()))

    def test_inconclusive_query_at_sentinel_prevents_stop(self):
        fixture = {**self.fixture, "observations": {"secondary:3:0": {"state": "empty"}}}
        manifest = self.run_scan(fixture=fixture)
        self.assertEqual("unresolved_sentinel", manifest["sectors"]["E"]["state"])
        self.assertEqual("unresolved", manifest["status"])

    def test_positive_does_not_hide_error_in_same_layer(self):
        fixture = {**self.fixture, "observations": {"primary:1:0": {"state": "found"},
                                                    "secondary:1:0": {"state": "error"}}}
        manifest = self.run_scan(fixture=fixture)
        self.assertEqual("unresolved", manifest["sectors"]["E"]["state"])

    def test_dense_and_sparse_claim_only_their_sampled_bounds(self):
        for strategy, origins, status in (("dense", 49, "bounds_reached"), ("sparse", 25, "sampled_bounds")):
            manifest = self.run_scan(config(strategy=strategy), directory=self.directory / strategy)
            self.assertEqual(status, manifest["status"])
            self.assertEqual(origins, manifest["selected_origins"])
            self.assertEqual(origins * 2, manifest["accounting"]["attempted_calls"])

    def test_cap_before_sentinel_is_not_sampled_stop(self):
        manifest = self.run_scan(config(max_shell=2))
        self.assertEqual("bounds_reached", manifest["status"])
        self.assertTrue(all(state["sentinel_shell"] is None for state in manifest["sectors"].values()))

    def test_budget_whole_origin_stop_and_resume_without_rebilling(self):
        first = self.run_scan(ceiling=0.006)
        self.assertEqual("budget_stop", first["status"])
        self.assertEqual(2, first["accounting"]["attempted_calls"])
        self.assertEqual(0.004, first["accounting"]["accounted_usd"])
        self.assertEqual(16, first["state_counts"]["unmeasured"])
        self.assertFalse(first["complete_common_base"])
        second = self.run_scan(ceiling=0.132)
        self.assertEqual("sampled_stop", second["status"])
        self.assertEqual((2, 64, 66), (second["accounting"]["resumed_calls"], second["accounting"]["new_calls"],
                                     second["accounting"]["attempted_calls"]))
        saved = self.rows()
        third = self.run_scan(ceiling=0.132)
        self.assertEqual(0, third["accounting"]["new_calls"])
        self.assertEqual(saved, self.rows())

    def test_probe_and_backfill_spend_use_same_ceiling(self):
        first = self.run_scan(ceiling=0.1)
        self.assertEqual("budget_stop", first["status"])
        self.assertEqual(50, first["accounting"]["attempted_calls"])
        self.assertEqual(0.1, first["accounting"]["accounted_usd"])
        self.assertEqual(2, first["sectors"]["E"]["clean_layers"])
        second = self.run_scan(ceiling=0.104)
        self.assertEqual(52, second["accounting"]["attempted_calls"])
        self.assertEqual("sampled_stop", second["sectors"]["E"]["state"])
        positive = {**self.fixture, "observations": {"primary:3:0": {"state": "found"}}}
        result = self.run_scan(fixture=positive, ceiling=0.104, directory=self.directory / "positive")
        self.assertEqual("budget_stop", result["status"])
        self.assertEqual(52, result["accounting"]["attempted_calls"])
        self.assertEqual(1, len(result["events"]))
        self.assertGreater(result["state_counts"]["unmeasured"], 0)
        resumed = self.run_scan(fixture=positive, ceiling=1, directory=self.directory / "positive")
        self.assertEqual(52, resumed["accounting"]["resumed_calls"])
        self.assertEqual(0, resumed["state_counts"]["unmeasured"])
        self.assertEqual("bounds_reached", resumed["status"])

    def test_max_calls_cumulative_across_resume(self):
        first = self.run_scan(config(max_calls=3))
        second = self.run_scan(config(max_calls=3))
        self.assertEqual("budget_stop", first["status"])
        self.assertEqual(2, second["accounting"]["attempted_calls"])
        self.assertEqual(0, second["accounting"]["new_calls"])

    def test_actual_charge_counts_and_stops_before_next_call(self):
        fixture = {"default": {"state": "error", "cost_usd": 0.03}}
        first = self.run_scan(fixture=fixture, ceiling=0.02)
        self.assertEqual("reported_charge_exceeds_ceiling", first["reason"])
        self.assertEqual((1, 0.03), (first["accounting"]["attempted_calls"], first["accounting"]["accounted_usd"]))
        second = self.run_scan(fixture=fixture, ceiling=0.02)
        self.assertEqual("prior_spend_exceeds_ceiling", second["reason"])
        self.assertEqual(0, second["accounting"]["new_calls"])
        self.assertEqual(9, second["selected_origins"])
        self.assertEqual(17, second["state_counts"]["unmeasured"])

    def test_cache_mismatch_refuses_without_changing_saved_ledger(self):
        self.run_scan(ceiling=0.004)
        original = (self.directory / "state.json").read_bytes()
        for cfg, fixture in ((config(provider_zoom=12), self.fixture),
                             (config(targets=[{"cid": "456"}]), self.fixture),
                             (config(), {"default": {"state": "empty"}})):
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                self.run_scan(cfg, fixture)
            self.assertEqual(original, (self.directory / "state.json").read_bytes())

    def test_ledger_integrity_mismatch_fails_closed(self):
        self.run_scan(ceiling=0.004)
        path = self.directory / "state.json"
        saved = json.loads(path.read_text())
        saved["ledger"] = {}
        path.write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            self.run_scan()

    def test_interrupted_reservation_is_retained_and_not_retried(self):
        adapter = ag.ReplayAdapter(self.fixture)
        with patch.object(adapter, "fetch", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.run_scan(adapter=adapter)
        result = self.run_scan()
        self.assertEqual(1, result["accounting"]["resumed_calls"])
        self.assertEqual(1, result["state_counts"]["error"])
        self.assertEqual("unresolved", result["status"])
        row = next(row for row in self.rows() if row["state"] == "error")
        self.assertEqual("interrupted_request_unknown_outcome", row["error_code"])

    def test_missing_ledger_does_not_overwrite_acquisition_artifacts(self):
        path = self.directory / "manifest.json"
        path.write_text('{"existing":true}')
        with self.assertRaisesRegex(ValueError, "without a ledger"):
            self.run_scan()
        self.assertEqual('{"existing":true}', path.read_text())

    def test_invalid_reported_charge_halts_and_cannot_be_reset_by_resume(self):
        fixture = {"default": {"state": "not_returned", "cost_usd": "unknown"}}
        first = self.run_scan(fixture=fixture)
        second = self.run_scan(fixture=fixture)
        self.assertEqual("unknown_reported_charge", first["reason"])
        self.assertEqual("unknown_reported_charge", second["reason"])
        self.assertEqual(1, second["accounting"]["attempted_calls"])
        self.assertEqual(0, second["accounting"]["new_calls"])

    def test_transport_exception_is_sanitized_and_never_negative(self):
        adapter = ag.ReplayAdapter(self.fixture)
        with patch.object(adapter, "fetch", side_effect=RuntimeError("sensitive-provider-detail")):
            result = self.run_scan(adapter=adapter)
        self.assertEqual("unresolved", result["status"])
        self.assertEqual(18, result["accounting"]["attempted_calls"])
        self.assertNotIn("sensitive-provider-detail", (self.directory / "state.json").read_text())
        self.assertTrue(all(row["state"] == "error" for row in self.rows()))

    def test_lock_prevents_concurrent_ledger_changes(self):
        with ag.RunLock(self.directory), self.assertRaisesRegex(ValueError, "locked"):
            self.run_scan()
        self.assertFalse((self.directory / "state.json").exists())

    def test_report_contract_and_jsonl_agree(self):
        self.run_scan()
        jsonl = [json.loads(line) for line in (self.directory / "observations.jsonl").read_text().splitlines()]
        self.assertEqual(self.rows(), jsonl)
        required = {"query_id", "lat", "lng", "rank", "state", "returned_count", "depth", "sampled_at", "source"}
        for row in jsonl:
            self.assertTrue(required <= row.keys())
            self.assertTrue(row["rank"] is None or type(row["rank"]) is int and row["rank"] > 0)

    def test_response_digest_links_each_row_to_original_source_and_survives_resume(self):
        cfg = config()
        adapter = ag.ReplayAdapter(self.fixture)
        self.run_scan(cfg, adapter=adapter)
        ledger = json.loads((self.directory / "state.json").read_text())["ledger"]
        for row in self.rows():
            query = next(q for q in cfg["queries"] if q["id"] == row["query_id"])
            payload, _ = adapter.fetch(cfg, query, row["x"], row["y"])
            provenance = row["provenance"]
            entry = ledger[ag.observation_key(query["id"], row["x"], row["y"])]
            self.assertEqual(ag.digest(payload), provenance["response_sha256"])
            self.assertEqual(entry["response_sha256"], provenance["response_sha256"])
            self.assertEqual(entry["request_fingerprint"], provenance["request_fingerprint"])
            self.assertEqual("synthetic-replay", row["source"])
        previous = (self.directory / "observations.json").read_bytes()
        self.run_scan(cfg, adapter=adapter)
        self.assertEqual(previous, (self.directory / "observations.json").read_bytes())

    def test_raw_provider_details_are_hashed_without_copying_into_outputs(self):
        payload = response(items(), internal_note="private-provider-field")
        self.run_scan(fixture={"default": {"response": payload}})
        for path in self.directory.glob("*.json*"):
            self.assertNotIn("private-provider-field", path.read_text())
        self.assertEqual(ag.digest(payload), self.rows()[0]["provenance"]["response_sha256"])

    def test_failed_transport_has_request_provenance_without_invented_response(self):
        adapter = ag.ReplayAdapter(self.fixture)
        with patch.object(adapter, "fetch", side_effect=OSError("unavailable")):
            self.run_scan(adapter=adapter)
        row = self.rows()[0]
        self.assertEqual("error", row["state"])
        self.assertEqual(64, len(row["provenance"]["request_fingerprint"]))
        self.assertIsNone(row["provenance"]["response_sha256"])


class CliTests(unittest.TestCase):
    def test_offline_default_and_spend_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            path = directory / "config.json"
            path.write_text(json.dumps(config()), encoding="utf-8")
            with patch.object(ag.runner, "call_dataforseo_live_task", side_effect=AssertionError("network")), \
                    patch.object(ag.runner, "http_json", side_effect=AssertionError("provider transport")):
                with patch("builtins.print"):
                    self.assertEqual(0, ag.main(["--config", str(path), "--output-dir", str(directory)]))
                    self.assertEqual(2, ag.main(["--config", str(path), "--execute", "--output-dir", str(directory)]))
                self.assertFalse((directory / "state.json").exists())
                self.assertEqual("offline-plan", json.loads((directory / "plan.json").read_text())["status"])

    def test_replay_does_not_access_authentication_or_network(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(ag.runner, "call_dataforseo_live_task", side_effect=AssertionError("network")), \
                    patch.object(ag.runner, "http_json", side_effect=AssertionError("provider transport")), \
                    patch("builtins.print"):
                result = ag.main(["--config", str(ROOT / "examples/adaptive/sample.json"),
                                  "--replay", str(ROOT / "examples/adaptive/replay.json"), "--output-dir", temp])
            self.assertEqual(0, result)
            manifest = json.loads((Path(temp) / "manifest.json").read_text())
            self.assertEqual("synthetic-replay", manifest["source"])
            self.assertEqual("positive_sentinel_reactivation", manifest["events"][0]["event"])

    def test_live_adapter_reuses_existing_runner(self):
        cfg = config()
        adapter = ag.LiveAdapter()
        with patch.object(ag.runner, "call_dataforseo_live_task", return_value=response(items())) as call:
            payload, timestamp = adapter.fetch(cfg, cfg["queries"][0], 0, 0)
        call.assert_called_once_with(ag.request_task(cfg, cfg["queries"][0], 0, 0), cfg["timeout_seconds"])
        self.assertEqual(20000, payload["status_code"])
        self.assertIsInstance(timestamp, str)

    def test_script_entry_point(self):
        with tempfile.TemporaryDirectory() as temp:
            process = subprocess.run([sys.executable, str(ROOT / "tools/adaptive_geogrid.py"),
                                      "--config", str(ROOT / "examples/adaptive/sample.json"),
                                      "--output-dir", temp], capture_output=True, text=True)
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual("offline-plan", json.loads(process.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
