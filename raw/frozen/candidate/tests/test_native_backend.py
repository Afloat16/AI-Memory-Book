"""Native text loops must preserve Python evidence, coordinates and fallbacks.

The small references below use the original regex/Unicode primitives, not the
native implementation. Full recall comparisons use one database and explicitly
clear connection-local work caches before switching the text backend.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import unicodedata
import unittest
from unittest.mock import Mock, patch

from memory_book import MemoryBook
from memory_book import store
from memory_book import text as lexical


ROOT = Path(__file__).resolve().parents[1]
NATIVE = (importlib.import_module("memory_book._native")
          if importlib.util.find_spec("memory_book._native") is not None else None)


def reference_ascii(text, query, stop, *, camel=True):
    if camel:
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).casefold()
    values = re.findall(r"[a-z0-9]+", text)
    return [value for value in values if value not in stop] if query else values


def reference_fold(text):
    pieces, positions = [], []
    for index, character in enumerate(text):
        piece = "".join(character for character in
                        unicodedata.normalize("NFKD", character).casefold()
                        if unicodedata.category(character) != "Mn")
        pieces.append(piece)
        positions.extend([index] * len(piece))
    return "".join(pieces), positions


_CJK_RANGES = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_UNICODE_RUNS = re.compile(rf"[{_CJK_RANGES}]+|[^\W_{_CJK_RANGES}]+(?:[_./:-][^\W_{_CJK_RANGES}]+)*")
_ONLY_CJK = re.compile(rf"^[{_CJK_RANGES}]+$")


def reference_unicode_tokens(text, query, stop, zh_stop):
    result = []
    for match in _UNICODE_RUNS.finditer(text):
        value = match.group()
        if _ONLY_CJK.fullmatch(value):
            parts = [value] if len(value) == 1 else [value[i:i + 2] for i in range(len(value) - 1)]
            result.extend(part for part in parts if not query or part not in zh_stop)
        else:
            result.extend(part for part in re.split(r"[_./:-]+", value)
                          if part and (not query or part not in stop))
    return result


def reference_units(text, width):
    units = []
    for line in re.finditer(r"[^\n]+", text):
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
            while start < hi and text[start].isspace():
                start += 1
        if start < hi and hi - start <= width:
            units.append((start, hi))
    return units


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeLoopEquivalenceTests(unittest.TestCase):
    def test_ascii_pairs_preserve_camel_boundaries_duplicates_and_stop_order(self):
        for left in range(128):
            for right in range(128):
                value = chr(left) + chr(right)
                for query in (False, True):
                    self.assertEqual(NATIVE.terms_ascii(value, query, lexical.STOP),
                                     reference_ascii(value, query, lexical.STOP),
                                     (repr(value), query))
        cases = ["HTTP2Parser HTTPParser parseHTTPResponse parse_http_response",
                 "abcAbc aA1B a1B A1b 17ms foo..bar/foo::bar",
                 "a an the cache cache current final cache\x00value"]
        rng = random.Random(72139)
        cases.extend("".join(chr(rng.randrange(128)) for _ in range(400)) for _ in range(40))
        for value in cases:
            for query in (False, True):
                self.assertEqual(NATIVE.terms_ascii(value, query, lexical.STOP),
                                 reference_ascii(value, query, lexical.STOP))

    def test_normalized_ascii_scanner_does_not_casefold_or_split_camel_again(self):
        for value in ("", "aBcd HTTP2Parser a1B _x_y", "current cache cache", "x\x00y\r\nz"):
            for query in (False, True):
                self.assertEqual(NATIVE.ascii_tokens(value, query, lexical.STOP),
                                 reference_ascii(value, query, lexical.STOP, camel=False))

    def test_unicode_token_character_classes_match_regex_for_every_codepoint(self):
        # Small independent blocks cover all Unicode values, including lone
        # surrogates and the unassigned values inside the fixed CJK ranges.
        for start in range(0, 0x110000, 4096):
            value = " ".join(chr(codepoint) for codepoint in range(start, start + 4096))
            for query in (False, True):
                self.assertEqual(NATIVE.unicode_tokens(value, query, lexical.STOP, lexical.ZH_STOP),
                                 reference_unicode_tokens(value, query, lexical.STOP, lexical.ZH_STOP),
                                 (hex(start), query))

    def test_unicode_tokens_keep_cjk_bigram_boundaries_and_identifier_piece_order(self):
        cases = ["", "普通 words 当前缓存有效期 foo_bar/path.ext:a-b::c", "当前__缓存/如何.失效",
                 "HTTPParser Straße café İ x\u0301y ١٢٣ ²Ⅸ ﻻ", "a\u302eb\ufe0fc\U0001d165d",
                 "A中🙂B \ud800word\udfff \U00020000\U00020001汉字",
                 "\u33ff\u3400\u4dbf\u4dc0\u4dff\u4e00\u9fff\ua000\uf8ff\uf900\ufaff\ufb00"]
        rng = random.Random(46912)
        alphabet = "AaBz019_./:- \t\n缓存当前如何失效中文éßİ\u302e\u0301١²Ⅸﻻ🙂\U00020000\x00"
        cases.extend("".join(rng.choices(alphabet, k=200)) for _ in range(100))
        for value in cases:
            for query in (False, True):
                self.assertEqual(NATIVE.unicode_tokens(value, query, lexical.STOP, lexical.ZH_STOP),
                                 reference_unicode_tokens(value, query, lexical.STOP, lexical.ZH_STOP),
                                 (repr(value), query))

    def test_stop_membership_keeps_order_and_propagates_the_original_exception(self):
        class Stop:
            def __init__(self):
                self.calls = []

            def __contains__(self, value):
                self.calls.append(value)
                return value == "skip"

        for method in (NATIVE.terms_ascii, NATIVE.ascii_tokens):
            stop = Stop()
            self.assertEqual(method("keep skip keep", True, stop), ["keep", "keep"])
            self.assertEqual(stop.calls, ["keep", "skip", "keep"])
            self.assertEqual(method("keep", False, object()), ["keep"])
            error = RuntimeError("custom membership")

            class Broken:
                def __contains__(self, value):
                    raise error

            with self.assertRaises(RuntimeError) as raised:
                method("keep", True, Broken())
            self.assertIs(raised.exception, error)

    def test_fold_keeps_codepoint_coordinates_and_the_historical_transform_order(self):
        cases = ["", "café Straße 缓存45秒。\n" * 30, "a\u0315\u0300\u0327b",
                 "\u0345a\u302eb\ufe0fc\U0001d165d", "ＡPI ① Ⅸ ﻻ 👩🏽‍💻",
                 "\ud800word\udfff", "\x00A中🙂B\U0010ffff"]
        rng = random.Random(23991)
        cases.extend("".join(chr(rng.randrange(0x110000)) for _ in range(100))
                     for _ in range(60))
        for value in cases:
            self.assertEqual(NATIVE.fold_excerpt_source(value, unicodedata.normalize,
                                                       unicodedata.category),
                             reference_fold(value), repr(value))

    def test_fold_cache_is_local_to_one_call_and_callback_failures_are_preserved(self):
        normalizations = []

        def normalize(form, value):
            normalizations.append((form, value))
            return unicodedata.normalize(form, value)

        for value in ("éßé", "AéAß A"):
            normalizations.clear()
            for _ in range(2):
                folded, positions = NATIVE.fold_excerpt_source(value, normalize, unicodedata.category)
                self.assertEqual((folded, positions), reference_fold(value))
                positions.clear()
            self.assertEqual(normalizations, [("NFKD", character) for character in dict.fromkeys(value)] * 2)
        for callback in ("normalize", "category"):
            error = RuntimeError(callback + " failure")

            def fail(*args):
                raise error

            with self.assertRaises(RuntimeError) as raised:
                NATIVE.fold_excerpt_source("é", fail if callback == "normalize" else unicodedata.normalize,
                                           fail if callback == "category" else unicodedata.category)
            self.assertIs(raised.exception, error)

    def test_evidence_units_match_regex_boundaries_and_python_unicode_whitespace(self):
        cases = ["", "\n\n", "A short line. Qualification remains.\nAnother line.",
                 "A.\u00a0B!\u2003C?\x85D。\u2028缓存！\u3000结尾？ tail",
                 "a...b!? no decimal 1.5 break.\r\n\tend",
                 "\ud800. \udfff! A中🙂B。 after\x00word"]
        rng = random.Random(81731)
        alphabet = "aB3中🙂 .!?。！？\n\r\t\v\f\x1c\x85\u00a0\u2003\u2028\u3000\x00"
        cases.extend("".join(rng.choices(alphabet, k=150)) for _ in range(60))
        for value in cases:
            for width in (-1, 0, 1, 2, 7, 16, 80, sys.maxsize):
                self.assertEqual(NATIVE.evidence_units(value, width), reference_units(value, width),
                                 (repr(value), width))

    def test_native_entrypoints_reject_inputs_outside_their_exact_type_contract(self):
        class Text(str):
            pass

        for method in (NATIVE.terms_ascii, NATIVE.ascii_tokens):
            for value in (None, b"abc", Text("abc"), "é"):
                with self.subTest(method=method.__name__, value=repr(value)), self.assertRaises((TypeError, ValueError)):
                    method(value, False, lexical.STOP)
            for query in (0, 1, None, object()):
                with self.assertRaises(TypeError):
                    method("abc", query, lexical.STOP)
        for value in (None, b"abc", Text("abc")):
            with self.assertRaises(TypeError):
                NATIVE.fold_excerpt_source(value, unicodedata.normalize, unicodedata.category)
            with self.assertRaises(TypeError):
                NATIVE.evidence_units(value, 20)
            with self.assertRaises(TypeError):
                NATIVE.unicode_tokens(value, False, lexical.STOP, lexical.ZH_STOP)
        for query in (0, 1, None, object()):
            with self.assertRaises(TypeError):
                NATIVE.unicode_tokens("缓存", query, lexical.STOP, lexical.ZH_STOP)


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeDispatchCompatibilityTests(unittest.TestCase):
    def compare_paths(self, operation):
        values = []
        for backend in (None, NATIVE):
            with patch.object(lexical, "_NATIVE", backend):
                try:
                    values.append(("value", operation()))
                except Exception as error:
                    values.append(("error", type(error), error.args))
        self.assertEqual(values[0], values[1])
        return values[0]

    def test_guarded_plain_inputs_really_dispatch_to_each_native_helper(self):
        observed = Mock(wraps=NATIVE)
        with patch.object(lexical, "_NATIVE", observed):
            self.assertEqual(lexical.terms("cacheKey"), ["cache", "key"])
            self.assertEqual(lexical.terms("café"), ["cafe"])
            self.assertEqual(lexical.terms("当前缓存", query=True), ["前缓", "缓存"])
            self.assertEqual(lexical._fold_excerpt_source("Straße"),
                             ("strasse", [0, 1, 2, 3, 4, 4, 5]))
            self.assertEqual(lexical._evidence_units("One. Two!", 5), [(0, 4), (5, 9)])
        observed.terms_ascii.assert_called_once()
        observed.ascii_tokens.assert_called_once()
        observed.unicode_tokens.assert_called_once()
        observed.fold_excerpt_source.assert_called_once()
        observed.evidence_units.assert_called_once()

    def test_dependencies_patched_before_first_import_are_not_certified_as_ordinary(self):
        script = r'''
import json, re, sys, unicodedata
if sys.argv[1] == "finditer":
    re.finditer = lambda *args, **kwargs: iter(())
elif sys.argv[1] == "normalize":
    class Normalized:
        def casefold(self):
            return ["x", "y"]
    unicodedata.normalize = lambda form, value: Normalized()
else:
    ordinary_compile = re.compile
    class CustomRuns:
        def findall(self, value):
            return ["custom", "tokens"]
    def compile(pattern, flags=0):
        return CustomRuns() if pattern == r"[a-z0-9]+" else ordinary_compile(pattern, flags)
    re.compile = compile
from memory_book import text
operation = {"finditer": lambda: text._evidence_units("abc", 10),
             "compile": lambda: text.terms("abc"),
             "normalize": lambda: text._fold_excerpt_source("ab")}[sys.argv[1]]
native = operation()
text._NATIVE = None
print(json.dumps([native, operation()]))
'''
        environment = dict(os.environ, MEMORY_BOOK_TEXT_BACKEND="native")
        for dependency in ("finditer", "compile", "normalize"):
            with self.subTest(dependency=dependency):
                result = subprocess.run([sys.executable, "-c", script, dependency], cwd=ROOT,
                                        env=environment, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                accelerated, reference = json.loads(result.stdout)
                self.assertEqual(accelerated, reference)

    def test_custom_patterns_and_stop_filter_keep_original_behavior(self):
        class Camel:
            def sub(self, replacement, value):
                return "CustomWords customWords"

        class Runs:
            def findall(self, value):
                return ["custom", "the", "custom"]

        for name, replacement in (("CAMEL_BOUNDARY", Camel()), ("ASCII_RUNS", Runs()),
                                  ("STOP", frozenset({"cache"}))):
            with self.subTest(dependency=name), patch.object(lexical, name, replacement):
                self.compare_paths(lambda: lexical.terms("Current cache cacheKey", query=True))

    def test_custom_unicode_patterns_and_stop_sets_keep_original_behavior(self):
        class Runs:
            def finditer(self, value):
                return iter(())

        class Cjk:
            def fullmatch(self, value):
                return None

        class Separator:
            def split(self, value):
                return ["custom"]

        dependencies = (("RUNS", Runs()), ("CJK_RUN", Cjk()),
                        ("IDENTIFIER_SEPARATOR", Separator()),
                        ("ZH_STOP", frozenset({"缓存"})), ("STOP", frozenset({"cafe"})))
        for name, replacement in dependencies:
            with self.subTest(dependency=name), patch.object(lexical, name, replacement):
                self.compare_paths(lambda: lexical.terms("cafe 当前缓存", query=True))

    def test_str_subclass_and_nonboolean_query_keep_python_method_and_error_behavior(self):
        class Text(str):
            def isascii(self):
                raise RuntimeError("subclass isascii")

        class IterableText(str):
            def __iter__(self):
                return iter("éß")

        class Query:
            def __bool__(self):
                raise RuntimeError("custom query truth")

        self.assertEqual(self.compare_paths(lambda: lexical.terms(Text("ASCII")))[0], "error")
        self.compare_paths(lambda: lexical.terms("current cache", query=Query()))
        self.compare_paths(lambda: lexical._fold_excerpt_source(IterableText("original")))

    def test_patched_unicode_callbacks_preserve_observable_calls_and_exceptions(self):
        for attribute in ("normalize", "category"):
            original = getattr(unicodedata, attribute)
            traces = []
            for backend in (None, NATIVE):
                calls = []

                def observe(*args):
                    calls.append(args)
                    return original(*args)

                with patch.object(lexical, "_NATIVE", backend), patch.object(unicodedata, attribute, observe):
                    value = lexical._fold_excerpt_source("éßé\u0301")
                traces.append((value, calls))
            self.assertEqual(traces[0], traces[1])
            error = RuntimeError("patched " + attribute)
            with patch.object(unicodedata, attribute, side_effect=error):
                self.assertEqual(self.compare_paths(lambda: lexical._fold_excerpt_source("é"))[0], "error")

    def test_patched_regex_iterator_is_not_bypassed_by_evidence_units(self):
        original = re.finditer
        traces = []
        for backend in (None, NATIVE):
            calls = []

            def observe(*args, **kwargs):
                calls.append(args)
                return original(*args, **kwargs)

            with patch.object(lexical, "_NATIVE", backend), patch.object(re, "finditer", observe):
                value = lexical._evidence_units("One. Two!\nThree?", 8)
            traces.append((value, calls))
        self.assertEqual(traces[0], traces[1])

    def test_excerpt_early_returns_noninteger_budgets_and_prepared_terms_keep_behavior(self):
        value = "Background café Straße 👩🏽‍💻. " * 12 + "\n缓存现在保留23分钟。\n" + "Later. " * 10
        for budget in (-1, 0, 1, 7, 8, 16, 63, 5000, True, 8.5, 10 ** 100):
            for prepared in (None, [], ["strasse", "缓存"], ["strasse", "strasse"]):
                with self.subTest(budget=budget, prepared=prepared):
                    self.compare_paths(lambda: lexical.excerpt(value, "cafe 缓存", budget,
                                                               prepared_terms=prepared))


def sessions():
    def session(project, identity, created, answer):
        return {"project": project, "project_name": "Similar engineering service",
                "task_id": "same-task", "task_title": "HTTPParser café 配置",
                "session_id": identity, "title": "Parser cache configuration",
                "created_at": created, "messages": [
                    {"role": "user", "content": "Current HTTPParser timeout and 缓存有效期"},
                    {"role": "assistant", "content": answer}]}

    return [
        session("alpha", "old", "2026-01-01T00:00:00Z",
                "HTTPParser timeout is 17ms. 缓存有效期为 11 分钟。 café Straße."),
        session("alpha", "current", "2026-02-01T00:00:00Z",
                "http_parser timeout is 29ms. 缓存有效期为 23 分钟。 café Straße 👩🏽‍💻.\n" +
                "Background detail. " * 20 + "\nThe café Straße pressure is 82 pascals.\n" +
                "Qualification: preserve a\u0315\u0300\u0327b and e\u0301 source coordinates. " * 8),
        session("beta", "current", "2026-03-01T00:00:00Z",
                "HTTPParser timeout is 999ms. 缓存有效期为 999 分钟。 café Straße pressure is 999."),
        session("alpha", "serializer", "2026-02-02T00:00:00Z",
                "XMLSerializer preserves UTF-8 encoding. ＡPI/cacheKey uses the approved setting."),
    ]


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeMemoryBookEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="adaptive", max_page_chars=240,
                               min_page_chars=0, cache_size=16)
        self.addCleanup(self.book.close)
        with patch.object(lexical, "_NATIVE", None), patch.object(store, "_now", return_value="2026-04-01T00:00:00Z"):
            self.ingested = [self.book.ingest(source) for source in sessions()]

    def recall(self, backend, query, **options):
        self.book._directory_tokens.cache_clear()
        self.book._token_count_memo = None
        with patch.object(lexical, "_NATIVE", backend):
            response = self.book.recall(query, use_cache=False, **options)
        response.pop("latency_ms")
        return response

    def assert_source_coordinates(self, response):
        for hit in response["results"]:
            page = self.book.read(hit["id"])["content"]
            for lo, hi in hit["excerpt_spans"]:
                self.assertIn(page[lo:hi], hit["text"])
            for ref in hit["source_refs"]:
                turn = self.book.db.execute("SELECT t.content FROM turns t JOIN sessions s ON s.id=t.session_pk "
                    "WHERE s.project_id=? AND s.external_id=? AND t.ordinal=?",
                    (ref["project"], ref["session_id"], ref["turn_index"])).fetchone()[0]
                self.assertEqual(page[ref["start"]:ref["end"]], turn[ref["turn_start"]:ref["turn_end"]])

    def test_ingestion_ids_hashes_pages_fts_and_source_coordinates_match(self):
        with MemoryBook(":memory:", segmentation="adaptive", max_page_chars=240, min_page_chars=0) as native:
            with patch.object(lexical, "_NATIVE", NATIVE), patch.object(store, "_now", return_value="2026-04-01T00:00:00Z"):
                actual = [native.ingest(source) for source in sessions()]
            self.assertEqual(actual, self.ingested)
            for table in ("projects", "chapters", "sessions", "turns", "sections", "pages",
                          "pages_fts", "pages_stem_fts"):
                sql = "SELECT * FROM " + table + " ORDER BY rowid"
                self.assertEqual([tuple(row) for row in native.db.execute(sql)],
                                 [tuple(row) for row in self.book.db.execute(sql)], table)

    def test_full_payloads_match_for_scope_history_identifiers_unicode_and_character_caps(self):
        cases = [(query, {"project": "alpha"}) for query in
                 ("current HTTPParser timeout", "previous HTTPParser timeout", "缓存有效期",
                  "cafe strasse pressure", "HTTPParser XMLSerializer", '"HttpParser" OR *')]
        cases += [("HTTPParser timeout", scope) for scope in
                  ({}, {"project": "beta"}, {"project": "missing"},
                   {"chapter": self.ingested[0]["chapter_id"]},
                   {"project": "alpha", "session": "current"})]
        cases += [("cafe strasse pressure", {"project": "alpha", "budget_chars": chars})
                  for chars in (0, 1, 7, 64, 350, 2400)]
        cases += [("HTTPParser XMLSerializer", {"project": "alpha", "limit": 2, "coverage": True}),
                  ("HTTPParser timeout", {"project": "alpha", "strategy": "flat"})]
        for query, options in cases:
            with self.subTest(query=query, options=options):
                expected = self.recall(None, query, **options)
                actual = self.recall(NATIVE, query, **options)
                self.assertEqual(actual, expected)
                self.assert_source_coordinates(actual)
                if options.get("project") == "alpha":
                    self.assertNotIn("999", actual["context"])

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Install .[tokens]")
    def test_token_caps_keep_complete_payload_counts_and_source_spans(self):
        for tokenizer in ("cl100k_base", "o200k_base"):
            for cap in (0, 64, 256, 1024):
                options = {"project": "alpha", "budget_chars": 8000,
                           "budget_tokens": cap, "tokenizer": tokenizer}
                with self.subTest(tokenizer=tokenizer, cap=cap):
                    expected = self.recall(None, "cafe strasse pressure 缓存", **options)
                    actual = self.recall(NATIVE, "cafe strasse pressure 缓存", **options)
                    self.assertEqual(actual, expected)
                    self.assert_source_coordinates(actual)

    def test_persistent_cache_is_interchangeable_and_replacement_invalidates_it(self):
        query, options = "current HTTPParser timeout", {"project": "alpha", "limit": 1}
        with patch.object(lexical, "_NATIVE", None):
            expected = self.book.recall(query, **options)
        with patch.object(lexical, "_NATIVE", NATIVE):
            cached = self.book.recall(query, **options)
        expected.pop("latency_ms")
        cached.pop("latency_ms")
        self.assertTrue(cached["cache_hit"])
        expected["cache_hit"] = True
        self.assertEqual(cached, expected)
        changed = sessions()[1]
        changed["messages"][1]["content"] = "http_parser timeout is 43ms. 缓存有效期为 31 分钟。"
        with patch.object(lexical, "_NATIVE", NATIVE):
            self.book.ingest(changed)
            updated = self.book.recall(query, **options)
        self.assertFalse(updated["cache_hit"])
        self.assertNotEqual(updated["revision"], expected["revision"])
        updated.pop("latency_ms")
        self.assertEqual(updated, self.recall(None, query, **options))


class NativeBackendSelectionTests(unittest.TestCase):
    def select(self, backend, *, missing=False):
        script = r'''
import importlib, json, sys
blocked = []
class MissingNative:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "memory_book._native":
            blocked.append(fullname)
            raise ModuleNotFoundError("native fixture unavailable", name=fullname)
if sys.argv[1] == "missing":
    sys.meta_path.insert(0, MissingNative())
try:
    selected = importlib.import_module("memory_book._text_backend")
    from memory_book.text import terms
    print(json.dumps({"requested": selected.REQUESTED_BACKEND, "backend": selected.BACKEND_NAME,
        "native": selected.NATIVE is not None, "terms": terms("HTTPParser cacheKey"), "blocked": blocked}))
except Exception as error:
    print(json.dumps({"error": type(error).__name__, "message": str(error),
        "cause": type(error.__cause__).__name__ if error.__cause__ else None, "blocked": blocked}))
'''
        env = dict(os.environ, MEMORY_BOOK_TEXT_BACKEND=backend)
        result = subprocess.run([sys.executable, "-c", script, "missing" if missing else "available"],
                                cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_python_mode_does_not_import_the_extension(self):
        result = self.select("python", missing=True)
        self.assertEqual(result["backend"], "python")
        self.assertFalse(result["native"])
        self.assertEqual(result["blocked"], [])
        self.assertEqual(result["terms"], ["httpparser", "cache", "key"])

    def test_auto_falls_back_but_forced_native_exposes_the_missing_extension(self):
        result = self.select("auto", missing=True)
        self.assertEqual(result["backend"], "python")
        self.assertFalse(result["native"])
        result = self.select("native", missing=True)
        self.assertEqual(result["error"], "RuntimeError")
        self.assertIn(result["cause"], ("ImportError", "ModuleNotFoundError"))
        self.assertTrue(result["blocked"])

    def test_invalid_backend_fails_explicitly(self):
        self.assertEqual(self.select("unrecognized-backend")["error"], "ValueError")

    @unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
    def test_native_mode_uses_the_installed_extension(self):
        result = self.select("native")
        self.assertEqual(result["backend"], "native")
        self.assertTrue(result["native"])
        self.assertEqual(result["terms"], ["httpparser", "cache", "key"])


if __name__ == "__main__":
    unittest.main()
