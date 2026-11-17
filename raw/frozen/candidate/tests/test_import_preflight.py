"""Invalid CLI batches must not partially replace an archive."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.cli import main


def session(sid="existing", text="Original engineering decision", **fields):
    return {
        "project": "engineering", "session_id": sid, "task_id": "design",
        "messages": [{"role": "user", "content": "What was decided?"},
                     {"role": "assistant", "content": text}],
        **fields,
    }


class ImportPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "book.db"

    def write(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        return path

    def run_import(self, *paths):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = main(["--db", str(self.database), "import", *map(str, paths)])
        return result, stdout.getvalue(), stderr.getvalue()

    def seed(self):
        with MemoryBook(self.database) as book:
            book.ingest(session(project_name="Engineering archive", task_title="Design decisions",
                                created_at="2026-01-02T03:04:05Z"))
            return book.export(), book.revision

    def assert_archive_unchanged(self, before):
        with MemoryBook(self.database) as book:
            self.assertEqual((book.export(), book.revision), before)
            evidence = book.recall("engineering decision", project="engineering")
            self.assertIn("Original engineering decision", evidence["context"])
            self.assertNotIn("Replacement decision", evidence["context"])

    def test_later_file_storage_validation_preserves_existing_session(self):
        before = self.seed()
        replacement = self.write("first.json", session(text="Replacement decision"))
        invalid = self.write("later.json", session("later", created_at="not-a-date"))
        code, stdout, stderr = self.run_import(replacement, invalid)
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn(f"{invalid}: session 1:", stderr)
        self.assertIn("ISO 8601", stderr)
        self.assert_archive_unchanged(before)

    def test_all_sessions_in_one_file_receive_storage_validation(self):
        before = self.seed()
        invalid_records = {
            "nul-content": session("bad", "bad\x00content"),
            "long-id": session("s" * 257),
            "long-project-name": session("bad", project_name="n" * 501),
            "long-task-title": session("bad", task_title="t" * 501),
            "system-only": session("bad", messages=[{"role": "system", "content": "instructions"}]),
            "surrogate-content": session("bad", "invalid\ud800text"),
            "surrogate-id": session("bad\udfff"),
            "surrogate-project-name": session("bad", project_name="bad\ud800name"),
            "surrogate-task-title": session("bad", task_title="bad\udfffname"),
        }
        for name, invalid in invalid_records.items():
            with self.subTest(case=name):
                source = self.write(name + ".json", [session(text="Replacement decision"), invalid])
                code, _, stderr = self.run_import(source)
                self.assertEqual(code, 2)
                self.assertIn("session 2:", stderr)
                self.assert_archive_unchanged(before)

    def test_invalid_batch_does_not_create_database_or_parent(self):
        self.database = self.root / "new-archive" / "book.db"
        source = self.write("invalid.json", [session("valid"), session("bad", created_at="wrong")])
        self.assertEqual(self.run_import(source)[0], 2)
        self.assertFalse(self.database.parent.exists())

    def test_invalid_batch_does_not_migrate_existing_archive(self):
        # Connection.__exit__ commits/rolls back but does not close the handle.
        # Close both fixture connections before Windows removes the temp dir.
        with contextlib.closing(sqlite3.connect(self.database)) as db, db:
            db.execute("PRAGMA user_version = 3")
            db.execute("CREATE TABLE sentinel (value TEXT)")
            db.execute("INSERT INTO sentinel VALUES ('untouched')")
        source = self.write("invalid.json", session(created_at="wrong"))
        self.assertEqual(self.run_import(source)[0], 2)
        with contextlib.closing(sqlite3.connect(self.database)) as db, db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertEqual(db.execute("SELECT value FROM sentinel").fetchone()[0], "untouched")
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("sentinel",)])

    def test_surrogate_input_does_not_create_database(self):
        source = self.write("invalid-unicode.json", [session("valid"), session("invalid", "bad\ud800text")])
        code, _, stderr = self.run_import(source)
        self.assertEqual(code, 2)
        self.assertIn("session 2:", stderr)
        self.assertIn("valid UTF-8", stderr)
        self.assertFalse(self.database.exists())

    def test_direct_ingestion_rejects_surrogates_without_changing_archive(self):
        self.seed()
        fields = ("project", "project_name", "session_id", "title", "task_id", "task_title")
        with MemoryBook(self.database) as book:
            before = book.export(), book.revision
            for field in fields:
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "valid UTF-8"):
                    book.ingest(session(**{field: "invalid\ud800value"}))
                self.assertEqual((book.export(), book.revision), before)
            with self.assertRaisesRegex(ValueError, "valid UTF-8"):
                book.ingest(session(text="invalid\udfffvalue"))
            self.assertEqual((book.export(), book.revision), before)

    def test_valid_unicode_survives_import(self):
        source = self.write("unicode.json", session(text="工程记录：数据集 🚀 与 café"))
        self.assertEqual(self.run_import(source)[0], 0)
        with MemoryBook(self.database) as book:
            self.assertEqual(book.export()[0]["messages"][1]["content"], "工程记录：数据集 🚀 与 café")

    def test_later_parse_error_prevents_earlier_valid_import(self):
        before = self.seed()
        valid = self.write("valid.json", session(text="Replacement decision"))
        invalid = self.root / "invalid.json"
        invalid.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.run_import(valid, invalid)[0], 2)
        self.assert_archive_unchanged(before)

    def test_capacity_failure_is_checked_before_first_write(self):
        before = self.seed()
        source = self.write("capacity.json", [session(text="Replacement decision"), session("large", "x" * 300)])
        with patch("memory_book.store.MAX_SESSION_CHARS", 100):
            code, _, stderr = self.run_import(source)
        self.assertEqual(code, 2)
        self.assertIn("session text exceeds 100", stderr)
        self.assert_archive_unchanged(before)

    def test_success_preserves_omitted_metadata_and_retry_is_idempotent(self):
        self.seed()
        source = self.write("valid.json", [session(text="Replacement decision"), session("second", "Additional evidence")])
        code, stdout, stderr = self.run_import(source)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(len(json.loads(stdout)), 2)
        with MemoryBook(self.database) as book:
            first, second = sorted(book.export(), key=lambda value: value["session_id"])
            self.assertEqual(first["created_at"], "2026-01-02T03:04:05+00:00")
            for record in (first, second):
                self.assertEqual(record["project_name"], "Engineering archive")
                self.assertEqual(record["task_title"], "Design decisions")
            revision = book.revision
        code, stdout, stderr = self.run_import(source)
        self.assertEqual((code, stderr), (0, ""))
        self.assertTrue(all(row["skipped"] for row in json.loads(stdout)))
        with MemoryBook(self.database) as book:
            self.assertEqual(book.revision, revision)


if __name__ == "__main__":
    unittest.main()
