"""Integrity checks for the frozen independent diagnostic corpus."""

from pathlib import Path
import tempfile
import unittest

from benchmarks.run import original_turn_texts
from benchmarks.transfer_data import DATA, load_transfer


class TransferIntegrityTests(unittest.TestCase):
    def test_all_labels_address_complete_original_source_turns(self):
        dataset = load_transfer()
        original = original_turn_texts(dataset)
        self.assertEqual(len({case.id for case in dataset.queries}), len(dataset.queries))
        for case in dataset.queries:
            self.assertEqual(bool(case.required), case.answerable)
            for evidence in case.required + case.stale:
                self.assertIn(evidence.needle,
                              original[(case.project, evidence.session_id, evidence.turn_index)])
        # Source-only import never receives these evaluator fields.
        for session in dataset.sessions:
            self.assertNotIn("required", session)
            self.assertNotIn("queries", session)
        self.assertEqual(dataset.description()["version"], "authored-transfer-1")

    def test_modified_frozen_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "cases.json"
            changed.write_bytes(DATA.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "frozen manifest"):
                load_transfer(changed)


if __name__ == "__main__":
    unittest.main()
