import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from competitive_collect import adapt_plan, collect, load_ledger
from competitive_queue import POST_ENDPOINT
from study_contract import digest
from test_competitive_collect import make_sample_plan, make_mock_serp_response


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan_path, self.plan = make_sample_plan(self.root)
        self.plan["measurement_settings"].pop("method")
        self.source = self.root / "source.json"
        self.source.write_text("{}")
        self.plan["source_study_plan"] = str(self.source)
        self.plan_path.write_text(json.dumps(self.plan))
        self.out = self.root / "out"
        p = patch("competitive_collect.validate_study_plan", return_value=(
            {"business": self.plan["target_business"],
             "queries": [dict(q, selected=True) for q in self.plan["query_selection"]]},
            {"plan_sha256": digest(self.source)}))
        p.start()
        self.addCleanup(p.stop)
        self.calls = []
        self.tasks = {}
        self.ready = False

    def api(self, endpoint, payload=None, **kwargs):
        self.calls.append((endpoint, payload, kwargs))
        if endpoint == POST_ENDPOINT:
            results = []
            for task in payload:
                self.assertEqual(task["priority"], 1)
                task_id = f"task-{len(self.tasks)}"
                self.tasks[task_id] = task
                results.append({"id": task_id, "status_code": 20100, "cost": .0006, "data": task})
            return {"status_code": 20000, "cost": len(results) * .0006, "tasks": results}
        self.assertIn("/task_get/advanced/", endpoint)
        task_id = endpoint.rsplit("/", 1)[1]
        if not self.ready:
            return {"status_code": 20000, "cost": 0, "tasks": [{"id": task_id, "status_code": 40602}]}
        task = self.tasks[task_id]
        response = make_mock_serp_response(task["keyword"], task["tag"], 38.6442, -121.2678)
        response["cost"] = 0
        response["tasks"][0].update(id=task_id, cost=0)
        return response

    def run_collect(self, **kwargs):
        with patch.dict(sys.modules, legends_dataforseo=types.SimpleNamespace(api_request=self.api)):
            return collect(plan_path=self.plan_path, output_dir=self.out, execute=True, **kwargs)

    def test_default_standard_wait_resume_without_repurchase(self):
        self.assertEqual(adapt_plan(self.plan)["settings"]["method"], "standard")
        first = self.run_collect(confirm_cost_usd=.0036)
        self.assertEqual(first["status"], "queued")
        self.assertEqual(first["pending_tasks"], 6)
        self.assertAlmostEqual(first["run_total_cost_usd"], .0036)
        self.assertEqual(len([c for c in self.calls if c[0] == POST_ENDPOINT]), 1)
        self.assertFalse(load_ledger(self.out / "collection-ledger.jsonl")[1])
        self.ready = True
        self.calls.clear()
        final = self.run_collect(confirm_cost_usd=0)
        self.assertEqual(final["status"], "collected")
        self.assertEqual(final["actual_cost_usd"], 0)
        self.assertAlmostEqual(final["run_total_cost_usd"], .0036)
        self.assertTrue(all("/task_get/" in c[0] for c in self.calls))
        self.calls.clear()
        self.run_collect(confirm_cost_usd=0)
        self.assertEqual(self.calls, [])
        self.assertEqual(json.loads((self.out / "lane-1/parsed-grid.json").read_text())["measurement_settings"]["method"], "standard")

    def test_live_plan_requires_opt_in_before_dispatch(self):
        self.plan["measurement_settings"]["method"] = "live"
        self.plan_path.write_text(json.dumps(self.plan))
        with self.assertRaisesRegex(ValueError, "explicit user choice"):
            self.run_collect(confirm_cost_usd=1)
        self.assertEqual(self.calls, [])

    def test_live_research_requires_opt_in(self):
        from study import research
        request = self.root / "probe.json"
        request.write_text(json.dumps({"kind": "maps_probe", "body": [{"keyword": "example"}],
                                       "estimated_cost_usd": .002}))
        with self.assertRaisesRegex(ValueError, "explicit user choice"):
            research(request, self.out, execute=True, ceiling=.01)
        self.assertFalse(self.out.exists())

    def test_budget_rejection_never_posts(self):
        with self.assertRaisesRegex(ValueError, "exceeds confirmed"):
            self.run_collect(confirm_cost_usd=.0035)
        self.assertEqual(self.calls, [])

    def test_ambiguous_post_cannot_be_retried(self):
        def broken(*args, **kwargs):
            raise TimeoutError("ambiguous POST")
        with patch.dict(sys.modules, legends_dataforseo=types.SimpleNamespace(api_request=broken)):
            with self.assertRaises(TimeoutError):
                collect(plan_path=self.plan_path, output_dir=self.out, execute=True, confirm_cost_usd=.01)
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.run_collect(confirm_cost_usd=.01)
        self.assertEqual(self.calls, [])

    def test_submission_tampering_blocks_resume(self):
        self.run_collect(confirm_cost_usd=.01)
        next((self.out / "submissions").glob("*.json")).write_text("{}")
        self.calls.clear()
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            self.run_collect(confirm_cost_usd=0)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
