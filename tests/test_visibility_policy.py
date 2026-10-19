"""Prevent paid regional studies from silently inheriting viewport clipping."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from visibility_policy import validate_visibility_policy
from competitive_collect import adapt_plan, collect, make_task_payload, fingerprint_task
from competitive_queue import POST_ENDPOINT
from test_competitive_collect import make_sample_plan
from test_study import fixture
from study import run


class VisibilityPolicyTests(unittest.TestCase):
    def test_open_search_allowed_but_missing_or_restricted_controls_rejected(self):
        validate_visibility_policy({"search_this_area": False})
        for settings in ({}, {"search_this_area": True}):
            with self.assertRaisesRegex(ValueError, "rectangular"):
                validate_visibility_policy(settings)

    def test_viewport_requires_explicit_intent_and_reason(self):
        settings = {"search_this_area": True}
        validate_visibility_policy(settings, {"intent": "viewport", "rationale": "Bounded viewport experiment"})
        validate_visibility_policy(settings, diagnostic={"purpose": "Compare controls", "source_scan": "saved/scan"})
        for policy in ({"intent": "viewport"}, {"rationale": "test"}):
            with self.assertRaises(ValueError):
                validate_visibility_policy(settings, policy)

    def test_new_competitive_requests_default_to_open_search(self):
        with tempfile.TemporaryDirectory() as d:
            _, plan = make_sample_plan(Path(d))
            del plan["measurement_settings"]["search_this_area"]
            self.assertIs(adapt_plan(plan)["settings"]["search_this_area"], False)

    def test_competitive_guard_before_creating_run_or_calling_provider(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, plan = make_sample_plan(root)
            del plan["collection_policy"]
            plan["measurement_settings"]["method"] = "standard"
            path.write_text(json.dumps(plan))
            with patch("competitive_collect.validate_lineage", return_value=({}, {"plan_sha256": "fixture"})):
                with self.assertRaisesRegex(ValueError, "rectangular"):
                    collect(plan_path=path, output_dir=root / "scan", execute=True, confirm_cost_usd=1)
            self.assertFalse((root / "scan").exists())

    def test_study_entry_blocks_unacknowledged_restriction_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, plan = fixture(root)
            plan = json.loads(path.read_text())
            del plan["collection_policy"]
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "rectangular"):
                run(path, root / "scan", execute=True, ceiling=1)
            self.assertFalse((root / "scan").exists())

    def test_already_queued_restricted_tasks_remain_resumable_without_new_purchase(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path, plan = make_sample_plan(root)
            del plan["collection_policy"]
            plan["measurement_settings"]["method"] = "standard"
            path.write_text(json.dumps(plan))
            adapted = adapt_plan(plan)
            queued = {
                fingerprint_task(make_task_payload(q["query"], o, adapted["settings"]), POST_ENDPOINT): {}
                for q in adapted["queries"] for o in adapted["origins"]
            }
            with patch("competitive_collect.load_submissions", return_value=queued):
                result = collect(plan_path=path, output_dir=root / "scan")
            self.assertEqual(result["new_tasks"], 0)
            self.assertEqual(result["pending_tasks"], 6)
            self.assertEqual(result["estimated_cost_usd"], 0)
