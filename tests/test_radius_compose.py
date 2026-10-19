import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from radius_compose import compose, read_archive, require_complete, require_same_search
from radius_sampling import radial_origins


class RadiusCompositionTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "business": dict(lat=38.6, lng=-121.2, cid="123", place_id="abc", domain="example.com"),
            "queries": [dict(query_id="q1", query="furnace repair")],
            "settings": dict(method="live", depth=20, zoom=13, search_this_area=True,
                             device="desktop", language_code="en", se_domain="google.com"),
        }

    def test_delivery_change_does_not_change_search(self):
        other = copy.deepcopy(self.base)
        other["settings"]["method"] = "standard"
        require_same_search(self.base, other)

    def test_incompatible_measurements_cannot_be_composed(self):
        changes = [("business", "cid", "456"), ("business", "lat", 38.7),
                   ("settings", "zoom", 14), ("settings", "search_this_area", False),
                   ("settings", "depth", 100)]
        for section, key, value in changes:
            with self.subTest(key=key):
                other = copy.deepcopy(self.base)
                other[section][key] = value
                with self.assertRaises(ValueError):
                    require_same_search(self.base, other)
        other = copy.deepcopy(self.base)
        other["queries"][0]["query"] = "heating repair"
        with self.assertRaisesRegex(ValueError, "query differs"):
            require_same_search(self.base, other)

    def test_each_query_must_cover_every_radial_location(self):
        origins = radial_origins(38.6, -121.2, 1, .5)
        queries = [{"query_id": "q1"}, {"query_id": "q2"}]
        observations = {(q["query_id"], o["lat"], o["lng"]): {}
                        for q in queries for o in origins}
        expected = require_complete(origins, queries, observations)
        self.assertEqual(len(expected), len(origins) * 2)
        del observations[next(iter(observations))]
        with self.assertRaisesRegex(ValueError, "1 unmeasured"):
            require_complete(origins, queries, observations)

    def test_off_lattice_nearby_result_cannot_fill_gap(self):
        origins = radial_origins(38.6, -121.2, 1, .5)
        queries = [{"query_id": "q1"}]
        observations = {("q1", o["lat"], o["lng"]): {} for o in origins}
        key = next(iter(observations))
        observations[("q1", key[1] + .0000001, key[2])] = observations.pop(key)
        with self.assertRaisesRegex(ValueError, "1 unmeasured"):
            require_complete(origins, queries, observations)

    def make_archive(self):
        # Reuse the offline queue simulator; no provider or credentials are involved.
        from test_competitive_queue import QueueTests
        fixture = QueueTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        target = fixture.plan["target_business"]
        fixture.plan["origins"] = radial_origins(target["lat"], target["lng"], 1, .5)
        fixture.plan_path.write_text(json.dumps(fixture.plan))
        fixture.ready = True
        fixture.run_collect(confirm_cost_usd=1)
        return fixture

    def test_composition_reparses_raw_and_keeps_short_lists_unknown(self):
        fixture = self.make_archive()
        # A modified display file must never become the source of ranking evidence.
        lane = fixture.out / "lane-1/parsed-grid.json"
        lane.write_text('{"results":[]}')
        dest = fixture.root / "radial"
        receipt = compose([fixture.out], dest, 1, .5)
        model = json.loads((dest / "companion-study.json").read_text())
        self.assertEqual(model["study"]["geometry"], "radius_grid")
        self.assertEqual(len(model["points"]), len(fixture.plan["origins"]))
        self.assertEqual(receipt["composition"]["new_collection_cost_usd"], 0)
        self.assertEqual(receipt["composition"]["reused_observations"], len(model["points"]) * 2)
        self.assertEqual(receipt["short_result_sets_by_query"]["q1"], len(model["points"]))
        obs = model["points"][0]["by_lane"]["q1"]
        self.assertEqual(obs["target_rank"], 1)
        self.assertEqual(obs["provenance"]["method"], "standard")
        self.assertEqual(len(obs["observed_ranks"]), 2)
        with self.assertRaisesRegex(ValueError, "must be new"):
            compose([fixture.out], dest, 1, .5)

    def test_tampered_raw_response_is_rejected(self):
        fixture = self.make_archive()
        raw = next((fixture.out / "responses").glob("*.json"))
        raw.write_text("{}")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            read_archive(fixture.out)


if __name__ == "__main__":
    unittest.main()
