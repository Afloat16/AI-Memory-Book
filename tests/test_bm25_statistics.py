"""Compare bounded searches with actual global FTS5 and exercise every writer."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import bm25_stats
from memory_book.text import query_terms


def source(project, identity, *, turns=1, value=12, task=None, title=None):
    return {"project": project, "session_id": str(identity), "task_id": task or f"policy-{identity % 3}",
            "title": title or "Worker policy conferences run running", "task_title": title or "Worker lease policy 缓存策略",
            "created_at": f"2025-02-{1 + identity % 27:02}T00:00:00Z",
            "messages": [message for _ in range(turns) for message in (
                {"role": "user", "content": "What is the approved lease_duration and HTTPParser policy?"},
                {"role": "assistant", "content": f"Production lease_duration={value}. HTTPParser keeps old boundary_guard=stable. "
                 + "Runners were running through conferences. 缓存有效时长=12。 " * (1 + identity % 4)})]}


def stable(response):
    return {key: value for key, value in response.items() if key != "latency_ms"}


class BM25StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", min_page_chars=0)
        self.addCleanup(self.book.close)
        for identity in range(14):
            self.book.ingest(source("target", identity, value=identity + 10))
            self.book.ingest(source("foreign", identity, turns=2, value=identity + 100))

    def assert_global_parity(self, query, **options):
        with patch.object(self.book._bm25, "ranked_routes", return_value=None):
            expected = self.book.recall(query, use_cache=False, **options)
        with patch.object(bm25_stats, "MIN_ARCHIVE_PAGES", 0):
            actual = self.book.recall(query, use_cache=False, **options)
        self.assertEqual(stable(actual), stable(expected))
        return actual

    def assert_statistics_match_fts(self, book=None):
        book = book or self.book
        for route, table in enumerate(("pages_fts", "pages_stem_fts")):
            book.db.execute(f"CREATE VIRTUAL TABLE temp.test_bm25_row_{route} USING fts5vocab(main,{table},'row')")
            book.db.execute(f"CREATE VIRTUAL TABLE temp.test_bm25_col_{route} USING fts5vocab(main,{table},'col')")
            book.db.execute(f"CREATE VIRTUAL TABLE temp.test_bm25_inst_{route} USING fts5vocab(main,{table},'instance')")
            try:
                expected = {}
                for row in book.db.execute(f"SELECT term,doc FROM test_bm25_row_{route}"):
                    expected[row[0]] = [row[1], 0, 0]
                for row in book.db.execute(f"SELECT term,doc FROM test_bm25_col_{route} WHERE col='body'"):
                    expected[row[0]][1] = row[1]
                for row in book.db.execute(f"""SELECT term,count(DISTINCT doc) FROM test_bm25_inst_{route}
                        WHERE col IN ('title','question','directory') GROUP BY term"""):
                    expected[row[0]][2] = row[1]
                actual = {row[0]: list(row)[1:] for row in book.db.execute(
                    "SELECT term,documents,body_documents,metadata_documents FROM bm25_terms WHERE route=?", (route,))}
                self.assertEqual(actual, expected)
                totals = tuple(book.db.execute("SELECT documents,tokens FROM bm25_corpus WHERE route=?", (route,)).fetchone())
                self.assertEqual(totals, (book.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0],
                                         book.db.execute(f"SELECT count(*) FROM test_bm25_inst_{route}").fetchone()[0]))
            finally:
                for mode in ("row", "col", "inst"):
                    book.db.execute(f"DROP TABLE test_bm25_{mode}_{route}")

    def test_global_scores_sources_and_context_match_actual_fts5(self):
        chapter = self.book.db.execute("SELECT id FROM chapters WHERE project_id='target' ORDER BY id LIMIT 1").fetchone()[0]
        for query in ("lease_duration", "current approved lease_duration", "old boundary_guard",
                      "conferences running runners", "run running", "HTTPParser", "缓存有效时长",
                      "nonexistent_needle", "policy conferences", "a the and"):
            for scope in ({"project": "target"}, {"project": "target", "chapter": chapter},
                          {"project": "target", "session": "3"}, {"project": "missing"}):
                for strategy in ("book", "flat"):
                    with self.subTest(query=query, scope=scope, strategy=strategy):
                        self.assert_global_parity(query, strategy=strategy, **scope)

    def test_statistics_match_original_sqlite_tokenizers_and_column_filters(self):
        self.book.ingest({**source("target", 77), "messages": [
            {"role": "user", "content": "Résumé naïve São HTTPParser λ Ελληνικά"},
            {"role": "assistant", "content": "缓存 序列 коты кот running runners élan café µ μ ᾶ"}]})
        self.assert_statistics_match_fts()

    def test_unrounded_ranks_and_ties_are_bit_identical_to_sqlite_bm25(self):
        self.book.ingest({**source("target", 31), "messages": [
            {"role": "user", "content": "Rarewort title"},
            {"role": "assistant", "content": "Rarewort controlled controlling running ran run. 缓存唯一方案。"}]})
        with patch.object(bm25_stats, "MIN_ARCHIVE_PAGES", 0):
            for query in ("lease_duration", "running run runners", "Rarewort controlled controlling",
                          "HTTPParser", "缓存唯一方案", "policy worker", "never_present"):
                tokens = query_terms(query)
                expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
                expression = f"({expression}) AND body : ({expression})"
                routes = self.book._bm25.ranked_routes("target", tokens, True, None, None)
                for route, table in enumerate(("pages_fts", "pages_stem_fts")):
                    expected = [(row[0], row[1]) for row in self.book.db.execute(
                        f"SELECT p.id,bm25({table},2.0,2.0,1.0,0.25) rank FROM {table} "
                        f"JOIN pages p ON p.rid={table}.rowid WHERE {table} MATCH ? "
                        "AND p.project_id=? ORDER BY rank,p.id LIMIT 96", (expression, "target"))]
                    actual = [(row["id"], row["rank"]) for row in routes[route]]
                    self.assertEqual(actual, expected, (query, table))

    def test_replacement_relink_delete_and_foreign_ingestion_keep_stats_exact(self):
        operations = (
            lambda: self.book.ingest(source("target", 3, value=77, turns=3)),
            lambda: self.book.ingest(source("foreign", 77, value=777, turns=8)),
            lambda: self.book.link_session("target", "3", "other-policy", "Revised lease policy"),
            lambda: self.book.ingest(source("target", 22, title="Renamed shared chapter", task="policy-1")),
            lambda: self.book.delete_session("target", "4"),
            lambda: self.book.delete_project("foreign"),
        )
        for operation in operations:
            operation()
            self.assert_statistics_match_fts()
            self.assert_global_parity("current approved lease_duration", project="target")
            self.assert_global_parity("running conferences", project="target", temporal="relevance")

    def test_failed_ingest_rolls_back_sources_statistics_and_revision(self):
        names = ("pages", "bm25_pages", "bm25_terms", "bm25_corpus", "meta")
        before = {name: [tuple(row) for row in self.book.db.execute(f"SELECT * FROM {name}")] for name in names}
        with patch.object(self.book, "_changed", side_effect=RuntimeError("stop before commit")):
            with self.assertRaisesRegex(RuntimeError, "stop before commit"):
                self.book.ingest(source("target", 3, value=888, turns=4))
        after = {name: [tuple(row) for row in self.book.db.execute(f"SELECT * FROM {name}")] for name in names}
        self.assertEqual(after, before)
        self.assert_global_parity("lease_duration", project="target")

    def test_one_time_upgrade_preserves_every_source_and_cached_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive.db"
            with MemoryBook(path) as book:
                book.ingest(source("target", 1))
                book.recall("lease_duration", project="target")
                original = {name: [tuple(row) for row in book.db.execute(f"SELECT * FROM {name}")]
                            for name in ("projects", "chapters", "sessions", "turns", "sections", "pages", "recall_cache")}
                revision = book.revision
                book.db.execute("DROP TRIGGER meta_revision_invalidate_bm25")
                for table in ("bm25_pages", "bm25_terms", "bm25_corpus"):
                    book.db.execute(f"DROP TABLE {table}")
                book.db.execute("DELETE FROM meta WHERE key IN ('bm25_revision','bm25_version')")
            with MemoryBook(path) as book:
                self.assertEqual(book.revision, revision)
                self.assertEqual({name: [tuple(row) for row in book.db.execute(f"SELECT * FROM {name}")]
                                  for name in original}, original)
                self.assertTrue(book.recall("lease_duration", project="target")["cache_hit"])
                self.assert_statistics_match_fts(book)

    def test_older_writer_invalidates_statistics_and_reads_fall_back_until_rebuild(self):
        # Simulate the already-supported lexical-aware writer: it updates
        # source/FTS rows and lexical_revision but knows no BM25 marker.
        self.book.db.execute("BEGIN IMMEDIATE")
        self.book.db.execute("UPDATE pages_fts SET body=body || ' extraunique' WHERE rowid=1")
        self.book.db.execute("UPDATE pages_stem_fts SET body=body || ' extraunique' WHERE rowid=1")
        for marker in ("stem_revision", "lexical_revision"):
            self.book.db.execute("""INSERT OR REPLACE INTO meta SELECT ?,CAST(value AS INTEGER)+1
              FROM meta WHERE key='revision'""", (marker,))
        self.book.db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
        self.book.db.execute("DELETE FROM recall_cache")
        self.book.db.execute("COMMIT")
        self.assertEqual(self.book.db.execute("SELECT value FROM meta WHERE key='bm25_revision'").fetchone()[0], "stale")
        with patch.object(bm25_stats, "MIN_ARCHIVE_PAGES", 0):
            self.assertIsNone(self.book._bm25.ranked_routes("target", ["extraunique"], True, None, None))
        self.book._bm25.ensure()
        self.assert_statistics_match_fts()
        self.assert_global_parity("extraunique", project="target")

    def test_scope_and_byte_caps_fall_back_without_a_partial_history(self):
        with patch.object(bm25_stats, "MIN_ARCHIVE_PAGES", 0):
            for size in (256, 257):
                with MemoryBook(":memory:", segmentation="turn", min_page_chars=0) as book:
                    book.ingest(source("target", 0, turns=size))
                    routes = book._bm25.ranked_routes("target", ["lease"], True, None, None)
                    if size == 256:
                        self.assertIsNotNone(routes)
                        self.assertEqual(len(routes.exact_matches), size)
                    else:
                        self.assertIsNone(routes)
            with patch.object(bm25_stats, "MAX_PROJECT_BYTES", 1):
                self.assertIsNone(self.book._bm25.ranked_routes("target", ["lease"], True, None, None))
            with patch.object(bm25_stats, "MAX_PROJECT_DECODED_BYTES", 1):
                self.assertIsNone(self.book._bm25.ranked_routes("target", ["lease"], True, None, None))

    def test_directory_counts_pagination_and_ownership_keep_global_ranks(self):
        for query in ("policy", "lease worker", "缓存策略", "missingneedle"):
            for options in ({"limit": 10}, {"limit": 1}, {"limit": 1, "offset": 1},
                            {"limit": 1, "offset": 100}):
                with patch.object(self.book._bm25, "directory_hits", return_value=None):
                    expected = self.book.search_directory(query, project="target", **options)
                with patch.object(bm25_stats, "MIN_ARCHIVE_PAGES", 0):
                    actual = self.book.search_directory(query, project="target", **options)
                self.assertEqual(actual, expected)

    def test_recent_expansion_uses_complete_project_and_retains_original_evidence(self):
        self.book.ingest(source("target", 25, turns=130, value=999, task="long-policy"))
        with patch.object(self.book._bm25, "ranked_routes", return_value=None):
            expected = self.book.recall("current lease_duration", project="target", use_cache=False)
        with patch.object(bm25_stats, "MIN_ARCHIVE_PAGES", 0):
            actual = self.book.recall("current lease_duration", project="target", use_cache=False)
        # The truthful route diagnostic changes; result ordering, full source
        # references, scores, context and all other assessment fields do not.
        expansion = actual["temporal"]["candidate_expansion"]
        self.assertEqual(expansion["metadata_source"], "complete_project_statistics")
        self.assertTrue(expansion["database_scan_bounded"])
        expansion["metadata_source"] = expected["temporal"]["candidate_expansion"]["metadata_source"]
        expansion["database_scan_bounded"] = expected["temporal"]["candidate_expansion"]["database_scan_bounded"]
        self.assertEqual(stable(actual), stable(expected))

    @unittest.skipUnless(hasattr(sqlite3.Connection, "setlimit"), "inspected SQLite limits unavailable")
    def test_reduced_sql_length_uses_original_successful_route(self):
        with MemoryBook(":memory:", cache_size=0) as book:
            book.ingest({"project": "target", "session_id": "one", "messages": [
                {"role": "assistant", "content": "Approved retry_limit=7."}]})
            prior = book.db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 600)
            try:
                with patch.object(book._bm25, "ranked_routes", return_value=None):
                    expected = book.recall("retry_limit", project="target", use_cache=False)
                with patch.object(bm25_stats, "MIN_ARCHIVE_PAGES", 0):
                    actual = book.recall("retry_limit", project="target", use_cache=False)
                self.assertEqual(stable(actual), stable(expected))
            finally:
                book.db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, prior)

    def test_cross_connection_replacement_and_snapshot_keep_exact_statistics(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive.db"
            with MemoryBook(path, segmentation="turn") as reader, MemoryBook(path, segmentation="turn") as writer:
                reader.ingest(source("target", 1))
                reader.ingest(source("foreign", 2))
                with patch.object(bm25_stats, "MIN_ARCHIVE_PAGES", 0):
                    before = reader.recall("current lease_duration", project="target")
                    self.assertTrue(reader.recall("current lease_duration", project="target")["cache_hit"])
                    reader.db.execute("BEGIN")
                    reader.db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()
                    original_stats = [tuple(row) for row in reader.db.execute("SELECT * FROM bm25_corpus")]
                    writer.ingest(source("target", 1, turns=3, value=99))
                    self.assertEqual([tuple(row) for row in reader.db.execute("SELECT * FROM bm25_corpus")], original_stats)
                    reader.db.execute("COMMIT")
                    after = reader.recall("current lease_duration", project="target")
                    self.assertFalse(after["cache_hit"])
                    self.assertGreater(after["revision"], before["revision"])
                    with patch.object(reader._bm25, "ranked_routes", return_value=None):
                        expected = reader.recall("current lease_duration", project="target", use_cache=False)
                    self.assertEqual(stable(after), stable(expected))
                    self.assert_statistics_match_fts(reader)

    def test_failed_migration_rolls_back_derived_tables_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive.db"
            with MemoryBook(path) as book:
                book.ingest(source("target", 1))
                revision = book.revision
                sources = book.export()
                book.db.execute("DROP TRIGGER meta_revision_invalidate_bm25")
                for table in ("bm25_pages", "bm25_terms", "bm25_corpus"):
                    book.db.execute(f"DROP TABLE {table}")
                book.db.execute("DELETE FROM meta WHERE key IN ('bm25_revision','bm25_version')")
            with patch.object(bm25_stats.BM25Statistics, "_summary", side_effect=RuntimeError("rebuild interrupted")):
                with self.assertRaisesRegex(RuntimeError, "rebuild interrupted"):
                    MemoryBook(path)
            with sqlite3.connect(path) as database:
                self.assertEqual(database.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0], str(revision))
                self.assertIsNone(database.execute("SELECT name FROM sqlite_master WHERE name='bm25_pages'").fetchone())
            with MemoryBook(path) as book:
                self.assertEqual(book.export(), sources)
                self.assertEqual(book.revision, revision)
                self.assert_statistics_match_fts(book)


if __name__ == "__main__":
    unittest.main()
