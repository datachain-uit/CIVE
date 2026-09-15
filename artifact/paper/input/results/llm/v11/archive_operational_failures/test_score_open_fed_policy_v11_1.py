import unittest
from score_open_fed_policy_v11_1 import align_evidence


class EvidenceAlignmentTest(unittest.TestCase):
    def test_exact_is_unchanged(self):
        self.assertEqual(align_evidence("alpha beta gamma" * 4, "alpha beta gamma" * 3), ("alpha beta gamma" * 3, False))

    def test_non_contiguous_join_uses_longest_exact_segment(self):
        first = "strong capital levels, allowing continued lending during a severe recession"
        text = first + "\n\nA paragraph omitted here.\n\nAll banks remained above minimums."
        evidence = first + ". All banks remained above minimums."
        aligned, fallback = align_evidence(text, evidence)
        self.assertTrue(fallback)
        self.assertEqual(aligned, first)

    def test_short_match_is_rejected(self):
        with self.assertRaises(ValueError):
            align_evidence("A real source sentence.", "unrelated paraphrase")


if __name__ == "__main__":
    unittest.main()
