"""Offline composition tests: immutable sources and exact profile identities."""
import copy
import datetime as dt
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import business_name_review as review
import compose_name_reviews as composer


class ComposeNameReviewsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "base" / "name-review.json"
        self.supplement = self.root / "supplement" / "name-review.json"
        self.enrichment = self.root / "enrichment.json"
        self.output = self.root / "composed" / "name-review.json"
        self.fingerprint = "a" * 64
        self.base_doc = self.make_document(self.base, ["11", "22"], .003)
        self.supplement_doc = self.make_document(self.supplement, ["33"], .0015)
        review.save(self.enrichment, {"schema": "geogrid-title-review-enrichment/v1",
                                     "study_plan_sha256": self.fingerprint, "cases": {}})

    def make_document(self, path, cids, cost):
        cases = []
        for cid in cids:
            checked = review.now()
            source = path.parent / "profiles" / (cid + ".json")
            name = "Fixture " + cid
            review.save(source, {"checked_at": checked, "response": {"tasks": [
                {"status_code": 20000, "result": [{"items": [{"cid": cid, "title": name}]}]}]}})
            cases.append({"id": "cid:" + cid, "cid": cid, "name": name, "total_wins": 0,
                          "returned_observations": 3, "wins_by_query": {}, "status": "unavailable",
                          "profile": {"status": "complete", "name": name, "checked_at": checked,
                                      "evidence_path": "profiles/" + cid + ".json", "sha256": review.sha(source)},
                          "website_evidence": {"status": "not_captured"}})
        doc = {"schema": "geogrid-name-review/v1", "study_plan_sha256": self.fingerprint,
               "collection": {"cost_usd": cost, "method": "standard"}, "cases": cases}
        review.save(path, doc)
        return doc

    def run_compose(self):
        return composer.compose(self.base, self.supplement, self.enrichment, self.output)

    def test_composes_exact_profiles_rebases_evidence_and_preserves_inputs(self):
        before = {path: path.read_bytes() for path in (self.base, self.supplement, self.enrichment)}
        result = self.run_compose()
        self.assertEqual({c["cid"] for c in result["cases"]}, {"11", "22", "33"})
        self.assertEqual(result["collection"]["cost_usd"], .0045)
        self.assertEqual(result["collection"]["supplement_cost_usd"], .0015)
        self.assertEqual(len(result["collection"]["provenance"]), 2)
        self.assertTrue(review.fresh(result["generated_at"]))
        for case in result["cases"]:
            evidence = (self.output.parent / case["profile"]["evidence_path"]).resolve()
            self.assertTrue(evidence.is_file())
            self.assertEqual(review.sha(evidence), case["profile"]["sha256"])
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_bound_score_is_added_without_status_promotion(self):
        enrichment = review.load(self.enrichment)
        enrichment["cases"]["33"] = {"confidence": {
            "rubric": "title-evidence-v1", "level": 2, "cid": "33", "profile_name": "Fixture 33",
            "rationale": "Mixed branding evidence.", "factors": [], "checked_at": review.now()}}
        review.save(self.enrichment, enrichment)
        case = next(c for c in self.run_compose()["cases"] if c["cid"] == "33")
        self.assertEqual(case["confidence"]["level"], 2)
        self.assertEqual(case["status"], "unavailable")
        self.assertNotIn("report_ready", case)

    def test_rejects_wrong_fingerprint_and_duplicate_cids(self):
        for mutate in (lambda d: d.update(study_plan_sha256="b" * 64),
                       lambda d: d["cases"].append(copy.deepcopy(d["cases"][0]))):
            changed = copy.deepcopy(self.supplement_doc)
            mutate(changed)
            review.save(self.supplement, changed)
            with self.assertRaises(ValueError):
                self.run_compose()
            self.assertFalse(self.output.exists())

    def test_rejects_incomplete_stale_or_mismatched_supplement(self):
        for mutate in (lambda c: c["profile"].update(status="pending"),
                       lambda c: c["profile"].update(checked_at="2000-01-01T00:00:00+00:00"),
                       lambda c: c.update(cid="999"),
                       lambda c: c["profile"].update(name="Other Name"),
                       lambda c: c["profile"].update(sha256="f" * 64)):
            changed = copy.deepcopy(self.supplement_doc)
            mutate(changed["cases"][0])
            review.save(self.supplement, changed)
            with self.assertRaises(ValueError):
                self.run_compose()
            self.assertFalse(self.output.exists())

    def test_refreshed_identity_drops_previous_confidence_and_review(self):
        old = self.base_doc["cases"][0]
        old["source_review"] = {"finding": "Old verdict"}
        old["confidence"] = {"rubric": "title-evidence-v1", "level": 4, "cid": "11",
                             "profile_name": "Old name", "rationale": "Old name evidence",
                             "factors": [], "checked_at": review.now()}
        old["historical_report"] = {"title": "Earlier research"}
        review.save(self.base, self.base_doc)
        self.make_document(self.supplement, ["11"], .0015)
        result = self.run_compose()
        new = next(c for c in result["cases"] if c["cid"] == "11")
        self.assertNotIn("confidence", new)
        self.assertNotIn("source_review", new)
        self.assertEqual(new["historical_report"]["title"], "Earlier research")
        self.assertEqual(len(result["cases"]), 2)

    def test_rejects_output_input_or_source_overwrite(self):
        for output in (self.base, self.supplement, self.enrichment,
                       self.base.parent / "profiles" / "11.json"):
            before = output.read_bytes()
            with self.assertRaises(ValueError):
                composer.compose(self.base, self.supplement, self.enrichment, output)
            self.assertEqual(output.read_bytes(), before)

    def test_rejects_unknown_or_wrong_name_enrichment(self):
        for cid, name in (("999", "Fixture 33"), ("33", "Old Name")):
            enrichment = review.load(self.enrichment)
            enrichment["cases"] = {cid: {"confidence": {
                "rubric": "title-evidence-v1", "level": 2, "cid": cid, "profile_name": name,
                "rationale": "Mixed", "factors": [], "checked_at": review.now()}}}
            review.save(self.enrichment, enrichment)
            with self.assertRaises(ValueError):
                self.run_compose()

    def test_rejects_older_supplement_even_when_still_fresh(self):
        self.make_document(self.supplement, ["11"], .0015)
        doc = review.load(self.supplement)
        old_time = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat()
        source = self.supplement.parent / doc["cases"][0]["profile"]["evidence_path"]
        response = review.load(source)
        response["checked_at"] = old_time
        review.save(source, response)
        doc["cases"][0]["profile"].update(checked_at=old_time, sha256=review.sha(source))
        review.save(self.supplement, doc)
        with self.assertRaisesRegex(ValueError, "older"):
            self.run_compose()


if __name__ == "__main__":
    unittest.main()
