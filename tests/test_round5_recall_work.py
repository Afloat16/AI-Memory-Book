"""Exactness checks for avoiding repeated route and accepted-block work."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import itertools
import random
import string
import sys
import unittest

from memory_book import MemoryBook
from memory_book import token_budget as budget


class CompleteCounter:
    """Keep complete-context counting outside the optimized certificate."""
    def __init__(self, name):
        self.original = budget.TokenCounter(name)

    def count(self, text):
        return self.original.count(text)

    def count_after(self, prefix):
        return self.original.count_after(prefix)


@contextmanager
def observed_counts():
    calls = []
    previous = sys.getprofile()

    def observe(frame, event, _):
        if event == "call" and frame.f_code is budget._ORDINARY_COUNT.__code__:
            calls.append(frame.f_locals["text"])

    sys.setprofile(observe)
    try:
        yield calls
    finally:
        sys.setprofile(previous)


def fixture(identity, text):
    row = {"id": identity, "project_id": "fixture", "session_id": identity,
           "created_at": "2026-11-14T00:00:00Z", "content": text,
           "token_source_units": budget.source_units(text)}
    header = f'[{identity}] fixture / {identity} | {row["created_at"]}\n'
    return row, header, text, [(0, len(text))]


@unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Install .[tokens]")
class AcceptedCountReuseTests(unittest.TestCase):
    def test_suffix_certificate_preserves_complete_token_ids_for_both_patterns(self):
        rng = random.Random(48115)
        prefixes = ["[page]", "English words café", "中文İＡßé", "e\u0301",
                    "👩🏽‍💻", "\r\n", "混合\n", "Приветहिन्दीعربي"]
        endings = ["", ".", ",", ";", "'", '"', "!", "?", ":", "...", "!?",
                   "\r\n", "\n\n", "\t ", " ", "\t\r\n .)\n",
                   "_./:-[]{}", "<|endoftext|>"]
        words = ["a", "A", "1", "can't", "I'm", "we're", "O'BRIEN", "123"]
        samples = [prefix + word + tail
                   for prefix, word, tail in itertools.product(prefixes, words, endings)]
        samples += ["[page] " + "".join(rng.choices(string.printable, k=rng.randrange(1, 150)))
                    for _ in range(5000)]
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            self.assertTrue(budget._can_seal_blocks(counter))
            encode = counter.encoding.encode_ordinary
            certified = 0
            for block in samples:
                suffix = budget._ascii_sealing_suffix(block)
                if suffix is None:
                    continue
                prefix = block[:-len(suffix)] if suffix else block
                self.assertEqual(encode(block), encode(prefix) + encode(suffix),
                                 (name, repr(block)))
                self.assertEqual(encode(block + "\n\n"),
                                 encode(prefix) + encode(suffix + "\n\n"),
                                 (name, repr(block)))
                certified += 1
            self.assertEqual(certified, 6152)

    def test_uncertified_unicode_and_long_tails_keep_full_counting(self):
        for block in ("", "...", "alphaé.", "alpha\u0301.", "alpha。",
                      "alpha\u200d", "alpha\ud800", "alpha" + "." * 65):
            self.assertIsNone(budget._ascii_sealing_suffix(block), repr(block))
        self.assertEqual(budget._ascii_sealing_suffix("alpha" + "." * 64), "." * 64)
        self.assertEqual(budget._ascii_sealing_suffix("café x."), ".")
        entries = [fixture("one", "Complete evidence with a non-ASCII ending é." * 8),
                   fixture("two", "Other evidence." * 8)]
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            block = entries[0][1] + entries[0][2]
            cap = counter.count(block) + 30
            with observed_counts() as calls:
                budget.assemble_with_count(entries, [], [], budget_chars=8000,
                                           budget_tokens=cap, counter=counter)
            self.assertIn(block, calls)
            self.assertIn(block + "\n\n", calls)

    def test_known_accepted_counts_do_not_reencode_complete_blocks(self):
        entries = [fixture("one", "A substantial source sentence. " * 8),
                   fixture("two", "Another source sentence. " * 8)]
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            blocks = [entry[1] + entry[2] for entry in entries]
            cap = counter.count("\n\n".join(blocks))
            self.assertLess(cap, len(blocks[0].encode()))
            expected = budget.assemble_with_count(entries, [], [], budget_chars=8000,
                        budget_tokens=cap, counter=CompleteCounter(name))
            with observed_counts() as calls:
                actual = budget.assemble_with_count(entries, [], [], budget_chars=8000,
                            budget_tokens=cap, counter=counter)
            self.assertEqual(actual, expected)
            self.assertEqual(len(actual[0]), 2)
            self.assertEqual(actual[1], cap)
            self.assertIn(blocks[0], calls)
            self.assertNotIn(blocks[0] + "\n\n", calls)

    def test_budget_edges_supplemental_spans_and_full_fallback_remain_identical(self):
        entries = [fixture("one", "Pressure is 82.\r\nRetry remains 45 seconds. " * 3),
                   fixture("two", "We've retained O'BRIEN's value 123.\n" * 5),
                   fixture("three", "café e\u0301 中文 👩🏽‍💻 <|endoftext|>.\n" * 5),
                   fixture("four", "```python\nretry = 45\n```\nQualification remains.")]
        pages = [entry[0] for entry in entries]
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            first_count = counter.count(entries[0][1] + entries[0][2])
            for chars, tokens in itertools.product((0, 128, 800, 8000),
                    (0, 1, first_count - 1, first_count, first_count + 1, 128, 256, 512, 100000)):
                options = {"budget_chars": chars, "budget_tokens": tokens}
                expected = budget.assemble_with_count(entries, pages, ["retry", "pressure"],
                            counter=CompleteCounter(name), **options)
                actual = budget.assemble_with_count(entries, pages, ["retry", "pressure"],
                            counter=counter, **options)
                self.assertEqual(actual, expected, (name, chars, tokens))
                context = "\n\n".join(head + text for _, head, text, _ in actual[0])
                self.assertEqual(actual[1], counter.count(context))
                self.assertLessEqual(actual[1], tokens)


class EqualRouteScoreTests(unittest.TestCase):
    def test_equal_routes_keep_the_exact_raw_bm25_scale(self):
        with MemoryBook(":memory:", cache_size=0, segmentation="turn") as book:
            for number, text in enumerate(("Quartz pressure 82.", "Quartz quartz pressure 90.",
                                          "Quartz is archived with unrelated detail.")):
                book.ingest({"project": "fixture", "session_id": str(number),
                             "title": "Record", "created_at": "2026-11-14T00:00:00Z",
                             "messages": [{"role": "user", "content": text}]})
            expression = '("quartz") AND body : ("quartz")'
            routes = []
            for table in ("pages_fts", "pages_stem_fts"):
                routes.append(book.db.execute(f"SELECT p.id,bm25({table},2.0,2.0,1.0,0.25) rank "
                    f"FROM {table} JOIN pages p ON p.rid={table}.rowid WHERE {table} MATCH ? "
                    "ORDER BY rank,p.id LIMIT 96", (expression,)).fetchall())
            self.assertEqual([row["id"] for row in routes[0]], [row["id"] for row in routes[1]])
            result = book.recall("quartz", project="fixture", limit=50, use_cache=False)
            self.assertEqual([(row["id"], row["score"]) for row in result["results"]],
                             [(row["id"], -row["rank"]) for row in routes[0]])


if __name__ == "__main__":
    unittest.main()
