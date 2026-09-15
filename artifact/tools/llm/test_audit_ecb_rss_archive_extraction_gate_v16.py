import unittest

from audit_ecb_rss_archive_extraction_gate_v16 import audit


def source(record_id: str, capture: str) -> dict:
    return {"record_id": record_id, "archive_capture_at": capture, "text": "TITLE: Bitcoin ETF approved"}


def extracted(record_id: str, capture: str, relevance: str = "direct") -> dict:
    return {
        "record_id": record_id, "headline_id": record_id, "archive_capture_at": capture,
        "status": "success", "error": None, "btc_relevance": relevance,
        "event_type": "etf_institutional_flow", "affected_assets": ["BTC"],
        "direction": "positive", "severity": 0.8, "reported_surprise": 0.5,
        "expected_horizon": "24h", "confidence": 0.9,
        "evidence_span": "Bitcoin ETF approved",
    }


class EcbRssV16ExtractionGateTests(unittest.TestCase):
    def payloads(self, minimum: int = 2):
        times = ("2025-01-01T00:00:00+00:00", "2025-01-02T00:00:00+00:00")
        corpus = {"corpus_id": "ecb-rss-internet-archive-v16", "records": [source(str(i), t) for i, t in enumerate(times)]}
        rows = [extracted(str(i), t) for i, t in enumerate(times)]
        extraction = {
            "status": "EXTRACTION_COMPLETE_OUTCOME_JOIN_PROHIBITED", "records": rows,
            "summary": {"success": 2, "errors": 0}, "outcomes_consulted": False,
            "trading_backtest_consulted": False,
        }
        predeclared = {
            "experiment_id": "test", "corpus": {"id": "ecb-rss-internet-archive-v16", "information_time": "archive_capture_at"},
            "data_gate": {"minimum_eligible_information_sets": minimum},
        }
        return corpus, extraction, predeclared

    def test_gate_passes_at_frozen_minimum(self):
        result = audit(*self.payloads(minimum=2))
        self.assertTrue(result["passed"])
        self.assertTrue(result["target_join_authorized"])

    def test_gate_fails_without_changing_eligibility(self):
        corpus, extraction, predeclared = self.payloads(minimum=2)
        extraction["records"][1]["btc_relevance"] = "indirect"
        result = audit(corpus, extraction, predeclared)
        self.assertFalse(result["passed"])
        self.assertEqual(result["counts"]["eligible_information_sets"], 1)
        self.assertEqual(result["counts"]["shortfall_information_sets"], 1)

    def test_evidence_must_be_source_substring(self):
        corpus, extraction, predeclared = self.payloads()
        extraction["records"][0]["evidence_span"] = "invented evidence"
        with self.assertRaisesRegex(ValueError, "substring"):
            audit(corpus, extraction, predeclared)


if __name__ == "__main__":
    unittest.main()

