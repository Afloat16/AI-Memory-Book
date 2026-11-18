"""Statement-local qualifier regressions authored after candidate3 review.

These cases exercise conservative admission of supplementary revisions. They
do not assert natural-language truth or change the original pool's fallback.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from tests.test_current_candidate_route import record, source_sessions
from tests.test_current_proposal_qualification import original_pool, evidence_payload


PADDING = "A separate administrative scheduling note follows. " * 100


def seed(book, count=104, *, text="Production lease_duration=30. ", task="queue"):
    for index in range(count):
        book.ingest(record(f"old-{index}", text + "production lease_duration. " * 12, task=task))


class CurrentProposalFacetTests(unittest.TestCase):
    def assert_unchanged_evidence(self, book, query="current production lease_duration", **options):
        request = dict(query=query, project="workers", limit=1, budget_chars=2400,
                       use_cache=False, **options)
        with patch.object(book, "_current_revision_pool", side_effect=original_pool):
            control = book.recall(**request)
        result = book.recall(**request)
        for key in ("results", "context", "candidate_count"):
            self.assertEqual(result[key], control[key], key)
        return result

    def test_other_sentence_cannot_lend_a_qualifier_to_staging_assignment(self):
        for count in (8, 104):
            with self.subTest(count=count), MemoryBook(":memory:", segmentation="turn") as book:
                seed(book, count)
                book.ingest(record("latest-staging", "Staging lease_duration=99. "
                                   "The production review remains open. " + PADDING,
                                   date="2026-10-01T00:00:00Z"))
                result = self.assert_unchanged_evidence(book)
                self.assertIn("Production lease_duration=30.", result["context"])
                self.assertNotIn("99", result["context"])

    def test_qualifier_cannot_cross_punctuation_or_discussion_before_assignment(self):
        texts = (
            "Production remains pending, staging lease_duration=99. ",
            "Production remains pending; staging lease_duration=99. ",
            "Production remains pending: staging lease_duration=99. ",
            "Production discussion includes staging lease_duration=99. ",
            "Production remains pending\nStaging lease_duration=99. ",
            "Staging lease_duration=99 for a production discussion. ",
            "Production lease_duration=99 for staging. ",
            "Production lease duration is now 99 for staging. ",
        )
        for text in texts:
            with self.subTest(text=text), MemoryBook(":memory:", segmentation="turn") as book:
                seed(book, 8)
                book.ingest(record("ambiguous", text + PADDING, date="2026-10-01T00:00:00Z"))
                self.assert_unchanged_evidence(book)

    def test_one_fields_qualifier_cannot_apply_to_another_field(self):
        for text in (
            "Production max_connections=50. Staging lease_duration=99. ",
            "Production max_connections=50; staging lease_duration=99. ",
            "Production max_connections=50, staging lease_duration=99. ",
        ):
            with self.subTest(text=text), MemoryBook(":memory:", segmentation="turn") as book:
                seed(book, 8)
                book.ingest(record("other-field", text + PADDING, date="2026-10-01T00:00:00Z"))
                self.assert_unchanged_evidence(book)

    def test_multiple_declarations_of_one_field_do_not_form_a_single_revision(self):
        for text in (
            "Production lease_duration=30. Staging lease_duration=99. ",
            "Production lease_duration=30; staging lease_duration=99. ",
            "Production lease_duration=30, staging lease_duration=99. ",
            "Production lease duration is 30. Staging lease duration is 99. ",
        ):
            with self.subTest(text=text), MemoryBook(":memory:", segmentation="turn") as book:
                seed(book, 8)
                book.ingest(record("mixed-values", text + PADDING, date="2026-10-01T00:00:00Z"))
                self.assert_unchanged_evidence(book)

    def test_anchor_also_requires_a_qualifier_attached_to_its_declaration(self):
        for text in (
            "Staging lease_duration=30. The production review remains open. ",
            "Staging lease_duration=30. Production lease_duration=40. ",
        ):
            with self.subTest(text=text), MemoryBook(":memory:", segmentation="turn") as book:
                seed(book, 8, text=text)
                book.ingest(record("unanchored-production", "Production lease_duration=12. " + PADDING,
                                   date="2026-10-01T00:00:00Z"))
                self.assert_unchanged_evidence(book)

    def test_user_question_cannot_supply_the_assignments_qualifier(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 8)
            source = record("unanswered-production", "unused", date="2026-10-01T00:00:00Z")
            source["messages"] = [
                {"role": "user", "content": "What is the production lease_duration?"},
                {"role": "assistant", "content": "Staging lease_duration=99. " + PADDING},
            ]
            book.ingest(source)
            self.assert_unchanged_evidence(book)

    def test_explicit_adjacent_qualifiers_keep_short_assignment_and_prose_updates(self):
        for text in (
            "Production lease_duration=12.",
            "Production: lease_duration=12.",
            "Production lease duration is now 12.",
        ):
            for count in (8, 104):
                with self.subTest(text=text, count=count), MemoryBook(":memory:", segmentation="turn") as book:
                    seed(book, count)
                    book.ingest(record("accepted", text, date="2026-06-01T00:00:00Z"))
                    result = book.recall("current production lease_duration", project="workers",
                                         limit=1, use_cache=False)
                    self.assertEqual(source_sessions(result), ["accepted"])
                    self.assertIn("12", result["context"])

    def test_each_field_in_a_contract_requires_its_own_adjacent_qualifier(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for index in range(8):
                book.ingest(record(f"old-{index}", "Production lease_duration=30. "
                                   "Production max_connections=20. "
                                   + "production lease_duration max_connections. " * 12))
            book.ingest(record("mixed", "Production lease_duration=12. "
                               "Staging max_connections=99. " + PADDING,
                               date="2026-10-01T00:00:00Z"))
            self.assert_unchanged_evidence(book, "current production lease_duration max_connections")
            book.ingest(record("accepted", "Production lease_duration=12. "
                               "Production max_connections=10.", date="2026-06-01T00:00:00Z"))
            result = book.recall("current production lease_duration max_connections", project="workers",
                                 limit=1, use_cache=False)
            self.assertEqual(source_sessions(result), ["accepted"])
            self.assertNotIn("99", result["context"])

    def test_original_pool_keeps_its_existing_whole_page_facet_behavior(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            seed(book, 2)
            book.ingest(record("already-in-pool", "Staging lease_duration=99. "
                               "The production review remains open. " + PADDING,
                               date="2026-10-01T00:00:00Z"))
            request = dict(query="current production lease_duration", project="workers", limit=1,
                           use_cache=False)
            with patch.object(book, "_current_revision_pool", side_effect=original_pool):
                control = book.recall(**request)
            result = book.recall(**request)
            self.assertEqual(source_sessions(control), ["already-in-pool"])
            self.assertEqual(evidence_payload(result), evidence_payload(control))

    def test_semantic_fusion_cannot_borrow_another_sentences_qualifier(self):
        from tests.test_semantic import FixtureEncoder
        with MemoryBook(":memory:", segmentation="turn", semantic_model_dir="/fixture") as book:
            book._semantic_model = FixtureEncoder()
            seed(book, 104)
            book.ingest(record("latest-staging", "Staging lease_duration=99. "
                               "The production review remains open. " + PADDING,
                               date="2026-10-01T00:00:00Z"))
            book.build_semantic_index()
            old = dict(book.db.execute(
                "SELECT p.id,p.rid,p.project_id,p.chapter_id,c.title chapter_title,"
                "s.external_id session_id,s.title session_title,s.created_at FROM pages p "
                "JOIN chapters c ON c.id=p.chapter_id JOIN sessions s ON s.id=p.session_pk "
                "WHERE s.external_id='old-0'").fetchone())
            with patch("memory_book.semantic.rank_pages", return_value=[{**old, "semantic_similarity": 1.0}]):
                self.assert_unchanged_evidence(book, semantic=True)


if __name__ == "__main__":
    unittest.main()
