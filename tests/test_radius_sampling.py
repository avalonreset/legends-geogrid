import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from radius_sampling import radial_origins, estimate, MILE_KM
from competitive_sampling import haversine_km


class RadiusSamplingTests(unittest.TestCase):
    def test_complete_lattice_inside_geodesic_circle(self):
        lat, lng, radius, spacing = 38.6441996, -121.2677833, 5, .5
        points = radial_origins(lat, lng, radius, spacing)
        actual = {(p["grid_x"], p["grid_y"]) for p in points}
        step = spacing * MILE_KM / 111.195
        expected = set()
        for y in range(-10, 11):
            for x in range(-10, 11):
                a = round(lat + y * step, 7)
                b = round(lng + x * step / math.cos(math.radians(lat)), 7)
                if haversine_km(lat, lng, a, b) <= radius * MILE_KM:
                    expected.add((x, y))
        self.assertEqual(actual, expected)
        self.assertIn((0, 0), actual)
        self.assertNotIn((10, 10), actual)
        self.assertEqual(len({p["origin_id"] for p in points}), len(points))

    def test_refinement_preserves_existing_coordinates(self):
        args = (38.6441996, -121.2677833, 5)
        coarse = {(p["lat"], p["lng"]) for p in radial_origins(*args, .5)}
        fine = {(p["lat"], p["lng"]) for p in radial_origins(*args, .25)}
        self.assertTrue(coarse <= fine)

    def test_shared_search_cost(self):
        result = estimate(38.6441996, -121.2677833, 5, .25, queries=4)
        self.assertEqual(result["requests"], result["locations"] * 4)
        self.assertAlmostEqual(result["estimated_scan_cost_usd"], result["requests"] * .0006)
        self.assertEqual(result["business_multiplier"], 1)

    def test_invalid_and_unbounded_sampling_rejected(self):
        for radius, spacing in [(0, .25), (5, 0), (5, 6), (5, .0001), (math.nan, .25)]:
            with self.subTest(radius=radius, spacing=spacing):
                with self.assertRaises(ValueError):
                    radial_origins(38.6, -121.2, radius, spacing)


if __name__ == "__main__":
    unittest.main()
