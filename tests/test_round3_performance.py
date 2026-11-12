"""Artificial failure fixtures only; no benchmark input or retrieval is loaded."""
import copy
import asyncio
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round3_performance as bench


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
    formal = plan["performance_candidate"]["formal"]
    formal["calls"] = 5 * 5 * 2 * 4
    sources = {"baseline": {"commit": bench.BASELINE, "runtime_sha256": bench.BASELINE_HASH},
               "candidate": {"commit": "a" * 40, "runtime_sha256": bench.digest("candidate")}}
    run = {"binding": {"sources": sources}, "evaluator_files": {"fixture": "hash"},
        "host": {"boot": "same-boot"}, "schedule": bench.schedule(plan),
        "cohorts": {name: {"queries": len(ids), "sha256": bench.digest(name),
                           "query_ids": sorted(ids), "query_ids_original_order": ids}
                    for name, ids in (("synthetic61", ["b", "a"]), ("public1015", ["z", "y", "x"]))}}
    report = {"plan": plan, "run": run, "workers": [], "evaluator_unchanged": True, "error": None}
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
            "configurations": []}
        for index, config in enumerate(formal["configs"]):
            rows = []
            mcp = config["surface"] == "official-sdk-mcp-stdio"
            ids = bench.query_order(run["cohorts"][item["cohort"]]["query_ids_original_order"], item["round"], index)
            for position, identity in enumerate(ids):
                elapsed = (10 + item["round"] * .01 + position * .001) * (factor if item["label"] == "candidate" else 1)
                row = {"query_id": identity, "category": "fixture", "wall_ms": elapsed,
                    "engine_source_sha256": sources[item["label"]]["runtime_sha256"],
                    "payload_sha256": bench.digest([identity, config["id"]]),
                    "native_payload_sha256": bench.digest([identity, "native-char4000" if mcp else config["id"]]),
                    "context_sha256": bench.digest(identity), "envelope_sha256": bench.digest(identity) if mcp else None,
                    "response_utf8_bytes": 50, "envelope_utf8_bytes": 70 if mcp else None,
                    "context_chars": 10, "result_count": 1, "cache_rows_before": 0, "cache_rows_after": 1 if mcp else 0,
                    "tokens": {name: {"context": 10, "response_text": 20,
                                      "response_envelope_json": 30 if mcp else None} for name in bench.ENCODINGS},
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
    def test_complete_abba_matrix_first_repeat_and_sorted_roundtrip(self):
        report = fixture()
        self.assertTrue(report["validation"]["passed"], report["validation"])
        self.assertEqual(report["validation"]["timed_calls"], 200)
        self.assertEqual(len(report["workers"]), 16)
        self.assertEqual([w["label"] for w in report["run"]["schedule"] if w["cohort"] == "synthetic61"],
                         ["baseline", "candidate", "candidate", "baseline", "candidate", "baseline", "baseline", "candidate"])
        compared = bench.comparisons(report)
        self.assertEqual(len(compared), 10)
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

    def test_attempt_ledger_must_match_every_started_and_finished_row(self):
        report = fixture()
        worker = report["workers"][0]
        ledger = ledger_bytes(worker)
        self.assertEqual(bench.verify_worker(worker, report["run"], report["plan"], ledger=ledger), 10)
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
                    patch.object(bench, "file_hashes", return_value=report["run"]["evaluator_files"]):
                self.assertEqual(bench.audit(output, state)["retrieval_calls_executed"], 0)
                summary = output.with_name("fixture.summary.json")
                value = json.loads(summary.read_bytes())
                value["full_report_sha256"] = "bad"
                summary.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "Summary or raw hashes"):
                    bench.audit(output, state)

    def test_zero_or_partial_workers_preserve_failure_report_and_all_ten_cells(self):
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
                self.assertEqual(len(saved["comparisons"]), 10)
                self.assertFalse(saved["acceptance"]["accepted"])
                self.assertTrue(path.with_name("partial.summary.json").is_file())

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


if __name__ == "__main__":
    unittest.main()
