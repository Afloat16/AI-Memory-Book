"""Close two retained v0.13 failures without broadening prose-name inference."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from memory_book import MemoryBook, store


def source(identity, text, *, newer=False, project="workers"):
    return {"project": project, "session_id": identity, "task_id": "configuration",
            "task_title": "Configuration", "title": "Configuration",
            "created_at": "2026-06-01T00:00:00Z" if newer else "2026-01-01T00:00:00Z",
            "messages": [{"role": "assistant", "content": text}]}


CASES = (
    ("最终输出维度", "当前最终输出维度", "最终输出维度为 768。" + "最终输出维度记录。" * 12,
     "最终输出维度为 1024。", "1024"),
    ("current.phase_size", "当前 current.phase_size",
     "current.phase_size is 30. " + "current.phase_size record. " * 12,
     "current.phase_size is 12.", "12"),
)


def first(result):
    return result["results"][0]["source_refs"][0]["session_id"]


def stable(result):
    return {key: value for key, value in result.items() if key != "latency_ms"}


class LiteralProseIdentifierTests(unittest.TestCase):
    def test_original_retained_cases_now_return_the_revised_literal_field(self):
        for _, query, initial, revised, value in CASES:
            for mode in ("global", "project"):
                with self.subTest(query=query, mode=mode), MemoryBook(
                        ":memory:", segmentation="turn", cache_size=0, ranking_scope=mode) as book:
                    book.ingest(source("initial", initial))
                    book.ingest(source("revised", revised, newer=True))
                    result = book.recall(query, project="workers", limit=1)
                    self.assertEqual(first(result), "revised")
                    self.assertIn(value, result["context"])
                    self.assertEqual(result["temporal"]["evidence_assessment"]["status"],
                                     "comparable_declaration")
                    self.assertEqual(result["results"][0]["source_refs"][0]["project"], "workers")

    def test_exact_names_do_not_absorb_namespace_prefixes_or_identifier_suffixes(self):
        for _, _, initial, revised, _ in CASES:
            with MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
                book.ingest(source("initial", initial))
                book.ingest(source("revised", revised, newer=True))
                queries = (("当前 other.current.phase_size", "当前 current.phase_size_extra",
                            "当前 current.phase_size.value", "当前 oldcurrent.phase_size",
                            "当前 phase_size", "current.phase_size")
                           if "current.phase_size" in initial else
                           ("当前最终输出维度上限", "当前新的最终输出维度", "当前 scope.最终输出维度",
                            "最终输出维度"))
                for query in queries:
                    with self.subTest(query=query):
                        actual = book.recall(query, project="workers", limit=1, use_cache=False)
                        with patch.object(store, "_literal_prose_identifier", return_value=False):
                            previous = book.recall(query, project="workers", limit=1, use_cache=False)
                        self.assertEqual(stable(actual), stable(previous))

    def test_spaced_temporal_phrases_and_unseparated_chinese_cues_keep_previous_behavior(self):
        examples = (
            ("current retry limit is 30. " + "retry limit record. " * 12,
             "current retry limit is 12.", "current retry limit"),
            ("当前输出维度为 768。" + "输出维度记录。" * 12,
             "当前输出维度为 1024。", "当前输出维度"),
            ("current is 30. " + "current record. " * 12,
             "current is 12.", "current current"),
        )
        for initial, revised, query in examples:
            with self.subTest(query=query), MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
                book.ingest(source("initial", initial))
                book.ingest(source("revised", revised, newer=True))
                actual = book.recall(query, project="workers", limit=1, use_cache=False)
                with patch.object(store, "_literal_prose_identifier", return_value=False):
                    previous = book.recall(query, project="workers", limit=1, use_cache=False)
                self.assertEqual(stable(actual), stable(previous))

    def test_quoted_conditional_and_foreign_mentions_do_not_become_revisions(self):
        for _, query, initial, revised, _ in CASES:
            for uncertain in ('"' + revised + '"', "If approved, " + revised,
                              "Example: " + revised, "假设 " + revised):
                with self.subTest(query=query, uncertain=uncertain), MemoryBook(
                        ":memory:", segmentation="turn", cache_size=0) as book:
                    book.ingest(source("initial", initial))
                    book.ingest(source("uncertain", uncertain, newer=True))
                    book.ingest(source("foreign", revised, newer=True, project="workers-copy"))
                    result = book.recall(query, project="workers", limit=1)
                    self.assertEqual(first(result), "initial")
                    self.assertTrue(all(ref["project"] == "workers" for page in result["results"]
                                        for ref in page["source_refs"]))

    def test_other_qualified_names_and_history_are_not_changed_into_current_evidence(self):
        _, query, initial, revised, _ = CASES[1]
        with MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
            book.ingest(source("initial", initial))
            book.ingest(source("revised", revised, newer=True))
            book.ingest(source("other", "previous.phase_size is 99.", newer=True))
            self.assertEqual(first(book.recall(query, project="workers", limit=1)), "revised")
            historical = book.recall("original current.phase_size", project="workers", limit=1)
            self.assertEqual(first(historical), "initial")
            self.assertEqual(historical["temporal"]["resolved"], "relevance")

    def test_previous_result_cache_cannot_hide_the_repaired_revision(self):
        for _, query, initial, revised, _ in CASES:
            with self.subTest(query=query), MemoryBook(":memory:", segmentation="turn") as book:
                book.ingest(source("initial", initial))
                book.ingest(source("revised", revised, newer=True))
                with patch.object(store, "RECALL_VERSION", 26), patch.object(
                        store, "_literal_prose_identifier", return_value=False):
                    prior = book.recall(query, project="workers", limit=1)
                self.assertEqual(first(prior), "initial")
                current = book.recall(query, project="workers", limit=1)
                self.assertFalse(current["cache_hit"])
                self.assertEqual(first(current), "revised")
                self.assertTrue(book.recall(query, project="workers", limit=1)["cache_hit"])


if __name__ == "__main__":
    unittest.main()
