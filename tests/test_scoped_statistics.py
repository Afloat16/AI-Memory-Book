from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.scoped import EXACT_TABLE, STEM_TABLE, project_tables, state
from memory_book.text import query_terms


def record(project, name, content, *, task="", title="Ledger"):
    return {"project": project, "session_id": name, "title": title,
            "task_id": task, "task_title": "Archive " + task,
            "created_at": "2026-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": content}]}


def stable(response):
    result = copy.deepcopy(response)
    result.pop("latency_ms", None)
    return result


def comparable(response):
    result = stable(response)
    result.pop("revision", None)
    result.pop("project_local_fts_statistics", None)
    return result


def native_scores(book, table, query, project):
    expression = " OR ".join('"' + token + '"' for token in query_terms(query))
    expression = f"({expression}) AND body : ({expression})"
    return [(row["id"], row["rank"]) for row in book.db.execute(
        f"SELECT p.id,bm25({table},2.0,2.0,1.0,0.25) rank "
        f"FROM {table} JOIN pages p ON p.rid={table}.rowid "
        f"WHERE {table} MATCH ? AND p.project_id=? ORDER BY rank,p.id LIMIT 96",
        (expression, project))]


def indexed_rows(book, table, project=None):
    if project is None:
        rows = book.db.execute(f"SELECT rowid,title,question,body,directory FROM temp.{table} ORDER BY rowid")
    else:
        rows = book.db.execute("SELECT f.rowid,f.title,f.question,f.body,f.directory "
            "FROM main.pages_fts f JOIN main.pages p ON p.rid=f.rowid "
            "WHERE p.project_id=? ORDER BY f.rowid", (project,))
    return [tuple(row) for row in rows]


class ProjectStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "book.db"
        self.book = MemoryBook(self.path)

    def tearDown(self):
        self.book.close()
        self.directory.cleanup()

    def local(self, query="alpha beta", project="wanted", **options):
        return self.book.recall(query, project=project, use_cache=False,
                                project_local_fts_statistics=True, **options)

    def seed(self):
        self.book.ingest(record("wanted", "a", "Alpha alpha alpha alpha alpha.", task="one"))
        self.book.ingest(record("wanted", "b", "Beta.", task="two"))
        self.book.ingest(record("outside", "c", "Gamma gamma.", task="three"))

    def assert_pair_matches_source(self, project):
        for table in (EXACT_TABLE, STEM_TABLE):
            self.assertEqual(indexed_rows(self.book, table), indexed_rows(self.book, "pages_fts", project))

    def test_validation_is_explicit_and_default_never_prepares_a_scope(self):
        self.seed()
        for bad in (None, 1, "project"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "must be a boolean"):
                self.book.recall("alpha", project="wanted", project_local_fts_statistics=bad)
        with self.assertRaisesRegex(ValueError, "requires project"):
            self.book.recall("alpha", project_local_fts_statistics=True)
        with patch("memory_book.scoped.project_tables", side_effect=AssertionError("default called helper")):
            implicit = self.book.recall("alpha beta", project="wanted", use_cache=False)
            explicit = self.book.recall("alpha beta", project="wanted", use_cache=False,
                                        project_local_fts_statistics=False)
        self.assertEqual(stable(implicit), stable(explicit))
        self.assertNotIn("project_local_fts_statistics", implicit)
        self.assertFalse(state(self.book.db)["initialized"])

    def test_native_scores_match_independent_single_project_exact_and_stem(self):
        sources = [record("wanted", "a", "Alpha alpha alpha. Running is reliable."),
                   record("wanted", "b", "Beta and a runner. Café Straße RetryCount."),
                   record("wanted", "c", "配置重试时间为三秒。缓存策略保持稳定。")]
        # Outside rows precede wanted rows, so equivalence cannot rely on rowids.
        self.book.ingest(record("outside", "noise", "Alpha alpha beta beta runner running."))
        with MemoryBook(":memory:", cache_size=0) as isolated:
            for source in sources:
                self.book.ingest(source)
                isolated.ingest(source)
            self.book.db.execute("BEGIN")
            try:
                tables = project_tables(self.book.db, "wanted", self.book.revision)
                for local, global_table in zip(tables, ("pages_fts", "pages_stem_fts")):
                    for query in ("alpha beta", "runs", "cafe strasse", "retry_count", "配置重试缓存"):
                        with self.subTest(table=local, query=query):
                            self.assertEqual(native_scores(self.book, local, query, "wanted"),
                                             native_scores(isolated, global_table, query, "wanted"))
            finally:
                self.book.db.execute("COMMIT")
            for query in ("alpha beta", "runs", "cafe strasse", "配置重试缓存"):
                self.assertEqual(comparable(self.local(query, budget_chars=100000)), comparable(
                    isolated.recall(query, project="wanted", budget_chars=100000, use_cache=False)))

    def test_other_project_changes_global_rank_but_not_local_scores_or_payload(self):
        self.book.ingest(record("wanted", "a", "Alpha alpha alpha alpha alpha."))
        self.book.ingest(record("wanted", "b", "Beta."))
        before = self.local(limit=1)
        before_scores = native_scores(self.book, EXACT_TABLE, "alpha beta", "wanted")
        global_before = self.book.recall("alpha beta", project="wanted", limit=1, use_cache=False)
        for index in range(40):
            self.book.ingest(record("outside", str(index), "Alpha alpha alpha alpha alpha."))
        after = self.local(limit=1)
        global_after = self.book.recall("alpha beta", project="wanted", limit=1, use_cache=False)
        self.assertNotEqual(global_before["results"][0]["id"], global_after["results"][0]["id"])
        self.assertEqual(native_scores(self.book, EXACT_TABLE, "alpha beta", "wanted"), before_scores)
        self.assertEqual(comparable(before), comparable(after))
        self.assertTrue(self.book.delete_project("outside"))
        self.assertEqual(comparable(before), comparable(self.local(limit=1)))
        self.assertEqual(state(self.book.db)["builds"], 3)

    def test_warm_pair_project_switches_empty_query_and_empty_project(self):
        self.seed()
        self.local()
        first = state(self.book.db)
        self.local("beta")
        self.assertEqual(state(self.book.db), first)
        self.local("gamma", project="outside")
        self.assertEqual((state(self.book.db)["builds"], state(self.book.db)["switches"]), (2, 1))
        self.assert_pair_matches_source("outside")
        self.local()
        self.assertEqual((state(self.book.db)["builds"], state(self.book.db)["switches"]), (3, 2))
        missing = self.local(project="missing")
        self.assertEqual(missing["results"], [])
        self.assertEqual(state(self.book.db)["page_count"], 0)
        self.assert_pair_matches_source("missing")
        before = state(self.book.db)
        self.local("", project="wanted")
        self.local("alpha", project="wanted", budget_chars=0)
        self.assertEqual(state(self.book.db), before)

    def test_current_project_write_delete_and_relink_refresh_all_four_columns(self):
        self.seed()
        self.local()
        self.book.ingest(record("wanted", "a", "Alpha changed to delta.", task="one"))
        self.local("delta")
        self.assert_pair_matches_source("wanted")
        self.book.link_session("wanted", "a", "renamed", "Revised directory")
        self.local("delta")
        self.assert_pair_matches_source("wanted")
        self.assertTrue(any("revised" in row[-1] for row in indexed_rows(self.book, EXACT_TABLE)))
        self.assertTrue(self.book.delete_session("wanted", "a"))
        self.local("beta")
        self.assert_pair_matches_source("wanted")
        self.assertTrue(self.book.delete_project("wanted"))
        self.assertEqual(self.local()["results"], [])
        self.assertEqual(state(self.book.db)["page_count"], 0)
        self.assertEqual(state(self.book.db)["builds"], 5)

    def test_external_writes_and_read_snapshot_do_not_mix_revisions(self):
        self.seed()
        self.local()
        old = state(self.book.db)
        old_rows = indexed_rows(self.book, EXACT_TABLE)
        self.book.db.execute("BEGIN")
        revision = self.book.revision
        with MemoryBook(self.path) as writer:
            writer.ingest(record("wanted", "a", "Alpha becomes epsilon.", task="one"))
            self.assertNotEqual(writer.revision, revision)
            project_tables(self.book.db, "wanted", revision)
            self.assertEqual(state(self.book.db), old)
            self.assertEqual(indexed_rows(self.book, EXACT_TABLE), old_rows)
        self.book.db.execute("COMMIT")
        self.assertIn("epsilon", self.local("epsilon")["context"])
        self.assert_pair_matches_source("wanted")
        with MemoryBook(self.path) as writer:
            writer.link_session("wanted", "a", "external", "External directory")
        self.local("epsilon")
        self.assert_pair_matches_source("wanted")
        with MemoryBook(self.path) as writer:
            writer.delete_session("wanted", "a")
        self.assertEqual(self.local("epsilon")["results"], [])
        self.assert_pair_matches_source("wanted")

    def test_first_build_and_switch_rollback_restore_sql_marker_and_indexes(self):
        self.seed()
        with self.assertRaisesRegex(RuntimeError, "read transaction"):
            project_tables(self.book.db, "wanted", self.book.revision)
        self.book.db.execute("BEGIN")
        project_tables(self.book.db, "wanted", self.book.revision)
        self.assertTrue(state(self.book.db)["initialized"])
        self.book.db.execute("ROLLBACK")
        self.assertFalse(state(self.book.db)["initialized"])
        self.local()
        old = state(self.book.db)
        old_rows = indexed_rows(self.book, EXACT_TABLE)
        self.book.db.execute("BEGIN")
        project_tables(self.book.db, "outside", self.book.revision)
        self.assertEqual(state(self.book.db)["project"], "outside")
        self.book.db.execute("ROLLBACK")
        self.assertEqual(state(self.book.db), old)
        self.assertEqual(indexed_rows(self.book, EXACT_TABLE), old_rows)
        self.local()
        self.assertEqual(state(self.book.db), old)

    def test_failed_rebuild_preserves_active_pair_even_before_outer_rollback(self):
        self.seed()
        self.local()
        old = state(self.book.db)
        old_rows = indexed_rows(self.book, EXACT_TABLE)
        denied = []

        def authorize(action, name, *_):
            if action == sqlite3.SQLITE_INSERT and name == STEM_TABLE:
                denied.append(name)
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.book.db.execute("BEGIN")
        self.book.db.set_authorizer(authorize)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                project_tables(self.book.db, "outside", self.book.revision)
        finally:
            self.book.db.set_authorizer(None)
        self.assertTrue(denied)
        self.assertTrue(self.book.db.in_transaction)
        self.assertEqual(state(self.book.db), old)
        self.assertEqual(indexed_rows(self.book, EXACT_TABLE), old_rows)
        self.book.db.execute("ROLLBACK")

    def test_partial_scopes_keep_whole_project_statistics_and_body_requirement(self):
        sources = [record("wanted", "a", "Alpha alpha beta.", task="one"),
                   record("wanted", "b", "Alpha beta beta.", task="two"),
                   record("wanted", "c", "Gamma only.", task="three", title="Nebulous")]
        with MemoryBook(":memory:") as isolated:
            chapters = []
            for source in sources:
                chapters.append(self.book.ingest(source)["chapter_id"])
                isolated.ingest(source)
            self.book.ingest(record("outside", "a", "Alpha beta.", task="one"))
            for options in ({"chapter": chapters[0]}, {"session": "b"},
                            {"chapter": chapters[0], "session": "b"}):
                self.assertEqual(comparable(self.local(**options)), comparable(
                    isolated.recall("alpha beta", project="wanted", use_cache=False, **options)))
                self.assertEqual(state(self.book.db)["page_count"], 3)
            self.assertEqual(self.local("nebulous")["results"], [])

    def test_coverage_uses_the_same_local_pair(self):
        self.book.ingest(record("wanted", "a", "Alpha sensor is stable."))
        self.book.ingest(record("wanted", "b", "Beta pressure is steady."))
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            response = self.local("alpha sensor and beta pressure", coverage=True, limit=2)
        finally:
            self.book.db.set_trace_callback(None)
        self.assertEqual({ref["session_id"] for hit in response["results"] for ref in hit["source_refs"]}, {"a", "b"})
        queries = [sql for sql in statements if "bm25(" in sql and not sql.startswith("--")]
        self.assertGreaterEqual(len(queries), 6)
        self.assertTrue(all(f"bm25({EXACT_TABLE}," in sql or f"bm25({STEM_TABLE}," in sql for sql in queries))
        self.assertTrue(any("+rowid IN" in sql for sql in queries))

    def test_result_cache_identity_and_temp_state_are_connection_local(self):
        self.seed()
        ordinary = self.book.recall("alpha beta", project="wanted")
        local = self.book.recall("alpha beta", project="wanted", project_local_fts_statistics=True)
        self.assertFalse(ordinary["cache_hit"])
        self.assertFalse(local["cache_hit"])
        self.assertEqual(self.book.stats()["cache_entries"], 2)
        self.assertTrue(self.book.recall("alpha beta", project="wanted")["cache_hit"])
        self.assertTrue(self.book.recall("alpha beta", project="wanted", project_local_fts_statistics=True)["cache_hit"])
        before = state(self.book.db)
        with MemoryBook(self.path) as other:
            self.assertFalse(state(other.db)["initialized"])
            from_cache = other.recall("alpha beta", project="wanted", project_local_fts_statistics=True)
            self.assertTrue(from_cache["cache_hit"])
            self.assertTrue(from_cache["project_local_fts_statistics"])
            self.assertFalse(state(other.db)["initialized"])
            other.recall("gamma", project="outside", use_cache=False, project_local_fts_statistics=True)
            self.assertEqual(state(other.db)["project"], "outside")
        self.assertEqual(state(self.book.db), before)

    def test_opt_in_preserves_source_schema_and_existing_semantic_vectors(self):
        from tests.test_semantic import FixtureEncoder
        self.seed()
        self.book.semantic_model_dir = Path(self.directory.name)
        self.book._semantic_model = FixtureEncoder()
        self.book.build_semantic_index()
        tables = ("meta", "pages", "pages_fts", "pages_stem_fts", "sessions",
                  "semantic_meta", "semantic_vectors")
        before = {table: [tuple(row) for row in self.book.db.execute(f"SELECT * FROM {table} ORDER BY 1")]
                  for table in tables}
        schema = [tuple(row) for row in self.book.db.execute("SELECT name,sql FROM main.sqlite_master ORDER BY name")]
        with patch.object(self.book._semantic_model, "encode_pages", side_effect=AssertionError("must reuse vectors")), \
                patch("memory_book.semantic.rank_pages", return_value=[]):
            ordinary = self.book.recall("alpha beta", project="wanted", semantic=True)
            scoped = self.book.recall("alpha beta", project="wanted", semantic=True,
                                       project_local_fts_statistics=True)
            self.assertFalse(ordinary["cache_hit"])
            self.assertFalse(scoped["cache_hit"])
            self.assertTrue(scoped["semantic"])
            self.assertTrue(self.book.recall("alpha beta", project="wanted", semantic=True,
                                             project_local_fts_statistics=True)["cache_hit"])
        self.assertEqual({table: [tuple(row) for row in self.book.db.execute(f"SELECT * FROM {table} ORDER BY 1")]
                          for table in tables}, before)
        self.assertEqual([tuple(row) for row in self.book.db.execute("SELECT name,sql FROM main.sqlite_master ORDER BY name")], schema)


if __name__ == "__main__":
    unittest.main()
