import tempfile
import unittest
from pathlib import Path

from technical_execution_semantics import EVENT_ORDER, funding_payment, long_stop_transition
from technical_experiment_manifest import build_experiment_manifest, sha256_file


class TechnicalExecutionSemanticsTest(unittest.TestCase):
    def test_gap_through_stop_fills_at_adverse_open(self):
        result = long_stop_transition(
            [0, 90, 96, 88, 94],
            {"stop": 95, "peak": 100, "atr": 2},
            trail_atr=4,
        )
        self.assertEqual(result.fill_price, 90)
        self.assertEqual(result.reason, "gap_stop")

    def test_intrabar_breach_fills_at_preexisting_stop(self):
        result = long_stop_transition(
            [0, 100, 103, 94, 96],
            {"stop": 95, "peak": 100, "atr": 2},
            trail_atr=4,
        )
        self.assertEqual(result.fill_price, 95)
        self.assertEqual(result.reason, "intrabar_stop")

    def test_current_high_cannot_retroactively_tighten_same_bar_stop(self):
        first = long_stop_transition(
            [0, 100, 110, 99, 108],
            {"stop": 90, "peak": 100, "atr": 2},
            trail_atr=4,
        )
        self.assertIsNone(first.fill_price)
        self.assertEqual(first.next_peak, 110)
        second = long_stop_transition(
            [1, 108, 109, 101, 102],
            {"stop": 90, "peak": first.next_peak, "atr": 2},
            trail_atr=4,
        )
        self.assertEqual(second.effective_stop, 102)
        self.assertEqual(second.fill_price, 102)

    def test_funding_precedes_intrabar_stop_and_uses_position_notional(self):
        self.assertLess(EVENT_ORDER.index("funding_settlement"), EVENT_ORDER.index("intrabar_stop"))
        self.assertEqual(funding_payment(2, 100, 0.001), 0.2)
        self.assertEqual(funding_payment(2, 100, -0.001), -0.2)

    def test_manifest_hashes_result_sources_and_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "result.json"
            source = root / "source.py"
            data = root / "data.json"
            result.write_text("{}", encoding="utf-8")
            source.write_text("x = 1\n", encoding="utf-8")
            data.write_text("[]", encoding="utf-8")
            manifest = build_experiment_manifest(
                repo_root=root, result_path=result, configuration={"top_n": 1},
                data_paths=[data], source_paths=[source],
                execution_semantics="test", event_order=("open", "close"),
            )
            self.assertEqual(manifest["result"]["sha256"], sha256_file(result))
            self.assertEqual(manifest["data"][0]["sha256"], sha256_file(data))
            self.assertEqual(manifest["configuration"]["top_n"], 1)
            self.assertIn("git_status_porcelain", manifest)


if __name__ == "__main__":
    unittest.main()
