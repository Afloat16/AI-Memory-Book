"""Independent review regressions; frozen engineering benchmark gold is unchanged."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from memory_book import MemoryBook
import memory_book.store as store


def source(identity, content, date="2026-01-01T00:00:00Z"):
    return {"project": "workers", "session_id": identity, "task_id": "configuration",
            "task_title": "Configuration", "title": "Configuration", "created_at": date,
            "messages": [{"role": "assistant", "content": content}]}


class AssessmentReviewRegressions(unittest.TestCase):
    def test_literal_destination_port_retains_de_inside_the_field_name(self):
        for spacing in ("", " "):
            with self.subTest(spacing=spacing), MemoryBook(":memory:", segmentation="turn") as book:
                book.ingest(source("initial", f"目的端口为{spacing}80。" + "目的端口记录。" * 12))
                book.ingest(source("revised", f"目的端口为{spacing}443。", "2026-06-01T00:00:00Z"))
                result = book.recall("当前目的端口", project="workers", limit=1)
                self.assertEqual(result["results"][0]["source_refs"][0]["session_id"], "revised")
                self.assertIn("443", result["context"])
                self.assertEqual(result["temporal"]["evidence_assessment"]["status"], "comparable_declaration")

    def test_clear_question_possession_still_matches_the_original_field(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(source("initial", "生产环境重试次数是 30。"))
            book.ingest(source("revised", "生产环境重试次数已调整为 12。", "2026-06-01T00:00:00Z"))
            result = book.recall("当前生产环境的重试次数是多少？", project="workers", limit=1)
            self.assertEqual(result["results"][0]["source_refs"][0]["session_id"], "revised")

    def test_current_inside_a_qualified_assignment_keeps_its_namespace(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(source("initial", "current.phase_size=30. " + "current.phase_size record. " * 12))
            book.ingest(source("revised", "current.phase_size=12.", "2026-06-01T00:00:00Z"))
            book.ingest(source("other", "previous.phase_size=99.", "2026-09-01T00:00:00Z"))
            result = book.recall("当前 current.phase_size", project="workers", limit=1)
            self.assertEqual(result["results"][0]["source_refs"][0]["session_id"], "revised")
            self.assertIn("current.phase_size=12", result["context"])

    def test_explicit_revocation_is_never_demoted_as_a_plain_nondecision(self):
        for revocation in ("The previous value was revoked.", "The old setting is no longer valid.", "旧值已失效。"):
            with self.subTest(revocation=revocation), MemoryBook(":memory:", segmentation="turn") as book:
                book.ingest(source("previous", "Production wait_limit=12."))
                book.ingest(source("revoked", "Production wait_limit remains on the review agenda. "
                                   + revocation + " No new value was selected. "
                                   + "production wait_limit review. " * 12, "2026-06-01T00:00:00Z"))
                result = book.recall("current production wait_limit", project="workers", limit=1)
                self.assertEqual(result["results"][0]["source_refs"][0]["session_id"], "revoked")
                self.assertIn(revocation, result["context"])
                self.assertNotIn("nondecision_priority", result["temporal"])

    def test_conflict_uses_only_whole_requested_fields_and_preserves_real_conflicts(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(source("a", "Production wait_limit=12. Production connection_limit=30."))
            book.ingest(source("b", "Production wait_limit=12. Production connection_limit=99."))
            for query in ("current production wait_limit", "current production waitlimit"):
                result = book.recall(query, project="workers")
                self.assertEqual(result["temporal"]["evidence_assessment"]["status"], "comparable_declaration")
                self.assertEqual(result["temporal"]["evidence_assessment"]["conflicts"], [])
            both = book.recall("current production wait_limit connection_limit", project="workers")
            self.assertEqual(both["temporal"]["evidence_assessment"]["status"], "potential_conflict")
            book.ingest(source("b", "Production wait_limit=20. Production connection_limit=99."))
            relevant = book.recall("current production wait_limit", project="workers")
            self.assertEqual(relevant["temporal"]["evidence_assessment"]["status"], "potential_conflict")

    def test_candidate_one_result_cache_is_not_reused_after_the_review_fix(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(source("a", "Production wait_limit=12."))
            with patch.object(store, "RECALL_VERSION", 22):
                first = book.recall("current production wait_limit", project="workers")
                cached = book.recall("current production wait_limit", project="workers")
            self.assertFalse(first["cache_hit"])
            self.assertTrue(cached["cache_hit"])
            after = book.recall("current production wait_limit", project="workers")
            self.assertFalse(after["cache_hit"])
            self.assertEqual(after["context"], first["context"])


if __name__ == "__main__":
    unittest.main()
