"""Same-snapshot source batching and reference projection with old-path guards."""
from contextlib import contextmanager
import importlib.util
import json
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store
from memory_book import token_budget as budget


HAS_TOKENS = importlib.util.find_spec("tiktoken") is not None
HAS_LIMITS = hasattr(sqlite3.Connection, "getlimit")


def populate(book):
    for number in range(4):
        book.ingest({"project": "fixture", "session_id": str(number), "title": "Quartz records",
            "created_at": "2026-11-14T00:00:00Z", "messages": [
                {"role": "user", "content": "Quartz pressure is 82. Retry remains 45 seconds. " * 12},
                {"role": "user", "content": "Quartz café e\u0301 缓存45秒。 <|endoftext|> is literal.\n" * 8}]})


def legacy_turns(book, wanted):
    turns = {}
    for session, ordinals in wanted.items():
        ordered = sorted(ordinals)
        for row in book.db.execute("SELECT ordinal,content FROM turns WHERE session_pk=? AND ordinal IN ("
                + ",".join("?" for _ in ordered) + ")", [session, *ordered]):
            turns[(session, row["ordinal"])] = row["content"]
    return turns


def response(book, **options):
    value = book.recall("quartz pressure retry", use_cache=False, **options)
    value.pop("latency_ms")
    return value


@contextmanager
def previous_source_path(book):
    with patch.object(book, "_batch_original_turns", return_value=None), \
            patch.object(store, "_ORDINARY_REFS", object()):
        yield


@contextmanager
def json_callers():
    counts = {}
    code = json.loads.__code__
    previous = sys.getprofile()
    def observe(frame, event, value):
        if event == "call" and frame.f_code is code and frame.f_back.f_code.co_filename == store.__file__:
            name = frame.f_back.f_code.co_name
            counts[name] = counts.get(name, 0) + 1
    sys.setprofile(observe)
    try:
        yield counts
    finally:
        sys.setprofile(previous)


class OriginalTurnBatchTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", cache_size=0, segmentation="turn")
        self.addCleanup(self.book.close)
        populate(self.book)
        self.sessions = [row[0] for row in self.book.db.execute("SELECT id FROM sessions ORDER BY id")]
        self.wanted = {key: {0, 1} for key in self.sessions}

    @unittest.skipUnless(HAS_LIMITS, "Python 3.10 retains the original per-session path")
    def test_one_indexed_batch_fetches_exact_pairs_including_missing_turns(self):
        wanted = {self.sessions[0]: {0, 1, 99}, self.sessions[1]: {1}, "absent-session": {0}}
        expected = legacy_turns(self.book, wanted)
        sql = []
        self.book.db.set_trace_callback(sql.append)
        actual = self.book._batch_original_turns(wanted)
        self.book.db.set_trace_callback(None)
        if actual is None:
            self.skipTest("SQLite build has nonstandard restrictive compiler limits")
        self.assertEqual(actual, expected)
        self.assertEqual(len(sql), 1)
        self.assertIn("CROSS JOIN turns", sql[0])
        plan = self.book.db.execute("EXPLAIN QUERY PLAN " + sql[0]).fetchall()
        self.assertTrue(any("SEARCH t USING INDEX" in row[3] and "session_pk=? AND ordinal=?" in row[3]
                            for row in plan), [row[3] for row in plan])

    def test_single_empty_malformed_overflow_and_excessive_sets_keep_old_path(self):
        cases = [{}, {self.sessions[0]: {0}}, {self.sessions[0]: set(), self.sessions[1]: {0}},
                 {self.sessions[0]: {0}, self.sessions[1]: {"1"}},
                 {self.sessions[0]: {0}, self.sessions[1]: {True}},
                 {self.sessions[0]: {0}, self.sessions[1]: {1 << 63}},
                 {self.sessions[0]: {0}, self.sessions[1]: {-(1 << 63) - 1}},
                 {self.sessions[0]: {0}, self.sessions[1]: {0, "mixed"}},
                 {self.sessions[0]: {0}, b"bytes-session": {1}},
                 {self.sessions[0]: set(range(200)), self.sessions[1]: set(range(201))}]
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            for wanted in cases:
                self.assertIsNone(self.book._batch_original_turns(wanted))
            self.assertEqual(statements, [])
            # Reject without sorting the later malformed set; the legacy
            # first session still executes before its original TypeError.
            with self.assertRaises(TypeError):
                legacy_turns(self.book, cases[7])
            self.assertEqual(len(statements), 1)
        finally:
            self.book.db.set_trace_callback(None)

    @unittest.skipUnless(HAS_LIMITS, "sqlite3 getlimit/setlimit are optional before Python 3.11")
    def test_runtime_variable_sql_length_and_compiler_limits_fall_back(self):
        limits = ((sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 3),
                  (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 150),
                  (sqlite3.SQLITE_LIMIT_COLUMN, 100),
                  (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 50),
                  (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 1),
                  (sqlite3.SQLITE_LIMIT_VDBE_OP, 2000))
        wanted = {key: {0, 1} for key in self.sessions[:2]}
        expected = legacy_turns(self.book, wanted)
        for category, value in limits:
            with self.subTest(category=category):
                previous = self.book.db.setlimit(category, value)
                try:
                    self.assertIsNone(self.book._batch_original_turns(wanted))
                    self.assertEqual(legacy_turns(self.book, wanted), expected)
                finally:
                    self.book.db.setlimit(category, previous)

    def test_absent_getlimit_and_custom_factories_keep_original_queries(self):
        original_getattr = getattr
        def absent(value, name, *default):
            return None if value is self.book.db and name == "getlimit" else original_getattr(value, name, *default)
        with patch.object(store, "getattr", absent, create=True):
            self.assertIsNone(self.book._batch_original_turns(self.wanted))
        for name, value in (("row_factory", lambda cursor, values: sqlite3.Row(cursor, values)),
                            ("text_factory", lambda raw: raw.decode())):
            old = getattr(self.book.db, name)
            try:
                setattr(self.book.db, name, value)
                self.assertIsNone(self.book._batch_original_turns(self.wanted))
            finally:
                setattr(self.book.db, name, old)
        class Connection(sqlite3.Connection):
            pass
        native_connect = sqlite3.connect
        with patch.object(sqlite3, "connect", side_effect=lambda *args, **kwargs:
                native_connect(*args, factory=Connection, **kwargs)):
            with MemoryBook(":memory:") as custom:
                self.assertIsNone(custom._batch_original_turns(self.wanted))

    @unittest.skipUnless(HAS_LIMITS, "Python 3.10 retains the original per-session path")
    def test_four_hundred_pairs_bound_and_lowered_variable_limit(self):
        wanted = {self.sessions[0]: set(range(200)), self.sessions[1]: set(range(200))}
        expected = legacy_turns(self.book, wanted)
        result = self.book._batch_original_turns(wanted)
        if result is None:
            self.skipTest("SQLite build has nonstandard restrictive compiler limits")
        self.assertEqual(result, expected)
        old = self.book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 799)
        try:
            self.assertIsNone(self.book._batch_original_turns(wanted))
            self.assertEqual(legacy_turns(self.book, wanted), expected)
        finally:
            self.book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, old)

    def test_reference_clipping_order_fresh_objects_and_empty_spans(self):
        refs = [{"start": 2, "end": 8, "turn_start": 10, "turn_end": 16,
                 "turn_index": 4, "project": "fixture", "session_id": "source"}]
        spans = [(0, 3), (7, 12), (2, 8), (8, 8)]
        expected = MemoryBook._refs({"source_refs": json.dumps(refs)}, spans)
        actual = store._refs_from_parsed(refs, spans)
        self.assertEqual(actual, expected)
        self.assertTrue(all(value is not refs[0] for value in actual))
        actual[0]["start"] = -1
        self.assertEqual(refs[0]["start"], 2)
        self.assertEqual(MemoryBook._refs({"source_refs": "invalid JSON"}, []), [])
        self.assertEqual(MemoryBook._refs({}, []), [])
        self.assertEqual(store._refs_from_parsed(None, []), [])

    def test_json_wrapper_installed_before_store_import_is_uncertified(self):
        code = """import json
from functools import wraps
ordinary = json.loads
@wraps(ordinary)
def replacement(*args, **kwargs):
    return ordinary(*args, **kwargs)
json.loads = replacement
from memory_book import store
assert store._ORDINARY_JSON_LOADS is None
assert store.MemoryBook._refs({'source_refs': '[]'}, [(0, 1)]) == []
"""
        subprocess.run([sys.executable, "-S", "-c", code], check=True, capture_output=True, text=True)


@unittest.skipUnless(HAS_TOKENS, "Install .[tokens] for complete token-path regression")
class InSnapshotSourceWorkTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", cache_size=0, segmentation="turn")
        self.addCleanup(self.book.close)
        populate(self.book)

    def compare(self, **options):
        actual = response(self.book, **options)
        with previous_source_path(self.book):
            expected = response(self.book, **options)
        self.assertEqual(actual, expected)
        return actual

    def test_complete_payloads_for_both_encoders_budgets_scopes_and_single_session(self):
        for name in budget.TOKENIZERS:
            for tokens in (0, 1, 64, 512, 1024, 10000):
                for scope in ({}, {"project": "fixture"}, {"project": "fixture", "session": "0"}):
                    result = self.compare(tokenizer=name, budget_tokens=tokens, budget_chars=8000, **scope)
                    self.assertEqual(result["context_tokens"], budget.TokenCounter(name).count(result["context"]))
        for chars in (0, 80, 4000):
            self.compare(budget_chars=chars)

    def test_fewer_source_queries_and_one_json_parse_per_selected_page(self):
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            with json_callers() as actual_counts:
                actual = response(self.book, budget_tokens=1024, budget_chars=8000)
            native_sql = list(statements)
            statements.clear()
            with previous_source_path(self.book), json_callers() as previous_counts:
                expected = response(self.book, budget_tokens=1024, budget_chars=8000)
            previous_sql = list(statements)
        finally:
            self.book.db.set_trace_callback(None)
        self.assertEqual(actual, expected)
        self.assertEqual(actual_counts.get("_refs", 0), 0)
        self.assertEqual(actual_counts["recall"], previous_counts["recall"])
        self.assertEqual(previous_counts["_refs"], len(actual["results"]))
        old = [sql for sql in previous_sql if sql.startswith("SELECT ordinal,content FROM turns")]
        self.assertGreater(len(old), 1)
        if HAS_LIMITS:
            self.assertEqual(sum(sql.startswith("WITH requested_turns") for sql in native_sql), 1)
            self.assertFalse(any(sql.startswith("SELECT ordinal,content FROM turns") for sql in native_sql))

    def test_custom_prepare_mutation_keeps_original_parsing_and_session_loop(self):
        prepare = budget.prepare_source_units
        def custom(pages, turns, refs_by_page):
            prepared = prepare(pages, turns, refs_by_page)
            for refs in refs_by_page.values():
                for ref in refs:
                    ref["unused_custom_marker"] = True
            return prepared
        statements = []
        self.book.db.set_trace_callback(statements.append)
        try:
            with patch.object(budget, "prepare_source_units", custom):
                result = self.compare(budget_tokens=10000, budget_chars=8000)
            self.assertFalse(any(sql.startswith("WITH requested_turns") for sql in statements))
            self.assertTrue(any(sql.startswith("SELECT ordinal,content FROM turns") for sql in statements))
            self.assertTrue(all("unused_custom_marker" not in ref for hit in result["results"] for ref in hit["source_refs"]))
        finally:
            self.book.db.set_trace_callback(None)

    def test_custom_reference_and_json_methods_are_called_with_original_arguments(self):
        original_refs, original_loads = self.book._refs, json.loads
        calls = []
        def custom_refs(row, spans):
            calls.append((row["id"], spans))
            return [{**ref, "custom": True} for ref in original_refs(row, spans)]
        with patch.object(self.book, "_refs", custom_refs):
            result = self.compare(budget_tokens=1024, budget_chars=8000)
            self.assertEqual(len(calls), 2 * len(result["results"]))
            self.assertTrue(all(ref["custom"] for hit in result["results"] for ref in hit["source_refs"]))
        parsed = []
        def custom_loads(value, *args, **kwargs):
            parsed.append(value)
            return original_loads(value, *args, **kwargs)
        with patch.object(json, "loads", custom_loads):
            self.compare(budget_tokens=1024, budget_chars=8000)
        self.assertGreaterEqual(len(parsed), 4 * len(result["results"]))

    def test_breadcrumb_changes_raw_id_or_refs_after_assembly_without_private_keys(self):
        ordinary = self.book._breadcrumb
        for mutation in ("raw", "id", "method"):
            seen = []
            def custom_refs(row, spans):
                return [{**ref, "late_method": True} for ref in MemoryBook._refs(row, spans)]
            def breadcrumbs(row):
                seen.append(set(row))
                self.assertTrue(all(type(key) is str for key in row))
                value = ordinary(row)
                if mutation == "raw":
                    refs = json.loads(row["source_refs"])
                    for ref in refs:
                        ref["late_raw"] = True
                    row["source_refs"] = json.dumps(refs)
                elif mutation == "id":
                    row["id"] = [row["id"]]
                else:
                    self.book._refs = custom_refs
                return value
            original_refs = self.book._refs
            try:
                with patch.object(self.book, "_breadcrumb", breadcrumbs):
                    result = self.compare(budget_tokens=1024, budget_chars=8000)
                count = len(result["results"])
                self.assertEqual(seen[:count], seen[count:])
                if mutation == "raw":
                    self.assertTrue(all(ref["late_raw"] for hit in result["results"] for ref in hit["source_refs"]))
                elif mutation == "id":
                    self.assertTrue(all(type(hit["id"]) is list for hit in result["results"]))
                else:
                    self.assertTrue(all(ref["late_method"] for hit in result["results"] for ref in hit["source_refs"]))
            finally:
                self.book._refs = original_refs

    def test_late_missing_raw_or_json_patch_preserves_errors_and_empty_span_behavior(self):
        ordinary_breadcrumb, ordinary_assemble, ordinary_loads = self.book._breadcrumb, budget.assemble_with_count, json.loads
        def missing_raw(row):
            crumbs = ordinary_breadcrumb(row)
            del row["source_refs"]
            return crumbs
        with patch.object(self.book, "_breadcrumb", missing_raw):
            self.assert_old_error()
        def empty_spans(*args, **kwargs):
            kept, count = ordinary_assemble(*args, **kwargs)
            self.assertTrue(all(all(type(key) is str for key in row) for row, _, _, _ in kept))
            return [(row, head, text, []) for row, head, text, _ in kept], count
        with patch.object(self.book, "_breadcrumb", missing_raw), \
                patch.object(budget, "assemble_with_count", empty_spans):
            result = self.compare(budget_tokens=1024, budget_chars=8000)
            self.assertTrue(all(hit["source_refs"] == [] for hit in result["results"]))
        errors = []
        for optimized in (True, False):
            def changed_json(value, *args, **kwargs):
                raise ValueError("late custom JSON loader")
            def install_json(row):
                crumbs = ordinary_breadcrumb(row)
                json.loads = changed_json
                return crumbs
            try:
                with patch.object(json, "loads", ordinary_loads), patch.object(self.book, "_breadcrumb", install_json):
                    if optimized:
                        response(self.book, budget_tokens=1024, budget_chars=8000)
                    else:
                        with previous_source_path(self.book):
                            response(self.book, budget_tokens=1024, budget_chars=8000)
            except Exception as exc:
                errors.append((type(exc), exc.args))
        self.assertEqual(errors, [(ValueError, ("late custom JSON loader",))] * 2)

    def assert_old_error(self):
        errors = []
        for optimized in (True, False):
            try:
                if optimized:
                    response(self.book, budget_tokens=1024, budget_chars=8000)
                else:
                    with previous_source_path(self.book):
                        response(self.book, budget_tokens=1024, budget_chars=8000)
            except Exception as exc:
                errors.append((type(exc), exc.args))
        self.assertEqual(len(errors), 2)
        self.assertEqual(errors[0], errors[1])

    def test_source_corruption_invalid_json_and_overflow_retain_original_errors(self):
        result = response(self.book, budget_tokens=1024, budget_chars=8000)
        identity = result["results"][0]["id"]
        original = self.book.db.execute("SELECT content,source_refs FROM pages WHERE id=?", (identity,)).fetchone()
        for mutation in ("text", "json", "missing", "overflow", "mixed"):
            with self.subTest(mutation=mutation):
                content, raw = original
                if mutation == "text":
                    content = content.replace("Quartz", "Wrong!")
                elif mutation == "json":
                    raw = "invalid JSON"
                else:
                    refs = json.loads(raw)
                    if mutation == "missing":
                        refs[0]["turn_index"] = -1
                    elif mutation == "overflow":
                        refs[0]["turn_index"] = 1 << 63
                    else:
                        refs.append({**refs[0], "turn_index": "mixed"})
                    raw = json.dumps(refs)
                self.book.db.execute("UPDATE pages SET content=?,source_refs=? WHERE id=?", (content, raw, identity))
                try:
                    self.assert_old_error()
                finally:
                    self.book.db.execute("UPDATE pages SET content=?,source_refs=? WHERE id=?", (*original, identity))


if __name__ == "__main__":
    unittest.main()
