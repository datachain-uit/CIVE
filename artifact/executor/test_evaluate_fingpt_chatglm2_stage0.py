import tempfile
import unittest
from pathlib import Path

from evaluate_fingpt_chatglm2_stage0 import CONTRACT_HASH, first_headlines, parse_label


class FinGptChatGlmStage0Test(unittest.TestCase):
    def test_contract_hash_is_pinned(self):
        self.assertEqual(
            CONTRACT_HASH,
            "391a70c9f75099f46dbc978b669b115efc03df9e87b2269a3472f2af3e6be168",
        )

    def test_parse_label_requires_exactly_one_unique_label(self):
        self.assertEqual(parse_label("positive"), "positive")
        with self.assertRaises(ValueError):
            parse_label("positive or negative")
        with self.assertRaises(ValueError):
            parse_label("unclear")

    def test_first_headlines_obeys_metadata_contract(self):
        payload = '{"records":[{"text":"- [00:00 UTC | x | BTC] One\\n- [01:00 UTC | y | BTC] Two"}]}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(payload, encoding="utf-8")
            self.assertEqual(first_headlines(path, 2), ["One", "Two"])


if __name__ == "__main__":
    unittest.main()
