import unittest

from score_llm_event_extractor_v3_4 import align_evidence_span


class EvidenceAlignmentTests(unittest.TestCase):
    def test_expands_ordered_ellipsis_fragments_to_exact_source_span(self):
        headline = (
            "Analysts Warn of Headwinds as Cryptos Gain Ahead of CPI Data, "
            "Luna Classic Pares Rally"
        )
        evidence = "Headwinds... Luna Classic Pares Rally"
        self.assertEqual(
            align_evidence_span(headline, evidence),
            "Headwinds as Cryptos Gain Ahead of CPI Data, Luna Classic Pares Rally",
        )

    def test_rejects_missing_ellipsis_fragment(self):
        with self.assertRaisesRegex(ValueError, "not an exact"):
            align_evidence_span("Bitcoin rises after CPI", "Bitcoin... FOMC")

    def test_preserves_existing_exact_span(self):
        self.assertEqual(
            align_evidence_span("Near Blockchain Moves Ahead With Phase One", "Phase One"),
            "Phase One",
        )


if __name__ == "__main__":
    unittest.main()
