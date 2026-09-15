import unittest
from datetime import datetime, timezone
from audit_social_intake_v9 import record_reasons


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.cutoff = datetime(2023, 5, 1, 4, tzinfo=timezone.utc)
        self.record = dict(created_at='2023-05-01T03:00:00Z',
                           observed_at='2023-05-01T03:00:20Z', text='Bitcoin event',
                           text_version_verified=True, selection_asof_verified=True,
                           usage_reviewed=True)

    def test_valid(self):
        self.assertEqual(record_reasons(self.record, self.cutoff), [])

    def test_naive_time_rejected(self):
        self.record['created_at'] = '2023-05-01T03:00:00'
        self.assertIn('created_at_missing_or_ambiguous', record_reasons(self.record, self.cutoff))

    def test_late_observation(self):
        self.record['observed_at'] = '2023-05-01T05:00:00Z'
        self.assertIn('not_available_at_cutoff', record_reasons(self.record, self.cutoff))

    def test_missing_provenance(self):
        for field in ('text_version_verified', 'selection_asof_verified', 'usage_reviewed'):
            record = self.record.copy()
            del record[field]
            self.assertTrue(record_reasons(record, self.cutoff))

    def test_removed_content(self):
        self.record['text'] = '[removed]'
        self.assertIn('text_unavailable', record_reasons(self.record, self.cutoff))

    def test_invalid_chronology(self):
        self.record['observed_at'] = '2023-04-30T00:00:00Z'
        self.assertIn('observation_before_creation', record_reasons(self.record, self.cutoff))


if __name__ == '__main__':
    unittest.main()
