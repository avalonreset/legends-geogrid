"""Offline evidence/queue regression checks; no real business allegations."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import business_name_review as review


def study_fixture():
    def winner(cid, title="Example Heating & Air"):
        return {"status": "found", "top_items": [
            {"cid": cid, "title": title, "rank": 1, "address": "Public branch"}]}
    return {
        "evidence": {"plan_sha256": "a" * 64},
        "factions": [
            {"cid": "11", "faction_id": "TARGET", "is_target": True},
            {"cid": "22", "faction_id": "cid:22", "lat": 40, "lng": -123},
        ],
        "points": [
            {"by_lane": {"q1": winner("11"), "q2": winner("22")}},
            {"by_lane": {"q1": winner("22"), "q2": winner("33")}},
            {"by_lane": {"q1": {"status": "pending", "top_items": [
                {"cid": "44", "title": "Pending Example", "rank": 1}]}}},
        ],
    }


class BusinessNameReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.study = self.root / "study.json"
        review.save(self.study, study_fixture())
        self.seed = review.seed_from_study(self.study)
        review.save(self.root / "seed.json", self.seed)

    def test_attach_preserves_study_and_links_relative_evidence(self):
        before = self.study.read_bytes()
        review.export(self.root)
        manifest_path = review.attach(self.root)
        manifest = review.load(manifest_path)
        self.assertEqual(manifest["name_review"], "name-review.json")
        self.assertEqual(manifest["study_plan_sha256"], self.seed["study_plan_sha256"])
        self.assertEqual(self.study.read_bytes(), before)
        manifest["other_attachment"] = "keep.json"
        review.save(manifest_path, manifest)
        review.attach(self.root)
        self.assertEqual(review.load(manifest_path)["other_attachment"], "keep.json")

    def test_attach_rejects_unrelated_evidence(self):
        review.save(self.root / "name-review.json", {"schema": "geogrid-name-review/v1", "study_plan_sha256": "wrong"})
        with self.assertRaisesRegex(ValueError, "different study"):
            review.attach(self.root)

    def ack(self, body):
        tasks = [{"id": "task-" + b["tag"], "status_code": 20100,
                  "cost": review.COST, "data": copy.deepcopy(b)} for b in body]
        return {"status_code": 20000, "cost": len(tasks) * review.COST,
                "tasks": tasks}

    def api(self):
        return Mock(side_effect=lambda endpoint, body, **kwargs: self.ack(body))

    def submit(self):
        api = self.api()
        review.submit(self.root, api, 1)
        return api

    def receipt(self):
        return self.root / "batch-0000-receipt.json"

    def profile(self, cid="22", items=None):
        path = self.root / "profiles" / f"{cid}.json"
        review.save(path, {"checked_at": "2026-10-18T12:00:00+00:00",
                          "response": {"status_code": 20000, "tasks": [{
                              "id": f"task-{cid}", "status_code": 20000,
                              "result": [{"items": items if items is not None else [
                                  {"cid": cid, "title": "Example Heating & Air"}]}]}]}})
        return path

    def analyst_fixture(self):
        profile = self.profile()
        data = review.load(profile)
        data["checked_at"] = review.now()
        review.save(profile, data)
        case = {"cid": "22", "status": "no_obvious_signal", "assessment": "Screen only",
                "profile": {"status": "complete", "name": "Example Heating & Air",
                            "checked_at": data["checked_at"],
                            "evidence_path": str(profile.relative_to(self.root)),
                            "sha256": review.sha(profile)}}
        note = {"current_profile_name": case["profile"]["name"], "checked_at": review.now(),
                "status": "name_supported", "reviewer": "Fixture analyst",
                "findings": ["Captured name agrees."], "counterevidence": ["Signage unchecked."],
                "next_action": "Confirm signage if needed.",
                "sources": [{"evidence_path": str(profile.relative_to(self.root)),
                             "sha256": review.sha(profile), "type": "fresh_provider_profile",
                             "url": "https://www.google.com/maps?cid=22"}],
                "report_ready": True}
        path = self.root / "manual-review-test.json"
        document = {"schema": "geogrid-manual-name-review/v1", "cases": {"22": note}}
        review.save(path, document)
        return case, note, document, path, profile

    def test_seed_preserves_branches_primary_and_singleton_outside_winner(self):
        cases = {c["cid"]: c for c in self.seed["cases"]}
        self.assertEqual(set(cases), {"11", "22", "33"})
        self.assertEqual(cases["11"]["id"], "TARGET")
        self.assertTrue(cases["11"]["target"])
        self.assertEqual(cases["22"]["lat"], 40)
        self.assertEqual(cases["22"]["total_wins"], 2)
        self.assertEqual(cases["33"]["total_wins"], 1)
        self.assertEqual(cases["22"]["wins_by_query"], {"q2": 1, "q1": 1})
        self.assertEqual(self.seed["study_sha256"], review.sha(self.study))

    def test_explicit_zero_win_profile_keeps_observed_identity_and_counts(self):
        raw = study_fixture()
        item = {"cid": "55", "title": "Exact observed branch", "rank": 12,
                "latitude": 0, "longitude": -120, "domain": "example.test", "address": "Branch five"}
        raw["points"][0]["by_lane"]["q1"]["top_items"].extend([item, copy.deepcopy(item)])
        raw["points"][1]["by_lane"]["q2"]["top_items"].append(item)
        review.save(self.study, raw)
        self.assertNotIn("55", {c["cid"] for c in review.seed_from_study(self.study)["cases"]})
        included = review.seed_from_study(self.study, include_cids=["55", "55"])
        self.assertEqual(len(included["cases"]), 4)
        only = review.seed_from_study(self.study, only_cids=["55", "55"])
        self.assertEqual(len(only["cases"]), 1)
        case = only["cases"][0]
        self.assertEqual(case["total_wins"], 0)
        self.assertEqual(case["wins_by_query"], {})
        self.assertEqual(case["returned_observations"], 2)
        self.assertEqual(case["name"], item["title"])
        self.assertEqual(case["domain"], item["domain"])
        self.assertEqual(case["lat"], 0)
        review.save(self.root / "seed.json", only)
        exported = review.export(self.root)["cases"][0]
        self.assertEqual(exported["returned_observations"], 2)
        self.assertEqual(exported["location"]["lat"], 0)
        self.assertEqual(exported["domain"], "example.test")

    def test_explicit_selection_accepts_faction_and_rejects_unknown_or_pending_only(self):
        raw = study_fixture()
        raw["factions"].append({"cid": "66", "name": "Observed faction", "lat": 42, "domain": "branch.test"})
        review.save(self.study, raw)
        case = review.seed_from_study(self.study, only_cids=["66"])["cases"][0]
        self.assertEqual(case["name"], "Observed faction")
        self.assertEqual(case["returned_observations"], 0)
        for field in ("include_cids", "only_cids"):
            for cid in ("999", "44", "bad"):
                with self.subTest(field=field, cid=cid), self.assertRaises(ValueError):
                    review.seed_from_study(self.study, **{field: [cid]})

    def enrichment_fixture(self):
        profile_path = self.profile()
        profile = review.load(profile_path)
        profile["checked_at"] = review.now()
        review.save(profile_path, profile)
        annotations = {
            "confidence": {"rubric": "title-evidence-v1", "level": 2,
                           "cid": "22", "profile_name": "Example Heating & Air",
                           "rationale": "Mixed public naming evidence.", "checked_at": review.now(),
                           "factors": [{"label": "Brand mismatch", "met": True, "reason": "Different wording."}]},
            "historical_report": {"title": "Earlier review", "date": "2026-09-25", "pages": [2, 3],
                                  "historical_name": "Example Heating", "disputed_terms": ["Repair"],
                                  "summary": "Earlier suspected addition.", "source_url": "report.pdf",
                                  "source_sha256": "f" * 64, "returned_observations": 4, "distance_miles": 3.2}}
        document = {"schema": "geogrid-title-review-enrichment/v1",
                    "study_plan_sha256": self.seed["study_plan_sha256"], "cases": {"22": annotations}}
        path = self.root / "title-review-enrichment.json"
        review.save(path, document)
        return document, path

    def test_export_preserves_bound_annotations_without_promoting_verdict(self):
        document, _ = self.enrichment_fixture()
        case = next(c for c in review.export(self.root)["cases"] if c["cid"] == "22")
        self.assertEqual(case["confidence"], document["cases"]["22"]["confidence"])
        self.assertEqual(case["historical_report"], document["cases"]["22"]["historical_report"])
        self.assertEqual(case["status"], "unavailable")
        self.assertNotIn("report_ready", case)

    def test_enrichment_rejects_other_study_unknown_profile_and_verdict_injection(self):
        document, path = self.enrichment_fixture()
        mutations = [
            lambda d: d.update(study_plan_sha256="b" * 64),
            lambda d: d["cases"].update({"999": {}}),
            lambda d: d["cases"]["22"].update(status="corroborated_discrepancy"),
            lambda d: d["cases"]["22"].update(report_ready=True),
            lambda d: d["cases"]["22"]["confidence"].update(report_ready=True),
            lambda d: d["cases"]["22"]["historical_report"].update(status="confirmed"),
            lambda d: d["cases"]["22"]["confidence"].update(cid="33"),
            lambda d: d["cases"]["22"]["confidence"].update(profile_name="Old Name"),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(document)
            mutate(changed)
            review.save(path, changed)
            with self.assertRaises(ValueError):
                review.export(self.root)

    def test_confidence_rejects_invalid_levels_rubric_factors_and_date(self):
        document, path = self.enrichment_fixture()
        for changes in ({"level": -1}, {"level": 6}, {"level": True}, {"level": 2.5},
                        {"rubric": "probability"}, {"checked_at": "unknown"},
                        {"factors": [{"label": "Mismatch", "met": "yes", "reason": "Not boolean"}]}):
            changed = copy.deepcopy(document)
            changed["cases"]["22"]["confidence"].update(changes)
            review.save(path, changed)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                review.export(self.root)
        document["cases"]["22"]["confidence"]["level"] = None
        review.save(path, document)
        case = next(c for c in review.export(self.root)["cases"] if c["cid"] == "22")
        self.assertIsNone(case["confidence"]["level"])

    def test_standard_queue_resume_does_not_repurchase(self):
        api = self.submit()
        review.submit(self.root, api, 1)
        self.assertEqual(api.call_count, 1)
        endpoint, body = api.call_args.args
        self.assertEqual(endpoint, review.POST)
        self.assertTrue(all(t["priority"] == 1 for t in body))
        self.assertTrue(all(t["keyword"] == "cid:" + t["tag"] for t in body))

    def test_ambiguous_post_reserves_and_blocks_repurchase(self):
        api = Mock(side_effect=TimeoutError("Uncertain submission"))
        with self.assertRaises(TimeoutError):
            review.submit(self.root, api, 1)
        with self.assertRaisesRegex(ValueError, "Unresolved submission"):
            review.submit(self.root, api, 1)
        self.assertEqual(api.call_count, 1)
        self.assertFalse((self.root / "submit.lock").exists())

    def test_insufficient_budget_never_sends_request(self):
        api = self.api()
        with self.assertRaisesRegex(ValueError, "cost"):
            review.submit(self.root, api, 0)
        api.assert_not_called()

    def test_nonfinite_budget_never_sends_request(self):
        api = self.api()
        with self.assertRaises(ValueError):
            review.submit(self.root, api, float("nan"))
        api.assert_not_called()

    def test_changed_case_identity_cannot_resume_paid_batch(self):
        api = self.submit()
        seed = review.load(self.root / "seed.json")
        seed["cases"][0]["cid"] = "999"
        review.save(self.root / "seed.json", seed)
        with self.assertRaises(ValueError):
            review.submit(self.root, api, 1)
        self.assertEqual(api.call_count, 1)

    def test_receipt_rejects_duplicate_profile_tags(self):
        self.submit()
        receipt = review.load(self.receipt())
        receipt["response"]["tasks"][1]["data"] = copy.deepcopy(receipt["response"]["tasks"][0]["data"])
        review.save(self.receipt(), receipt)
        with self.assertRaises(ValueError):
            review.validate_receipt(self.root, self.receipt())

    def test_receipt_rejects_duplicate_provider_task_ids(self):
        self.submit()
        receipt = review.load(self.receipt())
        receipt["response"]["tasks"][1]["id"] = receipt["response"]["tasks"][0]["id"]
        review.save(self.receipt(), receipt)
        with self.assertRaises(ValueError):
            review.validate_receipt(self.root, self.receipt())

    def test_receipt_rejects_cost_mismatch(self):
        self.submit()
        receipt = review.load(self.receipt())
        receipt["response"]["cost"] += .1
        review.save(self.receipt(), receipt)
        with self.assertRaisesRegex(ValueError, "cost"):
            review.validate_receipt(self.root, self.receipt())

    def test_receipt_rejects_tampered_request_evidence(self):
        self.submit()
        intent = self.root / "batch-0000-intent.json"
        record = review.load(intent)
        record["reserved_at"] = "changed"
        review.save(intent, record)
        with self.assertRaisesRegex(ValueError, "changed"):
            review.validate_receipt(self.root, self.receipt())

    def test_completed_retrieval_reuses_profile_without_api(self):
        self.submit()
        for case in self.seed["cases"]:
            self.profile(case["cid"])
        api = Mock()
        result = review.retrieve(self.root, api)
        api.assert_not_called()
        self.assertEqual(result["complete"], 3)

    def test_retrieval_rejects_result_from_another_task(self):
        self.submit()
        api = Mock(return_value={"tasks": [{"id": "wrong-task", "status_code": 20000}]})
        with self.assertRaisesRegex(ValueError, "identity"):
            review.retrieve(self.root, api)
        self.assertFalse(list((self.root / "profiles").glob("*.json")))

    def test_profile_requires_exact_unique_cid(self):
        path = self.profile(items=[{"cid": "33", "title": "Same Brand"}])
        self.assertEqual(review.profile_item(path, "22")[1], "identity_unresolved")
        path = self.profile(items=[{"cid": "22"}, {"cid": "22"}])
        self.assertEqual(review.profile_item(path, "22")[1], "identity_unresolved")
        path = self.profile()
        self.assertEqual(review.profile_item(path, "22")[1], "complete")

    def test_keyword_rich_real_name_is_not_automatically_suspect(self):
        name = "Example City Heating and Air Conditioning"
        state, _, _ = review.screen_name(name, {
            "status": "captured", "names": [{"name": name, "source": "og:site_name"}]})
        self.assertEqual(state, "branding_consistent")

    def test_keyword_signal_and_shorter_brand_never_prove_violation(self):
        state, signals, assessment = review.screen_name("Example Cooling Best AC Repair", {
            "status": "captured", "names": [{"name": "Example Cooling", "source": "logo alt text"}]})
        self.assertEqual(state, "needs_review")
        self.assertIn("shorter_website_brand", {s["code"] for s in signals})
        self.assertIn("does not establish", assessment)

    def test_no_evidence_is_not_a_clean_bill_of_health(self):
        state, _, assessment = review.screen_name("Example Mechanical", {"status": "unavailable"})
        self.assertEqual(state, "unavailable")
        self.assertIn("no name-compliance conclusion", assessment)

    def test_parser_does_not_use_service_page_title_as_business_name(self):
        parser = review.BrandingParser()
        parser.feed('<title>Best Furnace Repair Near Me | Example</title>'
                    '<meta property="og:site_name" content="Example Heating">'
                    '<script type="application/ld+json">{"@type":"Organization",'
                    '"name":"Example Heating","legalName":"Example Holdings LLC"}</script>')
        result = parser.finish()
        self.assertNotIn(result["title"], [n["name"] for n in result["names"]])
        self.assertIn({"name": "Example Holdings LLC", "source": "JSON-LD legalName"}, result["names"])

    def test_export_missing_profile_is_unavailable_not_inspected(self):
        result = review.export(self.root)
        self.assertEqual(result["collection"]["profile_complete"], 0)
        self.assertEqual(result["study_plan_sha256"], "a" * 64)
        self.assertTrue(all(c["status"] == "unavailable" for c in result["cases"]))
        self.assertTrue(all(c["profile"]["checked_at"] is None for c in result["cases"]))

    def test_export_rejects_changed_bound_study(self):
        raw = review.load(self.study)
        raw["evidence"]["plan_sha256"] = "b" * 64
        review.save(self.study, raw)
        with self.assertRaises(ValueError):
            review.export(self.root)

    def test_freshness_rejects_unknown_future_and_old_dates(self):
        for timestamp in (None, "", "not-a-date", "2099-01-01T00:00:00+00:00",
                          "2000-01-01T00:00:00+00:00"):
            self.assertFalse(review.fresh(timestamp))
        self.assertTrue(review.fresh(dt.datetime.now(dt.timezone.utc).isoformat()))

    def test_missing_site_timestamp_cannot_corroborate_current_name(self):
        url = "https://example.test/"
        path = self.profile(items=[{"cid": "22", "title": "Example Heating & Air", "url": url}])
        profile = review.load(path)
        profile["checked_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        review.save(path, profile)
        site = self.root / "websites" / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        review.save(site, {"status": "captured", "url": url,
                          "names": [{"name": "Example Heating & Air", "source": "og:site_name"}]})
        case = next(c for c in review.export(self.root)["cases"] if c["cid"] == "22")
        self.assertNotEqual(case["status"], "branding_consistent")

    def test_analyst_attachment_preserves_screen_and_never_approves_reports(self):
        case, _, _, path, _ = self.analyst_fixture()
        review.attach_source_reviews(self.root, [case])
        self.assertEqual(case["status"], "branding_consistent")
        self.assertEqual(case["automated_status"], "no_obvious_signal")
        self.assertEqual(case["automated_assessment"], "Screen only")
        self.assertEqual(case["source_review"]["sha256"], review.sha(path))
        self.assertEqual(case["source_review"]["counterevidence"], "Signage unchecked.")
        self.assertFalse(case["source_review"]["report_ready"])

    def test_analyst_attachment_rejects_unknown_case(self):
        case, note, document, path, _ = self.analyst_fixture()
        document["cases"] = {"999": note}
        review.save(path, document)
        with self.assertRaisesRegex(ValueError, "unknown"):
            review.attach_source_reviews(self.root, [case])

    def test_analyst_attachment_rejects_duplicate_case_files(self):
        case, _, document, _, _ = self.analyst_fixture()
        review.save(self.root / "manual-review-second.json", document)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            review.attach_source_reviews(self.root, [case])

    def test_analyst_attachment_rejects_superseded_profile_name(self):
        case, _, _, _, _ = self.analyst_fixture()
        case["profile"]["name"] = "New Example Name"
        with self.assertRaisesRegex(ValueError, "superseded"):
            review.attach_source_reviews(self.root, [case])

    def test_analyst_attachment_rejects_changed_evidence_file(self):
        case, _, _, _, profile = self.analyst_fixture()
        profile.write_text("changed response", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            review.attach_source_reviews(self.root, [case])

    def test_analyst_attachment_rejects_unbound_profile_hash(self):
        case, note, document, path, _ = self.analyst_fixture()
        note["sources"] = [{"sha256": case["profile"]["sha256"], "url": "https://example.test/"}]
        review.save(path, document)
        with self.assertRaises(ValueError):
            review.attach_source_reviews(self.root, [case])

    def test_analyst_attachment_rejects_other_profile_source(self):
        case, note, document, path, _ = self.analyst_fixture()
        other = self.profile("33")
        note["sources"] = [{"evidence_path": str(other.relative_to(self.root)),
                            "sha256": review.sha(other)}]
        review.save(path, document)
        with self.assertRaisesRegex(ValueError, "bind"):
            review.attach_source_reviews(self.root, [case])

    def test_analyst_attachment_does_not_promote_stale_profile(self):
        case, _, _, _, _ = self.analyst_fixture()
        case["profile"]["status"] = "stale"
        case["profile"]["checked_at"] = "2000-01-01T00:00:00+00:00"
        review.attach_source_reviews(self.root, [case])
        self.assertNotIn("source_review", case)

    def test_analyst_attachment_skips_stale_notes(self):
        case, note, document, path, _ = self.analyst_fixture()
        note["checked_at"] = "2000-01-01T00:00:00+00:00"
        review.save(path, document)
        review.attach_source_reviews(self.root, [case])
        self.assertNotIn("source_review", case)

    def test_streetview_quest_filters_time_machine_and_steps_along_road(self):
        from unittest import mock
        # Simulate an indoor 1-node response at radius=18 followed by an outdoor road graph at radius=30
        indoor_resp = [None, [None, [2, "indoor_pano"], None, None, None, [[
            [1], [[None, None, 30.3000, -97.7000]], None,
            [[[[2, "indoor_pano"], None, [[None, None, 30.3000, -97.7000]]]]],
            None, None, None, None, []
        ]]]]
        outdoor_resp = [None, [None, [2, "pano_v0"], None, None, None, [[
            [1], [[None, None, 30.30015, -97.7000]], None,
            [[
                [[2, "pano_v0"], None, [[None, None, 30.30015, -97.7000]]],
                [[2, "pano_v1"], None, [[None, None, 30.30015, -97.70015]]],
                [[2, "pano_old_2018"], None, [[None, None, 30.30016, -97.7000]]],
                [[2, "pano_v2"], None, [[None, None, 30.30015, -97.69985]]],
            ]],
            None, None, None, None, [[2, [2018, 5]]]
        ]]]]
        calls = iter([indoor_resp, outdoor_resp])
        class FakeResp:
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return json.dumps(self.payload).encode("utf-8")
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: FakeResp(next(calls))):
            urls = review.streetview_quest_urls(30.3000, -97.7000, max_vantages=3)
        self.assertEqual(len(urls), 3)
        self.assertTrue(any("panoid=pano_v0" in u for u in urls))
        self.assertTrue(any("panoid=pano_v1" in u for u in urls))
        self.assertTrue(any("panoid=pano_v2" in u for u in urls))
        self.assertFalse(any("pano_old_2018" in u for u in urls))
        self.assertFalse(any("indoor_pano" in u for u in urls))

    def test_optional_jev_signage_graceful_when_absent(self):
        from unittest import mock
        with mock.patch.dict("sys.modules", {"legends_jev": None, "legends_jev.core": None}):
            res = review.try_jev_optical_signage("Example Pizza", ["Pizza"], {"main": self.root / "missing.jpg"})
        self.assertEqual(res["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
