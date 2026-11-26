import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hex_to_companion.py"


def point(q, r, unit, spacing, role, rank, limited=False):
    east, north = (q + r / 2) * unit, r * math.sqrt(3) / 2 * unit
    top = [[1, "Rival", "99", 4.5, 10, 30.0, -97.0]]
    if rank:
        top.insert(rank - 1, [rank, "Biz", "1", 4.8, 50, 30.0, -97.0])
    return {"id": f"hex_{q}_{r}", "lat": 30 + north / 69, "lng": -97 + east / 60, "east": east, "north": north,
            "unit_q": q, "unit_r": r, "spacing": spacing, "role": role, "status": "ok", "rank": rank, "top": top,
            "instrument_limited": limited}


def export(grid, *args):
    tmp = tempfile.TemporaryDirectory()
    run = Path(tmp.name) / "runs" / "demo"
    (run / "grid").mkdir(parents=True)
    (run / "grid" / "grid_points.json").write_text(json.dumps(grid), encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPT), str(run), "--location", "Here", *args], check=True, capture_output=True)
    return tmp, run


class HexToCompanionTest(unittest.TestCase):
    def grid(self, unit=0.75):
        pts = [point(q, r, unit, 1.5, "coarse", 1) for q in (-2, 0, 2) for r in (-2, 0, 2)]
        pts += [point(1, 0, unit, 0.75, "refine_0.75", 3), point(0, 1, unit, 0.75, "refine_0.75", None)]
        return {"center": {"lat": 30, "lng": -97, "name": "Biz", "cid": "1"},
                "settings": {"zoom": 12, "depth": 20, "device": "desktop"}, "s0": 1.5,
                "radius": {"a": 3, "b": 3}, "phrases": {"a": pts, "b": pts[:5]}}

    def test_main_view_merges_every_rung_inside_the_circle(self):
        tmp, run = export(self.grid())
        with tmp:
            main = json.loads((run / "companion" / "view-1.5" / "companion-study.json").read_text(encoding="utf-8"))
            self.assertFalse((run / "companion" / "view-0.75").exists())
        self.assertEqual(len(main["points"]), 11)
        self.assertEqual(len(main["study_views"]), 1)
        rung = {p["tag"]: p["hex"]["rung_miles"] for p in main["points"]}
        self.assertEqual(rung["hex_2_2"], 1.5)
        self.assertEqual(rung["hex_1_0"], 0.75)
        self.assertEqual(main["study"]["sampling"]["hex"]["step"], 2)
        self.assertFalse(any(p.get("reach_beyond") for p in main["points"]))

    def test_points_beyond_the_circle_are_dropped_and_instrument_limited_kept(self):
        grid = self.grid()
        grid["study_radius"] = 1.6
        grid["phrases"]["a"].append(point(-1, 0, 0.75, 0.75, "refine_0.75", None, limited=True))
        tmp, run = export(grid)
        with tmp:
            main = json.loads((run / "companion" / "view-1.5" / "companion-study.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(main["study"]["sampling"]["radius_km"], 1.6 * 1.609344)
        by_tag = {p["tag"]: p for p in main["points"]}
        # hex_2_2 and hex_-2_-2 sit at sqrt(3) * 1.5 = 2.6 mi: beyond R, dropped from the study entirely.
        self.assertNotIn("hex_2_2", by_tag)
        self.assertNotIn("hex_-2_-2", by_tag)
        self.assertEqual(len(main["points"]), 10)
        self.assertFalse(any("reach_beyond" in p for p in main["points"]))
        self.assertIn("hex_2_0", by_tag)
        self.assertEqual(by_tag["hex_-1_0"]["by_lane"]["q1"]["status"], "instrument_limited")
        self.assertEqual(by_tag["hex_0_1"]["by_lane"]["q1"]["status"], "not_returned_depth_reached")
        # Edge signal: the six coarse points on the outermost ring inside R all rank #1.
        edge = main["study"]["edge_signal"]["q1"]
        self.assertEqual((edge["ring_points"], edge["scored"], edge["top3"], edge["share"]), (6, 6, 6, 1.0))
        self.assertTrue(edge["extends"])
        self.assertEqual(edge["radius_miles"], 1.6)

    def test_edge_signal_stays_quiet_when_the_ring_is_lost(self):
        grid = self.grid()
        grid["study_radius"] = 1.6
        grid["phrases"]["a"] = [point(p["unit_q"], p["unit_r"], 0.75, p["spacing"], p["role"],
                                      1 if (p["unit_q"], p["unit_r"]) in ((0, 0), (2, 0), (-2, 0)) else 8)
                                for p in grid["phrases"]["a"]]
        tmp, run = export(grid)
        with tmp:
            main = json.loads((run / "companion" / "view-1.5" / "companion-study.json").read_text(encoding="utf-8"))
        edge = main["study"]["edge_signal"]["q1"]
        # Two of six ring points top 3 (33%): under the 50% line, so no grow-the-circle note.
        self.assertEqual((edge["scored"], edge["top3"]), (6, 2))
        self.assertFalse(edge["extends"])

    def test_detail_views_stay_available_as_an_option(self):
        grid = self.grid(0.75)  # not the Dough Valley half mile: the unit is fitted from the points
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "runs" / "demo"
            (run / "grid").mkdir(parents=True)
            (run / "grid" / "grid_points.json").write_text(json.dumps(grid), encoding="utf-8")
            subprocess.run([sys.executable, str(SCRIPT), str(run), "--location", "Here", "--detail-views"], check=True, capture_output=True)
            main = json.loads((run / "companion" / "view-1.5" / "companion-study.json").read_text(encoding="utf-8"))
            detail = json.loads((run / "companion" / "view-0.75" / "companion-study.json").read_text(encoding="utf-8"))
            current = json.loads((Path(tmp) / "runs" / "current-study.json").read_text(encoding="utf-8"))
        self.assertEqual(main["schema"], "geogrid-companion/v1")
        self.assertEqual(main["study"]["geometry"], "hex_radius")
        self.assertEqual(main["study"]["sampling"]["hex"], {"unit_miles": 0.75, "step": 2})
        self.assertEqual(detail["study"]["sampling"]["hex"]["step"], 1)
        self.assertEqual(len(main["points"]), 11)
        self.assertEqual([lane["query"] for lane in main["lanes"]], ["a", "b"])
        self.assertEqual([v["url"] for v in main["study_views"]],
                         ["/runs/demo/companion/view-1.5/companion-study.json", "/runs/demo/companion/view-0.75/companion-study.json"])
        self.assertEqual(current["study"], main["study_views"][0]["url"])
        self.assertEqual(main["location"], "Here")
        rival = next(f for f in main["factions"] if not f["is_target"])
        self.assertEqual(rival["selection"]["position"], 1)
        by_lane = {p["tag"]: p["by_lane"] for p in detail["points"]}
        self.assertEqual(by_lane["hex_0_1"]["q1"]["status"], "not_returned_depth_reached")
        self.assertNotIn("q2", by_lane["hex_0_1"])

    def test_refuses_symlink_or_junction_input_and_output_paths(self):
        def _link_dir(link_path: Path, target: Path) -> None:
            if sys.platform == "win32":
                import _winapi
                _winapi.CreateJunction(str(target), str(link_path))
            else:
                link_path.symlink_to(target, target_is_directory=True)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_run = root / "runs" / "real_demo"
            (real_run / "grid").mkdir(parents=True)
            (real_run / "grid" / "grid_points.json").write_text(json.dumps(self.grid()), encoding="utf-8")

            # Linked run_dir must be refused cleanly.
            linked_run = root / "runs" / "linked_demo"
            _link_dir(linked_run, real_run)
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(linked_run), "--no-current"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertRegex(proc.stderr + proc.stdout, r"symlink|junction|reparse")

            # Linked companion output directory inside a real run_dir must also be refused.
            outside_out = root / "outside_out"
            outside_out.mkdir()
            _link_dir(real_run / "companion", outside_out)
            proc_out = subprocess.run(
                [sys.executable, str(SCRIPT), str(real_run), "--no-current"],
                capture_output=True, text=True,
            )
            self.assertNotEqual(proc_out.returncode, 0)
            self.assertRegex(proc_out.stderr + proc_out.stdout, r"symlink|junction|reparse")
            self.assertEqual(list(outside_out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
