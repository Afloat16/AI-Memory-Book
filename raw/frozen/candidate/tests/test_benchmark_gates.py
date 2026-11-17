"""Invalid measurements fail explicitly while retaining diagnostic artifacts."""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from benchmarks import component_eval, token_compare


def engine_record(label="candidate"):
    metrics = {"evidence_recall": 0.0, "complete_evidence_rate": 0.0,
               "mean_context_tokens": {name: 0.0 for name in token_compare.ENCODINGS},
               "budget_violations": 0, "context_size_mismatches": 0}
    latency = {"p50_ms": 0.0, "p95_ms": 0.0}
    return {"label": label, "engine_version": "fixture",
            "dataset": {"sha256": "same-dataset", "queries": 1},
            "source_sha256_before": "stable", "source_sha256_after": "stable",
            "source_unchanged": True,
            "configurations": [{"budget_chars": 2000, "metrics": copy.deepcopy(metrics),
                                "latency": latency, "query_results": [{"id": "q-1"}]}],
            "packed_configurations": [{"tokenizer": "o200k_base", "budget_tokens": 512,
                                       "metrics": copy.deepcopy(metrics),
                                       "packing_latency": latency, "token_budget_violations": 0,
                                       "query_results": [{"id": "q-1"}]}],
            "metadata": {}, "adapter_roundtrip_latency": latency,
            "native_query_costs": [{"id": "q-1"}]}


class BenchmarkGateTests(unittest.TestCase):
    def test_gates_do_not_require_a_favorable_quality_score_or_clean_checkout(self):
        record = engine_record()
        record["source_provenance"] = {"source_dirty": True, "commit_identifies_source": False}
        self.assertTrue(token_compare.validation_status([record])["passed"])
        external = {"label": "external", "metadata": {"version": "pinned"},
                    "packed_configurations": record["packed_configurations"]}
        self.assertTrue(token_compare.validation_status([external])["passed"])

    def test_each_recorded_budget_invariant_fails_independently(self):
        cases = [(collection, check) for collection in ("configurations", "packed_configurations")
                 for check in ("budget_violations", "context_size_mismatches")]
        cases.append(("packed_configurations", "token_budget_violations"))
        for collection, check in cases:
            with self.subTest(collection=collection, check=check):
                record = engine_record()
                config = record[collection][0]
                target = config if check == "token_budget_violations" else config["metrics"]
                target[check] = 1
                status = token_compare.validation_status([record])
                self.assertFalse(status["passed"])
                self.assertEqual(status["failures"][0]["check"], check)
                self.assertEqual(status["failures"][0]["configuration"]["collection"], collection)

    def test_source_hash_mismatch_overrides_a_claimed_unchanged_flag(self):
        record = engine_record()
        record["source_sha256_after"] = "changed"
        self.assertFalse(token_compare.validation_status([record])["passed"])
        component = engine_record()
        component["metadata"] = {"source_sha256": "before", "source_sha256_after": "after",
                                 "source_unchanged": True}
        self.assertFalse(token_compare.validation_status([component])["passed"])

    def test_workers_save_failed_measurement_records_before_returning_nonzero(self):
        for module, worker in ((token_compare, None), (component_eval, "measure"),
                               (component_eval, "export")):
            with self.subTest(module=module.__name__, worker=worker), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "diagnostic.json"
                record = engine_record()
                if worker == "export":
                    record["source_unchanged"] = False
                    measure_name = "export_frozen"
                elif worker == "measure":
                    record["packed_configurations"][0]["token_budget_violations"] = 1
                    measure_name = "measure_component"
                else:
                    record["configurations"][0]["metrics"]["context_size_mismatches"] = 1
                    measure_name = "measure_engine"
                arguments = ["benchmark", "--baseline-src", directory, "--worker"]
                if worker is not None:
                    arguments.extend([worker, "--cache", directory])
                arguments.extend(["--output", str(output)])
                with patch.object(sys, "argv", arguments), patch.object(module, measure_name, return_value=record):
                    self.assertEqual(module.main(), 2)
                saved = json.loads(output.read_text())
                self.assertFalse(saved["validation"]["passed"])
                self.assertEqual(saved["configurations"][0]["query_results"], [{"id": "q-1"}])

    def test_paired_parent_keeps_failed_worker_report_after_temporary_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "paired"

            def worker(command, **kwargs):
                label = command[command.index("--label") + 1]
                record = engine_record(label)
                failed = label == "candidate"
                if failed:
                    record["configurations"][0]["metrics"]["budget_violations"] = 1
                Path(command[command.index("--output") + 1]).write_text(json.dumps(record))
                return subprocess.CompletedProcess(command, 2 if failed else 0)

            arguments = ["token_compare", "--baseline-src", directory, "--candidate-src", directory,
                         "--output", str(prefix)]
            with patch.object(sys, "argv", arguments), \
                    patch.object(token_compare.subprocess, "run", side_effect=worker), \
                    patch.object(token_compare.platform, "platform", return_value="fixture"), \
                    patch("builtins.print"):
                self.assertEqual(token_compare.main(), 2)
            summary = json.loads(Path(str(prefix) + ".summary.json").read_text())
            full = json.loads(gzip.decompress(Path(str(prefix) + ".json.gz").read_bytes()))
            self.assertFalse(summary["validation"]["passed"])
            self.assertEqual(len(full["engines"]), 2)
            self.assertEqual(full["engines"][1]["configurations"][0]["query_results"], [{"id": "q-1"}])
            self.assertIn("**FAILED:", Path(str(prefix) + ".md").read_text())

    def test_component_parent_retains_failed_export_and_does_not_run_rankers(self):
        self._component_parent_failure(changed_export=True)

    def test_component_parent_retains_failed_measurement(self):
        self._component_parent_failure(changed_export=False)

    def _component_parent_failure(self, *, changed_export):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "components"
            calls = []

            def worker(command, **kwargs):
                kind = command[command.index("--worker") + 1]
                calls.append(kind)
                if kind == "export":
                    record = {"label": "baseline", "source_sha256_before": "before",
                              "source_sha256_after": "after" if changed_export else "before",
                              "source_unchanged": not changed_export}
                    Path(command[command.index("--database") + 1]).write_bytes(b"fixture database")
                    failed = changed_export
                else:
                    record = engine_record()
                    record["metadata"] = {"source_sha256": "before", "source_sha256_after": "after",
                                          "source_unchanged": False}
                    failed = True
                Path(command[command.index("--output") + 1]).write_text(json.dumps(record))
                return subprocess.CompletedProcess(command, 2 if failed else 0)

            arguments = ["component_eval", "--baseline-src", directory, "--candidate-src", directory,
                         "--cache", directory, "--engines", "candidate", "--output", str(prefix)]
            with patch.object(sys, "argv", arguments), \
                    patch.object(component_eval.subprocess, "run", side_effect=worker), \
                    patch.object(component_eval.platform, "platform", return_value="fixture"), \
                    patch.object(component_eval, "TokenCounter", return_value=SimpleNamespace(version="fixture")), \
                    patch("builtins.print"):
                self.assertEqual(component_eval.main(), 2)
            summary = json.loads(Path(str(prefix) + ".summary.json").read_text())
            full = json.loads(gzip.decompress(Path(str(prefix) + ".json.gz").read_bytes()))
            self.assertFalse(summary["validation"]["passed"])
            self.assertEqual(calls, ["export"] if changed_export else ["export", "measure"])
            self.assertEqual(len(full["engines"]), 0 if changed_export else 1)
            self.assertIn("**FAILED:", Path(str(prefix) + ".md").read_text())

    def test_component_source_change_is_recorded_after_database_close(self):
        engine = component_eval.CoreBook.__new__(component_eval.CoreBook)
        engine.book = Mock()
        engine.source_root = Path("fixture")
        engine.source_hash = "before"
        engine.metadata = {"source_sha256": "before"}
        with patch.object(component_eval, "engine_source_hash", return_value="after"):
            engine.close()
        engine.book.close.assert_called_once_with()
        self.assertFalse(token_compare.validation_status([
            {"label": "candidate", "metadata": engine.metadata}])["passed"])


if __name__ == "__main__":
    unittest.main()
