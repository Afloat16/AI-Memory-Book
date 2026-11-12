"""Failure gates for complete-payload, all-round performance evidence."""
import copy
import random
import unittest

from scripts.benchmark_default_recall import (BASELINE, BUDGETS, SURFACES,
    latency_summary, strict_validation)


def fixture():
    allowed = ["src/memory_book/store.py", "src/memory_book/text.py"]
    sources = {"baseline": {"git_commit": BASELINE, "sha256": "baseline-source"},
               "candidate": {"git_commit": "candidate", "sha256": "candidate-source"}}
    result = {"plan": {"cohorts": [{"name": "fixture"}], "measurement": {"rounds": 4},
                       "runtime_files_allowed": allowed, "baseline_commit": BASELINE,
                       "baseline_source_sha256": "baseline-source"},
              "sources": sources, "changed_runtime_files": allowed,
              "cohorts": {"fixture": {"sha256": "corpus", "query_ids": ["a", "b"],
                                       "query_ids_original_order": ["b", "a"]}},
              "workers": [], "evaluator_unchanged": True, "error": None}
    for repetition in range(4):
        for label in sources:
            source = sources[label]
            worker = {"label": label, "round": repetition, "cohort": "fixture",
                      "source_sha256_before": source["sha256"], "source_sha256_after": source["sha256"],
                      "source_unchanged": True, "source_provenance": {
                          "commit_identifies_source": True, "git_commit": source["git_commit"]},
                      "dataset": {"sha256": "corpus"}, "all_replayed_sessions_skipped": True,
                      "native_recall_cache_rows": 0, "indexed_content": {"pages": "same"},
                      "indexed_content_after_mcp": {"pages": "same"},
                      "fresh_ingestion_results_sha256": "same", "unchanged_reingestion_results_sha256": "same",
                      "mcp_tool_schema_sha256": "schema", "mcp_initialization_tokens": {"encoding": 20},
                      "configurations": []}
            for surface in SURFACES:
                for budget in BUDGETS:
                    ids = ["b", "a"]
                    random.Random(61 + 1009 * repetition + budget).shuffle(ids)
                    rows = [{"query_id": qid, "wall_ms": 1 + repetition / 10,
                             "cache_verified_empty": True, "context_chars": 10,
                             "payload_sha256": surface + str(budget) + qid,
                             "context_sha256": "same-context"} for qid in ids]
                    worker["configurations"].append({"surface": surface, "budget_chars": budget,
                        "rows": rows, "latency": latency_summary([r["wall_ms"] for r in rows])})
            result["workers"].append(worker)
    return result


class CompleteMeasurementGateTests(unittest.TestCase):
    def test_complete_balanced_matrix_and_repeated_payloads_pass(self):
        gate = strict_validation(fixture())
        self.assertTrue(gate["passed"], gate)
        self.assertEqual(gate["timed_calls"], 96)
        self.assertEqual(gate["unique_payload_pairs_per_surface"], 6)

    def test_missing_or_duplicate_round_cannot_pass(self):
        for mutate in (lambda r: r["workers"].pop(),
                       lambda r: r["workers"].append(copy.deepcopy(r["workers"][0]))):
            report = fixture()
            mutate(report)
            self.assertFalse(strict_validation(report)["passed"])

    def test_metadata_payload_change_fails_even_when_context_is_unchanged(self):
        report = fixture()
        report["workers"][-1]["configurations"][0]["rows"][0]["payload_sha256"] = "different-metadata"
        self.assertFalse(strict_validation(report)["passed"])

    def test_query_drop_order_cache_or_index_mutation_fails(self):
        mutations = [
            lambda w: w["configurations"][0]["rows"].pop(),
            lambda w: w["configurations"][0]["rows"].reverse(),
            lambda w: w["configurations"][0]["rows"][0].update(cache_verified_empty=False),
            lambda w: w.update(indexed_content_after_mcp={"pages": "changed"}),
            lambda w: w["configurations"][0]["latency"].update(p95_ms=0),
        ]
        for mutate in mutations:
            report = fixture()
            mutate(report["workers"][-1])
            self.assertFalse(strict_validation(report)["passed"])

    def test_uncommitted_changed_source_or_partial_evaluator_fails(self):
        for key, value in (("source_unchanged", False), ("source_sha256_after", "changed")):
            report = fixture()
            report["workers"][-1][key] = value
            self.assertFalse(strict_validation(report)["passed"])
        report = fixture()
        report["evaluator_unchanged"] = False
        self.assertFalse(strict_validation(report)["passed"])


if __name__ == "__main__":
    unittest.main()
