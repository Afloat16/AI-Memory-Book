"""The formal transport gate must retain losses and reject missing evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from memory_book.mcp_server import INDEXED_REFERENCE_INSTRUCTIONS
from scripts import benchmark_indexed_references as bench


def fixture_report():
    plan = json.loads(bench.PLAN_PATH.read_text())
    binding = json.loads(bench.BINDING_PATH.read_text())
    frozen = json.loads(bench.FIXTURE_PATH.read_text())
    identities = {name: {**bench.COHORT_IDENTITIES[name], "queries": 2} for name in bench.COHORTS}
    index = {"pages": {"rows": 2, "sha256": "unchanged-index"}}
    metadata = {}
    for mode in bench.FORMATS:
        instructions = frozen["instructions"] + (INDEXED_REFERENCE_INSTRUCTIONS if mode == "indexed" else "")
        metadata[mode] = {"schema": frozen["schema"], "instructions": instructions,
            "schema_sha256": bench.sha(frozen["schema"].encode()),
            "instructions_sha256": bench.sha(instructions.encode()),
            "tokens": {encoding: {"tool_schema": 100, "instructions": 20 if mode == "objects" else 89}
                       for encoding in bench.ENCODINGS}}
    report = {"plan": plan, "plan_sha256": bench.sha(bench.PLAN_PATH.read_bytes()),
        "binding": binding, "binding_sha256": bench.sha(bench.BINDING_PATH.read_bytes()),
        "reference_report_sha256": binding["reference_report_sha256"],
        "reference_schema_sha256": metadata["objects"]["schema_sha256"],
        "reference_indexes": {name: copy.deepcopy(index) for name in bench.COHORTS},
        "expected_metadata": metadata,
        "cohorts": {name: {"sha256": identities[name]["sha256"], "queries": 2,
            "query_ids": ["q1", "q2"], "query_ids_original_order": ["q2", "q1"]} for name in bench.COHORTS},
        "workers": [], "error": None, "evaluator_unchanged": True}
    for name in bench.COHORTS:
        for repetition in range(bench.ROUNDS):
            for mode in bench.FORMATS:
                worker = {"cohort": name, "round": repetition, "format": mode,
                    "source": {"sha256": binding["runtime_source_sha256"], "provenance": {
                        "git_commit": binding["runtime_commit"], "commit_identifies_source": True}},
                    "source_sha256_after": binding["runtime_source_sha256"],
                    "dataset": {"sha256": identities[name]["sha256"], "queries": 2},
                    "indexed_content": copy.deepcopy(index), "indexed_content_after_calls": copy.deepcopy(index),
                    "archive_references": {"passed": True, "pages": 2, "references": 3,
                        "original_sha256": "all-refs", "decoded_sha256": "all-refs"},
                    "metadata": copy.deepcopy(metadata[mode]), "configurations": []}
                for budget in bench.BUDGETS:
                    for details in bench.DETAILS:
                        ids = ["q2", "q1"]
                        random.Random(61 + 1009 * repetition + budget).shuffle(ids)
                        rows = []
                        for qid in ids:
                            rows.append({"query_id": qid, "wall_ms": 2 + repetition * .1 + (.2 if mode == "indexed" else 0),
                                "payload_sha256": mode, "envelope_sha256": mode,
                                "decoded_value_sha256": qid, "context_sha256": qid,
                                "context_chars": 100, "response_utf8_bytes": 600 if mode == "objects" else 550,
                                "result_count": 1, "source_refs": 2, "arguments_sha256": qid,
                                "cache_verified_empty": True, "prior_compact_matched": None if details else True,
                                "tokens": {e: {"context": 100, "arguments": 10,
                                    "response_text": 250 if mode == "objects" else 200,
                                    "response_envelope_json": 270 if mode == "objects" else 220} for e in bench.ENCODINGS}})
                        worker["configurations"].append({"budget_chars": budget, "details": details,
                            "rows": rows, "latency": bench.latency_summary([r["wall_ms"] for r in rows])})
                report["workers"].append(worker)
    order = [(c, r, f) for r in range(bench.ROUNDS) for c in bench.COHORTS
             for f in (bench.FORMATS if r % 2 == 0 else tuple(reversed(bench.FORMATS)))]
    report["workers"].sort(key=lambda w: order.index((w["cohort"], w["round"], w["format"])))
    return report, identities


class IndexedReferenceBenchmarkTests(unittest.TestCase):
    def test_complete_fixture_and_json_key_reordering_preserve_all_cells(self):
        report, identities = fixture_report()
        with patch.object(bench, "COHORT_IDENTITIES", identities):
            self.assertTrue(bench.strict_validation(report)["passed"])
            restored = json.loads(bench.dump(report))
            self.assertEqual(bench.strict_validation(report), bench.strict_validation(restored))
            self.assertEqual(bench.comparisons(report), bench.comparisons(restored))
            self.assertEqual(len(bench.comparisons(report)), 12)

    def test_gate_rejects_missing_workers_configurations_ids_and_source(self):
        report, identities = fixture_report()
        variants = []
        changed = copy.deepcopy(report)
        changed["workers"].pop()
        variants.append(changed)
        changed = copy.deepcopy(report)
        changed["workers"][0]["configurations"].pop()
        variants.append(changed)
        changed = copy.deepcopy(report)
        changed["workers"][0]["configurations"][0]["rows"].pop()
        variants.append(changed)
        changed = copy.deepcopy(report)
        changed["workers"][0]["source_sha256_after"] = "changed"
        variants.append(changed)
        with patch.object(bench, "COHORT_IDENTITIES", identities):
            for changed in variants:
                self.assertFalse(bench.strict_validation(changed)["passed"])

    def test_gate_rejects_lost_fields_wrong_cache_bytes_and_metadata(self):
        report, identities = fixture_report()
        for field, value in (("decoded_value_sha256", "lost-field"), ("arguments_sha256", "extra-argument"),
                             ("cache_verified_empty", False), ("context_chars", 2001),
                             ("prior_compact_matched", False)):
            changed = copy.deepcopy(report)
            changed["workers"][0]["configurations"][0]["rows"][0][field] = value
            with patch.object(bench, "COHORT_IDENTITIES", identities):
                self.assertFalse(bench.strict_validation(changed)["passed"], field)
        for location, field, value in (("archive_references", "decoded_sha256", "lost-extra"),
                                       ("metadata", "instructions", "missing decoding instructions")):
            changed = copy.deepcopy(report)
            changed["workers"][0][location][field] = value
            with patch.object(bench, "COHORT_IDENTITIES", identities):
                self.assertFalse(bench.strict_validation(changed)["passed"], field)

    def test_all_first_call_losses_and_latency_regressions_are_retained(self):
        report, _ = fixture_report()
        cells = bench.comparisons(report)
        for cell in cells:
            self.assertEqual(cell["paired_samples"], 8)
            self.assertEqual(len(cell["rounds"]), 4)
            self.assertGreater(cell["indexed_latency_change_percent"]["p95_ms"], 0)
            for encoding in bench.ENCODINGS:
                costs = cell["costs"][encoding]
                self.assertEqual(costs["savings"]["response_text"]["mean"], 50)
                self.assertEqual(costs["savings"]["first_call_text"]["mean"], -19)
                self.assertEqual(costs["savings"]["later_call_text"]["mean"], 50)
                self.assertEqual(costs["outcomes"]["first_call_text"]["adds_tokens"], 8)
                self.assertEqual(costs["objects"]["first_call_text"]["mean"], 380)
                self.assertEqual(costs["indexed"]["first_call_text"]["mean"], 399)

    def test_decoder_rejects_negative_indices_or_identity_overwriting_extras(self):
        value = {"source_format": "indexed-v1", "source_sessions": [["p", "s"]],
                 "context": "original", "results": [{"id": "page", "source_refs": [[0, 4, {"start": 1}]]}]}
        self.assertEqual(bench.decode(value)["results"][0]["source_refs"],
                         [{"project": "p", "session_id": "s", "turn_index": 4, "start": 1}])
        for entry in ([-1, 4], [True, 4], [1, 4], [0, 4, {"project": "wrong"}]):
            changed = copy.deepcopy(value)
            changed["results"][0]["source_refs"] = [entry]
            with self.assertRaises(ValueError):
                bench.decode(changed)


if __name__ == "__main__":
    unittest.main()
