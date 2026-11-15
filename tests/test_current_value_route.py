"""Independent value-route, scope and source-integrity regressions.

These fixtures exercise fleet configuration and cache services. They import
no engineering workload, expected-answer table, scorer or external adapter.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store
from memory_book.store import _current_value_filter
from memory_book.text import query_terms


def source(identity, body, *, project="harbor", task="dispatch", question="Fleet handover",
           task_title="Fleet dispatch configuration", day="2026-01-01"):
    return {"project": project, "session_id": identity, "task_id": task,
            "title": question, "task_title": task_title, "created_at": day + "T09:00:00Z",
            "messages": [{"role": "user", "content": question},
                         {"role": "assistant", "content": body}]}


def sessions(result):
    return [hit["source_refs"][0]["session_id"] for hit in result["results"]]


class CurrentValueRouteTests(unittest.TestCase):
    def test_value_predicate_requires_exact_binding_and_actual_topic_anchor(self):
        eligible = _current_value_filter("What is the current lease.ttl for fleet dispatch?")
        self.assertTrue(eligible("Fleet handover: lease.ttl=45.", "Fleet dispatch configuration", "Handover"))
        self.assertFalse(eligible("lease.ttl=45.", "Fleet dispatch configuration", "Handover"))
        self.assertFalse(eligible("Fleet dispatch lease.ttl was inspected.", "Fleet dispatch configuration", "Handover"))
        self.assertFalse(eligible("Fleet dispatch archive.ttl=45; lease.ttl was inspected.", "Fleet dispatch configuration", "Handover"))
        self.assertFalse(eligible("Fleet dispatch lease.ttl == 45.", "Fleet dispatch configuration", "Handover"))
        self.assertFalse(eligible("Fleet dispatch lease_ttl=45.", "Fleet dispatch configuration", "Handover"))
        self.assertFalse(eligible("Fleet dispatch Lease.Ttl=45.", "Fleet dispatch configuration", "Handover"))

    def test_property_only_queries_keep_existing_evidence_ordering(self):
        for query, body in (("current lease.ttl", "Fleet lease.ttl=45."),
                            ("current queue capacity", "Queue capacity is now 16.")):
            with self.subTest(query=query):
                self.assertFalse(_current_value_filter(query)(body, "Fleet settings", "Handover"))

    def test_numeric_phrase_and_unpunctuated_assignment_have_the_same_topic_guard(self):
        self.assertTrue(_current_value_filter("current warehouse queue capacity")(
            "Warehouse: Queue capacity is now 16.", "Warehouse settings", "Handover"))
        self.assertTrue(_current_value_filter("current Redis timeout")(
            "Redis timeout=12.", "Cache settings", "Handover"))
        self.assertFalse(_current_value_filter("current Redis timeout")(
            "Memcache timeout=12.", "Redis and Memcache settings", "Handover"))

    def test_capitalized_and_quoted_subjects_cannot_be_borrowed_from_directory(self):
        directory = "Redis and Memcache service settings"
        for query in ("What is the current Redis service retry_limit?",
                      "What is the current `redis` service retry_limit?"):
            with self.subTest(query=query):
                eligible = _current_value_filter(query)
                self.assertFalse(eligible("Memcache service retry_limit=9.", directory, "Service handover"))
        self.assertTrue(_current_value_filter("What is the current Redis service retry_limit?")(
            "Redis service retry_limit=3.", directory, "Service handover"))
        self.assertFalse(_current_value_filter("What is the current Redis service retry_limit?")(
            "Redis service Retry_Limit=9.", directory, "Service handover"))

    def test_another_sentence_or_question_cannot_lend_its_subject_to_a_binding(self):
        directory = "Redis and Memcache service settings"
        for subject in ("Redis", "redis"):
            eligible = _current_value_filter(f"current {subject} service retry_limit")
            for body in (
                "Redis service audit finished. Memcache retry_limit=9.",
                "Memcache retry_limit=9. Redis service audit finished.",
                "Redis service audit finished\nMemcache retry_limit=9.",
                "USER: Redis service retry_limit?\n\nASSISTANT: Memcache retry_limit=9.",
            ):
                with self.subTest(subject=subject, body=body):
                    self.assertFalse(eligible(body, directory, "Service configuration"))
        eligible = _current_value_filter("current Redis service retry_limit")
        for separator in (";", "。", "；", "！", "？"):
            with self.subTest(separator=separator):
                self.assertFalse(eligible("Redis service audit finished" + separator + "Memcache service retry_limit=9.",
                                          directory, "Service configuration"))
        self.assertTrue(eligible("Redis service retry_limit=3; Memcache retry_limit=9.", directory, "Service configuration"))

    def test_bare_configuration_block_can_inherit_only_its_direct_topic_header(self):
        eligible = _current_value_filter("current queue worker lease.ttl")
        self.assertTrue(eligible("Queue worker configuration.\nlease.ttl=30.", "Queue worker settings", "Handover"))
        multiple = _current_value_filter("current queue worker lease.ttl and cache.size")
        self.assertTrue(multiple("Queue worker configuration.\nlease.ttl=30;\ncache.size=64;", "Queue worker settings", "Handover"))
        for body in (
            "Queue worker configuration.\n\nlease.ttl=30.",
            "Queue worker configuration.\n```ini\nlease.ttl=30.",
            "Queue worker configuration.\nASSISTANT: lease.ttl=30.",
            "USER: Queue worker configuration?\n\nASSISTANT: lease.ttl=30.",
            "Queue worker note; archive.ttl=9.\nlease.ttl=30.",
        ):
            with self.subTest(body=body):
                self.assertFalse(eligible(body, "Queue worker settings", "Handover"))
        for subject in ("Redis", "redis"):
            subject_filter = _current_value_filter(f"current {subject} service retry_limit")
            self.assertTrue(subject_filter("Redis service configuration.\nretry_limit=3.",
                                           "Redis and Memcache service settings", "Handover"))
            self.assertFalse(subject_filter("Redis service note; Memcache timeout=9.\nretry_limit=3.",
                                            "Redis and Memcache service settings", "Handover"))

    def test_partial_multiple_code_properties_keep_the_conservative_fallback(self):
        query = "current Redis retry_limit and Memcache cache_size"
        eligible = _current_value_filter(query)
        self.assertFalse(eligible("Redis retry_limit=3. Memcache cache_size was inspected.",
                                 "Redis and Memcache settings", "Service configuration"))
        self.assertTrue(eligible("Redis retry_limit=3. Memcache cache_size=96.",
                                "Redis and Memcache settings", "Service configuration"))

    def test_value_route_filters_before_96_candidate_limit_and_preserves_both_sources(self):
        query = "What is the current lease.ttl for fleet dispatch?"
        with MemoryBook(":memory:", cache_size=0) as book:
            book.ingest(source("original", "Fleet dispatch lease.ttl=30."))
            book.ingest(source("replacement", "Fleet lease.ttl=45. " +
                               "The handover requires a signed equipment manifest and a supervised transfer. " * 5,
                               day="2026-05-01"))
            for index in range(128):
                book.ingest(source(f"inspection-{index}",
                    f"Inspection {index}: " + "fleet dispatch lease.ttl inspected. " * 6,
                    day="2026-10-01"))
            tokens = " OR ".join('"' + token + '"' for token in query_terms(query))
            expression = f"({tokens}) AND body : ({tokens})"
            native = book.db.execute("""SELECT s.external_id FROM pages_fts
                JOIN pages p ON p.rid=pages_fts.rowid JOIN sessions s ON s.id=p.session_pk
                WHERE pages_fts MATCH ? AND p.project_id=?
                ORDER BY bm25(pages_fts,2.0,2.0,1.0,0.25),p.id LIMIT 96""", [expression, "harbor"])
            self.assertNotIn("replacement", [row[0] for row in native])
            result = book.recall(query, project="harbor", limit=5, budget_chars=4000, use_cache=False)
            self.assertIn("replacement", sessions(result))
            self.assertIn("original", sessions(result))
            # Different body topic sets are retained as distinct evidence,
            # not treated as one authoritative cross-source revision group.
            self.assertLess(sessions(result).index("original"), sessions(result).index("replacement"))
            self.assertLessEqual(result["candidate_count"], 288)
            self.assertLessEqual(result["context_chars"], 4000)
            for hit in result["results"]:
                page = book.read(hit["id"])
                self.assertEqual(hit["text"], page["content"])
                self.assertEqual(hit["source_refs"], page["source_refs"])

    def test_same_body_topics_and_property_still_order_actual_replacements(self):
        with MemoryBook(":memory:") as book:
            book.ingest(source("original", "Fleet dispatch lease.ttl=30."))
            book.ingest(source("replacement", "Fleet dispatch lease.ttl=45. "
                               "The operator signed the amended handover schedule.", day="2026-05-01"))
            for index in range(8):
                book.ingest(source(f"inspection-{index}",
                    f"Inspection {index}: " + "fleet dispatch lease.ttl inspected. " * 6, day="2026-10-01"))
            current = book.recall("current fleet dispatch lease.ttl", project="harbor", limit=1)
            self.assertEqual(sessions(current), ["replacement"])

    def test_memcache_value_cannot_replace_redis_value_with_shared_directory_words(self):
        with MemoryBook(":memory:") as book:
            directory = "Redis and Memcache service settings"
            book.ingest(source("redis", "Redis service retry_limit=3.", task_title=directory,
                               question="Service configuration"))
            book.ingest(source("memcache", "Memcache service retry_limit=9. "
                               "The new setting was written in the equipment handover manifest.",
                               task_title=directory, question="Service configuration", day="2026-11-01"))
            result = book.recall("What is the current Redis service retry_limit?", project="harbor", limit=1)
            self.assertEqual(sessions(result), ["redis"])

    def test_new_route_cannot_import_a_low_ranked_other_entity_assignment_as_a_revision(self):
        with MemoryBook(":memory:", max_page_chars=100000) as book:
            directory = "Redis and Memcache service settings"
            book.ingest(source("redis-value", "Redis service retry_limit=3. " +
                               "Redis service retry_limit. " * 20,
                               task_title=directory, question="Service configuration"))
            book.ingest(source("memcache-value", "Redis service audit finished. Memcache service retry_limit=9. " +
                               "Equipment manifest reviewed by operators during the handover. " * 50,
                               task_title=directory, question="Service configuration", day="2026-11-01"))
            for index in range(128):
                book.ingest(source(f"inspection-{index}",
                    f"Inspection {index}: " + "Redis service retry_limit inspected. " * 6,
                    task_title=directory, question="Service configuration", day="2026-10-01"))
            for subject in ("Redis", "redis"):
                query = f"current {subject} service retry_limit"
                tokens = " OR ".join('"' + token + '"' for token in query_terms(query))
                native = book.db.execute("""SELECT s.external_id FROM pages_fts
                    JOIN pages p ON p.rid=pages_fts.rowid JOIN sessions s ON s.id=p.session_pk
                    WHERE pages_fts MATCH ? AND p.project_id=?
                    ORDER BY bm25(pages_fts,2.0,2.0,1.0,0.25),p.id LIMIT 96""",
                    [f"({tokens}) AND body : ({tokens})", "harbor"])
                with self.subTest(subject=subject):
                    self.assertNotIn("memcache-value", [row[0] for row in native])
                    result = book.recall(query, project="harbor", limit=1)
                    self.assertEqual(sessions(result), ["redis-value"])

    def test_explicit_conjunction_preserves_the_other_requested_service(self):
        with MemoryBook(":memory:") as book:
            directory = "Redis and Memcache service settings"
            for index in range(6):
                book.ingest(source(f"redis-{index}", f"Redis timeout={index + 1}.", task_title=directory,
                                   question="Service configuration", day=f"2026-01-{index + 1:02}"))
            book.ingest(source("memcache", "Memcache capacity=96. The equipment manifest has the revised service capacity.",
                               task_title=directory, question="Service configuration", day="2026-02-01"))
            result = book.recall("current Redis timeout and Memcache capacity", project="harbor", limit=2)
            self.assertIn("memcache", sessions(result))
            self.assertTrue(any(identity.startswith("redis-") for identity in sessions(result)))

    def test_question_mentions_do_not_count_as_value_coverage_of_other_facets(self):
        with MemoryBook(":memory:") as book:
            directory = "Redis and Memcache service settings"
            question = "Redis timeout and Memcache capacity?"
            for index in range(6):
                book.ingest(source(f"redis-{index}", f"Redis timeout={index + 1}.", task_title=directory,
                                   question=question, day=f"2026-11-{index + 1:02}"))
            book.ingest(source("memcache", "Memcache capacity=96.", task_title=directory,
                               question=question, day="2026-02-01"))
            result = book.recall("current Redis timeout and Memcache capacity", project="harbor", limit=2)
            self.assertIn("memcache", sessions(result))
            self.assertTrue(any(identity.startswith("redis-") for identity in sessions(result)))

    def test_same_source_later_turn_remains_a_revision_without_a_new_literal_binding(self):
        record = source("conversation", "Fleet dispatch lease.ttl=30. " + "fleet dispatch lease.ttl. " * 20)
        record["messages"] += [
            {"role": "user", "content": "Fleet dispatch lease.ttl?"},
            {"role": "assistant", "content": "Use forty-five seconds from this point on."}]
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(record)
            result = book.recall("current fleet dispatch lease.ttl", project="harbor", limit=1)
            self.assertIn("forty-five seconds", result["context"])
            self.assertEqual({ref["turn_index"] for ref in result["results"][0]["source_refs"]}, {1})

    def test_project_chapter_and_session_scopes_apply_to_the_new_route(self):
        with MemoryBook(":memory:") as book:
            book.ingest(source("local", "Fleet dispatch lease.ttl=30."))
            book.ingest(source("remote", "Fleet dispatch lease.ttl=90.", project="remote", day="2026-11-01"))
            book.ingest(source("other-task", "Fleet dispatch lease.ttl=75.", task="archive", day="2026-11-02"))
            chapter = book.db.execute("SELECT chapter_id FROM sessions WHERE project_id='harbor' AND external_id='local'").fetchone()[0]
            query = "current fleet dispatch lease.ttl"
            for scopes in ({"project": "harbor", "chapter": chapter}, {"project": "harbor", "session": "local"}):
                with self.subTest(scopes=scopes):
                    result = book.recall(query, limit=5, **scopes)
                    self.assertEqual(sessions(result), ["local"])

    def test_ordinary_history_event_and_flat_queries_do_not_execute_the_value_route(self):
        with MemoryBook(":memory:") as book:
            book.ingest(source("original", "Fleet dispatch lease.ttl=30."))
            with patch.object(book, "_current_value_route", side_effect=AssertionError("unexpected value route")):
                for query in ("fleet dispatch lease.ttl", "original fleet dispatch lease.ttl",
                              "current fleet dispatch lease.ttl as of 2026", "current fleet dispatch lease.ttl event timeline"):
                    with self.subTest(query=query):
                        book.recall(query, project="harbor", use_cache=False)
                book.recall("current fleet dispatch lease.ttl", project="harbor", strategy="flat", use_cache=False)
                book.recall("current lease.ttl", project="harbor", use_cache=False)
                book.recall("current timeout", project="harbor", use_cache=False)

    def test_value_route_has_an_independent_fixed_output_cap(self):
        with MemoryBook(":memory:") as book:
            for index in range(104):
                book.ingest(source(f"binding-{index}", f"Fleet dispatch lease.ttl={index + 1}."))
            original = book._current_value_route
            counts = []
            def observed(*args):
                rows = original(*args)
                counts.append(len(rows))
                return rows
            with patch.object(book, "_current_value_route", side_effect=observed):
                result = book.recall("current fleet dispatch lease.ttl", project="harbor", use_cache=False)
            self.assertEqual(counts, [96])
            self.assertLessEqual(result["candidate_count"], 288)

    def test_version_14_cache_cannot_supply_a_version_15_value_response(self):
        with MemoryBook(":memory:") as book:
            book.ingest(source("original", "Fleet dispatch lease.ttl=30."))
            with patch.object(store, "RECALL_VERSION", 14):
                book.recall("current fleet dispatch lease.ttl", project="harbor")
            book.db.execute("UPDATE recall_cache SET payload=?", (json.dumps({"context": "old value route cache"}),))
            result = book.recall("current fleet dispatch lease.ttl", project="harbor")
            self.assertFalse(result["cache_hit"])
            self.assertIn("lease.ttl=30", result["context"])

    def test_new_route_does_not_write_fts_or_change_bm25_corpus(self):
        with MemoryBook(":memory:") as book:
            book.ingest(source("original", "Fleet dispatch lease.ttl=30."))
            before = {table: [tuple(row) for row in book.db.execute(f"SELECT rowid,* FROM {table} ORDER BY rowid")]
                      for table in ("pages_fts", "pages_stem_fts")}
            changed = book.db.total_changes
            book.recall("current fleet dispatch lease.ttl", project="harbor", use_cache=False)
            self.assertEqual(book.db.total_changes, changed)
            for table, rows in before.items():
                self.assertEqual(rows, [tuple(row) for row in book.db.execute(f"SELECT rowid,* FROM {table} ORDER BY rowid")])

    @unittest.skipUnless(hasattr(sqlite3.Connection, "setlimit"), "SQLite limit controls require Python 3.11+")
    def test_existing_ten_column_sqlite_limit_still_allows_current_value_recall(self):
        with MemoryBook(":memory:") as book:
            book.ingest(source("original", "Fleet dispatch lease.ttl=30."))
            previous = book.db.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 10)
            try:
                result = book.recall("current fleet dispatch lease.ttl", project="harbor", use_cache=False)
            finally:
                book.db.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, previous)
            self.assertIn("lease.ttl=30", result["context"])

    @unittest.skipUnless(hasattr(sqlite3.Connection, "setlimit"), "SQLite limit controls require Python 3.11+")
    def test_three_disjoint_routes_preserve_response_under_192_variable_limit(self):
        with MemoryBook(":memory:", max_page_chars=10000) as book:
            padding = "Equipment manifest retained. "
            for index in range(96):
                records = {
                    f"exact-{index}": "deployment worker lease ttl. " * 2 + padding * 45,
                    f"stem-{index}": "deployments workers leases ttls. " * 10,
                    f"value-{index}": f"Deployment worker lease.ttl={10 + index}. " + padding * 150,
                }
                for identity, body in records.items():
                    book.ingest(source(identity, body, project="service", task_title="Configuration", question="Status"))
            query = "current deployment worker lease.ttl"
            for limit in (5, 50):
                with self.subTest(limit=limit):
                    baseline = book.recall(query, project="service", limit=limit, budget_chars=100000, use_cache=False)
                    self.assertEqual(baseline["candidate_count"], 288)
                    previous = book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 192)
                    try:
                        constrained = book.recall(query, project="service", limit=limit, budget_chars=100000, use_cache=False)
                    finally:
                        book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, previous)
                    self.assertEqual({key: value for key, value in constrained.items() if key != "latency_ms"},
                                     {key: value for key, value in baseline.items() if key != "latency_ms"})

    @unittest.skipUnless(hasattr(sqlite3.Connection, "setlimit"), "SQLite limit controls require Python 3.11+")
    def test_added_value_union_respects_a_caller_variable_limit_below_192(self):
        with MemoryBook(":memory:", max_page_chars=10000) as book:
            padding = "Equipment manifest retained. "
            for index in range(96):
                book.ingest(source(f"exact-{index}", "deployment worker lease ttl. " * 2 + padding * 45,
                                   project="service", task_title="Configuration", question="Status"))
            for index in range(20):
                book.ingest(source(f"value-{index}", f"Deployment worker lease.ttl={10 + index}. " + padding * 150,
                                   project="service", task_title="Configuration", question="Status"))
            query = "current deployment worker lease.ttl"
            for limit in (5, 50):
                with self.subTest(limit=limit):
                    baseline = book.recall(query, project="service", limit=limit, budget_chars=100000, use_cache=False)
                    self.assertEqual(baseline["candidate_count"], 116)
                    previous = book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 100)
                    try:
                        constrained = book.recall(query, project="service", limit=limit, budget_chars=100000, use_cache=False)
                    finally:
                        book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, previous)
                    self.assertEqual({key: value for key, value in constrained.items() if key != "latency_ms"},
                                     {key: value for key, value in baseline.items() if key != "latency_ms"})

    def test_reimport_delete_and_other_connection_invalidate_value_evidence_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.db"
            with MemoryBook(path) as writer, MemoryBook(path) as reader:
                writer.ingest(source("configuration", "Fleet dispatch lease.ttl=30."))
                query = "current fleet dispatch lease.ttl"
                first = reader.recall(query, project="harbor", limit=1)
                self.assertIn("lease.ttl=30", first["context"])
                with patch.object(store, "RECALL_VERSION", 14):
                    reader.recall(query, project="harbor", limit=1)
                writer.ingest(source("configuration", "Fleet dispatch lease.ttl=45.", day="2026-11-01"))
                replaced = reader.recall(query, project="harbor", limit=1)
                self.assertFalse(replaced["cache_hit"])
                self.assertIn("lease.ttl=45", replaced["context"])
                self.assertNotIn("lease.ttl=30", replaced["context"])
                writer.delete_session("harbor", "configuration")
                deleted = reader.recall(query, project="harbor", limit=1)
                self.assertFalse(deleted["cache_hit"])
                self.assertEqual(deleted["results"], [])

    def test_filter_failure_rolls_back_snapshot_and_leaves_next_recall_usable(self):
        with MemoryBook(":memory:") as book:
            book.ingest(source("original", "Fleet dispatch lease.ttl=30."))
            with patch.object(store, "_current_value_filter", return_value=lambda *args: 1 / 0):
                with self.assertRaises(sqlite3.OperationalError):
                    book.recall("current fleet dispatch lease.ttl", project="harbor", use_cache=False)
            self.assertFalse(book.db.in_transaction)
            self.assertIn("lease.ttl=30", book.recall("current fleet dispatch lease.ttl", project="harbor")["context"])


if __name__ == "__main__":
    unittest.main()
