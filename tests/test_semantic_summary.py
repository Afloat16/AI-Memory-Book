"""Preparation accounting must not erase the costs of interrupted processes."""

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.summarize_semantic_completion import load_reports, preparation_costs


def report():
    return {"preparation": {
        "ingestion_ms": 10.0,
        "semantic_index": {"model_load_ms": 20.0, "build_ms": 30.0,
                           "pages": 4, "windows": 6, "vector_bytes": 9216},
        "engine_stats": {"database_bytes": 65536}},
        "process_segments": [{"started_at": "start", "finished_at": "end"}],
        "preparation_attempts": [{"status": "completed"}],
        "preserved_incomplete_attempts": []}


class SemanticSummaryTests(unittest.TestCase):
    def test_fresh_run_reports_only_the_measured_preparation_phases(self):
        result = preparation_costs(report())
        self.assertEqual(result["known_preparation_ms"], 60.0)
        self.assertEqual(result["resumed_model_load_ms"], 0)
        self.assertEqual(result["resumed_model_loads"], 0)
        self.assertFalse(result["has_unknown_interrupted_costs"])

    def test_recovery_keeps_each_reload_and_unknown_attempt_cost(self):
        value = report()
        value["process_segments"] = [
            {"started_at": "interrupted-start"},
            {"started_at": "resumed", "finished_at": "finished", "resumed_model_load_ms": 15.0},
            {"started_at": "resumed-again", "finished_at": "finished-again", "resumed_model_load_ms": 7.0}]
        value["preparation_attempts"].insert(0, {"status": "interrupted"})
        value["preserved_incomplete_attempts"] = [{"status": "interrupted", "elapsed_ms": None}]
        result = preparation_costs(value)
        self.assertEqual(result["known_preparation_ms"], 82.0)
        self.assertEqual(result["resumed_model_load_ms"], 22.0)
        self.assertEqual(result["resumed_model_loads"], 2)
        self.assertEqual(result["unknown_preparation_attempts"], 1)
        self.assertEqual(result["unfinished_process_segments"], 1)
        self.assertEqual(result["preserved_incomplete_attempts"], 1)
        self.assertTrue(result["has_unknown_interrupted_costs"])

    def test_separate_host_metadata_is_allowed_but_engine_changes_are_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "benchmarks/results"
            output.mkdir(parents=True)
            config = {"budget_chars": 8000, "budget_tokens": 512, "tokenizer": "cl100k_base", "limit": 5}
            cohorts = [{"label": name, "sha256": name, "queries": 1} for name in ("one", "two")]
            plan = {"cohorts": cohorts, "parameters": {
                "budget_chars": 8000, "token_budgets": [512], "tokenizers": ["cl100k_base"],
                "limit": 5, "repeats": 3}}
            (root / "benchmarks/semantic-final-plan.json").write_text(json.dumps(plan))

            def write(name, source="same-engine"):
                value = {"validation": {"passed": True}, "completed_samples": 6,
                         "dataset": {"sha256": name, "queries": 1},
                         "identity": {"runtime_source_sha256": source, "evaluator_files": {},
                                      "model": {}, "configurations": [config], "repeats": 3,
                                      "runtime": {"platform": name}}}
                raw = json.dumps(value).encode()
                (output / ("semantic-final-" + name + ".json.gz")).write_bytes(gzip.compress(raw))
                (output / ("semantic-final-" + name + ".summary.json")).write_text(
                    json.dumps({"full_report_sha256": hashlib.sha256(raw).hexdigest()}))

            write("one")
            write("two")
            _, results, missing = load_reports(root)
            self.assertEqual(len(results), 2)
            self.assertEqual(missing, [])
            write("two", "changed-engine")
            with self.assertRaisesRegex(ValueError, "runtime_source_sha256"):
                load_reports(root)


if __name__ == "__main__":
    unittest.main()
