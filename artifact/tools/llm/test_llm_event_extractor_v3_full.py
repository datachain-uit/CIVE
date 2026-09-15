import json
import tempfile
import unittest
from pathlib import Path

from score_llm_event_extractor_v3_full import append_line, checkpoint_header, load_checkpoint


class FullExtractorCheckpointTest(unittest.TestCase):
    def test_checkpoint_resume_preserves_order(self):
        config = {
            "experiment_id": "test-full",
            "candidate": {"model": "model", "digest": "digest"},
            "frozen_contract": {
                "prompt": {"sha256": "p"}, "response_schema": {"sha256": "s"},
                "postprocessor": {"sha256": "x"},
            },
        }
        header = checkpoint_header(config, "c", "i", "run")
        source = [{"headline_id": str(index)} for index in range(5)]
        records = [{"headline_id": str(index), "status": "success"} for index in range(4)]
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.ndjson"
            append_line(checkpoint, header)
            append_line(checkpoint, {"type": "batch", "batch_index": 0,
                                     "records": records})
            resumed = load_checkpoint(checkpoint, header, source, 4)
        self.assertEqual([item["headline_id"] for item in resumed], ["0", "1", "2", "3"])

    def test_checkpoint_rejects_noncontiguous_batch(self):
        config = {
            "experiment_id": "test-full",
            "candidate": {"model": "model", "digest": "digest"},
            "frozen_contract": {
                "prompt": {"sha256": "p"}, "response_schema": {"sha256": "s"},
                "postprocessor": {"sha256": "x"},
            },
        }
        header = checkpoint_header(config, "c", "i", "run")
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.ndjson"
            checkpoint.write_text(json.dumps(header) + "\n" + json.dumps({
                "type": "batch", "batch_index": 1,
                "records": [{"headline_id": "0", "status": "success"}],
            }) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_checkpoint(checkpoint, header, [{"headline_id": "0"}], 4)


if __name__ == "__main__":
    unittest.main()
