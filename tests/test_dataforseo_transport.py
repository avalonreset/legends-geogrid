"""Verify the public shared transport boundary without paid requests."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import local_heatmap_poc as runner


class KitTransportTests(TestCase):
    def test_live_uses_kit_and_retains_empty_task_evidence(self):
        payload = {"status_code": 20000, "tasks": [{"status_code": 40102, "result": []}]}
        request = Mock(return_value=payload)
        kit = SimpleNamespace(API_ROOT="https://api.dataforseo.com/v3", api_request=request)
        with patch.dict(sys.modules, {"legends_dataforseo": kit}):
            result = runner.call_dataforseo_live_task({"keyword": "pizza"}, 30)
        self.assertIs(result, payload)
        request.assert_called_once_with("/serp/google/maps/live/advanced", [{"keyword": "pizza"}],
                                        timeout=30, confirm=True, consumer="legends-geogrid")

    def test_polling_is_get_without_paid_opt_in(self):
        request = Mock(return_value={"tasks": [{"status_code": 40601}]})
        kit = SimpleNamespace(API_ROOT="https://api.dataforseo.com/v3", api_request=request)
        with patch.dict(sys.modules, {"legends_dataforseo": kit}):
            runner.http_json(runner.DATAFORSEO_MAPS_TASK_GET_ADVANCED_URL.format(task_id="test"), 10)
        request.assert_called_once_with("/serp/google/maps/task_get/advanced/test", None,
                                        timeout=10, confirm=False, consumer="legends-geogrid")

    def test_missing_kit_explains_installation(self):
        with patch.dict(sys.modules, {"legends_dataforseo": None}):
            with self.assertRaisesRegex(RuntimeError, "requirements-dataforseo.txt"):
                runner.call_dataforseo_live_task({}, 10)

    def test_foreign_endpoint_is_rejected(self):
        request = Mock()
        kit = SimpleNamespace(API_ROOT="https://api.dataforseo.com/v3", api_request=request)
        with patch.dict(sys.modules, {"legends_dataforseo": kit}):
            with self.assertRaises(ValueError):
                runner.http_json("https://example.com/v3", 10, [{}])
        request.assert_not_called()
