"""CLI coverage opt-in and incompatible-mode behavior."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from memory_book import MemoryBook
from memory_book.cli import main, parser
from tests.test_conjunctive_recall import seed_conjunctive_book


class CoverageCLITests(unittest.TestCase):
    def test_coverage_flag_is_opt_in_and_reaches_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "memory.db")
            with MemoryBook(database, segmentation="turn", max_page_chars=3000,
                            min_page_chars=0) as book:
                primary, secondary, _ = seed_conjunctive_book(book)
            arguments = ["--db", database, "recall",
                         "rotor calibration offset and receiver tolerance",
                         "--project", "lab", "--limit", "2", "--budget", "600", "--json"]
            outputs = []
            for extra in ([], ["--coverage"]):
                stream = io.StringIO()
                with redirect_stdout(stream):
                    self.assertEqual(main(arguments + extra), 0)
                outputs.append(json.loads(stream.getvalue()))
            self.assertIn(primary, outputs[0]["context"])
            self.assertNotIn(secondary, outputs[0]["context"])
            self.assertIn(primary, outputs[1]["context"])
            self.assertIn(secondary, outputs[1]["context"])
            self.assertEqual(set(outputs[0]), set(outputs[1]))

    def test_flat_and_coverage_cannot_be_requested_together(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            parser().parse_args(["recall", "instrument notes", "--flat", "--coverage"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
