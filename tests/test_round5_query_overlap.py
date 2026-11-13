"""Invented exact-overlap fixtures; no benchmark corpus or timing probes."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import ModuleType
import random
import unittest
from unittest.mock import patch

from memory_book import text as lexical
from memory_book import token_budget as budget


class AcceptCounter:
    def __init__(self):
        self.calls = []

    def count(self, text):
        self.calls.append(text)
        return 0

    def count_after(self, prefix):
        raise AssertionError("The first selected invented unit always fits")


def page(identity, query, content="alpha. beta."):
    return {"id": identity, "project_id": "invented", "session_id": identity,
            "created_at": "2026-01-01", "content": content, "excerpt_terms": query,
            "token_source_units": [(0, 6), (7, len(content))]}


def assemble(pages, resolver=None):
    counter = AcceptCounter()
    result = budget.assemble_with_count([], pages, ["unused"], budget_chars=10000,
                                       budget_tokens=10000, counter=counter, source_units_for=resolver)
    return result, counter.calls


class ConsumerBehaviorTests(unittest.TestCase):
    """Run first on exact D, then unchanged on F to retain baseline behavior."""

    def test_same_rendered_text_uses_each_pages_effective_query_set(self):
        pages = [page("first", ["alpha"]), page("second", ["beta"]), page("third", [])]
        (kept, count), calls = assemble(pages)
        self.assertEqual([entry[3] for entry in kept], [[(0, 6)], [(7, 12)], [(0, 6)]])
        self.assertEqual([entry[2] for entry in kept], ["alpha.…", "…beta.", "alpha.…"])
        self.assertEqual(count, 0)
        self.assertEqual(len(calls), 3)

    def test_custom_terms_full_cache_is_not_recomputed_for_another_query(self):
        calls = []

        def custom(text, *, query=False):
            calls.append((text, query))
            return ["alpha"]

        with patch.object(budget, "terms", custom):
            (kept, _), _ = assemble([page("first", ["alpha"]), page("second", ["beta"])])
        self.assertEqual([entry[3] for entry in kept], [[(0, 6)], [(0, 6)]])
        self.assertEqual(calls, [("alpha.…", True), ("…beta.", True)])

    def test_later_callable_replacement_does_not_recompute_cached_plain_text(self):
        def fail(text, *, query=False):
            raise AssertionError("The original text-only cache already contains both units")

        def resolver(row):
            if row["id"] == "second":
                budget.terms = fail
            return row["token_source_units"]

        with patch.object(budget, "terms", budget.terms):
            (kept, _), _ = assemble([page("first", ["alpha"]), page("second", ["beta"])], resolver)
        self.assertEqual([entry[3] for entry in kept], [[(0, 6)], [(7, 12)]])

    def test_custom_then_ordinary_callable_keeps_original_cached_features(self):
        original, calls = budget.terms, []

        def custom(text, *, query=False):
            calls.append(text)
            return ["alpha"]

        def resolver(row):
            if row["id"] == "second":
                budget.terms = original
            return row["token_source_units"]

        with patch.object(budget, "terms", custom):
            (kept, _), _ = assemble([page("first", ["alpha"]), page("second", ["beta"])], resolver)
        self.assertEqual([entry[3] for entry in kept], [[(0, 6)], [(0, 6)]])
        self.assertEqual(calls, ["alpha.…", "…beta."])

    def test_changed_ordinary_globals_affect_new_text_but_not_existing_cache(self):
        def resolver(row):
            if row["id"] == "second":
                lexical.STOP = frozenset({"alpha", "beta"})
            return row["token_source_units"]

        with patch.object(lexical, "STOP", lexical.STOP):
            (kept, _), _ = assemble([page("first", ["alpha"]), page("second", ["beta"]),
                                    page("third", ["beta"], "alpha! beta?")], resolver)
        self.assertEqual([entry[3] for entry in kept], [[(0, 6)], [(7, 12)], [(0, 6)]])

    def test_native_cache_later_custom_query_preserves_comparison_failure(self):
        events = []

        class ComparisonFailure(Exception):
            pass

        class Custom(str):
            __hash__ = str.__hash__

            def __eq__(self, other):
                events.append("comparison")
                raise ComparisonFailure("invented query comparison")

        def resolver(row):
            events.append(row["id"])
            return row["token_source_units"]

        with self.assertRaises(ComparisonFailure):
            assemble([page("first", ["alpha"]), page("second", [Custom("beta")])], resolver)
        self.assertEqual(events, ["first", "second", "comparison"])


class ExactOverlapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Rejected F remains an exact historical fixture, outside the runtime.
        path = Path(__file__).parent / "fixtures" / "round5_rejected_query_overlap.txt"
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != "4e2d7cd383dc546a591dee38e4744ffc4ac4dd1b381574e7d307a29139e47262":
            raise AssertionError("Historical rejected F fixture changed")
        cls.overlap = ModuleType("memory_book._round5_rejected_query_overlap_fixture")
        cls.overlap.__package__ = "memory_book"
        cls.overlap.__file__ = str(path)
        exec(compile(raw, str(path), "exec"), cls.overlap.__dict__)

    def assert_overlap(self, text, wanted):
        expected = len(wanted.intersection(set(lexical.terms(text, query=True))))
        self.assertEqual(self.overlap.query_overlap(wanted, text, lexical.terms), expected,
                         (repr(text), wanted))
        entry = self.overlap.overlap_entry(text, lexical.terms)
        self.assertEqual(self.overlap.cached_overlap(wanted, entry), expected)
        return entry

    def test_directed_normalization_boundaries_stopwords_and_identifiers(self):
        texts = ["", "a an the current now alpha ALPHA alpha", "HTTPServer getHTTPValue foo_Bar/a.b:c-d",
                 "x_1 123 １２３ ﬁ ﬃ K Å ﬀ Straße ẞ", "café cafe\u0301 A\u030a\u0327 İ ı Σ ς σ",
                 "为什么缓存有效期是什么？请告诉我缓存如何失效。", "缓存期 缓 存 缓存 缓存缓存",
                 "的是什么 的是 是什 么的 如何 何时 怎样", "漢字\uf900\ufa10 㐀㐁 中文/中文",
                 "abc缓存def café缓存 XMLParser-缓存/path", "\ud800alpha\udc00缓存\ud800\udc00",
                 "a\u034f\u200d\u200c b\ufe0f\U0001f469\U0001f3fd\u200d\U0001f4bb",
                 "\x00\x1f\t\r\n123!!!_./:- 'can\'t' we're",
                 "अक्षर العربية עברית Ελληνικά русский ไทย 한국어"]
        extras = {"", "a", "the", "current", "为什么", "如何", "缓存期", "缓", "存", "缓存", "abc", "http", "ss"}
        for text in texts:
            tokens = set(lexical.terms(text, query=True))
            for wanted in (set(), tokens, tokens | extras, extras, {"not_present"}):
                with self.subTest(text=repr(text), wanted=wanted):
                    self.assert_overlap(text, wanted)

    def test_cjk_singletons_only_match_single_character_runs(self):
        for text, wanted, count in (("缓存", {"缓", "存"}, 0), ("缓 存", {"缓", "存"}, 2),
                                    ("缓存缓存", {"缓存", "存缓"}, 2), ("缓存期", {"缓存期"}, 0),
                                    ("为什么", {"为什", "什么", "为"}, 0)):
            self.assertEqual(self.overlap.query_overlap(wanted, text, lexical.terms), count)

    def test_seeded_invented_unicode_mixtures_match_the_unchanged_reference(self):
        rng = random.Random(51017)
        alphabet = ("abAZ09_./:- \n\r\t'" + "缓存有效期为什么如何请告诉我" +
                    "éÅİßΣςﬁÅ" + "\u0301\u0327\u034f\u093e\uf900\ufa10\ud800\udc00" +
                    "👩🏽‍💻" + "العربية한국어")
        for index in range(384):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 120)))
            tokens = lexical.terms(text, query=True)
            wanted = set(tokens[::2]) | {"alpha", "缓存", "存", "的", "a", "the", ""}
            with self.subTest(case=index):
                self.assert_overlap(text, wanted)

    def test_cached_representation_answers_different_queries_and_mutable_sets(self):
        entry = self.overlap.overlap_entry("alpha beta 缓存缓存 缓。", lexical.terms)
        wanted = {"alpha", "缓"}
        self.assertEqual(self.overlap.cached_overlap(wanted, entry), 2)
        wanted.clear()
        wanted.update({"beta", "缓存", "存"})
        self.assertEqual(self.overlap.cached_overlap(wanted, entry), 2)
        self.assertEqual(self.overlap.cached_overlap({"alpha", "缓"}, entry), 2)

    def test_cached_representation_preserves_initial_globals_when_later_materialized(self):
        class Word(str):
            pass
        entry = self.overlap.overlap_entry("alpha beta 缓存。", lexical.terms)
        with patch.object(lexical, "STOP", frozenset({"alpha", "beta"})), \
             patch.object(lexical, "ZH_STOP", frozenset({"缓存"})):
            self.assertEqual(self.overlap.cached_overlap({Word("alpha"), Word("缓存")}, entry), 2)
            self.assert_overlap("alpha beta 缓存。", {"alpha", "beta", "缓存"})

    def test_custom_text_and_callable_keep_original_operations(self):
        events = []

        class Text(str):
            def isascii(self):
                events.append("isascii")
                raise LookupError("invented text hook")

        with self.assertRaises(LookupError):
            self.overlap.query_overlap({"alpha"}, Text("alpha"), lexical.terms)
        self.assertEqual(events, ["isascii"])

        def custom(text, *, query=False):
            events.append((text, query))
            return ["custom", "custom"]

        entry = self.overlap.overlap_entry("alpha", custom)
        self.assertEqual(type(entry), set)
        self.assertEqual(self.overlap.cached_overlap({"custom"}, entry), 1)
        self.assertEqual(self.overlap.query_overlap({"custom"}, "alpha", custom), 1)
        self.assertEqual(events[1:], [("alpha", True), ("alpha", True)])

    def test_replaced_lexical_globals_use_the_actual_ordinary_function(self):
        replacements = {"STOP": frozenset({"alpha"}), "ZH_STOP": frozenset({"缓存"}),
                        "ASCII_RUNS": lexical.re.compile(r"[a-z]"), "RUNS": lexical.re.compile(r"[a-z]+"),
                        "CJK_RUN": lexical.re.compile(r"^NEVER$"),
                        "CAMEL_BOUNDARY": lexical.re.compile(r"(x)(y)"),
                        "IDENTIFIER_SEPARATOR": lexical.re.compile(r"-"),
                        "ZH_QUESTION": lexical.re.compile("缓存"),
                        "_strip_nonspacing_marks": lambda value: "changed"}
        for name, replacement in replacements.items():
            with self.subTest(global_name=name), patch.object(lexical, name, replacement):
                self.assert_overlap("alphaBeta缓存 é x_y", {"alpha", "beta", "缓存", "changed", "a", "x_y"})


if __name__ == "__main__":
    unittest.main()
