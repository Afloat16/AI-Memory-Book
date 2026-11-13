"""Artificial native events and protocol proofs. No benchmark corpus is loaded."""
from __future__ import annotations
import itertools
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import round5_lm_sql_attribution as d


def catalog():
    return d.SiteCatalog({}, ())


class NativeEvents(unittest.TestCase):
    def tearDown(self):
        sys.setprofile(None)

    def test_actual_builtin_identity_and_private_values_are_not_recorded(self):
        with sqlite3.connect(":memory:") as db:
            observer = d.SQLiteObserver(catalog())
            def work():
                db.execute("SELECT 'private-sentinel-not-in-report'").fetchall()
                return db.execute("SELECT 7").fetchone()
            self.assertEqual(d.observe_call(observer, work), (7,))
        report = observer.report()
        self.assertTrue(report["valid"])
        self.assertEqual([r["method"] for r in report["spans"]],
            ["Connection.execute", "Cursor.fetchall", "Connection.execute", "Cursor.fetchone"])
        self.assertEqual(report["target_events"], {"c_call": 4, "c_return": 4})
        self.assertNotIn("private-sentinel-not-in-report", json.dumps(report))
        self.assertNotIn("SELECT", json.dumps(report))

    def test_real_c_exception_uses_the_same_builtin_and_retains_exception_span(self):
        with sqlite3.connect(":memory:") as db:
            observer = d.SQLiteObserver(catalog())
            with self.assertRaises(sqlite3.OperationalError):
                d.observe_call(observer, db.execute, "SELECT invented_missing_column")
        report = observer.report()
        self.assertTrue(report["valid"])
        self.assertEqual(report["target_events"], {"c_call": 1, "c_exception": 1})
        self.assertEqual(report["spans"][0]["status"], "exception")
        self.assertNotIn("invented_missing_column", json.dumps(report))

    def test_nested_native_udf_calls_keep_parentage_and_exclusive_sums(self):
        with sqlite3.connect(":memory:") as outer, sqlite3.connect(":memory:") as inner:
            outer.create_function("nested", 0, lambda: inner.execute("SELECT 9").fetchone()[0])
            observer = d.SQLiteObserver(catalog())
            self.assertEqual(d.observe_call(observer, lambda: outer.execute("SELECT nested()").fetchone()), (9,))
        rows = observer.report()["spans"]
        self.assertTrue(observer.report()["valid"])
        self.assertEqual([r["parent_sequence"] for r in rows], [None, 0, 0, None])
        self.assertEqual(rows[0]["child_inclusive_ns"], rows[1]["inclusive_ns"] + rows[2]["inclusive_ns"])
        self.assertEqual(rows[0]["exclusive_ns"], rows[0]["inclusive_ns"] - rows[0]["child_inclusive_ns"])

    def test_nested_c_exceptions_unwind_in_order(self):
        with sqlite3.connect(":memory:") as outer, sqlite3.connect(":memory:") as inner:
            outer.create_function("nested_fail", 0, lambda: inner.execute("SELECT invented_missing").fetchone()[0])
            observer = d.SQLiteObserver(catalog())
            with self.assertRaises(sqlite3.OperationalError):
                d.observe_call(observer, outer.execute, "SELECT nested_fail()")
        self.assertTrue(observer.report()["valid"])
        self.assertEqual([r["status"] for r in observer.spans], ["exception", "exception"])
        self.assertEqual(observer.spans[1]["parent_sequence"], 0)

    def test_row_factory_exception_is_recorded_without_exception_values(self):
        with sqlite3.connect(":memory:") as db:
            def fail(cursor, row):
                raise ValueError("private-row-sentinel")
            db.row_factory = fail
            cursor = db.execute("SELECT 1")
            observer = d.SQLiteObserver(catalog())
            with self.assertRaises(ValueError):
                d.observe_call(observer, cursor.fetchone)
        self.assertTrue(observer.report()["valid"])
        self.assertEqual(observer.spans[0]["method"], "Cursor.fetchone")
        self.assertEqual(observer.spans[0]["status"], "exception")
        self.assertNotIn("private-row-sentinel", json.dumps(observer.report()))

    def test_interrupt_retains_other_native_builtin_and_exception(self):
        with sqlite3.connect(":memory:") as db:
            def stop():
                db.interrupt()
                return 1
            db.create_function("invented_stop", 0, stop)
            sites = catalog()
            observer = d.SQLiteObserver(sites)
            with self.assertRaises(sqlite3.OperationalError):
                d.observe_call(observer, lambda: db.execute("SELECT invented_stop()").fetchone())
        self.assertTrue(observer.report()["valid"])
        self.assertIn("Connection.interrupt", [r["method"] for r in observer.spans])
        self.assertIn("exception", [r["status"] for r in observer.spans])
        self.assertIn("other_sqlite_builtin", [s["category"] for s in sites.sites])

    def test_callback_has_no_filesystem_access_and_never_probes_user_objects(self):
        class Forbidden:
            def __getattribute__(self, name):
                raise AssertionError("user object inspected")
        self.assertIsNone(d.SQLiteObserver.native_method(Forbidden()))
        with sqlite3.connect(":memory:") as db:
            observer = d.SQLiteObserver(catalog())
            with patch.object(Path, "resolve", side_effect=AssertionError("resolve")), \
                 patch.object(Path, "stat", side_effect=AssertionError("stat")):
                self.assertEqual(d.observe_call(observer, lambda: db.execute("SELECT 1").fetchone()), (1,))
        self.assertTrue(observer.report()["valid"])

    def test_existing_profiler_is_not_replaced(self):
        callback = lambda frame, event, arg: None
        sys.setprofile(callback)
        observer = d.SQLiteObserver(catalog())
        with self.assertRaises(d.ObserverFailure):
            observer.begin()
        self.assertIs(sys.getprofile(), callback)
        self.assertFalse(observer.report()["valid"])
        self.assertEqual(observer.report()["callback_failure"]["type"], "ExistingProfiler")

    def test_lifecycle_misuse_always_invalidates_the_observation(self):
        observer = d.SQLiteObserver(catalog())
        with self.assertRaises(d.ObserverFailure):
            observer.finish()
        self.assertFalse(observer.report()["valid"])
        self.assertEqual(observer.report()["callback_failure"]["type"], "ObserverLifecycleMisuse")
        observer = d.SQLiteObserver(catalog())
        d.observe_call(observer, lambda: None)
        self.assertTrue(observer.report()["valid"])
        with self.assertRaises(d.ObserverFailure):
            observer.finish()
        self.assertFalse(observer.report()["valid"])
        observer = d.SQLiteObserver(catalog())
        observer.begin()
        sys.setprofile(None)
        with self.assertRaises(d.ObserverFailure):
            observer.finish()
        self.assertFalse(observer.report()["valid"])
        self.assertEqual(observer.report()["callback_failure"]["type"], "ProfileCallbackReplaced")
        observer = d.SQLiteObserver(catalog())
        observer.begin()
        with self.assertRaises(d.ObserverFailure):
            observer.begin()
        with self.assertRaises(d.ObserverFailure):
            observer.finish()
        self.assertFalse(observer.report()["valid"])


    def test_raw_native_wrapper_identity_probe(self):
        """Evidence only: never weaken the production observer from this probe."""
        from types import BuiltinMethodType, MethodDescriptorType
        descriptors = {(owner, name): value for owner in (sqlite3.Connection, sqlite3.Cursor)
            for name, value in vars(owner).items() if type(value) is MethodDescriptorType}
        stack, events = [], []
        label = None
        def callback(frame, event, arg):
            if event not in ("c_call", "c_return", "c_exception") or type(arg) is not BuiltinMethodType:
                return
            receiver = arg.__self__
            owner = type(receiver)
            if owner not in (sqlite3.Connection, sqlite3.Cursor):
                return
            descriptor = descriptors.get((owner, arg.__name__))
            if event == "c_call":
                stack.append((frame, arg, receiver, owner, descriptor, arg.__name__, len(stack)))
                return
            if not stack:
                events.append({"case":label, "event":event, "unmatched_exit":True})
                return
            original = stack.pop()
            events.append({"case":label, "event":event, "method":owner.__name__+"."+arg.__name__,
                "depth":original[6], "frame_is":original[0] is frame,
                "wrapper_is":original[1] is arg, "receiver_is":original[2] is receiver,
                "native_type_is":original[3] is owner,
                "descriptor_is":descriptor is not None and original[4] is descriptor,
                "method_same":original[5] == arg.__name__})
        with sqlite3.connect(":memory:") as first, sqlite3.connect(":memory:") as second:
            first.create_function("invented_nested",0,lambda:second.execute("SELECT 2").fetchone()[0])
            bound = first.execute
            sys.setprofile(callback)
            try:
                label = "inline-success"
                first.execute("SELECT 1").fetchone()
                label = "prebound-success"
                bound("SELECT 1").fetchone()
                label = "inline-exception"
                try:
                    first.execute("SELECT invented_missing")
                except sqlite3.OperationalError:
                    pass
                label = "nested-success"
                first.execute("SELECT invented_nested()").fetchone()
            finally:
                sys.setprofile(None)
        result = {"native_wrapper_probe":events, "unclosed_entries":len(stack),
            "corpus_calls":0, "timing_claim":False}
        print(json.dumps(result), flush=True)
        self.assertEqual(len(stack),0)
        self.assertTrue(events)
        self.assertTrue(all(all(row.get(key) for key in
            ("frame_is","receiver_is","native_type_is","descriptor_is","method_same")) for row in events))


class ArithmeticAndSites(unittest.TestCase):
    def test_fake_clock_nested_inclusive_exclusive_and_bookkeeping(self):
        moments = iter([0, 10, 11, 20, 30, 31, 50, 51, 80, 81])
        observer = d.SQLiteObserver(catalog(), lambda: next(moments))
        frame = sys._getframe()
        with sqlite3.connect(":memory:") as a, sqlite3.connect(":memory:") as b:
            first, second = a.execute, b.execute
            observer(frame, "c_call", first)
            observer(frame, "c_call", second)
            observer(frame, "c_return", second)
            observer(frame, "c_return", first)
        self.assertEqual([r["inclusive_ns"] for r in observer.spans], [70, 20])
        self.assertEqual([r["exclusive_ns"] for r in observer.spans], [50, 20])
        self.assertEqual(observer.bookkeeping_ns, 24)

    def test_fresh_wrapper_with_exact_native_identity_is_recorded(self):
        observer = d.SQLiteObserver(catalog(), itertools.count().__next__)
        with sqlite3.connect(":memory:") as db:
            first, another = db.execute, db.execute
            self.assertIsNot(first, another)
            frame = sys._getframe()
            observer(frame, "c_call", first)
            observer(frame, "c_return", another)
        self.assertEqual(observer.spans[0]["status"], "returned")
        self.assertIs(observer.spans[0]["wrapper_is"], False)
        self.assertIsNone(observer.callback_failure)

    def test_wrong_receiver_method_frame_and_non_lifo_still_fail(self):
        with sqlite3.connect(":memory:") as first, sqlite3.connect(":memory:") as second:
            frame = sys._getframe()
            for kind in ("receiver", "method", "frame", "order"):
                with self.subTest(kind=kind):
                    observer = d.SQLiteObserver(catalog(), itertools.count().__next__)
                    original = first.execute
                    observer(frame, "c_call", original)
                    if kind == "order":
                        observer(frame, "c_call", second.execute)
                    def wrong_frame():
                        observer(sys._getframe(), "c_return", original)
                    with self.assertRaises(d.ObserverFailure):
                        if kind == "frame":
                            wrong_frame()
                        else:
                            returned = second.execute if kind == "receiver" else first.commit if kind == "method" else original
                            observer(frame, "c_return", returned)
                    self.assertEqual(observer.callback_failure["type"], "NativePairMismatch")
                    self.assertTrue(observer.report()["open_sequences"])
                    self.assertFalse(observer.report()["valid"])

    def test_missing_exit_remains_terminal_and_keeps_open_span(self):
        with sqlite3.connect(":memory:") as db:
            observer = d.SQLiteObserver(catalog())
            observer.begin()
            observer(sys._getframe(), "c_call", db.execute)
            with self.assertRaises(d.ObserverFailure):
                observer.finish()
        self.assertEqual(observer.callback_failure["type"], "UnclosedNativeStack")
        self.assertEqual(observer.spans[0]["status"], "open")
        self.assertFalse(observer.report()["valid"])

    def test_negative_span_exit_without_entry_and_open_stack_keep_partial(self):
        observer = d.SQLiteObserver(catalog(), iter([0, 10, 11, 5, 6]).__next__)
        with sqlite3.connect(":memory:") as db:
            function, frame = db.execute, sys._getframe()
            observer(frame, "c_call", function)
            with self.assertRaises(d.ObserverFailure):
                observer(frame, "c_exception", function)
            empty = d.SQLiteObserver(catalog(), itertools.count().__next__)
            with self.assertRaises(d.ObserverFailure):
                empty(frame, "c_return", function)
        self.assertEqual(observer.spans[0]["status"], "open")
        self.assertIsNone(observer.spans[0]["end_ns"])
        self.assertFalse(observer.report()["valid"])
        self.assertIsNotNone(empty.callback_failure)

    def test_upper_caller_classification_and_unclassified_sites(self):
        sites = d.SiteCatalog({}, d.scope_value()["observer"]["source_mapping"]["rules"])
        location = {"path": "src/memory_book/store.py", "source_sha256": "a"*64,
            "qualname": "_candidate_rows", "line": 253}
        caller = {"path": location["path"], "source_sha256": "a"*64,
            "qualname": "MemoryBook.recall", "line": 811}
        self.assertEqual(sites.category("Cursor.fetchall", location, caller), "fts_candidates")
        caller["line"] = 895
        self.assertEqual(sites.category("Cursor.fetchall", location, caller), "directory_metadata")
        caller["line"] = 1
        self.assertEqual(sites.category("Cursor.fetchall", location, caller), "unclassified_primary")
        location["source_sha256"] = None
        caller["line"] = 811
        self.assertEqual(sites.category("Cursor.fetchall", location, caller), "unclassified_primary")
        self.assertEqual(sites.category("Connection.commit", location, caller), "other_sqlite_builtin")

    def test_fixed_artificial_calibration_retains_every_sample(self):
        value = d.artificial_calibration(catalog())
        self.assertEqual(len(value["clock_pair_deltas_ns"]), 1000)
        self.assertEqual(len(value["unobserved_native_operation_wall_ns"]), 128)
        self.assertEqual(len(value["observed_native_operations"]), 128)
        self.assertTrue(value["off_then_on_fixed_order"])
        self.assertEqual(value["corpus_calls"], 0)
        self.assertTrue(all(r["valid"] and len(r["spans"]) == 2 for r in value["observed_native_operations"]))
        self.assertNotIn("speedup", value)
        self.assertNotIn("corrected_ns", value)


@unittest.skipUnless(os.environ.get("SQL_ATTRIBUTION_TEST_SOURCE"), "dedicated CI supplies exact LM export")
class ExactLMIntegration(unittest.TestCase):
    def setUp(self):
        self.source = Path(os.environ["SQL_ATTRIBUTION_TEST_SOURCE"])
        self.identity = d.runtime_identity()
        self.rules = d.scope_value()["observer"]["source_mapping"]["rules"]
        self.filenames = d.frozen_filename_map(self.source, self.identity)
        from memory_book import MemoryBook, store
        self.Book, self.store = MemoryBook, store
        self.assertEqual(Path(store.__file__).resolve(), self.source / "src/memory_book/store.py")

    def test_real_payload_and_native_guard_with_both_upper_callsites(self):
        sites = d.SiteCatalog(self.filenames, self.rules)
        with self.Book(":memory:", cache_size=0) as book:
            for index, word in enumerate(("orbiting", "orbits", "orbit")):
                book.ingest({"project":"invented", "session_id":"fake-"+str(index),
                    "task_id":"relay", "task_title":"Relay calibration", "title":"Flight notes",
                    "created_at":"2024-01-01T00:00:00Z",
                    "messages":[{"role":"user","content":"Record the relay"},
                        {"role":"assistant","content":("The relay "+word+" the moon. Calibration is stable. ")*16}]})
            connection = d.native_book_identity(book)
            expected = book.recall("orbiting relay calibration", project="invented", use_cache=False, budget_chars=4000)
            observer = d.SQLiteObserver(sites)
            actual = d.observe_call(observer, book.recall, "orbiting relay calibration",
                project="invented", use_cache=False, budget_chars=4000)
            expected.pop("latency_ms")
            actual.pop("latency_ms")
            self.assertEqual(expected, actual)
            self.assertIs(d.native_book_identity(book), connection)
        self.assertTrue(observer.report()["valid"])
        native = [s for s in sites.sites if s["method"]=="Cursor.fetchall"
                  and s["location"]["qualname"]=="_candidate_rows"]
        self.assertTrue(native)
        self.assertTrue(all(s["location"]["line"]==253 for s in native))
        self.assertEqual({s["category"] for s in native}, {"fts_candidates","directory_metadata"})
        self.assertFalse([s for s in sites.sites if s["category"].startswith("disabled_")])

    def test_cursor_factory_restoration_and_unsupported_fallback(self):
        sites = d.SiteCatalog(self.filenames, self.rules)
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute("SELECT 1 AS invented")
            observer = d.SQLiteObserver(sites)
            rows, retained = d.observe_call(observer, self.store._candidate_rows,
                cursor, cursor.description, connection)
            self.assertEqual(rows, [(1,)])
            self.assertIs(retained, cursor)
            self.assertIs(cursor.row_factory, sqlite3.Row)
            fallback = connection.execute("SELECT 2 AS invented")
            fallback.row_factory = None
            second = d.SQLiteObserver(sites)
            rows, retained = d.observe_call(second, self.store._candidate_rows,
                fallback, fallback.description, connection)
            self.assertEqual(rows, [(2,)])
            self.assertIsNone(retained)
            self.assertIsNone(fallback.row_factory)
        self.assertEqual([s["location"]["line"] for s in sites.sites], [253,257])
        self.assertTrue(observer.report()["valid"] and second.report()["valid"])


class PreclaimAndIsolation(unittest.TestCase):
    def test_missing_binding_precedes_claim_download_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(d,"SOURCE_BINDING",Path(tmp)/"missing.json"), \
                 patch.object(d,"publish") as publish, patch.object(d,"archive_source") as export, \
                 patch.object(d.urllib.request,"urlopen") as download:
                with self.assertRaises(ValueError):
                    d.run()
                publish.assert_not_called()
                export.assert_not_called()
                download.assert_not_called()

    def test_namespace_cannot_publish_to_completed_lm_branch(self):
        value = "a"*40
        self.assertEqual(d.parse_remote(value+"\trefs/heads/"+d.BRANCH), value)
        with self.assertRaises(d.PublicationError):
            d.parse_remote(value+"\trefs/heads/validation/v033-candidate-lm-development-1")

    def test_full_guard_rejects_added_cache_and_modified_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/"src/memory_book/sample.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\n")
            identity = {"files_sha256":d.source_files(root), "runtime_sha256":d.runtime_sha(root)}
            d.verify_exact_source(root, identity)
            cache = source.parent/"__pycache__/sample.cpython-312.pyc"
            cache.parent.mkdir()
            cache.write_bytes(b"invented")
            with self.assertRaises(ValueError):
                d.verify_exact_source(root, identity)
            cache.unlink()
            source.write_text("VALUE = 2\n")
            with self.assertRaises(ValueError):
                d.verify_exact_source(root, identity)


if __name__ == "__main__":
    unittest.main()
