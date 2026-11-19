"""Project-local ranks preserve source identity and disclose bounded fallbacks."""

from __future__ import annotations

import copy
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.project_index import CACHE_PROJECT_LIMIT, PAGE_LIMIT


def source(project, number, *, answer=None, turns=1):
    text = answer or ("Production lease_duration=12. boundary_guard=stable. target_phrase. 租约时长=12。"
                      if project == "target" else "Production lease_duration=99. foreign_phrase. " * 3)
    return {"project": project, "project_name": "Shared worker project",
            "session_id": f"session-{number}", "task_id": f"task-{number % 3}",
            "task_title": "Worker lease policy 租约策略", "title": "Worker lease policy 租约策略",
            "created_at": "2016-02-01T00:00:00Z",
            "messages": [message for _ in range(turns) for message in (
                {"role": "user", "content": "What is the production lease_duration and boundary policy?"},
                {"role": "assistant", "content": text})]}


def stable(response, *, revision=False):
    value = copy.deepcopy(response)
    for key in ("latency_ms", "ranking_scope", "cache_hit"):
        value.pop(key, None)
    if not revision:
        value.pop("revision", None)
    return value


@unittest.skipUnless(hasattr(sqlite3.Connection, "getlimit"), "project route needs inspected SQLite limits")
class ProjectLocalRankingTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", ranking_scope="project")
        self.addCleanup(self.book.close)
        for number in range(8):
            self.book.ingest(source("target", number))
            self.book.ingest(source("foreign", number))

    def test_explicit_mode_preserves_isolated_corpus_payloads_and_original_offsets(self):
        # Independently ingested target-only archive is the intended ranking
        # oracle, not the globally scored archive with unrelated documents.
        with MemoryBook(":memory:", segmentation="turn") as isolated:
            for number in range(8):
                isolated.ingest(source("target", number))
            chapter = self.book.db.execute(
                "SELECT id FROM chapters WHERE project_id='target' ORDER BY id LIMIT 1").fetchone()[0]
            for query in ("current production lease_duration", "original boundary policy",
                          "target_phrase", "租约策略", "unmatchedneedle"):
                for scope in ({"project": "target"}, {"project": "target", "chapter": chapter},
                              {"project": "target", "session": "session-0"}):
                    with self.subTest(query=query, scope=scope):
                        actual = self.book.recall(query, use_cache=False, **scope)
                        expected = isolated.recall(query, use_cache=False, **scope)
                        self.assertEqual(stable(actual), stable(expected))
                        self.assertEqual(actual["ranking_scope"]["actual"], "project")
                        for row in actual["results"]:
                            self.assertEqual(row["breadcrumb"][0]["id"], "target")
                            for ref in row["source_refs"]:
                                self.assertEqual(ref["project"], "target")
            for query in ("worker lease", "租约策略", "unmatchedneedle"):
                for options in ({"project": "target"}, {"project": "target", "chapter": chapter},
                                {"project": "target", "limit": 1, "offset": 1}):
                    self.assertEqual(stable(self.book.search_directory(query, **options)),
                                     stable(isolated.search_directory(query, **options)))

    def test_foreign_growth_keeps_scores_order_and_index_but_refreshes_revision(self):
        first = self.book.recall("current lease_duration", project="target")
        directory = self.book.search_directory("worker lease", project="target")
        local = self.book._project_indexes.entries["target"].book
        for number in range(8, 80):
            self.book.ingest(source("foreign", number))
        after = self.book.recall("current lease_duration", project="target")
        self.assertIs(self.book._project_indexes.entries["target"].book, local)
        self.assertEqual(stable(first), stable(after))
        self.assertGreater(after["revision"], first["revision"])
        self.assertTrue(after["ranking_scope"]["index_cache_hit"])
        self.assertTrue(after["ranking_scope"]["fingerprint_checked"])
        self.assertEqual(stable(directory), stable(self.book.search_directory("worker lease", project="target")))
        again = self.book.recall("current lease_duration", project="target")
        self.assertTrue(again["ranking_scope"]["index_cache_hit"])
        self.assertFalse(again["ranking_scope"]["fingerprint_checked"])

    def test_cross_connection_replacement_relink_and_delete_are_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive.db"
            with MemoryBook(path, segmentation="turn", ranking_scope="project") as reader, MemoryBook(
                    path, segmentation="turn") as writer:
                writer.ingest(source("target", 0))
                first = reader.recall("current lease_duration", project="target")
                old = reader._project_indexes.entries["target"].book
                writer.ingest(source("target", 0, answer="Production lease_duration=43. replacement_phrase."))
                replaced = reader.recall("current lease_duration", project="target")
                self.assertNotIn("lease_duration=12", replaced["context"])
                self.assertIn("lease_duration=43", replaced["context"])
                self.assertNotEqual(first["results"][0]["id"], replaced["results"][0]["id"])
                self.assertIsNot(reader._project_indexes.entries["target"].book, old)
                linked = writer.link_session("target", "session-0", "updated", "Updated policy")
                moved = reader.recall("lease_duration", project="target", chapter=linked["chapter_id"])
                self.assertIn("lease_duration=43", moved["context"])
                writer.delete_session("target", "session-0")
                empty = reader.recall("lease_duration", project="target")
                self.assertEqual(empty["context"], "")
                writer.delete_project("target")
                missing = reader.recall("lease_duration", project="target")
                self.assertEqual(missing["context"], "")
                self.assertEqual(missing["ranking_scope"]["fallback_reason"], "project_not_found")

    def test_direct_committed_source_changes_and_caller_rollback_cannot_stale_cache(self):
        first = self.book.search_directory("worker lease", project="target")
        entry = self.book._project_indexes.entries["target"]
        chapter = first["results"][0]["id"]
        self.book.db.execute("BEGIN")
        self.book.db.execute("UPDATE chapters SET summary='Uncommitted summary' WHERE id=?", (chapter,))
        transient = self.book.search_directory("worker lease", project="target")
        self.assertTrue(self.book.db.in_transaction)
        self.assertTrue(any(row["summary"] == "Uncommitted summary" for row in transient["results"]))
        self.assertIs(self.book._project_indexes.entries["target"], entry)
        self.book.db.execute("ROLLBACK")
        self.assertEqual(stable(first), stable(self.book.search_directory("worker lease", project="target")))
        self.book.db.execute("UPDATE chapters SET summary='Committed summary' WHERE id=?", (chapter,))
        committed = self.book.search_directory("worker lease", project="target")
        self.assertTrue(any(row["summary"] == "Committed summary" for row in committed["results"]))

    def test_directory_caller_snapshot_survives_an_external_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "archive.db"
            with MemoryBook(path, segmentation="turn", ranking_scope="project") as reader:
                reader.ingest(source("target", 0))
                expected = reader.search_directory("worker lease", project="target")
                reader.db.execute("BEGIN")
                reader.db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()
                with MemoryBook(path, segmentation="turn") as writer:
                    writer.ingest(source("target", 1))
                try:
                    snapshot = reader.search_directory("worker lease", project="target")
                    self.assertEqual(stable(snapshot, revision=True), stable(expected, revision=True))
                    self.assertTrue(reader.db.in_transaction)
                finally:
                    reader.db.execute("ROLLBACK")
                latest = reader.search_directory("worker lease", project="target")
                self.assertGreater(latest["revision"], expected["revision"])
                self.assertEqual(sum(row["matching_pages"] for row in latest["results"]), 2)

    def test_all_segmentation_modes_reuse_original_page_identity_and_turn_spans(self):
        for mode in ("adaptive", "turn", "session"):
            with self.subTest(mode=mode), MemoryBook(":memory:", segmentation=mode,
                    max_page_chars=300, min_page_chars=0, ranking_scope="project") as local, MemoryBook(
                    ":memory:", segmentation=mode, max_page_chars=300, min_page_chars=0) as oracle:
                for number in range(4):
                    payload = source("target", number, turns=4)
                    local.ingest(payload)
                    oracle.ingest(payload)
                    local.ingest(source("foreign", number, turns=4))
                for query in ("current production lease_duration", "original boundary policy", "租约时长"):
                    self.assertEqual(stable(local.recall(query, project="target", use_cache=False)),
                                     stable(oracle.recall(query, project="target", use_cache=False)))

    def test_page_boundary_uses_complete_scope_or_explicit_global_fallback(self):
        with MemoryBook(":memory:", segmentation="turn", cache_size=0, ranking_scope="project") as book:
            book.ingest(source("target", 0, turns=PAGE_LIMIT))
            exact = book.recall("lease_duration", project="target", temporal="relevance", use_cache=False)
            self.assertEqual(exact["ranking_scope"]["actual"], "project")
            book.ingest(source("target", 1))
            fallback = book.recall("lease_duration", project="target", temporal="relevance", use_cache=False)
            self.assertEqual(fallback["ranking_scope"]["actual"], "global")
            self.assertEqual(fallback["ranking_scope"]["fallback_reason"], "project_page_limit")
            self.assertTrue(fallback["warnings"])
            self.assertNotIn("target", book._project_indexes.entries)
            expected = book._recall("lease_duration", project="target", temporal="relevance", use_cache=False)
            fallback["warnings"] = []
            self.assertEqual(stable(fallback), stable(expected))

    def test_source_byte_limit_and_malformed_ownership_never_return_partial_projection(self):
        with patch("memory_book.project_index.PROJECT_BYTE_LIMIT", 64):
            response = self.book.recall("lease_duration", project="target")
            self.assertEqual(response["ranking_scope"]["fallback_reason"], "project_byte_limit")
        foreign_session = self.book.db.execute(
            "SELECT id FROM sessions WHERE project_id='foreign' LIMIT 1").fetchone()[0]
        page = self.book.db.execute("SELECT rid FROM pages WHERE project_id='target' LIMIT 1").fetchone()[0]
        self.book.db.execute("UPDATE pages SET session_pk=? WHERE rid=?", (foreign_session, page))
        response = self.book.search_directory("worker lease", project="target")
        self.assertEqual(response["ranking_scope"]["fallback_reason"], "inconsistent_project_ownership")
        self.assertEqual(sum(row["matching_pages"] for row in response["results"]), 7)

    def test_lru_is_bounded_and_close_releases_all_local_connections(self):
        local_books = []
        for number in range(CACHE_PROJECT_LIMIT + 2):
            project = f"project-{number}"
            self.book.ingest(source(project, 0))
            self.book.recall("lease_duration", project=project)
            local_books.append(self.book._project_indexes.entries[project].book)
            self.assertLessEqual(len(self.book._project_indexes.entries), CACHE_PROJECT_LIMIT)
        with self.assertRaises(sqlite3.ProgrammingError):
            local_books[0].db.execute("SELECT 1")
        self.book.close()
        for local in local_books:
            with self.assertRaises(sqlite3.ProgrammingError):
                local.db.execute("SELECT 1")

    def test_reduced_sqlite_limits_and_no_project_explicitly_fall_back(self):
        before = self.book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 64)
        try:
            response = self.book.recall("lease_duration", project="target")
            self.assertEqual(response["ranking_scope"]["fallback_reason"], "customized_sqlite_connection")
        finally:
            self.book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, before)
        response = self.book.recall("lease_duration")
        self.assertEqual(response["ranking_scope"]["fallback_reason"], "explicit_project_required")

    def test_local_cache_payloads_and_default_global_behavior_remain_independent(self):
        first = self.book.recall("lease_duration", project="target")
        second = self.book.recall("lease_duration", project="target")
        self.assertTrue(second["cache_hit"])
        second["results"][0]["source_refs"][0]["project"] = "corrupted"
        again = self.book.recall("lease_duration", project="target")
        self.assertEqual(stable(first), stable(again))
        self.assertEqual(self.book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0], 0)
        self.book.ranking_scope = "global"
        global_result = self.book.recall("lease_duration", project="target")
        self.assertNotIn("ranking_scope", global_result)
        self.assertFalse(global_result["cache_hit"])
        self.assertTrue(self.book.recall("lease_duration", project="target")["cache_hit"])

    def test_subclass_and_instance_reference_hooks_keep_the_original_instance(self):
        class CustomizedBook(MemoryBook):
            @staticmethod
            def _refs(row, spans):
                return [{**ref, "custom_scope_checked": True} for ref in MemoryBook._refs(row, spans)]

        for kind in ("subclass", "instance"):
            cls = CustomizedBook if kind == "subclass" else MemoryBook
            with self.subTest(kind=kind), cls(":memory:", segmentation="turn", ranking_scope="project") as book:
                book.ingest(source("target", 0))
                calls = []
                if kind == "instance":
                    ordinary = book._refs
                    def refs(row, spans):
                        calls.append(row["id"])
                        return [{**ref, "custom_scope_checked": True} for ref in ordinary(row, spans)]
                    book._refs = refs
                response = book.recall("lease_duration", project="target", use_cache=False)
                self.assertEqual(response["ranking_scope"]["fallback_reason"], "customized_memory_book")
                self.assertTrue(response["results"])
                self.assertTrue(all(ref["custom_scope_checked"] for hit in response["results"] for ref in hit["source_refs"]))
                self.assertFalse(book._project_indexes.entries)
                if kind == "instance":
                    self.assertTrue(calls)

    def test_hook_added_after_projection_cannot_be_bypassed_by_its_cached_response(self):
        self.book.recall("lease_duration", project="target")
        def reject(row, spans):
            raise PermissionError("custom source policy rejected this excerpt")
        with patch.object(self.book, "_refs", reject):
            with self.assertRaisesRegex(PermissionError, "custom source policy"):
                self.book.recall("lease_duration", project="target", use_cache=False)
        self.assertFalse(self.book.db.in_transaction)
        with patch.object(self.book, "_directory_tokens", wraps=self.book._directory_tokens):
            changed = self.book.recall("lease_duration", project="target", use_cache=False)
            self.assertEqual(changed["ranking_scope"]["fallback_reason"], "customized_memory_book")
            ordinary = self.book._recall("lease_duration", project="target", use_cache=False)
            changed["warnings"] = ordinary["warnings"]
            self.assertEqual(stable(changed), stable(ordinary))

    def test_mutable_cache_size_is_honored_without_rebuilding_project_rows(self):
        self.book.recall("lease_duration", project="target")
        self.assertTrue(self.book.recall("lease_duration", project="target")["cache_hit"])
        local = self.book._project_indexes.entries["target"].book
        self.book.cache_size = 0
        disabled = self.book.recall("lease_duration", project="target")
        self.assertFalse(disabled["cache_hit"])
        self.assertEqual(local.cache_size, 0)
        self.assertIs(self.book._project_indexes.entries["target"].book, local)
        self.assertFalse(disabled["ranking_scope"]["fingerprint_checked"])
        self.book.cache_size = 2
        for query in ("boundary_guard", "target_phrase", "unknown_needle"):
            self.book.recall(query, project="target")
        self.assertEqual(local.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0], 2)
        self.assertTrue(self.book.recall("unknown_needle", project="target")["cache_hit"])
        self.assertIs(self.book._project_indexes.entries["target"].book, local)

    def test_close_failure_still_releases_every_other_local_and_parent_connection(self):
        for project in ("target", "foreign"):
            self.book.recall("lease_duration", project=project)
        entries = list(self.book._project_indexes.entries.values())
        def fail(message):
            raise RuntimeError(message)
        for index, entry in enumerate(entries):
            entry.book._directory_tokens = SimpleNamespace(cache_clear=lambda index=index: fail(f"cleanup-{index}"))
        # Entries close in reverse LRU order. Both cleanup hooks fail, but all
        # SQLite connections are still closed and the first error survives.
        with self.assertRaisesRegex(RuntimeError, "cleanup-1"):
            self.book.close()
        self.assertFalse(self.book._project_indexes.entries)
        for book in (self.book, *(entry.book for entry in entries)):
            with self.assertRaises(sqlite3.ProgrammingError):
                book.db.execute("SELECT 1")

    def test_replacement_cleanup_failure_keeps_new_projection_owned_for_later_close(self):
        self.book.recall("lease_duration", project="target")
        old = self.book._project_indexes.entries["target"].book
        def fail():
            raise RuntimeError("retired projection cleanup")
        old._directory_tokens = SimpleNamespace(cache_clear=fail)
        self.book.ingest(source("target", 0, answer="Production lease_duration=43. replacement_phrase."))
        with self.assertRaisesRegex(RuntimeError, "retired projection cleanup"):
            self.book.recall("replacement_phrase", project="target")
        replacement = self.book._project_indexes.entries["target"].book
        self.assertIsNot(replacement, old)
        self.assertEqual(replacement.db.execute("SELECT 1").fetchone()[0], 1)
        self.assertIn("replacement_phrase", self.book.recall("replacement_phrase", project="target")["context"])
        self.book.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            replacement.db.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
