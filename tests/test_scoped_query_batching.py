"""Equivalent scoped SQL must preserve all results and legacy connection limits."""

from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
import memory_book.store as store


HAS_WINDOWS_AND_LIMITS = (sqlite3.sqlite_version_info >= (3, 25, 0)
                         and hasattr(sqlite3.Connection, "getlimit"))


def source(project, number, *, task=None):
    return {"project": project, "session_id": f"session-{number}",
            "task_id": task or f"task-{number % 4}", "task_title": "Worker lease policy",
            "title": "Worker lease policy", "created_at": f"2025-01-0{1 + number % 3}T00:00:00Z",
            "messages": [
                {"role": "user", "content": "What is the production lease_duration?"},
                {"role": "assistant", "content": f"Production lease_duration={30 - number % 5}."},
                {"role": "user", "content": "What is the worker lease policy?"},
                {"role": "assistant", "content": "Production lease_duration=20. Keep the original source."},
            ]}


class ScopedQueryBatchingTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", cache_size=0)
        self.addCleanup(self.book.close)
        for project, count in (("target", 56), ("foreign", 112)):
            for number in range(count):
                self.book.ingest(source(project, number))
        self.chapters = [row[0] for row in self.book.db.execute(
            "SELECT id FROM chapters WHERE project_id='target' ORDER BY id")]

    def same_directory(self, query, **kwargs):
        actual = self.book.search_directory(query, **kwargs)
        with patch.object(self.book, "_can_batch_scoped_query", return_value=False):
            expected = self.book.search_directory(query, **kwargs)
        self.assertEqual(actual, expected)
        return actual

    def same_current(self, **kwargs):
        request = {"query": "current production lease_duration", "limit": 10,
                   "budget_chars": 10000, "use_cache": False, **kwargs}
        actual = self.book.recall(**request)
        with patch.object(self.book, "_can_batch_scoped_query", return_value=False):
            expected = self.book.recall(**request)
        actual.pop("latency_ms")
        expected.pop("latency_ms")
        self.assertEqual(actual, expected)
        return actual

    def test_directory_all_fields_scores_scopes_pagination_and_empty_results_match(self):
        for query in ("worker lease", "lease_duration", "unmatchedneedle", "the and is"):
            for options in ({}, {"project": "target"}, {"chapter": self.chapters[0]},
                            {"project": "target", "chapter": self.chapters[0]},
                            {"project": "target", "limit": 1, "offset": 1},
                            {"project": "target", "limit": 1, "offset": 100}):
                with self.subTest(query=query, options=options):
                    self.same_directory(query, **options)

    def test_current_sources_pool_diagnostics_and_chapter_order_match(self):
        for options in ({}, {"project": "target"}, {"chapter": self.chapters[0]},
                        {"project": "target", "chapter": self.chapters[0]},
                        {"project": "target", "session": "session-0"},
                        {"project": "missing"}, {"project": "target", "limit": 1}):
            with self.subTest(options=options):
                self.same_current(**options)
        response = self.same_current(project="target")
        diagnostic = response["temporal"]["candidate_expansion"]
        self.assertGreater(len(diagnostic["chapter_routes"]), 1)
        self.assertFalse(diagnostic["database_scan_bounded"])

    @unittest.skipUnless(HAS_WINDOWS_AND_LIMITS, "window batching needs inspected SQLite limits")
    def test_each_batched_route_has_one_match_cursor_and_no_schema_write(self):
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            self.book.search_directory("worker lease", project="target")
            directory_sql = [sql for sql in statements if "pages_fts MATCH" in sql and not sql.startswith("--")]
            statements.clear()
            self.book.recall("current production lease_duration", project="target", limit=10,
                             use_cache=False)
            chronology_sql = [sql for sql in statements if "requested_chapters" in sql and not sql.startswith("--")]
        finally:
            self.book.db.set_trace_callback(None)
        self.assertEqual(len(directory_sql), 1)
        self.assertEqual(len(chronology_sql), 1)
        for statement in (*directory_sql, *chronology_sql):
            plan = [row[3] for row in self.book.db.execute("EXPLAIN QUERY PLAN " + statement)]
            cursors = [row for row in plan if "VIRTUAL TABLE INDEX" in row and "M" in row]
            self.assertEqual(len(cursors), 1, plan)
            self.assertIn("><", cursors[0], plan)
            self.assertNotIn("CREATE", statement)

    def test_interleaved_rows_and_global_statistics_keep_equivalent_payloads(self):
        # Widen the target span past the archive midpoint. No rows or matching
        # history are removed to make the fast path favorable.
        self.book.ingest(source("target", 999))
        self.assertIsNone(self.book._project_rowid_bounds("target"))
        self.same_directory("worker lease", project="target")
        self.same_current(project="target")

    def test_mixed_ownership_still_fails_directory_join_chain(self):
        foreign_session = self.book.db.execute(
            "SELECT id FROM sessions WHERE project_id='foreign' LIMIT 1").fetchone()[0]
        target_page = self.book.db.execute(
            "SELECT rid FROM pages WHERE project_id='target' LIMIT 1").fetchone()[0]
        self.book.db.execute("BEGIN")
        try:
            self.book.db.execute("UPDATE pages SET session_pk=? WHERE rid=?", (foreign_session, target_page))
            response = self.same_directory("worker lease", project="target")
            self.assertEqual(sum(row["matching_pages"] for row in response["results"]), 111)
            self.assertTrue(self.book.db.in_transaction)
        finally:
            self.book.db.execute("ROLLBACK")

    @unittest.skipUnless(HAS_WINDOWS_AND_LIMITS, "getlimit/setlimit are optional before Python 3.11")
    def test_reduced_connection_limits_keep_successful_original_statements(self):
        with patch.object(self.book, "_can_batch_scoped_query", return_value=False):
            expected = self.book.search_directory("worker lease", project="target")
        original_routes = self.book._batch_current_revision_routes(
            self.chapters, 24, 0, '"lease"', " AND p.project_id=?", ["target"])
        limits = ((sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 4),
                  (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 2100),
                  (sqlite3.SQLITE_LIMIT_COLUMN, 100),
                  (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 50),
                  (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 1),
                  (sqlite3.SQLITE_LIMIT_VDBE_OP, 5000),
                  (sqlite3.SQLITE_LIMIT_LENGTH, 10000000))
        for category, value in limits:
            with self.subTest(category=category):
                previous = self.book.db.setlimit(category, value)
                try:
                    self.assertEqual(self.book.search_directory("worker lease", project="target"), expected)
                    routes = self.book._batch_current_revision_routes(
                        self.chapters, 24, 0, '"lease"', " AND p.project_id=?", ["target"])
                    # The chronology statement is shorter than the directory
                    # statement. It may still fit this SQL-length limit; when
                    # retained it must return exactly the original rows.
                    if category == sqlite3.SQLITE_LIMIT_SQL_LENGTH and routes is not None:
                        self.assertEqual(routes, original_routes)
                    else:
                        self.assertIsNone(routes)
                finally:
                    self.book.db.setlimit(category, previous)

    def test_old_sqlite_missing_limit_api_and_custom_factories_keep_original_path(self):
        with patch.object(store.sqlite3, "sqlite_version_info", (3, 24, 0)):
            self.assertFalse(self.book._can_batch_scoped_query("SELECT 1", 0))
            self.same_directory("worker lease", project="target")
        native_getattr = getattr

        def absent(value, name, *default):
            return None if value is self.book.db and name == "getlimit" else native_getattr(value, name, *default)

        with patch.object(store, "getattr", absent, create=True):
            self.assertFalse(self.book._can_batch_scoped_query("SELECT 1", 0))
            self.same_directory("worker lease", project="target")
        for attribute, factory in (("row_factory", lambda cursor, values: sqlite3.Row(cursor, values)),
                                   ("text_factory", lambda raw: raw.decode())):
            original = getattr(self.book.db, attribute)
            try:
                setattr(self.book.db, attribute, factory)
                self.assertFalse(self.book._can_batch_scoped_query("SELECT 1", 0))
                self.same_directory("worker lease", project="target")
                self.same_current(project="target")
            finally:
                setattr(self.book.db, attribute, original)

        class Wrapper:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

        original = self.book.db
        try:
            self.book.db = Wrapper(original)
            self.assertFalse(self.book._can_batch_scoped_query("SELECT 1", 0))
            self.same_directory("worker lease", project="target")
            self.same_current(project="target")
        finally:
            self.book.db = original


if __name__ == "__main__":
    unittest.main()
