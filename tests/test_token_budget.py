from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book.store import MemoryBook
from memory_book.token_budget import projected_units, source_units


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None


def sample(session="release", text=None):
    return {"project": "lab", "session_id": session,
            "created_at": "2026-01-02T00:00:00Z", "task_id": session,
            "messages": [
                {"role": "user", "content": "Which release pressure and retry delay were chosen?"},
                {"role": "assistant", "content": text or (
                    "The release pressure is 82 pascals. The retry delay is 45 seconds.\n" +
                    "Additional background information remains available for inspection. " * 30)},
            ]}


class SourceUnitTests(unittest.TestCase):
    def test_role_prefixed_text_inside_code_does_not_close_fence(self):
        text = 'USER: Give the example.\n\nASSISTANT: ```python\nvalue = 82\nUSER: ```\nretry = 45\n```\nOutside statement.'
        start = text.index("ASSISTANT: ```")
        end = text.index("\nOutside")
        for lo, hi in source_units(text):
            if max(lo, start) < min(hi, end):
                self.assertLessEqual(lo, start)
                self.assertGreaterEqual(hi, end)
        self.assertIn((start, end), source_units(text))

    def test_shorter_or_different_fence_cannot_close_block(self):
        text = 'ASSISTANT: ````python\nx = 1\n```\n~~~\ny = 2\n````'
        self.assertEqual(source_units(text), [(0, len(text))])

    def test_unclosed_code_is_not_offered_as_supplement(self):
        text = 'USER: Show pressure.\n\nASSISTANT: ```python\npressure = 82\nUSER: ```'
        for lo, hi in source_units(text):
            self.assertLessEqual(hi, text.index("ASSISTANT: ```"))

    def test_page_cut_inside_code_cannot_turn_it_into_a_sentence(self):
        text = 'ASSISTANT: ```\nfirst = 1\npressure = 82\nretry = 45\n```\n'
        lo, hi = text.index("pressure"), text.index("\n```", text.index("pressure"))
        row = {"session_pk": "s", "content": text[lo:hi], "source_refs": json.dumps([
            {"turn_index": 0, "turn_start": lo, "turn_end": hi,
             "start": 0, "end": hi - lo}])}
        self.assertEqual(projected_units(row, {("s", 0): text}, {}), [])


@unittest.skipUnless(HAS_TOKENS, "Install .[tokens] for exact budget checks")
class TokenBudgetTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=5000,
                               min_page_chars=0)
        self.addCleanup(self.book.close)
        self.book.ingest(sample())

    def test_default_never_initializes_tokenizer_or_adds_token_fields(self):
        with patch("memory_book.token_budget.TokenCounter", side_effect=AssertionError("tokenizer loaded")):
            result = self.book.recall("pressure", use_cache=False)
        self.assertNotIn("budget_tokens", result)
        self.assertNotIn("context_tokens", result)

    def test_both_caps_and_source_spans_for_unicode_and_special_strings(self):
        from memory_book.token_budget import TokenCounter
        self.book.ingest(sample("unicode", "ASSISTANT: café Straße 缓存保留45秒。\n<|endoftext|> is literal evidence.\n" * 12))
        for tokenizer in ("cl100k_base", "o200k_base"):
            counter = TokenCounter(tokenizer)
            for chars in (0, 80, 200, 2000):
                for tokens in (0, 1, 32, 64, 128, 512):
                    with self.subTest(tokenizer=tokenizer, chars=chars, tokens=tokens):
                        result = self.book.recall("pressure retry cafe 缓存 literal", budget_chars=chars,
                                                  budget_tokens=tokens, tokenizer=tokenizer,
                                                  use_cache=False)
                        self.assertEqual(result["context_tokens"], counter.count(result["context"]))
                        self.assertLessEqual(result["context_tokens"], tokens)
                        self.assertLessEqual(len(result["context"]), chars)
                        self.assertEqual(result["context_chars"], len(result["context"]))
                        self.assertEqual(len({r["id"] for r in result["results"]}), len(result["results"]))
                        for item in result["results"]:
                            page = self.book.read(item["id"], limit=100000)["content"]
                            self.assertEqual(len(item["excerpt_spans"]), 1)
                            start, end = item["excerpt_spans"][0]
                            rebuilt = ("…" if start else "") + page[start:end] + ("…" if end < len(page) else "")
                            self.assertEqual(item["text"], rebuilt)
                            self.assertIn(item["text"], result["context"])
                            for ref in item["source_refs"]:
                                original = self.book.db.execute(
                                    "SELECT content FROM turns WHERE ordinal=? AND session_pk=(SELECT id FROM sessions WHERE project_id=? AND external_id=?)",
                                    (ref["turn_index"], ref["project"], ref["session_id"])).fetchone()[0]
                                self.assertEqual(page[ref["start"]:ref["end"]],
                                                 original[ref["turn_start"]:ref["turn_end"]])

    def test_every_old_packed_block_and_metadata_are_preserved(self):
        from benchmarks.token_compare import TokenCounter, evidence_blocks, pack_whole_blocks
        for i, size in enumerate((1, 3, 7, 15)):
            self.book.ingest(sample(f"s-{i}", "Pressure is 82 pascals.\n" + "retry background. " * size))
        for tokenizer in ("cl100k_base", "o200k_base"):
            counter = TokenCounter(tokenizer)
            for chars in (256, 1000, 8000):
                legacy = self.book.recall("pressure retry", budget_chars=chars, use_cache=False)
                for tokens in (32, 64, 128, 256, 512, 1024):
                    packed = pack_whole_blocks(legacy, tokens, counter)
                    result = self.book.recall("pressure retry", budget_chars=chars,
                                              budget_tokens=tokens, tokenizer=tokenizer,
                                              use_cache=False)
                    by_id = {item["id"]: item for item in result["results"]}
                    for block, item in evidence_blocks(packed):
                        self.assertIn(block, result["context"])
                        self.assertEqual(by_id[item["id"]], item)

    def test_small_budget_adds_an_intact_fact_when_full_block_cannot_fit(self):
        from benchmarks.token_compare import TokenCounter, pack_whole_blocks
        legacy = self.book.recall("release pressure", budget_chars=4000, use_cache=False)
        packed = pack_whole_blocks(legacy, 96, TokenCounter("cl100k_base"))
        self.assertEqual(packed["context"], "")
        native = self.book.recall("release pressure", budget_chars=4000, budget_tokens=96)
        self.assertIn("The release pressure is 82 pascals.", native["context"])
        self.assertLessEqual(native["context_tokens"], 96)

    def test_generous_token_budget_preserves_default_context_and_results(self):
        legacy = self.book.recall("pressure", use_cache=False)
        result = self.book.recall("pressure", budget_tokens=100000, use_cache=False)
        self.assertEqual(legacy["context"], result["context"])
        self.assertEqual(legacy["results"], result["results"])

    def test_invalid_token_budgets_and_tokenizers_are_rejected(self):
        for value in (True, False, "512", 512.0, -1, 100001):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "budget_tokens"):
                self.book.recall("pressure", budget_tokens=value)
        for value in ("unknown", "", None, True, 5):
            with self.subTest(tokenizer=value), self.assertRaisesRegex(ValueError, "tokenizer"):
                self.book.recall("pressure", budget_tokens=64, tokenizer=value)

    def test_cache_is_separate_by_budget_and_tokenizer_and_invalidated_by_write(self):
        options = ({}, {"budget_tokens": 64}, {"budget_tokens": 128},
                   {"budget_tokens": 64, "tokenizer": "o200k_base"})
        for extra in options:
            self.assertFalse(self.book.recall("pressure", **extra)["cache_hit"])
            self.assertTrue(self.book.recall("pressure", **extra)["cache_hit"])
        self.book.ingest(sample(text="The release pressure is now 93 pascals."))
        changed = self.book.recall("pressure", budget_tokens=128)
        self.assertFalse(changed["cache_hit"])
        self.assertIn("93 pascals", changed["context"])

    def test_scope_and_top_limit_are_respected(self):
        other = sample("other", "Pressure is 99 pascals. " * 20)
        other["project"] = "secret-other-project"
        self.book.ingest(other)
        result = self.book.recall("pressure", project="lab", session="release",
                                  limit=1, budget_tokens=128)
        self.assertLessEqual(len(result["results"]), 1)
        for item in result["results"]:
            self.assertTrue(all(ref["project"] == "lab" and ref["session_id"] == "release"
                                for ref in item["source_refs"]))

    def test_cli_exposes_exact_count_and_enforces_cap(self):
        from memory_book.token_budget import TokenCounter
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "memory.db"
            with MemoryBook(db) as book:
                book.ingest(sample())
            result = subprocess.run([sys.executable, "-m", "memory_book", "--db", str(db),
                                     "recall", "pressure", "--budget", "1000", "--budget-tokens", "96",
                                     "--tokenizer", "o200k_base", "--json"],
                                    capture_output=True, text=True, check=True)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["context_tokens"], TokenCounter("o200k_base").count(payload["context"]))
            self.assertLessEqual(payload["context_tokens"], 96)
            self.assertEqual(payload["tokenizer"], "o200k_base")


if __name__ == "__main__":
    unittest.main()
