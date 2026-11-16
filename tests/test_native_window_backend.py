"""Differential tests for the complete, unchanged excerpt-window algorithm."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
import importlib
import importlib.util
from itertools import islice
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

from memory_book import text as lexical

ROOT = Path(__file__).resolve().parents[1]
NATIVE = (importlib.import_module("memory_book._native")
          if importlib.util.find_spec("memory_book._native") is not None else None)


def reference_units(value, width):
    units = []
    for line in re.finditer(r"[^\n]+", value):
        lo, hi = line.span()
        if hi - lo <= width:
            units.append((lo, hi))
            continue
        start = lo
        for boundary in re.finditer(r"[。！？]|[.!?](?=\s|$)", line.group()):
            end = lo + boundary.end()
            if end - start <= width:
                units.append((start, end))
            start = end
            while start < hi and value[start].isspace():
                start += 1
        if start < hi and hi - start <= width:
            units.append((start, hi))
    return units


def reference_positions(value, q):
    return [(match.start(), term) for term in q
            for match in islice(re.finditer(re.escape(term), value), 40)]


def reference_window(text, q, positions, width, evidence_units=reference_units,
                     log1p=math.log1p, fsum=math.fsum):
    """Frozen v0.8.1 window body, independent of the new dispatch wrapper."""
    positions.sort()
    starts = {0, max(0, len(text) - width)}
    for pos, _ in positions:
        starts.add(max(0, min(len(text) - width, pos - width // 3)))
    units = evidence_units(text, width) if positions else []
    unit_starts = [lo for lo, _ in units]
    masks = {}
    term_bits = {term: 1 << i for i, term in enumerate(dict.fromkeys(q))}
    for pos, term in positions:
        index = bisect_right(unit_starts, pos) - 1
        if index >= 0 and pos < units[index][1]:
            masks[index] = masks.get(index, 0) | term_bits[term]
    matched_units = [(units[i][0], units[i][1], mask) for i, mask in sorted(masks.items())]
    for lo, hi, _ in matched_units:
        starts.add(min(lo, len(text) - width))
        starts.add(max(0, hi - width))
    unit_starts = [lo for lo, _, _ in matched_units]
    unit_ends = [hi for _, hi, _ in matched_units]
    best_start, best_score = 0, (-1, -1, -1.0, -1.0, -1)
    left = right = position_sum = 0
    inside = Counter()
    for start in sorted(starts):
        while right < len(positions) and positions[right][0] < start + width:
            pos, term = positions[right]
            inside[term] += 1
            position_sum += pos
            right += 1
        while left < right and positions[left][0] < start:
            pos, term = positions[left]
            inside[term] -= 1
            if not inside[term]:
                del inside[term]
            position_sum -= pos
            left += 1
        whole_terms = 0
        first_unit = bisect_left(unit_starts, start)
        last_unit = bisect_right(unit_ends, start + width)
        for index in range(first_unit, last_unit):
            whole_terms |= matched_units[index][2]
        count = right - left
        placement = abs((position_sum / count - start) / width - 1 / 3) if count else 1.0
        score = (len(inside), whole_terms.bit_count(),
                 fsum(log1p(n) for n in inside.values()), -placement, -start)
        if score > best_score:
            best_start, best_score = start, score
    end = min(len(text), best_start + width)
    return ("…" if best_start else "") + text[best_start:end] + ("…" if end < len(text) else ""), [(best_start, end)]


def outcome(operation):
    try:
        return "value", operation()
    except Exception as error:
        return "error", type(error), error.args


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeWindowTests(unittest.TestCase):
    def compare(self, value, terms, width, positions=None):
        positions = reference_positions(value, terms) if positions is None else positions
        expected = reference_window(value, terms, list(positions), width)
        actual = NATIVE.excerpt_window(value, terms, list(positions), width,
                                       reference_units, math.log1p, math.fsum)
        self.assertEqual(actual, expected, (repr(value), terms, width, positions))
        return actual

    def test_no_matches_duplicate_terms_ties_and_unicode_codepoints(self):
        cases = [
            ("prefix " * 20 + "\ntarget retains 23 minutes.\n" + "tail " * 20, ["target", "23"]),
            ("alpha beta. " * 30, ["alpha", "beta", "alpha"]),
            ("a" * 150, ["aa", "a", "aaa"]),
            ("a" * 150, ["", "a", ""]),
            ("A中🙂B\ud800 éß\udfff\x00\n缓存保留23分钟。\n" * 12, ["🙂", "缓存", "\ud800", "23"]),
            ("\n\nalpha\n\nbeta\n\nalpha\n\n" * 12, ["alpha", "beta"]),
            ("irrelevant " * 60, []),
            ("irrelevant " * 60, ["absent"]),
        ]
        for value, terms in cases:
            for width in (1, 6, 7, 8, 17, 40, len(value) - 1):
                self.compare(value, terms, width)

    def test_all_sixty_four_term_bits_and_per_term_forty_occurrences(self):
        terms = [f"q{index:02d}" for index in range(64)]
        value = (" ".join(terms) + "\n") * 45
        for width in (40, 120, 300, 700):
            self.compare(value, terms, width)
        self.compare(value, ["q63"] + terms[:-1], 120)

    def test_counter_deletion_reinsertion_and_math_input_order(self):
        value = ("first unit.\n" + "x" * 20 + "\n") * 7
        q = ["alpha", "beta", "gamma"]
        positions = [(1, "alpha"), (2, "alpha"), (3, "beta"), (40, "gamma"),
                     (41, "beta"), (42, "beta"), (80, "alpha"), (81, "gamma"),
                     (82, "gamma"), (83, "gamma"), (84, "beta"), (125, "beta"),
                     (126, "alpha"), (127, "alpha")]
        for width in (6, 20, 43, 80):
            observations = []
            for implementation in (reference_window, NATIVE.excerpt_window):
                logged, grouped = [], []

                def log1p(number):
                    logged.append(number)
                    return math.log1p(number)

                def fsum(values):
                    values = tuple(values)
                    grouped.append(values)
                    return math.fsum(values)

                actual = implementation(value, q, list(reversed(positions)), width,
                                        reference_units, log1p, fsum)
                observations.append((actual, logged, grouped))
            self.assertEqual(observations[0], observations[1])

    def test_sorted_positions_are_visible_before_evidence_callback(self):
        value, q, width = "target " * 30, ["target"], 30
        positions = [(21, "target"), (0, "target"), (14, "target")]

        def units(text, budget):
            self.assertEqual(positions, sorted(positions))
            return reference_units(text, budget)

        actual = NATIVE.excerpt_window(value, q, positions, width, units, math.log1p, math.fsum)
        self.assertEqual(actual, reference_window(value, q, list(positions), width))

    def test_seeded_window_differential(self):
        rng = random.Random(203811)
        alphabet = "aaBB09_ .!?。\n\t缓存éß\u0301🙂\ud800\udfff"
        for _ in range(350):
            value = "".join(rng.choices(alphabet, k=rng.randrange(25, 350)))
            terms = [value[start:start + rng.randrange(0, 5)]
                     for start in (rng.randrange(len(value)) for _ in range(rng.randrange(0, 12)))]
            terms += ["absent"]
            for width in (6, rng.randrange(1, len(value)), len(value) - 1):
                self.compare(value, terms, width)

    def test_unsupported_inputs_do_not_sort_or_call_dependencies(self):
        class Values(list):
            pass

        class Text(str):
            pass

        value = "target " * 30
        normal = (value, ["target"], [(20, "target"), (2, "target")], 30)
        cases = [
            (Text(value), normal[1], normal[2], 30),
            (value, Values(["target"]), normal[2], 30),
            (value, (["target"]), Values(normal[2]), 30),
            (value, [Text("target")], normal[2], 30),
            (value, ["target"] * 65, normal[2], 30),
            (value, normal[1], normal[2], 30.0),
            (value, normal[1], normal[2], True),
            (value, normal[1], normal[2], 10 ** 100),
            (value, normal[1], [(10 ** 100, "target")], 30),
            (value, normal[1], [(-1, "target")], 30),
            (value, normal[1], [(2, "unknown")], 30),
            (value, normal[1], [[2, "target"]], 30),
            (value, normal[1], [(2, "target")] * 2561, 30),
        ]
        for text, terms, positions, width in cases:
            before = list(positions)

            def forbidden(*args):
                self.fail("unsupported input called a dependency")

            self.assertIs(NATIVE.excerpt_window(text, terms, positions, width,
                                                forbidden, forbidden, forbidden), NotImplemented)
            self.assertEqual(list(positions), before)


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeWindowDispatchTests(unittest.TestCase):
    VALUE = "Background café Straße 👩🏽‍💻. " * 12 + "\n缓存现在保留23分钟。\n" + "Later. " * 10

    def compare_paths(self, operation):
        values = []
        for backend in (None, NATIVE):
            with patch.object(lexical, "_NATIVE", backend):
                values.append(outcome(operation))
        self.assertEqual(values[0], values[1])
        return values[0]

    def test_default_public_excerpt_calls_complete_native_window(self):
        with patch.object(NATIVE, "excerpt_window", wraps=NATIVE.excerpt_window) as observed:
            actual = lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"])
            observed.assert_called_once()
        with patch.object(lexical, "_NATIVE", None):
            self.assertEqual(actual, lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"]))

    def test_complete_public_outputs_and_unusual_inputs(self):
        class Text(str):
            pass

        class Values(list):
            pass

        factories = [lambda: None, lambda: [], lambda: [""], lambda: ["strasse", "strasse"],
                     lambda: ("strasse", "缓存"), lambda: Values(["strasse"]),
                     lambda: iter(["strasse", "缓存"]), lambda: [Text("strasse")],
                     lambda: ["q" + str(index) for index in range(65)],
                     lambda: [None], lambda: [b"strasse"], lambda: "cafe"]
        for factory in factories:
            for budget in (-1, 0, 7, 8, 90, 5000, 8.5):
                self.compare_paths(lambda: lexical.excerpt(self.VALUE, "cafe", budget,
                                                          prepared_terms=factory()))
        for value in ("ß" * 10, "\ud800é🙂" * 20, "a\u0315\u0300" * 30, Text(self.VALUE)):
            self.compare_paths(lambda: lexical.excerpt(value, "", 12, prepared_terms=["", "ss", "a"]))

    def test_patched_window_dependencies_keep_calls_and_exceptions(self):
        for owner, name in ((lexical, "bisect_left"), (lexical, "bisect_right"),
                            (math, "log1p"), (math, "fsum"), (lexical, "_evidence_units")):
            ordinary = getattr(owner, name)
            traces = []
            for backend in (None, NATIVE):
                calls = []

                def observe(*args, **kwargs):
                    if name == "fsum":
                        args = (tuple(args[0]),)
                    calls.append((args, kwargs))
                    return ordinary(*args, **kwargs)

                with patch.object(lexical, "_NATIVE", backend), patch.object(owner, name, observe):
                    actual = lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"])
                traces.append((actual, calls))
            self.assertEqual(traces[0], traces[1])
            with patch.object(owner, name, side_effect=RuntimeError("custom " + name)):
                self.assertEqual(self.compare_paths(lambda: lexical.excerpt(
                    self.VALUE, "", 90, prepared_terms=["strasse"]))[0], "error")

    def test_patched_counter_method_and_native_dependencies_fall_back(self):
        ordinary = Counter.__missing__
        traces = []
        for backend in (None, NATIVE):
            calls = []

            def missing(instance, key):
                calls.append(key)
                return ordinary(instance, key)

            with patch.object(Counter, "__missing__", missing), patch.object(lexical, "_NATIVE", backend):
                actual = lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"])
            traces.append((actual, calls))
        self.assertEqual(traces[0], traces[1])
        for name in ("evidence_units", "literal_positions"):
            with patch.object(NATIVE, name, wraps=getattr(NATIVE, name)), \
                    patch.object(NATIVE, "excerpt_window", side_effect=AssertionError("must fall back")):
                lexical.excerpt(self.VALUE, "", 90, prepared_terms=["strasse", "缓存"])

    def test_modified_evidence_observes_original_sort_order(self):
        value, positions = "target " * 40, [(28, "target"), (0, "target"), (14, "target")]

        def evidence(text, width):
            self.assertEqual(positions, sorted(positions))
            return reference_units(text, width)

        with patch.object(NATIVE, "literal_positions", return_value=positions), \
                patch.object(lexical, "_evidence_units", evidence), \
                patch.object(NATIVE, "excerpt_window", side_effect=AssertionError("must fall back")):
            actual = lexical.excerpt(value, "", 42, prepared_terms=["target"])
        self.assertEqual(actual, reference_window(value, ["target"], list(positions), 40))

    def test_dependencies_modified_before_import_are_not_certified(self):
        script = r'''
import bisect, collections, json, math, sys
name = sys.argv[1]
if name == "bisect_left":
    ordinary = bisect.bisect_left
    bisect.bisect_left = lambda *args, **kwargs: ordinary(*args, **kwargs)
elif name == "Counter":
    ordinary = collections.Counter.__missing__
    collections.Counter.__missing__ = lambda self, key: ordinary(self, key)
else:
    ordinary = getattr(math, name)
    setattr(math, name, lambda *args: ordinary(*args))
from memory_book import text
assert not text._NATIVE_WINDOW_CERTIFIED
value = "prefix " * 30 + "\ntarget 317ms.\n" + "tail " * 30
actual = text.excerpt(value, "", 40, prepared_terms=["target"])
text._NATIVE = None
expected = text.excerpt(value, "", 40, prepared_terms=["target"])
print(json.dumps([actual, expected]))
'''
        environment = dict(os.environ, MEMORY_BOOK_TEXT_BACKEND="native", PYTHONDONTWRITEBYTECODE="1")
        for dependency in ("bisect_left", "Counter", "log1p", "fsum"):
            process = subprocess.run([sys.executable, "-c", script, dependency], cwd=ROOT,
                                     env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
            actual, expected = json.loads(process.stdout)
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
