"""Independent, offline release acceptance; fixtures are entirely fictional.

Run: python -m unittest discover -s tests -p test_release_pipeline.py -v
Failures are release findings, not expected failures. No provider calls occur.
Install requirements-report.txt before running this release gate; missing
modules or PDF dependencies are failures, never skipped acceptance checks.
"""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import bulk_geogrid_runner as bulk
import local_heatmap_poc as local
import report_builder as legacy


def arguments(name="Cedar Bicycle Workshop", **overrides):
    args = local.parse_args(["--target-name", name, "--keyword", "bicycle repair",
                             "--center-lat", "38", "--center-lng", "-100"])
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def response(point, items, code=20000):
    return {"status_code": code, "data": {"tag": point.tag},
            "result": [{"items": items}]}


def item(rank, cid="other", title="Other Bicycle Workshop", **extra):
    return {"type": "maps_search", "rank_group": rank, "cid": cid,
            "title": title, **extra}


def legacy_fixture(root, *, edge=False, prefix="probe"):
    """Synthetic 200px image and provider-shaped JSON, with no external assets."""
    root.mkdir(parents=True, exist_ok=True)
    legacy.write_png(root / "base.png", 200, 200, bytes([80, 80, 80]) * 40000)
    lng = -100 + ((95 * 360 / (256 * 2**12)) if edge else 0)
    (root / "points.txt").write_text(f"1 38 {lng}\n", encoding="utf-8")
    raw = {"tasks": [{"status_code": 20000, "data": {"keyword": "bicycle repair"},
                     "result": [{"items": [item(1, "cedar", "Cedar Bicycle Workshop")]}]}]}
    (root / f"{prefix}_1.json").write_text(json.dumps(raw), encoding="utf-8")
    cfg = {"business": "Cedar Bicycle Workshop", "center": [38, -100],
           "base_png": str(root / "base.png"), "out_dir": str(root / "maps"),
           "out_html": str(root / "report.html"),
           "grids": [{"label": "Bicycle", "keyword": "bicycle repair",
                      "dir": str(root), "prefix": prefix, "points": str(root / "points.txt")}]}
    path = root / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    common = ["--config", str(path), "--target", "Cedar Bicycle Workshop",
              "--target-cid", "cedar", "--category", "bicycle"]
    return cfg, common


class ReleasePipelineAcceptance(unittest.TestCase):
    def test_two_contrasting_synthetic_fixtures_reconcile(self):
        """Dense successful workshop and sparse polar marine service, exact oracles."""
        with tempfile.TemporaryDirectory() as directory:
            for name, lat, lng, mode in (("Cedar Bicycle Workshop", 38, -100, "dense"),
                                         ("Polar Marine Service", 72, 179.99, "sparse")):
                with self.subTest(fixture=name):
                    args = arguments(name, center_lat=lat, center_lng=lng, grid_size=3,
                                     radius_km=.1, target_cid="fixture-target", depth=10,
                                     keyword="bicycle repair" if mode == "dense" else "marine repair",
                                     output_dir=str(Path(directory) / mode))
                    points = local.generate_grid(lat, lng, 3, .1)
                    if mode == "dense":
                        tasks = [response(p, [item(1, "fixture-target", name)]) for p in points]
                        expected = (9, 9, 9, 9, 100.0, 0)
                    else:
                        tasks = [response(points[0], [item(4, "fixture-target", name)]),
                                 response(points[1], [item(n) for n in range(1, 11)]),
                                 response(points[2], [item(1), item(2)]),
                                 response(points[3], []), response(points[4], [], 50000),
                                 response(points[5], [item(1, is_paid=True)]),
                                 response(points[6], [item(1, "fixture-target", name)]),
                                 response(points[7], [item(1), item(2), item(3)])]
                        expected = (9, 2, 3, 4, 25.0, 2)
                    payload = {"tasks": tasks}
                    results = local.parse_results(payload, points, args)
                    metrics = local.calculate_metrics(results)
                    actual = tuple(metrics[k] for k in ("points", "found_points", "visible_eligible_points",
                                                        "top3_eligible_points", "solv", "error_points"))
                    self.assertEqual(expected, actual)
                    with patch.object(local, "http_json", side_effect=AssertionError("Network forbidden")):
                        outputs = local.write_outputs(args, local.build_tasks(args, points), payload, results)
                    parsed = json.loads(Path(outputs["parsed_json"]).read_text(encoding="utf-8"))
                    self.assertEqual(metrics, parsed["metrics"])
                    self.assertEqual(9, len(parsed["results"]))
                    self.assertEqual("fixture-target", parsed["measurement_settings"]["target_cid"])
                    if mode == "sparse":
                        self.assertIn("Incomplete scan", Path(outputs["markdown"]).read_text())

    def test_domain_only_multilocation_is_not_silently_a_single_branch(self):
        args = arguments(target_domain="cedar.example", target_name="Cedar")
        point = local.generate_grid(38, -100, 1, 1)[0]
        branches = [item(1, "north", "Cedar North", domain="cedar.example"),
                    item(8, "south", "Cedar South", domain="cedar.example")]
        result = local.parse_results({"tasks": [response(point, branches)]}, [point], args)[0]
        self.assertIsNone(result.rank, "Two branches share a domain; require an ID or report ambiguous matching")

    def test_exact_target_with_missing_rank_cannot_certify_absence(self):
        args = arguments(target_cid="fixture-target", depth=3)
        point = local.generate_grid(38, -100, 1, 1)[0]
        items = [item(None, "fixture-target")] + [item(rank) for rank in (1, 2, 3)]
        result = local.parse_results({"tasks": [response(point, items)]}, [point], args)[0]
        metrics = local.calculate_metrics([result])
        self.assertIsNone(result.rank)
        self.assertEqual(0, metrics["top3_eligible_points"],
                         "A matched target without a rank is unresolved, not a complete negative")
        self.assertIsNone(metrics["solv"])
        self.assertNotEqual("not_returned_depth_reached", result.status)

    def test_legacy_query_diagnostic_cannot_pass_provider_error(self):
        import pollution_gate
        payload = {"status_code": 20000, "tasks": [
            {"status_code": 50000, "status_message": "Synthetic provider failure", "result": None}
        ]}
        argv = ["pollution_gate.py", "--keyword", "bicycle repair",
                "--points", "38,-100", "--category", "bicycle"]
        with patch.object(sys, "argv", argv), patch.dict("os.environ", {
                "DATAFORSEO_LOGIN": "synthetic-fixture", "DATAFORSEO_PASSWORD": "synthetic-fixture"}), \
                patch.object(pollution_gate, "post", return_value=payload), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            result = pollution_gate.main()
        self.assertNotEqual(0, result,
                            "A provider failure must not pass the legacy query diagnostic: " + output.getvalue())

    def test_verifier_cannot_certify_missing_target_rank_as_not_returned(self):
        import verify_pins
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root)
            path = root / "probe_1.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["tasks"][0]["result"][0]["items"][0]["rank_group"] = None
            path.write_text(json.dumps(raw), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    legacy.main(common)
                except ValueError:
                    return  # Reject malformed rank evidence before publishing.
                result = verify_pins.main(common + ["--html", cfg["out_html"]])
            self.assertNotEqual(0, result,
                                "Exact target is present without a rank, but its NR pin received ALL_OK")

    def test_same_second_outputs_do_not_overwrite_another_keyword(self):
        class Frozen(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 1, 2, 3, 4, 5, tzinfo=tz)
        with tempfile.TemporaryDirectory() as directory, patch.object(local.dt, "datetime", Frozen):
            args = arguments(output_dir=directory, grid_size=1)
            first = local.write_outputs(args, [], {"tasks": []}, [])
            args.keyword = "bicycle wheel repair"
            second = local.write_outputs(args, [], {"tasks": []}, [])
            self.assertNotEqual(first["parsed_json"], second["parsed_json"])
            self.assertEqual("bicycle repair", json.loads(Path(first["parsed_json"]).read_text())["keyword"])

    def test_missing_cached_artifact_requires_reacquisition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv = root / "prospects.csv"
            csv.write_text("business_name,keyword,lat,lng\nCedar Bicycle Workshop,bicycle repair,38,-100\n")
            argv = ["--prospects", str(csv), "--output-root", str(root / "out"), "--run-id", "cache-check"]
            args = bulk.parse_args(argv)
            scan = bulk.load_prospects(args)[0]
            fp = bulk.fingerprint_scan(scan, args.method)
            bulk.write_json(root / "out" / "cache-index.json", {"entries": {fp: {
                "generated_at": bulk.utc_now(), "identity": bulk.scan_identity(scan, args.method),
                "outputs": {"parsed_json": str(root / "missing.json")}}}})
            with contextlib.redirect_stdout(io.StringIO()), patch.object(bulk.subprocess, "run", side_effect=AssertionError("No paid execution")):
                self.assertEqual(0, bulk.main(argv))
            manifest = json.loads((root / "out" / "cache-check" / "manifest.json").read_text())
            self.assertEqual("pending", manifest["rows"][0]["cache_status"])

    def test_generated_geography_stays_valid_at_dateline(self):
        points = local.generate_grid(72, 179.99, 3, 2)
        self.assertTrue(all(-180 <= p.lng <= 180 and -90 < p.lat < 90 for p in points),
                        [(p.lat, p.lng) for p in points])

    def test_nonfinite_radius_rejected_before_requests(self):
        args = arguments(radius_km=float("nan"))
        with self.assertRaises(ValueError):
            local.validate_run_args(args)
            local.generate_grid(args.center_lat, args.center_lng, 3, args.radius_km)

    def test_projection_wraps_dateline(self):
        x, y = legacy.project(72, -179.99, 72, 179.99, 12, 640, 480)
        self.assertAlmostEqual(320 + 256 * 2**12 * .02 / 360, x, places=6)
        self.assertEqual(240, y)

    def test_fixed_basemap_pin_offsets_change_with_physical_radius(self):
        offsets = []
        for radius in (1, 4):
            args = arguments(radius_km=radius, grid_size=3, zoom=15, map_image="same-basemap.png")
            results = [local.PointResult(p, 1, None, [], status="found")
                       for p in local.generate_grid(38, -100, 3, radius)]
            document = local.render_html(args, results, Path("report.md"))
            offsets.append(re.findall(r'style="left:([\d.]+)%;top:([\d.]+)%;"', document))
        self.assertTrue(offsets[0] and offsets[1])
        self.assertNotEqual(offsets[0], offsets[1], "1km and 4km grids use identical positions on the same fixed basemap")

    def test_verifier_rejects_marker_clipped_by_image_edge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root, edge=True)
            built = subprocess.run([sys.executable, str(TOOLS / "report_builder.py"), *common], capture_output=True, text=True)
            self.assertNotEqual(0, built.returncode, "Builder must refuse clipped evidence before writing")
            self.assertFalse(Path(cfg['out_html']).exists())
            # Independently forge the old invalid artifact: verifier must still
            # reject it even though the corrected builder cannot produce it.
            width, height, base = legacy.read_png_rgb(root / 'base.png')
            painted = bytearray(base)
            legacy.circle(painted, width, height, 195, 100, 18, legacy.GREEN, legacy.GOLD)
            Path(cfg['out_dir']).mkdir()
            legacy.write_png(Path(cfg['out_dir']) / 'probe.png', width, height, painted)
            Path(cfg['out_html']).write_text('<div class="mapwrap"><img class="map" src="maps/probe.png">'
                '<svg viewBox="0 0 200 200"><text x="195.0" y="100.0" class="rk1">1</text></svg></div>')
            verified = subprocess.run([sys.executable, str(TOOLS / "verify_pins.py"), *common,
                                       "--html", cfg["out_html"]], capture_output=True, text=True)
            self.assertNotEqual(0, verified.returncode, "Clipped 20px marker centered at x=195 on a 200px image:\n" + verified.stdout)
            self.assertIn('FAIL Bicycle full marker bounds', verified.stdout)

    def test_legacy_percent_styles_are_valid_css(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, common = legacy_fixture(Path(directory))
            built = subprocess.run([sys.executable, str(TOOLS / "report_builder.py"), *common], capture_output=True, text=True)
            self.assertEqual(0, built.returncode, built.stderr)
            self.assertFalse("100%%" in Path(cfg["out_html"]).read_text(encoding="utf-8"),
                             "Generated styles contain invalid width:100%% and height:100%%")

    def test_legacy_prefix_cannot_escape_map_output_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            cfg, common = legacy_fixture(root, prefix="../escaped")
            built = subprocess.run([sys.executable, str(TOOLS / "report_builder.py"), *common], capture_output=True, text=True)
            self.assertFalse((root / "escaped.png").exists(),
                             "Grid prefix traversed out of configured map directory")

    def test_legacy_client_html_has_no_absolute_workspace_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, common = legacy_fixture(Path(directory))
            built = subprocess.run([sys.executable, str(TOOLS / "report_builder.py"), *common], capture_output=True, text=True)
            self.assertEqual(0, built.returncode, built.stderr)
            self.assertFalse(directory in Path(cfg["out_html"]).read_text(encoding="utf-8"),
                             "Client HTML contains the operator's absolute output path")

    def test_png_average_filter_decodes_without_silent_corruption(self):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        # RGB [80,80,80], [100,100,100]: Average prediction for second pixel is 40.
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0)) +
               chunk(b"IDAT", zlib.compress(bytes([3, 80, 80, 80, 60, 60, 60]))) + chunk(b"IEND", b""))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "average.png"
            path.write_bytes(png)
            self.assertEqual(bytes([80, 80, 80, 100, 100, 100]), legacy.read_png_rgb(path)[2])

    def test_report_estimate_includes_depth_billing_units(self):
        args = arguments(depth=101, grid_size=1)
        point = local.generate_grid(38, -100, 1, 1)[0]
        result = local.PointResult(point, 1, None, [], status="found")
        report = local.render_markdown(args, [result], {}, "synthetic")
        self.assertIn("$0.0040 live", report)

    def test_competitor_top_three_uses_rank_not_list_position(self):
        point = local.generate_grid(38, -100, 1, 1)[0]
        result = local.PointResult(point, None, None, [{"rank": 8, "title": "Eighth Workshop"}],
                                   status="not_returned_incomplete")
        self.assertEqual([], local.competitor_counts([result]))


class LegacyReportFixAcceptance(unittest.TestCase):
    def run_tool(self, name, common, *extra):
        return subprocess.run([sys.executable, str(TOOLS / name), *common, *extra],
                              capture_output=True, text=True)

    def save_config(self, root, cfg):
        (root / 'config.json').write_text(json.dumps(cfg), encoding='utf-8')

    def test_existing_reports_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root)
            first = self.run_tool('report_builder.py', common)
            self.assertEqual(0, first.returncode, first.stderr)
            paths = [Path(cfg['out_html']), Path(cfg['out_dir']) / 'probe.png']
            originals = [path.read_bytes() for path in paths]
            cfg['business'] = 'Different business'
            self.save_config(root, cfg)
            second = self.run_tool('report_builder.py', common)
            self.assertNotEqual(0, second.returncode)
            self.assertIn('no overwrite', second.stderr)
            self.assertEqual(originals, [path.read_bytes() for path in paths])

    def test_later_invalid_grid_publishes_no_partial_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root)
            cfg['grids'].append({**cfg['grids'][0], 'prefix': '../escape'})
            self.save_config(root, cfg)
            result = self.run_tool('report_builder.py', common)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(Path(cfg['out_html']).exists())
            self.assertFalse(Path(cfg['out_dir']).exists())
            cfg['grids'][1]['prefix'] = 'probe'
            self.save_config(root, cfg)
            duplicate = self.run_tool('report_builder.py', common)
            self.assertNotEqual(0, duplicate.returncode)
            self.assertIn('Duplicate output', duplicate.stderr)

    def test_html_copy_and_portable_asset_paths_are_escaped_and_verify(self):
        from urllib.parse import unquote
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root)
            cfg.update(business='<script>alert("copy")</script>', subtitle='<img src=x onerror=bad>',
                       out_dir=str(root / 'maps & tiles #1'), attribution='Owner & <credit>')
            cfg['grids'][0].update(label='Bicycle & <service>', demand='<b>untrusted</b>')
            self.save_config(root, cfg)
            result = self.run_tool('report_builder.py', common)
            self.assertEqual(0, result.returncode, result.stderr)
            html = Path(cfg['out_html']).read_text(encoding='utf-8')
            self.assertNotIn('<script>', html)
            self.assertNotIn('<img src=x', html)
            self.assertIn('Bicycle &amp; &lt;service&gt;', html)
            self.assertIn('Owner &amp; &lt;credit&gt;', html)
            src = re.search(r'<img class="map" src="([^"]+)"', html)[1]
            self.assertEqual('maps%20%26%20tiles%20%231/probe.png', src)
            self.assertTrue((root / unquote(src)).is_file())
            self.assertNotIn(directory, html)
            verified = self.run_tool('verify_pins.py', common, '--html', cfg['out_html'])
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)

    def test_provider_metadata_and_error_text_are_not_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root)
            rawpath = root / 'probe_1.json'
            raw = json.loads(rawpath.read_text())
            task = raw['tasks'][0]
            task['data'].update(tag='SHOULD_STAY_LOCAL', postback_url='https://example.invalid/SHOULD_STAY_LOCAL',
                                authorization='SHOULD_STAY_LOCAL', nested={'private': 'SHOULD_STAY_LOCAL'}, depth=20)
            task['path'] = ['SHOULD_STAY_LOCAL']
            task.update(status_code=50000, status_message='SHOULD_STAY_LOCAL')
            rawpath.write_text(json.dumps(raw))
            result = self.run_tool('report_builder.py', common)
            self.assertEqual(0, result.returncode, result.stderr)
            html = Path(cfg['out_html']).read_text(encoding='utf-8')
            self.assertNotIn('SHOULD_STAY_LOCAL', html)
            self.assertIn('Provider task failed', html)
            self.assertEqual({'keyword', 'depth'}, set(legacy.load_measurement(rawpath)[2]['provider_request_data']))

    def test_attribution_strip_is_protected_and_tampering_fails_verification(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root)
            cfg['attribution_bottom_px'] = 80  # Origin's ring reaches protected row 120.
            self.save_config(root, cfg)
            rejected = self.run_tool('report_builder.py', common)
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn('attribution collision', rejected.stderr)
            self.assertFalse(Path(cfg['out_html']).exists())
            cfg['attribution_bottom_px'] = 44
            self.save_config(root, cfg)
            built = self.run_tool('report_builder.py', common)
            self.assertEqual(0, built.returncode, built.stderr)
            verified = self.run_tool('verify_pins.py', common, '--html', cfg['out_html'])
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
            png = Path(cfg['out_dir']) / 'probe.png'
            with Image.open(png) as source:
                changed = source.convert('RGB')
            changed.putpixel((10, 190), (0, 0, 0))
            changed.save(png)
            tampered = self.run_tool('verify_pins.py', common, '--html', cfg['out_html'])
            self.assertNotEqual(0, tampered.returncode)
            self.assertIn('FAIL Bicycle attribution preserved', tampered.stdout)

    def test_missing_or_wrong_html_map_cannot_skip_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root)
            self.assertEqual(0, self.run_tool('report_builder.py', common).returncode)
            html = Path(cfg['out_html'])
            original = html.read_text(encoding='utf-8')
            for altered in (original.replace('maps/probe.png', 'maps/wrong.png'),
                            original.replace('class="mapwrap"', 'class="not-a-map"'),
                            original.replace('class="rk1">1</text>', 'class="rk1">8</text>')):
                html.write_text(altered, encoding='utf-8')
                checked = self.run_tool('verify_pins.py', common, '--html', str(html))
                self.assertNotEqual(0, checked.returncode, checked.stdout)

    def test_actual_large_nonsquare_dimensions_replace_1280_constant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, common = legacy_fixture(root)
            base = root / 'wide.png'
            legacy.write_png(base, 1600, 240, bytes([80, 80, 80]) * 1600 * 240)
            cfg.update(base_png=str(base), attribution_bottom_px=44)
            (root / 'points.txt').write_text(f'1 38 {-100 + 600*360/(256*2**12)}\n')
            self.save_config(root, cfg)
            built = self.run_tool('report_builder.py', common)
            self.assertEqual(0, built.returncode, built.stderr)
            checked = self.run_tool('verify_pins.py', common, '--html', cfg['out_html'])
            self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)

    def test_png_palette_grayscale_alpha_and_corruption(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gray = Image.new('L', (2, 1), 91)
            gray.save(root / 'gray.png')
            self.assertEqual(bytes([91]*6), legacy.read_png_rgb(root / 'gray.png')[2])
            palette = Image.new('P', (1, 1), 1)
            palette.putpalette([0, 0, 0, 12, 34, 56] + [0]*762)
            palette.save(root / 'palette.png')
            self.assertEqual(bytes([12, 34, 56]), legacy.read_png_rgb(root / 'palette.png')[2])
            Image.new('RGBA', (1, 1), (255, 0, 0, 0)).save(root / 'alpha.png')
            self.assertEqual(bytes([255]*3), legacy.read_png_rgb(root / 'alpha.png')[2])
            Image.new('I;16', (1, 1), 1024).save(root / 'deep.png')
            with self.assertRaisesRegex(ValueError, '16-bit'):
                legacy.read_png_rgb(root / 'deep.png')
            broken = bytearray((root / 'gray.png').read_bytes())
            broken[29] ^= 255  # Corrupt IHDR checksum.
            (root / 'broken.png').write_bytes(broken)
            with self.assertRaises((ValueError, OSError)):
                legacy.read_png_rgb(root / 'broken.png')

    def test_projection_rejects_nonfinite_and_unsupported_latitudes(self):
        for lat, lng in ((86, 0), (float('nan'), 0), (0, float('inf'))):
            with self.subTest(lat=lat, lng=lng), self.assertRaises(ValueError):
                legacy.project(lat, lng, 0, 0, 12, 640, 480)


class StrategyModelAcceptance(unittest.TestCase):
    def test_synthetic_provenance_cannot_be_presented_as_real(self):
        import report_model
        cfg = {"schema_version": 1,
               "business": {"name": "Fictional Workshop", "location": "Fictional City", "lat": 38, "lng": -100},
               "thesis": "A hypothesis to test", "objectives": ["Check source labeling"],
               "lanes": [{"query_id": "repair", "label": "Repair", "query": "bicycle repair",
                          "records": [{"query_id": "repair", "lat": 38, "lng": -100,
                                       "rank": 1, "state": "found", "returned_count": 1,
                                       "depth": 1, "sampled_at": "2026-01-01T00:00:00Z",
                                       "source": "synthetic-replay", "observed_ranks": [1]}]}]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")
            try:
                model = report_model.load_config(path)
            except ValueError:
                return  # Rejecting mixed/unacknowledged synthetic input is also safe.
            self.assertTrue(model["synthetic"], "Synthetic source accepted with synthetic=false by default")

    def test_near_miss_boundaries_and_unknown_denominator_are_explicit(self):
        import report_model
        records = [dict(state="found", rank=rank) for rank in (1, 3, 4, 10, 11)]
        records += [dict(state="not_returned", rank=None, observed_ranks=[1, 2]),
                    dict(state="empty", rank=None), dict(state="error", rank=None),
                    dict(state="unmeasured", rank=None)]
        m = report_model.metrics(records)
        self.assertEqual((9, 6, 3, 2, 4, 2), tuple(m[k] for k in
                         ("sampled", "measured", "excluded", "top3", "top10", "near_miss")))
        self.assertEqual(1, m["top3_unknown_absence"])
        self.assertEqual(1, m["top10_unknown_absence"])


class AdaptiveReleaseAcceptance(unittest.TestCase):
    def config(self):
        return {"center": {"lat": 38, "lng": -100}, "max_shell": 4,
                "depth": 3, "negative_depth": 3, "targets": [{"cid": "123"}],
                "queries": [{"id": "repair", "keyword": "bicycle repair"},
                            {"id": "wheels", "keyword": "wheel repair"}]}

    def test_clean_negative_layers_require_sentinels_and_resume_is_free(self):
        import adaptive_geogrid as adaptive
        with tempfile.TemporaryDirectory() as directory, patch.object(local, "http_json", side_effect=AssertionError("Network forbidden")):
            adapter = adaptive.ReplayAdapter({"default": {"state": "not_returned"}})
            collector = adaptive.Collector(self.config(), adapter, Path(directory), 1)
            receipt = collector.run()
            # 3x3 common base, complete shell 2, then eight shell-3 sentinels; two lanes.
            self.assertEqual(66, receipt["accounting"]["attempted_calls"])
            self.assertEqual("sampled_stop", receipt["status"])
            self.assertEqual({"sampled_stop"}, {s["state"] for s in receipt["sectors"].values()})
            original = (Path(directory) / "observations.json").read_bytes()
            resumed = adaptive.Collector(self.config(), adapter, Path(directory), 1).run()
            self.assertEqual(0, resumed["accounting"]["new_calls"])
            self.assertEqual(66, resumed["accounting"]["resumed_calls"])
            self.assertEqual(original, (Path(directory) / "observations.json").read_bytes())

    def test_budget_preserves_complete_lane_pairs_and_reserved_accounting(self):
        import adaptive_geogrid as adaptive
        with tempfile.TemporaryDirectory() as directory:
            adapter = adaptive.ReplayAdapter({"default": {"state": "found"}})
            receipt = adaptive.Collector(self.config(), adapter, Path(directory), .008).run()
            self.assertEqual("budget_stop", receipt["status"])
            self.assertEqual((4, .008, True), tuple(receipt["accounting"][k] for k in
                                                ("attempted_calls", "accounted_usd", "synthetic")))
            rows = json.loads((Path(directory) / "observations.json").read_text())
            self.assertEqual(18, len(rows))
            self.assertEqual(14, sum(r["state"] == "unmeasured" for r in rows))
            for coord in {(r["x"], r["y"]) for r in rows}:
                states = {r["state"] for r in rows if (r["x"], r["y"]) == coord}
                self.assertEqual(1, len(states), "Budget produced selectively measured query lanes")
            changed = adaptive.ReplayAdapter({"default": {"state": "not_returned"}})
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                adaptive.Collector(self.config(), changed, Path(directory), .008).run()

    def test_short_results_never_become_absence_stops(self):
        import adaptive_geogrid as adaptive
        with tempfile.TemporaryDirectory() as directory:
            adapter = adaptive.ReplayAdapter({"default": {"state": "not_returned", "returned_count": 2}})
            receipt = adaptive.Collector(self.config(), adapter, Path(directory), 1).run()
            self.assertEqual("unresolved", receipt["status"])
            self.assertNotIn("sampled_stop", {s["state"] for s in receipt["sectors"].values()})


class StrategyPdfAcceptance(unittest.TestCase):
    def test_unknown_map_metadata_never_reaches_client_export(self):
        import strategy_report
        sentinel = "SYNTHETIC_INTERNAL_METADATA_SENTINEL"
        source = ROOT / "examples" / "reports" / "rural-mobile.json"
        config = json.loads(source.read_text(encoding="utf-8"))
        for lane in config["lanes"]:
            if "records_path" in lane:
                lane["records_path"] = str(source.parent / lane["records_path"])
        config.setdefault("map", {})["operator_metadata"] = {
            "private_path": "Z:/qa-private/" + sentinel,
            "credential": sentinel,
        }
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "input.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            output = Path(directory) / "report"
            try:
                strategy_report.load_config(config_path)
            except ValueError:
                return  # Rejecting unknown config fields before rendering is safe.
            strategy_report.build(config_path, output, True)
            for name in ("report-model.json", "report.html", "report-qa.json"):
                self.assertFalse(sentinel in (output / name).read_text(encoding="utf-8"),
                                 "Unsupported operational map metadata leaked into " + name)

    def test_both_documented_synthetic_pdfs_reconcile_and_label_every_page(self):
        import strategy_report
        import pypdfium2
        expected = {"urban-dentist": {"general": (49, 31, 9, 17, 8), "urgent": (49, 31, 9, 17, 8),
                                     "cosmetic": (49, 31, 8, 17, 9)},
                    "rural-mobile": {"mobile": (17, 11, 2, 6, 4)}}
        with tempfile.TemporaryDirectory() as directory:
            for fixture, counts in expected.items():
                folder = Path(directory) / fixture
                with self.subTest(fixture=fixture):
                    result = strategy_report.build(ROOT / "examples" / "reports" / (fixture + ".json"), folder, True)
                    self.assertEqual("passed", result["status"])
                    for lane, values in counts.items():
                        self.assertEqual(values, tuple(result["metrics"][lane][key] for key in
                                                      ("sampled", "measured", "top3", "top10", "near_miss")))
                    with pypdfium2.PdfDocument(str(folder / "report.pdf")) as document:
                        for page in document:
                            textpage = page.get_textpage()
                            content = textpage.get_text_range()
                            self.assertIn("SYNTHETIC DEMONSTRATION", content)
                            textpage.close()
                            page.close()
                    for filename in ("report.html", "report-model.json", "report-qa.json"):
                        self.assertFalse(str(ROOT) in (folder / filename).read_text(encoding="utf-8"))

    def test_distance_rings_are_complete_or_omitted(self):
        import strategy_report
        from PIL import ImageDraw
        model = strategy_report.load_config(ROOT / "examples" / "reports" / "rural-mobile.json")
        fonts = strategy_report.register_fonts(model)
        original = ImageDraw.ImageDraw.line
        arcs = []
        def capture(draw, xy, *args, **kwargs):
            if isinstance(xy, list) and len(xy) > 4:
                arcs.append(xy)
            return original(draw, xy, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory, patch.object(ImageDraw.ImageDraw, "line", capture):
            strategy_report.map_image(model["lanes"][0], model["business"], Path(directory) / "map.png", fonts)
        self.assertTrue(arcs)
        self.assertTrue(all(abs(a[0][0]-a[-1][0]) < .001 and abs(a[0][1]-a[-1][1]) < .001 for a in arcs),
                        "Map draws truncated distance arcs while caption lists complete configured bands")

    def test_default_font_supports_generated_north_arrow(self):
        import strategy_report
        from reportlab.pdfbase import pdfmetrics
        from PIL import ImageDraw
        model = strategy_report.load_config(ROOT / "examples" / "reports" / "rural-mobile.json")
        fonts = strategy_report.register_fonts(model)
        original = ImageDraw.ImageDraw.text
        emitted = []
        def capture(draw, xy, text, *args, **kwargs):
            emitted.append(text)
            return original(draw, xy, text, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory, patch.object(ImageDraw.ImageDraw, "text", capture):
            strategy_report.map_image(model["lanes"][0], model["business"], Path(directory) / "map.png", fonts)
        if any("\u2191" in value for value in emitted):
            self.assertIn(ord("\u2191"), pdfmetrics.getFont("ReportBody").face.charToGlyph,
                          "Generated map arrow is missing from the default font; draw it as a vector or validate it")


if __name__ == "__main__":
    unittest.main()
