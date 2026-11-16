"""Independent v0.8.0 identifier oracle for further native translations.

The reference below preserves the released regex implementation. It neither
calls identifier_terms nor shares the native scanner. Compare complete ordered
lists: a set comparison would conceal changed index frequencies and aliases.
"""

from __future__ import annotations

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
import unicodedata
import unittest
from unittest.mock import Mock, patch

from memory_book import text as lexical


ROOT = Path(__file__).resolve().parents[1]
NATIVE = (importlib.import_module("memory_book._native")
          if importlib.util.find_spec("memory_book._native") is not None else None)
_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_RUNS = re.compile(rf"[{_CJK}]+|[^\W_{_CJK}]+(?:[_./:-][^\W_{_CJK}]+)*", re.UNICODE)
_ASCII = re.compile(r"[a-z0-9]+")
_ONLY_CJK = re.compile(rf"^[{_CJK}]+$")
_CAMEL = re.compile(r"([a-z])([A-Z])")
_SEPARATOR = re.compile(r"[_./:-]+")
_IDENTIFIER = re.compile(r"[A-Za-z0-9_]+")
_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_ZH_QUESTION = re.compile(r"为什么|请告诉我|请问|是什么|什么|怎么样|怎么|如何|多少|哪些|哪个|是否")
_STOP = frozenset("a an the is are was were be been to of in on at for from and or it this that these those with as by what which who when where why how do does did can could would should please tell me we our you your i my about now current latest final s t re ve ll d m".split())
_ZH_STOP = frozenset("什么 怎么 如何 为什么 哪个 哪些 是否 现在 当前 最后 最终 我们 这个 那个 一个 一下 请问 告诉 多少 了吗 的是 是什 么的 如何 何时 怎样".split())


def reference_terms(value, *, query=False):
    if not value.isascii():
        value = unicodedata.normalize("NFKC", value)
    value = _CAMEL.sub(r"\1 \2", value).casefold()
    if not value.isascii():
        value = unicodedata.normalize("NFKD", value)
        removed = {ord(char): None for char in set(value)
                   if unicodedata.category(char) == "Mn"}
        if removed:
            value = value.translate(removed)
    if value.isascii():
        tokens = _ASCII.findall(value)
        return [token for token in tokens if token not in _STOP] if query else tokens
    if query:
        value = _ZH_QUESTION.sub(" ", value)
    tokens = []
    for match in _RUNS.finditer(value):
        token = match.group()
        if _ONLY_CJK.fullmatch(token):
            parts = [token] if len(token) == 1 else [token[i:i + 2] for i in range(len(token) - 1)]
            tokens.extend(part for part in parts if not query or part not in _ZH_STOP)
        else:
            tokens.extend(part for part in _SEPARATOR.split(token)
                          if part and (not query or part not in _STOP))
    return tokens


def reference_identifier_terms(value, *, query=False):
    normalized = value if value.isascii() else unicodedata.normalize("NFKC", value)
    if not _BOUNDARY.search(normalized):
        return reference_terms(normalized, query=query)
    if query:
        aliases = []

        def canonical(match):
            token = match.group()
            parts = [part.casefold() for part in _BOUNDARY.split(token) if part]
            if len(parts) < 2:
                return token
            joined = "".join(parts)
            if joined not in _STOP:
                aliases.append(joined)
            return " ".join(parts)

        return reference_terms(_IDENTIFIER.sub(canonical, normalized), query=True) + aliases
    result = reference_terms(normalized)
    for match in _IDENTIFIER.finditer(normalized):
        token = match.group()
        parts = [part.casefold() for part in _BOUNDARY.split(token) if part]
        if len(parts) < 2:
            continue
        existing = set(reference_terms(token))
        for alias in [*parts, "".join(parts)]:
            if alias not in existing:
                result.append(alias)
                existing.add(alias)
    return result


def outcome(operation):
    try:
        return "value", operation()
    except Exception as error:
        return "error", type(error), error.args


def recorded_calls(calls):
    # A fresh nested canonical callback is created on each Python invocation.
    # Its identity differs even when both invocations use the reference path.
    return [(name, tuple(("callable", arg.__name__) if callable(arg) else arg for arg in args), kwargs)
            for name, args, kwargs in calls]


def reference_aliases(normalized, query, stop):
    additions = []

    def canonical(match):
        value = match.group()
        parts = [part.casefold() for part in _BOUNDARY.split(value) if part]
        if len(parts) < 2:
            return value
        joined = "".join(parts)
        if query:
            if joined not in stop:
                additions.append(joined)
            return " ".join(parts)
        existing = set(reference_terms(value))
        for alias in [*parts, joined]:
            if alias not in existing:
                additions.append(alias)
                existing.add(alias)
        return value

    rewritten = _IDENTIFIER.sub(canonical, normalized)
    return rewritten, additions


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeIdentifierEquivalenceTests(unittest.TestCase):
    def compare_reference(self, value):
        for query in (False, True):
            expected = reference_identifier_terms(value, query=query)
            with patch.object(lexical, "_NATIVE", NATIVE):
                actual = lexical.identifier_terms(value, query=query)
            self.assertEqual(actual, expected, (repr(value), query))

    def test_order_frequency_and_aliases_match_the_released_implementation(self):
        cases = (
            "", "_", "__", "___a___", "_a_B_", "a_A_a_A", "aA aA a_a a_a",
            "HTTPParser HttpParser httpParser http_parser HTTP_PARSER",
            "HTTP2Parser A1b a1B 1Aa XML2HTTPParser parseHTTPResponse XMLHttpRequest",
            "network.HTTPParser::parseResponse /http_parser-path/to_file.py",
            "a_b is_It forThe s_t ABc ABc A_B_A_B AAaaBAAab",
            "_a____b_ ___HTTP__Parser___ cacheCache cache_cache cacheCACHE",
            "HTTP parser ordinary words 缓存有效期 http Parser _ _a_ a_",
            "A\x00B_a\r\nX\tY_Z,TypeName;CurrentCache() <HTTPParser>",
            "a" * 4096 + "B" * 4096 + "c_" * 1000,
        )
        for value in cases:
            with self.subTest(value=repr(value[:120])):
                self.compare_reference(value)

    def test_exhaustive_short_ascii_boundary_classes(self):
        # Lowercase, uppercase, digit, underscore and three delimiters exercise
        # both lookarounds, empty split parts, and adjacent qualified runs.
        alphabet = "aA0_. \x00"
        with patch.object(lexical, "_NATIVE", NATIVE):
            for size in range(6):
                for parts in itertools.product(alphabet, repeat=size):
                    value = "".join(parts)
                    for query in (False, True):
                        self.assertEqual(lexical.identifier_terms(value, query=query),
                                         reference_identifier_terms(value, query=query),
                                         (repr(value), query))

    def test_unicode_normalization_surrogates_and_codepoint_delimiters(self):
        cases = [
            "当前 ＨＴＴＰＰａｒｓｅｒ 是什么 Ａ＿Ｂ ①A ⅨParser ﻻ_http",
            "StraßeParser éHTTPParser İConfig ﬃParser KValue ǅName",
            "a\u0315\u0300\u0327B a\u0345B a\u302eB a\ufe0fB a\U0001d165B",
            "A中🙂B fooBar缓存_BAZ_qux 👩🏽‍💻TypeName",
            "\ud800HTTPParser\udfff foo\ud800Bar a_\udfff_b",
            "\U00020000HTTPParser\U00020001 \U0010ffff_aB_\x00",
            "\u33ff\u3400\u4dbf\u4dc0\u4dff\u4e00\u9fff\ua000\uf8ff\uf900\ufaff\ufb00_Aa",
        ]
        for codepoint in list(range(128)) + [0x0301, 0x0345, 0x200d, 0x2028, 0x302e,
                                            0x3400, 0x9fff, 0xd800, 0xdfff, 0xfe0f,
                                            0xff21, 0xff3f, 0x10400, 0x1d400, 0x10ffff]:
            char = chr(codepoint)
            cases.extend((f"A{char}aB_x", f"a_{char}B", f"xA{char}bY"))
        for value in cases:
            self.compare_reference(value)

    def test_seeded_mixed_unicode_strings_keep_complete_lists(self):
        rng = random.Random(108003)
        alphabet = ("AaZz019_./:- \t\r\n\x00缓存当前是什么éßİ\u0301\u302e١²Ⅸﻻ"
                    "ＡＢａｂ＿ﬃKǅ🙂\U00020000\ud800\udfff")
        for _ in range(240):
            value = "".join(rng.choices(alphabet, k=rng.randrange(1, 240)))
            self.compare_reference(value)
        for _ in range(160):
            value = "http_" + "".join(chr(rng.randrange(0x110000)) + "Aa_" for _ in range(12))
            self.compare_reference(value)

    def test_index_and_query_helpers_preserve_join_dedup_and_the_sixty_four_term_cap(self):
        value = " ".join(f"HTTPParser{i}_Timeout café_{i}缓存" for i in range(100))
        with patch.object(lexical, "_NATIVE", NATIVE):
            self.assertEqual(lexical.index_text(value), " ".join(reference_identifier_terms(value)))
            self.assertEqual(lexical.query_terms(value),
                             list(dict.fromkeys(reference_identifier_terms(value, query=True)))[:64])


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeIdentifierHelperTests(unittest.TestCase):
    def test_helper_preserves_rewrite_and_alias_lists_before_whole_text_tokenization(self):
        cases = ["", "___", "_A___b_", "HTTPParser http_parser parseHTTPResponse",
                 "a_A_a_A is_It a_a a_a", "aA0B HTTP2Parser XML2HTTPParser",
                 "CaféHTTPParser\ud800aB_é汉字_XYz🙂A\x00bC",
                 "XＨＴＴＰＹ_１２３", "a" * 4096 + "BAAab" + "_a" * 2000]
        for size in range(5):
            cases.extend("".join(chars) for chars in itertools.product("aA0_./", repeat=size))
        for value in cases:
            for query in (False, True):
                self.assertEqual(NATIVE.identifier_aliases(value, query, _STOP),
                                 reference_aliases(value, query, _STOP), (repr(value), query))

    def test_query_stop_membership_keeps_order_and_original_exception(self):
        class Stop:
            def __init__(self):
                self.calls = []

            def __contains__(self, value):
                self.calls.append(value)
                return value == "ab"

        traces = []
        for method in (reference_aliases, NATIVE.identifier_aliases):
            stop = Stop()
            traces.append((method("a_b is_It a_b HTTPParser", True, stop), stop.calls))
            self.assertEqual(method("HTTPParser a_b", False, object()),
                             reference_aliases("HTTPParser a_b", False, object()))
        self.assertEqual(traces[0], traces[1])
        self.assertEqual(traces[0][1], ["ab", "isit", "ab", "httpparser"])
        error = RuntimeError("custom stop membership")

        class Broken:
            def __contains__(self, value):
                raise error

        with self.assertRaises(RuntimeError) as raised:
            NATIVE.identifier_aliases("HTTPParser", True, Broken())
        self.assertIs(raised.exception, error)

    def test_native_helper_rejects_nonexact_text_and_boolean_contracts(self):
        class Text(str):
            pass

        for value in (None, b"HTTPParser", Text("HTTPParser"), 1, []):
            with self.subTest(value=repr(value)), self.assertRaises(TypeError):
                NATIVE.identifier_aliases(value, False, _STOP)
        for query in (0, 1, None, [], object()):
            with self.subTest(query=repr(query)), self.assertRaises(TypeError):
                NATIVE.identifier_aliases("HTTPParser", query, _STOP)

    def test_ordinary_public_inputs_really_dispatch_to_the_new_helper(self):
        for query in (False, True):
            observed = Mock(wraps=NATIVE)
            with patch.object(lexical, "_NATIVE", observed):
                self.assertEqual(lexical.identifier_terms("ＨＴＴＰＰａｒｓｅｒ a_b", query=query),
                                 reference_identifier_terms("ＨＴＴＰＰａｒｓｅｒ a_b", query=query))
            observed.identifier_aliases.assert_called_once_with("HTTPParser a_b", query, lexical.STOP)


@unittest.skipUnless(NATIVE is not None, "Native extension is not installed")
class NativeIdentifierCompatibilityTests(unittest.TestCase):
    def compare_paths(self, operation):
        values = []
        for backend in (None, NATIVE):
            with patch.object(lexical, "_NATIVE", backend):
                values.append(outcome(operation))
        self.assertEqual(values[0], values[1])
        return values[0]

    def test_custom_identifier_patterns_and_terms_are_preserved(self):
        replacements = (
            ("IDENTIFIER_WORD_BOUNDARY", re.compile(r"_+")),
            ("IDENTIFIER_WORD_BOUNDARY", re.compile(r"(?!)")),
            ("IDENTIFIER_RUN", re.compile(r"[a-z]+")),
            ("IDENTIFIER_RUN", re.compile(r"[A-Z]+", re.IGNORECASE)),
            ("STOP", frozenset({"httpparser", "http", "parser", "ab"})),
            ("terms", lambda value, *, query=False: ["custom", str(query), value]),
        )
        for name, replacement in replacements:
            with self.subTest(name=name), patch.object(lexical, name, replacement):
                for query in (False, True):
                    self.compare_paths(lambda: lexical.identifier_terms("HTTPParser a_b cacheCache", query=query))

    def test_custom_patterns_preserve_observable_calls_and_exceptions(self):
        for name in ("IDENTIFIER_WORD_BOUNDARY", "IDENTIFIER_RUN"):
            original = getattr(lexical, name)
            traces = []
            for backend in (None, NATIVE):
                observed = Mock(wraps=original)
                with patch.object(lexical, "_NATIVE", backend), patch.object(lexical, name, observed):
                    values = [lexical.identifier_terms("HTTPParser a_b a_b", query=query)
                              for query in (False, True)]
                traces.append((values, recorded_calls(observed.mock_calls)))
            self.assertEqual(traces[0], traces[1])
        for name, method in (("IDENTIFIER_WORD_BOUNDARY", "search"),
                             ("IDENTIFIER_WORD_BOUNDARY", "split"),
                             ("IDENTIFIER_RUN", "finditer"),
                             ("IDENTIFIER_RUN", "sub")):
            error = RuntimeError(f"custom {name}.{method}")
            observed = Mock(wraps=getattr(lexical, name))
            getattr(observed, method).side_effect = error
            with patch.object(lexical, name, observed):
                for query in (False, True):
                    self.compare_paths(lambda: lexical.identifier_terms("HTTPParser a_b", query=query))

    def test_patched_terms_preserve_call_order_and_keyword_arguments(self):
        ordinary = lexical.terms
        for query in (False, True):
            traces = []
            for backend in (None, NATIVE):
                observed = Mock(wraps=ordinary)
                with patch.object(lexical, "_NATIVE", backend), patch.object(lexical, "terms", observed):
                    value = lexical.identifier_terms("HTTPParser a_a aB_aB", query=query)
                traces.append((value, observed.mock_calls))
            self.assertEqual(traces[0], traces[1])
        error = RuntimeError("custom terms")
        with patch.object(lexical, "terms", side_effect=error):
            self.assertEqual(self.compare_paths(lambda: lexical.identifier_terms("HTTPParser"))[0], "error")

    def test_nonordinary_arguments_preserve_python_values_and_errors(self):
        class Text(str):
            def isascii(self):
                raise RuntimeError("custom isascii")

        class PlainText(str):
            pass

        class Query:
            def __bool__(self):
                raise RuntimeError("custom query truth")

        for value in (None, b"HTTPParser", 14, [], Text("HTTPParser"), PlainText("HTTPParser")):
            for query in (False, True):
                with self.subTest(value=repr(value), query=query):
                    self.compare_paths(lambda: lexical.identifier_terms(value, query=query))
        for query in (None, 0, 1, [], [1], "", "yes", Query()):
            self.compare_paths(lambda: lexical.identifier_terms("HTTPParser a_b", query=query))

    def test_patched_normalization_keeps_call_order_and_original_exceptions(self):
        ordinary = unicodedata.normalize
        for query in (False, True):
            traces = []
            for backend in (None, NATIVE):
                observed = Mock(wraps=ordinary)
                with patch.object(lexical, "_NATIVE", backend), patch.object(unicodedata, "normalize", observed):
                    value = lexical.identifier_terms("éＨＴＴＰＰａｒｓｅｒ_aB", query=query)
                traces.append((value, observed.mock_calls))
            self.assertEqual(traces[0], traces[1])
        with patch.object(unicodedata, "normalize", side_effect=RuntimeError("normalize failure")):
            self.assertEqual(self.compare_paths(lambda: lexical.identifier_terms("éHTTPParser"))[0], "error")

    def test_mutation_during_whole_text_tokenization_is_checked_before_alias_dispatch(self):
        ordinary_normalize = unicodedata.normalize
        ordinary_terms = lexical.terms
        traces = []
        for backend in (None, NATIVE):
            calls = []
            normalizations = 0

            def replacement(value, *, query=False):
                calls.append((value, query))
                return ["custom", value]

            def normalize(form, value):
                nonlocal normalizations
                normalizations += 1
                # First NFKC belongs to identifier_terms. The second belongs
                # to the whole-string terms call that precedes index aliases.
                if normalizations == 2:
                    lexical.terms = replacement
                return ordinary_normalize(form, value)

            with patch.object(lexical, "_NATIVE", backend), \
                    patch.object(lexical, "terms", ordinary_terms), \
                    patch.object(unicodedata, "normalize", normalize):
                value = lexical.identifier_terms("éHTTPParser a_b")
            traces.append((value, calls, normalizations))
        self.assertEqual(traces[0], traces[1])
        self.assertEqual(traces[0][1], [("HTTPParser", False), ("a_b", False)])

    def test_patterns_replaced_before_import_are_not_treated_as_default(self):
        script = r'''
import json, re, sys
ordinary_compile = re.compile
boundary = r"_+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
def compile(pattern, flags=0):
    if sys.argv[1] == "boundary" and pattern == boundary:
        return ordinary_compile(r"_+", flags)
    if sys.argv[1] == "runs" and pattern == r"[A-Za-z0-9_]+":
        return ordinary_compile(r"[a-z]+", flags)
    return ordinary_compile(pattern, flags)
re.compile = compile
from memory_book import text
values = [text.identifier_terms("HTTPParser a_b", query=q) for q in (False, True)]
text._NATIVE = None
reference = [text.identifier_terms("HTTPParser a_b", query=q) for q in (False, True)]
print(json.dumps([values, reference]))
'''
        environment = dict(os.environ, MEMORY_BOOK_TEXT_BACKEND="native", PYTHONDONTWRITEBYTECODE="1")
        for dependency in ("boundary", "runs"):
            with self.subTest(dependency=dependency):
                process = subprocess.run([sys.executable, "-c", script, dependency], cwd=ROOT,
                                         env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(process.returncode, 0, process.stderr)
                actual, expected = json.loads(process.stdout)
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
