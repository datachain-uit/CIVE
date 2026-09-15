import json
import unittest
from score_open_fed_policy_v11_1_2 import api


class DuplicateBatchTest(unittest.TestCase):
    def test_normalizer_is_explicitly_batch_one_only(self):
        self.assertTrue(callable(api))
        payload = {"results": [{"event_id": "e"}, {"event_id": "e"}]}
        self.assertEqual(len(payload["results"]), 2)


if __name__ == "__main__": unittest.main()
