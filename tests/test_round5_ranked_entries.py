"""Invented exact-output and sorting-mechanism checks for candidate L.

The legacy callable is reconstructed from the three registered replacements and
checked against the complete pre-L recall digest. No dataset or timing gate is
used. Float bit patterns, not NaN equality, verify unchanged scores.
"""
from __future__ import annotations

import ast
import cProfile
import hashlib
import importlib.util
import inspect
import json
import math
import pstats
import random
import sqlite3
import struct
import textwrap
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store
from tests import test_round5_materialization as fixtures


BASE_COMMIT = "4720728e47d53fc6c345fa89a2b5b739a67a1069"
BASE_RECALL_SHA256 = "c67c33615f32a063f40992adc28c7bd148625c5c9d54ec004d0785e5411a70ab"
LEGACY_FILENAME = "<candidate-l-literal-base-recall>"
CANDIDATE_RECALL = MemoryBook.recall
HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None
# These are the entire allowed changes, including comments. Restoring them must
# reproduce the exact complete base method, not an independently rewritten one.
REPLACEMENTS = (
    ("                    if late_materialize:\n                        # Carry the unchanged complete sort key in the entry.\n                        # Retain score itself, including signed zero and NaNs.\n                        if fuse_routes:\n                            ranked_rows.append((-score, exact_ranks.get(page_id, 97),\n                                                stem_ranks.get(page_id, 97), page_id, score, row, item))\n                        else:\n                            ranked_rows.append((-score, page_id, score, row, item))\n",
     "                    if late_materialize:\n                        ranked_rows.append((page_id, score, row, item))\n"),
    ("                if late_materialize:\n                    # Exact str IDs were deduplicated in rows. The complete old\n                    # key distinguishes every entry before the payload tail, so\n                    # comparisons never reach score, route rows or metadata.\n                    ranked_rows.sort()\n",
     "                if late_materialize:\n                    if fuse_routes:\n                        ranked_rows.sort(key=lambda entry: (-entry[1], exact_ranks.get(entry[0], 97),\n                                                            stem_ranks.get(entry[0], 97), entry[0]))\n                    else:\n                        ranked_rows.sort(key=lambda entry: (-entry[1], entry[0]))\n"),
    ("                    for ranked in ranked_rows[:prefix_size]:\n                        score = ranked[-3]\n                        row = ranked[-2]\n                        metadata = ranked[-1]\n                        item = dict(zip(route_columns, row))\n",
     "                    for _, score, row, metadata in ranked_rows[:prefix_size]:\n                        item = dict(zip(route_columns, row))\n"),
)


def restored_source():
    source = inspect.getsource(CANDIDATE_RECALL)
    for new, old in REPLACEMENTS:
        if source.count(new) != 1:
            raise AssertionError("Candidate L no longer has its one registered replacement")
        source = source.replace(new, old)
    source = source.rstrip() + "\n"
    if hashlib.sha256(source.encode()).hexdigest() != BASE_RECALL_SHA256:
        raise AssertionError("Literal base recall changed outside the three registered replacements")
    return textwrap.dedent(source)


def legacy_recall():
    namespace = dict(vars(store))
    exec(compile(restored_source(), LEGACY_FILENAME, "exec"), namespace)
    return namespace["recall"]


def exact(value):
    """Keep every payload field, including IEEE signs/payloads; omit only latency."""
    if type(value) is float:
        return ("float64", struct.pack(">d", value).hex())
    if type(value) is dict:
        return {key: exact(item) for key, item in value.items() if key != "latency_ms"}
    if type(value) in (list, tuple):
        return [exact(item) for item in value]
    return value


def candidate_expressions():
    tree = ast.parse(textwrap.dedent(inspect.getsource(CANDIDATE_RECALL)))
    found = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "ranked_rows"
                and node.func.attr == "append"):
            expression = node.args[0]
            if not isinstance(expression, ast.Tuple) or len(expression.elts) not in (5, 7):
                raise AssertionError("Unexpected ranked entry representation")
            found[len(expression.elts) == 7] = compile(ast.Expression(expression), "<actual-l-entry>", "eval")
    if set(found) != {False, True}:
        raise AssertionError("Both real runtime entry expressions are required")
    return found


def invoke(book, legacy, query, **options):
    method = legacy_recall() if legacy else CANDIDATE_RECALL
    return method(book, query, use_cache=False, **options)


class TailMustNotCompare:
    def __eq__(self, other):
        raise AssertionError("Sorting reached a payload tail")
    def __lt__(self, other):
        raise AssertionError("Sorting reached a payload tail")


class RankedEntryRepresentationTests(unittest.TestCase):
    def test_only_three_registered_changes_restore_literal_base_method(self):
        old = ast.parse(restored_source())
        new = ast.parse(textwrap.dedent(inspect.getsource(CANDIDATE_RECALL)))
        keys = lambda tree: [node for node in ast.walk(tree) if isinstance(node, ast.Lambda)
                             and node.args.args and node.args.args[0].arg == "entry"]
        self.assertEqual(len(keys(old)), 2)
        self.assertEqual(len(keys(new)), 0)
        sorts = [node for node in ast.walk(new) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "sort"
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == "ranked_rows"]
        self.assertEqual(len(sorts), 1)
        self.assertEqual(sorts[0].args, [])
        self.assertEqual(sorts[0].keywords, [])
        self.assertEqual(set(candidate_expressions()), {False, True})

    def compare_vectors(self, scores, fused, order):
        code = candidate_expressions()[fused]
        records = [(f"id-{index:04d}", scores[index], TailMustNotCompare(), TailMustNotCompare())
                   for index in order]
        # Shared ordinals exercise the ID tie-break even more broadly than the
        # runtime's unique last ordinal for each deduplicated route ID.
        exact_ranks = {page_id: index % 3 + 1 for index, (page_id, *_rest) in enumerate(records)
                       if index % 4 != 0}
        stem_ranks = {page_id: index % 5 + 1 for index, (page_id, *_rest) in enumerate(records)
                      if index % 3 != 0}
        if fused:
            expected = sorted(records, key=lambda entry: (
                -entry[1], exact_ranks.get(entry[0], 97), stem_ranks.get(entry[0], 97), entry[0]))
        else:
            expected = sorted(records, key=lambda entry: (-entry[1], entry[0]))
        actual = []
        for page_id, score, row, item in records:
            entry = eval(code, {}, {"page_id": page_id, "score": score, "row": row, "item": item,
                                    "exact_ranks": exact_ranks, "stem_ranks": stem_ranks})
            self.assertIs(entry[-3], score)
            self.assertIs(entry[-2], row)
            self.assertIs(entry[-1], item)
            actual.append(entry)
        actual.sort()
        id_position = 3 if fused else 1
        self.assertEqual([entry[id_position] for entry in actual], [entry[0] for entry in expected])
        self.assertEqual([exact(entry[-3]) for entry in actual], [exact(entry[1]) for entry in expected])

    def test_finite_ties_signed_zero_and_integer_scores_never_compare_payloads(self):
        scores = [0.0, -0.0, 0, 1, -1, 2.0, 2.0, -3.0,
                  float.fromhex("0x0.0000000000001p-1022"), 1e300] * 20
        order = list(range(len(scores)))
        for fused in (False, True):
            for arranged in (order, list(reversed(order))):
                with self.subTest(fused=fused, first=arranged[0]):
                    self.compare_vectors(scores, fused, arranged)

    def test_nonfinite_order_and_score_bits_match_legacy_for_fixed_permutations(self):
        scores = [float("inf"), float("-inf"), float("nan"), -float("nan"),
                  struct.unpack(">d", bytes.fromhex("7ff8000000000001"))[0],
                  struct.unpack(">d", bytes.fromhex("fff8000000000017"))[0],
                  0.0, -0.0, 3.0, 3.0, -2.0, 1, 0]
        randomizer = random.Random(51613)
        for iteration in range(24):
            order = list(range(len(scores)))
            randomizer.shuffle(order)
            for fused in (False, True):
                with self.subTest(iteration=iteration, fused=fused):
                    self.compare_vectors(scores, fused, order)


class RankedEntryRecallTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000,
                               min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)
        self.records = fixtures.seed(self.book)

    def compare(self, query, *, book=None, **options):
        book = book or self.book
        options = {"budget_chars": 4000, **options}
        expected = invoke(book, True, query, **options)
        actual = invoke(book, False, query, **options)
        self.assertEqual(exact(actual), exact(expected))
        return actual

    def derived(self):
        helper = fixtures.DerivedMapMaterializationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        return helper

    def injected(self, helper, legacy, *args, **kwargs):
        method = legacy_recall() if legacy else CANDIDATE_RECALL
        with patch.object(MemoryBook, "recall", method):
            return helper.recall_routes(*args, **kwargs)

    def test_real_sqlite_fused_identical_single_scope_and_temporal_payloads(self):
        for name, (query, options) in fixtures.scenarios(self.records).items():
            with self.subTest(name=name):
                self.compare(query, **options)

    def test_small_budgets_limits_and_default_cache_payloads_are_unchanged(self):
        for budget in (0, 30, 250, 4000, 100000):
            for limit in (1, 5, 50):
                with self.subTest(budget=budget, limit=limit):
                    self.compare("orbiting relay", project="lab", budget_chars=budget, limit=limit)
        self.book.cache_size = 2
        for legacy in (True, False):
            self.book.db.execute("DELETE FROM recall_cache")
            method = legacy_recall() if legacy else CANDIDATE_RECALL
            first = method(self.book, "orbiting relay", project="lab", use_cache=True)
            second = method(self.book, "orbiting relay", project="lab", use_cache=True)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            second["cache_hit"] = False
            self.assertEqual(exact(first), exact(second))

    def test_full_wide_union_and_limit_fifty_preserve_complete_count_and_order(self):
        helper = fixtures.WideCandidateMaterializationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        for query, options in [
            ("orbiting", {"limit": 50}),
            ("qzx17 relay", {"limit": 5}),
            ("current relay calibration", {"limit": 1}),
            ("缓存有效期", {"limit": 50}),
        ]:
            with self.subTest(query=query, options=options):
                result = self.compare(query, book=helper.book, project="wide",
                                      budget_chars=100000, **options)
                self.assertGreater(result["candidate_count"], options["limit"])
        exact_route = [(index, -float(193 - index)) for index in range(96)]
        # The real query above exercises SQLite; a separate route fixture below
        # proves duplicate/overlap precedence without relying on planner ranks.
        self.assertEqual(len(exact_route), 96)

    def test_duplicate_route_ids_last_rank_scale_and_metadata_last_value_match_literal_base(self):
        helper = self.derived()
        route = helper.route([(0, -100.0), (1, -4), (0, -2), (2, -1.0)])
        stem = helper.route([(1, -100), (0, -4.0), (1, 0), (2, -2)])
        for duplicate_metadata in (False, True):
            def transform(cursor, rows):
                if not duplicate_metadata:
                    return rows
                values = list(rows[0])
                values[3] = "qzx17 last metadata title"
                return [*rows, sqlite3.Row(cursor, tuple(values))]
            expected = self.injected(helper, True, route, stem, metadata_transform=transform)
            actual = self.injected(helper, False, route, stem, metadata_transform=transform)
            self.assertEqual(exact(actual), exact(expected))
            self.assertEqual(actual["candidate_count"], 3)

    def test_live_native_rows_with_nonfinite_and_signed_zero_ranks_preserve_score_bits(self):
        helper = self.derived()
        cases = [
            ([-0.0, 0.0, -1.0], [0.0, -0.0, -1.0], (0, 1, 2)),
            ([float("nan"), float("-inf"), -1.0], [float("-inf"), float("nan"), -2.0], (2, 1, 0)),
            ([float("inf"), float("inf"), -0.0], [0.0, -0.0, float("inf")], (1, 2, 0)),
        ]
        for exact_values, stem_values, order in cases:
            exact_route = helper.route(list(enumerate(exact_values)))
            stem = helper.route([(index, stem_values[index]) for index in order])
            with self.subTest(order=order, exact=[exact(x) for x in exact_values]):
                expected = self.injected(helper, True, exact_route, stem)
                actual = self.injected(helper, False, exact_route, stem)
                self.assertEqual(exact(actual), exact(expected))
                self.assertEqual(actual["candidate_count"], 3)

    def test_custom_row_factories_and_subclasses_keep_old_named_mapping_payloads(self):
        for factory in (fixtures.RowLike, fixtures.NamedLookupRow):
            with self.subTest(factory=factory):
                self.book.db.row_factory = factory
                try:
                    self.compare("orbiting relay", project="lab", budget_chars=100000)
                finally:
                    self.book.db.row_factory = sqlite3.Row

    def test_late_rank_error_precedes_metadata_and_keeps_rollback(self):
        helper = self.derived()
        class BadRank(float):
            def __neg__(self):
                raise ArithmeticError("invented late-rank failure")
        exact_route = helper.route([(0, -2.0), (1, BadRank(-1)), (2, -0.5)])
        stem = helper.route([(2, -1.0), (0, -0.5)])
        outcomes = []
        for legacy in (True, False):
            events = []
            with self.assertRaises(ArithmeticError) as caught:
                self.injected(helper, legacy, exact_route, stem, events=events,
                              metadata_error=AssertionError("metadata must not run"))
            outcomes.append((type(caught.exception), str(caught.exception), events))
            self.assertFalse(helper.book.db.in_transaction)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0][2], [])

    def test_unknown_and_missing_metadata_preserve_exception_and_rollback(self):
        helper = self.derived()
        route = helper.route([(0, -2.0), (1, -1.0), (2, -0.5)])
        for mode in ("unknown", "missing", "short-value"):
            def transform(cursor, rows):
                if mode == "unknown":
                    values = list(rows[0])
                    values[0] = "unknown-candidate-l-metadata"
                    return [*rows, sqlite3.Row(cursor, tuple(values))]
                if mode == "missing":
                    return rows[1:]
                return [sqlite3.Row(cursor, tuple(rows[0])[:-1]), *rows[1:]]
            outcomes = []
            for legacy in (True, False):
                try:
                    self.injected(helper, legacy, route, route, metadata_transform=transform)
                except (KeyError, IndexError) as error:
                    outcomes.append((type(error), str(error)))
                else:
                    self.fail("Original metadata error must remain observable")
                self.assertFalse(helper.book.db.in_transaction)
            self.assertEqual(outcomes[0], outcomes[1])

    def test_optional_coverage_semantic_and_title_following_keep_full_fallback(self):
        self.compare("relay calibration threshold and receiver tolerance", project="lab",
                     coverage=True, limit=3, budget_chars=1100)
        self.compare("orbiting relay", project="lab", follow_titles=True, limit=3)
        model = SimpleNamespace(fingerprint="candidate-l-invented-only")
        with patch.object(self.book, "_semantic_encoder", return_value=model), \
                patch("memory_book.semantic.check_index", return_value={}), \
                patch("memory_book.semantic.rank_pages", return_value=[]):
            self.compare("orbiting relay", project="lab", semantic=True, limit=3)

    @unittest.skipUnless(HAS_TOKENS, "optional tokenizer dependency not installed")
    def test_both_exact_tokenizers_preserve_full_payload_and_zero_budget(self):
        for tokenizer in ("cl100k_base", "o200k_base"):
            for budget in (0, 128, 512):
                with self.subTest(tokenizer=tokenizer, budget=budget):
                    self.compare("orbiting relay", project="lab", budget_chars=8000,
                                 budget_tokens=budget, tokenizer=tokenizer)

    def test_corrupt_text_id_keeps_original_sql_error_and_rollback(self):
        identity = self.book.db.execute("SELECT rid FROM pages ORDER BY rid LIMIT 1").fetchone()[0]
        self.book.db.execute("UPDATE pages SET id=CAST(x'80' AS TEXT) WHERE rid=?", (identity,))
        outcomes = []
        for legacy in (True, False):
            with self.assertRaises(sqlite3.OperationalError) as caught:
                invoke(self.book, legacy, "orbiting relay", project="lab", budget_chars=4000)
            outcomes.append((type(caught.exception), str(caught.exception)))
            self.assertFalse(self.book.db.in_transaction)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertIn("UTF-8", outcomes[0][1])

    def test_actual_profile_removes_only_the_old_per_entry_key_callback_and_keeps_sql(self):
        helper = fixtures.WideCandidateMaterializationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        key_lines = {node.lineno for node in ast.walk(ast.parse(restored_source()))
                     if isinstance(node, ast.Lambda) and node.args.args
                     and node.args.args[0].arg == "entry"}
        observations = []
        for legacy in (True, False):
            statements, native_reads = [], []
            ordinary = store._candidate_rows
            def watch(cursor, description, connection=None):
                result = ordinary(cursor, description, connection)
                native_reads.append(result[1] is not None)
                return result
            helper.book.db.set_trace_callback(lambda statement: statements.append(statement)
                if not statement.lstrip().startswith("--") else None)
            try:
                with patch.object(store, "_candidate_rows", watch):
                    method = legacy_recall() if legacy else CANDIDATE_RECALL
                    profiler = cProfile.Profile()
                    result = profiler.runcall(method, helper.book, "orbiting", project="wide",
                                             budget_chars=100000, limit=5, use_cache=False)
                stats = pstats.Stats(profiler).stats
                callbacks = sum(value[1] for (filename, line, name), value in stats.items()
                                if filename == LEGACY_FILENAME and line in key_lines and name == "<lambda>")
                observations.append((result, callbacks, statements))
                self.assertTrue(native_reads and all(native_reads))
            finally:
                helper.book.db.set_trace_callback(None)
        old, new = observations
        self.assertGreater(old[0]["candidate_count"], 96)
        self.assertEqual(old[1], old[0]["candidate_count"])
        self.assertEqual(new[1], 0)
        self.assertEqual(old[2], new[2])
        self.assertEqual(exact(old[0]), exact(new[0]))
        print(json.dumps({"mechanism": "candidate-l-ranked-entry-keys",
            "candidate_count": old[0]["candidate_count"], "legacy_key_callbacks": old[1],
            "candidate_key_callbacks": new[1], "same_application_sql": True,
            "same_full_payload_bits": True, "latency_claim": False}, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
