"""Small interleaved scopes retain global scores, ownership and cache contracts."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook


HAS_INSPECTED_LIMITS = (sqlite3.sqlite_version_info >= (3, 25, 0)
                        and hasattr(sqlite3.Connection, "getlimit"))


def source(project, number, *, turns=1):
    answer = ("Production lease_duration=12. boundary_guard=stable. target_phrase. 原始约束，租约时长=12。"
              if project == "target" else
              "Production lease_duration=99. This belongs to a different exact project. " * 3)
    return {"project": project, "project_name": "Shared worker project",
            "session_id": f"session-{number}", "task_id": f"task-{number % 3}",
            "task_title": "Worker lease policy 租约策略", "title": "Worker lease policy 租约策略",
            "created_at": "2026-02-01T00:00:00Z",
            "messages": [message for _ in range(turns) for message in (
                {"role": "user", "content": "What is the production lease_duration and boundary policy?"},
                {"role": "assistant", "content": answer})]}


def stable(response):
    return {key: value for key, value in response.items() if key != "latency_ms"}


class SparseProjectMembershipTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn")
        self.addCleanup(self.book.close)
        for number in range(64):
            if number % 8 == 0:
                self.book.ingest(source("target", number // 8))
            self.book.ingest(source("foreign", number))
        self.chapters = [row[0] for row in self.book.db.execute(
            "SELECT id FROM chapters WHERE project_id='target' ORDER BY id")]

    def equivalent(self, operation):
        actual = operation()
        with patch.object(self.book, "_small_project_rowids", return_value=None):
            expected = operation()
        self.assertEqual(stable(actual), stable(expected))
        self.assertEqual(json.dumps(stable(actual), ensure_ascii=False),
                         json.dumps(stable(expected), ensure_ascii=False))
        return actual

    def test_all_global_bm25_scores_sources_and_directory_pagination_are_preserved(self):
        self.assertIsNone(self.book._project_rowid_bounds("target"))
        for query in ("current production lease_duration", "original lease policy",
                      "target_phrase", "租约策略", "unmatchedneedle"):
            for scope in ({"project": "target"}, {"project": "target", "chapter": self.chapters[0]},
                          {"project": "target", "session": "session-0"},
                          {"project": "missing"}, {}):
                with self.subTest(query=query, scope=scope):
                    self.equivalent(lambda: self.book.recall(query, use_cache=False, **scope))
        for query in ("worker lease", "租约策略", "the and is", "unmatchedneedle"):
            for options in ({"project": "target"}, {"project": "target", "chapter": self.chapters[0]},
                            {"project": "target", "limit": 1, "offset": 1},
                            {"project": "target", "limit": 1, "offset": 3},
                            {"project": "target", "limit": 1, "offset": 10}, {}):
                with self.subTest(query=query, options=options):
                    self.equivalent(lambda: self.book.search_directory(query, **options))

    @unittest.skipUnless(HAS_INSPECTED_LIMITS, "optional inspected SQLite limits")
    def test_one_fts_cursor_retains_global_statistics_instead_of_point_queries(self):
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            self.book.search_directory("worker lease", project="target")
            self.book.recall("original production lease_duration", project="target", use_cache=False)
        finally:
            self.book.db.set_trace_callback(None)
        filtered = [statement for statement in statements
                    if "+pages_fts.rowid IN" in statement or "+pages_stem_fts.rowid IN" in statement]
        self.assertEqual(len(filtered), 3)  # Directory, exact recall, stem recall.
        for statement in filtered:
            plans = [row[3] for row in self.book.db.execute("EXPLAIN QUERY PLAN " + statement)]
            fts = [plan for plan in plans if "VIRTUAL TABLE INDEX" in plan and "M" in plan]
            self.assertEqual(len(fts), 1, plans)
            self.assertNotIn("=", fts[0], plans)
        self.assertFalse(any(statement.lstrip().upper().startswith(("CREATE", "ALTER", "DROP"))
                             for statement in statements))

    def test_same_membership_does_not_bypass_mixed_ownership_rejection(self):
        foreign_session = self.book.db.execute(
            "SELECT id FROM sessions WHERE project_id='foreign' LIMIT 1").fetchone()[0]
        target_page = self.book.db.execute(
            "SELECT rid FROM pages WHERE project_id='target' LIMIT 1").fetchone()[0]
        self.book.db.execute("BEGIN")
        try:
            self.book.db.execute("UPDATE pages SET session_pk=? WHERE rid=?", (foreign_session, target_page))
            response = self.equivalent(lambda: self.book.search_directory("worker lease", project="target"))
            self.assertEqual(sum(row["matching_pages"] for row in response["results"]), 7)
            self.assertTrue(self.book.db.in_transaction)
        finally:
            self.book.db.execute("ROLLBACK")

    def test_scope_cardinality_boundary_never_applies_a_partial_filter(self):
        for count in (256, 257):
            with self.subTest(count=count), MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
                book.ingest(source("foreign", 0))
                book.ingest(source("target", 0, turns=count))
                book.ingest(source("foreign", 1))
                self.assertIsNone(book._project_rowid_bounds("target"))
                membership = book._small_project_rowids("target")
                if count == 256 and HAS_INSPECTED_LIMITS:
                    self.assertEqual(len(membership), count)
                else:
                    self.assertIsNone(membership)
                actual = book.recall("lease_duration", project="target", temporal="relevance", use_cache=False)
                with patch.object(book, "_small_project_rowids", return_value=None):
                    expected = book.recall("lease_duration", project="target", temporal="relevance", use_cache=False)
                self.assertEqual(stable(actual), stable(expected))

    def test_all_segmentation_modes_keep_original_source_spans_and_global_ranks(self):
        for segmentation in ("adaptive", "turn", "session"):
            with self.subTest(segmentation=segmentation), MemoryBook(
                    ":memory:", segmentation=segmentation, max_page_chars=300, min_page_chars=0) as book:
                for number in range(8):
                    book.ingest(source("target", number, turns=4))
                    book.ingest(source("foreign", number, turns=4))
                self.assertIsNone(book._project_rowid_bounds("target"))
                for query in ("current production lease_duration", "original lease policy", "租约时长"):
                    actual = book.recall(query, project="target", use_cache=False)
                    with patch.object(book, "_small_project_rowids", return_value=None):
                        expected = book.recall(query, project="target", use_cache=False)
                    self.assertEqual(stable(actual), stable(expected))

    @unittest.skipUnless(HAS_INSPECTED_LIMITS, "getlimit/setlimit unavailable")
    def test_variable_headroom_reverts_to_the_original_complete_statement(self):
        with patch.object(self.book, "_small_project_rowids", return_value=None):
            expected_directory = self.book.search_directory("worker lease", project="target")
            expected_recall = self.book.recall("lease_duration", project="target",
                                             temporal="relevance", use_cache=False)
        for limit, operation, expected in (
            (12, lambda: self.book.search_directory("worker lease", project="target"), expected_directory),
            (9, lambda: self.book.recall("lease_duration", project="target",
                                        temporal="relevance", use_cache=False), expected_recall),
        ):
            prior = self.book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, limit)
            statements = []
            self.book.db.set_trace_callback(statements.append)
            try:
                actual = operation()
                self.assertEqual(stable(actual), stable(expected))
                self.assertFalse(any("+pages_fts.rowid IN" in sql or "+pages_stem_fts.rowid IN" in sql
                                     for sql in statements))
            finally:
                self.book.db.set_trace_callback(None)
                self.book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, prior)

    def test_custom_factories_retain_the_original_route(self):
        for attribute, factory in (("row_factory", lambda cursor, values: sqlite3.Row(cursor, values)),
                                   ("text_factory", lambda raw: raw.decode())):
            prior = getattr(self.book.db, attribute)
            try:
                setattr(self.book.db, attribute, factory)
                self.assertIsNone(self.book._small_project_rowids("target"))
                self.equivalent(lambda: self.book.search_directory("worker lease", project="target"))
                self.equivalent(lambda: self.book.recall("current production lease_duration",
                                                        project="target", use_cache=False))
            finally:
                setattr(self.book.db, attribute, prior)

    def test_warm_payload_mutation_and_validation_contracts_are_preserved(self):
        request = {"query": "current production lease_duration", "project": "target"}
        cold = self.book.recall(**request)
        warm = self.book.recall(**request)
        self.assertTrue(warm["cache_hit"])
        self.assertEqual(stable(warm), {**stable(cold), "cache_hit": True})
        warm["results"][0]["source_refs"][0]["project"] = "tampered-by-caller"
        warm["temporal"]["evidence_assessment"]["status"] = "tampered-by-caller"
        again = self.book.recall(**request)
        self.assertEqual(stable(again), {**stable(cold), "cache_hit": True})
        for invalid in ({"limit": 0}, {"budget_chars": -1}, {"temporal": "invalid"},
                        {"tokenizer": "invalid"}, {"project": ""}, {"semantic": True},
                        {"strategy": "flat", "coverage": True}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.book.recall(**{**request, **invalid})

    def test_membership_uses_one_snapshot_and_refreshes_after_external_ingest(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive.db"
            with MemoryBook(path, segmentation="turn") as reader:
                for number in range(8):
                    reader.ingest(source("target", number))
                    reader.ingest(source("foreign", number))
                expected = reader.search_directory("worker lease", project="target")
                reader.recall("current production lease_duration", project="target")
                self.assertTrue(reader.recall("current production lease_duration", project="target")["cache_hit"])
                reader.db.execute("BEGIN")
                reader.db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()
                with MemoryBook(path, segmentation="turn") as writer:
                    writer.ingest(source("target", 100))
                try:
                    self.assertEqual(reader.search_directory("worker lease", project="target"), expected)
                    self.assertTrue(reader.db.in_transaction)
                finally:
                    reader.db.execute("ROLLBACK")
                after = reader.search_directory("worker lease", project="target")
                self.assertGreater(after["revision"], expected["revision"])
                self.assertEqual(sum(row["matching_pages"] for row in after["results"]), 9)
                fresh = reader.recall("current production lease_duration", project="target")
                self.assertFalse(fresh["cache_hit"])
                uncached = reader.recall("current production lease_duration", project="target", use_cache=False)
                self.assertEqual(stable(fresh), stable(uncached))


if __name__ == "__main__":
    unittest.main()
