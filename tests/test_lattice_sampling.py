import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from lattice_sampling import lattice_plan


class LatticeTests(unittest.TestCase):
    def source(self):
        return {
            "target_business": {"name": "Example", "lat": 38.6, "lng": -121.2},
            "query_selection": [{"query": "example service"}],
            "measurement_settings": {"depth": 20, "zoom": 14},
            "origins": [{"origin_id": "old", "lat": 38.6, "lng": -121.2}],
        }

    def test_aligned_centered_unique_and_preserves_source(self):
        source = self.source()
        plan = lattice_plan(source)
        origins = plan["origins"]
        self.assertEqual(len(origins), 441)
        self.assertEqual(len({p["lat"] for p in origins}), 21)
        self.assertEqual(len({p["lng"] for p in origins}), 21)
        self.assertEqual(len({(p["lat"], p["lng"]) for p in origins}), 441)
        self.assertEqual((origins[220]["lat"], origins[220]["lng"]), (38.6, -121.2))
        self.assertEqual(source["origins"][0]["origin_id"], "old")
        self.assertEqual(plan["summary"]["total_tasks"], 441)
        self.assertEqual(plan["summary"]["total_estimated_cost_usd"], .2646)
        self.assertEqual(plan["measurement_settings"]["method"], "standard")

    def test_rejects_invalid_geometry(self):
        for size in (2, 4, 100):
            with self.assertRaises(ValueError):
                lattice_plan(self.source(), size=size)
        for spacing in (0, float("nan"), 10):
            with self.assertRaises(ValueError):
                lattice_plan(self.source(), spacing_km=spacing)
