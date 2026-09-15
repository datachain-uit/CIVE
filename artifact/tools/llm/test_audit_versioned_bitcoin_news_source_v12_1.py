import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name("audit_versioned_bitcoin_news_source_v12_1.py")
SPEC = importlib.util.spec_from_file_location("source_audit", MODULE)
source_audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(source_audit)


class LfsPointerTests(unittest.TestCase):
    def test_parses_valid_pointer(self) -> None:
        pointer = (
            b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:0123456789abcdef\n"
            b"size 42\n"
        )
        self.assertEqual(
            source_audit.lfs_pointer(pointer),
            {"sha256": "0123456789abcdef", "bytes": 42},
        )

    def test_returns_none_for_non_pointer(self) -> None:
        self.assertIsNone(source_audit.lfs_pointer(b"not an lfs pointer\n"))

    def test_rejects_malformed_pointer(self) -> None:
        with self.assertRaises(ValueError):
            source_audit.lfs_pointer(
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha1:abc\n"
                b"size unknown\n"
            )


if __name__ == "__main__":
    unittest.main()
