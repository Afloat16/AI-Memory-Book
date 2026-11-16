"""Independent v0.8.1 source-unit and projection differential checks.

No tokenizer dependency is needed. The reference functions below preserve the
released Python bodies, including fence handling, bisect boundaries, errors,
and cache mutation order. Ordered span lists, not sets, are compared.
"""
from __future__ import annotations

from bisect import bisect_left
import copy
import importlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from memory_book import token_budget as budget


ROOT = Path(__file__).resolve().parents[1]
NATIVE = (importlib.import_module("memory_book._native")
          if importlib.util.find_spec("memory_book._native") is not None else None)
HAS_NATIVE_SOURCE = NATIVE is not None and all(hasattr(NATIVE, name) for name in
    ("source_units", "projected_units", "source_map_matches"))
ROLE = re.compile(r"^(?:USER|ASSISTANT|SYSTEM|DEVELOPER|TOOL):[ \t]*")
OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
SENTENCE = re.compile(r"[。！？]|[.!?](?=\s|$)")


def reference_source_units(text):
    primary, sentences = [], []
    offset, fence = 0, None
    for line in text.splitlines(keepends=True):
        value = line.rstrip("\r\n")
        lo, hi = offset, offset + len(value)
        offset += len(line)
        if fence is not None:
            character, size, start = fence
            if re.fullmatch(r"[ \t]{0,3}" + re.escape(character) + "{" + str(size) + r",}[ \t]*", value):
                primary.append((start, hi))
                fence = None
            continue
        opening = OPEN.fullmatch(ROLE.sub("", value, count=1))
        if opening and (opening[1][0] != "`" or "`" not in opening[2]):
            fence = (opening[1][0], len(opening[1]), lo)
            continue
        if not value.strip():
            continue
        start = lo + len(value) - len(value.lstrip())
        end = hi - len(value) + len(value.rstrip())
        primary.append((start, end))
        cursor = start
        for match in SENTENCE.finditer(text[start:end]):
            stop = start + match.end()
            if cursor < stop:
                sentences.append((cursor, stop))
            cursor = stop
            while cursor < end and text[cursor].isspace():
                cursor += 1
        if cursor < end:
            sentences.append((cursor, end))
    spans = set(primary + sentences)
    for i, (start, _) in enumerate(primary):
        for j in range(i + 1, min(i + 3, len(primary))):
            spans.add((start, primary[j][1]))
    if fence is None and text:
        spans.add((0, len(text)))
    return sorted(spans)


def reference_projected_units(row, turns, unit_cache, refs):
    spans = set()
    for ref in refs:
        key = (row["session_pk"], ref["turn_index"])
        original = turns[key]
        if key not in unit_cache:
            unit_cache[key] = reference_source_units(original)
        units = unit_cache[key]
        if isinstance(ref.get("turn_start"), int) and isinstance(ref.get("turn_end"), int):
            first = bisect_left(units, (ref["turn_start"],))
            stop = bisect_left(units, (ref["turn_end"],))
            candidates = (units[i] for i in range(first, stop))
        else:
            candidates = iter(units)
        for start, end in candidates:
            if ref["turn_start"] <= start < end <= ref["turn_end"]:
                lo = ref["start"] + start - ref["turn_start"]
                hi = ref["start"] + end - ref["turn_start"]
                if row["content"][lo:hi] != original[start:end]:
                    raise ValueError("Page source coordinates do not match the original turn")
                spans.add((lo, hi))
    return sorted(spans)


def reference_source_map_matches(row, turns, refs):
    content = row["content"]
    for ref in refs:
        original = turns.get((row["session_pk"], ref["turn_index"]))
        start, end = ref.get("start"), ref.get("end")
        turn_start, turn_end = ref.get("turn_start"), ref.get("turn_end")
        if (original is None or
                not all(isinstance(value, int) for value in (start, end, turn_start, turn_end)) or
                not (0 <= start <= end <= len(content) and 0 <= turn_start <= turn_end <= len(original)) or
                end - start != turn_end - turn_start or
                content[start:end] != original[turn_start:turn_end]):
            return False
    return True


def outcome(operation):
    try:
        return "value", operation()
    except Exception as error:
        return "error", type(error), error.args


def fixture(text="USER: Alpha. Beta!\n\nASSISTANT: 答案。 More information.", lo=0, hi=None):
    hi = len(text) if hi is None else hi
    row = {"session_pk": "s", "content": text[lo:hi], "id": "p"}
    refs = [{"turn_index": 0, "turn_start": lo, "turn_end": hi,
             "start": 0, "end": hi - lo}]
    return row, {("s", 0): text}, refs


@unittest.skipUnless(HAS_NATIVE_SOURCE, "Native source helpers are not installed")
class NativeSourceUnitsTests(unittest.TestCase):
    def compare(self, text):
        expected = reference_source_units(text)
        self.assertEqual(NATIVE.source_units(text), expected, repr(text[:160]))
        with patch.object(budget, "_NATIVE", NATIVE):
            self.assertEqual(budget.source_units(text), expected)

    def test_public_default_dispatch_uses_new_native_methods(self):
        row, turns, refs = fixture()
        native = Mock(wraps=NATIVE)
        with patch.object(budget, "_NATIVE", native):
            self.assertTrue(budget._native_source_units_ready())
            budget.source_units(turns[("s", 0)])
            budget._projected_units(row, turns, {}, refs)
            self.assertTrue(budget._source_map_matches(row, turns, refs))
        self.assertEqual(native.source_units.call_count, 1)
        self.assertEqual(native.projected_units.call_count, 1)
        self.assertEqual(native.source_map_matches.call_count, 1)

    def test_fences_roles_and_neighbor_spans(self):
        cases = ["", "\n", " \t\r\n", "A. B! C?", "A.B?C!", "甲。乙！丙？丁",
                 " USER: A\n ASSISTANT: B\n\n C\nD\nE",
                 "USER: ```py\nx=1\nUSER: ```\ny=2\n```\nOutside.",
                 "ASSISTANT: ````py\nx\n```\n~~~\ny\n````",
                 "before\nASSISTANT: ```py\nnever closed",
                 "```info`invalid\nordinary.\n~~~a`b\nbody\n~~~~ \t",
                 "```\nbody\n   ``` \t\nnext",
                 "```\nbody\n    ```\nnext",
                 "```\nbody\n\t\t\t```\nnext",
                 "USER: \t  ```py\nbody\n```",
                 "user: ```py\nordinary\nnot a close",
                 "SYSTEM: ~~~\nx\n~~~\nDEVELOPER: ```\ny\n```\nTOOL: ~~~\nz\n~~~",
                 "\ud800. \udfff!\n🙂甲。 e\u0301.\u00a0次句。\x00done"]
        for text in cases:
            with self.subTest(text=repr(text)):
                self.compare(text)

    def test_every_python_line_boundary_and_crlf(self):
        boundaries = ("\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e",
                      "\x85", "\u2028", "\u2029")
        for separator in boundaries:
            for trailing in ("", separator):
                for opening in ("```", "ASSISTANT: ```py", " ~~~anything"):
                    text = separator.join(["A. B", opening, "USER: ```", "body", "```", "outside."]) + trailing
                    self.compare(text)

    def test_unicode_whitespace_matches_strip_and_regex(self):
        whitespace = " \t\n\r\v\f\x1c\x1d\x1e\x1f\x85\xa0\u1680" + "".join(
            chr(i) for i in range(0x2000, 0x200b)) + "\u2028\u2029\u202f\u205f\u3000"
        for space in whitespace:
            for punctuation in ".!?。！？":
                self.compare(space + "A" + punctuation + space + "B" + space)
                self.compare("```" + space + "body\n```" + space)

    def test_exhaustive_short_ascii_fence_boundary_classes(self):
        alphabet = "`~.\nA "
        for size in range(6):
            for parts in itertools.product(alphabet, repeat=size):
                value = "".join(parts)
                self.assertEqual(NATIVE.source_units(value), reference_source_units(value), repr(value))

    def test_seeded_random_mixed_unicode_and_fences(self):
        rng = random.Random(810929)
        fragments = ["A", " ", "\t", ". ", "!", "?", "。", "！？", "甲乙", "🙂",
                     "e\u0301", "\ud800", "\udfff", "\x00", "\xa0", "\x1f", "\x85", "\u2028",
                     "\n", "\r\n", "```", "````", "~~~", "``py`", "USER: ",
                     "ASSISTANT: ", "SYSTEM: ", "TOOL: ", "    ", "\t\t\t"]
        for _ in range(1600):
            value = "".join(rng.choices(fragments, k=rng.randrange(1, 100)))
            self.compare(value)

    def test_long_lines_and_all_unicode_coordinate_kinds(self):
        for value in ("a" * 70000 + ". end", "🙂中" * 35000 + "。下文",
                      "```\n" + "x" * 70000 + "\n```\nend"):
            self.compare(value)

    def test_subclass_and_odd_inputs_keep_reference_exceptions(self):
        class CustomText(str):
            def splitlines(self, keepends=False):
                return ["x. y\n"]
        for value in (CustomText("overridden"), b"x", None, 12, ["x"]):
            with patch.object(budget, "_NATIVE", None):
                expected = outcome(lambda: budget.source_units(value))
            with patch.object(budget, "_NATIVE", NATIVE):
                actual = outcome(lambda: budget.source_units(value))
            self.assertEqual(actual, expected)
        self.assertEqual(outcome(lambda: NATIVE.source_units(CustomText("x")))[1:],
                         (TypeError, ("text must be an exact str",)))

    def test_replaced_patterns_use_original_python_body(self):
        replacements = {"_ROLE": re.compile(r"^ANIMAL:[ \t]*"),
                        "_OPEN": re.compile(r"^(x{3,})(.*)$"),
                        "_SENTENCE": re.compile(r",")}
        for name, replacement in replacements.items():
            for text in ("ANIMAL: ```\nx\n```\nlast", "xxx\nbody\nxxx", "A,B,C"):
                with patch.object(budget, name, replacement):
                    with patch.object(budget, "_NATIVE", None):
                        expected = budget.source_units(text)
                    with patch.object(budget, "_NATIVE", NATIVE):
                        self.assertEqual(budget.source_units(text), expected)

    def test_replaced_fullmatch_and_escape_are_observed(self):
        text = "```\nvalue\n```\noutside."
        for name in ("fullmatch", "escape"):
            original = getattr(re, name)
            logs = []
            def wrapped(*args, **kwargs):
                logs.append((args, kwargs))
                return original(*args, **kwargs)
            with patch.object(re, name, wrapped):
                with patch.object(budget, "_NATIVE", None):
                    expected = budget.source_units(text)
                expected_calls = list(logs)
                logs.clear()
                with patch.object(budget, "_NATIVE", NATIVE):
                    self.assertEqual(budget.source_units(text), expected)
                self.assertEqual(logs, expected_calls)
                self.assertTrue(logs)

    def test_preimport_wrapped_regex_function_is_not_certified(self):
        program = r'''
import functools, json, re
original = re.fullmatch
calls = []
@functools.wraps(original)
def wrapper(*args, **kwargs):
    calls.append(args[0])
    return original(*args, **kwargs)
re.fullmatch = wrapper
from memory_book import token_budget as t
result = t.source_units("```\nvalue\n```\noutside.")
assert not t._NATIVE_SOURCE_CERTIFIED
assert calls and result
print(json.dumps({"certified": t._NATIVE_SOURCE_CERTIFIED, "calls": len(calls)}))
'''
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"),
               "PYTHONDONTWRITEBYTECODE": "1", "MEMORY_BOOK_TEXT_BACKEND": "native"}
        completed = subprocess.run([sys.executable, "-c", program], env=env,
                                   text=True, capture_output=True, check=True)
        self.assertFalse(json.loads(completed.stdout)["certified"])


@unittest.skipUnless(HAS_NATIVE_SOURCE, "Native source helpers are not installed")
class NativeSourceProjectionTests(unittest.TestCase):
    def compare(self, row, turns, refs, initial_cache=None):
        expected_cache = copy.deepcopy(initial_cache or {})
        actual_cache = copy.deepcopy(initial_cache or {})
        expected = outcome(lambda: reference_projected_units(row, turns, expected_cache, refs))
        with patch.object(budget, "_NATIVE", NATIVE):
            actual = outcome(lambda: budget._projected_units(row, turns, actual_cache, refs))
            matches = outcome(lambda: budget._source_map_matches(row, turns, refs))
        self.assertEqual(actual, expected, (row, refs, initial_cache))
        self.assertEqual(actual_cache, expected_cache)
        self.assertEqual(matches, outcome(lambda: reference_source_map_matches(row, turns, refs)))

    def test_complete_partial_multiref_and_duplicate_projection(self):
        text = "USER: Question?\nASSISTANT: ```py\nvalue=1\n```\nAnswer。 More.\n"
        for lo, hi in ((0, len(text)), (1, len(text) - 1), (text.index("value"), text.index("\n```")),
                       (0, text.index("ASSISTANT")), (len(text), len(text))):
            self.compare(*fixture(text, lo, hi))
        row, turns, refs = fixture(text)
        self.compare(row, turns, refs * 3)
        second = "ASSISTANT: another turn."
        original_length = len(row["content"])
        row["content"] += "\n\n" + second
        turns[("s", 1)] = second
        refs.append({"turn_index": 1, "turn_start": 0, "turn_end": len(second),
                     "start": original_length + 2, "end": len(row["content"])})
        self.compare(row, turns, refs)

    def test_seeded_random_pages_and_cache_reuse(self):
        rng = random.Random(810930)
        text = "USER: Q?\nASSISTANT: A。 B!\n\n```py\n🙂\ud800\n```\n尾声。 e\u0301 end.\n"
        cached = {("s", 0): reference_source_units(text)}
        for _ in range(700):
            lo, hi = sorted(rng.choices(range(len(text) + 1), k=2))
            row, turns, refs = fixture(text, lo, hi)
            prefix = rng.choice(("", "\n\n", "🙂 "))
            row["content"] = prefix + row["content"] + "tail"
            refs[0]["start"] += len(prefix)
            refs[0]["end"] += len(prefix)
            self.compare(row, turns, refs, cached if rng.randrange(2) else None)

    def test_native_cache_hits_keep_original_cached_list(self):
        row, turns, refs = fixture()
        existing = reference_source_units(turns[("s", 0)])
        cache = {("s", 0): existing}
        result = NATIVE.projected_units(row, turns, cache, refs)
        self.assertIsNot(result, NotImplemented)
        self.assertIs(cache[("s", 0)], existing)
        self.assertEqual(result, reference_projected_units(row, turns, {}, refs))

    def test_integer_maps_preserve_negative_slice_and_out_of_bounds_behavior(self):
        row, turns, refs = fixture("abcd")
        cached = {("s", 0): [(-9, -7), (-2, -1), (0, 1), (0, 4), (2, 4), (5, 8)]}
        for start, lo, hi in itertools.product((-9, -1, 0, 1, 4, 9), repeat=3):
            refs[0].update(start=start, turn_start=lo, turn_end=hi)
            self.compare(row, turns, refs, cached)

    def test_custom_bool_big_integer_and_noninteger_coordinates_fall_back(self):
        class IntSubclass(int):
            pass
        for value in (False, True, 10**100, -(10**100), IntSubclass(0), 0.0, None, "0"):
            for field in ("start", "end", "turn_start", "turn_end", "turn_index"):
                row, turns, refs = fixture("abcd")
                refs[0][field] = value
                self.compare(row, turns, refs)
                self.assertIs(NATIVE.source_map_matches(row, turns, refs), NotImplemented)
                if field != "end":
                    self.assertIs(NATIVE.projected_units(row, turns, {}, refs), NotImplemented)

    def test_missing_fields_and_turns_preserve_exception_order(self):
        for target, field in (("row", "session_pk"), ("row", "content"),
                              ("ref", "turn_index"), ("ref", "start"),
                              ("ref", "turn_start"), ("ref", "turn_end"), ("ref", "end")):
            row, turns, refs = fixture()
            del (row if target == "row" else refs[0])[field]
            self.compare(row, turns, refs)
        row, turns, refs = fixture()
        self.compare(row, {}, refs)
        self.compare(row, {("s", 0): None}, refs)

    def test_corruption_error_and_partial_cache_updates_are_exact(self):
        row, turns, refs = fixture("first sentence.")
        second = "second sentence."
        row["content"] += "\n\n" + "X" * len(second)
        turns[("s", 1)] = second
        refs.append({"turn_index": 1, "turn_start": 0, "turn_end": len(second),
                     "start": len("first sentence.\n\n"), "end": len(row["content"])})
        self.compare(row, turns, refs)
        row["content"] = "X" * len(row["content"])
        refs.append({"turn_index": 999, "start": 0, "end": 2, "turn_start": 0, "turn_end": 2})
        self.compare(row, turns, refs)
        cache = {}
        self.assertEqual(outcome(lambda: budget._projected_units(row, turns, cache, refs))[1:],
                         (ValueError, ("Page source coordinates do not match the original turn",)))
        self.assertEqual(set(cache), {("s", 0)})

    def test_malformed_cached_units_keep_bisect_and_unpack_errors(self):
        row, turns, refs = fixture("abcd")
        for units in ([(0,)], [(0, 1, 2)], [[0, 1]], [(0, "x")],
                      [(True, 2)], [(0.0, 2)], [(0, 10**100)],
                      [(2, 4), (0, 1)], [], ((0, 4),), iter([(0, 4)])):
            if isinstance(units, type(iter([]))):
                expected_cache = {("s", 0): iter([(0, 4)])}
                actual_cache = {("s", 0): iter([(0, 4)])}
                expected = outcome(lambda: reference_projected_units(row, turns, expected_cache, refs))
                actual = outcome(lambda: budget._projected_units(row, turns, actual_cache, refs))
                self.assertEqual(actual, expected)
            else:
                self.compare(row, turns, refs, {("s", 0): units})

    def test_custom_containers_and_string_subclasses_use_reference_path(self):
        class DictSubclass(dict):
            pass
        class ListSubclass(list):
            pass
        class TextSubclass(str):
            pass
        for modified in ("row", "turns", "refs", "ref", "cache", "content", "original", "session"):
            row, turns, refs = fixture()
            cache = {}
            if modified == "row": row = DictSubclass(row)
            if modified == "turns": turns = DictSubclass(turns)
            if modified == "refs": refs = ListSubclass(refs)
            if modified == "ref": refs[0] = DictSubclass(refs[0])
            if modified == "cache": cache = DictSubclass()
            if modified == "content": row["content"] = TextSubclass(row["content"])
            if modified == "original": turns[("s", 0)] = TextSubclass(turns[("s", 0)])
            if modified == "session": row["session_pk"] = TextSubclass("s")
            self.assertIs(NATIVE.projected_units(row, turns, cache, refs), NotImplemented)
            expected_cache = type(cache)()
            expected = reference_projected_units(row, turns, expected_cache, refs)
            self.assertEqual(budget._projected_units(row, turns, cache, refs), expected)
            self.assertEqual(cache, expected_cache)

    def test_patched_source_units_and_bisect_preserve_callback_calls(self):
        row, turns, refs = fixture()
        for name in ("source_units", "bisect_left"):
            original = getattr(budget, name)
            calls = []
            def wrapped(*args, **kwargs):
                calls.append((args, kwargs))
                return original(*args, **kwargs)
            with patch.object(budget, name, wrapped):
                with patch.object(budget, "_NATIVE", None):
                    expected = budget._projected_units(row, turns, {}, refs)
                expected_calls = list(calls)
                calls.clear()
                with patch.object(budget, "_NATIVE", NATIVE):
                    self.assertEqual(budget._projected_units(row, turns, {}, refs), expected)
                self.assertEqual(calls, expected_calls)
                self.assertTrue(calls)

    def test_uncertified_partial_fence_difference_does_not_create_new_error(self):
        text = "```\nunfinished content"
        row, turns, refs = fixture(text, 4, len(text))
        row["content"] = "X" * len(row["content"])
        self.assertFalse(budget._source_map_matches(row, turns, refs))
        self.assertEqual(budget._projected_units(row, turns, {}, refs), [])
        resolver = budget.prepare_source_units([row], turns, {row["id"]: refs})
        self.assertEqual(resolver(row), [])

    def test_json_wrapper_and_lazy_source_certificate_keep_existing_flow(self):
        row, turns, refs = fixture()
        row["source_refs"] = json.dumps(refs)
        self.assertEqual(budget.projected_units(row, turns, {}),
                         reference_projected_units(row, turns, {}, refs))
        calls = []
        def units(text):
            calls.append(text)
            return reference_source_units(text)
        with patch.object(budget, "source_units", units):
            resolver = budget.prepare_source_units([row], turns, {row["id"]: refs})
            self.assertFalse(calls)
            first = resolver(row)
            self.assertEqual(calls, [turns[("s", 0)]])
            self.assertIs(resolver(row), first)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
