"""Atomic index upgrades must preserve source data and withstand competing opens."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.store import SCHEMA_VERSION, STEM_REVISION_SQL


class IndexMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "legacy.db"

    def tearDown(self):
        self.temporary.cleanup()

    def _legacy(self, version=2):
        source = {
            "project": "travel", "session_id": "visit", "task_id": "journey",
            "created_at": "2025-07-03T12:00:00Z",
            "messages": [{"role": "user", "content": "Travel report"},
                         {"role": "assistant", "content": "Mira attended a conference in Tallinn. " +
                          "The archived itinerary also records transit and accommodation details. " * 25}],
        }
        with MemoryBook(self.path, segmentation="adaptive", max_page_chars=700, min_page_chars=150) as book:
            book.ingest(source)
            book.recall("conference", project="travel")
        # These derived tables/triggers are the only schema-3 additions. Dropping
        # them produces the prior source schema, including custom page boundaries.
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER meta_revision_sync_stem")
            db.execute("DELETE FROM meta WHERE key='stem_revision'")
            db.execute("DROP TRIGGER pages_delete_stem_fts")
            db.execute("DROP TABLE pages_stem_fts")
            if version == 1:
                db.execute("ALTER TABLE sessions DROP COLUMN settings_json")
                row = db.execute("SELECT raw_json FROM sessions").fetchone()
                raw = json.loads(row[0])
                raw["created_at"] = ""
                db.execute("UPDATE sessions SET raw_json=?", (json.dumps(raw),))
            db.execute(f"PRAGMA user_version={version}")
        return self._snapshot()

    def _snapshot(self):
        with sqlite3.connect(self.path) as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {
                "version": db.execute("PRAGMA user_version").fetchone()[0],
                "revision": int(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]),
                "meta": db.execute("SELECT key,value FROM meta ORDER BY key").fetchall(),
                "pages": db.execute("SELECT rid,id,content,source_refs FROM pages ORDER BY rid").fetchall(),
                "sources": db.execute("SELECT id,raw_json,created_at,content_hash FROM sessions ORDER BY id").fetchall(),
                "exact": db.execute("SELECT rowid,title,question,body,directory FROM pages_fts ORDER BY rowid").fetchall(),
                "stem": (db.execute("SELECT rowid,title,question,body,directory FROM pages_stem_fts ORDER BY rowid").fetchall()
                         if "pages_stem_fts" in tables else None),
                "cache": db.execute("SELECT key,revision,payload,touched_ns FROM recall_cache ORDER BY key").fetchall(),
                "columns": [row[1] for row in db.execute("PRAGMA table_info(sessions)")],
                "tables": tables,
            }

    def _assert_indexes_match(self, book):
        exact = [tuple(row) for row in book.db.execute(
            "SELECT rowid,title,question,body,directory FROM pages_fts ORDER BY rowid")]
        stem = [tuple(row) for row in book.db.execute(
            "SELECT rowid,title,question,body,directory FROM pages_stem_fts ORDER BY rowid")]
        self.assertEqual(stem, exact)
        marker = book.db.execute("SELECT value FROM meta WHERE key='stem_revision'").fetchone()[0]
        self.assertEqual(int(marker), book.revision)

    @staticmethod
    def _legacy_change(db, statements):
        """Schema-2 writers know only exact-index edits and revision invalidation."""
        db.execute("BEGIN IMMEDIATE")
        try:
            for statement, parameters in statements:
                db.execute(statement, parameters)
            db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
            db.execute("DELETE FROM recall_cache")
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    def test_schema_two_upgrade_preserves_sources_pages_and_existing_index(self):
        old = self._legacy()
        self.assertTrue(old["cache"])
        self.assertGreater(len(old["pages"]), 1)
        with MemoryBook(self.path) as book:
            self.assertEqual(book.stats()["schema_version"], SCHEMA_VERSION)
            self.assertEqual(book.revision, old["revision"] + 1)
            self.assertEqual(book.db.execute("SELECT count(*) FROM recall_cache").fetchone()[0], 0)
            stem = [tuple(row) for row in book.db.execute(
                "SELECT rowid,title,question,body,directory FROM pages_stem_fts ORDER BY rowid")]
            self.assertEqual(stem, old["exact"])
            self.assertIn("Tallinn", book.recall("conferences", project="travel", use_cache=False)["context"])
        new = self._snapshot()
        for key in ("pages", "sources", "exact", "columns"):
            self.assertEqual(new[key], old[key], key)
        with MemoryBook(self.path) as reopened:
            self.assertEqual(reopened.revision, new["revision"])

    def test_development_schema_upgrade_is_sequential_and_preserves_page_addresses(self):
        old = self._legacy(version=1)
        with MemoryBook(self.path) as book:
            self.assertEqual(book.stats()["schema_version"], SCHEMA_VERSION)
            self.assertEqual(book.revision, old["revision"] + 1)
            self.assertEqual(book.export()[0]["created_at"], old["sources"][0][2])
            self.assertIn("Tallinn", book.recall("conferences", project="travel", use_cache=False)["context"])
            settings = json.loads(book.db.execute("SELECT settings_json FROM sessions").fetchone()[0])
            self.assertEqual(settings["max_page_chars"], 1800)
        self.assertEqual(self._snapshot()["pages"], old["pages"])

    def test_failed_backfill_rolls_back_schema_data_cache_and_version(self):
        for version in (1, 2):
            with self.subTest(version=version):
                if self.path.exists():
                    self.path.unlink()
                old = self._legacy(version)
                migrate = MemoryBook._migrate_v2

                def interrupted(book):
                    migrate(book)
                    raise sqlite3.OperationalError("interrupted after stem backfill")

                with patch.object(MemoryBook, "_migrate_v2", interrupted):
                    with self.assertRaisesRegex(sqlite3.OperationalError, "interrupted"):
                        MemoryBook(self.path)
                self.assertEqual(self._snapshot(), old)
                with MemoryBook(self.path) as recovered:
                    self.assertEqual(recovered.stats()["schema_version"], SCHEMA_VERSION)
                    self.assertIn("Tallinn", recovered.recall("conferences", project="travel")["context"])

    def test_concurrent_upgrades_recheck_version_after_acquiring_write_lock(self):
        old = self._legacy()
        barrier = threading.Barrier(2)
        migrate = MemoryBook._migrate_schema

        def simultaneous(book):
            barrier.wait(timeout=10)
            migrate(book)

        def open_and_read(_):
            with MemoryBook(self.path) as book:
                return book.revision, book.db.execute("SELECT count(*) FROM pages_stem_fts").fetchone()[0]

        with patch.object(MemoryBook, "_migrate_schema", simultaneous):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(open_and_read, range(2)))
        expected = (old["revision"] + 1, len(old["pages"]))
        self.assertEqual(results, [expected, expected])
        self.assertEqual(self._snapshot()["pages"], old["pages"])

    def test_pre_guard_schema_three_database_is_repaired_once(self):
        self._legacy()
        with MemoryBook(self.path) as book:
            revision = book.revision
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER meta_revision_sync_stem")
            db.execute("DELETE FROM meta WHERE key='stem_revision'")
            db.execute("DELETE FROM pages_stem_fts")
        with MemoryBook(self.path) as repaired:
            self.assertEqual(repaired.revision, revision + 1)
            self._assert_indexes_match(repaired)
        with MemoryBook(self.path) as reopened:
            self.assertEqual(reopened.revision, revision + 1)
            self._assert_indexes_match(reopened)

    def test_already_open_legacy_writer_repairs_insert_directory_update_and_delete(self):
        self._legacy()
        legacy = sqlite3.connect(self.path, isolation_level=None)
        legacy.execute("PRAGMA foreign_keys=ON")
        self.assertEqual(legacy.execute("PRAGMA user_version").fetchone()[0], 2)
        try:
            with MemoryBook(self.path) as book:
                original = book.db.execute("SELECT * FROM pages ORDER BY rid LIMIT 1").fetchone()
                duplicate_rid = book.db.execute("SELECT max(rid)+1 FROM pages").fetchone()[0]
                # Copy a real source page, retaining valid original text and refs,
                # through only the SQL objects known to a schema-2 writer.
                self._legacy_change(legacy, [
                    ("""INSERT INTO pages
                        SELECT ?,?,section_id,session_pk,chapter_id,project_id,title,question,content,source_refs,ordinal
                        FROM pages WHERE rid=?""", (duplicate_rid, "legacy-added-page", original["rid"])),
                    ("""INSERT INTO pages_fts(rowid,title,question,body,directory)
                        SELECT ?,title,question,body,directory FROM pages_fts WHERE rowid=?""",
                     (duplicate_rid, original["rid"])),
                ])
                self._assert_indexes_match(book)
                self.assertEqual(book.db.execute(
                    "SELECT rowid FROM pages_stem_fts WHERE pages_stem_fts MATCH 'conferences' AND rowid=?",
                    (duplicate_rid,)).fetchone()[0], duplicate_rid)
                book.recall("conferences", project="travel")
                self.assertGreater(book.stats()["cache_entries"], 0)
                self._legacy_change(legacy, [
                    ("UPDATE chapters SET title=? WHERE id=?", ("Workshop planning", original["chapter_id"])),
                    ("""UPDATE pages_fts SET directory=? WHERE rowid IN
                        (SELECT rid FROM pages WHERE chapter_id=?)""", ("workshop planning", original["chapter_id"])),
                ])
                self._assert_indexes_match(book)
                self.assertEqual(book.stats()["cache_entries"], 0)
                self.assertEqual(book.db.execute(
                    "SELECT directory FROM pages_stem_fts WHERE rowid=?", (duplicate_rid,)).fetchone()[0],
                    "workshop planning")
                self._legacy_change(legacy, [
                    ("DELETE FROM sessions WHERE id=?", (original["session_pk"],)),
                ])
                self._assert_indexes_match(book)
                self.assertEqual(book.db.execute("SELECT count(*) FROM pages_stem_fts").fetchone()[0], 0)
        finally:
            legacy.close()

    def test_current_writes_skip_compatibility_rebuild(self):
        repairs = []
        with MemoryBook(self.path) as book:
            book.db.create_function("record_stem_repair", 0, lambda: repairs.append(True) or 0)
            # Instrument the actual guard body, preserving its real condition.
            book.db.execute("DROP TRIGGER meta_revision_sync_stem")
            book.db.execute(STEM_REVISION_SQL.replace("BEGIN\n", "BEGIN\n SELECT record_stem_repair();\n", 1))
            source = {"project": "travel", "session_id": "visit", "task_id": "trip",
                      "task_title": "Planning", "messages": [
                          {"role": "user", "content": "Mira attended a conference in Tallinn."}]}
            book.ingest(source)
            book.ingest({**source, "session_id": "next", "task_title": "Updated planning"})
            book.link_session("travel", "visit", "other", "Events")
            book.delete_session("travel", "visit")
            book.delete_project("travel")
            self._assert_indexes_match(book)
            self.assertEqual(repairs, [])
            # Confirm the probe itself observes the legacy path.
            self._legacy_change(book.db, [])
            self.assertEqual(repairs, [True])
            self._assert_indexes_match(book)

    def test_failed_legacy_rebuild_rolls_back_exact_stem_revision_and_cache(self):
        self._legacy()
        legacy = sqlite3.connect(self.path, isolation_level=None)
        try:
            with MemoryBook(self.path) as book:
                book.recall("conferences", project="travel")
                before = self._snapshot()
                book.db.execute("DROP TRIGGER meta_revision_sync_stem")
                # Fail after the derived table has actually been deleted.
                broken = STEM_REVISION_SQL.replace(
                    " DELETE FROM pages_stem_fts;",
                    " DELETE FROM pages_stem_fts;\n SELECT RAISE(ABORT,'legacy stem rebuild interrupted');", 1)
                book.db.execute(broken)
                edits = [("UPDATE pages_fts SET directory=?", ("incomplete legacy rename",))]
                with self.assertRaisesRegex(sqlite3.IntegrityError, "legacy stem rebuild interrupted"):
                    self._legacy_change(legacy, edits)
                self.assertEqual(self._snapshot(), before)
                book.db.execute("DROP TRIGGER meta_revision_sync_stem")
                book.db.execute(STEM_REVISION_SQL)
                self._legacy_change(legacy, edits)
                self._assert_indexes_match(book)
                self.assertEqual(book.stats()["cache_entries"], 0)
        finally:
            legacy.close()


if __name__ == "__main__":
    unittest.main()
