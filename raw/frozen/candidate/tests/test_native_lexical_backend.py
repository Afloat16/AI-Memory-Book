"""Whole Unicode mark removal and exact identifier-boundary predicate tests."""

from __future__ import annotations

import importlib
import importlib.util
from itertools import product
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import unicodedata
import unittest
from unittest.mock import patch

from memory_book import text as lexical

ROOT = Path(__file__).resolve().parents[1]
NATIVE = (importlib.import_module("memory_book._native")
          if importlib.util.find_spec("memory_book._native") is not None else None)


def reference_strip(value, category=unicodedata.category):
    removed = {ord(character): None for character in set(value) if category(character) == "Mn"}
    return value.translate(removed) if removed else value


def outcome(operation):
    try:
        return "value", operation()
    except Exception as error:
        return "error", type(error), error.args


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeLexicalCoreTests(unittest.TestCase):
    def test_mark_removal_preserves_all_other_categories_and_codepoints(self):
        cases = ["", "plain ASCII", "缓存🙂\ud800\udfff\x00",
                 "a\u0315\u0300éß\u034f\u302e\ufe0f", "\u0301\u0301\u0300",
                 "👩🏽‍💻\u200d\u20dd\u0903\u093e\u093f\u0300",
                 "".join(chr(index) for index in range(0x300, 0x370)),
                 "".join(chr(index) for index in range(0xfe00, 0xfe10))]
        rng = random.Random(783061)
        alphabet = "abcAZ09éß缓存🙂\u0300\u0315\u034f\u0903\u093e\u20dd\u302e\ufe0f\ud800\udfff\x00"
        cases += ["".join(rng.choices(alphabet, k=rng.randrange(0, 250))) for _ in range(250)]
        for value in cases:
            actual = NATIVE.strip_nonspacing_marks(value, unicodedata.category)
            self.assertEqual(actual, reference_strip(value))
            if not any(unicodedata.category(character) == "Mn" for character in value):
                self.assertIs(actual, value)

    def test_category_callback_order_once_per_distinct_character_and_exceptions(self):
        value = "éa\u0300\u0315缓存a🙂\ud800\u0300" * 5
        observations = []
        for operation in (reference_strip, NATIVE.strip_nonspacing_marks):
            calls = []

            def category(character):
                calls.append(character)
                return unicodedata.category(character)

            observations.append((operation(value, category), calls))
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(len(observations[0][1]), len(set(value)))

        for operation in (reference_strip, NATIVE.strip_nonspacing_marks):
            def fail(character):
                raise RuntimeError("category failure", character)
            self.assertEqual(outcome(lambda: operation(value, fail))[0], "error")
        self.assertEqual(outcome(lambda: NATIVE.strip_nonspacing_marks(value, lambda c: 3)),
                         outcome(lambda: reference_strip(value, lambda c: 3)))

    def test_identifier_boundary_exhaustive_ascii_classes(self):
        alphabet = "aA0_."
        for size in range(7):
            for characters in product(alphabet, repeat=size):
                value = "".join(characters)
                self.assertEqual(NATIVE.identifier_has_boundary(value),
                                 bool(lexical.IDENTIFIER_WORD_BOUNDARY.search(value)), repr(value))

    def test_identifier_boundary_unicode_and_acronym_edges(self):
        values = ["", "_", "__", "A", "a", "AA", "Aa", "aA", "0A", "A0", "XMLHttpRequest",
                  "HTTPParser", "éA", "Aé", "中Aa", "AA中a", "A🙂Aa", "\ud800A_\udfff",
                  "A\u0301a", "\U00020000Aa", "ＡＡａ", "a.A", "A/a", "a A"]
        rng = random.Random(783062)
        alphabet = "abcXYZ012_./ \téß缓存🙂\u0300\ud800\udfff"
        values += ["".join(rng.choices(alphabet, k=rng.randrange(0, 180))) for _ in range(1500)]
        for value in values:
            self.assertEqual(NATIVE.identifier_has_boundary(value),
                             bool(lexical.IDENTIFIER_WORD_BOUNDARY.search(value)), repr(value))

    def test_direct_helpers_reject_nonexact_text(self):
        class Text(str):
            pass

        for value in (None, b"abc", 3, Text("abc")):
            with self.assertRaises(TypeError):
                NATIVE.identifier_has_boundary(value)
            with self.assertRaises(TypeError):
                NATIVE.strip_nonspacing_marks(value, unicodedata.category)
        with self.assertRaises(TypeError):
            NATIVE.strip_nonspacing_marks("abc", None)


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeLexicalCoreDispatchTests(unittest.TestCase):
    def compare_paths(self, operation):
        values = []
        for backend in (None, NATIVE):
            with patch.object(lexical, "_NATIVE", backend):
                values.append(outcome(operation))
        self.assertEqual(values[0], values[1])
        return values[0]

    def test_public_helpers_really_dispatch(self):
        with patch.object(NATIVE, "strip_nonspacing_marks", wraps=NATIVE.strip_nonspacing_marks) as observed:
            self.assertEqual(lexical._strip_nonspacing_marks("a\u0300缓存"), "a缓存")
            observed.assert_called_once()
        with patch.object(NATIVE, "identifier_has_boundary", wraps=NATIVE.identifier_has_boundary) as observed:
            lexical.identifier_terms("HTTPParser 缓存", query=True)
            observed.assert_called_once()

    def test_whole_text_normalization_order_and_lexical_outputs(self):
        values = ["a\u0315\u0300", "A\u0315\u0300B", "éßİ ﬃ ＡＢＣ ＸＭＬＨｔｔｐ",
                  "HTTPParser XMLHttpRequest http_parser 缓存是什么",
                  "A中🙂B\ud800\udfff e\u0301\u0315", "a\u0345\u0300B" * 20]
        for value in values:
            for query in (False, True):
                self.compare_paths(lambda: lexical.terms(value, query=query))
                self.compare_paths(lambda: lexical.identifier_terms(value, query=query))
            self.compare_paths(lambda: lexical.index_text(value))
            self.compare_paths(lambda: lexical.query_terms(value))

    def test_modified_category_and_text_subclasses_keep_reference_behavior(self):
        ordinary = unicodedata.category
        observations = []
        for backend in (None, NATIVE):
            calls = []

            def category(character):
                calls.append(character)
                return ordinary(character)

            with patch.object(lexical, "_NATIVE", backend), patch.object(unicodedata, "category", category):
                actual = lexical._strip_nonspacing_marks("éa\u0300缓存a" * 5)
            observations.append((actual, calls))
        self.assertEqual(observations[0], observations[1])

        class Text(str):
            def translate(self, mapping):
                return "custom translate"

        self.compare_paths(lambda: lexical._strip_nonspacing_marks(Text("a\u0300")))
        with patch.object(unicodedata, "category", side_effect=RuntimeError("custom category")):
            self.assertEqual(self.compare_paths(lambda: lexical._strip_nonspacing_marks("a"))[0], "error")

    def test_modified_identifier_pattern_keeps_search_calls_and_errors(self):
        ordinary = lexical.IDENTIFIER_WORD_BOUNDARY
        observations = []
        for backend in (None, NATIVE):
            calls = []

            class Pattern:
                def search(self, text):
                    calls.append(text)
                    return None

            with patch.object(lexical, "_NATIVE", backend), patch.object(lexical, "IDENTIFIER_WORD_BOUNDARY", Pattern()):
                actual = lexical.identifier_terms("HTTPParser")
            observations.append((actual, calls))
        self.assertEqual(observations[0], observations[1])

        class Failure:
            def search(self, text):
                raise RuntimeError("custom identifier search")
        with patch.object(lexical, "IDENTIFIER_WORD_BOUNDARY", Failure()):
            self.assertEqual(self.compare_paths(lambda: lexical.identifier_terms("plain"))[0], "error")
        self.assertIs(lexical.IDENTIFIER_WORD_BOUNDARY, ordinary)

    def test_category_replaced_before_import_is_not_certified(self):
        script = r'''
import json, unicodedata
ordinary = unicodedata.category
calls = []
def category(character):
    calls.append(character)
    return ordinary(character)
unicodedata.category = category
from memory_book import text
assert not text._NATIVE_FOLD_CERTIFIED
actual = text._strip_nonspacing_marks("a\u0315\u0300缓存")
first = list(calls)
calls.clear()
text._NATIVE = None
expected = text._strip_nonspacing_marks("a\u0315\u0300缓存")
print(json.dumps([actual, expected, first, calls]))
'''
        environment = dict(os.environ, MEMORY_BOOK_TEXT_BACKEND="native", PYTHONDONTWRITEBYTECODE="1",
                           PYTHONPATH=str(Path(lexical.__file__).resolve().parents[1]))
        process = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment,
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        actual, expected, first, second = json.loads(process.stdout)
        self.assertEqual(actual, expected)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
