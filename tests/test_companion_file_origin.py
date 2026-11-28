"""Regression: the static Companion opened from disk (file://) must show a working basemap.

A file:// page sends no Referer, so tile.openstreetmap.org answers with "Access blocked" images. The static
Companion must therefore never request OpenStreetMap raster tiles from file://, must list only backgrounds
that work there, and must render the OpenFreeMap (MapLibre) style with its worker started from the page.
The network is mocked: OpenFreeMap style requests receive a small inline style and every other remote
request is aborted and recorded, so the test is hermetic.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import companion_standalone  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - optional report dependency
    sync_playwright = None

BACKGROUND = (18, 52, 86)
FILL = (200, 30, 170)
OFM_OPTIONS = ["ofm-fiord", "ofm-dark", "ofm-liberty", "ofm-positron"]
# Headless Chromium without a GPU renders WebGL through SwiftShader.
CHROMIUM_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]


def hermetic_style() -> dict:
    # A GeoJSON source makes MapLibre parse geometry in its worker, so a rendered fill proves the worker ran.
    north = [[[-80.0, 39.93], [-70.0, 39.93], [-70.0, 45.0], [-80.0, 45.0], [-80.0, 39.93]]]
    return {
        "version": 8,
        "sources": {"north": {"type": "geojson", "data": {"type": "Feature", "properties": {},
                                                          "geometry": {"type": "Polygon", "coordinates": north}}}},
        "layers": [
            {"id": "bg", "type": "background", "paint": {"background-color": "rgb(%d,%d,%d)" % BACKGROUND}},
            {"id": "north", "type": "fill", "source": "north", "paint": {"fill-color": "rgb(%d,%d,%d)" % FILL}},
        ],
    }


@unittest.skipIf(sync_playwright is None, "Playwright is not installed (requirements-basemaps.txt)")
class CompanionFileOriginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name) / "companion.html"
        cls.uri = companion_standalone.open_companion(output=out, open_browser=False)["companion_uri"]
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch(args=CHROMIUM_ARGS)
        except Exception as error:  # pragma: no cover - browser binary missing
            cls.pw.stop()
            cls.tmp.cleanup()
            raise unittest.SkipTest(f"Chromium is unavailable: {error}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()

    def open(self, query: str = "", init_script: str | None = None):
        page = self.browser.new_page(viewport={"width": 1400, "height": 900})
        remote, problems = [], []
        page.on("pageerror", lambda error: problems.append(str(error)))

        def route(route_obj):
            url = route_obj.request.url
            if url.startswith(("file:", "blob:", "data:")):
                return route_obj.continue_()
            remote.append(url)
            if url.startswith("https://tiles.openfreemap.org/styles/"):
                return route_obj.fulfill(status=200, content_type="application/json",
                                         headers={"access-control-allow-origin": "*"}, body=json.dumps(hermetic_style()))
            return route_obj.abort()

        page.route("**/*", route)
        if init_script:
            page.add_init_script(init_script)
        page.goto(self.uri + query)
        state = ""
        for _ in range(240):
            state = page.evaluate("document.querySelector('#map')?.dataset.basemapState || ''")
            if state in ("ready", "error"):
                break
            time.sleep(0.125)
        return page, state, remote, problems

    def test_file_origin_renders_openfreemap_without_openstreetmap_tiles(self):
        # A stale or shared OpenStreetMap choice must not reach the blocked tile server.
        page, state, remote, problems = self.open("?basemap=osm-legends")
        try:
            self.assertEqual(page.evaluate("location.protocol"), "file:")
            self.assertEqual([u for u in remote if "tile.openstreetmap.org" in u], [])
            status = page.evaluate("document.querySelector('#basemap-status p')?.textContent")
            self.assertEqual(state, "ready", f"basemap state {state!r}; status {status!r}; requests {remote}; errors {problems}")
            self.assertIn("https://tiles.openfreemap.org/styles/dark", remote)
            options = page.evaluate("[...document.querySelectorAll('#basemap option')].map(o => [o.value, o.disabled, o.textContent])")
            self.assertEqual([value for value, _, _ in options], OFM_OPTIONS)
            self.assertFalse(any(disabled for _, disabled, _ in options))
            self.assertFalse(any("HTTP server only" in text for _, _, text in options))
            self.assertEqual(page.evaluate("document.querySelector('#basemap').value"), "ofm-dark")
            self.assertTrue(page.evaluate("!!document.querySelector('#map canvas.maplibregl-canvas')"), "MapLibre canvas is mounted")
            time.sleep(0.6)  # basemap fade-in
            pixels = self.map_pixels(page)
            share = lambda rgb: sum(1 for p in pixels if all(abs(a - b) <= 6 for a, b in zip(p, rgb))) / len(pixels)
            self.assertGreater(share(BACKGROUND), 0.02, "style background is painted")
            self.assertGreater(share(FILL), 0.02, "worker-parsed GeoJSON fill is painted")
            self.assertEqual(problems, [])
        finally:
            page.close()

    def test_without_webgl_the_grid_stays_on_a_neutral_background(self):
        no_webgl = ("const original = HTMLCanvasElement.prototype.getContext;"
                    "HTMLCanvasElement.prototype.getContext = function (type, ...rest) {"
                    "  return /webgl/i.test(type) ? null : original.call(this, type, ...rest) }")
        page, state, remote, problems = self.open(init_script=no_webgl)
        try:
            self.assertEqual(state, "error")
            self.assertIn("WebGL", page.evaluate("document.querySelector('#basemap-status p').textContent"))
            self.assertTrue(page.evaluate("document.querySelector('#use-default-basemap').hidden"),
                            "no OpenStreetMap or duplicate rescue choice on file://")
            self.assertEqual([u for u in remote if "tile.openstreetmap.org" in u], [])
            self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('#map')).backgroundColor"), "rgb(8, 8, 8)")
            self.assertFalse(page.evaluate("!!document.querySelector('#map .leaflet-tile')"), "no raster tiles are shown")
            self.assertTrue(page.evaluate("!!document.querySelector('#map canvas.ranking-canvas')"), "ranking evidence stays on the map")
            self.assertEqual(problems, [])
        finally:
            page.close()

    @staticmethod
    def map_pixels(page):
        from PIL import Image

        image = Image.open(io.BytesIO(page.locator("#map").screenshot())).convert("RGB")
        image = image.resize((image.width // 4, image.height // 4), Image.NEAREST)
        raw = image.tobytes()
        return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]


if __name__ == "__main__":
    unittest.main()
