from __future__ import annotations

import importlib.util
import unittest

from memory_book.token_budget import TokenCounter, assemble


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None


class _FallbackEncoding:
    def __init__(self, stable_bytes):
        self.stable_bytes = stable_bytes
        self.encoded = []

    def encode_with_unstable(self, text, **kwargs):
        return [1, 2, 3], []

    def decode_bytes(self, tokens):
        return self.stable_bytes

    def encode_ordinary(self, text):
        self.encoded.append(text)
        return [0] * len(text.encode("utf-8"))


class _PreparedCount:
    def __init__(self, owner, minimum_tokens):
        self.owner = owner
        self.minimum_tokens = minimum_tokens

    def __call__(self, text):
        self.owner.suffixes.append(text)
        if self.owner.prepared_result is None:
            raise AssertionError("An impossible candidate was encoded")
        return self.owner.prepared_result


class _CountingCounter:
    def __init__(self, full_counts, *, minimum_tokens=0, prepared_result=None):
        self.full_counts = list(full_counts)
        self.minimum_tokens = minimum_tokens
        self.prepared_result = prepared_result
        self.full_texts = []
        self.prefixes = []
        self.suffixes = []
        self.events = []

    def count(self, text):
        self.events.append("full")
        self.full_texts.append(text)
        if not self.full_counts:
            raise AssertionError("Unexpected full-context encode")
        return self.full_counts.pop(0)

    def count_after(self, prefix):
        self.events.append("prepare")
        self.prefixes.append(prefix)
        return _PreparedCount(self, self.minimum_tokens)


def page(count=5, identity="supplement"):
    words = [f"unit{i:04d}" for i in range(count)]
    text = "\n".join(words)
    units, offset = [], 0
    for word in words:
        units.append((offset, offset + len(word)))
        offset += len(word) + 1
    return {"id": identity, "project_id": "p", "session_id": "s",
            "created_at": "2026-01-01T00:00:00Z", "content": text,
            "token_source_units": units}


class PrefixBoundControlFlowTests(unittest.TestCase):
    def run_assembly(self, row, counter, legacy=None):
        entries = legacy or []
        pages = [entry[0] for entry in entries] + [row]
        return assemble(entries, pages, [], budget_chars=10000,
                        budget_tokens=10, counter=counter)

    def test_invalid_stable_bytes_keep_zero_bound_and_full_fallback(self):
        # A partial UTF-8 code point exercises decode failure; a decodable but
        # incorrect prefix exercises the separate byte-prefix guard.
        for prefix, stable_bytes in (("é header\n", b"\xc3"),
                                     ("header\n", b"wrong")):
            with self.subTest(prefix=prefix, stable_bytes=stable_bytes):
                counter = TokenCounter.__new__(TokenCounter)
                counter.encoding = _FallbackEncoding(stable_bytes)
                prepared = counter.count_after(prefix)
                self.assertEqual(prepared.minimum_tokens, 0)
                suffix = "缓存 <|endoftext|>"
                self.assertEqual(prepared(suffix),
                                 len((prefix + suffix).encode("utf-8")))
                self.assertEqual(counter.encoding.encoded, [prefix + suffix])

    def test_first_choice_success_never_prepares_a_prefix(self):
        counter = _CountingCounter([10])
        result = self.run_assembly(page(), counter)
        self.assertEqual(len(result), 1)
        self.assertEqual(counter.events, ["full"])
        self.assertEqual(counter.prefixes, [])
        self.assertEqual(counter.suffixes, [])

    def test_short_failed_lists_keep_full_context_counts(self):
        for count in (1, 3):
            with self.subTest(count=count):
                counter = _CountingCounter([11] * count)
                self.assertEqual(self.run_assembly(page(count), counter), [])
                self.assertEqual(counter.events, ["full"] * count)
                self.assertEqual(counter.prefixes, [])

    def test_preparation_remains_after_the_first_failed_full_count(self):
        row = page()
        counter = _CountingCounter([11], prepared_result=10)
        result = self.run_assembly(row, counter)
        self.assertEqual(counter.events, ["full", "prepare"])
        self.assertEqual(len(counter.full_texts), 1)
        self.assertEqual(len(counter.suffixes), 1)
        self.assertEqual(result[0][3], [row["token_source_units"][1]])

    def test_impossible_bound_preserves_legacy_and_skips_suffix_encodes(self):
        old = page(1, "kept")
        entry = (old, "[kept]\n", old["content"], [(0, len(old["content"]))])
        counter = _CountingCounter([9, 11], minimum_tokens=11)
        self.assertEqual(self.run_assembly(page(), counter, [entry]), [entry])
        self.assertEqual(counter.events, ["full", "full", "prepare"])
        self.assertEqual(counter.suffixes, [])

    def test_bound_equal_to_cap_does_not_prune(self):
        counter = _CountingCounter([11], minimum_tokens=10, prepared_result=10)
        result = self.run_assembly(page(), counter)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(counter.suffixes), 1)

    def test_candidate_limit_stays_96_when_all_candidates_fail(self):
        counter = _CountingCounter([11], minimum_tokens=0, prepared_result=11)
        self.assertEqual(self.run_assembly(page(100), counter), [])
        self.assertEqual(len(counter.full_texts), 1)
        self.assertEqual(len(counter.prefixes), 1)
        self.assertEqual(len(counter.suffixes), 95)


@unittest.skipUnless(HAS_TOKENS, "Install .[tokens] for exact budget checks")
class ExactOrdinaryAndPrefixTests(unittest.TestCase):
    def test_ordinary_entry_matches_previous_counts_and_literal_specials(self):
        texts = ["", "A normal source sentence.",
                 "<|endoftext|> and <|fim_prefix|> are literal evidence.",
                 "café e\u0301 Straße 缓存45秒。", "👩🏽‍💻",
                 "\ud800", "\udfff", "before\ud83d\ude00after"]
        for tokenizer in ("cl100k_base", "o200k_base"):
            counter = TokenCounter(tokenizer)
            for text in texts:
                with self.subTest(tokenizer=tokenizer, text=repr(text)):
                    previous = len(counter.encoding.encode(text, disallowed_special=()))
                    self.assertEqual(counter.count(text), previous)

    def test_minimum_bounds_exact_appends_across_unicode_boundaries(self):
        prefixes = ["", "hello", "citation header\n", "\n\n", " \n ",
                    "café", "缓存", "👩🏽‍💻", "<|endoftext|>"]
        suffixes = ["", " world", "\n", " \n", "e\u0301", "缓存",
                    "<|fim_prefix|>"]
        for tokenizer in ("cl100k_base", "o200k_base"):
            counter = TokenCounter(tokenizer)
            for prefix in prefixes:
                prepared = counter.count_after(prefix)
                for suffix in suffixes:
                    with self.subTest(tokenizer=tokenizer, prefix=prefix, suffix=suffix):
                        exact = len(counter.encoding.encode(prefix + suffix,
                                                            disallowed_special=()))
                        self.assertGreaterEqual(prepared.minimum_tokens, 0)
                        self.assertLessEqual(prepared.minimum_tokens, exact)
                        self.assertEqual(prepared(suffix), exact)


if __name__ == "__main__":
    unittest.main()
