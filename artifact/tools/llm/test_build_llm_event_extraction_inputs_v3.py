import unittest

from build_llm_event_extraction_inputs_v3 import parse_headline_lines


class LlmEventExtractionInputsV3Test(unittest.TestCase):
    def test_parse_preserves_headline_punctuation(self):
        rows = parse_headline_lines(
            "- [09:20 UTC | example.com | Bitcoin] ETF approved: BTC jumps 5%"
        )
        self.assertEqual(rows[0]["domain"], "example.com")
        self.assertEqual(rows[0]["coin"], "Bitcoin")
        self.assertEqual(rows[0]["title"], "ETF approved: BTC jumps 5%")

    def test_invalid_line_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_headline_lines("ETF approved")


if __name__ == "__main__":
    unittest.main()
