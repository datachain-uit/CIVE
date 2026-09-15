import unittest
from score_open_fed_policy_v11_1_3 import edit_distance_one

class IdTest(unittest.TestCase):
    def test_one_edit_only(self):
        self.assertTrue(edit_distance_one("abcde", "abcdf")); self.assertFalse(edit_distance_one("abcde", "abxyz"))

if __name__ == "__main__": unittest.main()
