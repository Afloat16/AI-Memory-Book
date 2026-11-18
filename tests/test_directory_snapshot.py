"""Directory navigation stays on one SQLite snapshot during background capture."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from memory_book import MemoryBook


def record(identity="initial", task="one", text="lease_duration=30.") -> dict:
    return {"project": "workers", "project_name": "Workers", "session_id": identity,
            "task_id": task, "title": "Worker configuration", "created_at": "2026-01-01T00:00:00Z",
            "messages": [{"role": "assistant", "content": text}]}


class DirectorySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "memory.db"
        self.reader = MemoryBook(path, segmentation="adaptive", max_page_chars=160, min_page_chars=0)
        self.writer = MemoryBook(path, segmentation="adaptive", max_page_chars=160, min_page_chars=0)
        self.addCleanup(self.writer.close)
        self.addCleanup(self.reader.close)
        saved = self.reader.ingest(record(text="First source paragraph. " * 30))
        self.chapter_id = saved["chapter_id"]
        self.section_id = self.reader.chapter(self.chapter_id)["sections"][0]["id"]

    def race(self, fragment, mutation):
        state = {"fired": False, "errors": []}

        def trace(statement):
            if not state["fired"] and fragment in statement:
                state["fired"] = True
                try:
                    mutation()
                except BaseException as exc:
                    state["errors"].append(repr(exc))

        self.reader.db.set_trace_callback(trace)
        self.addCleanup(self.reader.db.set_trace_callback, None)
        return state

    def test_book_counts_rows_and_revision_share_a_snapshot(self):
        revision = self.reader.revision
        race = self.race("SELECT c.*,", lambda: self.writer.ingest(record("second", "two")))
        result = self.reader.toc("workers")
        self.assertTrue(race["fired"])
        self.assertFalse(race["errors"])
        self.assertEqual(result["revision"], revision)
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["chapters"]), 1)
        self.assertEqual(result["chapters"][0]["id"], self.chapter_id)
        self.assertIsNone(result["next_offset"])
        self.assertFalse(self.reader.db.in_transaction)
        current = self.reader.toc("workers")
        self.assertEqual(current["total"], 2)
        self.assertEqual(len(current["chapters"]), 2)
        self.assertGreater(current["revision"], revision)

    def test_section_count_and_pages_share_a_snapshot_across_source_replacement(self):
        original = self.reader.section(self.section_id)
        self.assertGreater(original["total"], 1)
        race = self.race("SELECT id,title,length(content)",
                         lambda: self.writer.ingest(record(text="Replacement source.")))
        result = self.reader.section(self.section_id)
        self.assertTrue(race["fired"])
        self.assertFalse(race["errors"])
        self.assertEqual(result, original)
        self.assertFalse(self.reader.db.in_transaction)
        self.assertEqual(self.reader.db.execute("SELECT COUNT(*) FROM pages").fetchone()[0], 1)

    def test_scoped_section_remains_consistent_if_its_source_is_deleted(self):
        original = self.reader.section(self.section_id, project="workers", limit=2)
        race = self.race("SELECT id,title,length(content)",
                         lambda: self.writer.delete_session("workers", "initial"))
        result = self.reader.section(self.section_id, project="workers", limit=2)
        self.assertTrue(race["fired"])
        self.assertFalse(race["errors"])
        self.assertEqual(result, original)
        self.assertFalse(self.reader.db.in_transaction)
        with self.assertRaises(KeyError):
            self.reader.section(self.section_id, project="workers")

    def test_existing_caller_transaction_is_never_committed_or_rolled_back(self):
        self.reader.db.execute("BEGIN")
        self.reader.db.execute("UPDATE projects SET name='Uncommitted caller name' WHERE id='workers'")
        result = self.reader.toc("workers")
        self.assertEqual(result["project"]["name"], "Uncommitted caller name")
        self.assertTrue(self.reader.db.in_transaction)
        self.assertTrue(self.reader.section(self.section_id)["pages"])
        self.assertTrue(self.reader.db.in_transaction)
        with self.assertRaises(KeyError):
            self.reader.toc("missing")
        self.assertTrue(self.reader.db.in_transaction)
        with self.assertRaises(KeyError):
            self.reader.section(self.section_id, project="foreign")
        self.assertTrue(self.reader.db.in_transaction)
        self.reader.db.execute("ROLLBACK")
        self.assertEqual(self.reader.toc("workers")["project"]["name"], "Workers")

    def test_failures_close_only_snapshots_owned_by_navigation(self):
        for operation, arguments in ((self.reader.toc, ("missing",)),
                                     (self.reader.section, ("missing",))):
            with self.subTest(operation=operation.__name__), self.assertRaises(KeyError):
                operation(*arguments)
            self.assertFalse(self.reader.db.in_transaction)


if __name__ == "__main__":
    unittest.main()
