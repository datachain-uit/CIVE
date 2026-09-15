import unittest
from datetime import datetime, timezone

from llm_lifecycle_adapter import build_targets


class LlmLifecycleAdapterTest(unittest.TestCase):
    def setUp(self):
        day = int(datetime(2020, 1, 2, tzinfo=timezone.utc).timestamp() * 1000)
        self.manifest = {"daily_membership": {str(day): ["BTCUSDT", "ETHUSDT"]}}

    def test_signal_executes_four_hours_after_availability(self):
        scores = {"model": "m", "records": [{
            "information_date": "2020-01-01", "available_at": "2020-01-02T00:00:00+00:00",
            "status": "success", "score": 0.3, "confidence": 0.7, "content_hash": "a" * 64,
        }]}
        result = build_targets(scores, self.manifest)
        execution = int(datetime(2020, 1, 2, 4, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(result["targets"][str(execution)], ["BTCUSDT"])

    def test_error_low_confidence_and_missing_membership_are_flat(self):
        base = {"information_date": "2020-01-01", "available_at": "2020-01-02T00:00:00+00:00",
                "content_hash": "b" * 64}
        cases = [
            {**base, "status": "error", "score": None, "confidence": None},
            {**base, "status": "success", "score": 0.8, "confidence": 0.69},
        ]
        for record in cases:
            self.assertEqual(build_targets({"records": [record]}, self.manifest)["summary"]["long_decisions"], 0)
        empty = {"daily_membership": {next(iter(self.manifest["daily_membership"])): ["ETHUSDT"]}}
        self.assertEqual(build_targets({"records": [{**base, "status": "success", "score": 0.8,
                                                       "confidence": 0.9}]}, empty)["summary"]["long_decisions"], 0)

    def test_missing_day_emits_explicit_flat_target(self):
        result = build_targets({"records": []}, self.manifest)
        self.assertEqual(result["summary"], {"decisions": 1, "long_decisions": 0, "flat_decisions": 1})
        self.assertEqual(next(iter(result["targets"].values())), [])
        self.assertEqual(result["decisions"][0]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
