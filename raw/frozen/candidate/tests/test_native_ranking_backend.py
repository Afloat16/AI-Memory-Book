"""Native store batches preserve scores, order, aliases, SQL and fallbacks."""
from __future__ import annotations

import copy
from decimal import Decimal
import importlib
import importlib.util
import math
import random
import sqlite3
import unittest
from unittest.mock import Mock, patch

from memory_book import MemoryBook, store


NATIVE = (importlib.import_module("memory_book._native")
          if importlib.util.find_spec("memory_book._native") is not None else None)
AVAILABLE = NATIVE is not None and hasattr(NATIVE, "rank_candidates")


def reference_rank(items, query, directory_tokens, book, base, fusion):
    """The pre-native loop, including arithmetic grouping and stable keys."""
    overlaps, candidates = {}, []
    if fusion is not None:
        exact, exact_scale, stem, stem_scale, exact_ranks, stem_ranks = fusion
    for item in items:
        title_overlap = 0.0
        if book:
            directory = item["chapter_title"] + " " + item["session_title"]
            if directory not in overlaps:
                overlaps[directory] = len(query & directory_tokens(directory)) / len(query)
            title_overlap = overlaps[directory]
        if base is not None:
            relevance = base[item["id"]]
        elif fusion is not None:
            relevance = (2 * exact.get(item["id"], 0.0) / exact_scale
                         + stem.get(item["id"], 0.0) / stem_scale)
        else:
            relevance = -item["rank"]
        item["score"] = relevance * (1 + 0.15 * title_overlap if book else 1)
        candidates.append(item)
    if fusion is not None:
        candidates.sort(key=lambda item: (-item["score"], exact_ranks.get(item["id"], 97),
            stem_ranks.get(item["id"], 97), item["id"]))
    else:
        candidates.sort(key=lambda item: (-item["score"], item["id"]))
    return candidates


def reference_novelty(pool, deferred, matched, query_count, limit):
    chosen, pending = [pool[0]], pool[1:]
    covered = set(matched[pool[0]["rid"]])
    while (pending or deferred) and len(chosen) < limit:
        if not pending:
            pending, deferred = deferred, []
        best = max(range(len(pending)), key=lambda i: pending[i]["score"] *
                   (1 + len(matched[pending[i]["rid"]] - covered) / query_count))
        item = pending.pop(best)
        chosen.append(item)
        covered.update(matched[item["rid"]])
    return chosen + pending + deferred


def allocation_page(identity, content):
    return {"id": identity, "project_id": "project 中", "session_id": "session🙂",
            "created_at": "2026-03-01T00:00:00Z", "content": content}


@unittest.skipUnless(AVAILABLE, "Native ranking extension is not installed")
class NativeRankingKernelTests(unittest.TestCase):
    def test_batch_scores_match_float_bits_and_route_ties(self):
        rng = random.Random(90410)
        for size in (0, 1, 5, 32, 96, 192):
            items = [{"id": f"{i:03d}中", "rank": -rng.choice((0.0, 5e-324, .125, 7.0, rng.random())),
                      "chapter_title": rng.choice(("cache", "pressure", "café", "中")),
                      "session_title": rng.choice(("cache", "cache pressure", "🙂", "\ud800"))}
                     for i in range(size)]
            rng.shuffle(items)
            exact = {item["id"]: rng.random() for item in items[::2]}
            stem = {item["id"]: rng.random() for item in items[1:]}
            fusion = (exact, max(exact.values(), default=1.0) or 1.0,
                      stem, max(stem.values(), default=1.0) or 1.0,
                      {identity: index + 1 for index, identity in enumerate(exact)},
                      {identity: index + 1 for index, identity in enumerate(stem)})
            for book in (False, True):
                for route in (None, fusion):
                    for base in (None, {item["id"]: rng.choice((0.0, -0.0, .75)) for item in items}):
                        calls = [[], []]
                        def tokenize(which):
                            def call(value):
                                calls[which].append(value)
                                return frozenset(value.split())
                            return call
                        expected = reference_rank(copy.deepcopy(items), {"cache", "pressure", "中"},
                                                  tokenize(0), book, base, route)
                        original = copy.deepcopy(items)
                        actual = NATIVE.rank_candidates(original, {"cache", "pressure", "中"},
                                                        tokenize(1), book, base, route)
                        self.assertIsNot(actual, NotImplemented)
                        self.assertEqual(actual, expected)
                        self.assertEqual([row["score"].hex() for row in actual],
                                         [row["score"].hex() for row in expected])
                        self.assertEqual(calls[0], calls[1])
                        self.assertEqual({id(row) for row in actual}, {id(row) for row in original})

    def test_same_id_equal_key_keeps_input_order_and_special_float_rounding(self):
        items = [{"id": "same", "rank": -0.0, "tag": index} for index in range(5)]
        actual = NATIVE.rank_candidates(items, {"x"}, None, False, None, None)
        self.assertEqual([row["tag"] for row in actual], list(range(5)))
        for rank in (-1.7976931348623157e308, -5e-324, -0.0, 0.0, 1.0):
            item = {"id": "x", "rank": rank, "chapter_title": "a", "session_title": "b"}
            expected = reference_rank([dict(item)], {"a", "b", "c"},
                                      lambda text: set(text.split()), True, None, None)
            actual = NATIVE.rank_candidates([dict(item)], {"a", "b", "c"},
                                            lambda text: set(text.split()), True, None, None)
            self.assertEqual(actual[0]["score"].hex(), expected[0]["score"].hex())

    def test_callback_exception_keeps_earlier_score_writes_and_call_order(self):
        items = [{"id": str(i), "rank": -.5, "chapter_title": str(i), "session_title": "cache"}
                 for i in range(3)]
        results, calls = [], [[], []]
        for index, implementation in enumerate((reference_rank, NATIVE.rank_candidates)):
            rows = copy.deepcopy(items)
            def callback(text):
                calls[index].append(text)
                if text.startswith("1 "):
                    raise LookupError("directory callback")
                return frozenset(("cache",))
            with self.assertRaisesRegex(LookupError, "directory callback"):
                implementation(rows, {"cache"}, callback, True, None, None)
            results.append(rows)
        self.assertEqual(results[0], results[1])
        self.assertEqual(calls[0], calls[1])

    def test_callback_title_subclasses_keep_addition_methods_and_lookup_order(self):
        outcomes = []
        for implementation in (reference_rank, NATIVE.rank_candidates):
            rows = [{"id": "a", "rank": -.5, "chapter_title": "first", "session_title": "old"},
                    {"id": "b", "rank": -.5, "chapter_title": "second", "session_title": "old"}]
            calls = []
            class Prefix(str):
                def __add__(self, other):
                    calls.append(("add", str(self), other))
                    rows[1]["session_title"] = "cache"
                    return str(self) + other
            def callback(text):
                calls.append(("tokens", text))
                rows[1]["chapter_title"] = Prefix("changed")
                return frozenset(text.split())
            result = implementation(rows, {"cache"}, callback, True, None, None)
            outcomes.append((result, calls))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertIn(("tokens", "changed cache"), outcomes[0][1])

    def test_callback_numeric_replacements_preserve_python_operator_errors(self):
        for mode in ("base", "rank", "exact", "stem"):
            observed = []
            for implementation in (reference_rank, NATIVE.rank_candidates):
                rows = [{"id": "a", "rank": -1.0, "chapter_title": "cache", "session_title": "x"}]
                base = {"a": 1.0} if mode == "base" else None
                fusion = ({"a": .5}, 1.0, {"a": .25}, 1.0, {"a": 1}, {"a": 1}) if mode in ("exact", "stem") else None
                def callback(text):
                    if mode == "base":
                        base["a"] = Decimal("2")
                    elif mode == "rank":
                        rows[0]["rank"] = Decimal("-2")
                    else:
                        fusion[0 if mode == "exact" else 2]["a"] = Decimal("2")
                    return {"cache"}
                try:
                    implementation(rows, {"cache"}, callback, True, base, fusion)
                except Exception as error:
                    observed.append((type(error), str(error), "score" in rows[0]))
                else:
                    self.fail("Decimal arithmetic should retain Python's TypeError")
            self.assertEqual(observed[0], observed[1], mode)

    def test_numeric_callback_changes_identity_before_second_fusion_lookup(self):
        results = []
        for implementation in (reference_rank, NATIVE.rank_candidates):
            rows = [{"id": "a", "rank": -1.0, "chapter_title": "cache", "session_title": "x"}]
            fusion = ({"a": .5, "b": .8}, 1.0, {"a": .25, "b": .75}, 1.0,
                      {"a": 1, "b": 2}, {"a": 1, "b": 2})
            class Shifted:
                def __rmul__(self, factor):
                    rows[0]["id"] = "b"
                    return factor * .5
            def callback(text):
                fusion[0]["a"] = Shifted()
                return {"cache"}
            results.append(implementation(rows, {"cache"}, callback, True, None, fusion))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1][0]["id"], "b")
        self.assertEqual(results[1][0]["score"].hex(), (1.75 * 1.15).hex())

    def test_unsupported_rank_inputs_decline_without_callbacks_or_partial_scores(self):
        ordinary = [{"id": "a", "rank": -1.0, "chapter_title": "cache", "session_title": "one"},
                    {"id": "b", "rank": -2.0, "chapter_title": "cache", "session_title": "two"}]
        class CustomDict(dict):
            pass
        for change in (lambda rows: rows[1].update(rank=math.nan),
                       lambda rows: rows[1].update(rank=math.inf),
                       lambda rows: rows[1].update(rank=1),
                       lambda rows: rows[1].pop("id"),
                       lambda rows: rows.__setitem__(1, CustomDict(rows[1]))):
            rows = copy.deepcopy(ordinary)
            change(rows)
            callback = Mock(side_effect=AssertionError("unsupported callback ran"))
            self.assertIs(NATIVE.rank_candidates(rows, {"cache"}, callback, True, None, None), NotImplemented)
            callback.assert_not_called()
            self.assertTrue(all("score" not in row for row in rows))

    def test_novelty_matches_ties_negative_scores_and_deferred_mutation(self):
        rng = random.Random(9482)
        for size in (1, 2, 8, 32, 192):
            items = [{"rid": i, "score": rng.choice((0.0, -0.0, 1.0, 1.5, -1.0, rng.random()))}
                     for i in range(size)]
            matched = {i: {token for token in ("a", "b", "中", "🙂") if rng.randrange(2)}
                       for i in range(size)}
            for split in (1, size // 2 or 1, size):
                for limit in (0, 1, 5, 50):
                    expected_deferred = items[split:]
                    actual_deferred = items[split:]
                    expected = reference_novelty(items[:split], expected_deferred, matched, 4, limit)
                    actual = NATIVE.select_novelty(items[:split], actual_deferred, matched, 4, limit)
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual_deferred, expected_deferred)
                    self.assertTrue(all(a is b for a, b in zip(actual, expected)))

    def test_novelty_unsupported_tail_is_checked_before_mutating_deferred(self):
        pool = [{"rid": 1, "score": 1.0}]
        deferred = [{"rid": 2, "score": .5}, {"rid": 3, "score": math.nan}]
        original = list(deferred)
        self.assertIs(NATIVE.select_novelty(pool, deferred, {1: {"a"}, 2: set(), 3: {"b"}}, 2, 5), NotImplemented)
        self.assertEqual(deferred, original)
        self.assertIs(NATIVE.select_novelty(pool, deferred, {1: {"a"}}, 0, 5), NotImplemented)
        self.assertIs(NATIVE.select_novelty(pool, [], {1: {"a"}}, 2**53 + 1, 5), NotImplemented)

    def test_context_allocations_match_all_tiny_boundaries_and_unicode_lengths(self):
        rng = random.Random(3341)
        texts = ["", "a", "中🙂e\u0301\ud800", "x" * 119, "x" * 120, "x" * 121, "句子。" * 300]
        for size in (0, 1, 5, 50):
            pages = [allocation_page(str(i), rng.choice(texts)) for i in range(size)]
            for budget in (*range(180), 2400, 100_000):
                with patch.object(store, "_NATIVE", None):
                    expected = store._context_allocations(pages, budget)
                actual = NATIVE.context_allocations(pages, budget)
                self.assertEqual(actual, expected)
                self.assertTrue(all(a[0] is b[0] for a, b in zip(actual, expected)))

    def test_allocation_fallback_preserves_custom_access_and_ignored_invalid_tail(self):
        class Observed(dict):
            def __getitem__(self, key):
                calls.append(key)
                return super().__getitem__(key)
        pages = [Observed(allocation_page("a", "x" * 500)), {"bad": "unreached"}]
        outcomes = []
        for backend in (None, NATIVE):
            calls = []
            with patch.object(store, "_NATIVE", backend):
                value = store._context_allocations(pages, 90)
            outcomes.append((value, calls))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertIs(NATIVE.context_allocations([allocation_page("a", "b")], 2**100), NotImplemented)

    def test_refs_preserve_big_integers_order_unknown_fields_and_shallow_aliases(self):
        shared = {"message_indices": [0, 2], "nested": {"flag": True}}
        big = 2**100
        refs = [{**shared, "start": big, "end": big + 10, "turn_start": big * 2},
                {**shared, "start": big + 5, "end": big + 20, "turn_start": -big}]
        spans = [(big, big + 8), [big + 4, big + 12], (big + 21, big + 22)]
        with patch.object(store, "_NATIVE", None):
            expected = store._refs_from_parsed(refs, spans)
        actual = NATIVE.refs_from_parsed(refs, spans)
        self.assertEqual(actual, expected)
        self.assertTrue(all(ref["message_indices"] is shared["message_indices"] for ref in actual))
        self.assertTrue(all(ref["nested"] is shared["nested"] for ref in actual))
        self.assertIs(actual[0]["start"], spans[0][0])
        self.assertIs(actual[0]["end"], spans[0][1])
        self.assertTrue(all(output is not original for output in actual for original in refs))

    def test_refs_custom_types_keep_python_calls_and_exceptions(self):
        class Observed(dict):
            def __getitem__(self, key):
                calls.append(key)
                return super().__getitem__(key)
        refs = [Observed(start=1, end=5, turn_start=10)]
        outcomes = []
        for backend in (None, NATIVE):
            calls = []
            with patch.object(store, "_NATIVE", backend):
                value = store._refs_from_parsed(refs, [(0, 3)])
            outcomes.append((value, calls))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertIs(NATIVE.refs_from_parsed([{"start": True, "end": 5, "turn_start": 0}], [(0, 3)]), NotImplemented)
        for backend in (None, NATIVE):
            with patch.object(store, "_NATIVE", backend):
                self.assertEqual(store._refs_from_parsed([{"start": 9, "end": 12}], [(0, 3)]), [])


@unittest.skipUnless(AVAILABLE, "Native ranking extension is not installed")
class NativeStoreEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", max_page_chars=500, min_page_chars=0)
        self.addCleanup(self.book.close)
        for i in range(32):
            self.book.ingest({"project": "alpha" if i < 30 else "foreign", "session_id": str(i),
                "task_id": str(i % 4), "task_title": "quartz pressure cache",
                "title": "caching pressure" if i % 2 else "quartz archive",
                "created_at": f"2026-03-{i % 28 + 1:02d}T00:00:00Z",
                "messages": [{"role": "assistant", "content":
                    f"quartz pressure = {i + 10}. The cache stores cached values. 中🙂\n" +
                    "Background source evidence. " * (i % 6)}]})

    def recall(self, backend, query, *, warmup=True, **options):
        # SQLite's first FTS access emits private initialization queries. Prime
        # the same request on each side before comparing complete SQL traces;
        # no trace statement is filtered or normalized.
        if warmup:
            with patch.object(store, "_NATIVE", backend):
                self.book.recall(query, use_cache=False, **options)
        self.book._directory_tokens.cache_clear()
        self.book._token_count_memo = None
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            with patch.object(store, "_NATIVE", backend):
                result = self.book.recall(query, use_cache=False, **options)
        finally:
            self.book.db.set_trace_callback(None)
        result.pop("latency_ms")
        return result, statements

    def test_complete_payloads_sql_and_sources_match_all_ranking_paths(self):
        for query in ("quartz pressure", "caching", "current quartz pressure", "previous current quartz"):
            for options in ({"project": "alpha"}, {"strategy": "flat"}, {"limit": 1, "budget_chars": 95},
                            {"limit": 50, "budget_chars": 100_000}, {"coverage": True},
                            {"project": "missing"}, {"budget_chars": 0}):
                with self.subTest(query=query, options=options):
                    self.assertEqual(self.recall(None, query, **options), self.recall(NATIVE, query, **options))

    def test_ordinary_recall_dispatches_score_novelty_and_allocation_batches(self):
        observed = Mock(wraps=NATIVE)
        self.recall(observed, "quartz pressure", project="alpha")
        for name in ("rank_candidates", "select_novelty", "context_allocations"):
            self.assertGreater(getattr(observed, name).call_count, 0, name)
        with patch.object(store, "_NATIVE", observed):
            store._refs_from_parsed([{"start": 0, "end": 5, "turn_start": 1}], [(0, 3)])
        self.assertEqual(observed.refs_from_parsed.call_count, 1)

    def test_replaced_directory_cache_and_sqlite_factories_keep_python_score_loop(self):
        ordinary = self.book._directory_tokens
        for mode in ("directory", "rows", "text"):
            observed = Mock(wraps=NATIVE)
            original_rows, original_text = self.book.db.row_factory, self.book.db.text_factory
            try:
                if mode == "directory":
                    self.book._directory_tokens = Mock(wraps=ordinary)
                elif mode == "rows":
                    self.book.db.row_factory = lambda cursor, row: sqlite3.Row(cursor, row)
                else:
                    self.book.db.text_factory = lambda raw: raw.decode("utf-8")
                with patch.object(store, "_NATIVE", observed):
                    self.book.recall("quartz pressure", project="alpha", use_cache=False)
                observed.rank_candidates.assert_not_called()
            finally:
                self.book._directory_tokens = ordinary
                self.book.db.row_factory, self.book.db.text_factory = original_rows, original_text

    def test_directory_replacement_inside_a_token_callback_remains_visible(self):
        ordinary = self.book._directory_tokens
        real_terms = store.terms
        results, recorded = [], []
        try:
            for backend in (None, NATIVE):
                self.book._directory_tokens = ordinary
                ordinary.cache_clear()
                with patch.object(store, "_NATIVE", backend):
                    self.book.recall("quartz pressure", limit=50, use_cache=False)
                ordinary.cache_clear()
                calls = []
                def replacement(directory):
                    calls.append(("replacement", directory))
                    return frozenset(real_terms(directory, query=True))
                def changed_terms(text, *, query=False):
                    calls.append(("terms", text))
                    self.book._directory_tokens = replacement
                    return real_terms(text, query=query)
                with patch.object(store, "terms", changed_terms):
                    results.append(self.recall(backend, "quartz pressure", limit=50, warmup=False))
                recorded.append(calls)
            self.assertEqual(results[0], results[1])
            self.assertEqual(recorded[0], recorded[1])
            self.assertTrue(any(kind == "replacement" for kind, _ in recorded[0]))
        finally:
            self.book._directory_tokens = ordinary

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Install .[tokens]")
    def test_both_token_encoders_keep_exact_budgets_and_source_refs(self):
        for tokenizer in ("cl100k_base", "o200k_base"):
            for budget in (0, 128, 1024):
                options = {"project": "alpha", "budget_tokens": budget, "tokenizer": tokenizer}
                self.assertEqual(self.recall(None, "quartz pressure", **options),
                                 self.recall(NATIVE, "quartz pressure", **options))


if __name__ == "__main__":
    unittest.main()
