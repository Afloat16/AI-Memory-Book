"""Offline parser, attribution and completeness fixtures; no product invocation."""
from __future__ import annotations

import copy
import gzip
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts import round5_resource_diagnostic as diagnostic


def stat(pid, parent, start, comm="python (worker)"):
    # Field 3 starts after comm; ppid=field4, starttime=field22.
    fields = ["S", str(parent)] + ["0"] * 17 + [str(start)] + ["0"] * 4
    return f"{pid} ({comm}) " + " ".join(fields)


class ResourceDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(diagnostic.PLAN.read_text())

    def fake_process(self, root, pid, parent, start, *, rss=100, pss=60, private=40, children=(), second_thread=()):
        path = root / str(pid)
        (path / "task" / str(pid)).mkdir(parents=True)
        (path / "stat").write_text(stat(pid, parent, start))
        (path / "status").write_text(f"VmRSS:\t{rss} kB\nVmSize:\t900 kB\nThreads:\t2\n")
        (path / "comm").write_text("git\n" if pid != 10 else "python3\n")
        if pss is not None:
            (path / "smaps_rollup").write_text(f"Pss: {pss} kB\nPrivate_Clean: {private} kB\nPrivate_Dirty: 0 kB\n")
        (path / "task" / str(pid) / "children").write_text(" ".join(map(str, children)))
        if second_thread:
            task = path / "task" / str(pid + 1)
            task.mkdir()
            (task / "children").write_text(" ".join(map(str, second_thread)))

    def test_stat_comm_with_parentheses_and_spaces(self):
        self.assertEqual(diagnostic.parse_stat(stat(10, 9, 1234)), {"ppid": 9, "start_ticks": 1234})
        with self.assertRaises(ValueError):
            diagnostic.parse_stat("10 (short) S 9")

    def test_memory_units_are_not_guessed(self):
        self.assertEqual(diagnostic.parse_kib_fields("Pss: 7 kB\nVmRSS: 9 kB\nThreads: 2\nPss_Anon: nope kB\n"),
                         {"Pss": 7168, "VmRSS": 9216})

    def test_tree_includes_other_threads_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fake_process(root, 10, 1, 100, children=(20,), second_thread=(20, 30))
            self.fake_process(root, 20, 10, 200, rss=80, pss=30, private=20)
            self.fake_process(root, 30, 10, 300, rss=50, pss=25, private=10)
            result = diagnostic.tree_sample(10, root, root_start_ticks=100)
            self.assertEqual(result["enumerated_pids"], [10, 20, 30])
            self.assertEqual(result["tree_rss_bytes"], 230 * 1024)
            self.assertEqual(result["descendant_rss_bytes"], 130 * 1024)
            self.assertEqual(result["tree_pss_bytes"], 115 * 1024)
            self.assertTrue(result["pss_complete"])

    def test_unavailable_pss_is_null_not_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fake_process(root, 10, 1, 100, children=(20,))
            self.fake_process(root, 20, 10, 200, pss=None)
            result = diagnostic.tree_sample(10, root)
            self.assertEqual(result["tree_rss_bytes"], 200 * 1024)
            self.assertIsNone(result["tree_pss_bytes"])
            self.assertFalse(result["pss_complete"])
            self.assertIsNone(result["processes"][1]["private_bytes"])
            self.assertEqual(result["processes"][1]["pss_unavailable_reason"], "process_exited_or_unreadable")

    def test_pid_reuse_or_wrong_parent_does_not_enter_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fake_process(root, 10, 1, 100, children=(20,))
            self.fake_process(root, 20, 999, 200)
            result = diagnostic.tree_sample(10, root, root_start_ticks=100)
            self.assertEqual([value["pid"] for value in result["processes"]], [10])
            self.assertFalse(result["pss_complete"])
            reused = diagnostic.tree_sample(10, root, root_start_ticks=99)
            self.assertIsNone(reused["root_rss_bytes"])
            self.assertEqual(reused["processes"], [])

    def test_unreadable_children_marks_discovery_incomplete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fake_process(root, 10, 1, 100)
            (root / "10/task/10/children").unlink()
            result = diagnostic.tree_sample(10, root)
            self.assertEqual(result["root_rss_bytes"], 100 * 1024)
            self.assertFalse(result["discovery_complete"])
            self.assertFalse(result["pss_complete"])
            self.assertIsNone(result["tree_pss_bytes"])
            self.assertEqual(result["discovery_errors"][0]["operation"], "thread_children")

    def test_unreadable_task_enumeration_suppresses_tree_pss(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fake_process(root, 10, 1, 100)
            (root / "10/task/10/children").unlink()
            (root / "10/task/10").rmdir()
            (root / "10/task").rmdir()
            result = diagnostic.tree_sample(10, root)
            self.assertFalse(result["discovery_complete"])
            self.assertIsNone(result["tree_pss_bytes"])
            self.assertEqual(result["discovery_errors"][0]["operation"], "task_enumeration")

    def test_post_record_identity_failure_suppresses_tree_pss(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fake_process(root, 10, 1, 100)
            original = diagnostic.process_record
            def disappear_after_record(pid, proc):
                record = original(pid, proc)
                (proc / str(pid) / "stat").unlink()
                return record
            with patch.object(diagnostic, "process_record", side_effect=disappear_after_record):
                result = diagnostic.tree_sample(10, root)
            self.assertFalse(result["discovery_complete"])
            self.assertIsNone(result["tree_pss_bytes"])
            self.assertEqual(result["discovery_errors"][0]["operation"], "post_record_identity")

    def test_normalized_input_mutation_cannot_rebind_original_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions, queries = root / "sessions.jsonl", root / "queries.jsonl"
            sessions.write_text('{"fixture":"session"}\n')
            queries.write_text('{"fixture":"query"}\n')
            frozen = {"sessions_sha256": diagnostic.file_hash(sessions), "queries_sha256": diagnostic.file_hash(queries)}
            saved = dict(frozen)
            diagnostic.verify_normalized_inputs(sessions, queries, frozen)
            queries.write_text('{"fixture":"changed"}\n')
            with self.assertRaisesRegex(ValueError, "original preparation"):
                diagnostic.verify_normalized_inputs(sessions, queries, frozen)
            self.assertEqual(frozen, saved)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux process-group/proc fixture")
    def test_cleanup_kills_descendant_after_leader_exits_with_stdout_open(self):
        # A separate watchdog bounds this fixture even if the original reader-
        # thread close deadlock returns. It never imports Book or runs retrieval.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state, ready = root / "pids.json", root / "ready"
            child_code = ("import signal,time;from pathlib import Path;"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                f"Path({str(ready)!r}).write_text('ready');time.sleep(60)")
            leader_code = ("import os,json,subprocess,sys,time;from pathlib import Path;"
                f"state=Path({str(state)!r});state.write_text(json.dumps({{'root':os.getpid()}}));"
                f"child=subprocess.Popen([sys.executable,'-c',{child_code!r}]);"
                "state.write_text(json.dumps({'root':os.getpid(),'child':child.pid}));"
                f"ready=Path({str(ready)!r});deadline=time.monotonic()+10;"
                "\nwhile not ready.exists() and time.monotonic()<deadline:time.sleep(.01)"
                "\nos._exit(0 if ready.exists() else 10)")
            command = [sys.executable, "-u", "-c", leader_code]
            driver = ("import json,os;from pathlib import Path;"
                "from scripts import round5_resource_diagnostic as d;"
                "plan=json.loads(d.PLAN.read_text());"
                f"result=d.observe({command!r},Path({str(root / 'fixture')!r}),plan,False,dict(os.environ),2.0);"
                "print(json.dumps(result))")
            started = time.monotonic()
            try:
                observed = subprocess.run([sys.executable, "-c", driver], cwd=diagnostic.ROOT,
                    capture_output=True, text=True, timeout=8, check=True)
                result = json.loads(observed.stdout)
                self.assertEqual(result["status"], "failed-incomplete")
                self.assertEqual(result["exit_code"], 0)
                self.assertIn("stdout", result["failure_check"])
                self.assertTrue(result["cleanup"]["term_sent"])
                self.assertTrue(result["cleanup"]["kill_sent"])
                self.assertTrue(result["cleanup"]["leader_reaped"])
                self.assertLess(time.monotonic() - started, 8)
                child = json.loads(state.read_text())["child"]
                child_stat = Path("/proc") / str(child) / "stat"
                if child_stat.exists():
                    value = child_stat.read_text()
                    self.assertEqual(value[value.rfind(")") + 1:].split()[0], "Z")
            finally:
                if state.exists():
                    try:
                        os.killpg(json.loads(state.read_text())["root"], signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_phase_crossing_is_never_assigned_to_product(self):
        events = [{"event": "phase_start", "phase": "product_queries", "monotonic_ns": 100},
                  {"event": "phase_end", "phase": "product_queries", "monotonic_ns": 200}]
        self.assertEqual(diagnostic.phase_at({"started_monotonic_ns": 50, "finished_monotonic_ns": 60}, events), "spawn")
        self.assertEqual(diagnostic.phase_at({"started_monotonic_ns": 90, "finished_monotonic_ns": 110}, events), "transition")
        self.assertEqual(diagnostic.phase_at({"started_monotonic_ns": 110, "finished_monotonic_ns": 190}, events), "product_queries")
        self.assertEqual(diagnostic.phase_at({"started_monotonic_ns": 210, "finished_monotonic_ns": 220}, events), "between_phases")
        self.assertEqual(diagnostic.phase_at({"boundary": "end", "phase": "product_queries"}, events), "product_queries")

    def test_summaries_retain_peak_child_identity_and_missing_pss(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "trace.gz"
            samples = []
            for index, total in enumerate((100, 180)):
                samples.append({"phase": "product_queries", "boundary": "start" if index == 0 else "end",
                    "root_rss_bytes": 100, "root_pss_bytes": 60, "tree_rss_bytes": total,
                    "descendant_rss_bytes": total - 100, "tree_pss_bytes": 60 if index == 0 else None,
                    "pss_complete": index == 0, "processes": [{"pid": 10}, {"pid": 20}] if index else [{"pid": 10}]})
            with gzip.open(path, "wt") as stream:
                for sample in samples:
                    stream.write(json.dumps(sample) + "\n")
            result = diagnostic.summarize_trace(path, [])
            phase = result["product_queries"]
            self.assertEqual(phase["samples"], 2)
            self.assertEqual(phase["complete_pss_samples"], 1)
            self.assertEqual(phase["peaks"]["tree_rss_bytes"]["sample_index"], 1)
            self.assertEqual(phase["peaks"]["tree_rss_bytes"]["processes"][1]["pid"], 20)

    def test_registered_subset_has_no_new_or_duplicate_ids(self):
        manifest = json.loads((diagnostic.ROOT / self.plan["corpus"]["manifest"]).read_text())
        ids = diagnostic.selected_ids(manifest, self.plan)
        self.assertEqual(len(ids), 32)
        self.assertTrue(set(ids) <= set(manifest["selected_ids"]))
        self.assertEqual(diagnostic.digest(ids), "41bd02edc9e0e63a2217b1e006537de068281ac9b4345716e0f55f5b87087a9b")
        diagnostic.validate_plan(self.plan)
        wrong = copy.deepcopy(self.plan)
        wrong["product"]["total_recall_calls"] = 255
        with self.assertRaisesRegex(ValueError, "counts"):
            diagnostic.validate_plan(wrong)

    def test_host_guard_rejects_rerun(self):
        environment = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_REPOSITORY": diagnostic.REPOSITORY,
                       "GITHUB_REF": diagnostic.TRIGGER, "GITHUB_EVENT_NAME": "push"}
        with patch.dict("os.environ", environment, clear=True), self.assertRaises(ValueError):
            diagnostic.actions_identity()

    def test_phase_boundary_acknowledgements_preserve_failed_body(self):
        with patch.object(diagnostic.sys, "stdin", io.StringIO("continue\ncontinue\n")), patch.object(diagnostic, "emit") as emit:
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                with diagnostic.phase("product_close"):
                    raise RuntimeError("fixture")
        self.assertEqual([call.args[0] for call in emit.call_args_list], ["phase_start", "phase_end"])
        with patch.object(diagnostic.sys, "stdin", io.StringIO("")), patch.object(diagnostic, "emit"):
            with self.assertRaisesRegex(ValueError, "Observer"):
                with diagnostic.phase("product_close"):
                    self.fail("Missing observer acknowledgement must stop the worker")

    def worker_fixture(self, name, ids):
        return {"name": name, "status": "completed", "calls_started": len(ids), "calls_finished": len(ids),
            "query_results": [{"id": identity, "payload_sha256": diagnostic.digest(identity)} for identity in ids],
            "phases": {"fixture": {"samples": 2, "complete_pss_samples": 1}}}

    def test_assessment_rejects_reordered_or_mismatched_outputs(self):
        ids = [f"old-{index}" for index in range(32)]
        names = ["evaluator"] + [f"r{index}-{label}" for index, pair in enumerate(diagnostic.ORDER) for label in pair]
        results = [self.worker_fixture(name, [] if index == 0 else ids) for index, name in enumerate(names)]
        self.assertEqual(diagnostic.assess(results, ids, self.plan)["product_calls"], 256)
        wrong = copy.deepcopy(results)
        wrong[-1]["query_results"][0]["payload_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "outputs"):
            diagnostic.assess(wrong, ids, self.plan)
        wrong = copy.deepcopy(results)
        wrong[1], wrong[2] = wrong[2], wrong[1]
        with self.assertRaisesRegex(ValueError, "order"):
            diagnostic.assess(wrong, ids, self.plan)

    def test_incomplete_or_unmeasured_phase_is_rejected(self):
        phases = self.plan["evaluator_only"]["phases"]
        events = [{"event": kind, "phase": phase} for phase in phases for kind in ("phase_start", "phase_end")]
        events.append({"event": "done"})
        observed = {phase: {"samples": 2, "root_unreadable": 0} for phase in phases}
        self.assertEqual(diagnostic.validate_events(events, observed, False, self.plan), [])
        observed[phases[-1]]["root_unreadable"] = 1
        with self.assertRaisesRegex(ValueError, "RSS"):
            diagnostic.validate_events(events, observed, False, self.plan)
        with self.assertRaisesRegex(ValueError, "phase"):
            diagnostic.validate_events(events[1:], observed, False, self.plan)


if __name__ == "__main__":
    unittest.main()
