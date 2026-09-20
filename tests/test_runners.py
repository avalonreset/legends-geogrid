from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
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
    parse_args as bulk_args,
    load_prospects,
    validate_scan,
)
from local_heatmap_poc import (  # noqa: E402
    calculate_metrics,
    domain_matches,
    estimate_scan_cost,
    generate_grid,
    parse_results,
    prospecting_verdict,
    validate_run_args,
    parse_args as single_args,
    build_tasks,
    match_score,
    write_outputs,
    call_dataforseo_live,
    call_dataforseo_standard,
    RANK_BASIS,
)
from report_builder import target_matches, load_measurement, write_png


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


class MeasurementTests(unittest.TestCase):
    def args(self, *extra):
        return single_args(['--keyword', 'hvac contractor', '--target-name', 'Example HVAC',
                            '--center-lat', '38', '--center-lng', '-121', '--grid-size', '1',
                            '--depth', '20', *extra])

    def result(self, items, status=20000, **overrides):
        args = self.args()
        for key, value in overrides.items():
            setattr(args, key, value)
        points = generate_grid(38, -121, 1, 2)
        return parse_results({'tasks': [{'status_code': status, 'data': {'tag': 'r0c0'},
                                        'result': [{'items': items}]}]}, points, args)[0]

    def test_explicit_viewport_flag_preserves_default_and_can_disable(self):
        for flags, expected in [((), True), (('--no-search-this-area',), False)]:
            args = self.args(*flags)
            self.assertEqual(expected, build_tasks(args, generate_grid(38, -121, 1, 2))[0]['search_this_area'])

    def test_zoom_provider_boundaries(self):
        for zoom in (3, 21):
            validate_run_args(self.args('--zoom', str(zoom)))
        for zoom in (0, 2, 22, 23):
            with self.assertRaises(ValueError):
                validate_run_args(self.args('--zoom', str(zoom)))

    def test_identifiers_cannot_fall_back_to_name_or_domain(self):
        args = self.args('--target-cid', '123', '--target-place-id', 'Place-A', '--target-domain', 'example.com')
        for fields in ({}, {'cid': '999', 'place_id': 'Place-A'}, {'cid': '123', 'place_id': 'Place-B'}):
            item = {'title': 'Example HVAC', 'domain': 'example.com', **fields}
            self.assertEqual(0, match_score(item, args))
            self.assertFalse(target_matches(item, 'Example HVAC', '123', 'Place-A'))
        self.assertEqual(1, match_score({'cid': '123', 'place_id': 'Place-A', 'title': 'Renamed'}, args))

    def test_empty_title_does_not_match_every_business(self):
        self.assertEqual(0, match_score({'title': ''}, self.args()))

    def test_organic_group_rank_excludes_both_paid_item_shapes(self):
        ads = [
            {'type': 'maps_paid_item', 'title': 'Example HVAC', 'cid': '123', 'rank_group': 1, 'rank_absolute': 1},
            {'type': 'maps_search', 'is_paid': True, 'title': 'Example HVAC', 'cid': '123', 'rank_group': 2, 'rank_absolute': 2},
        ]
        organic = {'type': 'maps_search', 'title': 'Example HVAC', 'cid': '123', 'rank_group': 1, 'rank_absolute': 3}
        result = self.result([*ads, organic], target_cid='123')
        self.assertEqual(1, result.rank)
        self.assertEqual((1,), result.observed_ranks)
        self.assertEqual(3, result.returned_items_count)
        self.assertEqual(1, result.organic_items_count)
        self.assertEqual(1, len(result.top_items))
        self.assertEqual(3, result.matched_item['rank_absolute'])
        self.assertEqual('no_organic_results', self.result(ads, target_cid='123').status)
        self.assertIsNone(self.result(ads, target_cid='123').rank)

    def test_absolute_position_does_not_substitute_for_missing_group_rank(self):
        result = self.result([{'type': 'maps_search', 'title': 'Example HVAC', 'rank_absolute': 3}])
        self.assertIsNone(result.rank)
        self.assertEqual((), result.observed_ranks)

    def test_status_and_denominators_separate_unknown_from_negative(self):
        found = self.result([{'title': 'Example HVAC', 'rank_group': 1, 'rank_absolute': 1}])
        short = self.result([{'title': 'Competitor', 'rank_group': 1, 'rank_absolute': 1}])
        empty = self.result([])
        error = self.result([], status=50000)
        full = self.result([{'title': 'Competitor', 'rank_group': n, 'rank_absolute': n} for n in range(1, 21)])
        sparse = self.result([{'title': 'Competitor', 'rank_group': 20, 'rank_absolute': 20}])
        self.assertEqual(['found', 'not_returned_incomplete', 'empty_results', 'provider_error',
                          'not_returned_depth_reached', 'not_returned_incomplete'],
                         [r.status for r in (found, short, empty, error, full, sparse)])
        metrics = calculate_metrics([found, short, empty, error, full, sparse])
        self.assertEqual(2, metrics['top3_eligible_points'])
        self.assertEqual(50, metrics['solv'])
        self.assertEqual(3, metrics['not_found_points'])
        self.assertEqual(1, metrics['empty_result_points'])
        self.assertIsNone(calculate_metrics([empty, short])['solv'])

    def test_successful_empty_array_is_not_provider_failure(self):
        args = self.args()
        result = parse_results({'tasks': [{'status_code': 20000, 'result': []}]},
                               generate_grid(38, -121, 1, 2), args)[0]
        self.assertEqual('empty_results', result.status)
        self.assertIsNone(result.error)

    def test_explicit_no_search_results_is_empty_and_nearby_error_remains_error(self):
        task = {'status_code': 40102, 'status_message': 'No Search Results.', 'cost': 0.002,
                'result_count': 1, 'data': {'keyword': 'hvac', 'tag': 'r0c0'},
                'result': [{'se_results_count': 0, 'items_count': 0, 'items': None}]}
        response = {'status_code': 20000, 'cost': 0.002, 'tasks_error': 0, 'tasks': [task]}
        points = generate_grid(38, -121, 1, 2)
        result = parse_results(response, points, self.args())[0]
        self.assertEqual('empty_results', result.status)
        self.assertIsNone(result.error)
        self.assertEqual(0, calculate_metrics([result])['error_points'])
        self.assertEqual('provider_error', self.result([], status=40101).status)
        with patch('local_heatmap_poc.call_dataforseo_live_task', return_value=response):
            live = call_dataforseo_live([{'tag': 'r0c0'}], timeout=1)
        self.assertEqual(0, live['tasks_error'])
        self.assertEqual(0.002, live['cost'])
        posted = {'tasks': [{'id': 'empty-task', 'status_code': 20100, 'cost': 0.0006}]}
        with patch('local_heatmap_poc.http_json', side_effect=[posted, response]):
            queue = call_dataforseo_standard([{'tag': 'r0c0'}], timeout=1, poll_seconds=2, poll_interval=1)
        self.assertEqual(0, queue['tasks_error'])
        self.assertEqual(40102, queue['tasks'][0]['status_code'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.json'
            path.write_text(json.dumps(response), encoding='utf-8')
            self.assertEqual(([], 'hvac'), load_measurement(path)[:2])
            self.assertIsNone(load_measurement(path)[3])

    def test_unknown_tag_does_not_land_on_wrong_coordinate(self):
        result = parse_results({'tasks': [{'status_code': 20000, 'data': {'tag': 'other'},
                                         'result': []}]}, generate_grid(38, -121, 1, 2), self.args())[0]
        self.assertEqual('missing_result', result.status)

    def test_bulk_false_override_and_measurement_cache_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.csv'
            path.write_text('business_name,keyword,lat,lng,search_this_area,search_places\n'
                            'Example HVAC,hvac contractor,38,-121,false,false\n', encoding='utf-8')
            args = bulk_args(['--prospects', str(path), '--search-places'])
            scan = load_prospects(args)[0]
            self.assertFalse(scan.search_this_area)
            self.assertFalse(scan.search_places)
            command = local_runner_command(scan, 'standard', Path(directory), args)
            self.assertIn('--no-search-this-area', command)
            for change in ({'search_this_area': True}, {'zoom': 13}, {'target_cid': '123'},
                           {'match_threshold': 0.9}, {'top_competitors': 10}):
                self.assertNotEqual(fingerprint_scan(scan, 'standard'),
                                    fingerprint_scan(replace(scan, **change), 'standard'))
            with self.assertRaises(ValueError):
                validate_scan(replace(scan, zoom=22))

    def test_parsed_and_human_reports_record_contract_and_states(self):
        args = self.args('--no-search-this-area', '--target-cid', '123')
        result = self.result([{'title': 'Competitor', 'rank_group': 1, 'rank_absolute': 1}])
        with tempfile.TemporaryDirectory() as directory:
            args.output_dir = directory
            outputs = write_outputs(args, build_tasks(args, [result.point]), {'tasks': []}, [result])
            parsed = json.loads(Path(outputs['parsed_json']).read_text(encoding='utf-8'))
            self.assertFalse(parsed['measurement_settings']['search_this_area'])
            self.assertEqual(RANK_BASIS, parsed['measurement_settings']['rank_basis'])
            self.assertEqual('123', parsed['measurement_settings']['target_cid'])
            self.assertEqual('not_returned_incomplete', parsed['results'][0]['status'])
            self.assertEqual(1, parsed['results'][0]['returned_items_count'])
            for key in ('html', 'markdown'):
                report = Path(outputs[key]).read_text(encoding='utf-8')
                self.assertIn('search_this_area', report)
                self.assertIn('not_returned_incomplete', report)
                self.assertIn('Measurement needs calibration', report)

    def test_report_loader_does_not_treat_error_payload_as_rank_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'point.json'
            path.write_text(json.dumps({'tasks': [{'status_code': 50000, 'status_message': 'failure',
                                                  'result': [{'items': [{'title': 'Example HVAC'}]}]}]}), encoding='utf-8')
            items, _, _, error = load_measurement(path)
            self.assertEqual([], items)
            self.assertEqual('failure', error)

    def test_report_and_verifier_use_exact_id_and_reject_wrong_pin_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_png(root / 'base.png', 200, 200, bytes([80, 80, 80]) * 40000)
            (root / 'points.txt').write_text('1 38 -121\n')
            (root / 'probe_1.json').write_text(json.dumps({'tasks': [{'status_code': 20000,
                'data': {'keyword': 'hvac', 'search_this_area': True, 'depth': 20},
                'result': [{'items': [
                    {'type': 'maps_paid_item', 'title': 'Example HVAC', 'rank_group': 1, 'rank_absolute': 1, 'cid': '123'},
                    {'type': 'maps_search', 'is_paid': True, 'title': 'Example HVAC', 'rank_group': 2, 'rank_absolute': 2, 'cid': '123'},
                    {'type': 'maps_search', 'title': 'Example HVAC', 'rank_group': 1, 'rank_absolute': 3, 'cid': 'lookalike'},
                    {'type': 'maps_search', 'title': 'Example HVAC', 'rank_group': 2, 'rank_absolute': 4, 'cid': '123'}]}]}]}), encoding='utf-8')
            config = {'business': 'Example HVAC', 'center': [38, -121], 'base_png': str(root / 'base.png'),
                      'out_dir': str(root / 'maps'), 'out_html': str(root / 'report.html'),
                      'grids': [{'label': 'HVAC', 'keyword': 'hvac', 'dir': str(root), 'prefix': 'probe',
                                 'points': str(root / 'points.txt')}]}
            (root / 'config.json').write_text(json.dumps(config), encoding='utf-8')
            common = ['--config', str(root / 'config.json'), '--target', 'Example HVAC',
                      '--target-cid', '123', '--category', 'hvac']
            build = subprocess.run([sys.executable, str(TOOLS / 'report_builder.py'), *common],
                                   capture_output=True, text=True)
            self.assertEqual(0, build.returncode, build.stderr)
            verify_command = [sys.executable, str(TOOLS / 'verify_pins.py'), *common,
                              '--html', str(root / 'report.html')]
            verified = subprocess.run(verify_command, capture_output=True, text=True)
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
            report = (root / 'report.html').read_text(encoding='utf-8')
            self.assertIn('search_this_area', report)
            self.assertNotIn('20+', report)
            self.assertIn('class="pin">2</text>', report)
            (root / 'report.html').write_text(report.replace('class="pin">2</text>',
                                                            'class="pin">1</text>'), encoding='utf-8')
            tampered = subprocess.run(verify_command, capture_output=True, text=True)
            self.assertNotEqual(0, tampered.returncode)
            self.assertIn('FAIL HVAC pin ranks and coordinates', tampered.stdout)
            # The provider can explicitly report no results using 40102. That is
            # an empty measured response, and must not fail the verifier as an error.
            (root / 'probe_1.json').write_text(json.dumps({'tasks': [{'status_code': 40102,
                'status_message': 'No Search Results.', 'data': {'keyword': 'hvac'},
                'result': [{'items': None, 'items_count': 0}]}]}), encoding='utf-8')
            # A new acquisition gets fresh deliverable paths; preserve the
            # earlier exact-ID/tamper evidence under the no-clobber contract.
            config['out_dir'] = str(root / 'empty-maps')
            config['out_html'] = str(root / 'empty-report.html')
            (root / 'config.json').write_text(json.dumps(config), encoding='utf-8')
            verify_command[-1] = config['out_html']
            rebuilt = subprocess.run([sys.executable, str(TOOLS / 'report_builder.py'), *common],
                                     capture_output=True, text=True)
            self.assertEqual(0, rebuilt.returncode, rebuilt.stderr)
            self.assertEqual(report.replace('class="pin">2</text>', 'class="pin">1</text>'),
                             (root / 'report.html').read_text(encoding='utf-8'))
            empty_verified = subprocess.run(verify_command, capture_output=True, text=True)
            self.assertEqual(0, empty_verified.returncode, empty_verified.stdout + empty_verified.stderr)
            failed = json.loads((root / 'probe_1.json').read_text())
            failed['tasks'][0]['status_code'] = 40101
            (root / 'probe_1.json').write_text(json.dumps(failed), encoding='utf-8')
            error_verified = subprocess.run(verify_command, capture_output=True, text=True)
            self.assertNotEqual(0, error_verified.returncode)
            self.assertIn('FAIL probe_1.json provider status', error_verified.stdout)


if __name__ == "__main__":
    unittest.main()
