import unittest
import numpy as np

from technical_selection_inference import annualized_sharpe, cscv_pbo, moving_block_indices


class TechnicalSelectionInferenceTest(unittest.TestCase):
    def test_sharpe_prefers_higher_constant_edge_with_same_noise(self):
        noise = np.array([-0.01, 0.01] * 100)
        self.assertGreater(annualized_sharpe(noise + 0.002), annualized_sharpe(noise + 0.001))

    def test_block_indices_have_requested_length_and_bounds(self):
        indices = moving_block_indices(17, 5, np.random.default_rng(1))
        self.assertEqual(len(indices), 17)
        self.assertTrue(np.all((indices >= 0) & (indices < 17)))

    def test_cscv_detects_unstable_alternating_winners(self):
        matrix = np.zeros((80, 4))
        matrix[:40, 0] = 0.01
        matrix[40:, 0] = -0.01
        matrix[:40, 1] = -0.01
        matrix[40:, 1] = 0.01
        matrix[:, 2] = np.tile([-0.001, 0.001], 40)
        matrix[:, 3] = np.tile([0.001, -0.001], 40)
        result = cscv_pbo(matrix, partitions=8)
        self.assertEqual(result["combinations"], 70)
        self.assertGreater(result["pbo"], 0.4)


if __name__ == "__main__":
    unittest.main()
