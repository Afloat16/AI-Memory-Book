"""Atomic empty archives and same-snapshot candidate metadata reuse."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store


def schema(connection):
    return [tuple(row) for row in connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]


class AtomicInitializationTests(unittest.TestCase):
    def test_empty_archive_matches_original_schema_and_initial_values(self):
        with sqlite3.connect(":memory:", isolation_level=None) as original:
            original.executescript(store.SCHEMA)
            with MemoryBook(":memory:") as book:
                self.assertEqual(schema(book.db), schema(original))
                for query in ("SELECT * FROM meta ORDER BY key",
                              "PRAGMA user_version", "PRAGMA application_id"):
                    self.assertEqual([tuple(row) for row in book.db.execute(query)],
                                     [tuple(row) for row in original.execute(query)])
                self.assertFalse(book.db.in_transaction)
                self.assertEqual(book.revision, 0)
                self.assertEqual(book.stats()["pages"], 0)

    def test_partial_schema_failure_rolls_back_and_closes_the_connection(self):
        connect = sqlite3.connect
        scripts = (
            store.SCHEMA.replace("CREATE TABLE IF NOT EXISTS sessions (",
                "SELECT absent_schema_function();\nCREATE TABLE IF NOT EXISTS sessions (", 1),
            store.SCHEMA + "\nSELECT absent_schema_function();\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            for number, script in enumerate(scripts):
                path = Path(directory) / f"failed-{number}.db"
                opened = []

                def recorded(*args, **kwargs):
                    connection = connect(*args, **kwargs)
                    opened.append(connection)
                    return connection

                with self.subTest(stage=number), patch.object(store, "SCHEMA", script), \
                        patch.object(store.sqlite3, "connect", side_effect=recorded):
                    with self.assertRaisesRegex(sqlite3.OperationalError, "absent_schema_function"):
                        MemoryBook(path)
                with self.assertRaises(sqlite3.ProgrammingError):
                    opened[0].execute("SELECT 1")
                with connect(path) as connection:
                    self.assertEqual(schema(connection), [])
                    self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
                    self.assertEqual(connection.execute("PRAGMA application_id").fetchone()[0], 0)
                with MemoryBook(path) as recovered:
                    self.assertEqual(recovered.revision, 0)
                    self.assertEqual(recovered.stats()["pages"], 0)

    def test_concurrent_initializers_recheck_under_the_write_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.db"
            barrier = threading.Barrier(2)
            migrate = MemoryBook._migrate_schema

            def simultaneous(book):
                barrier.wait(timeout=10)
                migrate(book)

            def open_archive(_):
                with MemoryBook(path) as book:
                    return book.revision, book.stats()["pages"], schema(book.db)

            with patch.object(MemoryBook, "_migrate_schema", simultaneous):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(open_archive, range(2)))
            self.assertEqual(results[0], results[1])
            self.assertEqual(results[0][:2], (0, 0))

    def test_foreign_writer_between_initial_read_and_lock_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "other.db"
            migrate = MemoryBook._migrate_schema

            def foreign_writer(book):
                with sqlite3.connect(path) as other:
                    other.execute("CREATE TABLE unrelated(value TEXT)")
                    other.execute("INSERT INTO unrelated VALUES('preserve me')")
                migrate(book)

            with patch.object(MemoryBook, "_migrate_schema", foreign_writer):
                with self.assertRaisesRegex(ValueError, "refusing to initialize"):
                    MemoryBook(path)
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("SELECT * FROM unrelated").fetchall(),
                                 [("preserve me",)])
                self.assertEqual([row[1] for row in schema(connection)], ["unrelated"])
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)


class IndependentMetadataConnection:
    """Keep the pre-carry native SQL route without changing its SQLite rows."""

    def __init__(self, connection):
        self.connection = connection

    def __getattr__(self, name):
        return getattr(self.connection, name)


class CandidateMetadataCarryTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", cache_size=0, segmentation="turn",
                               max_page_chars=900, min_page_chars=0)
        self.addCleanup(self.book.close)
        for session in range(10):
            messages = []
            for number in range(8):
                text = ("Quartz pressure " * (number + 1) + "cedars voltage evidence. " +
                        "ordinary background " * (36 - 4 * number))
                messages.append({"role": "user", "content": text})
            self.book.ingest({"project": "outside" if session == 9 else "fixture",
                "session_id": str(session), "task_id": f"task-{session}",
                "title": "Quartz pressure" if session % 2 else "Other notes",
                "task_title": "Cedar voltage" if session % 3 else "Record",
                "created_at": f"2026-11-{session + 1:02d}T00:00:00Z", "messages": messages})

    def both_paths(self, query, **options):
        connection = self.book.db
        results, statements = [], []
        try:
            for carried in (True, False):
                self.book.db = connection if carried else IndependentMetadataConnection(connection)
                traced = []
                connection.set_trace_callback(traced.append)
                result = self.book.recall(query, use_cache=False, **options)
                result.pop("latency_ms")
                results.append(result)
                statements.append(traced)
        finally:
            connection.set_trace_callback(None)
            self.book.db = connection
        self.assertEqual(results[0], results[1])
        return results[0], statements

    @unittest.skipUnless(hasattr(sqlite3.Connection, "getlimit"), "Python 3.10 retains the original SQL")
    def test_same_payload_avoids_reloading_the_union_covering_metadata(self):
        result, statements = self.both_paths("quartz", project="fixture", limit=1)
        redundant = "SELECT id,project_id,chapter_id,session_pk"
        self.assertFalse(any(redundant in query for query in statements[0]))
        self.assertTrue(any(redundant in query for query in statements[1]))
        self.assertGreater(result["candidate_count"], len(result["results"]))
        self.assertTrue(any("WITH requested(chapter_id,session_pk)" in query
                            for query in statements[0]))
        self.assertTrue(all("rank,p.project_id,p.chapter_id,p.session_pk" in query
            for query in statements[0] if query.lstrip().startswith("SELECT p.rid,p.id,bm25(")))

    def test_fused_routes_current_order_and_all_scopes_preserve_complete_payloads(self):
        chapter = self.book.db.execute("SELECT id FROM chapters WHERE project_id='fixture' ORDER BY id").fetchone()[0]
        for query in ("quartz pressure", "cedar", "current quartz", "previous current quartz"):
            for scope in ({}, {"project": "fixture"}, {"chapter": chapter},
                          {"session": "0"}, {"project": "absent"}):
                with self.subTest(query=query, scope=scope):
                    self.both_paths(query, budget_chars=4000, **scope)
        for limit, chars in ((1, 100), (50, 100000), (5, 0)):
            self.both_paths("quartz pressure", limit=limit, budget_chars=chars)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Install .[tokens]")
    def test_token_caps_and_encoders_preserve_source_spans_and_counts(self):
        for tokenizer in ("cl100k_base", "o200k_base"):
            for cap in (0, 512, 1024, 2048):
                with self.subTest(tokenizer=tokenizer, cap=cap):
                    self.both_paths("quartz pressure", project="fixture", budget_chars=8000,
                                    budget_tokens=cap, tokenizer=tokenizer)

    def test_custom_factories_keep_the_original_sql_path(self):
        for name, factory in (("row_factory", lambda cursor, row: sqlite3.Row(cursor, row)),
                              ("text_factory", lambda raw: raw.decode("utf-8"))):
            original = getattr(self.book.db, name)
            try:
                setattr(self.book.db, name, factory)
                _, statements = self.both_paths("quartz", project="fixture", limit=1)
                self.assertTrue(all("rank,p.project_id,p.chapter_id,p.session_pk" not in query
                    for query in statements[0]))
            finally:
                setattr(self.book.db, name, original)

    @unittest.skipUnless(hasattr(sqlite3.Connection, "setlimit"), "Requires inspectable SQLite limits")
    def test_lowered_sqlite_limits_keep_independent_metadata_queries(self):
        for category, value in ((sqlite3.SQLITE_LIMIT_COLUMN, 10),
                (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100),
                (sqlite3.SQLITE_LIMIT_VDBE_OP, 100000),
                (sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 128),
                (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 2000)):
            previous = self.book.db.setlimit(category, value)
            try:
                with self.subTest(category=category):
                    _, statements = self.both_paths("quartz", project="fixture", limit=1)
                    self.assertTrue(any("SELECT id,project_id,chapter_id,session_pk" in query
                                        for query in statements[0]))
                    self.assertTrue(all("rank,p.project_id,p.chapter_id,p.session_pk" not in query
                                        for query in statements[0]))
            finally:
                self.book.db.setlimit(category, previous)

    def test_corrupt_tail_directory_is_validated_before_omitting_candidates(self):
        self.book.db.execute("PRAGMA foreign_keys=OFF")
        identity, original = self.book.db.execute(
            "SELECT id,chapter_id FROM pages WHERE project_id='fixture' ORDER BY rid DESC LIMIT 1").fetchone()
        for chapter in ("missing", sqlite3.Binary(b"not text")):
            self.book.db.execute("UPDATE pages SET chapter_id=? WHERE id=?", (chapter, identity))
            errors = []
            connection = self.book.db
            try:
                for carried in (True, False):
                    self.book.db = connection if carried else IndependentMetadataConnection(connection)
                    try:
                        self.book.recall("quartz", project="fixture", limit=1, use_cache=False)
                    except Exception as error:
                        errors.append((type(error), error.args))
            finally:
                self.book.db = connection
            self.assertEqual(len(errors), 2)
            self.assertEqual(errors[0], errors[1])
            self.book.db.execute("UPDATE pages SET chapter_id=? WHERE id=?", (original, identity))


if __name__ == "__main__":
    unittest.main()
