"""Independent boundary cases for dense ranking's ordinary-SQL certificate."""

from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from memory_book import MemoryBook, store
from tests.test_round6_dense_rank import new_book, populate, stable


class _AfterCloseCursor:
    """Inject a change between the real rank cursor and metadata SQL."""

    def __init__(self, cursor, callback):
        self.cursor, self.callback = cursor, callback
        self.rows = 0

    def __iter__(self):
        return self

    def __next__(self):
        row = next(self.cursor)
        self.rows += 1
        return row

    def close(self):
        self.cursor.close()
        self.callback(self.rows)


@contextmanager
def after_first_rank(book, callback):
    """Do not install SQLite callbacks: those invalidate the initial guard."""
    execute = store._RecallConnection.execute
    statements, rank_statements = [], []

    def observed(connection, statement, *args, **kwargs):
        cursor = execute(connection, statement, *args, **kwargs)
        if connection is book.db:
            statements.append(statement)
            if statement.lstrip().startswith("SELECT rowid,rank FROM "):
                rank_statements.append(statement)
                if len(rank_statements) == 1:
                    return _AfterCloseCursor(cursor, callback)
        return cursor

    with patch.object(store._RecallConnection, "execute", new=observed):
        yield statements, rank_statements


@unittest.skipUnless(hasattr(sqlite3.Connection, "getlimit"),
                     "Python 3.10 retains the original candidate SQL")
class DenseRankIndependentGuards(unittest.TestCase):
    def setUp(self):
        self.book = new_book()
        self.addCleanup(self.book.close)
        populate(self.book)

    def certificate(self, book):
        book.db.execute("BEGIN")
        try:
            return book._dense_project_rank("target", book._project_rowid_bounds("target"))
        finally:
            book.db.execute("ROLLBACK")

    def assert_dense_baseline(self, book):
        self.assertTrue(self.certificate(book))
        routes = []
        original = book._dense_rank_route

        def observed(*args):
            result = original(*args)
            routes.append(result)
            return result

        with patch.object(book, "_dense_rank_route", side_effect=observed):
            result = stable(book, project="target")
        self.assertEqual(len(routes), 2)
        self.assertTrue(all(route is not None and len(route) == 96 for route in routes))
        self.assertFalse(book.db.in_transaction)
        return result

    def assert_original_route(self, book):
        self.assertFalse(self.certificate(book))
        with patch.object(book, "_dense_rank_route", wraps=book._dense_rank_route) as route:
            actual = stable(book, project="target")
            route.assert_not_called()
        with patch.object(book, "_dense_project_rank", return_value=False):
            expected = stable(book, project="target")
        self.assertEqual(actual, expected)
        self.assertFalse(book.db.in_transaction)
        return actual

    def test_adapter_registered_after_first_rank_stops_rebinding_and_later_rank_routes(self):
        for kind in (int, float, str):
            with self.subTest(adapter=kind.__name__):
                before = self.assert_dense_baseline(self.book)
                registry = dict(sqlite3.adapters)
                key = (kind, sqlite3.PrepareProtocol)
                changed = []

                def register_after_rank(rows):
                    self.assertEqual(rows, 132)
                    self.assertTrue(self.book.db.in_transaction)
                    self.assertTrue(self.book.db._rank_ordinary)
                    sqlite3.register_adapter(kind, lambda value: value)
                    changed.append(rows)

                try:
                    with after_first_rank(self.book, register_after_rank) as (statements, ranks):
                        actual = stable(self.book, project="target")
                    self.assertEqual(changed, [132])
                    self.assertEqual(len(ranks), 1)
                    self.assertFalse(any(sql.startswith("WITH scored(rid,rank)")
                                         for sql in statements))
                    self.assertEqual(actual, before)
                    self.assertEqual(self.assert_original_route(self.book), before)
                finally:
                    if key in registry:
                        sqlite3.adapters[key] = registry[key]
                    else:
                        sqlite3.adapters.pop(key, None)
                self.assertEqual(sqlite3.adapters, registry)
                self.assertTrue(self.certificate(self.book))

    def test_integer_primary_key_desc_is_not_a_rowid_alias(self):
        before = self.assert_dense_baseline(self.book)
        db = self.book.db
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("ALTER TABLE pages RENAME TO previous_pages")
        schema = store._DENSE_RANK_SCHEMAS[0].replace(
            "rid INTEGER PRIMARY KEY", "rid INTEGER PRIMARY KEY DESC")
        db.execute(schema)
        db.execute("INSERT INTO pages SELECT * FROM previous_pages")
        db.execute("DROP TABLE previous_pages")
        db.execute(store.RECALL_METADATA_INDEX_SQL)
        db.execute("UPDATE pages SET rowid=rowid+10000 WHERE project_id='target'")
        count, lo, hi, independent = db.execute("""SELECT COUNT(*),MIN(rid),MAX(rid),
            SUM(rowid != rid) FROM pages WHERE project_id='target'""").fetchone()
        self.assertEqual((count, hi - lo + 1, independent), (132, 132, 132))
        self.assertIn("INTEGER PRIMARY KEY DESC", db.execute(
            "SELECT sql FROM sqlite_master WHERE name='pages'").fetchone()[0])
        self.assertEqual(self.assert_original_route(self.book), before)

    def test_each_real_fts_tokenizer_schema_change_disables_dense_ranking(self):
        for table, index in (("pages_fts", 1), ("pages_stem_fts", 2)):
            with self.subTest(table=table), new_book() as book:
                populate(book)
                before = self.assert_dense_baseline(book)
                rows = [tuple(row) for row in book.db.execute(
                    f"SELECT rowid,title,question,body,directory FROM {table}")]
                book.db.execute(f"DROP TABLE {table}")
                schema = store._DENSE_RANK_SCHEMAS[index].replace(
                    "unicode61", "unicode61 remove_diacritics 0")
                book.db.execute(schema)
                book.db.executemany(f"INSERT INTO {table}(rowid,title,question,body,directory) "
                                    "VALUES(?,?,?,?,?)", rows)
                self.assertIn("remove_diacritics 0", book.db.execute(
                    "SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0])
                self.assertEqual([tuple(row) for row in book.db.execute(
                    f"SELECT rowid,title,question,body,directory FROM {table}")], rows)
                self.assertEqual(self.assert_original_route(book), before)

    def test_external_plain_and_custom_connection_factories_keep_original_call_shape(self):
        class CustomConnection(sqlite3.Connection):
            pass

        class RecallSubclass(store._RecallConnection):
            pass

        connect = sqlite3.connect
        for factory in (sqlite3.Connection, CustomConnection, RecallSubclass):
            with self.subTest(factory=factory.__name__):
                self.assert_dense_baseline(self.book)
                calls = []

                def external_connector(*args, **kwargs):
                    calls.append((args, dict(kwargs)))
                    return connect(*args, factory=factory, **kwargs)

                with patch.object(sqlite3, "connect", side_effect=external_connector):
                    book = new_book()
                self.addCleanup(book.close)
                self.assertEqual(calls, [((":memory:",), {"timeout": 10, "isolation_level": None})])
                self.assertIs(type(book.db), factory)
                self.book.db.backup(book.db)
                self.assertEqual(tuple(book.db.execute(
                    "SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0]
                    for name in ("pages", "pages_fts", "pages_stem_fts")), store._DENSE_RANK_SCHEMAS)
                self.assert_original_route(book)

    def test_other_connection_commit_between_rank_and_metadata_keeps_one_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.db"
            with MemoryBook(path, cache_size=0, segmentation="turn",
                            max_page_chars=900, min_page_chars=0) as book:
                populate(book)
                before = self.assert_dense_baseline(book)
                self.assertEqual(book.db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                victim = before["results"][0]["id"]
                with closing(sqlite3.connect(path, isolation_level=None)) as writer:
                    changed = []

                    def delete_after_rank(rows):
                        self.assertEqual(rows, 132)
                        self.assertTrue(book.db.in_transaction)
                        writer.execute("DELETE FROM pages WHERE id=?", (victim,))
                        self.assertEqual(writer.execute(
                            "SELECT COUNT(*) FROM pages WHERE id=?", (victim,)).fetchone()[0], 0)
                        changed.append(victim)

                    with after_first_rank(book, delete_after_rank) as (statements, ranks):
                        actual = stable(book, project="target")
                    self.assertEqual(changed, [victim])
                    self.assertEqual(len(ranks), 2)
                    self.assertEqual(sum(sql.startswith("WITH scored(rid,rank)")
                                         for sql in statements), 2)
                    self.assertEqual(actual, before)
                    self.assertFalse(book.db.in_transaction)
                    self.assertEqual(book.db.execute(
                        "SELECT COUNT(*) FROM pages WHERE id=?", (victim,)).fetchone()[0], 0)
                    after = stable(book, project="target")
                    with patch.object(book, "_dense_project_rank", return_value=False):
                        expected_after = stable(book, project="target")
                    self.assertEqual(after, expected_after)
                    self.assertNotEqual(after, before)
                    self.assertNotIn(victim, [row["id"] for row in after["results"]])


if __name__ == "__main__":
    unittest.main()
