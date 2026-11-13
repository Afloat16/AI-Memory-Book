"""Exact replay is read-only, with metadata and revision from one snapshot."""

from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store


def session(identity="one", **changes):
    value = {
        "project": "lab", "session_id": identity, "task_id": "calibration",
        "title": "Calibration record", "created_at": "2025-04-01T12:00:00Z",
        "messages": [
            {"role": "user", "content": "Review the calibration threshold."},
            {"role": "assistant", "content": "The pressure threshold is 82 pascals. " * 35},
            {"role": "user", "content": "What is the follow-up interval?"},
            {"role": "assistant", "content": "Repeat the inspection after 12 hours."},
        ],
    }
    return {**value, **changes}


class ExactReplayTests(unittest.TestCase):
    def test_replay_preserves_every_result_field_and_source_without_writes(self):
        for mode in ("adaptive", "turn", "session"):
            with self.subTest(mode=mode), MemoryBook(
                    ":memory:", segmentation=mode, max_page_chars=250,
                    min_page_chars=0) as book:
                source = session(created_at="")
                original_source = deepcopy(source)
                first = book.ingest(source)
                before = "\n".join(book.db.iterdump())
                for _ in range(2):
                    self.assertEqual(book.ingest(source), {**first, "skipped": True})
                self.assertEqual("\n".join(book.db.iterdump()), before)
                self.assertEqual(source, original_source)

    def test_replay_succeeds_while_another_connection_holds_the_write_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.db"
            with MemoryBook(path) as reader, MemoryBook(path) as writer:
                source = session()
                first = reader.ingest(source)
                reader.db.execute("PRAGMA busy_timeout=1")
                writer.db.execute("BEGIN IMMEDIATE")
                try:
                    self.assertEqual(reader.ingest(source), {**first, "skipped": True})
                    with self.assertRaises(sqlite3.OperationalError):
                        reader.ingest(session(title="A changed title"))
                finally:
                    writer.db.execute("ROLLBACK")
                self.assertFalse(reader.db.in_transaction)

    def test_changed_content_and_pagination_are_not_mistaken_for_replay(self):
        with MemoryBook(":memory:", max_page_chars=300, min_page_chars=0) as book:
            first = book.ingest(session())
            changed = session(messages=[{"role": "assistant", "content": "Threshold is now 93."}])
            second = book.ingest(changed)
            self.assertFalse(second["skipped"])
            self.assertEqual(second["revision"], first["revision"] + 1)
            self.assertIn("93", book.recall("threshold")["context"])
            book.max_page_chars = 450
            third = book.ingest(changed)
            self.assertFalse(third["skipped"])
            self.assertEqual(third["revision"], second["revision"] + 1)
            self.assertEqual(book.ingest(changed), {**third, "skipped": True})

    def test_omitted_names_follow_current_metadata_and_explicit_names_remain_explicit(self):
        with MemoryBook(":memory:") as book:
            source = session()
            book.ingest(source)
            book.ingest(session("two", project_name="Renamed lab", task_title="Renamed task"))
            updated = book.ingest(source)
            self.assertFalse(updated["skipped"])
            stored = next(row for row in book.export() if row["session_id"] == "one")
            self.assertEqual(stored["project_name"], "Renamed lab")
            self.assertEqual(stored["task_title"], "Renamed task")
            self.assertEqual(book.ingest(source), {**updated, "skipped": True})
            explicit = session(project_name="Explicit lab", task_title="Explicit task")
            changed = book.ingest(explicit)
            self.assertFalse(changed["skipped"])
            self.assertEqual(book.ingest(explicit), {**changed, "skipped": True})

    def test_fallback_rechecks_inherited_metadata_after_another_writer_changes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.db"
            with MemoryBook(path) as reader, MemoryBook(path) as writer:
                reader.ingest(session())
                original = reader._unchanged_ingest

                def concurrent_change(*args):
                    result = original(*args)
                    self.assertIsNone(result)
                    writer.ingest(session("two", project_name="Concurrent lab", task_title="Concurrent task"))
                    return result

                with patch.object(reader, "_unchanged_ingest", side_effect=concurrent_change):
                    result = reader.ingest(session(title="Changed source"))
                self.assertFalse(result["skipped"])
                stored = next(row for row in reader.export() if row["session_id"] == "one")
                self.assertEqual(stored["project_name"], "Concurrent lab")
                self.assertEqual(stored["task_title"], "Concurrent task")
                self.assertEqual(result["revision"], 3)

    def test_replay_revision_and_counts_stay_with_the_selected_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.db"
            with MemoryBook(path) as reader, MemoryBook(path) as writer:
                first = reader.ingest(session())
                original = store._json
                written = False

                def advance_after_select(value):
                    nonlocal written
                    if not written and isinstance(value, list) and isinstance(value[0], dict):
                        written = True
                        writer.ingest(session(messages=[{"role": "assistant", "content": "A new stored value."}]))
                    return original(value)

                with patch.object(store, "_json", side_effect=advance_after_select):
                    replay = reader.ingest(session())
                self.assertTrue(written)
                self.assertEqual(replay, {**first, "skipped": True})
                self.assertEqual(reader.revision, 2)
                self.assertIn("new stored value", reader.export()[0]["messages"][0]["content"])

    def test_invalid_requests_and_nested_transactions_keep_their_errors(self):
        with MemoryBook(":memory:") as book:
            book.ingest(session())
            with self.assertRaises(ValueError):
                book.ingest(session(messages=[{"role": "unsupported", "content": "Invalid."}]))
            book.db.execute("BEGIN")
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    book.ingest(session())
            finally:
                book.db.execute("ROLLBACK")


if __name__ == "__main__":
    unittest.main()
