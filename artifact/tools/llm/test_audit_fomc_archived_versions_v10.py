import unittest
import gzip
from datetime import datetime, timezone
from audit_fomc_archived_versions_v10 import CDX, choose_capture, compact, decode_archive_payload
from urllib.parse import urlencode


class ArchiveTests(unittest.TestCase):
    def test_nearest_capture(self):
        release = datetime(2024, 1, 31, 19, tzinfo=timezone.utc)
        rows = [{'timestamp': '20240130180000'},
                {'timestamp': '20240131191816'},
                {'timestamp': '20240131215604'}]
        self.assertEqual(choose_capture(rows, release)['timestamp'], '20240131191816')

    def test_outside_window(self):
        release = datetime(2024, 1, 31, 19, tzinfo=timezone.utc)
        self.assertIsNone(choose_capture([{'timestamp': '20240202190001'}], release))

    def test_bad_rows_ignored(self):
        release = datetime(2024, 1, 31, 19, tzinfo=timezone.utc)
        self.assertIsNone(choose_capture([{}, {'timestamp': 'bad'}], release))

    def test_cdx_filters_are_repeated_parameters(self):
        query = urlencode({'url': 'x', 'filter': ['statuscode:200', 'mimetype:text/html'],
                           'from': compact(datetime(2024, 1, 1, tzinfo=timezone.utc))}, doseq=True)
        self.assertIn('filter=statuscode%3A200&filter=mimetype%3Atext%2Fhtml', CDX + query)

    def test_gzip_archive_payload(self):
        payload = b'<html>ok</html>'
        self.assertEqual(decode_archive_payload(gzip.compress(payload)), payload)
        self.assertEqual(decode_archive_payload(payload), payload)


if __name__ == '__main__':
    unittest.main()
