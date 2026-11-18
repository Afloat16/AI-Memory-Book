"""Current-source decisions and bounded uncertainty, independent of gold labels."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from tests.test_current_candidate_route import record, source_sessions


def assessment(result):
    return result["temporal"]["evidence_assessment"]


class CurrentEvidenceAssessmentTests(unittest.TestCase):
    def test_chinese_parameter_counts_follow_completed_revisions(self):
        for subject in ("生产环境重试次数", "生产环境最大重试次数", "训练迭代次数"):
            for aspect in ("已调整为", "已经调整为", "现已设置为"):
                with self.subTest(subject=subject, aspect=aspect), MemoryBook(":memory:", segmentation="turn") as book:
                    book.ingest(record("initial", subject + "是 30。"))
                    book.ingest(record("revised", subject + aspect + " 12。", date="2026-06-01T00:00:00Z"))
                    result = book.recall("当前" + subject + "是多少？", project="workers", limit=1)
                    self.assertFalse(result["temporal"]["preserve_occurrences"])
                    self.assertEqual(source_sessions(result), ["revised"])
                    self.assertEqual(assessment(result)["status"], "comparable_declaration")

    def test_chinese_question_particles_do_not_change_the_index(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(record("initial", "生产环境重试次数是 30。"))
            book.ingest(record("revised", "生产环境重试次数已调整为 12。", date="2026-06-01T00:00:00Z"))
            query = "当前生产环境的重试次数是多少？"
            ordinary = book.recall(query, project="workers", temporal="relevance", limit=1)
            current = book.recall(query, project="workers", limit=1)
            self.assertEqual(source_sessions(ordinary), ["initial"])
            self.assertEqual(source_sessions(current), ["revised"])
            self.assertEqual(assessment(ordinary)["status"], "not_assessed")
            self.assertEqual(ordinary["candidate_count"], current["candidate_count"])

    def test_explicit_occurrence_requests_keep_all_repeated_sources(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for i in range(3):
                book.ingest(record(str(i), "生产环境重试次数是 30。", date=f"2026-0{i + 1}-01T00:00:00Z"))
            for query in ("当前生产环境重试次数的出现次数", "当前生产环境重试发生了多少次？",
                          "统计生产环境重试次数", "当前生产环境每次重试"):
                with self.subTest(query=query):
                    result = book.recall(query, project="workers", limit=5)
                    self.assertTrue(result["temporal"]["preserve_occurrences"])
                    self.assertEqual(set(source_sessions(result)), {"0", "1", "2"})
                    self.assertEqual(assessment(result)["status"], "not_assessed")

    def test_explicit_nondecision_cannot_lead_a_same_scope_declaration(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(record("decision", "Production wait_limit=12."))
            book.ingest(record("agenda", "Production wait_limit remains on the review agenda. No value was decided. "
                               + "production wait_limit review. " * 12, date="2026-06-01T00:00:00Z"))
            query = "current production wait_limit"
            ordinary = book.recall(query, project="workers", temporal="relevance", limit=1)
            current = book.recall(query, project="workers", limit=1)
            self.assertEqual(source_sessions(ordinary), ["agenda"])
            self.assertEqual(source_sessions(current), ["decision"])
            self.assertEqual(assessment(current)["status"], "comparable_declaration")

    def test_same_time_conflict_ids_remain_within_the_requested_project(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            for project, values in (("workers", (12, 30)), ("workers/child", (112, 130))):
                for identity, value in zip(("a", "b"), values):
                    book.ingest(record(identity, f"Production wait_limit={value}.", project=project))
            for limit in (1, 5):
                result = book.recall("current production wait_limit", project="workers", limit=limit)
                info = assessment(result)
                self.assertEqual(info["status"], "potential_conflict")
                self.assertEqual(info["scope"], "bounded_candidate_pool")
                self.assertTrue(any("Potential conflict" in warning for warning in result["warnings"]))
                ids = info["conflicts"][0]["page_ids"]
                self.assertEqual(len(set(ids)), 2)
                for identity in ids:
                    page = book.read(identity, project="workers", limit=100000)
                    self.assertEqual(page["source_refs"][0]["project"], "workers")
                if limit == 5:
                    self.assertEqual(set(source_sessions(result)), {"a", "b"})

    def test_duplicates_scopes_and_explicit_turn_order_are_not_conflicts(self):
        for other in ("Production wait_limit=12.", "Staging wait_limit=30.",
                      "Production connection_limit=30.", "Production wait_limit=30 if approved."):
            with self.subTest(other=other), MemoryBook(":memory:", segmentation="turn") as book:
                book.ingest(record("a", "Production wait_limit=12."))
                book.ingest(record("b", other))
                result = book.recall("current production wait_limit", project="workers", limit=5)
                self.assertEqual(assessment(result)["status"], "comparable_declaration")
                self.assertEqual(assessment(result)["conflicts"], [])
        with MemoryBook(":memory:", segmentation="turn") as book:
            source = record("ordered", "Production wait_limit=30.")
            source["messages"].extend([{"role": "user", "content": "Record the revised configuration."},
                                       {"role": "assistant", "content": "Production wait_limit=12."}])
            book.ingest(source)
            result = book.recall("current production wait_limit", project="workers", limit=5)
            self.assertEqual(assessment(result)["status"], "comparable_declaration")
            self.assertEqual(result["results"][0]["source_refs"][0]["turn_index"], 1)

    def test_missing_declaration_retains_related_sources_and_limits_its_claim(self):
        with MemoryBook(":memory:", segmentation="turn") as book:
            book.ingest(record("agenda", "Production wait_limit remains pending approval; no new value was selected."))
            result = book.recall("current production wait_limit", project="workers")
            self.assertTrue(result["context"])
            self.assertEqual(assessment(result)["status"], "no_comparable_declaration")
            self.assertEqual(assessment(result)["inspected_candidates"], 1)
            self.assertTrue(any("bounded candidate pool" in warning for warning in result["warnings"]))
            missing = book.recall("current unrelated_batch_bytes", project="workers")
            self.assertEqual(assessment(missing)["status"], "no_matching_evidence")
            unknown = book.recall("current production wait_limit", project="absent")
            self.assertEqual(assessment(unknown)["status"], "no_matching_evidence")
            self.assertEqual(unknown["results"], [])

    def test_skipped_retrieval_relevance_history_and_flat_are_not_assessed(self):
        with MemoryBook(":memory:") as book:
            book.ingest(record("a", "wait_limit=12."))
            for query, options in (("current wait_limit", {"budget_chars": 0}),
                                   ("", {"temporal": "current"}),
                                   ("the", {"temporal": "current"}),
                                   ("current wait_limit", {"strategy": "flat"}),
                                   ("current wait_limit", {"temporal": "relevance"}),
                                   ("original wait_limit", {})):
                with self.subTest(query=query, options=options):
                    result = book.recall(query, project="workers", **options)
                    self.assertEqual(assessment(result)["status"], "not_assessed")
                    self.assertEqual(assessment(result)["conflicts"], [])

    def test_semantic_fusion_uses_source_declarations_and_skipped_retrieval_stays_unassessed(self):
        from tests.test_semantic import FixtureEncoder
        with MemoryBook(":memory:", segmentation="turn", semantic_model_dir="/fixture") as book:
            book._semantic_model = FixtureEncoder()
            book.ingest(record("a", "Production wait_limit=12."))
            book.ingest(record("b", "Production wait_limit=30."))
            book.build_semantic_index()
            with patch("memory_book.semantic.rank_pages", return_value=[]):
                result = book.recall("current production wait_limit", project="workers", semantic=True)
                self.assertEqual(assessment(result)["status"], "potential_conflict")
                for query, options in (("", {"temporal": "current"}),
                                       ("current production wait_limit", {"budget_chars": 0})):
                    skipped = book.recall(query, project="workers", semantic=True, **options)
                    self.assertEqual(assessment(skipped)["status"], "not_assessed")


if __name__ == "__main__":
    unittest.main()
