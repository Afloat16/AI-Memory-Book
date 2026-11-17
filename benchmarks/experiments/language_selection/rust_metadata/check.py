"""Shared C/Rust correctness, callback-order and real-workload activation gate.

No performance timers are used here. The existing C4 suite is replayed with the
candidate installed, and actual native completion is observed only in this
untimed run. Timed workers must not leave the observer installed.
"""
from __future__ import annotations

import argparse
import builtins
from collections import Counter
import copy
import hashlib
import importlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sqlite3
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def outcome(function, *arguments):
    try:
        value = function(*arguments)
        return {"value": value, "order": list(value) if isinstance(value, dict) else None}
    except Exception as error:
        return {"error": [type(error).__module__, type(error).__qualname__, error.args]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-source", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--module", default="_language_rust_metadata")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--locomo", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Choose a new correctness output")
    sys.path[:0] = [str(args.python_source.resolve()), str(ROOT), str(ROOT / "tests")]
    from memory_book import store
    from adapter import install
    spec = importlib.util.spec_from_file_location(args.module, args.binary.resolve())
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    original = store.MemoryBook._bounded_candidate_metadata
    assert install(store, native), "The ordinary host must activate the candidate"
    wrapper = store.MemoryBook._bounded_candidate_metadata
    environment = wrapper._language_metadata_env
    assert environment["ordinary_ready"]()
    counters = Counter()

    def observe(frame, event, argument):
        if event == "return" and frame.f_code is wrapper.__code__:
            result = frame.f_locals.get("result", NotImplemented)
            counters["wrapper"] += 1
            counters["fallback" if result is NotImplemented else "completed"] += 1
            if isinstance(result, dict):
                counters["pruned"] += 1
        elif event == "c_call" and getattr(argument, "__self__", None) is native:
            counters["native_calls"] += 1
        elif event == "call" and frame.f_code is environment["after_light"].__code__:
            counters["after_light"] += 1
        elif event == "call" and frame.f_code is environment["after_directories"].__code__:
            counters["after_directories"] += 1

    test_module = importlib.import_module("test_round5_candidate_c4")
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_module)
    sys.setprofile(observe)
    try:
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        sys.setprofile(None)
    assert result.wasSuccessful(), "Existing candidate-metadata regressions failed"
    regression_counts = dict(counters)
    fixture = test_module.CandidateMetadataBoundTests("test_shared_directory_query_includes_every_pair_once")
    fixture.setUp()
    book = fixture.book
    digest = hashlib.sha256()
    direct_checks = 0
    callback_cases = []
    base_rows = fixture.rows
    base_relevance = fixture.relevance
    light = {row[0]: tuple(row) for row in book.db.execute(
        "SELECT id,project_id,chapter_id,session_pk FROM pages WHERE project_id='fixture'")}

    def rows_for(carried):
        values = copy.deepcopy(base_rows)
        if carried:
            values = store._RecallCandidates(values)
            values.metadata = dict(light)
        return values

    def compare(values, count, carried):
        nonlocal direct_checks
        records = []
        for function in (original, wrapper):
            rows = rows_for(carried)
            statements = []
            book.db.set_trace_callback(statements.append)
            try:
                value = outcome(function, book, rows, dict(values), count)
            finally:
                book.db.set_trace_callback(None)
            if isinstance(value.get("value"), dict):
                assert all(value["value"][key] is rows[key] for key in value["value"])
            records.append({"outcome": value, "mutated_rows": rows, "sql": statements})
        assert records[0] == records[1], (count, carried, records)
        digest.update(canonical(records[1]).encode())
        direct_checks += 1

    try:
        sys.setprofile(observe)
        for carried in (False, True):
            for count in (1, 3, 5, 20, len(base_rows), len(base_rows) + 1, 0, -1, 10**100):
                compare(base_relevance, count, carried)
            for value in (0.0, 1.0, -0.0, -0.01, math.nan, math.inf, -math.inf):
                modified = dict(base_relevance)
                modified[next(reversed(modified))] = value
                compare(modified, 3, carried)
            rng = random.Random(171117)
            for _ in range(48):
                modified = {key: rng.choice((0.0, 0.01, 0.99, 1.0, 1.15, 4.0, math.nextafter(1.0, 0.0)))
                            for key in base_rows}
                compare(modified, rng.choice((1, 3, 7, 20)), carried)
        sys.setprofile(None)

        class AlternateCandidates(dict):
            __slots__ = ("metadata",)

            def items(self):
                callback_log.append("alternate.items")
                return super().items()

        callback_log = []

        def callback_run(function, scenario):
            nonlocal callback_log
            carried = scenario in {"live_project", "live_missing_pair", "removed_candidate", "changed_class", "custom_update"}
            rows = rows_for(carried)
            values = dict(base_relevance)
            statements = []
            callback_log = []
            original_db = book.db
            alternate_db = sqlite3.connect(":memory:")
            original_db.backup(alternate_db)
            alternate_db.row_factory = sqlite3.Row
            saved_globals = {name: (name in store.__dict__, store.__dict__.get(name))
                             for name in ("len", "any", "str", "MemoryBook", "__getattr__")}
            saved_math_isfinite = math.isfinite
            fired = False
            callback_error = []
            original_len = len
            original_any = any
            original_type = type
            identifiers = list(rows)

            class Updating(dict):
                def update(self, *items, **keywords):
                    callback_log.append(["custom.update", list(keywords)])
                    return super().update(*items, **keywords)

            def changed_len(value):
                callback_log.append(["changed.len", original_type(value).__name__])
                return original_len(value)

            def changed_any(value):
                callback_log.append(["changed.any", original_type(value).__name__])
                return original_any(value)

            def trace(sql):
                nonlocal fired
                statements.append(sql)
                target = sql.startswith("WITH requested") if carried or scenario == "global_after_dirs" else sql.startswith("SELECT id,project_id")
                if fired or not target:
                    return
                fired = True
                try:
                    if scenario == "swap_db":
                        book.db = alternate_db
                    elif scenario == "live_project":
                        old = rows.metadata[identifiers[0]]
                        rows.metadata[identifiers[0]] = (old[0], "callback-project", old[2], old[3])
                    elif scenario == "live_missing_pair":
                        identity = identifiers[1]
                        old = rows.metadata[identity]
                        rows.metadata[identity] = (old[0], old[1], "missing-pair", old[3])
                    elif scenario == "removed_candidate":
                        del rows[identifiers[1]]
                    elif scenario == "changed_class":
                        rows.__class__ = AlternateCandidates
                    elif scenario == "custom_update":
                        rows[identifiers[1]] = Updating(rows[identifiers[1]])
                    elif scenario == "global_after_light":
                        store.len = changed_len
                        store.any = changed_any
                    elif scenario == "global_after_dirs":
                        store.len = changed_len
                        store.any = changed_any
                    elif scenario == "deleted_module_dependency":
                        del store.MemoryBook
                        def module_getattr(name):
                            callback_log.append(["module_getattr", name])
                            raise AttributeError(name)
                        store.__getattr__ = module_getattr
                    elif scenario == "deleted_math_dependency":
                        del math.isfinite
                    elif scenario == "row_factory":
                        def factory(cursor, values):
                            callback_log.append("row_factory")
                            return list(values)
                        original_db.row_factory = factory
                except Exception as error:
                    callback_error.append([type(error).__name__, str(error)])

            original_db.set_trace_callback(trace)
            alternate_db.set_trace_callback(trace)
            try:
                value = outcome(function, book, rows, values, 3)
                assert fired and not callback_error, (scenario, callback_error)
                if scenario == "changed_class":
                    assert type(rows) is AlternateCandidates
                record = {"scenario": scenario, "outcome": value, "rows": dict(rows),
                          "sql": statements, "callbacks": list(callback_log)}
            finally:
                original_db.set_trace_callback(None)
                alternate_db.set_trace_callback(None)
                original_db.row_factory = sqlite3.Row
                math.isfinite = saved_math_isfinite
                book.db = original_db
                alternate_db.close()
                for name, (present, previous) in saved_globals.items():
                    if present:
                        store.__dict__[name] = previous
                    else:
                        store.__dict__.pop(name, None)
            return record

        sys.setprofile(observe)
        for scenario in ("swap_db", "live_project", "live_missing_pair", "removed_candidate", "changed_class",
                         "custom_update", "global_after_light", "global_after_dirs", "row_factory",
                         "deleted_module_dependency", "deleted_math_dependency"):
            expected = callback_run(original, scenario)
            actual = callback_run(wrapper, scenario)
            assert actual == expected, (scenario, actual, expected)
            callback_cases.append(scenario)
            digest.update(canonical(actual).encode())
        sys.setprofile(None)
    finally:
        sys.setprofile(None)
        fixture.doCleanups()

    # Preinstallation guards must decline without invoking custom replacements.
    guard_cases = []
    for name in ("dict", "list", "set", "str", "int", "type", "len", "any", "sorted", "getattr"):
        saved = builtins.__dict__[name]
        calls = []
        def replaced(*arguments, **keywords):
            calls.append(name)
            return saved(*arguments, **keywords)
        store.MemoryBook._bounded_candidate_metadata = original
        builtins.__dict__[name] = replaced
        try:
            installed = install(store, native)
        finally:
            builtins.__dict__[name] = saved
            store.MemoryBook._bounded_candidate_metadata = wrapper
        assert installed is False and calls == [], (name, installed, calls)
        guard_cases.append("preinstall_builtin_" + name)
    saved_isfinite = math.isfinite
    calls = []
    def changed_isfinite(value):
        calls.append(value)
        return saved_isfinite(value)
    store.MemoryBook._bounded_candidate_metadata = original
    math.isfinite = changed_isfinite
    try:
        installed = install(store, native)
    finally:
        math.isfinite = saved_isfinite
        store.MemoryBook._bounded_candidate_metadata = wrapper
    assert installed is False and calls == []
    guard_cases.append("preinstall_math_isfinite")
    descriptor = store._RecallCandidates.__dict__["metadata"]
    store.MemoryBook._bounded_candidate_metadata = original
    store._RecallCandidates.metadata = property(lambda self: (_ for _ in ()).throw(AssertionError("must not call property")))
    try:
        installed = install(store, native)
    finally:
        store._RecallCandidates.metadata = descriptor
        store.MemoryBook._bounded_candidate_metadata = wrapper
    assert installed is False
    guard_cases.append("preinstall_metadata_property")
    code = original.__code__
    def altered(self, rows, relevance, count):
        raise AssertionError("must not call replaced method")
    store.MemoryBook._bounded_candidate_metadata = original
    original.__code__ = altered.__code__
    try:
        installed = install(store, native)
    finally:
        original.__code__ = code
        store.MemoryBook._bounded_candidate_metadata = wrapper
    assert installed is False
    guard_cases.append("preinstall_method_code")
    assert environment["ordinary_ready"]()

    from benchmarks.data import generate_dataset
    datasets = {"synthetic61": generate_dataset(seed=61, split="development", projects=8)}
    if args.locomo:
        from benchmarks.public_data import load_locomo
        datasets["public1015"] = load_locomo(args.locomo)
    cohort_records = {}
    for name, dataset in datasets.items():
        before = Counter(counters)
        cohort_digest = hashlib.sha256()
        with store.MemoryBook(":memory:", cache_size=0) as book:
            for session in dataset.sessions:
                book.ingest(session)
            for case in dataset.queries:
                store.MemoryBook._bounded_candidate_metadata = original
                try:
                    expected = book.recall(case.query, project=case.project, budget_chars=2400, limit=5, use_cache=False)
                finally:
                    store.MemoryBook._bounded_candidate_metadata = wrapper
                sys.setprofile(observe)
                try:
                    actual = book.recall(case.query, project=case.project, budget_chars=2400, limit=5, use_cache=False)
                finally:
                    sys.setprofile(None)
                expected.pop("latency_ms")
                actual.pop("latency_ms")
                assert actual == expected, (name, case.query)
                cohort_digest.update(canonical(actual).encode())
        counts = dict(counters - before)
        assert counts.get("native_calls", 0) > 0 and counts.get("pruned", 0) > 0, counts
        cohort_records[name] = {"queries": len(dataset.queries), "result_sha256": cohort_digest.hexdigest(), "dispatch": counts}
    report = {
        "status": "correctness-passed-no-timing", "module": args.module,
        "binary": str(args.binary.resolve()), "binary_sha256": sha(args.binary),
        "adapter_sha256": sha(HERE / "adapter.py"), "test_sha256": sha(__file__),
        "store_sha256": sha(Path(store.__file__)),
        "existing_regressions": {"run": result.testsRun, "skipped": len(result.skipped), "dispatch": regression_counts},
        "direct_differential_cases": direct_checks, "callback_cases": callback_cases,
        "preinstallation_guard_cases": guard_cases, "result_sha256": digest.hexdigest(),
        "dispatch_total": dict(counters), "cohorts": cohort_records,
        "locomo_sha256": sha(args.locomo) if args.locomo else None,
        "notes": ["No timers or performance claims", "All SQL callback traces and partial row mutation outcomes compared",
                  "Native NotImplemented only before SQL; exact continuations never repeat a previous query",
                  "Profiler is removed before exit and must not be enabled in timed workers"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
