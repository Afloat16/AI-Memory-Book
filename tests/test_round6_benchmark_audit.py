"""Independent numerical/ledger/source adversarial fixtures; no retrieval."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import round6_audit_performance as audit
from scripts import round6_performance as benchmark
from tests.test_round6_benchmark import acceptance_fixture, memo_snapshot, plan_fixture, set_nested


def row_fixture(spec=None):
    spec = spec or audit.CONFIGS[-1]
    mcp = spec["surface"] == "official-sdk-mcp-stdio"
    metadata = {"budget_tokens": spec["budget_tokens"], "tokenizer": "cl100k_base", "tokenizer_version": "0.12.0", "context_tokens": 100}
    return {"query_id": "fixture-query", "category": "fixture", "wall_ms": 2.0,
        "engine_source_sha256": "a" * 64, "payload_sha256": "b" * 64, "native_payload_sha256": "c" * 64,
        "context_sha256": "d" * 64, "envelope_sha256": "e" * 64 if mcp else None,
        "response_utf8_bytes": 200, "envelope_utf8_bytes": 300 if mcp else None,
        "context_chars": 150, "result_count": 1, "cache_rows_before": 0, "cache_rows_after": 1 if mcp else 0,
        "tokens": {name: {"context": 100, "response_text": 200, "response_envelope_json": 250 if mcp else None}
                   for name in ("cl100k_base", "o200k_base")},
        "token_metadata": {"native": metadata, "response": metadata} if spec["budget_tokens"] is not None else None,
        "invariants": {name: False for name in audit.INVARIANTS}}


def archive_fixture():
    semantic = {table: {"columns": fields, "excluded_host_columns": audit.EXCLUDED.get(table, []), "rows": 1, "sha256": "b" * 64}
                for table, fields in audit.SOURCE_COLUMNS.items()}
    indexed = {name: {"rows": 1, "sha256": "c" * 64} for name in ("pages", "sections", "turns", "chapters", "sessions", "pages_fts", "pages_stem_fts")}
    return {"source_snapshot_before": "a" * 64, "source_snapshot_after": "a" * 64,
        "source_semantics_before": semantic, "source_semantics_after": deepcopy(semantic), "indexed_content": indexed,
        "indexed_content_after_calls": deepcopy(indexed), "all_replayed_sessions_skipped": True, "native_recall_cache_rows": 0,
        "fresh_ingestion_results_sha256": "d" * 64, "unchanged_reingestion_results_sha256": "e" * 64}


class RoundSixAuditTests(unittest.TestCase):
    def test_independent_percentiles_preserve_extreme_samples(self):
        self.assertEqual(audit.quantile([1, 2, 4, 8], .5), 3)
        self.assertAlmostEqual(audit.quantile([1, 2, 4, 8], .95), 7.4)
        self.assertGreater(audit.latency([1, 2, 4, 800])["p95_ms"], 600)

    def test_independent_recomputation_matches_every_approved_gate(self):
        report, compared = acceptance_fixture()
        spec = report["run"]["measurement"]
        independently = audit.recompute_acceptance("formal", report["workers"], spec["cohorts"], spec["configs"], compared)
        audit.close(benchmark.acceptance(report, compared), independently)
        self.assertTrue(independently["accepted"])

    def test_missing_summary_fields_or_nonfinite_numbers_rejected(self):
        for actual, expected in (({}, {"gain": 10.0}), ({"gain": float("nan")}, {"gain": 10.0}), ({"gain": 10.0001}, {"gain": 10.0})):
            with self.assertRaises(ValueError):
                audit.close(actual, expected)

    def test_independent_raw_resource_failure_stays_false(self):
        report, compared = acceptance_fixture()
        for worker in report["workers"]:
            if worker["label"] == "candidate":
                worker["native_open_ms"] = 111
        spec = report["run"]["measurement"]
        result = audit.recompute_acceptance("formal", report["workers"], spec["cohorts"], spec["configs"], compared)
        self.assertTrue(result["numeric_gate_passed"])
        self.assertFalse(result["accepted"])
        altered = deepcopy(result)
        altered["accepted"] = True
        with self.assertRaises(ValueError):
            audit.close(altered, result)

    def test_every_complete_payload_field_is_stable_except_time_source(self):
        original = row_fixture()
        changed = deepcopy(original)
        changed.update(wall_ms=99, engine_source_sha256="f" * 64)
        self.assertEqual(audit.stable(original), audit.stable(changed))
        changed["native_payload_sha256"] = "0" * 64
        self.assertNotEqual(audit.stable(original), audit.stable(changed))

    def test_response_provenance_budget_cache_boundaries(self):
        spec, source = audit.CONFIGS[-1], {"runtime_sha256": "a" * 64}
        audit.verify_row(row_fixture(spec), spec, source)
        changes = (lambda r: r.update(wall_ms=0), lambda r: r.update(cache_rows_before=1),
            lambda r: r.update(envelope_sha256=None), lambda r: r["invariants"].pop("source_span_errors"),
            lambda r: r["invariants"].update(source_span_errors=1), lambda r: r.update(result_count=6),
            lambda r: r["tokens"]["cl100k_base"].update(context=1025))
        for mutation in changes:
            row = row_fixture(spec)
            mutation(row)
            with self.assertRaises(ValueError):
                audit.verify_row(row, spec, source)

    def test_original_attempt_ledger_rejects_missing_duplicate_changed_calls(self):
        row = row_fixture()
        start = {"event": "started", "seq": 0, "config": "mcp-token1024", "query_id": row["query_id"]}
        finish = {"event": "finished", "seq": 0, "config": "mcp-token1024", "row": row}
        encode = lambda values: b"\n".join(json.dumps(v).encode() for v in values) + b"\n"
        self.assertEqual(audit.verify_ledger(encode([start, finish]), [("mcp-token1024", row)]), 2)
        changed = deepcopy(finish)
        changed["row"]["wall_ms"] = 1.9
        for events in ([start], [start, finish, start, finish], [start, changed], [{**start, "seq": 1}, finish]):
            with self.assertRaises(ValueError):
                audit.verify_ledger(encode(events), [("mcp-token1024", row)])

    def test_cross_archive_host_time_is_not_confused_with_intra_archive_mutation(self):
        record = archive_fixture()
        audit.verify_archive(record)
        record["source_snapshot_after"] = "f" * 64
        with self.assertRaises(ValueError):
            audit.verify_archive(record)

    def test_projection_cannot_silently_drop_source_dates_or_project_names(self):
        for table, field in (("projects", "name"), ("sessions", "created_at")):
            record = archive_fixture()
            record["source_semantics_before"][table]["columns"] = [c for c in record["source_semantics_before"][table]["columns"] if c != field]
            record["source_semantics_after"] = deepcopy(record["source_semantics_before"])
            with self.assertRaises(ValueError):
                audit.verify_archive(record)

    def test_independent_memo_check_catches_warm_initial_baseline(self):
        spec = audit.CONFIGS[0]
        snapshot = memo_snapshot(allocated=1, entries=1, text_bytes=1)
        worker = {"configurations": [{**spec, "rows": [row_fixture(spec)]}], "native_token_count_memo":
            {"entry_limit": 2048, "text_byte_limit": 2097152, "configurations": [{"id": spec["id"], "first_query_id": "fixture-query",
                "before": snapshot, "after_first_call": snapshot, "after": snapshot}]}}
        with self.assertRaises(ValueError):
            audit.verify_memo(worker, [spec])

    def test_independent_resource_axes_match_without_extra_or_missing_costs(self):
        for stage in ("formal", "development-native", "development-mcp"):
            cohorts, configs, orders, calls = audit.matrix(stage)
            self.assertEqual(audit.resources_for(configs), benchmark.resource_fields({"configs": configs}))
            self.assertEqual(sum(audit.COHORTS[name]["queries"] for name in cohorts) * len(configs) * len(orders) * 2, calls)


class SavedObservationIntegrationTests(unittest.TestCase):
    def build_saved_fixture(self, root):
        # Synthetic numbers and payload hashes only. This never imports or
        # invokes MemoryBook, an MCP server, a tokenizer or a clock timer.
        blobs = {name: ("immutable fixture for " + name + "\n").encode() for name in (*audit.HELPERS, *audit.NEW_FILES)}
        blobs["benchmarks/locomo_split.json"] = json.dumps({"sha256": "1" * 64}).encode()
        plan = plan_fixture()
        blobs[audit.PLAN_PATH] = json.dumps(plan).encode()
        configs = [dict(audit.CONFIGS[-1])]
        spec = {**plan["performance_candidate"]["formal"], "configs": configs, "cohorts": ["public1015"],
                "rounds": 2, "engine_order": audit.ORDERS[:2], "calls": 4060}
        sources = {"baseline": audit.BASELINE, "candidate": {"commit": "2" * 40, "runtime_sha256": "3" * 64}}
        binding = {"schema_version": 1, "evaluator": audit.VERSION, "stage": "development-mcp", "status": "frozen-before-measurement",
            "plan_commit": audit.PLAN_COMMIT, "plan_sha256": audit.sha(blobs[audit.PLAN_PATH]), "evaluator_commit": "4" * 40,
            "sources": sources, "packages": audit.PACKAGES, "measurement": spec,
            "evaluator_files": {name: audit.sha(blobs[name]) for name in (*audit.HELPERS, *audit.NEW_FILES)}, "evidence": {}}
        binding_name = "benchmarks/experiments/round6-development-mcp-binding.json"
        blobs[binding_name] = json.dumps(binding).encode()
        ids = ["fixture-query-" + str(i) for i in range(1015)]
        cohort = {**audit.COHORTS["public1015"], "query_ids": sorted(ids), "query_ids_original_order": ids}
        schedule = [{"key": f"r{rep}-public1015-{label}", "round": rep, "cohort": "public1015", "label": label}
            for rep, pair in enumerate(audit.ORDERS[:2]) for label in pair]
        pair_key = audit.digest({"stage": "development-mcp", "sources": {k: v["runtime_sha256"] for k, v in sources.items()}})
        public = root / "benchmarks/reports/round6-development-mcp-123-1"
        path = public / "report.json.gz"
        run = {"evaluator": audit.VERSION, "stage": "development-mcp", "measurement": spec, "plan_sha256": binding["plan_sha256"],
            "binding": binding, "binding_sha256": audit.sha(blobs[binding_name]), "binding_path": binding_name,
            "evaluator_files": binding["evaluator_files"], "cohorts": {"public1015": cohort}, "schedule": schedule,
            "host": {"packages": audit.PACKAGES, "boot_sha256": "5" * 64, "machine_sha256": "6" * 64, "github_run_id": "123", "github_run_attempt": "1"},
            "locomo_file_sha256": "1" * 64, "output": str(path),
            "publication": {"run_id": "123", "run_attempt": "1", "branch": "validation/v034-round6-development-mcp-123-1",
                "claim_branch": "validation/v034-round6-claim-" + pair_key, "source_pair_stage_sha256": pair_key}}
        def save(location, value, compressed=False):
            raw = audit.canonical(value) + b"\n"
            content = gzip.compress(raw, mtime=0) if compressed else raw
            blobs[location.relative_to(root).as_posix()] = content
            return raw, content
        save(public / "run.json", run)
        save(public / "execution.json", {"evaluator": audit.VERSION, "binding_sha256": run["binding_sha256"],
            "run_identity_sha256": audit.digest(run), "host": run["host"], "output": str(path)})
        save(public / "resource-preflight.json", {"product_calls": 0, "sdk_sessions": 0,
            "observation": {"available": True, "rss_bytes": 100, "hwm_bytes": 100}})
        workers = []
        for item in schedule:
            worker = {**item, **archive_fixture(), "run_identity_sha256": audit.digest(run), "status": "completed", "error": None,
                "source": sources[item["label"]], "source_after": sources[item["label"]], "dataset_sha256": cohort["sha256"],
                "native_token_count_memo": benchmark.memo_diagnostics(), "mcp_sessions": {"mcp-token1024": {
                    "mcp_tool_schema_sha256": "7" * 64, "mcp_instructions_sha256": "8" * 64,
                    "mcp_initialization_tokens": {"cl100k_base": {"tool_schema": 2, "instructions": 3}, "o200k_base": {"tool_schema": 2, "instructions": 3}},
                    "mcp_server_memory_after_calls": {"available": True}}}}
            for field in audit.resources_for(configs):
                set_nested(worker, field, 100)
            # Full host timestamps can differ BETWEEN archives, never within one.
            worker["source_snapshot_before"] = worker["source_snapshot_after"] = audit.digest(item)
            order = list(ids)
            audit.random.Random(41061 + 1009 * item["round"]).shuffle(order)
            rows, ledger = [], []
            for sequence, identity in enumerate(order):
                row = row_fixture(configs[0])
                row.update(query_id=identity, engine_source_sha256=sources[item["label"]]["runtime_sha256"],
                           wall_ms=1.0 if item["label"] == "baseline" else 0.8)
                rows.append(row)
                ledger.extend([{"event": "started", "seq": sequence, "config": "mcp-token1024", "query_id": identity, "at": "fixture"},
                    {"event": "finished", "seq": sequence, "config": "mcp-token1024", "row": row, "at": "fixture"}])
            worker["configurations"] = [{**configs[0], "rows": rows, "latency": benchmark.latency_summary([r["wall_ms"] for r in rows])}]
            raw_ledger = b"\n".join(audit.canonical(event) for event in ledger) + b"\n"
            worker["ledger_sha256"] = audit.sha(raw_ledger)
            prefix = public / "workers" / item["key"]
            save(Path(str(prefix) + ".started.json"), {"worker": item, "run_identity_sha256": audit.digest(run)})
            save(Path(str(prefix) + ".json.gz"), worker, True)
            blobs[Path(str(prefix) + ".attempts.jsonl.gz").relative_to(root).as_posix()] = gzip.compress(raw_ledger, mtime=0)
            benchmark.verify_worker(worker, run, plan, ledger=raw_ledger)
            workers.append(worker)
        report = {"schema_version": 1, "evaluator": audit.VERSION, "status": "measurements_completed", "error": None,
            "evaluator_unchanged": True, "run": run, "plan": plan, "workers": workers}
        report["validation"] = benchmark.validation(report)
        self.assertTrue(report["validation"]["passed"], report["validation"])
        report["comparisons"] = benchmark.comparisons(report)
        report["acceptance"] = benchmark.acceptance(report, report["comparisons"])
        raw, compressed = save(path, report, True)
        save(public / "report.summary.json", benchmark.legacy.summary(report, compressed, raw))
        for name, content in blobs.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return path, public, blobs, sources

    def test_complete_saved_diagnostic_roundtrip_and_tampered_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, state, blobs, sources = self.build_saved_fixture(root)
            def git(*args):
                self.assertEqual(args[0], "show")
                return blobs[args[1].split(":", 1)[1]]
            def source_hash(commit):
                return next(value["runtime_sha256"] for value in sources.values() if value["commit"] == commit)
            with patch.object(audit, "ROOT", root), patch.object(audit, "git", side_effect=git), patch.object(audit, "source_hash", side_effect=source_hash):
                result = audit.audit(path, state, result_commit="9" * 40)
                self.assertTrue(result["passed"])
                self.assertEqual((result["timed_calls"], result["complete_output_pairs"], result["ledger_events"]), (4060, 2030, 8120))
                self.assertFalse(result["original_automatic_accepted"])
                self.assertIsNone(result["numeric_gate_passed"])
                summary_path = state / "report.summary.json"
                summary = json.loads(summary_path.read_bytes())
                summary["acceptance"]["accepted"] = True
                summary_path.write_text(json.dumps(summary))
                with self.assertRaisesRegex(ValueError, "Compact summary differs"):
                    audit.audit(path, state)


if __name__ == "__main__":
    unittest.main()
