import unittest
from unittest.mock import patch
from audit_arctic_pilot_v9 import main
from audit_arctic_pilot_v9 import inspect, audit, epoch


class ArcticTests(unittest.TestCase):
    def test_collection_stops_before_network(self):
        with patch('audit_arctic_pilot_v9.fetch') as network:
            with self.assertRaises(SystemExit):
                main()
            network.assert_not_called()

    def setUp(self):
        self.row = {'id': 'abc', 'subreddit': 'Bitcoin', 'created_utc': 1704067279,
                    'retrieved_on': 1704067294, 'edited': False,
                    '_meta': {'note': 'no_2nd_retrieval'}, 'title': 'Bitcoin news', 'selftext': ''}

    def test_clean_is_only_conditional(self):
        self.assertEqual(inspect(self.row, 'posts')['reasons'], [])
        self.assertEqual(inspect(self.row, 'posts')['observation_delay_seconds'], 15)

    def test_restored_excluded(self):
        self.row['_meta']['was_initially_deleted'] = True
        self.assertIn('restored_content_not_initial_version', inspect(self.row, 'posts')['reasons'])

    def test_edit_excluded(self):
        self.row['_meta']['is_edited'] = True
        self.assertIn('second_retrieval_edited', inspect(self.row, 'posts')['reasons'])

    def test_missing_metadata(self):
        del self.row['_meta']
        self.assertIn('version_metadata_missing', inspect(self.row, 'posts')['reasons'])

    def test_unknown_note(self):
        self.row['_meta']['note'] = 'new_semantics'
        self.assertIn('unknown_version_note', inspect(self.row, 'posts')['reasons'])

    def test_late_is_not_backdated(self):
        self.row['retrieved_on'] += 20000
        self.assertFalse(inspect(self.row, 'posts')['next_4h_creation_boundary_observed'])

    def test_invalid_epochs(self):
        for value in (True, float('nan'), float('inf'), '2024-01-01', None):
            self.assertIsNone(epoch(value))

    def test_duplicate_and_no_completeness_claim(self):
        result = audit([self.row, self.row], 'posts', '2024-01-01', '2024-01-02')
        self.assertEqual(result['reason_counts']['duplicate_id'], 1)
        self.assertEqual(result['conditional_temporal_candidates'], 1)
        self.assertFalse(result['coverage_complete'])

    def test_negative_delay(self):
        self.row['retrieved_on'] = self.row['created_utc'] - 1
        self.assertIn('observation_before_creation', inspect(self.row, 'posts')['reasons'])

    def test_removed_comment(self):
        self.row['body'] = '[removed]'
        self.assertIn('deleted_or_removed_text', inspect(self.row, 'comments')['reasons'])


if __name__ == '__main__':
    unittest.main()
