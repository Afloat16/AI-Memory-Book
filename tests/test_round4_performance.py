"""Artificial failure fixtures only; no benchmark input or retrieval is loaded."""
import copy
import asyncio
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round4_performance as bench


def ledger_bytes(worker):
    events = []
    for config in worker["configurations"]:
        for row in config["rows"]:
            seq = len(events) // 2
            events.extend([{"event": "started", "seq": seq, "config": config["id"],
                            "query_id": row["query_id"], "at": "fixture"},
                           {"event": "finished", "seq": seq, "config": config["id"],
                            "row": row, "at": "fixture"}])
    return b"".join(bench.json_bytes(event) for event in events)


def fixture(factor=.85):
    plan = json.loads(bench.PLAN.read_bytes())
    addendum = {"path": bench.ADDENDUM_PATH, "commit": bench.ADDENDUM_COMMIT,
                "sha256": bench.ADDENDUM_SHA256, "document": json.loads(bench.ADDENDUM.read_bytes())}
    counting_addendum = {"path": bench.COUNTING_ADDENDUM_PATH, "commit": bench.COUNTING_ADDENDUM_COMMIT,
                "sha256": bench.COUNTING_ADDENDUM_SHA256,
                "document": json.loads(bench.COUNTING_ADDENDUM.read_bytes())}
    formal = plan["performance_candidate"]["formal"]
    formal["calls"] = 5 * 6 * 2 * 4
    sources = {"baseline": {"commit": bench.BASELINE, "runtime_sha256": bench.BASELINE_HASH},
               "candidate": {"commit": "a" * 40, "runtime_sha256": bench.digest("candidate")}}
    run = {"binding": {"sources": sources, "development_addendum": addendum,
                       "counting_addendum": counting_addendum},
        "evaluator_files": {"fixture": "hash"},
        "host": {"boot": "same-boot"}, "schedule": bench.schedule(plan),
        "cohorts": {name: {"queries": len(ids), "sha256": bench.digest(name),
                           "query_ids": sorted(ids), "query_ids_original_order": ids}
                    for name, ids in (("synthetic61", ["b", "a"]), ("public1015", ["z", "y", "x"]))}}
    report = {"plan": plan, "development_addendum": copy.deepcopy(addendum),
              "counting_addendum": copy.deepcopy(counting_addendum), "run": run,
              "workers": [], "evaluator_unchanged": True, "error": None}
    for item in run["schedule"]:
        worker = {**item, "status": "completed", "error": None,
            "run_identity_sha256": bench.digest(run), "source": sources[item["label"]],
            "source_after": sources[item["label"]], "dataset_sha256": run["cohorts"][item["cohort"]]["sha256"],
            "runtime_import_ms": 1, "native_open_ms": 1, "fresh_ingestion_ms": 1,
            "unchanged_reingestion_ms": 1, "mcp_startup_to_initialize_ms": 1,
            "native_memory_after_ingestion": {"rss_bytes": 1000, "hwm_bytes": 1200},
            "native_memory_after_calls": {"rss_bytes": 1100, "hwm_bytes": 1300},
            "mcp_server_memory_after_calls": {"available": True, "rss_bytes": 2000, "hwm_bytes": 2200},
            "all_replayed_sessions_skipped": True, "native_recall_cache_rows": 0,
            "indexed_content": {"pages": "unchanged"}, "indexed_content_after_calls": {"pages": "unchanged"},
            "fresh_ingestion_results_sha256": bench.digest("ingest"),
            "unchanged_reingestion_results_sha256": bench.digest("replay"),
            "mcp_tool_schema_sha256": bench.digest("schema"), "mcp_instructions_sha256": bench.digest("instructions"),
            "mcp_initialization_tokens": {name: {"tool_schema": 20, "instructions": 10} for name in bench.ENCODINGS},
            "storage_after_mcp_live": {"logical_database_bytes": 4096}, "configurations": []}
        worker["mcp_sessions"] = {"mcp-char4000": {key: worker[key] for key in bench.MCP_SESSION_FIELDS}}
        worker["mcp_sessions"]["mcp-token1024"] = copy.deepcopy(worker["mcp_sessions"]["mcp-char4000"])
        for index, config in enumerate(formal["configs"]):
            rows = []
            mcp = config["surface"] == "official-sdk-mcp-stdio"
            ids = bench.query_order(run["cohorts"][item["cohort"]]["query_ids_original_order"], item["round"], index)
            for position, identity in enumerate(ids):
                elapsed = (10 + item["round"] * .01 + position * .001) * (factor if item["label"] == "candidate" else 1)
                row = {"query_id": identity, "category": "fixture", "wall_ms": elapsed,
                    "engine_source_sha256": sources[item["label"]]["runtime_sha256"],
                    "payload_sha256": bench.digest([identity, config["id"]]),
                    "native_payload_sha256": bench.digest([identity, config["id"].replace("mcp-", "native-") if mcp else config["id"]]),
                    "context_sha256": bench.digest(identity), "envelope_sha256": bench.digest(identity) if mcp else None,
                    "response_utf8_bytes": 50, "envelope_utf8_bytes": 70 if mcp else None,
                    "context_chars": 10, "result_count": 1, "cache_rows_before": 0, "cache_rows_after": 1 if mcp else 0,
                    "tokens": {name: {"context": 10, "response_text": 20,
                                      "response_envelope_json": 30 if mcp else None} for name in bench.ENCODINGS},
                    "token_metadata": {surface: {"budget_tokens": config["budget_tokens"],
                        "tokenizer": "cl100k_base", "tokenizer_version": "0.12.0", "context_tokens": 10}
                        for surface in ("native", "response")} if config["budget_tokens"] is not None else None,
                    "invariants": {name: 0 for name in bench.INVARIANTS}}
                rows.append(row)
            worker["configurations"].append({**config, "rows": rows,
                "latency": bench.latency_summary([r["wall_ms"] for r in rows])})
        worker["ledger_sha256"] = bench.sha(ledger_bytes(worker))
        report["workers"].append(worker)
    report["validation"] = bench.validation(report)
    return report


def save_worker(state, worker, run):
    prefix = state / "workers" / worker["key"]
    bench.exclusive(Path(str(prefix) + ".started.json"),
                    {"worker": next(w for w in run["schedule"] if w["key"] == worker["key"]),
                     "run_identity_sha256": bench.digest(run)})
    bench.atomic(Path(str(prefix) + ".json.gz"), worker, compressed=True)
    ledger = ledger_bytes(worker)
    Path(str(prefix) + ".attempts.jsonl").write_bytes(ledger)
    Path(str(prefix) + ".attempts.jsonl.gz").write_bytes(gzip.compress(ledger, mtime=0))


class PerformanceGateTests(unittest.TestCase):
    def test_development_addendum_is_fixed_to_original_commit_and_exact_bytes(self):
        raw = bench.ADDENDUM.read_bytes()
        self.assertEqual(bench.ADDENDUM_COMMIT, "fbfc6c56ae047abfd765e6149ba748c9e18adc42")
        self.assertEqual(bench.ADDENDUM_SHA256, "da8ccb8e4855493d2f32ed7cd2efec3a029bca346de064fb9b21399cb046b705")
        self.assertIn(bench.ADDENDUM_PATH, bench.REGISTERED_DOCUMENTS)
        self.assertNotIn(bench.ADDENDUM_PATH, bench.HELPERS)  # No rewrite of a historical helper.
        self.assertEqual(bench.file_hashes()[bench.ADDENDUM_PATH], bench.ADDENDUM_SHA256)
        with patch.object(bench, "git", return_value=raw) as git:
            registered = bench.registered_addendum()
            git.assert_called_once_with("show", bench.ADDENDUM_COMMIT + ":" + bench.ADDENDUM_PATH)
        self.assertEqual(registered["document"]["original_plan_commit"], bench.PLAN_COMMIT)
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "addendum.json"
            altered.write_bytes(raw + b" ")  # Identical parsed JSON is still different preregistered bytes.
            with patch.object(bench, "ADDENDUM", altered), patch.object(bench, "git", return_value=raw) as git:
                with self.assertRaisesRegex(ValueError, "preregistered development addendum bytes or commit"):
                    bench.registered_addendum()
                git.assert_not_called()
        with patch.object(bench, "git", return_value=raw + b" "):
            with self.assertRaisesRegex(ValueError, "preregistered development addendum bytes or commit"):
                bench.registered_addendum()

    def test_counting_addendum_is_fixed_to_original_commit_and_exact_bytes(self):
        raw = bench.COUNTING_ADDENDUM.read_bytes()
        self.assertEqual(bench.COUNTING_ADDENDUM_COMMIT, "e02584fd20d2626777449bc64322703de6df6948")
        self.assertEqual(bench.COUNTING_ADDENDUM_SHA256, "06f25800e849e20c8d5a3a557d47fe9b0a952859aa27122029a86e40ffcd02b2")
        self.assertEqual(bench.REGISTERED_DOCUMENTS, (bench.ADDENDUM_PATH, bench.COUNTING_ADDENDUM_PATH))
        self.assertNotIn(bench.COUNTING_ADDENDUM_PATH, bench.HELPERS)
        self.assertEqual(bench.file_hashes()[bench.COUNTING_ADDENDUM_PATH], bench.COUNTING_ADDENDUM_SHA256)
        with patch.object(bench, "git", return_value=raw) as git:
            registered = bench.registered_counting_addendum()
            git.assert_called_once_with("show", bench.COUNTING_ADDENDUM_COMMIT + ":" + bench.COUNTING_ADDENDUM_PATH)
        self.assertEqual(registered["document"]["original_plan_commit"], bench.PLAN_COMMIT)
        self.assertEqual(registered["document"]["prior_addendum_commit"], bench.ADDENDUM_COMMIT)
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "counting-addendum.json"
            altered.write_bytes(raw + b" ")
            with patch.object(bench, "COUNTING_ADDENDUM", altered), \
                    patch.object(bench, "git", return_value=raw) as git:
                with self.assertRaisesRegex(ValueError, "preregistered counting addendum bytes or commit"):
                    bench.registered_counting_addendum()
                git.assert_not_called()
        with patch.object(bench, "git", return_value=raw + b" "):
            with self.assertRaisesRegex(ValueError, "preregistered counting addendum bytes or commit"):
                bench.registered_counting_addendum()

    def test_binding_and_report_preserve_both_exact_addenda(self):
        report = fixture()
        addenda = {key: report[key] for key in ("development_addendum", "counting_addendum")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "binding.json"
            documents = {bench.ADDENDUM_PATH: bench.ADDENDUM.read_bytes(),
                         bench.COUNTING_ADDENDUM_PATH: bench.COUNTING_ADDENDUM.read_bytes()}
            hashes = {name: bench.sha(raw) for name, raw in documents.items()}
            value = {"status": "frozen-before-formal-timing", "evaluator": bench.VERSION,
                **addenda, "plan_sha256": bench.sha(bench.PLAN.read_bytes()),
                "evaluator_files": hashes, "packages": bench.PACKAGES,
                "sources": report["run"]["binding"]["sources"], "evaluator_commit": "f" * 40}
            raw = bench.json_bytes(value)
            path.write_bytes(raw)
            def git(*values):
                if values == ("show", "HEAD:binding.json"):
                    return raw
                for name, document in documents.items():
                    if values == ("show", "f" * 40 + ":" + name):
                        return document
                raise AssertionError(values)
            with patch.object(bench, "ROOT", root), patch.object(bench, "file_hashes", return_value=hashes), \
                    patch.object(bench, "registered_addendum", return_value=addenda["development_addendum"]), \
                    patch.object(bench, "registered_counting_addendum", return_value=addenda["counting_addendum"]), \
                    patch.object(bench, "git", side_effect=git):
                self.assertEqual(bench.load_binding(path), value)
                for key in addenda:
                    message = "Binding " + key.replace("_", " ")
                    for field, changed in (("path", "unregistered.json"), ("commit", "a" * 40),
                                           ("sha256", "0" * 64), ("document", {"fixture": "unregistered"})):
                        tampered = copy.deepcopy(value)
                        tampered[key][field] = changed
                        path.write_bytes(bench.json_bytes(tampered))
                        with self.subTest(addendum=key, field=field), self.assertRaisesRegex(ValueError, message):
                            bench.load_binding(path)
                    missing = copy.deepcopy(value)
                    del missing[key]
                    path.write_bytes(bench.json_bytes(missing))
                    with self.subTest(addendum=key, field="absent"), self.assertRaisesRegex(ValueError, message):
                        bench.load_binding(path)
        compact = bench.summary(report, b"compressed-fixture", b"raw-fixture")
        for key, original in addenda.items():
            self.assertEqual(compact[key], original)
            self.assertEqual(compact["run"]["binding"][key], original)
            changed = copy.deepcopy(report)
            changed[key]["commit"] = "a" * 40
            self.assertIn(key + "_changed", bench.validation(changed)["issues"])
            del changed[key]
            self.assertIn(key + "_changed", bench.validation(changed)["issues"])

    def test_registered_matrix_and_seed_are_the_new_round_four_axes(self):
        plan = json.loads(bench.PLAN.read_bytes())
        formal = plan["performance_candidate"]["formal"]
        self.assertEqual(formal["configs"], list(bench.CONFIGURATIONS))
        self.assertEqual(formal["calls"], (168 + 1015) * 6 * 2 * 4)
        self.assertEqual(bench.BASELINE, "7b7a5d7336b9350a128f5e0a888811b1b3015e68")
        self.assertEqual(bench.query_order(list(range(12)), 2, 5),
                         [8, 6, 2, 5, 4, 11, 10, 1, 0, 9, 7, 3])

    def test_complete_abba_matrix_first_repeat_and_sorted_roundtrip(self):
        report = fixture()
        self.assertTrue(report["validation"]["passed"], report["validation"])
        self.assertEqual(report["validation"]["timed_calls"], 240)
        self.assertEqual(len(report["workers"]), 16)
        self.assertEqual([w["label"] for w in report["run"]["schedule"] if w["cohort"] == "synthetic61"],
                         ["baseline", "candidate", "candidate", "baseline", "candidate", "baseline", "baseline", "candidate"])
        compared = bench.comparisons(report)
        self.assertEqual(len(compared), 12)
        self.assertEqual(compared[0]["baseline"]["first_round_latency"]["samples"], 2)
        self.assertEqual(compared[0]["baseline"]["repeat_rounds_latency"]["samples"], 6)
        self.assertTrue(bench.acceptance(report, compared)["accepted"])
        saved = json.loads(json.dumps(report, sort_keys=True))
        self.assertEqual(compared, bench.comparisons(saved))
        self.assertEqual(report["validation"], bench.validation(saved))

    def test_no_best_round_selection_or_missing_duplicate_worker(self):
        for mutation in (lambda r: r["workers"].pop(),
                         lambda r: r["workers"].append(copy.deepcopy(r["workers"][0])),
                         lambda r: r["workers"].reverse()):
            report = fixture()
            mutation(report)
            self.assertFalse(bench.validation(report)["passed"])

    def test_unchanged_context_cannot_hide_metadata_or_envelope_change(self):
        for field in ("payload_sha256", "native_payload_sha256", "envelope_sha256"):
            report = fixture()
            report["workers"][-1]["configurations"][1]["rows"][0][field] = "0" * 64
            self.assertFalse(bench.validation(report)["passed"], field)

    def test_drop_duplicate_order_cache_scope_budget_source_and_nan_fail(self):
        mutations = [lambda w: w["configurations"][0]["rows"].pop(),
            lambda w: w["configurations"][0]["rows"].reverse(),
            lambda w: w["configurations"][0]["rows"][0].update(cache_rows_before=1),
            lambda w: w["configurations"][0]["rows"][0]["invariants"].update(source_scope_errors=1),
            lambda w: w["configurations"][2]["rows"][0]["tokens"]["cl100k_base"].update(context=513),
            lambda w: w["configurations"][0]["rows"][0].update(engine_source_sha256="changed"),
            lambda w: w["configurations"][0]["rows"][0].update(wall_ms=float("nan")),
            lambda w: w["configurations"][0]["rows"][0].update(wall_ms=0),
            lambda w: w.update(indexed_content_after_calls={"pages": "changed"}),
            lambda w: w["source_after"].update(commit="another"),
            lambda w: w["configurations"][0]["latency"].update(p95_ms=0)]
        for mutation in mutations:
            report = fixture()
            mutation(report["workers"][-1])
            self.assertFalse(bench.validation(report)["passed"])

    def test_valid_performance_loss_is_retained_and_not_accepted(self):
        report = fixture(.98)
        compared = bench.comparisons(report)
        self.assertTrue(report["validation"]["passed"])
        result = bench.acceptance(report, compared)
        self.assertFalse(result["numeric_gate_passed"])
        self.assertAlmostEqual(result["geometric_mean_p95_improvement_percent"], 2)
        compared[0]["candidate_change_percent"]["p95_ms"] = 6
        result = bench.acceptance(fixture(), compared)
        self.assertEqual(len(result["regressions_above_five_percent"]), 1)
        self.assertFalse(result["accepted"])

    def test_resource_increase_requires_review_even_when_latency_passes(self):
        report = fixture()
        for worker in report["workers"]:
            if worker["label"] == "candidate":
                worker["mcp_server_memory_after_calls"]["rss_bytes"] *= 1.2
        result = bench.acceptance(report, bench.comparisons(report))
        self.assertTrue(result["numeric_gate_passed"])
        self.assertFalse(result["accepted"])
        self.assertEqual(len(result["resource_review"]), 2)

    def test_all_three_numeric_gates_are_independently_required(self):
        def result(base_factor, overrides):
            report = fixture(base_factor)
            for worker in report["workers"]:
                if worker["label"] != "candidate":
                    continue
                for config in worker["configurations"]:
                    factor = overrides.get((worker["cohort"], config["id"]), base_factor)
                    for row in config["rows"]:
                        row["wall_ms"] *= factor / base_factor
                    config["latency"] = bench.latency_summary([row["wall_ms"] for row in config["rows"]])
                worker["ledger_sha256"] = bench.sha(ledger_bytes(worker))
            report["validation"] = bench.validation(report)
            self.assertTrue(report["validation"]["passed"], report["validation"])
            return bench.acceptance(report, bench.comparisons(report))

        native_not_fast_enough = result(.8, {("public1015", "native-token" + str(budget)): .9
                                            for budget in (512, 1024, 2048)})
        self.assertGreater(native_not_fast_enough["geometric_mean_p95_improvement_percent"], 10)
        self.assertGreater(native_not_fast_enough["public_mcp_token1024_p95_improvement_percent"], 10)
        self.assertFalse(native_not_fast_enough["numeric_gate_passed"])
        mcp_not_fast_enough = result(.8, {("public1015", "mcp-token1024"): .95})
        self.assertGreater(mcp_not_fast_enough["geometric_mean_p95_improvement_percent"], 10)
        self.assertGreater(mcp_not_fast_enough["best_public_native_token_p95_improvement_percent"], 15)
        self.assertFalse(mcp_not_fast_enough["numeric_gate_passed"])
        matrix_not_fast_enough = result(.98, {("public1015", "native-token1024"): .8,
                                             ("public1015", "mcp-token1024"): .85})
        self.assertLess(matrix_not_fast_enough["geometric_mean_p95_improvement_percent"], 10)
        self.assertFalse(matrix_not_fast_enough["numeric_gate_passed"])
        self.assertTrue(result(.85, {})["accepted"])

    def test_token_mcp_session_startup_and_rss_require_separate_resource_review(self):
        for field in ("mcp_startup_to_initialize_ms", "mcp_server_memory_after_calls.rss_bytes"):
            report = fixture()
            for worker in report["workers"]:
                if worker["label"] == "candidate":
                    session = worker["mcp_sessions"]["mcp-token1024"]
                    parent, _, key = field.rpartition(".")
                    target = session[parent] if parent else session
                    target[key] *= 1.2
            self.assertTrue(bench.validation(report)["passed"])
            result = bench.acceptance(report, bench.comparisons(report))
            self.assertTrue(result["numeric_gate_passed"])
            self.assertFalse(result["accepted"])
            self.assertEqual(len(result["resource_review"]), 2)
            self.assertTrue(all("mcp-token1024" in item["metric"] for item in result["resource_review"]))

    def test_both_actual_mcp_token_metadata_surfaces_and_native_pair_are_required(self):
        for surface in ("native", "response"):
            for field in bench.TOKEN_METADATA_FIELDS:
                report = fixture()
                row = report["workers"][0]["configurations"][-1]["rows"][0]
                row["token_metadata"][surface][field] = "wrong"
                self.assertFalse(bench.validation(report)["passed"], (surface, field))
        report = fixture()
        report["workers"][0]["configurations"][-1]["rows"][0]["native_payload_sha256"] = "0" * 64
        self.assertFalse(bench.validation(report)["passed"])
        for mutation in (lambda worker: worker["mcp_sessions"].pop("mcp-token1024"),
                         lambda worker: worker["mcp_sessions"]["mcp-token1024"].update(mcp_tool_schema_sha256="wrong")):
            report = fixture()
            mutation(report["workers"][0])
            self.assertFalse(bench.validation(report)["passed"])

    def test_attempt_ledger_must_match_every_started_and_finished_row(self):
        report = fixture()
        worker = report["workers"][0]
        ledger = ledger_bytes(worker)
        self.assertEqual(bench.verify_worker(worker, report["run"], report["plan"], ledger=ledger), 12)
        for damaged in (ledger.splitlines(keepends=True)[0], ledger + ledger.splitlines(keepends=True)[0]):
            worker["ledger_sha256"] = bench.sha(damaged)
            with self.assertRaisesRegex(ValueError, "attempt ledger"):
                bench.verify_worker(worker, report["run"], report["plan"], ledger=damaged)

    def test_resume_skips_only_original_complete_prefix_and_refuses_interruption(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for worker in report["workers"][:2]:
                save_worker(state, worker, report["run"])
            values = bench.resume_prefix(state, report["run"], report["plan"])
            self.assertEqual([v["key"] for v in values], [w["key"] for w in report["workers"][:2]])
            pending = report["run"]["schedule"][2]
            bench.exclusive(state / "workers" / (pending["key"] + ".started.json"),
                            {"worker": pending, "run_identity_sha256": bench.digest(report["run"])})
            with self.assertRaisesRegex(ValueError, "do not remeasure"):
                bench.resume_prefix(state, report["run"], report["plan"])
            changed = copy.deepcopy(report["run"])
            changed["host"]["boot"] = "different-boot"
            with self.assertRaises(ValueError):
                bench.resume_prefix(state, changed, report["plan"])

    def test_resume_rejects_holes_or_tampered_complete_ledger(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            save_worker(state, report["workers"][1], report["run"])
            with self.assertRaisesRegex(ValueError, "scheduled prefix"):
                bench.resume_prefix(state, report["run"], report["plan"])
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            save_worker(state, report["workers"][0], report["run"])
            path = state / "workers" / (report["workers"][0]["key"] + ".attempts.jsonl")
            path.write_bytes(path.read_bytes() + b"{}\n")
            with self.assertRaisesRegex(ValueError, "do not remeasure"):
                bench.resume_prefix(state, report["run"], report["plan"])

    def test_saved_summary_and_compressed_hash_are_recomputed_without_retrieval(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture.json.gz"
            state = Path(directory) / "state"
            bench.exclusive(state / "run.json", report["run"])
            for worker in report["workers"]:
                save_worker(state, worker, report["run"])
            report["worker_artifacts_sha256"] = bench.artifact_hashes(state, report["run"])
            bench.save_report(output, report)
            with patch.object(bench, "load_plan", return_value=report["plan"]), \
                    patch.object(bench, "registered_addendum", return_value=report["development_addendum"]), \
                    patch.object(bench, "registered_counting_addendum", return_value=report["counting_addendum"]), \
                    patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]):
                self.assertEqual(bench.audit(output, state)["retrieval_calls_executed"], 0)
                summary = output.with_name("fixture.summary.json")
                value = json.loads(summary.read_bytes())
                value["full_report_sha256"] = "bad"
                summary.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "Summary or raw hashes"):
                    bench.audit(output, state)

    def test_saved_audit_rejects_coherent_counting_addendum_rewrite(self):
        report = fixture()
        registered = copy.deepcopy(report["counting_addendum"])
        # Matching report, binding, worker identities and recalculated summary
        # must not make altered preregistration content acceptable to the audit.
        for document in (report["counting_addendum"], report["run"]["binding"]["counting_addendum"]):
            document["document"]["candidate_c"]["guard"] = "unregistered replacement"
        for worker in report["workers"]:
            worker["run_identity_sha256"] = bench.digest(report["run"])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture.json.gz"
            bench.save_report(output, report)
            self.assertTrue(report["validation"]["passed"])
            with patch.object(bench, "load_plan", return_value=report["plan"]), \
                    patch.object(bench, "registered_addendum", return_value=report["development_addendum"]), \
                    patch.object(bench, "registered_counting_addendum", return_value=registered), \
                    patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]), \
                    patch.object(bench, "resume_prefix") as retrieval:
                with self.assertRaisesRegex(ValueError, "Report counting addendum differs"):
                    bench.audit(output, Path(directory) / "not-created-state")
                retrieval.assert_not_called()

    def test_zero_or_partial_workers_preserve_failure_report_and_all_twelve_cells(self):
        for count in (0, 1, 5):
            report = fixture()
            report["workers"] = report["workers"][:count]
            report["error"] = {"type": "FixtureInterruption", "message": "preserve"}
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "partial.json.gz"
                bench.save_report(path, report)
                saved = json.loads(gzip.decompress(path.read_bytes()))
                self.assertFalse(saved["validation"]["passed"])
                self.assertEqual(saved["error"], report["error"])
                self.assertEqual(len(saved["comparisons"]), 12)
                self.assertFalse(saved["acceptance"]["accepted"])
                self.assertTrue(path.with_name("partial.summary.json").is_file())

    def test_public_copy_retains_both_ledgers_and_is_directly_auditable(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state, public = Path(directory) / "state", Path(directory) / "public"
            output = public / "report.json.gz"
            bench.exclusive(state / "run.json", report["run"])
            bench.exclusive(state / "controller-attempts/0001.started.json", {"fixture": "started"})
            for worker in report["workers"]:
                save_worker(state, worker, report["run"])
            report["worker_artifacts_sha256"] = bench.artifact_hashes(state, report["run"])
            bench.save_report(output, report)
            args = SimpleNamespace(state_dir=state, output=output)
            bench.export_checkpoint(args)
            bench.export_checkpoint(args)  # Existing completed copies remain identical.
            self.assertEqual(bench.artifact_hashes(public, report["run"]), report["worker_artifacts_sha256"])
            self.assertEqual(len(list((public / "workers").glob("*.attempts.jsonl"))), 16)
            self.assertEqual(len(list((public / "workers").glob("*.attempts.jsonl.gz"))), 16)
            self.assertTrue((public / "controller-attempts/0001.started.json").is_file())
            with patch.object(bench, "load_plan", return_value=report["plan"]), \
                    patch.object(bench, "registered_addendum", return_value=report["development_addendum"]), \
                    patch.object(bench, "registered_counting_addendum", return_value=report["counting_addendum"]), \
                    patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]):
                self.assertEqual(bench.audit(output, public)["retrieval_calls_executed"], 0)

    def test_public_copy_refuses_overwrite_and_retains_truncated_ledger_bytes(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as directory:
            state, public = Path(directory) / "state", Path(directory) / "public"
            worker = report["workers"][0]
            save_worker(state, worker, report["run"])
            args = SimpleNamespace(state_dir=state, output=public / "report.json.gz")
            bench.export_checkpoint(args)
            destination = public / "workers" / (worker["key"] + ".json.gz")
            destination.write_bytes(b"preserve previously published divergent bytes")
            with self.assertRaisesRegex(ValueError, "Never overwrite"):
                bench.export_checkpoint(args)
            self.assertEqual(destination.read_bytes(), b"preserve previously published divergent bytes")
        with tempfile.TemporaryDirectory() as directory:
            state, public = Path(directory) / "state", Path(directory) / "public"
            path = state / "workers/unfinished.attempts.jsonl"
            raw = b'{"event":"started","seq":0}\n{"event":"fin'
            bench.exclusive_bytes(path, raw)
            bench.export_checkpoint(SimpleNamespace(state_dir=state, output=public / "report.json.gz"))
            self.assertEqual((public / "workers" / path.name).read_bytes(), raw)

    def test_unpublished_formal_controllers_stop_before_loading_or_creating_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "new-parent/state"
            args = SimpleNamespace(publish_branch=None, state_dir=state)
            with patch.object(bench, "load_plan") as plan, \
                    patch.object(bench, "load_binding") as binding, \
                    patch.object(bench, "host_identity") as host, \
                    patch.object(bench, "source_identity") as source, \
                    patch.object(bench, "dataset") as dataset, \
                    patch.object(bench, "claim_execution") as claim:
                for launch in (lambda: bench.main(["--binding", "unused.json"]),
                               lambda: bench.controller(args, {}, {}),
                               lambda: bench.controller_locked(args, {}, {})):
                    with self.assertRaisesRegex(ValueError, "requires --publish-branch"):
                        launch()
                for operation in (plan, binding, host, source, dataset, claim):
                    operation.assert_not_called()
            self.assertFalse(state.parent.exists())

    def test_formal_controller_requires_canonical_state_before_runtime_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publication = {"run_id": "123", "run_attempt": "1"}
            args = SimpleNamespace(publish_branch="validation/v032-round4-performance-123-1",
                baseline_src=root / "baseline", candidate_src=root / "candidate",
                locomo_path=root / "fixture", output=root / "public/report.json.gz",
                state_dir=root / "arbitrary-new-state")
            with patch.object(bench, "ROOT", root), \
                    patch.object(bench, "publication_identity", return_value=publication), \
                    patch.object(bench, "host_identity") as host, \
                    patch.object(bench, "source_identity") as source, \
                    patch.object(bench, "dataset") as dataset, \
                    patch.object(bench, "claim_execution") as claim:
                with self.assertRaisesRegex(ValueError, "canonical claimed run directory"):
                    bench.controller_locked(args, {}, {})
                for operation in (host, source, dataset, claim):
                    operation.assert_not_called()
            self.assertFalse(args.state_dir.exists())

    def test_direct_worker_without_claim_stops_before_source_load_or_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            bench.exclusive(state / "run.json", {"publication": None, "execution_claim": None})
            args = SimpleNamespace(state_dir=state, worker="unclaimed-worker")
            with patch.object(bench, "host_identity") as host, \
                    patch.object(bench, "source_identity") as source, \
                    patch.object(bench, "dataset") as dataset, \
                    patch.object(bench.time, "perf_counter_ns") as timer:
                with self.assertRaisesRegex(ValueError, "preserved hosted publication and execution claim"):
                    bench.worker(args, {}, {})
                for operation in (host, source, dataset, timer):
                    operation.assert_not_called()
            self.assertEqual(list(state.iterdir()), [state / "run.json"])

    def test_claimed_worker_requires_exact_published_next_intent_and_no_prior_evidence(self):
        # The valid case only checks receipts. No worker, input loader, runtime,
        # timing or Git write is executed by this artificial fixture.
        cases = {"valid": None, "alternate-state": "canonical claimed run directory",
            "missing-claim-ref": "not preserved remotely", "claim-bytes": "committed original",
            "claim-parent": "directly from the frozen", "remote-head": "exact published result head",
            "published-run": "published controller state", "missing-intent": "published controller start intent",
            "already-complete": "next worker", "failed-checkpoint": "next worker",
            "existing-ledger": "never remeasure", "local-compressed-ledger": "never repeat",
            "publication-failed": "Failed publication"}
        for mutation, error_message in cases.items():
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = json.loads(bench.PLAN.read_bytes())
                binding = {"fixture": "frozen"}
                binding_path = root / "binding.json"
                binding_path.write_bytes(bench.json_bytes(binding))
                fingerprint = bench.sha(binding_path.read_bytes())
                public = "benchmarks/reports/round4-performance-123-1"
                publication = {"branch": "validation/v032-round4-performance-123-1", "directory": public,
                    "workflow_commit": "d" * 40, "run_id": "123", "run_attempt": "1"}
                claim_path = public + "/execution-claim.json"
                claim_raw = bench.json_bytes({"schema_version": 1, "status": "claimed-before-measurement",
                    "workflow_commit": publication["workflow_commit"], "binding_sha256": fingerprint,
                    "run_id": "123", "run_attempt": "1", "claimed_at": "fixture"})
                bench.exclusive_bytes(root / claim_path, claim_raw)
                claim = {"branch": "validation/v032-round4-performance-claim-" + fingerprint,
                    "commit": "c" * 40, "path": claim_path, "sha256": bench.sha(claim_raw)}
                run = {"publication": publication, "execution_claim": claim,
                    "output": str(root / public / "report.json.gz"), "workflow_commit": "d" * 40,
                    "binding": binding, "binding_sha256": fingerprint,
                    "plan_sha256": bench.sha(bench.PLAN.read_bytes()), "evaluator_files": {"fixture": "hash"},
                    "schedule": bench.schedule(plan)}
                state = root / ".artifacts/round4-performance-123-1"
                args = SimpleNamespace(state_dir=state, binding=binding_path, worker=run["schedule"][0]["key"])
                run_raw = bench.json_bytes(run)
                bench.exclusive_bytes(state / "run.json", run_raw)
                intent_path = "workers/" + args.worker + ".started.json"
                intent_raw = bench.json_bytes({"worker": run["schedule"][0], "run_identity_sha256": bench.digest(run)})
                bench.exclusive_bytes(state / intent_path, intent_raw)
                checkpoint = {"run_identity_sha256": bench.digest(run), "status": "running",
                              "error": None, "completed_workers": []}
                head = "e" * 40
                responses = {
                    ("show", claim["commit"] + ":" + claim_path): claim_raw,
                    ("rev-parse", claim["commit"] + "^"): ("d" * 40 + "\n").encode(),
                    ("ls-remote", "--heads", "origin", "refs/heads/" + claim["branch"]):
                        (claim["commit"] + "\trefs/heads/" + claim["branch"] + "\n").encode(),
                    ("rev-parse", "HEAD"): (head + "\n").encode(),
                    ("ls-remote", "--heads", "origin", "refs/heads/" + publication["branch"]):
                        (head + "\trefs/heads/" + publication["branch"] + "\n").encode(),
                    ("show", head + ":" + public + "/run.json"): run_raw,
                    ("show", head + ":" + public + "/" + intent_path): intent_raw,
                }
                if mutation == "alternate-state":
                    args.state_dir = root / "fresh-replay-directory"
                elif mutation == "missing-claim-ref":
                    responses[("ls-remote", "--heads", "origin", "refs/heads/" + claim["branch"])] = b""
                elif mutation == "claim-bytes":
                    (root / claim_path).write_bytes(claim_raw + b" ")
                elif mutation == "claim-parent":
                    responses[("rev-parse", claim["commit"] + "^")] = b"f" * 40 + b"\n"
                elif mutation == "remote-head":
                    responses[("ls-remote", "--heads", "origin", "refs/heads/" + publication["branch"])] = b"moved"
                elif mutation == "published-run":
                    responses[("show", head + ":" + public + "/run.json")] = b"{}\n"
                elif mutation == "missing-intent":
                    responses[("show", head + ":" + public + "/" + intent_path)] = b"{}\n"
                elif mutation == "already-complete":
                    checkpoint["completed_workers"] = [args.worker]
                elif mutation == "failed-checkpoint":
                    checkpoint.update(status="failed_or_interrupted", error={"type": "fixture"})
                elif mutation == "local-compressed-ledger":
                    bench.exclusive_bytes(state / "workers" / (args.worker + ".attempts.jsonl.gz"),
                                          b"preserve an interrupted compressed ledger")
                elif mutation == "publication-failed":
                    bench.exclusive(root / public / "publication-failure.json", {"fixture": "preserved"})
                responses[("show", head + ":" + public + "/checkpoint.json")] = bench.json_bytes(checkpoint)
                def git(*values):
                    if values[0] == "ls-tree":
                        return b"existing.attempts.jsonl\n" if mutation == "existing-ledger" else b""
                    return responses[values]
                with patch.object(bench, "ROOT", root), \
                        patch.object(bench, "publication_identity", return_value=publication), \
                        patch.object(bench, "file_hashes", return_value={"fixture": "hash"}), \
                        patch.object(bench, "git", side_effect=git), \
                        patch.object(bench.subprocess, "run") as command, \
                        patch.object(bench, "dataset") as dataset:
                    if error_message is None:
                        self.assertEqual(bench.verify_worker_claim(args, run, plan, binding), claim)
                    else:
                        with self.assertRaisesRegex(ValueError, error_message):
                            bench.verify_worker_claim(args, run, plan, binding)
                    command.assert_not_called()
                    dataset.assert_not_called()

    def test_binding_claim_refuses_duplicates_and_never_retries_ambiguous_push(self):
        for already_claimed in (True, False):
            with self.subTest(already_claimed=already_claimed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args = SimpleNamespace(binding=root / "binding.json", state_dir=root / "state",
                    output=root / "benchmarks/reports/round4-performance-123-1/report.json.gz", resume=False)
                args.binding.write_bytes(b'{"fixture":"frozen"}\n')
                publication = {"workflow_commit": "d" * 40, "run_id": "123", "run_attempt": "1"}
                calls = []
                def git(*values):
                    if values[0] == "ls-remote":
                        return b"already claimed" if already_claimed else b""
                    if values[0] == "rev-parse":
                        committed = any("commit" in argv for argv in calls)
                        return (b"c" if committed else b"d") * 40 + b"\n"
                    return b""
                def command(argv, **kwargs):
                    calls.append(argv)
                    if argv[1] == "push":
                        raise subprocess.CalledProcessError(1, argv)
                with patch.object(bench, "ROOT", root), patch.object(bench, "git", side_effect=git), \
                        patch.object(bench.subprocess, "run", side_effect=command):
                    with self.assertRaises(bench.CheckpointPublicationError):
                        bench.claim_execution(args, publication)
                    self.assertTrue((args.output.parent / "publication-failure.json").is_file())
                    self.assertEqual(sum(argv[1] == "push" for argv in calls), int(not already_claimed))
                    count = len(calls)
                    with self.assertRaisesRegex(ValueError, "no automatic retry"):
                        bench.claim_execution(args, publication)
                    self.assertEqual(len(calls), count)
                self.assertFalse(any("--force" in argv or "--force-with-lease" in argv for argv in calls))

    def test_publication_is_limited_to_original_workflow_and_this_run_ref(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = "benchmarks/reports/round4-performance-123-1"
            args = SimpleNamespace(publish_branch="validation/v032-round4-performance-123-1",
                                   output=root / relative / "report.json.gz")
            environment = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                           "GITHUB_SHA": "d" * 40, "GITHUB_REPOSITORY": "Afloat16/AI-Memory-Book",
                           "GITHUB_EVENT_NAME": "push", "GITHUB_REF": bench.TRIGGER}
            changed = [relative + "/report.json.gz"]
            def git(*values):
                if values[0] == "remote":
                    return b"https://github.com/Afloat16/AI-Memory-Book.git\n"
                if values[0] == "merge-base":
                    return b""
                return ("\n".join(changed) + "\n").encode()
            with patch.object(bench, "ROOT", root), patch.dict(os.environ, environment), \
                    patch.object(bench, "git", side_effect=git):
                identity = bench.publication_identity(args)
                self.assertEqual(identity["workflow_commit"], environment["GITHUB_SHA"])
                args.publish_branch = "main"
                with self.assertRaisesRegex(ValueError, "exact Actions attempt"):
                    bench.publication_identity(args)
                args.publish_branch = identity["branch"]
                changed[:] = ["src/memory_book/store.py"]
                with self.assertRaisesRegex(ValueError, "only this attempt"):
                    bench.publication_identity(args)
                changed[:] = [relative + "/report.json.gz"]
                with patch.dict(os.environ, {"GITHUB_REPOSITORY": "someone/else"}):
                    with self.assertRaisesRegex(ValueError, "authorized repository"):
                        bench.publication_identity(args)

    def test_publication_refuses_unrelated_staging_and_does_not_retry_push(self):
        identity = {"branch": "validation/v032-round4-performance-123-1",
                    "directory": "benchmarks/reports/round4-performance-123-1"}
        args, run = SimpleNamespace(), {"publication": identity}
        with patch.object(bench, "publication_identity", return_value=identity), \
                patch.object(bench, "export_checkpoint"), \
                patch.object(bench, "git", return_value=b"README.md\n"), \
                patch.object(bench.subprocess, "run") as command:
            with self.assertRaisesRegex(bench.CheckpointPublicationError, "Unrelated staged"):
                bench.publish_checkpoint(args, run, "fixture")
            command.assert_not_called()
        calls = []
        def command(argv, **kwargs):
            calls.append(argv)
            if argv[1] == "push":
                raise subprocess.CalledProcessError(1, argv)
        with patch.object(bench, "publication_identity", return_value=identity), \
                patch.object(bench, "export_checkpoint"), \
                patch.object(bench, "git", side_effect=[b"", b"result\n"]), \
                patch.object(bench.subprocess, "run", side_effect=command):
            with self.assertRaisesRegex(bench.CheckpointPublicationError, "publication failed"):
                bench.publish_checkpoint(args, run, "fixture")
        self.assertEqual(sum(argv[1] == "push" for argv in calls), 1)
        self.assertFalse(any("--force" in argv or "--force-with-lease" in argv for argv in calls))

    def test_failed_start_or_complete_checkpoint_stops_before_next_worker(self):
        for fail_phase in ("started", "completed"):
            original = fixture()
            plan, binding = original["plan"], original["run"]["binding"]
            with self.subTest(phase=fail_phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                args = SimpleNamespace(baseline_src=root / "baseline", candidate_src=root / "candidate",
                    locomo_path=root / "artificial-input", binding=root / "binding.json",
                    output=root / "public/report.json.gz",
                    state_dir=root / ".artifacts/round4-performance-123-1", resume=False,
                    publish_branch="validation/v032-round4-performance-123-1")
                args.locomo_path.write_bytes(b"artificial data; never parsed")
                args.binding.write_bytes(bench.json_bytes(binding))
                publication = {"branch": args.publish_branch, "workflow_commit": "d" * 40,
                               "run_id": "123", "run_attempt": "1"}
                events = []
                def dataset(plan, name, path):
                    spec = original["run"]["cohorts"][name]
                    return SimpleNamespace(fingerprint=spec["sha256"],
                        queries=[SimpleNamespace(id=identity) for identity in spec["query_ids_original_order"]])
                def publish(arguments, run, phase):
                    events.append(phase)
                    key, state = phase.rsplit(" ", 1)
                    prefix = arguments.state_dir / "workers" / key
                    self.assertTrue(Path(str(prefix) + ".started.json").is_file())
                    if state == "completed":
                        self.assertTrue(Path(str(prefix) + ".attempts.jsonl.gz").is_file())
                    if state == fail_phase:
                        raise bench.CheckpointPublicationError("artificial push failure")
                def spawn(command, **kwargs):
                    key = command[command.index("--worker") + 1]
                    events.append(key + " launched")
                    run = json.loads((args.state_dir / "run.json").read_bytes())
                    worker = copy.deepcopy(next(w for w in original["workers"] if w["key"] == key))
                    worker["run_identity_sha256"] = bench.digest(run)
                    prefix = args.state_dir / "workers" / key
                    bench.atomic(Path(str(prefix) + ".json.gz"), worker, compressed=True)
                    ledger = ledger_bytes(worker)
                    Path(str(prefix) + ".attempts.jsonl").write_bytes(ledger)
                    Path(str(prefix) + ".attempts.jsonl.gz").write_bytes(gzip.compress(ledger, mtime=0))
                with patch.object(bench, "ROOT", root), \
                        patch.object(bench, "host_identity", return_value={"packages": bench.PACKAGES, "boot": "fixture"}), \
                        patch.object(bench, "source_identity", side_effect=lambda path: binding["sources"][path.name]), \
                        patch.object(bench, "dataset", side_effect=dataset), \
                        patch.object(bench, "file_hashes", return_value=original["run"]["evaluator_files"]), \
                        patch.object(bench, "publication_identity", return_value=publication), \
                        patch.object(bench, "claim_execution", return_value={"fixture": "claimed"}), \
                        patch.object(bench, "publish_checkpoint", side_effect=publish) as publisher, \
                        patch.object(bench.subprocess, "run", side_effect=spawn) as process, \
                        patch.dict(os.environ, {"GITHUB_SHA": "d" * 40}):
                    self.assertEqual(bench.controller_locked(args, plan, binding), 2)
                completed = int(fail_phase == "completed")
                self.assertEqual(process.call_count, completed)
                self.assertEqual(publisher.call_count, 1 + completed)
                saved = json.loads(gzip.decompress(args.output.read_bytes()))
                self.assertEqual(len(saved["workers"]), completed)
                self.assertEqual(saved["error"]["type"], "CheckpointPublicationError")
                self.assertEqual(saved["run"]["workflow_commit"], "d" * 40)
                self.assertFalse(saved["validation"]["passed"])
                self.assertFalse(saved["acceptance"]["accepted"])
                self.assertEqual(len(list((args.state_dir / "workers").glob("*.started.json"))), 1)
                self.assertTrue((args.output.parent / "controller-attempts/0001.finished.json").is_file())
                key = original["workers"][0]["key"]
                expected = [key + " started"] + ([key + " launched", key + " completed"] if completed else [])
                self.assertEqual(events, expected)

    def test_full_source_projection_rejects_invented_excerpt_and_wrong_scope(self):
        case = SimpleNamespace(id="fixture", category="fixture", query="alpha", project="p")
        text = "USER: alpha"
        native = {"query": "alpha", "context": "[page] p / s\n" + text,
            "context_chars": len("[page] p / s\n" + text), "budget_chars": 4000,
            "cache_hit": False, "results": [{"id": "page", "text": text,
                "breadcrumb": [{"id": "p"}], "excerpt_spans": [[0, len(text)]],
                "source_refs": [{"project": "p", "session_id": "s", "turn_index": 0,
                                 "turn_start": 0, "turn_end": len(text)}]}]}
        counters = {name: SimpleNamespace(count=len) for name in bench.ENCODINGS}
        config = {"surface": "native", "budget_chars": 4000, "budget_tokens": None}
        def measure():
            return bench.make_row(case, native, 1, bench.dump(native), None, native, config,
                counters, {("p", "s", 0): text}, {"page": text}, 0, 0, bench.BASELINE_HASH)
        self.assertFalse(any(measure()["invariants"].values()))
        # Registered synthetic cases also contain unscoped queries. None
        # permits genuine project references without disabling source checks.
        case.project = None
        self.assertFalse(any(measure()["invariants"].values()))
        case.project = "p"
        native["results"][0]["text"] += " invented"
        self.assertTrue(measure()["invariants"]["page_projection_errors"])
        native["results"][0]["source_refs"][0]["project"] = "foreign"
        self.assertTrue(measure()["invariants"]["source_scope_errors"])

    @unittest.skipUnless(importlib.util.find_spec("mcp"), "Optional real SDK is not installed")
    def test_actual_sdk_fixture_audits_same_call_cache_without_second_recall(self):
        # Artificial original source only. The deliberately simple counters
        # isolate this SDK/source/cache smoke from tokenizer downloads; formal
        # workers always construct the two pinned real TokenCounter instances.
        import memory_book
        from memory_book import MemoryBook
        source = Path(memory_book.__file__).resolve().parent
        case = SimpleNamespace(id="sdk-fixture", category="fixture", query="violet ledger", project="fixture")
        data = SimpleNamespace(queries=[case], sessions=[{"project": "fixture", "session_id": "one",
            "created_at": "2026-01-01T00:00:00Z", "messages": [
                {"role": "user", "content": "Where is the violet ledger?"},
                {"role": "assistant", "content": "The violet ledger is on shelf nine."}]}])
        config = {"id": "mcp-char4000", "surface": "official-sdk-mcp-stdio",
                  "budget_chars": 4000, "budget_tokens": None}
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            db_path = work / "fixture.db"
            with MemoryBook(db_path, cache_size=0) as book:
                book.ingest(data.sessions[0])
                native = book.recall(case.query, project=case.project, budget_chars=4000, limit=5, use_cache=False)
                native.pop("latency_ms")
                pages = {r["id"]: r["content"] for r in book.db.execute("SELECT id,content FROM pages")}
                report = {"source": {"runtime_sha256": bench.engine_source_hash(source)}}
                ledger = bench.Ledger(work / "attempts.jsonl")
                try:
                    # Unit-test sandboxes may hide child /proc entries. This
                    # fixture verifies the actual SDK/cache/source path only;
                    # formal workers still require real live-child RSS.
                    with patch.object(bench, "server_rss", return_value={"available": True,
                            "rss_bytes": 1, "hwm_bytes": 1}):
                        rows = asyncio.run(bench.mcp_configuration(data, config, [case.id], db_path, work,
                            source.parent, {name: SimpleNamespace(count=len) for name in bench.ENCODINGS},
                            bench.original_turn_texts(data), pages, report, ledger))
                finally:
                    ledger.close()
                self.assertEqual(len(rows), 1)
                self.assertFalse(any(rows[0]["invariants"].values()), rows[0]["invariants"])
                self.assertEqual(rows[0]["native_payload_sha256"], bench.digest(native))
                self.assertEqual(rows[0]["cache_rows_before"], 0)
                self.assertEqual(rows[0]["cache_rows_after"], 1)
                self.assertEqual(book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0], 0)
                self.assertTrue(report["mcp_server_memory_after_calls"]["available"])

    @unittest.skipUnless(importlib.util.find_spec("mcp") and importlib.util.find_spec("tiktoken"),
                         "Optional SDK and reference tokenizer are not installed")
    def test_actual_sdk_token_request_returns_both_metadata_surfaces_and_full_provenance(self):
        import memory_book
        from memory_book import MemoryBook
        source = Path(memory_book.__file__).resolve().parent
        case = SimpleNamespace(id="token-sdk-fixture", category="fixture", query="violet ledger", project="fixture")
        data = SimpleNamespace(queries=[case], sessions=[{"project": "fixture", "session_id": "one",
            "created_at": "2026-01-01T00:00:00Z", "messages": [
                {"role": "user", "content": "Where is the violet ledger?"},
                {"role": "assistant", "content": "The violet ledger is on shelf nine. Keep its sources intact."}]}])
        config = dict(bench.CONFIGURATIONS[-1])
        counters = {name: bench.TokenCounter(name) for name in bench.ENCODINGS}
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            db_path = work / "fixture.db"
            with MemoryBook(db_path, cache_size=0) as book:
                book.ingest(data.sessions[0])
                native = book.recall(case.query, project=case.project, budget_chars=8000,
                    budget_tokens=1024, tokenizer="cl100k_base", limit=5, use_cache=False)
                native.pop("latency_ms")
                pages = {row["id"]: row["content"] for row in book.db.execute("SELECT id,content FROM pages")}
                report = {"source": {"runtime_sha256": bench.engine_source_hash(source)}}
                ledger = bench.Ledger(work / "attempts.jsonl")
                try:
                    with patch.object(bench, "server_rss", return_value={"available": True, "rss_bytes": 1, "hwm_bytes": 1}):
                        rows = asyncio.run(bench.mcp_configuration(data, config, [case.id], db_path, work,
                            source.parent, counters, bench.original_turn_texts(data), pages, report, ledger))
                finally:
                    ledger.close()
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertFalse(any(row["invariants"].values()), row["invariants"])
                self.assertEqual(row["native_payload_sha256"], bench.digest(native))
                expected = {"budget_tokens": 1024, "tokenizer": "cl100k_base", "tokenizer_version": "0.12.0",
                            "context_tokens": counters["cl100k_base"].count(native["context"])}
                self.assertEqual(row["token_metadata"], {"native": expected, "response": expected})
                self.assertEqual(len(row["envelope_sha256"]), 64)
                self.assertEqual(set(report["mcp_sessions"]), {"mcp-token1024"})
                self.assertNotIn("mcp_startup_to_initialize_ms", report)  # No misleading character-session alias.
                self.assertEqual(len((work / "attempts.jsonl").read_text().splitlines()), 2)
                self.assertEqual(book.db.execute("SELECT COUNT(*) FROM recall_cache").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
