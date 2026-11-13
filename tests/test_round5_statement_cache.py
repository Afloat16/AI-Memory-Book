"""Invented SQL verifies preparation reuse without caching query results."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_book import MemoryBook, store


class StatementCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'book.db'

    @staticmethod
    def invented_working_set(connection):
        prepared = []

        def authorize(action, first, second, database, trigger):
            if action == sqlite3.SQLITE_SELECT:
                prepared.append(action)
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorize)
        try:
            observations = []
            for repetition in range(2):
                for identity in range(200):
                    statement = 'SELECT ? AS current_value /* invented-' + str(identity) + ' */'
                    value = identity + 1000 * repetition
                    if connection.execute(statement, (value,)).fetchone()[0] != value:
                        raise AssertionError('Prepared statement reused stale bound values')
                observations.append(len(prepared))
            return observations
        finally:
            # Python 3.10 cannot disable the authorizer with None.
            # Stop recording preparations while allowing later fixture queries.
            connection.set_authorizer(lambda *args: sqlite3.SQLITE_OK)

    def test_preparation_reuse_with_new_parameters_and_capacity_limited_control(self):
        with MemoryBook(self.path, cache_size=0) as book:
            actual = self.invented_working_set(book.db)
            self.assertEqual(actual, [200, 200])
            self.assertEqual(book.db.execute('SELECT COUNT(*) FROM recall_cache').fetchone()[0], 0)
        # A five-entry control cannot retain this 200-statement working set.
        # Assert re-preparation without assuming a version-specific eviction
        # count: Python 3.10 clamps capacities below five and uses LFU.
        with sqlite3.connect(':memory:', cached_statements=5) as limited_control:
            control = self.invented_working_set(limited_control)
            self.assertEqual(control[0], 200)
            self.assertGreater(control[1], control[0])

    def test_cached_statement_preserves_snapshot_and_external_commits(self):
        with MemoryBook(self.path, cache_size=0) as book:
            book.db.execute('CREATE TABLE statement_fixture(value INTEGER)')
            book.db.execute('INSERT INTO statement_fixture VALUES(1)')
            sql = 'SELECT value FROM statement_fixture'
            book.db.execute('BEGIN')
            self.assertEqual(book.db.execute(sql).fetchone()[0], 1)
            with sqlite3.connect(self.path, isolation_level=None) as writer:
                writer.execute('UPDATE statement_fixture SET value=2')
            self.assertEqual(book.db.execute(sql).fetchone()[0], 1)
            book.db.execute('COMMIT')
            self.assertEqual(book.db.execute(sql).fetchone()[0], 2)
            book.db.execute('BEGIN')
            book.db.execute('UPDATE statement_fixture SET value=3')
            self.assertEqual(book.db.execute(sql).fetchone()[0], 3)
            book.db.execute('ROLLBACK')
            self.assertEqual(book.db.execute(sql).fetchone()[0], 2)

    def test_schema_changes_invalidate_prepared_results(self):
        with MemoryBook(self.path, cache_size=0) as book:
            book.db.execute('CREATE TABLE statement_fixture(value INTEGER)')
            book.db.execute('INSERT INTO statement_fixture VALUES(7)')
            self.assertEqual(tuple(book.db.execute('SELECT * FROM statement_fixture').fetchone()), (7,))
            book.db.execute("ALTER TABLE statement_fixture ADD COLUMN marker TEXT DEFAULT 'new'")
            self.assertEqual(tuple(book.db.execute('SELECT * FROM statement_fixture').fetchone()), (7, 'new'))

    def test_custom_connect_receives_only_historical_arguments(self):
        original = sqlite3.connect
        observed = []

        def replacement(database, *, timeout, isolation_level):
            observed.append((database, timeout, isolation_level))
            return original(database, timeout=timeout, isolation_level=isolation_level)

        with patch.object(sqlite3, 'connect', replacement):
            with MemoryBook(self.path, cache_size=0) as book:
                self.assertIsNone(book._native_db)
                self.assertEqual(book.db.execute('SELECT 8').fetchone()[0], 8)
        self.assertEqual(observed, [(str(self.path), 10, None)])

    def test_native_certificate_and_pager_target_are_preserved(self):
        with sqlite3.connect(':memory:') as ordinary:
            expected_pager = ordinary.execute('PRAGMA main.cache_size').fetchone()[0]
        with MemoryBook(self.path, cache_size=0) as book:
            self.assertIs(book._native_db, book.db)
            self.assertIs(type(book.db), store._NATIVE_CONNECTION)
            self.assertIs(book.db.row_factory, sqlite3.Row)
            self.assertEqual(book.db.execute('PRAGMA main.cache_size').fetchone()[0], expected_pager)
            self.assertEqual(book.db.execute('PRAGMA foreign_keys').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
