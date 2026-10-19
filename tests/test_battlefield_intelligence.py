"""Offline spatial evidence analysis: no fabricated rankings or territory."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from battlefield_intelligence import analyze, classify, components, markdown
from radius_sampling import radial_origins, MILE_KM


def observation(rank=5, cid="target"):
    items = [{"cid": str(i), "title": "Rival " + str(i), "address": "A", "rank": i} for i in range(1,31)]
    if rank is not None:
        items[rank-1]["cid"] = cid
        items[rank-1]["title"] = "Primary"
    return {"target_rank": rank, "status": "found" if rank else "not_returned_depth_reached", "top_items": items}


def fixture():
    origins = radial_origins(38, -121, 1, .5)
    return {"target": {"cid": "target", "name": "Primary"}, "lanes": [{"lane_id": "q1", "query": "service"}],
            "study": {"sampling": {"geometry": "radius_grid", "center": {"lat": 38,"lng": -121}, "radius_km": MILE_KM, "spacing_km": .5*MILE_KM}},
            "points": [{"tag": p["origin_id"], "lat": p["lat"], "lng": p["lng"], "by_lane": {"q1": observation()}} for p in origins]}


class BattlefieldIntelligenceTests(unittest.TestCase):
    def test_orthogonal_components_do_not_join_diagonal_or_bridge_missing_cell(self):
        self.assertEqual(components([(0,0),(1,1),(3,1)]), [[(0,0)],[(1,1)],[(3,1)]])
        self.assertEqual(components([(1,0),(0,0),(1,1)]), [[(0,0),(1,0),(1,1)]])

    def test_censoring_and_incomplete_pending_identity_and_contradiction(self):
        self.assertEqual(classify(observation(None), "cid:target")[:2], ("not_top30",None))
        for obs in [dict(observation(), status="pending"), dict(observation(), target_rank=2),
                    dict(observation(),top_items=observation()["top_items"][:-1])]:
            self.assertEqual(classify(obs,"cid:target")[:2], ("unknown",None))
        obs=observation();obs["top_items"][2]["cid"]=obs["top_items"][1]["cid"]
        self.assertEqual(classify(obs,"cid:target")[0],"unknown")

    def test_missing_origins_remain_unknown_and_denominator_is_expected_circle(self):
        study=fixture(); count=len(study["points"]);study["points"].pop()
        result=analyze(study)
        self.assertEqual(result["expected_origins"],count)
        self.assertEqual(result["missing_origins"],1)
        self.assertEqual(result["queries"][0]["counts"]["unknown"],1)
        self.assertEqual(result["queries"][0]["counts"]["near_top3"],count-1)
        self.assertEqual(sum(result["queries"][0]["counts"].values()),count)

    def test_separate_cids_same_name_and_exact_ahead_counts(self):
        study=fixture()
        for p in study["points"]:
            p["by_lane"]["q1"]["top_items"][0]["title"]="Same name"
            p["by_lane"]["q1"]["top_items"][1]["title"]="Same name"
        report=analyze(study);count=len(study["points"])
        first=report["near_top3_rivals"][0]
        self.assertEqual(first["count"],count)
        self.assertEqual(first["first_place_count"],count)
        self.assertEqual(len([r for r in report["near_top3_rivals"] if r["name"]=="Same name"]),2)

    def test_each_query_separate_and_input_order_deterministic(self):
        study=fixture();study["lanes"].append({"lane_id":"q2","query":"other"})
        for p in study["points"]:p["by_lane"]["q2"]=observation(None)
        report=analyze(study);study["points"].reverse()
        self.assertEqual(report,analyze(study))
        self.assertEqual(report["queries"][1]["counts"]["not_top30"],len(study["points"]))
        self.assertEqual(report["cross_query_focus"]["origin_count"],0)

    def test_invalid_geometry_coordinates_and_duplicate_observations_rejected(self):
        for mutation in (lambda d:d["study"]["sampling"].update(geometry="radial"),
                         lambda d:d["points"][0].update(lat=35),
                         lambda d:d["points"].append(copy.deepcopy(d["points"][0]))):
            study=fixture();mutation(study)
            with self.assertRaises(ValueError):analyze(study)

    def test_markdown_escapes_provider_text(self):
        study=fixture();study["target"]["name"]="<script>bad</script> [link](oops) | test\nheader"
        text=markdown(analyze(study))
        self.assertNotIn("<script>",text)
        self.assertNotIn("[link]",text)
        self.assertIn("\\|",text)
        self.assertIn("&lt;script&gt;",text)
        study["target"]["name"]="DJ's"
        self.assertIn("DJ's",markdown(analyze(study)))

    def test_report_links_and_cross_query_filter_are_explicit(self):
        report=analyze(fixture(),"E:\\legends-geogrid\\runs\\sample\\companion-study.json")
        link=report["queries"][0]["components"]["near_top3"][0]["viewer_link"]
        self.assertIn("business=TARGET",link)
        self.assertIn("view=visibility",link)
        self.assertIn("study=%2Fruns%2Fsample%2Fcompanion-study.json",link)
        text=markdown(report)
        self.assertIn("threshold: min(3, number of studied queries)",text)
        self.assertIn("Existing top-three coverage",text)


if __name__=="__main__":unittest.main()
