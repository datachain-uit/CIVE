import unittest

import numpy as np

from run_contrastive_market_impact_v6 import return_classes, supervised_contrastive_loss


class RunContrastiveMarketImpactV6Tests(unittest.TestCase):
    def test_return_classes_use_three_training_quantiles(self):
        labels, thresholds = return_classes(np.arange(12, dtype=float))
        self.assertEqual(set(labels.tolist()), {0, 1, 2})
        self.assertEqual(len(thresholds), 2)

    def test_supervised_contrastive_loss_is_finite(self):
        import torch

        projected = torch.nn.functional.normalize(torch.tensor([
            [1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9],
        ]), p=2, dim=1)
        labels = torch.tensor([0, 0, 1, 1])
        loss = supervised_contrastive_loss(torch, projected, labels, 0.1)
        self.assertTrue(torch.isfinite(loss))
        self.assertGreaterEqual(float(loss), 0.0)


if __name__ == "__main__":
    unittest.main()
