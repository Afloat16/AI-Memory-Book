"""Invented archive fixtures for bounded revision-scoped index feature reuse.

These are correctness and retained-size checks, not timing measurements. Raw
FTS rows are used only to isolate the pure indexed-body/highlight helpers;
archive lifecycle tests use supported MemoryBook mutations.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from collections import OrderedDict
from pathlib import Path
from unittest.mock import patch

from memory_book import store
from memory_book.store import MemoryBook


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None
BODY_READ = re.compile(r"SELECT\s+rowid\s*,\s*body\s+FROM\s+pages_fts", re.I)


def session(identity, text, *, project="feature-fixture", stamp="2026-11-13T00:00:00Z"):
    return {"project": project, "session_id": identity, "task_id": "pressure-task",
            "created_at": stamp, "messages": [{"role": "user", "content": text}]}


def stable(response):
    return {key: value for key, value in response.items() if key != "latency_ms"}


def direct_features(book, ids):
    if not ids:
        return {}
    rows = book.db.execute("SELECT rowid,body FROM pages_fts WHERE rowid IN (" +
                           ",".join("?" for _ in ids) + ")", ids)
    return {row["rowid"]: frozenset(row["body"].split()) for row in rows}


def snapshot_features(book, ids):
    book.db.execute("BEGIN")
    try:
        revision = book.revision
        result = book._indexed_body_terms(ids, revision)
        book.db.execute("COMMIT")
        return result
    except BaseException:
        book.db.execute("ROLLBACK")
        raise


class FeatureFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "archive.db"
        self.book = MemoryBook(self.path, cache_size=8, min_page_chars=0)
        self.addCleanup(self.book.close)

    def add_bodies(self, values):
        self.book.db.executemany(
            "INSERT INTO pages_fts(rowid,title,question,body,directory) VALUES(?,'','',?,'')",
            values)

    def rids(self, project=None):
        if project is None:
            return [row[0] for row in self.book.db.execute("SELECT rid FROM pages ORDER BY rid")]
        return [row[0] for row in self.book.db.execute(
            "SELECT rid FROM pages WHERE project_id=? ORDER BY rid", (project,))]

    def assert_cache_bound(self, book=None):
        book = self.book if book is None else book
        cache = book._body_token_cache
        self.assertIsInstance(cache, OrderedDict)
        self.assertLessEqual(len(cache), store.BODY_TOKEN_CACHE_ENTRIES)
        self.assertEqual(book._body_token_cache_bytes, sum(value[1] for value in cache.values()))
        accounted = book._body_token_cache_bytes + sys.getsizeof(cache)
        self.assertLessEqual(accounted, store.BODY_TOKEN_CACHE_BYTES)
        actual = sys.getsizeof(cache)
        for rid, entry in cache.items():
            words, cost = entry
            self.assertIsInstance(words, frozenset)
            retained = (sys.getsizeof(rid) + sys.getsizeof(entry) + sys.getsizeof(cost) +
                        sys.getsizeof(words) + sum(sys.getsizeof(word) for word in words))
            self.assertLessEqual(retained, cost)
            actual += retained
        self.assertLessEqual(actual, accounted)


class IndexedBodyFeatureTests(FeatureFixture):
    def test_cold_warm_and_only_missing_rows_preserve_exact_features(self):
        bodies = {1: "alpha alpha beta", 2: "缓存\t线程\nalpha\u00a0beta",
                  3: "combining e\u0301 emoji 👩🏽‍💻"}
        self.add_bodies(bodies.items())
        expected = {rid: frozenset(body.split()) for rid, body in bodies.items()}
        trace = []
        self.book.db.set_trace_callback(trace.append)
        self.addCleanup(self.book.db.set_trace_callback, None)
        self.assertEqual(snapshot_features(self.book, [1, 2]), {rid: expected[rid] for rid in (1, 2)})
        self.assertEqual(len([sql for sql in trace if BODY_READ.search(sql)]), 1)
        trace.clear()
        self.assertEqual(snapshot_features(self.book, [2, 1, 2]), {rid: expected[rid] for rid in (1, 2)})
        self.assertFalse([sql for sql in trace if BODY_READ.search(sql)])
        trace.clear()
        self.assertEqual(snapshot_features(self.book, [2, 3]), {rid: expected[rid] for rid in (2, 3)})
        reads = [sql for sql in trace if BODY_READ.search(sql)]
        self.assertEqual(len(reads), 1)
        self.assertRegex(reads[0], r"IN\s*\(\s*3\s*\)")
        self.assertEqual(snapshot_features(self.book, [999]), {})
        self.assertNotIn(999, self.book._body_token_cache)
        self.assert_cache_bound()

    def test_accounting_bounds_actual_ascii_unicode_and_distinct_token_objects(self):
        self.assertEqual(store.BODY_TOKEN_CACHE_ENTRIES, 256)
        self.assertEqual(store.BODY_TOKEN_CACHE_BYTES, 2 * 1024 * 1024)
        bodies = ["alpha beta alpha " * 100, "缓存 线程 布局 漢字 " * 100,
                  "e\u0301 a\u0308 😀 👩🏽‍💻 𠮷 " * 100,
                  " ".join(f"distinct_{index:04d}" for index in range(400)),
                  "prefix\r\n\v\f\t\u001c\u0085\u2003suffix"]
        self.add_bodies(enumerate(bodies, 1))
        actual = snapshot_features(self.book, list(range(1, len(bodies) + 1)))
        self.assertEqual(actual, {rid: frozenset(body.split()) for rid, body in enumerate(bodies, 1)})
        self.assertEqual(len(self.book._body_token_cache), len(bodies))
        self.assert_cache_bound()

    def test_entry_limit_eviction_and_hit_recency_do_not_change_returned_features(self):
        self.add_bodies((rid, f"shared token{rid}") for rid in range(1, 6))
        with patch.object(store, "BODY_TOKEN_CACHE_ENTRIES", 3):
            for rid in (1, 2, 3, 1, 4):
                self.assertEqual(snapshot_features(self.book, [rid]), direct_features(self.book, [rid]))
                self.assert_cache_bound()
            self.assertEqual(list(self.book._body_token_cache), [3, 1, 4])
            self.assertEqual(snapshot_features(self.book, [2]), direct_features(self.book, [2]))
            self.assertEqual(list(self.book._body_token_cache), [1, 4, 2])
            self.assert_cache_bound()

    def test_byte_limit_applies_independently_of_entry_limit(self):
        self.add_bodies((rid, " ".join(f"term{rid}_{index}" for index in range(12))) for rid in range(1, 11))
        with patch.object(store, "BODY_TOKEN_CACHE_BYTES", 5000):
            for rid in range(1, 11):
                self.assertEqual(snapshot_features(self.book, [rid]), direct_features(self.book, [rid]))
                self.assert_cache_bound()
            self.assertGreater(len(self.book._body_token_cache), 0)
            self.assertLess(len(self.book._body_token_cache), 10)

    def test_empty_and_oversized_bodies_are_returned_but_not_retained(self):
        bodies = {1: "", 2: " \t\n", 3: "oversized " * 1000, 4: "small token"}
        self.add_bodies(bodies.items())
        with patch.object(store, "BODY_TOKEN_CACHE_BYTES", 4096):
            actual = snapshot_features(self.book, list(bodies))
            self.assertEqual(actual, {rid: frozenset(body.split()) for rid, body in bodies.items()})
            self.assertEqual(set(self.book._body_token_cache), {4})
            self.assert_cache_bound()

    def test_disabled_retention_uses_current_features_and_keeps_no_entries(self):
        self.add_bodies([(1, "alpha beta"), (2, "beta gamma")])
        with patch.object(store, "BODY_TOKEN_CACHE_ENTRIES", 0):
            self.assertEqual(snapshot_features(self.book, [1, 2]), direct_features(self.book, [1, 2]))
            self.assertFalse(self.book._body_token_cache)
            self.assertEqual(self.book._body_token_cache_bytes, 0)

    def test_clear_and_close_release_connection_local_features(self):
        self.book.ingest(session("one", "Pressure is 82 and retry is 45."))
        ids = self.rids()
        snapshot_features(self.book, ids)
        with MemoryBook(self.path, cache_size=0) as another:
            self.assertFalse(another._body_token_cache)
            self.assertIsNot(another._body_token_cache, self.book._body_token_cache)
            snapshot_features(another, ids)
            self.book._clear_body_token_cache()
            self.assertFalse(self.book._body_token_cache)
            self.assertEqual(self.book._body_token_cache_bytes, 0)
            self.assertIsNone(self.book._body_token_cache_revision)
            self.assertTrue(another._body_token_cache)
        self.assertFalse(another._body_token_cache)
        self.assertEqual(another._body_token_cache_bytes, 0)
        self.assertIsNone(another._body_token_cache_revision)
        snapshot_features(self.book, ids)
        self.book.close()
        self.assertFalse(self.book._body_token_cache)
        self.assertEqual(self.book._body_token_cache_bytes, 0)
        self.assertIsNone(self.book._body_token_cache_revision)


class RevisionAndPayloadTests(FeatureFixture):
    def test_same_and_other_connection_mutations_invalidate_reused_rids(self):
        self.book.ingest(session("one", "Original alpha pressure."))
        ids = self.rids()
        self.assertEqual(len(ids), 1)
        before = snapshot_features(self.book, ids)
        old_revision = self.book.revision
        self.book.delete_project("feature-fixture")
        self.book.ingest(session("two", "Replacement beta retry."))
        self.assertEqual(self.rids(), ids)
        current = snapshot_features(self.book, ids)
        self.assertNotEqual(before, current)
        self.assertEqual(current, direct_features(self.book, ids))
        self.assertGreater(self.book.revision, old_revision)
        with MemoryBook(self.path, cache_size=0) as writer:
            writer.delete_project("feature-fixture")
            writer.ingest(session("three", "External gamma duration."))
        self.assertEqual(self.rids(), ids)
        newest = snapshot_features(self.book, ids)
        self.assertNotEqual(current, newest)
        self.assertEqual(newest, direct_features(self.book, ids))
        self.assertEqual(self.book._body_token_cache_revision, self.book.revision)

    def test_external_writer_during_read_snapshot_keeps_old_hits_and_misses(self):
        self.book.ingest(session("one", "Original pressure alpha."))
        ids = self.rids()
        expected = snapshot_features(self.book, ids)
        with MemoryBook(self.path, cache_size=0) as writer:
            self.book.db.execute("BEGIN")
            revision = self.book.revision
            try:
                writer.ingest(session("one", "Updated pressure beta."))
                self.assertEqual(self.book._indexed_body_terms(ids, revision), expected)
                self.book._clear_body_token_cache()
                self.assertEqual(self.book._indexed_body_terms(ids, revision), expected)
            finally:
                self.book.db.execute("ROLLBACK")
        after = snapshot_features(self.book, self.rids())
        self.assertNotEqual(after, expected)
        self.assertEqual(after, direct_features(self.book, self.rids()))

    def test_failed_api_write_rolls_back_source_and_revision_without_poisoning_features(self):
        self.book.ingest(session("one", "Original pressure alpha."))
        ids = self.rids()
        before = snapshot_features(self.book, ids)
        revision = self.book.revision
        changed = self.book._changed

        def abort_after_revision_update():
            changed()
            raise RuntimeError("invented post-update failure")

        with patch.object(self.book, "_changed", side_effect=abort_after_revision_update):
            with self.assertRaisesRegex(RuntimeError, "invented"):
                self.book.ingest(session("one", "Uncommitted pressure beta."))
        self.assertFalse(self.book.db.in_transaction)
        self.assertEqual(self.book.revision, revision)
        self.assertEqual(snapshot_features(self.book, ids), before)
        self.assertEqual(direct_features(self.book, ids), before)

    def test_revision_change_clears_features_even_when_ranking_does_not_use_them(self):
        variants = ({"query": ""}, {"query": "pressure retry", "budget_chars": 0},
                    {"query": "pressure retry", "strategy": "flat"}, {"query": "pressure"})
        for index, options in enumerate(variants):
            with self.subTest(options=options):
                self.book.ingest(session("one", f"Pressure retry before change {index}."))
                snapshot_features(self.book, self.rids())
                self.assertTrue(self.book._body_token_cache)
                self.book.delete_project("feature-fixture")
                self.book.recall(project="feature-fixture", use_cache=False, **options)
                self.assertFalse(self.book._body_token_cache)
                self.assertEqual(self.book._body_token_cache_bytes, 0)
                self.assertIn(self.book._body_token_cache_revision, (None, self.book.revision))

    def test_current_revision_result_cache_hit_also_discards_old_source_features(self):
        query = "pressure retry"
        self.book.ingest(session("one", "Pressure is 82; retry is 45."))
        snapshot_features(self.book, self.rids())
        old_revision = self.book.revision
        with MemoryBook(self.path, cache_size=8) as writer:
            writer.ingest(session("one", "Pressure is 93; retry is 60."))
            writer.recall(query, project="feature-fixture", use_cache=True)
        result = self.book.recall(query, project="feature-fixture", use_cache=True)
        self.assertTrue(result["cache_hit"])
        self.assertGreater(result["revision"], old_revision)
        self.assertFalse(self.book._body_token_cache)
        self.assertEqual(self.book._body_token_cache_bytes, 0)

    def test_result_cache_writes_and_deletes_leave_same_revision_features_reusable(self):
        self.book.ingest(session("one", "Pressure is 82; retry is 45."))
        self.book.recall("pressure retry", project="feature-fixture", use_cache=True)
        retained = dict(self.book._body_token_cache)
        self.assertTrue(retained)
        revision = self.book.revision
        self.book.db.execute("DELETE FROM recall_cache")
        trace = []
        self.book.db.set_trace_callback(trace.append)
        try:
            result = self.book.recall("pressure retry", project="feature-fixture", use_cache=True)
        finally:
            self.book.db.set_trace_callback(None)
        self.assertFalse(result["cache_hit"])
        self.assertEqual(self.book.revision, revision)
        self.assertFalse([sql for sql in trace if BODY_READ.search(sql)])
        for rid, (words, _) in retained.items():
            self.assertIs(self.book._body_token_cache[rid][0], words)

    def test_complete_payload_matches_disabled_cold_warm_and_evicted_features(self):
        self.book.ingest(session("earlier", "Pressure is 82; retry is 45.", stamp="2025-01-01T00:00:00Z"))
        self.book.ingest(session("current", "Pressure is 93; retry is 60."))
        for index in range(5):
            self.book.ingest(session(str(index), f"Unrelated pressure retry {index}.", project=f"other-{index}"))
        evicting = self.rids("other-0") + self.rids("other-1") + self.rids("other-2")
        query = "latest pressure retry"
        with patch.object(store, "BODY_TOKEN_CACHE_ENTRIES", 0):
            self.book._clear_body_token_cache()
            expected = stable(self.book.recall(query, project="feature-fixture", use_cache=False))
            self.assertFalse(self.book._body_token_cache)
        with patch.object(store, "BODY_TOKEN_CACHE_ENTRIES", 2):
            self.book._clear_body_token_cache()
            for _ in range(2):
                self.assertEqual(stable(self.book.recall(query, project="feature-fixture", use_cache=False)), expected)
            snapshot_features(self.book, evicting)
            self.assertFalse(set(self.rids("feature-fixture")) & set(self.book._body_token_cache))
            self.assertEqual(stable(self.book.recall(query, project="feature-fixture", use_cache=False)), expected)
            self.assert_cache_bound()

    def test_recall_uses_one_snapshot_when_writer_commits_at_feature_read(self):
        self.book.ingest(session("one", "Pressure is 82; retry is 45."))
        query = "pressure retry"
        expected = stable(self.book.recall(query, project="feature-fixture", use_cache=False))
        original = self.book._indexed_body_terms
        with MemoryBook(self.path, cache_size=0) as writer:
            def change_then_read(ids, revision):
                self.assertTrue(self.book.db.in_transaction)
                writer.ingest(session("one", "Pressure is 93; retry is 60."))
                return original(ids, revision)
            with patch.object(self.book, "_indexed_body_terms", side_effect=change_then_read):
                actual = stable(self.book.recall(query, project="feature-fixture", use_cache=False))
        self.assertEqual(actual, expected)
        following = stable(self.book.recall(query, project="feature-fixture", use_cache=False))
        self.assertGreater(following["revision"], expected["revision"])
        self.assertIn("93", following["context"])

    @unittest.skipUnless(HAS_TOKENS, "requires the optional exact tokenizer")
    def test_warm_features_do_not_hide_source_coordinate_corruption(self):
        self.book.ingest(session("one", "Pressure is 82; retry is 45."))
        self.book.recall("pressure retry", project="feature-fixture", budget_tokens=1024, use_cache=False)
        self.assertTrue(self.book._body_token_cache)
        self.book.db.execute("UPDATE pages SET content=replace(content,'82','93')")
        with self.assertRaisesRegex(ValueError, "Page source coordinates"):
            self.book.recall("pressure retry", project="feature-fixture", budget_tokens=1024, use_cache=False)


class HighlightWhitelistTests(FeatureFixture):
    def test_highlight_bytes_match_original_query_across_guard_boundaries(self):
        rows = [(1, "run", "walking only"), (2, "", "running swiftly"),
                (3, "", "running unselected"), (4, "", "run and running"),
                (256, "", "running boundary"), (257, "", "running wider"),
                (700, "", "running far away")]
        self.book.db.executemany(
            "INSERT INTO pages_stem_fts(rowid,title,question,body,directory) VALUES(?,?,'',?,'')", rows)
        expression = '("run") AND body : ("run")'
        for ids in ([2], [2, 4], [2, 256], [1, 256], [1, 257], [2, 700], [255, 256], [2, 2]):
            with self.subTest(ids=ids):
                original = self.book.db.execute(
                    "SELECT rowid,highlight(pages_stem_fts,2,?,?) body FROM pages_stem_fts "
                    "WHERE pages_stem_fts MATCH ? AND rowid IN (" + ",".join("?" for _ in ids) + ")",
                    ["\x01", "\x02", expression, *ids]).fetchall()
                trace = []
                self.book.db.set_trace_callback(trace.append)
                try:
                    actual = self.book._highlighted_bodies(expression, ids)
                finally:
                    self.book.db.set_trace_callback(None)
                self.assertEqual({row["rowid"]: row["body"] for row in actual},
                                 {row["rowid"]: row["body"] for row in original})
                self.assertTrue(all(row["rowid"] in ids for row in actual))
                query = next(sql for sql in trace if "highlight(pages_stem_fts" in sql)
                bounded = len(ids) > 1 and max(ids) - min(ids) + 1 <= 256
                self.assertEqual("BETWEEN" in query, bounded)
                self.assertEqual("+rowid" in query, bounded)
        stem_only = self.book._highlighted_bodies(expression, [2])
        self.assertEqual(stem_only[0]["body"], "\x01running\x02 swiftly")

    def test_empty_highlight_selection_does_not_read_source(self):
        trace = []
        self.book.db.set_trace_callback(trace.append)
        try:
            self.assertEqual(self.book._highlighted_bodies('"run"', []), [])
        finally:
            self.book.db.set_trace_callback(None)
        self.assertEqual(trace, [])


if __name__ == "__main__":
    unittest.main()
