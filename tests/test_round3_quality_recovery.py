"""Integrity tests for read-only recovery of an interrupted result upload."""
import gzip
import unittest
from scripts.recover_round3_project_stats import (
    assert_original_prefix, controller_prefix, join_group,
)


class QualityEvidenceRecoveryTests(unittest.TestCase):
    def test_truncated_aggregate_preserves_complete_metadata(self):
        raw = b'{"attempted_workers":[{"exit_code":0}],"validation":{"workers":8},"workers":[{"id":"old"}]}'
        compressed = gzip.compress(raw, mtime=0)
        metadata, prefix = controller_prefix(compressed[:-8])
        self.assertEqual(metadata, {"attempted_workers": [{"exit_code": 0}], "validation": {"workers": 8}})
        self.assertEqual(prefix, raw)
        assert_original_prefix(raw, prefix)

    def test_complete_gzip_is_not_mislabeled_as_truncated(self):
        with self.assertRaisesRegex(ValueError, "expected to be incomplete"):
            controller_prefix(gzip.compress(b'{"workers":[]}'))

    def test_missing_controller_metadata_is_not_invented(self):
        raw = b'{"attempted_workers":[{"exit_code":'
        with self.assertRaises(ValueError):
            controller_prefix(gzip.compress(raw)[:-8])

    def test_duplicate_metadata_key_is_rejected(self):
        raw = b'{"attempted_workers":[],"attempted_workers":[],"workers":[]}'
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            controller_prefix(gzip.compress(raw)[:-8])

    def test_chunk_gap_duplicate_and_truncation_are_rejected(self):
        full = b"a" * 196608
        self.assertEqual(join_group([(1, b"tail"), (0, full)]), full + b"tail")
        for parts in ([(0, full), (2, b"tail")], [(0, full), (0, b"tail")]):
            with self.assertRaisesRegex(ValueError, "Missing or duplicate"):
                join_group(parts)
        with self.assertRaisesRegex(ValueError, "transfer tail"):
            join_group([(0, full)])
        self.assertEqual(join_group([(0, full)], truncated=True), full)

    def test_reconstruction_must_match_every_available_original_byte(self):
        assert_original_prefix(b'{"workers":[{"a":1}]}', b'{"workers":[{"a"')
        with self.assertRaisesRegex(ValueError, "disagrees"):
            assert_original_prefix(b'{"workers":[{"a":2}]}', b'{"workers":[{"a":1')


if __name__ == "__main__":
    unittest.main()
