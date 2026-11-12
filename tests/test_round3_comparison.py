"""Artificial interface/measurement fixtures; never open a real cohort."""
import copy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import round3_comparison as c
from scripts.smoke_round2_components import fixture


class Counter:
    version = "0.12.0"
    def __init__(self, name):
        self.name = name
    def count(self, text):
        return len(text)


def resources():
    return {"sampling_interval_ms": 20, "samples": {"setup": 1, "queries": 1},
            "sampled_process_tree_peak_rss_bytes": {"setup": 1024, "queries": 2048}}


def finish(report, ledger, path):
    ledger.close()
    report.update(status="completed", resources=resources(), ledger_sha256=c.file_sha(path),
        attempts_started=ledger.started, attempts_finished=ledger.finished,
        attempt_states=[json.loads(line) for line in path.read_text().splitlines()])


def small_plan():
    return json.loads(c.PLAN.read_bytes())


def binding():
    return {"baseline": c.BASELINE, "candidate": c.BASELINE,
        "optional_project_statistics": False, "upstream_locks": c.reused.UPSTREAM_LOCKS}


class Engine:
    def __init__(self, stage, bundle, *, empty=False):
        self.stage, self.empty = stage, empty
        self.documents = {doc["project"]: doc for doc in bundle["documents"]}
        self.searches, self.reads, self.closed = [], [], False
        name = {"claude-mem-fts": "claude-mem", "ai-memory-hybrid": "ai-memory", "billion-context": "billion-context"}[stage]
        lock = json.loads((c.ROOT / c.reused.UPSTREAM_LOCKS[name]).read_bytes())
        self.metadata = {"commit": lock["commit"], "source_unchanged": True}
        if stage == "ai-memory-hybrid":
            self.metadata.update(binary_sha256=lock["binary_sha256"], embedding_provider="local",
                                 embedding_model={"files": lock["embedding_model"]["files"]})

    def search(self, query, project, limit):
        self.searches.append((project, limit))
        doc = self.documents[project]
        elapsed = 2.0 if project.endswith("a") else 20.0
        common = {"search_ms": elapsed, "bridge_ms": elapsed}
        if self.stage == "claude-mem-fts":
            rows = [] if self.empty else [{"id": doc["id"], "project": project, "text": doc["text"]}]
            return {**common, "hit_ids": [] if self.empty else [doc["id"]], "native_payload": rows}
        if self.stage == "billion-context":
            return {**common, "results": [] if self.empty else [{"ref": doc["id"], "preview": doc["text"]}]}
        rows = [] if self.empty else [{"id": "metadata-" + project, "project": project, "workspace": "benchmark"},
            {"id": "native-" + doc["id"], "project": project, "workspace": "benchmark"}]
        return {**common, "hit_ids": [] if self.empty else [None, doc["id"]], "results": rows,
            "native_payload": {"content": rows}, "native_text": "native snippet and metadata"}

    def read(self, identity):
        self.reads.append(identity)
        doc = next(doc for doc in self.documents.values() if doc["id"] == identity)
        return {"result": {"body": doc["text"], "truncated": False}, "native_text": doc["text"],
            "native_payload": {"text": doc["text"], "id": identity},
            "read_ms": 10.0 if identity.endswith("a") else 1.0}

    def close(self):
        self.closed = True


class RoundThreeComparisonTests(unittest.TestCase):
    def run_component(self, stage, directory, *, empty=False):
        data, bundle = fixture()
        engine = Engine(stage, bundle, empty=empty)
        report = {"stage": stage, "timing_rows": [], "configurations": []}
        path = Path(directory) / "attempts.jsonl"
        ledger = c.reused.Ledger(path)
        with patch.object(c, "TokenCounter", Counter), patch.object(c, "component_engine", return_value=(engine, None)):
            c.component(SimpleNamespace(stage=stage), small_plan(), binding(), data, bundle,
                        report, ledger, SimpleNamespace(set_phase=lambda _: None))
        finish(report, ledger, path)
        c.verify_report(report, small_plan(), binding(), [case.id for case in data.queries])
        return report, engine

    def test_exact_registered_axes_and_only_prebound_optional_axis(self):
        plan = small_plan()
        b = binding()
        self.assertEqual(len(c.stages(b)), 10)
        configs = c.reused.native_configurations(c.old_shape_plan(plan, b, "candidate-native"))
        self.assertEqual(len(configs), 6)
        self.assertEqual({tuple(row.values()) for row in configs},
            {(8000, encoding, cap) for encoding in c.ENCODINGS for cap in (512, 1024, 2048)})
        self.assertEqual(len(c.NATIVE) * len(configs) * 256, 4608)
        self.assertEqual(len(c.COMPONENTS) * 256 * 3, 4608)
        b["optional_project_statistics"] = True
        self.assertEqual(len(c.stages(b)), 12)
        self.assertIn("candidate-statistics-native", c.stages(b))
        self.assertEqual(c.mode("candidate-semantic-native"), {"baseline": False, "semantic": True, "statistics": False})

    def test_all_external_response_contracts_reach_all_six_packing_configs(self):
        for stage in ("claude-mem-fts", "billion-context", "ai-memory-hybrid"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                report, engine = self.run_component(stage, directory)
                self.assertEqual(len(engine.searches), 6)
                self.assertTrue(engine.closed)
                self.assertEqual(len(report["configurations"]), 6)
                self.assertEqual(report["attempts_started"], report["attempts_finished"])
                self.assertTrue(all(config["metrics"]["complete_evidence_rate"] == 1 for config in report["configurations"]))
                if stage == "ai-memory-hybrid":
                    self.assertEqual(len(engine.reads), 2)
                    self.assertEqual(report["native_costs"]["unmapped_native_hits"], 2)
                    self.assertTrue(all(row["native_hit_ids"][0] is None for row in report["timing_rows"]))
                    self.assertEqual(report["first_pass_search_plus_all_reads_latency"], c.latency_summary([12.0, 21.0]))
                    self.assertNotEqual(report["first_pass_search_plus_all_reads_latency"]["p95_ms"],
                        c.latency_summary([2.0, 20.0])["p95_ms"] + c.latency_summary([10.0, 1.0])["p95_ms"])
                else:
                    self.assertEqual(engine.reads, [])
                    self.assertIsNone(report["native_costs"]["mean_search_content_tokens"])

    def test_empty_native_payloads_remain_valid_zero_evidence_cases(self):
        for stage in ("claude-mem-fts", "billion-context", "ai-memory-hybrid"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                report, engine = self.run_component(stage, directory, empty=True)
                self.assertEqual(len(engine.searches), 6)
                self.assertEqual(engine.reads, [])
                self.assertTrue(all(config["metrics"]["complete_evidence_rate"] == 0 for config in report["configurations"]))
                self.assertEqual(report["native_costs"]["mean_read_calls"], 0)

    def test_unknown_hits_and_wrong_full_reads_are_failed_intents(self):
        data, bundle = fixture()
        for problem in ("unknown", "wrong-read"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as directory:
                engine = Engine("ai-memory-hybrid", bundle)
                if problem == "unknown":
                    engine.search = lambda *_: {"hit_ids": ["not-supplied"], "results": [{"id": "fake"}]}
                else:
                    engine.read = lambda _: {"result": {"body": "not the supplied page"}}
                ledger = c.reused.Ledger(Path(directory) / "attempts.jsonl")
                report = {"stage": "ai-memory-hybrid", "timing_rows": [], "configurations": []}
                try:
                    with patch.object(c, "TokenCounter", Counter), patch.object(c, "component_engine", return_value=(engine, None)):
                        with self.assertRaises(ValueError):
                            c.component(SimpleNamespace(stage="ai-memory-hybrid"), small_plan(), binding(), data,
                                bundle, report, ledger, SimpleNamespace(set_phase=lambda _: None))
                    self.assertEqual((ledger.started, ledger.finished), (1, 0))
                    self.assertTrue(engine.closed)
                finally:
                    ledger.close()
                info = c.save_ledger(Path(directory), Path(directory) / "public" / "failed")
                self.assertEqual(info["raw_sha256"], c.file_sha(Path(directory) / "attempts.jsonl"))

    def test_cost_summary_and_packing_row_tampering_fail_strict_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _ = self.run_component("ai-memory-hybrid", directory)
            changed = copy.deepcopy(report)
            changed["native_costs"]["mean_read_calls"] = 0
            with self.assertRaisesRegex(ValueError, "cost aggregation"):
                c.verify_report(changed, small_plan(), binding(), ["fixture-query-a", "fixture-query-b"])
            changed = copy.deepcopy(report)
            changed["configurations"][0]["packing_samples"][0]["row_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "packing samples"):
                c.verify_report(changed, small_plan(), binding(), ["fixture-query-a", "fixture-query-b"])

    def test_raw_summary_ledger_projection_preserves_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _ = self.run_component("claude-mem-fts", directory)
            report.update(status="failed-incomplete", validation={"passed": False, "failures": [{"check": "fixture"}]})
            prefix = Path(directory) / "claude-mem-fts"
            c.save_ledger(Path(directory), prefix)
            c.write_report(report, prefix)
            loaded = c.read_report(prefix)
            self.assertEqual(loaded, report)
            summary = json.loads(c.public_paths(prefix)[1].read_bytes())
            self.assertNotIn("attempt_states", summary)
            self.assertNotIn("packing_samples", summary["configurations"][0])
            self.assertFalse(summary["validation"]["passed"])
            c.public_paths(prefix)[2].write_bytes(gzip.compress(b"{}\n", mtime=0))
            with self.assertRaisesRegex(ValueError, "ledger bytes"):
                c.read_report(prefix)

    def test_payload_hash_removes_only_latency_and_default_gate_checks_full_payload(self):
        a = {"latency_ms": 1, "context": "same", "results": [{"id": "p", "score": 2}], "cache_hit": False}
        b = copy.deepcopy(a)
        b["latency_ms"] = 999
        self.assertEqual(c.payload_hash(a), c.payload_hash(b))
        b["results"][0]["score"] = 3
        self.assertNotEqual(c.payload_hash(a), c.payload_hash(b))
        row = {"id": "q", "payload_sha256": c.payload_hash(a)}
        config = {"budget_chars": 8000, "tokenizer": "cl100k_base", "budget_tokens": 512, "query_results": [row]}
        native = {"configurations": [config]}
        component = {"timing_rows": [{"id": "q", "repetition": 0, "book_payload_sha256": c.payload_hash(a)}]}
        reports = {"baseline-native": native, "candidate-native": copy.deepcopy(native),
                   "baseline-component": component, "candidate-component": copy.deepcopy(component)}
        self.assertTrue(c.default_equivalence(reports)["passed"])
        reports["candidate-component"]["timing_rows"][0]["book_payload_sha256"] = c.payload_hash(b)
        self.assertFalse(c.default_equivalence(reports)["passed"])

    def test_optional_gate_keeps_small_groups_but_gates_registered_large_groups(self):
        cells = [{"budget_chars": 8000, "tokenizer": encoding, "budget_tokens": cap,
            "before": {"complete_evidence_rate": .5, "evidence_recall": .7},
            "after": {"complete_evidence_rate": .5, "evidence_recall": .7},
            "unsupported_before": 0, "unsupported_after": 0,
            "by_group": {c.PRIMARY_GROUPS[0]: {"before": {"queries": 9, "complete_evidence_rate": 1., "evidence_recall": 1.},
                "after": {"queries": 9, "complete_evidence_rate": 0., "evidence_recall": 0.}}}}
            for encoding in c.ENCODINGS for cap in (512, 1024, 2048)]
        self.assertTrue(c.statistics_gate(cells)["qualified"])
        for key in ("before", "after"):
            cells[0]["by_group"][c.PRIMARY_GROUPS[0]][key]["queries"] = 10
        result = c.statistics_gate(cells)
        self.assertFalse(result["qualified"])
        self.assertEqual(len(result["losses"]), 2)
        self.assertFalse(result["individual_zero_loss_required"])

    def test_worker_requires_telemetry_optout_before_any_registration_or_data_access(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(c, "frozen_inputs") as inputs:
            with self.assertRaisesRegex(ValueError, "telemetry"):
                c.worker(SimpleNamespace())
            inputs.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"),
        "requires optional tiktoken; covered by MCP and frozen comparison jobs")
    def test_real_book_export_native_and_component_in_fresh_module_process(self):
        # A subprocess avoids imports from unrelated unit modules selecting a
        # site-packages MemoryBook before the source-provenance guard runs.
        code = r'''
from pathlib import Path
from types import SimpleNamespace
import tempfile
from scripts import round3_comparison as c
from scripts.smoke_round2_components import fixture
from tests.test_round3_comparison import finish, small_plan
data, _ = fixture()
source = c.ROOT / "src"
identity = c.source_identity(source)
binding = {"baseline": identity, "candidate": identity, "optional_project_statistics": False}
resource = SimpleNamespace(set_phase=lambda _: None)
with tempfile.TemporaryDirectory() as temporary:
 root = Path(temporary)
 exported = root / "export"
 exported.mkdir()
 args = SimpleNamespace(source=source, state=exported, bundle=root / "bundle.json")
 report = {"configurations": [], "timing_rows": []}
 c.export(args, small_plan(), binding, data, report, resource)
 import json
 bundle = json.loads(args.bundle.read_bytes())
 for stage, function in (("candidate-native", c.native), ("candidate-component", c.component)):
  state = root / stage
  state.mkdir()
  args = SimpleNamespace(stage=stage, source=source, state=state, model_dir=root / "unused",
      frozen_db=exported / "frozen.db", reference_vectors=None)
  report = {"stage": stage, "configurations": [], "timing_rows": [],
      "frozen_corpus": {key:value for key,value in bundle.items() if key not in ("documents","diagnostics")}}
  ledger_path = state / "attempts.jsonl"
  ledger = c.reused.Ledger(ledger_path)
  function(args, small_plan(), binding, data, bundle, report, ledger, resource)
  finish(report, ledger, ledger_path)
  c.verify_report(report, small_plan(), binding, [case.id for case in data.queries])
  assert ledger.finished == (12 if stage.endswith("native") else 6)
  assert len(report["configurations"]) == 6
  assert all(config["metrics"]["complete_evidence_rate"] == 1 for config in report["configurations"])
print("actual invented Book export/native/component paths passed")
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=c.ROOT,
            env={**os.environ, "PYTHONPATH": str(c.ROOT / "src"), "ORT_DISABLE_TELEMETRY": "1"},
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("paths passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
