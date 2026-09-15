import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

PACKAGE = Path(__file__).resolve().parents[2] / 'paper/input/results/llm/v10/open_fomc_pilot/reviewer_text_pilot.zip'


class ReviewerPackageTests(unittest.TestCase):
    def run_verifier(self, corrupt=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with zipfile.ZipFile(PACKAGE) as archive:
                for name in archive.namelist():
                    self.assertEqual(Path(name).name, name)
                archive.extractall(root)
            if corrupt:
                rows = json.loads((root / 'corpus.json').read_text(encoding='utf-8'))
                rows[0]['text'] += ' modified'
                (root / 'corpus.json').write_text(json.dumps(rows), encoding='utf-8')
            return subprocess.run([sys.executable, str(root / 'verify.py')], cwd=root,
                                  capture_output=True, text=True, timeout=10)

    def test_clean_zip_verifies_offline(self):
        result = self.run_verifier()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_text_is_rejected(self):
        result = self.run_verifier(corrupt=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Hash mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main()
