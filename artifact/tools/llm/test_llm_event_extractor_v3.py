import unittest

from evaluate_llm_event_extractor_v3_stage1 import evaluate
from score_llm_event_extractor_v3 import align_evidence_span, parse_batch


def event(headline_id="a" * 64):
    return {
        "headline_id": headline_id, "btc_relevance": "direct", "event_type": "regulation",
        "affected_assets": ["Bitcoin"], "direction": "positive", "severity": 0.7,
        "reported_surprise": 0.4, "expected_horizon": "24h", "confidence": 0.8,
        "evidence_span": "Bitcoin ETF approved",
    }


class EventExtractorV3Test(unittest.TestCase):
    def test_align_evidence_restores_source_curly_quotes(self):
        headline = "Klarna will ‘embrace crypto,’ CEO says"
        self.assertEqual(align_evidence_span(headline, "'embrace crypto'"),
                         "‘embrace crypto,’")

    def test_parse_batch_requires_exact_evidence_and_id(self):
        expected = [{"headline_id": "a" * 64, "headline": "Bitcoin ETF approved today"}]
        parsed = parse_batch('{"results": [' + __import__("json").dumps(event()) + "]}", expected)
        self.assertEqual(parsed[0]["event_type"], "regulation")

    def test_parse_batch_maps_short_item_id_to_frozen_headline_id(self):
        expected = [{"headline_id": "a" * 64, "item_id": "1",
                     "headline": "Bitcoin ETF approved today"}]
        item = event()
        item["item_id"] = "1"
        del item["headline_id"]
        parsed = parse_batch(__import__("json").dumps({"results": [item]}), expected,
                             "ordinal_item_id")
        self.assertEqual(parsed[0]["headline_id"], "a" * 64)
        self.assertNotIn("item_id", parsed[0])

    def test_gate_passes_identical_runs(self):
        config = {"experiment_id": "test", "frozen_contract": {"stage1_sample": {"records": 1}},
                  "stage1_gate": {"required": {
                      "schema_success_each_run": 1, "headline_count_match_each_run": 1,
                      "headline_id_and_order_match_each_run": 1, "evidence_exact_substring_each_run": 1,
                      "btc_relevance_exact_agreement_min": 1, "event_type_exact_agreement_min": 1,
                      "direction_exact_agreement_min": 1, "expected_horizon_exact_agreement_min": 1,
                      "affected_assets_mean_jaccard_min": 1, "severity_mean_absolute_difference_max": 0,
                      "reported_surprise_mean_absolute_difference_max": 0,
                      "confidence_mean_absolute_difference_max": 0,
                      "continuous_field_max_absolute_difference_max": 0,
                  }}}
        run = {"records": [{**event(), "status": "success"}], "summary": {"success": 1, "errors": 0}}
        self.assertTrue(evaluate(config, run, run)["passed"])


if __name__ == "__main__":
    unittest.main()
