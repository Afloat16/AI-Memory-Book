"""Artificial GC bookkeeping/saved-report tests; no Book, corpus or inference."""
from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import round5_gc_diagnostic as g


def snapshot():
    return {"stats": [{"collections": 0, "collected": 0, "uncollectable": 0} for _ in range(3)],
            "count": [0, 0, 0]}


def binding_fixture():
    bound = {"state_root": "state", "results_root": "results", "remote_ref": "refs/remotes/origin/main",
             "sources": {label: {"path": label, "commit": commit, "runtime_sha256": sha}
                         for label, (commit, sha) in g.SOURCES.items()},
             "python": {"implementation": "fixture"},
             "gc_state": {"enabled": True, "threshold": [700, 10, 10], "debug": 0}, "_expected_cells": []}
    for cohort in g.COHORTS:
        count = 168 if cohort == "synthetic61" else 1015
        for config, _ in g.CONFIGS:
            bound["_expected_cells"].append({"cohort": cohort, "configuration": config, "dataset_sha256": "a" * 64,
                "reference": "invented-reference-" + cohort + "-" + config + ".json.gz", "reference_sha256": "d" * 64,
                "query_ids": [f"invented-{cohort}-{index}" for index in range(count)],
                "expected_payload_sha256": [g.digest([cohort, config, index]) for index in range(count)]})
    bound["cells"] = g.cell_bindings(bound["_expected_cells"])
    bound["jobs"] = g.schedule(bound)
    return bound


def report_fixture(bound, job):
    report = {"version": g.VERSION, "job": job, "binding_sha256": "b" * 64,
              "source": bound["sources"][job["label"]], "python": bound["python"],
              "gc_state_before": bound["gc_state"], "gc_state_after": bound["gc_state"],
              "callbacks_restored": True, "wrappers_restored": True, "inputs_verified_after": True,
              "process_boundary": "exec-fresh-interpreter-no-prefix-reports",
              "status": "completed", "attempted_calls": job["expected_calls"],
              "completed_calls": job["expected_calls"], "attempt_id": "fixture-attempt", "save_sequence": 0}
    if job["kind"] == "probe":
        d, late = job["label"] == "candidate-d", job["label"] != "v032"
        stem = job["case"] != "single-route"
        report.update(fixture_sha256="c" * 64, payload_sha256=g.digest(job["case"]),
            transaction_closed=True, cache_entries=0, snapshots=[{
                "ranked_present": late, "ranked_count": 3 if d else 0, "ranked_tracked_count": 3 if d else 0,
                "route_count": 2 if stem else 1, "route_row_count": 6 if stem else 3,
                "native_union_rows": 3 if late else 0, "metadata_owner_rows": 3 if late and stem else 0,
                "candidate_count": 3, "use_stem": stem, "fuse_routes": job["case"] == "fused",
                "late_materialize": late, "tuple_route_owners_complete": True,
                "tuple_item_owners_complete": True, "native_union_owned_by_routes": True}])
    else:
        counters = g.Counters()
        report.update(phase_names=list(g.PHASES), counter_fields=list(g.COUNTER_FIELDS),
                      outside_cell_counters=counters.values[8], outside_cell_wrapper_calls=[0, 0],
                      before=snapshot(), after=snapshot(), cells=[])
        for index, expected in enumerate(bound["_expected_cells"]):
            count = len(expected["query_ids"])
            token = expected["configuration"] != "native-char4000"
            report["cells"].append({key: copy.deepcopy(value) for key, value in expected.items()
                                    if key != "expected_payload_sha256"})
            report["cells"][-1].update(payload_sha256=list(expected["expected_payload_sha256"]),
                attempted=count, completed=count, status="completed", counters=counters.values[index],
                wrapper_calls=[count, count] if token else [0, 0], before=snapshot(), after=snapshot(),
                transaction_closed=True, cache_entries=0)
    return report


class BookkeepingTests(unittest.TestCase):
    def test_preallocated_callback_only_updates_selected_cell_phase_generation(self):
        counter = g.Counters()
        counter.cell, counter.phase = 3, 2
        slot = counter.values[3][2][1]
        counter.callback("start", {"generation": 1})
        counter.callback("stop", {"generation": 1, "collected": 7, "uncollectable": 2})
        self.assertIs(slot, counter.values[3][2][1])
        self.assertEqual(slot, [1, 1, 7, 2])
        self.assertEqual(sum(sum(bucket) for cell in counter.values for phase in cell for bucket in phase), 11)
        for cell in counter.values:
            g.validate_counters(cell)

    def test_fixed_signatures_forward_same_objects_once_and_restore_phase(self):
        counter = g.Counters()
        counter.cell, counter.phase = 2, 1
        resolver, result = object(), object()
        calls = []

        def prepare(pages, turns, refs_by_page):
            calls.append((counter.phase, pages, turns, refs_by_page))
            return resolver

        def assemble(legacy, pages, query_terms, *, budget_chars, budget_tokens, counter, source_units_for=None):
            calls.append((holder.phase, legacy, pages, query_terms, budget_chars, budget_tokens, counter, source_units_for))
            return result

        holder = counter
        module = SimpleNamespace(prepare_source_units=prepare, assemble_with_count=assemble)
        first, second = g.forwarding_wrappers(module, counter)
        self.assertEqual(str(inspect.signature(first)), "(pages, turns, refs_by_page)")
        self.assertEqual(str(inspect.signature(second)),
            "(legacy, pages, query_terms, *, budget_chars, budget_tokens, counter, source_units_for=None)")
        values = [object() for _ in range(5)]
        self.assertIs(first(*values[:3]), resolver)
        self.assertEqual(counter.phase, 1)
        self.assertIs(second(*values[:3], budget_chars=8, budget_tokens=1, counter=values[3], source_units_for=resolver), result)
        self.assertEqual(counter.phase, 1)
        self.assertEqual([entry[0] for entry in calls], [2, 3])
        self.assertEqual(counter.calls[2], [1, 1])
        self.assertIs(calls[1][-1], resolver)
        self.assertIs(module.prepare_source_units, prepare)

    def test_wrapper_exception_restores_prior_phase_without_retry(self):
        counter = g.Counters()
        counter.phase = 1
        fail = mock.Mock(side_effect=LookupError("invented"))
        first, second = g.forwarding_wrappers(SimpleNamespace(prepare_source_units=fail, assemble_with_count=fail), counter)
        with self.assertRaises(LookupError):
            first(None, None, None)
        self.assertEqual(counter.phase, 1)
        with self.assertRaises(LookupError):
            second(None, None, None, budget_chars=1, budget_tokens=1, counter=None)
        self.assertEqual(counter.phase, 1)
        self.assertEqual(fail.call_count, 2)

    def test_owner_snapshot_only_returns_scalar_counts_without_retaining_rows(self):
        class Native:
            pass
        rows = [Native(), Native()]
        metadata = [Native(), Native()]
        values = {"routes": [rows], "rows": {"a": rows[0], "b": rows[1]},
                  "metadata_by_id": {"a": metadata[0], "b": metadata[1]},
                  "ranked_rows": [("a", 1.0, rows[0], metadata[0]), ("b", 0.5, rows[1], metadata[1])],
                  "candidate_count": 2, "use_stem": True, "fuse_routes": False, "late_materialize": True}
        with mock.patch.object(g.sqlite3, "Row", Native):
            result = g.owner_snapshot(values)
        self.assertTrue(all(type(value) in (int, bool) for value in result.values()))
        self.assertTrue(result["tuple_route_owners_complete"])
        self.assertTrue(result["tuple_item_owners_complete"])
        values["ranked_rows"][0] = ("a", 1.0, object(), object())
        with mock.patch.object(g.sqlite3, "Row", Native):
            result = g.owner_snapshot(values)
        self.assertFalse(result["tuple_route_owners_complete"])
        self.assertFalse(result["tuple_item_owners_complete"])

    def test_static_exact_one_clear_proof_without_importing_runtime(self):
        d = b"def recall():\n    if late_materialize:\n        candidate_count = len(ranked_rows)\n        for item in ranked_rows:\n            candidates.append(item)\n"
        e = d + b"        ranked_rows.clear()\n"
        g.verify_one_clear({"store.py": d, "other.py": b"pass"}, {"store.py": e, "other.py": b"pass"})
        for changed in (d, e + b"        ranked_rows.clear()\n", e.replace(b"candidates.append", b"other.append")):
            with self.assertRaises(ValueError):
                g.verify_one_clear({"store.py": d}, {"store.py": changed})
        with self.assertRaises(ValueError):
            g.verify_one_clear({"store.py": d, "other.py": b"pass"}, {"store.py": e, "other.py": b"changed"})

    def test_v032_probe_locals_do_not_have_candidate_count(self):
        values = {"routes": [[]], "rows": {}, "candidates": [{}, {}, {}], "use_stem": False, "fuse_routes": False}
        result = g.owner_snapshot(values)
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["ranked_count"], 0)
        self.assertFalse(result["ranked_present"])


class SavedAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="round5-gc-fixture-", dir=g.ROOT)
        self.addCleanup(temporary.cleanup)
        patch = mock.patch.object(g, "ROOT", Path(temporary.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.bound = binding_fixture()

    def worker(self, label="candidate-d"):
        job = next(job for job in self.bound["jobs"] if job["kind"] == "worker" and job["label"] == label)
        return job, report_fixture(self.bound, job)

    def check(self, job, report):
        g.validate_report(self.bound, job, report, "b" * 64)

    def test_fixed_nine_probes_and_three_full_workers(self):
        jobs = self.bound["jobs"]
        self.assertEqual([job["label"] for job in jobs[:9]], [label for label in g.SOURCES for _ in g.CASES])
        self.assertEqual([job["case"] for job in jobs[:9]], list(g.CASES) * 3)
        self.assertEqual(sum(job["expected_calls"] for job in jobs), 14205)
        self.assertEqual(sum(cell["query_count"] for cell in self.bound["cells"]), 4732)
        self.assertTrue(all("query_ids" not in cell and "expected_payload_sha256" not in cell for cell in self.bound["cells"]))
        for job in jobs:
            self.check(job, report_fixture(self.bound, job))

    def test_complete_prefix_requires_remote_only_at_corpus_boundary(self):
        for job in self.bound["jobs"]:
            g.publish_new(g.local(job["report"]), report_fixture(self.bound, job))
        with mock.patch.object(g, "committed") as committed:
            self.assertEqual(len(g.audit_prefix(self.bound, "b" * 64, 8)), 8)
            committed.assert_not_called()
            self.assertEqual(len(g.audit_prefix(self.bound, "b" * 64, 9)), 9)
            self.assertEqual(committed.call_count, 18)
        with mock.patch.object(g, "committed") as committed:
            self.assertEqual(len(g.audit_prefix(self.bound, "b" * 64, 12)), 12)
            self.assertEqual(committed.call_count, 24)

    def test_reordered_missing_and_changed_payloads_are_rejected(self):
        job, report = self.worker()
        for mutate in (lambda value: value["cells"].reverse(),
                       lambda value: value["cells"].pop(),
                       lambda value: value["cells"][0]["query_ids"].reverse(),
                       lambda value: value["cells"][0]["payload_sha256"].pop(),
                       lambda value: value["cells"][0]["payload_sha256"].__setitem__(0, "f" * 64)):
            changed = copy.deepcopy(report)
            mutate(changed)
            with self.assertRaises(ValueError):
                self.check(job, changed)

    def test_runtime_gc_and_lifecycle_pins_are_required(self):
        job, report = self.worker()
        for key, value in (("source", {}), ("python", {}), ("status", "failed"),
                           ("completed_calls", 4731), ("attempted_calls", 4732.0),
                           ("callbacks_restored", False), ("wrappers_restored", False),
                           ("gc_state_after", {}), ("inputs_verified_after", False), ("process_boundary", "same-heap")):
            changed = copy.deepcopy(report)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(job, changed)
        for key, value in (("transaction_closed", False), ("cache_entries", False), ("wrapper_calls", [0, 0]),
                           ("attempted", 168.0)):
            changed = copy.deepcopy(report)
            changed["cells"][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(job, changed)

    def test_unmatched_noninteger_negative_or_wrong_axis_counters_fail(self):
        job, report = self.worker()
        variants = ([1, 0, 0, 0], [True, True, 0, 0], [1, 1, -1, 0], [1, 1, 0])
        for bucket in variants:
            changed = copy.deepcopy(report)
            changed["cells"][0]["counters"][2][0] = bucket
            with self.assertRaises(ValueError):
                self.check(job, changed)
        changed = copy.deepcopy(report)
        changed["outside_cell_counters"].pop()
        with self.assertRaises(ValueError):
            self.check(job, changed)

    def test_boundary_stats_must_be_monotonic_and_cover_callbacks(self):
        before, after = snapshot(), snapshot()
        values = g.Counters().values[0]
        values[2][0] = [1, 1, 0, 0]
        with self.assertRaises(ValueError):
            g.validate_window(before, after, [values])
        after["stats"][0]["collections"] = 2
        g.validate_window(before, after, [values])
        before["stats"][1]["collected"] = 1
        with self.assertRaises(ValueError):
            g.validate_window(before, after, [values])

    def test_controller_execs_fresh_before_any_product_function(self):
        path = g.ROOT / "binding.json"
        g.publish_new(path, {"invented": "no corpus"})
        args = SimpleNamespace(binding=path, command="worker", label="candidate-d")
        with mock.patch.object(g, "load_binding", return_value=self.bound), \
             mock.patch.object(g, "audit_prefix", return_value=[{"large_previous_report": "discarded on exec"}]) as prefix, \
             mock.patch.object(g, "environment", return_value=self.bound["python"]), \
             mock.patch.object(g, "gc_state", return_value=self.bound["gc_state"]), \
             mock.patch.object(g.os, "execv") as execute, \
             mock.patch.object(g, "frequency_run") as frequency:
            g.execute(args)
        self.assertEqual(prefix.call_args.args[2], 10)
        execute.assert_called_once()
        self.assertIn("_run", execute.call_args.args[1])
        self.assertEqual(execute.call_args.args[1][-1], "10")
        frequency.assert_not_called()
        job = self.bound["jobs"][10]
        self.assertEqual(g.read(g.local(job["report"]))["attempted_calls"], 0)
        self.assertFalse((g.local(job["state"]) / "started.json").exists())

    def test_private_entry_requires_same_pid_claim_and_never_audits_prefix(self):
        job = self.bound["jobs"][9]
        path = g.ROOT / "binding.json"
        g.publish_new(path, {"invented": "no corpus"})
        g.local(job["state"]).mkdir(parents=True)
        report = report_fixture(self.bound, job)
        report.update(status="running", attempted_calls=0, completed_calls=0, attempt_id="wrong-controller")
        g.publish_new(g.local(job["report"]), report)
        with mock.patch.object(g, "load_binding", return_value=self.bound), \
             mock.patch.object(g, "audit_prefix") as prefix, \
             mock.patch.object(g, "frequency_run") as frequency:
            with self.assertRaisesRegex(ValueError, "same live controller"):
                g.internal_run(SimpleNamespace(binding=path, index=9))
        prefix.assert_not_called()
        frequency.assert_not_called()

    def test_private_started_marker_is_exclusive_before_product_call(self):
        job = self.bound["jobs"][9]
        path = g.ROOT / "binding.json"
        g.publish_new(path, {"invented": "no corpus"})
        g.local(job["state"]).mkdir(parents=True)
        report = report_fixture(self.bound, job)
        report.update(status="running", attempted_calls=0, completed_calls=0,
                      attempt_id=f"{g.file_sha(path)}:9:{g.os.getpid()}")
        g.publish_new(g.local(job["report"]), report)
        g.publish_new(g.local(job["state"]) / "started.json", {"already_started": True})
        with mock.patch.object(g, "load_binding", return_value=self.bound), \
             mock.patch.object(g, "frequency_run") as frequency:
            with self.assertRaises(FileExistsError):
                g.internal_run(SimpleNamespace(binding=path, index=9))
        frequency.assert_not_called()

    def test_private_failure_finally_saves_completed_slots_and_counters(self):
        job = self.bound["jobs"][9]
        path = g.ROOT / "binding.json"
        g.publish_new(path, {"invented": "no corpus"})
        g.local(job["state"]).mkdir(parents=True)
        report = report_fixture(self.bound, job)
        report.update(status="running", attempted_calls=0, completed_calls=0,
                      attempt_id=f"{g.file_sha(path)}:9:{g.os.getpid()}")
        g.publish_new(g.local(job["report"]), report)

        def fail(bound, job, report, checkpoint):
            report.update(attempted_calls=2, completed_calls=1)
            report["cells"][0]["payload_sha256"][1:] = [None] * 167
            report["cells"][0]["counters"][2][0] = [1, 1, 3, 0]
            raise RuntimeError("artificial failure; no query was made")

        with mock.patch.object(g, "load_binding", return_value=self.bound), \
             mock.patch.object(g, "environment", return_value=self.bound["python"]), \
             mock.patch.object(g, "gc_state", return_value=self.bound["gc_state"]), \
             mock.patch.object(g, "frequency_run", side_effect=fail), \
             mock.patch.object(g.signal, "signal"), \
             mock.patch.object(g, "audit_prefix") as prefix:
            with self.assertRaises(RuntimeError):
                g.internal_run(SimpleNamespace(binding=path, index=9))
        saved = g.read(g.local(job["report"]))
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["completed_calls"], 1)
        self.assertEqual(saved["error_type"], "RuntimeError")
        self.assertEqual(saved["cells"][0]["counters"][2][0], [1, 1, 3, 0])
        self.assertIsNone(saved["cells"][0]["payload_sha256"][1])
        self.assertTrue((g.local(job["state"]) / "started.json").exists())
        prefix.assert_not_called()

    def test_named_source_commit_and_file_set_are_checked_without_import(self):
        package = g.ROOT / "fake-src" / "memory_book"
        package.mkdir(parents=True)
        content = b"# artificial source, never imported\n"
        (package / "store.py").write_bytes(content)
        source_hash = g.runtime_hash({"store.py": content})

        def git(*args):
            if args[0] == "ls-tree":
                return b"src/memory_book/store.py\n"
            return content

        with mock.patch.object(g, "SOURCES", {"v032": ("invented-commit", source_hash)}), \
             mock.patch.object(g, "git", side_effect=git):
            self.assertEqual(g.verify_source("v032", "fake-src")["runtime_sha256"], source_hash)
            (package / "store.py").write_bytes(content + b"# changed\n")
            with self.assertRaises(ValueError):
                g.verify_source("v032", "fake-src")
            (package / "store.py").write_bytes(content)
            (package / "extra.py").write_bytes(b"# extra")
            with self.assertRaises(ValueError):
                g.verify_source("v032", "fake-src")

    def test_probe_owner_route_and_hash_boundaries_fail_closed(self):
        job = self.bound["jobs"][3]
        report = report_fixture(self.bound, job)
        for key, value in (("tuple_item_owners_complete", False), ("ranked_count", 0),
                           ("ranked_tracked_count", 4), ("fuse_routes", False),
                           ("candidate_count", 3.0), ("late_materialize", False)):
            changed = copy.deepcopy(report)
            changed["snapshots"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check(job, changed)
        changed = copy.deepcopy(report)
        changed["payload_sha256"] = "z" * 64
        with self.assertRaises(ValueError):
            self.check(job, changed)

    def test_probe_cross_source_equality_and_d_e_inventory(self):
        reports = [report_fixture(self.bound, self.bound["jobs"][index]) for index in (0, 3, 6)]
        g.compare_probes(reports)
        changed = copy.deepcopy(reports)
        changed[-1]["payload_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            g.compare_probes(changed)
        changed = copy.deepcopy(reports)
        changed[-1]["snapshots"][0]["metadata_owner_rows"] = 2
        with self.assertRaises(ValueError):
            g.compare_probes(changed)

    def test_fresh_state_report_and_partial_are_independent_no_replay_claims(self):
        job = self.bound["jobs"][0]
        g.refuse_replay(self.bound, 0)
        state = g.local(job["state"])
        state.mkdir(parents=True)
        with self.assertRaises(ValueError):
            g.refuse_replay(self.bound, 0)
        state.rmdir()
        path = g.local(job["report"])
        g.publish_new(path, report_fixture(self.bound, job))
        with self.assertRaises(ValueError):
            g.refuse_replay(self.bound, 0)
        path.unlink()
        g.publish_new(path.with_name(path.name + ".partial-0001"), {"invented": True})
        with self.assertRaises(ValueError):
            g.refuse_replay(self.bound, 0)

    def test_exclusive_creation_and_owned_failed_report_save_preserve_prefix(self):
        job, report = self.worker()
        path = g.local(job["report"])
        g.publish_new(path, report)
        with self.assertRaises(FileExistsError):
            g.publish_new(path, report)
        report.update(status="failed", completed_calls=10)
        report["cells"][0]["payload_sha256"][10:] = [None] * 158
        g.save_owned(path, report)
        saved = g.read(path)
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["completed_calls"], 10)
        self.assertEqual(saved["cells"][0]["payload_sha256"], report["cells"][0]["payload_sha256"])
        report["attempt_id"] = "different-process"
        with self.assertRaises(ValueError):
            g.save_owned(path, report)

    def test_support_uses_e_vs_d_exact_registered_domains(self):
        _, d = self.worker()
        _, e = self.worker("candidate-e")
        for report, count in ((d, 10), (e, 5)):
            for cell in report["cells"]:
                if cell["configuration"] != "native-char4000":
                    cell["counters"][2][0] = [count, count, 0, 0]
        result = g.decision(d, e)
        self.assertTrue(result["supported"])
        self.assertEqual(result["values_d_then_e"]["synthetic61_token_gen01"], [30, 15])
        changed = copy.deepcopy(e)
        changed["cells"][2]["counters"][2][0] = [10, 10, 0, 0]
        self.assertFalse(g.decision(d, changed)["supported"])
        changed = copy.deepcopy(e)
        changed["cells"][0]["counters"][1][0] = [100, 100, 0, 0]
        self.assertFalse(g.decision(d, changed)["supported"])
        changed = copy.deepcopy(e)
        changed["cells"][0]["counters"][1][2] = [1, 1, 0, 0]
        self.assertFalse(g.decision(d, changed)["supported"])
        changed = copy.deepcopy(e)
        changed["cells"][0]["counters"][0][2] = [100, 100, 0, 0]
        self.assertTrue(g.decision(d, changed)["supported"])

    def test_zero_to_zero_is_not_support_and_collected_is_not_frequency(self):
        _, d = self.worker()
        _, e = self.worker("candidate-e")
        d["cells"][2]["counters"][2][0][2] = 100000
        self.assertFalse(g.decision(d, e)["supported"])


if __name__ == "__main__":
    unittest.main()
