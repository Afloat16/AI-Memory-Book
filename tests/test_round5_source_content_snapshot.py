"""Real invented SQLite fixtures; never open a corpus, selector or model."""
from __future__ import annotations

import json
import sqlite3
import time
import unittest

from memory_book import MemoryBook
from memory_book import store
from benchmarks.semantic_eval import source_snapshot
from scripts.round5_source_content_snapshot import (
    EXCLUDED_STORAGE_COLUMNS, SCHEMA, source_content_snapshot)


PAYLOADS = (
    {"project": "invented-lab", "project_name": "Invented Lab", "session_id": "memo-a",
     "title": "Calibration", "task_id": "archive", "task_title": "Research archive",
     "created_at": "2001-02-03T04:05:06Z",
     "messages": [{"role": "user", "content": "The quartz instrument was installed in 1997."},
                  {"role": "assistant", "content": "Its label is Cedar and the source date is 1997."}]},
    {"project": "invented-lab", "session_id": "memo-b", "title": "Observation",
     "task_id": "archive", "created_at": "2002-03-04T05:06:07Z",
     "messages": [{"role": "user", "content": "The northern inlet uses the quartz instrument."}]},
)


class SourceContentSnapshotTests(unittest.TestCase):
    def book(self):
        book = MemoryBook(":memory:", segmentation="turn", min_page_chars=0, cache_size=0)
        self.addCleanup(book.close)
        for payload in PAYLOADS:
            book.ingest(payload)
        return book

    def copy(self, source):
        db = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(db.close)
        source.backup(db)
        # Mutations below are invented negative cases, not measured databases.
        # Disable FK enforcement so every retained cell, including a referenced
        # ID, is independently checked by the digest instead of a SQL rejection.
        db.execute("PRAGMA foreign_keys=OFF")
        return db

    def test_separate_real_ingests_expose_v1_failure_and_preserve_content_identity(self):
        first = self.book()
        time.sleep(0.003)
        second = self.book()
        full_a, full_b = source_snapshot(first.db), source_snapshot(second.db)
        stable_a = source_content_snapshot(first.db)
        stable_b = source_content_snapshot(second.db)
        self.assertNotEqual(full_a, full_b)
        self.assertEqual(stable_a, stable_b)
        self.assertTrue(all(count > 0 for count in stable_a["row_counts"].values()))
        # A same-database copy continues to satisfy the original full identity.
        copied = self.copy(first.db)
        self.assertEqual(source_snapshot(copied), full_a)
        self.assertEqual(source_content_snapshot(copied), stable_a)
        print("Fresh v2 invented real-ingest proof:", json.dumps({
            "independent_full_snapshots_equal": full_a == full_b,
            "independent_content_snapshots_equal": stable_a == stable_b,
            "copied_database_full_snapshot_equal": source_snapshot(copied) == full_a,
            "retained_columns": sum(map(len, stable_a["retained_columns"].values())),
            "excluded_storage_columns": EXCLUDED_STORAGE_COLUMNS,
            "row_counts": stable_a["row_counts"],
            "retrieval_calls": 0, "fresh_rows_decoded": 0,
        }, sort_keys=True))

    def test_only_four_audited_storage_columns_are_excluded(self):
        self.assertEqual(EXCLUDED_STORAGE_COLUMNS, {
            "projects": ("created_at", "updated_at"),
            "chapters": ("updated_at",),
            "sessions": ("updated_at",)})
        book = self.book()
        before, full = source_content_snapshot(book.db), source_snapshot(book.db)
        changed = 0
        for table, columns in EXCLUDED_STORAGE_COLUMNS.items():
            for column in columns:
                with self.subTest(table=table, column=column):
                    db = self.copy(book.db)
                    db.execute(f'UPDATE "{table}" SET "{column}"="{column}" || ?',
                               ("-invented-storage-change",))
                    self.assertEqual(source_content_snapshot(db), before)
                    self.assertNotEqual(source_snapshot(db), full)
                    changed += 1
        self.assertEqual(changed, 4)

    def test_every_retained_cell_changes_the_cross_ingest_digest(self):
        book = self.book()
        before = source_content_snapshot(book.db)
        checked = []
        for table, columns in SCHEMA.items():
            for column, kind, *_ in columns:
                if column in EXCLUDED_STORAGE_COLUMNS.get(table, ()):
                    continue
                with self.subTest(table=table, column=column):
                    db = self.copy(book.db)
                    old = db.execute(f'SELECT "{column}" FROM "{table}" ORDER BY id LIMIT 1').fetchone()[0]
                    value = old + 100000 if kind == "INTEGER" else old + "-invented-change"
                    db.execute(f'UPDATE "{table}" SET "{column}"=? WHERE rowid='
                               f'(SELECT rowid FROM "{table}" ORDER BY id LIMIT 1)', (value,))
                    after = source_content_snapshot(db)
                    self.assertNotEqual(after["sha256"], before["sha256"])
                    self.assertNotEqual(after["table_sha256"][table], before["table_sha256"][table])
                    checked.append((table, column))
        self.assertEqual(len(checked), 43)
        self.assertIn(("sessions", "created_at"), checked)
        self.assertIn(("sessions", "raw_json"), checked)
        self.assertIn(("pages", "source_refs"), checked)
        self.assertIn(("pages", "rid"), checked)

    def test_row_counts_and_original_dates_remain_part_of_identity(self):
        book = self.book()
        before = source_content_snapshot(book.db)
        for table in SCHEMA:
            with self.subTest(table=table):
                db = self.copy(book.db)
                db.execute(f'DELETE FROM "{table}" WHERE rowid='
                           f'(SELECT rowid FROM "{table}" ORDER BY id LIMIT 1)')
                after = source_content_snapshot(db)
                self.assertNotEqual(after["sha256"], before["sha256"])
                self.assertEqual(after["row_counts"][table], before["row_counts"][table] - 1)
        raw = [json.loads(row[0]) for row in book.db.execute("SELECT raw_json FROM sessions")]
        self.assertEqual({item["created_at"] for item in raw},
                         {item["created_at"] for item in PAYLOADS})
        self.assertTrue(any("1997" in json.dumps(item) for item in raw))

    def test_schema_addition_removal_type_default_and_version_are_rejected(self):
        book = self.book()
        db = self.copy(book.db)
        db.execute("ALTER TABLE projects ADD COLUMN unexpected TEXT")
        with self.assertRaisesRegex(ValueError, "source schema changed: projects"):
            source_content_snapshot(db)
        # Build complete empty schemas with one precise schema mutation.
        for before, after in (
            ("name TEXT NOT NULL", "name BLOB NOT NULL"),
            ("name TEXT NOT NULL, ", ""),
            ("summary TEXT NOT NULL DEFAULT ''", "summary TEXT NOT NULL DEFAULT 'changed'"),
        ):
            with self.subTest(change=(before, after)):
                self.assertIn(before, store.SCHEMA)
                malformed = sqlite3.connect(":memory:", isolation_level=None)
                self.addCleanup(malformed.close)
                malformed.executescript(store.SCHEMA.replace(before, after, 1))
                with self.assertRaisesRegex(ValueError, "source schema changed:"):
                    source_content_snapshot(malformed)
        for pragma in ("user_version=4", "application_id=0"):
            with self.subTest(pragma=pragma):
                db = self.copy(book.db)
                db.execute("PRAGMA " + pragma)
                with self.assertRaisesRegex(ValueError, "registered MemoryBook schema"):
                    source_content_snapshot(db)

    def test_snapshot_is_read_only_and_full_worker_mutation_detection_remains(self):
        book = self.book()
        full = source_snapshot(book.db)
        revision = book.revision
        changes = book.db.total_changes
        first = source_content_snapshot(book.db)
        self.assertEqual(source_content_snapshot(book.db), first)
        self.assertEqual(book.db.total_changes, changes)
        self.assertEqual(book.revision, revision)
        self.assertEqual(source_snapshot(book.db), full)
        book.db.execute("UPDATE projects SET updated_at=updated_at || '-changed'")
        self.assertEqual(source_content_snapshot(book.db), first)
        self.assertNotEqual(source_snapshot(book.db), full)


if __name__ == "__main__":
    unittest.main()
