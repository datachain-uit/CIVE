import unittest

import numpy as np

from run_fulltext_market_impact_v5 import (
    aggregate_buckets,
    circular_block_indices,
    metrics,
)


class RunFulltextMarketImpactV5Tests(unittest.TestCase):
    def test_aggregate_bucket_shape_and_normalization(self):
        articles = np.asarray([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        result = aggregate_buckets(articles, [2, 1])
        self.assertEqual(result.shape, (2, 4))
        self.assertAlmostEqual(np.linalg.norm(result[0, :2]), 1.0)
        self.assertAlmostEqual(np.linalg.norm(result[0, 2:]), 1.0)

    def test_circular_blocks_return_requested_length(self):
        indices = circular_block_indices(10, 4, np.random.default_rng(7))
        self.assertEqual(len(indices), 10)
        self.assertTrue(np.all((0 <= indices) & (indices < 10)))

    def test_metrics_perfect_prediction(self):
        y = np.asarray([-1.0, 0.0, 1.0])
        result = metrics(y, y.copy())
        self.assertEqual(result["mse"], 0.0)
        self.assertAlmostEqual(result["pearson"], 1.0)


if __name__ == "__main__":
    unittest.main()
