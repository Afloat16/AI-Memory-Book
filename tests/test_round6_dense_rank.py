"""Dense-project FTS ranking keeps full ties, scope and native fallbacks."""
import importlib.util
import sqlite3
import unittest
from unittest.mock import patch

from memory_book import MemoryBook
from memory_book import store


def populate(book, target=132, outside=300, weaker_last=False):
    book.ingest({"project": "outside", "session_id": "other", "title": "Other records",
        "messages": [{"role": "user", "content": "Silver unrelated archive records."}
                     for _ in range(outside)]})
    remaining = target
    for session in range(3):
        count = remaining // (3 - session)
        remaining -= count
        messages = []
        for number in range(count):
            text = "Quartz pressure cedar budget evidence."
            if weaker_last and session == 2 and number == count - 1:
                text += " ordinary background" * 25
            messages.append({"role": "user", "content": text})
        book.ingest({"project": "target", "session_id": str(session), "task_id": "policy",
            "task_title": "Pressure policy", "title": "Pressure notes",
            "created_at": f"2026-11-{session + 1:02d}T00:00:00Z", "messages": messages})


def new_book():
    return MemoryBook(":memory:", cache_size=0, segmentation="turn",
                      max_page_chars=900, min_page_chars=0)


def stable(book, query="quartz pressure", **options):
    result = book.recall(query, use_cache=False, **options)
    result.pop("latency_ms")
    return result


@unittest.skipUnless(hasattr(sqlite3.Connection, "getlimit"),
                     "Python 3.10 retains the original candidate SQL")
class DenseRankTests(unittest.TestCase):
    def setUp(self):
        self.book = new_book()
        self.addCleanup(self.book.close)
        populate(self.book)

    def both(self, query="quartz pressure", *, book=None, **options):
        book = book or self.book
        routes = []
        original = book._dense_rank_route

        def observed(*args):
            value = original(*args)
            routes.append(value)
            return value

        with patch.object(book, "_dense_rank_route", side_effect=observed):
            actual = stable(book, query, **options)
        with patch.object(book, "_dense_project_rank", return_value=False):
            expected = stable(book, query, **options)
        self.assertEqual(actual, expected)
        self.assertFalse(book.db.in_transaction)
        return actual, routes

    def certificate(self):
        self.book.db.execute("BEGIN")
        try:
            bounds = self.book._project_rowid_bounds("target")
            return self.book._dense_project_rank("target", bounds)
        finally:
            self.book.db.execute("ROLLBACK")

    def test_actual_schema_certifies_dense_range_and_full_payload_without_source_changes(self):
        self.assertEqual(tuple(self.book.db.execute(
            "SELECT sql FROM main.sqlite_master WHERE name=?", (name,)).fetchone()[0]
            for name in ("pages", "pages_fts", "pages_stem_fts")), store._DENSE_RANK_SCHEMAS)
        self.assertTrue(self.certificate())
        names = ("meta", "projects", "chapters", "sessions", "turns", "sections", "pages",
                 "pages_fts", "pages_stem_fts", "recall_cache")
        before = {name: [tuple(row) for row in self.book.db.execute(f"SELECT * FROM {name}")]
                  for name in names}
        result, routes = self.both(project="target")
        self.assertEqual(len(routes), 2)
        self.assertTrue(all(route is not None and len(route) == 96 for route in routes))
        for route in routes:
            self.assertEqual([row["id"] for row in route], sorted(row["id"] for row in route))
        self.assertGreater(result["candidate_count"], len(result["results"]))
        self.assertEqual(before, {name: [tuple(row) for row in self.book.db.execute(f"SELECT * FROM {name}")]
                                  for name in names})

    def test_current_historical_queries_and_other_scopes_keep_complete_outputs(self):
        for query in ("quartz", "current quartz pressure", "previous current quartz pressure"):
            with self.subTest(query=query):
                _, routes = self.both(query, project="target")
                self.assertEqual(len(routes), 2)
        chapter = self.book.db.execute("SELECT id FROM chapters WHERE project_id='target'").fetchone()[0]
        for options in ({}, {"project": "absent"}, {"chapter": chapter}, {"session": "0"},
                        {"project": "target", "strategy": "flat"},
                        {"project": "target", "budget_chars": 0}):
            with self.subTest(options=options):
                _, routes = self.both(**options)
                self.assertEqual(routes, [])

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "Install .[tokens]")
    def test_token_encoders_and_caps_preserve_full_results(self):
        for tokenizer in ("cl100k_base", "o200k_base"):
            for cap in (0, 512, 1024, 2048):
                with self.subTest(tokenizer=tokenizer, cap=cap):
                    _, routes = self.both(project="target", budget_chars=8000,
                                          budget_tokens=cap, tokenizer=tokenizer)
                    self.assertEqual(len(routes), 2)

    def test_sparse_and_interleaved_projects_fall_back(self):
        rowid = self.book.db.execute(
            "SELECT rid FROM pages WHERE project_id='target' ORDER BY rid LIMIT 1 OFFSET 10").fetchone()[0]
        self.book.db.execute("UPDATE pages SET project_id='outside' WHERE rid=?", (rowid,))
        self.assertFalse(self.certificate())
        self.assertEqual(self.both(project="target")[1], [])
        self.book.db.execute("DELETE FROM pages WHERE rid=?", (rowid,))
        self.assertFalse(self.certificate())
        self.assertEqual(self.both(project="target")[1], [])

    def test_noncanonical_duplicate_rowids_cannot_fake_density(self):
        self.book.db.execute("PRAGMA foreign_keys=OFF")
        self.book.db.execute("ALTER TABLE pages RENAME TO previous_pages")
        self.book.db.execute(store._DENSE_RANK_SCHEMAS[0].replace("rid INTEGER PRIMARY KEY", "rid INTEGER"))
        self.book.db.execute("INSERT INTO pages SELECT * FROM previous_pages")
        self.book.db.execute("DROP TABLE previous_pages")
        self.book.db.execute(store.RECALL_METADATA_INDEX_SQL)
        rowid = self.book.db.execute(
            "SELECT MIN(rid) FROM pages WHERE project_id='target'").fetchone()[0]
        self.book.db.execute("UPDATE pages SET rid=? WHERE rid=?", (rowid + 1, rowid + 2))
        count, lo, hi = self.book.db.execute(
            "SELECT COUNT(*),MIN(rid),MAX(rid) FROM pages WHERE project_id='target'").fetchone()
        self.assertEqual(count, hi - lo + 1)
        self.assertFalse(self.certificate())
        self.assertEqual(self.both(project="target")[1], [])

    def test_mixed_case_temp_shadow_and_noncanonical_schema_keep_original_path(self):
        self.book.db.execute("CREATE TEMP VIEW PaGeS AS SELECT * FROM main.pages")
        self.assertFalse(self.certificate())
        errors = []
        for dense in (True, False):
            context = patch.object(self.book, "_dense_project_rank", wraps=self.book._dense_project_rank) if dense else \
                patch.object(self.book, "_dense_project_rank", return_value=False)
            with context, patch.object(self.book, "_dense_rank_route") as route:
                with self.assertRaises(sqlite3.OperationalError) as caught:
                    stable(self.book, project="target")
                errors.append(caught.exception.args)
                route.assert_not_called()
            self.assertFalse(self.book.db.in_transaction)
        self.assertEqual(errors[0], errors[1])
        self.book.db.execute("DROP VIEW temp.PaGeS")
        self.assertTrue(self.certificate())
        self.book.db.execute("ALTER TABLE pages ADD COLUMN extra TEXT")
        self.assertFalse(self.certificate())
        self.assertEqual(self.both(project="target")[1], [])

    def test_exact_tie_cap_and_strictly_worse_lookahead(self):
        for count, weaker, fallback in ((512, False, False), (513, False, True), (513, True, False)):
            with self.subTest(count=count, weaker_last=weaker), new_book() as book:
                populate(book, target=count, outside=600, weaker_last=weaker)
                _, routes = self.both(book=book, project="target")
                self.assertEqual(len(routes), 2)
                self.assertTrue(all((route is None) == fallback for route in routes))

    def test_unselected_invalid_utf8_identifier_is_not_decoded(self):
        rowid = self.book.db.execute(
            "SELECT MAX(rid) FROM pages WHERE project_id='target'").fetchone()[0]
        self.book.db.execute("UPDATE pages SET id=CAST(x'ff' AS TEXT) WHERE rid=?", (rowid,))
        _, routes = self.both(project="target")
        self.assertEqual(len(routes), 2)
        self.assertTrue(all(route is not None for route in routes))

    def test_explicit_weights_ignore_persistent_rank_mapping(self):
        for table in ("pages_fts", "pages_stem_fts"):
            self.book.db.execute(f"INSERT INTO {table}({table},rank) VALUES('rank','bm25(0.0,0.0,0.0,0.0)')")
        _, routes = self.both(project="target")
        self.assertEqual(len(routes), 2)
        self.assertTrue(all(row["rank"] < 0 for route in routes for row in route))

    def test_scope_excludes_corrupt_outside_docsize_but_inside_failure_rolls_back(self):
        outside = self.book.db.execute("SELECT MIN(rid) FROM pages").fetchone()[0]
        for table in ("pages_fts", "pages_stem_fts"):
            self.book.db.execute(f"UPDATE {table} SET body='quartz pressure' WHERE rowid=?", (outside,))
            self.book.db.execute(f"DELETE FROM {table}_docsize WHERE id=?", (outside,))
        self.assertTrue(all(route is not None for route in self.both(project="target")[1]))
        inside = self.book.db.execute("SELECT MIN(rid) FROM pages WHERE project_id='target'").fetchone()[0]
        self.book.db.execute("DELETE FROM pages_fts_docsize WHERE id=?", (inside,))
        errors = []
        for dense in (True, False):
            context = patch.object(self.book, "_dense_project_rank", wraps=self.book._dense_project_rank) if dense else \
                patch.object(self.book, "_dense_project_rank", return_value=False)
            with context:
                try:
                    stable(self.book, project="target")
                except sqlite3.DatabaseError as error:
                    errors.append((type(error), error.args))
            self.assertFalse(self.book.db.in_transaction)
        self.assertEqual(len(errors), 2)
        self.assertEqual(errors[0], errors[1])

    def test_same_arity_bm25_override_and_global_float_adapter_use_original_route(self):
        key = (float, sqlite3.PrepareProtocol)
        absent = object()
        previous = sqlite3.adapters.get(key, absent)
        try:
            sqlite3.register_adapter(float, lambda value: 0.0)
            self.assertFalse(self.certificate())
            self.assertEqual(self.both(project="target")[1], [])
        finally:
            if previous is absent:
                sqlite3.adapters.pop(key, None)
            else:
                sqlite3.adapters[key] = previous
        self.assertTrue(self.certificate())
        # FTS registers a variadic overload (-1), even though this route
        # supplies the table plus four weights. Verify registration itself.
        self.book.db.create_function("bm25", -1, lambda *args: -9.0)
        self.assertEqual(self.book.db.execute(
            "SELECT bm25(NULL,2.0,2.0,1.0,0.25)").fetchone()[0], -9.0)
        self.assertFalse(self.certificate())
        self.assertEqual(self.both(project="target")[1], [])

    def test_low_limits_custom_factories_and_project_subclasses_use_original_route(self):
        class Project(str):
            pass

        self.assertEqual(self.both(project=Project("target"))[1], [])
        for name, factory in (("row_factory", lambda cursor, row: sqlite3.Row(cursor, row)),
                              ("text_factory", lambda raw: raw.decode("utf-8"))):
            original = getattr(self.book.db, name)
            try:
                setattr(self.book.db, name, factory)
                self.assertEqual(self.both(project="target")[1], [])
            finally:
                setattr(self.book.db, name, original)
        self.book.db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 1023)
        self.assertEqual(self.both(project="target")[1], [])

    def test_trace_reentry_keeps_original_route_and_same_connection_write_semantics(self):
        rowid = self.book.db.execute(
            "SELECT MIN(rid) FROM pages WHERE project_id='target'").fetchone()[0]
        with new_book() as reference:
            self.book.db.backup(reference.db)
            reference.db.execute("DELETE FROM pages WHERE rid=?", (rowid,))
            with patch.object(reference, "_dense_project_rank", return_value=False):
                expected = stable(reference, project="target")
        statements = []
        changed = False

        def trace(statement):
            nonlocal changed
            statements.append(statement)
            if not changed and statement.lstrip().startswith("SELECT p.rid,p.id,bm25("):
                changed = True
                self.book.db.execute("DELETE FROM pages WHERE rid=?", (rowid,))

        self.book.db.set_trace_callback(trace)
        with patch.object(self.book, "_dense_rank_route", wraps=self.book._dense_rank_route) as route:
            actual = stable(self.book, project="target")
        self.book.db.set_trace_callback(None)
        self.assertTrue(changed)
        self.assertEqual(actual, expected)
        route.assert_not_called()
        self.assertFalse(any("SELECT CASE WHEN" in sql for sql in statements))
        self.assertFalse(self.book.db.in_transaction)


class NativeConnectionInterfaceTests(unittest.TestCase):
    def test_optional_apis_remain_optional_and_customizations_invalidate_before_forwarding(self):
        names = ("create_function", "create_aggregate", "create_window_function", "load_extension",
                 "enable_load_extension", "create_collation", "set_authorizer",
                 "set_progress_handler", "set_trace_callback", "setlimit")
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(hasattr(store._RecallConnection, name), hasattr(sqlite3.Connection, name))
                if not hasattr(sqlite3.Connection, name):
                    continue
                connection = store._RecallConnection(":memory:")
                try:
                    self.assertFalse(hasattr(connection, "__dict__"))
                    try:
                        getattr(connection, name)()
                    except (TypeError, sqlite3.Error):
                        pass
                    self.assertFalse(connection._rank_ordinary)
                finally:
                    connection.close()


if __name__ == "__main__":
    unittest.main()
