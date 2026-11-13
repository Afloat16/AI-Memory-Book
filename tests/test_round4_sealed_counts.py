"""Artificial exactness fixtures for the preregistered sealed-boundary work.

The reference counter deliberately uses the complete-context fallback. No
benchmark corpus, elapsed-time measurement or persistent text cache is used.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import hashlib
import importlib.util
import itertools
import sys
import unittest
from unittest.mock import patch

from memory_book import token_budget as budget


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None


def row(identity, text):
    return {"id": identity, "project_id": "fixture", "session_id": identity,
            "created_at": "2026-11-13T00:00:00Z", "content": text,
            "token_source_units": budget.source_units(text)}


def header(value):
    return (f'[{value["id"]}] {value["project_id"]} / {value["session_id"]}'
            f' | {value["created_at"]}\n')


def entry(value):
    return value, header(value), value["content"], [(0, len(value["content"]))]


def context(kept):
    return "\n\n".join(head + text for _, head, text, _ in kept)


class CompleteCounter:
    """Expose the old counting operations without claiming the certificate."""
    def __init__(self, name):
        self.original = budget.TokenCounter(name)
        self.calls = []
        self.prefixes = []

    def count(self, text):
        self.calls.append(text)
        return self.original.count(text)

    def count_after(self, prefix):
        self.prefixes.append(prefix)
        return self.original.count_after(prefix)


@contextmanager
def observed_counts():
    """Observe genuine methods without replacing them or weakening guards."""
    calls, prefixes = [], []
    count_code = budget._ORDINARY_COUNT.__code__
    prefix_code = budget._ORDINARY_COUNT_AFTER.__code__
    prior = sys.getprofile()

    def observe(frame, event, arg):
        if event == "call":
            if frame.f_code is count_code:
                calls.append(frame.f_locals["text"])
            elif frame.f_code is prefix_code:
                prefixes.append(frame.f_locals["prefix"])

    sys.setprofile(observe)
    try:
        yield calls, prefixes
    finally:
        sys.setprofile(prior)


@unittest.skipUnless(HAS_TOKENS, "Install .[tokens] for exact sealed-boundary fixtures")
class SealedCountTests(unittest.TestCase):
    def test_registered_patterns_and_exact_token_ids_at_only_the_certified_boundary(self):
        lefts = ["", " \t\r\n\u0085\u2028\u2029", "!!!///", "'ll we're 123456",
                 "café e\u0301 漢字 👩🏽‍💻", "```python\r\nx = '[a]'\r\n```",
                 "<|endoftext|><|fim_prefix|><|endofprompt|>", "x" * 129 + " " * 65,
                 "\ud800", "\udc00", "\ud800\udc00", "\ud800\n\udc00"]
        lefts += ["".join(chars) for chars in itertools.product("a /\r\n[", repeat=3)]
        rights = ["[", "[]", "[p] fixture / one\nanswer", "[漢]\r\n```\n[\n```",
                  "[<|endoftext|>]\n<|fim_suffix|>", "[\udc00] x\ud800"]
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            self.assertTrue(budget._can_seal_blocks(counter))
            encoding = counter.encoding
            self.assertEqual(hashlib.sha256(encoding._pat_str.encode()).hexdigest(),
                             budget._SEALED_PATTERNS[name])
            for left, right in itertools.product(lefts, rights):
                sealed = left + "\n\n"
                self.assertEqual(encoding.encode_ordinary(sealed + right),
                                 encoding.encode_ordinary(sealed) + encoding.encode_ordinary(right),
                                 (name, repr(left), repr(right)))
            self.assertNotEqual(counter.count("\n\n") + counter.count("\n"), counter.count("\n\n\n"))

    def test_all_fit_encodes_each_sealed_block_once_and_final_block_exactly(self):
        pages = [row(str(i), f"Evidence {i}: alpha beta. " * 20) for i in range(3)]
        legacy = [entry(value) for value in pages]
        blocks = [head + text for _, head, text, _ in legacy]
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            expected = budget.assemble_with_count(legacy, pages, ["alpha"], budget_chars=10000,
                budget_tokens=100000, counter=CompleteCounter(name))
            for _ in range(2):
                with observed_counts() as (calls, prefixes):
                    actual = budget.assemble_with_count(legacy, pages, ["alpha"], budget_chars=10000,
                        budget_tokens=100000, counter=counter)
                self.assertEqual(actual, expected)
                self.assertEqual(calls, [blocks[0] + "\n\n", blocks[1] + "\n\n", blocks[2]])
                self.assertEqual(prefixes, [])
                self.assertEqual(actual[1], counter.count(context(actual[0])))

    def test_complete_fallback_differential_over_caps_unicode_fences_and_special_literals(self):
        pages = [row("one", "Pressure is 82 pascals.\r\nRetry is 45 seconds."),
            row("two", "café e\u0301 缓存保留45秒。 👩🏽‍💻 <|endoftext|> is literal.\n" * 4),
            row("three", "```python\r\npressure = 82\r\nUSER: ```\r\nretry = 45\r\n```\r\n" +
                "Pressure remains recorded. Background detail. " * 12)]
        legacy = [entry(value) for value in pages]
        for name in budget.TOKENIZERS:
            independent = budget.TokenCounter(name)
            exact = independent.count(header(pages[0]) + pages[0]["content"])
            for chars, tokens in itertools.product((0, 32, 128, 800, 8000),
                                                   (0, 1, exact - 1, exact, exact + 1, 128, 512, 100000)):
                with self.subTest(name=name, chars=chars, tokens=tokens):
                    options = dict(budget_chars=chars, budget_tokens=tokens)
                    expected = budget.assemble_with_count(legacy, pages, ["pressure", "café"],
                        counter=CompleteCounter(name), **options)
                    actual = budget.assemble_with_count(legacy, pages, ["pressure", "café"],
                        counter=budget.TokenCounter(name), **options)
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual[1], independent.count(context(actual[0])))
                    self.assertLessEqual(actual[1], tokens)
                    self.assertLessEqual(len(context(actual[0])), chars)

    def test_real_nonmonotonic_counts_keep_the_later_first_fit(self):
        pages = [row("shorter", "hello worl"), row("longer", "hello world")]
        citation = "[p] fixture / session\n"
        legacy = [(value, citation, value["content"], [(0, len(value["content"]))]) for value in pages]
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            cap = counter.count(citation + "hello world")
            self.assertGreater(counter.count(citation + "hello worl"), cap)
            actual = budget.assemble_with_count(legacy, [], [], budget_chars=1000,
                budget_tokens=cap, counter=counter)
            self.assertEqual([value[0]["id"] for value in actual[0]], ["longer"])
            self.assertEqual(actual[1], cap)

    def test_later_rejections_keep_the_deferred_accepted_context_and_exact_count(self):
        pages = [row("one", "Pressure is 82."), row("two", "xqz 12345 " * 400)]
        legacy = [entry(value) for value in pages]
        first = header(pages[0]) + pages[0]["content"]
        cap = len(first.encode()) + 1  # First block is accepted by the byte bound.
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            actual = budget.assemble_with_count(legacy, [], [], budget_chars=10000,
                budget_tokens=cap, counter=counter)
            self.assertEqual(actual[0], [legacy[0]])
            self.assertEqual(actual[1], counter.count(first))

    def test_supplemental_counts_prepare_only_header_with_exact_sealed_offset(self):
        one = row("one", "Pressure was recorded.")
        lines = ["pressure " + "xqz " * size for size in (130, 100, 70, 40)] + ["pressure is 82."]
        two = row("two", "\n".join(lines))
        cursor = 0
        two["token_source_units"] = []
        for line in lines:
            two["token_source_units"].append((cursor, cursor + len(line)))
            cursor += len(line) + 1
        legacy = [entry(one)]
        final_text = "…" + lines[-1]
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            expected_context = header(one) + one["content"] + "\n\n" + header(two) + final_text
            cap = counter.count(expected_context)
            reference = CompleteCounter(name)
            expected = budget.assemble_with_count(legacy, [one, two], ["pressure"], budget_chars=10000,
                budget_tokens=cap, counter=reference)
            with observed_counts() as (_, prefixes):
                actual = budget.assemble_with_count(legacy, [one, two], ["pressure"], budget_chars=10000,
                    budget_tokens=cap, counter=counter)
            self.assertEqual(actual, expected)
            self.assertEqual(context(actual[0]), expected_context)
            self.assertEqual(actual[1], cap)
            self.assertEqual(prefixes, [header(two)])
            self.assertEqual(reference.prefixes, [header(one) + one["content"] + "\n\n" + header(two)])

    def test_unknown_version_pattern_and_missing_pattern_use_complete_fallback(self):
        pages = [row("one", "alpha beta"), row("two", "gamma delta")]
        legacy = [entry(value) for value in pages]
        expected_calls = [header(pages[0]) + pages[0]["content"],
                          "\n\n".join(head + text for _, head, text, _ in legacy)]
        for name in budget.TOKENIZERS:
            for mutation in ("version", "pattern", "missing-pattern", "encoder-method", "encoder-class"):
                counter = budget.TokenCounter(name)
                encoding = counter.encoding
                old_pattern = encoding._pat_str
                ordinary_encoder = type(encoding).encode_ordinary
                def changed_class_method(instance, text):
                    return ordinary_encoder(instance, text)
                manager = (patch.object(counter, "version", "future") if mutation == "version" else
                           patch.object(encoding, "_pat_str", "unregistered") if mutation == "pattern" else
                           patch.object(encoding, "encode_ordinary", wraps=encoding.encode_ordinary)
                           if mutation == "encoder-method" else
                           patch.object(type(encoding), "encode_ordinary", changed_class_method)
                           if mutation == "encoder-class" else None)
                if mutation == "missing-pattern":
                    del encoding._pat_str
                try:
                    if manager is not None:
                        manager.start()
                    self.assertFalse(budget._can_seal_blocks(counter))
                    with observed_counts() as (calls, _):
                        result = budget.assemble_with_count(legacy, pages, [], budget_chars=1000,
                            budget_tokens=10000, counter=counter)
                    self.assertEqual(calls, expected_calls, (name, mutation))
                    self.assertEqual(result[0], legacy)
                finally:
                    if manager is not None:
                        manager.stop()
                    if mutation == "missing-pattern":
                        encoding._pat_str = old_pattern

    def test_custom_and_monkeypatched_counters_keep_their_original_operations(self):
        values = [row("one", "alpha"), row("two", "beta")]
        legacy = [entry(value) for value in values]
        for name in budget.TOKENIZERS:
            ordinary = budget.TokenCounter(name)
            custom = CompleteCounter(name)
            custom.name, custom.version, custom.encoding = name, "0.12.0", ordinary.encoding
            self.assertFalse(budget._can_seal_blocks(custom))
            expected = budget.assemble_with_count(legacy, values, [], budget_chars=1000,
                budget_tokens=10000, counter=custom)
            for patch_class in (False, True):
                calls = []
                def counted(*args):
                    instance, text = args if patch_class else (ordinary, args[0])
                    calls.append(text)
                    return budget._ORDINARY_COUNT(instance, text)
                target = budget.TokenCounter if patch_class else ordinary
                with patch.object(target, "count", counted):
                    self.assertFalse(budget._can_seal_blocks(ordinary))
                    actual = budget.assemble_with_count(legacy, values, [], budget_chars=1000,
                        budget_tokens=10000, counter=ordinary)
                self.assertEqual(actual, expected)
                self.assertEqual(calls, custom.calls)

    def test_pre_initialization_encoder_override_cannot_bypass_budget_even_with_wraps(self):
        import tiktoken
        value = row("one", "alpha beta")
        block = header(value) + value["content"]
        cap = len(block.encode("utf-8")) + 1
        original = tiktoken.Encoding.encode_ordinary
        for name, decorated in itertools.product(budget.TOKENIZERS, (False, True)):
            calls = []
            # Deliberately retain the original code name as well as optional
            # wraps metadata. Its actual source file is still this test file.
            def encode_ordinary(instance, text):
                calls.append(text)
                return [0] * (3 * len(text.encode("utf-8")))
            replacement = wraps(original)(encode_ordinary) if decorated else encode_ordinary
            if decorated:
                self.assertEqual(replacement.__module__, original.__module__)
                self.assertEqual(replacement.__name__, original.__name__)
                self.assertEqual(replacement.__qualname__, original.__qualname__)
                self.assertEqual(replacement.__code__.co_name, original.__code__.co_name)
                self.assertNotEqual(replacement.__code__.co_filename, original.__code__.co_filename)
            budget._encoding.cache_clear()
            try:
                with self.subTest(name=name, decorated=decorated), \
                        patch.object(budget, "_ORDINARY_ENCODER_METHODS", None), \
                        patch.object(tiktoken.Encoding, "encode_ordinary", replacement):
                    self.assertEqual(budget._encoding.cache_info().currsize, 0)
                    counter = budget.TokenCounter(name)
                    self.assertIsNone(budget._ORDINARY_ENCODER_METHODS)
                    self.assertFalse(budget._can_seal_blocks(counter))
                    kept, count = budget.assemble_with_count([entry(value)], [], [],
                        budget_chars=1000, budget_tokens=cap, counter=counter)
                    # A byte-bound acceptance would return this block and a
                    # final count above cap. Historical full counting rejects.
                    self.assertEqual((kept, count), ([], 0))
                    self.assertLessEqual(count, cap)
                    self.assertEqual(calls, [block])
            finally:
                budget._encoding.cache_clear()

    def test_missing_or_unknown_initial_encoder_origins_fall_back_for_all_methods(self):
        import tiktoken
        from tiktoken import core
        values = [row("one", "alpha"), row("two", "beta")]
        legacy = [entry(value) for value in values]
        expected_calls = [header(values[0]) + values[0]["content"], context(legacy)]
        for method in (*budget._ENCODER_METHOD_NAMES, "missing-module-file"):
            if method == "missing-module-file":
                manager = patch.object(core, "__file__", None)
            else:
                original = getattr(tiktoken.Encoding, method)
                def substituted(*args, **kwargs):
                    return original(*args, **kwargs)
                manager = patch.object(tiktoken.Encoding, method, wraps(original)(substituted))
            budget._encoding.cache_clear()
            try:
                with self.subTest(method=method), patch.object(budget, "_ORDINARY_ENCODER_METHODS", None), manager:
                    counter = budget.TokenCounter("cl100k_base")
                    self.assertIsNone(budget._ORDINARY_ENCODER_METHODS)
                    self.assertFalse(budget._can_seal_blocks(counter))
                    with observed_counts() as (calls, _):
                        kept, count = budget.assemble_with_count(legacy, values, [],
                            budget_chars=1000, budget_tokens=10000, counter=counter)
                    self.assertEqual(kept, legacy)
                    self.assertEqual(calls, expected_calls)
                    self.assertEqual(count, counter.count(context(legacy)))
            finally:
                budget._encoding.cache_clear()

    def test_non_citation_header_forces_full_context_even_if_rejected(self):
        pages = [row("one", "alpha"), row("two", "beta")]
        legacy = [(pages[0], "plain header\n", "alpha", [(0, 5)]), entry(pages[1])]
        for name in budget.TOKENIZERS:
            reference = CompleteCounter(name)
            expected = budget.assemble_with_count(legacy, pages, [], budget_chars=1000,
                budget_tokens=10000, counter=reference)
            with observed_counts() as (calls, _):
                actual = budget.assemble_with_count(legacy, pages, [], budget_chars=1000,
                    budget_tokens=10000, counter=budget.TokenCounter(name))
            self.assertEqual(actual, expected)
            self.assertEqual(calls, reference.calls)

    def test_surrogate_prefixes_preserve_historical_lazy_prefix_errors(self):
        for name in budget.TOKENIZERS:
            for invalid in ("\ud800", "\udc00", "\ud800\udc00"):
                one = row("one", "alpha " + invalid)
                lines = ["pressure " + "xqz " * size for size in (100, 90, 80, 70)]
                two = row("two", "\n".join(lines))
                cursor = 0
                two["token_source_units"] = []
                for line in lines:
                    two["token_source_units"].append((cursor, cursor + len(line)))
                    cursor += len(line) + 1
                counter = budget.TokenCounter(name)
                cap = counter.count(header(one) + one["content"]) + counter.count(header(two)) + 3
                for counting in (CompleteCounter(name), counter):
                    with self.subTest(name=name, invalid=repr(invalid), kind=type(counting).__name__):
                        with self.assertRaises(UnicodeEncodeError):
                            budget.assemble_with_count([entry(one)], [one, two], ["pressure"],
                                budget_chars=10000, budget_tokens=cap, counter=counting)

    def test_surrogate_late_choice_rebuilds_the_original_prefix_and_matches_result(self):
        one = row("one", "alpha beta")
        lines = ["pressure " + "xqz " * 100, "pressure " + "xqz " * 70,
                 "pressure " + "café " * 8 + "\ud800", "pressure 82"]
        two = row("two", "\n".join(lines))
        cursor = 0
        two["token_source_units"] = []
        for line in lines:
            two["token_source_units"].append((cursor, cursor + len(line)))
            cursor += len(line) + 1
        old_prefix = header(one) + one["content"] + "\n\n" + header(two)
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            cap = counter.count(old_prefix + "…" + lines[2] + "…")
            options = dict(budget_chars=10000, budget_tokens=cap)
            expected = budget.assemble_with_count([entry(one)], [one, two], ["pressure"],
                counter=CompleteCounter(name), **options)
            with observed_counts() as (_, prefixes):
                actual = budget.assemble_with_count([entry(one)], [one, two], ["pressure"],
                    counter=counter, **options)
            self.assertEqual(actual, expected)
            self.assertEqual(prefixes, [header(two), old_prefix])
            self.assertEqual(actual[1], counter.count(context(actual[0])))

    def test_empty_and_zero_budget_do_not_eagerly_read_source_or_invalid_unused_header(self):
        for name in budget.TOKENIZERS:
            counter = budget.TokenCounter(name)
            self.assertEqual(budget.assemble_with_count([], [], [], budget_chars=0,
                budget_tokens=0, counter=counter), ([], 0))
            unused = {"id": "unused"}
            self.assertEqual(budget.assemble_with_count([(unused, None, "", [])], [unused], [],
                budget_chars=0, budget_tokens=0, counter=counter,
                source_units_for=lambda value: self.fail("unused source was read")), ([], 0))
            value = row("fits", "alpha")
            kept, count = budget.assemble_with_count([entry(value)], [value], [], budget_chars=1000,
                budget_tokens=10000, counter=counter,
                source_units_for=lambda page: self.fail("already accepted source was read"))
            self.assertEqual(kept, [entry(value)])
            self.assertEqual(count, counter.count(context(kept)))


if __name__ == "__main__":
    unittest.main()
