"""Generic current-configuration evidence under crowded and small budgets.

These queue/service fixtures contain no engineering-workload cases or labels.
"""

from __future__ import annotations

import importlib.util
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.store import _field_identity, _PROSE_BINDING


def record(name, date, text, *, project="workers", task="retry"):
    return {"project": project, "session_id": name, "task_id": task,
            "title": "Worker retry settings", "created_at": f"2026-{date}T00:00:00Z",
            "messages": [{"role": "user", "content": "Configure worker settings"},
                         {"role": "assistant", "content": text}]}


def seed(book, *, prose=False):
    first = book.ingest(record("initial", "01-01", "Current contract: retry_limit=3. " + "retry_limit. " * 12))
    book.ingest(record("middle", "02-01", "Current contract: retry_limit=5."))
    book.ingest(record("approved", "03-01", "Retry limit is now 7." if prose
                       else "Approved configuration: retry_limit=7. "
                            "Requests beyond this limit return a retryable error."))
    for index in range(2):
        book.ingest(record(f"maintenance-{index}", f"04-0{index + 1}",
                           "Reviewed retry_limit during routine worker maintenance. "
                           + "Checked service documentation and deployment notes. " * 7
                           + f"Review batch {index}. No setting was chosen."))
    return first["chapter_id"]


def session_ids(result):
    return [hit["source_refs"][0]["session_id"] for hit in result["results"]]


class CurrentDeclarationRecallTests(unittest.TestCase):
    def assert_original_sources(self, book, result):
        for hit in result["results"]:
            page = book.read(hit["id"], limit=100000)["content"]
            for ref in hit["source_refs"]:
                source = book.db.execute(
                    "SELECT t.content FROM turns t JOIN sessions s ON s.id=t.session_pk "
                    "WHERE s.project_id=? AND s.external_id=? AND t.ordinal=?",
                    (ref["project"], ref["session_id"], ref["turn_index"])).fetchone()[0]
                self.assertEqual(page[ref["start"]:ref["end"]], source[ref["turn_start"]:ref["turn_end"]])

    def test_current_setting_precedes_later_mentions_and_survives_whole_blocks(self):
        with MemoryBook(":memory:") as book:
            seed(book)
            result = book.recall("current retry_limit", project="workers", limit=5, budget_chars=100000)
            self.assertEqual(session_ids(result)[0], "approved")
            self.assertEqual(len(result["results"]), 5)
            self.assertEqual(result["candidate_count"], 5)
            self.assert_original_sources(book, result)
            # An independent whole-block consumer: no gold-aware truncation or
            # body rewriting, and the same order that a caller actually sees.
            blocks = []
            for hit in result["results"]:
                block = f"[{hit['id']}]\n" + hit["text"]
                if len("\n\n".join([*blocks, block])) <= 1200:
                    blocks.append(block)
            self.assertIn("retry_limit=7", "\n\n".join(blocks))
            for budget in (1200, 2400):
                native = book.recall("current retry_limit", project="workers", budget_chars=budget)
                self.assertIn("retry_limit=7", native["context"])
                self.assertLessEqual(len(native["context"]), budget)
                self.assert_original_sources(book, native)

    def test_latest_prose_remains_a_revision_after_two_assignments(self):
        with MemoryBook(":memory:") as book:
            seed(book, prose=True)
            for query in ("current retry_limit", "current retry limit", "当前 RetryLimit"):
                with self.subTest(query=query):
                    result = book.recall(query, project="workers", limit=1, budget_chars=600)
                    self.assertEqual(session_ids(result), ["approved"])
                    self.assertIn("is now 7", result["context"])
                    self.assertEqual(result["temporal"]["declaration_ordering"]["declaration_candidates"], 3)

    def test_aliases_match_but_word_and_qualified_boundaries_are_not_erased(self):
        self.assertEqual(_field_identity("RetryLimit"), _field_identity("retry_limit"))
        for left, right, query in (("a_bc", "ab_c", "a_bc ab_c"),
                                   ("a_bc", "bc", "bc"),
                                   ("user.id", "user_id", "user id")):
            with self.subTest(left=left, right=right), MemoryBook(":memory:") as book:
                self.assertNotEqual(_field_identity(left), _field_identity(right))
                book.ingest(record("stronger", "01-01", f"Selected {left}=3. " + (left + ". ") * 12))
                book.ingest(record("other-field", "04-01", f"Selected {right}=9."))
                relevant = book.recall(query, project="workers", temporal="relevance", limit=2)
                current = book.recall(query, project="workers", temporal="current", limit=2)
                self.assertEqual(session_ids(current), session_ids(relevant))
            with MemoryBook(":memory:") as book:
                book.ingest(record("before", "01-01", "Selected RetryLimit=3. " + "RetryLimit. " * 12))
                book.ingest(record("after", "04-01", "Selected retry_limit=7."))
                result = book.recall("current retry limit", project="workers", limit=1)
                self.assertEqual(session_ids(result), ["after"])

    def test_comparisons_examples_and_quoted_code_do_not_replace_plain_prose(self):
        examples = (
            "assert retry_limit == 999", "retry_limit != 999", "retry_limit <= 999",
            "Example: retry_limit=999", "```python\nretry_limit=999\n```",
            "The previous log contained \"retry_limit=999\".",
            "The previous log contained \"stale settings. retry_limit=999\".",
            "The previous log contained \"stale settings\nretry_limit=999\".",
            "Run `myapp --retry_limit=999` to reproduce the outdated configuration.",
            "Run `old settings. retry_limit=999` to reproduce the outdated configuration.",
            "Run ``old settings\nretry_limit=999`` to reproduce the outdated configuration.",
            "Should retry_limit=999？",
        )
        for text in examples:
            with self.subTest(text=text), MemoryBook(":memory:") as book:
                book.ingest(record("approved", "01-01", "Retry limit is now 3. " + "retry limit. " * 12))
                book.ingest(record("quoted-or-example", "04-01", text))
                result = book.recall("current retry limit", project="workers", limit=1)
                self.assertEqual(session_ids(result), ["approved"])
                diagnostic = result["temporal"].get("declaration_ordering")
                if diagnostic:
                    self.assertEqual(diagnostic["declaration_candidates"], 1)

    def test_first_continuation_cannot_claim_a_complete_declaration(self):
        with MemoryBook(":memory:", max_page_chars=128, min_page_chars=0, cache_size=0) as book:
            book.ingest(record("approved", "01-01", "retryLimit=3"))
            book.ingest(record("incomplete", "02-01", "retry limit is 999 " + "pending " * 80 + "not accepted"))
            result = book.recall("current retryLimit", project="workers", limit=1, budget_chars=1200)
            self.assertEqual(session_ids(result), ["approved"])
            self.assertIn("retryLimit=3", result["context"])
            self.assert_original_sources(book, result)

    def test_relevance_history_and_occurrence_paths_keep_their_existing_behavior(self):
        with MemoryBook(":memory:") as book:
            seed(book)
            for query in ("retry_limit", "original retry_limit", "current retry_limit as of 2026"):
                result = book.recall(query, project="workers", limit=5)
                explicit = book.recall(query, project="workers", temporal="relevance", limit=5)
                self.assertEqual(result["results"], explicit["results"])
                self.assertNotIn("declaration_ordering", result["temporal"])
            for ending in ("how many times", "event timeline", "出现次数"):
                result = book.recall("current retry_limit " + ending, project="workers", limit=5,
                                     budget_chars=100000)
                self.assertEqual(set(session_ids(result)),
                                 {"initial", "middle", "approved", "maintenance-0", "maintenance-1"})
                self.assertNotIn("declaration_ordering", result["temporal"])

    def test_query_qualifiers_and_explicit_scopes_are_preserved(self):
        with MemoryBook(":memory:") as book:
            chapter = seed(book)
            book.ingest(record("foreign", "06-01", "retry_limit=999", project="other"))
            book.ingest(record("other-task", "06-01", "retry_limit=88", task="another"))
            result = book.recall("current retry_limit", project="workers", chapter=chapter, limit=1)
            self.assertEqual(session_ids(result), ["approved"])
            original = book.recall("current retry_limit", project="workers", session="initial", limit=1)
            self.assertEqual(session_ids(original), ["initial"])
            self.assert_original_sources(book, result)
        with MemoryBook(":memory:") as book:
            book.ingest(record("production", "01-01", "Production retry_limit=3. " + "production retry_limit. " * 10))
            book.ingest(record("staging", "06-01", "Staging retry_limit=9."))
            result = book.recall("current production retry_limit", project="workers", limit=1)
            self.assertEqual(session_ids(result), ["production"])

    def test_cache_keeps_modes_and_invalidates_after_a_new_revision(self):
        with MemoryBook(":memory:") as book:
            seed(book)
            for mode in ("auto", "current", "relevance"):
                first = book.recall("current retry_limit", temporal=mode, project="workers", limit=1)
                cached = book.recall("current retry_limit", temporal=mode, project="workers", limit=1)
                self.assertFalse(first["cache_hit"])
                self.assertTrue(cached["cache_hit"])
                self.assertEqual(first["context"], cached["context"])
            book.ingest(record("approved", "06-01", "Approved configuration: retry_limit=2."))
            result = book.recall("current retry_limit", project="workers", limit=1)
            self.assertFalse(result["cache_hit"])
            self.assertIn("retry_limit=2", result["context"])

    def test_field_and_text_limits_preserve_candidates_with_a_diagnostic(self):
        with MemoryBook(":memory:", segmentation="session", cache_size=0) as book:
            book.ingest(record("many", "01-01", " ".join(f"max_field_{i}=3;" for i in range(65))))
            book.ingest(record("later", "02-01", "Mentioned max during routine review."))
            result = book.recall("current max", project="workers", limit=2, budget_chars=100000)
            self.assertEqual(set(session_ids(result)), {"many", "later"})
            self.assertIn("exceeded 64", result["temporal"]["declaration_ordering"]["basis"])
        with MemoryBook(":memory:", segmentation="session", cache_size=0) as book:
            book.ingest(record("large", "01-01", "max_limit=3; " + "pending " * 9000))
            book.ingest(record("later", "02-01", "Mentioned max during routine review."))
            result = book.recall("current max", project="workers", limit=2, budget_chars=100000)
            self.assertEqual(set(session_ids(result)), {"large", "later"})
            self.assertEqual(result["temporal"]["declaration_ordering"]["oversized_candidates"], 1)
        # Punctuation-heavy identifiers cannot restart a greedy scan at every
        # internal separator; this is a pathological input, not a timing score.
        for separator in (".", "-"):
            self.assertEqual(list(_PROSE_BINDING.finditer(("a" + separator) * 16000)), [])

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "optional real tokenizers are not installed")
    def test_exact_token_caps_preserve_the_selected_setting_and_sources(self):
        from memory_book.token_budget import TokenCounter
        with MemoryBook(":memory:") as book:
            seed(book, prose=True)
            for tokenizer in ("cl100k_base", "o200k_base"):
                result = book.recall("current retry_limit", project="workers", limit=1,
                                     budget_chars=1200, budget_tokens=100, tokenizer=tokenizer)
                self.assertIn("is now 7", result["context"])
                self.assertLessEqual(TokenCounter(tokenizer).count(result["context"]), 100)
                self.assert_original_sources(book, result)

    def test_semantic_fusion_uses_the_same_declaration_comparability(self):
        from tests.test_semantic import FixtureEncoder
        with MemoryBook(":memory:", semantic_model_dir="/fixture") as book:
            book._semantic_model = FixtureEncoder()
            seed(book, prose=True)
            book.build_semantic_index()
            rows = [dict(row) for row in book.db.execute(
                "SELECT p.id,p.rid,p.project_id,p.chapter_id,c.title chapter_title,"
                "s.external_id session_id,s.title session_title,s.created_at "
                "FROM pages p JOIN chapters c ON c.id=p.chapter_id "
                "JOIN sessions s ON s.id=p.session_pk ORDER BY s.created_at DESC")]
            with patch("memory_book.semantic.rank_pages", return_value=[
                {**row, "semantic_similarity": 1 - i / 10} for i, row in enumerate(rows)]):
                result = book.recall("current retry_limit", project="workers", limit=3,
                                     budget_chars=2400, semantic=True)
            self.assertEqual(session_ids(result)[0], "approved")
            self.assert_original_sources(book, result)


if __name__ == "__main__":
    unittest.main()
