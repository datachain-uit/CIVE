import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_causal_pipeline import write_json
from score_llm_daily_information_sets import PROMPT_VERSION, save, stratified_sample


class DailyScorerTest(unittest.TestCase):
    def test_stratified_sample_spans_each_year(self):
        records = [
            {"information_date": f"{year}-{month:02d}-01"}
            for year in (2020, 2021) for month in range(1, 7)
        ]
        selected = stratified_sample(records, 2)
        self.assertEqual([item["information_date"] for item in selected], [
            "2020-01-01", "2020-06-01", "2021-01-01", "2021-06-01"
        ])

    def test_checkpoint_persists_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "checkpoint.json"
            save(output, "run1", "model", "digest", [], disable_thinking=True, workers=2,
                 seed_checkpoint={"path": "seed.json", "records": 3})
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["prompt_version"], PROMPT_VERSION)
            self.assertEqual(payload["summary"]["attempted"], 0)
            self.assertFalse(payload["thinking"])
            self.assertEqual(payload["workers"], 2)
            self.assertEqual(payload["seed_checkpoint"]["records"], 3)

    def test_atomic_writer_retries_transient_windows_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            original = Path.replace
            attempts = 0

            def transient_lock(path, target):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("transient lock")
                return original(path, target)

            with patch.object(Path, "replace", transient_lock), patch("llm_causal_pipeline.time_module.sleep"):
                write_json(output, {"ok": True})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"ok": True})
            self.assertEqual(attempts, 2)


if __name__ == "__main__":
    unittest.main()
