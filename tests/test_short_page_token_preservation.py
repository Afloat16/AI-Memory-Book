"""Real token caps preserve completed short pages and protected current turns."""

from __future__ import annotations

from importlib.util import find_spec
import unittest

from benchmarks.token_compare import evidence_blocks, pack_whole_blocks
from memory_book import MemoryBook
from memory_book.token_budget import TokenCounter
from tests.test_current_turn_recall import same_page_session
from tests.test_token_budget import sample


TOKENIZERS = ("cl100k_base", "o200k_base")


@unittest.skipUnless(find_spec("tiktoken"), "the optional real tokenizers are not installed")
class ShortPageTokenPreservationTests(unittest.TestCase):
    def test_fitting_token_cap_keeps_the_rebalanced_character_context_exactly(self):
        with MemoryBook(":memory:", segmentation="turn", max_page_chars=5000,
                        min_page_chars=0) as book:
            book.ingest(sample())
            for index, size in enumerate((1, 3, 7, 15)):
                book.ingest(sample(f"s-{index}", "Pressure is 82 pascals.\n"
                                   + "retry background. " * size))
            request = dict(query="pressure retry", budget_chars=1000, use_cache=False)
            baseline = book.recall(**request)
            completed = next(hit for hit in baseline["results"]
                             if hit["source_refs"][0]["session_id"] == "s-1")
            self.assertFalse(completed["truncated"])
            self.assertEqual(completed["text"], book.read(completed["id"])["content"])
            for name in TOKENIZERS:
                counter = TokenCounter(name)
                for cap in (counter.count(baseline["context"]), 100000):
                    with self.subTest(tokenizer=name, cap=cap):
                        result = book.recall(**request, budget_tokens=cap, tokenizer=name)
                        self.assertEqual(result["context"], baseline["context"])
                        self.assertEqual(result["results"], baseline["results"])
                        self.assertEqual(result["context_tokens"], counter.count(result["context"]))
                        self.assertLessEqual(result["context_tokens"], cap)

    def test_short_page_completion_keeps_current_turn_and_fitting_legacy_blocks(self):
        with MemoryBook(":memory:") as book:
            book.ingest(same_page_session())
            for session, size in (("memo", 180), ("long", 600)):
                source = same_page_session()
                source["session_id"] = session
                body = ("Gradient accumulation steps require checking the original decision. "
                        + "Supporting administrative detail. " * 30)
                source["messages"] = [{"role": "assistant", "content": body[:size - 11]}]
                book.ingest(source)
            request = dict(query="current gradient accumulation steps", project="trainer",
                           limit=3, budget_chars=750, use_cache=False)
            baseline = book.recall(**request)
            current = next(hit for hit in baseline["results"]
                           if hit["source_refs"][0]["session_id"] == "s1")
            memo = next(hit for hit in baseline["results"]
                        if hit["source_refs"][0]["session_id"] == "memo")
            self.assertEqual({ref["turn_index"] for ref in current["source_refs"]}, {1})
            self.assertIn("steps are now 2", current["text"])
            self.assertFalse(memo["truncated"])
            current_block = next(block for block, hit in evidence_blocks(baseline)
                                 if hit["id"] == current["id"])
            for name in TOKENIZERS:
                counter = TokenCounter(name)
                complete_cap = counter.count(baseline["context"])
                for cap in (counter.count(current_block) - 1, counter.count(current_block),
                            complete_cap - 1, complete_cap, 100000):
                    with self.subTest(tokenizer=name, cap=cap):
                        expected = pack_whole_blocks(baseline, cap, counter)
                        result = book.recall(**request, budget_tokens=cap, tokenizer=name)
                        actual = {hit["id"]: hit for hit in result["results"]}
                        for block, hit in evidence_blocks(expected):
                            self.assertIn(block, result["context"])
                            self.assertEqual(actual[hit["id"]], hit)
                        if current["id"] in actual:
                            self.assertEqual({ref["turn_index"]
                                              for ref in actual[current["id"]]["source_refs"]}, {1})
                        if cap >= complete_cap:
                            self.assertEqual(result["context"], baseline["context"])
                            self.assertEqual(result["results"], baseline["results"])
                        self.assertEqual(result["context_tokens"], counter.count(result["context"]))
                        self.assertLessEqual(result["context_tokens"], cap)
                        self.assertLessEqual(result["context_chars"], request["budget_chars"])


if __name__ == "__main__":
    unittest.main()
