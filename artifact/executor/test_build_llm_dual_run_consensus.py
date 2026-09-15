import unittest

from build_llm_dual_run_consensus import build


def payload(score, confidence, digest="model"):
    return {
        "model": "llama", "model_digest": digest, "prompt_version": "p", "prompt_hash": "h",
        "records": [{
            "content_hash": "a" * 64, "information_date": "2020-01-01",
            "available_at": "2020-01-02T00:00:00+00:00", "source_snapshot_hash": "s",
            "article_count": 1, "selected_article_count": 1, "status": "success",
            "score": score, "confidence": confidence,
        }],
    }


class DualRunConsensusTest(unittest.TestCase):
    def test_disagreement_abstains_by_component_minimum(self):
        result = build(payload(0.4, 0.8), payload(0.2, 0.9))
        record = result["records"][0]
        self.assertEqual(record["score"], 0.2)
        self.assertEqual(record["confidence"], 0.8)
        self.assertEqual(result["summary"]["component_action_disagreements"], 1)
        self.assertEqual(result["summary"]["consensus_long"], 0)

    def test_rejects_different_model_digest(self):
        with self.assertRaises(ValueError):
            build(payload(0.4, 0.8), payload(0.4, 0.8, digest="other"))


if __name__ == "__main__":
    unittest.main()
