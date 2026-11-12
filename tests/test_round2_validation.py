import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmarks.data import Dataset, Evidence, QueryCase
from benchmarks.round2_eval import (Ledger, PLAN, ROOT, component, component_hits, digest, export, groups_for,
    native, native_configurations, sha, stages, summary_of, write_report)
from benchmarks.round2_resources import storage, tree_rss
from benchmarks.token_compare import latency_summary
from scripts.summarize_round2_validation import verify_configurations, verify_samples
from scripts import run_round2_validation as controller


class RoundTwoValidationTests(unittest.TestCase):
    def test_registered_axes_remain_complete(self):
        plan = json.loads(PLAN.read_bytes())
        configs = native_configurations(plan)
        self.assertEqual(len(configs), 12)
        self.assertEqual(len({tuple(config.values()) for config in configs}), 12)
        self.assertEqual(len(stages(plan, {"optional_semantic": False})), 8)
        self.assertEqual(len(stages(plan, {"optional_semantic": True})), 10)
        self.assertEqual(plan["cohort"]["queries"] * len(configs), 3072)

    def test_diagnostic_chapters_use_external_session_ids(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE sessions(id TEXT,project_id TEXT,external_id TEXT,chapter_id TEXT)")
            db.executemany("INSERT INTO sessions VALUES(?,?,?,?)", [("internal-a", "p", "s1", "c1"),
                ("internal-b", "p", "s2", "c2"), ("internal-other", "other", "s1", "c3")])
            data = Dataset(1, "fixture", queries=[QueryCase("q", "accessible accommodation", "fixture", "p",
                (Evidence("s1", 0, "large print"), Evidence("s2", 0, "audio guides")))])
            result = groups_for(data, SimpleNamespace(db=db))["q"]
            self.assertEqual(result["required_chapters"], 2)
            self.assertIn("cross_chapter", result["diagnostic_groups"])
            self.assertIn("low_lexical_overlap_le_0.25", result["diagnostic_groups"])

    def test_resource_accounting_includes_descendants_but_excludes_harness_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc = root / "proc"
            for pid, rss, children in ((10, 12, "11 12"), (11, 7, ""), (12, 8, "10")):
                path = proc / str(pid)
                (path / "task" / str(pid)).mkdir(parents=True)
                (path / "status").write_text(f"VmRSS: {rss} kB\n")
                (path / "task" / str(pid) / "children").write_text(children)
            self.assertEqual(tree_rss(10, proc), (27 * 1024, 3))
            state = root / "state"
            state.mkdir()
            for name, size in (("native.db", 13), ("native.db-wal", 5), ("native.db-shm", 7), ("attempts.jsonl", 999)):
                (state / name).write_bytes(b"x" * size)
            (state / "model-cache").symlink_to(proc, target_is_directory=True)
            result = storage(state, ("attempts.jsonl",))
            self.assertEqual(result["regular_file_bytes"], 25)
            self.assertEqual(result["sqlite_main_file_bytes"], 13)
            self.assertEqual(result["sqlite_wal_file_bytes"], 5)
            self.assertEqual(result["sqlite_shm_file_bytes"], 7)

    def component_report(self, path):
        report = {"stage": "ai-memory-hybrid", "timing_rows": [], "configurations": []}
        ledger = Ledger(path)
        for repetition in range(3):
            for identity in ("q1", "q2"):
                seq = ledger.start(report["stage"], "search", repetition, identity)
                reads = 2 if repetition == 0 else 0
                row = {"id": identity, "repetition": repetition, "status": "ok", "hit_ids": ["p1", "p2"],
                    "native_hit_ids": ["p1", "p2"], "native_result_id_sha256": ["b" * 64, "c" * 64],
                    "unmapped_native_hits": 0, "read_calls": reads, "read_ms": reads * 2,
                    "read_payload_sha256": ["a" * 64] * reads, "search_ms": 1, "bridge_ms": 1.5}
                ledger.finish(seq, row)
                report["timing_rows"].append(row)
        ledger.close()
        report.update(attempt_states=[json.loads(line) for line in path.read_text().splitlines()],
                      attempts_started=ledger.started, attempts_finished=ledger.finished, ledger_sha256=sha(path))
        report.update(native_search_latency=latency_summary([1] * 6),
            adapter_roundtrip_latency=latency_summary([1.5] * 6),
            first_pass_roundtrip_latency=latency_summary([1.5] * 2),
            repeat_roundtrip_latency=latency_summary([1.5] * 4),
            first_pass_search_plus_all_reads_latency=latency_summary([5.5] * 2))
        return report

    def test_missing_attempts_unmapped_ids_and_invented_latency_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = {"common": {"repeats": 3}}
            report = self.component_report(Path(directory) / "attempts.jsonl")
            verify_samples(report, plan, ["q1", "q2"])
            incomplete = copy.deepcopy(report)
            incomplete["timing_rows"].pop()
            with self.assertRaisesRegex(ValueError, "Missing, duplicated or unfinished"):
                verify_samples(incomplete, plan, ["q1", "q2"])
            altered = copy.deepcopy(report)
            altered["first_pass_search_plus_all_reads_latency"]["p95_ms"] = 99
            with self.assertRaisesRegex(ValueError, "latency summary differs"):
                verify_samples(altered, plan, ["q1", "q2"])
            unmapped = copy.deepcopy(report)
            unmapped["timing_rows"][0]["unmapped_native_hits"] = 1
            unmapped["attempt_states"][1]["unmapped_native_hits"] = 1
            from benchmarks.component_eval import canonical_json
            unmapped["ledger_sha256"] = hashlib.sha256("".join(canonical_json(row) + "\n"
                for row in unmapped["attempt_states"]).encode()).hexdigest()
            with self.assertRaisesRegex(ValueError, "Invalid native metadata"):
                verify_samples(unmapped, plan, ["q1", "q2"])

    def test_native_configuration_omission_is_rejected(self):
        plan = json.loads(PLAN.read_bytes())
        with self.assertRaisesRegex(ValueError, "Configuration axis/order changed"):
            verify_configurations({"stage": "candidate-native", "configurations": []}, plan, ["q1"])

    def test_summary_is_exact_projection_and_preserves_negative_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.component_report(Path(directory) / "ledger")
            report["validation"] = {"passed": False, "failures": [{"check": "intentional-fixture"}]}
            report["configurations"] = [{"metrics": {"complete_evidence_rate": 0}, "query_results": [{"id": "q1"}]}]
            prefix = Path(directory) / "report"
            write_report(report, prefix)
            import gzip
            raw = gzip.decompress(Path(str(prefix) + ".json.gz").read_bytes())
            summary = json.loads(Path(str(prefix) + ".summary.json").read_bytes())
            self.assertEqual(summary, summary_of(json.loads(raw), hashlib.sha256(raw).hexdigest()))
            self.assertNotIn("attempt_states", summary)
            self.assertFalse(summary["validation"]["passed"])
            self.assertEqual(summary["configurations"][0]["metrics"]["complete_evidence_rate"], 0)

    def test_unknown_native_page_aborts_before_common_packing(self):
        class Counter:
            def __init__(self, name):
                self.name = name
        class Engine:
            metadata = {}
            def search(self, *_):
                return {"hit_ids": ["unknown"], "results": [{"ref": "unknown"}]}
            def close(self):
                self.metadata["closed"] = True
        data = Dataset(1, "fixture", queries=[QueryCase("q", "fixture query", "fixture", "p")])
        engine = Engine()
        with tempfile.TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "attempts")
            try:
                with patch("benchmarks.round2_eval.TokenCounter", Counter), patch(
                        "benchmarks.round2_eval.component_engine", return_value=(engine, None)):
                    with self.assertRaisesRegex(ValueError, "unmapped page ID"):
                        component(SimpleNamespace(stage="billion-context"), {"common": {"repeats": 3},
                            "cohort": {"seed": 1}}, {}, data, {"documents": []}, {}, ledger,
                            SimpleNamespace(set_phase=lambda _: None))
                self.assertEqual(ledger.started, 1)
                self.assertEqual(ledger.finished, 0)
                self.assertTrue(engine.metadata["closed"])
            finally:
                ledger.close()

    def test_native_metadata_consumes_slots_and_payload_without_source_credit(self):
        documents = {"page": {"project": "p"}}
        response = {"hit_ids": [None, "page", None], "results": [
            {"id": 71, "project": "p", "workspace": "benchmark"},
            {"id": 72, "project": "p", "workspace": "benchmark"},
            {"id": 73, "project": "p", "workspace": "benchmark"}]}
        native_ids, mapped, hashes = component_hits(response, documents, "p", "ai-memory-hybrid")
        self.assertEqual(native_ids, [None, "page", None])
        self.assertEqual(mapped, ["page"])
        self.assertEqual(len(set(hashes)), 3)
        response["results"][0]["project"] = "other"
        with self.assertRaisesRegex(ValueError, "scope differs"):
            component_hits(response, documents, "p", "ai-memory-hybrid")

    def test_stage_publication_preserves_private_files_and_refuses_another_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root, remote = Path(directory) / "repo", Path(directory) / "remote.git"
            root.mkdir()
            def git(*arguments):
                return subprocess.check_output(["git", *arguments], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()
            git("init", "--bare", str(remote))
            git("init")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--allow-empty", "-m", "initial")
            git("remote", "add", "origin", str(remote))
            parent = git("rev-parse", "HEAD")
            checkpoint = root / "benchmarks/reports/round2-123-1-checkpoint.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text('{"status":"running"}')
            result_dir = root / "benchmarks/results/round2-123-1"
            result_dir.mkdir(parents=True)
            (result_dir / "baseline-native.summary.json").write_text('{}')
            (result_dir / "private-log.txt").write_text('must stay local')
            private = root / ".artifacts/private-source.txt"
            private.parent.mkdir()
            private.write_text('must stay local')
            env = {"GITHUB_REPOSITORY": "Afloat16/AI-Memory-Book", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
            with patch.object(controller, "ROOT", root), patch.dict(os.environ, env):
                published = controller.publish(checkpoint, result_dir, parent)
                names = git("ls-tree", "--name-only", "-r", published).splitlines()
                self.assertEqual(names, ['benchmarks/reports/round2-123-1-checkpoint.json',
                    'benchmarks/results/round2-123-1/baseline-native.summary.json'])
                self.assertEqual(git("diff", "--name-only", "--cached"), "")
                self.assertEqual(git("rev-parse", "HEAD"), parent)
                with self.assertRaisesRegex(ValueError, "Another writer changed"):
                    controller.publish(checkpoint, result_dir, parent)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "optional reference tokenizer not installed")
    def test_invented_archive_native_and_component_survive_strict_assessment(self):
        if os.environ.get("ROUND2_FIXTURE_WORKER") != "1":
            result = subprocess.run([sys.executable, "-m", "unittest",
                "tests.test_round2_validation.RoundTwoValidationTests.test_invented_archive_native_and_component_survive_strict_assessment"],
                cwd=ROOT, env={**os.environ, "ROUND2_FIXTURE_WORKER": "1", "PYTHONPATH": str(ROOT / "src")},
                capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        import memory_book
        self.assertEqual(Path(memory_book.__file__).resolve().parent, ROOT / "src/memory_book")
        from benchmarks.run import engine_source_hash
        from benchmarks.token_compare import checkout_provenance
        source = ROOT / "src/memory_book"
        pin = {"commit": checkout_provenance(source)["git_commit"], "source_sha256": engine_source_hash(source)}
        plan = json.loads(PLAN.read_bytes())
        plan["baseline"] = pin
        data = Dataset(1, "fixture")
        for index, fact in enumerate(("The amber ferry departs at sunrise.", "The blue ferry departs at noon.")):
            data.sessions.append({"project": "fixture", "session_id": f"s{index}",
                "title": f"Ferry {index}", "task_id": f"task{index}", "task_title": f"Route {index}",
                "created_at": f"2025-01-0{index+1}T09:00:00Z", "messages": [{"role": "user", "content": fact}]})
            data.queries.append(QueryCase(f"q{index}", f"When does the {'amber' if index == 0 else 'blue'} ferry depart?",
                "fixture", "fixture", (Evidence(f"s{index}", 0, fact),)))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            args = SimpleNamespace(state=base / "export", source=ROOT / "src", bundle=base / "bundle.json",
                frozen_db=base / "export/frozen.db", model_dir=None, cache=base / "cache", stage="export")
            args.state.mkdir()
            resource = SimpleNamespace(set_phase=lambda _: None)
            exported = {}
            export(args, plan, {"candidate": pin}, data, exported, resource)
            self.assertTrue(exported["validation"]["passed"])
            bundle = json.loads(args.bundle.read_bytes())
            for stage, function in (("baseline-native", native), ("baseline-component", component)):
                args.stage, args.state = stage, base / stage
                args.state.mkdir()
                ledger = Ledger(args.state / "attempts.jsonl")
                report = {"stage": stage, "timing_rows": [], "configurations": []}
                try:
                    function(args, plan, {"candidate": pin}, data, bundle, report, ledger, resource)
                finally:
                    ledger.close()
                report.update(attempt_states=[json.loads(line) for line in
                    (args.state / "attempts.jsonl").read_text().splitlines()], attempts_started=ledger.started,
                    attempts_finished=ledger.finished, ledger_sha256=sha(args.state / "attempts.jsonl"))
                self.assertTrue(report["validation"]["passed"], report["validation"])
                verify_samples(report, plan, ["q0", "q1"])
                verify_configurations(report, plan, ["q0", "q1"])


if __name__ == "__main__":
    unittest.main()
