"""Native-vs-native evaluator, frozen identity, ledger and preservation contracts."""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import native_core_performance as perf
from scripts import native_core_preserve as preserve


def plan():
    value = perf.read(perf.ROOT / "benchmarks/experiments/native_core_formal_plan.json")
    value["sources"]["candidate"]["commit"] = "a" * 40
    value["native_helper_calls"] = {label: dict.fromkeys(names, 1) for label, names in perf.PROBE_HELPERS.items()}
    calls = 2 * 4 * 3 * len(perf.CONFIGS) * sum(item["queries"] for item in perf.COHORTS.values())
    value.update(expected_timed_calls=calls, expected_paired_calls=calls // 2)
    return value


def fixture(directory):
    specification = plan()
    manifests = {label: {**source, "source_files": {
        "setup.py": ("a" if label == "baseline" else "d") * 64,
        "src/memory_book/_native.c": "f" * 64,
        **({"src/memory_book/_native_fixture.h": "8" * 64} if label == "candidate" else {})},
        "native_binaries": {"src/memory_book/_native.test.so": ("b" if label == "baseline" else "c") * 64}}
        for label, source in specification["sources"].items()}
    build = {"schema_version": 3, "status": "completed", "workflow_commit": "d" * 40,
             "workflow_run_id": "123", "workflow_run_attempt": 1, "host_preparation_sha256": "e" * 64,
             "builds": {label: {"status": "completed", "source_commit": source["commit"], "backend": "native",
                "command": ["python", "setup.py", "build_ext", "--inplace"], "compiler": "fixture gcc",
                "flags": {"extra_compile_args": ["-O3"]}, "build_log_sha256": "f" * 64,
                "native_binaries": source["native_binaries"],
                "build_inputs": {name: value for name, value in source["source_files"].items() if name in perf.BUILD_FILES},
                "native_source_inputs": {name: value for name, value in source["source_files"].items()
                    if Path(name).suffix in {".c", ".h"}}} for label, source in manifests.items()}}
    identities = {name: [f"{name}-q{i}" for i in range(value["queries"])] for name, value in perf.COHORTS.items()}
    run = {"protocol": perf.PROTOCOL, "plan": specification, "schedule": perf.schedule(specification),
           "sources": manifests, "query_ids": identities, "cohorts": {name: {"fixture": name} for name in identities},
           "ingestion_order": {name: [{"project": name, "session_id": "fixture"}] for name in identities},
           "build_manifest": build, "evaluator_commit": "d" * 40,
           "evaluator": {"scripts/native_core_host.py": "e" * 64}}
    perf.write(directory / "run.json", run)
    reports = []
    for item in run["schedule"]:
        source = manifests[item["label"]]
        helpers = specification["native_helper_calls"][item["label"]]
        report = {**item, "status": "completed", "source_unchanged": True, "run_sha256": perf.digest(run),
            "source_manifest_sha256": perf.digest(source), "runtime_import_ms": 1.0,
            "resources": {"fresh_ingestion_ms": 2.0, "unchanged_reingestion_ms": 1.0},
            "backend": {"requested": "native", "actual": "native", "binary_sha256": next(iter(source["native_binaries"].values())),
                "available_functions": sorted(helpers), "dispatch_probe": {"native_helper_calls": helpers,
                "outputs_sha256": "0" * 64, "instrumentation_restored": True,
                "uninstrumented_outputs_sha256": "0" * 64, "per_helper_outputs_sha256": dict.fromkeys(helpers, "0" * 64)},
                "wrapper_bindings": dict.fromkeys(("text",) if item["label"] == "baseline"
                    else ("text", "store", "segmentation", "token_budget"), True)},
            "dataset": {"fixture": item["cohort"]}, "archive_before": {"fixture": item["cohort"]},
            "archive_after": {"fixture": item["cohort"]}, "configurations": [],
            "ingestion_stage": "completed",
            "ingestion_order_sha256": perf.digest(run["ingestion_order"][item["cohort"]]),
            "ingestion_results": [{"id": "ingest-" + item["cohort"], "skipped": False}],
            "unchanged_reingestion_results": [{"id": "ingest-" + item["cohort"], "skipped": True}]}
        report["ingestion_sha256"] = perf.digest(report["ingestion_results"])
        report["unchanged_reingestion_sha256"] = perf.digest(report["unchanged_reingestion_results"])
        perf.write(directory / (item["key"] + ".started.json"), {"worker": item, "run_sha256": perf.digest(run)})
        ledger = perf.Ledger(directory / (item["key"] + ".attempts.jsonl.gz"))
        for index, config_id in enumerate(specification["configurations"]):
            order = perf.query_order(identities[item["cohort"]], item["round"], index)
            rows = []
            for attempt in order:
                row = {**attempt, "category": "fixture", "wall_ms": 1.0, "calling_process_cpu_ms": 0.5,
                    "payload_sha256": "3" * 64, "native_payload_sha256": "4" * 64, "context_sha256": "5" * 64,
                    "envelope_sha256": "6" * 64 if config_id.startswith("mcp-") else None,
                    "context_chars": 12, "context_tokens": None, "result_count": 1,
                    "invariants": {key: 0 for key in perf.INVARIANT_KEYS}}
                rows.append(row)
                ledger.event("started", config_id, row["query_id"], row["repetition"])
                ledger.event("finished", config_id, row["query_id"], row["repetition"], row)
            report["configurations"].append({"id": config_id, **perf.CONFIGS[config_id], "rows": rows,
                "query_order_sha256": perf.digest(order), "latency": perf.summary([1.0] * len(rows)),
                "resources": {"tool_schema_sha256": "7" * 64, "instructions_sha256": "8" * 64}})
        ledger.close()
        report["ledger_sha256"] = perf.sha((directory / (item["key"] + ".attempts.jsonl.gz")).read_bytes())
        perf.write(directory / (item["key"] + ".json.gz"), report)
        reports.append(report)
    return run, reports


class PlanAndSourceTests(unittest.TestCase):
    def test_full_native_matrix_is_fixed_to_released_baseline(self):
        value = perf.validate_plan(plan())
        self.assertEqual(value["expected_timed_calls"], 113568)
        self.assertEqual(value["expected_paired_calls"], 56784)
        for label in ("baseline", "candidate"):
            changed = plan()
            changed["sources"][label]["backend"] = "python"
            with self.subTest(label=label), self.assertRaises(ValueError):
                perf.validate_plan(changed)
        changed = plan()
        changed["sources"]["baseline"]["commit"] = "b" * 40
        with self.assertRaises(ValueError):
            perf.validate_plan(changed)
        for commit in ("UNFROZEN", perf.BASELINE):
            changed = plan()
            changed["sources"]["candidate"]["commit"] = commit
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                perf.validate_plan(changed)

    def test_no_cohort_secondary_cell_pass_or_output_field_can_be_dropped(self):
        for key, value in (("cohorts", ["synthetic61"]), ("configurations", list(perf.CONFIGS)[:2]),
                ("repetitions_per_worker", 1), ("excluded_native_response_fields", ["latency_ms", "source_refs"]),
                ("engine_order", [["baseline", "candidate"]] * 4), ("primary", ["native-char2400"]),
                ("secondary", []), ("expected_timed_calls", 1)):
            changed = plan()
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                perf.validate_plan(changed)

    def test_each_side_requires_every_native_helper(self):
        for label in ("baseline", "candidate"):
            changed = plan()
            changed["native_helper_calls"][label]["terms_ascii"] = 0
            with self.subTest(label=label), self.assertRaises(ValueError):
                perf.validate_plan(changed)
        changed = plan()
        del changed["native_helper_calls"]["candidate"]["literal_positions"]
        with self.assertRaises(ValueError):
            perf.validate_plan(changed)

    def test_guard_fallback_is_rejected_and_instrumentation_is_restored(self):
        for helpers in perf.PROBE_HELPERS.values():
            native = SimpleNamespace(**{name: (lambda *args: None) for name in helpers})
            text = SimpleNamespace(_NATIVE=native)
            originals = vars(native).copy()
            with patch.object(perf, "common_probe_suite", return_value=[]):
                with self.assertRaisesRegex(ValueError, "dispatch counts"):
                    perf.dispatch_probe(text, native, dict.fromkeys(helpers, 1))
            self.assertIs(text._NATIVE, native)
            self.assertTrue(all(getattr(native, name) is value for name, value in originals.items()))
            calls = []
            def fail_after_wrapping():
                calls.append(1)
                if len(calls) > 1:
                    raise RuntimeError("probe failure")
                return []
            with patch.object(perf, "common_probe_suite", side_effect=fail_after_wrapping):
                with self.assertRaisesRegex(RuntimeError, "probe failure"):
                    perf.dispatch_probe(text, native, dict.fromkeys(helpers, 1))
            self.assertTrue(all(getattr(native, name) is value for name, value in originals.items()))

    def test_single_helper_instrumentation_proves_every_helper_and_output_identity(self):
        for helpers in perf.PROBE_HELPERS.values():
            native = SimpleNamespace(**{name: (lambda *args: "same") for name in helpers})
            text = SimpleNamespace(_NATIVE=native)
            def suite():
                return [getattr(native, name)() for name in helpers]
            with patch.object(perf, "common_probe_suite", side_effect=suite):
                result = perf.dispatch_probe(text, native, dict.fromkeys(helpers, 1))
            self.assertEqual(result["native_helper_calls"], dict.fromkeys(helpers, 1))
            self.assertEqual(result["per_helper_outputs_sha256"], dict.fromkeys(helpers, result["outputs_sha256"]))
            self.assertTrue(result["instrumentation_restored"])

    def test_query_timing_invariant_and_ledger_cores_remain_frozen(self):
        old_tree = ast.parse((perf.ROOT / "scripts/native_incremental_performance.py").read_text())
        new_tree = ast.parse((perf.ROOT / "scripts/native_core_performance.py").read_text())
        names = ("mcp_calls", "Ledger", "validate_response", "make_row", "summary",
                 "archive_state", "query_order", "stable", "schedule")
        old = {node.name: node for node in old_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        new = {node.name: node for node in new_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for name in names:
            self.assertEqual(ast.dump(old[name], include_attributes=False),
                             ast.dump(new[name], include_attributes=False), name)

    def test_c_source_build_configuration_and_binary_are_bound_for_both_labels(self):
        blobs = {"src/memory_book/__init__.py": b"# package\n", "src/memory_book/_native.c": b"/* native source */\n",
                 "setup.py": b"# build flags\n", "src/memory_book/_native_fixture.h": b"/* compiled header */\n"}
        def fake_git(*args):
            if args[0] == "ls-tree":
                return ("\n".join(blobs) + "\n").encode()
            return blobs[args[1].split(":", 1)[1]]
        for label, specification in plan()["sources"].items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary, patch.object(perf, "git", fake_git):
                root = Path(temporary)
                for name, raw in blobs.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                binary = root / "src/memory_book/_native.test.so"
                binary.write_bytes(b"binary fixture")
                manifest = perf.source_manifest(root / "src", specification)
                perf.verify_source(root / "src", manifest)
                binary.write_bytes(b"another binary")
                with self.assertRaisesRegex(ValueError, "binary changed"):
                    perf.verify_source(root / "src", manifest)
                binary.write_bytes(b"binary fixture")
                (root / "setup.py").write_bytes(b"different build flags")
                with self.assertRaisesRegex(ValueError, "differs from source commit"):
                    perf.source_manifest(root / "src", specification)
                (root / "setup.py").write_bytes(blobs["setup.py"])
                header = root / "src/memory_book/_native_fixture.h"
                header.write_bytes(b"changed header")
                with self.assertRaisesRegex(ValueError, "differs from source commit"):
                    perf.source_manifest(root / "src", specification)
                header.unlink()
                with self.assertRaisesRegex(ValueError, "Missing frozen"):
                    perf.source_manifest(root / "src", specification)


class EvidenceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The entire schedule/configuration structure remains intact, with two
        # and three fixture queries. No corpus or performance timing is run.
        cls.cohorts = patch.object(perf, "COHORTS", {"synthetic61": {"queries": 2}, "public1015": {"queries": 3}})
        cls.cohorts.start()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.bound_run, cls.reports = fixture(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        cls.cohorts.stop()

    def test_all_cells_both_native_sources_and_raw_ledger_replay_pass(self):
        for report in self.reports:
            perf.verify_worker(report, self.bound_run, self.directory)
        result = perf.audit(self.directory)
        self.assertEqual(result["attempted_calls"], 480)
        self.assertEqual(result["paired_calls"], 240)
        self.assertEqual(len(result["comparison"]["cells"]), 8)
        self.assertTrue(result["comparison"]["complete_output_and_archive_equivalence"])
        self.assertEqual(len(result["ingestion_comparisons"]), 4)
        self.assertTrue(all(item["paired_batches"] == 4 for item in result["ingestion_comparisons"]))

    def test_both_sides_reject_wrong_binary_fallback_and_helper_inventory(self):
        for original in self.reports[:2]:
            for change in ("binary", "fallback", "probe", "inventory", "restoration"):
                report = copy.deepcopy(original)
                if change == "binary": report["backend"]["binary_sha256"] = "9" * 64
                elif change == "fallback": report["backend"]["actual"] = "python"
                elif change == "probe": report["backend"]["dispatch_probe"]["native_helper_calls"]["terms_ascii"] = 0
                elif change == "inventory": report["backend"]["available_functions"].pop()
                else: report["backend"]["dispatch_probe"]["instrumentation_restored"] = False
                with self.subTest(label=original["label"], change=change), self.assertRaises(ValueError):
                    perf.verify_worker(report, self.bound_run, self.directory)

    def test_both_builds_require_source_binary_and_identical_compiler_flags(self):
        for label in ("baseline", "candidate"):
            for field, changed in (("source_commit", "f" * 40), ("native_binaries", {}),
                    ("flags", {"extra_compile_args": ["-O0"]}), ("status", "failed")):
                build = copy.deepcopy(self.bound_run["build_manifest"])
                build["builds"][label][field] = changed
                with self.subTest(label=label, field=field), self.assertRaises(ValueError):
                    perf.validate_build_manifest(build, self.bound_run["sources"])
        build = copy.deepcopy(self.bound_run["build_manifest"])
        del build["builds"]["baseline"]
        with self.assertRaises(ValueError):
            perf.validate_build_manifest(build, self.bound_run["sources"])

    def test_per_source_setup_and_headers_are_bound_without_requiring_identical_definitions(self):
        build = copy.deepcopy(self.bound_run["build_manifest"])
        sources = self.bound_run["sources"]
        self.assertNotEqual(sources["baseline"]["source_files"]["setup.py"],
                            sources["candidate"]["source_files"]["setup.py"])
        perf.validate_build_manifest(build, sources)
        for field in ("build_inputs", "native_source_inputs"):
            changed = copy.deepcopy(build)
            changed["builds"]["candidate"][field] = {}
            with self.subTest(field=field), self.assertRaises(ValueError):
                perf.validate_build_manifest(changed, sources)

    def test_raw_ingestion_results_order_and_negative_resource_changes_are_retained(self):
        for field in ("ingestion_results", "unchanged_reingestion_results"):
            report = copy.deepcopy(self.reports[0])
            report[field][0]["id"] = "changed"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Raw ingestion"):
                perf.verify_worker(report, self.bound_run, self.directory)
        report = copy.deepcopy(self.reports[0])
        report["ingestion_order_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Ingestion order"):
            perf.verify_worker(report, self.bound_run, self.directory)
        reports = copy.deepcopy(self.reports)
        for report in reports:
            if report["label"] == "candidate":
                report["resources"]["unchanged_reingestion_ms"] = 2.0
        compared = perf.ingestion_comparisons(reports, self.bound_run)
        values = [item for item in compared if item["metric"] == "unchanged_reingestion_ms"]
        self.assertTrue(all(item["total_improvement_percent"] == -100.0 for item in values))
        self.assertTrue(all(len(item["rounds"]) == 4 for item in values))

    def test_host_script_hash_is_bound_to_frozen_evaluator(self):
        run = copy.deepcopy(self.bound_run)
        run["build_manifest"]["host_preparation_sha256"] = "0" * 64
        original_read = perf.read
        with patch.object(perf, "read", side_effect=lambda path: run if Path(path).name == "run.json" else original_read(path)):
            with self.assertRaisesRegex(ValueError, "Host preparation"):
                perf.audit(self.directory)

    def test_missing_duplicate_incomplete_or_edited_rows_fail(self):
        for change in ("missing", "duplicate", "incomplete", "payload", "ledger", "summary"):
            report = copy.deepcopy(self.reports[0])
            rows = report["configurations"][0]["rows"]
            if change == "missing": rows.pop()
            elif change == "duplicate": rows[1] = rows[0]
            elif change == "incomplete": report["status"] = "failed"
            elif change == "payload": rows[0]["payload_sha256"] = "9" * 64
            elif change == "ledger": report["ledger_sha256"] = "0" * 64
            else: report["configurations"][0]["latency"]["p95_ms"] = 0.01
            with self.subTest(change=change), self.assertRaises(ValueError):
                perf.verify_worker(report, self.bound_run, self.directory)

    def test_secondary_output_archive_and_protocol_differences_remain_visible(self):
        for change in ("secondary_payload", "archive", "protocol"):
            reports = copy.deepcopy(self.reports)
            if change == "secondary_payload": reports[1]["configurations"][3]["rows"][-1]["native_payload_sha256"] = "9" * 64
            elif change == "archive": reports[1]["archive_before"] = {"fixture": "changed"}
            else: reports[1]["configurations"][1]["resources"]["tool_schema_sha256"] = "9" * 64
            result = perf.comparisons(reports, self.bound_run)
            self.assertFalse(result["complete_output_and_archive_equivalence"])
            self.assertTrue(result["differences"])


class PreservationTests(unittest.TestCase):
    def test_corrupt_run_is_retained_and_marked_failed_without_blocking_publication(self):
        for raw in (b"{truncated", b"[]", b"null"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary)
                report = destination / preserve.REPORT_PATH
                report.mkdir(parents=True)
                (report / "run.json").write_bytes(raw)
                (report / "summary.json").write_bytes(b"{}")
                with patch.object(preserve.subprocess, "run") as execute:
                    audit = preserve.audit_snapshot(destination, "a" * 40, "123")
                self.assertEqual(audit["state"], "audit-failed")
                self.assertEqual(audit["remeasured_calls"], 0)
                self.assertEqual((report / "run.json").read_bytes(), raw)
                execute.assert_not_called()

    def test_partial_attempts_build_errors_and_preflight_logs_survive_without_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = {preserve.REPORT_PATH + "/run.json": b"{}\n",
                preserve.REPORT_PATH + "/r0-synthetic61-baseline.attempts.jsonl.gz": b"partial-gzip-ledger",
                preserve.REPORT_PATH + "/r0-synthetic61-baseline.json.gz.partial": b"partial-report",
                preserve.BUILD_PATH + "/preparation.events.jsonl": b'{"stage":"building"}\n{"stage":"failed"}\n',
                preserve.BUILD_PATH + "/baseline/build.log": b"compiler error\n",
                preserve.PREFLIGHT_PATH + "/install.log": b"dependency error\n"}
            for name, raw in records.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            corpus = root / preserve.REPORT_PATH / "native-language-temp" / "memory.db"
            corpus.parent.mkdir()
            corpus.write_bytes(b"temporary corpus-derived database")
            destination = root / "snapshot"
            with patch.object(preserve, "ROOT", root):
                inventory = preserve.collect_inputs(destination)
            self.assertEqual(set(inventory), set(records))
            for name, raw in records.items():
                self.assertEqual((destination / name).read_bytes(), raw)
                self.assertEqual(inventory[name]["sha256"], perf.sha(raw))
            with patch.object(preserve.subprocess, "run") as execute:
                audit = preserve.audit_snapshot(destination, "a" * 40, "123")
            self.assertEqual(audit["state"], "incomplete")
            self.assertEqual(audit["remeasured_calls"], 0)
            execute.assert_not_called()

    def test_symlink_input_is_rejected_without_reading_its_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / preserve.REPORT_PATH
            report.mkdir(parents=True)
            (report / "bad.log").symlink_to(root / "absent")
            with patch.object(preserve, "ROOT", root), self.assertRaisesRegex(ValueError, "regular file"):
                preserve.collect_inputs(root / "snapshot")

    def test_existing_different_evidence_ref_is_never_overwritten(self):
        calls = []
        def fake_git(*args, **kwargs):
            calls.append(args)
            result = {"hash-object": "1" * 40, "write-tree": "a" * 40,
                      "ls-remote": "b" * 40 + "\trefs/heads/evidence/fixture", "rev-parse": "c" * 40}.get(args[0], "")
            return SimpleNamespace(returncode=0, stdout=(result + "\n").encode())
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            (destination / "record.json").write_text("{}")
            with patch.object(preserve, "git", fake_git), patch.object(preserve, "WORK", destination):
                with self.assertRaisesRegex(ValueError, "will not be overwritten"):
                    preserve.publish(destination, "evidence/fixture")
        self.assertFalse(any(args[0] in {"push", "commit-tree"} for args in calls))


class ActualProtocolSmoke(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "linux" and importlib.util.find_spec("mcp") is not None,
                         "The real protocol fixture requires Linux and the optional MCP SDK")
    def test_small_fixture_real_sdk_roundtrip_and_source_checks(self):
        code = textwrap.dedent('''
            import asyncio, json, os, pathlib, tempfile
            from types import SimpleNamespace
            from scripts import native_core_performance as perf
            from memory_book import MemoryBook
            from benchmarks.run import original_turn_texts
            # Some managed test sandboxes omit /proc/<pid>/task/<tid>/children.
            # Still exercise the real SDK transport, but explicitly stub only
            # its resource observation in this tiny non-performance fixture.
            # The production controller retains its strict procfs requirement.
            real_procfs = pathlib.Path(f"/proc/self/task/{os.getpid()}/children").exists()
            if not real_procfs:
                perf.server_pid = lambda db: None
                perf.usage = lambda pid: {"available": False, "reason": "protocol fixture: sandbox omits child procfs"}
            class Events:
                def __init__(self): self.rows = []
                def event(self, *values): self.rows.append(values)
            session = {"project": "smoke", "session_id": "fixture", "title": "Timeout policy",
                "created_at": "2025-01-01T00:00:00+00:00", "messages": [
                {"role": "user", "content": "What is the timeout?"},
                {"role": "assistant", "content": "The timeout is 37 seconds and belongs only to this project."}]}
            case = SimpleNamespace(id="protocol-smoke", category="fixture", project="smoke", query="timeout")
            data = SimpleNamespace(sessions=[session], queries=[case])
            with tempfile.TemporaryDirectory() as temporary:
                work = pathlib.Path(temporary)
                db = work / "memory.db"
                with MemoryBook(db, cache_size=0) as book:
                    book.ingest(session)
                    native = book.recall(case.query, project=case.project, budget_chars=2400, use_cache=False)
                    native.pop("latency_ms")
                    assert native["results"]
                    sources = original_turn_texts(data)
                    pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                    errors, _ = perf.validate_response(case, native, perf.CONFIGS["native-char2400"], sources, pages, None)
                    assert not any(errors.values()), errors
                    ledger = Events()
                    rows, resource = asyncio.run(perf.mcp_calls(data, "mcp-char2400",
                        [{"query_id": case.id, "repetition": 0}], db, work, perf.ROOT / "src", "python",
                        sources, pages, None, ledger))
                    assert len(rows) == 1 and len(ledger.rows) == 2
                    assert rows[0]["native_payload_sha256"] == perf.digest(native)
                    assert rows[0]["envelope_sha256"] and not any(rows[0]["invariants"].values())
                    if real_procfs:
                        assert resource["server_after_calls"]["rss_bytes"] > 0
                    else:
                        assert resource["server_after_calls"]["available"] is False
                    assert book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0] == 0
                    native["results"][0]["excerpt_spans"][0][1] += 10000
                    errors, _ = perf.validate_response(case, native, perf.CONFIGS["native-char2400"], sources, pages, None)
                    assert errors["page_projection"] > 0
            print("Protocol fixture passed; no performance result published.")
        ''')
        environment = {**os.environ, "PYTHONPATH": str(perf.ROOT / "src"),
                       "MEMORY_BOOK_TEXT_BACKEND": "python", "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, "-c", code], cwd=perf.ROOT, env=environment,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Protocol fixture passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
