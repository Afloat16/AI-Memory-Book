"""Covering-index upgrade, scope, tie ordering and source preservation."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.store import SCHEMA_VERSION


def source(project, identity, task="policy"):
    return {"project": project, "session_id": identity, "task_id": task,
            "title": "Policy notes", "task_title": "Reliability policy",
            "created_at": "2026-11-14T00:00:00Z",
            "messages": [{"role": "user", "content": "What is the reliability policy?"},
                         {"role": "assistant", "content": "Needle reliability is checked twice. 缓存保留两小时。"}]}


class WithoutCoveringHint:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, *args):
        return self.connection.execute(sql.replace(" INDEXED BY pages_recall_metadata", ""), *args)

    def __getattr__(self, name):
        return getattr(self.connection, name)


class RecallCoveringIndexTests(unittest.TestCase):
    def assert_original_sql_response(self, book, query, **options):
        actual = book.recall(query, use_cache=False, **options)
        with patch.object(book, "db", WithoutCoveringHint(book.db)):
            expected = book.recall(query, use_cache=False, **options)
        actual.pop("latency_ms")
        expected.pop("latency_ms")
        self.assertEqual(actual, expected)
        return actual

    def test_existing_schema_three_archive_adds_only_a_derived_index(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "book.db"
            with MemoryBook(path) as book:
                book.ingest(source("target", "one"))
                book.recall("needle reliability", project="target")
                before = {name: [tuple(row) for row in book.db.execute(f"SELECT * FROM {name}")]
                          for name in ("meta", "projects", "chapters", "sessions", "turns",
                                       "sections", "pages", "recall_cache", "pages_fts", "pages_stem_fts")}
                book.db.execute("DROP INDEX pages_recall_metadata")
            with MemoryBook(path) as book:
                self.assertEqual(book.db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(SCHEMA_VERSION, 3)
                self.assertEqual([row[2] for row in book.db.execute("PRAGMA index_info(pages_recall_metadata)")],
                                 ["rid", "id", "project_id", "chapter_id", "session_pk"])
                after = {name: [tuple(row) for row in book.db.execute(f"SELECT * FROM {name}")]
                         for name in before}
                self.assertEqual(after, before)
                self.assertTrue(book.recall("needle reliability", project="target")["cache_hit"])

    def test_failed_index_creation_keeps_existing_sources_and_closes_connection(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "book.db"
            with MemoryBook(path) as book:
                book.ingest(source("target", "one"))
                revision = book.revision
                pages = [tuple(row) for row in book.db.execute("SELECT * FROM pages")]
                book.db.execute("DROP INDEX pages_recall_metadata")
            opened = []
            connect = sqlite3.connect

            def guarded_connect(*args, **kwargs):
                connection = connect(*args, **kwargs)
                connection.set_authorizer(lambda action, *_:
                    sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_INDEX else sqlite3.SQLITE_OK)
                opened.append(connection)
                return connection

            with patch("memory_book.store.sqlite3.connect", guarded_connect):
                with self.assertRaises(sqlite3.DatabaseError):
                    MemoryBook(path)
            self.assertEqual(len(opened), 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                opened[0].execute("SELECT 1")
            with connect(path) as database:
                self.assertEqual(database.execute("SELECT * FROM pages").fetchall(), pages)
                self.assertEqual(int(database.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]), revision)
                self.assertIsNone(database.execute("SELECT name FROM sqlite_master WHERE name='pages_recall_metadata'").fetchone())

    def test_schema_one_and_two_upgrades_also_create_the_missing_covering_index(self):
        from tests.test_index_migration import IndexMigrationTests

        for version in (1, 2):
            with self.subTest(version=version):
                legacy = IndexMigrationTests()
                legacy.setUp()
                self.addCleanup(legacy.tearDown)
                before = legacy._legacy(version)
                with sqlite3.connect(legacy.path) as database:
                    database.execute("DROP INDEX pages_recall_metadata")
                with MemoryBook(legacy.path) as book:
                    self.assertEqual(book.db.execute("PRAGMA user_version").fetchone()[0], 3)
                    self.assertEqual([row[2] for row in book.db.execute("PRAGMA index_info(pages_recall_metadata)")],
                                     ["rid", "id", "project_id", "chapter_id", "session_pk"])
                    self.assertEqual([tuple(row) for row in book.db.execute(
                        "SELECT rid,id,content,source_refs FROM pages ORDER BY rid")], before["pages"])
                    self.assertIn("Tallinn", book.recall("conferences", project="travel", use_cache=False)["context"])

    def test_complete_payloads_match_unhinted_sql_across_scopes_routes_and_ties(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            for i in range(140):
                book.ingest(source("outside", str(i)))
            for i in range(110):
                book.ingest(source("target", str(i), task="even" if i % 2 == 0 else "odd"))
            chapter = book.db.execute("SELECT id FROM chapters WHERE project_id='target' ORDER BY id").fetchone()[0]
            for query in ("needle reliability", "缓存保留", "missingword"):
                for scope in ({"project": "target"}, {"project": "target", "chapter": chapter},
                              {"project": "target", "session": "0"}, {"project": "missing"},
                              {"project": "outside", "chapter": chapter}, {}):
                    for budget in (2000, 100000):
                        with self.subTest(query=query, scope=scope, budget=budget):
                            self.assert_original_sql_response(book, query, budget_chars=budget, **scope)
            result = self.assert_original_sql_response(book, "needle reliability", project="target")
            self.assertEqual(result["candidate_count"], 96)

    def test_candidate_plans_cover_metadata_without_loading_page_bodies(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            book.ingest(source("target", "one"))
            for query in ("needle reliability", "缓存保留"):
                statements = []
                book.db.set_trace_callback(statements.append)
                book.recall(query, project="target", use_cache=False)
                book.db.set_trace_callback(None)
                candidate_sql = [sql for sql in statements if "INDEXED BY pages_recall_metadata" in sql]
                self.assertTrue(candidate_sql)
                for sql in candidate_sql:
                    plans = [row[3] for row in book.db.execute("EXPLAIN QUERY PLAN " + sql)]
                    self.assertTrue(any("COVERING INDEX pages_recall_metadata" in plan for plan in plans), plans)
                source_sql = [sql for sql in statements if "p.content,p.source_refs" in sql]
                self.assertTrue(source_sql)
                self.assertTrue(all("INDEXED BY pages_recall_metadata" not in sql for sql in source_sql))

    def test_index_tracks_other_connection_ingest_relink_and_delete(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "book.db"
            with MemoryBook(path, cache_size=0) as reader, MemoryBook(path, cache_size=0) as writer:
                writer.ingest(source("target", "one"))
                self.assert_original_sql_response(reader, "needle reliability", project="target")
                writer.ingest(source("target", "two"))
                linked = writer.link_session("target", "two", "new-task", "Renamed policy")
                self.assert_original_sql_response(reader, "needle reliability", project="target",
                                                  chapter=linked["chapter_id"])
                writer.delete_session("target", "one")
                self.assert_original_sql_response(reader, "needle reliability", project="target")
                writer.delete_project("target")
                self.assertEqual(self.assert_original_sql_response(reader, "needle reliability", project="target")["results"], [])

    def test_selective_unbounded_chapter_and_session_routes_keep_index_choice(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            book.ingest(source("target", "one"))
            chapter = book.db.execute("SELECT id FROM chapters").fetchone()[0]
            self.assertIsNone(book._project_rowid_bounds("target"))
            for scope in ({"chapter": chapter}, {"session": "one"},
                          {"project": "target", "chapter": chapter},
                          {"project": "target", "session": "one"}):
                statements = []
                book.db.set_trace_callback(statements.append)
                book.recall("needle reliability", use_cache=False, **scope)
                book.db.set_trace_callback(None)
                routes = [sql for sql in statements if "bm25(" in sql and "LIMIT 96" in sql]
                self.assertEqual(len(routes), 2)
                self.assertTrue(all("INDEXED BY pages_recall_metadata" not in sql for sql in routes))
                self.assertTrue(any("INDEXED BY pages_recall_metadata" in sql and "WHERE p.rid IN" in sql
                                    for sql in statements))


if __name__ == "__main__":
    unittest.main()
