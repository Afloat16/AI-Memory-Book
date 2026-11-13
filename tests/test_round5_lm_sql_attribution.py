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


CALIBRATION_CAPTURE = None


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
        global CALIBRATION_CAPTURE
        value = d.artificial_calibration(catalog())
        CALIBRATION_CAPTURE = value
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
        self.assertFalse([s for s in sites.sites if s["category"].startswith("disabled_")
                          or s["category"]=="unclassified_primary"])

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



def fake_observation():
    return {"valid": True, "started": True, "finished": True, "callback_failure": None,
        "open_sequences": [], "spans": [], "events": {}, "target_events": {},
        "non_target_events": 0, "callback_bookkeeping_ns": 0,
        "recall_wall_ns_including_observer": 10, "observed_exclusive_builtin_ns": 0,
        "unattributed_wall_ns": 10}


def fake_profile():
    old = {"helpers_sha256": {"helper": "a"*64}, "helper_dependency_sha256": {"dependency": "b"*64}, "cohorts": {}}
    cells = []
    for cohort, count in (("synthetic61",168),("public1015",1015)):
        ids = [cohort+"-invented-"+str(i) for i in range(count)]
        old["cohorts"][cohort] = {"queries":count,"dataset_sha256":"c"*64,"profile_query_order_sha256":d.digest(ids)}
        for configuration in d.CONFIG_NAMES:
            cells.append({"cohort":cohort,"configuration":configuration,"queries":count,
                "dataset_sha256":"c"*64,"status":"completed","sites":[],
                "rows":[{"query_id":qid,"non_timing_payload_sha256":"d"*64,"observation":fake_observation()} for qid in ids]})
    report = {"status":"completed","expected_calls":4732,"attempted_calls":4732,"completed_calls":4732,
        "runtime_source_sha256":d.RUNTIME_SHA,"script_sha256":"e"*64,"scope_sha256":d.SCOPE_SHA,
        "helpers_sha256":old["helpers_sha256"],"helper_dependency_sha256":old["helper_dependency_sha256"],"cells":cells}
    return report, old, json.loads(json.dumps(cells))


class CompleteProtocol(unittest.TestCase):

    def test_fingerprint_or_missing_latency_failure_keeps_current_native_spans(self):
        from types import SimpleNamespace
        with sqlite3.connect(":memory:") as db:
            class Book:
                missing = False
                def recall(self,*args,**kwargs):
                    value = db.execute("SELECT 1").fetchone()[0]
                    return {"number":value} if self.missing else {"number":value,"latency_ms":0}
            book = Book()
            case = SimpleNamespace(id="invented",query="invented",project="invented")
            def fail(value):
                raise ValueError("unreported-fingerprint-sentinel")
            row = d.observe_payload(book,case,{},catalog(),fail)
            self.assertEqual(row["state"],"failed")
            self.assertEqual(row["error_type"],"ValueError")
            self.assertEqual(len(row["observation"]["spans"]),2)
            self.assertTrue(row["observation"]["valid"])
            self.assertNotIn("unreported-fingerprint-sentinel",json.dumps(row))
            book.missing = True
            row = d.observe_payload(book,case,{},catalog(),d.digest)
            self.assertEqual(row["state"],"failed")
            self.assertEqual(row["error_type"],"KeyError")
            self.assertEqual(len(row["observation"]["spans"]),2)


    def test_all_4732_fake_payloads_and_orders_are_checked_and_mismatch_retained(self):
        report, old, references = fake_profile()
        self.assertTrue(d.profile_audit(report,old,references,"e"*64)["all_full_non_timing_payloads_equal_to_v032_c2"])
        report["cells"][-1]["rows"][-1]["non_timing_payload_sha256"] = "f"*64
        result = d.profile_audit(report,old,references,"e"*64)
        self.assertFalse(result["all_full_non_timing_payloads_equal_to_v032_c2"])
        self.assertEqual(len(result["mismatches"]),1)
        self.assertEqual(result["mismatches"][0]["query_id"],references[-1]["rows"][-1]["query_id"])

    def test_missing_extra_duplicate_reordered_invalid_payload_and_axes_are_rejected(self):
        report, old, references = fake_profile()
        for kind in ("missing","extra","duplicate","order","invalid-hash","axis","dataset","source","helper","producer","count","references"):
            with self.subTest(kind=kind):
                value = json.loads(json.dumps(report))
                baseline = references
                rows = value["cells"][0]["rows"]
                if kind == "missing": rows.pop()
                elif kind == "extra": rows.append(dict(rows[-1]))
                elif kind == "duplicate": rows[1]["query_id"] = rows[0]["query_id"]
                elif kind == "order": rows.reverse()
                elif kind == "invalid-hash": rows[0]["non_timing_payload_sha256"] = "invalid"
                elif kind == "axis": value["cells"][0]["configuration"] = "native-token2048"
                elif kind == "dataset": value["cells"][0]["dataset_sha256"] = "0"*64
                elif kind == "source": value["runtime_source_sha256"] = "0"*64
                elif kind == "helper": value["helpers_sha256"] = {}
                elif kind == "producer": value["script_sha256"] = "0"*64
                elif kind == "count": value["completed_calls"] = 4731
                else: baseline = references[:-1]
                with self.assertRaises(ValueError):
                    d.profile_audit(value,old,baseline,"e"*64)

    def test_unknown_primary_and_disabled_paths_remain_raw_but_fail_completion_gate(self):
        with sqlite3.connect(":memory:") as db:
            sites = catalog()
            observer = d.SQLiteObserver(sites)
            d.observe_call(observer, db.execute, "SELECT 1")
        for category in ("unclassified_primary","disabled_cache_path","disabled_coverage_path","disabled_optional_source"):
            with self.subTest(category=category):
                report, old, references = fake_profile()
                report["cells"][0]["sites"] = json.loads(json.dumps(sites.sites))
                report["cells"][0]["sites"][0]["category"] = category
                report["cells"][0]["rows"][0]["observation"] = observer.report()
                result = d.profile_audit(report,old,references,"e"*64)
                self.assertTrue(result["all_full_non_timing_payloads_equal_to_v032_c2"])
                self.assertFalse(result["all_classification_sites_valid"])
                self.assertEqual(result["cells"][0]["classification_violations"],[{"site_id":0,"category":category}])
                self.assertEqual(len(report["cells"][0]["rows"][0]["observation"]["spans"]),1)

    def test_raw_span_corruption_cannot_pass_accounting(self):
        with sqlite3.connect(":memory:") as db:
            sites = catalog()
            observer = d.SQLiteObserver(sites)
            d.observe_call(observer,lambda:db.execute("SELECT 1").fetchone())
        original = observer.report()
        d.audit_observation(original,sites.sites)
        for kind in ("sequence","open","site","time","child","counter","wall","wrapper"):
            value = json.loads(json.dumps(original))
            if kind == "sequence": value["spans"][0]["sequence"] = 2
            elif kind == "open": value["spans"][0]["status"] = "open"
            elif kind == "site": value["spans"][0]["site_id"] = 999
            elif kind == "time": value["spans"][0]["end_ns"] -= 1
            elif kind == "child": value["spans"][0]["child_inclusive_ns"] += 1
            elif kind == "counter": value["target_events"]["c_call"] += 1
            elif kind == "wall": value["unattributed_wall_ns"] += 1
            else: value["spans"][0]["wrapper_is"] = None
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                d.audit_observation(value,sites.sites)

    def test_cell_intent_then_lossless_partial_result_then_next_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public, state = root/"reports",root/"state"
            public.mkdir()
            state.mkdir()
            events = []
            with patch.object(d,"PUBLIC",public), patch.object(d,"STATE",state), \
                 patch.object(d,"publish",side_effect=lambda message: events.append(message)):
                paths = d.claim_cell("synthetic61","native-char4000","a"*64,168)
                self.assertTrue(paths["intent"].is_file())
                with paths["ledger"].open("xb") as stream:
                    d.append_ledger(stream,{"state":"started","query_id":"invented"})
                partial = {"status":"failed","rows":[{"query_id":"invented","observation":fake_observation()}]}
                storage = d.save_cell(paths,partial,[])
                self.assertEqual(json.loads(d.gzip.decompress(paths["output"].read_bytes()))["status"],"failed")
                self.assertEqual(d.gzip.decompress(paths["saved_ledger"].read_bytes()),paths["ledger"].read_bytes())
                self.assertEqual(storage["cell"]["sha256"],d.sha(paths["output"]))
                with self.assertRaises(ValueError):
                    d.claim_cell("synthetic61","native-char4000","a"*64,168)
                d.claim_cell("synthetic61","native-token512","a"*64,168)
            self.assertEqual(len(events),3)
            self.assertIn("claim",events[0])
            self.assertIn("preserve",events[1])
            self.assertIn("claim",events[2])

    def test_failed_intent_publication_prevents_a_query_or_next_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executed = []
            with patch.object(d,"PUBLIC",root/"reports"), patch.object(d,"STATE",root/"state"), \
                 patch.object(d,"publish",side_effect=d.PublicationError("invented rejection")):
                with self.assertRaises(d.PublicationError):
                    d.claim_cell("synthetic61","native-char4000","a"*64,168)
                    executed.append("query")
            self.assertEqual(executed,[])
            self.assertFalse((root/"state/ledgers/synthetic61-native-char4000.jsonl").exists())

    def test_worker_ownership_forbids_controller_publish_and_always_step_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            public,state = root/"reports",root/"state"
            public.mkdir()
            state.mkdir()
            d.save(state/"publisher.json",{"role":"worker"})
            d.save(state/"publication.json",{"expected_remote":"a"*40})
            with patch.object(d,"PUBLIC",public), patch.object(d,"STATE",state), \
                 patch.object(d,"publisher_role",return_value="controller"), \
                 patch.object(d,"git") as git, patch.object(d,"remote_head") as remote:
                with self.assertRaises(d.PublicationError):
                    d.publish("forbidden")
                d.preserve()
                git.assert_not_called()
                remote.assert_not_called()
            self.assertEqual(list(public.iterdir()),[])

    def test_publication_verifies_remote_and_never_retries_an_ambiguous_push(self):
        from types import SimpleNamespace
        for successful in (True,False):
            with self.subTest(successful=successful), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                public,state = root/"reports",root/"state"
                public.mkdir()
                state.mkdir()
                d.save(state/"publisher.json",{"role":"controller"})
                d.save(state/"publication.json",{"expected_remote":"a"*40})
                d.save(public/"invented.json",{"evidence":"invented"})
                state_of_git = {"head":"a"*40,"staged":False}
                def git(*args):
                    if args == ("rev-parse","HEAD"): return state_of_git["head"]
                    if args == ("diff","--cached","--name-only"):
                        return "reports/invented.json" if state_of_git["staged"] else ""
                    raise AssertionError(args)
                calls = []
                def command(args,**kwargs):
                    calls.append(args)
                    if args[1] == "add": state_of_git["staged"] = True
                    if args[1] == "commit": state_of_git["head"] = "b"*40
                    return SimpleNamespace(returncode=0,stdout="",stderr="")
                with patch.object(d,"ROOT",root), patch.object(d,"PUBLIC",public), patch.object(d,"STATE",state), \
                     patch.object(d,"publisher_role",return_value="controller"), patch.object(d,"git",side_effect=git), \
                     patch.object(d,"remote_head",side_effect=["a"*40, "b"*40 if successful else "c"*40]) as remote, \
                     patch.object(d.subprocess,"run",side_effect=command):
                    if successful:
                        d.publish("invented checkpoint")
                        self.assertEqual(d.read(state/"publication.json")["expected_remote"],"b"*40)
                    else:
                        with self.assertRaises(d.PublicationError): d.publish("ambiguous")
                        with self.assertRaises(d.PublicationError): d.publish("do not retry")
                        self.assertTrue((public/"publication-failure.json").exists())
                    self.assertEqual(remote.call_count,2)
                pushes = [args for args in calls if args[1]=="push"]
                self.assertEqual(len(pushes),1)
                self.assertEqual(pushes[0],["git","push","origin","HEAD:refs/heads/"+d.BRANCH])


    def test_publisher_handoff_requires_zero_exit_and_explicit_group_absence(self):
        for scenario in ("success","timeout","dead-leader-live-group","zero-live-group","unknown-group","launch-failure"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                public,state=root/"reports",root/"state"
                public.mkdir()
                state.mkdir()
                d.save(public/"binding.json",{"invented":True})
                d.save(state/"publisher.json",{"role":"controller"})
                events=[]
                class Process:
                    pid=12345
                    waits=0
                    def wait(self,timeout=None):
                        self.waits+=1
                        events.append("wait-"+str(timeout))
                        if scenario=="timeout" and self.waits==1:
                            raise d.subprocess.TimeoutExpired("invented",timeout)
                        return 17 if scenario=="dead-leader-live-group" else -9 if scenario=="timeout" else 0
                    def poll(self):
                        raise AssertionError("Leader poll cannot prove whole-group quiescence")
                process=Process()
                def launch(*args,**kwargs):
                    self.assertEqual(d.read(state/"publisher.json")["role"],"worker")
                    self.assertTrue(kwargs["start_new_session"])
                    events.append("launch")
                    if scenario=="launch-failure":
                        raise OSError("invented launch ambiguity")
                    return process
                def publish(message):
                    self.assertEqual(d.read(state/"publisher.json")["role"],"controller")
                    events.append("intent" if "claim" in message else "exit")
                def group_signal(pid,signal):
                    self.assertEqual(pid,12345)
                    events.append("group-"+str(signal))
                    if signal==0:
                        if scenario=="success": raise ProcessLookupError("group absent")
                        if scenario=="unknown-group": raise PermissionError("group unknown")
                with patch.object(d,"PUBLIC",public),patch.object(d,"STATE",state), \
                     patch.dict(os.environ,{"GITHUB_SHA":"a"*40,"GITHUB_RUN_ID":"invented"}), \
                     patch.object(d,"publish",side_effect=publish), \
                     patch.object(d.subprocess,"Popen",side_effect=launch), \
                     patch.object(d.os,"killpg",side_effect=group_signal):
                    if scenario=="success":
                        d.execute_worker()
                    else:
                        with self.assertRaises(d.PublicationError): d.execute_worker()
                confirmation=d.read(state/"worker-exit-confirmation.json")
                if scenario=="success":
                    self.assertEqual(events,["intent","launch","wait-1200","group-0","exit"])
                    self.assertTrue(confirmation["handoff_permitted"])
                    self.assertEqual(confirmation["group_state_before_cleanup"],"absent")
                    self.assertEqual(d.read(state/"publisher.json")["role"],"controller")
                    self.assertTrue((public/"worker-exit.json").exists())
                else:
                    self.assertFalse(confirmation["handoff_permitted"])
                    self.assertEqual(d.read(state/"publisher.json")["role"],"worker")
                    self.assertNotIn("exit",events)
                    self.assertFalse((public/"worker-exit.json").exists())
                    if scenario!="launch-failure":
                        self.assertIn("group-"+str(d.signal.SIGKILL),events)
                print(json.dumps({"invented_worker_lifecycle":scenario,"events":events,
                    "handoff_permitted":confirmation["handoff_permitted"],"corpus_calls":0}),flush=True)

    def test_bound_source_helpers_artifacts_and_prior_evidence_are_fail_closed(self):
        scope=d.scope_value()
        value={"status":"frozen-after-artificial-proof-before-sql-attribution-corpus","attempt":d.ATTEMPT,
            "runtime":d.runtime_identity(),"scope_sha256":d.SCOPE_SHA,
            "pairing_addendum_sha256":d.PAIRING_ADDENDUM_SHA,"publisher_addendum_sha256":d.PUBLISHER_ADDENDUM_SHA,
            "classification_sha256":d.digest(scope["observer"]["source_mapping"]),
            "planned_recall_calls":4732,"comparison_engine_calls":0,"fresh_rows_decoded":0,"speed_claim":False,
            "artifact_files_sha256":{p:d.sha(d.ROOT/p) for p in (d.SCRIPT_PATH,d.TEST_PATH,d.WORKFLOW_PATH)},
            "helpers_sha256":scope["inherited_protocol"]["helpers_sha256"],
            "helper_dependency_sha256":scope["inherited_protocol"]["helper_dependencies_sha256"],
            "prior_evidence":list(d.EVIDENCE),"source_ci":scope["prior_evidence"]["source_ci"],
            "artificial_evidence":{"commit":"a"*40,"path":"benchmarks/reports/invented.json","sha256":"b"*64}}
        d.validate_binding_value(value)
        for field in ("runtime","scope_sha256","pairing_addendum_sha256","publisher_addendum_sha256",
                      "classification_sha256","planned_recall_calls","comparison_engine_calls","fresh_rows_decoded",
                      "speed_claim","artifact_files_sha256","helpers_sha256","prior_evidence","source_ci"):
            changed=json.loads(json.dumps(value))
            if field in ("runtime","artifact_files_sha256","helpers_sha256","source_ci"): changed[field]={}
            elif field=="prior_evidence": changed[field]=[]
            elif field=="speed_claim": changed[field]=True
            elif field in ("planned_recall_calls","comparison_engine_calls","fresh_rows_decoded"): changed[field]=1
            else: changed[field]="0"*64
            with self.subTest(field=field),self.assertRaises(ValueError):
                d.validate_binding_value(changed)

    def test_artificial_evidence_must_cover_all_current_artifact_bytes_and_cases(self):
        files={d.SCRIPT_PATH:"a"*64,d.TEST_PATH:"b"*64,d.WORKFLOW_PATH:"c"*64}
        receipt={"source_commit":d.SOURCE_COMMIT,"runtime_sha256":d.RUNTIME_SHA,
            "script_sha256":files[d.SCRIPT_PATH],"test_file_sha256":files[d.TEST_PATH],
            "workflow_file_sha256":files[d.WORKFLOW_PATH],"expected":7,"tests":7,
            "passed":True,"errors":0,"failures":0,"skipped":0,"corpus_calls":0}
        value={"status":"passed-artificial-observer-and-protocol-tests","artifact_files_sha256":files,
            "workflow_run":{"conclusion":"success","status":"completed","run_attempt":1},
            "job":{"name":"protocol-fixtures","conclusion":"success","status":"completed"},"receipt":receipt}
        d.validate_artificial_evidence(value,{"artifact_files_sha256":files})
        for field in ("source_commit","runtime_sha256","script_sha256","test_file_sha256",
                      "workflow_file_sha256","tests","expected","passed","errors","failures","skipped","corpus_calls"):
            changed=json.loads(json.dumps(value))
            changed["receipt"][field]=False if field=="passed" else 1 if field in (
                "tests","expected","errors","failures","skipped","corpus_calls") else "0"*64
            with self.subTest(field=field),self.assertRaises(ValueError):
                d.validate_artificial_evidence(changed,{"artifact_files_sha256":files})


if __name__ == "__main__":
    unittest.main()
