"""Artificial saved-record fixtures only. No SDK, product or real data calls."""
import copy
import gzip
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import round5_c7_mcp_development_pair as helper
from tests.test_round4_performance import ledger_bytes

frozen, c7 = helper.frozen, helper.c7
ARTIFICIAL = {"commit": "a" * 40, "runtime_sha256": "b" * 64}


def fixture(state):
    ids = ["ARTIFICIAL-" + str(index) for index in range(1015)]
    run = {"evaluator": helper.VERSION, "plan_sha256": helper.PLAN_SHA256,
        "sources": {"baseline": c7.BASELINE, "candidate": ARTIFICIAL},
        "schedule": list(helper.SCHEDULE), "query_ids_original_order": ids,
        "dataset_sha256": "c" * 64}
    report = {"run": run, "workers": []}
    frozen.atomic(state / "run.json", run)
    for item in helper.SCHEDULE:
        frozen.atomic(state / "workers" / (item["key"] + ".started.json"),
            {"worker": item, "run_identity_sha256": frozen.digest(run)})
        source = run["sources"][item["label"]]
        rows = []
        for identity in frozen.query_order(ids, item["round"], helper.CONFIG_INDEX):
            row = {"query_id": identity, "category": "ARTIFICIAL", "wall_ms": 2 if item["label"] == "baseline" else 3,
                "engine_source_sha256": source["runtime_sha256"],
                "payload_sha256": frozen.digest([identity, "payload"]),
                "native_payload_sha256": frozen.digest([identity, "native"]),
                "context_sha256": frozen.digest(identity), "envelope_sha256": frozen.digest([identity, "envelope"]),
                "response_utf8_bytes": 50, "envelope_utf8_bytes": 70,
                "context_chars": 10, "result_count": 1, "cache_rows_before": 0, "cache_rows_after": 1,
                "tokens": {name: {"context": 10, "response_text": 20, "response_envelope_json": 30}
                    for name in frozen.ENCODINGS},
                "token_metadata": {surface: {"budget_tokens": 1024, "tokenizer": "cl100k_base",
                    "tokenizer_version": "0.12.0", "context_tokens": 10} for surface in ("native", "response")},
                "invariants": {name: 0 for name in frozen.INVARIANTS}}
            rows.append(row)
        session = {"mcp_startup_to_initialize_ms": 1, "mcp_tool_schema_sha256": "d" * 64,
            "mcp_instructions_sha256": "e" * 64, "mcp_initialization_tokens": {},
            "mcp_server_memory_after_calls": {"available": True, "rss_bytes": 1000, "hwm_bytes": 1100},
            "storage_after_mcp_live": {"logical_database_bytes": 4096}}
        projection = {"source_snapshot_sha256": "f" * 64, "indexed_content": {"pages": "fixture"},
            "revision": 1, "cache_entries": 0}
        worker = {**item, "status": "completed", "error": None, "source": source, "source_after": source,
            "run_identity_sha256": frozen.digest(run), "dataset_sha256": run["dataset_sha256"],
            "all_replayed_sessions_skipped": True, "archive_before": projection, "archive_after": projection,
            "fresh_ingestion_results_sha256": "1" * 64, "unchanged_reingestion_results_sha256": "2" * 64,
            "configurations": [{**helper.CONFIG, "rows": rows,
                "latency": frozen.latency_summary([row["wall_ms"] for row in rows])}],
            "mcp_sessions": {helper.CONFIG["id"]: session}}
        save(state, worker)
        report["workers"].append(worker)
    return report


def save(state, worker):
    raw = ledger_bytes(worker)
    worker["ledger_sha256"] = frozen.sha(raw)
    frozen.atomic(state / "workers" / (worker["key"] + ".json.gz"), worker, compressed=True)
    path = state / "workers" / (worker["key"] + ".attempts.jsonl.gz")
    path.write_bytes(gzip.compress(raw, mtime=0))
    return raw


class HelperFixtures(unittest.TestCase):
    def test_missing_source_blocks_every_execution_entry_before_read(self):
        with patch.object(c7, "C7_SOURCE", {"commit": None, "runtime_sha256": None}), \
                patch.object(Path, "read_bytes", side_effect=AssertionError("Source guard must precede file reads")):
            for call in (helper.registered_inputs, lambda: helper.main([]),
                         lambda: helper.worker(SimpleNamespace())):
                with self.assertRaisesRegex(ValueError, "C7 is blocked"):
                    call()

    def test_all_rows_all_events_adverse_values_and_corruption(self):
        with patch.object(c7, "C7_SOURCE", ARTIFICIAL), tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            report = fixture(state)
            verified = helper.inspect_saved(report, state)
            self.assertEqual((verified["timed_calls"], verified["complete_output_pairs"], verified["ledger_events"]),
                (4060, 2030, 8120))
            self.assertEqual(len(verified["adverse_metrics"]), 9)
            self.assertTrue(all(row["change_percent"] == 50 for row in verified["adverse_metrics"]))
            self.assertEqual(len(verified["first_queries_retained"]), 4)
            self.assertFalse(verified["formal_acceptance_evaluated"])
            worker = report["workers"][-1]
            raw = ledger_bytes(worker)
            with self.assertRaisesRegex(ValueError, "ledger bytes changed"):
                helper.validate_saved_worker(worker, report["run"], raw + b"{}\n")
            worker["configurations"][0]["rows"][0]["envelope_sha256"] = "0" * 64
            save(state, worker)
            with self.assertRaisesRegex(ValueError, "Complete MCP/native/envelope output differs"):
                helper.inspect_saved(report, state)
            worker["mcp_sessions"][helper.CONFIG["id"]]["mcp_server_memory_after_calls"]["available"] = False
            raw = save(state, worker)
            with self.assertRaisesRegex(ValueError, "resource observation is missing"):
                helper.validate_saved_worker(worker, report["run"], raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
