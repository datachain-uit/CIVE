import unittest
from build_open_fed_policy_corpus_v11 import parse_archive, parse_release


class CorpusTests(unittest.TestCase):
    def test_archive_structure(self):
        page = b'''<div class="row"><div><time>1/24/2024</time></div><div>
        <p><a href="/newsevents/pressreleases/monetary20240124a.htm"><em>Policy title</em></a></p>
        <p class="eventlist__press"><em><strong>Monetary Policy</strong></em></p></div></div>'''
        self.assertEqual(parse_archive(page), [{'listed_date': '1/24/2024',
                         'path': '/newsevents/pressreleases/monetary20240124a.htm',
                         'listed_title': 'Policy title', 'category': 'Monetary Policy'}])

    def test_release_requires_explicit_clock(self):
        body = 'A policy paragraph with sufficient content. ' * 8
        page = f'''<p class="article__time">January 24, 2024</p><h3 class="title">Policy title</h3>
        <div class="col-xs-12 col-sm-8 col-md-8"><p>{body}</p></div>'''.encode()
        row = parse_release(page, {'listed_title': 'Policy title'})
        self.assertIn('release_timestamp_missing_or_ambiguous', row['admission_reasons'])

    def test_release_admits_valid_text(self):
        body = 'A policy paragraph with sufficient content. ' * 8
        page = f'''<p class="article__time">January 24, 2024</p><h3 class="title">Policy title</h3>
        <p class="releaseTime">For release at 7:00 p.m. EST</p>
        <div class="col-xs-12 col-sm-8 col-md-8"><p>{body}</p></div>'''.encode()
        row = parse_release(page, {'listed_title': 'Policy title'})
        self.assertEqual(row['admission_reasons'], [])
        self.assertEqual(row['published_at_claimed_utc'], '2024-01-25T00:00:00+00:00')

    def test_rights_marker_excluded(self):
        body = ('Copyright third party. ' + 'Long text. ' * 30)
        page = f'''<p class="article__time">January 24, 2024</p><h3 class="title">Policy title</h3>
        <p class="releaseTime">For release at 7:00 p.m. EST</p>
        <div class="col-xs-12 col-sm-8 col-md-8"><p>{body}</p></div>'''.encode()
        row = parse_release(page, {'listed_title': 'Policy title'})
        self.assertIn('article_body_contains_rights_marker', row['admission_reasons'])


if __name__ == '__main__':
    unittest.main()
