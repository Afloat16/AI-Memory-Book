"""Integrity checks for the supplemental startup diagnosis."""
import sqlite3
import unittest

from scripts.round3_startup_review import SQLRecorder, unchanged_startup


class StartupReviewTests(unittest.TestCase):
    def test_constructor_change_cannot_be_ignored_as_recall_change(self):
        source = "SCHEMA = 'original'\nclass MemoryBook:\n def __init__(self):\n  self.a = 1\n def recall(self):\n  return 1\n"
        recall_only = source.replace("return 1", "return 2") + " def _project_rowid_bounds(self):\n  return None\n"
        self.assertTrue(unchanged_startup(source, recall_only)["passed"])
        for changed in (recall_only.replace("self.a = 1", "self.a = 2"),
                        recall_only.replace("'original'", "'changed'")):
            with self.assertRaisesRegex(ValueError, "Startup/store code"):
                unchanged_startup(source, changed)

    def test_trace_covers_schema_script_and_keeps_instrumentation_explicit(self):
        recorder = SQLRecorder()
        connection = recorder.connect(":memory:")
        try:
            connection.executescript("CREATE TABLE items(id INTEGER); INSERT INTO items VALUES(1);")
            self.assertEqual(connection.execute("SELECT id FROM items").fetchone()[0], 1)
            self.assertEqual([event["method"] for event in recorder.events],
                             ["connect", "executescript", "execute"])
            self.assertEqual([entry["sql"].strip() for entry in recorder.trace],
                             ["CREATE TABLE items(id INTEGER);", "INSERT INTO items VALUES(1);",
                              "SELECT id FROM items"])
            for event in recorder.events:
                self.assertGreaterEqual(event["wall_ms"], 0)
                self.assertGreaterEqual(event["cpu_ms"], 0)
                self.assertAlmostEqual(event["wall_minus_cpu_ms"], event["wall_ms"] - event["cpu_ms"])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
