import unittest
from build_conditional_fed_policy_events_v11 import listed_date, update_date


class GateTests(unittest.TestCase):
    def test_dates_parse(self):
        row = {'listed_date': '1/24/2024', 'last_update_label': 'Last Update: January 24, 2024'}
        self.assertEqual(listed_date(row), update_date(row))

    def test_later_update_differs(self):
        row = {'listed_date': '1/24/2024', 'last_update_label': 'Last Update: January 30, 2024'}
        self.assertNotEqual(listed_date(row), update_date(row))

    def test_ambiguous_labels_rejected(self):
        self.assertIsNone(update_date({'last_update_label': 'Updated recently'}))
        self.assertIsNone(listed_date({'listed_date': '2024'}))


if __name__ == '__main__':
    unittest.main()
