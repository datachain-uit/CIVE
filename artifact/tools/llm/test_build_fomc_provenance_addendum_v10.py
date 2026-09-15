import unittest
from build_fomc_provenance_addendum_v10 import approximate_correlation_mde


class PowerTests(unittest.TestCase):
    def test_mde_decreases_with_sample_size(self):
        self.assertGreater(approximate_correlation_mde(24), approximate_correlation_mde(100))

    def test_invalid_sample(self):
        with self.assertRaises(ValueError):
            approximate_correlation_mde(3)

    def test_fixed_value(self):
        self.assertAlmostEqual(approximate_correlation_mde(24), 0.5450809287304434, places=12)


if __name__ == '__main__':
    unittest.main()
