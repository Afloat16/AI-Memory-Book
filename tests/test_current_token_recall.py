"""Current evidence stays source-bounded when only the token cap truncates it."""

from __future__ import annotations

import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book.token_budget import TokenCounter, prepare_source_units
from tests.test_current_turn_recall import same_page_session


QUERY = "current gradient accumulation steps"
TOKENIZERS = ("cl100k_base", "o200k_base")


@unittest.skipUnless(find_spec("tiktoken"), "the optional real tokenizers are not installed")
class CurrentTokenRecallTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:")
        self.addCleanup(self.book.close)
        self.assertEqual(self.book.ingest(same_page_session())["pages"], 1)

    def recall(self, name, cap, **options):
        return self.book.recall(QUERY, project="trainer", limit=1, budget_chars=4000,
                                budget_tokens=cap, tokenizer=name, use_cache=False, **options)

    def assert_source_spans(self, book, result):
        self.assertEqual(result["context_chars"], len(result["context"]))
        self.assertLessEqual(result["context_chars"], result["budget_chars"])
        self.assertEqual(result["context_tokens"],
                         TokenCounter(result["tokenizer"]).count(result["context"]))
        self.assertLessEqual(result["context_tokens"], result["budget_tokens"])
        for hit in result["results"]:
            page = book.read(hit["id"], limit=100000)["content"]
            self.assertEqual(len(hit["excerpt_spans"]), 1)
            start, end = hit["excerpt_spans"][0]
            self.assertEqual(hit["text"], ("…" if start else "") + page[start:end]
                             + ("…" if end < len(page) else ""))
            for ref in hit["source_refs"]:
                original = book.db.execute(
                    "SELECT content FROM turns WHERE ordinal=? AND session_pk="
                    "(SELECT id FROM sessions WHERE project_id=? AND external_id=?)",
                    (ref["turn_index"], ref["project"], ref["session_id"])).fetchone()[0]
                self.assertEqual(page[ref["start"]:ref["end"]],
                                 original[ref["turn_start"]:ref["turn_end"]])

    def test_token_only_truncation_does_not_revert_as_budget_increases(self):
        full = self.book.recall(QUERY, project="trainer", limit=1, budget_chars=4000,
                                use_cache=False)
        page = self.book.read(full["results"][0]["id"])
        latest = next(ref for ref in page["source_refs"] if ref["turn_index"] == 1)
        header = full["context"].split("\n", 1)[0] + "\n"
        preferred = "…" + page["content"][latest["start"]:latest["end"]]
        for name in TOKENIZERS:
            counter = TokenCounter(name)
            latest_cap = counter.count(header + preferred)
            full_cap = counter.count(full["context"])
            self.assertLess(latest_cap, 90)
            self.assertLess(90, full_cap)
            for cap in (latest_cap, latest_cap + 5, 90, full_cap - 1):
                with self.subTest(tokenizer=name, cap=cap):
                    result = self.recall(name, cap)
                    self.assertIn("steps are now 2", result["context"])
                    self.assertIn("no longer valid", result["context"])
                    self.assertNotIn("steps are 8", result["context"])
                    self.assertEqual({ref["turn_index"] for hit in result["results"]
                                      for ref in hit["source_refs"]}, {1})
                    self.assert_source_spans(self.book, result)

    def test_generous_token_cap_preserves_complete_current_page(self):
        full = self.book.recall(QUERY, project="trainer", limit=1, budget_chars=4000,
                                use_cache=False)
        for name in TOKENIZERS:
            for cap in (TokenCounter(name).count(full["context"]), 100000):
                with self.subTest(tokenizer=name, cap=cap):
                    result = self.recall(name, cap)
                    self.assertEqual(result["context"], full["context"])
                    self.assertEqual(result["results"], full["results"])
                    self.assert_source_spans(self.book, result)

    def test_tiny_token_caps_never_backfill_an_obsolete_turn(self):
        for name in TOKENIZERS:
            for cap in (0, 1, 32, 45, 60):
                with self.subTest(tokenizer=name, cap=cap):
                    result = self.recall(name, cap)
                    self.assertTrue(all(ref["turn_index"] == 1 for hit in result["results"]
                                        for ref in hit["source_refs"]))
                    self.assertNotIn("steps are 8", result["context"])
                    self.assert_source_spans(self.book, result)

    def test_ordinary_and_historical_queries_keep_existing_token_selection(self):
        for name in TOKENIZERS:
            for query in ("gradient accumulation steps", "original gradient accumulation steps",
                          "current gradient accumulation steps as of 2026"):
                with self.subTest(tokenizer=name, query=query):
                    result = self.book.recall(query, project="trainer", limit=1,
                                              budget_chars=4000, budget_tokens=90,
                                              tokenizer=name, use_cache=False)
                    self.assertIn("steps are 8", result["context"])
                    self.assertEqual({ref["turn_index"] for hit in result["results"]
                                      for ref in hit["source_refs"]}, {0})
                    self.assert_source_spans(self.book, result)

    def test_selected_page_without_character_allocation_uses_current_units(self):
        leading = same_page_session()
        leading["session_id"] = "🦄" * 50
        leading["created_at"] = "2026-12-01T00:00:00Z"
        leading["messages"] = [{"role": "assistant", "content":
                                "Gradient accumulation steps maintenance. "
                                + "gradient accumulation steps. " * 12}]
        self.book.ingest(leading)
        char_only = self.book.recall(QUERY, project="trainer", limit=2, budget_chars=400,
                                     use_cache=False)
        # The first page's header/body reservation leaves no allocation for s1.
        # Its Unicode header then exceeds the token cap, freeing space for s1.
        self.assertEqual(len(char_only["results"]), 1)
        self.assertEqual(char_only["results"][0]["source_refs"][0]["session_id"], leading["session_id"])
        for name in TOKENIZERS:
            with self.subTest(tokenizer=name):
                result = self.book.recall(QUERY, project="trainer", limit=2, budget_chars=400,
                                          budget_tokens=90, tokenizer=name, use_cache=False)
                self.assertIn("steps are now 2", result["context"])
                self.assertEqual({(ref["session_id"], ref["turn_index"])
                                  for hit in result["results"] for ref in hit["source_refs"]}, {("s1", 1)})
                self.assert_source_spans(self.book, result)

    def test_previous_accepted_block_does_not_reopen_old_turn_units(self):
        leading = same_page_session()
        leading["session_id"] = "maintenance"
        leading["created_at"] = "2026-12-01T00:00:00Z"
        leading["messages"] = [{"role": "assistant", "content":
                                "Gradient accumulation steps need a source check."}]
        self.book.ingest(leading)
        full = self.book.recall(QUERY, project="trainer", limit=2, budget_chars=4000,
                                use_cache=False)
        self.assertEqual(len(full["results"]), 2)
        self.assertEqual(full["results"][0]["source_refs"][0]["session_id"], "maintenance")
        for name in TOKENIZERS:
            with self.subTest(tokenizer=name):
                cap = TokenCounter(name).count(full["context"]) - 1
                result = self.book.recall(QUERY, project="trainer", limit=2, budget_chars=4000,
                                          budget_tokens=cap, tokenizer=name, use_cache=False)
                self.assertIn("need a source check", result["context"])
                self.assertIn("steps are now 2", result["context"])
                self.assertEqual({ref["turn_index"] for hit in result["results"]
                                  for ref in hit["source_refs"] if ref["session_id"] == "s1"}, {1})
                self.assert_source_spans(self.book, result)

    def test_incomplete_original_turn_does_not_certify_a_current_span(self):
        self.book.db.execute("UPDATE turns SET content=content || ? WHERE ordinal=1",
                             (" Additional qualification outside this page.",))
        for name in TOKENIZERS:
            with self.subTest(tokenizer=name):
                result = self.recall(name, 90)
                ordinary = self.book.recall("gradient accumulation steps", project="trainer", limit=1,
                                            budget_chars=4000, budget_tokens=90, tokenizer=name,
                                            use_cache=False)
                self.assertEqual(result["context"], ordinary["context"])
                self.assertEqual(result["results"], ordinary["results"])
                self.assert_source_spans(self.book, result)

    def test_current_token_scope_and_cache_follow_the_actual_project(self):
        other = same_page_session()
        other["project"] = "another-trainer"
        other["messages"][3]["content"] = other["messages"][3]["content"].replace("now 2", "now 4")
        self.book.ingest(other)
        for name in TOKENIZERS:
            for project, value in (("trainer", "2"), ("another-trainer", "4")):
                with self.subTest(tokenizer=name, project=project):
                    options = dict(project=project, limit=1, budget_chars=4000,
                                   budget_tokens=90, tokenizer=name)
                    result = self.book.recall(QUERY, **options)
                    self.assertIn("steps are now " + value, result["context"])
                    self.assertEqual({ref["project"] for hit in result["results"]
                                      for ref in hit["source_refs"]}, {project})
                    cached = self.book.recall(QUERY, **options)
                    self.assertTrue(cached["cache_hit"])
                    self.assertEqual(cached["context"], result["context"])
                    self.assertEqual(cached["results"], result["results"])
                    self.assert_source_spans(self.book, result)

    def test_current_code_fence_is_not_reinterpreted_as_partial_sentences(self):
        source = same_page_session()
        source["messages"][3]["content"] = (
            "```python\n# Gradient accumulation steps\nsteps = 2\n"
            + "checked_value = 123456789\n" * 30 + "```\nThe old value is invalid.")
        with MemoryBook(":memory:", segmentation="session") as book:
            self.assertEqual(book.ingest(source)["pages"], 1)
            for name in TOKENIZERS:
                with self.subTest(tokenizer=name):
                    result = book.recall(QUERY, project="trainer", limit=1, budget_chars=4000,
                                          budget_tokens=90, tokenizer=name, use_cache=False)
                    self.assertTrue(result["results"])
                    self.assertEqual({ref["turn_index"] for hit in result["results"]
                                      for ref in hit["source_refs"]}, {1})
                    self.assertNotIn("steps = 2", result["context"])
                    self.assertNotIn("```", result["context"])
                    self.assert_source_spans(book, result)

    def test_current_token_sources_remain_in_the_read_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "current.db"
            with MemoryBook(path, cache_size=0) as reader, MemoryBook(path, cache_size=0) as writer:
                reader.ingest(same_page_session())
                options = dict(project="trainer", limit=1, budget_chars=4000,
                               budget_tokens=90, use_cache=False)
                expected = reader.recall(QUERY, **options)
                self.assertIn("steps are now 2", expected["context"])
                state = {"written": False, "resolving": False}
                late_reads = []

                def trace(statement):
                    if state["resolving"]:
                        late_reads.append(statement)

                def prepare(rows, turns, refs):
                    resolve = prepare_source_units(rows, turns, refs)

                    def after_commit(row):
                        self.assertFalse(reader.db.in_transaction)
                        state["resolving"] = True
                        if not state["written"]:
                            changed = same_page_session()
                            changed["messages"][3]["content"] = changed["messages"][3]["content"].replace("now 2", "now 3")
                            writer.ingest(changed)
                            state["written"] = True
                        return resolve(row)

                    return after_commit

                reader.db.set_trace_callback(trace)
                with patch("memory_book.token_budget.prepare_source_units", prepare):
                    result = reader.recall(QUERY, **options)
                reader.db.set_trace_callback(None)
                self.assertTrue(state["written"])
                self.assertEqual(late_reads, [])
                self.assertEqual({key: value for key, value in result.items() if key != "latency_ms"},
                                 {key: value for key, value in expected.items() if key != "latency_ms"})
                self.assertIn("steps are now 3", reader.recall(QUERY, **options)["context"])


if __name__ == "__main__":
    unittest.main()
