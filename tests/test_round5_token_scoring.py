"""Boundary and source-fidelity regressions for supplemental span scoring."""

from __future__ import annotations

import importlib.util
import itertools
import unittest

from memory_book.text import terms
from memory_book.token_budget import TokenCounter, assemble_with_count


class SupplementalScoringTests(unittest.TestCase):
    def test_display_ellipses_preserve_source_lexical_features(self):
        # Include normalization expansions, combining marks at source cuts,
        # identifiers, CJK question removal, and literal tokenizer syntax.
        # A display boundary must not change the terms used to rank evidence.
        sources = (
            "", "retryDelay_ms is 45.", "_part/Name:42-foo.bar_", ".foo.",
            "Ｃａｆé e\u0301", "\u0301retry", "retry\u0345", "Straße İ ﬃ Ⅳ",
            "缓存是什么容量？保留45秒。", "什么", "👩🏽‍💻 retry", "\r\n retry \t",
            "<|endoftext|> is literal", "...retry...", "…retry…",
            "\ud800retry\udc00", "Ａ．Ｚ/路径", "retry\u200dDelay",
        )
        for source, leading, trailing in itertools.product(sources, ("", "…"), ("", "…")):
            with self.subTest(source=repr(source), leading=leading, trailing=trailing):
                self.assertEqual(terms(leading + source + trailing, query=True),
                                 terms(source, query=True))

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Install .[tokens]")
    def test_ranked_supplement_keeps_original_span_and_exact_budget(self):
        wanted = "Ｃａｆé retryDelay_ms is 45. 缓存保留45秒。"
        irrelevant = "Unrelated background details remain available for inspection."
        source = irrelevant + "\n" + wanted + "\nTrailing source."
        start, end = len(irrelevant) + 1, len(irrelevant) + 1 + len(wanted)
        row = {"id": "evidence", "project_id": "round5", "session_id": "source",
               "created_at": "2026-11-14T00:00:00Z", "content": source,
               "token_source_units": [(0, len(irrelevant)), (start, end)]}
        header = "[evidence] round5 / source | 2026-11-14T00:00:00Z\n"
        text = "…" + wanted + "…"
        for name in ("cl100k_base", "o200k_base"):
            with self.subTest(tokenizer=name):
                counter = TokenCounter(name)
                cap = counter.count(header + text)
                kept, counted = assemble_with_count([], [row], ["cafe", "retry", "缓存", "45"],
                    budget_chars=512, budget_tokens=cap, counter=counter)
                self.assertEqual(kept, [(row, header, text, [(start, end)])])
                self.assertEqual(source[start:end], wanted)
                self.assertEqual(counted, cap)
                self.assertEqual(counted, counter.count(header + kept[0][2]))


if __name__ == "__main__":
    unittest.main()
