"""Revision crowding regressions independent of the engineering benchmark.

Chronological proposals must remain in the requested project/task/facets and
must not turn a newer mention, example, or incomplete turn into a declaration.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from memory_book import MemoryBook
import memory_book.store as store


def record(identity: str, text: str, *, project="workers", task="queue",
           date="2026-01-01T00:00:00Z") -> dict:
    return {"project": project, "session_id": identity, "task_id": task,
            "task_title": "Worker configuration", "title": "Worker configuration",
            "created_at": date, "messages": [{"role": "assistant", "content": text}]}


def seed(book: MemoryBook, count=4, *, project="workers", task="queue") -> str:
    for index in range(count):
        result = book.ingest(record(f"old-{index}", "lease_duration=30. " + "lease_duration. " * 12,
                                    project=project, task=task))
    book.ingest(record("accepted", "lease_duration=12. The accepted configuration is deliberately concise.",
                       project=project, task=task, date="2026-06-01T00:00:00Z"))
    return result["chapter_id"]


def source_sessions(result: dict) -> list[str]:
    return [hit["source_refs"][0]["session_id"] for hit in result["results"]]


class CurrentCandidateRouteTests(unittest.TestCase):
    def test_requested_result_count_does_not_hide_the_short_revision(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book)
            for limit in (1, 2, 5):
                with self.subTest(limit=limit):
                    result = book.recall("lease_duration", project="workers", temporal="current",
                                         limit=limit, use_cache=False)
                    self.assertEqual(source_sessions(result)[0], "accepted")
                    self.assertIn("lease_duration=12", result["context"])
                    diagnostic = result["temporal"]["candidate_expansion"]
                    self.assertEqual(diagnostic["metadata_source"], "complete_exact_route")
                    self.assertEqual(diagnostic["new_candidates"], 0)

    def test_more_than_96_old_matches_cannot_hide_a_recent_comparable_revision(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 104)
            for limit in (1, 5):
                result = book.recall("current lease_duration", project="workers", limit=limit,
                                     use_cache=False)
                self.assertEqual(source_sessions(result)[0], "accepted")
                self.assertIn("lease_duration=12", result["context"])
                diagnostic = result["temporal"]["candidate_expansion"]
                self.assertEqual(diagnostic["metadata_source"], "scoped_fts_chronology")
                self.assertLessEqual(diagnostic["returned"], 96)
                self.assertLessEqual(diagnostic["pool_size"], 4 * limit + 96)
                self.assertGreater(diagnostic["admitted_proposals"], 0)
                self.assertFalse(diagnostic["database_scan_bounded"])
                self.assertTrue(diagnostic["scope_before_limit"])

    def test_relevance_historical_and_flat_paths_do_not_expand_candidates(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 104)
            for query, options in (
                ("lease_duration", {}),
                ("original lease_duration", {}),
                ("current lease_duration as of 2026", {}),
                ("current lease_duration", {"temporal": "relevance"}),
                ("current lease_duration", {"strategy": "flat"}),
            ):
                with self.subTest(query=query, options=options):
                    result = book.recall(query, project="workers", limit=1, use_cache=False, **options)
                    self.assertNotEqual(source_sessions(result)[0], "accepted")
                    self.assertNotIn("candidate_expansion", result["temporal"])
                    self.assertEqual(result["candidate_count"], 96)

    def test_every_scope_precedes_the_recent_route_limit(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            chapter = seed(book, 104)
            seed(book, 104, project="workers-copy")
            book.ingest(record("other-task", "lease_duration=88.", task="another",
                               date="2026-08-01T00:00:00Z"))
            book.ingest(record("foreign", "lease_duration=99.", project="workers-copy",
                               date="2026-09-01T00:00:00Z"))
            result = book.recall("current lease_duration", project="workers", chapter=chapter, limit=1)
            self.assertEqual(source_sessions(result), ["accepted"])
            self.assertEqual({ref["project"] for hit in result["results"] for ref in hit["source_refs"]},
                             {"workers"})
            self.assertEqual({row["chapter_id"] for row in result["temporal"]["candidate_expansion"]["chapter_routes"]},
                             {chapter})
            earlier = book.recall("current lease_duration", project="workers", chapter=chapter,
                                  session="old-0", limit=1)
            self.assertEqual(source_sessions(earlier), ["old-0"])
            missing = book.recall("current lease_duration", project="missing", chapter=chapter, limit=1)
            self.assertFalse(missing["results"])
            mismatch = book.recall("current lease_duration", project="workers-copy", chapter=chapter, limit=1)
            self.assertFalse(mismatch["results"])

    def test_newer_mentions_and_other_fields_cannot_replace_a_declaration(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 104)
            for identity, text in (
                ("mention", "Reviewed lease_duration during maintenance without deciding a new value."),
                ("other-field", "lease_duration documentation: max_connections=999."),
                ("example", "Example: lease_duration=999."),
                ("code", "```python\nlease_duration=999\n```"),
                ("another-topic", "compression_level=999. Newer unrelated work."),
            ):
                book.ingest(record(identity, text, date="2026-10-01T00:00:00Z"))
            result = book.recall("current lease_duration", project="workers", limit=1)
            self.assertEqual(source_sessions(result), ["accepted"])
            self.assertNotIn("999", result["context"])
            self.assertGreater(result["temporal"]["candidate_expansion"]["unmatched_proposals"], 0)

    def test_remaining_environment_facet_keeps_staging_out_of_production_slot(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for index in range(104):
                book.ingest(record(f"old-{index}", "Production lease_duration=30. " +
                                   "production lease_duration. " * 12))
            book.ingest(record("production", "Production lease_duration=12.", date="2026-06-01T00:00:00Z"))
            book.ingest(record("staging", "Staging lease_duration=99.", date="2026-10-01T00:00:00Z"))
            result = book.recall("current production lease_duration", project="workers", limit=1)
            self.assertEqual(source_sessions(result), ["production"])
            self.assertNotIn("99", result["context"])

    def test_different_declared_field_sets_do_not_replace_a_complete_contract(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for index in range(104):
                book.ingest(record(f"old-{index}", "lease_duration=30; max_connections=20. " +
                                   "lease_duration max_connections. " * 8))
            book.ingest(record("partial-update", "lease_duration=12.", date="2026-06-01T00:00:00Z"))
            result = book.recall("current lease_duration max_connections", project="workers", limit=1)
            self.assertNotEqual(source_sessions(result), ["partial-update"])
            self.assertIn("max_connections=20", result["context"])

    def test_continuation_page_cannot_claim_a_complete_declaration(self):
        with MemoryBook(":memory:", segmentation="adaptive", max_page_chars=300, min_page_chars=0) as book:
            for index in range(104):
                book.ingest(record(f"old-{index}", "lease_duration=30. " + "lease_duration. " * 5))
            book.ingest(record("incomplete", "lease_duration=999. " + "pending " * 180 + "Not accepted.",
                               date="2026-06-01T00:00:00Z"))
            result = book.recall("current lease_duration", project="workers", limit=1)
            self.assertNotEqual(source_sessions(result), ["incomplete"])
            self.assertNotIn("999", result["context"])

    def test_latest_turn_within_one_long_session_is_in_the_recent_route(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            source = record("long-session", "unused")
            source["messages"] = []
            for index in range(104):
                source["messages"].extend([
                    {"role": "user", "content": f"lease_duration review {index}?"},
                    {"role": "assistant", "content": "lease_duration=30. " + "lease_duration. " * 12},
                ])
            source["messages"].extend([
                {"role": "user", "content": "lease_duration correction?"},
                {"role": "assistant", "content": "lease_duration=12."},
            ])
            book.ingest(source)
            result = book.recall("current lease_duration", project="workers", limit=1)
            self.assertIn("lease_duration=12", result["context"])
            self.assertEqual(result["results"][0]["source_refs"][0]["turn_index"], 104)

    def test_replacing_the_short_session_invalidates_cached_revision(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 104)
            first = book.recall("current lease_duration", project="workers", limit=1)
            cached = book.recall("current lease_duration", project="workers", limit=1)
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(first["context"], cached["context"])
            book.ingest(record("accepted", "lease_duration=6.", date="2026-06-01T00:00:00Z"))
            updated = book.recall("current lease_duration", project="workers", limit=1)
            self.assertFalse(updated["cache_hit"])
            self.assertGreater(updated["revision"], first["revision"])
            self.assertIn("lease_duration=6", updated["context"])

    @unittest.skipIf(store._NATIVE is None, "native extension not built")
    def test_python_and_native_return_identical_candidate_expansion_evidence(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 104)
            native = book.recall("current lease_duration", project="workers", limit=5, use_cache=False)
            with patch.object(store, "_NATIVE", None):
                reference = book.recall("current lease_duration", project="workers", limit=5, use_cache=False)
            for result in (native, reference):
                result.pop("latency_ms")
            self.assertEqual(native, reference)


if __name__ == "__main__":
    unittest.main()
