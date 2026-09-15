import unittest
from datetime import datetime, timezone
from llm_causal_pipeline import aggregate_window, causal_availability, migrate_legacy_corpus, parse_model_response

class LlmCausalPipelineTest(unittest.TestCase):
    def test_date_only_becomes_available_next_day(self):
        _, available, precision = causal_availability("2022-10-14")
        self.assertEqual(available.isoformat(), "2022-10-15T00:00:00+00:00")
        self.assertEqual(precision, "date-only-next-day")

    def test_migration_deduplicates_and_drops_legacy_score(self):
        rows = [{"date":"2022-10-14","text":" A  headline ","sentiment_score":20}, {"date":"2022-10-14","text":"A headline"}]
        records, audit = migrate_legacy_corpus(rows, "test")
        self.assertEqual(len(records), 1); self.assertNotIn("sentiment_score", records[0])
        self.assertEqual(audit["duplicates_removed"], 1)

    def test_parser_rejects_extra_or_out_of_range_values(self):
        with self.assertRaises(ValueError): parse_model_response('{"score":2,"confidence":1,"reason_code":"x"}')
        with self.assertRaises(ValueError): parse_model_response('{"score":0,"confidence":1,"reason_code":"x","extra":1}')

    def test_aggregation_never_uses_future_item(self):
        rows = [
            {"status":"success","available_at":"2026-08-14T10:00:00+00:00","score":.5,"content_hash":"a"*64},
            {"status":"success","available_at":"2026-08-14T13:00:00+00:00","score":-1,"content_hash":"b"*64},
        ]
        result = aggregate_window(rows, datetime(2026,8,14,12,tzinfo=timezone.utc), minimum=1)
        self.assertEqual(result["score"], .5); self.assertEqual(result["successful_articles"], 1)

if __name__ == "__main__": unittest.main()
