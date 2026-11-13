"""Invented exact-output and query-mechanism checks for candidate J.

No corpus, model, benchmark timing or fresh-question selector is used here.
"""
from __future__ import annotations

import math
import sqlite3
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store


EXPRESSION = '("needle") AND body : ("needle")'
TABLES = ("pages_fts", "pages_stem_fts")


def tuples(rows):
    return [tuple(row) for row in rows]


def without_timing(result):
    return {key: value for key, value in result.items() if key != "latency_ms"}


class RankedRouteTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE pages(
                rid INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
                project_id TEXT, chapter_id TEXT, session_pk TEXT);
            CREATE TABLE sessions(id TEXT PRIMARY KEY, external_id TEXT);
            CREATE VIRTUAL TABLE pages_fts
                USING fts5(title,question,body,directory,tokenize='unicode61');
            CREATE VIRTUAL TABLE pages_stem_fts
                USING fts5(title,question,body,directory,tokenize='porter unicode61');
        """)
        self.db.executemany("INSERT INTO sessions VALUES(?,?)",
                            [(f"s{i}", f"external-{i}") for i in range(4)])

    def seed(self, count, *, style="distinct"):
        for table in (*TABLES, "pages"):
            self.db.execute(f"DELETE FROM {table}")
        rows, documents = [], []
        for i in range(count):
            frequency = (1 if style == "tied" else
                         3 if style == "bands" and i < 80 else
                         2 if style == "bands" and i < 96 else
                         1 if style == "bands" else i + 1)
            body = " ".join(["needle"] * frequency + ["filler"] * (count + 1 - frequency))
            rows.append((i + 1, f"page-{count-i:04d}",
                         "kept" if i < count // 2 else "outside",
                         f"c{i % 3}", f"s{i % 4}"))
            documents.append((i + 1, "Title", "", body, "Archive"))
        self.db.executemany("INSERT INTO pages VALUES(?,?,?,?,?)", rows)
        for table in TABLES:
            self.db.executemany(f"INSERT INTO {table}(rowid,title,question,body,directory) VALUES(?,?,?,?,?)",
                                documents)

    def statement(self, table="pages_fts", *, where="", values=(), session=False,
                  bounds=None):
        sql = (f"SELECT p.rid,p.id,bm25({table},2.0,2.0,1.0,0.25) rank "
               f"FROM {table} JOIN pages p ON p.rid={table}.rowid")
        if session:
            sql += " JOIN sessions s ON s.id=p.session_pk"
        sql += f" WHERE {table} MATCH ?" + where
        parameters = [EXPRESSION, *values]
        if bounds is not None:
            sql += f" AND {table}.rowid BETWEEN ? AND ?"
            parameters.extend(bounds)
        return sql + " ORDER BY rank,p.id LIMIT 96", parameters

    def expected(self, sql, parameters):
        return tuples(self.db.execute(sql, parameters).fetchall())

    def invoke(self, sql, parameters, table="pages_fts", connection=None):
        rows, cursor = store._ranked_candidate_rows(
            self.db, sql, parameters, table,
            self.db if connection is None else connection)
        return tuples(rows), cursor

    def traced(self, sql, parameters, table="pages_fts"):
        trace = []
        self.db.set_trace_callback(trace.append)
        try:
            rows, cursor = self.invoke(sql, parameters, table)
        finally:
            self.db.set_trace_callback(None)
        return rows, cursor, trace

    @staticmethod
    def probes(trace):
        return [sql for sql in trace if sql.startswith("SELECT rid,id,rank FROM (")]

    @staticmethod
    def legacy(trace):
        return [sql for sql in trace if sql.startswith("SELECT p.rid,p.id,bm25(")]

    def test_empty_small_and_cutoff_counts_match_both_routes_exactly(self):
        for count in (0, 1, 95, 96, 97, 130):
            self.seed(count)
            for table in TABLES:
                with self.subTest(count=count, table=table):
                    sql, parameters = self.statement(table)
                    expected = self.expected(sql, parameters)
                    actual, _, trace = self.traced(sql, parameters, table)
                    self.assertEqual(actual, expected)
                    self.assertEqual(len(actual), min(count, 96))
                    self.assertEqual(len(self.probes(trace)), 1)
                    self.assertEqual(self.legacy(trace), [])

    def test_cutoff_ties_fall_back_without_an_arbitrary_tie_cap(self):
        self.seed(350, style="tied")
        for table in TABLES:
            with self.subTest(table=table):
                sql, parameters = self.statement(table)
                expected = self.expected(sql, parameters)
                actual, _, trace = self.traced(sql, parameters, table)
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), 96)
                self.assertEqual(len(self.probes(trace)), 1)
                self.assertEqual(len(self.legacy(trace)), 1)
                self.assertEqual([row[1] for row in actual],
                                 sorted(row[1] for row in actual))

    def test_complete_earlier_tie_groups_need_no_legacy_requery(self):
        self.seed(140, style="bands")
        sql, parameters = self.statement()
        actual, _, trace = self.traced(sql, parameters)
        self.assertEqual(actual, self.expected(sql, parameters))
        self.assertEqual(len(actual), 96)
        self.assertEqual(len(self.probes(trace)), 1)
        self.assertEqual(self.legacy(trace), [])

    def test_every_scope_filters_before_the_97_row_limit(self):
        self.seed(240)
        cases = [
            {"where": " AND p.project_id=?", "values": ["kept"]},
            {"where": " AND p.chapter_id=?", "values": ["c1"]},
            {"where": " AND s.external_id=?", "values": ["external-2"], "session": True},
            {"where": " AND p.project_id=? AND p.chapter_id=? AND s.external_id=?",
             "values": ["kept", "c1", "external-2"], "session": True},
            {"where": " AND p.project_id=?", "values": ["missing"]},
        ]
        for table in TABLES:
            for options in cases:
                with self.subTest(table=table, options=options):
                    sql, parameters = self.statement(table, **options)
                    actual, _, trace = self.traced(sql, parameters, table)
                    self.assertEqual(actual, self.expected(sql, parameters))
                    self.assertEqual(len(self.probes(trace)), 1)
        sql, parameters = self.statement(where=" AND p.project_id=?", values=["kept"])
        actual, _ = self.invoke(sql, parameters)
        self.assertEqual(len(actual), 96)
        self.assertTrue(all(row[0] <= 120 for row in actual))

    def test_rowid_bounds_interleaving_and_empty_bounds_keep_global_scores(self):
        self.seed(240)
        self.db.execute("UPDATE pages SET project_id=CASE WHEN rid%2=0 THEN 'even' ELSE 'odd' END")
        for table in TABLES:
            for bounds in ((1, 240), (17, 219), (0, -1)):
                with self.subTest(table=table, bounds=bounds):
                    sql, parameters = self.statement(
                        table, where=" AND p.project_id=?", values=["even"], bounds=bounds)
                    actual, _ = self.invoke(sql, parameters, table)
                    self.assertEqual(actual, self.expected(sql, parameters))

    def test_actual_plan_uses_hidden_rank_inside_a_bounded_outer_sort(self):
        self.seed(130)
        sql, parameters = self.statement()
        _, _, trace = self.traced(sql, parameters)
        probe = self.probes(trace)[0]
        self.assertIn("pages_fts.rank AS rank", probe)
        self.assertIn("pages_fts.rank MATCH 'bm25(2.0,2.0,1.0,0.25)'", probe)
        self.assertIn("ORDER BY pages_fts.rank LIMIT 97", probe)
        self.assertIn("CROSS JOIN pages p", probe)
        plan = [row[3] for row in self.db.execute("EXPLAIN QUERY PLAN " + probe)]
        print("J invented EXPLAIN:", plan)
        self.assertTrue(any("ranked_route" in value for value in plan), plan)
        fts_plans = [value for value in plan if "VIRTUAL TABLE INDEX" in value]
        self.assertEqual(len(fts_plans), 1, plan)
        # FTS5_BI_ORDER_RANK is bit32 in the inspected FTS5 planner. Retain the
        # raw plan in CI and fail if a supported build chooses another route.
        index_number = int(fts_plans[0].split("VIRTUAL TABLE INDEX ", 1)[1].split(":", 1)[0])
        self.assertTrue(index_number & 32, plan)
        self.assertTrue(any("TEMP B-TREE FOR ORDER BY" in value for value in plan), plan)

    def test_closed_probe_cursor_restores_real_rows_for_later_fallback(self):
        self.seed(130)
        sql, parameters = self.statement()
        actual, cursor = self.invoke(sql, parameters)
        self.assertIsNotNone(cursor)
        restored = store._restore_candidate_rows(actual, cursor)
        self.assertTrue(all(type(row) is sqlite3.Row for row in restored))
        self.assertEqual(tuples(restored), self.expected(sql, parameters))
        self.assertEqual(restored[0]["id"], actual[0][1])
        with self.assertRaises(sqlite3.ProgrammingError):
            cursor.execute("SELECT 1")
        self.assertEqual(self.db.execute("SELECT 1").fetchone()[0], 1)
        self.assertIs(self.db.row_factory, sqlite3.Row)

    def test_custom_row_text_and_connection_factories_keep_the_old_query(self):
        self.seed(130)
        sql, parameters = self.statement()
        for factory in (lambda cursor, values: sqlite3.Row(cursor, values), None):
            with self.subTest(row_factory=factory):
                self.db.row_factory = factory
                actual, _, trace = self.traced(sql, parameters)
                self.assertEqual(actual, self.expected(sql, parameters))
                self.assertEqual(self.probes(trace), [])
                self.assertEqual(len(self.legacy(trace)), 1)
        self.db.row_factory = sqlite3.Row
        self.db.text_factory = bytes
        actual, _, trace = self.traced(sql, parameters)
        self.assertEqual(actual, self.expected(sql, parameters))
        self.assertEqual(self.probes(trace), [])
        self.db.text_factory = str

        class Wrapper:
            def __init__(self, db):
                self.db, self.calls = db, []
            def execute(self, statement, values):
                self.calls.append(statement)
                return self.db.execute(statement, values)

        wrapper = Wrapper(self.db)
        rows, _ = store._ranked_candidate_rows(wrapper, sql, parameters, "pages_fts", wrapper)
        self.assertEqual(tuples(rows), self.expected(sql, parameters))
        self.assertEqual(wrapper.calls, [sql])

    def test_changed_public_row_alias_keeps_the_old_query(self):
        self.seed(130)
        sql, parameters = self.statement()
        expected = self.expected(sql, parameters)
        with patch.object(sqlite3, "Row", object):
            actual, _, trace = self.traced(sql, parameters)
        self.assertEqual(actual, expected)
        self.assertEqual(self.probes(trace), [])
        self.assertEqual(len(self.legacy(trace)), 1)

    def test_custom_parameter_adapter_is_bound_only_once(self):
        self.seed(130)
        sql, parameters = self.statement()
        expected = self.expected(sql, parameters)
        key = (str, sqlite3.PrepareProtocol)
        missing = object()
        previous = sqlite3.adapters.get(key, missing)
        calls = []
        sqlite3.register_adapter(str, lambda value: calls.append(value) or value)
        try:
            actual, _, trace = self.traced(sql, parameters)
        finally:
            if previous is missing:
                sqlite3.adapters.pop(key, None)
            else:
                sqlite3.adapters[key] = previous
        self.assertEqual(actual, expected)
        self.assertEqual(calls, [EXPRESSION])
        self.assertEqual(self.probes(trace), [])
        self.assertEqual(len(self.legacy(trace)), 1)

    def test_invalid_utf8_only_in_lookahead_keeps_the_original_success(self):
        self.seed(97)
        # rid1 has the worst unique rank; only the new lookahead sees its ID.
        self.db.execute("UPDATE pages SET id=CAST(x'80' AS TEXT) WHERE rid=1")
        sql, parameters = self.statement()
        expected = self.expected(sql, parameters)
        actual, _, trace = self.traced(sql, parameters)
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 96)
        self.assertEqual(len(self.probes(trace)), 1)
        self.assertEqual(len(self.legacy(trace)), 1)
        self.assertEqual(self.db.execute("SELECT 1").fetchone()[0], 1)

    def test_invalid_utf8_in_selected_ids_keeps_the_original_error(self):
        self.seed(97)
        self.db.execute("UPDATE pages SET id=CAST(x'80' AS TEXT) WHERE rid=97")
        sql, parameters = self.statement()
        with self.assertRaises(sqlite3.OperationalError) as old:
            self.expected(sql, parameters)
        with self.assertRaises(sqlite3.OperationalError) as new:
            self.invoke(sql, parameters)
        self.assertEqual(new.exception.args, old.exception.args)
        self.assertIn("Could not decode to UTF-8 column 'id'", str(new.exception))
        self.assertEqual(self.db.execute("SELECT 1").fetchone()[0], 1)

    def test_nontext_ids_and_uncertified_rank_or_shape_use_the_old_query(self):
        self.seed(97)
        sql, parameters = self.statement()
        self.db.execute("UPDATE pages SET id=x'80' WHERE rid=1")
        actual, _, trace = self.traced(sql, parameters)
        self.assertEqual(actual, self.expected(sql, parameters))
        self.assertEqual(len(self.legacy(trace)), 1)
        self.seed(97)
        original = store._candidate_rows
        for bad in ((97, "page-0001", math.inf), (97, "page-0001", math.nan),
                    (97, "page-0001", "rank"), (97, "page-0001", -1.0, "extra")):
            with self.subTest(bad=bad):
                calls = []
                def altered(cursor, description, connection=None):
                    rows, retained = original(cursor, description, connection)
                    calls.append(cursor)
                    if len(calls) == 1:
                        rows[0] = bad
                    return rows, retained
                # Fault injection deliberately certifies this mock as the reader
                # so impossible native shapes exercise the separate value guard.
                with patch.object(store, "_candidate_rows", side_effect=altered) as reader:
                    with patch.object(store, "_ORDINARY_CANDIDATE_ROWS", reader):
                        actual, _ = self.invoke(sql, parameters)
                self.assertEqual(actual, self.expected(sql, parameters))
                self.assertEqual(len(calls), 2)
                with self.assertRaises(sqlite3.ProgrammingError):
                    calls[0].execute("SELECT 1")

    def test_explicit_weights_ignore_a_changed_persistent_rank_default(self):
        self.seed(130)
        for table in TABLES:
            sql, parameters = self.statement(table)
            expected = self.expected(sql, parameters)
            self.db.execute(f"INSERT INTO {table}({table},rank) VALUES('rank','bm25(9.0,0.0,0.0,1.0)')")
            actual, _ = self.invoke(sql, parameters, table)
            self.assertEqual(actual, expected)

    def test_registered_scalar_bm25_mechanism_preserves_original_outcome(self):
        self.seed(130)
        sql, parameters = self.statement()
        for arity in (5, -1):
            calls = []
            self.db.create_function("bm25", arity, lambda *values: calls.append(values) or 123.0)
            expected = self.expected(sql, parameters)
            old_calls = len(calls)
            calls.clear()
            actual, _ = self.invoke(sql, parameters)
            self.assertEqual(actual, expected)
            self.assertEqual(len(calls), old_calls)
            print("J invented scalar bm25 arity/calls:", arity, old_calls)

    def test_sqlite_errors_are_not_swallowed_or_replayed(self):
        self.seed(130)
        sql, parameters = self.statement()
        original = store._candidate_rows
        errors = (sqlite3.OperationalError("interrupted"),
                  sqlite3.DatabaseError("not authorized"),
                  sqlite3.DatabaseError("database disk image is malformed"))
        for error in errors:
            with self.subTest(error=str(error)):
                cursors = []
                def fail(cursor, description, connection=None):
                    cursors.append(cursor)
                    raise error
                with patch.object(store, "_candidate_rows", side_effect=fail) as reader:
                    with patch.object(store, "_ORDINARY_CANDIDATE_ROWS", reader):
                        with self.assertRaises(type(error)) as caught:
                            self.invoke(sql, parameters)
                self.assertIs(caught.exception, error)
                self.assertEqual(len(cursors), 1)
                with self.assertRaises(sqlite3.ProgrammingError):
                    cursors[0].execute("SELECT 1")
                self.assertEqual(self.db.execute("SELECT 1").fetchone()[0], 1)

    def test_unrecognized_statement_shape_uses_the_legacy_reader(self):
        self.seed(130)
        sql, parameters = self.statement()
        sql = sql.replace("LIMIT 96", "LIMIT 95")
        actual, _, trace = self.traced(sql, parameters)
        self.assertEqual(actual, self.expected(sql, parameters))
        self.assertEqual(len(actual), 95)
        self.assertEqual(self.probes(trace), [])


class RankedRouteMemoryBookTests(unittest.TestCase):
    def test_default_and_optional_paths_keep_complete_payloads_and_provenance(self):
        with MemoryBook(":memory:", segmentation="turn", min_page_chars=0, cache_size=0) as book:
            for identity, title, content in (
                ("anchor", "Calibration memo",
                 "quartzsignal points to Cedar Observatory. quartzsignal is recorded here."),
                ("target", "Cedar Observatory", "The instruments stand beside the northern inlet."),
            ):
                book.ingest({"project": "lab", "session_id": identity, "title": title,
                             "task_id": "archive", "created_at": "2025-01-01T00:00:00Z",
                             "messages": [{"role": "user", "content": content}]})
            native_reader = store._candidate_rows
            def legacy(db, statement, parameters, table, connection=None):
                return native_reader(db.execute(statement, parameters),
                                     store._STEM_ROUTE_DESCRIPTION, connection)
            for options in ({}, {"follow_titles": False}, {"follow_titles": True},
                            {"follow_titles": True, "limit": 1}, {"coverage": True},
                            {"strategy": "flat"}, {"session": "anchor"}):
                with self.subTest(options=options):
                    arguments = {"project": "lab", "budget_chars": 2000, "use_cache": False}
                    arguments.update(options)
                    with patch.object(store, "_ranked_candidate_rows", side_effect=legacy):
                        expected = book.recall("quartzsignal", **arguments)
                    with patch.object(store, "_ranked_candidate_rows",
                                      wraps=store._ranked_candidate_rows) as mechanism:
                        actual = book.recall("quartzsignal", **arguments)
                    self.assertEqual(without_timing(actual), without_timing(expected))
                    if options.get("coverage") or options.get("strategy") == "flat" or (
                            options.get("follow_titles") and options.get("limit") != 1):
                        self.assertEqual(mechanism.call_count, 0)
                    else:
                        self.assertEqual(mechanism.call_count, 2)
                    if options.get("follow_titles") and options.get("limit") != 1:
                        self.assertTrue(actual["title_reference"]["applied"])
                        self.assertIn("northern inlet", actual["context"])


if __name__ == "__main__":
    unittest.main()
