import copy
import unittest

from audit_llm_determinism import audit


def payload(records):
    return {
        "model": "model",
        "model_digest": "digest",
        "prompt_version": "prompt-v1",
        "prompt_hash": "prompt-hash",
        "records": records,
    }


def record(content_hash, score, confidence=0.8):
    return {
        "content_hash": content_hash,
        "status": "success",
        "score": score,
        "confidence": confidence,
    }


class DeterminismAuditTests(unittest.TestCase):
    def test_reports_score_and_action_disagreement(self):
        left = payload([record("a", 0.3), record("b", -0.2)])
        right = payload([record("a", 0.2), record("b", -0.2)])

        result = audit(left, right)

        self.assertEqual(result["exact_score_agreement"], 1)
        self.assertEqual(result["long_flat_action_disagreements"], 1)
        self.assertEqual(result["long_flat_action_agreement_rate"], 0.5)
        self.assertFalse(result["action_deterministic"])

    def test_rejects_nonidentical_information_sets(self):
        left = payload([record("a", 0.3)])
        right = copy.deepcopy(left)
        right["records"][0]["content_hash"] = "b"

        with self.assertRaisesRegex(ValueError, "identical information sets"):
            audit(left, right)


if __name__ == "__main__":
    unittest.main()
