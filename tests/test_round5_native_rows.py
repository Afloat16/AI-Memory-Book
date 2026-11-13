"""Real-cursor regressions for bounded tuple reads and mapping restoration."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store


class RowLike:
    def __init__(self, cursor, values):
        self.names = tuple(field[0] for field in cursor.description)
        self.values = values

    def keys(self):
        return self.names

    def __getitem__(self, key):
        return self.values[key if isinstance(key, int) else self.names.index(key)]


def stable(response):
    return {key: value for key, value in response.items() if key != "latency_ms"}


class NativeCursorTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row

    def test_native_rows_restore_the_actual_ordered_mapping(self):
        cursor = self.db.execute("SELECT 7 AS rid, 'page-one' AS id, -2.5 AS rank")
        rows, certified = store._candidate_rows(cursor, store._STEM_ROUTE_DESCRIPTION, self.db)
        self.assertIs(certified, cursor)
        self.assertIs(type(rows[0]), tuple)
        self.assertEqual(rows, [(7, "page-one", -2.5)])
        restored = store._restore_candidate_rows(rows, certified)
        self.assertIs(type(restored[0]), sqlite3.Row)
        self.assertEqual(restored[0].keys(), ["rid", "id", "rank"])
        self.assertEqual(dict(restored[0]), {"rid": 7, "id": "page-one", "rank": -2.5})
        self.assertIs(cursor.row_factory, sqlite3.Row)
        self.assertIs(self.db.row_factory, sqlite3.Row)
        self.assertIs(type(self.db.execute("SELECT 1").fetchone()), sqlite3.Row)

    def test_duplicate_extra_missing_reordered_and_empty_shapes_keep_rows(self):
        statements = (
            "SELECT 7 AS rid, 'page-one' AS id, -2.5 AS rank, -9 AS rank",
            "SELECT 7 AS rid, 'page-one' AS id, -2.5 AS rank, 9 AS extra",
            "SELECT 7 AS rid, 'page-one' AS id",
            "SELECT 'page-one' AS id, 7 AS rid, -2.5 AS rank",
            "SELECT 7 AS rid, 'page-one' AS id, -2.5 AS rank, 9 AS extra WHERE 0",
        )
        for statement in statements:
            with self.subTest(statement=statement):
                expected = self.db.execute(statement).fetchall()
                cursor = self.db.execute(statement)
                actual, certified = store._candidate_rows(cursor, store._STEM_ROUTE_DESCRIPTION, self.db)
                self.assertIsNone(certified)
                self.assertEqual(actual, expected)
                self.assertIs(cursor.row_factory, sqlite3.Row)

    def test_custom_cursor_observes_its_original_factory(self):
        observed = []

        class Cursor(sqlite3.Cursor):
            def fetchall(self):
                observed.append(self.row_factory)
                return super().fetchall()

        cursor = self.db.cursor(factory=Cursor).execute("SELECT 7 AS rid, 'p' AS id, -1 AS rank")
        rows, certified = store._candidate_rows(cursor, store._STEM_ROUTE_DESCRIPTION, self.db)
        self.assertIsNone(certified)
        self.assertEqual(observed, [sqlite3.Row])
        self.assertIs(type(rows[0]), sqlite3.Row)

    def test_custom_text_factory_observes_its_original_cursor_factory(self):
        seen = []
        cursor = None

        def decode(value):
            seen.append(cursor.row_factory)
            return value.decode()

        self.db.text_factory = decode
        cursor = self.db.execute("SELECT 7 AS rid, 'page-one' AS id, -1 AS rank")
        rows, certified = store._candidate_rows(cursor, store._STEM_ROUTE_DESCRIPTION, self.db)
        self.assertIsNone(certified)
        self.assertEqual(seen, [sqlite3.Row])
        self.assertEqual(rows[0]["id"], "page-one")

    def test_custom_row_factory_and_subclass_are_not_bypassed(self):
        seen = []

        class Row(sqlite3.Row):
            def __getitem__(self, key):
                value = super().__getitem__(key)
                return value * 3 if key == "rank" else value

        def factory(cursor, values):
            seen.append(tuple(values))
            return Row(cursor, values)

        for selected in (Row, factory):
            with self.subTest(factory=selected):
                cursor = self.db.execute("SELECT 7 AS rid, 'page-one' AS id, -1 AS rank")
                cursor.row_factory = selected
                rows, certified = store._candidate_rows(cursor, store._STEM_ROUTE_DESCRIPTION, self.db)
                self.assertIsNone(certified)
                self.assertEqual(rows[0]["rank"], -3)
                self.assertIs(cursor.row_factory, selected)
        self.assertEqual(seen, [(7, "page-one", -1)])

    def test_interrupted_native_fetch_restores_cursor_and_connection(self):
        cursor = self.db.execute("""WITH RECURSIVE numbers(n) AS (
            SELECT 1 UNION ALL SELECT n+1 FROM numbers WHERE n<100
            ) SELECT n AS rid, 'page-'||n AS id, -n AS rank FROM numbers""")
        self.db.set_progress_handler(lambda: 1, 1)
        try:
            with self.assertRaisesRegex(sqlite3.OperationalError, "interrupted"):
                store._candidate_rows(cursor, store._STEM_ROUTE_DESCRIPTION, self.db)
        finally:
            self.db.set_progress_handler(None, 0)
        self.assertIs(cursor.row_factory, sqlite3.Row)
        self.assertIs(self.db.row_factory, sqlite3.Row)
        self.assertEqual(self.db.execute("SELECT 11 AS value").fetchone()["value"], 11)


class RecallFactoryTransitionTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryBook(":memory:", segmentation="turn", max_page_chars=3000,
                               min_page_chars=0, cache_size=0)
        self.addCleanup(self.book.close)
        for number, word in enumerate(("orbiting", "orbits", "orbit")):
            self.book.ingest({"project": "lab", "session_id": str(number),
                "task_id": "archive", "task_title": "Flight observations", "title": "Relay notes",
                "created_at": "2025-01-01T00:00:00Z",
                "messages": [{"role": "assistant", "content":
                    f"The relay is {word} the moon. Calibration is stable. 缓存有效期是四十秒。"}]})

    def recall(self, **options):
        return self.book.recall("orbiting relay", project="lab", budget_chars=100000,
                                use_cache=False, **options)

    def test_real_recall_uses_tuples_without_changing_sources_or_connection_factory(self):
        ordinary = store._candidate_rows
        seen = []

        def watch(cursor, description, connection=None):
            rows, native = ordinary(cursor, description, connection)
            seen.append((description, native is not None, [type(row) for row in rows]))
            return rows, native

        with patch.object(store, "_candidate_rows", lambda cursor, *args: (cursor.fetchall(), None)):
            expected = stable(self.recall())
        with patch.object(store, "_candidate_rows", watch):
            result = stable(self.recall())
        self.assertEqual(result, expected)
        self.assertEqual(len(seen), 3)
        self.assertTrue(all(native and all(kind is tuple for kind in kinds)
                            for _, native, kinds in seen))
        self.assertIs(self.book.db.row_factory, sqlite3.Row)
        for hit in result["results"]:
            self.assertIsInstance(self.book.read(hit["id"])["source_refs"], list)

    def _transition(self, boundary, *, fail_metadata=False, disable_native=False):
        ordinary = store._candidate_rows
        route_count, native_reads, statements = 0, [], []

        def factory(cursor, values):
            if fail_metadata and tuple(column[0] for column in cursor.description) == tuple(
                    column[0] for column in store._DIRECTORY_DESCRIPTION):
                values = ("missing-metadata-page", *values[1:])
            return RowLike(cursor, values)

        def trace(statement):
            nonlocal route_count
            # FTS emits additional internal data_version reads on first use;
            # compare the actual application queries and transaction order.
            if not statement.startswith("--"):
                statements.append(statement)
            if statement.startswith("SELECT p.rid,p.id,bm25("):
                route_count += 1
                if route_count == (1 if boundary == "route" else 2):
                    # This cursor already captured Row; only the next query
                    # sees the custom factory. At least one route is native.
                    self.book.db.row_factory = factory

        def watch(cursor, description, connection=None):
            result = (cursor.fetchall(), None) if disable_native else ordinary(cursor, description, connection)
            native_reads.append(result[1] is not None)
            return result

        self.book.db.set_trace_callback(trace)
        try:
            with patch.object(store, "_candidate_rows", watch):
                try:
                    result = stable(self.recall())
                except Exception as error:
                    result = (type(error), str(error))
            return result, native_reads, statements
        finally:
            self.book.db.set_trace_callback(None)
            self.book.db.row_factory = sqlite3.Row

    def test_mixed_native_and_custom_routes_restore_mapping_before_fallback(self):
        expected, _, old_sql = self._transition("route", disable_native=True)
        actual, native, new_sql = self._transition("route")
        self.assertEqual(actual, expected)
        self.assertEqual(new_sql, old_sql)
        self.assertEqual(native, [True, False, False])
        self.assertFalse(self.book.db.in_transaction)

    def test_native_routes_with_custom_metadata_restore_mapping_before_merge(self):
        expected, _, old_sql = self._transition("metadata", disable_native=True)
        actual, native, new_sql = self._transition("metadata")
        self.assertEqual(actual, expected)
        self.assertEqual(new_sql, old_sql)
        self.assertEqual(native, [True, True, False])

    def test_metadata_failure_keeps_error_order_and_rolls_back_native_snapshot(self):
        expected, _, old_sql = self._transition("metadata", fail_metadata=True, disable_native=True)
        actual, native, new_sql = self._transition("metadata", fail_metadata=True)
        self.assertEqual(actual, (KeyError, "'missing-metadata-page'"))
        self.assertEqual(actual, expected)
        self.assertEqual(new_sql, old_sql)
        self.assertEqual(native, [True, True, False])
        self.assertFalse(self.book.db.in_transaction)

    def test_custom_text_factory_does_not_get_a_native_certificate(self):
        observed = []
        ordinary = store._candidate_rows

        def watch(cursor, description, connection=None):
            result = ordinary(cursor, description, connection)
            observed.append(result[1])
            return result

        expected = stable(self.recall())
        self.book.db.text_factory = lambda value: value.decode("utf-8")
        try:
            with patch.object(store, "_candidate_rows", watch):
                actual = stable(self.recall())
        finally:
            self.book.db.text_factory = str
        self.assertEqual(actual, expected)
        self.assertEqual(observed, [None, None, None])

    def test_replaced_connection_and_wrapped_connect_never_inherit_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            with MemoryBook(path, cache_size=0) as book:
                book.ingest({"project": "lab", "session_id": "one",
                             "messages": [{"role": "user", "content": "Orbiting relay."}]})
                original = book.db
                replacement = sqlite3.connect(path, isolation_level=None, detect_types=sqlite3.PARSE_DECLTYPES)
                replacement.row_factory = sqlite3.Row
                book.db = replacement
                original.close()
                ordinary = store._candidate_rows
                observed = []

                def watch(cursor, description, connection=None):
                    result = ordinary(cursor, description, connection)
                    observed.append(result[1])
                    return result

                with patch.object(store, "_candidate_rows", watch):
                    self.assertTrue(book.recall("orbiting", use_cache=False)["results"])
                self.assertIsNone(book._native_db)
                self.assertTrue(observed)
                self.assertTrue(all(value is None for value in observed))
            connect = sqlite3.connect
            with patch.object(sqlite3, "connect", lambda *args, **kwargs: connect(*args, **kwargs)), \
                    MemoryBook(":memory:") as wrapped:
                self.assertIsNone(wrapped._native_db)
        self.book.close()
        self.assertIsNone(self.book._native_db)

    def test_public_sqlite_alias_replacements_before_import_keep_original_factories(self):
        script = r'''
import sqlite3
import sys
native_connect, native_row = sqlite3.connect, sqlite3.Row
mode = sys.argv[1]
if mode == "connect":
    def connect(*args, **kwargs):
        kwargs["detect_types"] = sqlite3.PARSE_DECLTYPES
        return native_connect(*args, **kwargs)
    sqlite3.connect = connect
else:
    def row(cursor, values):
        return native_row(cursor, values)
    sqlite3.Row = row
from memory_book import MemoryBook, store
with MemoryBook(":memory:", segmentation="turn", cache_size=0) as book:
    book.ingest({"project": "lab", "session_id": "one",
                 "messages": [{"role": "user", "content": "The relay is orbiting."}]})
    if mode == "connect":
        assert book._native_db is None, "An import-time connect wrapper is not a native constructor"
    original = store._candidate_rows
    certificates = []
    def watch(cursor, description, connection=None):
        rows, certificate = original(cursor, description, connection)
        certificates.append(certificate)
        return rows, certificate
    store._candidate_rows = watch
    assert book.recall("orbiting", project="lab", use_cache=False)["results"]
    assert certificates and all(item is None for item in certificates), "An import-time factory replacement was bypassed"
    assert book.db.row_factory is sqlite3.Row
'''
        for mode in ("connect", "row"):
            with self.subTest(mode=mode):
                child = subprocess.run([sys.executable, "-c", script, mode],
                                       capture_output=True, text=True)
                self.assertEqual(child.returncode, 0, child.stdout + child.stderr)


if __name__ == "__main__":
    unittest.main()
