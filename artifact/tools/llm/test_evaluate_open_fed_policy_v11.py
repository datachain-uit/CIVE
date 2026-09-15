import unittest
from evaluate_open_fed_policy_v11 import indices


class FoldTest(unittest.TestCase):
    def test_expanding_fold_boundaries(self):
        rows = [{"decision_at": value} for value in ("2023-01-01T00:00:00+00:00", "2023-07-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00")]
        train, valid = indices(rows, {"train_end": "2023-06-30T23:59:59+00:00", "valid_start": "2023-07-01T00:00:00+00:00", "valid_end": "2023-12-31T23:59:59+00:00"})
        self.assertEqual(train, [0]); self.assertEqual(valid, [1])


if __name__ == "__main__": unittest.main()
