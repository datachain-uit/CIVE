import unittest
from build_open_fed_policy_events_v11 import group_documents


class EventTests(unittest.TestCase):
    def test_same_time_is_one_event_deterministically(self):
        rows = [
            {'id': 'b', 'published_at_claimed_utc': '2024-01-01T19:00:00+00:00',
             'text': 'Second', 'category': 'Monetary Policy',
             'historical_first_version_verified': False},
            {'id': 'a', 'published_at_claimed_utc': '2024-01-01T19:00:00+00:00',
             'text': 'First', 'category': 'Monetary Policy',
             'historical_first_version_verified': False}]
        event = group_documents(rows)[0]
        self.assertEqual(event['document_ids'], ['a', 'b'])
        self.assertEqual(event['document_count'], 2)
        self.assertLess(event['text'].index('First'), event['text'].index('Second'))

    def test_different_times_remain_separate(self):
        base = {'category': 'Monetary Policy', 'historical_first_version_verified': False}
        rows = [dict(base, id='a', text='A', published_at_claimed_utc='2024-01-01T19:00:00+00:00'),
                dict(base, id='b', text='B', published_at_claimed_utc='2024-01-01T20:00:00+00:00')]
        self.assertEqual(len(group_documents(rows)), 2)


if __name__ == '__main__':
    unittest.main()
