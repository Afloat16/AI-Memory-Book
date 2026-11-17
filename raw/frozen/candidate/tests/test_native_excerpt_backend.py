"""Literal excerpt occurrences retain the released regex and mapping semantics."""

from __future__ import annotations

import importlib
import importlib.util
from itertools import islice
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from memory_book import text as lexical


ROOT = Path(__file__).resolve().parents[1]
NATIVE = (importlib.import_module("memory_book._native")
          if importlib.util.find_spec("memory_book._native") is not None else None)


def reference_positions(lower, terms, source_positions):
    result = []
    for term in terms:
        for match in islice(re.finditer(re.escape(term), lower), 40):
            position = match.start() if source_positions is None else source_positions[match.start()]
            result.append((position, term))
    return result


def outcome(operation):
    try:
        return "value", operation()
    except Exception as error:
        return "error", type(error), error.args


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeLiteralPositionsTests(unittest.TestCase):
    def compare(self, value, terms, source_positions=None):
        self.assertEqual(outcome(lambda: NATIVE.literal_positions(value, terms, source_positions)),
                         outcome(lambda: reference_positions(value, terms, source_positions)),
                         (repr(value), terms, source_positions))

    def test_nonoverlap_per_term_cap_duplicates_and_term_major_order(self):
        for value in ("", "a", "aaaaa", "ababa", "a" * 120, "abc " * 100):
            for terms in ([], [""], ["a"], ["aa", "a", "aaa"], ["a", "a"],
                          ["aba", "bab"], ["", "abc", "", "absent"]):
                self.compare(value, terms)
        actual = NATIVE.literal_positions("a" * 120, ["aa", "a", "aa"], None)
        self.assertEqual(len(actual), 120)
        self.assertEqual(actual[:40], [(2 * index, "aa") for index in range(40)])
        self.assertEqual(actual[40:80], [(index, "a") for index in range(40)])
        self.assertEqual(actual[80:], actual[:40])

    def test_regex_metacharacters_are_literals_and_offsets_are_unicode_codepoints(self):
        cases = [
            (r"a.b a*b [ab] (ab) \w+ ^a$ {a} ?x|y", [".", "*", "[ab]", "(ab)", r"\w+", "^a$", "{a}", "?x|y"]),
            ("A中🙂B\ud800_éß\udfff\x00A中🙂B", ["🙂", "中🙂", "\ud800", "\udfff", "\x00", "A中🙂B"]),
            ("a\u0301A\u0301a\u302eb\ufe0f👩🏽‍💻\U0010ffff", ["a\u0301", "\u0301", "a", "\u302e", "👩", "💻", "\U0010ffff"]),
        ]
        for value, terms in cases:
            self.compare(value, terms)
            self.compare(value, terms, [index // 2 for index in range(len(value))])

    def test_empty_terms_and_short_maps_keep_the_original_index_error(self):
        for value in ("", "a", "abc", "a" * 39, "a" * 40, "a" * 50):
            for size in (0, max(0, len(value) - 1), len(value), len(value) + 1):
                self.compare(value, [""], list(range(size)))
                self.compare(value, ["absent"], list(range(size)))
        self.compare("abcabc", ["b"], [0])
        self.compare("abcabc", ["b"], [0, 1, 2, 3, 4, 5])

    def test_mapping_objects_are_preserved_without_numeric_conversion(self):
        marker = object()
        mapping = [-1, 10 ** 100, marker, "mapped", None]
        terms = ["a", "b", "c", "d", "e", "a"]
        self.compare("abcde", terms, mapping)
        actual = NATIVE.literal_positions("abcde", terms, mapping)
        for index in range(5):
            self.assertIs(actual[index][0], mapping[index])
            self.assertIs(actual[index][1], terms[index])

    def test_seeded_unicode_literals_match_independent_regex_reference(self):
        rng = random.Random(818071)
        alphabet = "aaAB0_ .+*?[]()\\^$\t\n\x00缓存éß\u0301🙂\U00020000\ud800\udfff"
        for _ in range(240):
            value = "".join(rng.choices(alphabet, k=rng.randrange(1, 150)))
            terms = [value[start:start + rng.randrange(0, 7)]
                     for start in (rng.randrange(len(value)) for _ in range(8))]
            terms.extend(["absent", terms[0]])
            self.compare(value, terms)
            self.compare(value, terms, [index // 2 for index in range(len(value) + 1)])

    def test_native_entrypoint_rejects_out_of_contract_container_and_string_types(self):
        class Text(str):
            pass

        class Values(list):
            pass

        for value in (None, b"abc", Text("abc"), 1):
            with self.assertRaises(TypeError):
                NATIVE.literal_positions(value, ["a"], None)
        for terms in (None, ("a",), Values(["a"]), "a", [1], [Text("a")], [b"a"]):
            with self.assertRaises(TypeError):
                NATIVE.literal_positions("abc", terms, None)
        for mapping in ((0, 1, 2), Values([0, 1, 2]), {0: 0}, object()):
            with self.assertRaises(TypeError):
                NATIVE.literal_positions("abc", ["a"], mapping)


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeLiteralDispatchTests(unittest.TestCase):
    VALUE = "Background café Straße 👩🏽‍💻. " * 12 + "\n缓存现在保留23分钟。\n" + "Later. " * 10

    def compare_paths(self, operation):
        values = []
        for backend in (None, NATIVE):
            with patch.object(lexical, "_NATIVE", backend):
                values.append(outcome(operation))
        self.assertEqual(values[0], values[1])
        return values[0]

    def test_ordinary_excerpt_really_calls_native_literal_positions(self):
        observed = Mock(wraps=NATIVE)
        with patch.object(lexical, "_NATIVE", observed):
            actual = lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"])
        with patch.object(lexical, "_NATIVE", None):
            expected = lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"])
        self.assertEqual(actual, expected)
        observed.literal_positions.assert_called_once()

    def test_prepared_terms_unusual_types_and_empty_terms_keep_python_behavior(self):
        class Text(str):
            pass

        class Values(list):
            pass

        factories = [lambda: None, lambda: [], lambda: [""], lambda: ["strasse", "strasse"],
                     lambda: ("strasse", "缓存"), lambda: Values(["strasse"]),
                     lambda: iter(["strasse", "缓存"]), lambda: [Text("strasse")],
                     lambda: [None], lambda: [b"strasse"], lambda: [1], lambda: "cafe"]
        for factory in factories:
            for budget in (0, 7, 8, 90, 5000, 8.5):
                self.compare_paths(lambda: lexical.excerpt(self.VALUE, "cafe", budget,
                                                           prepared_terms=factory()))

    def test_patched_escape_and_finditer_are_not_bypassed(self):
        for name in ("escape", "finditer"):
            ordinary = getattr(re, name)
            traces = []
            for backend in (None, NATIVE):
                observed = Mock(wraps=ordinary)
                with patch.object(lexical, "_NATIVE", backend), patch.object(re, name, observed):
                    value = lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"])
                traces.append((value, observed.mock_calls))
            self.assertEqual(traces[0], traces[1])
            with patch.object(re, name, side_effect=RuntimeError("custom " + name)):
                self.assertEqual(self.compare_paths(lambda: lexical.excerpt(
                    self.VALUE, "", 90, prepared_terms=["strasse"]))[0], "error")

    def test_patched_islice_calls_and_limit_are_not_bypassed(self):
        ordinary = lexical.islice
        traces = []
        for backend in (None, NATIVE):
            calls = []

            def observe(iterator, *args):
                calls.append(args)
                return ordinary(iterator, 2)

            with patch.object(lexical, "_NATIVE", backend), patch.object(lexical, "islice", observe):
                value = lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"])
            traces.append((value, calls))
        self.assertEqual(traces[0], traces[1])
        self.assertEqual(traces[0][1], [(40,), (40,)])

    def test_nonlist_source_maps_keep_indexing_and_exception_behavior(self):
        lower = "cafe " * 120

        class Mapping(list):
            def __getitem__(self, key):
                raise RuntimeError("custom source map")

        for mapping in (tuple(range(len(lower))), dict(enumerate(range(len(lower)))),
                        Mapping(range(len(lower)))):
            with patch.object(lexical, "_fold_excerpt_source", return_value=(lower, mapping)):
                self.compare_paths(lambda: lexical.excerpt(self.VALUE, "", 90, prepared_terms=["cafe"]))

    def test_dependencies_replaced_before_import_are_not_certified_as_ordinary(self):
        script = r'''
import itertools, json, re, sys
if sys.argv[1] == "finditer":
    re.finditer = lambda *args, **kwargs: iter(())
elif sys.argv[1] == "escape":
    re.escape = lambda value: "absent"
else:
    ordinary = itertools.islice
    itertools.islice = lambda iterator, *args: ordinary(iterator, 0)
from memory_book import text
value = "prefix " * 30 + "target 317ms" + " tail" * 30
actual = text.excerpt(value, "", 40, prepared_terms=["target"])
text._NATIVE = None
expected = text.excerpt(value, "", 40, prepared_terms=["target"])
print(json.dumps([actual, expected]))
'''
        environment = dict(os.environ, MEMORY_BOOK_TEXT_BACKEND="native", PYTHONDONTWRITEBYTECODE="1")
        for dependency in ("finditer", "escape", "islice"):
            with self.subTest(dependency=dependency):
                process = subprocess.run([sys.executable, "-c", script, dependency], cwd=ROOT,
                                         env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(process.returncode, 0, process.stderr)
                actual, expected = json.loads(process.stdout)
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
