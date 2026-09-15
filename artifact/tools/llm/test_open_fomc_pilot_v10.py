import unittest
from build_open_fomc_pilot_v10 import timestamp, extract


class Tests(unittest.TestCase):
    def test_winter(self):
        self.assertEqual(timestamp('January 31, 2024', 'For release at 2:00 p.m. EST'), '2024-01-31T19:00:00+00:00')

    def test_summer(self):
        self.assertEqual(timestamp('July 31, 2024', 'For release at 2:00 p.m. EDT'), '2024-07-31T18:00:00+00:00')

    def test_unknown_zone(self):
        with self.assertRaises(ValueError):
            timestamp('July 31, 2024', 'For release at 2:00 p.m. ET')

    def test_extract_allowlist(self):
        html = b'''<p>Navigation</p><p class="article__time">January 31, 2024</p>
        <h3 class="title">Federal Reserve issues FOMC statement</h3>
        <p class="releaseTime">For release at 2:00 p.m. EST<ul><li>Share</li></ul>
        <div class="col-xs-12 col-sm-8 col-md-8"><p>First <b>paragraph</b>.</p>
        <p>Second paragraph.</p><p>Voting for the action.</p><p>For media inquiries contact us</p></div>
        <div id="lastUpdate">Last Update: January 31, 2024</div>'''
        row = extract(html)
        self.assertEqual(row['text'], 'First paragraph.\n\nSecond paragraph.\n\nVoting for the action.')
        self.assertFalse(row['historical_first_version_verified'])


if __name__ == '__main__':
    unittest.main()
