"""Credential-free tests for pre-scan evidence freshness and query-review validation."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from query_review import format_markdown, main as query_review_main, review_plan
import study
from study_contract import digest, validate
from test_study import fixture


class QueryReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path, self.plan = fixture(self.root)

    def save(self) -> None:
        self.path.write_text(json.dumps(self.plan), encoding="utf-8")

    def test_validate_receipt_embeds_query_review(self) -> None:
        _, receipt = validate(self.path)
        self.assertIn("query_review", receipt)
        qr = receipt["query_review"]
        self.assertEqual(qr["schema"], "geogrid-query-review/v1")
        self.assertEqual(qr["plan_sha256"], receipt["plan_sha256"])
        self.assertTrue(qr["adapter_boundary"]["standalone_mode"])
        self.assertFalse(qr["adapter_boundary"]["home_runtime_required"])

    def test_source_ages_mixed_vintage_and_historical_frozen_preservation(self) -> None:
        now = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
        # Set website and GBP to 25 days old (aging >= 14d), demand and pilots to 0 days old
        twenty_five_days_ago = (now - timedelta(days=25)).isoformat()
        fresh_iso = now.isoformat()
        for src in self.plan["sources"]:
            if src["kind"] in ("website", "gbp"):
                src["observed_at"] = twenty_five_days_ago
            else:
                src["observed_at"] = fresh_iso
        self.save()

        review = review_plan(self.path, now=now, warn_age_days=10.0, max_age_days=28.0)
        sf = review["source_freshness"]
        self.assertEqual(sf["oldest_age_days"], 25.0)
        self.assertEqual(sf["newest_age_days"], 0.0)
        self.assertEqual(sf["age_spread_days"], 25.0)
        self.assertTrue(sf["mixed_vintage"])
        self.assertEqual(sorted(sf["aging_source_ids"]), ["gbp", "site"])
        self.assertEqual(sf["expired_source_ids"], [])
        self.assertTrue(review["measurement_posture"]["source_age_within_window"])
        self.assertEqual(review["measurement_posture"]["advisory_scope"], "review_not_collection_authorization")
        self.assertTrue(review["measurement_posture"]["review_not_collection_authorization"])
        self.assertEqual(review["measurement_posture"]["collection_readiness"], "not_assessed")
        self.assertNotIn("eligible_for_new_paid_collection", review["measurement_posture"])
        self.assertTrue(
            any("28-day contract window, but older than the 10-day freshness warning threshold" in f for f in review["measurement_posture"]["flags"])
        )
        self.assertEqual(review["status"], "review_recommended")
        self.assertIn("not proof that external website or GBP facts changed", sf["certainty_note"])

        # Now test >30 day historical study: validate() rejects for new run, but review_plan()
        # marks historical_frozen without crashing or erasing historical queries
        forty_five_days_ago = (now - timedelta(days=45)).isoformat()
        self.plan["sources"][0]["observed_at"] = forty_five_days_ago
        self.save()
        with self.assertRaisesRegex(ValueError, "older than 30 days"):
            validate(self.path, now=now)

        frozen_review = review_plan(self.path, now=now)
        self.assertEqual(frozen_review["status"], "historical_frozen")
        self.assertEqual(frozen_review["measurement_posture"]["mode"], "historical_frozen_evidence")
        self.assertFalse(frozen_review["measurement_posture"]["source_age_within_window"])
        self.assertEqual(frozen_review["measurement_posture"]["advisory_scope"], "review_not_collection_authorization")
        self.assertEqual(frozen_review["measurement_posture"]["collection_readiness"], "not_assessed")
        self.assertTrue(frozen_review["measurement_posture"]["historical_study_frozen"])
        self.assertEqual(frozen_review["source_freshness"]["expired_source_ids"], ["site"])

        # Empty sources must never claim source_age_within_window or authorize collection
        self.plan["sources"] = []
        self.save()
        empty_review = review_plan(self.path, now=now)
        self.assertFalse(empty_review["measurement_posture"]["source_age_within_window"])
        self.assertEqual(empty_review["measurement_posture"]["advisory_scope"], "review_not_collection_authorization")
        self.assertEqual(empty_review["measurement_posture"]["collection_readiness"], "not_assessed")

    def test_synonym_overlap_gbp_coverage_and_candidate_dispositions(self) -> None:
        # Update GBP categories to include HVAC contractor, Air conditioning repair service,
        # Heating contractor (covered indirectly via furnace repair), and Plumbing contractor (unselected)
        gbp_path = self.root / "gbp.json"
        gbp_doc = json.loads(gbp_path.read_text(encoding="utf-8"))
        item = gbp_doc["tasks"][0]["result"][0]["items"][0]
        item["category"] = "HVAC contractor"
        item["additional_categories"] = [
            "Air conditioning repair service",
            "Heating contractor",
            "Plumbing contractor",
        ]
        gbp_path.write_text(json.dumps(gbp_doc), encoding="utf-8")
        next(s for s in self.plan["sources"] if s["id"] == "gbp")["sha256"] = digest(gbp_path)

        base_q = copy.deepcopy(self.plan["queries"][0])
        q1 = copy.deepcopy(base_q)
        q1["query"] = "air conditioning repair"
        q1["role"] = "user_requested"
        q1["user_instruction"] = "Owner restored exact historical comparison."
        q1["theme"] = {
            "id": "cooling-repair",
            "label": "Air conditioning repair",
            "customer_need": "Repair existing AC",
            "distinct_value": "Urgent repair vs replacement",
        }
        q2 = copy.deepcopy(base_q)
        q2["query"] = "air conditioning contractor"
        q2["role"] = "user_requested"
        q2["user_instruction"] = "Owner restored exact historical comparison."
        q2["theme"] = {
            "id": "cooling-contractor",
            "label": "Air conditioning contractor",
            "customer_need": "Hire AC contractor",
            "distinct_value": "Contractor selection vs repair",
        }
        q3 = copy.deepcopy(base_q)
        q3["query"] = "furnace repair"
        q3["role"] = "service"
        q3["theme"] = {
            "id": "furnace-repair",
            "label": "Furnace repair",
            "customer_need": "Repair furnace",
            "distinct_value": "Seasonal heating service",
        }
        q_rejected = {
            "query": "plumbing repair",
            "selected": False,
            "disposition": "rejected",
            "role": "service",
            "reason": "Plumbing is not promoted on the current homepage; excluded from HVAC baseline.",
        }
        q_deferred = {
            "query": "heat pump installation",
            "selected": False,
            "disposition": "deferred",
            "role": "service",
            "reason": "Deferred to phase 2 seasonal equipment study after dedicated service page capture.",
        }
        self.plan["queries"] = [q1, q2, q3, q_rejected, q_deferred]
        self.save()

        review = review_plan(self.path)
        cov = review["service_theme_coverage"]
        self.assertEqual(cov["selected_count"], 3)
        self.assertEqual(cov["non_selected_count"], 2)
        self.assertTrue(cov["non_selected_candidates_documented"])
        self.assertIn("Air conditioning repair service", cov["directly_matched_gbp_categories"])
        self.assertIn("Heating contractor", cov["indirect_or_partial_gbp_categories"])
        self.assertIn("Plumbing contractor", cov["unselected_gbp_categories"])

        overlaps = review["synonym_overlaps"]
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0]["queries"], ["air conditioning repair", "air conditioning contractor"])
        self.assertEqual(overlaps[0]["status"], "documented_comparison")
        self.assertIn("air_conditioning", overlaps[0]["shared_concepts"])

        decisions = review["query_decisions"]
        self.assertEqual([q["query"] for q in decisions["accepted"]], [
            "air conditioning repair",
            "air conditioning contractor",
            "furnace repair",
        ])
        self.assertEqual([q["query"] for q in decisions["rejected"]], ["plumbing repair"])
        self.assertEqual([q["query"] for q in decisions["deferred"]], ["heat pump installation"])

    def test_business_inputs_and_external_adapter_boundary(self) -> None:
        # Default plan without private inputs is allowed as an explicitly exploratory public study
        default_review = review_plan(self.path)
        self.assertTrue(default_review["business_inputs"]["public_study_allowed_without_private_inputs"])
        self.assertEqual(default_review["business_inputs"]["study_posture"], "explicitly_exploratory_public_study")
        for item in default_review["business_inputs"]["missing_business_inputs"]:
            self.assertEqual(item["status"], "unknown")
            self.assertFalse(item["required_for_first_use"])

        # Attach a local Study Library / Home evidence record and mark gsc_query_performance observed
        ext_file = self.root / "library-summary.json"
        ext_file.write_text(json.dumps({"note": "Prior banked baseline summary"}), encoding="utf-8")
        now_iso = datetime.now(timezone.utc).isoformat()
        self.plan["external_evidence"] = [
            {
                "id": "lib-note-1",
                "adapter": "study_library",
                "file": ext_file.name,
                "sha256": digest(ext_file),
                "observed_at": now_iso,
                "contract": "geogrid-library/v1",
            }
        ]
        self.plan["business_inputs"] = {
            "gsc_query_performance": {"status": "observed", "source_id": "site"},
        }
        self.save()

        review = review_plan(self.path)
        self.assertEqual(len(review["adapter_boundary"]["attached_external_records"]), 1)
        self.assertEqual(review["adapter_boundary"]["attached_external_records"][0]["adapter"], "study_library")
        provided = [x["input"] for x in review["business_inputs"]["provided_private_inputs"]]
        missing = [x["input"] for x in review["business_inputs"]["missing_business_inputs"]]
        self.assertEqual(provided, ["gsc_query_performance"])
        self.assertIn("crm_job_history", missing)
        self.assertIn("service_economics", missing)

        # Tampering with external evidence file fails hash verification
        ext_file.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "external evidence hash mismatch"):
            review_plan(self.path)

    def test_request_payload_hash_and_pending_or_empty_rejected(self) -> None:
        req_file = self.root / "demand-req.json"
        req_file.write_text(json.dumps({"body": [{"keywords": ["pizza restaurant"]}]}), encoding="utf-8")
        demand_src = next(s for s in self.plan["sources"] if s["id"] == "demand")
        demand_src["request_file"] = req_file.name
        demand_src["request_sha256"] = digest(req_file)
        self.save()

        # Valid request hash passes
        review = review_plan(self.path)
        self.assertEqual(review["schema"], "geogrid-query-review/v1")

        # Tampered request payload fails
        req_file.write_text(json.dumps({"body": []}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "request payload hash mismatch"):
            review_plan(self.path)

        # Matching hash but empty body fails
        demand_src["request_sha256"] = digest(req_file)
        self.save()
        with self.assertRaisesRegex(ValueError, "empty or missing body"):
            review_plan(self.path)

        # Restore valid request body, then test pending (20100) and empty result rejection
        req_file.write_text(json.dumps({"body": [{"keywords": ["pizza restaurant"]}]}), encoding="utf-8")
        demand_src["request_sha256"] = digest(req_file)
        demand_path = self.root / "demand.json"
        demand_doc = json.loads(demand_path.read_text(encoding="utf-8"))
        demand_doc["tasks"][0]["status_code"] = 20100
        demand_path.write_text(json.dumps(demand_doc), encoding="utf-8")
        demand_src["sha256"] = digest(demand_path)
        self.save()
        with self.assertRaisesRegex(ValueError, "pending or failed provider task"):
            review_plan(self.path)

        # Restore status 20000 but empty items list
        demand_doc["tasks"][0]["status_code"] = 20000
        demand_doc["tasks"][0]["result"][0]["items"] = []
        demand_path.write_text(json.dumps(demand_doc), encoding="utf-8")
        demand_src["sha256"] = digest(demand_path)
        self.save()
        with self.assertRaisesRegex(ValueError, "empty provider result items"):
            review_plan(self.path)

    def test_refresh_dir_manifest_validation(self) -> None:
        refresh = self.root / "refresh"
        (refresh / "pilots").mkdir(parents=True)
        req = refresh / "pilots" / "profile-post.json"
        req.write_text(json.dumps({"request": {"body": [{"keyword": "cid:123"}]}}), encoding="utf-8")
        resp = refresh / "pilots" / "task1-result.json"
        now_iso = datetime.now(timezone.utc).isoformat()
        resp_payload = {
            "retrieved_at": now_iso,
            "endpoint": "/business_data/google/my_business_info/task_get/task1",
            "response": {
                "status_code": 20000,
                "tasks": [
                    {
                        "id": "task1",
                        "status_code": 20000,
                        "result_count": 1,
                        "data": {"keyword": "cid:123"},
                        "result": [
                            {
                                "items": [
                                    {
                                        "cid": "123",
                                        "title": "Example Pizza",
                                        "category": "Pizza restaurant",
                                        "additional_categories": ["Italian restaurant"],
                                        "domain": "example.org",
                                    }
                                ]
                            }
                        ],
                    }
                ],
            },
        }
        resp.write_text(json.dumps(resp_payload), encoding="utf-8")
        manifest = {
            "schema": "geogrid-refresh-evidence/v1",
            "verified_at": now_iso,
            "business_cid": "123",
            "method": "standard",
            "tasks": 1,
            "submission_cost_usd": 0.0015,
            "entries": [
                {
                    "task_id": "task1",
                    "request_file": "pilots/profile-post.json",
                    "request_sha256": digest(req),
                    "response_file": "pilots/task1-result.json",
                    "response_sha256": digest(resp),
                    "retrieved_at": now_iso,
                    "endpoint": "/business_data/google/my_business_info/task_get/task1",
                    "status_code": 20000,
                    "result_count": 1,
                }
            ],
        }
        (refresh / "provider-evidence-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        res = review_plan(refresh_dir=refresh)
        self.assertEqual(res["refresh_evidence"]["tasks_verified"], 1)
        self.assertTrue(res["refresh_evidence"]["all_request_and_response_hashes_valid"])
        self.assertEqual(res["refresh_evidence"]["refreshed_gbp_profile"]["primary_category"], "Pizza restaurant")
        self.assertEqual(res["measurement_posture"]["advisory_scope"], "review_not_collection_authorization")
        self.assertTrue(res["measurement_posture"]["review_not_collection_authorization"])
        self.assertEqual(res["measurement_posture"]["collection_readiness"], "not_assessed")
        self.assertNotIn("eligible_for_new_paid_collection", res["measurement_posture"])
        self.assertEqual(res["status"], "review_recommended")
        self.assertTrue(any("1 provider tasks" in f for f in res["measurement_posture"]["flags"]))
        self.assertFalse(any("60" in f or "148" in f for f in res["measurement_posture"]["flags"]))

        # Old manifest tasks in refresh branch mark source_age_within_window=False and status=historical_frozen
        future_now = datetime.now(timezone.utc) + timedelta(days=40)
        expired_res = review_plan(refresh_dir=refresh, now=future_now, warn_age_days=10.0, max_age_days=25.0)
        self.assertEqual(expired_res["status"], "historical_frozen")
        self.assertFalse(expired_res["measurement_posture"]["source_age_within_window"])
        self.assertEqual(expired_res["measurement_posture"]["collection_readiness"], "not_assessed")
        self.assertEqual(expired_res["source_freshness"]["expired_source_ids"], ["task1"])
        self.assertTrue(any("25-day new-collection window" in f for f in expired_res["measurement_posture"]["flags"]))

        # Reject fabricated opportunity_score in analysis/query-review.json
        (refresh / "analysis").mkdir()
        (refresh / "analysis" / "query-review.json").write_text(
            json.dumps({"schema": "geogrid-query-review/v1", "opportunity_score": 95}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "opportunity_score"):
            review_plan(refresh_dir=refresh)

    def test_competitive_plan_alignment_and_cli_outputs(self) -> None:
        comp_path = self.root / "competitive-plan.json"
        comp_plan = {
            "schema": "legends-geogrid-competitive-plan/v1",
            "source_study_plan": str(self.path),
            "measurement_settings": {
                "method": "standard",
                "depth": 20,
                "zoom": 13,
                "device": "desktop",
                "search_this_area": False,
                "language_code": "en",
                "se_domain": "google.com",
            },
            "composition": {"mode": "reused_from_archive"},
            "query_selection": [
                {"query_id": "q1", "query": "pizza restaurant"},
            ],
        }
        comp_path.write_text(json.dumps(comp_plan), encoding="utf-8")

        out_json = self.root / "query-review.json"
        out_md = self.root / "query-review.md"
        rc = study.main([
            "query-review",
            "--plan",
            str(self.path),
            "--competitive-plan",
            str(comp_path),
            "--output",
            str(out_json),
            "--markdown",
            str(out_md),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue(out_json.is_file())
        self.assertTrue(out_md.is_file())

        saved = json.loads(out_json.read_text(encoding="utf-8"))
        self.assertEqual(saved["measurement_posture"]["mode"], "composed_archive_reuse")
        self.assertTrue(saved["competitive_alignment"]["matches_study_plan_ids"])
        self.assertTrue(saved["competitive_alignment"]["matches_study_plan_order_and_text"])
        self.assertTrue(saved["competitive_alignment"]["matches_study_plan_ids_and_text"])
        self.assertTrue(saved["competitive_alignment"]["historical_query_ids_preserved"])

        # Mismatched query_id with identical query text is caught and flagged
        comp_plan["query_selection"][0]["query_id"] = "q_substituted"
        comp_path.write_text(json.dumps(comp_plan), encoding="utf-8")
        mismatch_res = review_plan(self.path, competitive_plan_path=comp_path)
        self.assertFalse(mismatch_res["competitive_alignment"]["matches_study_plan_ids"])
        self.assertTrue(mismatch_res["competitive_alignment"]["matches_study_plan_order_and_text"])
        self.assertFalse(mismatch_res["competitive_alignment"]["matches_study_plan_ids_and_text"])
        self.assertFalse(mismatch_res["competitive_alignment"]["historical_query_ids_preserved"])

        md_text = out_md.read_text(encoding="utf-8")
        self.assertIn("# Query & Evidence Review: Example Pizza", md_text)
        self.assertNotIn("\u2014", md_text)  # No em dashes allowed

        # Refuses to overwrite existing review artifact
        rc_dup = query_review_main(["--plan", str(self.path), "--output", str(out_json)])
        self.assertEqual(rc_dup, 2)


if __name__ == "__main__":
    unittest.main()
