"""Adversarial review regressions for chronological comparison proposals.

The agenda examples reproduce a candidate2 regression found during review.
They are authored regression cases, not an independent retrieval benchmark.
The no-expansion control exercises the original comparison-pool contract.
"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from memory_book import MemoryBook

from tests.test_current_candidate_route import record, seed, source_sessions


def agenda_sessions(count):
    for index in range(count):
        yield {
            "project": "alpha", "task_id": "deploy", "task_title": "Deployment policy",
            "session_id": f"old-{index:03d}", "title": "Retry limit",
            "created_at": "2026-01-01T00:00:00Z",
            "messages": [
                {"role": "user", "content": "What retry limit should we ship?"},
                {"role": "assistant", "content": "The retry limit is three attempts."},
            ],
        }
    yield {
        "project": "alpha", "task_id": "deploy", "task_title": "Deployment policy",
        "session_id": "latest-agenda", "title": "Meeting agenda",
        "created_at": "2026-10-01T00:00:00Z",
        "messages": [
            {"role": "user", "content": "What will the upcoming review discuss?"},
            {"role": "assistant", "content":
             "Whether the retry limit remains approved will be discussed later. "
             "This meeting note provides no new decision. "
             + "A separate administrative scheduling note follows. " * 100},
        ],
    }


def original_pool(candidates, pool_size, *args):
    return list(candidates[:pool_size]), list(candidates[pool_size:])


def evidence_payload(result):
    result = copy.deepcopy(result)
    result.pop("latency_ms")
    result["temporal"].pop("candidate_expansion", None)
    return result


class CurrentProposalQualificationTests(unittest.TestCase):
    def test_new_agenda_cannot_inherit_a_recorded_decisions_relevance_slot(self):
        for count, limit in ((8, 1), (120, 1), (24, 2)):
            with self.subTest(old_sessions=count, limit=limit), MemoryBook(":memory:", segmentation="turn") as book:
                for source in agenda_sessions(count):
                    book.ingest(source)
                request = dict(query="What is the current retry limit?", project="alpha",
                               limit=limit, budget_chars=2400, use_cache=False)
                with patch.object(book, "_current_revision_pool", side_effect=original_pool):
                    control = book.recall(**request)
                result = book.recall(**request)
                self.assertIn("The retry limit is three attempts.", control["context"])
                self.assertIn("The retry limit is three attempts.", result["context"])
                self.assertNotIn("latest-agenda", source_sessions(result))
                # Pure numeric prose now supplies a real field identity, so
                # additional older declarations may be analyzed. That changes
                # diagnostic counts, never the selected source evidence here.
                for key in ("results", "context", "context_chars", "candidate_count", "warnings"):
                    self.assertEqual(result[key], control[key], key)
                expansion = result["temporal"]["candidate_expansion"]
                self.assertGreater(expansion["added_to_pool"], 0)
                self.assertEqual(expansion["new_candidates"] == 0, count < 96)
                self.assertGreater(expansion["rejected_before_ordering"], 0)

    def test_promoted_tail_copy_cannot_mutate_original_tail_scores_or_order(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 8)
            expand = book._current_revision_pool
            observed = {}

            def capture(candidates, pool_size, *args):
                observed["original_tail"] = candidates[pool_size:]
                observed["before"] = copy.deepcopy(observed["original_tail"])
                expanded, tail = expand(candidates, pool_size, *args)
                observed["returned_tail"] = tail
                return expanded, tail

            with patch.object(book, "_current_revision_pool", side_effect=capture):
                result = book.recall("current lease_duration", project="workers", limit=1,
                                     use_cache=False)
            self.assertEqual(source_sessions(result), ["accepted"])
            self.assertEqual(observed["original_tail"], observed["before"])
            self.assertEqual(observed["returned_tail"], observed["before"])
            self.assertEqual(result["candidate_count"], 9)
            self.assertEqual(result["temporal"]["candidate_expansion"]["new_candidates"], 0)

    def test_original_pool_agenda_cannot_take_a_recorded_decisions_slot(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for source in agenda_sessions(2):
                book.ingest(source)
            request = dict(query="What is the current retry limit?", project="alpha",
                           limit=1, budget_chars=2400, use_cache=False)
            with patch.object(book, "_current_revision_pool", side_effect=original_pool):
                control = book.recall(**request)
            result = book.recall(**request)
            # All three sources are already in the original four-item pool.
            # The old failure is retained in the v0.12 development baseline.
            self.assertTrue(source_sessions(control)[0].startswith("old-"))
            self.assertIn("The retry limit is three attempts.", control["context"])
            self.assertEqual(evidence_payload(result), evidence_payload(control))
            self.assertEqual(result["temporal"]["candidate_expansion"]["added_to_pool"], 0)

    def test_rejected_field_example_cannot_change_original_pool_grouping(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for index in range(3):
                book.ingest(record(f"decision-{index}",
                                   "Retry limit is 3. " + "retry limit. " * 20))
            book.ingest(record("review", "Reviewed retry limit during maintenance. "
                               + "retry limit. " * 20, date="2026-03-01T00:00:00Z"))
            book.ingest(record("example", "Example: retry_limit=999. "
                               + "Administrative scheduling discussion. " * 100,
                               date="2026-10-01T00:00:00Z"))
            for limit in (1, 2):
                with self.subTest(limit=limit):
                    request = dict(query="current retry limit", project="workers", limit=limit,
                                   use_cache=False, budget_chars=100000)
                    with patch.object(book, "_current_revision_pool", side_effect=original_pool):
                        control = book.recall(**request)
                    result = book.recall(**request)
                    self.assertEqual(evidence_payload(result), evidence_payload(control))
                    if limit == 1:
                        self.assertTrue(source_sessions(control)[0].startswith("decision-"))
                        self.assertIn("Retry limit is 3", control["context"])

    def test_semantic_fusion_still_rejects_an_unclassified_chronology_proposal(self):
        from tests.test_semantic import FixtureEncoder
        with MemoryBook(":memory:", segmentation="turn", semantic_model_dir="/fixture") as book:
            book._semantic_model = FixtureEncoder()
            for source in agenda_sessions(120):
                book.ingest(source)
            book.build_semantic_index()
            old = dict(book.db.execute(
                "SELECT p.id,p.rid,p.project_id,p.chapter_id,c.title chapter_title,"
                "s.external_id session_id,s.title session_title,s.created_at FROM pages p "
                "JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk "
                "WHERE s.external_id='old-000'").fetchone())
            request = dict(query="What is the current retry limit?", project="alpha", limit=1,
                           budget_chars=2400, use_cache=False, semantic=True)
            with patch("memory_book.semantic.rank_pages", return_value=[{**old, "semantic_similarity": 1.0}]):
                with patch.object(book, "_current_revision_pool", side_effect=original_pool):
                    control = book.recall(**request)
                result = book.recall(**request)
            self.assertIn("The retry limit is three attempts.", result["context"])
            for key in ("results", "context", "context_chars", "candidate_count", "warnings"):
                self.assertEqual(result[key], control[key], key)

    def test_pure_prose_update_does_not_depend_on_a_rejected_identifier_example(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for index in range(8):
                book.ingest(record(f"decision-{index}", "Retry limit is 3. " + "retry limit. " * 20))
            book.ingest(record("prose-update", "Retry limit is now 7. "
                               + "Administrative scheduling discussion. " * 60,
                               date="2026-06-01T00:00:00Z"))
            book.ingest(record("example", "Example: retry_limit=999. "
                               + "Administrative scheduling discussion. " * 100,
                               date="2026-10-01T00:00:00Z"))
            request = dict(query="current retry limit", project="workers", limit=1,
                           use_cache=False, budget_chars=2400)
            with patch.object(book, "_current_revision_pool", side_effect=original_pool):
                control = book.recall(**request)
            result = book.recall(**request)
            # Numeric prose now establishes its own query-matching subject.
            # Removing the rejected code example must not withdraw that valid
            # independently authenticated update or change its source text.
            self.assertNotEqual(source_sessions(control), ["prose-update"])
            self.assertEqual(source_sessions(result), ["prose-update"])
            self.assertIn("Retry limit is now 7", result["context"])
            expansion = result["temporal"]["candidate_expansion"]
            self.assertGreater(expansion["admitted_proposals"], 0)
            self.assertGreater(expansion["rejected_before_ordering"], 0)
            self.assertTrue(book.delete_session("workers", "example"))
            without_example = book.recall(**request)
            self.assertEqual(result["context"], without_example["context"])
            self.assertEqual(result["results"][0]["source_refs"],
                             without_example["results"][0]["source_refs"])

    def test_proposal_requires_an_original_declaration_in_its_own_chapter(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(record("declared-elsewhere", "lease_duration=30. " + "lease_duration. " * 20,
                               task="declared"))
            for index in range(3):
                book.ingest(record(f"topic-{index}", "Reviewed lease_duration during maintenance. "
                                   + "lease_duration. " * 20, task="mentioned"))
            book.ingest(record("different-chapter-update", "lease_duration=12. "
                               + "Administrative scheduling discussion. " * 100,
                               task="mentioned", date="2026-10-01T00:00:00Z"))
            request = dict(query="current lease_duration", project="workers", limit=1,
                           use_cache=False, budget_chars=2400)
            with patch.object(book, "_current_revision_pool", side_effect=original_pool):
                control = book.recall(**request)
            result = book.recall(**request)
            self.assertEqual(len(result["temporal"]["candidate_expansion"]["chapter_routes"]), 2)
            self.assertEqual(evidence_payload(result), evidence_payload(control))
            self.assertNotIn("different-chapter-update", source_sessions(result))

    def test_duplicate_text_cannot_replace_independent_source_authentication(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 104)
            valid_text = "lease_duration=12. The accepted configuration is deliberately concise."
            book.ingest(record("damaged-source", valid_text, date="2026-10-01T00:00:00Z"))
            # Deliberately corrupt the archive after ordinary ingestion. Equal
            # page bytes and plausible coordinates cannot certify another turn.
            book.db.execute("UPDATE turns SET content=replace(content,'12','88') WHERE session_pk IN "
                            "(SELECT id FROM sessions WHERE external_id='damaged-source')")
            book.db.commit()
            for limit in (1, 5):
                with self.subTest(limit=limit):
                    result = book.recall("current lease_duration", project="workers", limit=limit,
                                         use_cache=False)
                    self.assertEqual(source_sessions(result)[0], "accepted")
                    self.assertNotIn("damaged-source", source_sessions(result))

    def test_occurrence_query_keeps_the_original_pool_and_tail(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 104)
            request = dict(query="current lease_duration event timeline", project="workers",
                           limit=1, use_cache=False)
            with patch.object(book, "_current_revision_pool", side_effect=original_pool):
                control = book.recall(**request)
            result = book.recall(**request)
            self.assertTrue(result["temporal"]["preserve_occurrences"])
            self.assertEqual(evidence_payload(result), evidence_payload(control))

    def test_noncurrent_paths_do_not_enter_proposal_qualification(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for source in agenda_sessions(120):
                book.ingest(source)
            with patch.object(book, "_current_revision_pool", side_effect=AssertionError("expanded relevance")):
                for query, options in (
                    ("retry limit", {}),
                    ("original retry limit", {}),
                    ("current retry limit as of 2026", {}),
                    ("current retry limit", {"temporal": "relevance"}),
                    ("current retry limit", {"strategy": "flat"}),
                ):
                    with self.subTest(query=query, options=options):
                        result = book.recall(query, project="alpha", limit=1, use_cache=False, **options)
                        self.assertNotIn("candidate_expansion", result["temporal"])
                        self.assertIn("The retry limit is three attempts.", result["context"])


if __name__ == "__main__":
    unittest.main()
